"""Shared local pipeline orchestration; neither CLI nor HTTP imports Qt."""
from __future__ import annotations

import json
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path
from threading import Event
from typing import Callable, Sequence

from chapters import NormalizeOptions, build_patterns, detect_headers_in_text, normalize_chapters
from config.settings import Settings
from media.artifacts import atomic_write_text, require_artifact_root, slugify_job_name
from media.groups import (
    GROUPING_METHOD_DETECTED, GROUPING_METHOD_NUMERIC, analyze_grouping,
    delete_group, preview_groups, write_groups,
)
from pipeline.document import PipelineDocument, PipelineStateError, StageKey
from pipeline.loader import insert_missing_headers, load_paths
from pipeline.sessions import SessionStore, missing_artifacts

# Match desktop sessions: account configuration and preferences stay global.
GLOBAL_SETTINGS = {
    "youtube_client_secrets_path", "title_history", "youtube_title_tags", "window_geometry",
    "font_size", "max_log_lines", "last_input_dir",
}


def load_document(paths: Sequence[str], settings: Settings, *, sort_mode: str = "natural"):
    """Load the same ordered, decoded input used by the desktop window."""
    if not paths:
        raise PipelineStateError("Select at least one TXT or ZIP input.")
    if sort_mode not in {"natural", "selection", "name"}:
        raise ValueError("Unknown input ordering.")
    result = load_paths(paths, chain=settings.encoding_chain, sort_mode=sort_mode)
    if settings.auto_insert_headers:
        patterns = build_patterns(settings)

        def header_numbers(text):
            return [item[1] for item in detect_headers_in_text(text, patterns)]

        result.files, inserted = insert_missing_headers(
            result.files, has_header=lambda text: bool(header_numbers(text)),
            prefix=settings.auto_insert_prefix, continuous=settings.continuous_numbering,
            detect_max_number=lambda text: max(header_numbers(text), default=None),
        )
        result.diagnostics.extend(inserted)
    document = PipelineDocument()
    first = Path(paths[0]).expanduser().resolve()
    document.load_original_input(
        result.text, source_path=str(first),
        input_directory=str(first if first.is_dir() else first.parent),
    )
    document.source_files = result.files
    document.source_encoding = ", ".join(result.encodings_used)
    document.entry_names = [source.name for source in result.files]
    document.merge_order = list(document.entry_names)
    document.diagnostics.extend(result.diagnostics)
    document.set_job_identity(first.stem or "Novel Title", "")
    return document, result


def normalize_document(document: PipelineDocument, settings: Settings):
    """Commit canonical normalization or withdraw a failed previous result."""
    if not document.original_input_text:
        raise PipelineStateError("No text loaded. Load files first.")
    try:
        chapters, report, diagnostics = normalize_chapters(
            document.original_input_text, build_patterns(settings),
            NormalizeOptions.from_settings(settings), source_name="merged",
        )
        document.set_normalized_output(chapters)
        document.diagnostics.extend(diagnostics)
        document.stage(StageKey.NORMALIZE).touch(
            f"{len(document.source_files)} sources", f"{len(chapters)} chapters", report.to_dict(),
        )
        return report
    except Exception as error:
        document.normalized_text = None
        document.cleaned_text = None
        document.filtered_output = None
        document.chunks = []
        document.stage(StageKey.NORMALIZE).fail(str(error))
        raise


class PipelineService:
    """One workspace. Callers serialize mutation and publish completed snapshots."""

    def __init__(self, settings=None, document=None):
        self.settings = settings if settings is not None else Settings.load()
        self.document = document if document is not None else PipelineDocument()
        self.sessions = SessionStore()
        self.session_id = None
        self.ui_state = {}

    def preview_grouping(self, size=20):
        text, source = self.document.grouping_input_text()
        empty = {
            "headings": [], "groups": [], "warnings": [], "requires_numeric_boundaries": False,
            "numeric_available": False, "confirmation_fingerprint": "", "source": source,
        }
        if not text:
            return empty
        try:
            analysis = analyze_grouping(text, self.settings, size)
            method = GROUPING_METHOD_NUMERIC if analysis.requires_numeric_boundaries else GROUPING_METHOD_DETECTED
            groups = []
            if not analysis.numeric_unavailable_reason:
                _, groups, _ = preview_groups(text, self.settings, size, method=method)
            return {
                **empty, "headings": [asdict(row) for row in analysis.headings], "groups": groups,
                "warnings": analysis.diagnostics, "requires_numeric_boundaries": analysis.requires_numeric_boundaries,
                "numeric_available": bool(analysis.numeric_groups),
                "confirmation_fingerprint": analysis.numeric_identity_fingerprint,
                "error": analysis.numeric_unavailable_reason,
            }
        except (PipelineStateError, ValueError) as error:
            return {**empty, "error": str(error)}

    def snapshot(self):
        document = self.document
        text, _ = document.grouping_input_text()
        groups = []
        for group in document.chapter_groups:
            row = asdict(group)
            folder = Path(group.output_dir)
            try:
                plan = json.loads((folder / "tts_chunks.json").read_text(encoding="utf-8"))
                if isinstance(plan, dict) and plan.get("group_id") == group.group_id:
                    row["state"]["tts_plan"] = plan
            except (OSError, ValueError):
                pass
            from media.youtube import load_upload_state
            try:
                row["state"]["youtube"] = load_upload_state(folder)
            except (RuntimeError, ValueError):
                # Invalid saved recovery state is visible, never implicitly trusted.
                row["state"]["youtube"] = {"status": "Invalid", "error": "Invalid saved upload state."}
            groups.append(row)
        size = self.ui_state.get("web_group_size", document.grouping_config.get("chapters_per_group", 20))
        return {
            "title": document.job_title, "source_path": document.source_path,
            "input_directory": document.input_directory,
            "original_text": document.original_input_text, "normalized_text": document.normalized_text,
            "youtube_tags": {
                "current": self.settings.tags_for_uploaded_title(document.job_title),
                "history": dict(self.settings.youtube_title_tags),
            },
            "text": text, "chapters": [row.to_dict() for row in document.chapters],
            "sources": [row.to_dict() for row in document.source_files], "groups": groups,
            "stages": {key: value.to_dict() for key, value in document.stage_status.items()},
            "diagnostics": [row.to_dict() for row in document.diagnostics],
            "grouping": self.preview_grouping(size), "outputs": self.output_files(),
            "session_id": self.session_id, "ui_state": dict(self.ui_state),
            "missing_artifacts": missing_artifacts(document),
        }

    def output_files(self):
        """Only explicitly registered job/preview/export files are downloadable."""
        document = self.document
        candidates = set()

        def add(path, root=None):
            path = Path(path)
            actual = path.resolve()
            if (root is None or actual.is_relative_to(Path(root).resolve())) and actual.is_file():
                candidates.add(actual)

        if document.group_manifest_path:
            path = Path(document.group_manifest_path)
            add(path, path.parent)
        for group in document.chapter_groups:
            root = Path(group.output_dir)
            for name in ("final.txt", "final.json", "tts_chunks.json", "tts_overrides.json", "job_state.json",
                         "youtube_upload.json", "thumbnail.jpg", "audiobook.mp3", "video_timeline.json",
                         "visuals.json", f"{group.slug}.mp4"):
                add(root / name, root)
            for directory, suffixes in (("audio_chunks", {".mp3", ".json"}),
                                        ("render_pages", {".png", ".json"}),
                                        ("visuals", {".png", ".jpg", ".jpeg", ".webp", ".bmp"})):
                for path in (root / directory).glob("*"):
                    if path.suffix.lower() in suffixes and not path.name.startswith("."):
                        add(path, root)
        if document.step3_artifacts:
            bundle = document.step3_artifacts
            for path in (bundle.txt_path, bundle.json_path, document.thumbnail_path, document.audiobook_path,
                         document.video_path):
                if path:
                    add(path, bundle.output_dir)
        for value in document.metadata.get("web_outputs", []):
            add(value)
        outputs = []
        for path in sorted(candidates):
            try:
                outputs.append({"path": str(path), "name": path.name, "size": path.stat().st_size})
            except OSError:
                continue
        return outputs

    def update_settings(self, data):
        from config.validation import validate_settings
        settings = validate_settings({**self.settings.to_dict(), **data})
        path = getattr(self.settings, "_loaded_config_path", None)
        settings.save(path)
        if path is not None:
            settings._loaded_config_path = path
        self.settings = settings
        return settings.to_dict()

    def save_session(self, ui=None):
        if ui is not None:
            self.ui_state = dict(ui)
        values = {key: value for key, value in self.settings.to_dict().items() if key not in GLOBAL_SETTINGS}
        self.session_id = self.sessions.save(self.document, values, self.ui_state, self.session_id)
        return self.session_id

    def open_session(self, session_id):
        document, values, ui = self.sessions.load(session_id)
        if self.document.original_input_text or self.document.chapter_groups:
            self.save_session()
        merged = self.settings.to_dict()
        merged.update({key: value for key, value in values.items() if key not in GLOBAL_SETTINGS})
        path = getattr(self.settings, "_loaded_config_path", None)
        self.settings = Settings.from_dict(merged)
        if path is not None:
            self.settings._loaded_config_path = path
        self.document, self.ui_state, self.session_id = document, ui, session_id
        return self.snapshot()

    def new_session(self):
        if self.document.original_input_text or self.document.chapter_groups:
            self.save_session()
        self.document, self.ui_state, self.session_id = PipelineDocument(), {}, None
        return self.snapshot()

    def perform(self, action: str, options: dict, *, cancel_event: Event, progress: Callable):
        if cancel_event.is_set():
            return {"cancelled": True}
        progress(0, 1, action)
        if action == "import":
            document, loaded = load_document(options.get("paths", []), self.settings,
                                             sort_mode=options.get("sort_mode", "natural"))
            if not document.original_input_text:
                details = "; ".join(row.message for row in loaded.diagnostics)
                raise PipelineStateError("No readable text in selected inputs." + (" " + details if details else ""))
            if cancel_event.is_set():
                return {"cancelled": True}
            if self.document.original_input_text or self.document.chapter_groups:
                self.save_session()
            self.document, self.session_id, self.ui_state = document, None, {}
            self.settings.last_input_dir = document.input_directory
            self.settings.save(getattr(self.settings, "_loaded_config_path", None))
            result = {"summary": loaded.summary()}
        elif action == "normalize":
            report = normalize_document(self.document, self.settings)
            result = {"report": report.to_dict()}
        elif action == "edit":
            if self.document.normalized_text is None:
                raise PipelineStateError("Normalize input before editing its output.")
            text = options.get("text")
            if not isinstance(text, str):
                raise ValueError("Edited text must be a string.")
            self.document.set_normalized_edit(text)
            from pipeline.document import derive_chapters_from_text
            self.document.chapters = derive_chapters_from_text(text, build_patterns(self.settings))
            result = {"revision": self.document.normalized_revision}
        elif action == "group":
            size = options.get("size", 20)
            groups = write_groups(
                self.document, self.settings, options.get("title", self.document.job_title), size,
                method=options.get("method", GROUPING_METHOD_DETECTED),
                confirmation_fingerprint=options.get("confirmation_fingerprint", ""),
            )
            self.ui_state["web_group_size"] = size
            self.document.stage(StageKey.CLEAN_CHUNK).touch("Current text", f"{len(groups)} groups")
            title = self.document.job_title
            self.settings.title_history = [title, *[item for item in self.settings.title_history if item != title]]
            self.settings.save(getattr(self.settings, "_loaded_config_path", None))
            result = {"group_ids": [group.group_id for group in groups]}
        elif action == "delete_group":
            delete_group(self.document, options.get("group_id", ""))
            result = {}
        elif action == "export":
            result = self._export(options.get("format", "txt"))
        else:
            from pipeline.media_service import MEDIA_ACTIONS, execute_media
            if action not in MEDIA_ACTIONS:
                raise ValueError(f"Unknown pipeline action: {action}")
            result = execute_media(action, self.document, self.settings, options,
                                   cancel_event=cancel_event, progress=progress)
            if action == "preview" and result.get("path"):
                outputs = self.document.metadata.setdefault("web_outputs", [])
                path = str(Path(result["path"]).resolve())
                if path not in outputs:
                    outputs.append(path)
        if not result.get("cancelled"):
            progress(1, 1, "Đã hoàn thành" if result.get("status") != "partial" else "Một số nhóm thất bại")
        return result

    def _export(self, format):
        text = self.document.require_grouping_input()
        if format not in {"txt", "json", "zip"}:
            raise ValueError("Export format must be txt, json or zip.")
        root = require_artifact_root(self.settings, self.document.input_directory)
        folder = root / slugify_job_name(self.document.job_title or "Novel", "").rstrip("_") / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            filename = self.settings.filename_template.format(tag="export").strip() or "novel_export"
        except (KeyError, IndexError, ValueError):
            filename = "novel_export"
        if Path(filename).suffix.lower() in {".txt", ".json", ".zip"}:
            filename = str(Path(filename).with_suffix(""))
        filename = slugify_job_name(filename, "").rstrip("_")
        path = folder / f"{filename}.{format}"
        if format == "txt":
            atomic_write_text(path, text, encoding=self.settings.export_encoding)
        elif format == "json":
            payload = {
                "text": text, "chapters": [c.to_dict() for c in self.document.chapters],
                "chunks": [c.to_dict() for c in self.document.chunks],
                "summary": self.document.summary(),
                "diagnostics": [d.to_dict() for d in self.document.diagnostics],
            }
            atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding=self.settings.export_encoding)
        else:
            self.document.require_chapter_groups()
            with tempfile.NamedTemporaryFile(prefix=f".{filename}-", suffix=".zip", dir=folder, delete=False) as handle:
                temporary = Path(handle.name)
            try:
                with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                    for group in self.document.chapter_groups:
                        if self.settings.zip_folder_per_range:
                            archive.write(group.txt_path, f"{group.slug}/final.txt")
                            archive.write(group.json_path, f"{group.slug}/final.json")
                        else:
                            archive.write(group.txt_path, f"{group.slug}.txt")
                            archive.write(group.json_path, f"{group.slug}.json")
                    if self.settings.zip_include_manifest:
                        archive.write(self.document.group_manifest_path, "chapter_groups.json")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        outputs = self.document.metadata.setdefault("web_outputs", [])
        if str(path.resolve()) not in outputs:
            outputs.append(str(path.resolve()))
        return {"path": str(path.resolve())}

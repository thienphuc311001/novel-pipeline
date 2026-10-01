"""Versioned, atomic session snapshots. Media stays in its existing job folder."""
from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from config.settings import config_dir
from media.artifacts import atomic_write_json
from pipeline.document import (
    Chapter, Chunk, Diagnostic, PipelineDocument, SourceFile, StageStatus,
    Step3ArtifactBundle,
)


class SessionError(RuntimeError):
    pass


def document_to_dict(document):
    result = {}
    for name in vars(PipelineDocument()):
        value = getattr(document, name)
        if name == "source_bytes":
            value = base64.b64encode(value).decode("ascii")
        elif name == "stage_status":
            value = {key: asdict(row) for key, row in value.items()}
        elif name == "step3_artifacts":
            value = asdict(value) if value else None
        elif name in {"source_files", "chapters", "chunks", "diagnostics", "chapter_groups", "deleted_chapter_groups"}:
            value = [asdict(row) for row in value]
        result[name] = value
    return result


def document_from_dict(data):
    from media.groups import ChapterGroup

    if not isinstance(data, dict):
        raise ValueError("Invalid document")
    document = PipelineDocument()
    classes = {"source_files": SourceFile, "chapters": Chapter, "chunks": Chunk,
               "diagnostics": Diagnostic, "chapter_groups": ChapterGroup,
               "deleted_chapter_groups": ChapterGroup}
    for name, default in vars(document).copy().items():
        if name not in data:
            continue
        value = data[name]
        if name == "source_bytes":
            value = base64.b64decode(value, validate=True)
        elif name in classes:
            value = [classes[name](**row) for row in value]
        elif name == "stage_status":
            value = {key: StageStatus(**row) for key, row in value.items()}
            value = {**document.stage_status, **value}
        elif name == "step3_artifacts":
            value = Step3ArtifactBundle(**value) if value is not None else None
        elif default is not None and not isinstance(value, type(default)):
            raise ValueError(f"Invalid document field: {name}")
        elif name in {"normalized_text", "cleaned_text", "filtered_output"} and value is not None and not isinstance(value, str):
            raise ValueError(f"Invalid text field: {name}")
        setattr(document, name, value)
    return document


class SessionStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else config_dir() / "sessions"

    def _path(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise SessionError("Mã phiên làm việc không hợp lệ.")
        return self.root / f"{session_id}.json"

    def save(self, document, settings, ui, session_id=None):
        session_id = session_id or uuid.uuid4().hex
        try:
            payload = {
                "schema_version": 1, "id": session_id,
                "title": document.job_title or Path(document.source_path).stem or "Phiên chưa đặt tên",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "document": document_to_dict(document), "settings": settings, "ui": ui,
            }
            atomic_write_json(self._path(session_id), payload)
        except (OSError, TypeError, ValueError) as error:
            raise SessionError(f"Không lưu được phiên làm việc: {error}") from error
        return session_id

    def load(self, session_id):
        try:
            payload = json.loads(self._path(session_id).read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1 or payload.get("id") != session_id:
                raise ValueError("Unsupported session format")
            if not isinstance(payload.get("settings"), dict) or not isinstance(payload.get("ui"), dict):
                raise ValueError("Invalid settings or UI state")
            ui = payload["ui"]
            for name in ("tab", "group_size", "custom_size"):
                if name in ui and not isinstance(ui[name], int):
                    raise ValueError("Invalid saved page")
            for name in ("panels", "upload_titles", "upload_metadata", "group_upload_metadata"):
                if name in ui and not isinstance(ui[name], dict):
                    raise ValueError("Invalid saved controls")
            for name in ("cover_image", "qr_image"):
                if name in ui and not isinstance(ui[name], str):
                    raise ValueError("Invalid image path")
            for key in ("upload_metadata", "group_upload_metadata"):
                row = ui.get(key, {})
                for name in ("title", "description", "category_id", "privacy"):
                    if name in row and not isinstance(row[name], str):
                        raise ValueError("Invalid upload draft")
                for name in ("playlist_id", "publish_at"):
                    if row.get(name) is not None and not isinstance(row[name], str):
                        raise ValueError("Invalid upload draft")
                if not isinstance(row.get("tags", []), list) or any(not isinstance(tag, str) for tag in row.get("tags", [])):
                    raise ValueError("Invalid upload tags")
            for row in ui.get("panels", {}).values():
                if not isinstance(row, dict) or not isinstance(row.get("checked", []), list):
                    raise ValueError("Invalid group selection")
            document = document_from_dict(payload["document"])
            from media.groups import load_job_state
            saved_at = datetime.fromisoformat(payload["updated_at"]).timestamp()
            for group in document.chapter_groups:
                state_path = Path(group.output_dir) / "job_state.json"
                if state_path.is_file() and state_path.stat().st_mtime > saved_at:
                    latest = load_job_state(group)
                    if latest:
                        group.state = latest
            return document, payload["settings"], payload["ui"]
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise SessionError(f"Không mở được phiên làm việc: {error}") from error

    def list_sessions(self):
        result = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("schema_version") != 1 or payload.get("id") != path.stem:
                    continue
                self._path(path.stem)
                result.append({"id": path.stem, "title": str(payload["title"]),
                               "updated_at": str(payload["updated_at"]),
                               "step": max(1, min(5, int(payload["ui"].get("tab", 0)) + 1))})
            except (OSError, ValueError, TypeError, KeyError, AttributeError, SessionError):
                continue
        return sorted(result, key=lambda row: row["updated_at"], reverse=True)


def missing_artifacts(document):
    """Report missing references without trusting them as usable stage outputs."""
    paths = [document.group_manifest_path, document.thumbnail_path, document.audiobook_path,
             document.video_path, document.tts_manifest_path]
    if document.step3_artifacts:
        paths.extend([document.step3_artifacts.txt_path, document.step3_artifacts.json_path])
    for group in document.chapter_groups:
        paths.extend([group.txt_path, group.json_path])
        for name in ("thumbnail", "audiobook", "video", "cover", "qr"):
            row = group.state.get(name)
            if isinstance(row, dict):
                paths.append(row.get("path", ""))
    return [path for path in dict.fromkeys(paths) if path and not Path(path).is_file()]

"""The in-memory pipeline document shared by every stage.

Each stage receives a :class:`PipelineDocument` and returns a new one.  Nothing
in the pipeline ever requires the user to save a temporary file in order to
continue: intermediate results live in memory only.
"""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


class Severity:
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    ORDER = {INFO: 0, WARNING: 1, ERROR: 2}


@dataclass
class Diagnostic:
    """A single reportable event produced by a stage."""

    code: str
    severity: str = Severity.INFO
    chapter: Optional[int] = None
    line: Optional[int] = None
    message: str = ""
    detail: str = ""
    snippet: str = ""
    stage: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "chapter": self.chapter,
            "line": self.line,
            "message": self.message,
            "detail": self.detail,
            "snippet": self.snippet,
            "stage": self.stage,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Diagnostic":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def describe(self) -> str:
        where = []
        if self.chapter is not None:
            where.append(f"chương {self.chapter}")
        if self.line is not None:
            where.append(f"dòng {self.line}")
        location = f" [{', '.join(where)}]" if where else ""
        detail = f" - {self.detail}" if self.detail else ""
        return f"{self.severity.upper()}: {self.code}{location}: {self.message}{detail}"


@dataclass
class SourceFile:
    """One input file or archive entry that contributed to the document."""

    name: str
    path: str = ""
    origin: str = ""  # "" | archive name
    encoding: str = ""
    char_count: int = 0
    text: str = ""
    order: int = 0
    injected_header: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "origin": self.origin,
            "encoding": self.encoding,
            "char_count": self.char_count,
            "order": self.order,
            "injected_header": self.injected_header,
        }


@dataclass
class Chapter:
    number: int
    header_line: str = ""
    title: str = ""
    text: str = ""
    char_count: int = 0
    source_line: int = 0
    source_name: str = ""
    language: str = "vi"
    raw_header: str = ""
    duplicates_removed: int = 0
    text_loss: int = 0

    def body(self, include_header: bool = True) -> str:
        if include_header and self.header_line:
            return f"{self.header_line}\n{self.text}".strip()
        return self.text

    def display_title(self) -> str:
        if self.title:
            return self.title
        return self.header_line or f"Chương {self.number}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "header_line": self.header_line,
            "title": self.title,
            "text": self.text,
            "char_count": self.char_count,
            "source_line": self.source_line,
            "source_name": self.source_name,
            "language": self.language,
            "raw_header": self.raw_header,
            "duplicates_removed": self.duplicates_removed,
            "text_loss": self.text_loss,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chapter":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Chunk:
    chapter: int
    index: int
    order: int
    text: str
    char_count: int = 0
    chapter_title: str = ""
    hard_split: bool = False
    part: int = 1
    parts: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter": self.chapter,
            "index": self.index,
            "order": self.order,
            "char_count": self.char_count,
            "chapter_title": self.chapter_title,
            "hard_split": self.hard_split,
            "part": self.part,
            "parts": self.parts,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chunk":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Step3ArtifactBundle:
    """The immutable-on-disk bundle materialized by Step 3.

    The strings stay in :class:`PipelineDocument`; this object only records the
    exact files that represent that state and the fingerprints needed to reject
    stale or manually modified files before Step 4 consumes them.
    """

    title: str
    chapter: str
    slug: str
    output_dir: str
    txt_path: str
    json_path: str
    source_revision: int
    text_sha256: str
    chunks_sha256: str
    txt_sha256: str
    json_sha256: str
    chunk_count: int
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "chapter": self.chapter,
            "slug": self.slug,
            "output_dir": self.output_dir,
            "txt_path": self.txt_path,
            "json_path": self.json_path,
            "source_revision": self.source_revision,
            "text_sha256": self.text_sha256,
            "chunks_sha256": self.chunks_sha256,
            "txt_sha256": self.txt_sha256,
            "json_sha256": self.json_sha256,
            "chunk_count": self.chunk_count,
            "config": dict(self.config),
        }


@dataclass
class Step4MediaBundle:
    """Validated media inputs that Step 5 is allowed to consume."""

    title: str
    chapter: str
    slug: str
    output_dir: str
    thumbnail_path: str
    audiobook_path: str
    video_path: str
    thumbnail_fingerprint: Dict[str, Any]
    audiobook_fingerprint: Dict[str, Any]


@dataclass
class Step5UploadBundle:
    """Current generated video and thumbnail that Step 6 may upload."""

    title: str
    chapter: str
    output_dir: str
    video_path: str
    thumbnail_path: str
    video_fingerprint: Dict[str, Any]
    thumbnail_fingerprint: Dict[str, Any]


@dataclass
class StageStatus:
    key: str
    name: str
    ran: bool = False
    ok: bool = False
    input_summary: str = ""
    result_summary: str = ""
    counts: Dict[str, Any] = field(default_factory=dict)
    ran_at: float = 0.0
    duration: float = 0.0
    error: str = ""

    def touch(self, input_summary: str, result_summary: str, counts: Dict[str, Any] | None = None) -> None:
        self.ran = True
        self.ok = True
        self.input_summary = input_summary
        self.result_summary = result_summary
        self.counts = counts or {}
        self.ran_at = time.time()

    def fail(self, message: str) -> None:
        self.ran = True
        self.ok = False
        self.error = message
        self.ran_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "ran": self.ran,
            "ok": self.ok,
            "input_summary": self.input_summary,
            "result_summary": self.result_summary,
            "counts": self.counts,
            "ran_at": self.ran_at,
            "duration": self.duration,
            "error": self.error,
        }


class StageKey:
    NORMALIZE = "normalize"
    CHINESE = "chinese"
    CLEAN_CHUNK = "clean_chunk"
    FILTER_EXPORT = "filter_export"
    VIDEO = "video"
    YOUTUBE = "youtube"

    ORDER = [NORMALIZE, CHINESE, CLEAN_CHUNK, FILTER_EXPORT, VIDEO, YOUTUBE]
    NAMES = {
        NORMALIZE: "Chuẩn hoá chương",
        CHINESE: "Duyệt & dịch Trung",
        CLEAN_CHUNK: "Làm sạch & chia đoạn",
        FILTER_EXPORT: "Thumbnail & audiobook",
        VIDEO: "Tạo video",
        YOUTUBE: "Tải lên YouTube",
    }


def _blank_span(text: str) -> Dict[str, int]:
    return {"chars": len(text), "lines": text.count("\n") + 1 if text else 0}


class PipelineStateError(RuntimeError):
    """Raised when a stage transition would violate pipeline provenance."""


def render_chapters_text(chapters: Sequence[Chapter], *, chapter_separator: str = "\n\n\n") -> str:
    """Render normalized chapters to the in-memory clean-text representation.

    This is intentionally the same header/body shape used by the clean TXT
    exporter, but it never touches the filesystem.  Keeping this conversion in
    the pipeline model gives Step 2 one exact upstream string to consume.
    """
    parts: List[str] = []
    for chapter in chapters:
        if chapter.header_line:
            parts.append(chapter.header_line)
            parts.append("\n\n")
        body = (chapter.text or "").strip()
        if body:
            parts.append(body)
            parts.append(chapter_separator)
    return "".join(parts).rstrip() + "\n" if parts else ""


def derive_chapters_from_text(text: str, pattern_set: Any, *, source_name: str = "pipeline") -> List[Chapter]:
    """Build chapter views from a later-stage text without normalizing it.

    Step 3 needs chapter boundaries for chunking, but it must not rerun Step 1
    and silently alter a user-edited or translated Step 2 string.  Detection is
    therefore used only as a lossless structural view here.
    """
    if not text:
        return []
    from chapters.detector import detect_chapters

    hits, _preamble, _notes = detect_chapters(text, pattern_set, source_name=source_name)
    return [
        Chapter(
            number=hit.number,
            header_line=hit.header_line,
            title=hit.title,
            text=hit.body,
            char_count=len(hit.body),
            source_line=hit.line_index + 1,
            source_name=source_name,
            language=hit.language,
            raw_header=hit.raw_line,
        )
        for hit in hits
    ]


class PipelineDocument:
    """Mutable working document shared by every pipeline stage."""

    def __init__(self) -> None:
        self.source_bytes: bytes = b""
        self.source_path: str = ""
        self.input_directory: str = ""
        self.source_files: List[SourceFile] = []
        self.source_encoding: str = ""
        self.entry_names: List[str] = []
        self.merge_order: List[str] = []
        # Explicit stage-to-stage text.  ``None`` means that stage has not
        # produced an output yet; an empty string is still a real output.
        self.original_input_text: str = ""
        self.normalized_text: Optional[str] = None
        self.chinese_review_text: Optional[str] = None
        self.step2_confirmed_output: Optional[str] = None
        self.chinese_review_session: Optional[Any] = None
        self._chinese_review_source_text: Optional[str] = None
        self.normalized_revision: int = 0
        self.step2_revision: int = 0
        self.cleaned_text: Optional[str] = None
        # Step 3/4/5/6 job state is intentionally distinct from the text stages.
        # Existing files are never deleted by invalidation; only the in-memory
        # authority to use them is withdrawn.
        self.job_title: str = ""
        self.job_chapter: str = ""
        self.step3_artifacts: Optional[Step3ArtifactBundle] = None
        self.thumbnail_path: str = ""
        self.thumbnail_fingerprint: Dict[str, Any] = {}
        self.audio_chunks_dir: str = ""
        self.audiobook_path: str = ""
        self.audiobook_fingerprint: Dict[str, Any] = {}
        self.tts_manifest_path: str = ""
        self.tts_failures: List[Dict[str, Any]] = []
        self.video_path: str = ""
        self.video_fingerprint: Dict[str, Any] = {}
        self.video_metadata: Dict[str, Any] = {}
        self._video_source_fingerprint: Dict[str, Any] = {}
        self.youtube_upload_state: Dict[str, Any] = {}
        self.filtered_output: Optional[str] = None
        self.text: str = ""
        # Kept for compatibility with older callers.  It is never used to
        # select a downstream stage input.
        self.original_text: str = ""
        self.preamble: str = ""
        self.chapters: List[Chapter] = []
        self.chunks: List[Chunk] = []
        self.translations: Dict[str, str] = {}
        self.translation_meta: Dict[str, Dict[str, Any]] = {}
        self.diagnostics: List[Diagnostic] = []
        self.stage_status: Dict[str, StageStatus] = {
            key: StageStatus(key=key, name=StageKey.NAMES[key]) for key in StageKey.ORDER
        }
        self.generated_headers: List[Dict[str, Any]] = []
        self.selection: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.notes: List[str] = []

    # ------------------------------------------------------------- basics
    def clone(self) -> "PipelineDocument":
        clone = PipelineDocument()
        clone.source_bytes = self.source_bytes
        clone.source_path = self.source_path
        clone.input_directory = self.input_directory
        clone.source_encoding = self.source_encoding
        clone.entry_names = list(self.entry_names)
        clone.merge_order = list(self.merge_order)
        clone.original_input_text = self.original_input_text
        clone.normalized_text = self.normalized_text
        clone.chinese_review_text = self.chinese_review_text
        clone.step2_confirmed_output = self.step2_confirmed_output
        clone.chinese_review_session = (
            self.chinese_review_session.clone()
            if self.chinese_review_session is not None
            else None
        )
        clone._chinese_review_source_text = self._chinese_review_source_text
        clone.normalized_revision = self.normalized_revision
        clone.step2_revision = self.step2_revision
        clone.cleaned_text = self.cleaned_text
        clone.job_title = self.job_title
        clone.job_chapter = self.job_chapter
        clone.step3_artifacts = copy.copy(self.step3_artifacts)
        clone.thumbnail_path = self.thumbnail_path
        clone.thumbnail_fingerprint = dict(self.thumbnail_fingerprint)
        clone.audio_chunks_dir = self.audio_chunks_dir
        clone.audiobook_path = self.audiobook_path
        clone.audiobook_fingerprint = dict(self.audiobook_fingerprint)
        clone.tts_manifest_path = self.tts_manifest_path
        clone.tts_failures = copy.deepcopy(self.tts_failures)
        clone.video_path = self.video_path
        clone.video_fingerprint = dict(self.video_fingerprint)
        clone.video_metadata = copy.deepcopy(self.video_metadata)
        clone._video_source_fingerprint = copy.deepcopy(self._video_source_fingerprint)
        clone.youtube_upload_state = copy.deepcopy(self.youtube_upload_state)
        clone.filtered_output = self.filtered_output
        clone.text = self.text
        clone.original_text = self.original_text
        clone.preamble = self.preamble
        clone.source_files = [copy.copy(f) for f in self.source_files]
        clone.chapters = [copy.copy(c) for c in self.chapters]
        clone.chunks = [copy.copy(c) for c in self.chunks]
        clone.translations = dict(self.translations)
        clone.translation_meta = copy.deepcopy(self.translation_meta)
        clone.diagnostics = [copy.copy(d) for d in self.diagnostics]
        clone.stage_status = {k: copy.copy(v) for k, v in self.stage_status.items()}
        clone.generated_headers = copy.deepcopy(self.generated_headers)
        clone.selection = copy.deepcopy(self.selection)
        clone.metadata = copy.deepcopy(self.metadata)
        clone.notes = list(self.notes)
        return clone

    # -------------------------------------------------------- diagnostics
    def add_diagnostic(
        self,
        code: str,
        message: str,
        severity: str = Severity.INFO,
        chapter: Optional[int] = None,
        line: Optional[int] = None,
        detail: str = "",
        snippet: str = "",
        stage: str = "",
    ) -> Diagnostic:
        diagnostic = Diagnostic(
            code=code,
            severity=severity,
            chapter=chapter,
            line=line,
            message=message,
            detail=detail,
            snippet=snippet,
            stage=stage,
        )
        self.diagnostics.append(diagnostic)
        return diagnostic

    def extend_diagnostics(self, items: Iterable[Diagnostic]) -> None:
        self.diagnostics.extend(items)

    def diagnostics_for(self, stage: str) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.stage == stage]

    def count_severity(self, severity: str) -> int:
        return sum(1 for d in self.diagnostics if d.severity == severity)

    def clear_diagnostics(self, stage: str) -> None:
        self.diagnostics = [d for d in self.diagnostics if d.stage != stage]

    # ------------------------------------------------------------ helpers
    def load_original_input(
        self,
        text: str,
        *,
        source_path: str = "",
        input_directory: str = "",
    ) -> None:
        """Start a new run while preserving the loaded text as the source."""
        self.source_path = source_path or ""
        self.input_directory = input_directory or ""
        self.original_input_text = text or ""
        self.original_text = self.original_input_text
        self.text = self.original_input_text
        self.normalized_text = None
        self.chinese_review_text = None
        self.step2_confirmed_output = None
        self.chinese_review_session = None
        self._chinese_review_source_text = None
        self.normalized_revision = 0
        self.step2_revision = 0
        self.cleaned_text = None
        self.job_title = ""
        self.job_chapter = ""
        self._clear_step3_artifacts()
        self.filtered_output = None
        self.chapters = []
        self.chunks = []
        self.translations = {}
        self.translation_meta = {}
        self.selection = []
        self.diagnostics = []
        self.stage_status = {
            key: StageStatus(key=key, name=StageKey.NAMES[key]) for key in StageKey.ORDER
        }

    def set_normalized_output(self, chapters: Sequence[Chapter]) -> str:
        """Commit the complete Step 1 result and invalidate later stages."""
        rendered = render_chapters_text(chapters)
        self.normalized_text = rendered
        self.normalized_revision += 1
        self.text = rendered
        self.chapters = list(chapters)
        self.chinese_review_text = None
        self.step2_confirmed_output = None
        self.chinese_review_session = None
        self._chinese_review_source_text = None
        self.cleaned_text = None
        self._clear_step3_artifacts()
        self.filtered_output = None
        self.chunks = []
        self.reset_downstream(StageKey.NORMALIZE)
        return rendered

    def set_normalized_edit(self, text: str) -> bool:
        """Commit a user edit to the Step 1 output and invalidate dependents."""
        value = text or ""
        changed = value != self.normalized_text
        self.normalized_text = value
        self.text = value
        if changed:
            self.normalized_revision += 1
            self.chinese_review_text = None
            self.step2_confirmed_output = None
            self.chinese_review_session = None
            self._chinese_review_source_text = None
            self.cleaned_text = None
            self._clear_step3_artifacts()
            self.filtered_output = None
            self.chunks = []
            self.reset_downstream(StageKey.NORMALIZE)
        return changed

    def begin_chinese_review(self) -> tuple[str, str]:
        """Return the canonical Step 2 source and its user-facing label."""
        normalized_status = self.stage(StageKey.NORMALIZE)
        if normalized_status.ran and normalized_status.ok:
            if self.normalized_text is None:
                raise PipelineStateError(
                    "Step 1 is marked successful but has no normalized text output."
                )
            step2_input = self.step2_input_text()
            source_label = "Source: Step 1 — Normalized Text"
            # Safe provenance check: successful normalization can never select
            # the immutable original input.
            if step2_input != self.normalized_text:
                raise PipelineStateError("Step 2 input is not the current normalized output.")
        else:
            step2_input = self.original_input_text
            source_label = (
                "Source: Original File — Step 1 failed"
                if normalized_status.ran
                else "Source: Original File — Step 1 not run"
            )

        if (
            self.chinese_review_text is None
            or self._chinese_review_source_text != step2_input
        ):
            self.chinese_review_text = step2_input
            self.step2_confirmed_output = None
            self.chinese_review_session = None
            self._chinese_review_source_text = step2_input
            self.text = step2_input
        return self.chinese_review_text, source_label

    def step2_input_text(self) -> str:
        """Return only the upstream text eligible to initialize Step 2."""
        status = self.stage(StageKey.NORMALIZE)
        if status.ran and status.ok:
            if self.normalized_text is None:
                raise PipelineStateError(
                    "Step 1 is marked successful but has no normalized text output."
                )
            return self.normalized_text
        return self.original_input_text

    def set_chinese_review_output(self, text: str) -> None:
        """Commit Step 2's current text and invalidate later stages."""
        value = text or ""
        if (
            self.chinese_review_session is not None
            and self.chinese_review_session.working_text != value
        ):
            self.chinese_review_session = None
        changed = value != self.chinese_review_text
        self.chinese_review_text = value
        if changed:
            self.step2_revision += 1
        if not changed:
            return
        self.step2_confirmed_output = None
        self.text = self.chinese_review_text
        self.cleaned_text = None
        self._clear_step3_artifacts()
        self.filtered_output = None
        self.chunks = []
        self.reset_downstream(StageKey.CHINESE)

    def complete_chinese_review(self, text: str) -> str:
        """Commit the only text that Step 3 is allowed to consume."""
        from chinese.detector import has_han

        value = text or ""
        if has_han(value):
            self.step2_confirmed_output = None
            raise PipelineStateError(
                "Step 2 cannot be completed while Chinese Han characters remain."
            )
        changed = value != self.chinese_review_text or self.step2_confirmed_output != value
        if changed:
            self.step2_revision += 1
        self.chinese_review_text = value
        self.step2_confirmed_output = value
        self.text = value
        if changed:
            self.cleaned_text = None
            self._clear_step3_artifacts()
            self.filtered_output = None
            self.chunks = []
            self.reset_downstream(StageKey.CHINESE)
        return value

    def require_step2_confirmed_output(self) -> str:
        """Return Step 2's verified result or fail closed."""
        if self.step2_confirmed_output is None:
            raise PipelineStateError(
                "Complete Step 2 Chinese Residue Review before continuing to Step 3."
            )
        from chinese.detector import has_han

        if has_han(self.step2_confirmed_output):
            raise PipelineStateError(
                "Step 2 confirmed output is invalid because Han characters remain."
            )
        if self.chinese_review_text != self.step2_confirmed_output:
            raise PipelineStateError(
                "Step 2 working text changed after confirmation; review it again."
            )
        return self.step2_confirmed_output

    def step3_input_text(self) -> str:
        """Compatibility accessor with the same fail-closed Step 3 contract."""
        return self.require_step2_confirmed_output()

    def set_cleaned_output(self, text: str) -> None:
        value = text or ""
        if value != self.cleaned_text:
            self._clear_step3_artifacts()
        self.cleaned_text = value
        self.text = self.cleaned_text

    def set_filtered_output(self, text: str) -> None:
        self.filtered_output = text or ""

    # ---------------------------------------------------------- Step 3/4
    def set_job_identity(self, title: str, chapter: str) -> bool:
        """Set editable per-job labels and invalidate only derived artifacts."""
        title = (title or "").strip()
        chapter = (chapter or "").strip()
        changed = (title, chapter) != (self.job_title, self.job_chapter)
        self.job_title, self.job_chapter = title, chapter
        if changed:
            self._clear_step3_artifacts()
            self.filtered_output = None
            self.reset_downstream(StageKey.CLEAN_CHUNK)
        return changed

    def set_step3_artifacts(self, bundle: Step3ArtifactBundle) -> None:
        self.step3_artifacts = bundle
        self.thumbnail_path = ""
        self.thumbnail_fingerprint = {}
        self.audio_chunks_dir = ""
        self.audiobook_path = ""
        self.audiobook_fingerprint = {}
        self.tts_manifest_path = ""
        self.tts_failures = []
        self._clear_video_output()

    def set_thumbnail_output(self, path: str) -> None:
        self.thumbnail_path = path or ""
        self.thumbnail_fingerprint = self._fingerprint_file(self.thumbnail_path)
        self._clear_video_output()

    def set_tts_output(
        self,
        *,
        audio_chunks_dir: str,
        manifest_path: str,
        audiobook_path: str = "",
        failures: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        self.audio_chunks_dir = audio_chunks_dir
        self.tts_manifest_path = manifest_path
        self.audiobook_path = audiobook_path
        self.audiobook_fingerprint = self._fingerprint_file(self.audiobook_path)
        self.tts_failures = [dict(item) for item in (failures or [])]
        self._clear_video_output()

    def set_video_output(self, path: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        media = self.require_step4_outputs()
        self.video_path = path or ""
        self.video_fingerprint = self._fingerprint_file(self.video_path)
        self.video_metadata = dict(metadata or {})
        self._video_source_fingerprint = self._current_video_source_fingerprint(media)
        self._clear_youtube_upload_state()

    def _clear_video_output(self) -> None:
        self.video_path = ""
        self.video_fingerprint = {}
        self.video_metadata = {}
        self._video_source_fingerprint = {}
        self._clear_youtube_upload_state()
        if StageKey.VIDEO in self.stage_status:
            self.stage_status[StageKey.VIDEO] = StageStatus(
                key=StageKey.VIDEO,
                name=StageKey.NAMES[StageKey.VIDEO],
            )

    def set_youtube_upload_state(self, state: Dict[str, Any]) -> None:
        """Mirror upload state in memory; the upload service owns persistence."""
        self.youtube_upload_state = copy.deepcopy(state)
        status = self.stage(StageKey.YOUTUBE)
        if state.get("status") == "completed" and state.get("video_id"):
            status.touch("Step 5 video", "YouTube upload completed", {
                "video_id": state["video_id"], "thumbnail_uploaded": state.get("thumbnail_uploaded", False),
                "playlist_added": state.get("playlist_added", False),
            })
        elif state:
            status.ran = True
            status.ok = False
            status.result_summary = str(state.get("status", "pending"))
            status.error = str(state.get("error", ""))

    def _clear_youtube_upload_state(self) -> None:
        """Withdraw UI authority without touching the on-disk duplicate guard."""
        self.youtube_upload_state = {}
        if StageKey.YOUTUBE in self.stage_status:
            self.stage_status[StageKey.YOUTUBE] = StageStatus(
                key=StageKey.YOUTUBE,
                name=StageKey.NAMES[StageKey.YOUTUBE],
            )

    def _current_video_source_fingerprint(self, media: Step4MediaBundle) -> Dict[str, Any]:
        bundle = self.step3_artifacts
        if bundle is None:
            raise PipelineStateError("Step 3 bundle is missing; regenerate the video.")
        return {
            "source_revision": bundle.source_revision,
            "text_sha256": bundle.text_sha256,
            "chunks_sha256": bundle.chunks_sha256,
            "thumbnail": dict(media.thumbnail_fingerprint),
            "audiobook": dict(media.audiobook_fingerprint),
            "output_path": str(Path(media.video_path).expanduser().resolve()),
        }

    @staticmethod
    def _fingerprint_file(path: str) -> Dict[str, Any]:
        if not path:
            return {}
        candidate = Path(path)
        try:
            stat = candidate.stat()
        except OSError:
            return {}
        return {
            "path": str(candidate.expanduser().resolve()),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    def _clear_step3_artifacts(self) -> None:
        self.step3_artifacts = None
        self.thumbnail_path = ""
        self.thumbnail_fingerprint = {}
        self.audio_chunks_dir = ""
        self.audiobook_path = ""
        self.audiobook_fingerprint = {}
        self.tts_manifest_path = ""
        self.tts_failures = []
        self._clear_video_output()

    def require_step3_artifacts(self) -> Step3ArtifactBundle:
        """Return the current bundle only when it still matches disk and state."""
        bundle = self.step3_artifacts
        if bundle is None:
            raise PipelineStateError(
                "Run Step 3 Clean & Chunk to create the TXT/JSON job bundle first."
            )
        if self.cleaned_text is None or bundle.source_revision != self.step2_revision:
            raise PipelineStateError("Step 3 bundle is stale; run Step 3 again.")
        text_hash = hashlib.sha256(self.cleaned_text.encode("utf-8")).hexdigest()
        chunks_hash = self.chunk_fingerprint()
        if text_hash != bundle.text_sha256 or chunks_hash != bundle.chunks_sha256:
            raise PipelineStateError("Step 3 bundle no longer matches the current pipeline output.")
        try:
            from media.artifacts import validate_step3_bundle

            validate_step3_bundle(bundle)
        except ImportError:
            raise
        except Exception as error:
            raise PipelineStateError(f"Step 3 bundle is unavailable or modified: {error}") from error
        return bundle

    def require_step4_outputs(self) -> Step4MediaBundle:
        """Return only the current, validated thumbnail and audiobook pair."""
        bundle = self.require_step3_artifacts()
        if not self.thumbnail_path:
            raise PipelineStateError("Generate the Step 4 thumbnail before opening Step 5.")
        if not self.audiobook_path:
            raise PipelineStateError("Generate the Step 4 audiobook before opening Step 5.")

        output_dir = Path(bundle.output_dir).expanduser().resolve()
        current = (
            ("thumbnail", self.thumbnail_path, self.thumbnail_fingerprint),
            ("audiobook", self.audiobook_path, self.audiobook_fingerprint),
        )
        for label, value, recorded in current:
            path = Path(value).expanduser()
            fingerprint = self._fingerprint_file(str(path))
            if not fingerprint or fingerprint["size"] <= 0:
                raise PipelineStateError(f"Step 4 {label} is missing or empty: {path}")
            if path.resolve().parent != output_dir:
                raise PipelineStateError(f"Step 4 {label} is outside the current job folder.")
            if not recorded or fingerprint != recorded:
                raise PipelineStateError(
                    f"Step 4 {label} changed after it was generated; regenerate it before Step 5."
                )

        return Step4MediaBundle(
            title=bundle.title,
            chapter=bundle.chapter,
            slug=bundle.slug,
            output_dir=bundle.output_dir,
            thumbnail_path=self.thumbnail_path,
            audiobook_path=self.audiobook_path,
            video_path=str(output_dir / f"{bundle.slug}.mp4"),
            thumbnail_fingerprint=dict(self.thumbnail_fingerprint),
            audiobook_fingerprint=dict(self.audiobook_fingerprint),
        )

    def require_step5_outputs(self) -> Step5UploadBundle:
        """Fail closed unless Step 6 would upload the current generated video."""
        media = self.require_step4_outputs()
        if not self.video_path:
            raise PipelineStateError("Create the Step 5 video before opening Step 6.")
        path = Path(self.video_path).expanduser()
        fingerprint = self._fingerprint_file(str(path))
        if not fingerprint or fingerprint["size"] <= 0 or not path.is_file():
            raise PipelineStateError(f"Step 5 video is missing or empty: {path}")
        if (
            path.resolve().parent != Path(media.output_dir).expanduser().resolve()
            or path.resolve() != Path(media.video_path).expanduser().resolve()
        ):
            raise PipelineStateError("Step 5 video is not the generated MP4 for the current job.")
        if not self.video_fingerprint or fingerprint != self.video_fingerprint:
            raise PipelineStateError(
                "Step 5 video changed after it was generated; create it again before Step 6."
            )
        if self._video_source_fingerprint != self._current_video_source_fingerprint(media):
            raise PipelineStateError(
                "Step 5 video no longer matches the current Step 4 outputs; create it again."
            )
        return Step5UploadBundle(
            title=media.title,
            chapter=media.chapter,
            output_dir=media.output_dir,
            video_path=self.video_path,
            thumbnail_path=media.thumbnail_path,
            video_fingerprint=dict(self.video_fingerprint),
            thumbnail_fingerprint=dict(media.thumbnail_fingerprint),
        )

    def chunk_fingerprint(self) -> str:
        payload = "\n".join(
            f"{chunk.order}\0{chunk.chapter}\0{chunk.text}" for chunk in self.chunks
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def set_text(self, text: str, *, record_original: bool = False) -> None:
        if record_original and not self.original_text:
            self.original_input_text = text
            self.original_text = text
        self.text = text

    def chapter_numbers(self) -> List[int]:
        return [c.number for c in self.chapters]

    def chapter_map(self) -> Dict[int, Chapter]:
        mapping: Dict[int, Chapter] = {}
        for chapter in self.chapters:
            mapping.setdefault(chapter.number, chapter)
        return mapping

    def get_chapter(self, number: int) -> Optional[Chapter]:
        for chapter in self.chapters:
            if chapter.number == number:
                return chapter
        return None

    def number_of_chapters(self) -> int:
        return len(self.chapters)

    def total_characters(self) -> int:
        if self.cleaned_text is not None:
            return len(self.cleaned_text)
        if self.chinese_review_text is not None:
            return len(self.chinese_review_text)
        if self.normalized_text is not None:
            return len(self.normalized_text)
        if self.chapters:
            return sum(c.char_count for c in self.chapters)
        return len(self.text)

    def stage(self, key: str) -> StageStatus:
        if key not in self.stage_status:
            self.stage_status[key] = StageStatus(key=key, name=StageKey.NAMES.get(key, key))
        return self.stage_status[key]

    def reset_downstream(self, stage_key: str) -> None:
        """Invalidate stage results that follow *stage_key* in the flow."""
        if stage_key not in StageKey.ORDER:
            return
        index = StageKey.ORDER.index(stage_key)
        for key in StageKey.ORDER[index + 1:]:
            self.stage_status[key] = StageStatus(key=key, name=StageKey.NAMES[key])
        if index < StageKey.ORDER.index(StageKey.YOUTUBE):
            self._clear_youtube_upload_state()
        self.diagnostics = [d for d in self.diagnostics if d.stage in StageKey.ORDER[: index + 1]]
        if stage_key in (StageKey.NORMALIZE, StageKey.CHINESE):
            self.chunks = []
            self.cleaned_text = None
            self.filtered_output = None
        if stage_key in (StageKey.NORMALIZE,):
            self.selection = []
            self.chinese_review_text = None
            self.step2_confirmed_output = None
            self.chinese_review_session = None
            self._chinese_review_source_text = None

    # ------------------------------------------------------------- export
    def summary(self) -> Dict[str, Any]:
        chunk_sizes = [c.char_count for c in self.chunks]
        return {
            "source_path": self.source_path,
            "source_encoding": self.source_encoding,
            "source_files": len(self.source_files),
            "characters": self.total_characters(),
            "chapter_count": len(self.chapters),
            "chunk_count": len(self.chunks),
            "translation_count": len(self.translations),
            "chunk_min": min(chunk_sizes) if chunk_sizes else 0,
            "chunk_max": max(chunk_sizes) if chunk_sizes else 0,
            "chunk_avg": int(sum(chunk_sizes) / len(chunk_sizes)) if chunk_sizes else 0,
            "diagnostics": len(self.diagnostics),
            "warnings": self.count_severity(Severity.WARNING),
            "errors": self.count_severity(Severity.ERROR),
        }

    def status_lines(self) -> List[str]:
        lines = []
        for key in StageKey.ORDER:
            status = self.stage_status[key]
            mark = "●" if status.ok else ("✕" if status.ran else "○")
            detail = status.result_summary or status.error or "chưa chạy"
            lines.append(f"{mark} {status.name}: {detail}")
        return lines


@dataclass
class StageResult:
    """Return value of a stage function."""

    document: PipelineDocument
    diagnostics: List[Diagnostic] = field(default_factory=list)
    counts: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    input_summary: str = ""

    def status(self) -> str:
        return self.summary

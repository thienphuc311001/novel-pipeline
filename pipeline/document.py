"""The in-memory pipeline document shared by every stage.

Each stage receives a :class:`PipelineDocument` and returns a new one.  Nothing
in the pipeline ever requires the user to save a temporary file in order to
continue: intermediate results live in memory only.
"""

from __future__ import annotations

import copy
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

    ORDER = [NORMALIZE, CHINESE, CLEAN_CHUNK, FILTER_EXPORT]
    NAMES = {
        NORMALIZE: "Chuẩn hoá chương",
        CHINESE: "Duyệt & dịch Trung",
        CLEAN_CHUNK: "Làm sạch & chia đoạn",
        FILTER_EXPORT: "Lọc & xuất",
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
    """Mutable working document shared by all four stages."""

    def __init__(self) -> None:
        self.source_bytes: bytes = b""
        self.source_path: str = ""
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
        self.cleaned_text: Optional[str] = None
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
        clone.cleaned_text = self.cleaned_text
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
    def load_original_input(self, text: str) -> None:
        """Start a new run while preserving the loaded text as the source."""
        self.original_input_text = text or ""
        self.original_text = self.original_input_text
        self.text = self.original_input_text
        self.normalized_text = None
        self.chinese_review_text = None
        self.step2_confirmed_output = None
        self.chinese_review_session = None
        self._chinese_review_source_text = None
        self.normalized_revision = 0
        self.cleaned_text = None
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
        self.chinese_review_text = value
        self.step2_confirmed_output = None
        self.text = self.chinese_review_text
        self.cleaned_text = None
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
        self.chinese_review_text = value
        self.step2_confirmed_output = value
        self.text = value
        self.cleaned_text = None
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
        self.cleaned_text = text or ""
        self.text = self.cleaned_text

    def set_filtered_output(self, text: str) -> None:
        self.filtered_output = text or ""

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

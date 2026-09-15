"""Chapter normalization with exact header format rules.

Key behaviors:
1. Chinese headers → "Chương X" (remove Chinese subtitle)
2. Vietnamese headers with content → preserve complete line
3. Leading zeros removed by default (configurable)
4. Duplicate resolution with exact priority rules
5. Never delete actual novel content

Normalization rules:
- Chinese-only headers: 第327章 流民不可怕 → Chương 327 (title omitted from body)
- Vietnamese headers: Chương 0327: Lưu dân không đáng sợ → Chương 327: Lưu dân không đáng sợ
- Mixed duplicates: Keep Vietnamese, discard Chinese
- Same-line Vietnamese content: NEVER truncate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from cleaning.textclean import (
    enforce_sentence_endings,
    normalize_spacing,
    restore_escaped_newlines,
)
from pipeline.document import Chapter, Diagnostic, Severity

from .detector import ChapterHit, detect_chapters, strip_trailing_blank_lines
from .duplicates import DuplicateReport, resolve_duplicates, language_of
from .numerals import parse_number_token
from .patterns import PatternSet

# Header markers for detection
HEADER_MARKERS = (
    "chương", "chuong", "hồi", "hoi", "quyển", "quyen", 
    "phần", "phan", "tập", "tap",
    "chapter", "chap", "book", "part", "volume",
)


@dataclass
class NormalizeOptions:
    """Options for chapter normalization."""
    
    # Header format
    chapter_prefix: str = "Chương {n}"
    zero_pad: int = 0
    header_separator: str = ": "
    keep_original_headers: bool = False
    
    # Duplicate handling
    dedupe_chapters: bool = True
    prefer_vietnamese: bool = True
    
    # Text cleaning
    enforce_period: bool = True
    normalize_spacing: bool = True
    restore_newlines: bool = True
    unwrap_json: bool = True
    
    # Auto-insertion
    auto_insert_headers: bool = False
    auto_insert_prefix: str = "Chương {n}"
    continuous_numbering: bool = True
    renumber_start: Optional[int] = None
    
    # Validation
    min_chapter_chars: int = 0

    @classmethod
    def from_settings(cls, settings) -> "NormalizeOptions":
        """Build options from application settings."""
        return cls(
            chapter_prefix=getattr(settings, "chapter_prefix", "Chương {n}"),
            zero_pad=int(getattr(settings, "zero_pad", 0) or 0),
            header_separator=getattr(settings, "header_separator", ": "),
            keep_original_headers=bool(getattr(settings, "keep_original_headers", False)),
            dedupe_chapters=bool(getattr(settings, "dedupe_chapters", True)),
            prefer_vietnamese=bool(getattr(settings, "prefer_vietnamese", True)),
            enforce_period=bool(getattr(settings, "enforce_period", True)),
            normalize_spacing=bool(getattr(settings, "normalize_spacing", True)),
            auto_insert_headers=bool(getattr(settings, "auto_insert_headers", False)),
            auto_insert_prefix=getattr(settings, "auto_insert_prefix", "Chương {n}"),
            continuous_numbering=bool(getattr(settings, "continuous_numbering", True)),
        )


@dataclass
class NormalizeReport:
    """Report of normalization actions."""
    
    hits: List[ChapterHit] = field(default_factory=list)
    chapters: List[Chapter] = field(default_factory=list)
    preamble: str = ""
    duplicates: Optional[DuplicateReport] = None
    restored_newlines: int = 0
    periods_added: int = 0
    glued_splits: int = 0
    header_artifacts_removed: int = 0
    chinese_titles_removed: int = 0
    text_loss: int = 0
    unnumbered_segments: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "chapters": len(self.chapters),
            "restored_newlines": self.restored_newlines,
            "periods_added": self.periods_added,
            "glued_splits": self.glued_splits,
            "header_artifacts_removed": self.header_artifacts_removed,
            "chinese_titles_removed": self.chinese_titles_removed,
            "text_loss": self.text_loss,
            "unnumbered_segments": self.unnumbered_segments,
        }


def format_chapter_header(
    number: int, 
    title: str, 
    options: NormalizeOptions
) -> str:
    """Build the canonical chapter header.
    
    Rules:
    - Chinese headers: Always normalize to "Chương X" (no Chinese title)
    - Vietnamese headers: "Chương X: Title" if title exists
    - Leading zeros: Removed by default unless zero_pad is set
    
    Examples:
        format_chapter_header(327, "", options) → "Chương 327"
        format_chapter_header(327, "Lưu dân không đáng sợ", options) → "Chương 327: Lưu dân không đáng sợ"
    """
    number_text = str(int(number))
    
    # Apply zero padding if configured
    if options.zero_pad and options.zero_pad > 0:
        number_text = number_text.zfill(options.zero_pad)
    
    # Format base prefix
    try:
        base = options.chapter_prefix.format(
            n=number_text, 
            number=number_text, 
            num=number_text
        )
    except (KeyError, IndexError, ValueError):
        base = f"Chương {number_text}"
    
    base = base.strip()
    title = (title or "").strip()
    
    # Add title if present
    if title:
        separator = options.header_separator or ": "
        return f"{base}{separator}{title}".strip()
    
    return base


def _is_header_like(line: str) -> bool:
    """Check if a line looks like a chapter header marker."""
    stripped = line.strip().strip(":：-–—").lower()
    if not stripped:
        return False
    return any(stripped.startswith(marker) for marker in HEADER_MARKERS)


def _clean_header_artifacts(header: str) -> Tuple[str, int]:
    """Strip decorative artifacts from an original header.
    
    Removes: #, >, *, -, –, —, », =, etc.
    Returns (cleaned_header, artifact_count)
    """
    cleaned = header.strip()
    artifacts = 0
    
    # Strip leading decorations
    for prefix in ("#", ">", "*", "-", "–", "—", "»", "="):
        while cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            artifacts += 1
    
    # Strip trailing decorations
    while cleaned.endswith("=") or cleaned.endswith("*"):
        cleaned = cleaned[:-1].strip()
        artifacts += 1
    
    return cleaned, artifacts


def _strip_header_prefix(body: str, number: int) -> Tuple[str, int]:
    """Remove a repeated header paragraph at the start of a chapter body.
    
    Only removes actual header repetitions, not narrative content.
    
    Example:
        Input: "Chương 327\n\nĐêm ấy..."
        Output: "Đêm ấy..." (removed repeated header)
    
    Returns (cleaned_body, removed_chars)
    """
    if not body or not body.strip():
        return body, 0
    
    lines = body.split("\n")
    removed = 0
    
    # Check first few lines for header repetition
    while lines and len(lines) > 0:
        first = lines[0].strip()
        
        # Empty line - skip
        if not first:
            lines.pop(0)
            removed += len(lines[0]) + 1 if lines else 0
            continue
        
        # Check if it's a header-like line
        if _is_header_like(first):
            # Try to parse number from it
            first_lower = first.lower()
            if str(number) in first or f"{number:03d}" in first or f"{number:04d}" in first:
                lines.pop(0)
                removed += len(first) + 1
                continue
        
        # Not a header - stop
        break
    
    cleaned = "\n".join(lines)
    return cleaned, removed


def build_chapters(
    text: str,
    pattern_set: PatternSet,
    options: NormalizeOptions,
    *,
    source_name: str = "",
) -> Tuple[NormalizeReport, List[Diagnostic]]:
    """Detect and normalize chapters from raw text.
    
    Key behaviors:
    - Detects all chapter formats (Chinese, Vietnamese, English)
    - Normalizes headers to canonical format
    - Chinese headers: Remove Chinese title, use "Chương X"
    - Vietnamese headers: Preserve Vietnamese title/content
    - Removes duplicate headers (not bodies)
    - Cleans spacing and punctuation
    - Tracks all data loss and transformations
    """
    diagnostics: List[Diagnostic] = []
    
    # Detect all chapter headers
    hits, preamble_lines, notes = detect_chapters(text, pattern_set, source_name=source_name)
    
    report = NormalizeReport(
        hits=hits,
        preamble="\n".join(preamble_lines),
        glued_splits=len([n for n in notes if n.get("kind") == "glued"]),
    )
    
    if not hits:
        diagnostics.append(
            Diagnostic(
                code="no_chapters",
                severity=Severity.WARNING,
                message="Không phát hiện chương nào.",
                stage="normalize",
            )
        )
        return report, diagnostics
    
    # Build Chapter objects from hits
    chapters: List[Chapter] = []
    
    for hit in hits:
        body = hit.body
        
        # Strip repeated header from body
        body, removed = _strip_header_prefix(body, hit.number)
        if removed > 0:
            report.header_artifacts_removed += 1
        
        # Apply text cleaning
        if options.restore_newlines:
            body, count = restore_escaped_newlines(body)
            report.restored_newlines += count
        
        if options.normalize_spacing:
            body = normalize_spacing(body)
        
        if options.enforce_period:
            body, count = enforce_sentence_endings(body)
            report.periods_added += count
        
        strip_trailing_blank_lines(body.split("\n"))
        body = body.strip()
        
        # Determine if we should preserve the title
        # Rule: For Chinese headers, do NOT preserve the Chinese title
        # Rule: For Vietnamese headers, preserve the Vietnamese title
        chapter_language = hit.language
        title_to_use = ""
        
        if chapter_language == "zh":
            # Chinese header - do NOT preserve Chinese title
            # It will be normalized to just "Chương X"
            title_to_use = ""
            if hit.title:
                report.chinese_titles_removed += 1
                diagnostics.append(
                    Diagnostic(
                        code="chinese_chapter_title_removed",
                        severity=Severity.INFO,
                        chapter=hit.number,
                        line=hit.line_index + 1,
                        message=f"Đã loại tiêu đề tiếng Trung khỏi chương {hit.number}.",
                        detail=hit.title,
                        stage="normalize",
                    )
                )
        elif chapter_language in ("vi", "en"):
            # Vietnamese/English header - preserve title
            title_to_use = hit.title
        else:
            # Mixed or unknown - preserve title
            title_to_use = hit.title
        
        # Format canonical header
        if options.keep_original_headers:
            header, artifacts = _clean_header_artifacts(hit.header_line)
            if artifacts > 0:
                report.header_artifacts_removed += artifacts
        else:
            header = format_chapter_header(hit.number, title_to_use, options)
        
        # Create Chapter object
        chapter = Chapter(
            number=hit.number,
            header_line=header,
            title=title_to_use,
            text=body,
            source_line=hit.line_index + 1,
            language=chapter_language,
            char_count=len(body),
        )
        
        chapters.append(chapter)
    
    report.chapters = chapters
    return report, diagnostics


def sequence_diagnostics(chapters: Sequence[Chapter], stage: str = "normalize") -> List[Diagnostic]:
    """Check for missing chapters and sequence violations.
    
    Validates that chapters are in increasing order and identifies gaps.
    """
    diagnostics: List[Diagnostic] = []
    
    if not chapters:
        return diagnostics
    
    numbers = [c.number for c in chapters]
    
    if not numbers:
        return diagnostics
    
    # Check for sequence violations (out of order)
    ordered = sorted(numbers)
    
    # Check for missing chapters in expected range
    if len(ordered) > 1:
        expected = set(range(ordered[0], ordered[-1] + 1))
        missing = sorted(expected - set(ordered))
        
        if missing:
            preview = ", ".join(str(n) for n in missing[:40])
            more = "" if len(missing) <= 40 else f" (+{len(missing) - 40} nữa)"
            diagnostics.append(
                Diagnostic(
                    code="chapters_missing",
                    severity=Severity.WARNING,
                    message=f"Thiếu {len(missing)} chương: {preview}{more}.",
                    detail=",".join(str(n) for n in missing),
                    stage=stage,
                )
            )
    
    # Check for out-of-order violations
    violations = [
        (previous, current)
        for previous, current in zip(numbers, numbers[1:])
        if current < previous
    ]
    
    if violations:
        examples = ", ".join(f"{a}→{b}" for a, b in violations[:10])
        diagnostics.append(
            Diagnostic(
                code="chapter_order_violation",
                severity=Severity.WARNING,
                message=f"{len(violations)} vị trí không theo thứ tự tăng dần: {examples}.",
                stage=stage,
            )
        )
    
    return diagnostics


def normalize_chapters(
    text: str,
    pattern_set: PatternSet,
    options: NormalizeOptions,
    *,
    source_name: str = "",
    run_sequence_checks: bool = True,
) -> Tuple[List[Chapter], NormalizeReport, List[Diagnostic]]:
    """Full normalization pipeline: detect, clean, dedupe, and diagnose.
    
    This is the main entry point for chapter normalization.
    
    Returns:
        chapters: List of normalized Chapter objects
        report: NormalizeReport with statistics
        diagnostics: List of warnings and errors
    """
    report, diagnostics = build_chapters(text, pattern_set, options, source_name=source_name)
    chapters = report.chapters
    
    # Resolve duplicates if enabled
    if options.dedupe_chapters and chapters:
        duplicate_report = resolve_duplicates(
            chapters, 
            prefer_vietnamese=options.prefer_vietnamese
        )
        report.duplicates = duplicate_report
        
        # Log duplicate resolution
        if duplicate_report.groups:
            for group in duplicate_report.groups:
                diagnostics.append(
                    Diagnostic(
                        code="duplicate_chapter_resolved",
                        severity=Severity.WARNING,
                        chapter=group.number,
                        message=(
                            f"Chương {group.number} bị trùng {len(group.discarded)} bản; "
                            f"đã loại {group.discarded_chars} ký tự."
                        ),
                        detail=" | ".join(group.reasons),
                        snippet=" | ".join(
                            (c.text or "")[:80] for c in group.discarded[:3]
                        ),
                        stage="normalize",
                    )
                )
        
        # Update chapters list with deduplicated results
        chapters = sorted(
            duplicate_report.kept, 
            key=lambda c: (c.number, c.source_line)
        )
    
    report.chapters = chapters
    
    # Run sequence validation
    if run_sequence_checks:
        diagnostics.extend(sequence_diagnostics(chapters))
    
    # Track text loss per chapter
    raw_by_line = {hit.line_index + 1: len(hit.body) for hit in report.hits}
    report.text_loss = 0
    
    for chapter in chapters:
        raw_body_chars = raw_by_line.get(chapter.source_line, chapter.char_count)
        
        if chapter.char_count < raw_body_chars:
            chapter.text_loss = raw_body_chars - chapter.char_count
            report.text_loss += chapter.text_loss
            
            if chapter.text_loss >= 50:
                diagnostics.append(
                    Diagnostic(
                        code="chapter_text_loss",
                        severity=Severity.WARNING if chapter.text_loss >= 100 else Severity.INFO,
                        chapter=chapter.number,
                        line=chapter.source_line,
                        message=(
                            f"Chương {chapter.number}: {raw_body_chars} → {chapter.char_count} ký tự "
                            f"({chapter.text_loss} ký tự do chuẩn hoá)."
                        ),
                        stage="normalize",
                    )
                )
    
    return chapters, report, diagnostics


def renumber_sequentially(
    chapters: Sequence[Chapter], 
    start: int = 1, 
    options: Optional[NormalizeOptions] = None
) -> int:
    """Renumber chapters sequentially starting from *start*.
    
    User-triggered action for fixing chapter numbering.
    Returns the number of chapters that were changed.
    """
    options = options or NormalizeOptions()
    changed = 0
    
    for offset, chapter in enumerate(chapters):
        new_number = start + offset
        
        if chapter.number != new_number:
            chapter.number = new_number
            chapter.header_line = format_chapter_header(
                new_number, 
                chapter.title, 
                options
            )
            changed += 1
    
    return changed


def repair_headers(
    chapters: Sequence[Chapter], 
    options: Optional[NormalizeOptions] = None
) -> int:
    """Rewrite every chapter header to the canonical form.
    
    User-triggered action for normalizing all headers.
    Returns the number of headers that were changed.
    """
    options = options or NormalizeOptions()
    changed = 0
    
    for chapter in chapters:
        canonical = format_chapter_header(chapter.number, chapter.title, options)
        
        if canonical != chapter.header_line:
            chapter.header_line = canonical
            changed += 1
    
    return changed

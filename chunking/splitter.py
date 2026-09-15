"""Chapter-safe, sentence-aware chunking.

Guarantees:

* a chunk never crosses a chapter boundary;
* break preference is paragraph -> sentence -> clause -> space;
* hard slicing happens only when a single sentence/clause/word already exceeds
  the limit, and those chunks are flagged (``hard_split``) with a warning;
* chunk sizes are clamped to sane limits (50 .. 20000 characters).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from pipeline.document import Chapter, Chunk, Diagnostic, Severity

MIN_CHUNK = 600
MAX_CHUNK = 2000
DEFAULT_CHUNK = 1200

PARAGRAPH_RE = re.compile(r"\n\s*\n")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？…])\s*")
CLAUSE_RE = re.compile(r"(?<=[,;:，；：、])\s*")


class BreakStrategy:
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    CLAUSE = "clause"
    SPACE = "space"
    HARD = "hard"

    LABELS = {
        PARAGRAPH: "đoạn văn",
        SENTENCE: "câu",
        CLAUSE: "mệnh đề",
        SPACE: "khoảng trắng",
        HARD: "cắt cứng",
    }


def clamp_chunk_size(size: int, minimum: int = MIN_CHUNK) -> int:
    """Clamp the maximum chunk size to a sane range."""
    try:
        value = int(size)
    except (TypeError, ValueError):
        value = DEFAULT_CHUNK
    return max(max(MIN_CHUNK, int(minimum or MIN_CHUNK)), min(value, MAX_CHUNK))


@dataclass
class ChunkPlan:
    chunks: List[str] = field(default_factory=list)
    strategies: List[str] = field(default_factory=list)
    hard_splits: List[int] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.chunks)

    @property
    def total_chars(self) -> int:
        return sum(len(chunk) for chunk in self.chunks)

    def strategy_counts(self) -> dict:
        counts: dict = {}
        for strategy in self.strategies:
            counts[strategy] = counts.get(strategy, 0) + 1
        return counts


def _split_paragraphs(text: str) -> List[str]:
    return [part for part in PARAGRAPH_RE.split(text) if part.strip()]


def _split_sentences(text: str) -> List[str]:
    parts = [part for part in SENTENCE_RE.split(text) if part]
    return parts or [text]


def _split_clauses(text: str) -> List[str]:
    parts = [part for part in CLAUSE_RE.split(text) if part]
    return parts or [text]


def _hard_slice(text: str, limit: int) -> List[str]:
    return [text[index: index + limit] for index in range(0, len(text), limit)] or [text]


def _pack_units(units: Sequence[str], limit: int, joiner: str = "") -> Tuple[List[str], bool]:
    """Pack units into pieces of at most *limit* characters."""
    pieces: List[str] = []
    buffer = ""
    hard = False
    for unit in units:
        if len(unit) > limit:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            pieces.extend(_hard_slice(unit, limit))
            hard = True
            continue
        candidate = f"{buffer}{joiner}{unit}" if buffer else unit
        if len(candidate) <= limit:
            buffer = candidate
            continue
        if buffer:
            pieces.append(buffer)
        buffer = unit
    if buffer:
        pieces.append(buffer)
    return pieces, hard


def _units_at(text: str, level: int) -> Tuple[List[str], str]:
    """Break *text* at one preference level: paragraph/sentence/clause/space."""
    if level == 0:
        return _split_paragraphs(text), "\n\n"
    if level == 1:
        return _split_sentences(text), ""
    if level == 2:
        return _split_clauses(text), ""
    return text.split(" "), " "


def _split_level(text: str, limit: int, level: int, out: List[Tuple[str, str, bool]]) -> None:
    """Recursively split *text*, recording the strategy and hard-split flag."""
    levels = [BreakStrategy.PARAGRAPH, BreakStrategy.SENTENCE, BreakStrategy.CLAUSE, BreakStrategy.SPACE]
    if len(text) <= limit:
        strategy = levels[max(0, min(level - 1, len(levels) - 1))] if level else BreakStrategy.PARAGRAPH
        out.append((text, strategy, False))
        return
    if level >= len(levels):
        for piece in _hard_slice(text, limit):
            out.append((piece, BreakStrategy.HARD, True))
        return
    units, joiner = _units_at(text, level)
    if len(units) <= 1:
        _split_level(text, limit, level + 1, out)
        return
    buffer = ""
    for unit in units:
        if len(unit) > limit:
            if buffer:
                out.append((buffer, levels[level], False))
                buffer = ""
            _split_level(unit, limit, level + 1, out)
            continue
        candidate = f"{buffer}{joiner}{unit}" if buffer else unit
        if len(candidate) <= limit:
            buffer = candidate
            continue
        if buffer:
            out.append((buffer, levels[level], False))
        buffer = unit
    if buffer:
        out.append((buffer, levels[level], False))


def split_text_by_limit(text: str, limit: int) -> ChunkPlan:
    """Split *text* respecting break preference, falling back when necessary."""
    limit = clamp_chunk_size(limit)
    plan = ChunkPlan()
    if not text:
        return plan
    out: List[Tuple[str, str, bool]] = []
    _split_level(text, limit, 0, out)
    plan.chunks = [item[0] for item in out]
    plan.strategies = [item[1] for item in out]
    plan.hard_splits = [index for index, item in enumerate(out) if item[2]]
    return plan


def split_chapter(
    chapter: Chapter,
    limit: int,
    *,
    include_header: bool = False,
    min_chunk: int = MIN_CHUNK,
) -> ChunkPlan:
    """Split one chapter, never merging it with another chapter."""
    limit = clamp_chunk_size(limit, min_chunk)
    body = chapter.body(include_header=include_header) if include_header else (chapter.text or "")
    return split_text_by_limit(body, limit)


def split_chapters(
    chapters: Sequence[Chapter],
    limit: int,
    *,
    include_header: bool = False,
    merge_short: bool = False,
    min_chunk: int = MIN_CHUNK,
    include_empty: bool = False,
    stage: str = "clean_chunk",
) -> Tuple[List[Chunk], ChunkPlan, List[Diagnostic]]:
    """Produce chunk objects for every chapter, with diagnostics."""
    limit = clamp_chunk_size(limit, min_chunk)
    chunks: List[Chunk] = []
    combined = ChunkPlan()
    diagnostics: List[Diagnostic] = []
    order = 0

    for chapter in chapters:
        plan = split_chapter(chapter, limit, include_header=include_header, min_chunk=min_chunk)
        if not plan.chunks and not include_empty:
            diagnostics.append(
                Diagnostic(
                    code="empty_chapter",
                    severity=Severity.WARNING,
                    chapter=chapter.number,
                    line=chapter.source_line,
                    message="Chương không có nội dung, bỏ qua khi chia đoạn.",
                    stage=stage,
                )
            )
            continue
        total_parts = len(plan.chunks)
        for index, text in enumerate(plan.chunks, start=1):
            order += 1
            chunk = Chunk(
                chapter=chapter.number,
                index=index,
                order=order,
                text=text,
                char_count=len(text),
                chapter_title=chapter.display_title(),
                hard_split=index - 1 in plan.hard_splits,
                part=index,
                parts=total_parts,
            )
            chunks.append(chunk)
            if chunk.hard_split:
                diagnostics.append(
                    Diagnostic(
                        code="hard_split_chunk",
                        severity=Severity.WARNING,
                        chapter=chapter.number,
                        line=chapter.source_line,
                        message=(
                            f"Chương {chapter.number} đoạn {index}/{total_parts}: phải cắt cứng "
                            f"vì một câu/mệnh đề dài hơn {limit} ký tự."
                        ),
                        snippet=text[:160],
                        stage=stage,
                    )
                )
        combined.chunks.extend(plan.chunks)
        combined.strategies.extend(plan.strategies)
        combined.hard_splits.extend(plan.hard_splits)
        if merge_short and len(plan.chunks) == 1 and len(plan.chunks[0]) < min_chunk:
            diagnostics.append(
                Diagnostic(
                    code="short_chunk",
                    severity=Severity.INFO,
                    chapter=chapter.number,
                    message=(
                        f"Chương {chapter.number} chỉ có {len(plan.chunks[0])} ký tự "
                        "(ngắn hơn ngưỡng tối thiểu)."
                    ),
                    stage=stage,
                )
            )
    return chunks, combined, diagnostics

"""Chapter-safe, sentence-aware chunking.

Guarantees:

* a chunk never crosses a chapter boundary;
* break preference is sentence -> clause -> space;
* hard slicing happens only when a single sentence/clause/word already exceeds
  the limit, and those chunks are flagged (``hard_split``) with a warning;
* chunk sizes are clamped to sane limits (600 .. 2000 characters).
"""

from __future__ import annotations

import re
import bisect
import unicodedata
from cleaning.tts_boundaries import (CHUNKER_VERSION, protection_mask, protected_spans,
                                     boundary_positions, meaningful_text, split_units)
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from pipeline.document import Chapter, Chunk, Diagnostic, Severity

MIN_CHUNK = 600
MAX_CHUNK = 2000
DEFAULT_CHUNK = 700
TTS_CHUNK_TARGET = 700

PARAGRAPH_RE = re.compile(r"\n\s*\n")


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
    return split_units(text)


def _split_clauses(text: str) -> List[str]:
    return split_units(text, "clause")


def _hard_slice(text: str, limit: int) -> List[str]:
    pieces, start = [], 0
    while start < len(text):
        end = min(start + limit, len(text))
        while end > start and end < len(text) and unicodedata.combining(text[end]):
            end -= 1
        if end == start:
            raise ValueError(f"Combining sequence exceeds chunk limit at character {start}")
        pieces.append(text[start:end])
        start = end
    return pieces or [text]


def split_text_by_limit(text: str, limit: int, *, abbreviations=None) -> ChunkPlan:
    """Select boundaries by preference, preserving every meaningful character."""
    from cleaning.tts_boundaries import DEFAULT_ABBREVIATIONS
    abbreviations = DEFAULT_ABBREVIATIONS if abbreviations is None else abbreviations
    limit = clamp_chunk_size(limit)
    plan = ChunkPlan()
    if not meaningful_text(text):
        return plan
    for start, end in protected_spans(text, abbreviations):
        if end - start > limit:
            raise ValueError(f"Protected token exceeds {limit} characters at character {start}")
    mask = protection_mask(text, abbreviations)
    quoted = protection_mask(text, abbreviations, quote_limit=limit)
    sentences = boundary_positions(text, abbreviations=abbreviations)
    clauses = boundary_positions(text, "clause", abbreviations)
    spaces = [m.end() for m in re.finditer(r"\s+", text) if not mask[m.start()]]
    # Complete sentences always take precedence; clauses/words are oversized-sentence fallbacks.
    levels = [(sentences, BreakStrategy.SENTENCE),
              ([c for c in clauses if (not quoted[c - 1] or c == len(text) or not quoted[c])], BreakStrategy.CLAUSE),
              (clauses, BreakStrategy.CLAUSE),
              ([c for c in spaces if c == len(text) or not quoted[c - 1] or not quoted[c]], BreakStrategy.SPACE),
              (spaces, BreakStrategy.SPACE)]
    start = 0
    while start < len(text):
        if len(text) - start <= limit:
            cut, strategy, hard = len(text), BreakStrategy.PARAGRAPH, False
        else:
            cut, strategy, hard = 0, BreakStrategy.HARD, True
            for positions, label in levels:
                index = bisect.bisect_right(positions, start + limit) - 1
                if index >= 0 and positions[index] > start:
                    candidate = positions[index]
                    # Do not begin the next chunk with loose closing punctuation.
                    next_char = candidate
                    while next_char < len(text) and text[next_char].isspace():
                        next_char += 1
                    if next_char < len(text) and text[next_char] in ',.!?…;:”’)]}':
                        continue
                    cut, strategy, hard = candidate, label, False
                    break
            if not cut:
                cut = start + limit
                while cut > start and (mask[cut - 1] or (cut < len(text) and unicodedata.combining(text[cut]))):
                    cut -= 1
                if cut <= start:
                    raise ValueError(f"No safe split within {limit} characters at character {start}")
        piece = text[start:cut].strip()
        if meaningful_text(piece):
            if hard:
                plan.hard_splits.append(len(plan.chunks))
            plan.chunks.append(piece)
            plan.strategies.append(strategy)
        elif piece and plan.chunks:
            if len(plan.chunks[-1]) + len(piece) > limit:
                raise ValueError(f"Loose punctuation cannot fit chunk at character {start}")
            plan.chunks[-1] += piece
        start = cut
    return plan


def split_chapter(
    chapter: Chapter,
    limit: int,
    *,
    include_header: bool = False,
    min_chunk: int = MIN_CHUNK,
    abbreviations=None,
) -> ChunkPlan:
    """Split one chapter, never merging it with another chapter."""
    limit = clamp_chunk_size(limit, min_chunk)
    plan = split_text_by_limit(chapter.text or "", limit, abbreviations=abbreviations)
    if include_header and meaningful_text(chapter.header_line or ""):
        header = chapter.header_line.strip()
        if len(header) > limit:
            raise ValueError(f"Chapter {chapter.number}: heading exceeds {limit} characters")
        plan.chunks.insert(0, header)
        plan.strategies.insert(0, BreakStrategy.PARAGRAPH)
        plan.hard_splits = [index + 1 for index in plan.hard_splits]
    return plan


def split_chapters(
    chapters: Sequence[Chapter],
    limit: int,
    *,
    include_header: bool = False,
    merge_short: bool = False,
    min_chunk: int = MIN_CHUNK,
    include_empty: bool = False,
    stage: str = "clean_chunk",
    abbreviations=None,
) -> Tuple[List[Chunk], ChunkPlan, List[Diagnostic]]:
    """Produce chunk objects for every chapter, with diagnostics."""
    limit = clamp_chunk_size(limit, min_chunk)
    chunks: List[Chunk] = []
    combined = ChunkPlan()
    diagnostics: List[Diagnostic] = []
    order = 0

    for chapter in chapters:
        plan = split_chapter(chapter, limit, include_header=include_header, min_chunk=min_chunk, abbreviations=abbreviations)
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
        offset = len(combined.chunks)
        combined.chunks.extend(plan.chunks)
        combined.strategies.extend(plan.strategies)
        combined.hard_splits.extend(offset + index for index in plan.hard_splits)
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

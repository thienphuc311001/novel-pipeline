"""Chapter-safe, sentence-aware, layout-driven chunking.

Guarantees:

* a chunk never crosses a chapter boundary;
* break preference is paragraph -> sentence -> clause -> space;
* with a layout budget the *measured rendered pixel height* of the candidate decides
  the boundary: the planner takes the farthest natural boundary that still fits the
  page, so dense prose packs more characters per page than dialogue-heavy text and
  no page is left half empty by a character ceiling;
* hard slicing happens only when a single sentence/clause/word already exceeds
  the page, and those chunks are flagged (``hard_split``) with a warning;
* ``TTS_CHUNK_SOFT_TARGET`` is only the initial search estimate;
* ``MAX_CHUNK`` bounds the *scan window* (never the acceptance rule).
"""

from __future__ import annotations

import bisect
import hashlib
import re
import unicodedata
from cleaning.tts_boundaries import (CHUNKER_VERSION, protection_mask, protected_spans,
                                     boundary_positions, meaningful_text, split_units)
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

from pipeline.document import Chapter, Chunk, Diagnostic, Severity

MIN_CHUNK = 600
# Scan window for the boundary search: candidates are looked for in this many
# characters, while the measured page height decides where the chunk really ends.
MAX_CHUNK = 2000
DEFAULT_CHUNK = 700
# Soft search estimate only.  The final chunk boundary is the largest semantic
# boundary whose measured rendered height stays inside the page; this estimate seeds
# the first binary search so planning stays fast without ever being the final rule.
TTS_CHUNK_SOFT_TARGET = 700
# Backwards-compatible alias; every pipeline path reads the soft target above.
TTS_CHUNK_TARGET = TTS_CHUNK_SOFT_TARGET

# ``split_chapter``/``split_chapters`` default to the renderer's own layout budget so
# every chunk that reaches TTS was validated against the page it will be rendered on.
# Passing ``layout=None`` explicitly keeps the historic character-only behaviour, and
# ``layout=<budget>`` injects a specific budget (dependency injection keeps this
# module free of ``media`` imports at import time).
_DEFAULT_LAYOUT = object()

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
    # Layout metadata/reason per chunk, parallel to ``chunks``; empty when the plan
    # was built without a layout budget.
    layouts: List[Dict[str, Any]] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

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


class LayoutChunkError(ValueError):
    """A source unit cannot be split into a chunk that fits the rendered page.

    The message carries the same facts the renderer would report: chapter context,
    reason, character count, visible lines, validation font size and body width.
    """

    def __init__(self, reason, *, detail="", chapter=None, chars=0, visible_lines=0,
                 font_size=0, body_width=0, body_height=0, snippet=""):
        self.reason = reason
        self.detail = detail
        self.chapter = chapter
        self.chars = int(chars)
        self.visible_lines = int(visible_lines)
        self.font_size = int(font_size)
        self.body_width = int(body_width)
        self.body_height = int(body_height)
        self.snippet = (snippet or "")[:80]
        super().__init__(self._message())

    def _message(self) -> str:
        context = f"Chương {self.chapter}: " if self.chapter else ""
        detail = f"{self.detail} " if self.detail else ""
        return (f"{context}{detail}reason={self.reason}, chars={self.chars}, "
                f"visible_lines={self.visible_lines}, font_size={self.font_size}px, "
                f"body_width={self.body_width}px, body_height={self.body_height}px, "
                f"snippet={self.snippet!r}")

    def with_chapter(self, chapter) -> "LayoutChunkError":
        """Add chapter context without losing the measured facts."""
        return LayoutChunkError(self.reason, detail=self.detail, chapter=chapter, chars=self.chars,
                                visible_lines=self.visible_lines, font_size=self.font_size,
                                body_width=self.body_width, body_height=self.body_height,
                                snippet=self.snippet)


def default_layout_budget():
    """Build the renderer's own page budget (lazy import keeps this module portable)."""
    from media.text_layout import LayoutBudget
    return LayoutBudget.from_style()


def _layout_error(layout, reason, snippet, *, detail="", chapter=None, chars=None) -> LayoutChunkError:
    measurement = layout.measure(snippet) if layout is not None else None
    return LayoutChunkError(reason, detail=detail, chapter=chapter,
                            chars=len(snippet) if chars is None else chars,
                            visible_lines=getattr(measurement, "visible_lines", 0),
                            font_size=getattr(measurement, "font_size", 0),
                            body_width=getattr(measurement, "body_width", 0),
                            body_height=getattr(measurement, "body_height", 0),
                            snippet=snippet)


def chunk_layout_metadata(layout, text, strategy, reason) -> Dict[str, Any]:
    """Per-chunk layout facts for the manifest (never the chunk text itself).

    Carries everything the renderer and the diagnostics need to talk about the page:
    the measured pixel height, the fill ratio against the available band, the line
    count at the fixed font, and the layout fingerprint the plan was built with.
    """
    metadata: Dict[str, Any] = {"chars": len(text), "strategy": strategy, "reason": reason}
    if layout is None:
        return metadata
    described = layout.describe(text)
    metadata.update(visible_lines=described["visible_lines"], line_count=described["visible_lines"],
                    font_size=described["font_size"], body_width=described["body_width"],
                    body_height=described["body_height"], max_visible_lines=described["max_visible_lines"],
                    measured_height=described["measured_height"], fill_ratio=described["fill_ratio"],
                    text_sha256=described["text_sha256"], fits=described["fits"],
                    final_page=reason == "end_of_text",
                    layout_fingerprint=getattr(layout, "fingerprint", lambda: "")())
    return metadata


def _starts_with_loose_punctuation(text: str, position: int) -> bool:
    """True when the next chunk would begin with loose closing punctuation."""
    while position < len(text) and text[position].isspace():
        position += 1
    return position < len(text) and text[position] in ',.!?…;:”’)]}'


def _stop_reason(text, start, cut, window, layout, positions) -> str:
    """Why the planner stopped here: can the next semantic unit still be added?

    ``positions`` are the boundaries of the level that produced the cut, so the
    reason describes the real next unit (next sentence, clause or word) instead of
    an arbitrary nearer boundary.
    """
    if cut >= len(text):
        return "end_of_text"
    if layout is None or not positions:
        return "character_limit"
    following = bisect.bisect_right(positions, cut)
    if following >= len(positions) or positions[following] - start > window:
        return "character_limit"
    if not layout.fits(text[start:positions[following]].strip()):
        return "next_unit_would_exceed_page_height"
    return "character_limit"


def _last_fitting(text, start, positions, low, high, layout):
    """Farthest boundary in ``positions[low..high]`` whose rendered page still fits.

    The wrapped height of a growing prefix never shrinks, so ``fits`` is monotone
    over the boundary list and a binary search finds the page-filling boundary in
    ``log`` measures instead of growing the candidate character by character.
    """
    best, best_index = -1, -1
    while low <= high:
        middle = (low + high) // 2
        endpoint = positions[middle]
        if layout.fits(text[start:endpoint].strip()):
            best, best_index, low = endpoint, middle, middle + 1
        else:
            high = middle - 1
    while best > start and _starts_with_loose_punctuation(text, best):
        index = bisect.bisect_left(positions, best) - 1
        if index < 0:
            return -1
        best = positions[index]
    return best if best > start else -1


def _hard_cut(text, start, limit, layout, mask, chapter=None):
    """Last-resort character split: the largest prefix that still fits the page."""
    cut = min(start + limit, len(text))
    while cut > start and (mask[cut - 1] or (cut < len(text) and unicodedata.combining(text[cut]))):
        cut -= 1
    if cut <= start:
        raise _layout_error(layout, "no_safe_split", text[start:start + limit],
                            detail=f"No safe split within {limit} characters at character {start}.",
                            chapter=chapter, chars=min(limit, len(text) - start))
    if layout is None:
        return cut, BreakStrategy.HARD, True
    low, high, best = start + 1, cut, 0
    while low <= high:
        middle = (low + high) // 2
        end = middle
        while end > start and end < len(text) and unicodedata.combining(text[end]):
            end -= 1
        if end <= start:
            low = middle + 1
            continue
        if layout.fits(text[start:end].strip()):
            best, low = end, middle + 1
        else:
            high = middle - 1
    if best <= start:
        raise _layout_error(layout, "text_cannot_fit_page", text[start:start + limit],
                            detail="No prefix of this unit fits the page at the readable font size.",
                            chapter=chapter, chars=min(limit, len(text) - start))
    return best, BreakStrategy.HARD, True


def _select_cut(text, start, limit, levels, layout, mask, chapter=None):
    """Farthest semantic cut that also fits the rendered page.

    Character-only mode keeps the original behaviour exactly: the farthest boundary
    of the first usable level wins inside ``limit``.

    With a layout budget ``limit`` is only the soft search estimate: the window is
    the scan ceiling and every level is searched by binary search, so dense prose
    keeps growing until the next natural unit no longer fits the page, while
    dialogue-heavy text stops much earlier.  The measured rendered height — never a
    character count — decides where the page ends.  Returns
    ``(cut, strategy, hard, positions)`` where ``positions`` are the boundaries of the
    winning level.
    """
    ceiling = start + (MAX_CHUNK if layout is not None else limit)
    for positions, label in levels:
        low = bisect.bisect_right(positions, start)
        high = bisect.bisect_right(positions, ceiling) - 1
        if high < low:
            continue
        if layout is None:
            candidate = positions[high]
            # Do not begin the next chunk with loose closing punctuation.
            if _starts_with_loose_punctuation(text, candidate):
                continue
            return candidate, label, False, positions
        candidate = _last_fitting(text, start, positions, low, high, layout)
        if candidate > start:
            return candidate, label, False, positions
    cut, strategy, hard = _hard_cut(text, start, ceiling - start, layout, mask, chapter)
    return cut, strategy, hard, []


def split_text_by_limit(text: str, limit: int, *, abbreviations=None, layout=None) -> ChunkPlan:
    """Select boundaries by preference, preserving every meaningful character.

    ``layout`` is an optional renderer budget exposing ``fits()``/``measure()`` (see
    :class:`media.text_layout.LayoutBudget`).  With a budget, a cut is only valid
    while the candidate also fits the rendered page, so dialogue-heavy text yields
    shorter chunks instead of failing Step 4.  ``None`` keeps the character-only
    behaviour used by raw-text callers and unit tests.
    """
    from cleaning.tts_boundaries import DEFAULT_ABBREVIATIONS
    abbreviations = DEFAULT_ABBREVIATIONS if abbreviations is None else abbreviations
    limit = clamp_chunk_size(limit)
    plan = ChunkPlan()
    if not meaningful_text(text):
        return plan
    for start, end in protected_spans(text, abbreviations):
        if end - start > limit:
            raise _layout_error(layout, "protected_token_exceeds_limit", text[start:end],
                                detail=f"Protected token exceeds {limit} characters at character {start}.",
                                chars=end - start)
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
    # The layout budget decides cut points by measured pixel height; ``limit`` stays
    # only as the soft search estimate (and as the hard rule in character-only mode).
    window = MAX_CHUNK if layout is not None else limit
    while start < len(text):
        reason = "character_limit"
        cut_positions = []
        if len(text) - start <= window and (layout is None or layout.fits(text[start:].strip())):
            cut, strategy, hard = len(text), BreakStrategy.PARAGRAPH, False
        else:
            cut, strategy, hard, cut_positions = _select_cut(text, start, limit, levels, layout, mask)
        if layout is not None:
            reason = "hard_split" if hard else _stop_reason(text, start, cut, window, layout, cut_positions)
        piece = text[start:cut].strip()
        if meaningful_text(piece):
            if hard:
                plan.hard_splits.append(len(plan.chunks))
            plan.chunks.append(piece)
            plan.strategies.append(strategy)
            plan.layouts.append(chunk_layout_metadata(layout, piece, strategy, reason))
            plan.reasons.append(reason)
        elif piece and plan.chunks:
            if len(plan.chunks[-1]) + len(piece) > window:
                raise ValueError(f"Loose punctuation cannot fit chunk at character {start}")
            merged = plan.chunks[-1] + piece
            if layout is not None and not layout.fits(merged):
                raise _layout_error(layout, "loose_punctuation_over_budget", merged,
                                    detail="Loose punctuation cannot fit chunk at character "
                                           f"{start} without overflowing the page.",
                                    chars=len(merged))
            plan.chunks[-1] = merged
            plan.layouts[-1] = chunk_layout_metadata(layout, merged, plan.strategies[-1], plan.reasons[-1])
        start = cut
    return plan


def layout_statistics(plan: ChunkPlan) -> Dict[str, Any]:
    """Aggregate page-fill counters for plan statistics (no per-chunk log noise).

    Final pages (``end_of_text``) and standalone headings (``chapter_heading``) are
    legitimate short pages and are counted separately, so they never look like a
    planning failure.
    """
    from media.text_layout import LAYOUT_FILL_MIN  # lazy: keeps this module portable
    short_page = {"end_of_text", "chapter_heading"}
    fills = [float(entry["fill_ratio"]) for entry in plan.layouts if entry.get("fill_ratio") is not None]
    normal = [float(entry["fill_ratio"]) for entry in plan.layouts
              if entry.get("fill_ratio") is not None and entry.get("reason") not in short_page]
    visible = [int(entry.get("visible_lines", 0)) for entry in plan.layouts]
    return {
        "layout_limited_chunks": sum(1 for reason in plan.reasons
                                     if reason == "next_unit_would_exceed_page_height"),
        "layout_visible_lines_max": max(visible, default=0),
        "layout_fill_average": round(sum(fills) / len(fills), 4) if fills else 0.0,
        "layout_fill_min": round(min(normal), 4) if normal else 0.0,
        "layout_fill_max": round(max(fills), 4) if fills else 0.0,
        "layout_underfilled_pages": sum(1 for fill in normal if fill < LAYOUT_FILL_MIN),
        "layout_final_underfilled_pages": sum(1 for entry in plan.layouts
                                              if entry.get("reason") == "end_of_text"
                                              and float(entry.get("fill_ratio", 1.0)) < LAYOUT_FILL_MIN),
        "layout_overflow_pages": 0,
    }


def verify_chunk_integrity(source: str, plan: ChunkPlan, *, chapter=None) -> None:
    """Prove the plan is a lossless, ordered cover of ``source``.

    Whitespace between chunks belongs to the page margins, not to speech, so the
    check is whitespace-insensitive: every non-space character of the source must
    appear exactly once, in order, in exactly one chunk.  A dropped, duplicated or
    reordered character raises :class:`LayoutChunkError` before any TTS request, so a
    bad plan can never reach the audiobook or the renderer.
    """
    index = 0
    for number, chunk in enumerate(plan.chunks, start=1):
        for character in chunk:
            if character.isspace():
                continue
            while index < len(source) and source[index].isspace():
                index += 1
            if index >= len(source) or source[index] != character:
                raise _layout_error(
                    None, "text_integrity_violation", chunk,
                    detail=(f"Chunk {number} does not reproduce the source text at character {index} "
                            f"(expected {source[index:index + 1]!r})."),
                    chapter=chapter, chars=len(chunk))
            index += 1
    while index < len(source) and source[index].isspace():
        index += 1
    if index != len(source):
        raise _layout_error(None, "text_integrity_violation", source[index:index + 80],
                            detail=(f"The planned chunks cover {index} of {len(source)} source "
                                    "characters; text is missing."), chapter=chapter,
                            chars=len(source) - index)


def split_chapter(
    chapter: Chapter,
    limit: int,
    *,
    include_header: bool = False,
    min_chunk: int = MIN_CHUNK,
    abbreviations=None,
    layout=_DEFAULT_LAYOUT,
) -> ChunkPlan:
    """Split one chapter, never merging it with another chapter.

    ``layout`` defaults to the renderer's own page budget, so chapter-level callers
    (Step 3/4 pipelines) always produce page-safe chunks; pass ``layout=None`` for
    the historic character-only behaviour.
    """
    limit = clamp_chunk_size(limit, min_chunk)
    if layout is _DEFAULT_LAYOUT:
        layout = default_layout_budget()
    try:
        plan = split_text_by_limit(chapter.text or "", limit, abbreviations=abbreviations, layout=layout)
        if include_header and meaningful_text(chapter.header_line or ""):
            header = chapter.header_line.strip()
            if len(header) > limit:
                raise ValueError(f"Chapter {chapter.number}: heading exceeds {limit} characters")
            if layout is not None and not layout.fits(header):
                raise _layout_error(layout, "chapter_heading_over_budget", header,
                                    detail=f"Chapter {chapter.number}: heading does not fit the page.",
                                    chapter=chapter.number)
            plan.chunks.insert(0, header)
            plan.strategies.insert(0, BreakStrategy.PARAGRAPH)
            plan.layouts.insert(0, chunk_layout_metadata(layout, header, BreakStrategy.PARAGRAPH, "chapter_heading"))
            plan.reasons.insert(0, "chapter_heading")
            plan.hard_splits = [index + 1 for index in plan.hard_splits]
    except LayoutChunkError as error:
        if error.chapter is None:
            raise error.with_chapter(chapter.number) from None
        raise
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
    layout=_DEFAULT_LAYOUT,
) -> Tuple[List[Chunk], ChunkPlan, List[Diagnostic]]:
    """Produce chunk objects for every chapter, with diagnostics.

    ``layout`` defaults to the renderer's page budget, so every chunk produced for
    TTS was validated against the page it will be rendered on.
    """
    limit = clamp_chunk_size(limit, min_chunk)
    if layout is _DEFAULT_LAYOUT:
        layout = default_layout_budget()
    chunks: List[Chunk] = []
    combined = ChunkPlan()
    diagnostics: List[Diagnostic] = []
    order = 0

    for chapter in chapters:
        plan = split_chapter(chapter, limit, include_header=include_header, min_chunk=min_chunk,
                             abbreviations=abbreviations, layout=layout)
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
                layout=dict(plan.layouts[index - 1]) if index - 1 < len(plan.layouts) else {},
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
        combined.layouts.extend(plan.layouts)
        combined.reasons.extend(plan.reasons)
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

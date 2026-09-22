"""One source of truth for page text layout: fonts, wrapping and the body band.

The Step 3/4 chunk planner validates every narration chunk through
:class:`LayoutBudget`, while the video page renderer measures and wraps through the
same :func:`wrap_lines` / :func:`fit_body` implementations defined here.  A chunk the
planner accepts therefore cannot be rejected by the renderer for layout reasons, and
a style or font change moves both sides together through :func:`layout_identity`.

Only text layout lives here.  Frame drawing, neon geometry, colors, image
composition and ``render_page`` stay in :mod:`media.video_pages`.
"""
from __future__ import annotations

import json
import math
import re
import threading
import unicodedata
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from media.artifacts import sha256_file, sha256_text
from media.video import VideoValidationError


@dataclass(frozen=True)
class PageStyle:
    # v5 makes the rendered pixel height the single source of truth.  The body font
    # is fixed: the planner and the renderer always wrap with ``body_size`` and the
    # page is full when the wrapped block reaches the real ``body_bottom`` margin, so
    # a Step 3 chunk boundary never depends on a character target as its final rule.
    # ``body_max_lines`` stays only as a sanity guard against pathological input;
    # pixels decide acceptance, and a chunk that needs more height is re-split by the
    # planner instead of being shrunk below the readable font.
    version: str = "minimal-neon-theater-v5"
    width: int = 1920
    height: int = 1080
    frame: tuple[int, int, int, int] = (48, 27, 1872, 1053)  # 95% of the canvas
    radius: int = 36
    padding: int = 72
    blur: int = 42
    brightness: float = 0.68
    title_size: int = 54
    chapter_size: int = 32
    # The one fixed body size.  Both the planner and the renderer wrap at this size;
    # there is no per-page font search and no shrinking to rescue an oversized chunk.
    body_size: int = 36
    # Kept equal to ``body_size`` for compatibility with existing budgets and
    # fingerprints: it is the size every measurement uses.
    min_body_size: int = 36
    # The body block is centered in its own readable column.  Chunk size follows the
    # measured height in this column, so dense prose packs more characters per page
    # than dialogue-heavy text without any special casing.
    body_width: int = 1150
    # Sanity guards only — pixels decide.  A normal page lands wherever the wrapped
    # height lands; the ceiling merely rejects pathological single-chunk input that
    # the planner must re-split (and would reject first).
    body_min_lines: int = 1
    body_max_lines: int = 20
    # Blank lines between paragraphs advance half a step: enough for the eye to read
    # the break without spending a whole line on it.
    paragraph_gap: float = 0.5
    # The renderer's defensive guard may compress the blank-paragraph advance down to
    # this fraction of a line before a page is declared unfittable.  The requested
    # paragraph_gap is always tried first and the font never shrinks, so this only
    # matters for custom styles that raise the line budget.
    paragraph_gap_floor: float = 0.2
    # The body block runs down to this margin above the frame edge.  With the v4 line
    # ceiling the band is never the limiting factor; the margin keeps the block clear
    # of the neon outline for custom styles that raise the line budget.
    body_bottom_margin: int = 24
    line_spacing: float = 1.15
    # Vertical text grid shared by the renderer and the chunk planner.  The renderer
    # lays the block out with the real title/chapter height; the planner reserves
    # these maxima, so :func:`page_band` returns the worst-case band any page of this
    # style can offer.  Both sides read the same fields, so changing the page grid
    # automatically changes what chunk planning accepts.
    title_max_height: int = 156
    chapter_max_height: int = 84
    title_top_offset: int = 42
    title_gap: int = 12
    chapter_gap: int = 24
    body_top_gap: int = 30


DEFAULT_STYLE = PageStyle()
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Fill policy for layout-aware chunk planning.  Pixels — never a character count —
# decide a chunk boundary; these thresholds shape how full a normal page should be.
# A candidate chunk is grown until its measured rendered height reaches
# ``FILL_TARGET`` of the available body band; a boundary whose next semantic unit
# would overshoot ``FILL_MAX`` is kept, so pages land in the ``FILL_MIN .. FILL_MAX``
# window instead of being padded or split arbitrarily.
LAYOUT_FILL_TARGET = 0.96
LAYOUT_FILL_MIN = 0.90
LAYOUT_FILL_MAX = 1.00


def font_paths():
    return FONT_DIR / "LiberationSerif-Regular.ttf", FONT_DIR / "LiberationSerif-Bold.ttf"


# Glyph fallback for characters the Latin serif faces do not cover.
#
# Liberation Serif (the page typeface) ships no CJK glyphs: PIL renders a missing
# face as a zero-height blank, so brackets such as 【】「」《》 silently vanish from
# the page even though the chunk text, the TTS audio and the planner all carry
# them.  The CJK fallback below draws only the characters the primary face cannot
# (detected per glyph, cached per face/size), while every Latin/Vietnamese glyph
# keeps the exact Liberation advance it always had — measurements therefore stay
# planner/renderer identical.  The Noto Serif CJK collection matches the serif
# voice of the page and is OFL-licensed like the Liberation faces.
def fallback_font_paths():
    return FONT_DIR / "NotoSerifCJK-Regular.ttc", FONT_DIR / "NotoSerifCJK-Bold.ttc"


def _coverage_key(font, character):
    """Cache key for "does this face draw ``character``" (path+size identify the face)."""
    return (str(getattr(font, "path", "")), int(getattr(font, "size", 0)), character)


_COVERAGE = {}


# Characters that never select the CJK fallback: Liberation draws them correctly,
# while Noto Serif CJK gives a space a full CJK advance and a bare combining mark a
# dotted-circle base, both of which would visibly change the rendered page.
def _is_fallback_ignored(character):
    return character.isspace() or unicodedata.combining(character) != 0


def cover_font(font, fallback, character):
    """Return ``font`` when it really draws ``character``, else the CJK ``fallback``.

    A missing CJK face in Liberation produces a zero-height ``getmask`` box; any
    other character keeps the primary face and its exact advance.  Results are
    cached per face and character because the segmentation runs per wrapped line.
    """
    if not character or _is_fallback_ignored(character):
        return font
    key = _coverage_key(font, character)
    covered = _COVERAGE.get(key)
    if covered is None:
        try:
            mask = font.getmask(character)
            covered = mask.size[1] > 0
        except Exception:
            covered = False
        _COVERAGE[key] = covered
    return font if covered else fallback


def fallback_segments(text, font, fallback):
    """Split ``text`` into ``(face, segment)`` runs sharing one drawing face."""
    runs, current_face, current = [], None, []
    for character in text:
        face = cover_font(font, fallback, character)
        if face is not current_face:
            if current:
                runs.append((current_face, "".join(current)))
            current_face, current = face, [character]
        else:
            current.append(character)
    if current:
        runs.append((current_face, "".join(current)))
    return runs


def fallback_textlength(draw, text, *, font, fallback):
    """Advance of ``text`` measured with the same faces the painter will use."""
    return math.fsum(draw.textlength(segment, font=face)
                     for face, segment in fallback_segments(text, font, fallback))


@lru_cache(maxsize=8)
def _fallback_pair(font_path: str, size: int):
    """(primary, CJK fallback) faces for ``font_path`` at ``size``.

    Cached because :meth:`ImageFont.FreeTypeFont.getmask` is not thread-safe on a
    shared face instance; every call site resolves its faces through this builder
    (or through the thread-local :func:`load_font`) before measuring or drawing.
    """
    _regular, bold = font_paths()
    fallback_regular, fallback_bold = fallback_font_paths()
    fallback = fallback_bold if Path(font_path).name == Path(bold).name else fallback_regular
    return load_font(font_path, size), load_font(str(fallback), size)


def matching_fallback(font_path, size):
    """Public accessor: the CJK face paired with ``font_path`` at ``size``."""
    return _fallback_pair(str(font_path), int(size))[1]


def draw_segmented_text(draw, position, text, *, font, size, font_path, fill, anchor="ls"):
    """Draw ``text`` at ``position``, swapping in the CJK face per missing glyph.

    Returns ``(right, top, bottom)``: the pen position after the final advance plus
    the ink bbox of the whole line, so the caller can centre and frame-check with
    the same segmentation the painter used.  The bbox unions one measurement per
    face run, because ``textbbox`` with the primary face would collapse every
    missing glyph to zero height and clip the CJK runs out of the box.
    """
    fallback = matching_fallback(font_path, size)
    x, y = position
    top = bottom = None
    for run_face, segment in fallback_segments(text, font, fallback):
        draw.text((x, y), segment, font=run_face, fill=fill, anchor=anchor)
        x += draw.textlength(segment, font=run_face)
        try:
            run_top, run_bottom = draw.textbbox((x, y), segment, font=run_face,
                                                anchor=anchor, length=0)[1::2]
        except Exception:
            ascent, descent = run_face.getmetrics()
            run_top, run_bottom = y - ascent, y + descent
        top = run_top if top is None else min(top, run_top)
        bottom = run_bottom if bottom is None else max(bottom, run_bottom)
    if top is None:
        ascent, descent = font.getmetrics()
        top, bottom = y - ascent, y + descent
    return x, int(top), int(bottom)



# --------------------------------------------------------------- measurement


_LOCAL = threading.local()


def measure_draw():
    """Return this thread's measuring context; PIL draw objects are not shareable."""
    draw = getattr(_LOCAL, "draw", None)
    if draw is None:
        draw = ImageDraw.Draw(Image.new("L", (1, 1)))
        _LOCAL.draw = draw
    return draw


def load_font(path, size):
    """Load one font face per thread, so concurrent measuring cannot share state.

    A ``.ttc`` collection resolves to its first face; the page fonts never need a
    named sub-face beyond that.
    """
    cache = getattr(_LOCAL, "fonts", None)
    if cache is None:
        cache = _LOCAL.fonts = {}
    key = (str(path), int(size))
    font = cache.get(key)
    if font is None:
        font = ImageFont.truetype(str(path), int(size))
        cache[key] = font
    return font


def measure_length(draw, text, font, fallback=None):
    """Advance of ``text`` exactly as the painter will draw it.

    With a ``fallback`` face, characters the primary face cannot draw are measured
    in the CJK face, so the planner and the renderer agree on every width.
    """
    if fallback is None:
        return draw.textlength(text, font=font)
    return fallback_textlength(draw, text, font=font, fallback=fallback)


@lru_cache(maxsize=8192)
def _wrapped_lines(font_path: str, size: int, width: int, text: str):
    """Immutable measurement result: safe to cache and to share between threads."""
    primary, fallback = _fallback_pair(str(font_path), int(size))
    return tuple(wrap_lines(measure_draw(), text, primary, width, fallback=fallback))


def measure_text(text, style=DEFAULT_STYLE, *, font_path=None, size=None, width=None):
    """Wrap ``text`` exactly like the renderer does and return its visual lines."""
    size = int(style.min_body_size if size is None else size)
    width = int(style.body_width if width is None else width)
    return list(_wrapped_lines(str(font_path or font_paths()[0]), size, width, text))


def wrap_lines(draw, text, font, width, fallback=None):
    """Visual wrapping retains all characters; paragraph/line breaks stay explicit.

    ``fallback`` is the CJK face for characters ``font`` cannot draw; every width
    below is measured with the same faces the painter will use, so wrapping can
    never disagree with the drawn page.
    """
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        remaining = paragraph
        while remaining:
            if measure_length(draw, remaining, font, fallback) <= width:
                lines.append(remaining)
                break
            lo, hi = 1, len(remaining)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if measure_length(draw, remaining[:mid], font, fallback) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            cut = lo
            whitespace = [m.end() for m in re.finditer(r"\s+", remaining[:cut])]
            if whitespace:
                cut = whitespace[-1]
            while cut > 0 and cut < len(remaining) and unicodedata.combining(remaining[cut]):
                cut -= 1
            if cut <= 0 or measure_length(draw, remaining[:cut], font, fallback) > width:
                raise VideoValidationError("A glyph cannot fit inside the page")
            lines.append(remaining[:cut])
            remaining = remaining[cut:]
    return lines


def line_height(font, size, spacing):
    ascent, descent = font.getmetrics()
    return max(ascent + descent, math.ceil(size * spacing))


def block_height(lines, step, gap=1.0):
    """Advance of a wrapped block; blank paragraph lines take a fraction of one step."""
    blank = max(1, round(step * gap))
    return sum(blank if not line else step for line in lines)


def gap_ladder(gap, floor=None):
    """Descending paragraph gaps: the requested gap first, then compressed rungs.

    ``floor`` is the smallest fraction of a line a blank paragraph may advance.
    Without a usable floor the ladder is just the requested gap, which keeps the
    pre-v3 behaviour available to callers that want a single measurement.
    """
    values = [gap]
    if floor is not None and 0 < floor < gap:
        values += [round(gap * ratio, 3) for ratio in (0.8, 0.7, 0.6, 0.5, 0.4, 0.3)]
        values.append(round(float(floor), 3))
    ladder = []
    for value in values:
        if value != gap and floor is not None and value < floor:
            continue
        if value not in ladder:
            ladder.append(value)
    return sorted(ladder, reverse=True)


def fit_lines(draw, text, path, maximum, minimum, width, height, spacing, gap=1.0, gap_floor=None):
    """Largest readable size, then the largest paragraph gap, that fit the block.

    Sizes are searched from ``maximum`` down to ``minimum`` at the requested
    ``gap`` first, so pages that already fit keep the largest font and the normal
    paragraph spacing.  Only a page that overflows at every size compresses its
    blank-paragraph advance — never below ``gap_floor``, and never below
    ``minimum`` px — before it is reported as unfittable.

    Widths are measured with the CJK fallback faces, exactly like the painter.
    """
    needed = 0
    count = len(text.split("\n"))
    for candidate in gap_ladder(gap, gap_floor):
        for size in range(maximum, minimum - 1, -1):
            font = load_font(path, size)
            fallback = _fallback_pair(str(path), size)[1]
            lines = wrap_lines(draw, text, font, width, fallback=fallback)
            step = line_height(font, size, spacing)
            needed = block_height(lines, step, candidate)
            if needed <= height:
                return font, lines, step, candidate
            count = len(lines)
    raise VideoValidationError(
        f"Text cannot fit at readable minimum {minimum}px: {count} lines need {needed}px "
        f"of {height}px; correct the chunk in Step 3")


def fit_body(draw, text, path, style, width, height):
    """Lay out one page body at the one fixed size; pixels decide, never a search.

    The wrapped block is accepted when its measured height — including the blank
    advance of every paragraph break — stays inside ``height`` at the fixed
    ``style.body_size``.  Spacing may be compressed through the gap ladder (never the
    font size), and ``style.body_max_lines`` only guards against pathological input.
    A text that cannot fit is reported so the stale chunk is regenerated in Step 3;
    the renderer never re-chunks and never shrinks the font to rescue a bad chunk.

    This is the same acceptance rule :class:`LayoutBudget` applies while planning, so
    a chunk Step 3 accepted always renders here.  Widths are measured with the CJK
    fallback faces, exactly like the painter.
    """
    font = load_font(path, style.body_size)
    fallback = _fallback_pair(str(path), style.body_size)[1]
    lines = wrap_lines(draw, text, font, width, fallback=fallback)
    visible = sum(1 for line in lines if line.strip())
    step = line_height(font, style.body_size, style.line_spacing)
    if visible > style.body_max_lines:
        raise VideoValidationError(
            f"Page needs {visible} text lines at the fixed {style.body_size}px body font and cannot "
            f"respect the {style.body_max_lines}-line sanity guard; regenerate the Step 3 chunk plan")
    needed = 0
    for gap in gap_ladder(style.paragraph_gap, style.paragraph_gap_floor):
        needed = block_height(lines, step, gap)
        if needed <= height:
            return font, lines, step, gap, visible
    raise VideoValidationError(
        f"Chunk no longer matches the finalized page layout: {visible} lines need {needed}px of the "
        f"{height}px body band at the fixed {style.body_size}px font. The layout fingerprint changed "
        f"(style, font, title or band); regenerate the Step 3 chunks before rendering.")


def page_band(style=DEFAULT_STYLE, *, title_height=None, chapter_height=None):
    """Return the vertical band the body block may occupy on one page.

    The renderer passes the fitted per-line title/chapter advances, which expand to
    exactly ``body_bottom - body_top`` of the current page.  The chunk planner passes
    the measured reserves of the real title and of every chapter label the job can
    draw (see :func:`header_reserve`), so both sides validate against the same real
    band; omitting them falls back to the configured maxima for custom styles.
    """
    top = style.frame[1] + style.title_top_offset
    top += style.title_max_height if title_height is None else int(title_height)
    top += style.title_gap
    top += style.chapter_max_height if chapter_height is None else int(chapter_height)
    top += style.chapter_gap + style.body_top_gap
    return max(0, style.frame[3] - style.body_bottom_margin - top)


def scaled_style(width, height, style=DEFAULT_STYLE):
    """Return the same page style rescaled onto another canvas size.

    The text grid fields (``title_max_height``/``chapter_max_height``/gaps) are left
    untouched on purpose: the renderer used literal values for them before this
    module existed, so keeping them unscaled preserves existing output exactly.
    """
    ratio = width / style.width
    left, top, right, bottom = style.frame
    return replace(style, width=int(width), height=int(height),
                   frame=(round(left * ratio), round(top * ratio), round(right * ratio), round(bottom * ratio)),
                   radius=max(1, round(style.radius * ratio)), padding=max(1, round(style.padding * ratio)),
                   blur=max(1, round(style.blur * ratio)), title_size=max(1, round(style.title_size * ratio)),
                   chapter_size=max(1, round(style.chapter_size * ratio)),
                   body_size=max(1, round(style.body_size * ratio)),
                   min_body_size=max(1, round(style.min_body_size * ratio)),
                   body_width=max(1, round(style.body_width * ratio)),
                   body_bottom_margin=max(1, round(style.body_bottom_margin * ratio)))


# ------------------------------------------------- real page reservations

JUSTIFY_MAX_STEP_GAIN = 0.05   # +5% on the line step
JUSTIFY_MAX_GAP_GAIN = 0.30    # +30% on the blank-paragraph advance
JUSTIFY_MIN_GAPS = 3           # a very short page keeps its own spacing


def fitted_advance(text, *, font_path, maximum, minimum, width, height, spacing):
    """Vertical advance the renderer will spend on one heading or label.

    Uses the renderer's own :func:`fit_lines` with the renderer's own limits, so a
    reserve the planner computed is exactly what the page will use for that text.  A
    text that cannot fit the reserved band falls back to the whole reservation.
    """
    try:
        _font, lines, step, _gap = fit_lines(measure_draw(), text or "", font_path, int(maximum),
                                             int(minimum), int(width), int(height), float(spacing))
        return len(lines) * int(step)
    except VideoValidationError:
        return int(height)


def header_reserve(style=DEFAULT_STYLE, *, title="", chapter_labels=(), regular=None, bold=None):
    """Worst-case vertical space the real title/chapter areas of a job can consume.

    ``title`` is the exact title the pages will draw and ``chapter_labels`` every
    label a page of the job can carry (one per chapter plus the group fallback), so
    the measured reserve covers the real rendering instead of a magic maximum.
    """
    if regular is None or bold is None:
        default_regular, default_bold = font_paths()
        regular = regular or default_regular
        bold = bold or default_bold
    width = style.frame[2] - style.frame[0] - style.padding * 2
    title_height = fitted_advance(title, font_path=bold, maximum=style.title_size, minimum=36,
                                  width=width, height=style.title_max_height, spacing=1.12)
    # The empty label is always reserved: a page without a chapter caption still
    # advances one blank step, so ignoring it would under-reserve every page.
    labels = ["", *chapter_labels]
    chapter_height = max(fitted_advance(label, font_path=regular, maximum=style.chapter_size,
                                        minimum=24, width=width,
                                        height=style.chapter_max_height, spacing=1.2)
                         for label in labels)
    return int(title_height), int(chapter_height)


def renderer_budget(style=DEFAULT_STYLE, *, title="", chapter_labels=(), font_path=None) -> "LayoutBudget":
    """Page budget for a real job: the header band is measured, not maximised.

    The planner and every page of that job therefore share one measured
    ``available_body_height`` instead of reserving the worst case for a title that is
    one line long.  The reserve never shrinks below what any page of the job needs, so
    the ``Step 3 fits ⇒ Step 5 renders`` invariant still holds.
    """
    title_height, chapter_height = header_reserve(style, title=title, chapter_labels=chapter_labels)
    band = page_band(style, title_height=title_height, chapter_height=chapter_height)
    return LayoutBudget.from_style(style, font_path=font_path, body_height=band)


def justify_block(lines, step, gap, height, *, step_gain=JUSTIFY_MAX_STEP_GAIN,
                  gap_gain=JUSTIFY_MAX_GAP_GAIN, min_gaps=JUSTIFY_MIN_GAPS):
    """Distribute leftover vertical space across existing gaps, never the font.

    Returns ``(step, gap, leftover)``.  The line step may grow by at most
    ``step_gain`` and the blank-paragraph advance by at most ``gap_gain``; a page with
    fewer than ``min_gaps`` gaps keeps its natural spacing, and whatever cannot be
    spent within those limits stays as bottom whitespace instead of being forced.
    """
    current = block_height(lines, step, gap)
    leftover = int(height) - int(current)
    gaps = max(0, len(lines) - 1)
    if leftover <= 0 or gaps < min_gaps:
        return int(step), gap, 0
    blanks = sum(1 for line in lines[:-1] if not line)
    step_extra = min(leftover // gaps, max(0, round(step * step_gain)))
    new_step = int(step) + int(step_extra)
    remaining = leftover - int(step_extra) * gaps
    new_gap = gap
    if blanks and remaining > 0:
        gap_extra = min(remaining // blanks, max(0, round(step * gap * gap_gain)))
        if gap_extra > 0:
            new_gap = (round(step * gap) + int(gap_extra)) / float(step)
    return new_step, float(new_gap), max(0, int(height) - block_height(lines, new_step, new_gap))


# ------------------------------------------------------- planner-facing budget


@dataclass(frozen=True)
class PageMeasurement:
    """Result of measuring one candidate chunk against one page layout."""

    visible_lines: int
    total_lines: int
    font_size: int
    body_width: int
    body_height: int
    block_height: int
    paragraph_gap: float
    fits: bool
    reason: str  # "" when it fits, otherwise why the page rejects it


@dataclass(frozen=True)
class LayoutBudget:
    """The renderer's own page budget, reused by the Step 3 chunk planner.

    The wrapped pixel height is the acceptance rule: a candidate chunk fits when its
    block height at the fixed ``min_font_size`` (== ``body_size``) stays inside
    ``body_height`` with a paragraph gap from the renderer's gap ladder.
    ``body_max_lines`` is only a sanity guard against pathological input.  The same
    wrapping, spacing and band drive ``fit_body`` in the renderer, so a chunk the
    planner accepts cannot be rejected by the renderer for layout reasons.
    """

    style_version: str
    font_path: str
    min_font_size: int
    body_width: int
    body_max_lines: int
    body_height: int
    line_spacing: float
    paragraph_gap: float
    paragraph_gap_floor: float

    @classmethod
    def from_style(cls, style=DEFAULT_STYLE, *, font_path=None, body_height=None) -> "LayoutBudget":
        return cls(style.version, str(font_path or font_paths()[0]), int(style.min_body_size),
                   int(style.body_width), int(style.body_max_lines),
                   int(page_band(style) if body_height is None else body_height),
                   float(style.line_spacing), float(style.paragraph_gap), float(style.paragraph_gap_floor))

    def measure(self, text) -> PageMeasurement:
        """Wrap like the renderer and accept on measured pixels, not line counts."""
        text = text or ""
        try:
            lines = measure_text(text, style=DEFAULT_STYLE, font_path=self.font_path,
                                 size=self.min_font_size, width=self.body_width)
        except VideoValidationError:
            return PageMeasurement(0, 0, self.min_font_size, self.body_width, self.body_height, 0,
                                   0.0, False, "unrenderable_text")
        visible = sum(1 for line in lines if line.strip())
        font = load_font(self.font_path, self.min_font_size)
        step = line_height(font, self.min_font_size, self.line_spacing)
        if visible > self.body_max_lines:
            # Sanity guard for pathological input; normal chunks are bounded by the
            # pixel band long before this ceiling is reached.
            return PageMeasurement(visible, len(lines), self.min_font_size, self.body_width,
                                   self.body_height, block_height(lines, step, self.paragraph_gap),
                                   self.paragraph_gap, False, "visual_line_budget")
        for gap in gap_ladder(self.paragraph_gap, self.paragraph_gap_floor):
            height = block_height(lines, step, gap)
            if height <= self.body_height:
                return PageMeasurement(visible, len(lines), self.min_font_size, self.body_width,
                                       self.body_height, height, gap, True, "")
        return PageMeasurement(visible, len(lines), self.min_font_size, self.body_width, self.body_height,
                               block_height(lines, step, self.paragraph_gap_floor), self.paragraph_gap_floor,
                               False, "vertical_space")

    def fits(self, text) -> bool:
        return self.measure(text).fits

    def measure_height(self, text) -> int:
        """Measured rendered height of ``text`` in pixels (whether it fits or not)."""
        return self.measure(text).block_height

    def fill_ratio(self, text) -> float:
        """Fraction of the available body band this text would occupy."""
        if self.body_height <= 0:
            return 0.0
        return min(1.0, self.measure(text).block_height / self.body_height)

    @property
    def available_height(self) -> int:
        return self.body_height

    def describe(self, text) -> dict:
        """Stable per-chunk metadata for manifests and diagnostics (no chunk text)."""
        measurement = self.measure(text)
        return {"chars": len(text or ""), "visible_lines": measurement.visible_lines,
                "font_size": measurement.font_size, "body_width": measurement.body_width,
                "body_height": measurement.body_height, "max_visible_lines": self.body_max_lines,
                "measured_height": measurement.block_height,
                "fill_ratio": round(self.fill_ratio(text), 4),
                "text_sha256": sha256_text(text or ""), "fits": measurement.fits,
                "reason": measurement.reason}

    def identity(self) -> dict:
        """Identity of this exact budget, including its measured body band."""
        return budget_identity(self)

    def fingerprint(self) -> str:
        return sha256_text(json.dumps(self.identity(), ensure_ascii=False, sort_keys=True))


@lru_cache(maxsize=8)
def font_identity(path: str) -> str:
    """Stable font identity; a missing face is reported instead of raising."""
    candidate = Path(path)
    try:
        return f"{candidate.name}:{sha256_file(candidate)}"
    except OSError:
        return f"{candidate.name}:missing"


def layout_identity(style=DEFAULT_STYLE, *, font_path=None) -> dict:
    """Identity of every layout input that can move a chunk boundary.

    Stored with the chunk plan, so a style, font or band change invalidates an old
    plan instead of silently keeping chunks that no longer fit the page.  The CJK
    fallback faces are part of the identity: they change both what the renderer
    draws and how wide the wrapped lines measure.
    """
    path = str(font_path or font_paths()[0])
    return {"style_version": style.version, "font_identity": font_identity(path),
            "fallback_identities": [font_identity(str(p)) for p in fallback_font_paths()],
            "font_size": int(style.min_body_size), "body_width": int(style.body_width),
            "max_visible_lines": int(style.body_max_lines), "body_band": int(page_band(style)),
            "line_spacing": float(style.line_spacing), "paragraph_gap": float(style.paragraph_gap),
            "paragraph_gap_floor": float(style.paragraph_gap_floor),
            "fill_target": LAYOUT_FILL_TARGET, "fill_min": LAYOUT_FILL_MIN,
            "fill_max": LAYOUT_FILL_MAX}


def budget_identity(budget, style=DEFAULT_STYLE) -> dict:
    """Identity of one injected budget (its band can differ from the style maximum)."""
    identity = dict(layout_identity(style, font_path=budget.font_path))
    identity["body_band"] = int(budget.body_height)
    return identity


def layout_fingerprint(budget, style=DEFAULT_STYLE) -> str:
    """Short digest of a budget identity, stored with every planned chunk."""
    return sha256_text(json.dumps(budget_identity(budget, style), ensure_ascii=False, sort_keys=True))

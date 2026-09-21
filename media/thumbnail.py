"""Deterministic YouTube thumbnail rendering for Step 3.

The still image reuses the Step 4 neon-theater page style — the same glowing
rounded frame, panel palette, and Liberation Serif typography — so thumbnail and
video share one visual identity; the title and the chapter range both use its bold
face. Unlike a video page, the cover is never blurred or dimmed: it fills all
1280×720 pixels, and the labels sit in a dark band across the bottom 20% of the
picture.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from media.video_pages import (CHAPTER_COLOR, DEFAULT_STYLE, DIVIDER_COLOR, FRAME_GLOW, FRAME_GLOW_WIDTH,
                               PANEL_COLOR, TITLE_COLOR, draw_frame, font_paths, line_height, scaled_style,
                               wrap_lines)
from media.text_layout import draw_segmented_text, matching_fallback, measure_length


WIDTH = 1280
HEIGHT = 720
CAPTION_RATIO = 0.20                       # labels over the bottom fifth of the picture
CAPTION_HEIGHT = round(HEIGHT * CAPTION_RATIO)
FRAME_INSET = 40                           # the neon frame hugs the picture edge
MINIMUM_TITLE_SIZE = 20
MINIMUM_CHAPTER_SIZE = 14
TITLE_SPACING = 1.12
CHAPTER_SPACING = 1.2
CAPTION_GAP = 10
TITLE_GLOW_COLOR = (255, 255, 255, 65)

_GEOMETRY = scaled_style(WIDTH, HEIGHT)    # same frame style, thumbnail-sized canvas
FRAME_RADIUS = _GEOMETRY.radius
CAPTION_PADDING = _GEOMETRY.padding
_SCALE = WIDTH / DEFAULT_STYLE.width
GLOW_BLUR = max(1, round(FRAME_GLOW * _SCALE))
GLOW_WIDTH = max(2, round(FRAME_GLOW_WIDTH * _SCALE))
TITLE_GLOW_BLUR = max(1, round(5 * _SCALE))


def _atomic_save_jpeg(image: Image.Image, path: Path, *, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".jpg", dir=path.parent)
    os.close(descriptor)
    try:
        image.save(temporary, format="JPEG", quality=max(70, min(int(quality), 100)), optimize=True)
        if Path(temporary).stat().st_size <= 0:
            raise RuntimeError("Generated thumbnail is empty.")
        os.replace(temporary, path)
    except Exception:
        try:
            Path(temporary).unlink()
        except OSError:
            pass
        raise


def _wrap_title(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Word-wrap a heading into at most two lines without discarding any text."""
    words = (title or "").split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= 2:
        return lines
    # Rebalance a long heading into exactly two lines; size fitting then shrinks
    # the font until both lines fit instead of discarding title text.
    midpoint = max(1, len(words) // 2)
    return [" ".join(words[:midpoint]), " ".join(words[midpoint:])]


def _fit_caption(draw, title, chapter, bold, width, height):
    """Shrink the video-sized title/chapter pair until both fit the caption band."""
    for title_size in range(DEFAULT_STYLE.title_size, MINIMUM_TITLE_SIZE - 1, -1):
        chapter_size = max(MINIMUM_CHAPTER_SIZE,
                           round(title_size * DEFAULT_STYLE.chapter_size / DEFAULT_STYLE.title_size))
        title_font = ImageFont.truetype(str(bold), title_size)
        # The chapter number shares the title's bold face so the group range reads as
        # part of the cover typography instead of a lighter caption.
        chapter_font = ImageFont.truetype(str(bold), chapter_size)
        title_lines = _wrap_title(draw, title, title_font, width)
        if len(title_lines) > 2 or any(draw.textlength(line, font=title_font) > width for line in title_lines):
            continue
        chapter_lines = wrap_lines(draw, chapter, chapter_font, width)
        title_step = line_height(title_font, title_size, TITLE_SPACING)
        chapter_step = line_height(chapter_font, chapter_size, CHAPTER_SPACING)
        if len(title_lines) * title_step + CAPTION_GAP + len(chapter_lines) * chapter_step <= height:
            return title_font, title_lines, title_step, chapter_font, chapter_lines, chapter_step
    raise RuntimeError("Tiêu đề và số chương quá dài để vừa dải thumbnail 20%.")


def _paint_centered(draw, lines, font, step, y, fill, font_path=None, size=None):
    """Draw the video page's centered baseline-aligned text block.

    Like the video page painter, CJK glyphs missing from Liberation are drawn with
    the bundled Noto Serif CJK face and centring measures the same segmentation.
    """
    ascent, _ = font.getmetrics()
    fallback = matching_fallback(font_path, size or font.size) if font_path else None
    for line in lines:
        tx = (WIDTH - measure_length(draw, line, font, fallback)) / 2
        draw_segmented_text(draw, (tx, y + ascent), line, font=font,
                            size=size or font.size, font_path=font_path or str(font.path),
                            fill=fill, anchor="ls")
        y += step
    return y


def generate_thumbnail(
    image_path: Path,
    output_dir: Path,
    *,
    title: str,
    chapter: str,
    quality: int = 95,
) -> Path:
    """Create a 1280×720 thumbnail and return its saved JPEG path."""
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")
    with Image.open(image_path) as source:
        cover = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (WIDTH, HEIGHT),
                             method=Image.Resampling.LANCZOS)
    canvas = cover.convert("RGBA")
    frame = (FRAME_INSET, FRAME_INSET, WIDTH - FRAME_INSET - 1, HEIGHT - FRAME_INSET - 1)
    band_top = frame[3] - CAPTION_HEIGHT + 1
    band = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(band).rounded_rectangle(frame, radius=FRAME_RADIUS, fill=255)
    ImageDraw.Draw(band).rectangle((0, 0, WIDTH - 1, band_top - 1), fill=0)
    canvas = Image.alpha_composite(canvas, Image.composite(
        Image.new("RGBA", canvas.size, PANEL_COLOR), Image.new("RGBA", canvas.size, (0, 0, 0, 0)), band))
    canvas = draw_frame(canvas, frame, radius=FRAME_RADIUS, glow=GLOW_BLUR, glow_width=GLOW_WIDTH, fill=None)
    draw = ImageDraw.Draw(canvas)
    _regular, bold = font_paths()
    text_width = frame[2] - frame[0] - CAPTION_PADDING * 2
    title_font, title_lines, title_step, chapter_font, chapter_lines, chapter_step = _fit_caption(
        draw, title, chapter, bold, text_width, CAPTION_HEIGHT)
    used = len(title_lines) * title_step + CAPTION_GAP + len(chapter_lines) * chapter_step
    y = band_top + max(CAPTION_GAP, (CAPTION_HEIGHT - used) // 2)
    draw.line((frame[0] + CAPTION_PADDING, band_top, frame[2] - CAPTION_PADDING, band_top),
              fill=DIVIDER_COLOR, width=1)
    # A soft title glow contains no additional visual content.
    glow = Image.new("RGBA", canvas.size)
    glow_draw = ImageDraw.Draw(glow)
    for index, line in enumerate(title_lines):
        glow_draw.text(((WIDTH - glow_draw.textlength(line, font=title_font)) / 2, y + index * title_step),
                       line, font=title_font, fill=TITLE_GLOW_COLOR)
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(TITLE_GLOW_BLUR)))
    draw = ImageDraw.Draw(canvas)
    title_size = title_font.size
    y = _paint_centered(draw, title_lines, title_font, title_step, y, TITLE_COLOR,
                        font_path=bold, size=title_size) + CAPTION_GAP
    _paint_centered(draw, chapter_lines, chapter_font, chapter_step, y, CHAPTER_COLOR,
                    font_path=bold, size=chapter_font.size)
    output_path = Path(output_dir) / f"{image_path.stem}_youtube.jpg"
    _atomic_save_jpeg(canvas.convert("RGB"), output_path, quality=quality)
    return output_path

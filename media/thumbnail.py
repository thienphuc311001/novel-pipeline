"""Deterministic YouTube thumbnail rendering for Step 4."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps


WIDTH = 1280
HEIGHT = 720
DEFAULT_BANNER_HEIGHT = 145


def bundled_font_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates: Iterable[str | Path] = (
        bundled_font_path(),
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    raise RuntimeError("Không tìm thấy phông DejaVu Sans Bold đi kèm ứng dụng.")


def _wrap_title(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = (title or "").split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= 2:
        return lines
    # Rebalance a long heading into exactly two lines; font fitting will reduce
    # size until each line fits rather than discarding title text.
    midpoint = max(1, len(words) // 2)
    return [" ".join(words[:midpoint]), " ".join(words[midpoint:])]


def _fit_text(
    draw: ImageDraw.ImageDraw,
    title: str,
    chapter: str,
    banner_height: int,
    *,
    max_width: int,
) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, List[str], int]:
    available_height = banner_height - 22
    for title_size in range(52, 15, -1):
        chapter_size = max(16, int(title_size * 0.70))
        title_font = _font(title_size)
        chapter_font = _font(chapter_size)
        title_lines = _wrap_title(draw, title, title_font, max_width)
        if len(title_lines) > 2:
            continue
        title_height = sum(
            draw.textbbox((0, 0), line or " ", font=title_font)[3]
            for line in title_lines
        )
        chapter_box = draw.textbbox((0, 0), chapter or " ", font=chapter_font)
        widest = max(
            [draw.textbbox((0, 0), line or " ", font=title_font)[2] for line in title_lines]
            + [chapter_box[2]]
        )
        if widest <= max_width and title_height + chapter_box[3] + 10 <= available_height:
            return title_font, chapter_font, title_lines, title_height
    # A minimum-size rendition is still preferable to a silent truncation.
    return _font(16), _font(16), _wrap_title(draw, title, _font(16), max_width), 16


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


def generate_thumbnail(
    image_path: Path,
    output_dir: Path,
    *,
    title: str,
    chapter: str,
    banner_height: int = DEFAULT_BANNER_HEIGHT,
    quality: int = 95,
) -> Path:
    """Create a 1280×720 thumbnail and return its saved JPEG path."""
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")
    banner_height = max(100, min(int(banner_height), HEIGHT - 100))
    top_height = HEIGHT - banner_height
    with Image.open(image_path) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        top = ImageOps.fit(
            source,
            (WIDTH, top_height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "black")
    canvas.paste(top, (0, 0))
    draw = ImageDraw.Draw(canvas)
    title_font, chapter_font, title_lines, title_height = _fit_text(
        draw, title, chapter, banner_height, max_width=WIDTH - 80
    )
    title_line_heights = [
        draw.textbbox((0, 0), line or " ", font=title_font)[3] for line in title_lines
    ]
    chapter_height = draw.textbbox((0, 0), chapter or " ", font=chapter_font)[3]
    used_height = sum(title_line_heights) + chapter_height + 10
    y = top_height + max(8, (banner_height - used_height) // 2)
    shadow = (0, 0, 0)
    for line, line_height in zip(title_lines, title_line_heights):
        box = draw.textbbox((0, 0), line or " ", font=title_font)
        x = (WIDTH - (box[2] - box[0])) // 2
        draw.text((x + 2, y + 2), line, font=title_font, fill=shadow)
        draw.text((x, y), line, font=title_font, fill="white")
        y += line_height
    y += 10
    chapter_box = draw.textbbox((0, 0), chapter or " ", font=chapter_font)
    chapter_x = (WIDTH - (chapter_box[2] - chapter_box[0])) // 2
    draw.text((chapter_x + 2, y + 2), chapter, font=chapter_font, fill=shadow)
    draw.text((chapter_x, y), chapter, font=chapter_font, fill="white")

    name = f"{image_path.stem}_youtube.jpg"
    output_path = Path(output_dir) / name
    _atomic_save_jpeg(canvas, output_path, quality=quality)
    return output_path

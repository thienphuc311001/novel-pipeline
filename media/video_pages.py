"""Exact TTS text, cached neon-theater pages, and measured static timelines."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from threading import Event

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from media.artifacts import atomic_write_json, atomic_write_text, sha256_file, sha256_text
from media.video import VideoValidationError, probe_audio, audio_rounding_tolerance


@dataclass(frozen=True)
class PageStyle:
    version: str = "minimal-neon-theater-v1"
    width: int = 1920
    height: int = 1080
    frame: tuple[int, int, int, int] = (192, 108, 1728, 972)
    radius: int = 36
    padding: int = 72
    blur: int = 42
    brightness: float = 0.68
    title_size: int = 54
    chapter_size: int = 32
    body_size: int = 30
    # The body font searches from body_size downwards, so every page that fits keeps
    # the largest size; only overflowing pages shrink, and never below this floor.
    min_body_size: int = 26
    # Blank lines between paragraphs advance half a step: enough for the eye to read
    # the break without spending a whole line on it, which keeps paragraph-heavy
    # chunks inside the readable band instead of failing Step 4.
    paragraph_gap: float = 0.5
    line_spacing: float = 1.15


DEFAULT_STYLE = PageStyle()
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# One palette shared by every rendered surface (video pages and thumbnails).
PANEL_COLOR = (8, 10, 23, 220)
PANEL_OUTLINE = (159, 176, 213, 100)
DIVIDER_COLOR = (174, 179, 210, 100)
TITLE_COLOR = (250, 250, 255)
CHAPTER_COLOR = (201, 183, 235)
BODY_COLOR = (244, 244, 250)
GLOW_COLORS = (((76, 221, 245, 75), -1), ((154, 112, 224, 65), 1))
FRAME_GLOW = 12
FRAME_GLOW_WIDTH = 5
FRAME_OUTLINE_WIDTH = 2


def font_paths():
    return FONT_DIR / "LiberationSerif-Regular.ttf", FONT_DIR / "LiberationSerif-Bold.ttf"


def visual_settings(style=DEFAULT_STYLE):
    regular, bold = font_paths()
    settings = asdict(style)
    settings["frame"] = list(style.frame)  # Stable equality after JSON recovery.
    return {"style": settings, "fonts": {p.name: sha256_file(p) for p in (regular, bold)}}


def _identity(value):
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def load_narration(media):
    """Fail closed: only exact full requests in a complete recorded merge qualify."""
    try:
        manifest_path = Path(media.tts_manifest_path)
        folder = Path(media.output_dir).resolve()
        if manifest_path.resolve().parent.parent != folder:
            raise ValueError("TTS manifest must be inside the job's chunk directory")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        ordered = data["ordered_chunks"]
        merge = data["merge"]
        if data["schema_version"] != 2 or not merge["complete"] or not ordered:
            raise ValueError("A completed full-chunk audiobook is required")
        orders = list(range(1, len(ordered) + 1))
        if [c["order"] for c in ordered] != orders or merge["orders"] != orders:
            raise ValueError("Chunk order does not match the final audiobook")
        if (Path(merge["file"]).resolve() != Path(media.audiobook_path).resolve()
                or merge["mp3_sha256"] != sha256_file(Path(media.audiobook_path))):
            raise ValueError("Final audiobook differs from its recorded merge")
        records = []
        for chunk in ordered:
            record = data["chunks"][str(chunk["order"])]
            expected_name = f"chunk_{chunk['order']:05d}.mp3"
            path = manifest_path.parent / expected_name
            if (record["order"] != chunk["order"] or record["chapter"] != chunk["chapter"]
                    or record["text"] != chunk["text"] or record["text_sha256"] != sha256_text(chunk["text"])
                    or chunk["text_sha256"] != record["text_sha256"]
                    or record["voice"] != data["settings"]["voice"]
                    or record["request_mode"] != "full_chunk" or record["file"] != expected_name
                    or not path.is_file() or path.stat().st_size <= 0
                    or record["mp3_sha256"] != sha256_file(path)):
                raise ValueError(f"Chunk {chunk['order']} text/audio provenance changed")
            records.append(dict(record, mp3_path=str(path.resolve())))
        if merge["chunks"] != [data["chunks"][str(o)] for o in orders]:
            raise ValueError("Chunk MP3s differ from those used in the audiobook")
        effective_hash = sha256_text("\n".join(f"{r['order']}\0{r['text']}" for r in records))
        if getattr(media, "effective_text_sha256", "") and effective_hash != media.effective_text_sha256:
            raise ValueError("Narration differs from the current Step 3 effective text")
        return records
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise VideoValidationError(f"Resume/regenerate Step 3 before rendering: {error}") from error


def source_fingerprint(media):
    records = load_narration(media)
    timeline_path = Path(media.output_dir) / "video_timeline.json"
    if not timeline_path.is_file():
        raise VideoValidationError("Create a measured page timeline in Step 4 before recording/uploading the video")
    return {"profile": visual_settings(), "title": media.title, "chapter": media.chapter,
            "thumbnail_sha256": sha256_file(Path(media.thumbnail_path)),
            "audiobook_sha256": sha256_file(Path(media.audiobook_path)),
            "thumbnail": dict(getattr(media, "thumbnail_fingerprint", {})),
            "audio": dict(getattr(media, "audiobook_fingerprint", {})),
            "chunks": records,
            "timeline_sha256": sha256_file(timeline_path)}


def file_states(paths):
    states = {}
    try:
        for path in paths:
            path = Path(path).resolve()
            stat = path.stat()
            states[str(path)] = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        return states
    except OSError as error:
        raise VideoValidationError(f"Video input disappeared: {error}") from error


def require_unchanged(states):
    if file_states(states) != states:
        raise VideoValidationError("Video inputs changed during preparation/rendering; regenerate Step 4")


def _input_paths(media, records):
    folder = Path(media.output_dir)
    return [media.tts_manifest_path, media.audiobook_path, media.thumbnail_path, *font_paths(),
            *(r['mp3_path'] for r in records),
            *(folder / name for name in ('tts_chunks.json', 'tts_overrides.json') if (folder / name).exists())]


def wrap_lines(draw, text, font, width):
    """Visual wrapping retains all characters; paragraph/line breaks stay explicit."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        remaining = paragraph
        while remaining:
            if draw.textlength(remaining, font=font) <= width:
                lines.append(remaining)
                break
            lo, hi = 1, len(remaining)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if draw.textlength(remaining[:mid], font=font) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            cut = lo
            whitespace = [m.end() for m in re.finditer(r"\s+", remaining[:cut])]
            if whitespace:
                cut = whitespace[-1]
            while cut > 0 and cut < len(remaining) and unicodedata.combining(remaining[cut]):
                cut -= 1
            if cut <= 0 or draw.textlength(remaining[:cut], font=font) > width:
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


def fit_lines(draw, text, path, maximum, minimum, width, height, spacing, gap=1.0):
    for size in range(maximum, minimum - 1, -1):
        font = ImageFont.truetype(str(path), size)
        lines = wrap_lines(draw, text, font, width)
        step = line_height(font, size, spacing)
        if block_height(lines, step, gap) <= height:
            return font, lines, step
    raise VideoValidationError(f"Text cannot fit at readable minimum {minimum}px; correct the chunk in Step 3")


def scaled_style(width, height, style=DEFAULT_STYLE):
    """Return the same page style rescaled onto another canvas size."""
    ratio = width / style.width
    left, top, right, bottom = style.frame
    return replace(style, width=int(width), height=int(height),
                   frame=(round(left * ratio), round(top * ratio), round(right * ratio), round(bottom * ratio)),
                   radius=max(1, round(style.radius * ratio)), padding=max(1, round(style.padding * ratio)),
                   blur=max(1, round(style.blur * ratio)), title_size=max(1, round(style.title_size * ratio)),
                   chapter_size=max(1, round(style.chapter_size * ratio)),
                   body_size=max(1, round(style.body_size * ratio)),
                   min_body_size=max(1, round(style.min_body_size * ratio)))


def draw_frame(canvas, frame, *, radius, glow=FRAME_GLOW, glow_width=FRAME_GLOW_WIDTH,
               outline_width=FRAME_OUTLINE_WIDTH, fill=PANEL_COLOR):
    """Composite the neon rounded frame (glow layers, panel, outline) onto an RGBA canvas."""
    edges = (frame[0], frame[1], frame[2] - 1, frame[3] - 1)
    for color, offset in GLOW_COLORS:
        layer = Image.new("RGBA", canvas.size)
        ImageDraw.Draw(layer).rounded_rectangle(edges, radius=radius, outline=color, width=glow_width)
        canvas = Image.alpha_composite(canvas, layer.filter(ImageFilter.GaussianBlur(glow + offset)))
    panel = Image.new("RGBA", canvas.size)
    ImageDraw.Draw(panel).rounded_rectangle(edges, radius=radius, fill=fill, outline=PANEL_OUTLINE,
                                            width=outline_width)
    return Image.alpha_composite(canvas, panel)


def render_page(thumbnail, output, *, title, chapter, text, style=DEFAULT_STYLE):
    with Image.open(thumbnail) as source:
        background = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"),
                                  (style.width, style.height), method=Image.Resampling.LANCZOS)
    background = ImageEnhance.Brightness(background.filter(ImageFilter.GaussianBlur(style.blur))).enhance(style.brightness)
    canvas = draw_frame(background.convert("RGBA"), style.frame, radius=style.radius)
    draw = ImageDraw.Draw(canvas)
    regular, bold = font_paths()
    left, top, right, bottom = style.frame
    x, y = left + style.padding, top + 42
    width = right - left - style.padding * 2
    title_font, title_lines, title_h = fit_lines(draw, title, bold, style.title_size, 36, width, 156, 1.12)
    chapter_font, chapter_lines, chapter_h = fit_lines(draw, chapter, regular, style.chapter_size, 24, width, 84, 1.2)
    bounds = []
    def paint(lines, font, step, y, color, centered=False, gap=1.0):
        blank_step = max(1, round(step * gap))
        for line in lines:
            tx = (style.width - draw.textlength(line, font=font)) / 2 if centered else x
            ascent, _ = font.getmetrics()
            bbox = draw.textbbox((tx, y + ascent), line, font=font, anchor="ls")
            if line:
                if bbox[0] < left or bbox[2] > right or bbox[1] < top or bbox[3] > bottom:
                    raise VideoValidationError("Text would overflow the content frame")
                bounds.append(bbox)
            draw.text((tx, y + ascent), line, font=font, fill=color, anchor="ls")
            y += step if line else blank_step
        return y
    # A soft title glow contains no additional visual content.
    glow = Image.new("RGBA", canvas.size)
    gd = ImageDraw.Draw(glow)
    for i, line in enumerate(title_lines):
        gd.text(((style.width - gd.textlength(line, font=title_font)) / 2, y + i * title_h),
                line, font=title_font, fill=(255, 255, 255, 65))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(5)))
    draw = ImageDraw.Draw(canvas)
    y = paint(title_lines, title_font, title_h, y, TITLE_COLOR, True) + 12
    y = paint(chapter_lines, chapter_font, chapter_h, y, CHAPTER_COLOR, True) + 24
    draw.line((x, y, right - style.padding, y), fill=DIVIDER_COLOR, width=1)
    body_top, body_bottom = y + 30, bottom - 44
    font, lines, line_step = fit_lines(draw, text, regular, style.body_size, style.min_body_size,
                                       width, body_bottom - body_top, style.line_spacing, style.paragraph_gap)
    body_y = body_top + (body_bottom - body_top - block_height(lines, line_step, style.paragraph_gap)) / 2
    paint(lines, font, line_step, body_y, BODY_COLOR, gap=style.paragraph_gap)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".page_", suffix=".png", dir=output.parent)
    os.close(fd)
    try:
        canvas.convert("RGB").save(name, format="PNG")
        os.replace(name, output)
    finally:
        Path(name).unlink(missing_ok=True)
    return {"font_size": font.size, "text_bounds": bounds}


@dataclass
class VideoPage:
    order: int
    chapter: int
    text: str
    text_sha256: str
    mp3_path: str
    mp3_sha256: str
    duration: float
    start: float
    end: float
    page_path: str
    visual_fingerprint: str
    page_sha256: str = ""
    layout: dict = field(default_factory=dict)


@dataclass
class VideoTimeline:
    pages: list[VideoPage]
    duration: float
    audiobook_duration: float
    concat_path: str
    settings: dict
    schema_version: int = 1
    source: dict = field(default_factory=dict, repr=False)
    source_files: dict = field(default_factory=dict, repr=False)

    def to_dict(self):
        data = asdict(self)
        data.pop('source')
        data.pop('source_files')
        return data


def _concat_file(path):
    return "file '" + Path(path).resolve().as_posix().replace("'", "'\\''") + "'\noption framerate 1000\n"


def prepare_video_timeline(media, ffprobe_path, *, style=DEFAULT_STYLE, cancel_event=None, progress=None):
    cancel_event = cancel_event or Event()
    def check():
        if cancel_event.is_set():
            raise VideoValidationError("Video preparation cancelled")
    check()
    records = load_narration(media)
    initial_files = file_states(_input_paths(media, records))
    audio = probe_audio(Path(media.audiobook_path), ffprobe_path)
    probes = []
    for record in records:
        check()
        probes.append(probe_audio(Path(record["mp3_path"]), ffprobe_path))
    if any(p.codec != "mp3" for p in [audio, *probes]):
        raise VideoValidationError("Step 3 chunks and the merged audiobook must contain MP3 audio")
    total = math.fsum(p.duration for p in probes)
    # Allow at most two MPEG audio frames of container rounding, never accumulated drift.
    tolerance = max(audio_rounding_tolerance(p) for p in [audio, *probes])
    if abs(total - audio.duration) > tolerance:
        raise VideoValidationError(f"Chunk duration total {total:.6f}s differs from audiobook {audio.duration:.6f}s; regenerate Step 3")
    folder = Path(media.output_dir)
    settings = visual_settings(style)
    visual_source = {"settings": settings, "thumbnail": sha256_file(Path(media.thumbnail_path)),
                     "title": media.title, "chapter": media.chapter}
    pages = []
    start = 0.0
    for record, probe in zip(records, probes):
        check()
        key = _identity(dict(visual_source, text=record["text"]))
        page_path = folder / "render_pages" / f"page_{record['order']:05d}_{key}.png"
        cache_path = page_path.with_suffix(".json")
        layout = None
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if cache["visual_fingerprint"] == key and cache["page_sha256"] == sha256_file(page_path):
                with Image.open(page_path) as image:
                    image.verify()
                layout = cache["layout"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if layout is None:
            try:
                layout = render_page(media.thumbnail_path, page_path, title=media.title,
                                     chapter=media.chapter, text=record["text"], style=style)
            except VideoValidationError as error:
                raise VideoValidationError(f"Chunk {record['order']}: {error}") from error
            check()
            atomic_write_json(cache_path, {"visual_fingerprint": key, "page_sha256": sha256_file(page_path), "layout": layout})
        end = math.fsum([start, probe.duration])
        pages.append(VideoPage(record["order"], record["chapter"], record["text"], record["text_sha256"],
                               record["mp3_path"], record["mp3_sha256"], probe.duration, start, end,
                               str(page_path.resolve()), key, sha256_file(page_path), layout))
        start = end
        if progress:
            progress(len(pages), len(records), f"Prepared page {record['order']}/{len(records)}")
    check()
    concat_path = folder / "render_pages" / "timeline.ffconcat"
    # The final duplicate is an endpoint packet, not a second visual page.
    # Its 1ms packet duration closes the last page exactly instead of adding a tail.
    script = "ffconcat version 1.0\n"
    for index, page in enumerate(pages):
        end = page.end - (0.001 if index == len(pages) - 1 else 0)
        # Quantize cumulative endpoints, so decimal rounding cannot accumulate.
        duration_us = round(end * 1_000_000) - round(page.start * 1_000_000)
        if duration_us <= 0:
            raise VideoValidationError("Chunk duration must exceed the 1ms timeline tick")
        script += _concat_file(page.page_path) + f"duration {duration_us / 1_000_000:.9f}\n"
    script += _concat_file(pages[-1].page_path)
    timeline = VideoTimeline(pages, total, audio.duration, str(concat_path.resolve()), settings)
    require_unchanged(initial_files)
    atomic_write_text(concat_path, script)
    atomic_write_json(folder / "video_timeline.json", timeline.to_dict())
    timeline.source = source_fingerprint(media)
    require_unchanged(initial_files)
    timeline.source_files = file_states([*initial_files, folder / 'video_timeline.json', concat_path,
                                        *(p.page_path for p in pages)])
    check()
    return timeline


def validate_timeline_timestamps(path, timeline, ffprobe_path, runner=None):
    """Inspect actual decoded timestamps; reject encoders that duplicate/retime pages."""
    from media.video import _default_runner
    completed = (runner or _default_runner)([ffprobe_path, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time,pkt_duration_time,duration_time:stream=duration", "-of", "json", str(path)], 30.0)
    try:
        if completed.returncode:
            raise ValueError(completed.stderr)
        data = json.loads(completed.stdout)
        frames = data["frames"]
        timestamps = [float(f["best_effort_timestamp_time"]) for f in frames]
        expected = [p.start for p in timeline.pages] + [timeline.duration - 0.001]
        if (len(timestamps) != len(expected) or not all(math.isfinite(t) for t in timestamps)
                or any(abs(a - b) > 0.00101 for a, b in zip(timestamps, expected))):
            raise ValueError(f"Expected {len(expected)} VFR packets at measured page boundaries; got {timestamps[:12]}")
        end = float((data.get("streams") or [{}])[0].get("duration") or
                    timestamps[-1] + float(frames[-1].get("duration_time") or frames[-1].get("pkt_duration_time") or 0))
        if not math.isfinite(end) or abs(end - timeline.duration) > 0.002:
            raise ValueError("Final page duration changed during encoding")
    except (ValueError, KeyError, TypeError) as error:
        raise VideoValidationError(f"Encoder failed VFR timing validation: {error}") from error

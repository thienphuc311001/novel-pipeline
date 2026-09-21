"""Exact TTS text, cached neon-theater pages, and measured static timelines."""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from threading import Event

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from media.artifacts import atomic_write_json, atomic_write_text, sha256_file, sha256_text
from media.text_layout import (DEFAULT_STYLE, FONT_DIR, LAYOUT_FILL_MIN, LAYOUT_FILL_TARGET, PageStyle,
                               block_height, fit_body, fit_lines, font_paths, gap_ladder, header_reserve,
                               justify_block, layout_identity, line_height, page_band, renderer_budget,
                               scaled_style, wrap_lines)
from media.video import VideoValidationError, probe_audio, audio_rounding_tolerance

# The text-layout module owns fonts, wrapping and the body band; importing the names
# here keeps the existing ``media.video_pages`` API (used by thumbnails and tests)
# working while both sides measure text through one implementation.
__all__ = [
    "DEFAULT_STYLE", "FONT_DIR", "PageStyle", "block_height", "fit_body", "fit_lines", "font_paths",
    "gap_ladder", "line_height", "wrap_lines", "BODY_COLOR", "CHAPTER_COLOR", "DIVIDER_COLOR",
    "PANEL_COLOR", "PANEL_OUTLINE", "TITLE_COLOR", "draw_frame", "render_page", "scaled_style",
    "page_chapter_label", "load_narration", "prepare_video_timeline", "source_fingerprint",
    "validate_page_layout", "validate_timeline_timestamps", "visual_settings", "VideoPage", "VideoTimeline",
]

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


def visual_settings(style=DEFAULT_STYLE):
    regular, bold = font_paths()
    settings = asdict(style)
    settings["frame"] = list(style.frame)  # Stable equality after JSON recovery.
    return {"style": settings, "fonts": {p.name: sha256_file(p) for p in (regular, bold)}}


def _identity(value):
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def page_chapter_label(chapter_number, fallback=""):
    """Label one page with its own chapter; the thumbnail keeps the group range.

    Every TTS chunk belongs to exactly one chapter, so a page can always name
    the chapter it narrates instead of repeating the whole group range.  A
    missing/zero number falls back to the group label so a page never loses
    its caption.
    """
    try:
        number = int(chapter_number)
    except (TypeError, ValueError):
        number = 0
    return f"Chương {number}" if number > 0 else str(fallback or "")


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


def _stored_chunk_plan(media):
    """The Step 3 plan of this job, or ``None`` when no plan file is readable."""
    try:
        return json.loads((Path(media.output_dir) / "tts_chunks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def validate_page_layout(media, records, *, style=DEFAULT_STYLE):
    """Fail closed when a saved chunk plan no longer matches the current pages.

    Step 3 finalized every chunk against a measured band (the real title and chapter
    labels of the job).  If the pages would now offer less room — a longer title, a
    changed font, a changed band or a changed fill policy — the plan is stale, and
    rendering must stop with a clear fingerprint mismatch instead of silently
    re-chunking, truncating or shrinking the font.  Returns the page budget used.

    A job without a readable plan keeps the historical behaviour: the renderer's own
    ``fit_body`` guard still rejects any chunk that does not fit.
    """
    plan = _stored_chunk_plan(media)
    if not plan:
        return renderer_budget(style, title=media.title, chapter_labels=[])
    planned = dict(plan.get("config", {}).get("layout") or {})
    current = layout_identity(style)
    labels = [page_chapter_label(record.get("chapter"), media.chapter) for record in records]
    budget = renderer_budget(style, title=media.title, chapter_labels=[*labels, media.chapter])
    for key in ("style_version", "font_identity", "font_size", "body_width", "line_spacing",
                "paragraph_gap", "paragraph_gap_floor", "max_visible_lines", "fill_target",
                "fill_min", "fill_max"):
        if planned.get(key) is not None and planned[key] != current[key]:
            raise VideoValidationError(
                f"Layout fingerprint mismatch: the saved chunk plan was built with {key}="
                f"{planned[key]!r} but the current page layout uses {current[key]!r}. "
                "Regenerate the Step 3 chunks before rendering; the renderer never re-chunks.")
    if int(planned.get("body_band", 0)) > int(budget.body_height):
        raise VideoValidationError(
            f"Stale chunk plan: pages now offer {budget.body_height}px of body band but the plan was "
            f"measured against {planned['body_band']}px. Regenerate the Step 3 chunks before rendering.")
    return budget


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
    x, y = left + style.padding, top + style.title_top_offset
    width = right - left - style.padding * 2
    title_font, title_lines, title_h, _ = fit_lines(draw, title, bold, style.title_size, 36, width,
                                                    style.title_max_height, 1.12)
    chapter_font, chapter_lines, chapter_h, _ = fit_lines(draw, chapter, regular, style.chapter_size, 24, width,
                                                          style.chapter_max_height, 1.2)
    bounds = []
    def paint(lines, font, step, y, color, centered=False, gap=1.0, origin=None):
        blank_step = max(1, round(step * gap))
        for line in lines:
            if centered:
                tx = (style.width - draw.textlength(line, font=font)) / 2
            else:
                tx = x if origin is None else origin
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
    title_advance = paint(title_lines, title_font, title_h, y, TITLE_COLOR, True) - y
    y += title_advance + style.title_gap
    chapter_advance = paint(chapter_lines, chapter_font, chapter_h, y, CHAPTER_COLOR, True) - y
    y += chapter_advance + style.chapter_gap
    # The body runs in its own readable column, and the divider marks that column so
    # the narrower block reads as a deliberate page grid instead of an accident.
    column = min(width, style.body_width)
    column_x = (style.width - column) // 2
    draw.line((column_x, y, column_x + column, y), fill=DIVIDER_COLOR, width=1)
    body_top = y + style.body_top_gap
    body_bottom = bottom - style.body_bottom_margin
    # body_bottom - body_top equals page_band with the real fitted title/chapter
    # advances, and the chunk planner validates the same measured band through
    # header_reserve/renderer_budget, so a chunk planned for this job always fits.
    band = body_bottom - body_top
    font, lines, line_step, line_gap, visible_lines = fit_body(
        draw, text, regular, style, column, band)
    fitted_gap = line_gap
    measured = block_height(lines, line_step, line_gap)
    # Minor leftover space is distributed across the existing gaps — never the font.
    # Whatever the subtle spacing limits cannot spend stays as bottom whitespace.
    line_step, line_gap, _leftover = justify_block(lines, line_step, line_gap, band)
    justified = block_height(lines, line_step, line_gap)
    body_y = body_top + (band - justified) / 2
    paint(lines, font, line_step, body_y, BODY_COLOR, gap=line_gap, origin=column_x)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".page_", suffix=".png", dir=output.parent)
    os.close(fd)
    try:
        canvas.convert("RGB").save(name, format="PNG")
        os.replace(name, output)
    finally:
        Path(name).unlink(missing_ok=True)
    return {"font_size": font.size, "paragraph_gap": line_gap, "paragraph_gap_base": fitted_gap,
            "lines": visible_lines, "line_step": line_step,
            "body_height": band, "measured_height": measured,
            "fill_ratio": round(measured / band, 4) if band > 0 else 0.0,
            "fill_min": LAYOUT_FILL_MIN, "fill_target": LAYOUT_FILL_TARGET,
            "spacing_compensation": justified - measured,
            "title_height": title_h * len(title_lines), "chapter_height": chapter_h * len(chapter_lines),
            "text_bounds": bounds}


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
    validate_page_layout(media, records, style=style)
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
        # Each page names only its own chapter; the group range stays on the thumbnail.
        chapter_label = page_chapter_label(record.get("chapter"), media.chapter)
        key = _identity(dict(visual_source, chapter=chapter_label, text=record["text"]))
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
                                     chapter=chapter_label, text=record["text"], style=style)
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

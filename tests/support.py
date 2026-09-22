"""Small native-format fixtures used by unit/UI tests."""

from __future__ import annotations

from pathlib import Path

def create_visuals_fixture(job_dir, *, cover=(400, 400, (200, 30, 30)), qr_size=250):
    """Record the two required Step 4 page pictures for one job folder.

    Returns ``{"cover": path, "qr": path}`` pointing at the job's byte-identical
    copies, ready to be attached to a media bundle.
    """
    from PIL import Image, ImageDraw
    from media.visuals import record_visuals
    job_dir = Path(job_dir)
    sources = job_dir / "_fixture_visual_sources"
    sources.mkdir(parents=True, exist_ok=True)
    cover_path = sources / "cover.png"
    Image.new("RGB", (cover[0], cover[1]), cover[2]).save(cover_path)
    qr_path = sources / "qr.png"
    # A real QR-like checkerboard: the renderer only resizes it, never redraws it.
    squares = 10
    step = max(1, qr_size // squares)
    image = Image.new("RGB", (squares * step, squares * step), "white")
    draw = ImageDraw.Draw(image)
    for x in range(squares):
        for y in range(squares):
            if (x + y) % 2 == 0:
                draw.rectangle((x * step, y * step, x * step + step - 1, y * step + step - 1), fill="black")
    image.save(qr_path)
    record = record_visuals(job_dir, cover_path, qr_path)
    return {"cover": str(job_dir / record["cover"]["file"]), "qr": str(job_dir / record["qr"]["file"])}


def create_narration_fixture(job_dir, chunks, audiobook):
    """Create valid request/merge provenance for tests that stub media encoding."""
    from media.tts import TtsChunk, TtsProcessor
    from media.artifacts import atomic_write_json
    class Client:
        def __init__(self, text):
            self.text = text
        async def save(self, path):
            Path(path).write_bytes(b"mp3:" + self.text.encode("utf-8"))
    processor = TtsProcessor([TtsChunk(c.order, c.text, c.chapter) for c in chunks],
                             Path(job_dir) / "audio_chunks", voice="fixture",
                             client_factory=lambda text, voice: Client(text), ffmpeg_path="ffmpeg")
    result = processor.run()
    content = Path(audiobook).read_bytes() if Path(audiobook).exists() else b"audiobook"
    processor._ffmpeg_concat = lambda inputs, output: Path(output).write_bytes(content)
    processor.merge(result, Path(audiobook))
    atomic_write_json(Path(job_dir) / "video_timeline.json", {"schema_version": 1, "fixture": True})
    return processor

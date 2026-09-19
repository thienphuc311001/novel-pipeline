"""Small native-format fixtures used by unit/UI tests."""

from __future__ import annotations

from pathlib import Path

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

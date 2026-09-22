"""Network-free tests for the fixed channel intro (audio prepend + thumbnail frame)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from config.settings import DEFAULT_CHANNEL_INTRO_TEXT, Settings
from media.artifacts import sha256_file
from media.channel_intro import (
    channel_intro_text,
    channel_intro_voice,
    ensure_channel_intro_audio,
    intro_cache_path,
    prepare_job_intro,
    read_manifest_intro,
    render_intro_frame,
)
from media.tts import TtsChunk, TtsProcessor
from media.video import AudioProbe
from tests.support import create_narration_fixture, create_visuals_fixture


class _Client:
    def __init__(self, text, action):
        self.text = text
        self.action = action

    async def save(self, path):
        await self.action(self.text, Path(path))


class ChannelIntroTests(unittest.TestCase):
    def test_fixed_text_is_exact(self):
        self.assertEqual(
            DEFAULT_CHANNEL_INTRO_TEXT,
            "Chào mừng bạn đến với Ghiền Truyện Chữ. "
            "Đừng quên nhấn thích và đăng ký kênh để ủng hộ mình nhé.",
        )
        self.assertEqual(channel_intro_text(Settings()), DEFAULT_CHANNEL_INTRO_TEXT)
        self.assertEqual(channel_intro_voice(Settings()), "vi-VN-HoaiMyNeural")
        custom = Settings(channel_intro_enabled=True, channel_intro_voice="vi-VN-NamMinhNeural")
        self.assertEqual(channel_intro_voice(custom), "vi-VN-NamMinhNeural")

    def test_cache_reuses_same_bytes(self):
        async def write(text, path):
            path.write_bytes(b"mp3:" + text.encode())

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            first = ensure_channel_intro_audio(
                "Chào mừng bạn đến với Ghiền Truyện Chữ. Đừng quên nhấn thích và đăng ký kênh để ủng hộ mình nhé.",
                "voice",
                cache_dir=cache,
                client_factory=lambda t, v: _Client(t, write),
            )
            second = ensure_channel_intro_audio(
                "Chào mừng bạn đến với Ghiền Truyện Chữ. Đừng quên nhấn thích và đăng ký kênh để ủng hộ mình nhé.",
                "voice",
                cache_dir=cache,
                client_factory=lambda t, v: _Client(t, lambda *a: (_ for _ in ()).throw(AssertionError("must reuse cache"))),
            )
            self.assertEqual(first, second)
            self.assertTrue(first.is_file())

    def test_job_intro_copy_and_merge_prepends_intro(self):
        async def write(text, path):
            path.write_bytes(b"mp3:" + text.encode())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_dir = root / "cache"
            audio_dir = root / "audio_chunks"
            settings = Settings()
            staged = prepare_job_intro(
                audio_dir, settings,
                client_factory=lambda t, v: _Client(t, write),
                cache_dir=cache_dir,
            )
            self.assertIsNotNone(staged)
            self.assertEqual((audio_dir / "intro.mp3").read_bytes(), (intro_cache_path(staged["voice"], staged["text"], cache_dir=cache_dir)).read_bytes())

            chunks = [TtsChunk(1, "one"), TtsChunk(2, "two")]
            processor = TtsProcessor(
                chunks, audio_dir, voice="vi-VN-HoaiMyNeural",
                client_factory=lambda t, v: _Client(t, write), ffmpeg_path="/bin/true",
            )
            result = processor.run()
            seen = []

            def fake_concat(inputs, output):
                seen.append([Path(p).name for p in inputs])
                Path(output).write_bytes(b"".join(Path(p).read_bytes() for p in inputs))

            processor._ffmpeg_concat = fake_concat  # type: ignore[method-assign]
            out = processor.merge(
                result, root / "audiobook.mp3",
                intro_path=Path(staged["path"]), intro_text=staged["text"], intro_voice=staged["voice"],
            )
            self.assertTrue(out.is_file())
            self.assertEqual(seen[-1], ["intro.mp3", "chunk_00001.mp3", "chunk_00002.mp3"])
            manifest = json.loads(processor.manifest_path.read_text())
            self.assertEqual(manifest["merge"]["orders"], [1, 2])
            self.assertEqual(manifest["merge"]["intro"]["text"], staged["text"])
            back = read_manifest_intro(processor.manifest_path)
            self.assertIsNotNone(back)
            self.assertEqual(back["mp3_sha256"], sha256_file(audio_dir / "intro.mp3"))

    def test_intro_frame_is_full_1920x1080_crop_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Non-16:9 source to prove crop-fit fills without black bars.
            thumb = root / "thumb.jpg"
            Image.new("RGB", (800, 1000), (10, 120, 200)).save(thumb)
            out = root / "intro.png"
            layout = render_intro_frame(thumb, out)
            with Image.open(out) as frame:
                self.assertEqual(frame.size, (1920, 1080))
            self.assertEqual(layout["mode"], "crop-fit")
            self.assertEqual(layout["width"], 1920)

    def test_video_timeline_prepends_thumbnail_intro(self):
        from media.video_pages import prepare_video_timeline

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            texts = ["Chương 1", "Hắn bước vào căn phòng."]
            chunks = [TtsChunk(i + 1, t, 1) for i, t in enumerate(texts)]
            audio = root / "audiobook.mp3"
            processor = create_narration_fixture(root, chunks, audio)
            # Stage a fake intro.mp3 + manifest intro entry (no network).
            intro_mp3 = processor.audio_dir / "intro.mp3"
            intro_mp3.write_bytes(b"fake-intro-audio")
            manifest_path = processor.manifest_path
            data = json.loads(manifest_path.read_text())
            from media.artifacts import atomic_write_json, sha256_text

            intro_text = channel_intro_text(Settings())
            data["merge"]["intro"] = {
                "text": intro_text, "text_sha256": sha256_text(intro_text),
                "voice": "fixture", "file": "intro.mp3", "mp3_sha256": sha256_file(intro_mp3),
            }
            atomic_write_json(manifest_path, data)
            # Rebuild audiobook bytes (fixture concat stub) so hashes stay consistent.
            audio.write_bytes(b"audiobook")

            thumb = root / "thumbnail.jpg"
            Image.new("RGB", (1280, 720), (70, 100, 140)).save(thumb)
            visuals = create_visuals_fixture(root)
            media = SimpleNamespace(output_dir=str(root), title="T", chapter="Chương 1-2",
                                    thumbnail_path=str(thumb), audiobook_path=str(audio),
                                    tts_manifest_path=str(manifest_path),
                                    cover_image_path=visuals["cover"], qr_image_path=visuals["qr"])

            durations = {"intro.mp3": 2.0, "chunk_00001.mp3": 0.737, "chunk_00002.mp3": 1.213, "audiobook.mp3": 3.95}

            def probe(path, *args):
                return AudioProbe(durations[Path(path).name], "mp3", 24000, 1)

            with patch("media.video_pages.probe_audio", side_effect=probe):
                timeline = prepare_video_timeline(media, "ffprobe")
            self.assertEqual(len(timeline.pages), 3)
            self.assertEqual(timeline.pages[0].order, 0)
            self.assertEqual(timeline.pages[0].text, intro_text)
            self.assertAlmostEqual(timeline.pages[0].duration, 2.0)
            self.assertAlmostEqual(timeline.pages[1].start, 2.0)
            with Image.open(timeline.pages[0].page_path) as frame:
                self.assertEqual(frame.size, (1920, 1080))
            script = Path(timeline.concat_path).read_text()
            self.assertEqual(script.count("file '"), 4)  # 3 pages + endpoint

    def test_no_intro_keeps_legacy_timeline(self):
        from media.video_pages import prepare_video_timeline

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            texts = ["Chương 1", "Hắn bước vào căn phòng."]
            chunks = [TtsChunk(i + 1, t, 1) for i, t in enumerate(texts)]
            audio = root / "audiobook.mp3"
            processor = create_narration_fixture(root, chunks, audio)
            thumb = root / "thumbnail.jpg"
            Image.new("RGB", (1280, 720), (70, 100, 140)).save(thumb)
            visuals = create_visuals_fixture(root)
            media = SimpleNamespace(output_dir=str(root), title="T", chapter="Chương 1-2",
                                    thumbnail_path=str(thumb), audiobook_path=str(audio),
                                    tts_manifest_path=str(processor.manifest_path),
                                    cover_image_path=visuals["cover"], qr_image_path=visuals["qr"])

            def probe(path, *args):
                duration = {"chunk_00001.mp3": 0.737, "chunk_00002.mp3": 1.213, "audiobook.mp3": 1.95}[Path(path).name]
                return AudioProbe(duration, "mp3", 24000, 1)

            with patch("media.video_pages.probe_audio", side_effect=probe):
                timeline = prepare_video_timeline(media, "ffprobe")
            self.assertEqual([p.order for p in timeline.pages], [1, 2])


if __name__ == "__main__":
    unittest.main()

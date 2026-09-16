"""Network-free tests for resume, retry, fallback, and ordering."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from media.tts import TtsChunk, TtsConfigurationError, TtsProcessor


class _Client:
    def __init__(self, text, action):
        self.text = text
        self.action = action

    async def save(self, path):
        await self.action(self.text, Path(path))


class TtsTests(unittest.TestCase):
    def test_blank_voice_fails_before_work_or_manifest_creation(self):
        calls = []

        def factory(_text, _voice):
            calls.append(True)
            raise AssertionError("client factory must not run")

        with tempfile.TemporaryDirectory() as directory:
            audio_dir = Path(directory) / "audio"
            processor = TtsProcessor(
                [TtsChunk(1, "hello")],
                audio_dir,
                voice="   ",
                client_factory=factory,
                ffmpeg_path="/bin/true",
            )
            with self.assertRaisesRegex(TtsConfigurationError, "để trống"):
                processor.run()
            self.assertEqual(calls, [])
            self.assertFalse(audio_dir.exists())

    def test_resume_uses_matching_manifest_and_voice(self):
        calls = []

        async def write(text, path):
            calls.append(text)
            path.write_bytes(b"mp3:" + text.encode())

        chunks = [TtsChunk(1, "one"), TtsChunk(2, "two")]
        with tempfile.TemporaryDirectory() as directory:
            processor = TtsProcessor(
                chunks, Path(directory), voice="vi-VN-HoaiMyNeural", client_factory=lambda text, _voice: _Client(text, write), ffmpeg_path="/bin/true"
            )
            first = processor.run()
            self.assertEqual(first.generated, [1, 2])
            self.assertEqual(calls, ["one", "two"])

            async def should_not_run(_text, _path):
                raise AssertionError("matched chunk should have resumed")

            resumed = TtsProcessor(
                chunks, Path(directory), voice="vi-VN-HoaiMyNeural", client_factory=lambda text, _voice: _Client(text, should_not_run), ffmpeg_path="/bin/true"
            ).run()
            self.assertEqual(resumed.skipped, [1, 2])

    def test_retry_fallback_and_numeric_merge_order(self):
        original = "one two three four"
        attempts = {original: 0}

        async def selective(text, path):
            attempts[text] = attempts.get(text, 0) + 1
            if text == original:
                raise RuntimeError("normal request failed")
            path.write_bytes(text.encode())

        with tempfile.TemporaryDirectory() as directory:
            processor = TtsProcessor(
                [TtsChunk(2, "second"), TtsChunk(1, original)],
                Path(directory), voice="voice", retry_count=1, fallback_retry_count=1,
                client_factory=lambda text, _voice: _Client(text, selective), ffmpeg_path="/bin/true",
            )
            seen = []

            def fake_concat(inputs, output):
                inputs = list(inputs)
                seen.append([item.name for item in inputs])
                Path(output).write_bytes(b"".join(item.read_bytes() for item in inputs))

            processor._ffmpeg_concat = fake_concat  # type: ignore[method-assign]
            result = processor.run()
            self.assertEqual(result.failures, [])
            self.assertEqual(seen[0], [".chunk_00001_part1.mp3", ".chunk_00001_part2.mp3"])
            final = processor.merge(result, Path(directory) / "final.mp3")
            self.assertEqual(seen[-1], ["chunk_00001.mp3", "chunk_00002.mp3"])
            self.assertTrue(final.is_file())

    def test_concurrency_is_limited_and_failures_are_detailed(self):
        active = 0
        maximum = 0

        async def delayed(text, path):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            if text == "bad":
                raise ValueError("bad chunk")
            path.write_bytes(b"ok")

        with tempfile.TemporaryDirectory() as directory:
            processor = TtsProcessor(
                [TtsChunk(index, "bad" if index == 3 else str(index)) for index in range(1, 6)],
                Path(directory), voice="voice", max_concurrency=2, retry_count=1, fallback_retry_count=1,
                client_factory=lambda text, _voice: _Client(text, delayed), ffmpeg_path="/bin/true",
            )
            result = processor.run()
            self.assertLessEqual(maximum, 2)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(result.failures[0].chunk_number, 3)
            self.assertIn(result.failures[0].failed_part, {"whole", "part1", "part2", "merge_parts"})
            self.assertEqual(result.failures[0].original_text, "bad")
            self.assertTrue(result.failures[0].failed_part_text)

            merged = []

            def fake_concat(inputs, output):
                merged.extend(path.name for path in inputs)
                Path(output).write_bytes(b"merged")

            processor._ffmpeg_concat = fake_concat  # type: ignore[method-assign]
            final = processor.merge(result, Path(directory) / "partial.mp3", skip_failed=True)
            self.assertTrue(final.is_file())
            self.assertEqual(
                merged,
                ["chunk_00001.mp3", "chunk_00002.mp3", "chunk_00004.mp3", "chunk_00005.mp3"],
            )

    def test_merge_rejects_zero_successes_without_calling_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = TtsProcessor(
                [TtsChunk(1, "one")], Path(directory), voice="voice",
                client_factory=lambda *_args: None, ffmpeg_path="/bin/true",
            )
            called = []
            processor._ffmpeg_concat = lambda *_args: called.append(True)  # type: ignore[method-assign]
            result = processor._result
            with self.assertRaisesRegex(RuntimeError, "Không có đoạn MP3 thành công"):
                processor.merge(result, Path(directory) / "final.mp3", skip_failed=True)
            self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()

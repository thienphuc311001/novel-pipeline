"""Headless consumer boundaries; no network, keyring, GPU or Qt required."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config.settings import Settings
from media.groups import write_groups
from media.tts import TtsFailure, TtsResult
from media.video import EncoderCandidate
from pipeline.document import PipelineDocument, PipelineStateError, StageKey
from pipeline.media_service import (
    MediaCancelled, _run_ffmpeg, _upload_metadata, execute_media, render_video,
)


class HeadlessMediaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings(channel_intro_enabled=False)
        self.document = PipelineDocument()
        self.document.original_input_text = "immutable input"
        self.document.normalized_text = "Chương 1\nMột câu chuyện đầu tiên.\n\nChương 2\nMột câu chuyện tiếp theo.\n"
        self.document.normalized_revision = 1
        self.document.stage(StageKey.NORMALIZE).touch("fixture", "fixture")
        self.document.input_directory = str(self.root)
        write_groups(self.document, self.settings, "Truyện", 1)
        self.cancel = threading.Event()
        self.updates = []

    def perform(self, action, options):
        return execute_media(action, self.document, self.settings, options,
                             cancel_event=self.cancel,
                             progress=lambda *update: self.updates.append(update))

    def test_empty_unknown_and_duplicate_selections_are_rejected(self):
        first = self.document.chapter_groups[0].group_id
        for ids in ([], ["missing"], [first, first]):
            with self.subTest(ids=ids), self.assertRaises(PipelineStateError):
                self.perform("prepare", {"group_ids": ids})

    def test_broken_first_artifact_does_not_block_later_selected_group(self):
        first, second = self.document.chapter_groups
        Path(first.txt_path).write_text("tampered", encoding="utf-8")
        result = self.perform("prepare", {"group_ids": [first.group_id, second.group_id]})
        self.assertEqual(result["status"], "partial")
        self.assertEqual([row["status"] for row in result["groups"]], ["failed", "completed"])
        self.assertTrue((Path(second.output_dir) / "tts_chunks.json").is_file())

    def test_stop_preserves_prepared_group_without_advertising_batch_success(self):
        first, second = self.document.chapter_groups
        def stop_after_first(done, total, message):
            if done == 1000 and total == 2000:
                self.cancel.set()
        result = execute_media(
            "prepare", self.document, self.settings,
            {"group_ids": [first.group_id, second.group_id]},
            cancel_event=self.cancel, progress=stop_after_first,
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["groups"][0]["status"], "completed")
        self.assertTrue((Path(first.output_dir) / "tts_chunks.json").is_file())
        self.assertFalse((Path(second.output_dir) / "tts_chunks.json").exists())

    def test_partial_merge_requires_explicit_boolean_confirmation(self):
        group = self.document.chapter_groups[0]
        for confirmation in (None, False, 1, "true"):
            with self.subTest(confirmation=confirmation), self.assertRaises(PipelineStateError):
                self.perform("merge_partial", {"group_ids": [group.group_id], "allow_partial": confirmation})
        self.assertNotIn("audiobook", group.state)

    def test_cancellation_before_start_is_not_a_failure(self):
        self.cancel.set()
        result = self.perform("prepare", {})
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["groups"], [])

    def test_incomplete_tts_never_reports_success_or_merges(self):
        group = self.document.chapter_groups[0]
        failure = TtsFailure(1, "text", "whole", "Network", "safe failure", 2)
        result = TtsResult("audio", "manifest", failures=[failure])
        processor = SimpleNamespace(preparation_plan={"plan_id": "plan", "warnings": []},
                                    chunks=[SimpleNamespace(order=1)], run=lambda: result)
        with patch("pipeline.media_service._processor", return_value=processor), \
                patch("pipeline.media_service._merge") as merge:
            value = self.perform("tts", {"group_ids": [group.group_id]})
        self.assertEqual(value["status"], "partial")
        self.assertEqual(value["groups"][0]["status"], "failed")
        self.assertEqual(group.state["tts_status"], "TTS Incomplete")
        self.assertEqual(group.state["failures"][0]["original_text"], "text")
        merge.assert_not_called()

    def test_frozen_upload_metadata_ignores_new_drafts_and_past_schedule(self):
        group = self.document.chapter_groups[0]
        saved = {"title": "Frozen", "privacy": "private", "publish_at": "2001-01-01T00:00:00Z", "tags": ["old"]}
        with patch("media.youtube.load_upload_state", return_value={"status": "cancelled", "metadata": saved}):
            metadata = _upload_metadata(group, self.settings, {
                "metadata": {"title": "Changed", "tags": ["new"]},
                "group_metadata": {group.group_id: {"title": "Other"}},
            })
        self.assertEqual(metadata.title, "Frozen")
        self.assertEqual(metadata.tags, ["old"])
        self.assertEqual(metadata.publish_at, saved["publish_at"])

    def test_saved_story_tags_apply_by_default_but_explicit_empty_tags_win(self):
        group = self.document.chapter_groups[0]
        self.settings.youtube_title_tags = {"  TRUYỆN  ": ["audio", "novel"]}
        automatic = _upload_metadata(group, self.settings, {"metadata": {}})
        explicit = _upload_metadata(group, self.settings, {"metadata": {"tags": []}})
        self.assertEqual(automatic.tags, ["audio", "novel"])
        self.assertEqual(explicit.tags, [])

    def test_per_group_upload_metadata_wins_over_shared_defaults(self):
        group = self.document.chapter_groups[0]
        with patch("media.youtube.load_upload_state", return_value={}):
            metadata = _upload_metadata(group, self.settings, {
                "metadata": {"description": "shared", "privacy": "private"},
                "titles": {group.group_id: "title draft"},
                "group_metadata": {group.group_id: {"title": "specific", "privacy": "unlisted"}},
            })
        self.assertEqual(metadata.title, "specific")
        self.assertEqual(metadata.privacy, "unlisted")
        self.assertEqual(metadata.description, "shared")

    def test_unexpected_youtube_exception_never_exposes_credentials(self):
        with patch("media.youtube_auth.YouTubeAuth.connect", side_effect=RuntimeError("https://secret-session/?access_token=PASSWORD")):
            with self.assertRaises(Exception) as caught:
                self.perform("youtube_connect", {})
        self.assertNotIn("PASSWORD", str(caught.exception))
        self.assertNotIn("secret-session", str(caught.exception))

    def test_ffmpeg_streaming_parses_progress_and_bounds_stderr(self):
        program = (
            "import sys; "
            "sys.stderr.write('x' * 100000 + 'final diagnostic'); sys.stderr.flush(); "
            "sys.stdout.write('out_time_us=2500000\\nspeed=2.0x\\nprogress=end\\n'); sys.stdout.flush()"
        )
        code, diagnostics, last = _run_ffmpeg([sys.executable, "-c", program], 5.0, self.cancel,
                                             lambda *update: self.updates.append(update))
        self.assertEqual(code, 0)
        self.assertLessEqual(len(diagnostics.encode()), 32768)
        self.assertTrue(diagnostics.endswith("final diagnostic"))
        self.assertEqual(last["percentage"], 50.0)
        self.assertEqual(last["speed"], 2.0)

    def test_ffmpeg_cancellation_terminates_worker(self):
        program = "import sys,time; print('out_time_us=1000', flush=True); time.sleep(60)"
        with self.assertRaises(MediaCancelled):
            _run_ffmpeg([sys.executable, "-c", program], 1.0, self.cancel,
                        lambda *update: self.cancel.set())

    def test_render_fallback_validates_before_atomic_publication(self):
        target = self.root / "video.mp4"
        target.write_bytes(b"old valid output")
        media = SimpleNamespace(video_path=str(target), audiobook_path="audio.mp3")
        timeline = SimpleNamespace(concat_path="pages.ffconcat", source={"identity": "same"},
                                   source_files={}, audiobook_duration=5.0)
        candidates = [EncoderCandidate("h264_nvenc", "NVIDIA", verified=True),
                      EncoderCandidate("libx264", "CPU", verified=True)]
        caps = SimpleNamespace(verified_candidates=candidates, ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")
        calls = []

        def run(command, *args):
            calls.append(command)
            Path(command[-1]).write_bytes(b"new candidate output")
            return (1, "hardware initialization failed", {"speed": 0}) if len(calls) == 1 else (0, "", {"speed": 3})

        with patch("pipeline.media_service._run_ffmpeg", side_effect=run), \
                patch("media.video_pages.source_fingerprint", return_value={"identity": "same"}), \
                patch("media.video_pages.require_unchanged"), \
                patch("media.video.validate_rendered_video", return_value=5.0) as validate, \
                patch("media.video_pages.validate_timeline_timestamps") as timestamps:
            result = render_video(caps, media, timeline, audio_copy=True, cancel_event=self.cancel,
                                  progress=lambda *update: None)
        self.assertEqual(result.encoder, "libx264")
        self.assertEqual(len(result.attempt_errors), 1)
        self.assertEqual(target.read_bytes(), b"new candidate output")
        self.assertFalse((self.root / ".video.part.mp4").exists())
        validate.assert_called_once()
        timestamps.assert_called_once()

    def test_render_cancellation_cleans_partial_and_retains_previous_output(self):
        target = self.root / "video.mp4"
        target.write_bytes(b"previous")
        partial = self.root / ".video.part.mp4"
        media = SimpleNamespace(video_path=str(target), audiobook_path="audio.mp3")
        timeline = SimpleNamespace(concat_path="pages", source={"identity": "same"},
                                   source_files={}, audiobook_duration=5.0)
        caps = SimpleNamespace(verified_candidates=[EncoderCandidate("libx264", "CPU", verified=True)],
                               ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")

        def cancel(*args):
            partial.write_bytes(b"unfinished")
            raise MediaCancelled("cancelled")

        with patch("pipeline.media_service._run_ffmpeg", side_effect=cancel), \
                patch("media.video_pages.source_fingerprint", return_value={"identity": "same"}), \
                patch("media.video_pages.require_unchanged"), self.assertRaises(MediaCancelled):
            render_video(caps, media, timeline, audio_copy=False, cancel_event=self.cancel,
                         progress=lambda *update: None)
        self.assertFalse(partial.exists())
        self.assertEqual(target.read_bytes(), b"previous")

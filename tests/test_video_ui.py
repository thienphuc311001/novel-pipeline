"""Headless Step 4 UI and transition tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from media.artifacts import write_step3_artifacts
from media.video import AudioProbe, EncoderCandidate, VideoCapabilities
from pipeline.document import Chapter, Chunk, PipelineDocument
from ui.main_window import MainWindow


class VideoUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_ready_document(self, root: Path) -> PipelineDocument:
        document = PipelineDocument()
        document.normalized_revision = 1
        document.chapters = [
            Chapter(number=1, header_line="Chương 1", text="Nội dung.", char_count=9)
        ]
        document.set_cleaned_output("Chương 1\n\nNội dung.\n")
        document.chunks = [Chunk(1, 1, 1, "Chương 1\nNội dung.", char_count=20)]
        document.set_job_identity("Truyện", "Chương 1")
        bundle = write_step3_artifacts(
            document, root, title=document.job_title, chapter=document.job_chapter,
            chunk_limit=1200,
        )
        document.set_step3_artifacts(bundle)
        thumbnail = Path(bundle.output_dir) / "cover_youtube.jpg"
        audiobook = Path(bundle.output_dir) / f"{bundle.slug}_audiobook.mp3"
        thumbnail.write_bytes(b"jpeg")
        audiobook.write_bytes(b"mp3")
        from tests.support import create_narration_fixture
        processor = create_narration_fixture(Path(bundle.output_dir), document.chunks, audiobook)
        document.set_thumbnail_output(str(thumbnail))
        document.set_tts_output(
            audio_chunks_dir=str(processor.audio_dir),
            manifest_path=str(processor.manifest_path),
            audiobook_path=str(audiobook),
        )
        return document

    def test_step4_uses_current_step3_paths_without_upload_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            document = self.make_ready_document(Path(directory))
            window = MainWindow(Settings())
            window.document = document
            window._refresh_stage4_ui()
            self.assertTrue(window.stage4_continue_btn.isEnabled())
            with patch.object(window, "_start_video_detection") as detect:
                window._continue_to_stage4()

            self.assertEqual(window.tabs.currentIndex(), 3)
            self.assertEqual(window.stage5_thumbnail_label.text(), document.thumbnail_path)
            self.assertEqual(window.stage5_audio_label.text(), document.audiobook_path)
            self.assertFalse(hasattr(window, "stage5_thumbnail_upload_btn"))
            self.assertFalse(hasattr(window, "stage5_audio_upload_btn"))
            detect.assert_called_once()
            window.close()

    def test_step5_progress_is_visible_and_video_state_invalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            document = self.make_ready_document(Path(directory))
            window = MainWindow(Settings())
            window.document = document
            media = document.require_step4_outputs()
            candidate = EncoderCandidate("libx264", "CPU", hardware=False, verified=True)
            window._video_media = media
            window._video_capabilities = VideoCapabilities(
                "ffmpeg", "ffprobe", "test", "Linux", candidates=[candidate]
            )
            window._video_audio_probe = AudioProbe(100.0, "mp3", 24000, 1)
            window._refresh_stage5_ui()
            self.assertTrue(window.stage5_create_btn.isEnabled())

            window._on_video_progress(
                {"elapsed": 25.0, "percentage": 25.0, "speed": 5.0, "eta": 15.0}
            )
            self.assertEqual(window.stage5_progress.value(), 250)
            self.assertIn("5.00x", window.stage5_status.text())

            existing = Path(media.video_path)
            existing.write_bytes(b"old video")
            document.set_video_output(str(existing), {"encoder": "libx264"})
            document.set_thumbnail_output(document.thumbnail_path)
            self.assertEqual(document.video_path, "")
            window.close()

    def test_cancel_during_async_page_preparation_preserves_old_video(self):
        from threading import Event
        from PyQt6.QtTest import QTest
        from ui.main_window import _VideoRenderSession
        from media.video import VideoValidationError
        with tempfile.TemporaryDirectory() as directory:
            document = self.make_ready_document(Path(directory))
            media = document.require_step4_outputs()
            output = Path(media.video_path)
            output.write_bytes(b'previous completed video')
            candidate = EncoderCandidate('libx264', 'CPU', hardware=False, verified=True)
            caps = VideoCapabilities('ffmpeg', 'ffprobe', 'test', 'Linux', candidates=[candidate])
            started = Event()
            def prepare(media, ffprobe, *, cancel_event, progress):
                started.set()
                cancel_event.wait(2)
                raise VideoValidationError('cancelled')
            session = _VideoRenderSession(caps, media, 1.0, audio_copy=True)
            cancelled, failures = [], []
            session.cancelled.connect(lambda: cancelled.append(True))
            session.failed.connect(failures.append)
            with patch('media.video_pages.prepare_video_timeline', side_effect=prepare), patch.object(session, '_start_next_attempt') as encode:
                session.start()
                for _ in range(300):
                    QApplication.processEvents()
                    if started.is_set():
                        break
                    QTest.qWait(10)
                self.assertTrue(started.is_set())
                session.cancel()
                for _ in range(300):
                    QApplication.processEvents()
                    if cancelled or failures:
                        break
                    QTest.qWait(10)
                self.assertEqual(cancelled, [True])
                self.assertFalse(failures)
                encode.assert_not_called()
                self.assertIsNone(session.preparation_thread)
            self.assertEqual(output.read_bytes(), b'previous completed video')
            session.deleteLater()
            QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()

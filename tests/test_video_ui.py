"""Headless Step 5 UI and transition tests."""

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
        document.step2_revision = 1
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
        document.set_thumbnail_output(str(thumbnail))
        document.set_tts_output(
            audio_chunks_dir=str(Path(bundle.output_dir) / "audio"),
            manifest_path=str(Path(bundle.output_dir) / "manifest.json"),
            audiobook_path=str(audiobook),
        )
        return document

    def test_step5_uses_current_step4_paths_without_upload_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            document = self.make_ready_document(Path(directory))
            window = MainWindow(Settings(output_dir=directory))
            window.document = document
            window._refresh_stage4_ui()
            self.assertTrue(window.stage4_continue_btn.isEnabled())
            with patch.object(window, "_start_video_detection") as detect:
                window._continue_to_stage5()

            self.assertEqual(window.tabs.currentIndex(), 4)
            self.assertEqual(window.stage5_thumbnail_label.text(), document.thumbnail_path)
            self.assertEqual(window.stage5_audio_label.text(), document.audiobook_path)
            self.assertFalse(hasattr(window, "stage5_thumbnail_upload_btn"))
            self.assertFalse(hasattr(window, "stage5_audio_upload_btn"))
            detect.assert_called_once()
            window.close()

    def test_step5_progress_is_visible_and_video_state_invalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            document = self.make_ready_document(Path(directory))
            window = MainWindow(Settings(output_dir=directory))
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


if __name__ == "__main__":
    unittest.main()

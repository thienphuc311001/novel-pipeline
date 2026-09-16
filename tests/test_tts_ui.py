"""Headless UI checks for terminal TTS failure handling."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from media.tts import TtsFailure, TtsResult
from ui.main_window import MainWindow, _FailedChunksDialog, _TtsWorker


class TtsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_zero_successes_show_root_error_without_merge_dialog(self):
        window = MainWindow(Settings())
        result = TtsResult(
            audio_dir="/tmp/audio",
            manifest_path="/tmp/audio/manifest.json",
            failures=[
                TtsFailure(1, "text", "part1", "ValueError", "Invalid voice ''.", 3)
            ],
        )

        with patch("ui.main_window._FailedChunksDialog") as dialog:
            window._on_tts_completed(object(), result)

        dialog.assert_called_once()
        self.assertFalse(dialog.call_args.kwargs["allow_merge"])
        self.assertIn("Không tạo được đoạn MP3 nào", window.stage4_tts_status.text())
        self.assertIn("Invalid voice", window.stage4_tts_status.text())
        self.assertIsNone(window._merge_thread)
        window.close()

    def test_failed_chunk_dialog_shows_original_and_failed_part_text(self):
        dialog = _FailedChunksDialog(
            [
                TtsFailure(
                    7,
                    "This is the complete original chunk.",
                    "part2",
                    "TimeoutError",
                    "Timeout > 120s",
                    3,
                    failed_part_text="This is the failed second part.",
                    main_error_type="ConnectionError",
                    main_error_message="main request failed",
                )
            ],
            allow_merge=True,
        )

        self.assertIsNotNone(dialog.merge_button)
        self.assertIn("TimeoutError", dialog.failure_details.text())
        self.assertIn("complete original chunk", dialog.failure_text.toPlainText())
        self.assertIn("failed second part", dialog.failure_text.toPlainText())
        dialog.close()

    def test_worker_bridges_processor_progress_to_qt_signal(self):
        class Processor:
            progress = None

        processor = Processor()
        worker = _TtsWorker(processor, "/tmp/out.mp3")
        updates = []
        worker.progress.connect(lambda done, total, message: updates.append((done, total, message)))

        processor.progress(3, 10, "Đã tạo đoạn 3/10")

        self.assertEqual(updates, [(3, 10, "Đã tạo đoạn 3/10")])


if __name__ == "__main__":
    unittest.main()

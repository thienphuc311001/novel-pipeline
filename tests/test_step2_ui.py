"""Direct Step 2 grouping UI regression tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from media.groups import write_groups
from pipeline.document import StageKey, PipelineDocument
from ui.grouped_pipeline import GroupBatchPanel
from ui.main_window import MainWindow, _FailedChunksDialog
from ui.youtube_tab import YouTubeTab


class Step2UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, text: str) -> tuple[MainWindow, tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory()
        settings = Settings()
        window = MainWindow(settings)
        document = PipelineDocument()
        document.load_original_input(text, input_directory=temporary.name)
        document.normalized_text = text
        document.normalized_revision = 1
        document.stage(StageKey.NORMALIZE).touch("1 source", "1 chapter")
        window.document = document
        window._set_job_editors("Novel", "Chương 1")
        return window, temporary

    def test_step2_is_grouping_and_preserves_chinese_text(self):
        window, temporary = self.make_window("Chương 1\n中文 修炼者.")
        self.addCleanup(window.close)
        self.addCleanup(temporary.cleanup)

        self.assertEqual(window.tabs.count(), 5)
        self.assertEqual(
            [window.tabs.tabText(i) for i in range(window.tabs.count())],
            [
                "1️⃣ Input & Normalize",
                "2️⃣ Detect Chapters & Group",
                "3️⃣ Thumbnail & Audiobook",
                "4️⃣ Create Video",
                "5️⃣ YouTube Upload",
            ],
        )
        self.assertNotIn("Chinese", " ".join(window.tabs.tabText(i) for i in range(window.tabs.count())))

        window._continue_to_stage2()
        self.assertEqual(window.tabs.currentIndex(), 1)
        self.assertEqual(window.document.require_grouping_input(), "Chương 1\n中文 修炼者.")
        self.assertIn("Effective output root:", window.stage3_output.toPlainText())
        self.assertIn("Job folder:", window.stage3_output.toPlainText())
        window.stage3_create_groups_btn.click()

        group_text = Path(window.document.chapter_groups[0].txt_path).read_text(encoding="utf-8")
        self.assertIn("中文 修炼者", group_text)

    def test_copy_all_copies_complete_step2_output(self):
        window, temporary = self.make_window("Chương 1\nNội dung.")
        self.addCleanup(window.close)
        self.addCleanup(temporary.cleanup)

        expected = "first line\nsecond line"
        window.stage3_output.setPlainText(expected)
        window.stage3_output.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), expected)

    def test_copy_all_covers_diagnostics_group_panel_dialog_and_youtube(self):
        window, temporary = self.make_window("Chương 1\nNội dung.")
        self.addCleanup(window.close)
        self.addCleanup(temporary.cleanup)

        diagnostics = "warning\nsecond diagnostic line"
        window.status_text.setPlainText(diagnostics)
        window.status_text.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), diagnostics)

        document = window.document
        write_groups(document, window.settings, "Novel", 1)
        panel = GroupBatchPanel(lambda: document, window.settings)
        self.addCleanup(panel.close)
        panel.refresh()
        group_details = "group details\nwith line breaks"
        panel.details.setPlainText(group_details)
        panel.details.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), group_details)

        dialog = _FailedChunksDialog([{
            "chunk_number": 1,
            "failed_part": "whole",
            "attempts": 1,
            "error_type": "Error",
            "error_message": "failure",
            "original_text": "failed output\nline 2",
        }], allow_merge=False)
        self.addCleanup(dialog.close)
        dialog.failure_text.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), "ORIGINAL CHUNK TEXT:\nfailed output\nline 2")

        youtube = YouTubeTab(lambda: document, window.settings)
        self.addCleanup(youtube.close)
        youtube.result.setPlainText("upload result\nvideo id")
        youtube.result_copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), "upload result\nvideo id")


if __name__ == "__main__":
    unittest.main()

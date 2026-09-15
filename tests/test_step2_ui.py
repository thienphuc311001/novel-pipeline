from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from pipeline.document import StageKey
from tests.support import create_dictionary_fixture
from ui.main_window import MainWindow


class Step2UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dictionary = create_dictionary_fixture(Path(self.temp.name))

    def tearDown(self):
        self.dictionary.close()
        self.temp.cleanup()

    def make_window(self, text: str) -> MainWindow:
        window = MainWindow(Settings(), master_dictionary=self.dictionary)
        window.document.load_original_input(text)
        window.document.normalized_text = text
        window.document.normalized_revision = 1
        window.document.stage(StageKey.NORMALIZE).touch("input", "normalized")
        return window

    def test_confirm_updates_preview_and_unlocks_step3(self):
        text = "Chương 1\n\nHắn nhìn 大相国寺 rồi đi."
        window = self.make_window(text)

        self.assertTrue(window._enter_stage2())
        self.assertEqual(window.stage2_source_label.text(), "Source: Step 1 — Normalized Text")
        self.assertIn("大相国寺", window.stage2_sentence_text.toPlainText())
        self.assertEqual(window.stage2_suggestion_combo.count(), 2)
        self.assertTrue(window.stage2_confirm_btn.isEnabled())

        window._on_review_confirm()

        self.assertIn("Đại Tướng Quốc Tự", window.stage2_input_preview.toPlainText())
        self.assertEqual(
            window.document.step2_confirmed_output,
            "Chương 1\n\nHắn nhìn Đại Tướng Quốc Tự rồi đi.",
        )
        self.assertTrue(window.stage2_continue_btn.isEnabled())
        window._on_clean_chunk()
        self.assertTrue(window.document.chunks)

    def test_multiple_dictionary_values_require_explicit_selection(self):
        window = self.make_window("Chương 1\n\nHắn 阻挡不了 việc đó.")
        window._enter_stage2()

        self.assertGreater(window.stage2_suggestion_combo.count(), 2)
        self.assertFalse(window.stage2_confirm_btn.isEnabled())

        window.stage2_suggestion_combo.setCurrentIndex(1)
        self.assertTrue(window.stage2_confirm_btn.isEnabled())
        window._on_review_confirm()
        self.assertIsNotNone(window.document.step2_confirmed_output)

    def test_skip_remains_unresolved_and_direct_step3_navigation_is_blocked(self):
        window = self.make_window("Chương 1\n\nHắn nhìn 大相国寺.")
        errors = []
        window._error = errors.append
        window._enter_stage2()
        window._on_review_skip()

        self.assertIn("Skipped", window.stage2_fragment_combo.currentText())
        self.assertFalse(window.stage2_continue_btn.isEnabled())
        window.tabs.setCurrentIndex(2)
        self.assertEqual(window.tabs.currentIndex(), 1)
        self.assertTrue(errors)

    def test_missing_master_file_shows_error_without_small_dictionary_fallback(self):
        (self.dictionary.dictionary_dir / "Names.txt").unlink()
        window = self.make_window("Chương 1\n\nHắn nhìn 大相国寺.")

        self.assertTrue(window._enter_stage2())
        self.assertIn("Master dictionary error", window.stage2_dictionary_label.text())
        self.assertEqual(window.stage2_suggestion_combo.count(), 1)
        self.assertIn("No suggestion found", window.stage2_suggestion_message.text())
        self.assertFalse(window.stage2_confirm_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()

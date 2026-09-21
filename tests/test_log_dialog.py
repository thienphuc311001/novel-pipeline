"""Headless tests for the shared, step-independent log window."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from ui.main_window import MainWindow


class LogDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, **overrides) -> MainWindow:
        window = MainWindow(Settings(**overrides))
        self.addCleanup(window.close)
        return window

    def test_shared_log_keeps_every_step_line_across_closing(self):
        window = self.make_window()
        self.assertFalse(window.log_dialog.isVisible())
        self.assertIs(window.log_dialog.parent(), window)

        for step in range(window.tabs.count()):
            window._log(f"step {step + 1} log line")
        window._show_log_dialog()
        self.app.processEvents()

        self.assertTrue(window.log_dialog.isVisible())
        self.assertFalse(window.log_dialog.isModal())
        text = window.log_dialog.lines_text()
        for step in range(window.tabs.count()):
            self.assertIn(f"step {step + 1} log line", text)

        window._toggle_log_dialog()
        self.assertFalse(window.log_dialog.isVisible())
        window._log("line written while the log window was closed")
        window._show_log_dialog()
        self.assertIn(
            "line written while the log window was closed",
            window.log_dialog.lines_text(),
        )

    def test_opening_the_log_leaves_the_active_step_and_busy_state_untouched(self):
        window = self.make_window()
        window._set_youtube_busy(True)
        self.assertEqual(window.tabs.currentIndex(), 4)
        self.assertFalse(window.tabs.isTabEnabled(0))

        window._show_log_dialog()
        self.app.processEvents()

        self.assertTrue(window.log_dialog.isVisible())
        self.assertTrue(window.log_btn.isEnabled())
        self.assertEqual(window.tabs.currentIndex(), 4)
        self.assertFalse(window.tabs.isTabEnabled(0))

    def test_log_button_and_shortcut_toggle_the_window(self):
        window = self.make_window()
        window.show()
        self.app.processEvents()

        self.assertEqual(window.log_btn.text(), "📋 Log")
        window._log("unread line")
        self.assertIn("●", window.log_btn.text())

        window.log_btn.click()
        self.app.processEvents()
        self.assertTrue(window.log_dialog.isVisible())
        self.assertEqual(window.log_btn.text(), "📋 Log")

        window.log_dialog.close_btn.click()
        self.app.processEvents()
        self.assertFalse(window.log_dialog.isVisible())

        window.log_btn.click()
        self.app.processEvents()
        self.assertTrue(window.log_dialog.isVisible())

        self.assertEqual(window._log_shortcut.key().toString(), "Ctrl+L")
        self.assertTrue(window._log_shortcut.isEnabled())
        # Real key delivery needs an active window, which the offscreen
        # platform cannot provide, so the wired slot is triggered directly.
        window._log_shortcut.activated.emit()
        self.app.processEvents()
        self.assertFalse(window.log_dialog.isVisible())

    def test_max_log_lines_bounds_the_shared_buffer(self):
        window = self.make_window(max_log_lines=100)
        for index in range(150):
            window._log(f"line {index}")

        document = window.log_dialog.log_text.document()
        self.assertEqual(document.maximumBlockCount(), 100)
        self.assertEqual(document.blockCount(), 100)
        text = window.log_dialog.lines_text()
        self.assertIn("line 149", text)
        self.assertNotIn("line 0\n", text)

    def test_closing_the_main_window_hides_the_log_window(self):
        window = self.make_window()
        window.show()
        self.app.processEvents()
        window._show_log_dialog()
        self.app.processEvents()
        self.assertTrue(window.log_dialog.isVisible())

        window.close()
        self.app.processEvents()
        self.assertFalse(window.log_dialog.isVisible())

    def test_copy_all_and_clear_use_the_shared_log(self):
        window = self.make_window()
        window._log("first line")
        window._log("second line")

        window.log_dialog.log_text.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), window.log_dialog.lines_text())
        self.assertIn("second line", self.app.clipboard().text())

        window.log_dialog.clear_btn.click()
        self.assertEqual(window.log_dialog.lines_text(), "")
        self.assertEqual(window.log_dialog.status_label.text(), "Log is empty.")


if __name__ == "__main__":
    unittest.main()

"""Tests for remembering the TXT/ZIP picker directory."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from ui.main_window import MainWindow


class LastInputFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_setting_round_trip_and_invalid_folder_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            input_dir = Path(directory) / "inputs"
            input_dir.mkdir()
            Settings(last_input_dir=str(input_dir)).save(config_path)

            loaded = Settings.load(config_path)
            self.assertEqual(loaded.resolved_input_dir(), str(input_dir))

            input_dir.rmdir()
            self.assertEqual(loaded.resolved_input_dir(), "")

    def test_output_folder_always_follows_the_input(self):
        with tempfile.TemporaryDirectory() as directory:
            input_dir = Path(directory) / "input"
            input_dir.mkdir()
            input_file = input_dir / "input.txt"
            input_file.write_text("source", encoding="utf-8")
            settings = Settings()
            self.assertEqual(settings.resolved_output_dir(input_dir), input_dir)
            self.assertEqual(settings.resolved_output_dir(input_file), input_dir)
            self.assertEqual(settings.require_output_dir(input_file), input_dir)

            # A legacy override key cannot redirect generated files anywhere.
            legacy = Settings.from_dict({"output_dir": str(Path(directory) / "override")})
            self.assertFalse(hasattr(legacy, "output_dir"))
            self.assertEqual(legacy.resolved_output_dir(input_dir), input_dir)

            with self.assertRaisesRegex(ValueError, "Step 1"):
                settings.require_output_dir("")

    def test_file_picker_starts_at_and_updates_last_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            initial_dir = Path(directory) / "initial"
            selected_dir = Path(directory) / "selected"
            initial_dir.mkdir()
            selected_dir.mkdir()
            selected_file = selected_dir / "novel.txt"
            selected_file.write_text("Chương 1\nNội dung.", encoding="utf-8")

            settings = Settings(last_input_dir=str(initial_dir))
            window = MainWindow(settings)
            with (
                patch(
                    "ui.main_window.QFileDialog.getOpenFileNames",
                    return_value=([str(selected_file)], ""),
                ) as picker,
                patch.object(settings, "save", return_value=Path(directory) / "config.json") as save,
            ):
                window._on_load()

            self.assertEqual(picker.call_args.args[2], str(initial_dir))
            self.assertEqual(settings.last_input_dir, str(selected_dir))
            save.assert_called_once_with()
            self.assertEqual(window.document.original_input_text, "Chương 1\nNội dung.")
            self.assertEqual(window.document.source_path, str(selected_file.resolve()))
            self.assertEqual(window.document.input_directory, str(selected_dir.resolve()))


if __name__ == "__main__":
    unittest.main()

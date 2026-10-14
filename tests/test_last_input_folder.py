"""Tests for remembering the TXT/ZIP picker directory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from tests.web_only_support import WebWorkspaceMixin


class LastInputFolderTests(WebWorkspaceMixin, unittest.TestCase):
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

    def test_import_updates_and_persists_last_folder(self):
        self.start_workspace()
        initial_dir = self.root / "initial"
        selected_dir = self.root / "selected"
        initial_dir.mkdir()
        selected_dir.mkdir()
        selected_file = selected_dir / "novel.txt"
        selected_file.write_text("Chương 1\nNội dung.", encoding="utf-8")
        response = self.client.put("/api/settings", json={"last_input_dir": str(initial_dir)})
        self.assertEqual(response.status_code, 200, response.text)

        self.run_job("import", {"paths": [str(selected_file)]})

        self.assertEqual(self.service.settings.last_input_dir, str(selected_dir.resolve()))
        self.assertEqual(self.client.get("/api/settings").json()["last_input_dir"], str(selected_dir.resolve()))
        self.assertEqual(Settings.load(self.config_dir / "config.json").last_input_dir, str(selected_dir.resolve()))
        state = self.state()
        self.assertEqual(state["original_text"], "Chương 1\nNội dung.")
        self.assertEqual(state["source_path"], str(selected_file.resolve()))
        self.assertEqual(state["input_directory"], str(selected_dir.resolve()))


if __name__ == "__main__":
    unittest.main()

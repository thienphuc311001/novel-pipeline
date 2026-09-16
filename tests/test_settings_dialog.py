"""Headless tests for the comprehensive settings dialog."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QComboBox, QLineEdit, QSpinBox, QTextEdit

from chapters import NormalizeOptions, build_patterns, normalize_chapters
from config.settings import DEFAULT_TTS_VOICE, Settings
from pipeline.document import StageKey
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_user_facing_settings_have_controls(self):
        dialog = SettingsDialog(Settings())
        expected = set(Settings.__dataclass_fields__) - SettingsDialog.HIDDEN_FIELDS

        self.assertEqual(dialog.editable_fields(), expected)
        self.assertEqual(dialog.tabs.count(), 7)

    def test_collects_changed_values(self):
        dialog = SettingsDialog(Settings())
        zero_pad = dialog.controls["zero_pad"]
        mode = dialog.controls["quote_mode"]
        symbol_map = dialog.controls["symbol_map"]
        api_key = dialog.controls["gemini_api_key"]
        self.assertIsInstance(zero_pad, QSpinBox)
        self.assertIsInstance(mode, QComboBox)
        self.assertIsInstance(symbol_map, QTextEdit)
        self.assertIsInstance(api_key, QLineEdit)

        zero_pad.setValue(4)
        mode.setCurrentIndex(mode.findData("keep"))
        symbol_map.setPlainText('{"%": " phần trăm "}')
        api_key.setText("secret")
        updated = dialog._collect()

        self.assertEqual(updated.zero_pad, 4)
        self.assertEqual(updated.quote_mode, "keep")
        self.assertEqual(updated.symbol_map, {"%": " phần trăm "})
        self.assertEqual(updated.gemini_api_key, "secret")
        self.assertEqual(api_key.echoMode(), QLineEdit.EchoMode.Password)

    def test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit(self):
        self.assertEqual(Settings.from_dict({"tts_voice": ""}).tts_voice, DEFAULT_TTS_VOICE)
        self.assertEqual(Settings.from_dict({"tts_voice": "   "}).tts_voice, DEFAULT_TTS_VOICE)

        dialog = SettingsDialog(Settings())
        voice = dialog.controls["tts_voice"]
        self.assertIsInstance(voice, QLineEdit)
        voice.setText("   ")
        with self.assertRaisesRegex(ValueError, "TTS voice cannot be empty"):
            dialog._collect()

    def test_step3_title_history_can_be_remembered_and_removed(self):
        settings = Settings(title_history=["Old Novel"])
        saved = []
        settings.save = lambda: saved.append(True)  # type: ignore[method-assign]
        window = MainWindow(settings)

        self.assertEqual(window.stage3_title_combo.itemText(0), "Old Novel")
        window.stage3_title_combo.setEditText("New Novel")
        window._remember_current_title()
        self.assertEqual(settings.title_history, ["New Novel", "Old Novel"])
        self.assertTrue(saved)

        window._on_remove_saved_title()
        self.assertEqual(settings.title_history, ["Old Novel"])
        self.assertEqual(window.stage3_title_combo.currentText(), "")
        window.close()

    def test_rejects_invalid_json_shape_and_chunk_range(self):
        dialog = SettingsDialog(Settings())
        symbol_map = dialog.controls["symbol_map"]
        minimum = dialog.controls["min_chunk_chars"]
        maximum = dialog.controls["max_chunk_chars"]

        symbol_map.setPlainText("[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            dialog._collect()

        symbol_map.setPlainText("{}")
        minimum.setValue(5000)
        maximum.setValue(1000)
        with self.assertRaisesRegex(ValueError, "Minimum chunk"):
            dialog._collect()

    def test_runtime_ui_settings_are_applied(self):
        settings = Settings(font_size=13, max_log_lines=321)
        window = MainWindow(settings)

        self.assertEqual(window.settings_btn.text(), "⚙ Settings")
        self.assertEqual(window.font().pointSize(), 13)
        self.assertEqual(window.status_text.document().maximumBlockCount(), 321)
        self.assertEqual(window._default_export_filename(), "novel_export.json")

    def test_diagnostics_panel_is_large_and_resizable(self):
        window = MainWindow(Settings())
        window.show()
        self.app.processEvents()

        self.assertEqual(window.main_splitter.orientation().value, 2)
        self.assertGreaterEqual(window.main_splitter.widget(1).minimumHeight(), 180)
        self.assertGreaterEqual(window.main_splitter.sizes()[1], 180)
        window.main_splitter.setSizes([500, 320])
        self.app.processEvents()
        self.assertGreaterEqual(window.main_splitter.sizes()[1], 300)
        window.close()

    def test_cleaning_settings_affect_step3(self):
        settings = Settings(symbol_map={"%": " phần trăm "}, remove_html=True)
        window = MainWindow(settings)
        raw = "Chương 1\n<p>Giá trị 10%</p>"
        window.document.load_original_input(raw)
        chapters, _report, diagnostics = normalize_chapters(
            raw,
            build_patterns(settings),
            NormalizeOptions.from_settings(settings),
        )
        window.document.set_normalized_output(chapters)
        window.document.diagnostics.extend(diagnostics)
        window.document.stage(StageKey.NORMALIZE).touch("input", "normalized")
        window._enter_stage2()

        window._on_clean_chunk()
        chunk_text = "\n".join(chunk.text for chunk in window.document.chunks)

        self.assertNotIn("<p>", chunk_text)
        self.assertIn("phần trăm", chunk_text)


if __name__ == "__main__":
    unittest.main()

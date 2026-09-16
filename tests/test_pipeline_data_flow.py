"""Regression tests for the in-memory stage-to-stage pipeline flow."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chapters import NormalizeOptions, build_patterns, normalize_chapters
from config.settings import Settings
from pipeline.document import PipelineDocument, PipelineStateError, StageKey
from ui.main_window import MainWindow
from tests.support import create_dictionary_fixture


RAW_TEXT = """第327章 流民不可怕
Chương 327: Lưu dân không đáng sợ

Đám lao dịch bận rộn.

第328章
Chinese body 修炼者 修炼.
"""


class PipelineDataFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.settings = Settings()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(output_dir=self.temp.name)
        self.master_dictionary = create_dictionary_fixture(Path(self.temp.name))

    def tearDown(self):
        self.master_dictionary.close()
        self.temp.cleanup()

    def make_document(self) -> PipelineDocument:
        document = PipelineDocument()
        document.load_original_input(RAW_TEXT)
        chapters, _report, diagnostics = normalize_chapters(
            RAW_TEXT,
            build_patterns(self.settings),
            NormalizeOptions(),
            source_name="merged",
        )
        document.set_normalized_output(chapters)
        document.diagnostics.extend(diagnostics)
        document.stage(StageKey.NORMALIZE).touch("1 source", f"{len(chapters)} chapters")
        return document

    def make_window(self, document: PipelineDocument) -> MainWindow:
        window = MainWindow(self.settings, master_dictionary=self.master_dictionary)
        window.document = document
        return window

    def test_step2_uses_exact_normalized_text_and_preserves_original(self):
        document = self.make_document()
        original = document.original_input_text

        step2_input, source = document.begin_chinese_review()

        self.assertEqual(step2_input, document.normalized_text)
        self.assertEqual(source, "Source: Step 1 — Normalized Text")
        self.assertEqual(document.original_input_text, original)
        self.assertNotIn("第327章", step2_input)
        self.assertNotIn("流民不可怕", step2_input)
        self.assertIn("Chương 327: Lưu dân không đáng sợ", step2_input)

        window = self.make_window(document)
        window._on_scan_chinese()
        scan_output = window.stage2_output.toPlainText()
        self.assertNotIn("流民不可怕", scan_output)
        self.assertIn("修炼者", scan_output)

    def test_scan_uses_current_text_not_stale_chapter_objects(self):
        document = self.make_document()
        window = self.make_window(document)
        edited = document.normalized_text.replace("修炼者 修炼", "新词")
        document.set_normalized_edit(edited)
        # Deliberately leave the old parsed chapters in place.  Step 2 must
        # still scan the edited authoritative string.
        window._enter_stage2()
        self.assertIn("新词", window.stage2_output.toPlainText())
        self.assertNotIn("修炼者", window.stage2_output.toPlainText())

    def test_removed_chinese_title_is_absent_from_step2(self):
        raw = "第329章 只应出现在标题\n正文中的中文词语。"
        document = PipelineDocument()
        document.load_original_input(raw)
        chapters, _report, diagnostics = normalize_chapters(
            raw,
            build_patterns(self.settings),
            NormalizeOptions(),
            source_name="merged",
        )
        document.set_normalized_output(chapters)
        document.diagnostics.extend(diagnostics)
        document.stage(StageKey.NORMALIZE).touch("1 source", "1 chapter")
        window = self.make_window(document)

        window._enter_stage2()

        self.assertNotIn("只应出现在标题", document.normalized_text)
        self.assertNotIn("只应出现在标题", window.stage2_input_preview.toPlainText())
        self.assertNotIn("只应出现在标题", window.stage2_output.toPlainText())
        self.assertIn("正文中的中文词语", window.stage2_output.toPlainText())

    def test_original_is_the_only_fallback_before_step1(self):
        document = PipelineDocument()
        document.load_original_input(RAW_TEXT)

        step2_input, source = document.begin_chinese_review()

        self.assertEqual(step2_input, RAW_TEXT)
        self.assertEqual(source, "Source: Original File — Step 1 not run")

    def test_successful_step1_without_output_fails_closed(self):
        document = PipelineDocument()
        document.load_original_input(RAW_TEXT)
        document.stage(StageKey.NORMALIZE).touch("input", "successful")

        with self.assertRaises(PipelineStateError):
            document.begin_chinese_review()

    def test_manual_step1_edit_replaces_step2_source(self):
        document = self.make_document()
        window = self.make_window(document)
        window._enter_stage2()
        self.assertIsNotNone(document.chinese_review_text)

        edited = document.normalized_text.replace("Đám lao dịch", "Nội dung đã sửa")
        window.stage1_output.setReadOnly(False)
        window.stage1_output.setPlainText(edited)

        self.assertIsNone(document.chinese_review_text)
        window._enter_stage2()
        self.assertEqual(document.chinese_review_text, edited)
        self.assertEqual(window.stage2_input_preview.toPlainText(), edited)

    def test_translation_output_reaches_step3_chunks(self):
        document = self.make_document()
        window = self.make_window(document)
        window._enter_stage2()
        document.translations = {"修炼者": "tu luyện giả", "修炼": "tu luyện"}

        window._on_translate()
        self.assertIn("tu luyện giả", document.chinese_review_text)
        self.assertNotIn("修炼者", document.chinese_review_text)
        self.assertEqual(document.step2_confirmed_output, document.chinese_review_text)

        window._on_clean_chunk()
        chunk_text = "\n".join(chunk.text for chunk in document.chunks)
        self.assertIn("tu luyện giả", chunk_text)
        self.assertNotIn("修炼者", chunk_text)
        self.assertEqual(document.cleaned_text, document.chinese_review_text)

    def test_step3_bundle_unlocks_step4_with_first_chapter_preview(self):
        document = self.make_document()
        window = self.make_window(document)
        window._enter_stage2()
        document.translations = {"修炼者": "tu luyện giả", "修炼": "tu luyện"}
        window._on_translate()
        window._on_clean_chunk()

        bundle = document.require_step3_artifacts()
        self.assertTrue(Path(bundle.txt_path).is_file())
        self.assertTrue(Path(bundle.json_path).is_file())
        window._continue_to_stage4()
        self.assertEqual(window.tabs.currentIndex(), 3)
        self.assertIn("Chương 327", window.stage4_first_chapter.toPlainText())
        self.assertIn("Đám lao dịch", window.stage4_first_chapter.toPlainText())
        self.assertFalse(hasattr(window, "stage4_txt_upload_btn"))

    def test_step4_export_uses_step3_output(self):
        document = self.make_document()
        window = self.make_window(document)
        window._enter_stage2()
        document.translations = {"修炼者": "tu luyện giả", "修炼": "tu luyện"}
        window._on_translate()
        window._on_clean_chunk()

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "export.json")
            with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(path, "")):
                window._on_export()
            exported = Path(path).read_text(encoding="utf-8")

        self.assertIn("tu luyện giả", exported)
        self.assertNotIn("修炼者", exported)
        self.assertEqual(document.filtered_output, exported)

    def test_ui_continue_and_tab_navigation_share_handoff(self):
        document = self.make_document()
        window = self.make_window(document)

        window._continue_to_stage2()
        first = document.chinese_review_text
        self.assertEqual(window.stage2_source_label.text(), "Source: Step 1 — Normalized Text")

        window.tabs.setCurrentIndex(0)
        window.tabs.setCurrentIndex(1)
        self.assertEqual(document.chinese_review_text, first)
        self.assertEqual(window.stage2_input_preview.toPlainText(), document.normalized_text)

    def test_step3_requires_explicit_han_free_confirmed_output(self):
        document = self.make_document()
        document.begin_chinese_review()

        with self.assertRaises(PipelineStateError):
            document.require_step2_confirmed_output()

        document.set_chinese_review_output(document.chinese_review_text.replace("修炼者 修炼", "done"))
        document.complete_chinese_review(document.chinese_review_text)
        self.assertEqual(document.require_step2_confirmed_output(), document.chinese_review_text)

    def test_step1_change_invalidates_confirmed_step2_and_chunks(self):
        document = self.make_document()
        window = self.make_window(document)
        window._enter_stage2()
        document.translations = {"修炼者": "tu luyện giả", "修炼": "tu luyện"}
        window._on_translate()
        window._on_clean_chunk()
        self.assertTrue(document.chunks)

        document.set_normalized_edit(document.normalized_text + "\nĐã thay đổi.")

        self.assertIsNone(document.step2_confirmed_output)
        self.assertIsNone(document.chinese_review_session)
        self.assertEqual(document.chunks, [])


if __name__ == "__main__":
    unittest.main()

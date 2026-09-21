"""Regression tests for the direct Step 1 -> Step 2 pipeline flow."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chapters import NormalizeOptions, build_patterns, normalize_chapters
from config.settings import Settings
from pipeline.document import PipelineDocument, PipelineStateError, StageKey
from ui.main_window import MainWindow


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

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings()

    def tearDown(self):
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

    def test_step2_consumes_exact_normalized_text_without_han_gate(self):
        document = self.make_document()
        original = document.original_input_text

        source, label = document.grouping_input_text()

        self.assertEqual(source, document.normalized_text)
        self.assertEqual(label, "Source: Step 1 — Normalized Text")
        self.assertEqual(document.original_input_text, original)
        self.assertNotIn("第327章", source)
        self.assertNotIn("流民不可怕", source)
        self.assertIn("Chương 327: Lưu dân không đáng sợ", source)
        self.assertIn("修炼者", source)
        self.assertEqual(document.require_grouping_input(), source)

    def test_original_is_fallback_before_step1(self):
        document = PipelineDocument()
        document.load_original_input(RAW_TEXT)

        source, label = document.grouping_input_text()

        self.assertEqual(source, RAW_TEXT)
        self.assertEqual(label, "Source: Original File — Step 1 not run")

    def test_successful_step1_without_output_fails_closed(self):
        document = PipelineDocument()
        document.load_original_input(RAW_TEXT)
        document.stage(StageKey.NORMALIZE).touch("input", "successful")

        with self.assertRaises(PipelineStateError):
            document.grouping_input_text()

    def test_step1_edit_replaces_grouping_source_and_invalidates_chunks(self):
        document = self.make_document()
        document.chunks = [object()]
        edited = document.normalized_text.replace("Đám lao dịch", "Nội dung đã sửa")

        self.assertTrue(document.set_normalized_edit(edited))

        self.assertEqual(document.require_grouping_input(), edited)
        self.assertEqual(document.chunks, [])
        self.assertIsNone(document.step3_artifacts)

    def test_main_window_allows_chinese_text_in_step2(self):
        window = MainWindow(self.settings)
        self.addCleanup(window.close)
        window.document = self.make_document()
        window._set_job_editors("Novel", "Chương 327")

        window._continue_to_stage2()

        self.assertEqual(window.tabs.currentIndex(), 1)
        self.assertIn("修炼者", window.document.require_grouping_input())


if __name__ == "__main__":
    unittest.main()

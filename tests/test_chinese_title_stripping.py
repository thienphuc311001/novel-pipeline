"""Regression tests for Chinese same-line chapter-title removal."""

from __future__ import annotations

import unittest

from chapters.normalizer import NormalizeOptions, normalize_chapters
from chapters.patterns import DEFAULT_PATTERNS, PatternSet


class ChineseTitleStrippingTests(unittest.TestCase):
    def normalize(self, text: str, *, keep_original_headers: bool = False):
        return normalize_chapters(
            text,
            PatternSet(patterns=DEFAULT_PATTERNS),
            NormalizeOptions(keep_original_headers=keep_original_headers),
        )

    def test_chinese_only_same_line_titles_are_removed(self):
        samples = (
            "第327章 流民不可怕",
            "第327章：流民不可怕",
            "第327章-流民不可怕",
            "第327章流民不可怕",
            "[第327章] 流民不可怕",
            "【第327章】 流民不可怕",
            "第327回 流民不可怕",
            "第327节 流民不可怕",
            "第三百二十七章 流民不可怕",
        )

        for sample in samples:
            with self.subTest(sample=sample):
                chapters, report, _diagnostics = self.normalize(sample)
                self.assertEqual(len(chapters), 1)
                self.assertEqual(chapters[0].header_line, "Chương 327")
                self.assertEqual(chapters[0].text, "")
                self.assertEqual(report.chinese_titles_removed, 1)

    def test_title_punctuation_and_digits_are_removed(self):
        chapters, report, _diagnostics = self.normalize("第327章《流民不可怕！第2部》")

        self.assertEqual(chapters[0].header_line, "Chương 327")
        self.assertEqual(chapters[0].text, "")
        self.assertEqual(report.chinese_titles_removed, 1)

    def test_following_line_chinese_body_is_preserved(self):
        chapters, report, _diagnostics = self.normalize(
            "第327章 流民不可怕\n正文中的中文内容仍然保留。"
        )

        self.assertEqual(chapters[0].header_line, "Chương 327")
        self.assertIn("正文中的中文内容仍然保留", chapters[0].text)
        self.assertNotIn("流民不可怕", chapters[0].text)
        self.assertEqual(report.chinese_titles_removed, 1)

    def test_mixed_same_line_narrative_is_preserved(self):
        for sample in (
            "第327章: Đêm ấy trời mưa.",
            "第327章Đêm ấy trời mưa.",
            "[第327章] Đêm ấy trời mưa.",
        ):
            with self.subTest(sample=sample):
                chapters, report, _diagnostics = self.normalize(sample)
                self.assertIn("Đêm ấy trời mưa", chapters[0].text)
                self.assertEqual(report.chinese_titles_removed, 0)

    def test_keep_original_headers_retains_only_marker(self):
        chapters, report, _diagnostics = self.normalize(
            "[第327章] 流民不可怕", keep_original_headers=True
        )

        self.assertEqual(chapters[0].header_line, "[第327章]")
        self.assertEqual(chapters[0].text, "")
        self.assertEqual(report.chinese_titles_removed, 1)


if __name__ == "__main__":
    unittest.main()

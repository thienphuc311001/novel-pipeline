"""Regression tests for countdown/clock lines inside chapter bodies.

Countdown stamps such as ``【4:59:50】`` or ``【12:09:57 — rương báu】`` are
narrative content.  They used to match the plain numbered pattern and became
phantom chapters (``Chương 0``, ``Chương 23``) while splitting the body of the
chapter they belong to.
"""

from __future__ import annotations

import unittest

from chapters.detector import detect_chapters
from chapters.normalizer import NormalizeOptions, normalize_chapters
from chapters.patterns import DEFAULT_PATTERNS, PatternSet, build_patterns
from config.settings import Settings
from media.groups import analyze_grouping, preview_groups, scan_headings


class ClockLineTests(unittest.TestCase):
    def patterns(self) -> PatternSet:
        # Default user-facing pattern set: plain numbered OFF so that
        # in-body enumerated lists ("1. ...") are not phantom chapters.
        return build_patterns(Settings())

    def patterns_with_plain(self) -> PatternSet:
        settings = Settings()
        settings.detect_plain_numbered = True
        return build_patterns(settings)

    def detect_with_plain(self, text: str):
        hits, _preamble, _notes = detect_chapters(text, self.patterns_with_plain())
        return hits

    def detect(self, text: str):
        hits, _preamble, _notes = detect_chapters(text, self.patterns())
        return hits

    def normalize(self, text: str):
        return normalize_chapters(text, self.patterns(), NormalizeOptions())

    def test_decorated_countdown_lines_are_not_headers(self):
        samples = (
            "【4:59:50】",
            "【4:52:03】",
            "【00:18】",
            "【0:15】",
            "【23:59:59】",
            "【12:09:57 — rương báu】",
            "【1:56】",
            "[4:59:50]",
            "（00:18）",
        )

        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(self.detect(sample), [])

    def test_undecorated_clock_line_is_not_a_header(self):
        self.assertEqual(self.detect("10:30 sáng hôm đó trời mưa rất to."), [])

    def test_countdown_line_stays_in_chapter_body(self):
        text = (
            "Chương 14: Trăng xanh\n\n"
            "Đồng hồ đếm ngược hiện ra trước mắt.\n\n"
            "【4:59:50】\n\n"
            "Khâu Đồ im lặng vài giây rồi chậm rãi bật cười.\n"
        )

        chapters, _report, _diagnostics = self.normalize(text)

        self.assertEqual([chapter.number for chapter in chapters], [14])
        self.assertIn("【4:59:50】", chapters[0].text)
        self.assertIn("Khâu Đồ im lặng vài giây", chapters[0].text)

    def test_source_with_twenty_chapters_detects_twenty(self):
        chapters, _report, _diagnostics = self.normalize(self.twenty_chapter_source())

        self.assertEqual([chapter.number for chapter in chapters], list(range(1, 21)))
        body = "\n".join(chapter.text for chapter in chapters)
        self.assertIn("【23:59:59】", body)
        self.assertIn("【12:09:57 — rương báu】", body)

    def test_chapter_after_countdown_lines_keeps_the_rest_of_its_body(self):
        chapters, _report, _diagnostics = self.normalize(self.twenty_chapter_source())

        chapter = next(item for item in chapters if item.number == 14)
        self.assertIn("rương có đồng hồ đếm ngược 24 giờ", chapter.text)
        self.assertIn("Sáng hôm sau", chapter.text)
        self.assertIn("Thân chương 14", chapter.text)

    def test_plain_numbered_headers_are_still_detected_when_opted_in(self):
        for sample in ("12. Đêm đầu tiên", "12: Đêm đầu tiên", "12) Đêm đầu tiên"):
            with self.subTest(sample=sample):
                hits = self.detect_with_plain(sample)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].number, 12)

    def test_plain_numbered_lines_are_ignored_by_default(self):
        for sample in ("12. Đêm đầu tiên", "12: Đêm đầu tiên", "12) Đêm đầu tiên"):
            with self.subTest(sample=sample):
                self.assertEqual(self.detect(sample), [])

    def test_enumerated_list_inside_chapter_body_is_not_split(self):
        text = (
            "Chương 36: Bí mật của nhà họ Tần\n\n"
            "Manh mối Khâu Đồ nắm chủ yếu có bốn điểm:\n\n"
            "1. Tần Chính Quang, nhị chi nhà họ Tần, có vấn đề chuyển lợi ích.\n\n"
            "2. Tần Chính Quang vẫn luôn âm thầm hợp tác với Liên Trận.\n\n"
            "3. Hai tháng trước, Tần Chính Quang tự ý thả một nhóm nghi phạm.\n\n"
            "4. Tần Chính Quang vét thuốc từ chợ đen do mình khống chế.\n\n"
            "Còn trong tay Lâm Tả là những manh mối khác.\n"
        )

        chapters, _report, _diagnostics = self.normalize(text)

        self.assertEqual([chapter.number for chapter in chapters], [36])
        body = chapters[0].text
        for fragment in (
            "1. Tần Chính Quang",
            "2. Tần Chính Quang",
            "3. Hai tháng trước",
            "4. Tần Chính Quang",
        ):
            self.assertIn(fragment, body)

    def test_enumerated_list_becomes_chapters_only_when_plain_opted_in(self):
        text = (
            "Chương 36: Bí mật của nhà họ Tần\n\n"
            "Manh mối Khâu Đồ nắm chủ yếu có bốn điểm:\n\n"
            "1. Tần Chính Quang, nhị chi nhà họ Tần, có vấn đề chuyển lợi ích.\n\n"
            "2. Tần Chính Quang vẫn luôn âm thầm hợp tác với Liên Trận.\n"
        )

        hits, _preamble, _notes = detect_chapters(text, self.patterns_with_plain())

        self.assertEqual(
            [(hit.number, hit.pattern_name) for hit in hits],
            [(36, "vietnamese"), (1, "plain"), (2, "plain")],
        )

    def test_vietnamese_header_with_numeric_title_is_kept(self):
        hits = self.detect("Chương 12: 30 ngày đêm")

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].number, 12)
        self.assertEqual(hits[0].title, "30 ngày đêm")

    @staticmethod
    def twenty_chapter_source() -> str:
        parts = []
        for number in range(1, 21):
            parts.append(f"Chương {number}: Tiêu đề {number}\n\n")
            if number == 4:
                parts.append("【4:59:50】\n\n")
            if number == 14:
                parts.append(
                    "Nhưng khác với chiếc rương lần trước, lần này rương có "
                    "đồng hồ đếm ngược 24 giờ.\n\n"
                    "【23:59:59】\n\n"
                    "Khâu Đồ: ...\n\n"
                    "【12:09:57 — rương báu】\n\n"
                    "Sáng hôm sau, Khâu Đồ bị tiếng gõ cửa đánh thức.\n\n"
                )
            parts.append(f"Thân chương {number} vẫn còn nguyên vẹn.\n\n")
        return "".join(parts)


    def test_step2_scanner_ignores_countdown_lines(self):
        headings = scan_headings(self.twenty_chapter_source(), Settings())

        self.assertEqual([heading.number for heading in headings], list(range(1, 21)))

    def test_step2_analysis_reports_no_phantom_numbering(self):
        analysis = analyze_grouping(self.twenty_chapter_source(), Settings(), 20)

        self.assertEqual(analysis.expected_count, 20)
        self.assertEqual(analysis.diagnostics, [])
        self.assertFalse(analysis.requires_numeric_boundaries)

    def test_step2_preview_groups_uses_only_real_chapters(self):
        text = self.twenty_chapter_source()
        headings, groups, diagnostics = preview_groups(text, Settings(), 20)

        self.assertEqual(len(headings), 20)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["label"], "Chương 1-20")
        self.assertEqual(len(groups[0]["chapters"]), 20)
        self.assertEqual(diagnostics, [])
        self.assertEqual("".join(text[group["start"]:group["end"]] for group in groups), text)


if __name__ == "__main__":
    unittest.main()

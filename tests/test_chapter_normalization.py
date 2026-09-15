"""Comprehensive tests for chapter detection and normalization.

Tests all requirements:
1. Multi-language chapter detection
2. Canonical chapter format (Chương X)
3. Chinese subtitle removal
4. Vietnamese content preservation
5. Duplicate detection and resolution
6. Clean TXT export
"""

from __future__ import annotations

from pathlib import Path

from chapters.detector import detect_chapters
from chapters.duplicates import resolve_duplicates
from chapters.normalizer import (
    normalize_chapters,
    format_chapter_header,
    NormalizeOptions,
)
from chapters.patterns import build_patterns, PatternSet, DEFAULT_PATTERNS
from chapters.numerals import chinese_to_int, parse_number_token
from pipeline.document import Chapter
from config.settings import Settings
from exporters.txt_export import export_clean_txt


class TestChineseNumeralParsing:
    """Test Chinese numeral conversion."""
    
    def test_simple_numerals(self):
        assert chinese_to_int("一") == 1
        assert chinese_to_int("二") == 2
        assert chinese_to_int("三") == 3
        assert chinese_to_int("九") == 9
    
    def test_tens(self):
        assert chinese_to_int("十") == 10
        assert chinese_to_int("二十") == 20
        assert chinese_to_int("二十三") == 23
    
    def test_hundreds(self):
        assert chinese_to_int("一百") == 100
        assert chinese_to_int("一百二十三") == 123
        assert chinese_to_int("三百二十七") == 327
    
    def test_complex(self):
        assert chinese_to_int("一千") == 1000
        assert chinese_to_int("九千九百九十九") == 9999
    
    def test_fullwidth_digits(self):
        assert parse_number_token("０３２７") == 327
        assert parse_number_token("１２３") == 123


class TestChapterDetection:
    """Test multi-language chapter detection."""
    
    def get_pattern_set(self):
        settings = Settings()
        return build_patterns(settings)
    
    def test_chinese_basic(self):
        """Test basic Chinese chapter formats."""
        pattern_set = self.get_pattern_set()
        
        test_cases = [
            ("第1章", 1),
            ("第2章", 2),
            ("第10章", 10),
            ("第001章", 1),
            ("第0327章", 327),
        ]
        
        for text, expected_number in test_cases:
            hits, _, _ = detect_chapters(text, pattern_set)
            assert len(hits) == 1
            assert hits[0].number == expected_number
            assert hits[0].language == "zh"
    
    def test_chinese_numerals(self):
        """Test Chinese numeral chapter numbers."""
        pattern_set = self.get_pattern_set()
        
        test_cases = [
            ("第一章", 1),
            ("第二章", 2),
            ("第十章", 10),
            ("第二十三章", 23),
            ("第一百二十三章", 123),
            ("第三百二十七章", 327),
        ]
        
        for text, expected_number in test_cases:
            hits, _, _ = detect_chapters(text, pattern_set)
            assert len(hits) == 1
            assert hits[0].number == expected_number
    
    def test_chinese_units(self):
        """Test different Chinese chapter units."""
        pattern_set = self.get_pattern_set()
        
        test_cases = [
            "第1回",
            "第1节",
            "第1集",
        ]
        
        for text in test_cases:
            hits, _, _ = detect_chapters(text, pattern_set)
            assert len(hits) == 1
            assert hits[0].number == 1
    
    def test_chinese_with_brackets(self):
        """Test Chinese chapters with decorative brackets."""
        pattern_set = self.get_pattern_set()
        
        test_cases = [
            "【第1章】",
            "[第1章]",
            "（第1章）",
            "★第1章",
            "#第1章",
        ]
        
        for text in test_cases:
            hits, _, _ = detect_chapters(text, pattern_set)
            assert len(hits) == 1
            assert hits[0].number == 1
    
    def test_vietnamese_basic(self):
        """Test Vietnamese chapter formats."""
        pattern_set = self.get_pattern_set()
        
        test_cases = [
            ("Chương 1", 1),
            ("Chương 01", 1),
            ("Chương 001", 1),
            ("CHƯƠNG 1", 1),
            ("Chuong 1", 1),
        ]
        
        for text, expected_number in test_cases:
            hits, _, _ = detect_chapters(text, pattern_set)
            assert len(hits) == 1
            assert hits[0].number == expected_number
            assert hits[0].language == "vi"
    
    def test_vietnamese_variants(self):
        """Test Vietnamese chapter prefix variants."""
        pattern_set = self.get_pattern_set()
        
        test_cases = [
            "Hồi 1",
            "Tập 1",
            "Quyển 1",
            "Phần 1",
        ]
        
        for text in test_cases:
            hits, _, _ = detect_chapters(text, pattern_set)
            assert len(hits) == 1
            assert hits[0].number == 1


class TestChapterNormalization:
    """Test chapter header normalization."""
    
    def test_chinese_to_vietnamese_format(self):
        """Test Chinese headers normalize to Chương X."""
        options = NormalizeOptions()
        
        # Chinese headers should normalize to "Chương X"
        assert format_chapter_header(327, "", options) == "Chương 327"
        assert format_chapter_header(1, "", options) == "Chương 1"
        assert format_chapter_header(123, "", options) == "Chương 123"
    
    def test_vietnamese_with_title(self):
        """Test Vietnamese headers preserve titles."""
        options = NormalizeOptions()
        
        result = format_chapter_header(327, "Lưu dân không đáng sợ", options)
        assert result == "Chương 327: Lưu dân không đáng sợ"
    
    def test_leading_zero_removal(self):
        """Test leading zeros are removed by default."""
        options = NormalizeOptions(zero_pad=0)
        
        result = format_chapter_header(327, "", options)
        assert result == "Chương 327"
        assert "0327" not in result
    
    def test_leading_zero_preservation(self):
        """Test leading zero preservation when configured."""
        options = NormalizeOptions(zero_pad=4)
        
        result = format_chapter_header(327, "", options)
        assert result == "Chương 0327"


class TestChineseSubtitleRemoval:
    """Test Chinese subtitle removal."""
    
    def test_chinese_subtitle_removed(self):
        """Chinese subtitles must be removed during normalization."""
        pattern_set = PatternSet(patterns=DEFAULT_PATTERNS)
        options = NormalizeOptions()
        
        text = "第327章 流民不可怕"
        chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
        
        assert len(chapters) == 1
        assert chapters[0].number == 327
        # Chinese subtitle should NOT appear in final header
        assert "流民不可怕" not in chapters[0].header_line
        assert chapters[0].header_line == "Chương 327"
    
    def test_chinese_subtitle_with_colon(self):
        """Test Chinese subtitle removal with colon separator."""
        pattern_set = PatternSet(patterns=DEFAULT_PATTERNS)
        options = NormalizeOptions()
        
        text = "第327章：流民不可怕"
        chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
        
        assert len(chapters) == 1
        assert chapters[0].header_line == "Chương 327"


class TestVietnameseContentPreservation:
    """Test Vietnamese content preservation (CRITICAL)."""
    
    def test_vietnamese_title_preserved(self):
        """Vietnamese title must be preserved."""
        pattern_set = PatternSet(patterns=DEFAULT_PATTERNS)
        options = NormalizeOptions()
        
        text = "Chương 0327: Lưu dân không đáng sợ"
        chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
        
        assert len(chapters) == 1
        # Vietnamese title MUST be preserved
        assert "Lưu dân không đáng sợ" in chapters[0].header_line
        assert chapters[0].header_line == "Chương 327: Lưu dân không đáng sợ"
    
    def test_vietnamese_dialogue_preserved(self):
        """Vietnamese dialogue on same line must be preserved."""
        pattern_set = PatternSet(patterns=DEFAULT_PATTERNS)
        options = NormalizeOptions()
        
        text = 'Chương 0328: "Tiểu tử hiểu rồi……". Khấu Quý chắp tay nói với Lý Địch.'
        chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
        
        assert len(chapters) == 1
        # Complete Vietnamese content must be preserved
        header = chapters[0].header_line
        assert "Tiểu tử hiểu rồi" in header
        assert "Khấu Quý" in header


class TestDuplicateResolution:
    """Test duplicate chapter detection and resolution."""
    
    def test_same_chapter_number_detection(self):
        """Test detection of duplicate chapter numbers."""
        chapters = [
            Chapter(number=327, header_line="第327章", text="Chinese", language="zh"),
            Chapter(number=327, header_line="Chương 327", text="Vietnamese", language="vi"),
        ]
        
        report = resolve_duplicates(chapters, prefer_vietnamese=True)
        
        assert len(report.groups) == 1
        assert len(report.kept) == 1
        assert len(report.discarded) == 1
    
    def test_vietnamese_priority_over_chinese(self):
        """Vietnamese candidate must win over Chinese."""
        chapters = [
            Chapter(number=327, header_line="第327章 流民不可怕", text="Chinese", language="zh", source_line=1),
            Chapter(number=327, header_line="Chương 327", text="Vietnamese", language="vi", source_line=2),
        ]
        
        report = resolve_duplicates(chapters, prefer_vietnamese=True)
        
        assert len(report.kept) == 1
        assert report.kept[0].language == "vi"
        assert len(report.discarded) == 1
        assert report.discarded[0].language == "zh"
    
    def test_title_priority(self):
        """Candidate with title wins over bare number."""
        chapters = [
            Chapter(number=327, header_line="Chương 327", text="Content", title="", language="vi", source_line=1),
            Chapter(number=327, header_line="Chương 327: Lưu dân", text="Content", title="Lưu dân", language="vi", source_line=2),
        ]
        
        report = resolve_duplicates(chapters, prefer_vietnamese=True)
        
        assert len(report.kept) == 1
        assert report.kept[0].title == "Lưu dân"
    
    def test_longer_content_priority(self):
        """Longer content wins over shorter."""
        chapters = [
            Chapter(number=327, header_line="Chương 327", text="Short", language="vi", source_line=1),
            Chapter(number=327, header_line="Chương 327", text="Much longer content here", language="vi", source_line=2),
        ]
        
        report = resolve_duplicates(chapters, prefer_vietnamese=True)
        
        assert len(report.kept) == 1
        assert len(report.kept[0].text) > 10
    
    def test_original_position_tiebreaker(self):
        """First occurrence wins on complete tie."""
        chapters = [
            Chapter(number=327, header_line="Chương 327", text="Same", language="vi", source_line=1),
            Chapter(number=327, header_line="Chương 327", text="Same", language="vi", source_line=2),
        ]
        
        report = resolve_duplicates(chapters, prefer_vietnamese=True)
        
        assert len(report.kept) == 1
        assert report.kept[0].source_line == 1


class TestCleanTxtExport:
    """Test clean TXT export (no metadata)."""
    
    def test_export_clean_txt_format(self, tmp_path):
        """Test clean TXT export contains only headers and content."""
        chapters = [
            Chapter(
                number=327,
                header_line="Chương 327: Lưu dân không đáng sợ",
                title="Lưu dân không đáng sợ",
                text="Đám lao dịch bận rộn trên đường phố...",
                language="vi",
                source_line=1,
            ),
            Chapter(
                number=328,
                header_line='Chương 328: "Tiểu tử hiểu rồi……"',
                title='"Tiểu tử hiểu rồi……"',
                text="Khấu Quý chắp tay nói với Lý Địch.",
                language="vi",
                source_line=10,
            ),
        ]
        
        output_path = tmp_path / "clean.txt"
        export_clean_txt(chapters, output_path)
        
        content = output_path.read_text(encoding="utf-8")
        
        # Must contain headers
        assert "Chương 327: Lưu dân không đáng sợ" in content
        assert 'Chương 328: "Tiểu tử hiểu rồi……"' in content
        
        # Must contain body content
        assert "Đám lao dịch bận rộn" in content
        assert "Khấu Quý chắp tay" in content
        
        # Must NOT contain metadata
        assert "source_line" not in content
        assert "language" not in content
        assert "diagnostic" not in content
        assert "duplicate" not in content
        assert "JSON" not in content.lower()


class TestEndToEndNormalization:
    """End-to-end normalization tests."""
    
    def test_mixed_chinese_vietnamese_normalization(self):
        """Test complete normalization of mixed Chinese/Vietnamese text."""
        pattern_set = PatternSet(patterns=DEFAULT_PATTERNS)
        options = NormalizeOptions()
        
        text = """第0327章 并不可怕的流民
Chương 0327: Lưu dân không đáng sợ

Đám lao dịch bận rộn trên đường phố...

第0328章
Chương 0328: "Tiểu tử hiểu rồi……". Khấu Quý chắp tay nói với Lý Địch.
"""
        
        chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
        
        # Should have 2 chapters after deduplication
        assert len(chapters) == 2
        
        # Chapter 327: Vietnamese title should be preserved
        ch327 = chapters[0]
        assert ch327.number == 327
        assert "Lưu dân không đáng sợ" in ch327.header_line
        assert "并不可怕的流民" not in ch327.header_line  # Chinese removed
        
        # Chapter 328: Vietnamese dialogue must be preserved
        ch328 = chapters[1]
        assert ch328.number == 328
        assert "Tiểu tử hiểu rồi" in ch328.header_line
    
    def test_full_pipeline_with_export(self, tmp_path):
        """Test complete pipeline from detection to clean export."""
        pattern_set = PatternSet(patterns=DEFAULT_PATTERNS)
        options = NormalizeOptions()
        
        text = """第327章 流民不可怕
Chương 327: Lưu dân không đáng sợ

Đám lao dịch bận rộn...

第328章
Chương 328

Khấu Quý chắp tay nói.
"""
        
        # Normalize
        chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
        
        # Export clean TXT
        output_path = tmp_path / "output.txt"
        export_clean_txt(chapters, output_path)
        
        content = output_path.read_text(encoding="utf-8")
        
        # Verify clean output
        assert "Chương 327: Lưu dân không đáng sợ" in content
        assert "Chương 328" in content
        assert "Đám lao dịch" in content
        assert "Khấu Quý" in content
        
        # Verify no Chinese headers
        assert "第327章" not in content
        assert "第328章" not in content
        
        # Verify no metadata
        assert "source_line" not in content
        assert "language" not in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

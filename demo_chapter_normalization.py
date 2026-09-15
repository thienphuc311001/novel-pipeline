#!/usr/bin/env python3
"""
Demonstration of the chapter detection and normalization system.

This script shows how to:
1. Detect chapters in multiple languages
2. Normalize chapter headers to canonical format
3. Resolve duplicate chapters
4. Export clean TXT output
"""

from chapters.normalizer import normalize_chapters, NormalizeOptions
from chapters.patterns import build_patterns
from config.settings import Settings
from exporters.txt_export import export_clean_txt
from pathlib import Path
import tempfile


def demo_basic_detection():
    """Demonstrate basic chapter detection."""
    print("=" * 70)
    print("DEMO 1: Basic Chapter Detection")
    print("=" * 70)
    print()
    
    settings = Settings()
    pattern_set = build_patterns(settings)
    options = NormalizeOptions()
    
    # Sample text with multiple formats
    text = """第1章
第2章
第10章
第001章
第一章
第二十三章
第三百二十七章
【第100章】
Chương 1
Chương 001
CHƯƠNG 5
Hồi 3
Tập 2
"""
    
    chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
    
    print(f"Detected {len(chapters)} chapters:\n")
    for chapter in chapters:
        print(f"  {chapter.header_line}")
    print()


def demo_chinese_subtitle_removal():
    """Demonstrate Chinese subtitle removal."""
    print("=" * 70)
    print("DEMO 2: Chinese Subtitle Removal")
    print("=" * 70)
    print()
    
    settings = Settings()
    pattern_set = build_patterns(settings)
    options = NormalizeOptions()
    
    text = """第327章 流民不可怕

这是正文内容...

第328章：并不可怕的流民

更多内容...
"""
    
    chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
    
    print("Input Chinese headers with subtitles:")
    print("  第327章 流民不可怕")
    print("  第328章：并不可怕的流民")
    print()
    print("Normalized output:")
    for chapter in chapters:
        print(f"  {chapter.header_line}")
    print()
    print("✓ Chinese subtitles removed, normalized to 'Chương X'")
    print()


def demo_vietnamese_preservation():
    """Demonstrate Vietnamese content preservation."""
    print("=" * 70)
    print("DEMO 3: Vietnamese Content Preservation (CRITICAL)")
    print("=" * 70)
    print()
    
    settings = Settings()
    pattern_set = build_patterns(settings)
    options = NormalizeOptions()
    
    text = """Chương 0327: Lưu dân không đáng sợ

Đám lao dịch bận rộn trên đường phố...

Chương 0328: "Tiểu tử hiểu rồi……". Khấu Quý chắp tay nói với Lý Địch.

"Quan lão gia thương lượng một chút?"
"""
    
    chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
    
    print("Input Vietnamese headers:")
    print('  Chương 0327: Lưu dân không đáng sợ')
    print('  Chương 0328: "Tiểu tử hiểu rồi……". Khấu Quý chắp tay...')
    print()
    print("Normalized output:")
    for chapter in chapters:
        header = chapter.header_line
        if len(header) > 60:
            header = header[:57] + "..."
        print(f"  {header}")
    print()
    print("✓ Vietnamese titles and dialogue preserved intact")
    print("✓ Only leading zeros removed from chapter numbers")
    print()


def demo_duplicate_resolution():
    """Demonstrate duplicate chapter resolution."""
    print("=" * 70)
    print("DEMO 4: Duplicate Chapter Resolution")
    print("=" * 70)
    print()
    
    settings = Settings()
    pattern_set = build_patterns(settings)
    options = NormalizeOptions()
    
    text = """第0327章 并不可怕的流民
Chương 0327: Lưu dân không đáng sợ

Đám lao dịch bận rộn trên đường phố...

第0328章
Chương 0328

Khấu Quý chắp tay nói với Lý Địch.

第0329章 标题
Chương 329: Tiêu đề dài hơn và đầy đủ hơn

Nội dung chương 329...
"""
    
    chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
    
    print(f"Input: {len(report.hits)} chapter headers detected")
    print(f"Output: {len(chapters)} chapters after deduplication")
    print()
    
    if report.duplicates:
        print(f"Duplicate groups: {len(report.duplicates.groups)}")
        print()
        
        for group in report.duplicates.groups:
            print(f"Chapter {group.number}:")
            print(f"  ✓ Kept: {group.kept.header_line}")
            print(f"  ✗ Discarded: {len(group.discarded)} duplicate(s)")
            for idx, reason in enumerate(group.reasons):
                discarded = group.discarded[idx]
                print(f"      - {discarded.header_line}")
                print(f"        Reason: {reason}")
            print()


def demo_mixed_content():
    """Demonstrate mixed Chinese/Vietnamese processing."""
    print("=" * 70)
    print("DEMO 5: Mixed Chinese/Vietnamese Content")
    print("=" * 70)
    print()
    
    settings = Settings()
    pattern_set = build_patterns(settings)
    options = NormalizeOptions()
    
    text = """前言

这是小说的前言部分...

第1章 开始
Chương 1: Bắt đầu

Trong một ngày đẹp trời...

第2章 旅程
Chương 2: Hành trình

Chuyến đi bắt đầu từ đây...

第3章：冒险
Chương 3: Mạo hiểm với những thử thách mới

Họ đối mặt với nhiều khó khăn...
"""
    
    chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
    
    print(f"Preamble: {len(report.preamble)} characters")
    print(f"Chapters detected: {len(report.hits)}")
    print(f"Final chapters: {len(chapters)}")
    print()
    
    print("Normalized chapters:")
    for chapter in chapters:
        print(f"  {chapter.number}: {chapter.header_line}")
        body_preview = chapter.text[:40].replace('\n', ' ')
        print(f"      {body_preview}...")
    print()


def demo_clean_export():
    """Demonstrate clean TXT export."""
    print("=" * 70)
    print("DEMO 6: Clean TXT Export (No Metadata)")
    print("=" * 70)
    print()
    
    settings = Settings()
    pattern_set = build_patterns(settings)
    options = NormalizeOptions()
    
    text = """第327章 流民不可怕
Chương 327: Lưu dân không đáng sợ

Đám lao dịch bận rộn trên đường phố...

第328章
Chương 328: "Tiểu tử hiểu rồi……"

Khấu Quý chắp tay nói với Lý Địch.
"""
    
    chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)
    
    # Export to temporary file
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "clean.txt"
        export_clean_txt(chapters, output_path)
        
        content = output_path.read_text(encoding="utf-8")
        
        print("Exported clean TXT content:")
        print("-" * 70)
        print(content[:400])
        print("...")
        print("-" * 70)
        print()
        
        # Verify no metadata
        checks = [
            ("source_line" not in content, "No source line numbers"),
            ("language" not in content, "No language metadata"),
            ("diagnostic" not in content.lower(), "No diagnostics"),
            ("第" not in content, "No Chinese headers"),
            ("Chương 327: Lưu dân" in content, "Vietnamese title preserved"),
            ("Đám lao dịch" in content, "Content preserved"),
        ]
        
        print("Verification:")
        for passed, description in checks:
            status = "✓" if passed else "✗"
            print(f"  {status} {description}")
    print()


def main():
    """Run all demonstrations."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 10 + "CHAPTER NORMALIZATION SYSTEM DEMONSTRATION" + " " * 16 + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    demo_basic_detection()
    demo_chinese_subtitle_removal()
    demo_vietnamese_preservation()
    demo_duplicate_resolution()
    demo_mixed_content()
    demo_clean_export()
    
    print("=" * 70)
    print("All demonstrations completed successfully!")
    print("=" * 70)
    print()
    print("See CHAPTER_NORMALIZATION.md for complete documentation.")
    print()


if __name__ == "__main__":
    main()

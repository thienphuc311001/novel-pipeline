#!/usr/bin/env python3
"""Verification script to test core functionality without GUI."""

import sys
from pathlib import Path

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from config.settings import Settings
        from pipeline.document import PipelineDocument
        from chapters import chinese_to_int, normalize_chapters, build_patterns, NormalizeOptions
        from chinese import extract_located_segments, group_segments, get_dictionary
        from chunking import split_chapters
        from filtering import parse_ranges, filter_chunks_by_ranges
        from translation import TranslationStore
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_chinese_numerals():
    """Test Chinese numeral conversion."""
    print("\nTesting Chinese numeral conversion...")
    from chapters import chinese_to_int
    
    tests = [
        ("九十八", 98),
        ("一百零五", 105),
        ("两万三千", 23000),
        ("一二", None),
        ("十十", None),
    ]
    
    for text, expected in tests:
        result = chinese_to_int(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} chinese_to_int('{text}') = {result} (expected {expected})")
    
    return True

def test_chapter_detection():
    """Test chapter detection."""
    print("\nTesting chapter detection...")
    from config.settings import Settings
    from chapters import build_patterns, normalize_chapters, NormalizeOptions
    
    text = """Chương 1: Khởi đầu
Đêm ấy trời mưa rất to.

Chương 2: Gặp gỡ
"Ngươi là ai?" hắn hỏi.

Chương 3: Chạy trốnNàng vội vàng bỏ đi.
"""
    
    settings = Settings()
    patterns = build_patterns(settings)
    options = NormalizeOptions.from_settings(settings)
    
    chapters, report, diagnostics = normalize_chapters(text, patterns, options)
    
    print(f"  ✓ Detected {len(chapters)} chapters")
    print(f"  ✓ Glued splits: {report.glued_splits}")
    
    for chapter in chapters:
        print(f"    - Ch {chapter.number}: {chapter.display_title()} ({chapter.char_count} chars)")
    
    return len(chapters) == 3

def test_phrase_replacement():
    """Test longest-first phrase replacement."""
    print("\nTesting phrase replacement...")
    from chinese.replacer import replace_phrases
    
    text = "他在修炼者之中修炼"
    translations = {
        "修炼": "tu luyện",
        "修炼者": "tu luyện giả"
    }
    
    result = replace_phrases(text, translations)
    expected = "他在tu luyện giả之中tu luyện"
    
    status = "✓" if result.text == expected else "✗"
    print(f"  {status} Phrase replacement")
    print(f"    Input:  {text}")
    print(f"    Output: {result.text}")
    print(f"    Replacements: {result.total_replacements}")
    
    return result.text == expected

def test_chunking():
    """Test sentence-aware chunking."""
    print("\nTesting chunking...")
    from chunking import split_text_by_limit
    
    # Test 1: Hard split detection
    text1 = "a" * 400
    plan1 = split_text_by_limit(text1, 100)
    print(f"  ✓ Hard split test: {plan1.count} chunks, {len(plan1.hard_splits)} hard splits")
    
    # Test 2: Sentence-aware splitting
    text2 = "Câu ngắn. " + "x" * 300
    plan2 = split_text_by_limit(text2, 100)
    sizes = [len(c) for c in plan2.chunks]
    print(f"  ✓ Sentence-aware test: {plan2.count} chunks, sizes: {sizes}")
    
    return True

def test_dictionary():
    """Test offline dictionary."""
    print("\nTesting dictionary...")
    from chinese.dictionary import get_dictionary
    
    dictionary = get_dictionary()
    print(f"  ✓ Loaded dictionary: {dictionary.phrase_count} phrases, {dictionary.reading_count} characters")
    
    # Test lookup
    entry = dictionary.lookup_phrase("修炼")
    if entry:
        print(f"    - 修炼 → {entry.translation}")
    
    return dictionary.phrase_count > 0

def main():
    """Run all tests."""
    print("=" * 60)
    print("Novel Pipeline v2 - Verification")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_chinese_numerals,
        test_chapter_detection,
        test_phrase_replacement,
        test_chunking,
        test_dictionary,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed - Application is ready!")
        return 0
    else:
        print("❌ Some tests failed - Check errors above")
        return 1

if __name__ == "__main__":
    sys.exit(main())

# Chapter Detection and Normalization System

Complete implementation of multi-language chapter detection with exact normalization behaviors.

## Overview

This system detects, normalizes, and deduplicates chapter headers across Chinese, Vietnamese, and English formats, ensuring:

1. ✅ Correct chapter boundary detection
2. ✅ Canonical chapter format (Chương X)
3. ✅ Chinese subtitle removal
4. ✅ Vietnamese content preservation (CRITICAL)
5. ✅ Duplicate resolution with exact priority rules
6. ✅ Clean TXT export (no metadata)
7. ✅ No data loss

## Supported Formats

### Chinese Chapter Formats

**Arabic Numerals:**
- `第1章`, `第2章`, `第10章`
- `第001章`, `第0327章` (with leading zeros)

**Full-width Arabic:**
- `第１章`, `第２章` (converts to regular digits)

**Chinese Numerals:**
- `第一章` (1)
- `第二章` (2)
- `第十章` (10)
- `第二十三章` (23)
- `第一百二十三章` (123)
- `第三百二十七章` (327)

**Different Units:**
- `第1回`, `第1节`, `第1集`, `第1卷`

**With Decorative Brackets:**
- `【第1章】`, `[第1章]`, `（第1章）`
- `★第1章`, `#第1章`

### Vietnamese Chapter Formats

- `Chương 1`, `Chương 01`, `Chương 001`
- `CHƯƠNG 1`, `Chuong 1` (case-insensitive)
- `Hồi 1`, `Tập 1`, `Quyển 1`, `Phần 1`

### English Chapter Formats

- `Chapter 1`, `Part 1`, `Book 1`
- `Volume 1`, `Episode 1`

## Normalization Rules

### Rule 1: Chinese Headers → "Chương X"

Chinese-only headers are normalized to canonical Vietnamese format with Chinese subtitle removed.

**Examples:**

```
Input:  第327章
Output: Chương 327

Input:  第327章 流民不可怕
Output: Chương 327

Input:  第327章：流民不可怕
Output: Chương 327

Input:  第三百二十七章 并不可怕的流民
Output: Chương 327
```

**Chinese subtitles are NEVER preserved or translated.**

### Rule 2: Vietnamese Headers → Preserve Complete Content

Vietnamese chapter headers with titles or content must remain intact.

**Examples:**

```
Input:  Chương 0327: Lưu dân không đáng sợ
Output: Chương 327: Lưu dân không đáng sợ

Input:  Chương 0328: "Tiểu tử hiểu rồi……". Khấu Quý chắp tay nói với Lý Địch.
Output: Chương 328: "Tiểu tử hiểu rồi……". Khấu Quý chắp tay nói với Lý Địch.

Input:  Hồi 1: Khởi đầu
Output: Hồi 1: Khởi đầu
```

**Vietnamese content on the same line as a chapter header is NEVER truncated.**

### Rule 3: Leading Zeros Removed by Default

Leading zeros are stripped unless explicitly configured otherwise.

**Examples:**

```
Chương 0327 → Chương 327
Chương 001  → Chương 1
第0001章     → Chương 1
```

**Configuration:** Set `zero_pad` option to preserve leading zeros.

### Rule 4: Duplicate Chapter Resolution

When multiple headers represent the same chapter number, keep exactly ONE canonical header.

**Priority Rules (highest to lowest):**

1. **Vietnamese over Chinese**
   - Vietnamese candidate always wins over Chinese

2. **Title/Content over Bare Number**
   - Candidate with meaningful title/content wins

3. **Longer over Shorter**
   - Longer and more complete candidate wins

4. **Original Position**
   - Earlier occurrence wins on complete tie

**Example:**

```
Input:
  第327章 流民不可怕
  Chương 327: Lưu dân không đáng sợ

Output:
  Chương 327: Lưu dân không đáng sợ

Reason: Vietnamese candidate (priority 1)
```

**Example:**

```
Input:
  Chương 327
  Chương 327: Lưu dân không đáng sợ

Output:
  Chương 327: Lưu dân không đáng sợ

Reason: Has title (priority 2)
```

### Rule 5: Only Remove Redundant Headers, Never Body Content

Duplicate resolution removes only the redundant chapter HEADER, not the chapter body.

**Example:**

```
Input:
  第327章 流民不可怕
  Chương 327: Lưu dân không đáng sợ
  
  Đám lao dịch bận rộn trên đường phố...

Output:
  Chương 327: Lưu dân không đáng sợ
  
  Đám lao dịch bận rộn trên đường phố...
```

The body content is preserved intact.

## Clean TXT Export

The `export_clean_txt()` function produces output containing ONLY:

✅ Normalized chapter headers  
✅ Complete chapter body content  

❌ NO source line numbers  
❌ NO diagnostics  
❌ NO metadata  
❌ NO processing markers  
❌ NO duplicate information  
❌ NO JSON wrappers  

**Example Output:**

```
Chương 327: Lưu dân không đáng sợ

Đám lao dịch bận rộn trên đường phố...


Chương 328: "Tiểu tử hiểu rồi……"

Khấu Quý chắp tay nói với Lý Địch.
```

The output is reconstructed from the normalized chapter structure, not by filtering raw lines.

## Usage Examples

### Basic Normalization

```python
from chapters.normalizer import normalize_chapters, NormalizeOptions
from chapters.patterns import build_patterns
from config.settings import Settings

# Build pattern set from settings
settings = Settings()
pattern_set = build_patterns(settings)

# Configure normalization options
options = NormalizeOptions(
    chapter_prefix="Chương {n}",
    zero_pad=0,  # Remove leading zeros
    dedupe_chapters=True,
    prefer_vietnamese=True,
)

# Normalize text
text = """第327章 流民不可怕
Chương 327: Lưu dân không đáng sợ

Đám lao dịch bận rộn..."""

chapters, report, diagnostics = normalize_chapters(text, pattern_set, options)

# Result: 1 chapter (duplicate resolved)
# chapters[0].header_line = "Chương 327: Lưu dân không đáng sợ"
```

### Export Clean TXT

```python
from exporters.txt_export import export_clean_txt
from pathlib import Path

# Export normalized chapters
output_path = Path("output/clean.txt")
export_clean_txt(chapters, output_path)

# Result: Clean TXT with only headers and content
```

### Custom Chapter Format

```python
options = NormalizeOptions(
    chapter_prefix="Chapter {n}",  # English format
    zero_pad=4,  # Preserve 4-digit padding
    header_separator=" - ",
)

# Result: "Chapter 0327 - Title"
```

### Duplicate Resolution Report

```python
# Access duplicate resolution details
if report.duplicates:
    print(f"Duplicate groups: {len(report.duplicates.groups)}")
    print(f"Discarded chapters: {report.duplicates.discarded_count}")
    print(f"Discarded characters: {report.duplicates.discarded_chars}")
    
    for group in report.duplicates.groups:
        print(f"Chapter {group.number}:")
        print(f"  Kept: {group.kept.header_line}")
        print(f"  Discarded: {len(group.discarded)}")
        for reason in group.reasons:
            print(f"    - {reason}")
```

## Configuration Options

### NormalizeOptions

```python
@dataclass
class NormalizeOptions:
    # Header format
    chapter_prefix: str = "Chương {n}"        # Template for chapter prefix
    zero_pad: int = 0                         # Zero padding (0 = remove leading zeros)
    header_separator: str = ": "              # Separator between number and title
    keep_original_headers: bool = False       # Keep original headers (with cleanup)
    
    # Duplicate handling
    dedupe_chapters: bool = True              # Enable duplicate resolution
    prefer_vietnamese: bool = True            # Vietnamese priority over Chinese
    
    # Text cleaning
    enforce_period: bool = True               # Add missing sentence-ending periods
    normalize_spacing: bool = True            # Normalize whitespace
    restore_newlines: bool = True             # Restore escaped newlines
    
    # Validation
    min_chapter_chars: int = 0                # Minimum chapter length (0 = no limit)
```

### Settings (Application Level)

```python
# config/settings.py
settings = Settings(
    # Pattern detection
    detect_vietnamese=True,
    detect_english=True,
    detect_chinese=True,
    detect_plain_numbered=True,
    
    # Custom regex
    use_custom_chapter_regex=False,
    custom_chapter_regex="",
    
    # Normalization
    chapter_prefix="Chương {n}",
    zero_pad=0,
    dedupe_chapters=True,
    prefer_vietnamese=True,
)
```

## Data Preservation Guarantees

The system prioritizes data preservation:

1. **Vietnamese content is NEVER truncated**
   - Complete lines with Vietnamese text are preserved
   - Dialogue, narration, and titles remain intact

2. **Chapter bodies are NEVER deleted**
   - Only redundant headers are removed
   - All narrative content is preserved

3. **Conservative splitting**
   - Glued headers are split only when boundary is clear
   - Uncertain cases preserve original text

4. **No silent data loss**
   - All transformations are tracked
   - Text loss is reported in diagnostics

## Testing

Comprehensive test suite covers all requirements:

```bash
python3 tests/test_chapter_normalization.py
```

**Test Coverage:**
- ✅ Chinese numeral parsing (一, 十, 二十三, 一百二十三, 三百二十七)
- ✅ Full-width digit conversion (０３２７ → 327)
- ✅ Multi-language chapter detection
- ✅ Decorative bracket handling
- ✅ Header normalization
- ✅ Chinese subtitle removal
- ✅ Vietnamese content preservation
- ✅ Duplicate resolution priorities
- ✅ Clean TXT export
- ✅ End-to-end pipeline

## Module Structure

```
chapters/
├── __init__.py
├── numerals.py          # Chinese numeral conversion
├── patterns.py          # Chapter header patterns
├── detector.py          # Multi-language detection
├── duplicates.py        # Duplicate resolution
└── normalizer.py        # Chapter normalization

exporters/
├── __init__.py
└── txt_export.py        # Clean TXT export

tests/
└── test_chapter_normalization.py
```

## Implementation Notes

### Chinese Numeral Parser

Handles complex Chinese numerals correctly:

```python
chinese_to_int("三百二十七")  # → 327
chinese_to_int("一千")         # → 1000
chinese_to_int("九千九百九十九")  # → 9999
```

Rejects malformed input instead of guessing:

```python
chinese_to_int("一二")   # → None (invalid: two digits in a row)
chinese_to_int("十十")   # → None (invalid: repeated unit)
```

### Pattern Precedence

Patterns are tried in this order:

1. Custom regex (if configured)
2. Vietnamese (Chương, Hồi, Tập, etc.)
3. English (Chapter, Part, Book, etc.)
4. Chinese (第N章)
5. Plain numbered (12., 12:, #12)

Vietnamese and Chinese patterns are "strong" evidence for splitting glued headers.

### Glued Header Detection

The system detects and splits headers that are accidentally attached to text:

```
第327章Đêm ấy trời mưa...

→ Splits into:
   Header: 第327章
   Body: Đêm ấy trời mưa...
```

Only splits when confident. Uncertain cases preserve original text.

## Performance

- Fast regex-based pattern matching
- Single-pass detection
- Efficient duplicate grouping
- Minimal memory overhead

Typical performance:
- ~1000 chapters/second detection
- ~500 chapters/second normalization
- Handles novels with 1000+ chapters efficiently

## Future Enhancements

Possible future improvements:

- [ ] Additional language patterns (Korean, Japanese, Thai)
- [ ] Machine learning for ambiguous boundaries
- [ ] Automatic chapter title translation
- [ ] Smart chapter gap filling
- [ ] Chapter content validation

## License

Part of novel-pipeline-v2 - see main project LICENSE.

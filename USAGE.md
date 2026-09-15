# Usage Guide

## Quick Start

1. **Launch the application**
   ```bash
   python app.py
   ```

2. **Load your novel files**
   - Click "📁 Load Files"
   - Select one or more `.txt` or `.zip` files
   - Files are merged in natural order (ch9 before ch10)

3. **Process through the pipeline**
   - Tab 1: Normalize chapters
   - Tab 2: Review Chinese text (optional)
   - Tab 3: Clean and chunk
   - Tab 4: Filter and export

## Stage 1: Input & Normalize

### Loading Files

**Supported formats:**
- Plain text files (`.txt`)
- ZIP archives containing text files
- Multiple files merged automatically

**What gets loaded:**
- Text files with UTF-8, UTF-16, UTF-32, cp1258 (Vietnamese), cp1252
- Automatic encoding detection with BOM support

**What gets skipped:**
- Directories
- macOS metadata (`__MACOSX`, `._*`)
- Hidden files (`.something`)
- Non-text files

### Normalizing Chapters

Click **"▶️ Normalize Chapters"** to:

1. **Detect chapters** in Vietnamese, English, Chinese, or numbered formats:
   - `Chương 12`, `Chương 12: Tiêu đề`
   - `Chapter 5`, `Chapter V: The End`
   - `第12章`, `第九十八章 标题`
   - `12.`, `12:`, `#12`

2. **Unwrap JSON** translation artifacts automatically

3. **Split glued headers** like `Chương 3: Chạy trốnNàng vội...`
   → Header: `Chương 3: Chạy trốn`
   → Body: `Nàng vội vàng bỏ đi.`

4. **Remove duplicates** (keeps Vietnamese over Chinese, longer over shorter)

5. **Normalize spacing** and enforce sentence endings

**Output:** List of normalized chapters with diagnostics

## Stage 2: Chinese Review

### Scanning Chinese Text

Click **"🔍 Scan Chinese"** to:
- Find all Chinese characters (Han ideographs)
- Group identical phrases
- Show occurrence counts and locations
- Report total unique phrases

**Example output:**
```
Found 150 unique Chinese phrases:
• 修炼 (45x)
• 修炼者 (23x)
• 灵气 (18x)
```

### Translation Workflow

**Manual translation:**
1. Edit phrases in the table
2. Press Enter to save
3. Translations persist across sessions

**AI translation (optional):**
1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/)
2. Open Settings and enter your key
3. Click "🔄 Translate with AI"
4. Wait for batch completion
5. Review and edit results

**Priority order:**
- Manual edits (highest priority)
- AI translations
- Offline dictionary (fallback)
- Hán-Việt readings (last resort)

**Applying translations:**
Click **"🔄 Apply Translations"** to replace Chinese with Vietnamese throughout the text.

**Algorithm:** Longest phrases first, so `修炼者` (tu luyện giả) replaces before `修炼` (tu luyện).

## Stage 3: Clean & Chunk

### Text Cleaning

Removes TTS-unfriendly elements:
- Control characters
- HTML tags and entities
- Quotes and brackets (configurable)
- Symbol-to-word conversion: `&` → "và", `%` → "phần trăm"

### Chunking

Click **"🧹 Clean & Chunk"** to split chapters into TTS-ready chunks.

**Default limit:** 3000 characters per chunk

**Break preference:**
1. Paragraph boundaries (`\n\n`)
2. Sentence endings (`.!?。！？`)
3. Clause boundaries (`,;:，；：`)
4. Word boundaries (spaces)
5. Hard slice (only when unavoidable, flagged with warning)

**Guarantees:**
- Never splits across chapter boundaries
- Warns when hard slicing is required

**Example output:**
```
Created 45 chunks:
• Ch 1 part 1/3: 2850 chars
• Ch 1 part 2/3: 2920 chars
• Ch 1 part 3/3: 1200 chars
```

## Stage 4: Filter & Export

### Filtering by Range

**Range syntax:**
```
1-20          → Chapters 1 through 20
25            → Just chapter 25
30-40, 45, 50 → Multiple ranges
```

**Quick blocks:**
- 10 chapters: Generates 1-10, 11-20, 21-30...
- 20 chapters: Generates 1-20, 21-40, 41-60...
- etc.

### Export Formats

**JSON export:**
```json
{
  "chunks": [...],
  "chapters": [...],
  "summary": {...}
}
```

**TXT export:**
```
=== Chương 1: Khởi đầu ===

Text of chunk 1...

Text of chunk 2...

=== Chương 2: Tiếp tục ===
...
```

**ZIP batch export:**
- Multiple ranges in one archive
- Includes manifest.json
- One file or folder per range

## Common Workflows

### Basic Novel Processing

```
1. Load TXT files
2. Normalize chapters
3. Clean & chunk
4. Export JSON
```

### Chinese to Vietnamese Translation

```
1. Load TXT files
2. Normalize chapters
3. Scan Chinese
4. Translate (manual or AI)
5. Apply translations
6. Clean & chunk
7. Export
```

### TTS Preparation

```
1. Load pre-translated text
2. Normalize chapters
3. Clean & chunk (with TTS settings)
4. Filter to desired range
5. Export TXT for TTS engine
```

## Settings

Settings are auto-saved to:
- Linux/macOS: `~/.config/novel-pipeline-v2/config.json`
- Windows: `%APPDATA%\novel-pipeline-v2\config.json`

**Key settings:**
- Chapter prefix format: `Chương {n}`, `Chapter {n}`, etc.
- Maximum chunk size: 50-20000 characters
- Encoding chain: Order of encoding attempts
- TTS cleaning rules: What to remove/convert
- AI translation: Model, batch size, timeout

## Diagnostics

The bottom status panel shows:
- Stage completion status
- Warnings (missing chapters, duplicates)
- Errors (encoding issues, parse failures)
- Info (chapters detected, chunks created)

**Example:**
```
✓ Loaded 3 sources
✓ Detected 50 chapters
⚠ Chương 12 bị trùng 2 bản; đã loại 3500 ký tự
✓ Created 180 chunks
```

## Tips

### Best Practices

1. **Load files in order** - Use natural naming (ch001, ch002) for auto-sort

2. **Check diagnostics** - Review warnings before exporting

3. **Save often** - Settings auto-save, but translations are in-memory until you export

4. **Test chunks** - Export a small range first to verify formatting

5. **Backup translations** - The translation table is saved separately

### Performance

- **Large files:** The app handles 1000+ chapters without issues
- **AI translation:** Batches of 40 phrases take ~10-30 seconds
- **Chunking:** Near-instant for typical novels (50-200 chapters)

### Troubleshooting

**"No chapters detected"**
- Check if text has chapter headers
- Try custom regex in settings
- Enable auto-insert headers for headerless files

**"Encoding errors"**
- Try different encodings in settings
- Check BOM markers
- Re-save source files as UTF-8

**"Hard split warnings"**
- Increase chunk size limit
- Check for very long sentences
- Review those chunks manually

**"Chinese not detected"**
- Verify text actually contains Han characters
- Check encoding (must decode correctly)
- Look at the Unicode ranges in source

## Keyboard Shortcuts

- `Ctrl+O` - Load files (planned)
- `Ctrl+S` - Save settings (planned)
- `Ctrl+E` - Export (planned)
- `Ctrl+Q` - Quit (planned)

## Advanced Features

### Custom Chapter Regex

Define your own chapter pattern:
```regex
^(?P<number>\d+)\s*[-–]\s*(?P<title>.*)$
```

**Requirements:**
- Must have `(?P<number>...)` group
- Number can be Arabic or Chinese numerals

### Custom Cleaning Rules

Add replacement patterns in settings:
```json
{
  "pattern": "\\[.*?\\]",
  "replacement": "",
  "regex": true
}
```

### Translation Priority

The app uses a strict priority order:
1. Manual edits (you typed it)
2. AI translations (if enabled)
3. Dictionary terms (common phrases)
4. Hán-Việt readings (single characters)
5. Leave unchanged (if nothing else works)

## Data Safety

**What's persistent:**
- Settings (`config.json`)
- Translation table (`translations.json`)

**What's temporary:**
- Loaded text (in-memory only)
- Normalized chapters (until exported)
- Chunks (until exported)

**What's never lost:**
- Source files (never modified)
- Manual translations (auto-saved)
- Export history (files on disk)

**No data loss guarantee:**
- Vietnamese text never treated as artifact
- Duplicate removal reports what was discarded
- Text cleaning shows before/after counts
- Hard splits are flagged for review

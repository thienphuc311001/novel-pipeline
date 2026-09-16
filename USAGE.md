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
   - Tab 4: Generate thumbnail and audiobook
   - Tab 5: Create the final MP4

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

**Default limit:** 1200 characters per chunk

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

## Stage 4: Thumbnail & Audiobook

Step 4 uses only the TXT/JSON bundle created by Step 3. It displays the first
chapter, creates a 1280×720 YouTube thumbnail from one selected image, and
generates/resumes a Vietnamese Edge-TTS audiobook. Output is saved directly in
the Step 3 title/chapter job folder. FFmpeg must be installed to combine MP3
chunks into the final audiobook.

Unless **Output folder override** is set in Settings, the Step 3 job folder is
created beside the first TXT/ZIP selected in Step 1. Steps 4 and 5 continue to
use that same folder.

## Stage 5: Create Video

Step 5 automatically uses the current Step 4 thumbnail and audiobook. It
detects the installed GPU, drivers, FFmpeg hardware backends, and H.264
encoders, then performs a real short encode before selecting an encoder. A
failed hardware encoder falls back to another verified option and finally to
`libx264`.

Click **Create Video** to produce a 1920×1080 H.264 MP4. The image is preserved
without stretching, FFmpeg progress and speed remain visible, and **Cancel**
stops only the partial render. The completed file is saved automatically as
`<title>_<chapter>.mp4` in the current job folder.

## Common Workflows

### Basic Novel Processing

```
1. Load TXT files
2. Normalize chapters
3. Complete Chinese review
4. Clean & chunk to create TXT/JSON
5. Generate thumbnail and/or audiobook
6. Create MP4 video
```

### Chinese to Vietnamese Translation

```
1. Load TXT files
2. Normalize chapters
3. Scan Chinese
4. Translate (manual or AI)
5. Apply translations
6. Clean & chunk to create TXT/JSON
7. Generate thumbnail and/or audiobook
8. Create MP4 video
```

### TTS Preparation

```
1. Load pre-translated text
2. Normalize chapters
3. Confirm Step 2 has no Chinese residue
4. Clean & chunk (with TTS settings)
5. Generate/resume the Edge-TTS audiobook
6. Create the final MP4
```

## Settings

Settings are auto-saved to:
- Linux/macOS: `~/.config/novel-pipeline-v2/config.json`
- Windows: `%APPDATA%\novel-pipeline-v2\config.json`

**Key settings:**
- Chapter prefix format: `Chương {n}`, `Chapter {n}`, etc.
- Maximum chunk size: defaults to 1200 characters
- Encoding chain: Order of encoding attempts
- TTS cleaning rules: What to remove/convert
- Edge-TTS: voice, concurrency, timeout, and retry counts
- Output folder override: leave blank to save beside the Step 1 input

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

## Step 6: YouTube Upload

Create the Step 5 video, then click **Continue to Step 6** (direct tab selection uses the same validation). The current MP4 and Step 4 thumbnail appear automatically. Step 6 never selects a separate video or renders another MP4.

Choose the downloaded Google **Desktop app** OAuth client JSON in **Settings → YouTube** once; see [installation setup](INSTALL.md#optional-youtube-desktop-oauth). Click **Connect YouTube Account** and authorize in your system browser. The panel shows the connected email and channel. **Disconnect** removes the local saved credentials; it does not remove previously uploaded videos or job records.

Review the default `Novel Title | Chapter` title, description, comma-separated tags, category, Private/Unlisted/Public visibility, made-for-kids setting, and optional playlist. Scheduled publication requires **Private** and a future publishing time. Enter the time in your local time zone; the API receives UTC. The app validates metadata before starting network upload.

Click **Upload to YouTube**. Progress shows bytes transferred, percentage, and upload speed. Temporary upload failures use bounded backoff and query the server's received position before retransmission. **Cancel** stops at the next safe request boundary, retaining resumable recovery data. The current HTTP request has a bounded timeout. Upstream controls are disabled while an operation runs to preserve its inputs.

`youtube_upload.json` persists video ID/URL, metadata, byte position, and independent video/thumbnail/playlist outcomes. Resumable URLs and OAuth tokens remain in the OS credential store. **Resume Upload** queries that existing session rather than creating a new video. Resume uses the metadata originally sent; edit metadata for a new upload only. If a session expires or completion cannot be confirmed, the app stops. Check YouTube Studio to establish the previous outcome before explicitly using **Upload Again**. It never automatically creates another upload from an uncertain state.

After video upload, thumbnail and optional playlist operations run separately. A failure preserves the video ID. Use **Retry Thumbnail** or **Retry Playlist**; these controls do not upload the video again. An uncertain playlist insert is checked for existing membership before another insertion. An explicit retry rechecks after bounded delays and inserts only if the video remains absent; it does not automatically repeat an uncertain playlist write. If YouTube cannot confirm membership, check the playlist and retry later.

A completed job shows **This job has already been uploaded**, its ID, URL, actual visibility, thumbnail status, and playlist status. **Open YouTube Video** opens the URL; **Copy URL** copies it. **Upload Again** requires a separate explicit confirmation. Keep `youtube_upload.json` and the secure credential store for recovery; corrupt/missing session records cannot silently start another copy.

Upload preparation exposes this layout without renaming the app's existing artifacts:

```text
<title>_<chapter>/
    final.txt
    final.json
    thumbnail.jpg
    audiobook.mp3
    <title>_<chapter>.mp4
    youtube_upload.json
```

The four convenience filenames use hard links when supported, so large MP3s do not require another copy. Other filesystems use cancellable atomic copies. Existing job-derived names and the audio-chunk resume directory remain available.

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

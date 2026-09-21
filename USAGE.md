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
   - Tab 2: Detect chapters and group
   - Tab 3: Generate thumbnail and audiobook
   - Tab 4: Create the final MP4
   - Tab 5: Upload to YouTube

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

2. **Unwrap JSON** artifacts automatically

3. **Split glued headers** like `Chương 3: Chạy trốnNàng vội...`
   → Header: `Chương 3: Chạy trốn`
   → Body: `Nàng vội vàng bỏ đi.`

4. **Remove duplicates** (keeps Vietnamese over Chinese, longer over shorter)

5. **Normalize spacing** and enforce sentence endings

**Output:** List of normalized chapters with diagnostics

## Stage 2: Detect Chapters & Group

After Step 1, the grouping stage consumes the normalized text directly. Chinese
content is preserved as-is; there is no Chinese residue scan, dictionary review,
or translation gate. Chinese chapter headers and numerals remain supported when
recognizing chapter structure. If Step 1 has not run successfully, grouping
uses the original loaded text as the documented fallback.

Enter/select a saved novel title. Step 2 displays the
detected count and exact first/last headings. Choose **10**, **20** (default),
**25**, **50**, or **Custom** chapters per group; the full preview updates
automatically. Numbering gaps, repeats, and resets are reported but not changed.
`Quyển` headings count as flat entries, not a volume hierarchy.

If detected headings are fewer than the numeric range because chapter numbers
are missing, Step 2 does not group by heading count. It previews numeric ranges
and asks for confirmation before using them. Missing headings inside a range
(including an end number) are allowed; every calculated group-start heading
must exist exactly once. A missing, duplicate, or reset boundary disables
automatic numeric grouping and requires manual review.

Click **Create Group Files**. Each group receives exact UTF-8 `final.txt` and
`final.json` under `<output-root>/<novel-title>/<novel-title>_<range>/`.
The first group retains the preamble. These files are not cleaned or TTS-chunked.
The novel folder contains `chapter_groups.json`, the source of truth for all
later stages. **Restore Matching Groups** validates that manifest against the
current grouping source text, title, grouping configuration, heading patterns and
numeric-boundary confirmation identity when applicable, and canonical files.
It never discovers/regroups files by scanning folders.

## Stage 3: Thumbnail & Audiobook

All groups appear unchecked. Highlight a group and click **Select Image for
Highlighted Group** to choose its own image and create a 1280×720 `thumbnail.jpg`
labeled with its group range (for example `Chương 1-20`). The cover stays sharp and full-bleed (never blurred or
dimmed) while the still reuses the Step 4 video-style neon frame and title/chapter
typography, with the labels in a dark band across the bottom 20%. Repeat for each
group; checklist selections control the TTS batch. Highlight a group to inspect its canonical paths, exact first
chapter, thumbnail, and failure details.

**Delete Highlighted Group** removes that job from Steps 3–5, even if its
canonical files are missing or modified. Deletions persist in the manifest
and remain excluded when restoring matching groups. Existing files are kept;
**Create Group Files** in Step 2 recreates the full group list. A damaged job
reports the affected file and fails independently while other batch jobs continue.

**Start TTS** processes groups sequentially. Inside each group, Step 3 cleans a
working copy and creates chapter-safe 700-character chunks in `tts_chunks.json`.
`final.txt`/`final.json` remain unchanged. Numbered audio and the resume manifest
live in `audio_chunks/`; the final file is `<group-name>_audiobook.mp3`.
Current-group and overall progress stay visible. **Cancel** stops queued groups
and retains completed chunks.

An incomplete group does not automatically publish a partial MP3; the batch
continues. Use **View Failed Chunks**, **Retry Failed Chunks**, **Resume TTS**, or
**Edit Text and Retry** on the highlighted group. Editing affects only one
failed chunk, is non-empty and bounded by the chunk limit, and persists in
`tts_overrides.json`. Unchanged valid audio is reused. **Merge with Missing
Chunks** requires explicit confirmation and valid existing audio; excluded
numbers are recorded and the result is labeled partial.

The Step 2 job folder is always created beside the first TXT/ZIP selected in
Step 1; generated files never use a temporary folder. Steps 3–5 continue to
use that same folder.

## Stage 4: Create Video

Step 4 automatically uses the current Step 3 thumbnail and audiobook. It
detects the installed GPU, drivers, FFmpeg hardware backends, and H.264
encoders, then performs a real short encode before selecting an encoder. A
failed hardware encoder falls back to another verified option and finally to
`libx264`.

Select groups and click **Create Videos** to produce one 1920×1080 H.264 MP4
per group sequentially. Every page names only the chapter it narrates (for
example `Chương 7`) instead of the whole group range; the Step 3 thumbnail keeps
the group range. Valid current videos are verified and skipped. The image is preserved
without stretching, FFmpeg progress and speed remain visible, and **Cancel**
stops only the partial render. The completed file is saved automatically as
`<title>_<chapter>.mp4` in the current job folder.

## Stage 5: YouTube Upload

Create the Step 4 video, then click **Continue to Step 5**. The current MP4 and
Step 3 thumbnail appear automatically. Step 5 never selects a separate video or
renders another MP4.

Choose the downloaded Google **Desktop app** OAuth client JSON in **Settings → YouTube** once; see [installation setup](INSTALL.md#optional-youtube-desktop-oauth). Click **Connect YouTube Account** and authorize in your system browser. The panel shows the connected email and channel. **Disconnect** removes the local saved credentials; it does not remove previously uploaded videos or job records.

Review the default `Novel Title | Chapter` title, description, comma-separated tags, category, Private/Unlisted/Public visibility, made-for-kids setting, and optional playlist. Scheduled publication requires **Private** and a future publishing time. Enter the time in your local time zone; the API receives UTC. The app validates metadata before starting network upload.

All group checkboxes start unchecked. Select groups and click **Start Uploads**. Uploads run sequentially with current-group and overall progress. Authentication failures pause the batch for reconnect; **Cancel** stops queued groups at a safe boundary.

`youtube_upload.json` persists video ID/URL, metadata, byte position, and independent video/thumbnail/playlist outcomes. Resumable URLs and OAuth tokens remain in the OS credential store. **Resume Upload** queries an existing session rather than creating a new video; uncertain uploads never automatically create duplicates.

## Common Workflows

### Basic Novel Processing

```
1. Load TXT files
2. Normalize chapters
3. Detect/group chapters to create canonical TXT/JSON
4. Generate thumbnail and/or audiobook
5. Create MP4 video
6. Upload selected videos to YouTube
```

### Text containing Chinese content

```
1. Load TXT files
2. Normalize chapters
3. Detect/group chapters directly; Chinese text is preserved
4. Generate thumbnail and/or audiobook
5. Create MP4 video
```

### TTS Preparation

```
1. Load pre-translated text
2. Normalize chapters
3. Create chapter groups, then clean/chunk each selected group in Step 3
4. Generate/resume the Edge-TTS audiobook
5. Create the final MP4
```

## Settings

Settings are auto-saved to:
- Linux/macOS: `~/.config/novel-pipeline-v2/config.json`
- Windows: `%APPDATA%\novel-pipeline-v2\config.json`

**Key settings:**
- Chapter prefix format: `Chương {n}`, `Chapter {n}`, etc.
- TTS chunk target: 700 characters
- Encoding chain: Order of encoding attempts
- TTS cleaning rules: What to remove/convert
- Edge-TTS: voice, concurrency, timeout, and retry counts
- Job location: always beside the Step 1 input file (not configurable)

## Diagnostics

**📋 Log** in the toolbar (or `Ctrl+L`) opens the shared log window:
- Stage completion status
- Warnings (missing chapters, duplicates)
- Errors (encoding issues, parse failures)
- Info (chapters detected, chunks created)

The window is modeless and shared by all five steps: it keeps every line when
you close it, reopen it, or switch steps, and it never blocks or interrupts a
running job. `Auto-scroll` follows new lines, `Clear` empties the buffer, and
the retained line count follows **Max log lines** in Settings.

Read-only generated text panels, previews, group details, failure dialogs,
YouTube results, and the shared log window include **Copy all**. The action
copies the complete plain text with its original line breaks; editable title,
description, JSON, and TTS fields remain ordinary editors.

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

3. **Save often** - Settings auto-save; generated output remains available in the job folder

4. **Test chunks** - Export a small range first to verify formatting

5. **Backup job folders** - Canonical TXT/JSON, audio, video, and upload records are kept separately

### Performance

- **Large files:** The app handles 1000+ chapters without issues
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

**"Chinese chapter headers are not recognized"**
- Check the decoded text and encoding
- Verify the header pattern or Chinese numeral is supported by chapter settings
- Use the Step 2 preview diagnostics to inspect missing or ambiguous boundaries

Each grouped job has this layout:

```text
<title>_<chapter>/
    final.txt
    final.json
    thumbnail.jpg
    tts_chunks.json
    <title>_<chapter>_audiobook.mp3
    audio_chunks/
    job_state.json
    <title>_<chapter>.mp4
    youtube_upload.json
```

Legacy single-job files remain untouched; they are not automatically migrated
or deleted. Grouped jobs are restored only from a matching chapter manifest.

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

## Data Safety

**What's persistent:**
- Settings (`config.json`)
- Job artifacts and manifests in the input folder beside the loaded TXT/ZIP

**What's temporary:**
- Loaded text (in-memory only)
- Normalized chapters (until exported)
- Chunks (until exported)

**What's never lost:**
- Source files (never modified)
- Canonical group files and export history (files on disk)

**No data loss guarantee:**
- Vietnamese text never treated as artifact
- Duplicate removal reports what was discarded
- Text cleaning shows before/after counts
- Hard splits are flagged for review

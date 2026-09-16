# Novel Pipeline v2

A standalone local Python desktop application that merges three novel-processing tools into one unified pipeline.

## Purpose

Process raw Chinese/Vietnamese web-novel files into clean, reviewable, chunked output suitable for reading and text-to-speech. Intended for translators, editors, and audiobook/TTS producers.

## Features

### Complete Workflow

```
Raw TXT / ZIP
  → Extract / Merge
  → Chapter Normalize
  → Detect & Remove Duplicate Chapters
  → Review Remaining Chinese
  → Translate Chinese (optional AI)
  → Detect chapters / preview consecutive chapter groups
  → Create exact TXT / JSON files per group
  → Clean and TTS-chunk each selected group independently
  → Generate group thumbnails / sequential resumable audiobooks
  → Sequential hardware-accelerated MP4 batch
  → Sequential YouTube uploads with per-group recovery
```

### Stage 1: Chapter Normalization

- **JSON artifact unwrapping** - Detects and unwraps translation JSON structures
- **Escaped newline restoration** - Converts literal `\n` to real line breaks
- **Multilingual chapter detection** - Vietnamese, English, Chinese, plain numbered formats
- **Chinese numeral conversion** - Supports full range (零一二两...千万亿)
- **Glued header splitting** - Separates headers from narrative when no line break
- **Duplicate chapter detection** - Vietnamese over Chinese, longer over shorter
- **Automatic period enforcement** - Adds periods to prose lines missing punctuation
- **Spacing normalization** - Collapses repeated spaces, fixes punctuation spacing
- **Encoding detection** - UTF-8/16/32 BOM, cp1258 (Vietnamese), cp1252, latin-1

### Stage 2: Chinese Review & Translation

- **Han character detection** - Full Unicode range including extensions
- **Phrase grouping** - Deduplicates identical phrases with occurrence counts
- **Source tracking** - Shows file/line/chapter location for each phrase
- **Offline dictionary** - Bundled Sino-Vietnamese readings + common web-novel terms
- **Manual translation** - User edits persist across sessions
- **Optional AI translation** - Google Gemini (requires API key, fully optional)
- **Longest-first replacement** - Prevents substring corruption (修炼者 before 修炼)

### Stage 3: Detect Chapters & Group

- Detects configured headings losslessly, including Chương, Chuong, Chapter, Hồi, and Quyển.
- Shows count, exact first/last headings, numbering gaps/repetitions/resets, and all group ranges.
- Groups consecutive entries by 10, 20 (default), 25, 50, or a custom count; never sorts/renumbers.
- When missing numbers make heading-count groups unsafe, offers confirmed numeric ranges and splits only at verified group-start headings.
- Saves `final.txt` and `final.json` per group plus a validated `chapter_groups.json` manifest.
- Concatenating group TXT files exactly reproduces confirmed Step 2 text, including the preamble and original line endings.
- Does **not** clean text or create TTS chunks. Title history remains available.

### Stage 4: Thumbnail & Audiobook

- Unchecked group checklists, shared cover image, per-group `thumbnail.jpg`, and exact first-chapter preview.
- Cleans only a TTS working copy, then writes separate ordered `tts_chunks.json` plans (1200-character default).
- Sequential groups with existing bounded concurrency, retries, fallback splitting, and resume inside each group.
- Incomplete groups retain detailed failures and successful audio; later groups continue.
- Failed-chunk editing persists separate overrides. Partial merge requires explicit approval.
- Visible current-group/overall progress; Cancel preserves completed files and stops queued groups.

### Stage 5: Create Video

- **Automatic inputs** - Uses the current Step 4 thumbnail and audiobook without another upload
- **Verified acceleration** - Detects the GPU and performs a real test encode before selecting VA-API, Quick Sync, NVENC, AMF, or VideoToolbox
- **Reliable fallback** - Retries with the next verified encoder and always keeps `libx264` as the CPU fallback
- **YouTube-ready MP4** - Creates a 1920×1080 H.264 video with live progress and clean cancellation
- **Input-relative jobs** - By default the job folder is created beside the first Step 1 input; Settings can override the output root
- **Sequential groups** - Select a subset; validated current MP4s are skipped, failures remain isolated.

### Stage 6: YouTube Upload

- Uses the current Step 5 MP4 and Step 4 thumbnail automatically.
- Connects through the system browser; credentials and resumable session URLs live in the OS credential store.
- Reviews editable title, description, tags, category, visibility, made-for-kids, playlist, and optional publication time.
- Shows transferred bytes, percentage, and speed, with bounded retries and saved-session recovery.
- Stores `youtube_upload.json` in the job folder; another video upload requires explicit action.
- Retries thumbnail and playlist failures independently using the saved video ID.
- Uploads selected groups sequentially; completed uploads are skipped and authentication failures pause for reconnect.
- Shared metadata and individual titles; started sessions use frozen metadata, with a separate post-upload metadata editor.
- Every group retains its own `youtube_upload.json`; uncertain uploads never automatically create another video.

See [YouTube setup and recovery](USAGE.md#step-6-youtube-upload) before first use.

## Installation

### Requirements

- Python 3.11+
- PyQt6
- FFmpeg and FFprobe (for joining MP3 chunks and creating/validating video)

### Setup

```bash
# System packages (Arch Linux example)
sudo pacman -S python-pyqt6

# Or via pip
pip install -r requirements.txt

# Clone and run
git clone <repo>
cd novel-pipeline-v2
python app.py
```

## Usage

### Quick Start

1. **Load Files** - Select TXT or ZIP files
2. **Normalize Chapters** - Detect and clean chapter structure
3. **Scan Chinese** (optional) - Find remaining Chinese text
4. **Detect Chapters & Group** - Choose a chapter count and create exact group files
5. **Generate media** - Select groups, choose a shared cover, and start TTS
6. **Create Videos** - Render selected groups, automatically skipping valid completed MP4s
7. **Start Uploads** - Connect your channel, review shared metadata/per-group titles, and upload selected groups

### Configuration

Settings are stored in `~/.config/novel-pipeline-v2/config.json` (or `XDG_CONFIG_HOME`).

Manual translations are stored in `~/.config/novel-pipeline-v2/translations.json`.

### AI Translation (Optional)

To enable Gemini translation:

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/)
2. Open Settings and enter your API key
3. The app works fully offline without this; AI is only for batch translation

## Project Structure

```
novel-pipeline-v2/
├── app.py                      # Entry point
├── config/
│   └── settings.py             # Settings and configuration
├── pipeline/
│   ├── document.py             # In-memory pipeline document
│   └── loader.py               # TXT/ZIP input loading
├── chapters/
│   ├── numerals.py             # Chinese numeral conversion
│   ├── patterns.py             # Chapter header patterns
│   ├── detector.py             # Multilingual chapter detection
│   ├── duplicates.py           # Duplicate resolution
│   └── normalizer.py           # Chapter assembly & normalization
├── cleaning/
│   ├── encodings.py            # Encoding detection
│   ├── json_artifacts.py       # JSON unwrapping
│   └── textclean.py            # TTS cleaning rules
├── chinese/
│   ├── detector.py             # Han character detection
│   ├── grouping.py             # Phrase grouping & counting
│   ├── dictionary.py           # Offline dictionary
│   ├── replacer.py             # Longest-first phrase replacement
│   └── data/
│       ├── sino_vietnamese.tsv # Hán-Việt character readings
│       └── common_terms.tsv    # Web-novel vocabulary
├── translation/
│   ├── table.py                # Translation store (persisted)
│   ├── gemini.py               # Optional Gemini client
│   └── runner.py               # Batch translation runner
├── chunking/
│   ├── splitter.py             # Sentence-aware chunking
│   └── stats.py                # Chunk statistics
├── filtering/
│   ├── ranges.py               # Range parsing & filtering
│   └── repair.py               # Renumber & repair actions
└── ui/
    └── main_window.py          # PyQt6 main window
```

## Algorithms

### Chinese Numeral Conversion

Supports full range including 零, 两, 十百千万亿. Rejects malformed forms (一二, 十十) rather than guessing.

### Duplicate Chapter Resolution

Priority order:
1. Vietnamese text over Chinese text
2. Copy with title over copy without title
3. Longer text over shorter text
4. First occurrence on full tie

### Phrase Replacement

Applied **longest to shortest** so `修炼者` (3 chars) replaces before `修炼` (2 chars), preventing substring corruption.

### Sentence-Aware Chunking

Break preference cascade:
1. Paragraph boundaries (`\n\n`)
2. Sentence endings (`.!?。！？`)
3. Clause boundaries (`,;:，；：`)
4. Word boundaries (spaces)
5. Hard slice (only when unavoidable)

## Technology

- **Python 3.11+** - Modern Python with type hints
- **PyQt6** - Native desktop UI
- **No database** - In-memory pipeline, lightweight JSON persistence
- **No mandatory network** - Fully offline; AI translation is optional
- **Minimal dependencies** - Standard library + PyQt6

## License

See BUILD_PROMPT.md for project requirements and design decisions.

## Credits

Unifies and preserves the behavior of three existing novel-processing tools:
- Novel Chapter Auditor & Cleaner
- Chinese Character Scanner & Localization Tool  
- Text & Novel Data Processor

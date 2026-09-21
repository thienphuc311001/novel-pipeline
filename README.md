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
  → Detect chapters / preview consecutive chapter groups
  → Create exact TXT / JSON files per group
  → Clean and TTS-chunk each selected group independently
  → Generate group thumbnails / sequential resumable audiobooks
  → Sequential hardware-accelerated MP4 batch
  → Sequential YouTube uploads with per-group recovery
```

### Stage 1: Chapter Normalization

- **JSON artifact unwrapping** - Detects and unwraps structured JSON artifacts
- **Escaped newline restoration** - Converts literal `\n` to real line breaks
- **Multilingual chapter detection** - Vietnamese, English, Chinese, plain numbered formats
- **Chinese numeral conversion** - Supports full range (零一二两...千万亿)
- **Glued header splitting** - Separates headers from narrative when no line break
- **Duplicate chapter detection** - Vietnamese over Chinese, longer over shorter
- **Automatic period enforcement** - Adds periods to prose lines missing punctuation
- **Spacing normalization** - Collapses repeated spaces, fixes punctuation spacing
- **Encoding detection** - UTF-8/16/32 BOM, cp1258 (Vietnamese), cp1252, latin-1

### Stage 2: Detect Chapters & Group

- Detects configured headings losslessly, including Chương, Chuong, Chapter, Hồi, and Quyển.
- Shows count, exact first/last headings, numbering gaps/repetitions/resets, and all group ranges.
- Groups consecutive entries by 10, 20 (default), 25, 50, or a custom count; never sorts/renumbers.
- When missing numbers make heading-count groups unsafe, offers confirmed numeric ranges and splits only at verified group-start headings.
- Saves `final.txt` and `final.json` per group plus a validated `chapter_groups.json` manifest.
- Concatenating group TXT files exactly reproduces the current Step 2 source text, including the preamble and original line endings.
- Does **not** clean text or create TTS chunks. Title history remains available.

### Stage 3: Thumbnail & Audiobook

- Unchecked TTS checklists; select an individual image for the highlighted group's `thumbnail.jpg` and exact first-chapter preview. The 1280×720 still reuses the video page's neon frame, panel palette, and title/chapter typography over an unblurred, full-bleed cover, with the labels in a dark band across the bottom 20%; it keeps the group range (for example `Chương 1-20`) while video pages name only their own chapter.
- Delete any highlighted group from Steps 3–5, including missing/modified jobs; the manifest remembers deletions and existing files remain available.
- Cleans only a TTS working copy, then writes separate ordered `tts_chunks.json` plans (700-character target, including existing jobs).
- Sequential groups with existing bounded concurrency, full-chunk retries and fingerprinted resume inside each group.
- Incomplete groups retain detailed failures and successful audio; later groups continue.
- Exact effective text and MP3 hashes live in `audio_chunks/manifest.json`; final merges record their ordered inputs. The merge rebuilds continuous decoded audio timestamps to prevent MP3 padding from shifting page timing.
- Group outputs include `final.txt`, `final.json`, `thumbnail.jpg`, `audio_chunks/`, `audiobook.mp3`, `render_pages/`, `video_timeline.json`, and `<title>_<chapter>.mp4`.
- Failed-chunk editing persists separate overrides. Partial merge requires explicit approval.
- Visible current-group/overall progress; Cancel preserves completed files and stops queued groups.

### Stage 4: Create Video

- **Automatic inputs** - Uses the current Step 3 thumbnail and audiobook without another upload
- **Verified acceleration** - Detects the GPU and performs a real test encode before selecting VA-API, Quick Sync, NVENC, AMF, or VideoToolbox
- **Reliable fallback** - Retries with the next verified encoder and always keeps `libx264` as the CPU fallback
- **Exact text pages** - One 1920×1080 minimal neon-theater page per TTS chunk, with a centered 80% frame over the blurred thumbnail. Only the title, that page's own chapter label (for example `Chương 7`, never the whole group range), divider, and exact spoken text appear.
- **Measured VFR timing** - FFprobe reads each MP3 duration; cached pages form a static-duration timeline muxed with the final audiobook. Partial audiobooks are blocked and unreadable overflow reports the affected chunk.
- **YouTube-ready MP4** - Creates H.264 video with live progress, VFR timing validation, and clean cancellation
- **Input-relative jobs** - The job folder is always created beside the first Step 1 input; there is no output-folder override, so generated files never use a temporary folder
- **Sequential groups** - Select a subset; validated current MP4s are skipped, failures remain isolated.

### Stage 5: YouTube Upload

- Uses the current Step 4 MP4 and Step 3 thumbnail automatically.
- Connects through the system browser; credentials and resumable session URLs live in the OS credential store.
- Reviews editable title, description, tags, category, visibility, made-for-kids, playlist, and optional publication time.
- Shows transferred bytes, percentage, and speed, with bounded retries and saved-session recovery.
- Stores `youtube_upload.json` in the job folder; another video upload requires explicit action.
- Retries thumbnail and playlist failures independently using the saved video ID.
- Uploads selected groups sequentially; completed uploads are skipped and authentication failures pause for reconnect.
- Shared metadata and individual titles; started sessions use frozen metadata, with a separate post-upload metadata editor.
- Every group retains its own `youtube_upload.json`; uncertain uploads never automatically create another video.

See [YouTube setup and recovery](USAGE.md#step-5-youtube-upload) before first use.

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
3. **Detect Chapters & Group** - Choose a chapter count and create exact group files
4. **Generate media** - Select groups, choose a shared cover, and start TTS
5. **Create Videos** - Render selected groups, automatically skipping valid completed MP4s
6. **Start Uploads** - Connect your channel, review shared metadata/per-group titles, and upload selected groups

### Configuration

Settings are stored in `~/.config/novel-pipeline-v2/config.json` (or `XDG_CONFIG_HOME`).

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
- **No mandatory network** - Core processing is fully offline
- **Minimal dependencies** - Standard library + PyQt6

## License

See BUILD_PROMPT.md for project requirements and design decisions.

## Credits

Unifies and preserves the behavior of three existing novel-processing tools:
- Novel Chapter Auditor & Cleaner
- Text & Novel Data Processor

## TTS text preprocessing

Audiobook preparation now runs **safe clean → deterministic TTS sanitization → sentence-aware chunking → Edge TTS**. Original TXT and canonical chapter-group files are preserved. The TTS profile keeps quotes, brackets, numbers and symbols instead of applying the older global symbol-to-word map.

Settings → **TTS & UI** exposes preprocessing enablement, URL/email policy, decorative emoji removal and one-sentence-per-line. Advanced JSON supports abbreviation lists and explicit boilerplate/footnote patterns. URL policy defaults to `remove`; email defaults to `keep`. CJK, encoding damage and replacement characters are diagnosed, not guessed or translated. Chinese chapter headers and numerals remain supported as structural input.

Preprocessing runs before chunking, including failed-chunk replacement preparation. Plans include versions/configuration so stale text plans are rebuilt; audio resumes only when chunk text and voice match. Changed plans retain old override files and report that they were not applied. Large legacy inputs and grouped TTS preparation run on workers with cancellation.

See [implementation plan](TTS_PREPROCESSING_PLAN.md) and [validation report](TTS_PREPROCESSING_REPORT.md). Offline benchmark:

```bash
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 10
```

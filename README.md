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
  → Clean Text for TTS
  → Detect Chapters
  → Chunk Text
  → Select Chapter Ranges
  → Export TXT / JSON / ZIP
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

### Stage 3: Text Cleaning & Chunking

- **TTS cleaning** - Removes control chars, HTML, configurable quotes/brackets
- **Symbol-to-word conversion** - `&` → "và", `%` → "phần trăm"
- **Custom replacement rules** - User-defined patterns
- **Chapter-safe chunking** - Never splits across chapter boundaries
- **Sentence-aware splitting** - Break preference: paragraph → sentence → clause → space
- **Hard-split warnings** - Flags chunks where natural breaks weren't possible

### Stage 4: Chapter Range Filtering & Export

- **Range syntax** - `1-20, 25, 30-40` (comma-separated, inclusive)
- **Quick blocks** - Generate 10/20/25/50/100 chapter blocks automatically
- **Sequential renumbering** - Repair action for out-of-order chapters
- **JSON export** - Structured output with metadata
- **TXT export** - Plain text with configurable headers
- **ZIP batch export** - Multiple ranges in one archive

## Installation

### Requirements

- Python 3.11+
- PyQt6

### Setup

```bash
# System packages (Arch Linux example)
sudo pacman -S python-pyqt6

# Or via pip
pip install PyQt6

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
4. **Clean & Chunk** - Split into TTS-ready chunks
5. **Export** - Save as JSON/TXT

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

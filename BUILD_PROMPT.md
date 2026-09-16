Build a standalone local Python desktop application that merges three existing novel-processing tools into ONE unified application:

1. Novel Chapter Auditor & Cleaner
2. Chinese Character Scanner & Localization Tool
3. Text & Novel Data Processor

This is a native offline desktop application. Do not build a web application. Do not use React, Next.js, Node.js, browsers, cloud services, databases, or microservices. Do not reproduce three separate UIs side by side. Consolidate overlapping features instead of placing three apps next to each other.

## APPLICATION PURPOSE

The application processes raw Chinese/Vietnamese web-novel files into clean, reviewable, chunked output suitable for reading and text-to-speech. Intended users are translators, editors, and audiobook/TTS producers working with scraped or machine-translated novels.

Complete workflow:

Raw TXT / ZIP
-> Extract / Merge
-> Chapter Normalize
-> Detect & Remove Duplicate Chapters
-> Review Remaining Chinese
-> Translate Chinese if needed
-> Clean Text for TTS
-> Detect Chapters
-> Chunk Text
-> Select Chapter Ranges
-> Export TXT / JSON / ZIP

## TECHNOLOGY

- Python 3.11+, PySide6 preferred (PyQt6 acceptable).
- Single main window, pipeline-oriented.
- All processing in Python; local filesystem for TXT/JSON/ZIP; in-memory stage-to-stage data flow; lightweight local config for preferences.
- No database unless genuinely unavoidable.
- Optional Google Gemini API only for AI translation, behind a simple service interface. Optional local TTS/pronunciation preview where available.
- The core application must work fully offline.

## SHARED DATA MODEL

Define a small in-memory pipeline document:

- `source_bytes`, `source_path`, `source_encoding`, `entry_names`
- `text` (current working text)
- `chapters: list of {number, header_line, title, text, char_count, source_line}`
- `chunks: list of {chapter, index, order, char_count, text}`
- `translations: map of Chinese phrase -> Vietnamese`
- `diagnostics: list of {code, severity, chapter, line, message, detail, snippet}`
- `stage_status` for each of the five stages

Each stage receives this document and returns a new document. Stages must be runnable individually and as a chain. Intermediate results stay in memory: never require the user to save and reload temporary files to continue the pipeline. Keep an explicit "run whole pipeline" action.

## STEP 1 - CHAPTER FILTER & NORMALIZATION

Preserve all important behavior of the existing chapter-cleaning tool:

- JSON translation-artifact unwrapping: detect JSON-shaped input where chapter text is nested inside translation objects/fields, and unwrap it to plain chapter text.
- Escaped newline restoration (`\n`, `\r\n` literals become real line breaks) before chapter detection.
- Chinese chapter detection, including numeral headers such as 第九十八章.
- Chinese numeral conversion supporting 零一二两三四五六七八九十百千万亿, plus Arabic digits as pass-through; reject malformed forms (一二, 十十, 零 after a bare digit) rather than guessing.
- Vietnamese chapter detection (Chương N and equivalents), English (Chapter N) and plain numbered (N., N:, N-, #N) formats.
- Chapter header normalization to one canonical form with a configurable prefix and zero-padded numbering.
- Glued chapter/dialogue separation: when a header is immediately followed by narrative or dialogue with no line break, split the header from the body instead of discarding it.
- Duplicate chapter detection, with duplicate resolution rules: Vietnamese over Chinese, title over text, longer text over shorter text; report what was discarded and why.
- Vietnamese-over-Chinese priority and title/text priority and longer-text priority applied consistently.
- Chapter numbering and sequence diagnostics: first/last number, gaps, out-of-order entries, repeated numbers.
- Missing chapter detection with the explicit list of missing numbers.
- Automatic period enforcement at end of prose lines that lack terminal punctuation.
- Spacing normalization: collapse repeated spaces, fix space-before-punctuation, trim line edges, collapse 3+ blank lines to a paragraph break.
- Preservation of Vietnamese sentences and dialogue: never treat Vietnamese narrative as an artifact.
- Encoding handling: UTF-8, UTF-8 BOM, UTF-16 LE/BE BOM, UTF-32 BOM, cp1258 and cp1252 fallback; report which encoding was used; never mangle Vietnamese diacritics.
- Cleaning chapter headers must strip only header artifacts. Never remove narrative text, dialogue, or paragraphs anywhere in a chapter body. Report per-chapter text loss (before/after char counts) so any accidental loss is visible.

## STEP 2 - CHINESE REVIEW & TRANSLATION

Preserve the important functionality of the Chinese scanning/localization tool:

- Input from JSON and TXT, with automatic format detection.
- Chinese character detection (Han ideographs, including extension ranges).
- Extraction mode choice: Chinese segments only, or the full containing string/line; scanning applies to both JSON values and JSON keys.
- Duplicate Chinese phrase grouping with occurrence counts and source locations (file, JSON path or line number, chapter).
- Searchable translation table: filter by phrase, sort by count or alphabetically, jump to source location.
- Manual translation editing in the table, with persistence of user edits across reruns.
- Offline dictionary fallback: use a bundled/local Chinese-to-Vietnamese dictionary (Sino-Vietnamese reading plus common-term map) when no manual or AI translation exists.
- Chinese-to-Vietnamese replacement, applying phrases from LONGEST to SHORTEST to avoid partial-substring corruption; replacement must be applied over the whole working text.
- Translated JSON export preserving the original JSON structure; translated TXT export.
- CSV translation mapping export (phrase, translation, count, source locations).
- Optional AI translation using Gemini: configurable model name, locally stored API key, batch translation with configurable batch size, structured JSON results, background execution with progress reporting, graceful API error handling that retains the offline translation on failure, and retention of all existing offline/manual translations.
- AI translation must be optional and never block basic processing.
- Optional Chinese pronunciation / TTS preview if a local engine is available.

## STEP 3 - TEXT & NOVEL PROCESSING

Preserve the important functionality of the existing text/novel processor:

- Merging multiple TXT files in user-selected order.
- Natural filename sorting (ch9 before ch10).
- Merging TXT files from ZIP archives; support multiple archives.
- Ignoring directories and unwanted archive entries (macOS `__MACOSX`, hidden files, non-TXT files); handle `metadata`/`readme` entries as ignorable.
- Optional automatic chapter-header insertion when a file or entry has no header.
- Optional continuous chapter renumbering across merged sources.
- Text cleaning for TTS: control-character removal, HTML tag/entity removal, quote and bracket removal (configurable remove vs strip pairs), whitespace normalization, punctuation spacing normalization, symbol-to-Vietnamese-word conversion (`& < > %` etc.), and user-defined custom replacement rules applied in order.
- Chapter detection across Vietnamese, English, Chinese and numbered formats, plus a validated custom regex that must expose a `(?P<number>...)` capture group.
- Chapter continuity diagnostics: missing numbers, duplicates, order violations.
- Chapter-safe chunking: never split across a chapter boundary.
- Maximum chunk character limit with sane min/max clamping.
- Sentence-aware splitting with break preference: paragraph -> sentence -> clause -> space; fall back to hard slicing only when a single sentence/clause/word alone exceeds the limit, and emit a warning for those chunks.
- Chunk statistics: per-chapter chunk counts, total chunks, total characters, average/min/max chunk size.
- JSON export, detailed JSON export (includes per-chunk metadata and diagnostics), TXT export, clipboard copying, and TTS preview of a chunk or chapter.

## STEP 4 - CHAPTER RANGE FILTERING & EXPORT

Preserve:

- Chapter-range input such as `1-20` and `21-40`, accepting multiple ranges and comma-separated values.
- Quick block sizes: 10, 20, 25, 50, 100 chapters, generating consecutive blocks automatically from the detected chapter range.
- Select all / first 5 / first 10 / clear selection.
- Chapter diagnostics: missing and duplicate chapter warnings shown before export.
- Sequential renumbering repair and automatic chapter-header repair as explicit, user-triggered actions.
- Filtering chunks by chapter range.
- Single JSON export, single TXT export, batch ZIP export (one file or folder per selected range, mapping recorded in a manifest).
- Preview of each selected range with chapter count, chunk count, character count, and a text preview.
- Boundary fallback warnings when a range starts or ends inside a chapter or when a chunk had to be hard-split.

## ALGORITHMS TO PRESERVE EXACTLY

Do not simplify away behavior that affects correctness:

- Chinese numeral conversion.
- Multilingual chapter detection precedence.
- Duplicate chapter resolution order.
- Chapter continuity detection.
- Chinese substring replacement ordering (longest first).
- Chapter-safe chunking and sentence-boundary chunking.
- Range boundary fallback behavior.
- File encoding fallback chain.
- JSON structure preservation on export.

Do not invent new business rules. Where two original tools implemented the same feature differently, keep the more complete behavior that prevents data loss.

## NO DATA LOSS RULE

The single most important rule: never silently discard novel text, dialogue, chapter content, metadata, or translations. Cleaning may only remove content that the original tools explicitly treat as an artifact (translation JSON wrappers, escaped newlines, HTML markup, control characters, configured bracket pairs, duplicate chapter copies). Vietnamese narrative and dialogue attached to chapter headers must remain intact. Every destructive operation must be reportable: show what was removed, from where, and how many characters.

## UNIFIED UI

One main window, pipeline-oriented, not three separate apps. Stages arranged as a clear left-to-right or top-to-bottom flow:

- Input / Files
- Chapter Normalize
- Chinese Review
- Clean & Chunk
- Filter & Export

Shared reusable components: file picker, drag and drop, text editor/viewer, search box, statistics panel, progress/status indicator, preview pane, export controls, error/warning notification area.

Avoid duplicated controls and duplicated settings: if two stages share a behavior (encoding, chapter pattern, chunk size, output directory), define it once in a shared settings area.

Provide: background execution for long operations with cancel support, progress reporting, a log/console panel, and a stage status indicator showing which stage ran, on what input, with what result counts.

## PROJECT STRUCTURE

Keep it small and practical:

- `app.py` / `__main__.py` - application entry point
- `ui/` - main window, stage panels, shared widgets (file picker, editor, table, preview, stats, progress)
- `pipeline/` - stage orchestration, in-memory document, stage state
- `chapters/` - chapter detection, patterns, numerals, header normalization, duplicate resolution
- `cleaning/` - TTS cleaning, encoders, JSON unwrapping, text cleaning rules
- `chinese/` - Chinese detection, phrase extraction, grouping, dictionary, replacement
- `translation/` - translation table store, Gemini service interface, batch/background runner
- `chunking/` - chunk splitting, chunk metadata, statistics
- `filtering/` - chapter ranges, block generation, selection and repair
- `exporters/` - TXT, JSON, detailed JSON, CSV, ZIP batch export
- `tts/` - optional TTS and pronunciation preview
- `config/` - local configuration file for preferences and API key

Do not over-engineer. No plugin system, no abstraction layers beyond what the pipeline stages need.

Step 6 consumes only validated Step 5 MP4/Step 4 thumbnail state. Desktop OAuth uses the system browser and OS credential store. Persist resumable upload checkpoints and separate thumbnail/playlist outcomes in the current job's `youtube_upload.json`; never expose tokens/session URLs, retry a full video after a follow-up failure, or automatically create a duplicate from uncertain state. Keep API operations off the Qt UI thread with progress and cancellation.

## DELIVERABLE

A working, runnable local Python desktop application implementing the unified pipeline above, preserving every listed behavior, with no mandatory cloud dependency and no data loss.

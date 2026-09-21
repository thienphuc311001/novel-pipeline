# Implementation Manifest

Novel Pipeline v2 is a local PyQt6 application for normalizing novel text,
grouping chapters, generating audiobook/video media, and uploading selected
videos to YouTube.

## Current five-step workflow

1. **Input & Normalize** — load TXT/ZIP files and normalize multilingual
   chapter structure. Chinese headers and numerals are supported structurally;
   Chinese body text is preserved.
2. **Detect Chapters & Group** — preview headings and write exact UTF-8
   `final.txt`/`final.json` group artifacts plus `chapter_groups.json`.
3. **Thumbnail & Audiobook** — create per-group thumbnails and resumable TTS
   audiobooks from the current group text.
4. **Create Video** — render validated 1080p MP4 files with measured audio
   timing and hardware detection/fallback.
5. **YouTube Upload** — upload selected, validated MP4s with resumable state.

The internal artifact names `Step3ArtifactBundle` and `step3_artifacts` remain
unchanged for compatibility with existing jobs. They refer to the historical
bundle schema, not to a visible tab number.

## Components

- `pipeline/` — document state, stage tracking, and input loading
- `chapters/` — multilingual heading patterns, numerals, normalization, and
  duplicate handling
- `cleaning/` and `chunking/` — safe TTS preparation and sentence-aware chunks
- `media/` — exact group artifacts, thumbnails, TTS, video, and YouTube state
- `ui/` — five-step main window, group panels, settings, YouTube, and reusable
  `Copy all` controls
- `exporters/` — JSON and text exports

The former Chinese scanning and translation packages are intentionally absent.
Unknown keys from older config files are ignored by `Settings.from_dict`, so
old settings remain safe to load without restoring those features.

## Output and copy behavior

Every generated file — canonical `final.txt`/`final.json`, `thumbnail.jpg`,
`audio_chunks/`, audiobooks, `render_pages/`, and MP4s — is created inside the
folder of the Step 1 input file. There is no output-folder override: job files
never use a temporary folder, and creating groups refuses to run until an input
folder is loaded. The test suite points `NOVEL_PIPELINE_CONFIG_DIR` at an
isolated directory, so running tests never rewrites the user's `config.json`.

Read-only generated text in the main window, diagnostics, group panels,
failure dialogs, capability/result panels, and YouTube results exposes a
`Copy all` button. It copies the complete plain text and preserves line breaks.
Editable title, description, JSON, and TTS fields do not receive this control.

## Verification

Run the headless suite with:

```bash
python -m unittest discover -q
```

Run the lightweight import and chapter checks with:

```bash
python verify.py
```

# Implementation Manifest

Novel Pipeline v2 is a local React/Vite/shadcn workspace backed by FastAPI and a
Qt-free Python core for normalizing text, grouping chapters, generating media,
and uploading selected videos. The legacy PyQt6 interface is retained for
incremental migration comparisons, not required by CLI or web.

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

- `pipeline/` — document state, shared workspace/media actions, Qt-free CLI,
  input loading, and the existing versioned session store
- `chapters/` — multilingual heading patterns, numerals, normalization, and
  duplicate handling
- `cleaning/` and `chunking/` — safe TTS preparation and sentence-aware chunks
- `media/` — exact group artifacts, thumbnails, TTS, video, required Step 4 page
  pictures (`media/visuals.py`: byte-identical `visuals/` copies plus `visuals.json`
  records), and YouTube state
- `backend/` — loopback-only FastAPI, single-flight job manager, cooperative
  cancellation, SSE, durable input/assets uploads, registered output downloads
- `frontend/` — React + Vite + shadcn/ui, five-step workflow, live monitoring,
  configuration and saved sessions
- `ui/` — five-step main window, group panels, settings, YouTube, reusable
  `Copy all` controls, the shared modeless log window (`ui/log_dialog.py`), and
  the full-frame video page preview (`ui/video_preview.py`)
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

Read-only generated text in the main window, the shared log window, group
panels, failure dialogs, capability/result panels, and YouTube results exposes
a `Copy all` button. It copies the complete plain text and preserves line
breaks. Editable title, description, JSON, and TTS fields do not receive this
control.

## Log window

The workspace uses the full window height: the former bottom status panel is
gone. One `LogDialog` instance collects the status lines of every stage and is
opened from the toolbar **📋 Log** button or `Ctrl+L`. It is modeless, shared
by all five steps, keeps its lines across closing/reopening and step changes,
and never changes the active step, disables a control, or interrupts a running
job.

## Verification

Run the complete suite (including retained desktop comparisons) with optional
desktop dependencies installed:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Run the lightweight import and chapter checks with:

```bash
python verify.py
```

# Project Status

The application supports the existing five-step workflow through a Qt-free CLI,
local FastAPI + React/Vite/shadcn workspace, and retained optional PyQt6 desktop:

1. Input & Normalize
2. Detect Chapters & Group
3. Thumbnail & Audiobook
4. Create Video
5. YouTube Upload

## Recent changes

- Added root `np run dev` / `npm run dev`: starts the existing Vite and FastAPI
  commands together, selects the project `.venv`, labels logs per server and
  stops the sibling process tree on interruption or server exit.
- Fixed frontend startup when another application occupies port 8000: the dev
  launcher now uses API port 8765 and Vite's dev proxy targets that same port.
  The built application's default port is unchanged. Verified the connected
  Chromium UI, real import/normalize jobs and TypeScript/Vite production build.

- Incremental web migration: shared input/normalization/settings validation,
  headless grouped TTS/video/YouTube operations, single-flight API jobs, SSE,
  durable uploads and allowlisted output downloads, and existing JSON sessions.
- Translation/dictionary remain intentionally removed. PyQt6 remains optional
  for parity comparisons; external-provider success is not assumed from tests.
- Dependencies are split into `requirements-core.txt`, web `requirements.txt`,
  and optional `requirements-desktop.txt`; launch with `python -m pipeline`,
  `python -m backend`, or legacy `python app.py`.
- Web sessions restore the last workflow step, legacy group selections/images
  and grouped upload drafts. Tag reuse preserves titles and explicit empty-tag
  overrides; settings saves submit edits without overwriting newer tag history.
- TXT/JSON exports honor filename/encoding settings; ZIP layout/manifest options
  are preserved and archive publication is atomic.


- Step 4 pages use style `minimal-neon-theater-v5`: the neon frame covers 95% of
  the 1920×1080 canvas and the body block runs in a fixed, centered 1150px column
  at a fixed 36px, so each Step 3 chunk fills roughly 90–98% of its own measured
  page band (the real title and chapter labels, not a worst-case reserve) instead
  of stopping at a 700-character target. The measured pixel height decides every
  chunk boundary and a 20-line sanity guard stays secondary; a chunk that would
  need more than the band is reported for a Step 3 re-split, while short chapter
  headings and chapter tails (which cannot be stretched) simply show fewer lines.
  Rendered against a real multi-chapter novel, normal pages land near the 96%
  fill target and never overflow; paragraph-gap compression remains a safety net,
  with the same bold face as the title. The style change is part of the visual
  fingerprint, so Step 4 repaints every cached page of a group once — regenerate a
  group's thumbnail to pick up the bold chapter range; the old
  `render_pages/page_*` files stay on disk and can be deleted safely.
- Countdown/clock stamps such as `【4:59:50】` and `【12:09:57 — rương báu】` no
  longer match the plain numbered pattern: they stay in the chapter body
  instead of inventing `Chương 0`/`Chương 23` and splitting real chapters.
- Step 1 normalization and the Step 2 heading scanner share that guard; the
  `heading-scan-v2` scanner version therefore invalidates older numeric-boundary
  confirmations.
- Removed the legacy Chinese scanning/translation flow and its `chinese/` and
  `translation/` packages.
- Step 2 consumes successful Step 1 `normalized_text` directly, with a safe
  fallback to the original loaded text when Step 1 has not run.
- Chinese chapter headers and numerals remain available to structural chapter
  normalization; body text is not scanned, blocked, or translated.
- Artifact, grouping, and TTS provenance now use `normalized_revision`.
- Existing `Step3ArtifactBundle`/`step3_artifacts` names remain compatible with
  saved jobs.
- Replaced the bottom status/diagnostics panel with a shared modeless log
  window opened from the toolbar **📋 Log** button or `Ctrl+L`; the log stays
  available from every step and never interrupts a running job.
- Added reusable `Copy all` controls to generated read-only output, the shared
  log window, group panels, result/capability views, failure dialogs, and
  YouTube results.
- Removed dictionary/translation settings tabs and safely ignore those keys in
  legacy config files.

## Validation

The test suite covers direct Chinese-text flow from normalization to grouping,
five-tab ordering/navigation, legacy config loading, copy-to-clipboard output,
the shared log window, group/media provenance, TTS preparation, video timing,
and YouTube recovery.

Use:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m pipeline run /path/story.txt --title "Smoke story" --prepare --export zip
python verify.py
```

## Web migration verification

- Python suite: 352 passed, 163 subtests passed; one dependency deprecation
  warning from Starlette's httpx TestClient.
- React production build: TypeScript and Vite passed.
- CLI/core ran with Qt imports forbidden. Desktop and headless normalization
  produced identical text/headings on the mixed-language smoke input.
- Real browser checks covered import/edit/group/export, numeric-boundary consent,
  UTF-16 output downloads, thumbnails, legacy session restoration, tag reuse,
  settings-history preservation and cooperative TTS stop (`stopping` → `cancelled`).
  All seven screens fit a 375px viewport; desktop and landscape were inspected.
- FFmpeg rendered and FFprobe validated a 1920×1080 H.264 MP4 using controlled
  fixture audio; Chromium played it. This is not a complete real-speech parity run.
- Real Edge-TTS generated resumable chunks but returned `NoAudioReceived` for
  some chunks. Real YouTube OAuth/upload was not exercised without a test client
  and channel. PyQt6 therefore remains available; its removal gate is not met.

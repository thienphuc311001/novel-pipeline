# Project Status

The application now uses a five-step desktop workflow:

1. Input & Normalize
2. Detect Chapters & Group
3. Thumbnail & Audiobook
4. Create Video
5. YouTube Upload

## Recent changes

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
python -m unittest discover -q
python verify.py
```

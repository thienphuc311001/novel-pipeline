# Project Status

The application now uses a five-step desktop workflow:

1. Input & Normalize
2. Detect Chapters & Group
3. Thumbnail & Audiobook
4. Create Video
5. YouTube Upload

## Recent changes

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

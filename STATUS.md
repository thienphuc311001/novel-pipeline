# Project Status

The application now uses a five-step desktop workflow:

1. Input & Normalize
2. Detect Chapters & Group
3. Thumbnail & Audiobook
4. Create Video
5. YouTube Upload

## Recent changes

- Removed the legacy Chinese scanning/translation flow and its `chinese/` and
  `translation/` packages.
- Step 2 consumes successful Step 1 `normalized_text` directly, with a safe
  fallback to the original loaded text when Step 1 has not run.
- Chinese chapter headers and numerals remain available to structural chapter
  normalization; body text is not scanned, blocked, or translated.
- Artifact, grouping, and TTS provenance now use `normalized_revision`.
- Existing `Step3ArtifactBundle`/`step3_artifacts` names remain compatible with
  saved jobs.
- Added reusable `Copy all` controls to generated read-only output, diagnostics,
  group panels, result/capability views, failure dialogs, and YouTube results.
- Removed dictionary/translation settings tabs and safely ignore those keys in
  legacy config files.

## Validation

The test suite covers direct Chinese-text flow from normalization to grouping,
five-tab ordering/navigation, legacy config loading, copy-to-clipboard output,
group/media provenance, TTS preparation, video timing, and YouTube recovery.

Use:

```bash
python -m unittest discover -q
python verify.py
```

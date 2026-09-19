# Novel Pipeline v2 — Current Summary

The desktop application now exposes five visible steps:

1. Input & Normalize
2. Detect Chapters & Group
3. Thumbnail & Audiobook
4. Create Video
5. YouTube Upload

Step 2 consumes the successful Step 1 normalized text directly. If Step 1 has
not run, it uses the original loaded text as a fallback; a failed Step 1 does
not silently supply stale normalized output. Chinese text is preserved without
residue scanning, dictionary replacement, or translation. Chinese chapter
headers and numerals remain supported for structural normalization.

The removed `chinese/` and `translation/` packages are no longer part of the
application. Dictionary, review, and AI-translation settings are gone. Legacy
unknown config keys are ignored safely. Existing `Step3ArtifactBundle` and
`step3_artifacts` names remain for job compatibility, while source provenance
uses `normalized_revision`.

Generated read-only output has a shared **Copy all** control in the main
window, diagnostics, chapter/group previews, batch details/results,
capability/result panels, failure dialogs, and YouTube results. It copies the
complete plain text with line breaks; editable fields remain editable.

## Verification

```bash
python -m unittest discover -q
python verify.py
```

The current headless run passes 156 tests; one optional Google OAuth test is
skipped when `google-auth-oauthlib` is not installed.

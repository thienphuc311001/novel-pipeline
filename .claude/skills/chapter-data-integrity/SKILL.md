---
name: chapter-data-integrity
description: >-
  Use when changing or reviewing chapter import, normalization, grouping, TTS
  cleaning, preprocessing, chunking, or text-dependent cache/provenance in
  novel-pipeline-v2; also for lost/reordered text or stale audio (mất dữ liệu
  chương, bảo toàn văn bản nguồn/canonical). Not for UI styling, deployment,
  or smoke-check reporting alone.
---

# Chapter Data Integrity

Apply the repository's data contracts to the authorized change. Read root
[CLAUDE.md](../../../CLAUDE.md); this skill adds a review procedure, not permission
to modify files, run tests or invoke providers.

## Established contracts

| Layer | Contract and evidence |
| --- | --- |
| Input | On-disk source bytes, decoded/merged text and normalized text are different. Loading chooses encoding/order, joins inputs and can insert headers: [loader.py](../../../pipeline/loader.py), [service.py](../../../pipeline/service.py). Preserve input files during downstream processing; do not assume `original_input_text` is a byte-identical archive backup. |
| Canonical | `require_grouping_input()` chooses successful normalized output or original loaded text: [document.py](../../../pipeline/document.py). Initial complete grouping preserves exact slices, preamble, line endings and order in `final.txt`/`final.json`: [groups.py](../../../media/groups.py), `write_groups`/`validate_group`. Selected/deleted subsets do not reproduce the entire source. |
| TTS copy | `prepare_chapter` copies its chapter; safe cleaning and preprocessing precede chunking without rewriting canonical files: [tts_prepare.py](../../../cleaning/tts_prepare.py), `prepare_tts` in groups.py. |
| Transformations | Normalization may intentionally change headings, quotes, titles or duplicates. TTS policies may change working text. Suspicious encoding/CJK diagnostics are not authorization to guess, translate or discard narrative: [normalizer.py](../../../chapters/normalizer.py), [preprocessor](../../../cleaning/tts_text_preprocessor.py). |
| Chunking | `verify_chunk_integrity` checks ordered coverage of every non-whitespace character of prepared text; it is not byte equality: [splitter.py](../../../chunking/splitter.py). |
| Provenance | Plan identity includes source hash/revision and preparation config/versions/layout. Old overrides remain stored but are not applied to a different plan. Audio resume validates exact text/hash, order, chapter, voice, request mode and MP3 hash: groups.py; [tts.py](../../../media/tts.py). |
| Storage | Artifact writers use same-directory temporary files and atomic replacement: [artifacts.py](../../../media/artifacts.py). This is per-file atomicity, not proof of a multi-file transaction. |

## Review workflow

1. **Baseline:** record task scope, Git state and affected read/write paths. With
   synthetic fixtures, snapshot relevant source/canonical bytes or hashes,
   decoded text, encoding/order, grouping source, revision and manifests.
   Do not read real novels, user configuration or credentials to build fixtures.
2. **Trace transformations:** map input → normalization/grouping → prepared TTS
   text → base chunks → effective overrides → audio/merge. State expected
   changed spans and unchanged layers. Compare canonical TXT bytes with JSON
   text encoded as UTF-8; compare all initial groups in recorded order with
   current grouping input. Account explicitly for authorized selections/deletions.
3. **Check provenance:** use existing validators, not refreshed hashes to bless
   changed files. Check source revision/hash, group IDs/offsets, plan/config
   identity, effective text, audio records and affected downstream invalidation.
   Review version changes when algorithm semantics change. Plan changes do not
   automatically invalidate unchanged audio; chunk count alone never permits
   reuse. Preserve stale overrides and require a reviewed mapping before migration.
4. **Regression:** choose cases for the affected layer: unchanged source/canonical;
   expected transformation output and diagnostic retention; paragraph/newline
   structure promised by the planner; missing/duplicate/reordered non-space
   characters; changed text with unchanged chunk count;
   changed voice/tampered MP3; stale plans/overrides; cancellation and write failure.
   Test idempotence where the transformation promises it. Include the unchanged
   success path and a targeted failure path. Run only task-authorized checks with
   temporary config/output and fake providers; distinguish environment failures
   from demonstrated regressions.

Read the relevant existing tests before selecting commands (runtime results are
not established by this skill):

- Grouping/canonical: [test_chapter_groups.py](../../../tests/test_chapter_groups.py).
- Normalization/title semantics: [test_chapter_normalization.py](../../../tests/test_chapter_normalization.py),
  [test_chinese_title_stripping.py](../../../tests/test_chinese_title_stripping.py).
- TTS preparation/overrides: [test_tts_preprocessing.py](../../../tests/test_tts_preprocessing.py).
- Coverage/layout: [test_layout_chunking.py](../../../tests/test_layout_chunking.py).
- Audio provenance/resume: [test_tts.py](../../../tests/test_tts.py).

## Stop conditions

Stop the affected mutation/media operation and report evidence when source or
canonical changes unexpectedly, text is lost/duplicated/reordered outside the
established contract, provenance validation fails, or required validation cannot
run. Continue independent read-only diagnosis; do not fabricate a pass.

If expected text changes, migration or deletion behavior is unspecified, request
the Product Owner's decision before implementing that behavior. Missing technical
evidence goes to the Technical Lead. Existing diagnostic warnings alone are not
new automatic blockers.

## Report

Provide: affected layers/files; invariant → evidence → check/result; expected
text deltas; provenance/cache impact; failures/skips/unverified items; owner
decisions still needed. Byte-exact chunking, zero-warning TTS gates, changed
normalization defaults and automatic override migration are proposals requiring
approval, not contracts established here.

# Coverage ledger — Remove PyQt6 desktop (web-only)

- Status: Complete for review (S1 inventory frozen; S2–S5 executed; S6 independent-review fixes applied and rerun; owner gap dispositions recorded). Every non-retired row has a destination that ran in the S5 and S6 full suites.
- Plan: `intent/web-only-remove-pyqt6/plan.md` (Approved). Rules: Plan §3 (real service/job/HTTP/persistence; fakes only at provider/process boundaries) and §4 (no assertion disappears unnoticed).
- Baseline: `main` at `8b4bb31` (PR #3 merge). Appendix A: 14/14 file SHA-256 values re-verified unchanged before any edit.
- Static inventory: 139 test methods, 697 direct assertion calls (AST extraction of `assert*` calls and `assert` statements).

## Planned disposition totals (Appendix B)

| Disposition | Count |
| --- | --- |
| Retain in place (body unchanged, Qt setup/imports removed from module only) | 59 |
| Migrate (business assertions kept; Qt presentation sub-assertions retire) | 67 |
| Move unchanged (pure metadata cases → `tests/test_youtube.py`) | 3 |
| Retire desktop-only | 10 |
| **Total** | **139** |

Correction applied before deletion (Plan §4, "any mistaken retirement classification is corrected"): #25 `test_file_picker_starts_at_and_updates_last_folder` mixes a native picker start-directory assertion (desktop-only) with business assertions (import records `last_input_dir`, persists it, loads document text/source path/input directory). The business part is migrated to `tests/test_last_input_folder.py::LastInputFolderTests::test_import_updates_and_persists_last_folder`; only the QFileDialog start-directory assertion retires. Net: 68 migrated, 9 retired.

## S1 results (executed on unchanged baseline)

| Check | Command (inside `wo_py`, private network, fresh config dir) | Result |
| --- | --- | --- |
| Removal RED | `python -m unittest -v tests.test_web_only_runtime.WebOnlyRuntimeTests.test_desktop_boundary_removed` | exit 1, `AssertionError` listing present `app.py`, `ui/`, `requirements-desktop.txt` (expected RED, not ImportError/collection-zero) |
| Real-backend Host/Origin (AT2) | `python -m unittest -v tests.test_web_only_runtime.WebOnlyRuntimeTests.test_real_backend_host_origin_policy` | exit 0; 38 cases: 8 accepted (loopback Host ×3, same-origin ×2, dev origins ×2, dev preflight) → 200; 28 rejected Host/Origin → 403; missing Host / duplicate Host → 400 |
| Runtime oracles | `…test_supported_modules_import_without_qt`, `…test_real_backend_health_without_qt`, `…test_cli_fixture_pipeline_without_qt` | exit 0 each |
| Import-blocker negative control | blocker child importing `app` / `ui.copy_controls` | exit 1 each with `ImportError: retired desktop import` (blocker effective) |
| Qt-free preflight | `python -m pytest -q` over 18 Qt-free modules | exit 0: 213 passed, 99 subtests passed |
| Headless/web preflight | `python -m pytest -q -rA tests/test_headless_service.py tests/test_headless_media.py tests/test_web_jobs.py tests/test_web_api.py` | exit 0: 38 passed, 42 subtests passed |

## Coverage gaps requiring owner disposition

Found while tracing assertions to the web/core product. Per Plan §3/§4 these are recorded, not implemented in test code and not silently relaxed.

| Gap | Baseline assertions | Web/core behavior observed in source | Disposition |
| --- | --- | --- | --- |
| G1 settings-change invalidation | #84 `test_config_ui_and_downstream_invalidation`: changing audio settings invalidates group TTS/audiobook/video, JPEG quality invalidates thumbnail/video, grouping change invalidates ungrouped step-3 artifacts | `PUT /api/settings` → `PipelineService.update_settings` validates and saves only; it does not invalidate document artifacts | Owner (2026-10-13): `@unittest.expectedFailure` with gap id |
| G2 tag import on story open | #124 `test_existing_completed_upload_is_imported_when_its_story_is_opened` | The web/core path records story tags when an upload confirms a `video_id`; it does not import tags from an existing completed `youtube_upload.json` when a story is opened | Owner (2026-10-13): `@unittest.expectedFailure` with gap id; RED evidence `s2-g2-red.log` |
| G3 auth-failure pause queue | #14 auth failure pauses the queue with remaining groups; #15 paused shared edits apply to unstarted groups | `execute_media` stops the remaining batch on auth failure (`break`) and reports "reconnect"; a rerun reuses frozen metadata for started groups and new shared metadata for unstarted groups. No paused queue object exists | Owner (2026-10-13): `@unittest.expectedFailure` with gap id; the business intent that is supported (no further uploads after auth failure; rerun semantics) is still migrated |
| G4 web duplicate-upload confirmation | #134 `test_progress_completion_copy_url_and_duplicate_confirmation` (confirmed duplicate re-upload) | `frontend/src/screens/youtube-screen.tsx:114` sends `allow_duplicate: true`; `backend/validation.py:66` `_ACTIONS["upload"]` accepts only `group_ids`/`metadata`/`group_metadata`/`titles`, so `POST /api/jobs` returns 422 `Tùy chọn không được hỗ trợ: allow_duplicate`. Core `pipeline/media_service.py:399/456` honors `allow_duplicate` | Owner (2026-10-13): `@unittest.expectedFailure` with gap id; evidence test via HTTP |
| G5 video-job refusal wording | #19 `test_video_process_group_refuses_without_inputs_and_records_them_after` (desktop text "Add both page images (1:1 left + QR right) before creating a video.", `ui/grouped_pipeline.py:908`) | The web video job refuses correctly (no render, no video recorded) but `_video` (`pipeline/media_service.py:330-337`) has no page-image pre-check, so the refusal is the lower-level `media/visuals.py:34` "Missing the 1:1 (left) image for the video pages: ."; preview has the pre-check (`pipeline/media_service.py:364`). The equivalent preview row #120 was migrated to the core refusal | Owner (2026-10-13): retired desktop wording like #120; the test asserts the core refusal (`s3-dispositions.log`) |

Gap assertions run only inside `@unittest.expectedFailure` tests whose decorator comment names the gap; every supported assertion from the same baseline method sits in a sibling test that must pass. A product fix turns the xfail into an unexpected success (a failing result), which forces the decorator and this table to be updated. The actual failing assertion of each xfail is recorded in `s3-xfail-reasons.log` and, after the S6 review fixes (G1 sibling now asserts the canonical bytes; G2 asserts on the live `service.settings`), in `s6-xfail-reasons.log`.

Owner sign-off (2026-10-13) also covers the recorded substitutions and deviations: desktop strings replaced by the equivalent core behavior/error (#85, #119 speed with one decimal, #120, #19/G5); #4 cancelled job status 'failed' with `result.cancelled` true; #15 a second upload job stands in for resume; #135/#138 two groups because of G4; #139 half-size 308 Range; #133 generic error text.

## Executed commands

Log names refer to files under `$WEB_ONLY_RUN/evidence/`; sizes and SHA-256 values are in `evidence.md`. Every Python command ran inside `wo_py` (private network namespace, read-only source, fresh `NOVEL_PIPELINE_CONFIG_DIR`).

| Stage | Command | Log | Result |
| --- | --- | --- | --- |
| S2 | `pytest -q tests/test_youtube_title_tags.py` after the FakeAuth switch | `s2-title-tags.log` | exit 1: 6 passed, 1 failed (#124, G2) |
| S2 | focused mixed modules (`test_last_input_folder`, `test_pipeline_data_flow`, `test_sessions`, `test_tts_preprocessing`, `test_video_preview`, `test_video_pages`, `test_youtube_title_tags`) | `s2-focused.log` | exit 1: 78 passed, 2 failed (#84 G1, #124 G2) |
| S2 | headless/web/runtime set | `s2-headless-web.log` | exit 1: 42 passed, 1 failed (`test_desktop_boundary_removed`, expected removal RED before S4) |
| S2 | first RED of G1 / G2 in isolation | `s2-g1-red.log`, `s2-g2-red.log` | exit 1 each at the gap assertion |
| S2 | frontend tests | `s2-frontend-test.log` | exit 0, 11 pass |
| S3 | `pytest -q tests/test_web_business_regressions.py tests/test_youtube.py tests/test_youtube_auth.py tests/test_youtube_pipeline.py` | `s3.log` | exit 1 before dispositions: 78 passed, 4 failed (G3 #14/#15, G4 #134, G5 #19) |
| S3 | same set after owner dispositions | `s3-dispositions.log` | exit 0: 79 passed, 5 xfailed |
| S3 | each xfail run without the decorator | `s3-xfail-reasons.log` | each fails at its gap assertion (listed in the gap table) |
| S4 | runtime oracles `python -m unittest -v tests.test_web_only_runtime` | `s4-runtime-oracles.log` | exit 0: 5 OK; `test_desktop_boundary_removed` is now GREEN (S1 RED was exit 1) |
| S4 | `pytest --collect-only -q` | `s4-collect.log` | exit 0: 365 collected, no Qt import/collection error |
| S5 | full suite `pytest -q -rA --junitxml=pytest-full.xml` | `pytest-full.log`, `pytest-full.xml` | exit 0: 360 passed, 5 xfailed, 0 skipped, 0 failed, 166 subtests passed |
| S5 | isolation repeat, modules forward and reversed in one process | `s5-isolation-forward.log`, `s5-isolation-reverse.log` | exit 0 each: 124 passed, 5 xfailed; 8 patch targets restored; `os.environ` restored; 0 child processes; fresh config dir |
| S5 | frontend tests and build (`wo_node`) | `frontend-test.log`, `frontend-build.log` | exit 0: 11 pass; build into `$WEB_ONLY_DIST` |
| S5 | browser smoke attempt 8 (real build, fake providers, local Firefox) | `smoke-attempts/smoke-attempt8-results.json` | exit 0: 16 PASS, 1 XFAIL (G4 duplicate upload refused with 422 `allow_duplicate`); superseded by attempt 9 |
| S6 | modules touched by the review fixes (`test_tts_preprocessing`, `test_youtube_title_tags`, `test_web_business_regressions`, `web_smoke_app` import) | `s6-fix-affected.log` | exit 0: 32 passed, 2 xfailed |
| S6 | each xfail run without the decorator | `s6-xfail-reasons.log` | each fails at its gap assertion: G3 :467/:509, G4 :1047, G1 :462, G2 :72 |
| S6 | G2 positive control (live settings, simulated product fix) | `s6-g2-fix-control.log` | without fix FAIL `None != ['tag cũ']`; with simulated fix PASS (the xfail can turn into an unexpected success) |
| S6 | full suite `pytest -q -rA --junitxml=pytest-full-s6.xml` | `pytest-full-s6.log`, `pytest-full-s6.xml` | exit 0: 360 passed, 5 xfailed, 0 skipped, 0 failed, 166 subtests passed |
| S6 | isolation repeat, forward and reversed | `s6-isolation-forward.log`, `s6-isolation-reverse.log` | exit 0 each: 124 passed, 5 xfailed; 8 patch targets restored; `os.environ` restored; 0 child processes; fresh config dir |
| S6 | frontend tests and build (`wo_node`) | `s6-frontend-test.log`, `s6-frontend-build.log` | exit 0: 11 pass; build manifest `s6-dist-manifest.txt` identical to S5 |
| S6 | browser smoke attempt 9 (adds step 18: reopen a desktop-shaped schema-v1 session) | `smoke-results.json`, `smoke-driver.log`, `smoke-postchecks.txt` | exit 0: 17 PASS, 1 XFAIL (G4); 0 console errors |

S5 ledger reconciliation: of 139 baseline methods, 10 retire desktop-only, and 129 have destinations. All 129 ran in `pytest-full.xml`: 124 rows PASS, 4 rows PASS + XFAIL (#14, #15, #84, #134: the supported part passes, the gap part is xfail), 1 row XFAIL (#124, G2). No destination is missing, skipped or failing. The S6 rerun (`pytest-full-s6.xml`) gives the identical per-row mapping.


## Ledger (139 baseline methods)

`BR::` = `tests/test_web_business_regressions.py::BusinessRegressionTests::`. Baseline AST = first 16 hex of SHA-256 over `ast.dump` of the baseline method (retained rows must keep the same AST). Result cells come from the command evidence listed under "Executed commands".

| # | Baseline source | Baseline AST | Asserts | Disposition | Destination | Req · AT | Result | Retirement justification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `test_group_batches.py:48` `GroupBatchTests.test_step3_active_ui_creates_groups_not_tts` | `29d19ede52ef0858` | 7 | Migrate | `BR::test_step3_active_ui_creates_groups_not_tts` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 group-size combo value, A5 Step-4 stack widget, A6 empty check state (widget/selection presentation; the size is sent explicitly as `size: 10`) |
| 2 | `test_group_batches.py:65` `GroupBatchTests.test_step3_numeric_boundary_confirmation_and_unavailable_boundary` | `7cd66643c075008e` | 6 | Migrate | `BR::test_step3_numeric_boundary_confirmation_and_unavailable_boundary` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 desktop wording 'Some chapter numbers are missing.' (stage3_output text; web exposes the same state as `requires_numeric_boundaries` + 'Numbering gap' warning, rendered by text-screens.tsx:149); A6 button-disabled (web: create gated on `numeric_available`, text-screens.tsx:118) |
| 3 | `test_group_batches.py:95` `GroupBatchTests.test_defaults_and_select_all_subset_snapshot` | `083b9038d8595ca2` | 5 | Migrate | `BR::test_defaults_and_select_all_subset_snapshot` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1/A5 check-all/uncheck widget state (the subset is the explicit `group_ids` list) |
| 4 | `test_group_batches.py:116` `GroupBatchTests.test_group_failure_continues_cancel_stops_future_groups` | `63be4c86710688a2` | 2 | Migrate | `BR::test_group_failure_continues_cancel_stops_future_groups` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 5 | `test_group_batches.py:133` `GroupBatchTests.test_tts_incomplete_continues_and_resume_keeps_canonical_files` | `d05591198f1eff2e` | 9 | Migrate | `BR::test_tts_incomplete_continues_and_resume_keeps_canonical_files` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A6 `status_for` label text (asserted on state `tts_status` instead) |
| 6 | `test_group_batches.py:176` `GroupBatchTests.test_zero_audio_partial_merge_rejected_without_dialog` | `9e81626e040e8664` | 1 | Migrate | `BR::test_zero_audio_partial_merge_rejected_without_dialog` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 7 | `test_group_batches.py:183` `GroupBatchTests.test_partial_merge_is_explicit_and_records_missing_numbers` | `173e8839e38b4408` | 6 | Migrate | `BR::test_partial_merge_is_explicit_and_records_missing_numbers` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | QMessageBox No/Yes dialog (web: explicit `allow_partial` flag; `false` is rejected 422 by validation) |
| 8 | `test_group_batches.py:217` `GroupBatchTests.test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks` | `636c6f3c1b128c64` | 11 | Migrate | `BR::test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A7/A8 empty thumbnail pixmap + 'No thumbnail selected' label (asserted as no thumbnail.jpg / no `thumbnail` state on g1) |
| 9 | `test_group_batches.py:250` `GroupBatchTests.test_damaged_group_does_not_block_entry_or_other_batch_jobs` | `5f508caa72e0b473` | 3 | Migrate | `BR::test_damaged_group_does_not_block_entry_or_other_batch_jobs` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 10 | `test_group_batches.py:266` `GroupBatchTests.test_step3_can_delete_any_group_and_refresh_later_stages` | `a9ffd03ac4a066e6` | 17 | Migrate | `BR::test_step3_can_delete_any_group_and_refresh_later_stages` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 tab index, A2/A3/A4/A16 Step-4 panel widget contents, A13 thumbnail label '—', A14/A15 button enablement, A17 stack widget |
| 11 | `test_group_batches.py:302` `GroupBatchTests.test_step4_busy_blocks_image_selection_and_group_deletion` | `8ddaf0ed10ff323f` | 3 | Migrate | `BR::test_step4_busy_blocks_image_selection_and_group_deletion` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 12 | `test_group_batches.py:316` `GroupBatchTests.test_progress_visible_and_busy_blocks_other_stages` | `1237cc4e07a50e26` | 6 | Migrate | `BR::test_progress_visible_and_busy_blocks_other_stages` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A3 progress-bar visibility (widget) |
| 13 | `test_group_batches.py:334` `GroupBatchTests.test_upload_metadata_frozen_individually_completed_skipped` | `863e4f18deeaefc9` | 9 | Migrate | `BR::test_upload_metadata_frozen_individually_completed_skipped` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 14 | `test_group_batches.py:366` `GroupBatchTests.test_auth_failure_pauses_remaining_queue` | `43ec22d54217acc7` | 4 | Owner disposition 2026-10-13: expectedFailure with gap id. Gap G3 — no pause queue; execute_media breaks the loop on auth failure (pipeline/media_service.py:606-607) and the job is marked 'failed' (backend/jobs.py:179-181). | `BR::test_auth_failure_stops_batch_before_later_groups` (GREEN part) + `BR::test_auth_failure_pauses_remaining_queue` (`@unittest.expectedFailure`, G3) | R5/R8/R9 · AT5/AT8 | PASS (GREEN part) + **XFAIL — gap G3** (`s3-dispositions.log` exit 0; real failing assertion in `s3-xfail-reasons.log`: :467 job status 'failed' != 'paused'); S5 full suite (`pytest-full.xml`): PASS + XFAIL; S6 full suite (`pytest-full-s6.xml`): PASS + XFAIL | — |
| 15 | `test_group_batches.py:382` `GroupBatchTests.test_paused_batch_shared_edits_affect_only_unstarted_sessions` | `1cd61139690c83f1` | 7 | Owner disposition 2026-10-13: expectedFailure with gap id; owner accepted the second upload job as the stand-in for resume. Frozen-vs-draft metadata semantics hold across separate jobs. | `BR::test_rerun_after_auth_failure_keeps_frozen_metadata_and_applies_shared_edits` (GREEN part) + `BR::test_paused_batch_shared_edits_affect_only_unstarted_sessions` (`@unittest.expectedFailure`, G3) | R5/R8/R9 · AT5/AT8 | PASS (GREEN part) + **XFAIL — gap G3** (`s3-dispositions.log` exit 0; real failing assertion in `s3-xfail-reasons.log`: :509 first job status 'failed' != 'paused'); S5 full suite (`pytest-full.xml`): PASS + XFAIL; S6 full suite (`pytest-full-s6.xml`): PASS + XFAIL | — |
| 16 | `test_group_batches.py:409` `GroupBatchTests.test_sequential_upload_engine_continues_after_group_failure` | `15270fc81f190ab4` | 4 | Migrate | `BR::test_sequential_upload_engine_continues_after_group_failure` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 17 | `test_group_batches.py:436` `GroupBatchTests.test_video_current_output_skip_and_sequential_subset` | `f2bc1a77edaa21f9` | 1 | Migrate | `BR::test_video_current_output_skip_and_sequential_subset` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 18 | `test_group_batches.py:456` `GroupBatchTests.test_video_refuses_to_start_without_both_page_inputs` | `bdaaea986daf77ab` | 6 | Migrate | `BR::test_video_refuses_to_start_without_both_page_inputs` | R5/R8/R9 · AT5/AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A3/A5 start-button enablement and A4/A6 desktop inputs-status text (web blocks start client-side: media-screens.tsx:140 'Chọn ảnh bìa'/'Chọn ảnh QR') |
| 19 | `test_group_batches.py:477` `GroupBatchTests.test_video_process_group_refuses_without_inputs_and_records_them_after` | `374097dadedea995` | 7 | Migrate. Owner disposition 2026-10-13 (G5 treated like #120): the desktop wording 'Add both page images (1:1 left + QR right) before creating a video.' (ui/grouped_pipeline.py:908 @8b4bb31) retires; the test asserts the core refusal 'Missing the 1:1 (left) image for the video pages' (media/visuals.py:34). The web `_video` has no page-images precondition (pipeline/media_service.py:335-337); preview keeps it (:363-364). | `BR::test_video_process_group_refuses_without_inputs_and_records_them_after` | R5/R8/R9 · AT5/AT8 | PASS (`s3-dispositions.log` exit 0); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 desktop wording 'page images' → core message (owner-approved, as #120) |
| 20 | `test_group_batches.py:508` `VideoMetadataUpdateTests.test_metadata_update_preserves_unrelated_fields_and_frozen_insertion` | `0ffb9ad615eb9fef` | 10 | Move unchanged | `tests/test_youtube.py::VideoMetadataUpdateTests::test_metadata_update_preserves_unrelated_fields_and_frozen_insertion` | R5/R8/R9 · AT5/AT8 | PASS (`s2-focused.log`, `s3.log`); moved unchanged, AST equal to baseline; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 21 | `test_group_batches.py:523` `VideoMetadataUpdateTests.test_metadata_update_can_clear_ai_disclosure` | `cf9045e5ce0ab158` | 3 | Move unchanged | `tests/test_youtube.py::VideoMetadataUpdateTests::test_metadata_update_can_clear_ai_disclosure` | R5/R8/R9 · AT5/AT8 | PASS (`s2-focused.log`, `s3.log`); moved unchanged, AST equal to baseline; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 22 | `test_group_batches.py:532` `VideoMetadataUpdateTests.test_api_failure_keeps_local_record_unchanged` | `251a26cae0930591` | 2 | Move unchanged | `tests/test_youtube.py::VideoMetadataUpdateTests::test_api_failure_keeps_local_record_unchanged` | R5/R8/R9 · AT5/AT8 | PASS (`s2-focused.log`, `s3.log`); moved unchanged, AST equal to baseline; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 23 | `test_last_input_folder.py:24` `LastInputFolderTests.test_setting_round_trip_and_invalid_folder_fallback` | `1552752095c3f22b` | 2 | Retain | `tests/test_last_input_folder.py::LastInputFolderTests::test_setting_round_trip_and_invalid_folder_fallback` | R10 · AT6 | PASS (`s2-focused.log`); AST unchanged `1552752095c3f22b`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 24 | `test_last_input_folder.py:37` `LastInputFolderTests.test_output_folder_always_follows_the_input` | `abc9bc3e84c9a27a` | 6 | Retain | `tests/test_last_input_folder.py::LastInputFolderTests::test_output_folder_always_follows_the_input` | R10 · AT6 | PASS (`s2-focused.log`); AST unchanged `abc9bc3e84c9a27a`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 25 | `test_last_input_folder.py:56` `LastInputFolderTests.test_file_picker_starts_at_and_updates_last_folder` | `f7a4ff869fc8e9e3` | 6 | Retire desktop only | — | R10 · AT6 | Retired; supplementary web evidence `LastInputFolderTests::test_import_updates_and_persists_last_folder` PASS (`s2-focused.log`) | O1: native QFileDialog interaction; retain Settings/input-relative output and real HTTP import coverage. |
| 26 | `test_log_dialog.py:26` `LogDialogTests.test_shared_log_keeps_every_step_line_across_closing` | `296eae7857de27ac` | 7 | Migrate | `BR::test_job_logs_remain_available_across_reads` | R5 · AT4 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1–A4, A6 log-window visibility/parent/modality (no desktop window) |
| 27 | `test_log_dialog.py:51` `LogDialogTests.test_opening_the_log_leaves_the_active_step_and_busy_state_untouched` | `b4729af664417a9b` | 6 | Migrate | `BR::test_reading_job_logs_preserves_busy_state` | R5 · AT4 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A3/A4 log window/button widget state; A1/A5 tab index (web screen is client state) |
| 28 | `test_log_dialog.py:65` `LogDialogTests.test_log_button_and_shortcut_toggle_the_window` | `ae3851e6cd571ce2` | 9 | Retire desktop only | — | R5 · AT4 | Retired (desktop only) | O1: Qt window/shortcut interaction only; job log visibility retained. |
| 29 | `test_log_dialog.py:95` `LogDialogTests.test_max_log_lines_bounds_the_shared_buffer` | `198fe5efbb04092c` | 4 | Migrate | `BR::test_max_log_lines_bounds_the_shared_buffer` | R5 · AT4 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | QTextDocument block-count API (replaced by the per-job log buffer) |
| 30 | `test_log_dialog.py:107` `LogDialogTests.test_closing_the_main_window_hides_the_log_window` | `bd7cd8a6dba15e10` | 2 | Retire desktop only | — | R5 · AT4 | Retired (desktop only) | O1: window lifecycle only; persisted session and job log recovery retained. |
| 31 | `test_log_dialog.py:119` `LogDialogTests.test_copy_all_and_clear_use_the_shared_log` | `f9df3c185c656c04` | 4 | Retire desktop only | — | R5 · AT4 | Retired (desktop only) | O1: clipboard/Qt log controls; preserve log content/order/bounds in migrated cases. |
| 32 | `test_pipeline_data_flow.py:55` `PipelineDataFlowTests.test_step2_consumes_exact_normalized_text_without_han_gate` | `5518a6ed478b7cfa` | 8 | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_step2_consumes_exact_normalized_text_without_han_gate` | R6 · AT5 | PASS (`s2-focused.log`); AST unchanged `5518a6ed478b7cfa`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 33 | `test_pipeline_data_flow.py:70` `PipelineDataFlowTests.test_original_is_fallback_before_step1` | `4a9ae732f31de288` | 2 | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_original_is_fallback_before_step1` | R6 · AT5 | PASS (`s2-focused.log`); AST unchanged `4a9ae732f31de288`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 34 | `test_pipeline_data_flow.py:79` `PipelineDataFlowTests.test_successful_step1_without_output_fails_closed` | `a09a24080a495d85` | 1 | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_successful_step1_without_output_fails_closed` | R6 · AT5 | PASS (`s2-focused.log`); AST unchanged `a09a24080a495d85`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 35 | `test_pipeline_data_flow.py:87` `PipelineDataFlowTests.test_step1_edit_replaces_grouping_source_and_invalidates_chunks` | `88ed960f3f214913` | 4 | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_step1_edit_replaces_grouping_source_and_invalidates_chunks` | R6 · AT5 | PASS (`s2-focused.log`); AST unchanged `88ed960f3f214913`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 36 | `test_pipeline_data_flow.py:98` `PipelineDataFlowTests.test_main_window_allows_chinese_text_in_step2` | `5f0716bfc3ab1d93` | 2 | Migrate | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_service_allows_chinese_text_in_step2` | R6 · AT5 | PASS (`s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 `tabs.currentIndex()` widget read |
| 37 | `test_sessions.py:44` `SessionTests.test_roundtrip_retains_text_types_and_validated_media` | `1d2118a97d56069a` | 5 | Retain | `tests/test_sessions.py::SessionTests::test_roundtrip_retains_text_types_and_validated_media` | R7 · AT6 | PASS (`s2-focused.log`); AST unchanged `1d2118a97d56069a`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 38 | `test_sessions.py:60` `SessionTests.test_atomic_failure_preserves_previous_session` | `960836f6ffb781a3` | 3 | Retain | `tests/test_sessions.py::SessionTests::test_atomic_failure_preserves_previous_session` | R7 · AT6 | PASS (`s2-focused.log`); AST unchanged `960836f6ffb781a3`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 39 | `test_sessions.py:72` `SessionTests.test_corrupt_sessions_and_traversal_are_rejected` | `e9b24bb03f49ee44` | 3 | Retain | `tests/test_sessions.py::SessionTests::test_corrupt_sessions_and_traversal_are_rejected` | R7 · AT6 | PASS (`s2-focused.log`); AST unchanged `e9b24bb03f49ee44`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 40 | `test_sessions.py:87` `SessionTests.test_group_snapshot_recovers_newer_completed_job_state` | `0152366eb0476a81` | 2 | Retain | `tests/test_sessions.py::SessionTests::test_group_snapshot_recovers_newer_completed_job_state` | R7 · AT6 | PASS (`s2-focused.log`); AST unchanged `0152366eb0476a81`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 41 | `test_sessions.py:97` `SessionTests.test_close_and_reopen_at_step4_without_repeating_previous_stages` | `8eae60c7218e3b6a` | 12 | Migrate | `tests/test_sessions.py::SessionTests::test_close_and_reopen_at_step4_without_repeating_previous_stages` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A5 `tabs.currentIndex()` widget read (web screen comes from saved `tab`/`web_draft.screen`) |
| 42 | `test_sessions.py:125` `SessionTests.test_multiple_sessions_restore_edited_text_and_group_selection` | `bc0007a77637b647` | 8 | Migrate | `tests/test_sessions.py::SessionTests::test_multiple_sessions_restore_edited_text_and_group_selection` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A5 current-row focus `group5.selected_id()` (presentation) |
| 43 | `test_sessions.py:151` `SessionTests.test_missing_media_keeps_text_and_reports_missing_files` | `317e2fa4b09b93c7` | 5 | Migrate | `tests/test_sessions.py::SessionTests::test_missing_media_keeps_text_and_reports_missing_files` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A5 `session_status` label text 'Thiếu' (the web shows `missing_artifacts`) |
| 44 | `test_sessions.py:163` `SessionTests.test_busy_session_cannot_be_replaced` | `92d96b203a7b38d9` | 2 | Migrate | `tests/test_sessions.py::SessionTests::test_busy_session_cannot_be_replaced` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 45 | `test_sessions.py:170` `SessionTests.test_failed_save_prevents_close_and_retains_document` | `59edf73f83222376` | 3 | Migrate | `tests/test_sessions.py::SessionTests::test_failed_save_retains_document_and_previous_session` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 window close veto (desktop window lifecycle) |
| 46 | `test_sessions.py:178` `SessionTests.test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id` | `171ea1e0386e96a4` | 5 | Migrate | `tests/test_sessions.py::SessionTests::test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 47 | `test_sessions.py:193` `SessionTests.test_reopening_older_session_keeps_latest_uploaded_story_tags` | `0ed428ea97c9ed2d` | 3 | Migrate | `tests/test_sessions.py::SessionTests::test_reopening_older_session_keeps_latest_uploaded_story_tags` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 48 | `test_sessions.py:203` `SessionTests.test_reopening_youtube_page_preserves_unuploaded_tag_draft` | `73f13f36db917c72` | 3 | Migrate | `tests/test_sessions.py::SessionTests::test_reopening_youtube_page_preserves_unuploaded_tag_draft` | R7 · AT6 | PASS (S2 `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | `stage6_widget.tags_edit.text()` widget read |
| 49 | `test_settings_dialog.py:25` `SettingsDialogTests.test_legacy_translation_settings_are_ignored_safely` | `0dd49b928a0e674d` | 3 | Migrate | `BR::test_legacy_translation_settings_are_ignored_safely` | R10 · AT5/AT6 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 50 | `test_settings_dialog.py:38` `SettingsDialogTests.test_collects_changed_values` | `26728b38b11b4c98` | 8 | Migrate | `BR::test_collects_changed_values` | R10 · AT5/AT6 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1–A4 Qt control types (QSpinBox/QComboBox/QTextEdit/QLineEdit) |
| 51 | `test_settings_dialog.py:60` `SettingsDialogTests.test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit` | `8a1c6e3fd52d4d5e` | 4 | Migrate | `BR::test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit` | R10 · AT5/AT6 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A3 QLineEdit control type |
| 52 | `test_settings_dialog.py:71` `SettingsDialogTests.test_step3_title_history_can_be_remembered_and_removed` | `a2157f0b663c2798` | 5 | Migrate | `BR::test_step3_title_history_can_be_remembered_and_removed` | R10 · AT5/AT6 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1/A5 Step-3 title combo item/edit text |
| 53 | `test_settings_dialog.py:88` `SettingsDialogTests.test_runtime_ui_settings_are_applied` | `7dce893ba8365e3b` | 5 | Migrate | `BR::test_runtime_ui_settings_are_applied` | R10 · AT5/AT6 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 settings button label; A2 native font point size (font geometry retires per §4; value persistence kept); A4 widget identity |
| 54 | `test_settings_dialog.py:98` `SettingsDialogTests.test_log_window_is_detached_and_resizable` | `93c05d729408ddfe` | 7 | Retire desktop only | — | R10 · AT5/AT6 | Retired (desktop only) | O1: Qt window geometry only. |
| 55 | `test_settings_dialog.py:118` `SettingsDialogTests.test_cleaning_settings_affect_step3` | `f49f0dc0f51e6904` | 2 | Migrate | `BR::test_cleaning_settings_affect_step3` | R10 · AT5/AT6 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 56 | `test_step2_ui.py:40` `Step2UiTests.test_step2_is_grouping_and_preserves_chinese_text` | `e2103d2e26e30785` | 8 | Migrate | `BR::test_step2_is_grouping_and_preserves_chinese_text` | R6 · AT5 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1–A3 desktop tab count/titles; A4 tab index; A6/A7 Step-2 output panel labels |
| 57 | `test_step2_ui.py:68` `Step2UiTests.test_copy_all_copies_complete_step2_output` | `b84ef86dfdff341e` | 1 | Retire desktop only | — | R6 · AT5 | Retired (desktop only) | O1: clipboard interaction; complete grouping payload retained by Step2/business and data-flow tests. |
| 58 | `test_step2_ui.py:78` `Step2UiTests.test_copy_all_covers_diagnostics_group_panel_dialog_and_youtube` | `dce736db11169cb3` | 4 | Retire desktop only | — | R6 · AT5 | Retired (desktop only) | O1: clipboard/widget routing; diagnostics, failed-chunk detail and upload URL/state retained in their business cases. |
| 59 | `test_tts_preprocessing.py:59` `PreprocessingTests.test_required_examples_and_idempotence` | `fb46a2e95321ba51` | 3 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_required_examples_and_idempotence` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `fb46a2e95321ba51`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 60 | `test_tts_preprocessing.py:68` `PreprocessingTests.test_full_required_example_and_adjacent_url` | `fac8c43c8205fe0d` | 4 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_full_required_example_and_adjacent_url` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `fac8c43c8205fe0d`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 61 | `test_tts_preprocessing.py:76` `PreprocessingTests.test_double_quote_fallback_matches_step1_policy` | `4aebb5f9ab4ec989` | 6 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_double_quote_fallback_matches_step1_policy` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `4aebb5f9ab4ec989`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 62 | `test_tts_preprocessing.py:94` `PreprocessingTests.test_protected_structures_and_semantics` | `7dce81050968676c` | 1 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_protected_structures_and_semantics` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `7dce81050968676c`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 63 | `test_tts_preprocessing.py:107` `PreprocessingTests.test_unicode_and_entities` | `33387291f6353adb` | 7 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_unicode_and_entities` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `33387291f6353adb`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 64 | `test_tts_preprocessing.py:120` `PreprocessingTests.test_valid_vietnamese_diacritics_are_not_mojibake` | `f5ad61f0a63ffb1b` | 4 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_valid_vietnamese_diacritics_are_not_mojibake` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `f5ad61f0a63ffb1b`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 65 | `test_tts_preprocessing.py:129` `PreprocessingTests.test_mojibake_diagnostics_are_aggregated_and_preserved` | `73b1784e97a6e1bb` | 6 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_mojibake_diagnostics_are_aggregated_and_preserved` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `73b1784e97a6e1bb`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 66 | `test_tts_preprocessing.py:144` `PreprocessingTests.test_chapter_preparation_keeps_chapter_context_in_diagnostics` | `289d894df22aa715` | 3 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_chapter_preparation_keeps_chapter_context_in_diagnostics` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `289d894df22aa715`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 67 | `test_tts_preprocessing.py:153` `PreprocessingTests.test_policies_and_custom_rules` | `7e903cb090a3732c` | 9 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_policies_and_custom_rules` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `7e903cb090a3732c`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 68 | `test_tts_preprocessing.py:171` `PreprocessingTests.test_technical_json_emoji_and_comments` | `f03e429aafc5623d` | 6 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_technical_json_emoji_and_comments` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `f03e429aafc5623d`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 69 | `test_tts_preprocessing.py:182` `PreprocessingTests.test_sentence_per_line` | `303c1411648b0625` | 2 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_sentence_per_line` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `303c1411648b0625`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 70 | `test_tts_preprocessing.py:189` `PreprocessingTests.test_invariants_seeded_mixed_input` | `fd5f7ecaff8d21da` | 4 | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_invariants_seeded_mixed_input` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `fd5f7ecaff8d21da`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 71 | `test_tts_preprocessing.py:206` `BoundaryTests.test_technical_boundaries` | `7f657398241f3781` | 3 | Retain | `tests/test_tts_preprocessing.py::BoundaryTests::test_technical_boundaries` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `7f657398241f3781`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 72 | `test_tts_preprocessing.py:213` `BoundaryTests.test_lossless_chunking_quotes_numbers_and_empty` | `b643867e8151eca0` | 6 | Retain | `tests/test_tts_preprocessing.py::BoundaryTests::test_lossless_chunking_quotes_numbers_and_empty` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `b643867e8151eca0`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 73 | `test_tts_preprocessing.py:225` `BoundaryTests.test_oversized_protected_heading_and_combining` | `140876050f81326b` | 7 | Retain | `tests/test_tts_preprocessing.py::BoundaryTests::test_oversized_protected_heading_and_combining` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `140876050f81326b`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 74 | `test_tts_preprocessing.py:240` `SentencePackingTests.test_pack_sentences_not_short_paragraphs` | `219a769574af3692` | 2 | Retain | `tests/test_tts_preprocessing.py::SentencePackingTests::test_pack_sentences_not_short_paragraphs` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `219a769574af3692`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 75 | `test_tts_preprocessing.py:249` `SentencePackingTests.test_paragraph_break_inside_sentence_does_not_cut_short_sentence` | `42d96896ef02461b` | 1 | Retain | `tests/test_tts_preprocessing.py::SentencePackingTests::test_paragraph_break_inside_sentence_does_not_cut_short_sentence` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `42d96896ef02461b`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 76 | `test_tts_preprocessing.py:256` `SentencePackingTests.test_oversized_sentence_uses_words_before_hard_slicing` | `07119a5fd24b1b87` | 3 | Retain | `tests/test_tts_preprocessing.py::SentencePackingTests::test_oversized_sentence_uses_words_before_hard_slicing` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `07119a5fd24b1b87`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 77 | `test_tts_preprocessing.py:275` `TtsIntegrationTests.test_fixed_700_target_ignores_saved_legacy_sizes` | `050df66c43ac1b39` | 4 | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_fixed_700_target_ignores_saved_legacy_sizes` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `050df66c43ac1b39`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 78 | `test_tts_preprocessing.py:285` `TtsIntegrationTests.test_group_tts_plan_propagates_chapter_mojibake_diagnostics` | `9fcd076964978378` | 2 | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_group_tts_plan_propagates_chapter_mojibake_diagnostics` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `9fcd076964978378`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 79 | `test_tts_preprocessing.py:297` `TtsIntegrationTests.test_preprocessing_before_chunking_and_resume` | `80b621deb513d64d` | 12 | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_preprocessing_before_chunking_and_resume` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `80b621deb513d64d`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 80 | `test_tts_preprocessing.py:328` `TtsIntegrationTests.test_old_cache_overrides_cancel_and_empty` | `1f4dfb7a2a9485fc` | 7 | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_old_cache_overrides_cancel_and_empty` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `1f4dfb7a2a9485fc`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 81 | `test_tts_preprocessing.py:352` `TtsIntegrationTests.test_settings_roundtrip_and_custom_clean` | `fba5c8f3e44d85b9` | 3 | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_settings_roundtrip_and_custom_clean` | R6/R8 · AT5 | PASS (`s2-focused.log`); AST unchanged `fba5c8f3e44d85b9`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 82 | `test_tts_preprocessing.py:374` `LegacyAndUiTests.test_legacy_bundle_client_and_old_provenance` | `092be82f5688b13c` | 9 | Migrate | `tests/test_tts_preprocessing.py::HeadlessLegacyTests::test_legacy_bundle_client_and_old_provenance` | R6/R8 · AT5 | PASS (`s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A6 `window._on_clean_chunk()` button handler (replaced by the web `tts` job) |
| 83 | `test_tts_preprocessing.py:424` `LegacyAndUiTests.test_large_preparation_worker_cancel_and_snapshot` | `4d3481d53d073652` | 9 | Migrate | `tests/test_tts_preprocessing.py::HeadlessLegacyTests::test_large_preparation_worker_cancel_and_snapshot` | R6/R8 · AT5 | PASS (`s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A2/A3/A7 `_tts_prepare_thread` worker-handle reads (job lifecycle replaces them) |
| 84 | `test_tts_preprocessing.py:455` `LegacyAndUiTests.test_config_ui_and_downstream_invalidation` | `8e4b43f8a533065d` | 6 | Migrate. Owner disposition 2026-10-13: expectedFailure with gap id (G1). | `test_tts_preprocessing.py` `HeadlessLegacyTests.test_config_preprocessing_settings_round_trip` (GREEN part) + `HeadlessLegacyTests.test_config_ui_and_downstream_invalidation` (`@unittest.expectedFailure`, G1) | R6/R8 · AT5 | PASS (GREEN part, now including the canonical-byte check) + **XFAIL — gap G1** (`s3-dispositions.log` exit 0; failing assertion :456 in `s3-xfail-reasons.log`, :462 `'Completed' != 'TTS Incomplete'` after the S6 fix in `s6-xfail-reasons.log`; first RED `s2-g1-red.log`); S5 full suite (`pytest-full.xml`): PASS + XFAIL; S6 full suite (`pytest-full-s6.xml`): PASS + XFAIL | Settings-dialog widget writes (replaced by `PUT /api/settings`) |
| 85 | `test_tts_ui.py:23` `TtsUiTests.test_zero_successes_show_root_error_without_merge_dialog` | `73be32e22102af48` | 5 | Migrate | `BR::test_zero_successes_show_root_error_without_merge_dialog` | R8 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 `_FailedChunksDialog` construction and A3 desktop status prefix 'Không tạo được đoạn MP3 nào' (widget text; web shows the group root error `last_error` as its alert, media-screens.tsx:102) |
| 86 | `test_tts_ui.py:43` `TtsUiTests.test_failed_chunk_dialog_shows_original_and_failed_part_text` | `92c70a9966578672` | 4 | Migrate | `BR::test_failed_chunk_dialog_shows_original_and_failed_part_text` | R8 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | Dialog widgets (`merge_button`, `failure_details`, `failure_text`) — the web TTS screen renders `state.failures` (media-screens.tsx:103–108) |
| 87 | `test_tts_ui.py:67` `TtsUiTests.test_worker_bridges_processor_progress_to_qt_signal` | `de539f68aa20345a` | 1 | Migrate | `BR::test_worker_progress_reaches_http_job_snapshot` | R8 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | Qt signal bridge (`_TtsWorker.progress` connection) |
| 88 | `test_video_pages.py:54` `VideoPageTests.test_exact_text_and_measured_timeline` | `ccd38096d498ecb1` | 9 | Retain | `tests/test_video_pages.py::VideoPageTests::test_exact_text_and_measured_timeline` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `ccd38096d498ecb1`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 89 | `test_video_pages.py:68` `VideoPageTests.test_selective_cache_and_audio_only_updates` | `b089e408e2687246` | 7 | Retain | `tests/test_video_pages.py::VideoPageTests::test_selective_cache_and_audio_only_updates` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `b089e408e2687246`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 90 | `test_video_pages.py:96` `VideoPageTests.test_visual_changes_and_corrupted_cache_repaint` | `6fff3a14e2deb391` | 3 | Retain | `tests/test_video_pages.py::VideoPageTests::test_visual_changes_and_corrupted_cache_repaint` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `6fff3a14e2deb391`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 91 | `test_video_pages.py:111` `VideoPageTests.test_each_page_names_only_its_own_chapter` | `5dd8c146d1c4547c` | 9 | Retain | `tests/test_video_pages.py::VideoPageTests::test_each_page_names_only_its_own_chapter` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `5dd8c146d1c4547c`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 92 | `test_video_pages.py:137` `VideoPageTests.test_cjk_brackets_render_visible_ink_on_the_page` | `89313d9be914c326` | 8 | Retain | `tests/test_video_pages.py::VideoPageTests::test_cjk_brackets_render_visible_ink_on_the_page` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `89313d9be914c326`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 93 | `test_video_pages.py:177` `VideoPageTests.test_latin_and_vietnamese_advances_are_unchanged_by_the_fallback` | `09f83f3eb2eaadca` | 4 | Retain | `tests/test_video_pages.py::VideoPageTests::test_latin_and_vietnamese_advances_are_unchanged_by_the_fallback` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `09f83f3eb2eaadca`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 94 | `test_video_pages.py:195` `VideoPageTests.test_invalid_audio_or_request_provenance_is_rejected` | `942a3b16e39761cc` | 2 | Retain | `tests/test_video_pages.py::VideoPageTests::test_invalid_audio_or_request_provenance_is_rejected` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `942a3b16e39761cc`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 95 | `test_video_pages.py:212` `VideoPageTests.test_mismatched_audio_duration_and_cancellation_fail_before_publication` | `67a652bc65a0837c` | 3 | Retain | `tests/test_video_pages.py::VideoPageTests::test_mismatched_audio_duration_and_cancellation_fail_before_publication` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `67a652bc65a0837c`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 96 | `test_video_pages.py:223` `VideoPageTests.test_input_change_during_page_generation_keeps_old_timeline` | `6fcd5e63720f02da` | 2 | Retain | `tests/test_video_pages.py::VideoPageTests::test_input_change_during_page_generation_keeps_old_timeline` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `6fcd5e63720f02da`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 97 | `test_video_pages.py:234` `VideoPageTests.test_readable_layout_bounds_and_line_budget` | `984ebf9622f77eb1` | 19 | Retain | `tests/test_video_pages.py::VideoPageTests::test_readable_layout_bounds_and_line_budget` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `984ebf9622f77eb1`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 98 | `test_video_pages.py:286` `VideoPageTests.test_paragraph_breaks_compress_before_a_page_fails` | `5c25172f46da31ff` | 8 | Retain | `tests/test_video_pages.py::VideoPageTests::test_paragraph_breaks_compress_before_a_page_fails` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `5c25172f46da31ff`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 99 | `test_video_pages.py:306` `VideoPageTests.test_reclaimed_bottom_margin_absorbs_the_reported_three_pixel_overflow` | `fc8d65b072ec1b71` | 6 | Retain | `tests/test_video_pages.py::VideoPageTests::test_reclaimed_bottom_margin_absorbs_the_reported_three_pixel_overflow` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `fc8d65b072ec1b71`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 100 | `test_video_pages.py:323` `VideoPageTests.test_gap_ladder_always_keeps_the_requested_gap_first` | `af293645c7385f15` | 3 | Retain | `tests/test_video_pages.py::VideoPageTests::test_gap_ladder_always_keeps_the_requested_gap_first` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `af293645c7385f15`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 101 | `test_video_pages.py:329` `VideoPageTests.test_nonfinite_audio_metadata_rejected` | `24f0bd5b70d98ea7` | 1 | Retain | `tests/test_video_pages.py::VideoPageTests::test_nonfinite_audio_metadata_rejected` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `24f0bd5b70d98ea7`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 102 | `test_video_pages.py:338` `VideoPageTests.test_mp3_playable_duration_uses_exact_packet_ticks_and_padding` | `8b3eeadf09cbf512` | 1 | Retain | `tests/test_video_pages.py::VideoPageTests::test_mp3_playable_duration_uses_exact_packet_ticks_and_padding` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `8b3eeadf09cbf512`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 103 | `test_video_pages.py:353` `RealVfrTests.test_real_mp3_merge_and_fractional_static_pages` | `a2ed666eda1cd82f` | 10 | Migrate | `tests/test_video_pages.py::RealVfrTests::test_real_mp3_merge_and_fractional_static_pages` | R8 · AT7 | PASS (`s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A6/A7 Qt signal collection (`failed`/`completed` lists) — `render_video` raises on failure and returns one result |
| 104 | `test_video_pages.py:447` `RealVfrTests.test_single_page_holds_to_the_end_at_44100hz` | `c582526d33ef9cf9` | 3 | Retain | `tests/test_video_pages.py::RealVfrTests::test_single_page_holds_to_the_end_at_44100hz` | R8 · AT7 | PASS (`s2-focused.log`); AST unchanged `c582526d33ef9cf9`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 105 | `test_video_preview.py:20` `SidePanelGeometryTests.test_slots_are_fixed_305_squares_flush_in_the_frame_corners` | `b51a4b0dacf52d86` | 14 | Retain | `tests/test_video_preview.py::SidePanelGeometryTests::test_slots_are_fixed_305_squares_flush_in_the_frame_corners` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `b51a4b0dacf52d86`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 106 | `test_video_preview.py:76` `SidePanelRenderTests.test_cover_and_qr_keep_their_pixels_without_background` | `5c2b0f64fe7f02c0` | 11 | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_cover_and_qr_keep_their_pixels_without_background` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `5c2b0f64fe7f02c0`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 107 | `test_video_preview.py:96` `SidePanelRenderTests.test_wide_cover_is_letterboxed_instead_of_cropped` | `33562709d6be5d21` | 4 | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_wide_cover_is_letterboxed_instead_of_cropped` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `33562709d6be5d21`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 108 | `test_video_preview.py:110` `SidePanelRenderTests.test_transparent_qr_has_no_card_just_composited_pixels` | `64996260358482d5` | 3 | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_transparent_qr_has_no_card_just_composited_pixels` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `64996260358482d5`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 109 | `test_video_preview.py:123` `SidePanelRenderTests.test_pictures_never_intersect_the_text_column` | `0fbd504199db9aa3` | 4 | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_pictures_never_intersect_the_text_column` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `0fbd504199db9aa3`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 110 | `test_video_preview.py:135` `SidePanelRenderTests.test_text_layout_is_identical_with_or_without_pictures` | `130c940c26b4094c` | 1 | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_text_layout_is_identical_with_or_without_pictures` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `130c940c26b4094c`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 111 | `test_video_preview.py:142` `SidePanelRenderTests.test_missing_picture_is_reported_instead_of_silently_skipped` | `440a7bee09492798` | 1 | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_missing_picture_is_reported_instead_of_silently_skipped` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `440a7bee09492798`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 112 | `test_video_preview.py:170` `SidePanelTimelineTests.test_both_picture_inputs_are_required_before_any_page` | `fb0b4e03b386261e` | 3 | Retain | `tests/test_video_preview.py::SidePanelTimelineTests::test_both_picture_inputs_are_required_before_any_page` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `fb0b4e03b386261e`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 113 | `test_video_preview.py:184` `SidePanelTimelineTests.test_changing_a_picture_repaints_and_updates_the_source_fingerprint` | `155a3edd4170a580` | 4 | Retain | `tests/test_video_preview.py::SidePanelTimelineTests::test_changing_a_picture_repaints_and_updates_the_source_fingerprint` | R11 · AT7/AT9 | PASS (`s2-focused.log`); AST unchanged `155a3edd4170a580`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 114 | `test_video_preview.py:220` `VideoPreviewTests.test_build_page_preview_renders_a_real_full_frame` | `9ee3178106794180` | 3 | Migrate | `tests/test_video_preview.py::WebPreviewRegressionTests::test_prepared_preview_renders_real_full_frame` | R11 · AT7/AT9 | PASS (`s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 115 | `test_video_preview.py:229` `VideoPreviewTests.test_build_page_preview_falls_back_to_sample_text` | `c9154884832b5c53` | 2 | Retire desktop only | — | R11 · AT7/AT9 | Retired (O1 desktop-only) | O1: desktop sample/fallback preview explicitly retired; AT9 rejects missing prepared inputs. |
| 116 | `test_video_preview.py:236` `VideoPreviewTests.test_first_page_text_uses_the_plan_or_the_sample` | `d57bb587d26129cd` | 1 | Retire desktop only | — | R11 · AT7/AT9 | Retired (O1 desktop-only) | O1: obsolete desktop helper/sample choice; prepared effective narration/provenance covered by AT9. |
| 117 | `test_video_preview.py:239` `VideoPreviewTests.test_dialog_shows_the_whole_rendered_frame` | `560d5652287d42d9` | 2 | Retire desktop only | — | R11 · AT7/AT9 | Retired (O1 desktop-only) | O1: Qt dialog presentation; actual full-frame rendering retained. |
| 118 | `test_video_ui.py:57` `VideoUiTests.test_step4_uses_current_step3_paths_without_upload_controls` | `88d53a8e8bb01715` | 7 | Migrate | `BR::test_step4_uses_current_step3_paths_without_upload_controls` | R8 · AT7 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A2 `tabs.currentIndex()`; A1 continue-button enabled state (replaced by an accepted, completed video job) |
| 119 | `test_video_ui.py:75` `VideoUiTests.test_step5_progress_is_visible_and_video_state_invalidates` | `a214be1f4e23dd10` | 4 | Migrate | `BR::test_step5_progress_is_visible_and_video_state_invalidates` | R8 · AT7 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 create-button state; A3 exact desktop label formatting '5.00x' (web log reports the same FFmpeg speed with one decimal) |
| 120 | `test_video_ui.py:102` `VideoUiTests.test_create_video_is_blocked_until_both_page_images_are_added` | `17af1f8b82654194` | 5 | Migrate | `BR::test_create_video_is_blocked_until_both_page_images_are_added` | R8 · AT7 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 create-button state and A2 desktop inputs label 'Bắt buộc Add đủ 2 ảnh' (web form blocks with 'Chọn ảnh bìa'/'Chọn ảnh QR', media-screens.tsx:141); A4 desktop wording 'Add both page images' → core message |
| 121 | `test_video_ui.py:124` `VideoUiTests.test_cancel_during_async_page_preparation_preserves_old_video` | `f0b305022cd19a4a` | 6 | Migrate | `BR::test_cancel_during_async_page_preparation_preserves_old_video` | R8 · AT7 | PASS (`s3.log`); repeated 5× locally, stop observed after page 1/16; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A5 `preparation_thread` handle; Qt cancelled/failed signal lists |
| 122 | `test_youtube_title_tags.py:51` `UploadedTitleTagTests.test_completed_upload_saves_story_tags_and_next_video_loads_them` | `c56225164e0733ff` | 5 | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_completed_upload_saves_story_tags_and_next_video_loads_them` | R9 · AT8 | PASS (S2 `s2-title-tags.log`, `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | `saved_titles_combo.findText`, `tags_edit.text()` widget reads |
| 123 | `test_youtube_title_tags.py:75` `UploadedTitleTagTests.test_failure_does_not_save_draft_tags` | `920333306af55ccf` | 2 | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_failure_does_not_save_draft_tags` | R9 · AT8 | PASS (S2 `s2-title-tags.log`, `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 124 | `test_youtube_title_tags.py:91` `UploadedTitleTagTests.test_existing_completed_upload_is_imported_when_its_story_is_opened` | `c14c76faba184ffd` | 2 | Owner disposition 2026-10-13: whole test kept as `@unittest.expectedFailure` with gap id G2 (both assertions are the gap). | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_existing_completed_upload_is_imported_when_its_story_is_opened` | R9 · AT8 | **XFAIL — gap G2** (`s3-dispositions.log` exit 0; failing assertion :71 in `s3-xfail-reasons.log`, :72 `None != ['tag cũ']` on the live `service.settings` after the S6 fix in `s6-xfail-reasons.log`; positive control `s6-g2-fix-control.log`; first RED `s2-g2-red.log`); S5 full suite (`pytest-full.xml`): XFAIL; S6 full suite (`pytest-full-s6.xml`): XFAIL | — |
| 125 | `test_youtube_title_tags.py:107` `UploadedTitleTagTests.test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title` | `d5a0940df834b920` | 2 | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title` | R9 · AT8 | PASS (S2 `s2-title-tags.log`, `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | `tags_edit.text()` widget read |
| 126 | `test_youtube_title_tags.py:122` `UploadedTitleTagTests.test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags` | `49e010982246c169` | 3 | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags` | R9 · AT8 | PASS (S2 `s2-title-tags.log`, `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | `panel.editor.tags_edit.text()` widget reads (A1/A3 display) |
| 127 | `test_youtube_title_tags.py:152` `UploadedTitleTagTests.test_group_upload_uses_story_tags_and_records_confirmed_result` | `c1a9a7b8307617fb` | 4 | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_group_upload_uses_story_tags_and_records_confirmed_result` | R9 · AT8 | PASS (S2 `s2-title-tags.log`, `s2-focused.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | `panel.editor.tags_edit.text()` widget read (A1) |
| 128 | `test_youtube_title_tags.py:179` `UploadedTitleTagTests.test_unrelated_stories_keep_separate_tags_and_bad_config_is_ignored` | `dde553cc5647eb0a` | 4 | Retain | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_unrelated_stories_keep_separate_tags_and_bad_config_is_ignored` | R9 · AT8 | PASS (`s2-focused.log`); AST unchanged `dde553cc5647eb0a`; S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 129 | `test_youtube_ui.py:79` `YouTubeUiTests.test_connect_uses_changed_oauth_settings_without_reentering_tab` | `1f4fb94b1d478512` | 3 | Migrate | `BR::test_connect_uses_changed_oauth_settings_without_reentering_tab` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 130 | `test_youtube_ui.py:90` `YouTubeUiTests.test_configured_oauth_without_saved_login_explains_sign_in` | `231b1c96133b7bc8` | 4 | Migrate | `BR::test_configured_oauth_without_saved_login_explains_sign_in` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1 account label text, A3/A4 button enablement (widget state) |
| 131 | `test_youtube_ui.py:99` `YouTubeUiTests.test_group_connection_error_visible_beside_account` | `1cc9ac4a811bb278` | 5 | Migrate | `BR::test_group_connection_error_visible_beside_account` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A2–A4 hint/status/dialog visibility |
| 132 | `test_youtube_ui.py:114` `YouTubeUiTests.test_connect_without_config_displays_error_dialog` | `42f7e03a0210cb6f` | 3 | Migrate | `BR::test_connect_without_config_displays_error_dialog` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A2 dialog visibility |
| 133 | `test_youtube_ui.py:122` `YouTubeUiTests.test_continue_and_direct_navigation_share_automatic_inputs_and_metadata` | `9aef8c90fa7ecc81` | 12 | Uses 2 groups so the stale check is not short-circuited by the completed-upload guard (pipeline/media_service.py:456). Observation, not a gap (the baseline asserted only the exception type): web hides the PipelineStateError text behind the generic 'YouTube operation failed. Check the connection…' (pipeline/media_service.py:387-392, 587). | `BR::test_continue_and_direct_navigation_share_automatic_inputs_and_metadata` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1/A2 tab count/index, A8 privacy combo labels, A9 button enablement, A10 absence of select/save buttons (the web screen has no manual file pickers) |
| 134 | `test_youtube_ui.py:143` `YouTubeUiTests.test_progress_completion_copy_url_and_duplicate_confirmation` | `ad7476f4fd372e0c` | 12 | G4: frontend/src/screens/youtube-screen.tsx:114 sends allow_duplicate; backend/validation.py:66 omits it, so :85 rejects it; the core honours it at pipeline/media_service.py:456. A10's exact text 'This job has already been uploaded' (media/youtube.py:349) is not reachable on the web path, which returns status 'skipped' first; covered by the skipped status. Owner disposition 2026-10-13: expectedFailure with gap id. | `BR::test_progress_completion_copy_url_and_duplicate_confirmation` (GREEN part) + `BR::test_confirmed_duplicate_upload_creates_new_video` (`@unittest.expectedFailure`, G4) | R9 · AT8 | PASS (GREEN part) + **XFAIL — gap G4** (`s3-dispositions.log` exit 0; real failing assertion in `s3-xfail-reasons.log`: :1047 POST upload {allow_duplicate: true} → 422 'Tùy chọn không được hỗ trợ: allow_duplicate' != 202); S5 full suite (`pytest-full.xml`): PASS + XFAIL; S6 full suite (`pytest-full-s6.xml`): PASS + XFAIL | A1/A2/A5 progress-bar value/speed formatting, A6–A9 widget enablement/visibility/parent, A11 clipboard |
| 135 | `test_youtube_ui.py:173` `YouTubeUiTests.test_ai_checkbox_uploads_both_values_and_restores_saved_choice` | `6486dc7fad86074d` | 4 | The baseline uploaded the same job twice with allow_duplicate; that is unavailable over HTTP (G4), so two groups carry the two values. | `BR::test_ai_checkbox_uploads_both_values_and_restores_saved_choice` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | — |
| 136 | `test_youtube_ui.py:190` `YouTubeUiTests.test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry` | `c7224ad639db01b6` | 6 | Migrate | `BR::test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1/A4/A5 button enablement |
| 137 | `test_youtube_ui.py:206` `YouTubeUiTests.test_bad_metadata_never_starts_worker_and_schedule_requires_private` | `bded52ff5cee9dd5` | 5 | Migrate | `BR::test_bad_metadata_never_starts_worker_and_schedule_requires_private` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A1/A4 `tab.busy` (the web job runs on the worker but fails validation before any Google call) |
| 138 | `test_youtube_ui.py:220` `YouTubeUiTests.test_standalone_resume_preserves_saved_metadata_and_past_schedule` | `0dc13bd2d7a2319c` | 7 | The baseline re-uploaded the same job with allow_duplicate (G4); a fresh group exercises the same require_future validation. | `BR::test_standalone_resume_preserves_saved_metadata_and_past_schedule` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A6 `tab.busy` |
| 139 | `test_youtube_ui.py:261` `YouTubeUiTests.test_api_worker_keeps_ui_responsive_and_cancel_saves_session` | `1f93e3ac0510e312` | 9 | The literal 8388608 came from overwriting the MP4 with 8 MiB+1 bytes. Web require_video rejects a modified video by fingerprint, so the real rendered MP4 is used with a half-size 308 Range; the invariant (bytes_sent == confirmed range) is unchanged. | `BR::test_api_worker_keeps_ui_responsive_and_cancel_saves_session` | R9 · AT8 | PASS (`s3.log`); S5 full suite (`pytest-full.xml`): PASS; S6 full suite (`pytest-full-s6.xml`): PASS | A3/A8 tab enablement, A4 QTimer tick, A9 button enablement; window-close trigger → `POST /api/jobs/{id}/stop` |

## Assertion-group trace

Each baseline assertion is listed in source order (whitespace-collapsed, truncated at 160 chars). For migrated/retired rows, the trace states where each assertion group now lives and which presentation-only assertions retire. Retained rows are verified by unchanged method AST.


### `tests/test_group_batches.py` (baseline SHA-256 `12dfa8c4d98ab31d5f0e27d4df79e806640748c4b2dfa94957021a6b04532d97`)

<details><summary>#1 <code>GroupBatchTests.test_step3_active_ui_creates_groups_not_tts</code> — Migrate</summary>

1. `self.assertEqual(window._selected_group_size(), 10)`
2. `self.assertIn('Detected chapters: 3', window.stage3_detection_label.text())`
3. `self.assertEqual(len(self.doc.chapter_groups), 1)`
4. `self.assertEqual(self.doc.chunks, [])`
5. `self.assertEqual(window.stage4_stack.currentWidget(), window.group4)`
6. `self.assertFalse(window.group4.checked_ids())`
7. `self.assertIn('Chương 1', window.group4.first_chapter.toPlainText())`

**Trace:** Real import+normalize, `GET /api/grouping?size=10`, then real `group` job with `cleaning.textclean.clean_text` guarded. A2 → preview `headings` length 3; A3 → `group_ids` length 1; A4 → `service.document.chunks == []` and no `tts_plan` in state; A7 → state group `chapters[0].heading` and group txt contain 'Chương 1'.

</details>

<details><summary>#2 <code>GroupBatchTests.test_step3_numeric_boundary_confirmation_and_unavailable_boundary</code> — Migrate</summary>

1. `self.assertIn('Some chapter numbers are missing.', window.stage3_output.toPlainText())`
2. `self.assertIn('601-620', window.stage3_output.toPlainText())`
3. `self.assertFalse(numeric_doc.chapter_groups)`
4. `self.assertEqual([group.range_label for group in numeric_doc.chapter_groups], ['601-620', '621-640', '641-660', '661-680', '681-700'])`
5. `self.assertIn('Missing required group-start heading', window.stage3_output.toPlainText())`
6. `self.assertFalse(window.stage3_create_groups_btn.isEnabled())`

**Trace:** Import `numeric_source({620})`. A1 → preview `requires_numeric_boundaries` true + 'Numbering gap' warning; A2 → preview groups include '601-620'; A3 → `group` job with `method=numeric_boundaries` and no confirmation fails ('confirmation') and state has no groups; A4 → with preview `confirmation_fingerprint` range labels equal baseline list. Import `numeric_source({621})`: A5 → preview `error` contains 'Missing required group-start heading'; A6 → `numeric_available` false, no groups, and a numeric `group` job fails with the same error, no groups.

</details>

<details><summary>#3 <code>GroupBatchTests.test_defaults_and_select_all_subset_snapshot</code> — Migrate</summary>

1. `self.assertEqual(panel.checked_ids(), [])`
2. `self.assertEqual([row[0] for row in panel.visited], [self.groups[0].group_id, self.groups[2].group_id])`
3. `self.assertTrue(all(row[1] == 'vi-VN-HoaiMyNeural' for row in panel.visited))`
4. `self.assertEqual(panel.overall_progress.value(), 1000)`
5. `self.assertFalse(panel.checked_ids())`

**Trace:** Real `tts` job for [g0,g2] with a gated fake Edge-TTS client; after start the live `service.settings.tts_voice` is mutated and `PUT /api/settings` returns 409. A2 → request texts map to groups in order [g0,g2] and result rows are [g0,g2]; A3 → every request voice 'vi-VN-HoaiMyNeural'; A4 → final job progress done == total.

</details>

<details><summary>#4 <code>GroupBatchTests.test_group_failure_continues_cancel_stops_future_groups</code> — Migrate</summary>

1. `self.assertEqual(len(panel.visited), 2)`
2. `self.assertIn('Group-specific failure', panel.result.toPlainText())`

**Trace:** Real `tts` job for all 3 groups; g0 requests raise RuntimeError('Group-specific failure'), g1 is gated and the job is stopped via `POST /api/jobs/{id}/stop`. A1 → requests touched exactly {g0,g1}, result rows [(g0,failed),(g1,cancelled)], g2 never called, `result.cancelled` true (job status 'failed' because a failed row outranks cancel); A2 → g0 state `failures[].error_message` contains 'Group-specific failure'.

</details>

<details><summary>#5 <code>GroupBatchTests.test_tts_incomplete_continues_and_resume_keeps_canonical_files</code> — Migrate</summary>

1. `self.assertEqual([g.state['tts_status'] for g in self.groups], ['TTS Incomplete', 'Completed', 'Completed'])`
2. `self.assertFalse(Path(self.groups[0].output_dir, self.groups[0].slug + '_audiobook.mp3').exists())`
3. `self.assertTrue(self.groups[0].state['failures'])`
4. `self.assertEqual(before, [Path(g.txt_path).read_bytes() for g in self.groups])`
5. `self.assertEqual(len(calls), count)`
6. `self.assertIn('TTS Incomplete', panel.status_for(self.groups[0]))`
7. `self.assertEqual(first.state['tts_status'], 'Completed')`
8. `self.assertEqual(calls[count:], ['Corrected speech.'])`
9. `self.assertEqual(before[0], Path(first.txt_path).read_bytes())`

**Trace:** Retries lowered via `PUT /api/settings` (baseline set retry=fallback=1). Fake client fails 'Trời mưa' text. A1 → statuses ['TTS Incomplete','Completed','Completed']; A2 → no `<slug>_audiobook.mp3` (and no audiobook.mp3); A3 → failures non-empty; A4 → txt bytes unchanged; A5 → rerun `tts` [g1] adds no requests; A6 → g0 still 'TTS Incomplete'; `edit_chunk` job (saves override + retries) → A7 'Completed', A8 new requests == ['Corrected speech.'], A9 g0 txt bytes unchanged.

</details>

<details><summary>#6 <code>GroupBatchTests.test_zero_audio_partial_merge_rejected_without_dialog</code> — Migrate</summary>

1. `self.assertIn('valid audio', panel.status.text())`

**Trace:** `merge_partial` (`allow_partial: true`) on a group with no audio: job failed; A1 → row error contains 'valid audio'; no Edge-TTS request, no audiobook.mp3.

</details>

<details><summary>#7 <code>GroupBatchTests.test_partial_merge_is_explicit_and_records_missing_numbers</code> — Migrate</summary>

1. `self.assertGreater(len(processor.chunks), 1)`
2. `self.assertFalse(Path(group.output_dir, 'audiobook.mp3').exists())`
3. `self.assertEqual(group.state['tts_status'], 'Partial')`
4. `self.assertEqual(group.state['excluded_chunks'], list(range(2, len(processor.chunks) + 1)))`
5. `self.assertTrue(manifest['partial_audiobook'])`
6. `self.assertEqual(manifest['excluded_chunks'], group.state['excluded_chunks'])`

**Trace:** Real `tts` for g0 where only chunk 1 succeeds. A1 → manifest `ordered_chunks` > 1; A2 → `merge_partial` with `allow_partial: false` → 422 and no audiobook.mp3; with `true`: A3 'Partial'; A4 `excluded_chunks == range(2, n+1)`; A5 manifest `partial_audiobook`; A6 manifest `excluded_chunks` equals state.

</details>

<details><summary>#8 <code>GroupBatchTests.test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks</code> — Migrate</summary>

1. `self.assertEqual(self.groups[index].state['thumbnail_source'], str(cover))`
2. `self.assertEqual(thumbnail.size, (1280, 720))`
3. `self.assertEqual(thumbnail.format, 'JPEG')`
4. `self.assertEqual(thumbnail.getpixel((10, 10)), expected)`
5. `self.assertIn('thumbnail', group.state)`
6. `self.assertFalse(Path(self.groups[1].output_dir, 'thumbnail.jpg').exists())`
7. `self.assertTrue(panel.thumbnail.pixmap().isNull())`
8. `self.assertIn('No thumbnail selected', panel.thumbnail.text())`
9. `self.assertIn('thumbnail', self.groups[1].state)`
10. `self.assertEqual(restored.chapter_groups[0].state['thumbnail_source'], str(self.root / 'red.png'))`
11. `self.assertEqual(restored.chapter_groups[2].state['thumbnail_source'], str(self.root / 'blue.png'))`

**Trace:** Real `thumbnail` jobs per group. A1 → `thumbnail_source` == resolved red/blue path; A2–A4 → 1280×720 JPEG, pixel (10,10) (254,0,0)/(0,0,254); A5 → `thumbnail` in state; A6 → g1 has no thumbnail.jpg; A9 → `thumbnail` job on g1 regardless of selection adds `thumbnail`; A10/A11 → after save session, `close_app`/`open_app` restart and `POST /api/sessions/{id}/open`, sources preserved.

</details>

<details><summary>#9 <code>GroupBatchTests.test_damaged_group_does_not_block_entry_or_other_batch_jobs</code> — Migrate</summary>

1. `self.assertEqual(panel.visited, [self.groups[0].group_id, self.groups[2].group_id])`
2. `self.assertIn('externally modified', panel.summary[1])`
3. `self.assertEqual(len(panel.summary), 3)`

**Trace:** g1 txt externally changed; `GET /api/state` 200; real `tts` on all 3. A1 → requests visit [g0,g2]; A2 → result row[1] error contains 'externally modified'; A3 → 3 result rows.

</details>

<details><summary>#10 <code>GroupBatchTests.test_step3_can_delete_any_group_and_refresh_later_stages</code> — Migrate</summary>

1. `self.assertEqual(window.tabs.currentIndex(), 2)`
2. `self.assertTrue(panel.first_chapter.toPlainText() == '')`
3. `self.assertTrue(panel.thumbnail.pixmap().isNull())`
4. `self.assertFalse(panel.checked_ids())`
5. `self.assertEqual(stage.groups.count(), 2)`
6. `self.assertNotIn(self.groups[2].group_id, [stage.groups.item(i).data(Qt.ItemDataRole.UserRole) for i in range(2)])`
7. `self.assertTrue(Path(self.groups[2].txt_path).exists())`
8. `self.assertEqual(self.doc.require_chapter_groups(), self.doc.chapter_groups)`
9. `self.assertEqual(window.group5.groups.count(), 0)`
10. `self.assertEqual(window.group6.groups.count(), 0)`
11. `self.assertIsNone(window.group6.editor.media)`
12. `self.assertFalse(window.group6.editor.state)`
13. `self.assertEqual(window.group6.editor.thumbnail_label.text(), '—')`
14. `self.assertFalse(panel.cover_btn.isEnabled())`
15. `self.assertFalse(panel.delete_btn.isEnabled())`
16. `self.assertTrue(panel.first_chapter.toPlainText() == '')`
17. `self.assertEqual(window.stage4_stack.currentWidget(), panel)`

**Trace:** g2 txt damaged; `GET /api/state` 200 with 3 groups (entry not blocked). `delete_group` g2: A5/A6 → 2 groups, g2 id absent; A7 → g2 txt still exists; A8 → `document.require_chapterstate()['groups'] == document.chapter_groups`. Delete the rest: A9/A10 → state `groups == []` (one shared list feeds all later web steps); A11/A12 → no stale group/media/youtube state remains in the snapshot.

</details>

<details><summary>#11 <code>GroupBatchTests.test_step4_busy_blocks_image_selection_and_group_deletion</code> — Migrate</summary>

1. `self.assertFalse(panel.cover_btn.isEnabled())`
2. `self.assertFalse(panel.delete_btn.isEnabled())`
3. `self.assertEqual(len(self.doc.chapter_groups), 3)`

**Trace:** Gated real `tts` job running. A1 → `thumbnail` job submit → 409 (and g1 has no `thumbnail_source`); A2 → `delete_group` submit → 409; A3 → 3 groups remain after the job completes.

</details>

<details><summary>#12 <code>GroupBatchTests.test_progress_visible_and_busy_blocks_other_stages</code> — Migrate</summary>

1. `self.assertEqual(window.group4.progress.value(), 500)`
2. `self.assertEqual(window.group4.overall_progress.value(), 167)`
3. `self.assertFalse(window.group4.progress.isHidden())`
4. `self.assertFalse(window.load_btn.isEnabled())`
5. `self.assertFalse(window.tabs.isTabEnabled(2))`
6. `self.assertFalse(window.tabs.isTabEnabled(5))`

**Trace:** Real `tts` on 3 groups with g0 chunk 2 gated. A1 → job progress (500, 3000): current group 500‰; A2 → overall round(500*1000/3000)=167; A4 → `import` submit 409; A5 → `group` (Step 3) submit 409; A6 → `video` submit 409.

</details>

<details><summary>#13 <code>GroupBatchTests.test_upload_metadata_frozen_individually_completed_skipped</code> — Migrate</summary>

1. `self.assertEqual(captured[0].title, 'Frozen title')`
2. `self.assertEqual(captured[0].description, 'saved')`
3. `self.assertFalse(captured[0].contains_synthetic_media)`
4. `self.assertEqual(captured[1].title, 'Individual second title')`
5. `self.assertEqual(captured[1].description, 'New shared description')`
6. `self.assertTrue(captured[1].contains_synthetic_media)`
7. `self.assertTrue(captured[2].contains_synthetic_media)`
8. `self.assertIn('already uploaded', panel.result.toPlainText())`
9. `self.assertIn('using saved metadata', panel.status_for(first))`

**Trace:** g0 has a completed youtube_upload.json with frozen UploadMetadata('Frozen title','saved'); real video for g1/g2; real `upload` job with shared `{description:'New shared description', contains_synthetic_media:true}` and `titles[g1]`. A1–A3 → g0 record metadata unchanged (title/description/synthetic False); A4–A6 → first created snippet title 'Individual second title', description 'New shared description', `status.containsSyntheticMedia` true; A7 → second created snippet synthetic true; A8 → g0 row `status: skipped` ('already uploaded'); A9 → g0 row youtube metadata title 'Frozen title' ('using saved metadata').

</details>

<details><summary>#14 <code>GroupBatchTests.test_auth_failure_pauses_remaining_queue</code> — Migrate</summary>

1. `self.assertTrue(panel.paused)`
2. `self.assertFalse(panel.running)`
3. `self.assertEqual(len(panel.queue), 3)`
4. `self.assertIn('Reconnect', panel.status.text())`

**Trace:** Real `upload` on 3 groups; transport returns 401. GREEN: A4 → only g0 attempted, row error contains 'Reconnect'; A2 → no group completed. XFAIL G3: A1 → job status 'paused'; A3 → `result.queue` of 3.

</details>

<details><summary>#15 <code>GroupBatchTests.test_paused_batch_shared_edits_affect_only_unstarted_sessions</code> — Migrate</summary>

1. `self.assertTrue(panel.paused)`
2. `self.assertEqual(captured[0].description, 'Frozen description')`
3. `self.assertFalse(captured[0].contains_synthetic_media)`
4. `self.assertEqual(captured[1].description, 'Changed while paused')`
5. `self.assertEqual(captured[2].description, 'Changed while paused')`
6. `self.assertTrue(captured[1].contains_synthetic_media)`
7. `self.assertTrue(captured[2].contains_synthetic_media)`

**Trace:** g0 has a pending 'uploading' record with frozen description 'Frozen description' + saved resumable session; first `upload` job hits 401 ('Reconnect'). A second `upload` job (stand-in for resume) with shared 'Changed while paused' + synthetic true completes: A2/A3 → g0 record keeps 'Frozen description', synthetic False; A4–A7 → g1/g2 created snippets description 'Changed while paused', synthetic true. A1 → first job status 'paused' (RED).

</details>

<details><summary>#16 <code>GroupBatchTests.test_sequential_upload_engine_continues_after_group_failure</code> — Migrate</summary>

1. `self.assertIn('Failed', panel.summary[0])`
2. `self.assertIn('completed', panel.summary[1])`
3. `self.assertEqual(json.loads(Path(self.groups[1].output_dir, 'youtube_upload.json').read_text())['video_id'], 'abc123')`
4. `self.assertFalse(Path(self.groups[2].output_dir, 'youtube_upload.json').exists())`

**Trace:** Real `upload` on [g0,g1]; transport 403 then START/COMPLETE/thumbnail. A1 → row[0] status 'failed'; A2 → row[1] status 'completed'; A3 → g1 youtube_upload.json video_id 'abc123'; A4 → g2 has no youtube_upload.json.

</details>

<details><summary>#17 <code>GroupBatchTests.test_video_current_output_skip_and_sequential_subset</code> — Migrate</summary>

1. `self.assertEqual(seen, [self.groups[1].group_id])`

**Trace:** Real video for g1 only, then a second `video` job [g1]. A1 → result rows [(g1,'skipped')] (current verified MP4); only g1 has an MP4.

</details>

<details><summary>#18 <code>GroupBatchTests.test_video_refuses_to_start_without_both_page_inputs</code> — Migrate</summary>

1. `self.assertEqual(seen, [])`
2. `self.assertFalse(panel.busy)`
3. `self.assertFalse(panel.start_btn.isEnabled())`
4. `self.assertIn('Bắt buộc Add đủ 2 ảnh', panel.inputs_status.text())`
5. `self.assertTrue(panel.start_btn.isEnabled())`
6. `self.assertIn('Đã đủ 2 ảnh input', panel.inputs_status.text())`

**Trace:** Media-ready g0. `video` with no images and with only a cover: A1 → job failed, no `video` state, no MP4 rendered; A2 → no job left running (`/api/jobs` all terminal). With both images the job completes and `video` is recorded.

</details>

<details><summary>#19 <code>GroupBatchTests.test_video_process_group_refuses_without_inputs_and_records_them_after</code> — Migrate</summary>

1. `self.assertRaisesRegex(PipelineStateError, 'page images')`
2. `self.assertEqual(Path(record['cover']['file']).name, 'cover.png')`
3. `self.assertEqual(record['cover']['sha256'], sha256_file(Path(group.output_dir) / record['cover']['file']))`
4. `self.assertTrue(Path(group.output_dir, 'visuals.json').is_file())`
5. `self.assertEqual(Path(images['cover']).read_bytes(), Path(cover).read_bytes())`
6. `self.assertEqual(Path(images['qr']).read_bytes(), Path(qr).read_bytes())`
7. `self.assertEqual(group.state['visuals']['sources'], {'cover': str(Path(cover).resolve()), 'qr': str(Path(qr).resolve())})`

**Trace:** Media-ready g0 ('Completed'). A1 → `video` without inputs fails before render (no `video` state) with the core refusal 'Missing the 1:1 (left) image for the video pages'. Then a real `video` with both images: A2 → visuals.json cover file name 'cover.png'; A3 → sha256 matches copied file; A4 → visuals.json exists; A5/A6 → `available_images` bytes equal sources; A7 → state `visuals.sources` resolved paths.

</details>

<details><summary>#20 <code>VideoMetadataUpdateTests.test_metadata_update_preserves_unrelated_fields_and_frozen_insertion</code> — Move unchanged</summary>

1. `self.assertEqual(session.calls[1][0], 'PUT')`
2. `self.assertEqual(body['snippet']['defaultLanguage'], 'vi')`
3. `self.assertEqual(body['snippet']['defaultAudioLanguage'], 'vi')`
4. `self.assertEqual(body['status']['license'], 'creativeCommon')`
5. `self.assertFalse(body['status']['embeddable'])`
6. `self.assertTrue(body['status']['containsSyntheticMedia'])`
7. `self.assertEqual(result['metadata']['title'], 'Original')`
8. `self.assertEqual(result['updated_metadata']['title'], 'New')`
9. `self.assertTrue(result['updated_metadata']['contains_synthetic_media'])`
10. `self.assertEqual(result['playlist_id'], 'playlist')`

**Trace:** `VideoMetadataUpdateTests.test_metadata_update_preserves_unrelated_fields_and_frozen_insertion` moved verbatim into `tests/test_youtube.py` (class appended unchanged; AST equality checked against the baseline in `s3-retained-ast.json`). Fake transport only; every metadata/atomic-write assertion is preserved.

</details>

<details><summary>#21 <code>VideoMetadataUpdateTests.test_metadata_update_can_clear_ai_disclosure</code> — Move unchanged</summary>

1. `self.assertIs(session.calls[1][2]['json']['status']['containsSyntheticMedia'], False)`
2. `self.assertIs(result['updated_metadata']['contains_synthetic_media'], False)`
3. `self.assertEqual(result['metadata'], self.state['metadata'])`

**Trace:** `VideoMetadataUpdateTests.test_metadata_update_can_clear_ai_disclosure` moved verbatim into `tests/test_youtube.py` (class appended unchanged; AST equality checked against the baseline in `s3-retained-ast.json`). Fake transport only; every metadata/atomic-write assertion is preserved.

</details>

<details><summary>#22 <code>VideoMetadataUpdateTests.test_api_failure_keeps_local_record_unchanged</code> — Move unchanged</summary>

1. `self.assertRaises(YouTubeUploadError)`
2. `self.assertEqual(before, Path(self.job, 'youtube_upload.json').read_bytes())`

**Trace:** `VideoMetadataUpdateTests.test_api_failure_keeps_local_record_unchanged` moved verbatim into `tests/test_youtube.py` (class appended unchanged; AST equality checked against the baseline in `s3-retained-ast.json`). Fake transport only; every metadata/atomic-write assertion is preserved.

</details>


### `tests/test_last_input_folder.py` (baseline SHA-256 `3158793288456cb444a13d9159c6cad92151aaa297d81c1014432ba93228709e`)

<details><summary>#23 <code>LastInputFolderTests.test_setting_round_trip_and_invalid_folder_fallback</code> — Retain</summary>

1. `self.assertEqual(loaded.resolved_input_dir(), str(input_dir))`
2. `self.assertEqual(loaded.resolved_input_dir(), "")`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#24 <code>LastInputFolderTests.test_output_folder_always_follows_the_input</code> — Retain</summary>

1. `self.assertEqual(settings.resolved_output_dir(input_dir), input_dir)`
2. `self.assertEqual(settings.resolved_output_dir(input_file), input_dir)`
3. `self.assertEqual(settings.require_output_dir(input_file), input_dir)`
4. `self.assertFalse(hasattr(legacy, "output_dir"))`
5. `self.assertEqual(legacy.resolved_output_dir(input_dir), input_dir)`
6. `self.assertRaisesRegex(ValueError, "Step 1")`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#25 <code>LastInputFolderTests.test_file_picker_starts_at_and_updates_last_folder</code> — Retire desktop only</summary>

1. `self.assertEqual(picker.call_args.args[2], str(initial_dir))`
2. `self.assertEqual(settings.last_input_dir, str(selected_dir))`
3. `save.assert_called_once_with()`
4. `self.assertEqual(window.document.original_input_text, "Chương 1\nNội dung.")`
5. `self.assertEqual(window.document.source_path, str(selected_file.resolve()))`
6. `self.assertEqual(window.document.input_directory, str(selected_dir.resolve()))`

**Trace:** Picker initial-directory argument (A1) and `QFileDialog` mock retire with the desktop. A2/A3 → `PUT /api/settings last_input_dir`, real `import` job updates `service.settings.last_input_dir`, `GET /api/settings` and reloaded `config.json` agree. A4–A6 → `/api/state` `original_text`, `source_path`, `input_directory` (resolved).

</details>


### `tests/test_log_dialog.py` (baseline SHA-256 `bff59ca23e83d756d070c09b94e01363af27c6dfac222a4ca8bfc28f2850a0aa`)

<details><summary>#26 <code>LogDialogTests.test_shared_log_keeps_every_step_line_across_closing</code> — Migrate</summary>

1. `self.assertFalse(window.log_dialog.isVisible())`
2. `self.assertIs(window.log_dialog.parent(), window)`
3. `self.assertTrue(window.log_dialog.isVisible())`
4. `self.assertFalse(window.log_dialog.isModal())`
5. `self.assertIn(f"step {step + 1} log line", text)`
6. `self.assertFalse(window.log_dialog.isVisible())`
7. `self.assertIn( "line written while the log window was closed", window.log_dialog.lines_text(), )`

**Trace:** A5 → real import/normalize/group jobs and a failed import: each job's `GET /api/jobs/{id}/logs` stays readable after later jobs, sequences 1..n in order, first line is the action, repeated reads return identical rows; the failed job ends with an `error`-level line equal to the job error. A7 → a gated TTS job read mid-run, then `?after=<last sequence>` returns only the lines written while unread; seen+rest equals the full log, ending `Đã hoàn thành`.

</details>

<details><summary>#27 <code>LogDialogTests.test_opening_the_log_leaves_the_active_step_and_busy_state_untouched</code> — Migrate</summary>

1. `self.assertEqual(window.tabs.currentIndex(), 4)`
2. `self.assertFalse(window.tabs.isTabEnabled(0))`
3. `self.assertTrue(window.log_dialog.isVisible())`
4. `self.assertTrue(window.log_btn.isEnabled())`
5. `self.assertEqual(window.tabs.currentIndex(), 4)`
6. `self.assertFalse(window.tabs.isTabEnabled(0))`

**Trace:** A2/A6 (other steps disabled while busy) → during a gated real TTS job, repeated log reads leave the job `running` and the only active job; `POST /api/jobs normalize` and `POST /api/sessions/new` return 409; `/api/state` unchanged by reads; job then completes.

</details>

<details><summary>#28 <code>LogDialogTests.test_log_button_and_shortcut_toggle_the_window</code> — Retire desktop only</summary>

1. `self.assertEqual(window.log_btn.text(), "📋 Log")`
2. `self.assertIn("●", window.log_btn.text())`
3. `self.assertTrue(window.log_dialog.isVisible())`
4. `self.assertEqual(window.log_btn.text(), "📋 Log")`
5. `self.assertFalse(window.log_dialog.isVisible())`
6. `self.assertTrue(window.log_dialog.isVisible())`
7. `self.assertEqual(window._log_shortcut.key().toString(), "Ctrl+L")`
8. `self.assertTrue(window._log_shortcut.isEnabled())`
9. `self.assertFalse(window.log_dialog.isVisible())`

**Trace:** Qt log button/shortcut toggling only. Job log content/order/repeated reads covered by `BR::test_job_logs_remain_available_across_reads`; the web log panel is `frontend/src/components/job-panel.tsx`.

</details>

<details><summary>#29 <code>LogDialogTests.test_max_log_lines_bounds_the_shared_buffer</code> — Migrate</summary>

1. `self.assertEqual(document.maximumBlockCount(), 100)`
2. `self.assertEqual(document.blockCount(), 100)`
3. `self.assertIn("line 149", text)`
4. `self.assertNotIn("line 0\n", text)`

**Trace:** A1 → `PUT /api/settings max_log_lines=100`, `GET` reflects 100. Real 150-chapter group TTS job (fake Edge-TTS client) writes >150 lines: A2 → exactly 100 rows returned; A3 → newest rows kept (contiguous sequences ending at the final `Đã hoàn thành`); A4 → the first line (`tts`) dropped.

</details>

<details><summary>#30 <code>LogDialogTests.test_closing_the_main_window_hides_the_log_window</code> — Retire desktop only</summary>

1. `self.assertTrue(window.log_dialog.isVisible())`
2. `self.assertFalse(window.log_dialog.isVisible())`

**Trace:** Window lifecycle only. Logs stay per job in the JobManager and are readable after later jobs (`BR::test_job_logs_remain_available_across_reads`); session persistence on shutdown covered in `tests/test_sessions.py`.

</details>

<details><summary>#31 <code>LogDialogTests.test_copy_all_and_clear_use_the_shared_log</code> — Retire desktop only</summary>

1. `self.assertEqual(self.app.clipboard().text(), window.log_dialog.lines_text())`
2. `self.assertIn("second line", self.app.clipboard().text())`
3. `self.assertEqual(window.log_dialog.lines_text(), "")`
4. `self.assertEqual(window.log_dialog.status_label.text(), "Log is empty.")`

**Trace:** Clipboard and Qt clear controls. Log content/order/bounds covered by `BR::test_job_logs_remain_available_across_reads` and `BR::test_max_log_lines_bounds_the_shared_buffer`.

</details>


### `tests/test_pipeline_data_flow.py` (baseline SHA-256 `dd06a6743767125051deb6a0f014a124cd988b6b3fb309b9ffb75a513097ba8e`)

<details><summary>#32 <code>PipelineDataFlowTests.test_step2_consumes_exact_normalized_text_without_han_gate</code> — Retain</summary>

1. `self.assertEqual(source, document.normalized_text)`
2. `self.assertEqual(label, "Source: Step 1 — Normalized Text")`
3. `self.assertEqual(document.original_input_text, original)`
4. `self.assertNotIn("第327章", source)`
5. `self.assertNotIn("流民不可怕", source)`
6. `self.assertIn("Chương 327: Lưu dân không đáng sợ", source)`
7. `self.assertIn("修炼者", source)`
8. `self.assertEqual(document.require_grouping_input(), source)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#33 <code>PipelineDataFlowTests.test_original_is_fallback_before_step1</code> — Retain</summary>

1. `self.assertEqual(source, RAW_TEXT)`
2. `self.assertEqual(label, "Source: Original File — Step 1 not run")`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#34 <code>PipelineDataFlowTests.test_successful_step1_without_output_fails_closed</code> — Retain</summary>

1. `self.assertRaises(PipelineStateError)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#35 <code>PipelineDataFlowTests.test_step1_edit_replaces_grouping_source_and_invalidates_chunks</code> — Retain</summary>

1. `self.assertTrue(document.set_normalized_edit(edited))`
2. `self.assertEqual(document.require_grouping_input(), edited)`
3. `self.assertEqual(document.chunks, [])`
4. `self.assertIsNone(document.step3_artifacts)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#36 <code>PipelineDataFlowTests.test_main_window_allows_chinese_text_in_step2</code> — Migrate</summary>

1. `self.assertEqual(window.tabs.currentIndex(), 1)`
2. `self.assertIn("修炼者", window.document.require_grouping_input())`

**Trace:** Real `import` (Chinese-bearing `RAW_TEXT`) + `normalize` jobs; `stages.normalize.ok` true, 修炼者 in `/api/state` text and A2 kept on `service.document.require_grouping_input()`; grouping preview succeeds without a Han gate error.

</details>


### `tests/test_sessions.py` (baseline SHA-256 `c779a8902143dcd06fc637d4d58c6f26a20084cfe8a1d82c592b0004613b3663`)

<details><summary>#37 <code>SessionTests.test_roundtrip_retains_text_types_and_validated_media</code> — Retain</summary>

1. `self.assertEqual(document_to_dict(restored), document_to_dict(document))`
2. `self.assertEqual(restored.source_files[0].text, "Original full text")`
3. `self.assertEqual(restored.require_step5_outputs(), document.require_step5_outputs())`
4. `self.assertEqual(ui["tab"], 3)`
5. `self.assertRaises(PipelineStateError)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#38 <code>SessionTests.test_atomic_failure_preserves_previous_session</code> — Retain</summary>

1. `self.assertRaises(SessionError)`
2. `self.assertEqual(restored.original_input_text, "Saved text")`
3. `self.assertFalse(list(self.store.root.glob("*.tmp")))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#39 <code>SessionTests.test_corrupt_sessions_and_traversal_are_rejected</code> — Retain</summary>

1. `self.assertEqual(self.store.list_sessions(), [])`
2. `self.assertRaises(SessionError)`
3. `self.assertRaises(SessionError)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#40 <code>SessionTests.test_group_snapshot_recovers_newer_completed_job_state</code> — Retain</summary>

1. `self.assertEqual(restored.chapter_groups[0].state["tts_status"], "Completed")`
2. `self.assertEqual(restored.require_chapter_groups(), document.require_chapter_groups())`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#41 <code>SessionTests.test_close_and_reopen_at_step4_without_repeating_previous_stages</code> — Migrate</summary>

1. `self.assertTrue(first.close())`
2. `self.assertEqual(self.store.list_sessions()[0]["step"], 4)`
3. `self.assertTrue(second._open_session(session_id))`
4. `normalize.assert_not_called()`
5. `self.assertEqual(second.tabs.currentIndex(), 3)`
6. `self.assertEqual(second.settings.tts_voice, "vi-VN-NamMinhNeural")`
7. `self.assertEqual(second.settings.youtube_client_secrets_path, "current-global-client.json")`
8. `self.assertEqual(second.document.require_step5_outputs(), first.document.require_step5_outputs())`
9. `self.assertEqual(second.stage6_widget.description_edit.toPlainText(), "Mô tả chưa upload")`
10. `self.assertTrue(second.stage6_widget.ai_check.isChecked())`
11. `self.assertTrue(second.group6.editor.ai_check.isChecked())`
12. `self.assertEqual(second._video_media.audiobook_path, first.document.audiobook_path)`

**Trace:** Real app: import → normalize → group → thumbnail/TTS/video jobs, `PUT /api/settings` tts_voice, `POST /api/sessions` ui `{tab:3, web_draft}`. A1 close → real application shutdown (`JobManager.close` saves). A2 kept (`list_sessions()[0].step == 4`). Global config rewritten while closed. A3 → `POST /api/sessions/{id}/open` 200; A4 (no stage rerun) → `GET /api/jobs == []` and stages/normalized text unchanged; A6/A7 kept on `service.settings` (session voice restored, global client path kept); A8/A12 → group stage state identical, `missing_artifacts == []`, audiobook still a registered output; A9–A11 → `ui_state.web_draft` (description, AI disclosure) restored; frontend parse in `frontend/tests/pipeline.test.ts`.

</details>

<details><summary>#42 <code>SessionTests.test_multiple_sessions_restore_edited_text_and_group_selection</code> — Migrate</summary>

1. `self.assertTrue(first._save_session())`
2. `self.assertTrue(first._save_session())`
3. `self.assertTrue(first._open_session(first_id))`
4. `self.assertEqual(first.document.normalized_text, "Chương 1\nĐã sửa.\nChương 2\nB.")`
5. `self.assertEqual(first.group5.selected_id(), groups[1].group_id)`
6. `self.assertEqual(first.group5.checked_ids(), [groups[1].group_id])`
7. `self.assertNotEqual(first_id, second_id)`
8. `self.assertEqual(len(self.store.list_sessions()), 2)`

**Trace:** A1/A2 → `POST /api/sessions` 200 twice (second after `/api/sessions/new` + import of another story); A3 → open first session 200; A4 kept via state `normalized_text` after real `edit` job; A6 checked groups → `ui_state.web_draft.selected == [ids[1]]`; A7, A8 kept (`GET /api/sessions` length 2).

</details>

<details><summary>#43 <code>SessionTests.test_missing_media_keeps_text_and_reports_missing_files</code> — Migrate</summary>

1. `self.assertTrue(window._open_session(session_id))`
2. `enter.assert_not_called()`
3. `self.assertEqual(window.document.original_input_text, document.original_input_text)`
4. `self.assertIn(document.audiobook_path, missing_artifacts(window.document))`
5. `self.assertIn("Thiếu", window.session_status.text())`

**Trace:** Audiobook deleted while the app is closed; A1 → open 200; A2 (no stage entry) → `GET /api/jobs == []`; A3 kept via `original_text`; A4 → `missing_artifacts` contains audiobook path (and it is not an allowed output).

</details>

<details><summary>#44 <code>SessionTests.test_busy_session_cannot_be_replaced</code> — Migrate</summary>

1. `self.assertFalse(window._open_session("0" * 32))`
2. `self.assertEqual(window.document.original_input_text, "Work in progress")`

**Trace:** Real TTS job held at the Edge-TTS boundary (gate); A1 → `POST /api/sessions/{id}/open` and `/api/sessions/new` return 409 while busy; A2 → document text unchanged; job then completes.

</details>

<details><summary>#45 <code>SessionTests.test_failed_save_prevents_close_and_retains_document</code> — Migrate</summary>

1. `self.assertFalse(window.close())`
2. `error.assert_called_once_with("Disk full")`
3. `self.assertEqual(window.document.original_input_text, "Unsaved edits")`

**Trace:** Destination renamed per Appendix B. Real save with `media.artifacts.os.replace` failing: A2 → HTTP 422 detail contains 'Disk full'; A3 → edited text and `session_id` retained; previous session bytes unchanged and no `*.tmp` left.

</details>

<details><summary>#46 <code>SessionTests.test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id</code> — Migrate</summary>

1. `self.assertEqual(self.store.list_sessions(), [])`
2. `self.assertEqual(restored.normalized_text, "User edits")`
3. `self.assertEqual(len(self.store.list_sessions()), 1)`
4. `self.assertNotIn("youtube_client_secrets_path", settings)`
5. `self.assertNotIn("youtube_title_tags", settings)`

**Trace:** A1 → `GET /api/sessions == []` on empty startup and after empty shutdown; job autosave: import creates one id, normalize/edit update it; A2–A5 kept on `SessionStore.load`/`list_sessions`.

</details>

<details><summary>#47 <code>SessionTests.test_reopening_older_session_keeps_latest_uploaded_story_tags</code> — Migrate</summary>

1. `self.assertTrue(window._save_session())`
2. `self.assertTrue(window._open_session(session_id))`
3. `self.assertEqual(window.settings.tags_for_uploaded_title("Truyện A"), ["latest"])`

**Trace:** A1/A2 → HTTP save/open 200; A3 kept on `service.settings` plus `youtube_tags.history` in state.

</details>

<details><summary>#48 <code>SessionTests.test_reopening_youtube_page_preserves_unuploaded_tag_draft</code> — Migrate</summary>

1. `self.assertTrue(first._save_session())`
2. `self.assertTrue(second._open_session(first._session_id))`
3. `self.assertEqual(second.stage6_widget.tags_edit.text(), "tag mới chưa upload")`

**Trace:** A1/A2 → HTTP save, app restart, open 200; A3 → `ui_state.web_draft` (tagsText/tagsEdited) restored beside `youtube_tags.current == ['tag đã upload']`; frontend `draftSchema` accepts the restored draft (`frontend/tests/pipeline.test.ts`). `restoreDraft` precedence itself is not exported, so it is not unit-tested; the browser smoke covers reopening (step 6 reopens a saved web session; step 18 reopens a desktop-shaped schema-v1 session and shows its legacy upload metadata, tags and cover/QR paths).

</details>


### `tests/test_settings_dialog.py` (baseline SHA-256 `fb5f837e8e04551881d535db7beaf529f438cf12a11adcfb8e33d72153d225d5`)

<details><summary>#49 <code>SettingsDialogTests.test_legacy_translation_settings_are_ignored_safely</code> — Migrate</summary>

1. `self.assertTrue(settings.detect_chinese)`
2. `self.assertFalse(hasattr(settings, "dictionary_enabled"))`
3. `self.assertFalse(hasattr(settings, "gemini_api_key"))`

**Trace:** Legacy keys written into the isolated `config.json`, app restarted (real lifespan, `Settings.load`). A1 → `GET /api/settings detect_chinese` true; A2/A3 → no `dictionary_*`, `gemini_api_key`, `ai_*` keys and the legacy value is not exposed; `PUT gemini_api_key` → 422 without echoing the value; the next real save writes no legacy key.

</details>

<details><summary>#50 <code>SettingsDialogTests.test_collects_changed_values</code> — Migrate</summary>

1. `self.assertIsInstance(zero_pad, QSpinBox)`
2. `self.assertIsInstance(mode, QComboBox)`
3. `self.assertIsInstance(symbol_map, QTextEdit)`
4. `self.assertIsInstance(voice, QLineEdit)`
5. `self.assertEqual(updated.zero_pad, 4)`
6. `self.assertEqual(updated.quote_mode, "keep")`
7. `self.assertEqual(updated.symbol_map, {"%": " phần trăm "})`
8. `self.assertEqual(updated.tts_voice, "vi-VN-HoaiMyNeural")`

**Trace:** A5–A8 → `PUT /api/settings` zero_pad/quote_mode/symbol_map/tts_voice; the response, `GET /api/settings` and reloaded `config.json` all hold the same values.

</details>

<details><summary>#51 <code>SettingsDialogTests.test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit</code> — Migrate</summary>

1. `self.assertEqual(Settings.from_dict({"tts_voice": ""}).tts_voice, DEFAULT_TTS_VOICE)`
2. `self.assertEqual(Settings.from_dict({"tts_voice": " "}).tts_voice, DEFAULT_TTS_VOICE)`
3. `self.assertIsInstance(voice, QLineEdit)`
4. `self.assertRaisesRegex(ValueError, "TTS voice cannot be empty")`

**Trace:** A1/A2 → saved `tts_voice` "" and "   " in `config.json`, app restarted, `GET /api/settings` gives `DEFAULT_TTS_VOICE`. A4 → `PUT tts_voice "   "` returns 422 `TTS voice cannot be empty…`; settings and `config.json` bytes unchanged.

</details>

<details><summary>#52 <code>SettingsDialogTests.test_step3_title_history_can_be_remembered_and_removed</code> — Migrate</summary>

1. `self.assertEqual(window.stage3_title_combo.itemText(0), "Old Novel")`
2. `self.assertEqual(settings.title_history, ["New Novel", "Old Novel"])`
3. `self.assertTrue(saved)`
4. `self.assertEqual(settings.title_history, ["Old Novel"])`
5. `self.assertEqual(window.stage3_title_combo.currentText(), "")`

**Trace:** A1 data → `title_history[0] == "Old Novel"` via `GET /api/settings`. A2/A3 → real `group` job titled `New Novel` records `["New Novel", "Old Novel"]` in `GET /api/settings` and saved `config.json`. A4 → `PUT title_history ["Old Novel"]` removes it in both.

</details>

<details><summary>#53 <code>SettingsDialogTests.test_runtime_ui_settings_are_applied</code> — Migrate</summary>

1. `self.assertEqual(window.settings_btn.text(), "⚙ Settings")`
2. `self.assertEqual(window.font().pointSize(), 13)`
3. `self.assertEqual(window.log_dialog.log_text.document().maximumBlockCount(), 321)`
4. `self.assertIs(window.status_text, window.log_dialog.log_text)`
5. `self.assertEqual(window._default_export_filename(), "novel_export.json")`

**Trace:** A2 value → `GET /api/settings font_size == 13`. A3 → `max_log_lines=321` bounds a real 330-chapter TTS job log to exactly 321 rows. A5 → real `export json` job publishes `novel_export.json`.

</details>

<details><summary>#54 <code>SettingsDialogTests.test_log_window_is_detached_and_resizable</code> — Retire desktop only</summary>

1. `self.assertFalse(hasattr(window, "main_splitter"))`
2. `self.assertFalse(window.log_dialog.isVisible())`
3. `self.assertIs(window.log_dialog.parent(), window)`
4. `self.assertTrue(window.log_dialog.isVisible())`
5. `self.assertGreaterEqual(window.log_dialog.width(), 600)`
6. `self.assertGreaterEqual(window.log_dialog.height(), 300)`
7. `self.assertGreaterEqual(window.log_dialog.height(), 600)`

**Trace:** Qt window geometry only; no business assertion.

</details>

<details><summary>#55 <code>SettingsDialogTests.test_cleaning_settings_affect_step3</code> — Migrate</summary>

1. `self.assertNotIn("<p>", chunk_text)`
2. `self.assertIn("10%", chunk_text)`

**Trace:** `PUT /api/settings symbol_map/remove_html`; real import/normalize/group of `Chương 1\n<p>Giá trị 10%</p>`, then real `prepare` job. A1/A2 on the group TTS plan in `/api/state` (`tts_plan.chunks[].text`): no `<p>`, keeps `10%`.

</details>


### `tests/test_step2_ui.py` (baseline SHA-256 `340f26f0e6806896e0b1d574908c5406ec2efa321ce2916231501eddc492c920`)

<details><summary>#56 <code>Step2UiTests.test_step2_is_grouping_and_preserves_chinese_text</code> — Migrate</summary>

1. `self.assertEqual(window.tabs.count(), 5)`
2. `self.assertEqual( [window.tabs.tabText(i) for i in range(window.tabs.count())], [ "1️⃣ Input & Normalize", "2️⃣ Detect Chapters & Group", "3️⃣ Thumbnail & Audio`
3. `self.assertNotIn("Chinese", " ".join(window.tabs.tabText(i) for i in range(window.tabs.count())))`
4. `self.assertEqual(window.tabs.currentIndex(), 1)`
5. `self.assertEqual(window.document.require_grouping_input(), "Chương 1\n中文 修炼者.")`
6. `self.assertIn("Effective output root:", window.stage3_output.toPlainText())`
7. `self.assertIn("Job folder:", window.stage3_output.toPlainText())`
8. `self.assertIn("中文 修炼者", group_text)`

**Trace:** Real import/normalize/`edit` jobs with `Chương 1\n中文 修炼者.`; normalize stage ok. A3 business (no Chinese gate) → `/api/grouping` has no error and one group. A5 kept on `service.document.require_grouping_input()` and `/api/state.text`. A6/A7 business → group `output_dir` lies under the input directory. A8 → real `group` job's `txt_path` contains `中文 修炼者`.

</details>

<details><summary>#57 <code>Step2UiTests.test_copy_all_copies_complete_step2_output</code> — Retire desktop only</summary>

1. `self.assertEqual(self.app.clipboard().text(), expected)`

**Trace:** Clipboard interaction. Complete grouping input/output covered by `BR::test_step2_is_grouping_and_preserves_chinese_text` and `tests/test_pipeline_data_flow.py`.

</details>

<details><summary>#58 <code>Step2UiTests.test_copy_all_covers_diagnostics_group_panel_dialog_and_youtube</code> — Retire desktop only</summary>

1. `self.assertEqual(self.app.clipboard().text(), diagnostics)`
2. `self.assertEqual(self.app.clipboard().text(), group_details)`
3. `self.assertEqual(self.app.clipboard().text(), "ORIGINAL CHUNK TEXT:\nfailed output\nline 2")`
4. `self.assertEqual(self.app.clipboard().text(), "upload result\nvideo id")`

**Trace:** Clipboard/widget routing. Diagnostics, failed-chunk detail and upload result/state are asserted in their own business cases (TTS failure and YouTube BR rows, `tests/test_youtube_title_tags.py`).

</details>


### `tests/test_tts_preprocessing.py` (baseline SHA-256 `7e06ff428beb370d8c8e58504b94f3c91789e9dc63c1e95ebcdac39879d425f1`)

<details><summary>#59 <code>PreprocessingTests.test_required_examples_and_idempotence</code> — Retain</summary>

1. `self.assertEqual(result.text, expected)`
2. `self.assertEqual(preprocess_for_tts(result.text), result.text)`
3. `self.assertTrue(result.warnings)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#60 <code>PreprocessingTests.test_full_required_example_and_adjacent_url</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts(source), expected)`
2. `self.assertEqual(preprocess_for_tts(expected), expected)`
3. `self.assertEqual(preprocess_for_tts('Ta đi...https://example.com'), 'Ta đi…')`
4. `self.assertEqual(preprocess_for_tts('Ta đi...https://example.com', TTSPreprocessConfig(url_policy='keep')), 'Ta đi… https://example.com')`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#61 <code>PreprocessingTests.test_double_quote_fallback_matches_step1_policy</code> — Retain</summary>

1. `self.assertEqual( preprocess_for_tts('Hắn nói “xin chào” rồi đi “về”.'), "Hắn nói 'xin chào' rồi đi 'về'.", )`
2. `self.assertEqual(preprocess_for_tts('Cô đáp ＂đi ngay＂.'), "Cô đáp 'đi ngay'.")`
3. `self.assertEqual( preprocess_for_tts('{"title":"abc","value":3.14}'), '{"title":"abc","value":3.14}', )`
4. `self.assertEqual(result.text, "Nói 'hi'.")`
5. `self.assertEqual(result.statistics.get("double_quotes_normalized"), 2)`
6. `self.assertEqual(preprocess_for_tts(result.text), result.text)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#62 <code>PreprocessingTests.test_protected_structures_and_semantics</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts(sample), sample)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#63 <code>PreprocessingTests.test_unicode_and_entities</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts('Ngu\u031bo\u031b\u0300i\u00a0\u2009đó\r\n\tTa\x00 đi.\r'), 'Người đó\nTa đi.')`
2. `self.assertEqual(preprocess_for_tts('&amp;lt;p&amp;gt;**Ta đi.**&amp;lt;/p&amp;gt;'), 'Ta đi.')`
3. `self.assertEqual(preprocess_for_tts(once), once)`
4. `self.assertIn('\u200d', result.text)`
5. `self.assertEqual(result.statistics['detected_cjk_chars'], 4)`
6. `self.assertGreater(result.statistics['detected_other_script_chars'], 0)`
7. `self.assertTrue(result.warnings)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#64 <code>PreprocessingTests.test_valid_vietnamese_diacritics_are_not_mojibake</code> — Retain</summary>

1. `self.assertEqual(result.statistics["detected_mojibake_patterns"], 0)`
2. `self.assertFalse(any("mojibake" in warning for warning in result.warnings))`
3. `self.assertEqual(result.text, source)`
4. `self.assertEqual(result.diagnostics, [])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#65 <code>PreprocessingTests.test_mojibake_diagnostics_are_aggregated_and_preserved</code> — Retain</summary>

1. `self.assertEqual(result.statistics["detected_mojibake_patterns"], 4)`
2. `self.assertEqual(result.text, source)`
3. `self.assertEqual(len(result.diagnostics), 4)`
4. `self.assertTrue(any("rule=cp1252-punctuation" in warning and "x2" in warning and "line 2" in warning and "line 3" in warning for warning in result.warnings))`
5. `self.assertTrue(any("rule=latin1-utf8" in warning and "Æ°" in warning and "context=" in warning for warning in result.warnings))`
6. `self.assertTrue(any("rule=latin1-vietnamese" in warning and "á»" in warning and "char" in warning for warning in result.warnings))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#66 <code>PreprocessingTests.test_chapter_preparation_keeps_chapter_context_in_diagnostics</code> — Retain</summary>

1. `self.assertEqual(statistics["detected_mojibake_patterns"], 2)`
2. `self.assertEqual(prepared.text, source)`
3. `self.assertTrue(any("possible mojibake" in warning and "x2" in warning for warning in warnings))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#67 <code>PreprocessingTests.test_policies_and_custom_rules</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts(text), 'Ta xem. Hắn viết abc@gmail.com.')`
2. `self.assertEqual(preprocess_for_tts(text, keep), text)`
3. `self.assertEqual(preprocess_for_tts(uppercase, keep), uppercase)`
4. `self.assertEqual(preprocess_for_tts(uppercase), '')`
5. `self.assertEqual(once, 'Ta xem [đường dẫn]. Hắn viết [email].')`
6. `self.assertEqual(preprocess_for_tts(once, replace), once)`
7. `self.assertEqual(preprocess_for_tts('Nguồn: abc\nHắn đi [1].\nchapter_id=2', config), 'Hắn đi.')`
8. `self.assertEqual(preprocess_for_tts('Nguồn: abc'), 'Nguồn: abc')`
9. `self.assertRaises(ValueError)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#68 <code>PreprocessingTests.test_technical_json_emoji_and_comments</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts(source), source)`
2. `self.assertEqual(boundary_positions(source), [])`
3. `self.assertEqual(preprocess_for_tts(family), '')`
4. `self.assertEqual(preprocess_for_tts(family, TTSPreprocessConfig(remove_emoji=False)), family)`
5. `self.assertEqual(preprocess_for_tts('Ta <!-- note --> đi.'), 'Ta đi.')`
6. `self.assertEqual(preprocess_for_tts(unclosed), unclosed)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#69 <code>PreprocessingTests.test_sentence_per_line</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts(source, config), expected)`
2. `self.assertEqual(preprocess_for_tts(expected, config), expected)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#70 <code>PreprocessingTests.test_invariants_seeded_mixed_input</code> — Retain</summary>

1. `self.assertEqual(preprocess_for_tts(once, config), once, repr(source))`
2. `self.assertFalse(any(c in once for c in ('\x00', '\r', '\ufeff', '\u200b')))`
3. `self.assertNotRegex(once, r' {2,}|\n{3,}')`
4. `self.assertEqual(preprocess_for_tts(''), '')`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#71 <code>BoundaryTests.test_technical_boundaries</code> — Retain</summary>

1. `self.assertEqual(len(units), 3)`
2. `self.assertTrue(units[0].endswith('3.14.'))`
3. `self.assertTrue(units[1].endswith('?”'))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#72 <code>BoundaryTests.test_lossless_chunking_quotes_numbers_and_empty</code> — Retain</summary>

1. `self.assertEqual(' '.join(plan.chunks), source)`
2. `self.assertTrue(all(len(c) <= 600 and meaningful_text(c) for c in plan.chunks))`
3. `self.assertTrue(all(not c.startswith(tuple(',.!?…;:”’)]}')) for c in plan.chunks))`
4. `self.assertFalse(plan.hard_splits)`
5. `self.assertEqual(split_text_by_limit('… !!! —', 600).chunks, [])`
6. `self.assertEqual(plan.chunks[0], chapter.header_line)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#73 <code>BoundaryTests.test_oversized_protected_heading_and_combining</code> — Retain</summary>

1. `self.assertRaisesRegex(ValueError, 'Protected token')`
2. `self.assertRaisesRegex(ValueError, 'heading')`
3. `self.assertTrue(plan.hard_splits)`
4. `self.assertEqual(''.join(plan.chunks), 'a\u0301' * 700)`
5. `self.assertTrue(all(not c.startswith('\u0301') for c in plan.chunks))`
6. `self.assertEqual(safe_half_split('192.168.1.1'), ('192.168.1.1', ''))`
7. `self.assertEqual(first + ' ' + second, 'Giá 3.14. Hắn đã đến. Ta biết.')`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#74 <code>SentencePackingTests.test_pack_sentences_not_short_paragraphs</code> — Retain</summary>

1. `self.assertEqual(plan.chunks, [first + '\n\n' + second, third])`
2. `self.assertFalse(plan.hard_splits)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#75 <code>SentencePackingTests.test_paragraph_break_inside_sentence_does_not_cut_short_sentence</code> — Retain</summary>

1. `self.assertEqual(plan.chunks, [sentence, next_sentence])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#76 <code>SentencePackingTests.test_oversized_sentence_uses_words_before_hard_slicing</code> — Retain</summary>

1. `self.assertGreater(len(plan.chunks), 1)`
2. `self.assertTrue(all(len(c) <= 700 for c in plan.chunks))`
3. `self.assertFalse(plan.hard_splits)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#77 <code>TtsIntegrationTests.test_fixed_700_target_ignores_saved_legacy_sizes</code> — Retain</summary>

1. `self.assertEqual(first['config']['limit'], 700)`
2. `self.assertEqual(first['source_revision'], self.doc.normalized_revision)`
3. `self.assertEqual(first['plan_id'], second['plan_id'])`
4. `self.assertEqual([c.text for c in chunks], [c.text for c in same])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#78 <code>TtsIntegrationTests.test_group_tts_plan_propagates_chapter_mojibake_diagnostics</code> — Retain</summary>

1. `self.assertEqual(plan["statistics"]["detected_mojibake_patterns"], 2)`
2. `self.assertTrue(any("Chapter 109:" in warning and "x2" in warning and "rule=cp1252-punctuation" in warning for warning in plan["warnings"]))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#79 <code>TtsIntegrationTests.test_preprocessing_before_chunking_and_resume</code> — Retain</summary>

1. `self.assertIn('Ngươi là ai? Ta không biết…', speech)`
2. `self.assertIn("'Hắn sống!' Lâm hét.", speech)`
3. `self.assertNotIn('https://', speech)`
4. `self.assertTrue(plan['warnings'])`
5. `self.assertEqual(prepare_tts(self.doc, self.group.group_id, self.settings)[0], plan)`
6. `self.assertEqual(calls, [c.text for c in chunks])`
7. `self.assertEqual(len(run(chunks).skipped), len(chunks))`
8. `self.assertEqual(len(calls), count)`
9. `self.assertNotEqual(changed['plan_id'], plan['plan_id'])`
10. `self.assertGreater(len(calls), count)`
11. `self.assertEqual(self.doc.require_grouping_input(), self.source)`
12. `self.assertEqual(canonical, [Path(self.group.txt_path).read_bytes(), Path(self.group.json_path).read_bytes()])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#80 <code>TtsIntegrationTests.test_old_cache_overrides_cancel_and_empty</code> — Retain</summary>

1. `self.assertEqual(new, plan)`
2. `self.assertEqual(prepare_tts(self.doc, self.group.group_id, self.settings)[1][-1].text, 'Đã sửa! Đúng…')`
3. `self.assertRaises(PipelineStateError)`
4. `self.assertTrue(any('older plan' in w for w in changed['warnings']))`
5. `self.assertRaisesRegex(PipelineStateError, 'hủy')`
6. `self.assertEqual(path.read_bytes(), before)`
7. `self.assertRaisesRegex(Exception, 'nội dung')`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#81 <code>TtsIntegrationTests.test_settings_roundtrip_and_custom_clean</code> — Retain</summary>

1. `self.assertEqual(preprocessing_identity(Settings.load(saved)), preprocessing_identity(self.settings))`
2. `self.assertIn('chưa biết', '\n'.join(c.text for c in chunks))`
3. `self.assertEqual(Settings.from_dict({}).tts_preprocessing, {})`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#82 <code>LegacyAndUiTests.test_legacy_bundle_client_and_old_provenance</code> — Migrate</summary>

1. `self.assertEqual(data['tts_preparation'], job_preprocessing_identity(prepared, self.settings))`
2. `self.assertEqual(Path(data['resolved_output_dir']), self.root.resolve())`
3. `self.assertIn('Lời đầu.', data['chunks'][0]['text'])`
4. `self.assertIn('Ngươi là ai? Ta không biết…', prepared.cleaned_text)`
5. `self.assertEqual(doc.require_grouping_input(), source)`
6. `self.assertTrue(window._on_clean_chunk())`
7. `self.assertIn('Ngươi là ai? Ta không biết…', '\n'.join(seen))`
8. `self.assertNotIn('biết.....', '\n'.join(seen))`
9. `self.assertEqual(load_bundle_json(window.document.step3_artifacts)['tts_preparation'], job_preprocessing_identity(window.document, self.settings))`

**Trace:** A1–A5 kept verbatim on the core legacy bundle (`prepare_legacy_bundle`, `job_preprocessing_identity`). A7/A8 → real group `tts` job through the fake Edge-TTS client: spoken text contains the preprocessed sentence and never `biết.....`. A9 (old provenance rebuilt) → `tts_chunks.json` `config` removed, TTS rerun rebuilds a plan equal to the original; canonical text files unchanged.

</details>

<details><summary>#83 <code>LegacyAndUiTests.test_large_preparation_worker_cancel_and_snapshot</code> — Migrate</summary>

1. `self.assertFalse(window._on_clean_chunk())`
2. `self.assertIsNotNone(window._tts_prepare_thread)`
3. `self.assertIsNone(window._tts_prepare_thread)`
4. `self.assertIsNone(window.document.step3_artifacts)`
5. `self.assertEqual(window.document.require_grouping_input(), source)`
6. `self.assertFalse(window._on_clean_chunk())`
7. `self.assertIsNone(window._tts_prepare_thread)`
8. `self.assertIsNotNone(window.document.step3_artifacts)`
9. `self.assertIn('Ngươi là ai? Ta biết.', window.document.cleaned_text)`

**Trace:** A1/A4 → 6000-line `prepare` job stopped via `POST /api/jobs/{id}/stop` after its `prepare` log: status `cancelled`, group error `Đã hủy chuẩn bị TTS…`, no plan file and no `tts_plan` in `/api/state`. A5 → normalized/canonical text unchanged. A6/A8/A9 → rerun `prepare` completes and its plan contains `Ngươi là ai? Ta biết.`.

</details>

<details><summary>#84 <code>LegacyAndUiTests.test_config_ui_and_downstream_invalidation</code> — Migrate</summary>

1. `self.assertEqual(updated.tts_preprocessing['url_policy'], 'keep')`
2. `self.assertTrue(updated.tts_preprocessing['sentence_per_line'])`
3. `self.assertEqual(group.state['tts_status'], 'TTS Incomplete')`
4. `self.assertNotIn('audiobook', group.state)`
5. `self.assertNotIn('video', group.state)`
6. `self.assertTrue(Path(group.txt_path).exists())`

**Trace:** GREEN: A1/A2 → `PUT /api/settings tts_preprocessing` then `GET /api/settings` reflects `url_policy=keep`, `sentence_per_line`; A6 → after the change the group `txt_path` exists and the canonical txt/json bytes equal those captured before it (S6 review: A6 moved out of the xfail test so a gap failure cannot mask it). XFAIL G1: A3–A5 → after a real video-ready group, `/api/state` group must be `TTS Incomplete` with audiobook/video removed; web/core keeps `Completed`.

</details>


### `tests/test_tts_ui.py` (baseline SHA-256 `70b3f654fd00744dbac34fe9f1cb281f4971cd5d905ffd46897063d395b785f3`)

<details><summary>#85 <code>TtsUiTests.test_zero_successes_show_root_error_without_merge_dialog</code> — Migrate</summary>

1. `dialog.assert_called_once()`
2. `self.assertFalse(dialog.call_args.kwargs["allow_merge"])`
3. `self.assertIn("Không tạo được đoạn MP3 nào", window.stage4_tts_status.text())`
4. `self.assertIn("Invalid voice", window.stage4_tts_status.text())`
5. `self.assertIsNone(window._merge_thread)`

**Trace:** Real group `tts` job with the fake Edge-TTS client raising the baseline ValueError("Invalid voice ''."). A4 → job result row `error` and `/api/state` group `last_error` contain 'Invalid voice'; `tts_status` 'TTS Incomplete', no `audiobook`, no MP3 in the group folder. A2/A5 (no merge offered/started) → `merge_partial` with `allow_partial=true` fails 'Partial merge requires both valid audio chunks and missing chunks' and no audiobook.mp3 is published.

</details>

<details><summary>#86 <code>TtsUiTests.test_failed_chunk_dialog_shows_original_and_failed_part_text</code> — Migrate</summary>

1. `self.assertIsNotNone(dialog.merge_button)`
2. `self.assertIn("TimeoutError", dialog.failure_details.text())`
3. `self.assertIn("complete original chunk", dialog.failure_text.toPlainText())`
4. `self.assertIn("failed second part", dialog.failure_text.toPlainText())`

**Trace:** `PUT /api/settings tts_retry_count=1`; real `tts` job where the fake client raises TimeoutError('Timeout > 120s') for one chunk. A2 → `/api/state` failure `error_type` 'TimeoutError' / `error_message`; A3 → `original_text` contains the full chunk text; A4 → `failed_part_text` contains the failed request text (current core sends whole chunks, so part == chunk); job result failures equal state; log 'Lỗi đoạn N: Timeout > 120s'. A1 (merge available when some chunks succeeded) → `merge_partial` completes, `tts_status` 'Partial', `excluded_chunks == [N]`.

</details>

<details><summary>#87 <code>TtsUiTests.test_worker_bridges_processor_progress_to_qt_signal</code> — Migrate</summary>

1. `self.assertEqual(updates, [(3, 10, "Đã tạo đoạn 3/10")])`

**Trace:** `tts_max_concurrency=1`; real `prepare` then `tts` job, fake client gated on the last chunk. A1 (processor progress triple reaches the observer unchanged) → while gated, `GET /api/jobs/{id}` progress equals {done: round((N-1)/N·1000), total: 1000, message: '<label>: Đang xử lý đoạn N/N'} and job logs already contain '<label>: Đã tạo đoạn N-1/N'; after release the job completes and the logs list 'Đã tạo đoạn k/N' for k=1..N in order.

</details>


### `tests/test_video_pages.py` (baseline SHA-256 `ecb9f6d6988ec2818630c59f26e967115091b1a35b8a87973a33737b6e651abc`)

<details><summary>#88 <code>VideoPageTests.test_exact_text_and_measured_timeline</code> — Retain</summary>

1. `self.assertEqual([p.text for p in timeline.pages], self.texts)`
2. `self.assertEqual([p.duration for p in timeline.pages], [.737, 1.213])`
3. `self.assertEqual([p.start for p in timeline.pages], [0, .737])`
4. `self.assertAlmostEqual(timeline.pages[-1].end, 1.950)`
5. `self.assertEqual(saved['pages'][1]['text'], self.texts[1])`
6. `self.assertIn('duration 0.737000000', script)`
7. `self.assertIn('option framerate 1000', script)`
8. `self.assertEqual(script.count("file '"), len(self.chunks) + 1)`
9. `self.assertTrue(source_fingerprint(self.media)['timeline_sha256'])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#89 <code>VideoPageTests.test_selective_cache_and_audio_only_updates</code> — Retain</summary>

1. `self.assertEqual(render.call_count, 0)`
2. `self.assertEqual([p.page_path for p in first.pages], [p.page_path for p in second.pages])`
3. `self.assertEqual(render.call_count, 1)`
4. `self.assertEqual(changed.pages[0].page_path, first.pages[0].page_path)`
5. `self.assertNotEqual(changed.pages[1].page_path, first.pages[1].page_path)`
6. `render.assert_not_called()`
7. `self.assertAlmostEqual(retimed.duration, 2.150)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#90 <code>VideoPageTests.test_visual_changes_and_corrupted_cache_repaint</code> — Retain</summary>

1. `self.assertEqual(render.call_count, 1)`
2. `self.assertEqual(render.call_count, 2)`
3. `render.assert_not_called()`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#91 <code>VideoPageTests.test_each_page_names_only_its_own_chapter</code> — Retain</summary>

1. `self.assertEqual(page_chapter_label(7, 'Chương 1–20'), 'Chương 7')`
2. `self.assertEqual(page_chapter_label('12', 'Chương 1–20'), 'Chương 12')`
3. `self.assertEqual(page_chapter_label(0, 'Chương 1–20'), 'Chương 1–20')`
4. `self.assertEqual(page_chapter_label(None, 'Chương 1–20'), 'Chương 1–20')`
5. `self.assertEqual(page_chapter_label('', ''), '')`
6. `self.assertNotEqual(self.chapter_page_bytes('Chương 7', 'label-7.png'), self.chapter_page_bytes('Chương 8', 'label-8.png'))`
7. `self.assertEqual(render.call_count, 1)`
8. `self.assertNotEqual(changed.pages[0].page_path, before.pages[0].page_path)`
9. `self.assertEqual(changed.pages[1].page_path, before.pages[1].page_path)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#92 <code>VideoPageTests.test_cjk_brackets_render_visible_ink_on_the_page</code> — Retain</summary>

1. `self.assertTrue(any(face is fallback for face, _ in segments), segments)`
2. `self.assertAlmostEqual(measure_length(draw, sample, font, fallback), draw.textlength(sample, font=font), delta=1e-6)`
3. `self.assertGreater(measure_length(draw, '【', font, fallback), 4)`
4. `self.assertTrue(DEFAULT_STYLE.frame[0] <= left <= right <= DEFAULT_STYLE.frame[2])`
5. `self.assertTrue(DEFAULT_STYLE.frame[1] <= top <= bottom <= DEFAULT_STYLE.frame[3])`
6. `self.assertGreater(ink((int(bracket_x), body_top, int(bracket_x) + 34, body_bottom + 2)), 30)`
7. `self.assertGreater(ink((int(left), top, int(right), bottom + 2)), 300)`
8. `self.assertGreater(ink((int(title_bracket), title_top, int(title_bracket) + 46, title_bottom + 2)), 40)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#93 <code>VideoPageTests.test_latin_and_vietnamese_advances_are_unchanged_by_the_fallback</code> — Retain</summary>

1. `self.assertEqual(len(segments), 1, segments)`
2. `self.assertIs(segments[0][0], font)`
3. `self.assertAlmostEqual(measure_length(draw, sample, font, fallback), draw.textlength(sample, font=font), delta=1e-6)`
4. `self.assertEqual([segment for _, segment in fallback_segments('hã lên', font, fallback)], ['hã lên'])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#94 <code>VideoPageTests.test_invalid_audio_or_request_provenance_is_rejected</code> — Retain</summary>

1. `self.assertRaisesRegex(VideoValidationError, 'Step 3')`
2. `self.assertRaises(VideoValidationError)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#95 <code>VideoPageTests.test_mismatched_audio_duration_and_cancellation_fail_before_publication</code> — Retain</summary>

1. `self.assertRaisesRegex(VideoValidationError, 'duration total')`
2. `self.assertRaisesRegex(VideoValidationError, 'cancelled')`
3. `self.assertFalse((self.root / 'render_pages').exists())`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#96 <code>VideoPageTests.test_input_change_during_page_generation_keeps_old_timeline</code> — Retain</summary>

1. `self.assertRaisesRegex(VideoValidationError, 'inputs changed')`
2. `self.assertEqual((self.root / 'video_timeline.json').read_bytes(), previous)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#97 <code>VideoPageTests.test_readable_layout_bounds_and_line_budget</code> — Retain</summary>

1. `self.assertEqual(layout['font_size'], DEFAULT_STYLE.body_size)`
2. `self.assertEqual(layout['lines'], expected_lines)`
3. `self.assertEqual(layout['lines'], budget.measure(text).visible_lines)`
4. `self.assertLessEqual(layout['measured_height'], layout['body_height'])`
5. `self.assertLessEqual(layout['paragraph_gap_base'], DEFAULT_STYLE.paragraph_gap)`
6. `self.assertGreaterEqual(layout['paragraph_gap_base'], DEFAULT_STYLE.paragraph_gap_floor)`
7. `self.assertLessEqual(layout['paragraph_gap'], DEFAULT_STYLE.paragraph_gap * (1 + JUSTIFY_MAX_GAP_GAIN))`
8. `self.assertGreaterEqual(layout['spacing_compensation'], 0)`
9. `self.assertLessEqual(layout['title_height'], DEFAULT_STYLE.title_max_height)`
10. `self.assertTrue(DEFAULT_STYLE.frame[0] <= left <= right <= DEFAULT_STYLE.frame[2])`
11. `self.assertTrue(DEFAULT_STYLE.frame[1] <= top <= bottom <= DEFAULT_STYLE.frame[3])`
12. `self.assertEqual(column_layout['lines'], 9)`
13. `self.assertTrue(column_x <= left and right <= column_x + column)`
14. `self.assertRaisesRegex(VideoValidationError, 'body band')`
15. `self.assertFalse((self.root / 'overflow.png').exists())`
16. `self.assertRaisesRegex(VideoValidationError, 'sanity guard')`
17. `self.assertFalse((self.root / 'overflow.png').exists())`
18. `self.assertRaisesRegex(VideoValidationError, 'body band')`
19. `self.assertFalse((self.root / 'overflow.png').exists())`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#98 <code>VideoPageTests.test_paragraph_breaks_compress_before_a_page_fails</code> — Retain</summary>

1. `self.assertEqual(layout['font_size'], DEFAULT_STYLE.body_size)`
2. `self.assertLess(layout['paragraph_gap'], DEFAULT_STYLE.paragraph_gap)`
3. `self.assertGreaterEqual(layout['paragraph_gap'], DEFAULT_STYLE.paragraph_gap_floor)`
4. `self.assertLessEqual(layout['measured_height'], layout['body_height'])`
5. `self.assertTrue(DEFAULT_STYLE.frame[0] <= left <= right <= DEFAULT_STYLE.frame[2])`
6. `self.assertTrue(DEFAULT_STYLE.frame[1] <= top <= bottom <= DEFAULT_STYLE.frame[3])`
7. `self.assertRaisesRegex(VideoValidationError, 'body band')`
8. `self.assertFalse((self.root / 'full-gap.png').exists())`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#99 <code>VideoPageTests.test_reclaimed_bottom_margin_absorbs_the_reported_three_pixel_overflow</code> — Retain</summary>

1. `self.assertEqual(layout['font_size'], DEFAULT_STYLE.body_size)`
2. `self.assertLess(layout['paragraph_gap'], DEFAULT_STYLE.paragraph_gap)`
3. `self.assertGreaterEqual(layout['paragraph_gap'], DEFAULT_STYLE.paragraph_gap_floor)`
4. `self.assertLessEqual(layout['measured_height'], layout['body_height'])`
5. `self.assertRaisesRegex(VideoValidationError, 'body band')`
6. `self.assertFalse((self.root / 'v2-margin.png').exists())`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#100 <code>VideoPageTests.test_gap_ladder_always_keeps_the_requested_gap_first</code> — Retain</summary>

1. `self.assertEqual(gap_ladder(DEFAULT_STYLE.paragraph_gap, DEFAULT_STYLE.paragraph_gap_floor), [0.5, 0.4, 0.35, 0.3, 0.25, 0.2])`
2. `self.assertEqual(gap_ladder(1.0), [1.0])`
3. `self.assertEqual(gap_ladder(0.5, 0.5), [0.5])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#101 <code>VideoPageTests.test_nonfinite_audio_metadata_rejected</code> — Retain</summary>

1. `self.assertRaises(VideoValidationError)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#102 <code>VideoPageTests.test_mp3_playable_duration_uses_exact_packet_ticks_and_padding</code> — Retain</summary>

1. `self.assertAlmostEqual(measured.duration, (30 * 1152 - 1405) / 44100, places=12)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#103 <code>RealVfrTests.test_real_mp3_merge_and_fractional_static_pages</code> — Migrate</summary>

1. `self.assertEqual(len(timeline.pages), 3)`
2. `self.assertEqual([p.text for p in timeline.pages], texts)`
3. `self.assertAlmostEqual(timeline.duration, timeline.audiobook_duration, places=3)`
4. `self.assertGreaterEqual(audio.duration + .001, timeline.audiobook_duration)`
5. `self.assertLess(sum(ImageStat.Stat(diff).mean) / 3, 4)`
6. `self.assertFalse(errors, errors)`
7. `self.assertEqual(len(completed), 1)`
8. `self.assertEqual(completed[0].encoder, 'libx264')`
9. `self.assertEqual(len(completed[0].attempt_errors), 1)`
10. `self.assertEqual(completed[0].source, source_fingerprint(media))`

**Trace:** A1–A5 kept verbatim (real FFmpeg merge, VFR timeline, both audio modes, decoded pixels). A8–A10 → `pipeline.media_service.render_video` (the web `video` job path) with `[test_failure, libx264]` candidates and the same `fail_first` command patch, for a probed (`mp3_copy_is_safe`) and a forced-copy audio mode on a freshly prepared timeline: encoder `libx264`, one attempt error, `source == source_fingerprint(media)`, and `validate_timeline_timestamps` on the published MP4.

</details>

<details><summary>#104 <code>RealVfrTests.test_single_page_holds_to_the_end_at_44100hz</code> — Retain</summary>

1. `self.assertAlmostEqual(probe_audio(source, 'ffprobe').duration, actual_duration, places=10)`
2. `self.assertEqual(len(timeline.pages), 1)`
3. `self.assertAlmostEqual(timeline.pages[0].duration, actual_duration, places=10)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>


### `tests/test_video_preview.py` (baseline SHA-256 `1bd657745ecde340da230430027cc1fde846c71257f20a8e38a7debfcc3240e7`)

<details><summary>#105 <code>SidePanelGeometryTests.test_slots_are_fixed_305_squares_flush_in_the_frame_corners</code> — Retain</summary>

1. `self.assertEqual(SIDE_PANEL_SIZE, 305)`
2. `self.assertEqual(left[2] - left[0], 305)`
3. `self.assertEqual(left[2] - left[0], left[3] - left[1])`
4. `self.assertEqual(right[2] - right[0], left[2] - left[0])`
5. `self.assertEqual(right[3] - right[1], left[3] - left[1])`
6. `self.assertEqual(left[0], left_frame)`
7. `self.assertEqual(left[2], left_frame + 305)`
8. `self.assertEqual(right[0], right_frame - 305)`
9. `self.assertEqual(right[2], right_frame)`
10. `self.assertEqual(left[1], top_frame)`
11. `self.assertEqual(right[1], left[1])`
12. `self.assertTrue(left_frame <= box[0] and box[2] <= right_frame)`
13. `self.assertTrue(top_frame <= box[1] and box[3] <= bottom_frame)`
14. `self.assertEqual(side_panel_boxes(DEFAULT_STYLE), side_panel_boxes(DEFAULT_STYLE, 402, 1002))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#106 <code>SidePanelRenderTests.test_cover_and_qr_keep_their_pixels_without_background</code> — Retain</summary>

1. `self.assertEqual(cover["source"], [400, 400])`
2. `self.assertEqual(cover["drawn"], [305, 305])`
3. `self.assertEqual(cover["radius"], DEFAULT_STYLE.radius)`
4. `self.assertIsNone(cover["card"])`
5. `self.assertEqual(qr["drawn"], [305, 305])`
6. `self.assertEqual(qr["quiet_zone"], 0.0)`
7. `self.assertIsNone(qr["card"])`
8. `self.assertEqual(page.getpixel((DEFAULT_STYLE.frame[0] + 100, cover["box"][1] + 100)), (200, 30, 30))`
9. `self.assertNotEqual(page.getpixel((cover["box"][0] + 2, cover["box"][1] + 2)), (200, 30, 30))`
10. `self.assertLess(sum(page.getpixel(center)), 300)`
11. `self.assertNotEqual(page.getpixel((qr["box"][0] + 2, qr["box"][1] + 2)), (255, 255, 255))`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#107 <code>SidePanelRenderTests.test_wide_cover_is_letterboxed_instead_of_cropped</code> — Retain</summary>

1. `self.assertEqual(layout["side_images"]["cover"]["drawn"], [305, 152])`
2. `self.assertEqual(page.getpixel((box[0] + 100, box[1] + 140)), (30, 150, 30))`
3. `self.assertEqual(margin, page.getpixel((box[0] + 105, box[1] + 60)))`
4. `self.assertLess(sum(margin), 120)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#108 <code>SidePanelRenderTests.test_transparent_qr_has_no_card_just_composited_pixels</code> — Retain</summary>

1. `self.assertIsNone(qr["card"])`
2. `self.assertEqual(qr["drawn"], [305, 305])`
3. `self.assertLess(sum(page.getpixel(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))), 300)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#109 <code>SidePanelRenderTests.test_pictures_never_intersect_the_text_column</code> — Retain</summary>

1. `self.assertLessEqual(cover_box[2], column_x - SIDE_PANEL_GAP)`
2. `self.assertGreaterEqual(qr_box[0], column_x + min(DEFAULT_STYLE.body_width, content_width) + SIDE_PANEL_GAP)`
3. `self.assertGreaterEqual(left, column_x)`
4. `self.assertLessEqual(right, column_x + 1150)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#110 <code>SidePanelRenderTests.test_text_layout_is_identical_with_or_without_pictures</code> — Retain</summary>

1. `self.assertEqual(plain, with_pictures)`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#111 <code>SidePanelRenderTests.test_missing_picture_is_reported_instead_of_silently_skipped</code> — Retain</summary>

1. `self.assertRaisesRegex(VideoValidationError, "Cannot open page image")`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#112 <code>SidePanelTimelineTests.test_both_picture_inputs_are_required_before_any_page</code> — Retain</summary>

1. `self.assertEqual(len(timeline.pages), 1)`
2. `self.assertTrue(Path(timeline.pages[0].page_path).is_file())`
3. `self.assertRaisesRegex(VideoValidationError, "requires both page images")`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#113 <code>SidePanelTimelineTests.test_changing_a_picture_repaints_and_updates_the_source_fingerprint</code> — Retain</summary>

1. `self.assertNotEqual(first.pages[0].page_path, second.pages[0].page_path)`
2. `self.assertIn("cover", hashes)`
3. `self.assertIn("qr", hashes)`
4. `self.assertNotEqual(hashes["qr"], hashes["cover"])`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>

<details><summary>#114 <code>VideoPreviewTests.test_build_page_preview_renders_a_real_full_frame</code> — Migrate</summary>

1. `self.assertEqual(note, "")`
2. `self.assertTrue(path.is_file())`
3. `self.assertEqual(page.size, (1920, 1080))`

**Trace:** Real `preview` job after real group TTS: missing QR fails with no output (A1 no-fallback → failure, not sample text). A2/A3 → `page_preview.png` is 1920×1080 and pixel-identical to `render_page` of the first prepared narration chunk (`Chương 1: Mưa`) with both pictures. Changed cover repaints; deleting the audiobook fails closed, keeps the last preview byte-identical and leaves no `.page_preview*` partial.

</details>

<details><summary>#115 <code>VideoPreviewTests.test_build_page_preview_falls_back_to_sample_text</code> — Retire desktop only</summary>

1. `self.assertIn("sample paragraph shown", note)`
2. `self.assertTrue(path.is_file())`

**Trace:** Desktop sample-text fallback preview is retired by O1. The web preview rejects missing prepared inputs instead: #114 (`WebPreviewRegressionTests::test_prepared_preview_renders_real_full_frame`) asserts a missing QR fails with no output, and deleting the audiobook fails closed (AT9).

</details>

<details><summary>#116 <code>VideoPreviewTests.test_first_page_text_uses_the_plan_or_the_sample</code> — Retire desktop only</summary>

1. `self.assertEqual(self.first_page_text(self.root)[2], "sample text (no TTS plan yet)")`

**Trace:** Obsolete desktop helper choosing plan text vs sample text. The web preview always renders the first prepared narration chunk; #114 asserts pixel equality with `render_page` of `load_narration(media)[0]` (AT9).

</details>

<details><summary>#117 <code>VideoPreviewTests.test_dialog_shows_the_whole_rendered_frame</code> — Retire desktop only</summary>

1. `self.assertFalse(dialog._pixmap.isNull())`
2. `self.assertEqual(dialog.caption.text(), "caption line")`

**Trace:** Qt dialog presentation of the frame. The full 1920×1080 rendered frame is asserted by #114 and shown by the web `img[alt="Xem trước trang video"]` in the browser smoke.

</details>


### `tests/test_video_ui.py` (baseline SHA-256 `e3d5e941063a1b0c776810cbb0205f706929279a73124a08746e5e47b44bc54f`)

<details><summary>#118 <code>VideoUiTests.test_step4_uses_current_step3_paths_without_upload_controls</code> — Migrate</summary>

1. `self.assertTrue(window.stage4_continue_btn.isEnabled())`
2. `self.assertEqual(window.tabs.currentIndex(), 3)`
3. `self.assertEqual(window.stage5_thumbnail_label.text(), document.thumbnail_path)`
4. `self.assertEqual(window.stage5_audio_label.text(), document.audiobook_path)`
5. `self.assertFalse(hasattr(window, "stage5_thumbnail_upload_btn"))`
6. `self.assertFalse(hasattr(window, "stage5_audio_upload_btn"))`
7. `detect.assert_called_once()`

**Trace:** Real import/group, thumbnail+TTS twice (second thumbnail replaces the first). A3/A4 → `/api/state` group `thumbnail.path`/`audiobook.path` equal core `require_step4_outputs` paths, both inside the group output folder; the completed video's recorded `source` hashes equal the current thumbnail/audiobook bytes. A5/A6 (no separate upload controls) → `POST /api/jobs` video with `thumbnail_path`/`audiobook_path` options → 422. A7 (capability detection) → job log '<label>: Đang kiểm tra encoder FFmpeg thực tế…'.

</details>

<details><summary>#119 <code>VideoUiTests.test_step5_progress_is_visible_and_video_state_invalidates</code> — Migrate</summary>

1. `self.assertTrue(window.stage5_create_btn.isEnabled())`
2. `self.assertEqual(window.stage5_progress.value(), 250)`
3. `self.assertIn("5.00x", window.stage5_status.text())`
4. `self.assertEqual(document.video_path, "")`

**Trace:** A2/A3 → core `parse_progress_line` for out_time_us=25s/speed=5x/duration=100 yields the baseline {elapsed 25, percentage 25, speed 5, eta 15} (job progress = round(percentage·10)/1000); a real video job logs '<label>: Video: Xs / Ys · Z.Zx · còn Ws' lines from real FFmpeg. A4 → after a new `thumbnail` job, `/api/state` group has no `video` and `require_step5_outputs` raises PipelineStateError.

</details>

<details><summary>#120 <code>VideoUiTests.test_create_video_is_blocked_until_both_page_images_are_added</code> — Migrate</summary>

1. `self.assertFalse(window.stage5_create_btn.isEnabled())`
2. `self.assertIn("Bắt buộc Add đủ 2 ảnh", window.stage5_inputs_status.text())`
3. `error.assert_called_once()`
4. `self.assertIn("Add both page images", str(error.call_args[0][0]))`
5. `self.assertIsNone(window._video_render_session)`

**Trace:** Real video job with no pictures, then cover only. A3/A4 → job fails with group error 'Missing the 1:1 (left) image for the video pages' / 'Missing the QR (right) image for the video pages'. A5 (no render session) → no 'Prepared page'/'Rendering with' log, no MP4, no `video_timeline.json`, no `video` state.

</details>

<details><summary>#121 <code>VideoUiTests.test_cancel_during_async_page_preparation_preserves_old_video</code> — Migrate</summary>

1. `self.assertTrue(started.is_set())`
2. `self.assertEqual(cancelled, [True])`
3. `self.assertFalse(failures)`
4. `encode.assert_not_called()`
5. `self.assertIsNone(session.preparation_thread)`
6. `self.assertEqual(output.read_bytes(), b'previous completed video')`

**Trace:** Real 16-chunk group (fake TTS client, real merge); previous video bytes written at the group's MP4 path as in the baseline. Real video job; A1 → wait for log 'Prepared page 1/'; then `POST /api/jobs/{id}/stop`. A2/A3 → job status 'cancelled' (not failed); A4 → no 'Rendering with' log and fewer prepared pages than chunks; A6 → MP4 bytes unchanged, no `.part.mp4`, no `video` state. Boundary: real page preparation checks cancellation per page; no test patch.

</details>


### `tests/test_youtube_title_tags.py` (baseline SHA-256 `43b1a81f861e0aeb663141172a7f1885289dc5a9687e21266d801ef147a72339`)

<details><summary>#122 <code>UploadedTitleTagTests.test_completed_upload_saves_story_tags_and_next_video_loads_them</code> — Migrate</summary>

1. `self.assertEqual(self.settings.youtube_title_tags, {"Bắc Tống": ["truyện tiên hiệp", "sách nói"]})`
2. `self.assertEqual(tab.saved_titles_combo.findText("Bắc Tống") >= 0, True)`
3. `self.assertEqual(Settings.load(self.root / "config.json").tags_for_uploaded_title(" BẮC TỐNG "), ["truyện tiên hiệp", "sách nói"])`
4. `self.assertEqual(tab.tags_edit.text(), "truyện tiên hiệp, sách nói")`
5. `self.assertEqual(tab.title_edit.text(), "Bắc Tống | Chương 1")`

**Trace:** Upload runs as real HTTP `upload` job (real thumbnail/TTS/FFmpeg video first; FakeAuth + scripted transport). A1 → `settings.youtube_title_tags` after job; A3 → `Settings.load(config).tags_for_uploaded_title('  BẮC   TỐNG ')`; A2 (story appears in saved-title picker) → `GET /api/state` `youtube_tags.history` contains the story; A4 (next video of the story preloads tags) → re-import same story then `youtube_tags.current`; A5 default title → snippet title asserted in #125. Added: request snippet carries the draft tags. Retired: Qt widget reads only.

</details>

<details><summary>#123 <code>UploadedTitleTagTests.test_failure_does_not_save_draft_tags</code> — Migrate</summary>

1. `self.assertEqual(self.settings.youtube_title_tags, {})`
2. `self.assertEqual(Settings.load(self.root / "config.json").youtube_title_tags, {})`

**Trace:** A1, A2 kept verbatim (in-memory and reloaded config) after a failed real upload job (`Response(400)`).

</details>

<details><summary>#124 <code>UploadedTitleTagTests.test_existing_completed_upload_is_imported_when_its_story_is_opened</code> — Migrate</summary>

1. `self.assertEqual(self.settings.tags_for_uploaded_title("Bắc Tống"), ["tag cũ"])`
2. `self.assertEqual(Settings.load(self.root / "config.json").tags_for_uploaded_title("Bắc Tống"), ["tag cũ"])`

**Trace:** A2 kept verbatim. A1 asserts on the live `service.settings`: `open_session` replaces the Settings object, so the baseline's shared `self.settings` would stay stale and could never pass (S6 review fix; positive control `s6-g2-fix-control.log`: with a simulated tag import the body passes, without it fails). Arrangement through HTTP: import + group, completed `youtube_upload.json` with tags, `POST /api/sessions`, `/api/sessions/new`, `/api/sessions/{id}/open`. Web/core does not import tags on story open → recorded as G2, not implemented in test code.

</details>

<details><summary>#125 <code>UploadedTitleTagTests.test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title</code> — Migrate</summary>

1. `self.assertEqual(tab.tags_edit.text(), "tag B")`
2. `self.assertEqual(tab.title_edit.text(), title)`

**Trace:** A1 (picking another story's tags yields 'tag B') → state `youtube_tags.history['Truyện B']` and the uploaded snippet tags `['tag B']`; A2 (video title unchanged) → snippet title `Bắc Tống | Chương 1`.

</details>

<details><summary>#126 <code>UploadedTitleTagTests.test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags</code> — Migrate</summary>

1. `self.assertEqual(panel.editor.tags_edit.text(), "tag đã gửi")`
2. `self.assertEqual(captured[0].tags, ["tag đã gửi"])`
3. `self.assertEqual(panel.editor.tags_edit.text(), "tag mới")`

**Trace:** A2 (pending upload keeps frozen tags) → real upload job resumes the saved session (`PUT` `bytes */N` first) and `youtube_upload.json` metadata tags stay `['tag đã gửi']` despite draft `['tag mới']`; A3 (rejected upload uses story tags) → after rejected state, upload with no draft tags sends snippet tags `['tag mới']`. A1 display-only.

</details>

<details><summary>#127 <code>UploadedTitleTagTests.test_group_upload_uses_story_tags_and_records_confirmed_result</code> — Migrate</summary>

1. `self.assertEqual(panel.editor.tags_edit.text(), "chung, bắc tống")`
2. `self.assertEqual([row.tags for row in captured], [["chung", "bắc tống"]] * 2)`
3. `self.assertEqual(self.settings.tags_for_uploaded_title("Bắc Tống"), ["tag mới"])`
4. `self.assertEqual(Settings.load(self.root / "config.json").tags_for_uploaded_title("Bắc Tống"), ["tag mới"])`

**Trace:** A2 → snippet tags of both created videos in a 2-group real upload job; A3, A4 kept verbatim after a partial (thumbnail-retry failure) upload with a confirmed `video_id`.

</details>

<details><summary>#128 <code>UploadedTitleTagTests.test_unrelated_stories_keep_separate_tags_and_bad_config_is_ignored</code> — Retain</summary>

1. `self.assertEqual(self.settings.tags_for_uploaded_title("TRUYỆN A"), ["a2"])`
2. `self.assertEqual(self.settings.tags_for_uploaded_title("Truyện B"), ["b"])`
3. `self.assertEqual(len(self.settings.youtube_title_tags), 2)`
4. `self.assertEqual(loaded.youtube_title_tags, {"valid": ["one"]})`

**Trace:** Method kept verbatim; AST equal to baseline (`s2-retained-ast.json`).

</details>


### `tests/test_youtube_ui.py` (baseline SHA-256 `10b2600a4a9d94c24356ca08378ef847c6edbb88311a04c20e91b777645d8f5e`)

<details><summary>#129 <code>YouTubeUiTests.test_connect_uses_changed_oauth_settings_without_reentering_tab</code> — Migrate</summary>

1. `factory.assert_called_once_with("new-client.json")`
2. `self.assertIsNot(self.tab.auth, old_auth)`
3. `self.assertEqual(self.tab.account["channel_id"], "channel1")`

**Trace:** A1 → `youtube_connect` job, then `PUT /api/settings youtube_client_secrets_path=new-client.json`, then a second `youtube_connect`; a per-job `YouTubeAuth` factory records ['fake.json', 'new-client.json'] (the changed path is used with no screen re-entry). A2 → the second job's auth is a new instance. A3 → both job results report `account.channel_id == 'channel1'`.

</details>

<details><summary>#130 <code>YouTubeUiTests.test_configured_oauth_without_saved_login_explains_sign_in</code> — Migrate</summary>

1. `self.assertEqual(self.tab.account_label.text(), "Not connected")`
2. `self.assertIn("Connect YouTube Account", self.tab.connection_hint.text())`
3. `self.assertFalse(self.tab.upload_btn.isEnabled())`
4. `self.assertTrue(self.tab.connect_btn.isEnabled())`

**Trace:** A2 (sign-in guidance) → with `FakeAuth.restore` returning None, an upload job on a video-ready group fails with 'Chưa kết nối YouTube. Hãy kết nối tài khoản Google.'; zero transport calls; no group youtube state. A4 intent (connect still possible) → a later `youtube_connect` completes with account user@example.com.

</details>

<details><summary>#131 <code>YouTubeUiTests.test_group_connection_error_visible_beside_account</code> — Migrate</summary>

1. `self.assertEqual(self.tab.connection_hint.text(), "OAuth test error")`
2. `self.assertFalse(self.tab.connection_hint.isHidden())`
3. `self.assertTrue(self.tab.status_label.isHidden())`
4. `self.assertTrue(self.tab._connection_error_dialog.isVisible())`
5. `self.assertEqual(self.tab._connection_error_dialog.text(), "OAuth test error")`

**Trace:** A1/A5 → `FakeAuth.connect` raises YouTubeAuthError('OAuth test error'); the `youtube_connect` job fails with error == 'OAuth test error' and exactly one error-level log line with the same text.

</details>

<details><summary>#132 <code>YouTubeUiTests.test_connect_without_config_displays_error_dialog</code> — Migrate</summary>

1. `self.assertFalse(self.tab.busy)`
2. `self.assertTrue(self.tab._connection_error_dialog.isVisible())`
3. `self.assertIn("Settings", self.tab._connection_error_dialog.text())`

**Trace:** A3 → empty `youtube_client_secrets_path` and the real (unpatched) `YouTubeAuth` (it rejects before keyring/browser/network): the `youtube_connect` job fails with an error containing 'Settings' and result None. A1 (not busy) → the job reaches a terminal state and the next identical job is accepted (202) and fails the same way.

</details>

<details><summary>#133 <code>YouTubeUiTests.test_continue_and_direct_navigation_share_automatic_inputs_and_metadata</code> — Migrate</summary>

1. `self.assertEqual(self.window.tabs.count(), 5)`
2. `self.assertEqual(self.window.tabs.currentIndex(), 4)`
3. `self.assertEqual(self.tab.video_label.text(), self.document.video_path)`
4. `self.assertEqual(self.tab.thumbnail_label.text(), self.document.thumbnail_path)`
5. `self.assertEqual(self.tab.title_edit.text(), "Bắc Tống | Chương 1")`
6. `self.assertEqual(self.tab.account_label.text(), "user@example.com")`
7. `self.assertIn("Audiobooks", self.tab.channel_label.text())`
8. `self.assertEqual([self.tab.privacy_combo.itemText(i) for i in range(3)], ["Private", "Unlisted", "Public"])`
9. `self.assertTrue(self.tab.upload_btn.isEnabled())`
10. `self.assertFalse(any("select" in btn.text().lower() or "save" in btn.text().lower() for btn in self.tab.findChildren(QPushButton)))`
11. `self.assertEqual(self.tab.video_label.text(), self.document.video_path)`
12. `self.assertRaises(PipelineStateError)`

**Trace:** A3/A11 → the `/api/state` group read before the `youtube_connect` step equals the read after it; the group's state video path == `require_step5_outputs(gid).video_path`. A4 → the thumbnail lies in the group output dir, and the uploaded thumbnail bytes equal it. A5 → an upload with no metadata sends snippet title 'Bắc Tống | Chương 1'. A6/A7 → the `youtube_connect` result has email user@example.com and channel_title containing 'Audiobooks'. A12 → a rerun of the `thumbnail` job with a new image on group 2: core `require_step5_outputs(g2)` raises PipelineStateError; the upload job for g2 fails, with zero transport calls and no youtube state.

</details>

<details><summary>#134 <code>YouTubeUiTests.test_progress_completion_copy_url_and_duplicate_confirmation</code> — Migrate</summary>

1. `self.assertEqual(self.tab.progress.value(), 520)`
2. `self.assertIn("/s", self.tab.status_label.text())`
3. `self.assertEqual(self.document.youtube_upload_state["video_id"], "abc123")`
4. `self.assertEqual((job / alias).read_bytes(), Path(source).read_bytes())`
5. `self.assertEqual(self.tab.progress.value(), 1000)`
6. `self.assertFalse(self.tab.upload_btn.isEnabled())`
7. `self.assertTrue(self.tab.progress.isVisible())`
8. `self.assertIs(self.tab.progress.parentWidget(), self.tab)`
9. `self.assertTrue(self.tab.again_btn.isEnabled())`
10. `self.assertIn("This job has already been uploaded", self.tab.result.toPlainText())`
11. `self.assertEqual(self.app.clipboard().text(), "https://www.youtube.com/watch?v=abc123")`
12. `self.assertEqual(len(self.tab.auth.transport.calls), calls)`

**Trace:** A3 → upload job completed; state video_id abc123 and video_url https://www.youtube.com/watch?v=abc123; final job progress done == total; logs include 'Đang upload YouTube…'. A4 → uploaded video/thumbnail bytes equal `require_step5_outputs`; the group folder's final.txt equals final.json['text']; audiobook.mp3 is non-empty. A10/A12 (no duplicate without confirmation) → a re-upload with no flag gives row status 'skipped' and zero calls. Confirmed duplicate → `POST /api/jobs upload {allow_duplicate: true}` asserts 202, a completed row and a new video_id def456. Actual: 422 'Tùy chọn không được hỗ trợ: allow_duplicate'.

</details>

<details><summary>#135 <code>YouTubeUiTests.test_ai_checkbox_uploads_both_values_and_restores_saved_choice</code> — Migrate</summary>

1. `self.assertFalse(self.tab.ai_check.isChecked())`
2. `self.assertIs(payload["status"]["containsSyntheticMedia"], enabled)`
3. `self.assertIs(self.tab.state["metadata"]["contains_synthetic_media"], enabled)`
4. `self.assertTrue(self.tab.ai_check.isChecked())`

**Trace:** A1 → a group without an override uploads containsSyntheticMedia False (the default). A2/A3 (subTests False/True) → one upload job over 2 groups with `group_metadata {g2: {contains_synthetic_media: true}}`; the payload status.containsSyntheticMedia is [False, True]; each group's saved metadata matches. A4 → after session save, app restart and session open, the saved choices are restored (g2 True, g1 False).

</details>

<details><summary>#136 <code>YouTubeUiTests.test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry</code> — Migrate</summary>

1. `self.assertTrue(self.tab.retry_thumbnail_btn.isEnabled())`
2. `self.assertIn("Thumbnail", self.tab.result.toPlainText())`
3. `self.assertEqual(len(self.tab.auth.transport.calls), 1)`
4. `self.assertFalse(self.tab.retry_thumbnail_btn.isEnabled())`
5. `self.assertFalse(self.tab.upload_btn.isEnabled())`
6. `self.assertEqual(self.tab.state["video_id"], "abc123")`

**Trace:** A2 → after a thumbnail 403, the job fails; the row error equals the state thumbnail_error (non-empty); video_id abc123; thumbnail_uploaded False. A3 → a `youtube_retry_thumbnail` job makes exactly 1 call and completes; thumbnail_uploaded True. A6 → after session save, app restart and session open, video_id is still abc123 with status completed; a re-upload is 'skipped' with zero calls (covers A5's intent).

</details>

<details><summary>#137 <code>YouTubeUiTests.test_bad_metadata_never_starts_worker_and_schedule_requires_private</code> — Migrate</summary>

1. `self.assertFalse(self.tab.busy)`
2. `self.assertFalse(self.tab.auth.transport.calls)`
3. `self.assertIn("Title", self.tab.status_label.text())`
4. `self.assertFalse(self.tab.busy)`
5. `self.assertIn("Private", self.tab.status_label.text())`

**Trace:** A3 → metadata title '' gives row error containing 'Title'. A5 → title 'Scheduled title' with a future publish_at and privacy 'public' gives row error containing 'Private'. A2 → zero transport calls across both; no youtube state saved.

</details>

<details><summary>#138 <code>YouTubeUiTests.test_standalone_resume_preserves_saved_metadata_and_past_schedule</code> — Migrate</summary>

1. `self.assertEqual(self.tab.state["status"], "completed")`
2. `self.assertEqual(self.tab.state["metadata"], metadata.__dict__)`
3. `self.assertEqual(first[0], "PUT")`
4. `self.assertEqual(first[2]["headers"]["Content-Range"], f"bytes */{state['total_bytes']}")`
5. `self.assertTrue(self.tab.ai_check.isChecked())`
6. `self.assertFalse(self.tab.busy)`
7. `self.assertIn("future", self.tab.status_label.text())`

**Trace:** A1–A4 → a pending 'uploading' state (Saved title, past publish_at, synthetic True, session key in FakeAuth.secret_store, real video fingerprint) plus an upload with an edited title: completed; saved metadata == the original dict; the first call is a PUT with Content-Range `bytes */{total}`. A5 → the restored metadata has contains_synthetic_media True. A7 → an explicit new upload with the restored (past) schedule on a fresh group 2 fails with 'future' and zero calls.

</details>

<details><summary>#139 <code>YouTubeUiTests.test_api_worker_keeps_ui_responsive_and_cancel_saves_session</code> — Migrate</summary>

1. `self.assertTrue(called.is_set())`
2. `self.assertNotEqual(thread_ids[0], threading.get_ident())`
3. `self.assertFalse(self.window.tabs.isTabEnabled(0))`
4. `self.assertTrue(ticks)`
5. `self.assertTrue(self.tab._cancel.is_set())`
6. `self.assertEqual(state["status"], "cancelled")`
7. `self.assertEqual(state["bytes_sent"], 8388608)`
8. `self.assertTrue(self.window.tabs.isTabEnabled(0))`
9. `self.assertTrue(self.tab.upload_btn.isEnabled())`

**Trace:** A1/A2 → a blocking chunk callable runs on a non-test thread. Responsiveness → while blocked, `GET /api/jobs/{id}` is 'running', `/api/state` returns 200, and another mutation gets 409. A5 → stop returns 'stopping'. A6/A7 → the job is cancelled; youtube_upload.json has status 'cancelled' and bytes_sent == the confirmed Range end + 1 (also in /api/state). Idle again → the resume upload completes; the first call is `bytes */{total}` and the next chunk starts at the saved offset.

</details>

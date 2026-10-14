# Evidence — Remove PyQt6 desktop (web-only)

- Status: S0–S6 executed (self-review and independent review done; review fixes rerun). Ready for human PR review. Plan: `intent/web-only-remove-pyqt6/plan.md` (Approved). Ledger: `intent/web-only-remove-pyqt6/coverage.md`.
- Base: `main` at `8b4bb314a5e6ae073050535a99f2000930c286cb` (PR #3 merge; merged before S0, ancestor of `origin/main`). Branch: `codex/web-only-remove-pyqt6`.
- Tested code identity: the PR head commit. This report and the ledger sit in the same commit, so the commit cannot quote its own SHA. The PR body names the head SHA. Every check below ran against the uncommitted tree that became that commit:
  - **Code-scope fingerprint `2ac4b176c8fc4b55ea125908b94b59950bfeece0be5091e5885e3f48b7807f0e`** (after the S6 review fixes; the S5 value `af0ab77c…` is superseded because three test files changed). Recompute it on the head commit with `$WEB_ONLY_RUN/bin/code_fp.sh <worktree>` (hash script listed below; it covers all non-ignored paths except `intent/web-only-remove-pyqt6/`). The fingerprint is the same before and after commit (S6 check).
  - **Full source fingerprint (includes task docs) during the S6 reruns: `9244faba282c1aa2f8841aeb1eb07aa6ae2ab14d5a1a341cdf10cadae9946705`** (`evidence/s6-source-fingerprint-{before,after-build,after-smoke}.txt`). It is identical before the build, after the build and after the smoke, so no test or build wrote to the source tree. The S5 value `c406d3b5…` held through S5 in the same way. The ledger and this report were regenerated after the reruns, so the committed docs differ from both values; the code-scope fingerprint above excludes them.
- Raw artifacts stay local under `$WEB_ONLY_RUN` (a private `mktemp -d` run root outside Git) until human review ends. `gh` cannot attach binaries to a PR, and none were uploaded elsewhere. Paths below are `$WEB_ONLY_RUN`-relative.

## Environment

| Item | Value |
| --- | --- |
| OS | Linux (CachyOS kernel 7.x), x86_64 |
| Python | 3.14.7 in a fresh venv (`include-system-site-packages = false`); PyQt6 not installed (`importlib.util.find_spec("PyQt6") is None`). The project floor is 3.11; **Python 3.11 itself was not run.** |
| Key Python packages | pytest 9.1.1, fastapi 0.143.0, starlette 1.8.0, uvicorn 0.54.0, httpx 0.28.1, pillow 12.3.0, edge-tts 7.2.8 (full list in `evidence/pip-freeze.txt`, 53 lines) |
| Node / npm | v22.23.3 / 10.9.9; `npm ci --ignore-scripts` (120 packages); package manifests and lockfiles unchanged |
| Frontend toolchain | Vite 6.4.4, TypeScript ~5.9, React 19; tests run with `node --experimental-strip-types --test` |
| Media | FFmpeg/FFprobe n9.0.2 (real binaries; required VFR tests ran, none skipped) |
| Sandbox | bubblewrap 0.13.0 |
| Browser | Firefox 157.0.1, headless, driven over its built-in WebDriver BiDi by a Node 22 script (built-in `WebSocket`; no driver, Playwright or Selenium installed) |

### Isolation used for every run

- `wo_py`: bubblewrap with `--unshare-all` (private network namespace: loopback only, no DNS), `--clearenv` plus an explicit allowlist, read-only source, `/tmp` tmpfs. Each invocation gets a private run directory with its own `HOME`, `TMPDIR`, XDG dirs and `NOVEL_PIPELINE_CONFIG_DIR`. Successful runs are deleted; failed runs are retained for diagnosis, and every run is logged in `evidence/runs.tsv`. S0 controls: loopback 200; `1.1.1.1:443` and `8.8.8.8:53` ENETUNREACH; DNS `gaierror`; under the host home only the read-only project parent directory is visible; source writes fail with EROFS.
- `wo_node`: the same sandbox for npm, with the source read-only. Writes go to private overlays only: `frontend/node_modules/.tmp`, `.vite` and `.vite-temp` (gitignored mount points). The build goes to `$WEB_ONLY_DIST`, and no `frontend/dist` was created. Registry fetch was denied (`EAI_AGAIN`).
- `wo_smoke_server`: the same sandbox, but with `--share-net`, because the host browser must reach its loopback port. Egress is then controlled by:
  - the in-process socket guard in `tests/web_smoke_app.py`, which denies non-loopback connect, `connect_ex` and `getaddrinfo`; the server's self-check printed all three as `denied` and loopback as `connected`;
  - fake providers at the TTS client and Google auth/transport boundaries;
  - the bind address `127.0.0.1` only.

  **Limit:** this guard is a Python-level patch, not an OS sandbox.
- Browser: `env -i` with `PATH`, `HOME`, `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_RUNTIME_DIR`, `LANG` and `MOZ_HEADLESS` pointing into a fresh run dir. It uses a fresh profile whose `user.js` routes every non-loopback request to a dead proxy `127.0.0.1:9` (Plan §6). Launch args: `--headless --no-remote --window-size=1440,1000 --profile <run>/profile --remote-debugging-port=0`.

## Commands and results

Every Python line ran as `bash -c 'source $WEB_ONLY_RUN/bin/wo-env.bash; wo_py …'` from the worktree root.

| Stage | Command | Exit | Counts / result | Log |
| --- | --- | --- | --- | --- |
| S1 | `python -m unittest -v tests.test_web_only_runtime.WebOnlyRuntimeTests.test_desktop_boundary_removed` (baseline) | 1 | expected RED: `AssertionError` listing present `app.py`, `requirements-desktop.txt`, `ui/…` (not ImportError/collection-zero) | `evidence/s1-red-boundary.log` |
| S1 | `… test_real_backend_host_origin_policy` (baseline) | 0 | 38 cases as expected (table below) | `evidence/s1-host-origin.log` |
| S1 | `… test_supported_modules_import_without_qt` / `test_real_backend_health_without_qt` / `test_cli_fixture_pipeline_without_qt` | 0 / 0 / 0 | OK each | `evidence/s1-test_*.log` |
| S1 | import-blocker negative control (child importing `app`, `ui.copy_controls`) | 1 / 1 | `ImportError: retired desktop import` (blocker effective) | `evidence/s1-blocker-negative-control.log` |
| S1 | `pytest -q` over 18 Qt-free modules | 0 | 213 passed, 99 subtests | `evidence/s1-preflight-qtfree.log` |
| S1 | `pytest -q -rA tests/test_headless_service.py tests/test_headless_media.py tests/test_web_jobs.py tests/test_web_api.py` | 0 | 38 passed, 42 subtests | `evidence/s1-preflight-headless-web.log` |
| S2 | FakeAuth extraction: AST of `tests/web_only_support.FakeAuth` vs baseline `tests/test_youtube_ui.py:30`; child import with a PyQt6/`ui` blocker | 0 | AST equal; no Qt/`ui` import attempted | `evidence/s2-fakeauth-ast.json`, `evidence/s2-support-blocker-import.log` |
| S2 | `pytest -q tests/test_youtube_title_tags.py` | 1 | 6 passed, 1 failed (#124 = gap G2) | `evidence/s2-title-tags.log` |
| S2 | `pytest -q -rA` over the 7 mixed modules | 1 | 78 passed, 2 failed (G1 #84, G2 #124) | `evidence/s2-focused.log` |
| S2 | headless/web + runtime set | 1 | 42 passed, 1 failed (`test_desktop_boundary_removed`, expected before S4) | `evidence/s2-headless-web.log` |
| S2 | frontend tests | 0 | 11 pass | `evidence/s2-frontend-test.log` |
| S3 | `pytest -q tests/test_web_business_regressions.py tests/test_youtube.py tests/test_youtube_auth.py tests/test_youtube_pipeline.py` (before owner dispositions) | 1 | 78 passed, 4 failed (G3 #14/#15, G4 #134, G5 #19) | `evidence/s3.log` |
| S3 | same, after dispositions | 0 | 79 passed, 5 xfailed, 64 subtests | `evidence/s3-dispositions.log` |
| S3 | each xfail test body run without its decorator | — | each fails at its gap assertion | `evidence/s3-xfail-reasons.log` |
| S3 | retained-method AST comparison | — | 62/62 retained methods keep their baseline AST | `evidence/s3-retained-ast.json` |
| S4 | `python -m unittest -v tests.test_web_only_runtime` | 0 | 5 OK; the S1 RED is now GREEN; Host/Origin still GREEN | `evidence/s4-runtime-oracles.log` |
| S4 | `pytest -p no:cacheprovider --collect-only -q` | 0 | 365 collected; no Qt import or collection error | `evidence/s4-collect.log` |
| S5 | `pytest -p no:cacheprovider -q -rA --junitxml=$WEB_ONLY_RUN/evidence/pytest-full.xml` | 0 | **360 passed, 5 xfailed, 0 skipped, 0 failed, 0 errors**, 166 subtests | `evidence/pytest-full.log`, `evidence/pytest-full.xml` |
| S5 | `wo_node run test` | 0 | 11 pass, 0 fail, 0 skipped | `evidence/frontend-test.log` |
| S5 | `wo_node run build -- --outDir "$WEB_ONLY_DIST" --emptyOutDir` (`tsc -b && vite build`) | 0 | 1667 modules; 3 output files | `evidence/frontend-build.log`, `evidence/dist-manifest.txt` |
| S5 | isolation repeat (`bin/isolation_probe.py`, forward and reversed module order, in one process each) | 0 / 0 | 124 passed, 5 xfailed each; 8 patch targets restored; `os.environ` restored; 0 child processes; config dir fresh at start | `evidence/s5-isolation-forward.log`, `evidence/s5-isolation-reverse.log` |
| S5 | browser smoke `bin/run-smoke.sh` (attempt 8) | 0 | 16 PASS, 1 XFAIL (G4); 0 console errors; teardown clean | `evidence/smoke-attempts/smoke-attempt8-*` |
| S6 | `pytest -q -rA` over the modules touched by the review fixes | 0 | 32 passed, 2 xfailed, 62 subtests | `evidence/s6-fix-affected.log` |
| S6 | each xfail test body run without its decorator (`bin/xfail_reasons.py`) | 0 | each fails at its gap assertion (table below) | `evidence/s6-xfail-reasons.log` |
| S6 | G2 positive control (`bin/g2_fix_control.py`) | 0 | without a fix: FAIL `None != ['tag cũ']`; with a simulated fix: PASS | `evidence/s6-g2-fix-control.log` |
| S6 | `pytest -p no:cacheprovider -q -rA --junitxml=$WEB_ONLY_RUN/evidence/pytest-full-s6.xml` | 0 | **360 passed, 5 xfailed, 0 skipped, 0 failed, 0 errors**, 166 subtests | `evidence/pytest-full-s6.log`, `evidence/pytest-full-s6.xml` |
| S6 | isolation repeat, forward and reversed | 0 / 0 | 124 passed, 5 xfailed each; 8 patch targets restored; `os.environ` restored; 0 child processes; config dir fresh at start | `evidence/s6-isolation-forward.log`, `evidence/s6-isolation-reverse.log` |
| S6 | `wo_node run test`; `wo_node run build …` | 0 / 0 | 11 pass; 1667 modules; manifest identical to S5 | `evidence/s6-frontend-test.log`, `evidence/s6-frontend-build.log`, `evidence/s6-dist-manifest.txt` |
| S6 | browser smoke `bin/run-smoke.sh` (attempt 9, adds step 18) | 0 | **17 PASS, 1 XFAIL (G4)**; 0 console errors; teardown clean | `evidence/smoke-*.{log,json,txt,png}` |
| S6 | run-dir cleanup after diagnosis | — | 5 retained run dirs removed; `runs/` empty; no leftover processes | `evidence/s6-run-cleanup.txt` |

Full-suite warnings (S5 and S6): one, `StarletteDeprecationWarning` from `fastapi.testclient` (httpx with `starlette.testclient`). It is a third-party deprecation and has no effect on results.

### Expected failures (owner disposition 2026-10-13)

Each xfail test holds only gap assertions. Its supported sibling assertions sit in a separate test that passes. A product fix turns the xfail into an unexpected success, which fails the run. The S6 independent review found two places where this did not hold; both were fixed (see S6 below), and the line numbers are from `evidence/s6-xfail-reasons.log` (S3 values in `evidence/s3-xfail-reasons.log`).

| Gap | xfail test | Fails at |
| --- | --- | --- |
| G1 settings-change invalidation | `tests/test_tts_preprocessing.py::HeadlessLegacyTests::test_config_ui_and_downstream_invalidation` | :462 `'Completed' != 'TTS Incomplete'` |
| G2 tag import on story open | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_existing_completed_upload_is_imported_when_its_story_is_opened` | :72 `None != ['tag cũ']` (on the live `service.settings`) |
| G3 auth-failure pause queue | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_auth_failure_pauses_remaining_queue` | :467 job status `failed`, not `paused` |
| G3 paused shared edits | `…::test_paused_batch_shared_edits_affect_only_unstarted_sessions` | :509 no paused state to resume |
| G4 web duplicate upload | `…::test_confirmed_duplicate_upload_creates_new_video` | :1047 HTTP 422 `allow_duplicate` != 202 |

G5 (#19 desktop refusal wording) is retired like #120. The test asserts the core refusal "Missing the 1:1 (left) image for the video pages" and passes.

## Real-backend Host/Origin oracle (AT2)

`test_real_backend_host_origin_policy` starts `python -B -m backend --port <free port>` as a child, without TestClient, and sends raw HTTP. It ran GREEN at S1 (baseline), S4, S5 and S6 (in the full suites). The 38 cases (S1 log):

| Case | Request | Expected | Actual |
| --- | --- | --- | --- |
| Loopback Host | `Host: 127.0.0.1:P`, `localhost:P`, `LOCALHOST:P` → `/api/health` | 200 | 200 ×3 |
| Same-origin | `Origin: http://127.0.0.1:P` with `Host: 127.0.0.1:P`; `Origin: http://localhost:P` with `Host: localhost:P` | 200 | 200 ×2 |
| Dev origins | `Origin: http://localhost:5173`, `http://127.0.0.1:5173` | 200 | 200 ×2 |
| Dev CORS preflight | `OPTIONS /api/jobs`, `Origin: http://localhost:5173`, `Access-Control-Request-Method: POST` | 200, ACAO = origin | 200 |
| Rejected Host | `evil.example`, `localhost.evil.example`, `127.0.0.1.evil.example`, `[::1]:P`, `localhost:0`, `localhost:70000` × (`/api/health`, `/`) | 403 | 403 ×12 |
| Rejected Origin (with `Host: 127.0.0.1:P`) | `null`, `https://evil.example`, `http://localhost:9999`, `https://127.0.0.1:P`, `http://127.0.0.1:P/evil`, `http://user@127.0.0.1:P`, cross-host `http://localhost:P`, duplicate Origin headers × (`/api/health`, `/`) | 403 | 403 ×16 |
| Protocol | no Host header; two Host headers | non-2xx | 400 / 400 |

## Acceptance status

| AT/AR | Status | Evidence |
| --- | --- | --- |
| AT1 Qt-free runtime | PASS | PyQt6 absent in venv; `test_supported_modules_import_without_qt` and `test_desktop_boundary_removed` GREEN; no Qt display variables (`--clearenv`) |
| AT2 backend + built frontend + Host/Origin | PASS | `test_real_backend_health_without_qt`; Host/Origin table; the browser loaded the real Vite build served by `create_app(dist_dir=$WEB_ONLY_DIST)` through loopback (smoke steps 1–2) |
| AT3 CLI | PASS | `test_cli_fixture_pipeline_without_qt`: real `python -m pipeline --help` and `run … --title --group-size --export json` child, natural exit 0, ordered output, no provider options |
| AT4 collection / regression / ledger | PASS, with recorded gaps | 365 collected; full suite 360 passed + 5 xfailed (S5 and S6); frontend 11 pass and build OK; all 14 Qt-related baseline files audited in `coverage.md` (139 methods: 129 with executed destinations, 10 retired desktop-only) |
| AT5 normalize/edit/group/prepare/overrides/cancel | PASS (G1 xfail) | ledger rows for `test_pipeline_data_flow`, `test_step2_ui`, `test_tts_preprocessing` (the G1 sibling asserts canonical `final.txt`/`tts_chunks.json` bytes survive a preprocessing change), `test_group_batches`; smoke steps 3–5 and 7–11 |
| AT6 sessions / settings / failures | PASS | `tests/test_sessions.py`, `test_last_input_folder.py`, BR settings tests; smoke step 6 (save, new, reopen) and step 18 (a desktop-shaped schema-v1 session reopens in the browser with its legacy upload metadata, tags and cover/QR paths, and its stored `ui` is unchanged) |
| AT7 real FFmpeg media | PASS | `RealVfrTests` (2 tests) ran with real FFmpeg (5.1 s, 1.0 s), not skipped; headless media/preview tests; smoke step 14 rendered and downloaded MP4 (`ftyp`) |
| AT8 fake OAuth/YouTube/TTS orchestration | PASS (G2, G3, G4 xfail) | BR YouTube/TTS tests; smoke steps 7–11 and 15–17 (cancel, failure, declined partial merge, chunk recovery, upload with one rejected thumbnail then retry, duplicate refusal) |
| AT9 web preview | PASS | `tests/test_video_preview.py` incl. missing/tampered inputs; smoke step 13: 1920×1080 preview from uploaded cover/QR |
| AT10 isolation repeat / network controls | PASS, with limits | isolation probe forward and reverse; smoke post-checks; negative (dead-proxy navigation, denied egress/DNS) and positive (loopback) controls. Limits are listed under Isolation. |
| AR1 deletions vs scope | Ready for review | the commit contains only §2 allowlist paths (21 deletions, 14 modifications, 4 new tests, task docs) |
| AR2 docs / parity statements | Ready for review | README/INSTALL/USAGE/CLAUDE updated for web/CLI only; fixtures do not establish real TTS/YouTube parity (below) |
| AR3 before/after evidence | This report + `coverage.md` | baseline RED → GREEN; source fingerprint unchanged by build/tests |

## Browser smoke (S6, attempt 9)

Driver: `bin/smoke.mjs` + `bin/bidi.mjs`, run by `bin/run-smoke.sh`. Server: `python -B -m tests.web_smoke_app` under `wo_smoke_server`, using the real `PipelineService`, `JobManager`, FastAPI app and built frontend. Only the Edge-TTS client and the Google account/transport are fake. The story is a generated fixture; no real story text is used.

Steps, with job outcomes taken from `/api/jobs` and screenshots under `evidence/`:

| # | Step | Result | Jobs (action:status `id prefix`) | Observed |
| --- | --- | --- | --- | --- |
| 1 | control: non-loopback navigation fails | PASS | — | error: unknown error: Error: NS_ERROR_PROXY_CONNECTION_REFUSED |
| 2 | control: loopback app loads | PASS | — | health: 200; screenshot `smoke-01-loaded.png` |
| 3 | import story by local path (import → normalize chain) | PASS | import:completed `159a51ee`; normalize:completed `8640880e` | screenshot `smoke-02-imported.png` |
| 4 | edit text and save (confirmed) | PASS | edit:completed `a22024ac` | dialog: Áp dụng văn bản đã sửa? |
| 5 | group by 2 chapters with title | PASS | group:completed `c5be5424` | groups: ["Chương 1-2", "Chương 3-4"]; screenshot `smoke-03-grouped.png` |
| 6 | save session, start new, reopen saved | PASS | — | newDialog: Bắt đầu phiên mới?; reopened: {"title": "Truyện khói", "groups": 2}; screenshot `smoke-04-reopened.png` |
| 7 | TTS on selected group 1 with uploaded thumbnail | PASS | thumbnail:completed `29370cca`; tts:completed `645a3721` | screenshot `smoke-05-tts-group1.png` |
| 8 | TTS on group 2 is stopped from the job bar (cancel) | PASS | thumbnail:completed `e996cfc7`; tts:cancelled `20d88de8` | dialog: Dừng tác vụ?; screenshot `smoke-06-tts-cancelled.png` |
| 9 | TTS on group 2 fails at the fake provider and shows the failed chunk | PASS | thumbnail:completed `098efa81`; tts:failed `413665cb` | screenshot `smoke-07-tts-failed-chunk.png` |
| 10 | partial-audio confirmation can be declined without starting a job | PASS | — | dialog: Chấp nhận âm thanh không đầy đủ?; declined: true |
| 11 | edit the failed chunk; saving it regenerates group 2 | PASS | edit_chunk:completed `293a001f` | recovered: {"failures": 0, "chunks_ok": 4}; screenshot `smoke-08-tts-recovered.png` |
| 12 | YouTube partial batch warning before videos exist | PASS | — | warning: 2 nhóm đã chọn chưa có video.; upload_disabled: true; screenshot `smoke-09-youtube-partial.png` |
| 13 | prepared page preview with uploaded cover and QR | PASS | preview:completed `95a79cdb` | preview: 1920x1080; screenshot `smoke-10-preview.png` |
| 14 | render videos and download one | PASS | video:completed `db93b7db` | download: HTTP 200 video/mp4 130009 B, MP4 brand ftyp; screenshot `smoke-11-video.png` |
| 15 | connect fake YouTube account | PASS | youtube_connect:completed `3e6ade74` | — |
| 16 | upload both videos; first thumbnail fails, retry succeeds | PASS | upload:failed `26f8d1a4`; youtube_retry_thumbnail:completed `72a19d0b` | screenshot `smoke-12-upload-thumbnail-failed.png`, `smoke-13-upload-thumbnail-retried.png` |
| 17 | duplicate upload requires explicit confirmation | XFAIL G4 | — | declined: Tạo video YouTube mới?; dialog: Tạo video YouTube mới?; started_jobs: 0; alert: Tùy chọn không được hỗ trợ: allow_duplicate; screenshot `smoke-14-duplicate-upload.png` |
| 18 | reopen a baseline desktop-shaped schema-v1 session (legacy ui_state) | PASS | — | restored: {"screen": "youtube", "selected": ["3-4"], "description": "Mô tả nhóm desktop", "tags": "tag desktop", "group_title": "Truyện khói \| Bản desktop", "cover": "fixtures/cover.png", "qr": "fixtures/qr.png"}; ui_state_unchanged: true; screenshot `smoke-15-legacy-youtube.png`, `smoke-16-legacy-video.png` |

Post-checks (`evidence/smoke-postchecks.txt`), taken by `bin/smoke_postchecks.py` on the retained run before deletion:

- 0 `*.part`/`*.tmp`/`*.partial`/`*.seed` files; 72 files in the run.
- The config dir was inside the fixture root, and no files were written to the run's home, tmp or XDG dirs.
- **Provenance:** the chunk edit is stored only in `tts_overrides.json`. The source story, `final.txt` and `tts_chunks.json` keep the original text, including the failure marker.
- Both upload records are `completed` with `thumbnail_uploaded: true` after the retry.
- 4 sessions, one of them the seeded desktop-shaped session (schema version 1; `ui` keys `cover_image`, `custom_size`, `group_size`, `group_upload_metadata`, `panels`, `qr_image`, `tab`, `upload_metadata`, `upload_titles`). Reopening it in the browser did not rewrite it.
- 7 fake YouTube calls.
- Teardown: `server_stop=TERM server_rc=143 port_listeners_after=0 leftover_processes=0`.

Observations, not defects:

- With one rejected thumbnail, the upload job ends `failed` ("Một hoặc nhiều nhóm chưa xử lý thành công."), even though both videos were created. **Gửi lại thumbnail** completes the group.
- Saving an edited failed chunk re-synthesizes it and re-merges the group, so the failure panel and its **Chạy lại nhóm này** button disappear. The per-group re-run itself is the same `tts` job that steps 7–9 exercise.

## S6 review

Self-review plus one independent read-only review of the full diff, the ledger and this report. Confirmed findings and fixes (test code only; no product source changed):

| Finding | Fix | Rerun evidence |
| --- | --- | --- |
| G2 xfail could never become an unexpected success: it read a `Settings` object that opening a session replaces | assert on the live `self.service.settings` | `s6-g2-fix-control.log` (FAIL without a fix, PASS with a simulated fix); `s6-xfail-reasons.log` :72 |
| G1 xfail hid a supported assertion (canonical text survives a preprocessing change) behind the gap | the check moved to the passing sibling `test_config_preprocessing_settings_round_trip`, which now asserts `txt_path` exists and the canonical `final.txt`/`tts_chunks.json` bytes are unchanged | `s6-fix-affected.log`; `s6-xfail-reasons.log` :462 |
| Plan §4 legacy session restore was proven only at the API level, not in the browser | smoke step 18 seeds a desktop-shaped schema-v1 session and reopens it in the browser | smoke attempt 9; `smoke-15-legacy-youtube.png`, `smoke-16-legacy-video.png`; post-checks |
| #133 compared one `/api/state` read with itself | the group read is taken before `youtube_connect` and compared after it | `s6-fix-affected.log`, `pytest-full-s6.log` |
| smoke-server egress self-check leaked a socket | `connect_ex` probe runs inside `with socket.socket()` | smoke attempt 9 server log, 0 console errors |

Recorded, not changed (outside the approved scope or low risk):

- Comments that still mention "desktop" in `pipeline/service.py`, `pipeline/media_service.py`, `pipeline/document.py`, `backend/jobs.py` and `config/validation.py`. They are product source, which this plan does not change; left for a follow-up.
- One migrated save-failure test patches `media.artifacts.os.replace`, which is the process-wide `os.replace`; the isolation probe confirms it is restored after the run.
- #134 A4 is weaker than the baseline: it checks `final.txt == final.json['text']` and a non-empty audiobook, not alias bytes against the step-3 canonical sources. Group-mode `final.txt` is the canonical text (`media/groups.py:289`); comparing against the recorded SHA-256 would be stronger.
- `expectedFailure` would also absorb a setup error inside a gap test; the sibling tests that pass share the same helpers, which limits this.
- G1–G4 have no tracking issues yet; they are recorded here and in `coverage.md`.

## Harness deviations and attempts

| Item | Deviation | Reason / effect |
| --- | --- | --- |
| `wo_node` | adds a private overlay for `frontend/node_modules/.vite-temp`, plus a gitignored mount point | Vite 6 writes its bundled config there; the first build failed with ENOENT on the read-only source. Isolation is unchanged: still a private writable path. |
| Browser viewport | `--window-size=1440,1000` instead of BiDi `browsingContext.setViewport` | `setViewport` requires `-remote-allow-system-access` in Firefox 157 |
| Driver text entry | select-all then type over the selection | Backspace-then-type left the old value in a numeric field (attempt 2) |
| Server exit | `server_rc=143` after TERM | Uvicorn re-raises SIGTERM after a graceful shutdown, so the final `FakeProviderCalls` line is not printed. Provider calls are counted from the `FakeYouTube` log lines instead. The run dir was therefore retained and then removed after the post-checks. |
| Python version | 3.14.7 | Only interpreter available for the fresh venv; 3.11 not exercised |
| Smoke attempts 1–7 | failed on driver selectors or expectations, not on product behavior | 1: `setViewport` unsupported. 2: numeric field typed as `302`. 3: session list reached through the header link. 4: picker shows chapter ranges (`1-2`), not group labels. 5: the job-bar text wait used the wrong text. 6: chunk save already regenerates the group. 7: the upload with a rejected thumbnail is reported as `failed`, and the warning selector matched the wrong element. Each attempt's outputs are archived in `evidence/smoke-attempts/smoke-attemptN-*`. |
| Smoke attempt 8 | the S5 run of record (16 PASS + 1 XFAIL) | Superseded after the S6 review added step 18. Its outputs and driver are archived as `evidence/smoke-attempts/smoke-attempt8-*` and `smoke.mjs.attempt8`. Attempt 9 is the run of record. |

## Not verified

- Real Edge-TTS, real Google OAuth/YouTube and any network provider: fixtures and fakes only. Live checks were not authorized.
- Windows, macOS and Python 3.11 itself.
- `python -m backend` serving the built frontend on its default port. Static serving of the real build was verified through `create_app(dist_dir=…)` in the smoke server, and backend module startup through the runtime test on a free port. Operator ports 8000/8765 were never touched.
- Existing CI is Eval CI and does not run these web/core tests. CI status for the PR head is reported in the PR, not here.

## Harness scripts (outside Git)

`*.bak`, `*.pre-vite-temp` and `smoke-attempts/smoke.mjs.attempt8` are the earlier versions that the deviations table refers to. `gen_smoke_table.py` renders `smoke-results.json` as the smoke table above.

| Path | Bytes | SHA-256 |
| --- | --- | --- |
| `bin/bidi.mjs` | 9083 | `ba11faf142e7e2506e0af702e1ac2640345aecb7919954ec4cc451232006c48e` |
| `bin/code_fp.sh` | 481 | `30c548613e756969397d511dbf7e737432e0f7808689aa6ee4599c05626dad42` |
| `bin/g2_fix_control.py` | 1150 | `a3f6fbcd15b2c75379a7e2b8820d60d8d167a864fcc1d2bc8f1270000241b2b9` |
| `bin/gen_smoke_table.py` | 1450 | `47ff043e94aba777234a07536cc13b28debad17722cace5a60d6743acb1da8be` |
| `bin/isolation_probe.py` | 2656 | `7e7eb2ce83af02dfc9b12e68a55d058489b133db1f2b1ee2298780198c5bf304` |
| `bin/probe.py` | 1123 | `be83bbf2973b9ce27cf725fd207bc634d9205bf592c6ae7a10e94f44fcfeaea1` |
| `bin/run-smoke.sh` | 2315 | `b2ed8847ac6f4c728432a10e988f79fa1a3ad9dc19de0b2f8aa3e2dcee93d619` |
| `bin/s5_ledger.py` | 1854 | `9cd29252e9524740cf549cf54cb5a3f9603e065ca180e1f152bc5a772f42cd10` |
| `bin/smoke.mjs` | 29263 | `96bf43c81cfd033ed51d134c831c4399ff9601e0e8707854099a3d023a0294df` |
| `bin/smoke.mjs.bak` | 22453 | `f72a64ec2e6f55b4afa26d8b9fd1da4031b4cc11665a8c6d45d3b76fc75f6200` |
| `bin/smoke_postchecks.py` | 3019 | `3dd22f9a01811a5a21763fcfb2e7723baf166778dc8d671c0ff7d2fa2e4575e3` |
| `bin/wo-env.bash` | 5116 | `249c73cc87468e256946eeb1fcab23dea7509a2706c316ff98ea96ab79528744` |
| `bin/wo-env.bash.pre-vite-temp` | 5019 | `91e35b4bf6078638aa9e9613e9c16bf5170e34f24d34345ab6b11b76e9917254` |
| `bin/xfail_reasons.py` | 1372 | `ad96bc414330d78cb3bed8888aa09dab3acf7f6f93672ba9bc38db9fb0fe8f3f` |

## Raw artifacts

`$WEB_ONLY_DIST` (`frontend-dist/`) holds the build output, as recorded in `evidence/dist-manifest.txt`:

| Path | SHA-256 |
| --- | --- |
| `index.html` | `82fbd65f834f455542ac68b4aaceff1e6e502728cf46a771872847a626974bc2` |
| `assets/index-1vwpJTGz.js` | `04f4ac1bc09981f76ad3cea47c38b4e55cb7ef968393c2a64951a5971901400d` |
| `assets/index-YOtWNzEE.css` | `fec62ffb2ffddb6f094d2b0791bc638f9433b409e9498a84271c23ed5f108783` |

The evidence files, as of the end of S6 (before commit):

<details><summary>191 files</summary>

| Path | Bytes | SHA-256 |
| --- | --- | --- |
| `evidence/controls/blocker_control.py` | 807 | `09ecbc676a745cf871b3374e6a7ed076587912b70b8813a633d7cdf13e4b9b39` |
| `evidence/controls/blocker_import.py` | 823 | `02350bff794795588d316d446ef9c5f71561a0408c9c58a6087c9fa04efd7bec` |
| `evidence/controls/fakeauth_ast.py` | 1053 | `a0f94b85e99fa56d8ea0fdaa6584642642939e0371197e4bcda8ff142db9a38b` |
| `evidence/controls/probe_br121.py` | 597 | `be4d670e637baa6b0692316bcd6972126e8ee2739f6973d478bba471c736d476` |
| `evidence/controls/probe_cancel.py` | 896 | `2ee72fce2759111a53bbd2b1451fccb01c4d1a4c4538d6f70ac8c619e185c51f` |
| `evidence/controls/probe_norm.py` | 472 | `b873ea0bf9de40de17d0c0370d557f3c04acbe3f42f8990f6e3477615323508b` |
| `evidence/controls/probe_prepare.py` | 733 | `c54fa9d2367107507192239983c4201a593e6b6533c7a192702633925b2e584b` |
| `evidence/controls/probe_smoke.py` | 1433 | `0f26c825832351dabf5af9bbeba6b3948502f378af795de6086214a643f444e4` |
| `evidence/controls/probe_video.py` | 682 | `b620f0dd915d23e6bd9c3bc3148b4c8e1001daf57e01ebeb469ad15dd88c3ae3` |
| `evidence/dist-manifest.txt` | 266 | `cfbc4e158c3153bca9c29386c9699a834baec53e6011f1301eb85f77c0e119a9` |
| `evidence/dist-source-fingerprint.txt` | 65 | `87d723d6b0a65a04f18cb67b7f906ee2ecfc46d2b070d87f041ec50caccb27a1` |
| `evidence/frontend-build.log` | 627 | `bbea16d8c0980bf9673f02ec65a6de6fa8f173ea1857c856504c241fe15d1f8f` |
| `evidence/frontend-test.log` | 2310 | `b7581f93fa98cc53ee142b7f29ef00d9f68d2e14e101bbc6292c0b97ee01ef65` |
| `evidence/pip-freeze.txt` | 971 | `fe9edd3024f2bb56c248cd1113c58d15e7eab779b568a9d9ff9b879a7b3d1063` |
| `evidence/pr-body.template.md` | 4111 | `e19da7206cf28302c287f1d4774e40e8c2b1b6b98796981b2c2f9d328283b82d` |
| `evidence/pytest-full-s6.log` | 47569 | `93c0423741f782aded2f50d22b574c7c0306b0ae9ae213684097e0f8d4c8cac1` |
| `evidence/pytest-full-s6.xml` | 52128 | `d2f4a740215ce11d2ed0da3c68834cd2643d64f227c8f35a956cf0d68c9926a0` |
| `evidence/pytest-full.log` | 47569 | `8ec4a949f820a4519b9d20089e1f10de7f1c093338e9bbbb4946394e6024061b` |
| `evidence/pytest-full.xml` | 52128 | `a76c6759a2f41029fa5aa3ff3fd8d5f628cfcf99c35e2c6d839891331287c84b` |
| `evidence/runs.tsv` | 28500 | `d957e3fabb48cf98efed433c5894240d3a9a07fa22b54af7e077c980939e24b0` |
| `evidence/s0-isolation-probe-node.log` | 501 | `a466c2853c8f5ac10a2e7b894c826780c8be4a841cd8b8e2c61c4ea4145577b7` |
| `evidence/s0-isolation-probe-py.log` | 540 | `1e3c486d34d7a6bbba839cde759992f7122be430b5a71e4b7c3959b3d744f8fe` |
| `evidence/s0.md` | 1235 | `bf922d70cca444a5f4229083e435616e9c6278077d5ecace44765e3206de43f4` |
| `evidence/s1-baseline-asserts.json` | 67774 | `bbf9b78017dd8b4b6933bab91d09b37baef5b7fc93b667ce02970a41a20756f1` |
| `evidence/s1-blocker-negative-control.log` | 241 | `486fe7569ce9bf90802a21510884cc74c677ed71a41fe1d5c1732ddb46a84072` |
| `evidence/s1-host-origin.log` | 2499 | `571acc35d859dcb6b59ae9ea6f0a766fd35362d91dac54a946c2ffb186fddd5e` |
| `evidence/s1-preflight-headless-web.log` | 6547 | `d5b12cd1db3932843ac3568714b466e5ef5c3434f15f4946ab6ae788d48b5414` |
| `evidence/s1-preflight-qtfree.log` | 860 | `8adb44467ae1cb866dc37bfcf0355b73c2516665c7b63b6e8db6b0f19aebec65` |
| `evidence/s1-preflight-qtfree.xml` | 29976 | `f18901a3455baaa3f79afb2d7cb696cbd1bb2a61eddce0432567f6667b11de7c` |
| `evidence/s1-red-boundary.log` | 5969 | `bbfbbb873ff3b52430ff57ebd1994302a0988a67e0fe14a9dda640e73f749bdb` |
| `evidence/s1-test_cli_fixture_pipeline_without_qt.log` | 228 | `3b38b31273b300cfb845468ca6b17e217ee046360dfafb9f345acd053d6c37d2` |
| `evidence/s1-test_real_backend_health_without_qt.log` | 226 | `657b579dc27150ee20d914d472509577ec92451fa316ce17f2aaf025f679eda3` |
| `evidence/s1-test_supported_modules_import_without_qt.log` | 236 | `0695a2dfa81648bf6d02f948a37756dfdbaf780ac6ba8358c6e9d0d1b2874ad0` |
| `evidence/s2-fakeauth-ast.json` | 148 | `0fde56bed8637a8e0cf43ba20a3e08d3caa8372379add024ea55eba77e5d870f` |
| `evidence/s2-focused.log` | 12228 | `671beafa45d09b58baa9158fd96ae51e41c031de4945bcf75f13402275e95adb` |
| `evidence/s2-focused.xml` | 13688 | `4472860ec46a5aa3eeb2e3eacb8124373859e8293727f178e6034e80128a9485` |
| `evidence/s2-frontend-test.log` | 2311 | `d3e356ed89774cd00dc9ca9da124bf284f0c241a7f31b913a3fc4125d3c7acbc` |
| `evidence/s2-g1-red.log` | 2099 | `915139f48decc1840cc204e07ab3401906d7865493c877bce385496fbd9fd95f` |
| `evidence/s2-g2-red.log` | 2133 | `9ee32c5da962798b7ccec327e3e66733d6e8c16193082292ddb01e4bac6233d2` |
| `evidence/s2-headless-web.log` | 15837 | `b679db99bdf6e93de19ebac00b50501d38f9acd4bfb8e2bd00d9ea57f69fca5d` |
| `evidence/s2-retained-ast.json` | 13820 | `0501b61b1c435943a212420cf7c1b2e3fd7d69c81aaacc4281b4adff6991c5d1` |
| `evidence/s2-support-blocker-import.log` | 87 | `f00f7b283d04cb7f47fd53ed01c5ffbf9fa8cfac5362ec28d1d91de107d753fa` |
| `evidence/s2-title-tags.log` | 2997 | `d73bd474c9d98d5fd6fa8ebfd8bb55115220419dacfb63842a8f403e4a1630fc` |
| `evidence/s3-br-group.log` | 9358 | `a5dbb3114180da6bf05e344f65c18cef62998fe79683c1605768f1687356385a` |
| `evidence/s3-br-media.log` | 1510 | `0e931333db5fa3be8b6bae1719a92f36d6cd5f2be06ec85e70c6ae96539c2726` |
| `evidence/s3-br-settings.log` | 1758 | `ca555012e1bf1a88c2bcc805bde92a499dc15013ea77edba4a6632620a509c48` |
| `evidence/s3-br-youtube.log` | 4851 | `787c4714c75396cafbb377903bf63481abfaedf48d6cad3b7ccef16e1c343f92` |
| `evidence/s3-dispositions.log` | 11667 | `122956ad43e58ac95284f0db97f9640b1aa99e2ffe1065744954ee4639fd7f07` |
| `evidence/s3-dispositions.xml` | 13334 | `efb263bcea7789d435275473522eb42e626b3e5269b6224474b060445bd59323` |
| `evidence/s3-retained-ast.json` | 13859 | `b49be670a2083b7b5e4250eca7eb46dda104a3473108853f57cc3b50ee8ea7f7` |
| `evidence/s3-xfail-reasons.log` | 1511 | `fbe9234250a2b418ba56129e61fabbf0971eeb8dd011f86e5b656dbe91140b95` |
| `evidence/s3.log` | 21052 | `3679eca68a33fc6b70d37bc3f5c036257066b605e637274f479c0d714d376742` |
| `evidence/s3.xml` | 23455 | `f7b12d68e27b3d5c3b3a3a509bc209bd322e68dfb6b9ba39e361c6914d881a12` |
| `evidence/s4-collect.log` | 37946 | `537c1d6c9e317181d84c0754afb812ee474b70209e585ad4e7a73119e9c5c4a7` |
| `evidence/s4-runtime-oracles.log` | 3023 | `bf051d7b1025349472bd7ebe20a9398ef820a301adda7e2d289c039429d295bd` |
| `evidence/s5-code-scope-fingerprint.txt` | 65 | `d9133b16734b307c531452b2a33ac1e9c9f2fc2485f61edd31a89cae7bab5dff` |
| `evidence/s5-final-source-fingerprint.txt` | 65 | `87d723d6b0a65a04f18cb67b7f906ee2ecfc46d2b070d87f041ec50caccb27a1` |
| `evidence/s5-isolation-forward.log` | 1084 | `d5bf2014b84ff0b708c37a8726e228e646f74b9c708a0e618196eca01c5d5aab` |
| `evidence/s5-isolation-reverse.log` | 1050 | `be7da8cec8d538de68e788408e867362417f8d552ff9bb522e6876c745d7b18c` |
| `evidence/s6-code-scope-fingerprint.txt` | 65 | `d13f4d7890fc2920a3149edb7e5e123df92fadd919eb23927681e14128389367` |
| `evidence/s6-dist-manifest.txt` | 266 | `cfbc4e158c3153bca9c29386c9699a834baec53e6011f1301eb85f77c0e119a9` |
| `evidence/s6-fix-affected.log` | 4962 | `2c40435da74c9267d1aebf7a3cfe0644b5330307a5a6b0b28121d49697fbe079` |
| `evidence/s6-frontend-build.log` | 627 | `67d7f1e1bdab8aba0ca0b7b820adfe571b66f7089277a5606edf83f61f87c5b9` |
| `evidence/s6-frontend-test.log` | 2309 | `f2e36c3e758537f0808ff777eb55530cf35eee5be51f6f3238a37e93236d5d51` |
| `evidence/s6-g2-fix-control.log` | 377 | `830941898dc2b6d8c711290b8db39482895bae694d6972ea9a7f27105fae8abd` |
| `evidence/s6-isolation-forward.log` | 1084 | `5fedd93d6a10d663f8c6da2731717316cbd663c402960dd339549328cd360f9c` |
| `evidence/s6-isolation-reverse.log` | 1050 | `72edfbe75b28847e39cf1e9a8c2b8c429bc231fea8e2417a66e80b5f104d62e5` |
| `evidence/s6-run-cleanup.txt` | 118 | `6af709fcd82f3efde98f2205da0a784de38a87657193d29641e920e41884a1de` |
| `evidence/s6-source-fingerprint-after-build.txt` | 65 | `b76b6b8d8b745ba6a76a84d924fdec2a367ff8a71c7272516554f1300951f859` |
| `evidence/s6-source-fingerprint-after-smoke.txt` | 65 | `b76b6b8d8b745ba6a76a84d924fdec2a367ff8a71c7272516554f1300951f859` |
| `evidence/s6-source-fingerprint-before.txt` | 65 | `b76b6b8d8b745ba6a76a84d924fdec2a367ff8a71c7272516554f1300951f859` |
| `evidence/s6-xfail-reasons.log` | 1511 | `77bb88d36cf23a6d0f0e324d4230fe2575630825f7905d2c99824752f85273ce` |
| `evidence/setup-npm.log` | 77 | `318c9e4fce07354f0c4d482e08d8d3c3ae6d9a9221771383a41f7af1d3906971` |
| `evidence/setup-pip.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `evidence/smoke-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-02-imported.png` | 91900 | `ead2ff053ee7ea262213f91a54127de41519d2604a80bbb3048322ad81d56b05` |
| `evidence/smoke-03-grouped.png` | 285290 | `1a4d9f3a246e409507c23c31dac2109b275735397c1c940ebc751cd343ffe171` |
| `evidence/smoke-04-reopened.png` | 130832 | `fdeb4dfb0bae692335190eb2dab2e5551ae031025b8dc00ea06cca4f0fcfca21` |
| `evidence/smoke-05-tts-group1.png` | 147783 | `64c6edefea0ab9cb64944c7591f2d30c457bffb5dc8bc0d279ab1c5a40563115` |
| `evidence/smoke-06-tts-cancelled.png` | 144327 | `2900a3dde0601c42fd17f1c1027a4c39c966b23c47368747dae0a9c6858d2398` |
| `evidence/smoke-07-tts-failed-chunk.png` | 214049 | `b478a35ff87e4a5429f6ef5e090d54e6a59dadb620f3e5cac41ae27cb2765005` |
| `evidence/smoke-08-tts-recovered.png` | 198879 | `7a2dc3f2a9af43307aad81d4ac053186307a74ddae3145436d72b7221671d7e7` |
| `evidence/smoke-09-youtube-partial.png` | 142300 | `7cfbe241774e075da88fb5a0d5fcc4f0534eeb05a0c25c0526d109f3f7493e40` |
| `evidence/smoke-10-preview.png` | 195804 | `a3e22cea45165c451e340b09f26438197bfe33ee542640ca44ac6addfe4e0c2e` |
| `evidence/smoke-11-video.png` | 238074 | `3855e849998b7b450b3413df4cecb0ab444f85373fc9d6a7638134f8dc12de18` |
| `evidence/smoke-12-upload-thumbnail-failed.png` | 233606 | `3786cc2d179d6801a827e66fb8527c6707d556d06dc0e0e77bdd1da9736c9610` |
| `evidence/smoke-13-upload-thumbnail-retried.png` | 235946 | `7608564d3aa67fa34e61da472f80105c8682cd8ba68658947b054aa4f2363ad1` |
| `evidence/smoke-14-duplicate-upload.png` | 245846 | `c997602ee71697cf193a1d23ca3295c7be828e2099fb7a44ba8662f17101d6b6` |
| `evidence/smoke-15-legacy-youtube.png` | 242580 | `16365fbe708e31050809fbc7ad655c9637533591918cbd50b0185aea1c16574e` |
| `evidence/smoke-16-legacy-video.png` | 207787 | `c9dbb97587c4b9707f5c5eeccb8965654d91c52ed1fea90b78f195c01192e9ce` |
| `evidence/smoke-attempts/smoke-attempt1-driver.log` | 162 | `6b656a608fc7bf5083d521f2125ee6114d1bee326a5327d4849a70389615ae13` |
| `evidence/smoke-attempts/smoke-attempt1-firefox.log` | 261 | `0ed133d237c856b59e18154e0218bb93011464b7f5c1ac3a6a3b4f2568a5b378` |
| `evidence/smoke-attempts/smoke-attempt1-results.json` | 496 | `b4c388e57182f39552ca71d471370ac6f37aa1cab384773108c5e182487d019c` |
| `evidence/smoke-attempts/smoke-attempt2-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt2-02-imported.png` | 92271 | `2550ddb155208e93f78fd74baea29652934f70363b6c8746324e06d1fe8f663e` |
| `evidence/smoke-attempts/smoke-attempt2-03-FAIL-group-by-2-chapters-with-title.png` | 174126 | `5b1126c31920db1ed0909847243c8d3757d90d0f954a2fef2c4388b3b9eeaedf` |
| `evidence/smoke-attempts/smoke-attempt2-driver.log` | 1007 | `569e38de48a2371c8ea4bf39b077d28e49ad43d128f86ca97c4a162951e2a0c5` |
| `evidence/smoke-attempts/smoke-attempt2-firefox.log` | 261 | `a1b79e2e195d801105bc733eacd3d9402a924b349732cbbbadba68a980aa8e66` |
| `evidence/smoke-attempts/smoke-attempt2-results.json` | 2099 | `db6f22df2257ab76f8df04c86890e280dac9680c2486567eed87c650d13c3da4` |
| `evidence/smoke-attempts/smoke-attempt2-server.log` | 2968 | `a2fcaab202f7668b976ed6533900528a53eb90961af57493609f2c1baaa5903b` |
| `evidence/smoke-attempts/smoke-attempt3-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt3-02-imported.png` | 92050 | `3054369901c2aeae34ea3623a89cbae93ab1e170d53f6e6d9502510a7354ba7c` |
| `evidence/smoke-attempts/smoke-attempt3-03-grouped.png` | 284807 | `d32567ef229ec3f35af7d7c927e881e967b12ffa0f556efa5444aae53adf1a39` |
| `evidence/smoke-attempts/smoke-attempt3-04-FAIL-save-session-start-new-reopen-saved.png` | 112590 | `c571c74d1254f483266d661f47f493b0287467525de8a50158212af6a6cf4620` |
| `evidence/smoke-attempts/smoke-attempt3-driver.log` | 1228 | `0ed3ac4e06c2deabc049ee58602fc57502c65000632835b32874596c46bf3971` |
| `evidence/smoke-attempts/smoke-attempt3-firefox.log` | 827 | `1b91f587a06718104c013118eb0b4f3dbcff7d21d360bdf70a6c21c29742925b` |
| `evidence/smoke-attempts/smoke-attempt3-results.json` | 2492 | `176f9dbf3dd634a7ae80de2bfa2b8c3b895483d25a56206ed2edef0480a3d881` |
| `evidence/smoke-attempts/smoke-attempt3-server.log` | 3840 | `3f545e480e23f6a84bc63f0c6bb196ff03f5b821b0f27910953267c4d02f9758` |
| `evidence/smoke-attempts/smoke-attempt3-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |
| `evidence/smoke-attempts/smoke-attempt4-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt4-02-imported.png` | 92270 | `d3f9ce2aea9b8c89cce90c9ee1cdbf7385f3f8e4f039cbe3a70c0730fed77207` |
| `evidence/smoke-attempts/smoke-attempt4-03-grouped.png` | 285882 | `51a3ac1ccb4e7dc2f0735711fd5fe07879a001fe441c9f6d1cfe0e15a0c646d4` |
| `evidence/smoke-attempts/smoke-attempt4-04-reopened.png` | 131153 | `3e0e13e385917d54e702fcc80d86ce09bbddee9e067956a7aea65eb3d5ff8dbd` |
| `evidence/smoke-attempts/smoke-attempt4-05-FAIL-TTS-on-selected-group-1-with-uploaded-thumbnail.png` | 144005 | `ab5000b3f38322615b8c83a9c19b006d1559b4e56e6c172162602b44f6562ff4` |
| `evidence/smoke-attempts/smoke-attempt4-driver.log` | 1432 | `042da1dae64673993b385f61fbed507f8f666c9a90421b75add22fc715fd3cdc` |
| `evidence/smoke-attempts/smoke-attempt4-firefox.log` | 261 | `04b5a95e82aaf79c5daf416e1ff0eae4e90e0024f645b0d2b6c5798939f1a1e6` |
| `evidence/smoke-attempts/smoke-attempt4-results.json` | 2789 | `361894a21db3e984d299ee637fd6c58e80f263f0b39ef59ada2451bc04442636` |
| `evidence/smoke-attempts/smoke-attempt4-server.log` | 4387 | `f30fd4c7d94ce1fd880341e362f8327172e0522147beab68bde66770885c1674` |
| `evidence/smoke-attempts/smoke-attempt4-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |
| `evidence/smoke-attempts/smoke-attempt5-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt5-02-imported.png` | 92166 | `dd4bcfcc2c87cd4efa104a3cd3bbef64f03288a54b768ac6e51958b213ac5bd4` |
| `evidence/smoke-attempts/smoke-attempt5-03-grouped.png` | 285804 | `c0613e5f38767e170f44c6f597427a840ed91eed751c2b51ab6afb2f79d4cf69` |
| `evidence/smoke-attempts/smoke-attempt5-04-reopened.png` | 131249 | `ebe4cfc8db5b3f06cb196cb5297ef950acb4aa401dd5b57499620bc94889968a` |
| `evidence/smoke-attempts/smoke-attempt5-05-tts-group1.png` | 148188 | `2efb9368286caa49210ce4df2224c51620828251b4bb105b41b20eb19b3207ea` |
| `evidence/smoke-attempts/smoke-attempt5-06-FAIL-TTS-on-group-2-is-stopped-from-the-job-bar-cancel-.png` | 150784 | `334dcffa5897beca3bb38f718bfcfd795efbf53c6ff0d4cfb8dc7ceebae8bbb9` |
| `evidence/smoke-attempts/smoke-attempt5-driver.log` | 1689 | `eb9130ac8ec285514162a7da6cba9a72444d1f696bb2d4d252e4d8ef784936ad` |
| `evidence/smoke-attempts/smoke-attempt5-firefox.log` | 261 | `d363fa07d31c0b5ffaa979201404abf5a5bcae9ea0b85d4cc3b4ff8641d365f2` |
| `evidence/smoke-attempts/smoke-attempt5-results.json` | 3388 | `0854f32182c716c2a31989eedb2d631bb4d60c56918d536f33b1cbebffdde677` |
| `evidence/smoke-attempts/smoke-attempt5-server.log` | 5390 | `1846d7e10474a8e3fc8f58d65482cd66604ab4cff739b03e4865dba38ff5bc21` |
| `evidence/smoke-attempts/smoke-attempt5-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |
| `evidence/smoke-attempts/smoke-attempt6-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt6-02-imported.png` | 92393 | `3632552e4f64402d749407e0a4b92a3aa7a98271499ff4228061f31579721e8f` |
| `evidence/smoke-attempts/smoke-attempt6-03-grouped.png` | 284634 | `5c660330c479e79c838d6a2039e851830fe8147bca3c50c2889ae1e65449a05c` |
| `evidence/smoke-attempts/smoke-attempt6-04-reopened.png` | 131575 | `b76eb9f22055d7660727eba486a96af54c8e50ee1d64860bdf4474c1e3c1dbc8` |
| `evidence/smoke-attempts/smoke-attempt6-05-tts-group1.png` | 148168 | `d06ca46cda51eac2f25b33e8ac2ff30bc21a0a58fea2f65dc306138486a23ea6` |
| `evidence/smoke-attempts/smoke-attempt6-06-tts-cancelled.png` | 144728 | `4187b9420f0ff745b8886478e00f8851a0605851e803ac81a888122be9fa2208` |
| `evidence/smoke-attempts/smoke-attempt6-07-tts-failed-chunk.png` | 214656 | `a2d9acf447ea041da58dbe9b4eba201f8f2a6d8fda939a6229699c5d926c9074` |
| `evidence/smoke-attempts/smoke-attempt6-08-FAIL-edit-the-failed-chunk-and-re-run-group-2.png` | 199572 | `31075b9d96398bff73b4190b1db67266c47ae40576bb3b6a41e018fa10895299` |
| `evidence/smoke-attempts/smoke-attempt6-driver.log` | 2699 | `4ad83c7110c557dd63bffe86d4fa7e3b4dd4ce6c2a02c9af815150a1ca47554e` |
| `evidence/smoke-attempts/smoke-attempt6-firefox.log` | 261 | `7caa9de8a9e998c2c0d93687945a99fb0e6b6e5c1b89e993655b79d59870d63a` |
| `evidence/smoke-attempts/smoke-attempt6-results.json` | 4813 | `3d9a93d34250f7680a8a49389bf0649c10c2dafe3b4f9cddce4a2b804e2bcee9` |
| `evidence/smoke-attempts/smoke-attempt6-server.log` | 10610 | `fa700afe06c88f7ad553dadb1612c9d35cb3cf927d0e83c8851ad416ca31dd87` |
| `evidence/smoke-attempts/smoke-attempt6-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |
| `evidence/smoke-attempts/smoke-attempt7-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt7-02-imported.png` | 92320 | `2801b99fc77210e6aef8b2c39bbe22c1721e3a4a62b3ba004d21f1af1aecc602` |
| `evidence/smoke-attempts/smoke-attempt7-03-grouped.png` | 285668 | `f632899066e11ad02e1366bf4cca2e3fd43cbafbeff33e6e2369ab10da8a6f1f` |
| `evidence/smoke-attempts/smoke-attempt7-04-reopened.png` | 131638 | `f71476add0d66b73321b458107fd4a95db60a03449205d04bb1f73e3beddb688` |
| `evidence/smoke-attempts/smoke-attempt7-05-tts-group1.png` | 148180 | `fc22bf65b7617aea1349982b1689e0926c89482201dd9ca4b79d7b362415f38e` |
| `evidence/smoke-attempts/smoke-attempt7-06-tts-cancelled.png` | 144564 | `77953ef233ed1a4a6368b4bee650aaffdef3e1a8adb4e69ef17af1fca7090d44` |
| `evidence/smoke-attempts/smoke-attempt7-07-tts-failed-chunk.png` | 214756 | `b21152c086f2ce5c000317ef9f6ed521147166b86061ebbe2758f2cce35ff75d` |
| `evidence/smoke-attempts/smoke-attempt7-08-tts-recovered.png` | 199818 | `b26837f0a529b22b0b2ca3d40409e8a4288e5273574ce6d1b77500e3a1b27406` |
| `evidence/smoke-attempts/smoke-attempt7-09-youtube-partial.png` | 142911 | `add44972ba1d4061c89f6cd4ff47458d7431a1cfd674ef36923c7ec61a848ef7` |
| `evidence/smoke-attempts/smoke-attempt7-10-preview.png` | 196437 | `bd9a0d537f7d772f321cb5f9d5db7d6bab0f3a3b2e969827d0a244843c9e4752` |
| `evidence/smoke-attempts/smoke-attempt7-11-video.png` | 238793 | `d05abfd7bb22b40c1b7ad371929ee74427347b76293617bcdea01b7cbef0ebf1` |
| `evidence/smoke-attempts/smoke-attempt7-12-FAIL-upload-both-videos-first-thumbnail-fails-retry-succeeds.png` | 200184 | `11afbcd5509e43193c3a86494041e7d2392d7f60596b678825f3d83c239e177e` |
| `evidence/smoke-attempts/smoke-attempt7-driver.log` | 3664 | `4e5bb5a4e898a1a70e60b627fe137832160b2abe18d26cadc883cc6a63856d51` |
| `evidence/smoke-attempts/smoke-attempt7-firefox.log` | 261 | `8ce83cde31829f9a96b38ad3465572bf3314b830113d3482967e4335ab752bf1` |
| `evidence/smoke-attempts/smoke-attempt7-results.json` | 6581 | `caa2b7df9cc1057e4a57cd8c352501354c37edc181b6cfd65a286886bd505394` |
| `evidence/smoke-attempts/smoke-attempt7-server.log` | 14846 | `fdea95641116700804a386921bcefa729dbb19fb2953ee09290d6fdfb1c9bd32` |
| `evidence/smoke-attempts/smoke-attempt7-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |
| `evidence/smoke-attempts/smoke-attempt8-01-loaded.png` | 47826 | `afe3795cdf5e5139667755bb7425a3727e4b4ca6016ac10276e7b4e4e80927fc` |
| `evidence/smoke-attempts/smoke-attempt8-02-imported.png` | 92151 | `a4d3d1e91e6d36b1e9434ce4a7dba437b928b1a9b106c84d2cdf7e9ab61eba13` |
| `evidence/smoke-attempts/smoke-attempt8-03-grouped.png` | 285322 | `379cc75dd1acbc681ac26e96e18d9f5b4a01852df3b5cb59557796a6420e38e7` |
| `evidence/smoke-attempts/smoke-attempt8-04-reopened.png` | 130945 | `3dcfedb71deacf76998fdbdffa9fcce82cd0b4901ffbfa3f84f47c64216d1d56` |
| `evidence/smoke-attempts/smoke-attempt8-05-tts-group1.png` | 148016 | `043fa40c64eeaa4eed124a138bc66688bf8e7bd5c9e0a40d07a45d5dc0de9004` |
| `evidence/smoke-attempts/smoke-attempt8-06-tts-cancelled.png` | 144564 | `9c88ea36c56b11564db95f6406493fb29a9895be439bfd33ec02162b12ebb386` |
| `evidence/smoke-attempts/smoke-attempt8-07-tts-failed-chunk.png` | 215355 | `1d743beb243baf09d046b90e64146798356b56aaa98269bf8370f3be1046c2ab` |
| `evidence/smoke-attempts/smoke-attempt8-08-tts-recovered.png` | 200223 | `563d6df8c6d9294a02a0550e6a789dbdc89b4d27214a0a0e8eb551025db61359` |
| `evidence/smoke-attempts/smoke-attempt8-09-youtube-partial.png` | 142674 | `1ddf47bffa8de25ed583782124fdd14843c08958ab01b510189971e86de5462e` |
| `evidence/smoke-attempts/smoke-attempt8-10-preview.png` | 195885 | `371000f5c7f7de85eb945f418a181a735c02cf9adaff5a67fdf6393175dfb0fb` |
| `evidence/smoke-attempts/smoke-attempt8-11-video.png` | 238444 | `8df56a4d91bb540a1c427c5ed22249c83971e8506acdfc7ad8dc9d32ef35059b` |
| `evidence/smoke-attempts/smoke-attempt8-12-upload-thumbnail-failed.png` | 234381 | `410e215b632cf68e7212988bc6ea3e1d8ff600f4cf04a34264f9128abe33d07a` |
| `evidence/smoke-attempts/smoke-attempt8-13-upload-thumbnail-retried.png` | 236603 | `445607650c8912bc9857c9406d5a21bf964eff7589c77b2559e1a635b7587a00` |
| `evidence/smoke-attempts/smoke-attempt8-14-duplicate-upload.png` | 246461 | `fc395938d38faba87616f7235071e7069a18800dc45ca381a5297bee1b1d06c8` |
| `evidence/smoke-attempts/smoke-attempt8-browser-run.txt` | 47 | `f7a0c0fd241210d3e501e8b757792ccb1c3f25dceb5a4b98ffa1aea354f8368d` |
| `evidence/smoke-attempts/smoke-attempt8-driver.log` | 4162 | `fcec3c9389ceab6005d60d94a043ee04cfd80d6c85e95c25b1bdd3dff1e026e1` |
| `evidence/smoke-attempts/smoke-attempt8-firefox.log` | 261 | `d8962db6f09aa9a5d3d0a33648ebdf142f3f9fedd74fa0da79283f4b7bac2527` |
| `evidence/smoke-attempts/smoke-attempt8-port.txt` | 6 | `2195916cbc2c0d9cde5ca592c3fde2cc0b8437acf6eff4c147cb03946067e5f7` |
| `evidence/smoke-attempts/smoke-attempt8-postchecks.txt` | 907 | `c8dc771ff9734e84b007ce9f54488eb9804fe5fcda8fade42451f379e6521234` |
| `evidence/smoke-attempts/smoke-attempt8-results.json` | 7420 | `691e171cf13bf33fc2f9c580ee63e97e70b0fd40f9f13890a534cf89cfd289b1` |
| `evidence/smoke-attempts/smoke-attempt8-server.log` | 15475 | `9c90f43dc8e1fc24539751d850561a31d66b30244ec7c8e5bb6124b2a01a240d` |
| `evidence/smoke-attempts/smoke-attempt8-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |
| `evidence/smoke-attempts/smoke.mjs.attempt8` | 24566 | `04a8b935a8d91cd89d9b9947319956a3e0e35187b21163c66d876e29509491ea` |
| `evidence/smoke-browser-run.txt` | 47 | `98716f869d427b2f690ae473723132cc50564473fc645f0c2ae8e14df5c53be2` |
| `evidence/smoke-driver.log` | 4548 | `a4467240f6cf589ed789b9b1d59bc69de88bf91f7200e658b4126b1a6ce00e09` |
| `evidence/smoke-firefox.log` | 261 | `4b983d33f928123eebc0737e674e5cea62c19d17938e94b12844e19bfca82ca5` |
| `evidence/smoke-port.txt` | 6 | `97fdd2d105007e117a5192b8261199c7861706c68654966f071af8f01f38aab5` |
| `evidence/smoke-postchecks.txt` | 1133 | `423a85d21f5c5b5a2e7eef679c0f7b02838efb06fe04f5631868c95473203daa` |
| `evidence/smoke-results.json` | 7998 | `17b05b57a76ec3b246ae1c0d7d2a9a48c9b83776e37dc9628a800c46022082ab` |
| `evidence/smoke-server.log` | 16551 | `a778cef808746426eded84f85cb81b5ed09cce0d8a16d0b5e27df4e4d1b0bfe8` |
| `evidence/smoke-teardown.txt` | 75 | `19265531014ca0e25ad7039f2b2b3490860eb41937f723ecc91908197f6255c3` |

</details>

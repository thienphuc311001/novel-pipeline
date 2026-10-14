# Web-only PyQt6 Removal Implementation Plan

> **For agentic workers:** After explicit human Plan approval, execute natively and sequentially with the executing agent's own checklist/task tools; no external Skill or vendor-specific tool is required. Apply `chapter-data-integrity` to data/media migrations and `REVIEW.md` to the complete diff. Implementation is authorized by the owner's Plan approval, within this Plan's scope and preconditions.

**Status:** Approved — explicit owner message `approved`, 2026-10-13; implementation in progress (PR #3 merged by the owner as `8b4bb314a5e6ae073050535a99f2000930c286cb`)
**Prepared:** 2026-10-13
**Goal:** Remove the PyQt6 desktop consumer and dependency while preserving the supported web application, internal CLI, data contracts and valuable regression coverage.
**Architecture:** Keep React → loopback FastAPI → JobManager → PipelineService → shared core/media, and CLI → PipelineService. Remove Qt consumers only. Test fixtures replace external provider boundaries; production business methods, workers, persistence and media validation remain real.
**Tech Stack:** Existing Python 3.11+, FastAPI/Uvicorn, React/Vite/TypeScript, Node 22.12+, unittest/pytest, FFmpeg/FFprobe. No new production framework.
**Spec:** `intent/web-only-remove-pyqt6/spec.md` — Approved by explicit owner message `approved spec`.
**Intent SHA-256:** `1288612572425f80a7374dcd6c006dc6b81376e302149aa485ad3eb1ab8cf91b`
**Spec SHA-256:** `000990a0a42fee4abad5303673b71e98d090259954a079fa5c4ae702756089df`
**Evidence:** Static inspection, AST inventory and Git/tool metadata only. No application tests, builds, dependency installation or provider calls were run to prepare this Plan. All runtime gates below are Not executed.

## Global Constraints

- N1 — Preserve all real files/configuration/accounts. No secrets or real novel/session data read or emitted. Temporary config must be selected before importing test packages.
- N2 — Automated regression uses fixed/generated fixtures and fake provider transports. Allow explicitly needed local HTTP/OAuth loopback while denying external calls; prove controls before claiming isolation. No live provider calls.
- N3 — Keep Python 3.11+ and Node 22.12+ requirements, existing web/core contracts and formats. Preserve safe Qt-free helpers based on callers/compatibility, not naming. No new runtime framework.
- N4 — Record interpreter, dependency origins, clean Qt-free environment, source identity, commands/exit codes, collection, failures/skips and validation limits. Missing dependencies/timeouts are ERROR or unverified evidence, not PASS.
- N5 — Preserve dirty files and both Lesson 7 worktrees. Use a separately designated branch/workspace. Do not copy/stage unrelated untracked files. Apply REVIEW and data-integrity procedures.
- N6 — No automatic merge/deploy, broad uninstall, global configuration edits, paid Eval, secret provisioning or new CI workflow.
- Approved O1: preview uses prepared narration/audio; desktop sample/fallback, widgets, shortcuts and native pickers retire. No new web features.
- Approved O2: removal requires offline regression, real local FFmpeg, actual browser smoke, preserved business functions and valuable coverage from all 14 files. Real TTS/YouTube remain unverified.
- Approved O3: keep CLI, shared core, settings, schema-v1 sessions and artifacts. Initial runtime acceptance is Linux; do not claim Windows/macOS PASS or silently remove their support.
- Never modify converter/chunking/TTS/upload/render algorithms, session formats, provenance validators or expected values to make migrations pass. A newly discovered required workflow gap is a scope decision.

## Review Focus

1. An edited or failed TTS chunk must not rewrite source/canonical text or bless stale provenance; S2/S3 exercise overrides, failed parts, resume and cancellation.
2. Reopening an older schema-v1 session must preserve its supported draft/group state without restoring stale global account/story-tag configuration; S2 tests older/current sessions and failed atomic saves.
3. A selected multi-group operation must retain order, frozen metadata, partial/cancel outcomes and duplicate-upload confirmation; S3 checks real worker results and S5 checks web controls.
4. Missing/tampered narration, pictures or audio must fail preview/video safely while retaining an existing valid publication; S2/S5 test these inputs and actual FFmpeg.
5. Reading logs or attempting an operation while busy must preserve the current job/document and show actual failure/recovery information; S3/S5 test real JobManager/HTTP state.
6. A request with a foreign Host or Origin must be rejected by the real backend process, while same-authority loopback and the two dev origins keep working; S1/S4/S5 run the real-backend Host/Origin oracle (§3).

## Owner Plan-review decisions (2026-10-13)

Recorded from the owner's explicit chat instructions during Plan review. They do not approve this Plan and do not rewrite the approved Spec text.

| ID | Owner decision | Plan effect |
| --- | --- | --- |
| P1 | `MANIFEST.md` and `STATUS.md` are pre-SDLC working documents; remove them if the project no longer needs them. | Static reference search found consumers only in historical `intent/verify-smoke-check/{intent,spec}.md`, which stay unchanged. S4 re-runs the reference check and deletes both; if an active consumer (README/INSTALL/USAGE/CLAUDE/AGENTS, scripts, Skills, CI, code) appears, stop that deletion and report. Owner-directed addition to the Spec R12/D6 document list. |
| P2 | Merge PR #3 separately first, sync this work with the new main, and put only PyQt6-removal changes in the new PR. | S0 precondition: a human reviews/merges PR #3; the agent never merges it. Lesson 9 changes (CLAUDE stage continuation, Eval workflow) arrive only via main; nothing is cherry-picked or copied. |
| P3 | Plan corrections: extract FakeAuth in S2 before running tests; define `wo_node` with a writable build directory, source protection and network isolation; per-invocation config, explicit environment and controlled cleanup; real-backend Host/Origin test with accepted and rejected cases; attach or link test reports/artifacts to the PR with available tools, otherwise provide paths and substitute evidence. | §2, §3, §5 and §6. |

## 1. Workspace and baseline

| Item | Static observation / execution policy |
| --- | --- |
| Inspected checkout | Repository root resolved with `git rev-parse --show-toplevel`; branch `codex/lesson9-eval-ci`, HEAD `a80efa8d92bd4f24cf4f66eefc62b20795f53aa8`. Do not execute removal in this checkout. |
| Dirty files | Untracked `REVIEW.md`, `.claude/agents/plan-auditor.md` and the Qt-removal documents. Preserve them. Only the three approved Qt documents transfer to the implementation branch. |
| Existing worktrees | `novel-pipeline-l7-smoke` at `e122862f68c9bc03b8d61adbe49659b07ecb6510`; `novel-pipeline-l7-chapters` at `ef085c089709bc0dac4fd13366743ce07720bf3c`. Neither is an execution target. |
| PR #3 precondition (P2) | PR #3 (`codex/lesson9-eval-ci` → `main`) observed OPEN, Draft, MERGEABLE on 2026-10-13. A human completes its review and merge separately. Implementation starts only after `gh pr view 3` reports MERGED and its merge commit is an ancestor of fetched `origin/main`. Open, closed-unmerged or reverted PR #3 is a blocker to report, not something to work around. |
| Proposed PR base | `main` after the PR #3 merge; record that exact SHA at S0. The previously observed main `ea9d65589299e31fced2876600689a13776a060f` is historical only. |
| Branch separation | GitHub comparison showed only CLAUDE.md and .github/workflows/agent-eval.yml differences between observed main and the inspected branch; application/requirements/tests were equivalent. After PR #3 merges, those Lesson 9 changes come from main. Do not cherry-pick, copy or re-apply any Lesson 9 commit or hunk. |
| Implementation workspace | A new managed worktree from the revalidated post-PR #3 main commit; branch `codex/web-only-remove-pyqt6`. Use its returned root for every operation. Never hardcode the main checkout as a test/edit destination. |
| Inputs | Copy exact approved Intent/Spec and owner-approved Plan to the new workspace; capture all three hashes in external evidence. CLAUDE.md is taken from main as-is; this task edits only its Qt/desktop guidance. Read REVIEW privately without staging the unrelated untracked file. |
| Dependency environment | Fresh disposable venv with `include-system-site-packages = false`; never reuse/uninstall Qt in the shared venv. Install only existing web requirements and test dependencies into it. Agent shell state does not persist between tool calls, so variables and helper functions live in a generated `wo-env.bash` outside Git (§6) and every command sources it. |
| Observed tool versions | /usr/bin/python3 3.14.7; Node v22.23.3/npm 10.9.9 under the configured mise Node 22 installation; /usr/bin/ffmpeg and ffprobe n9.0.2; /usr/bin/bwrap 0.13.0; /usr/bin/firefox present (version not recorded); no Chrome/Chromium on PATH. `/bin`, `/sbin`, `/lib`, `/lib64` are symlinks into `/usr` (merged-usr). Versions are metadata, not proof of integration/sandbox operation. |

S0 records the execution branch/HEAD, PR #3 merge commit, approved document hashes, hashes of all Appendix A test files, production removal targets, dependency declarations and shared consumers. Compare to the inspected snapshot. Validate the scoped diff between `a80efa8` and the new main; material source/contract changes require Plan revision. Hash this Plan externally after approval rather than embedding a self-referential hash.

## 2. Exact proposed file allowlist

Paths are repository-relative in the execution worktree. The following list is the scope boundary, not permission to edit them before Plan approval.

| Action | Exact paths | Purpose |
| --- | --- | --- |
| Delete desktop | `app.py`; `requirements-desktop.txt`; `ui/__init__.py`, `ui/copy_controls.py`, `ui/grouped_pipeline.py`, `ui/log_dialog.py`, `ui/main_window.py`, `ui/session_dialog.py`, `ui/session_support.py`, `ui/settings_dialog.py`, `ui/video_preview.py`, `ui/youtube_tab.py` | Retire GUI/dependency after caller and coverage gates. |
| Delete obsolete pre-SDLC documents (P1) | `MANIFEST.md`, `STATUS.md` | Owner decision P1. Delete in S4 after the reference re-check; no content migrated into other files. |
| Modify mixed tests | `tests/test_last_input_folder.py`, `tests/test_pipeline_data_flow.py`, `tests/test_sessions.py`, `tests/test_tts_preprocessing.py`, `tests/test_video_pages.py`, `tests/test_video_preview.py`, `tests/test_youtube_title_tags.py` | Keep pure assertions; replace supported business coverage through Qt-free consumers. `test_youtube_title_tags.py` switches its FakeAuth import to `tests.web_only_support` in S2. |
| Modify existing tests | `tests/test_youtube.py`; `frontend/tests/pipeline.test.ts` | Move three pure VideoMetadataUpdateTests; add web draft/tag/session restoration assertions. |
| Create test support/coverage/evidence | `tests/web_only_support.py`; `tests/test_web_business_regressions.py`; `tests/test_web_only_runtime.py`; `tests/web_smoke_app.py`; `intent/web-only-remove-pyqt6/coverage.md`; `intent/web-only-remove-pyqt6/evidence.md` | Qt-free fixtures, business replacements, runtime and Host/Origin oracles, browser fake-provider harness, executed coverage ledger and sanitized test/artifact report linked from the PR. |
| Delete Qt-centric tests, last | `tests/test_group_batches.py`, `tests/test_log_dialog.py`, `tests/test_settings_dialog.py`, `tests/test_step2_ui.py`, `tests/test_tts_ui.py`, `tests/test_video_ui.py`, `tests/test_youtube_ui.py` | Only after every valuable assertion has a GREEN destination; Appendix B accounts for desktop-only retirements. |
| Modify active guidance | `README.md`, `INSTALL.md`, `USAGE.md`, `CLAUDE.md` | Web/CLI setup, Qt-free commands, O1–O3 limits. Preserve Google Desktop OAuth guidance and automatic SDLC continuation. |
| Modify comment only | `media/video.py` module docstring | Remove obsolete QProcess wording if still present. No function/body change. |
| Carry approved task documents | `intent/web-only-remove-pyqt6/intent.md`, `intent/web-only-remove-pyqt6/spec.md`, `intent/web-only-remove-pyqt6/plan.md` | Include approved handoff in the isolated branch; preserve Intent/Spec content. Plan status/checklists may record authorized progress. |

No other source, test, package manifest/lockfile, AGENTS, Skill, .github, Eval, historical report or prior SDLC file changes are planned. References to `MANIFEST.md`/`STATUS.md` in `intent/verify-smoke-check/*` and Qt mentions in `BUILD_PROMPT.md`, `TTS_PREPROCESSING_*` and `evals/**` stay as historical/frozen text. Build/config/evidence outputs live outside Git under `$WEB_ONLY_RUN`; the only build-time writes inside the worktree are the gitignored `frontend/node_modules/.tmp` and `.vite` mount points, which `wo_node` overlays with private directories. If an additional business-source fix is necessary, stop that change and explain the uncovered scope gap.

## 3. Test support interfaces and isolation

Use existing unittest.TestCase conventions. Import modules by module name, not copied test functions. A test's green result must depend on the real behavior it claims.

| Component | Contract |
| --- | --- |
| `tests/web_only_support.py` | Created first in S2. Copy the Qt-free `FakeAuth` class from `tests/test_youtube_ui.py:30` with unchanged behavior, reusing MemorySecrets/ScriptedSession from tests/test_youtube.py; record an AST comparison of the two class bodies. The Qt-centric original keeps its local copy until S4 deletes it, so no deletion candidate is edited. Provide generated story/image/audio fixtures and a bounded job-wait helper. All outputs remain under the caller's TemporaryDirectory. No Settings.load from operator paths; the module itself imports no PyQt6/`ui`. |
| `BusinessRegressionTests` | New cases use the real PipelineService, JobManager, validated HTTP actions and persistence. Cases retain original method names except explicit renames in Appendix B. Fake OAuth/TTS/YouTube clients/transports and codec boundaries only where that test is a unit test. |
| `HeadlessLegacyTests` | Replace LegacyAndUiTests in-place; retain legacy preparation/provenance, worker cancellation/snapshot and settings-driven invalidation. Keep the other 23 preprocessing cases. |
| `WebPreviewRegressionTests` | Real prepared-narration preview path, both pictures and effective overrides; assert frame dimensions/content, missing inputs, changed provenance and safe publication. No sample fallback. |
| `WebOnlyRuntimeTests` | Five named entry tests: test_desktop_boundary_removed; test_supported_modules_import_without_qt; test_real_backend_health_without_qt; test_real_backend_host_origin_policy; test_cli_fixture_pipeline_without_qt. Child processes record attempts to import PyQt6/retired ui and verify actual installed-package absence. |
| `tests/web_smoke_app.py` | Test-only CLI accepts --fixture-root, --dist-dir and --port. Refuse to start unless `NOVEL_PIPELINE_CONFIG_DIR` is set and lies inside --fixture-root, and --dist-dir contains `index.html`. Bind 127.0.0.1, build the real service/JobManager/FastAPI app with `create_app(service, dist_dir=…)`, inject fake provider boundaries before startup, install the non-loopback socket guard, generate valid local FFmpeg media and print a FakeProviderActive diagnostic. Reject fixture paths outside the private root/symlinks. No production feature flag. |

TTS injection may supply a fake client_factory to the real TtsProcessor constructor; do not replace TtsProcessor.run/merge, execute_media, PipelineService.perform or JobManager with success stubs. Patch where the service actually resolves the client factory; verify the binding and call counts. Restore patches on every exit. A fake service test already present elsewhere is not proof of preserved real orchestration.

For child processes: use the explicit fresh venv interpreter without resolving its symlink to system Python. Set cwd to the execution root; keep root on sys.path for real module entry points. Use -B; do not use -I with -m tests/backend/pipeline unless an explicit root bootstrap is supplied. Build each child env from the explicit allowlist below, never by copying `os.environ` wholesale; give every child its own config/HOME/TMPDIR subdirectory under the invocation run directory. Assert that no QT_*, DISPLAY, WAYLAND_DISPLAY, PYTHONPATH, PYTHONHOME or credential-like variable (`*TOKEN*`, `*SECRET*`, `*KEY*`, `GOOGLE_*`) reaches the child. Direct subprocess tests use timeout=30 seconds; real media tests may use a declared 120-second bound. Timeout is ERROR, then terminate/reap all harness children.

### Per-invocation environment and cleanup

Every wrapper call (`wo_py`, `wo_node`, `wo_smoke_server`, §6) creates a fresh `$WEB_ONLY_RUN/runs/<kind>.XXXXXX` with private `home`, `tmp`, `config`, `xdg-config`, `xdg-cache` and a generated `hosts` file. Nothing is shared between invocations except the read-only venv/Node runtime/source, the build output directory and the evidence directory.

| Consumer | Variables passed explicitly (everything else cleared by `--clearenv`/`env -i`) |
| --- | --- |
| Python runtime/tests (`wo_py`, smoke server) | `PATH=/usr/bin:/bin`, `HOME`, `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `USER`/`LOGNAME=webonly`, `LANG`/`LC_ALL=C.UTF-8`, `TZ=UTC`, `NOVEL_PIPELINE_CONFIG_DIR=<run>/config`, `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`. |
| Node/npm (`wo_node`) | `PATH=<node prefix>/bin:/usr/bin:/bin`, `HOME`, `TMPDIR`, XDG pair, `USER`/`LOGNAME`, `LANG`/`LC_ALL`, `TZ`, `npm_config_cache=<run>/npm-cache`, `npm_config_offline=true`, `npm_config_update_notifier=false`, `npm_config_fund=false`, `npm_config_audit=false`. |
| Locally launched browser (only if used, §6) | `PATH=/usr/bin:/bin`, `HOME=<run>/browser-home`, `TMPDIR`, XDG pair, `XDG_RUNTIME_DIR=<run>/xdg-runtime` (mode 0700), `LANG`, `MOZ_HEADLESS=1`. Headed mode additionally passes exactly one of `DISPLAY` or `WAYLAND_DISPLAY` from the host; record the variable name, not its value. |
| Setup (pip/npm ci only) | `env -i` with `PATH`, `HOME=$WEB_ONLY_RUN/setup-home`, `TMPDIR=$WEB_ONLY_RUN/setup-tmp`, `LANG`, `PIP_CONFIG_FILE=/dev/null`, `PIP_DISABLE_PIP_VERSION_CHECK=1` or `npm_config_cache=<setup-home>/.npm`. No credential/proxy variables are forwarded; if the network requires a proxy, stop and report. |

Cleanup is controlled: `wo_cleanup_run` deletes only a resolved path under `$WEB_ONLY_RUN/runs/`, with `rm -rf --one-file-system`. A run directory is deleted automatically on exit 0 after its log/JUnit output is in `$WEB_ONLY_RUN/evidence`; on non-zero exit it is retained for diagnosis and listed in `evidence/runs.tsv`. Retained run directories are removed in S6 once sanitized evidence is captured. The smoke server is stopped by process group (TERM, then KILL after 5 seconds), then port closure and absence of leftover children are verified. `$WEB_ONLY_RUN` itself (venv, build, evidence) stays until the human review/merge decision and is removed afterwards only on owner instruction, after checking that it matches the recorded `novel-web-only.*` path and is owned by the current user. Never touch operator config, venvs, browser profiles or services on ports 8000/8765.

### Real-backend Host/Origin oracle (AT2)

`test_real_backend_host_origin_policy` starts the real `[fresh_venv_python, "-B", "-m", "backend", "--port", P]` child, waits for `/api/health`, and sends raw requests with `http.client` to `127.0.0.1:P`, setting Host explicitly (`putrequest(..., skip_host=True)`). It complements, and does not replace, the in-process `tests/test_web_api.py:36` case. Expected behavior derives from `backend/app.py:23–59` and `create_app` CORS settings:

| Case | Requests | Expected |
| --- | --- | --- |
| Accepted Host | Host `127.0.0.1:P`, `localhost:P`, `LOCALHOST:P`; no Origin | `GET /api/health` → 200 |
| Accepted Origin | Origin `http://127.0.0.1:P` with Host `127.0.0.1:P`; `http://localhost:P` with Host `localhost:P`; dev origins `http://localhost:5173` and `http://127.0.0.1:5173` | 200; `OPTIONS /api/jobs` preflight from `http://localhost:5173` with `Access-Control-Request-Method: POST` returns `access-control-allow-origin: http://localhost:5173` |
| Rejected Host | Host `evil.example`, `localhost.evil.example`, `127.0.0.1.evil.example`, `[::1]:P`, `localhost:0`, `localhost:70000` | 403 with the local-boundary detail on both `/api/health` and `/` |
| Rejected Origin | `null`, `https://evil.example`, `http://localhost:9999`, `https://127.0.0.1:P`, `http://127.0.0.1:P/evil`, `http://user@127.0.0.1:P`, cross-authority `http://localhost:P` with Host `127.0.0.1:P`, two Origin headers | 403 with the origin detail on both `/api/health` and `/`; no `access-control-allow-origin` header |
| Protocol-level rejection | Missing Host; two Host headers | Non-2xx. Record the actual status (h11 may answer 400 before the middleware's 403); either is acceptable, 2xx is FAIL |
| Bind address | Startup output and listening socket | Uvicorn reports `http://127.0.0.1:P`; no wildcard bind |

This is a preservation test: expected GREEN at the S1 baseline and after S4. A failure is a security regression or harness defect to diagnose, never an expected RED.

### Network controls and limits

- Automated Python regression (`wo_py`): private Bubblewrap network/mount namespace, minimal read-only runtime/source mounts, private /tmp, per-invocation HOME/config, generated `/etc/hosts` with only loopback names, no `/etc/resolv.conf`, operator home, keyring sockets or common Git directory. Loopback works inside the namespace; external network is denied by namespace, not merely provider mocks.
- Frontend test/build (`wo_node`): the same namespace policy with preinstalled dependencies and `npm_config_offline=true`. The worktree is read-only; the only writable paths are the run directory, private overlays on the gitignored `frontend/node_modules/.tmp` and `.vite`, `$WEB_ONLY_DIST` and the evidence directory. A source fingerprint taken before and after each call must match.
- Before claiming either profile works, prove local HTTP success, external connection failure and absence of host-home/config paths. If bwrap/user namespaces are unavailable, report an environment blocker; do not silently share the host network or change global sysctl/AppArmor.
- Installation (pip/npm ci) is a separate public-package setup phase, never a provider/account call.
- Browser smoke (`wo_smoke_server`): the same mount/env isolation, but with `--share-net` so the browser can reach the loopback port. The server binds only 127.0.0.1, and its Python socket guard denies non-loopback connect/connect_ex/create_connection/getaddrinfo, with positive/negative controls. Credentials are absent and providers are fake.
- The browser itself: a locally launched browser uses a fresh profile with a dead proxy for every non-loopback host (§6), with a negative control. A browser controlled through the agent's browser tool runs outside this environment; record that limit. Neither is an OS egress sandbox for the browser; do not claim one. Only launch known local FFmpeg/FFprobe fixture commands, never provider URLs or real account sign-in.

## 4. Coverage migration rules

Appendix B assigns all **139 statically inventoried methods in 14 files**: 59 retained, 67 migrated, 3 pure cases moved, 10 desktop-only methods retired. These are planned dispositions, not collected counts or runtime PASS. In mixed methods, retain every business assertion and retire only identified Qt presentation assertions. Any mistaken retirement classification is corrected before deletion.

Before editing, create coverage.md with each source ID/hash, original assertion groups, destination assertions, disposition, requirement/AT, actual command/result and retirement justification. Appendix B is the initial map. Explicitly trace assertion groups sharing a method; one generic replacement or equal test count is insufficient.

| Family | Assertions that must survive / exact verification target |
| --- | --- |
| Data flow/grouping | Original fallback; exact normalized input including CJK; missing output fails closed; edited text invalidates chunks; ordered grouping and numeric confirmation fingerprint. Real document/service plus Step2 replacement; no widget assertions. |
| Input/settings | Settings roundtrip/invalid-folder fallback, input-relative output, ignored legacy output_dir; saved blank voice fallback vs rejected live blank edit; custom cleaning/quote/symbol rules on separate TTS text; title history, max_log_lines and export defaults. Native picker/font geometry retire. |
| Sessions | Schema-v1 field/text/media recovery; atomic failure keeps previous bytes; corrupt/traversal rejected; newer group state recovery; edited text/selection/drafts; missing media diagnostics; busy rejection; failed save preserves document; no empty startup session; current global account/tags stay current. Close prevention is replaced by save-error retention, not a fabricated web-close event. |
| Preprocessing | Preserve all 23 pure assertions. Legacy bundle/provenance, completed artifacts on cancel, separate working text, overrides/stale-plan rejection and downstream settings invalidation use real preparation/service workers. |
| Group batches | Selected subset/order and frozen settings; failure continues where supported, cancellation stops future work, incomplete TTS/resume keeps canonical bytes, zero-audio partial rejection, explicit partial missing indices, per-group pictures, damaged/deleted group safety, busy exclusion/progress, metadata freezing/completed skips, auth failure and restart semantics. Do not implement a missing queue inside test code and call that product coverage. |
| Upload metadata/tags | Preserve unrelated metadata fields and frozen insertion; disclosure both values; failure leaves local record unchanged; confirmed results persist story tags, failed/draft results do not; pending metadata remains frozen; story isolation and invalid saved config. Three pure metadata cases move unchanged. |
| Logs | Actual per-job lines, ordering/severity/bounds and repeated reads; reads leave active job unchanged. Window/shortcut/clipboard interaction retires. |
| TTS failures/progress | Root error on zero successes, no invalid merge, full original/effective failed-part diagnostics, callback progress visible in real HTTP job snapshots, cancel/resume semantics. Qt signal bridge retires. |
| Video/pages | All 17 page/VFR cases preserved, including real MP3/packet timing. Replace Qt render session segment by real headless render/CPU fallback; exact input hashes, both pictures, current paths, progress, cancellation and prior valid publication remain covered. |
| Preview | Nine geometry/render/timeline cases retained. Full frame derives from prepared effective narration/audio/pictures; no sample on missing inputs. Changed picture/audio/provenance rejected or invalidates cache; failures do not publish a bad replacement. |
| Fake OAuth/upload | Changed settings reach factory; configured-but-disconnected stays disconnected; clear safe errors; valid automatic inputs/metadata; progress/video ID/URL and duplicate guard; thumbnail retry without second upload; metadata validation/schedule privacy; frozen resume metadata; responsive cancellation and persisted partial state. No real login/upload. |
| Actual web UI | Built app restores legacy schema-v1 state, selection and metadata/tag draft; explicit partial/duplicate confirmation, busy/error/cancel controls, preview/download and retry visible in real browser. Pure frontend state tests alone do not prove these interactions. |

Source inspection shows web selected-group actions/confirmations in frontend/src/screens/media-screens.tsx, youtube-screen.tsx and components/wizard.tsx; headless job failure/cancellation in backend/jobs.py. This establishes candidate consumers, not exact parity for every desktop queue edge case. If a valuable assertion exposes an unsupported required workflow, record the gap and seek scope disposition instead of relaxing the assertion or implementing a new feature.

## 5. Ordered execution tasks

### S0 — Pin isolated workspace and usable evidence environment

**Dependencies:** Explicit approval of this Plan; approved Intent/Spec hashes; PR #3 merged by a human (P2).
**Files:** Carry only the three approved task documents; no product edits.
**Trace:** N1–N6, D4/D6, AT1/AT10, AR3.

- [x] Confirm PR #3 is MERGED and its merge commit is an ancestor of fetched `origin/main`; otherwise stop and report the blocker. Never merge, rebase or push PR #3 from this task.
- [x] Capture status/HEAD/worktree inventory and hashes without reading secret configuration.
- [x] Validate scoped source equivalence between `a80efa8` and the new main; create the managed worktree and codex/web-only-remove-pyqt6 branch from that main. Resolve all paths from its root.
- [x] Copy the three approved task documents; read the preserved REVIEW and Skill. Capture their hashes privately. No Lesson 9 commit/hunk or unrelated untracked file is transferred.
- [x] Create `$WEB_ONLY_RUN`, the fresh venv and `wo-env.bash` (§6); run public-package setup with `env -i`; `npm ci --ignore-scripts` in this worktree's frontend; pre-create the gitignored `node_modules/.tmp` and `.vite` mount points. Confirm package manifests/lockfiles unchanged. Record versions/origins without credential-bearing URLs.
- [x] Verify Python/Node floors, no installed Qt, importable required test dependencies, real local FFmpeg/FFprobe, fonts; probe `wo_py`/`wo_node` loopback-positive, egress-negative and host-home-absent controls; confirm the source fingerprint is unchanged by a `wo_node` dry run.
- [x] Identify the browser path for S5: the executing agent's browser automation tool, or the local Firefox driven by an automation client already available to the agent. Record which. No new browser/driver installation without separate approval; if neither can perform interactive smoke, that is a recorded blocker for S5.

**Done:** Exact isolated baseline/input hashes, PR #3 merge evidence and usable dependency/isolation evidence recorded. An absent dependency or denied namespace is setup ERROR, not an expected feature failure.

### S1 — Establish removal RED and freeze coverage inventory

**Dependencies:** S0.
**Files:** Create test_web_only_runtime.py and coverage.md.
**Trace:** R1/R3/R5, D3/D4, AT1/AT4, AR1/AR3.

- [x] Build the coverage ledger from Appendix B and original assertion groups before deletion.
- [x] Add test_desktop_boundary_removed asserting absent desktop files/declaration, and runtime tests using real entry points/bounded children, including test_real_backend_host_origin_policy (§3).
- [x] Run only the desktop-boundary oracle on baseline: expect unittest FAIL/AssertionError because app.py/ui/requirements-desktop.txt are present; record assertion and exit 1.
- [x] Run test_real_backend_host_origin_policy on baseline: expect GREEN (preservation of the existing loopback policy). Record each accepted/rejected case and the actual status for protocol-level cases.
- [x] Preflight existing Qt-free preservation tests separately. Baseline failures become recorded baseline/harness concerns; do not count ImportError, collection zero, timeout or setup ERROR as removal RED.

**Done:** Legitimate removal RED, Host/Origin baseline GREEN and immutable original coverage inventory. No migration or deletion yet.

### S2 — Preserve mixed-module data/session/media coverage

**Dependencies:** S1.
**Files:** Modify seven mixed test files, create web_only_support.py, modify frontend/tests/pipeline.test.ts.
**Trace:** R2/R5–R11, D2/D3/D5, AT4–AT9/AT10.

- [x] First, create `tests/web_only_support.py` with the extracted FakeAuth (§3) and record the AST comparison with `tests/test_youtube_ui.py:30`. Validate in a child with the PyQt6/`ui` import blocker that importing `tests.web_only_support` attempts no Qt/`ui` import.
- [x] Switch `tests/test_youtube_title_tags.py:20` to `from tests.web_only_support import FakeAuth` and remove its other Qt/`ui` setup in the same change. Then run that file under `wo_py`; an ImportError here is a migration defect to fix before continuing, not a skip.
- [x] Remove Qt setup from the remaining mixed modules, preserving pure assertions and 23 preprocessing cases. Implement each migrated destination in Appendix B with the existing real consumers.
- [x] Keep schema-v1 fixtures, global configuration isolation and atomic failure bytes; add frontend draft/tag restoration tests using baseline-shaped legacy state.
- [x] Replace only the real VFR test's Qt session segment; retain real FFmpeg audio/timing checks and headless render/fallback/provenance.
- [x] Test prepared web preview plus missing/tampered inputs and prior-valid-output safety; retire only the three desktop sample/dialog cases.
- [x] Run focused mixed/headless/frontend tests. Newly added coverage is a preservation test, normally GREEN on unchanged core; do not invent RED by changing expected product behavior.

**Done:** Migrated mixed-module tests actually execute without Qt and preserve identified assertion groups. Update ledger with commands/results. Core is unchanged.

### S3 — Replace Qt-centric business coverage before deleting it

**Dependencies:** S2.
**Files:** Create test_web_business_regressions.py; move VideoMetadataUpdateTests into test_youtube.py. Keep seven old Qt-centric files until coverage is GREEN.
**Trace:** R2/R5/R6/R8–R10, D2/D3/D5, AT4–AT8/AT10, AR1.

- [x] Add mapped BusinessRegressionTests against actual service/job/HTTP paths; use only controlled provider/process boundaries.
- [x] Move three pure metadata cases unchanged. (The title-tag FakeAuth dependency was already removed in S2.)
- [x] Verify selected group order, numeric confirmation, busy exclusion, failure/cancel/resume, partial merging, per-group images, logs and settings invariants.
- [x] Verify fake account/upload metadata, frozen retries, disclosure, tag persistence, thumbnail retry/duplicate guard and cancellation.
- [x] Cross-check every old business assertion against its new destination and executed evidence. Do not use a harness-invented queue to satisfy missing production behavior.
- [x] Run all focused replacements, pure metadata and existing headless/web/auth regressions.

**Done:** Every valuable assertion in the seven deletion candidates has an executed GREEN destination or an explicit unresolved coverage blocker. No deletion with unresolved business gaps.

### S4 — Remove desktop consumer and update active guidance

**Dependencies:** S2/S3 coverage gates.
**Files:** All desktop deletions, seven Qt-centric test deletions, MANIFEST.md/STATUS.md deletion (P1), README/INSTALL/USAGE/CLAUDE, media/video.py docstring only.
**Trace:** R1–R5/R11/R12, D1/D3/D4/D6, AT1/AT2/AT4/AT9, AR1/AR2.

- [x] Recheck all callers/imports before deleting desktop files. Keep media/tts_preparation.py and other needed Qt-free compatibility helpers.
- [x] Delete allowlisted desktop files/dependency and now-covered Qt-centric modules. No skips/ignore lists or compatibility Qt shim.
- [x] Re-run `git grep -nI -E 'MANIFEST\.md|STATUS\.md'` outside the two files. If only historical `intent/verify-smoke-check/*` matches, delete both files; otherwise stop that deletion and report the active consumer.
- [x] Correct active web/CLI installation/test guidance; replace old real-provider retention gate with approved conditional O2 evidence, retaining explicit live-provider limits. Remove any link to the deleted MANIFEST/STATUS from active guidance.
- [x] Preserve existing safety/SDLC continuation rules (as merged via PR #3) and Google installed-client/OS keyring guidance. Correct only the obsolete QProcess docstring at `media/video.py:5` if present.
- [x] Run the removal oracle: expect GREEN for the same assertion that failed S1; then the Host/Origin oracle (still GREEN), Qt-free collection and focused imports/entry tests.

**Done:** Boundary removed; real no-Qt imports/collection, Host/Origin policy and CLI/backend checks pass. Active guidance is coherent, historical/Eval files unchanged.

### S5 — Prove full retained regression and actual Linux web use

**Dependencies:** S4.
**Files:** Test harness and ledger only as already allowlisted; no business-source fix without scope disposition.
**Trace:** R1–R11/N1–N4, D4/D5, AT1–AT10, AR3.

- [x] Run full Python collection and suite in fresh Qt-free private-network environment; review every skip/error/failure.
- [x] Run frontend tests/build through `wo_node` into `$WEB_ONLY_DIST`, with matching before/after source fingerprints, and required real FFmpeg/FFprobe integrations. Missing tooling/required skips block acceptance.
- [x] Verify actual backend module startup/health, the real-backend Host/Origin oracle, and real CLI help + fixture import→normalize→group→export, ordered outputs and natural exit. Static serving of the real build is verified through the smoke server's `create_app(dist_dir=$WEB_ONLY_DIST)`.
- [x] Start the fake-provider browser harness with `wo_smoke_server`, probe its guards and diagnostic; use the real built frontend in the browser identified at S0 through loopback, with the browser environment/proxy controls of §6.
- [x] Exercise import/edit/group/save/reopen, selected-group TTS success/failure/cancel, prepared preview with pictures, video/download, fake account/upload/thumbnail retry and partial/duplicate confirmations. Capture job IDs/outcomes and console/screenshots; do not open real provider URLs.
- [x] Repeat isolation-sensitive cases; check patch restoration, child reaping, fresh configuration, bytes/provenance and no leftover publication parts.
- [x] Complete each ledger evidence cell and AT status from actual outputs; write the sanitized `evidence.md` report (§6). Linux result must not claim Python 3.11 itself, Windows/macOS or real TTS/YouTube have passed.

**Done:** All required local acceptance gates have actual successful evidence; remaining non-required limits explicitly recorded. A browser substitute/static response does not satisfy browser smoke.

### S6 — Review, scoped PR and human handoff

**Dependencies:** S5 acceptance evidence.
**Files:** Only allowlist; Plan/coverage evidence as authorized.
**Trace:** R5/R12/N4–N6, D6, AR1–AR3.

- [x] Self-review Bugs/Security/Compliance with REVIEW.md and the data-integrity Skill.
- [x] Obtain one fresh read-only independent review of the complete diff, assertion ledger and evidence; main agent retains decisions. Fix only in-scope findings, rerun affected checks after any change.
- [x] Compare root/sibling worktree status and protected hashes to S0. Check untracked additions in diff review as well as tracked deletions.
- [x] Commit only explicit allowlisted paths in isolated branch; no git add ., unrelated artifacts, force push or reset/stash.
- [x] Confirm the branch is based on post-PR #3 main and its diff contains no Lesson 9 change (`git diff origin/main...HEAD --stat` lists only §2 paths).
- [ ] Prepare a scoped Draft PR against main with actual evidence, coverage and unverified provider/platform limits. Link `evidence.md` and `coverage.md` at the exact head SHA and attach or list artifacts as in §6 "Evidence report and PR attachments". Give the PR URL and local artifact paths in the handoff message. Push only this branch as part of approved PR preparation.
- [x] Remove retained per-invocation run directories after their sanitized evidence is captured; keep `$WEB_ONLY_RUN` (venv, build, evidence) until the human decision.
- [ ] Observe existing CI for that PR's exact tested head. Existing Eval CI is not proof of web/core tests; do not run paid Live Eval or fix unrelated Eval infrastructure. Report FAIL/ERROR/skips honestly.
- [ ] Stop for final human review/merge decision. Keep implementation worktree available. No automatic merge or deploy.

**Done:** Reviewable scoped PR and exact-head evidence; unresolved required tests/findings/CI blockers are visible, not called READY to merge.

## 6. Commands after approval — not executed

Commands run from the implementation worktree created in S0 from post-PR #3 main. No command below authorizes an action now. Setup downloads are limited to public dependencies in the disposable environment; test/provider phases are offline. Agent shell state does not persist between tool calls: after setup, every command runs in **bash** as `bash -c 'source "$WEB_ONLY_ENV"; <command>'`, where `WEB_ONLY_ENV` is the generated `$WEB_ONLY_RUN/bin/wo-env.bash` path recorded in evidence.

### PR #3 precondition and identity

```sh
gh pr view 3 --json state,mergedAt,mergeCommit,baseRefName,headRefName
git fetch origin main
git merge-base --is-ancestor "<PR #3 merge commit SHA>" origin/main
git diff --stat a80efa8d92bd4f24cf4f66eefc62b20795f53aa8 origin/main -- app.py ui backend pipeline media config chapters cleaning chunking filtering exporters tests frontend requirements.txt requirements-core.txt requirements-desktop.txt README.md INSTALL.md USAGE.md MANIFEST.md STATUS.md
```

Continue only when the state is MERGED and the ancestry check exits 0. Any scoped diff in the last command is reviewed against this Plan before the worktree is created; material change requires Plan revision. Then, in the new worktree:

```sh
git status --short
git rev-parse HEAD
git worktree list --porcelain
sha256sum intent/web-only-remove-pyqt6/intent.md intent/web-only-remove-pyqt6/spec.md intent/web-only-remove-pyqt6/plan.md
```

### Private run root and setup

```sh
WEB_ONLY_ROOT=$(git rev-parse --show-toplevel)
WEB_ONLY_RUN=$(mktemp -d -t novel-web-only.XXXXXX)
chmod 700 "$WEB_ONLY_RUN"
mkdir -p "$WEB_ONLY_RUN"/bin "$WEB_ONLY_RUN"/runs "$WEB_ONLY_RUN"/evidence "$WEB_ONLY_RUN"/frontend-dist "$WEB_ONLY_RUN"/setup-home "$WEB_ONLY_RUN"/setup-tmp
WEB_ONLY_NODE_PREFIX=$(dirname "$(dirname "$(readlink -f "$(command -v node)")")")
/usr/bin/python3 -m venv "$WEB_ONLY_RUN/venv"
env -i PATH=/usr/bin:/bin HOME="$WEB_ONLY_RUN/setup-home" TMPDIR="$WEB_ONLY_RUN/setup-tmp" LANG=C.UTF-8 \
  PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 \
  "$WEB_ONLY_RUN/venv/bin/python" -m pip install -r requirements.txt pytest httpx
env -i PATH="$WEB_ONLY_NODE_PREFIX/bin:/usr/bin:/bin" HOME="$WEB_ONLY_RUN/setup-home" TMPDIR="$WEB_ONLY_RUN/setup-tmp" LANG=C.UTF-8 \
  npm_config_cache="$WEB_ONLY_RUN/setup-home/.npm" npm_config_update_notifier=false npm_config_fund=false \
  npm --prefix "$WEB_ONLY_ROOT/frontend" ci --ignore-scripts
mkdir -p "$WEB_ONLY_ROOT/frontend/node_modules/.tmp" "$WEB_ONLY_ROOT/frontend/node_modules/.vite"
git status --short -- frontend/package.json frontend/package-lock.json package.json requirements.txt requirements-core.txt
```

`WEB_ONLY_NODE_PREFIX` resolves the observed Node 22 installation (not a repository path); if `command -v node` is absent or below 22.12, that is setup ERROR. If a necessary dependency install script was suppressed by `--ignore-scripts`, inspect the specific public package requirement and report setup failure; do not pretend the build succeeded. The setup phase forwards no credential or proxy variables.

Write `$WEB_ONLY_RUN/bin/wo-env.bash` (outside Git), substituting the literal values recorded above:

```bash
# Generated for one WEB_ONLY_RUN; bash only. Not part of the repository.
export WEB_ONLY_ROOT='<worktree root>' WEB_ONLY_RUN='<run root>' WEB_ONLY_NODE_PREFIX='<node prefix>'
export WEB_ONLY_PYTHON="$WEB_ONLY_RUN/venv/bin/python" WEB_ONLY_DIST="$WEB_ONLY_RUN/frontend-dist"
WEB_ONLY_RUN_REAL=$(realpath -e -- "$WEB_ONLY_RUN") || return 1

wo_new_run() {       # $1 = kind; prints a fresh per-invocation directory
  local dir
  dir=$(mktemp -d "$WEB_ONLY_RUN/runs/$1.XXXXXX") || return 1
  mkdir -p "$dir"/home "$dir"/tmp "$dir"/config "$dir"/xdg-config "$dir"/xdg-cache || return 1
  printf '127.0.0.1 localhost\n::1 localhost\n' > "$dir/hosts"
  printf '%s\n' "$dir"
}

wo_cleanup_run() {   # deletes only a directory created by wo_new_run
  local resolved
  resolved=$(realpath -e -- "$1") || return 1
  case "$resolved" in
    "$WEB_ONLY_RUN_REAL"/runs/?*) rm -rf --one-file-system -- "$resolved" ;;
    *) echo "refusing cleanup outside runs/: $resolved" >&2; return 1 ;;
  esac
}

wo_finish_run() {    # $1 run dir, $2 exit code, $3 label
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$2" "${1#"$WEB_ONLY_RUN"/}" "$3" >> "$WEB_ONLY_RUN/evidence/runs.tsv"
  if [ "$2" -eq 0 ]; then wo_cleanup_run "$1"; else echo "retained for diagnosis: $1" >&2; fi
}

wo_source_fingerprint() {   # tracked + untracked (non-ignored) source state
  { git -C "$WEB_ONLY_ROOT" rev-parse HEAD
    git -C "$WEB_ONLY_ROOT" status --porcelain=v1 --untracked-files=all
    git -C "$WEB_ONLY_ROOT" diff HEAD --binary
    (cd "$WEB_ONLY_ROOT" && git ls-files -o --exclude-standard -z | xargs -0r sha256sum --)
  } | sha256sum | cut -d' ' -f1
}

wo_base_args() {     # fills WO_ARGS for run dir $1; /tmp tmpfs comes BEFORE binds under /tmp
  local run=$1 p
  WO_ARGS=(--unshare-all --new-session --die-with-parent --cap-drop ALL --clearenv
           --proc /proc --dev /dev --tmpfs /tmp --ro-bind /usr /usr)
  for p in bin sbin lib lib64; do
    if [ -L "/$p" ]; then WO_ARGS+=(--symlink "$(readlink "/$p")" "/$p")
    elif [ -d "/$p" ]; then WO_ARGS+=(--ro-bind "/$p" "/$p"); fi
  done
  WO_ARGS+=(--dir /etc --ro-bind "$run/hosts" /etc/hosts
            --ro-bind "$WEB_ONLY_ROOT" "$WEB_ONLY_ROOT"
            --bind "$run" "$run"
            --bind "$WEB_ONLY_RUN/evidence" "$WEB_ONLY_RUN/evidence"
            --setenv HOME "$run/home" --setenv TMPDIR "$run/tmp"
            --setenv XDG_CONFIG_HOME "$run/xdg-config" --setenv XDG_CACHE_HOME "$run/xdg-cache"
            --setenv USER webonly --setenv LOGNAME webonly
            --setenv LANG C.UTF-8 --setenv LC_ALL C.UTF-8 --setenv TZ UTC)
}

wo_py_args() {       # Python-specific env for run dir $1
  WO_PY_ARGS=(--ro-bind "$WEB_ONLY_RUN/venv" "$WEB_ONLY_RUN/venv" --chdir "$WEB_ONLY_ROOT"
              --setenv PATH /usr/bin:/bin --setenv NOVEL_PIPELINE_CONFIG_DIR "$1/config"
              --setenv PYTHONIOENCODING utf-8 --setenv PYTHONUTF8 1
              --setenv PYTHONDONTWRITEBYTECODE 1 --setenv PYTHONNOUSERSITE 1)
}

wo_py() {            # offline Python: private net namespace, loopback only
  local run rc
  run=$(wo_new_run py) || return 1
  wo_base_args "$run"; wo_py_args "$run"
  bwrap "${WO_ARGS[@]}" "${WO_PY_ARGS[@]}" "$WEB_ONLY_PYTHON" -B "$@"
  rc=$?; wo_finish_run "$run" "$rc" "py $*"; return "$rc"
}

wo_node() {          # offline npm in frontend/: read-only source, private build/cache paths
  local run rc before after
  run=$(wo_new_run node) || return 1
  mkdir -p "$run"/ts-buildinfo "$run"/vite-cache "$run"/npm-cache
  before=$(wo_source_fingerprint)
  wo_base_args "$run"
  bwrap "${WO_ARGS[@]}" \
    --ro-bind "$WEB_ONLY_NODE_PREFIX" "$WEB_ONLY_NODE_PREFIX" \
    --bind "$run/ts-buildinfo" "$WEB_ONLY_ROOT/frontend/node_modules/.tmp" \
    --bind "$run/vite-cache" "$WEB_ONLY_ROOT/frontend/node_modules/.vite" \
    --bind "$WEB_ONLY_DIST" "$WEB_ONLY_DIST" \
    --chdir "$WEB_ONLY_ROOT/frontend" \
    --setenv PATH "$WEB_ONLY_NODE_PREFIX/bin:/usr/bin:/bin" \
    --setenv npm_config_cache "$run/npm-cache" --setenv npm_config_offline true \
    --setenv npm_config_update_notifier false --setenv npm_config_fund false --setenv npm_config_audit false \
    npm "$@"
  rc=$?
  after=$(wo_source_fingerprint)
  if [ "$before" != "$after" ]; then echo "source fingerprint changed during wo_node" >&2; rc=90; fi
  wo_finish_run "$run" "$rc" "node $*"; return "$rc"
}

wo_smoke_server() {  # $1 = port; loopback-reachable server, in-process egress guard
  local run rc
  run=$(wo_new_run smoke) || return 1
  mkdir -p "$run/browser"
  wo_base_args "$run"; wo_py_args "$run"
  WO_PY_ARGS+=(--setenv NOVEL_PIPELINE_CONFIG_DIR "$run/browser/config")
  bwrap "${WO_ARGS[@]}" --share-net "${WO_PY_ARGS[@]}" \
    --ro-bind "$WEB_ONLY_DIST" "$WEB_ONLY_DIST" \
    "$WEB_ONLY_PYTHON" -B -m tests.web_smoke_app \
      --fixture-root "$run/browser" --dist-dir "$WEB_ONLY_DIST" --port "$1"
  rc=$?; wo_finish_run "$run" "$rc" "smoke port=$1"; return "$rc"
}
```

The worktree is mounted read-only in every wrapper, so tests and builds cannot overwrite source; the fingerprint check in `wo_node` is recorded evidence of that. The only writable paths are the invocation run directory, `$WEB_ONLY_RUN/evidence`, `$WEB_ONLY_DIST` (`wo_node` only) and the two private overlays on gitignored `frontend/node_modules/.tmp` and `.vite`. The later `--setenv NOVEL_PIPELINE_CONFIG_DIR` in `wo_smoke_server` overrides the earlier one, which keeps the config inside --fixture-root as the harness requires. Namespace availability and this mount profile are runtime-unverified; S0 proves them with positive/negative controls. If public font/cache files outside /usr are required, bind only that identified public directory read-only and record it. No operator HOME, /run credential sockets or /etc secret/config directory is mounted.

The complete suite may attempt writes under repository paths. Treat a resulting read-only setup error as a fixture-isolation defect to diagnose; do not silently expose user directories or count it as a product RED. Any writable test-copy fallback must be an isolated copy with the same tracked-source hash and recorded boundaries.

### RED, focused GREEN and regression

Each line below runs as `bash -c 'source "$WEB_ONLY_ENV"; <line>'`:

```sh
wo_py -m unittest -v tests.test_web_only_runtime.WebOnlyRuntimeTests.test_desktop_boundary_removed
wo_py -m unittest -v tests.test_web_only_runtime.WebOnlyRuntimeTests.test_real_backend_host_origin_policy
wo_py -m pytest -p no:cacheprovider -q tests/test_headless_service.py tests/test_headless_media.py tests/test_web_jobs.py tests/test_web_api.py
wo_py -m pytest -p no:cacheprovider -q tests/test_youtube_title_tags.py
wo_py -m pytest -p no:cacheprovider -q tests/test_last_input_folder.py tests/test_pipeline_data_flow.py tests/test_sessions.py tests/test_tts_preprocessing.py tests/test_video_preview.py
wo_py -m pytest -p no:cacheprovider -q tests/test_web_business_regressions.py tests/test_youtube.py tests/test_youtube_auth.py tests/test_youtube_pipeline.py
wo_py -m pytest -p no:cacheprovider -q tests/test_video_pages.py::RealVfrTests
wo_py -m unittest -v tests.test_web_only_runtime
wo_py -m pytest -p no:cacheprovider --collect-only -q
wo_py -m pytest -p no:cacheprovider -q -rA --junitxml="$WEB_ONLY_RUN/evidence/pytest-full.xml"
```

S1's first command must return 1 with the expected assertion FAIL; after S4 the identical command must return 0. The Host/Origin command must return 0 at S1, S4 and S5. Setup ERROR, pytest exit 2/3/4/5, zero tests, timeouts or unrelated failures never establish RED or GREEN. Required VFR tests must run rather than skip; summarize full-suite skips individually.

Frontend commands, each wrapped the same way; the build writes only to `$WEB_ONLY_DIST`:

```sh
wo_node run test > "$WEB_ONLY_RUN/evidence/frontend-test.log" 2>&1
wo_node run build -- --outDir "$WEB_ONLY_DIST" --emptyOutDir > "$WEB_ONLY_RUN/evidence/frontend-build.log" 2>&1
(cd "$WEB_ONLY_DIST" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$WEB_ONLY_RUN/evidence/dist-manifest.txt"
wo_source_fingerprint > "$WEB_ONLY_RUN/evidence/dist-source-fingerprint.txt"
```

`npm run build -- …` appends the options to the `vite build` part of `tsc -b && vite build`; check the build log to confirm output went to `$WEB_ONLY_DIST` and that no `frontend/dist` appeared in the worktree. Record exits, test counts and tool versions. Build already includes TypeScript checking.

Runtime test child argv are [fresh_venv_python, "-B", "-m", "backend", "--port", available_port] and [fresh_venv_python, "-B", "-m", "pipeline", "--help"]. The CLI fixture child uses the existing `run` arguments with generated input paths, `--title`, `--group-size` and `--export json`; verify canonical grouping/output and natural return code 0. No provider options (`--tts`, `--video`, `--prepare`) are enabled.

### Browser smoke

```sh
wo_smoke_server "$WEB_ONLY_PORT"      # run in background; logs to $WEB_ONLY_RUN/evidence/smoke-server.log
```

WEB_ONLY_PORT is a harness-reserved free loopback port; retry bounded allocation races, never kill an operator service on 8000/8765. The browser opens only `http://127.0.0.1:$WEB_ONLY_PORT/`. Server/request bounds: startup 30 seconds; each operation 120 seconds; entire smoke 15 minutes. Stop the server by process group (TERM, then KILL after 5 seconds), verify the port is closed and no child remains. Missing browser, provider marker or guard control is ERROR, not simulated PASS.

If the local Firefox is the browser (S0), launch it with a cleared environment and a fresh profile whose `user.js` sends every non-loopback request to a dead proxy:

```sh
BROWSER_RUN=$(wo_new_run browser); mkdir -p -m 700 "$BROWSER_RUN/xdg-runtime"; mkdir -p "$BROWSER_RUN/profile"
cat > "$BROWSER_RUN/profile/user.js" <<'EOF'
user_pref("network.proxy.type", 1);
user_pref("network.proxy.http", "127.0.0.1");
user_pref("network.proxy.http_port", 9);
user_pref("network.proxy.ssl", "127.0.0.1");
user_pref("network.proxy.ssl_port", 9);
user_pref("network.proxy.no_proxies_on", "127.0.0.1");
user_pref("network.proxy.allow_hijacking_localhost", false);
user_pref("app.update.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("network.captive-portal-service.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
EOF
env -i PATH=/usr/bin:/bin HOME="$BROWSER_RUN/home" TMPDIR="$BROWSER_RUN/tmp" \
  XDG_CONFIG_HOME="$BROWSER_RUN/xdg-config" XDG_CACHE_HOME="$BROWSER_RUN/xdg-cache" \
  XDG_RUNTIME_DIR="$BROWSER_RUN/xdg-runtime" LANG=C.UTF-8 MOZ_HEADLESS=1 \
  firefox --headless --no-remote --profile "$BROWSER_RUN/profile" <automation-client remote options>
```

The `<automation-client remote options>` belong to the automation client already available to the agent; record them. Headed mode drops `MOZ_HEADLESS`/`--headless` and passes exactly one of `DISPLAY` or `WAYLAND_DISPLAY`, recording only the name. Negative control: an `http://example.invalid/` navigation must fail; positive control: the loopback app loads. Finish with `wo_finish_run "$BROWSER_RUN" <exit> browser`. If the agent's own browser tool is used instead, its browser runs outside this environment: record the browser name/version, open only the loopback URL in a new tab, sign in nowhere, and state that its environment and egress were not controlled by this Plan.

### Evidence report and PR attachments

- Raw evidence stays under `$WEB_ONLY_RUN/evidence/`: `runs.tsv`, pytest JUnit XML, frontend test/build logs, `dist-manifest.txt`, the source fingerprint, smoke-server log, browser job IDs, console logs and screenshots.
- `intent/web-only-remove-pyqt6/evidence.md` (committed, sanitized) records the environment/versions, source fingerprint and head SHA, every command with exit code, test counts, each skip/failure/error, AT1–AT10/AR1–AR3 status, the Host/Origin case table, coverage summary, and for every raw artifact its `$WEB_ONLY_RUN`-relative path, size and SHA-256. No home paths, usernames, secrets, real story text or credential-bearing URLs.
- The PR body summarizes results and links `evidence.md` and `coverage.md` as `https://github.com/<owner>/<repo>/blob/<head SHA>/intent/web-only-remove-pyqt6/…` so the links stay pinned to the tested head. Results produced after PR creation are posted with `gh pr comment --body-file` and the new head SHA.
- `gh` cannot attach binary files (screenshots, XML) to a PR or comment. If the executing agent has a tool that attaches files to the PR or shares them with the reviewer, use it and record the link. Otherwise do not upload them to gists or external hosts, and do not commit them, without separate owner approval. List them in `evidence.md`/PR body as above, give their absolute local paths in the handoff message, and keep `$WEB_ONLY_RUN/evidence` until the human review ends.

### Diff, staging and PR

```sh
git diff --check
git diff --stat
git diff --stat origin/main...HEAD
git status --short
git diff --no-index --check /dev/null tests/web_only_support.py
git diff --no-index --check /dev/null tests/test_web_business_regressions.py
git diff --no-index --check /dev/null tests/test_web_only_runtime.py
git diff --no-index --check /dev/null tests/web_smoke_app.py
git diff --no-index --check /dev/null intent/web-only-remove-pyqt6/coverage.md
git diff --no-index --check /dev/null intent/web-only-remove-pyqt6/evidence.md
```

Review the other new task documents too. For new-file diff commands, distinguish reported whitespace errors from normal no-index difference status; never omit untracked additions from review. Stage only explicit §2 paths; inspect staged names/diff before git commit. Write PR body to an external temporary file with real newlines, then:

```sh
git push -u origin codex/web-only-remove-pyqt6
gh pr create --draft --base main --head codex/web-only-remove-pyqt6 --title "Remove PyQt6 desktop and preserve web/core regression coverage" --body-file "$WEB_ONLY_RUN/evidence/pr-body.md"
```

No commit/push/PR occurs before Plan approval. CI/review evidence belongs to the tested head; a subsequent fix requires corresponding fresh validation and an updated `evidence.md`.

## 7. Requirements → steps → acceptance

| Requirements | Design | Steps | Acceptance |
| --- | --- | --- | --- |
| R1/R3 | D1/D4 | S0/S1/S4/S5 | AT1/AT4, AR1 |
| R2 | D2/D4/D5 | S1/S2/S3/S4/S5 | AT2 (incl. real-backend Host/Origin oracle)/AT4, AR2 |
| R4 | D2/D4 | S1/S4/S5 | AT3, AR1 |
| R5 | D3/D5 | S1/S2/S3/S5/S6 | AT4–AT9, AR1/AR3 |
| R6 | D2/D3/D5 | S2/S3/S5 | AT5/AT7/AT9, AR1 |
| R7 | D2/D3 | S2/S5 | AT6, AR1 |
| R8 | D2/D3/D5 | S2/S3/S5 | AT5–AT8/AT10 |
| R9 | D2/D3/D6 | S3/S4/S5 | AT8/AT10, AR2 |
| R10 | D2/D3 | S2/S3/S5 | AT3/AT6/AT8 |
| R11 | D1/D3/D5 | S2/S4/S5 | AT9, AR1/AR2 |
| R12 | D6 | S4 (guidance; MANIFEST.md/STATUS.md deletion per P1)/S6 | AR2/AR3 |
| N1/N2 | D2/D4/D5 | S0/S2/S3/S5 | AT5–AT10, AR3 |
| N3 | D1–D4 | S2/S3/S4/S5 | AT1/AT3–AT9, AR1 |
| N4/N5/N6 | D3–D6 | S0–S6 | AT1–AT10, AR1–AR3 |

## 8. Risks, alternatives, stop conditions and rollback

| Priority / owner | Risk and response |
| --- | --- |
| P1 Technical Lead/QA | Highest risk is losing business assertions in Qt-centric batch/session/upload tests. Method counts alone are inadequate. Require assertion ledger and real-consumer GREEN before deletions; unresolved workflow gaps require owner decision. |
| P1 Technical Lead | Main/source baselines may advance; exact inspected application equivalence is static only. Revalidate scope/hashes before work; material changes require Plan revision. |
| P1 QA | Namespace, dependencies, fonts, FFmpeg or browser may fail. Diagnose setup separately; do not claim coverage or provider parity from skips/stubs. |
| P1 QA | Fake fixture boundary can mask real persistence/worker failures. Keep business functions/workers real, assert call/outputs/errors and browser outcomes. |
| P1 Technical Lead | Old sessions/global settings/provenance may be invalidated accidentally. Use baseline-shaped synthetic sessions and atomic-error/tamper cases; no migrations or real-data reads. |
| P1 Owner/Reviewer | PR #3 (Lesson 9 eval CI + SDLC rules) is not yet merged. S0 is blocked until a human merges it; this task never merges, cherry-picks or rebases PR #3 content. If PR #3 changes scoped files, revise this Plan before work. |
| P2 Reviewer | Lesson 9 changes reach this PR only through post-PR #3 main. Do not import Eval fixes; record unrelated existing CI failure separately. Existing workflow is not product-regression proof. |
| P2 QA | Evidence binaries cannot be attached with `gh`. Link committed sanitized `evidence.md` at the head SHA and keep raw artifacts locally with path/size/SHA-256 until review ends (§6). |
| P2 Product Owner | Qt widgets disappear intentionally; future users may expect desktop-only behavior. Document approved retirements and retained web workflows; new required features need separate scope approval. |

Considered alternatives: remove dependency first (rejected: collection and mixed coverage break); retain Qt shim/offscreen tests (rejected: violates R1/R3); blanket-delete/skip Qt tests (rejected: violates R5); move sample preview into core (rejected: contradicts O1); implement all missing desktop features in web (rejected: exceeds Spec); execute on current Lesson 9 branch (rejected: unrelated PR/workspace changes); new web CI workflow (deferred: outside scope). Native sequential migration is recommended because tests/fixtures/deletions are coupled; use a fresh independent reader for final review.

Stop the dependent step for a genuine blocker: real data/credential access needed; unsupported required business contract; algorithm/schema change; unmapped business assertion; materially changed baseline; missing required execution tooling/isolation; unavailable GitHub permission. Continue independent authorized work while recording the blocker. Do not ask approval for routine intermediate checks. Do not loosen acceptance to hide failures.

Rollback is limited to this task's changes in its isolated branch/worktree: inspect the task diff and revert only its commits/hunks if needed. Never reset/stash another checkout, force-push, uninstall shared Qt, delete user sessions/artifacts or synchronize Lesson 7–8 worktrees. Keep evidence/worktree until human review; no automatic merge/deploy.

## 9. Human Plan review and execution readiness

Approval requested for this precise file scope (including deletion of MANIFEST.md/STATUS.md and the new `evidence.md`), the PR #3-merged precondition, Native sequential implementation, isolated public-package setup/Qt-free tests, the `wo_py`/`wo_node`/`wo_smoke_server` environment, per-run config and cleanup policy, the real-backend Host/Origin test, test-only fake-provider browser harness, scoped Draft PR preparation with linked evidence and a fresh read-only final review. O1–O3 are already resolved and are not re-opened here.

No paid provider call or Agent Eval is proposed. Coding/review uses the existing agent quota; public dependency downloads/local CPU/media/browser work are additional execution time. No dollar estimate or absolute spending cap is asserted.

Runtime-unverified gates: PR #3 merge, fresh venv install/Qt absence, namespace isolation and the bwrap mount profile, offline npm in `wo_node`, collection, migrated behavior, real FFmpeg, actual browser and CI. Main commit must be fetched/revalidated. Exact desktop/web batch edge-case parity remains an assertion-level verification obligation, not a claim of success.

Self-review: scope matches R1–R12/N1–N6; all 139 source methods have an initial destination/retirement map; FakeAuth moves before any mixed-module run (S2); Host/Origin acceptance and rejection run against a real backend process; every wrapped run has its own config dir and controlled cleanup; CLI and safe Qt-free preparation stay; real browser/process/media checks are distinct from fixtures; no expected-value/algorithm changes or skipped coverage are authorized. An incoming agent reads Intent, Spec, this Plan and the mapped source assertions; it must not invent a product decision if a required workflow is missing.

**Assessment:** Plan approved by the owner on 2026-10-13 (`approved`). Execution check on 2026-10-13: PR #3 first observed OPEN (S0 blocked); the owner then merged it (`8b4bb314a5e6ae073050535a99f2000930c286cb`, an ancestor of `origin/main`, with no scoped diff from `a80efa8`). Implementation proceeds from S0. Acceptance remains pending actual evidence.

## Appendix A — Static source hashes

These are SHA-256 hashes of the inspected test files, not runtime results. Recheck at S0; no assertion may disappear unnoticed.

| Baseline file | SHA-256 |
| --- | --- |
| `tests/test_group_batches.py` | `12dfa8c4d98ab31d5f0e27d4df79e806640748c4b2dfa94957021a6b04532d97` |
| `tests/test_last_input_folder.py` | `3158793288456cb444a13d9159c6cad92151aaa297d81c1014432ba93228709e` |
| `tests/test_log_dialog.py` | `bff59ca23e83d756d070c09b94e01363af27c6dfac222a4ca8bfc28f2850a0aa` |
| `tests/test_pipeline_data_flow.py` | `dd06a6743767125051deb6a0f014a124cd988b6b3fb309b9ffb75a513097ba8e` |
| `tests/test_sessions.py` | `c779a8902143dcd06fc637d4d58c6f26a20084cfe8a1d82c592b0004613b3663` |
| `tests/test_settings_dialog.py` | `fb5f837e8e04551881d535db7beaf529f438cf12a11adcfb8e33d72153d225d5` |
| `tests/test_step2_ui.py` | `340f26f0e6806896e0b1d574908c5406ec2efa321ce2916231501eddc492c920` |
| `tests/test_tts_preprocessing.py` | `7e06ff428beb370d8c8e58504b94f3c91789e9dc63c1e95ebcdac39879d425f1` |
| `tests/test_tts_ui.py` | `70b3f654fd00744dbac34fe9f1cb281f4971cd5d905ffd46897063d395b785f3` |
| `tests/test_video_pages.py` | `ecb9f6d6988ec2818630c59f26e967115091b1a35b8a87973a33737b6e651abc` |
| `tests/test_video_preview.py` | `1bd657745ecde340da230430027cc1fde846c71257f20a8e38a7debfcc3240e7` |
| `tests/test_video_ui.py` | `e3d5e941063a1b0c776810cbb0205f706929279a73124a08746e5e47b44bc54f` |
| `tests/test_youtube_title_tags.py` | `43b1a81f861e0aeb663141172a7f1885289dc5a9687e21266d801ef147a72339` |
| `tests/test_youtube_ui.py` | `10b2600a4a9d94c24356ca08378ef847c6edbb88311a04c20e91b777645d8f5e` |

## Appendix B — Complete initial method trace (139 definitions)

Line numbers refer to the inspected baseline. Destination IDs are proposed, not yet implemented/collected. All runtime evidence is Not executed. Original assertion groups must be enumerated in coverage.md and verified under §4 before deleting source tests.

| # | Baseline source/method | Disposition | Exact destination | Assertion handling |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_group_batches.py:48` — `GroupBatchTests.test_step3_active_ui_creates_groups_not_tts` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step3_active_ui_creates_groups_not_tts` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 2 | `tests/test_group_batches.py:65` — `GroupBatchTests.test_step3_numeric_boundary_confirmation_and_unavailable_boundary` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step3_numeric_boundary_confirmation_and_unavailable_boundary` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 3 | `tests/test_group_batches.py:95` — `GroupBatchTests.test_defaults_and_select_all_subset_snapshot` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_defaults_and_select_all_subset_snapshot` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 4 | `tests/test_group_batches.py:116` — `GroupBatchTests.test_group_failure_continues_cancel_stops_future_groups` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_group_failure_continues_cancel_stops_future_groups` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 5 | `tests/test_group_batches.py:133` — `GroupBatchTests.test_tts_incomplete_continues_and_resume_keeps_canonical_files` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_tts_incomplete_continues_and_resume_keeps_canonical_files` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 6 | `tests/test_group_batches.py:176` — `GroupBatchTests.test_zero_audio_partial_merge_rejected_without_dialog` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_zero_audio_partial_merge_rejected_without_dialog` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 7 | `tests/test_group_batches.py:183` — `GroupBatchTests.test_partial_merge_is_explicit_and_records_missing_numbers` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_partial_merge_is_explicit_and_records_missing_numbers` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 8 | `tests/test_group_batches.py:217` — `GroupBatchTests.test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 9 | `tests/test_group_batches.py:250` — `GroupBatchTests.test_damaged_group_does_not_block_entry_or_other_batch_jobs` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_damaged_group_does_not_block_entry_or_other_batch_jobs` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 10 | `tests/test_group_batches.py:266` — `GroupBatchTests.test_step3_can_delete_any_group_and_refresh_later_stages` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step3_can_delete_any_group_and_refresh_later_stages` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 11 | `tests/test_group_batches.py:302` — `GroupBatchTests.test_step4_busy_blocks_image_selection_and_group_deletion` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step4_busy_blocks_image_selection_and_group_deletion` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 12 | `tests/test_group_batches.py:316` — `GroupBatchTests.test_progress_visible_and_busy_blocks_other_stages` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_progress_visible_and_busy_blocks_other_stages` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 13 | `tests/test_group_batches.py:334` — `GroupBatchTests.test_upload_metadata_frozen_individually_completed_skipped` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_upload_metadata_frozen_individually_completed_skipped` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 14 | `tests/test_group_batches.py:366` — `GroupBatchTests.test_auth_failure_pauses_remaining_queue` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_auth_failure_pauses_remaining_queue` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 15 | `tests/test_group_batches.py:382` — `GroupBatchTests.test_paused_batch_shared_edits_affect_only_unstarted_sessions` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_paused_batch_shared_edits_affect_only_unstarted_sessions` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 16 | `tests/test_group_batches.py:409` — `GroupBatchTests.test_sequential_upload_engine_continues_after_group_failure` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_sequential_upload_engine_continues_after_group_failure` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 17 | `tests/test_group_batches.py:436` — `GroupBatchTests.test_video_current_output_skip_and_sequential_subset` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_video_current_output_skip_and_sequential_subset` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 18 | `tests/test_group_batches.py:456` — `GroupBatchTests.test_video_refuses_to_start_without_both_page_inputs` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_video_refuses_to_start_without_both_page_inputs` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 19 | `tests/test_group_batches.py:477` — `GroupBatchTests.test_video_process_group_refuses_without_inputs_and_records_them_after` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_video_process_group_refuses_without_inputs_and_records_them_after` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 20 | `tests/test_group_batches.py:508` — `VideoMetadataUpdateTests.test_metadata_update_preserves_unrelated_fields_and_frozen_insertion` | Move unchanged | `tests/test_youtube.py::VideoMetadataUpdateTests::test_metadata_update_preserves_unrelated_fields_and_frozen_insertion` | Preserve metadata/atomic-write assertions; fake transport only. |
| 21 | `tests/test_group_batches.py:523` — `VideoMetadataUpdateTests.test_metadata_update_can_clear_ai_disclosure` | Move unchanged | `tests/test_youtube.py::VideoMetadataUpdateTests::test_metadata_update_can_clear_ai_disclosure` | Preserve metadata/atomic-write assertions; fake transport only. |
| 22 | `tests/test_group_batches.py:532` — `VideoMetadataUpdateTests.test_api_failure_keeps_local_record_unchanged` | Move unchanged | `tests/test_youtube.py::VideoMetadataUpdateTests::test_api_failure_keeps_local_record_unchanged` | Preserve metadata/atomic-write assertions; fake transport only. |
| 23 | `tests/test_last_input_folder.py:24` — `LastInputFolderTests.test_setting_round_trip_and_invalid_folder_fallback` | Retain | `tests/test_last_input_folder.py::LastInputFolderTests::test_setting_round_trip_and_invalid_folder_fallback` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 24 | `tests/test_last_input_folder.py:37` — `LastInputFolderTests.test_output_folder_always_follows_the_input` | Retain | `tests/test_last_input_folder.py::LastInputFolderTests::test_output_folder_always_follows_the_input` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 25 | `tests/test_last_input_folder.py:56` — `LastInputFolderTests.test_file_picker_starts_at_and_updates_last_folder` | Retire desktop only | — | O1: native QFileDialog interaction; retain Settings/input-relative output and real HTTP import coverage. |
| 26 | `tests/test_log_dialog.py:26` — `LogDialogTests.test_shared_log_keeps_every_step_line_across_closing` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_job_logs_remain_available_across_reads` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 27 | `tests/test_log_dialog.py:51` — `LogDialogTests.test_opening_the_log_leaves_the_active_step_and_busy_state_untouched` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_reading_job_logs_preserves_busy_state` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 28 | `tests/test_log_dialog.py:65` — `LogDialogTests.test_log_button_and_shortcut_toggle_the_window` | Retire desktop only | — | O1: Qt window/shortcut interaction only; job log visibility retained. |
| 29 | `tests/test_log_dialog.py:95` — `LogDialogTests.test_max_log_lines_bounds_the_shared_buffer` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_max_log_lines_bounds_the_shared_buffer` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 30 | `tests/test_log_dialog.py:107` — `LogDialogTests.test_closing_the_main_window_hides_the_log_window` | Retire desktop only | — | O1: window lifecycle only; persisted session and job log recovery retained. |
| 31 | `tests/test_log_dialog.py:119` — `LogDialogTests.test_copy_all_and_clear_use_the_shared_log` | Retire desktop only | — | O1: clipboard/Qt log controls; preserve log content/order/bounds in migrated cases. |
| 32 | `tests/test_pipeline_data_flow.py:55` — `PipelineDataFlowTests.test_step2_consumes_exact_normalized_text_without_han_gate` | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_step2_consumes_exact_normalized_text_without_han_gate` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 33 | `tests/test_pipeline_data_flow.py:70` — `PipelineDataFlowTests.test_original_is_fallback_before_step1` | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_original_is_fallback_before_step1` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 34 | `tests/test_pipeline_data_flow.py:79` — `PipelineDataFlowTests.test_successful_step1_without_output_fails_closed` | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_successful_step1_without_output_fails_closed` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 35 | `tests/test_pipeline_data_flow.py:87` — `PipelineDataFlowTests.test_step1_edit_replaces_grouping_source_and_invalidates_chunks` | Retain | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_step1_edit_replaces_grouping_source_and_invalidates_chunks` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 36 | `tests/test_pipeline_data_flow.py:98` — `PipelineDataFlowTests.test_main_window_allows_chinese_text_in_step2` | Migrate | `tests/test_pipeline_data_flow.py::PipelineDataFlowTests::test_service_allows_chinese_text_in_step2` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 37 | `tests/test_sessions.py:44` — `SessionTests.test_roundtrip_retains_text_types_and_validated_media` | Retain | `tests/test_sessions.py::SessionTests::test_roundtrip_retains_text_types_and_validated_media` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 38 | `tests/test_sessions.py:60` — `SessionTests.test_atomic_failure_preserves_previous_session` | Retain | `tests/test_sessions.py::SessionTests::test_atomic_failure_preserves_previous_session` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 39 | `tests/test_sessions.py:72` — `SessionTests.test_corrupt_sessions_and_traversal_are_rejected` | Retain | `tests/test_sessions.py::SessionTests::test_corrupt_sessions_and_traversal_are_rejected` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 40 | `tests/test_sessions.py:87` — `SessionTests.test_group_snapshot_recovers_newer_completed_job_state` | Retain | `tests/test_sessions.py::SessionTests::test_group_snapshot_recovers_newer_completed_job_state` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 41 | `tests/test_sessions.py:97` — `SessionTests.test_close_and_reopen_at_step4_without_repeating_previous_stages` | Migrate | `tests/test_sessions.py::SessionTests::test_close_and_reopen_at_step4_without_repeating_previous_stages` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 42 | `tests/test_sessions.py:125` — `SessionTests.test_multiple_sessions_restore_edited_text_and_group_selection` | Migrate | `tests/test_sessions.py::SessionTests::test_multiple_sessions_restore_edited_text_and_group_selection` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 43 | `tests/test_sessions.py:151` — `SessionTests.test_missing_media_keeps_text_and_reports_missing_files` | Migrate | `tests/test_sessions.py::SessionTests::test_missing_media_keeps_text_and_reports_missing_files` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 44 | `tests/test_sessions.py:163` — `SessionTests.test_busy_session_cannot_be_replaced` | Migrate | `tests/test_sessions.py::SessionTests::test_busy_session_cannot_be_replaced` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 45 | `tests/test_sessions.py:170` — `SessionTests.test_failed_save_prevents_close_and_retains_document` | Migrate | `tests/test_sessions.py::SessionTests::test_failed_save_retains_document_and_previous_session` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 46 | `tests/test_sessions.py:178` — `SessionTests.test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id` | Migrate | `tests/test_sessions.py::SessionTests::test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 47 | `tests/test_sessions.py:193` — `SessionTests.test_reopening_older_session_keeps_latest_uploaded_story_tags` | Migrate | `tests/test_sessions.py::SessionTests::test_reopening_older_session_keeps_latest_uploaded_story_tags` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 48 | `tests/test_sessions.py:203` — `SessionTests.test_reopening_youtube_page_preserves_unuploaded_tag_draft` | Migrate | `tests/test_sessions.py::SessionTests::test_reopening_youtube_page_preserves_unuploaded_tag_draft` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 49 | `tests/test_settings_dialog.py:25` — `SettingsDialogTests.test_legacy_translation_settings_are_ignored_safely` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_legacy_translation_settings_are_ignored_safely` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 50 | `tests/test_settings_dialog.py:38` — `SettingsDialogTests.test_collects_changed_values` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_collects_changed_values` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 51 | `tests/test_settings_dialog.py:60` — `SettingsDialogTests.test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 52 | `tests/test_settings_dialog.py:71` — `SettingsDialogTests.test_step3_title_history_can_be_remembered_and_removed` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step3_title_history_can_be_remembered_and_removed` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 53 | `tests/test_settings_dialog.py:88` — `SettingsDialogTests.test_runtime_ui_settings_are_applied` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_runtime_ui_settings_are_applied` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 54 | `tests/test_settings_dialog.py:98` — `SettingsDialogTests.test_log_window_is_detached_and_resizable` | Retire desktop only | — | O1: Qt window geometry only. |
| 55 | `tests/test_settings_dialog.py:118` — `SettingsDialogTests.test_cleaning_settings_affect_step3` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_cleaning_settings_affect_step3` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 56 | `tests/test_step2_ui.py:40` — `Step2UiTests.test_step2_is_grouping_and_preserves_chinese_text` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step2_is_grouping_and_preserves_chinese_text` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 57 | `tests/test_step2_ui.py:68` — `Step2UiTests.test_copy_all_copies_complete_step2_output` | Retire desktop only | — | O1: clipboard interaction; complete grouping payload retained by Step2/business and data-flow tests. |
| 58 | `tests/test_step2_ui.py:78` — `Step2UiTests.test_copy_all_covers_diagnostics_group_panel_dialog_and_youtube` | Retire desktop only | — | O1: clipboard/widget routing; diagnostics, failed-chunk detail and upload URL/state retained in their business cases. |
| 59 | `tests/test_tts_preprocessing.py:59` — `PreprocessingTests.test_required_examples_and_idempotence` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_required_examples_and_idempotence` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 60 | `tests/test_tts_preprocessing.py:68` — `PreprocessingTests.test_full_required_example_and_adjacent_url` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_full_required_example_and_adjacent_url` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 61 | `tests/test_tts_preprocessing.py:76` — `PreprocessingTests.test_double_quote_fallback_matches_step1_policy` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_double_quote_fallback_matches_step1_policy` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 62 | `tests/test_tts_preprocessing.py:94` — `PreprocessingTests.test_protected_structures_and_semantics` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_protected_structures_and_semantics` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 63 | `tests/test_tts_preprocessing.py:107` — `PreprocessingTests.test_unicode_and_entities` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_unicode_and_entities` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 64 | `tests/test_tts_preprocessing.py:120` — `PreprocessingTests.test_valid_vietnamese_diacritics_are_not_mojibake` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_valid_vietnamese_diacritics_are_not_mojibake` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 65 | `tests/test_tts_preprocessing.py:129` — `PreprocessingTests.test_mojibake_diagnostics_are_aggregated_and_preserved` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_mojibake_diagnostics_are_aggregated_and_preserved` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 66 | `tests/test_tts_preprocessing.py:144` — `PreprocessingTests.test_chapter_preparation_keeps_chapter_context_in_diagnostics` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_chapter_preparation_keeps_chapter_context_in_diagnostics` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 67 | `tests/test_tts_preprocessing.py:153` — `PreprocessingTests.test_policies_and_custom_rules` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_policies_and_custom_rules` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 68 | `tests/test_tts_preprocessing.py:171` — `PreprocessingTests.test_technical_json_emoji_and_comments` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_technical_json_emoji_and_comments` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 69 | `tests/test_tts_preprocessing.py:182` — `PreprocessingTests.test_sentence_per_line` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_sentence_per_line` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 70 | `tests/test_tts_preprocessing.py:189` — `PreprocessingTests.test_invariants_seeded_mixed_input` | Retain | `tests/test_tts_preprocessing.py::PreprocessingTests::test_invariants_seeded_mixed_input` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 71 | `tests/test_tts_preprocessing.py:206` — `BoundaryTests.test_technical_boundaries` | Retain | `tests/test_tts_preprocessing.py::BoundaryTests::test_technical_boundaries` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 72 | `tests/test_tts_preprocessing.py:213` — `BoundaryTests.test_lossless_chunking_quotes_numbers_and_empty` | Retain | `tests/test_tts_preprocessing.py::BoundaryTests::test_lossless_chunking_quotes_numbers_and_empty` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 73 | `tests/test_tts_preprocessing.py:225` — `BoundaryTests.test_oversized_protected_heading_and_combining` | Retain | `tests/test_tts_preprocessing.py::BoundaryTests::test_oversized_protected_heading_and_combining` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 74 | `tests/test_tts_preprocessing.py:240` — `SentencePackingTests.test_pack_sentences_not_short_paragraphs` | Retain | `tests/test_tts_preprocessing.py::SentencePackingTests::test_pack_sentences_not_short_paragraphs` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 75 | `tests/test_tts_preprocessing.py:249` — `SentencePackingTests.test_paragraph_break_inside_sentence_does_not_cut_short_sentence` | Retain | `tests/test_tts_preprocessing.py::SentencePackingTests::test_paragraph_break_inside_sentence_does_not_cut_short_sentence` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 76 | `tests/test_tts_preprocessing.py:256` — `SentencePackingTests.test_oversized_sentence_uses_words_before_hard_slicing` | Retain | `tests/test_tts_preprocessing.py::SentencePackingTests::test_oversized_sentence_uses_words_before_hard_slicing` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 77 | `tests/test_tts_preprocessing.py:275` — `TtsIntegrationTests.test_fixed_700_target_ignores_saved_legacy_sizes` | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_fixed_700_target_ignores_saved_legacy_sizes` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 78 | `tests/test_tts_preprocessing.py:285` — `TtsIntegrationTests.test_group_tts_plan_propagates_chapter_mojibake_diagnostics` | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_group_tts_plan_propagates_chapter_mojibake_diagnostics` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 79 | `tests/test_tts_preprocessing.py:297` — `TtsIntegrationTests.test_preprocessing_before_chunking_and_resume` | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_preprocessing_before_chunking_and_resume` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 80 | `tests/test_tts_preprocessing.py:328` — `TtsIntegrationTests.test_old_cache_overrides_cancel_and_empty` | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_old_cache_overrides_cancel_and_empty` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 81 | `tests/test_tts_preprocessing.py:352` — `TtsIntegrationTests.test_settings_roundtrip_and_custom_clean` | Retain | `tests/test_tts_preprocessing.py::TtsIntegrationTests::test_settings_roundtrip_and_custom_clean` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 82 | `tests/test_tts_preprocessing.py:374` — `LegacyAndUiTests.test_legacy_bundle_client_and_old_provenance` | Migrate | `tests/test_tts_preprocessing.py::HeadlessLegacyTests::test_legacy_bundle_client_and_old_provenance` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 83 | `tests/test_tts_preprocessing.py:424` — `LegacyAndUiTests.test_large_preparation_worker_cancel_and_snapshot` | Migrate | `tests/test_tts_preprocessing.py::HeadlessLegacyTests::test_large_preparation_worker_cancel_and_snapshot` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 84 | `tests/test_tts_preprocessing.py:455` — `LegacyAndUiTests.test_config_ui_and_downstream_invalidation` | Migrate | `tests/test_tts_preprocessing.py::HeadlessLegacyTests::test_config_ui_and_downstream_invalidation` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 85 | `tests/test_tts_ui.py:23` — `TtsUiTests.test_zero_successes_show_root_error_without_merge_dialog` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_zero_successes_show_root_error_without_merge_dialog` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 86 | `tests/test_tts_ui.py:43` — `TtsUiTests.test_failed_chunk_dialog_shows_original_and_failed_part_text` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_failed_chunk_dialog_shows_original_and_failed_part_text` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 87 | `tests/test_tts_ui.py:67` — `TtsUiTests.test_worker_bridges_processor_progress_to_qt_signal` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_worker_progress_reaches_http_job_snapshot` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 88 | `tests/test_video_pages.py:54` — `VideoPageTests.test_exact_text_and_measured_timeline` | Retain | `tests/test_video_pages.py::VideoPageTests::test_exact_text_and_measured_timeline` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 89 | `tests/test_video_pages.py:68` — `VideoPageTests.test_selective_cache_and_audio_only_updates` | Retain | `tests/test_video_pages.py::VideoPageTests::test_selective_cache_and_audio_only_updates` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 90 | `tests/test_video_pages.py:96` — `VideoPageTests.test_visual_changes_and_corrupted_cache_repaint` | Retain | `tests/test_video_pages.py::VideoPageTests::test_visual_changes_and_corrupted_cache_repaint` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 91 | `tests/test_video_pages.py:111` — `VideoPageTests.test_each_page_names_only_its_own_chapter` | Retain | `tests/test_video_pages.py::VideoPageTests::test_each_page_names_only_its_own_chapter` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 92 | `tests/test_video_pages.py:137` — `VideoPageTests.test_cjk_brackets_render_visible_ink_on_the_page` | Retain | `tests/test_video_pages.py::VideoPageTests::test_cjk_brackets_render_visible_ink_on_the_page` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 93 | `tests/test_video_pages.py:177` — `VideoPageTests.test_latin_and_vietnamese_advances_are_unchanged_by_the_fallback` | Retain | `tests/test_video_pages.py::VideoPageTests::test_latin_and_vietnamese_advances_are_unchanged_by_the_fallback` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 94 | `tests/test_video_pages.py:195` — `VideoPageTests.test_invalid_audio_or_request_provenance_is_rejected` | Retain | `tests/test_video_pages.py::VideoPageTests::test_invalid_audio_or_request_provenance_is_rejected` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 95 | `tests/test_video_pages.py:212` — `VideoPageTests.test_mismatched_audio_duration_and_cancellation_fail_before_publication` | Retain | `tests/test_video_pages.py::VideoPageTests::test_mismatched_audio_duration_and_cancellation_fail_before_publication` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 96 | `tests/test_video_pages.py:223` — `VideoPageTests.test_input_change_during_page_generation_keeps_old_timeline` | Retain | `tests/test_video_pages.py::VideoPageTests::test_input_change_during_page_generation_keeps_old_timeline` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 97 | `tests/test_video_pages.py:234` — `VideoPageTests.test_readable_layout_bounds_and_line_budget` | Retain | `tests/test_video_pages.py::VideoPageTests::test_readable_layout_bounds_and_line_budget` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 98 | `tests/test_video_pages.py:286` — `VideoPageTests.test_paragraph_breaks_compress_before_a_page_fails` | Retain | `tests/test_video_pages.py::VideoPageTests::test_paragraph_breaks_compress_before_a_page_fails` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 99 | `tests/test_video_pages.py:306` — `VideoPageTests.test_reclaimed_bottom_margin_absorbs_the_reported_three_pixel_overflow` | Retain | `tests/test_video_pages.py::VideoPageTests::test_reclaimed_bottom_margin_absorbs_the_reported_three_pixel_overflow` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 100 | `tests/test_video_pages.py:323` — `VideoPageTests.test_gap_ladder_always_keeps_the_requested_gap_first` | Retain | `tests/test_video_pages.py::VideoPageTests::test_gap_ladder_always_keeps_the_requested_gap_first` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 101 | `tests/test_video_pages.py:329` — `VideoPageTests.test_nonfinite_audio_metadata_rejected` | Retain | `tests/test_video_pages.py::VideoPageTests::test_nonfinite_audio_metadata_rejected` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 102 | `tests/test_video_pages.py:338` — `VideoPageTests.test_mp3_playable_duration_uses_exact_packet_ticks_and_padding` | Retain | `tests/test_video_pages.py::VideoPageTests::test_mp3_playable_duration_uses_exact_packet_ticks_and_padding` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 103 | `tests/test_video_pages.py:353` — `RealVfrTests.test_real_mp3_merge_and_fractional_static_pages` | Migrate | `tests/test_video_pages.py::RealVfrTests::test_real_mp3_merge_and_fractional_static_pages` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 104 | `tests/test_video_pages.py:447` — `RealVfrTests.test_single_page_holds_to_the_end_at_44100hz` | Retain | `tests/test_video_pages.py::RealVfrTests::test_single_page_holds_to_the_end_at_44100hz` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 105 | `tests/test_video_preview.py:20` — `SidePanelGeometryTests.test_slots_are_fixed_305_squares_flush_in_the_frame_corners` | Retain | `tests/test_video_preview.py::SidePanelGeometryTests::test_slots_are_fixed_305_squares_flush_in_the_frame_corners` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 106 | `tests/test_video_preview.py:76` — `SidePanelRenderTests.test_cover_and_qr_keep_their_pixels_without_background` | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_cover_and_qr_keep_their_pixels_without_background` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 107 | `tests/test_video_preview.py:96` — `SidePanelRenderTests.test_wide_cover_is_letterboxed_instead_of_cropped` | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_wide_cover_is_letterboxed_instead_of_cropped` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 108 | `tests/test_video_preview.py:110` — `SidePanelRenderTests.test_transparent_qr_has_no_card_just_composited_pixels` | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_transparent_qr_has_no_card_just_composited_pixels` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 109 | `tests/test_video_preview.py:123` — `SidePanelRenderTests.test_pictures_never_intersect_the_text_column` | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_pictures_never_intersect_the_text_column` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 110 | `tests/test_video_preview.py:135` — `SidePanelRenderTests.test_text_layout_is_identical_with_or_without_pictures` | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_text_layout_is_identical_with_or_without_pictures` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 111 | `tests/test_video_preview.py:142` — `SidePanelRenderTests.test_missing_picture_is_reported_instead_of_silently_skipped` | Retain | `tests/test_video_preview.py::SidePanelRenderTests::test_missing_picture_is_reported_instead_of_silently_skipped` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 112 | `tests/test_video_preview.py:170` — `SidePanelTimelineTests.test_both_picture_inputs_are_required_before_any_page` | Retain | `tests/test_video_preview.py::SidePanelTimelineTests::test_both_picture_inputs_are_required_before_any_page` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 113 | `tests/test_video_preview.py:184` — `SidePanelTimelineTests.test_changing_a_picture_repaints_and_updates_the_source_fingerprint` | Retain | `tests/test_video_preview.py::SidePanelTimelineTests::test_changing_a_picture_repaints_and_updates_the_source_fingerprint` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 114 | `tests/test_video_preview.py:220` — `VideoPreviewTests.test_build_page_preview_renders_a_real_full_frame` | Migrate | `tests/test_video_preview.py::WebPreviewRegressionTests::test_prepared_preview_renders_real_full_frame` | Prepared narration/audio and both pictures through real preview; preserve full-frame dimensions/pixels. |
| 115 | `tests/test_video_preview.py:229` — `VideoPreviewTests.test_build_page_preview_falls_back_to_sample_text` | Retire desktop only | — | O1: desktop sample/fallback preview explicitly retired; AT9 rejects missing prepared inputs. |
| 116 | `tests/test_video_preview.py:236` — `VideoPreviewTests.test_first_page_text_uses_the_plan_or_the_sample` | Retire desktop only | — | O1: obsolete desktop helper/sample choice; prepared effective narration/provenance covered by AT9. |
| 117 | `tests/test_video_preview.py:239` — `VideoPreviewTests.test_dialog_shows_the_whole_rendered_frame` | Retire desktop only | — | O1: Qt dialog presentation; actual full-frame rendering retained. |
| 118 | `tests/test_video_ui.py:57` — `VideoUiTests.test_step4_uses_current_step3_paths_without_upload_controls` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step4_uses_current_step3_paths_without_upload_controls` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 119 | `tests/test_video_ui.py:75` — `VideoUiTests.test_step5_progress_is_visible_and_video_state_invalidates` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_step5_progress_is_visible_and_video_state_invalidates` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 120 | `tests/test_video_ui.py:102` — `VideoUiTests.test_create_video_is_blocked_until_both_page_images_are_added` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_create_video_is_blocked_until_both_page_images_are_added` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 121 | `tests/test_video_ui.py:124` — `VideoUiTests.test_cancel_during_async_page_preparation_preserves_old_video` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_cancel_during_async_page_preparation_preserves_old_video` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 122 | `tests/test_youtube_title_tags.py:51` — `UploadedTitleTagTests.test_completed_upload_saves_story_tags_and_next_video_loads_them` | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_completed_upload_saves_story_tags_and_next_video_loads_them` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 123 | `tests/test_youtube_title_tags.py:75` — `UploadedTitleTagTests.test_failure_does_not_save_draft_tags` | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_failure_does_not_save_draft_tags` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 124 | `tests/test_youtube_title_tags.py:91` — `UploadedTitleTagTests.test_existing_completed_upload_is_imported_when_its_story_is_opened` | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_existing_completed_upload_is_imported_when_its_story_is_opened` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 125 | `tests/test_youtube_title_tags.py:107` — `UploadedTitleTagTests.test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title` | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 126 | `tests/test_youtube_title_tags.py:122` — `UploadedTitleTagTests.test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags` | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 127 | `tests/test_youtube_title_tags.py:152` — `UploadedTitleTagTests.test_group_upload_uses_story_tags_and_records_confirmed_result` | Migrate | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_group_upload_uses_story_tags_and_records_confirmed_result` | Real shared/service/media behavior per §4; preserve business assertions; Qt interaction subassertions retire. |
| 128 | `tests/test_youtube_title_tags.py:179` — `UploadedTitleTagTests.test_unrelated_stories_keep_separate_tags_and_bad_config_is_ignored` | Retain | `tests/test_youtube_title_tags.py::UploadedTitleTagTests::test_unrelated_stories_keep_separate_tags_and_bad_config_is_ignored` | Keep existing non-widget assertions; remove Qt setup/imports only. |
| 129 | `tests/test_youtube_ui.py:79` — `YouTubeUiTests.test_connect_uses_changed_oauth_settings_without_reentering_tab` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_connect_uses_changed_oauth_settings_without_reentering_tab` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 130 | `tests/test_youtube_ui.py:90` — `YouTubeUiTests.test_configured_oauth_without_saved_login_explains_sign_in` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_configured_oauth_without_saved_login_explains_sign_in` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 131 | `tests/test_youtube_ui.py:99` — `YouTubeUiTests.test_group_connection_error_visible_beside_account` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_group_connection_error_visible_beside_account` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 132 | `tests/test_youtube_ui.py:114` — `YouTubeUiTests.test_connect_without_config_displays_error_dialog` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_connect_without_config_displays_error_dialog` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 133 | `tests/test_youtube_ui.py:122` — `YouTubeUiTests.test_continue_and_direct_navigation_share_automatic_inputs_and_metadata` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_continue_and_direct_navigation_share_automatic_inputs_and_metadata` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 134 | `tests/test_youtube_ui.py:143` — `YouTubeUiTests.test_progress_completion_copy_url_and_duplicate_confirmation` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_progress_completion_copy_url_and_duplicate_confirmation` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 135 | `tests/test_youtube_ui.py:173` — `YouTubeUiTests.test_ai_checkbox_uploads_both_values_and_restores_saved_choice` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_ai_checkbox_uploads_both_values_and_restores_saved_choice` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 136 | `tests/test_youtube_ui.py:190` — `YouTubeUiTests.test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 137 | `tests/test_youtube_ui.py:206` — `YouTubeUiTests.test_bad_metadata_never_starts_worker_and_schedule_requires_private` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_bad_metadata_never_starts_worker_and_schedule_requires_private` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 138 | `tests/test_youtube_ui.py:220` — `YouTubeUiTests.test_standalone_resume_preserves_saved_metadata_and_past_schedule` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_standalone_resume_preserves_saved_metadata_and_past_schedule` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |
| 139 | `tests/test_youtube_ui.py:261` — `YouTubeUiTests.test_api_worker_keeps_ui_responsive_and_cancel_saves_session` | Migrate | `tests/test_web_business_regressions.py::BusinessRegressionTests::test_api_worker_keeps_ui_responsive_and_cancel_saves_session` | Real service/job/HTTP assertions per §4; retire widget/signal/clipboard subassertions only. |

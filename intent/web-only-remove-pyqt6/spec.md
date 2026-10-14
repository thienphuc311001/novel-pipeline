# Spec: Remove PyQt6 and use the web application

**Project:** novel-pipeline-v2

**Status:** Approved — complete Specification approved by owner on 2026-10-13; implementation pending

**Source:** Approved `intent/web-only-remove-pyqt6/intent.md`. Owner explicitly reaffirmed approval in chat on 2026-10-13; approval is not inferred from the status field.

**Intent SHA-256:** `1288612572425f80a7374dcd6c006dc6b81376e302149aa485ad3eb1ab8cf91b`

**Inspected baseline:** `a80efa8d92bd4f24cf4f66eefc62b20795f53aa8`, branch `codex/lesson9-eval-ci`.

**Evidence status:** Static source/document inspection and AST inventory only. No application, build, test, installation or provider call executed for this Spec. All acceptance tests below are Not executed.

## 1. Purpose, scope and authority

Remove the PyQt6 desktop application and its dependency while retaining the local React/FastAPI application and the internal `python -m pipeline` CLI. Preserve supported processing/data contracts and meaningful regression coverage.

This Spec defines the approved technical design and inventory requirements. The owner explicitly approved O1–O3 with the conditions recorded in §10, then approved the complete Specification with the chat message `approved spec` on 2026-10-13. Spec approval permits creating a Draft Plan; implementation begins after explicit Plan approval under `CLAUDE.md`.

In scope: desktop retirement; Qt-free test migration; minimal installation, usage and guidance corrections; verification without Qt. Out of scope: core algorithm changes, new web features, public/multi-user hosting, account/data migration, Eval changes, Orchestrator work, CI/CD expansion, automatic merge or deployment.

The current `CLAUDE.md:77`/`INSTALL.md:64,94–97` policy retains desktop until real provider parity is verified. Approved O2 replaces that removal gate with offline regression, real local FFmpeg integration and browser smoke, conditional on preserving required business functions and valuable coverage from all 14 Qt-related test files. These checks still have to be performed after implementation authorization. Real TTS/YouTube remain unverified; neither this decision nor local fixture results establish external provider parity. Update active guidance during authorized implementation; historical reports and approved prior intent/spec/plan remain historical, not files to rewrite.

## 2. Verified evidence and limits

Paths/lines describe this baseline; recheck at implementation preflight.

| ID | Verified statically | Evidence |
| --- | --- | --- |
| E1 | Desktop boot imports Qt and MainWindow; `ui/` contains ten tracked Python files. | `app.py:7–26`; Git inventory of `ui/` |
| E2 | `requirements-desktop.txt` declares PyQt6; web requirements reference the core file and FastAPI/Uvicorn/multipart. | `requirements-desktop.txt:1–3`, `requirements.txt:1–6`, `requirements-core.txt` |
| E3 | Web transport runs on loopback and validates local Host/Origin. | `backend/__main__.py:7–14`, `backend/app.py:23–59` |
| E4 | HTTP action validation includes import/normalize/edit/group/export, TTS/video/preview and YouTube recovery. The CLI calls the shared service. | `backend/validation.py:50–69`, `pipeline/cli.py:13–49` |
| E5 | Real worker/service tests cover single-flight, partial results, cancellation, upload metadata and render publication boundaries with controlled dependencies. | `tests/test_web_jobs.py:83–225`, `tests/test_headless_media.py:22–190`, `tests/test_headless_service.py:15–117` |
| E6 | SessionStore uses schema version 1; pure storage assertions coexist with MainWindow lifecycle assertions. Web restores several legacy UI-state keys. | `pipeline/sessions.py:79–118`, `tests/test_sessions.py:44–95`, `frontend/src/hooks/use-workspace.ts:60–120` |
| E7 | Desktop preview can render sample text without a TTS plan or fall back on layout failure. Web preview uses validated media and actual narration. | `ui/video_preview.py:25–53`, `pipeline/media_service.py:358–384` |
| E8 | Pure data-flow/settings assertions are inside files importing Qt at module/class setup. Real FFmpeg video tests also contain a Qt session section. | `tests/test_pipeline_data_flow.py:55–107`, `tests/test_last_input_folder.py:24–75`, `tests/test_video_pages.py:348–443` |
| E9 | `test_youtube_title_tags.py` imports FakeAuth from a Qt UI test module; it also contains pure Settings assertions. | `tests/test_youtube_title_tags.py:20,179–187` |
| E10 | Core/media/backend scan found no direct PyQt6 or `ui` imports in the inspected source paths. This is not proof about transitive dependency imports. | Static import search over `backend/`, `pipeline/`, `media/`, `config/`, `chapters/`, `cleaning/`, `chunking/`, `filtering/`, `exporters/` |
| E11 | Google installed-client OAuth, loopback authorization and OS-backed secret storage are independent of GUI retirement. | `media/youtube_auth.py:51–78,109–126,169`, `pipeline/media_service.py:499–504`, `tests/test_youtube_auth.py:71–78` |
| E12 | Existing CI is an Eval workflow with path filters; its success does not establish web/core migration acceptance. | `.github/workflows/agent-eval.yml:3–10` |

No scoped source delta was found between the Intent's `36a1dd7` snapshot and this baseline for app/UI/core/web/tests/requirements/current usage docs. `a80efa8` adds stage continuation in CLAUDE; old Intent line references remain anchored to its stated snapshot.

Not verified: runtime parity, full indirect import graph, installed dependencies, Qt-free collection, browser behavior, provider success, fresh-environment installation and cross-platform results. AST inventory found **14 Qt-related test files and 139 `test_*` definitions**; these are not collected test counts or a target for the post-migration count.

## 3. Functional requirements

| ID | Requirement | Intent |
| --- | --- | --- |
| R1 | Retire `app.py` desktop launch and PyQt6-backed `ui/`; remove the desktop requirements file/declaration from supported installation. No replacement desktop shell or compatibility shim that imports Qt. | Outcome; S1–S2 |
| R2 | Preserve web launch/development entry points, current HTTP contract and frontend build/test scripts. Web remains local-only. | Outcome; constraints; S1 |
| R3 | Supported production code and retained tests must run/collect without PyQt6, Qt display configuration or desktop `ui` imports. Verify direct references and attempted transitive imports. | S1–S2, S4 |
| R4 | Keep CLI parser/commands and shared core interfaces; prove a fixture import→normalize→group→export succeeds offline through the real CLI process. | Owner CLI decision; S3 |
| R5 | For all 14 Qt-related baseline test files, map every affected test method/assertion group to retained coverage, migrated coverage or an explicitly retired desktop interaction before deletion. Preserve required business functions and replace valuable coverage with meaningful assertions against real supported consumers. Unmapped business assertions, lost coverage or an unexecuted required replacement block acceptance. A ledger or unchanged test count alone is insufficient; do not create trivial tests or blanket skips. | Scope; S4; approved O2 conditions |
| R6 | Preserve source/canonical text, supported transformations, grouping order/preamble, artifact/provenance checks and invalidation/resume behavior. No algorithm or data-format changes. | Constraints; S6 |
| R7 | Preserve session schema version 1, supported saved fields and artifact recovery; missing/corrupt media remains visible and invalid. Do not read real sessions or migrate user data. | Constraints; S6 |
| R8 | Preserve controlled failure, cancel, retry/resume, partial batch reporting, safe media publication and explicit partial-merge/duplicate-upload confirmations. UI retirement must not weaken these contracts. | Outcome; S5–S6 |
| R9 | Preserve installed-client OAuth and secure credential storage; exercise YouTube logic with fake accounts/transports. Do not convert OAuth client type, log credentials or trigger uploads automatically. | Constraints; S7 |
| R10 | Preserve story-tag persistence/defaults, settings validation and input-relative output placement, including assertions currently tied to desktop tests. | S4–S6; E8–E9 |
| R11 | Web Preview uses only actual prepared narration/audio, required pictures and valid provenance. Desktop sample/fallback preview is retired under approved O1. Do not add sample narration, fallback content or a pre-TTS preview requirement to the web contract. | Scope; S5; E7; approved O1 |
| R12 | Update active README/INSTALL/USAGE/CLAUDE guidance to web-only plus internal CLI, Qt-free test commands and honest verification limits. AGENTS remains an adapter; historical reports and frozen Eval files stay untouched. | Scope; S7–S8 |

## 4. Non-functional requirements

| ID | Requirement |
| --- | --- |
| N1 — Data/privacy | Preserve all real files/configuration/accounts. No secrets or real novel/session data read or emitted. Temporary config must be selected before importing test packages. |
| N2 — Offline | Automated regression uses fixed/generated fixtures and fake provider transports. Any isolation guard must allow explicitly needed local HTTP/OAuth loopback while denying external calls; prove controls before claiming isolation. No live provider calls by default. |
| N3 — Compatibility | Keep Python 3.11+ and Node 22.12+ requirements, existing web/core contracts and formats. Preserve safe Qt-free helpers based on callers/compatibility, not naming. No new runtime framework. |
| N4 — Evidence | Record interpreter, dependency origins, clean Qt-free environment, source identity, commands/exit codes, collection, failures/skips and validation limits. Missing dependencies/timeouts are ERROR or unverified evidence, not PASS. |
| N5 — Workspace/review | Preserve dirty files and both Lesson 7 worktrees. Implementation uses a separately designated branch/workspace under an approved Plan. Do not copy/stage unrelated untracked files. Review with REVIEW.md and applicable chapter-data-integrity procedures. |
| N6 — Boundaries | No automatic merge/deploy, broad uninstall, global configuration edits, paid Eval, secret provisioning or new CI workflow within this scope. |

## 5. Technical design

### D1 — Retire the desktop boundary

Proposed removal targets: `app.py`, the ten tracked `ui/*.py` files and `requirements-desktop.txt`. Check all callers and test fixtures first. No change is required to normalizer, converter, chunking, TTS, renderer, upload algorithms or CLI command semantics to remove their GUI consumer.

Keep the shared Python Core and `media/tts_preparation.py` with its Qt-free legacy preparation/provenance behavior in this change. Its name is not grounds for deletion. The pure functions inside `ui/video_preview.py` are a separate case: E7 identifies the desktop-only sample/fallback preview contract retired by approved O1. Confirm callers before deletion; do not extract those helpers into core or add web sample preview merely to preserve obsolete tests. Internal CLI, settings, sessions and supported artifacts remain required under O3.

### D2 — Supported data/state flow

```text
Browser React → loopback HTTP/SSE → JobManager → PipelineService
                                               ├─ load/normalize/group/edit/export
                                               ├─ Settings + SessionStore
                                               └─ media actions + cancellation
                                                  → validated artifacts/provenance
                                                  → TTS / FFmpeg / YouTube adapters
Internal CLI ─────────────────────────────────→ PipelineService

Source/canonical text → separate prepared TTS text → chunks/overrides
                     → audio/merge → page timeline/video → upload state
```

Remove Qt worker/signal/widget consumers; retain existing threading/event/subprocess mechanisms used by the headless services. A job fails or is partial/cancelled according to actual worker outcome; removing Qt must not turn that into completion. Shared code reads/writes its existing schemas; no conversion of session files or artifact hashes is introduced.

### D3 — Coverage migration, not blanket deletion

The following inventory is exact at this baseline. Classification is an implementation proposal; the Plan must complete a method/assertion-level ledger for all 14 files before any test is deleted. O2 requires both preservation of required business functions and meaningful retained/replacement coverage, with actual regression evidence before acceptance. Use actual core/service/HTTP consumers for migrated behavior. Fake only providers, clocks/process fixtures or other environment boundaries; do not stub the business method being verified. Desktop-only retirements approved in O1 do not authorize dropping core, data or recovery assertions that share the same test method.

| Affected file(s) | Baseline definitions | Required handling |
| --- | --- | --- |
| `tests/test_pipeline_data_flow.py` | 5 | Retain four document/data-flow cases without Qt; preserve Chinese-body Step 2 behavior through a service/HTTP fixture instead of MainWindow tab inspection. |
| `tests/test_last_input_folder.py` | 3 | Retain two Settings/output-placement cases without Qt. Native QFileDialog start-directory interaction retires under approved O1; browser import durability/safe paths remain covered through HTTP. |
| `tests/test_sessions.py` | 12 | Retain pure SessionStore cases; migrate supported save/open/new, busy/error recovery, draft/tag/settings restoration cases to service/HTTP/frontend state boundaries. QWidget close/startup timing may retire; data and failure semantics may not. |
| `tests/test_tts_preprocessing.py` | 26 | Retain 23 existing non-GUI cases. Split the three LegacyAndUi cases: preserve legacy preparation/provenance, cancellation/source retention and settings-driven invalidation using real core/service workers with fake TTS. Qt control/signal assertions retire. |
| `tests/test_video_pages.py` | 17 | Keep pure page/timeline tests and real local FFmpeg/VFR checks. Replace only the Qt `_VideoRenderSession` section with headless render/fallback/provenance assertions; do not delete its preceding real media validation. |
| `tests/test_video_preview.py` | 13 | Preserve nine geometry/render/timeline cases. Replace preview business coverage with the supported web preview contract using prepared narration/audio. Dialog presentation and desktop sample/fallback helper assertions retire under approved O1; do not introduce sample narration into real media or discard shared rendering/provenance assertions. |
| `tests/test_youtube_title_tags.py` | 7 | Separate pure Settings cases and exercise successful-upload persistence, failed-upload non-persistence, frozen metadata and story isolation through service/fake YouTube boundaries. Remove dependency on a Qt fixture module. |
| `tests/test_group_batches.py` | 22 | Migrate sequential selection, partial/failure/recovery, metadata and persisted job semantics; retire only panel/widget assertions with ledger justification. |
| `tests/test_log_dialog.py` | 6 | Preserve bounded logs/severity/order where used by web jobs. Modeless-window/copy-button rendering is desktop-specific; it does not justify dropping log error visibility. |
| `tests/test_settings_dialog.py` | 7 | Preserve settings validation/persistence and relevant data invalidation through config/HTTP/service; retire Qt form widgets. |
| `tests/test_step2_ui.py` | 3 | Map grouping source/confirmation/output and chunk-edit behavior to shared/web paths; retire Qt tab/control assertions only. |
| `tests/test_tts_ui.py` | 3 | Map preparation/effective text/provenance/worker failure semantics to actual headless consumers; retire Qt dialog/thread UI only. |
| `tests/test_video_ui.py` | 4 | Map video metadata/timeline/encoder fallback and failure publication to headless rendering; retire Qt interaction only. |
| `tests/test_youtube_ui.py` | 11 | Preserve account/metadata/upload-state/retry/security semantics with fake OAuth and uploads; Qt widget bindings retire. Extract reusable fake fixtures to a Qt-free test support location before deleting this module. |

Existing `test_headless_service`, `test_headless_media`, `test_web_api`, `test_web_jobs`, `test_chapter_groups`, `test_youtube_auth`, `test_youtube_pipeline`, `test_tts`, `test_video` and `frontend/tests/pipeline.test.ts` are candidate destinations/evidence. Their presence alone does not prove a deleted assertion is covered. The Plan must name exact destinations and avoid duplicate assertions that add no evidence.

### D4 — Prove the Qt-free runtime

Add a focused `tests/test_web_only_runtime.py` using standard-library process/import instrumentation where practical. Inspect dependency declarations and supported import paths, then use bounded child processes with temporary config and an import blocker for `PyQt6`/retired `ui` to catch attempted imports. Also verify real absence of PyQt6 in an isolated environment, not just a blocker in a machine that has Qt installed.

Exercise real backend startup/health/static serving and real CLI help/fixture processing; capture actual process exit status. Static response fixtures cannot prove the built React application loads. Browser smoke uses built frontend and a generated story, temporary settings/output and fake media providers. Exact commands, timeouts, interpreter/dependency setup and cleanup belong to the Plan.

Dependency installation, if needed later, is confined to an approved disposable environment; never uninstall Qt from the operator's current venv or mutate shared environments. Confirm transitive dependency resolution from the environment used to validate.

### D5 — Regression and acceptance levels

1. **Core/offline:** retained/migrated Python tests, isolated HTTP job tests and frontend tests; provider transports fake, supported behavior real.
2. **Local integration:** real FFmpeg/FFprobe with generated audio/images, CPU fallback and timeline validation; no online TTS/account/upload.
3. **Browser smoke:** import/edit/group/save/reopen, job progress/error/cancel visibility, validated media preview/download and fake-provider upload/recovery where applicable.
4. **External provider parity:** not established by 1–3. Approved O2 accepts those levels as the removal gate only with required business preservation and valuable retained/replacement coverage from all 14 Qt-related files. Live TTS/YouTube are not checked by this gate and remain explicitly unverified; it does not say provider parity passed.

No skip/importorskip blanket, no global test ignore list and no replacement of production workers with success stubs. Check missing FFmpeg, browser/runtime dependencies and network controls before broader regression. Required local integration that cannot run is a gap requiring disposition, not an automatic skip-as-success.

### D6 — Documentation and review

Update `README.md`, `INSTALL.md`, `USAGE.md` and `CLAUDE.md` minimally during implementation: supported web launch, internal CLI, Qt-free installation/testing, removed desktop interactions and acceptance limits. Keep shared business instructions even if they appear under the old desktop section. Preserve Google Desktop app OAuth instructions and secret-store guidance.

Keep AGENTS as the existing adapter; it needs no duplicate rules. Retain `BUILD_PROMPT.md` as historical. Historical reports/previous SDLC files and `evals/**` are not rewritten to erase Qt mentions. Such text is not a runtime dependency violation. Any necessary stale source comment correction must be scoped in the later Plan without algorithm changes.

Run Bugs/Security/Compliance review on the complete deletion/migration diff and evidence ledger. Existing Eval CI may run when CLAUDE changes; it is not web/core test coverage. Do not change or launch paid Eval to make this migration look verified.

## 6. Acceptance tests and reviews — Not executed

| ID | Scenario | Required outcome |
| --- | --- | --- |
| AT1 | Fresh approved isolated runtime, no PyQt6/Qt display variables; resolve web dependencies and import supported code. | Qt absent and not required transitively; no supported Qt/UI imports or desktop entry point. Record dependency evidence. |
| AT2 | Start real backend with built frontend; generated story in temporary config/output. | Health/API and actual browser workspace load through loopback; Host/Origin protections remain effective; no Qt initialization. |
| AT3 | Real CLI help and fixture import→normalize→group→export child process. | Natural success exit, expected ordered text/files/session output; no Qt, provider network or real configuration dependency. |
| AT4 | Collect and run retained/migrated Python tests without Qt; run frontend tests/build. Audit all 14 Qt-related baseline files. | No Qt collection/import errors; required business functions preserved; valuable coverage retained or replaced by meaningful assertions that actually execute against supported consumers. Record results and a ledger destination for every affected business assertion; no unresolved business coverage gaps, blanket skips or count-only substitutes. GUI-only retirements follow approved O1. |
| AT5 | Fixture normalization/edit/group/prepare/overrides and cancellation. | Source/canonical contract, exact supported grouping slices, expected transformation/invalidation, stale-plan/resume rejection and no lost completed artifacts. |
| AT6 | Save/reopen supported schema-v1 session fixtures; corrupt/missing files and failed writes. | Preserve story/settings/drafts/group state and validated media; retain global account configuration; safe atomic failure, traversal rejection and visible missing-media diagnostics. No user-data migration. |
| AT7 | Generated media with real FFmpeg/FFprobe, including fallback/cancellation and picture/timeline validation. | Existing safe publication/provenance/VFR contracts hold; no Qt session. Missing tooling is reported as an acceptance gap. |
| AT8 | Fake OAuth/YouTube/TTS with actual service/job orchestration. | Success and failure/partial outcomes correct; retries/resume and explicit confirmations preserved; story tags persist only on confirmed appropriate results; no credentials leaked or real provider call. |
| AT9 | Actual web preview using prepared fixture narration/audio/pictures; missing/tampered inputs. | Preview derives only from prepared effective narration/audio with current provenance; invalid inputs fail without publishing bad output or substituting sample content. Desktop sample/fallback behavior is retired under approved O1. |
| AT10 | Repeat controlled HTTP/job/CLI/session cases with config/output isolation and bounded cleanup; network controls include negative egress and permitted loopback controls. | No inherited real config/provider use, leaked patches or live test child; record the actual guard's limits rather than claiming an OS sandbox from Python mocks. |
| AR1 | Review all source/dependency/test deletions and coverage ledger. | Only approved removal/migration/docs scope, internal CLI retained, no business coverage silently dropped, no data or algorithm migration. |
| AR2 | Review documentation, Skills/policies and parity statements. | O1/O2/O3 reflected accurately; active instructions Qt-free and web-only; no claim that fixtures establish external provider parity. |
| AR3 | Review before/after evidence and workspace preservation. | Baseline and candidate identities, commands/output, expected RED reasons, GREEN and regression results, failures/skips/unexecuted checks. No unrelated files/worktrees altered. |

A baseline negative test may fail because supported collection/desktop references still require Qt. That is expected only for the pinned removal requirement; a missing unrelated dependency, zero-test collection, timeout or setup failure is not valid RED. Product behavior preservation cases should keep their baseline expectations. The later Plan must distinguish these categories and show real before/after evidence.

## 7. Requirements traceability matrix

| Requirement | Design | Acceptance |
| --- | --- | --- |
| R1 — desktop/dependency retirement | D1, D4, D6 | AT1, AR1–AR2 |
| R2 — supported local web | D2, D4 | AT2, AT4, AR2 |
| R3 — Qt-free imports/collection | D3–D4 | AT1, AT4, AR1 |
| R4 — internal CLI | D2, D4 | AT3, AR1 |
| R5 — coverage preservation | D3, D5 | AT4–AT9, AR1, AR3 |
| R6 — text/provenance/contracts | D2–D3, D5 | AT5, AT7, AT9, AR1 |
| R7 — session compatibility | D2–D3 | AT6, AR1 |
| R8 — failures/cancel/recovery | D2–D3, D5 | AT5–AT8, AT10 |
| R9 — OAuth/secrets | D2–D3, D5–D6 | AT8, AT10, AR2 |
| R10 — tags/settings/output placement | D2–D3 | AT3, AT6, AT8 |
| R11 — supported preview/retirement choice | D1–D3, D5 | AT9, AR1–AR2 |
| R12 — active guidance/limits | D6 | AR2–AR3 |
| N1 — privacy/data isolation | D2, D4–D5 | AT5–AT6, AT8, AT10, AR3 |
| N2 — offline/network | D4–D5 | AT7–AT10 |
| N3 — compatibility/helpers | D1–D4 | AT1, AT3–AT9, AR1 |
| N4 — actual evidence | D4–D6 | AT1–AT10, AR3 |
| N5 — workspace/review | D3, D6 | AR1–AR3 |
| N6 — bounded scope | D1, D6 | AR1–AR3 |

## 8. Intent constraint audit

| Approved constraint | How this Spec addresses it |
| --- | --- |
| Source/canonical text, transformations, provenance/resume preserved. | R6/R8, existing shared services retained, AT5/AT7/AT9; no weakened validators or refreshed hashes to bless changed output. |
| Supported settings/session/artifact formats retained. | R7/R10, schema-v1 synthetic fixtures and AT6; migrations outside scope. |
| Qt-free helpers evaluated by callers/compatibility. | D1 keeps legacy preparation; desktop preview helper retirement is justified by callers plus O1, not naming. |
| Local API and secure credentials preserved. | R2/R9, AT2/AT8; no OAuth type change or plaintext store. |
| Temporary config/output, fake providers, separate live permission. | N1/N2, D4–D5 and AT10; no live authorization inferred from Spec/Plan approval. |
| No blanket skips or false parity claims. | R5, D3 ledger, D5/AT4/AR2; local and external evidence separated. |
| Preserve uncommitted work/worktrees and bounded rollback. | N5/N6, AR3; workspace/rollback commands are later Plan decisions, not performed here. |

## 9. Areas of concern

| ID | Priority | Evidence / concern | Handling and proposed owner |
| --- | --- | --- | --- |
| C1 | P1 validation | E7: desktop sample preview and web prepared-narration preview are different. | Product decision resolved by approved O1. Technical Lead/QA verify the retained web contract with prepared narration/audio and no sample fallback; no extra preview feature is introduced. |
| C2 | P1 before implementation | E1/E8/E9: removing Qt imports or whole tests can lose sessions/provenance/tag/render coverage. | Technical Lead completes method/assertion ledger and fixture graph in Plan; QA verifies destinations and outcomes before deletion acceptance. |
| C3 | P1 acceptance | Existing guidance requires real provider parity; owner approved a conditional replacement removal gate in O2. | Decision resolved; QA still must prove required business preservation, valuable coverage for all 14 files, offline regression, real FFmpeg integration and browser smoke. Update active guidance during authorized implementation; explicitly report real TTS/YouTube unverified. |
| C4 | P1 validation | E10 does not prove Qt-free transitive dependencies or runtime; existing venv may contain Qt/system packages. | Technical Lead validates a disposable Qt-free environment and import controls, without uninstalling shared packages. |
| C5 | P1 validation | Sessions carry legacy UI-state fields and per-job recovery formats. | QA/Technical Lead uses baseline-shaped fixtures plus actual web state restoration; unsupported format needs owner decision, not guessed migration. |
| C6 | P1 validation | Broad suite may use network/keyring/FFmpeg/loopback and has environment-dependent skips. | QA preflights dependencies and network controls; required gaps are surfaced. No test run authorized during this Spec stage. |
| C7 | P2 | E12: Eval-only CI is not web/core CI; frozen Eval baselines can legitimately retain historical desktop files. | Report CI coverage limits; do not change Eval or add CI within this Spec. New workflow is a separate approval if requested. |
| C8 | P2 | Intent line references predate the new CLAUDE section; old reports/BUILD_PROMPT can conflict with current architecture. | Preserve approved historical content, use this baseline evidence/current owner decisions; docs owner fixes only active guidance. |
| C9 | P1 at handoff | Intent and REVIEW are currently untracked; other untracked agent file is unrelated. | Carry exact approved inputs into designated implementation workspace after authorization; commit only scoped files. No reset/stash or edits to Lesson 7 worktrees. |

## 10. Approved owner decisions and conditions

**Approval record:** On 2026-10-13, the owner explicitly approved O1–O3 in chat with the conditions below and requested this Spec be checked/updated to match. After that update, the owner approved the complete Specification with `approved spec`. The decisions and complete Specification are Approved; runtime acceptance is not implied.

| ID | Approved decision and mandatory conditions | Limits |
| --- | --- | --- |
| O1 — Product parity | Web Preview uses only prepared narration/audio; PyQt6 sample/fallback preview need not be retained. Preserve required shared/web business workflows and data contracts; retire desktop widgets/shortcuts/native picker behavior. No new web features. | Required business functions are not silently dropped. A newly discovered required workflow gap needs disposition before removal. |
| O2 — Removal evidence | Offline/fake-provider regression, real local FFmpeg integration and browser smoke are the removal gate. Mandatory: preserve required business functions and retain/replace valuable coverage from all 14 Qt-related test files, supported by actual regression results and a traceability ledger. Real TTS/YouTube remain explicitly unverified. | Replaces the old desktop-retention condition for this removal only and permits later active-guidance correction. It does not grant access to real accounts or live provider calls; partial or missing required evidence is not acceptance PASS. |
| O3 — Compatibility/platform acceptance | Retain internal CLI, shared Python Core, settings, sessions and supported artifacts, including current schema-v1 compatibility and existing formats. Perform initial runtime acceptance on Linux using the existing Python 3.11+/Node 22.12+ requirements. | Do not claim Windows/macOS PASS or remove their support automatically. No user-data migration or expanded platform-specific change is authorized. |

Technical inventory and migration procedure in D1–D6 are part of the approved Specification. O1–O3 are resolved by the owner's explicit decision approval above, not by the Intent status field. Requirements R5/R11, designs D1/D3/D5 and acceptance AT4/AT9 incorporate the conditions; O3 is reflected in R2/R4/R6/R7/R10 and AT2/AT3/AT5/AT6.

## 11. Stage completion and handoff

This Specification has been checked against Intent scope, constraints and S1–S8: S1→AT1/AT2; S2→AT1/AR1/AR2; S3→AT3; S4→AT4/AR1; S5→AT5/AT7–AT9; S6→AT5/AT6/AT7/AT9; S7→AR2; S8→AR3.

**Assessment:** Approved for planning. O1–O3 and the complete Specification are Approved; runtime validation gaps remain explicit. No implementation or acceptance PASS is claimed. Source, tests, dependencies and guidance are unchanged by this approval record.

Next stage: create a Draft `plan.md`, complete precise file/coverage/environment/command/rollback choices, and validate that Plan against this approved Spec. Stop at Plan human review; do not implement before Plan approval.

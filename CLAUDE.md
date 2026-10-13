# Project Guidance

`CLAUDE.md` is the shared project rule source. `AGENTS.md` is the Codex adapter.

## Context

- Shared Python core: `pipeline/`, `chapters/`, `cleaning/`, `chunking/`, `filtering/`, `media/`, `config/`. Keep CLI/HTTP core independent of Qt.
- `backend/` provides local FastAPI; `frontend/` uses React/Vite. `ui/` and `app.py` retain the optional PyQt6 interface.
- Read `README.md` and `INSTALL.md` for architecture/setup; for UI work, read `design-system/novel-pipeline/MASTER.md`.

## Working Rules

- Follow the current task and applicable approved intent/spec/plan. Explicit user approval authorizes the stage transitions below; a Markdown status field alone does not authorize execution.
- Inspect Git status first. Preserve uncommitted changes; do not reset, stash, overwrite or commit unrelated work.
- Preserve existing interfaces and data formats unless the task authorizes changes. Follow neighboring conventions; frontend uses strict TypeScript and semantic design tokens.
- Treat `BUILD_PROMPT.md` as historical: flag conflicts with current requirements/code rather than adopting its outdated platform restrictions.

## AI-Native SDLC — Automatic Stage Continuation

Follow the project's Intent → Spec → Plan → Implementation
→ Testing → PR Review workflow.

### Automatic transitions

When the user explicitly approves a stage:

1. Intent Approved:
   - Update intent.md to Approved.
   - Immediately create spec.md as Draft.
   - Validate Spec against the approved Intent.
   - Stop only when Spec is ready for human review.

2. Spec Approved:
   - Update spec.md to Approved.
   - Immediately create plan.md as Draft.
   - Validate Plan against the approved Spec.
   - Stop only when Plan is ready for human review.

3. Plan Approved:
   - Update plan.md to Approved.
   - Execute implementation within the approved scope.
   - Run relevant tests and fix failures.
   - Perform code review and prepare a Pull Request.
   - Stop for final human review and merge decision.

### Continuation rules

- Approval is permission to proceed to the next stage.
- Do not stop immediately after updating document status.
- Do not ask the user to say "continue" or repeat instructions.
- Do not request approval for routine intermediate steps.
- Never approve a stage on behalf of the user.
- Never infer approval solely from a Markdown status field.
- Preserve all existing uncommitted changes.
- Pause only for genuine blockers, scope changes,
  missing permissions, or required human decisions.
- Never auto-merge or deploy.
- If execution is interrupted, report the unfinished stage.

## Commands

Run from repository root with the environment prepared per `INSTALL.md` (Python 3.11+, Node 22.12+). **All commands below are source-verified but runtime-unverified when this guide was authored.** Obtain fresh results for the current checkout.

| Purpose | Command | Source |
| --- | --- | --- |
| Development | `npm run dev` | root `package.json`; `INSTALL.md` |
| Frontend build | `npm --prefix frontend run build` | `frontend/package.json`; `INSTALL.md` |
| Frontend tests | `npm --prefix frontend run test` | `frontend/package.json` |
| Typecheck only | `npm --prefix frontend run typecheck` | `frontend/package.json` |
| Python suite (POSIX shell) | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | `INSTALL.md` |

## Safety

- Do not read or expose `.env`, secrets, tokens, API keys or credential-file contents.
- Before importing tests, select a fresh temporary `NOVEL_PIPELINE_CONFIG_DIR`; never inherit an override pointing at real user configuration.
- TTS processing must preserve original/canonical text and media provenance.
- Keep the API local-only; it has no multi-user authentication. Retain desktop until real TTS/video/YouTube parity is verified.
- Confirm dependencies and network requirements before broad test runs. Live provider checks must be within the authorized task.

## Known Gotchas

- Dev: UI `5173`, API `8765`; built application: API `8000` by default.
- Root has only the `dev` script. Use the frontend prefix for build/test/typecheck; `npm run dev` avoids global `npm link` registration.
- Build includes typecheck. Build/typecheck can write output/cache; tests can write configuration. These are not read-only commands.
- Python tests mix pytest and unittest; unittest discovery alone does not establish pytest-style collection. Full Python suite includes Qt.

## Verification

- Run only checks allowed by the task. Report actual commands, exit status, failures/skips and remaining gaps.
- Smoke checks, fixture media and historical reports do not establish whole-application readiness or real provider parity.

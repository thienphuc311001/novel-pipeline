# Project Guidance

`CLAUDE.md` is the shared project rule source. `AGENTS.md` is the Codex adapter.

## Context

- Shared Python core: `pipeline/`, `chapters/`, `cleaning/`, `chunking/`, `filtering/`, `media/`, `config/`. Keep CLI/HTTP core independent of Qt.
- `backend/` provides local FastAPI; `frontend/` uses React/Vite. `ui/` and `app.py` retain the optional PyQt6 interface.
- Read `README.md` and `INSTALL.md` for architecture/setup; for UI work, read `design-system/novel-pipeline/MASTER.md`.

## Working Rules

- Follow the current task and applicable approved intent/spec/plan. Document approval alone does not authorize execution.
- Inspect Git status first. Preserve uncommitted changes; do not reset, stash, overwrite or commit unrelated work.
- Preserve existing interfaces and data formats unless the task authorizes changes. Follow neighboring conventions; frontend uses strict TypeScript and semantic design tokens.
- Treat `BUILD_PROMPT.md` as historical: flag conflicts with current requirements/code rather than adopting its outdated platform restrictions.

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

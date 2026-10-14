# Installation Guide

## Requirements

- Python 3.11+.
- Node.js 22.12+ and npm for React development or building the local UI.
- FFmpeg and FFprobe on PATH for audiobook merging and video rendering.
- Optional GPU drivers for VA-API, Quick Sync, NVENC, AMF or VideoToolbox. Verified encoders fall back to CPU.
- A current desktop browser (Firefox, Chrome, Edge or Safari). The PyQt6 desktop interface was removed; no Qt packages are needed.

## Local web application

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m backend
```

On Windows, activate with `.venv\Scripts\Activate.ps1` instead. Open `http://127.0.0.1:8000` after starting the backend. The backend serves the built `frontend/dist` assets and the API on the same origin. A frontend build is needed again after changing UI source.

For development, install the root launcher and register `np` once:

```bash
npm ci
npm link
np run dev
```

`np run dev` starts FastAPI on port 8765 and Vite on port 5173 in one terminal.
It automatically uses `.venv` when present, otherwise Python on PATH. Ctrl+C
stops both process trees; if either server exits, the other is stopped too.
After installing root dependencies, `npm run dev` runs the same launcher
without requiring the global `np` command.
When starting services separately, use `python -m backend --port 8765` with
`npm --prefix frontend run dev`. The built application still uses port 8000
by default; the dev launcher does not require that port to be free.

Open the Vite URL on port 5173; its `/api` proxy connects to `127.0.0.1:8765`. The API accepts only local Host/Origin values. Do not expose this filesystem-capable service to a LAN or the internet; it intentionally has no multi-user authentication.

## Internal CLI

The smaller dependency set supports Python/CLI processing without FastAPI:

```bash
python -m pip install -r requirements-core.txt
python -m pipeline run /path/story.txt --title "My story" --group-size 20 --prepare --export zip
python -m pipeline sessions
```

`Ctrl+C` requests cooperative cancellation. Completed media and resumable job files remain on disk. Translation and dictionary features remain intentionally absent.

## Configuration and inputs

The existing settings location is unchanged: `~/.config/novel-pipeline-v2/config.json`, beneath `XDG_CONFIG_HOME` when set, or beneath `NOVEL_PIPELINE_CONFIG_DIR` when overridden.

```bash
export NOVEL_PIPELINE_CONFIG_DIR=/custom/path
```

Saved sessions remain in `sessions/` beneath that configuration directory. Use local input paths to keep outputs beside the original story files. Browser uploads are durable copies under the configuration directory's `imports/` area; their outputs live beside those copies. Image/OAuth uploads use a separate durable assets area. No generated file uses a request-scoped temporary input folder.

## YouTube desktop OAuth

Enable YouTube Data API v3 in Google Cloud, configure the consent screen, add your account as a test user when appropriate, and create an OAuth client of type **Desktop app**. Download its client JSON, set `youtube_client_secrets_path` in configuration, then connect from the YouTube screen. The sign-in flow opens the system browser; the path alone does not connect an account.

Access/refresh tokens and resumable upload URLs stay in the OS credential store. Linux requires an unlocked Secret Service or KWallet; macOS uses Keychain and Windows uses Credential Manager. The app does not fall back to plaintext token files. Credentials are not included in session JSON.

Google may require OAuth verification/API auditing and may restrict uploads from unverified projects to private visibility. See [desktop OAuth setup](https://developers.google.com/identity/protocols/oauth2/native-app) and [videos.insert restrictions](https://developers.google.com/youtube/v3/docs/videos/insert).

## Tests

The suite needs no Qt. Media regressions use the real local FFmpeg/FFprobe on PATH:

```bash
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q
npm --prefix frontend ci
npm --prefix frontend run test
npm --prefix frontend run build
```

Use a fresh temporary `NOVEL_PIPELINE_CONFIG_DIR` when running tests so they never touch your real configuration.

The desktop was removed on offline/fake-provider regression, real local FFmpeg
rendering and a browser smoke against fake providers. Those checks do not
establish real Edge-TTS or YouTube behavior: a rendered video using fixture audio
proves local rendering/muxing only. Before relying on a new environment, check a
complete real Edge-TTS run, resume/error handling and a private upload on a test
YouTube channel yourself.

## Troubleshooting

- **Missing frontend:** run `npm --prefix frontend ci` and `npm --prefix frontend run build`, or use the Vite development server.
- **Cannot import backend/FastAPI:** activate the same virtual environment in which `requirements.txt` was installed; launch from the repository root.
- **Cannot connect UI:** run `np run dev`, then open port 5173. Its dev API uses port 8765, independently of other apps on port 8000. The built application (`python -m backend`) uses port 8000 by default. Use localhost or 127.0.0.1, not a LAN hostname.
- **Missing FFmpeg/FFprobe:** install the system `ffmpeg` package and verify both binaries are on PATH.
- **Configuration permission error:** point `NOVEL_PIPELINE_CONFIG_DIR` at a writable persistent directory.

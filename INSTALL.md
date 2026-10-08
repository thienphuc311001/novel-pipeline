# Installation Guide

## Requirements

- Python 3.11+.
- Node.js 22.12+ and npm for React development or building the local UI.
- FFmpeg and FFprobe on PATH for audiobook merging and video rendering.
- Optional GPU drivers for VA-API, Quick Sync, NVENC, AMF or VideoToolbox. Verified encoders fall back to CPU.
- A browser. PyQt6 is needed only for the retained legacy desktop interface.

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

## CLI without Qt

The smaller dependency set supports Python/CLI processing without FastAPI or PyQt6:

```bash
python -m pip install -r requirements-core.txt
python -m pipeline run /path/story.txt --title "My story" --group-size 20 --prepare --export zip
python -m pipeline sessions
```

`Ctrl+C` requests cooperative cancellation. Completed media and resumable job files remain on disk.

## Optional legacy desktop

```bash
python -m pip install -r requirements-desktop.txt
python app.py
```

The desktop and web workspace share normalization/loading/settings validation and use the same session format and media provenance. Keep this interface until real TTS/video/YouTube comparisons in your environment are complete. Translation and dictionary features remain intentionally absent.

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

## Tests and migration parity

The complete suite also exercises the retained Qt interface:

```bash
python -m pip install -r requirements-desktop.txt pytest httpx
QT_QPA_PLATFORM=offscreen python -m pytest -q
npm --prefix frontend run build
```

Tests do not establish external-provider parity. Check a complete real Edge-TTS
run, resume/error handling, and a private upload on your test YouTube channel
before removing PyQt6. A rendered video using fixture audio proves local
rendering/muxing, not speech-provider or YouTube success.

## Troubleshooting

- **Missing frontend:** run `npm --prefix frontend ci` and `npm --prefix frontend run build`, or use the Vite development server.
- **Cannot import backend/FastAPI:** activate the same virtual environment in which `requirements.txt` was installed; launch from the repository root.
- **Cannot connect UI:** run `np run dev`, then open port 5173. Its dev API uses port 8765, independently of other apps on port 8000. The built application (`python -m backend`) uses port 8000 by default. Use localhost or 127.0.0.1, not a LAN hostname.
- **Missing FFmpeg/FFprobe:** install the system `ffmpeg` package and verify both binaries are on PATH.
- **Missing PyQt6 / xcb errors:** these apply only to `python app.py`; install `requirements-desktop.txt` and the platform Qt plugins. They do not affect the CLI/web core.
- **Configuration permission error:** point `NOVEL_PIPELINE_CONFIG_DIR` at a writable persistent directory.

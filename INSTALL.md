# Installation Guide

## System Requirements

- Python 3.11 or newer
- PyQt6
- Pillow and edge-tts (installed by `requirements.txt`)
- FFmpeg and FFprobe on your system PATH (required for audiobook merge and Step 5 video)
- Optional GPU drivers/runtime for VA-API, Quick Sync, NVENC, AMF, or VideoToolbox
- ~10 MB disk space

## Quick Install

### Linux (Arch/Manjaro)

```bash
# Install system PyQt6
sudo pacman -S python-pyqt6

# Clone and run
git clone https://github.com/your-repo/novel-pipeline-v2
cd novel-pipeline-v2
python app.py
```

### Linux (Debian/Ubuntu)

```bash
# Install Python and pip
sudo apt update
sudo apt install python3 python3-pip

# Install PyQt6
pip3 install PyQt6

# Clone and run
git clone https://github.com/your-repo/novel-pipeline-v2
cd novel-pipeline-v2
python3 app.py
```

### macOS

```bash
# Install Python via Homebrew
brew install python@3.11

# Install PyQt6
pip3 install PyQt6

# Clone and run
git clone https://github.com/your-repo/novel-pipeline-v2
cd novel-pipeline-v2
python3 app.py
```

### Windows

```powershell
# Install Python from python.org (3.11+)
# Then in PowerShell:

pip install PyQt6

git clone https://github.com/your-repo/novel-pipeline-v2
cd novel-pipeline-v2
python app.py
```

## Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Linux example for the MP3 merge and video tools (includes ffprobe)
# sudo apt install ffmpeg

# Run
python app.py
```

## Configuration

Settings are stored in:
- **Linux/macOS**: `~/.config/novel-pipeline-v2/config.json`
- **Windows**: `%APPDATA%\novel-pipeline-v2\config.json`

You can override the config location with:
```bash
export NOVEL_PIPELINE_CONFIG_DIR=/custom/path
```

## Optional: Gemini AI Translation

To enable AI translation:

1. Get API key from [Google AI Studio](https://aistudio.google.com/)
2. Open the app and go to Settings
3. Enter your API key in the "Gemini API Key" field
4. Save settings

The app works fully offline without this feature.

## Optional: YouTube desktop OAuth

Install the project requirements in the same environment used to run `app.py`:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Enable YouTube Data API v3 in Google Cloud, configure the consent screen, add your account as a test user if the project is in testing, and create an OAuth client of type **Desktop app**. Download its client JSON and select it once in **Settings → YouTube**. The JSON path is a setting; access/refresh tokens are stored only in the OS credential store.

Linux requires an unlocked Secret Service or KWallet; macOS uses Keychain and Windows uses Credential Manager. The app reports unavailable/locked credential stores and does not substitute plaintext token files. Linux keyring support (`SecretStorage`/`jeepney`) is installed with the Python requirements.

Google projects may need OAuth verification/API auditing for production use. Google restricts uploads from some unverified API projects to private visibility; the app reports the visibility returned by YouTube. See [desktop OAuth setup](https://developers.google.com/identity/protocols/oauth2/native-app) and [YouTube videos.insert restrictions](https://developers.google.com/youtube/v3/docs/videos/insert).

## Troubleshooting

### "No module named 'PyQt6'"

```bash
pip install PyQt6
```

### "xcb" errors on Linux

```bash
# Install Qt platform plugins
sudo apt install libxcb-xinerama0 libxcb-cursor0
```

### "ImportError: No module named 'config'"

Make sure you're running from the project root:
```bash
cd /path/to/novel-pipeline-v2
python app.py
```

### Permission denied on config directory

```bash
mkdir -p ~/.config/novel-pipeline-v2
chmod 755 ~/.config/novel-pipeline-v2
```

## Running from Source

No build step required! Just run:
```bash
python app.py
```

## Uninstall

```bash
# Remove application
rm -rf /path/to/novel-pipeline-v2

# Remove user data (optional)
rm -rf ~/.config/novel-pipeline-v2
```

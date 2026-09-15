# Installation Guide

## System Requirements

- Python 3.11 or newer
- PyQt6
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

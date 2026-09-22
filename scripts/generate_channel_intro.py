"""Generate the fixed channel intro MP3 once: python scripts/generate_channel_intro.py.

Uses the configured TTS voice (default vi-VN-HoaiMyNeural) and the exact fixed
text. The file is cached globally and reused at the start of every audiobook.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from media.channel_intro import (
    channel_intro_text,
    channel_intro_voice,
    ensure_channel_intro_audio,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="", help="Override TTS voice (default: settings tts_voice)")
    parser.add_argument("--text", default="", help="Override intro text (default: fixed channel text)")
    parser.add_argument("--output", default="", help="Copy the cached MP3 to this path as well")
    args = parser.parse_args()

    settings = Settings.load()
    text = args.text.strip() or channel_intro_text(settings)
    voice = args.voice.strip() or (args.voice.strip() if args.voice else "") or channel_intro_voice(settings) or settings.tts_voice
    print(f"Text: {text}")
    print(f"Voice: {voice}")
    path = ensure_channel_intro_audio(text, voice)
    print(f"Cached: {path} ({path.stat().st_size} bytes)")
    if args.output:
        from shutil import copyfile

        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(path, target)
        print(f"Copied: {target}")


if __name__ == "__main__":
    main()

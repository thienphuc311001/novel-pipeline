"""Local CLI for the same workspace operations exposed by FastAPI."""
from __future__ import annotations

import argparse
import json
import signal
import sys
from threading import Event

from pipeline.service import PipelineService


def main(argv=None):
    parser = argparse.ArgumentParser(description="Novel Pipeline — Qt-free local processing")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Import, normalize, group and export a story")
    run.add_argument("paths", nargs="+", help="TXT/ZIP files or local directories")
    run.add_argument("--title", default="", help="Story title (default: first input filename)")
    run.add_argument("--group-size", type=int, default=20)
    run.add_argument("--sort", choices=("natural", "selection", "name"), default="natural")
    run.add_argument("--prepare", action="store_true", help="Prepare real per-group TTS plans")
    run.add_argument("--tts", action="store_true", help="Generate/resume all selected group audiobooks (online)")
    run.add_argument("--thumbnail", default="", help="Cover image used for group thumbnails")
    run.add_argument("--video", action="store_true", help="Render videos after generating/resuming TTS")
    run.add_argument("--cover", default="", help="Required square page image for video")
    run.add_argument("--qr", default="", help="Required QR image for video")
    run.add_argument("--export", choices=("txt", "json", "zip"), default="txt")
    action = commands.add_parser("action", help="Continue a saved workspace using an API action")
    action.add_argument("action", help="Action name: prepare, tts, video, upload, edit, export, …")
    action.add_argument("--session", help="Saved session ID; omitted for a new workspace")
    action.add_argument("--options", default="{}", help="JSON options object (same shape as POST /api/jobs)")
    commands.add_parser("sessions", help="List saved work sessions")
    args = parser.parse_args(argv)
    service = PipelineService()
    if args.command == "sessions":
        print(json.dumps(service.sessions.list_sessions(), ensure_ascii=False, indent=2))
        return 0
    cancelled = Event()
    previous_handler = signal.signal(signal.SIGINT, lambda *_: cancelled.set())

    def progress(done, total, message):
        print(f"[{done}/{total}] {message}", file=sys.stderr, flush=True)

    results = []

    def perform(name, options):
        result = service.perform(name, options, cancel_event=cancelled, progress=progress)
        results.append({"action": name, **result})
        return not result.get("cancelled") and result.get("status") not in {"partial", "failed"}

    try:
        if args.command == "action":
            if args.session:
                service.open_session(args.session)
            options = json.loads(args.options)
            if not isinstance(options, dict):
                raise ValueError("--options must be a JSON object.")
            success = perform(args.action, options)
        else:
            if args.video and (not args.tts or not args.thumbnail or not args.cover or not args.qr):
                raise ValueError("--video requires --tts, --thumbnail, --cover and --qr.")
            success = perform("import", {"paths": args.paths, "sort_mode": args.sort})
            if success:
                success = perform("normalize", {})
            if success:
                preview = service.preview_grouping(args.group_size)
                if preview["requires_numeric_boundaries"]:
                    raise ValueError("Numbering gaps require reviewed numeric boundaries. Use the web preview, or saved-session group action with its confirmation fingerprint.")
                success = perform("group", {"title": args.title or service.document.job_title, "size": args.group_size})
            ids = [group.group_id for group in service.document.chapter_groups]
            if success and args.thumbnail:
                success = perform("thumbnail", {"group_ids": ids, "image_path": args.thumbnail})
            if success and args.prepare:
                success = perform("prepare", {"group_ids": ids})
            if success and args.tts:
                success = perform("tts", {"group_ids": ids})
            if success and args.video:
                success = perform("video", {"group_ids": ids, "cover_image": args.cover, "qr_image": args.qr})
            if success:
                success = perform("export", {"format": args.export})
        if service.document.original_input_text or service.document.chapter_groups:
            service.save_session()
        print(json.dumps({"session_id": service.session_id, "results": results}, ensure_ascii=False, indent=2))
        return 130 if cancelled.is_set() else (0 if success else 1)
    except Exception as error:
        if service.document.original_input_text or service.document.chapter_groups:
            try:
                service.save_session()
            except Exception as save_error:
                print(f"Could not save workspace: {save_error}", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 130 if cancelled.is_set() else 1
    finally:
        signal.signal(signal.SIGINT, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())

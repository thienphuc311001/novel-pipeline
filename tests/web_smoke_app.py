"""Test-only loopback server for the browser smoke: real application, fake providers.

Not a production entry point and not a feature flag.  It runs the real
PipelineService, JobManager, FastAPI application and built frontend, replacing
only the Edge-TTS client and the Google account/transport.  It refuses to start
unless its configuration and fixtures live inside ``--fixture-root``, binds
127.0.0.1 only, and denies every non-loopback connection made by this process.

    python -B -m tests.web_smoke_app --fixture-root DIR --dist-dir DIST --port PORT
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import socket
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tests.test_youtube import MemorySecrets, Response
from tests.web_only_support import ACCOUNT, STORY, FakeTtsClients, make_mp3, tts_clients, write_image

# Any TTS request containing this token fails at the fake provider boundary, so
# the browser can exercise failed-chunk recovery by editing it out.
FAIL_MARKER = "LOIGIALAP"
SMOKE_STORY = STORY + f"\nChương 4\nĐoạn này dừng ở {FAIL_MARKER} để thử lỗi TTS.\n"
TTS_DELAY = 0.25  # seconds per fake request: long enough to click Stop
UPLOAD_SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=SMOKE"


class EgressDenied(ConnectionRefusedError):
    pass


def _loopback(host) -> bool:
    if not isinstance(host, str):
        return False
    host = host.strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def install_socket_guard(stack: ExitStack):
    """Deny DNS and connections to anything but loopback for this whole process."""
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    create_connection, getaddrinfo = socket.create_connection, socket.getaddrinfo

    def require(address):
        if isinstance(address, tuple) and not _loopback(address[0]):
            raise EgressDenied(f"web_smoke_app: non-loopback connection denied: {address[0]}")

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            require(address)
        return connect(self, address)

    def guarded_connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            require(address)
        return connect_ex(self, address)

    def guarded_create_connection(address, *args, **kwargs):
        require(address)
        return create_connection(address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and not _loopback(host.decode() if isinstance(host, bytes) else host):
            raise socket.gaierror(socket.EAI_NONAME, f"web_smoke_app: non-loopback lookup denied: {host}")
        return getaddrinfo(host, *args, **kwargs)

    stack.enter_context(patch.object(socket.socket, "connect", guarded_connect))
    stack.enter_context(patch.object(socket.socket, "connect_ex", guarded_connect_ex))
    stack.enter_context(patch.object(socket, "create_connection", guarded_create_connection))
    stack.enter_context(patch.object(socket, "getaddrinfo", guarded_getaddrinfo))


def guard_controls() -> dict:
    """Positive: a loopback listener is reachable. Negative: egress and DNS are denied."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2):
            positive = "connected"
    finally:
        listener.close()

    def connect_ex():
        with socket.socket() as probe:
            return probe.connect_ex(("192.0.2.1", 443))

    negative = {}
    for name, attempt in (("connect", lambda: socket.create_connection(("192.0.2.1", 443), timeout=2)),
                          ("connect_ex", connect_ex),
                          ("getaddrinfo", lambda: socket.getaddrinfo("www.googleapis.com", 443))):
        try:
            attempt()
            negative[name] = "ALLOWED"
        except (EgressDenied, socket.gaierror):
            negative[name] = "denied"
    if positive != "connected" or set(negative.values()) != {"denied"}:
        raise SystemExit(f"web_smoke_app: socket guard controls failed: {positive} {negative}")
    return {"loopback": positive, **negative}


class SmokeTransport:
    """Google API boundary: answers uploads locally; the first thumbnail upload fails once."""

    def __init__(self):
        self.calls = []
        self.videos = 0
        self.thumbnail_failures = 1

    def request(self, method, url, **kwargs):
        path = url.split("?", 1)[0].removeprefix("https://www.googleapis.com")
        self.calls.append((method, path))
        print(f"FakeYouTube {method} {path}", flush=True)
        headers = kwargs.get("headers") or {}
        if method == "POST" and path == "/upload/youtube/v3/videos":
            self.videos += 1
            return Response(headers={"Location": f"{UPLOAD_SESSION}{self.videos}"})
        if method == "PUT" and path == "/upload/youtube/v3/videos":
            if headers.get("Content-Range", "").startswith("bytes */"):
                return Response(308)
            return Response(data={"id": f"smoke{self.videos}", "status": {"privacyStatus": "private"}})
        if method == "POST" and path == "/upload/youtube/v3/thumbnails/set":
            if self.thumbnail_failures:
                self.thumbnail_failures -= 1
                return Response(403, data={"error": {"message": "fake thumbnail rejection"}})
            return Response()
        if method == "GET" and path == "/youtube/v3/playlistItems":
            return Response(data={"items": []})
        if method == "POST" and path == "/youtube/v3/playlistItems":
            return Response(data={"id": "smoke-playlist-item"})
        raise AssertionError(f"web_smoke_app: unexpected fake YouTube call {method} {path}")

    def close(self):
        pass


class SmokeAuth:
    """Google account boundary: connects without a browser flow or stored token."""

    def __init__(self, transport):
        self.account = None
        self.secret_store = MemorySecrets()
        self.transport = transport

    def restore(self):
        return self.account

    def connect(self, cancel_event=None):
        self.account = dict(ACCOUNT, email="smoke@example.invalid", channel_title="Smoke fake channel")
        return self.account

    def disconnect(self):
        self.account = None

    def session(self):
        return self.transport


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _private_file(path: Path, root: Path) -> str:
    """Refuse fixture paths that leave the private root or pass through a symlink."""
    for part in [path, *path.parents]:
        if part == root.parent:
            break
        if part.is_symlink():
            raise SystemExit(f"web_smoke_app: refusing symlinked fixture path {path}")
    resolved = path.resolve(strict=True)
    if not _inside(resolved, root):
        raise SystemExit(f"web_smoke_app: refusing fixture outside --fixture-root: {path}")
    return str(resolved)


def prepare_fixtures(root: Path) -> dict:
    folder = root / "fixtures"
    folder.mkdir(exist_ok=True)
    story = folder / "Truyện khói.txt"
    story.write_text(SMOKE_STORY, encoding="utf-8")
    secrets = folder / "fake_client_secret.json"
    secrets.write_text(json.dumps({"installed": {"client_id": "fake-smoke-client"}}), encoding="utf-8")
    fixtures = {
        "story": story,
        "cover": Path(write_image(folder / "cover.png", (400, 400), (200, 30, 30))),
        "qr": Path(write_image(folder / "qr.png", (250, 250), (255, 255, 255))),
        "thumbnail_source": Path(write_image(folder / "thumbnail-source.png", (1600, 900), (30, 60, 200))),
        "voice": make_mp3(folder / "voice.mp3"),
        "client_secrets": secrets,
    }
    return {name: _private_file(path, root) for name, path in fixtures.items()}


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tests.web_smoke_app", description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--dist-dir", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args(argv)
    root = arguments.fixture_root
    if root.is_symlink() or not root.is_dir():
        parser.error("--fixture-root must be an existing, non-symlinked directory")
    arguments.fixture_root = root.resolve()
    config = os.environ.get("NOVEL_PIPELINE_CONFIG_DIR", "")
    if not config or not _inside(Path(config).resolve(), arguments.fixture_root):
        parser.error("NOVEL_PIPELINE_CONFIG_DIR must be set inside --fixture-root")
    if not (arguments.dist_dir / "index.html").is_file():
        parser.error("--dist-dir must contain the built index.html")
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    return arguments


def main(argv=None):
    arguments = parse_arguments(argv)
    import uvicorn

    from backend.app import create_app
    from config.settings import Settings
    from pipeline.service import PipelineService

    root = arguments.fixture_root
    with ExitStack() as stack:
        install_socket_guard(stack)
        controls = guard_controls()
        fixtures = prepare_fixtures(root)
        settings = Settings.load()
        if not _inside(Path(settings._loaded_config_path).resolve(), root):
            raise SystemExit("web_smoke_app: settings would load outside --fixture-root")
        settings.channel_intro_enabled = False
        settings.youtube_client_secrets_path = fixtures["client_secrets"]
        settings.save(settings._loaded_config_path)

        def delay(text):
            return asyncio.sleep(TTS_DELAY)

        def fail(text):
            return RuntimeError("fake Edge-TTS rejection") if FAIL_MARKER in text else None

        clients = FakeTtsClients(fixtures["voice"], fail=fail, gate=delay)
        stack.enter_context(tts_clients(clients))
        auth = SmokeAuth(SmokeTransport())
        stack.enter_context(patch("media.youtube_auth.YouTubeAuth", side_effect=lambda path: auth))
        service = PipelineService(settings)
        app = create_app(service, dist_dir=arguments.dist_dir)
        print("FakeProviderActive " + json.dumps({
            "tts": "FakeTtsClients via TtsProcessor client_factory", "fail_marker": FAIL_MARKER,
            "youtube": "SmokeAuth + SmokeTransport (no OAuth, no network)", "socket_guard": controls,
            "fixtures": {name: os.path.relpath(path, root) for name, path in fixtures.items()},
            "fixture_root": str(root), "bind": f"127.0.0.1:{arguments.port}",
        }, ensure_ascii=False), flush=True)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=arguments.port,
                                               proxy_headers=False, log_level="info"))
        server.run()
        print(f"FakeProviderCalls tts={len(clients.calls)} youtube={len(auth.transport.calls)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

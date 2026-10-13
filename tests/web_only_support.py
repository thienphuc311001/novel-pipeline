"""Qt-free fixtures for web/core regression tests; no real provider is contacted.

Fakes stop at provider/process boundaries only: the Google account/transport
(``FakeAuth`` + scripted HTTP session) and the Edge-TTS client.  Everything else
runs through the real PipelineService, JobManager, HTTP application and files.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tests.test_youtube import MemorySecrets, ScriptedSession


ACCOUNT = {"email": "user@example.com", "channel_id": "channel1", "channel_title": "Audiobooks",
           "categories": [{"id": "22", "title": "People & Blogs"}],
           "playlists": [{"id": "playlist1", "title": "Bắc Tống"}]}


class FakeAuth:
    def __init__(self, path):
        self.account = ACCOUNT.copy()
        self.secret_store = MemorySecrets()
        self.transport = ScriptedSession()

    def restore(self):
        return self.account

    def connect(self, cancel_event=None):
        return self.account

    def disconnect(self):
        self.account = None

    def session(self):
        return self.transport


TERMINAL = {"completed", "failed", "cancelled"}
# Long enough for the scoring decoder to settle on UTF-8 (very short Vietnamese
# samples can legitimately score better under a legacy code page).
STORY = ("Chương 1: Mưa\nTrời mưa rất to trên núi Thanh Vân, nàng đứng lặng bên hiên nhà.\n\n"
         "Chương 2\nTa là ai giữa nhân gian này? Hắn hỏi mà không ai trả lời.\n\n"
         "Chương 3\nNàng đi rồi, không quay lại, chỉ để lại một bức thư ngắn.\n")


@contextmanager
def youtube_auth(auth):
    """Inject one persistent FakeAuth where jobs build ``YouTubeAuth(path)``; record each path."""
    paths = []

    def factory(path):
        paths.append(path)
        return auth

    with patch("media.youtube_auth.YouTubeAuth", side_effect=factory):
        yield paths


def make_mp3(path, seconds=0.4, frequency=440):
    """Encode a short real MP3 with the local FFmpeg so concat/probe stay real."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required for web-only media regressions.")
    path = Path(path)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency={frequency}:sample_rate=24000:duration={seconds}",
                    "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", str(path)],
                   check=True, timeout=60, stdin=subprocess.DEVNULL)
    return path


class FakeTtsClients:
    """Edge-TTS boundary: writes a real MP3 per request; ``fail`` decides failures by text."""

    def __init__(self, mp3_path, fail=None, gate=None):
        self.content = Path(mp3_path).read_bytes()
        self.fail = fail or (lambda text: None)
        self.gate = gate
        self.calls = []

    def __call__(self, text, voice):
        owner = self

        class Client:
            async def save(self, path):
                owner.calls.append((text, voice))
                if owner.gate is not None:
                    await owner.gate(text)
                error = owner.fail(text)
                if error is not None:
                    raise error
                Path(path).write_bytes(owner.content)

        return Client()


@contextmanager
def tts_clients(factory):
    """Give every real TtsProcessor created by a job this client factory."""
    from media.tts import TtsProcessor

    original = TtsProcessor.__init__

    def init(self, *args, **kwargs):
        kwargs["client_factory"] = factory
        original(self, *args, **kwargs)

    with patch.object(TtsProcessor, "__init__", init):
        yield factory


def write_image(path, size, color):
    from PIL import Image

    Image.new("RGB", size, color).save(path)
    return str(Path(path).resolve())


class WebWorkspaceMixin:
    """Fresh config/session/output root plus the real FastAPI app around one service."""

    settings_overrides = {"channel_intro_enabled": False}

    def start_workspace(self, settings=None):
        from config.settings import Settings

        temporary = tempfile.TemporaryDirectory(prefix="web-only-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_dir = self.root / "config"
        environment = patch.dict(os.environ, {"NOVEL_PIPELINE_CONFIG_DIR": str(self.config_dir)})
        environment.start()
        self.addCleanup(environment.stop)
        if settings is None:
            settings = Settings.load()
            for name, value in self.settings_overrides.items():
                setattr(settings, name, value)
            settings.save(settings._loaded_config_path)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        (self.dist / "index.html").write_text("<html>web-only</html>", encoding="utf-8")
        self.client = None
        self.addCleanup(self.close_app)
        return self.open_app(settings)

    def open_app(self, settings=None):
        """Start the real application lifespan; a restart reloads the global config from disk."""
        from fastapi.testclient import TestClient

        from backend.app import create_app
        from config.settings import Settings
        from pipeline.service import PipelineService
        from pipeline.sessions import SessionStore

        self.service = PipelineService(settings if settings is not None else Settings.load())
        self.service.sessions = SessionStore(self.root / "sessions")
        self.client = TestClient(create_app(self.service, dist_dir=self.dist), base_url="http://127.0.0.1:8000")
        self.client.__enter__()
        return self.service

    def close_app(self):
        """Application shutdown (JobManager.close: cancel, join, final session save)."""
        client, self.client = self.client, None
        if client is not None:
            client.__exit__(None, None, None)

    # HTTP helpers --------------------------------------------------------
    def submit(self, action, options=None):
        response = self.client.post("/api/jobs", json={"action": action, "options": options or {}})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()["id"]

    def wait(self, job_id, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in TERMINAL:
                return job
            time.sleep(0.01)
        self.fail(f"job {job_id} did not finish within {timeout}s")

    def run_job(self, action, options=None, *, expect="completed", timeout=60):
        job = self.wait(self.submit(action, options), timeout)
        if expect is not None:
            self.assertEqual(job["status"], expect, job)
        return job

    def stop(self, job_id):
        response = self.client.post(f"/api/jobs/{job_id}/stop")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def state(self):
        return self.client.get("/api/state").json()

    def logs(self, job_id, after=0):
        return self.client.get(f"/api/jobs/{job_id}/logs", params={"after": after}).json()

    # Story fixtures ------------------------------------------------------
    def import_story(self, text=STORY, name="Bắc Tống.txt", *, normalize=True):
        folder = self.root / "input"
        folder.mkdir(exist_ok=True)
        source = folder / name
        source.write_text(text, encoding="utf-8")
        self.run_job("import", {"paths": [str(source)]})
        if normalize:
            self.run_job("normalize")
        return source

    def group_story(self, size=1, title="Bắc Tống", **options):
        job = self.run_job("group", {"title": title, "size": size, **options})
        return job["result"]["group_ids"]

    def page_inputs(self):
        cover = write_image(self.root / "cover.png", (400, 400), (200, 30, 30))
        qr = write_image(self.root / "qr.png", (250, 250), (255, 255, 255))
        return cover, qr

    def media_ready(self, group_ids, *, mp3=None, thumbnail_color=(30, 60, 200)):
        """Real thumbnail + TTS (fake Edge-TTS client, real FFmpeg merge) for the given groups."""
        mp3 = mp3 or make_mp3(self.root / "voice.mp3")
        source = write_image(self.root / "thumb-source.png", (1600, 900), thumbnail_color)
        self.run_job("thumbnail", {"group_ids": list(group_ids), "image_path": source})
        clients = FakeTtsClients(mp3)
        with tts_clients(clients):
            self.run_job("tts", {"group_ids": list(group_ids)})
        return clients

    def video_ready(self, group_ids, **media):
        """Media plus a real rendered MP4 for each group (real FFmpeg encoder)."""
        clients = self.media_ready(group_ids, **media)
        cover, qr = self.page_inputs()
        self.run_job("video", {"group_ids": list(group_ids), "cover_image": cover, "qr_image": qr}, timeout=240)
        return clients


def video_fingerprint(video):
    """The uploader's saved MP4 identity, for arranging a pending resumable upload."""
    from hashlib import sha256

    video = Path(video)
    stat = video.stat()
    return {"path": str(video.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": sha256(video.read_bytes()).hexdigest()}

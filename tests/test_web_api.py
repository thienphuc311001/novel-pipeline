"""HTTP error, durable-file and loopback/security behavior (no source wiring tests)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import create_app
from config.settings import Settings
from pipeline.service import PipelineService
from pipeline.sessions import SessionStore
from tests.test_web_jobs import ControlledService


class WebApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"NOVEL_PIPELINE_CONFIG_DIR": str(self.root / "config")})
        environment.start()
        self.addCleanup(environment.stop)
        self.service = PipelineService(Settings(channel_intro_enabled=False))
        self.service.sessions = SessionStore(self.root / "sessions")
        self.dist = self.root / "dist"
        self.dist.mkdir()
        (self.dist / "index.html").write_text("<html>real built page</html>", encoding="utf-8")
        self.client = TestClient(create_app(self.service, dist_dir=self.dist), base_url="http://127.0.0.1:8000")
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_local_origin_and_host_boundaries_apply_to_api_and_static(self):
        for host in ("evil.example", "localhost.evil.example", "127.0.0.1.evil.example", "localhost:65536", "[::1]"):
            with self.subTest(host=host):
                self.assertEqual(self.client.get("/api/health", headers={"Host": host}).status_code, 403)
        for origin in ("null", "https://evil.example", "http://localhost:9999", "http://127.0.0.1:8000/evil", "http://user@127.0.0.1:8000"):
            with self.subTest(origin=origin):
                self.assertEqual(self.client.get("/api/health", headers={"Origin": origin}).status_code, 403)
                self.assertEqual(self.client.get("/", headers={"Origin": origin}).status_code, 403)
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8000"):
            with self.subTest(origin=origin):
                self.assertEqual(self.client.get("/api/health", headers={"Origin": origin}).status_code, 200)
        preflight = self.client.options("/api/jobs", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_static_fallback_does_not_swallow_api_or_missing_assets(self):
        self.assertIn("real built page", self.client.get("/novel/session").text)
        for path in ("/api/not-real", "/api", "/missing.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.headers["content-type"], "application/json")
        secret = self.root / "outside.txt"
        secret.write_text("private")
        self.assertEqual(self.client.get("/%2e%2e/outside.txt").status_code, 404)

    def test_upload_preserves_safe_basename_is_unique_and_survives_request(self):
        first = self.client.post("/api/inputs", files=[("files", ("C:\\source\\truyện.txt", "Chương 1\nNội dung.".encode(), "text/plain"))])
        second = self.client.post("/api/inputs", files=[("files", ("truyện.txt", b"second", "text/plain"))])
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_path = Path(first.json()["paths"][0])
        second_path = Path(second.json()["paths"][0])
        self.assertEqual(first_path.name, "truyện.txt")
        self.assertNotEqual(first_path.parent, second_path.parent)
        self.assertTrue(first_path.is_relative_to(self.root / "config" / "imports"))
        self.assertIn("Nội dung", first_path.read_text(encoding="utf-8"))
        self.assertEqual(self.client.get("/api/state").json()["original_text"], "")
        submitted = self.client.post("/api/jobs", json={"action": "import", "options": {"paths": [str(first_path)]}})
        self.assertEqual(submitted.status_code, 202)
        job_id = submitted.json()["id"]
        manager = self.client.app.state.manager
        with manager.changed:
            ready = manager.changed.wait_for(
                lambda: manager.job(job_id)["status"] in {"completed", "failed", "cancelled"}, timeout=5,
            )
        self.assertTrue(ready)
        self.assertEqual(manager.job(job_id)["status"], "completed")
        state = self.client.get("/api/state").json()
        self.assertEqual(state["input_directory"], str(first_path.parent))
        self.assertIn("Nội dung", state["original_text"])
        self.assertTrue(state["session_id"])

    def test_failed_upload_removes_partial_directory_and_rejects_wrong_types(self):
        response = self.client.post("/api/inputs", files=[
            ("files", ("good.txt", b"text", "text/plain")),
            ("files", ("bad.exe", b"payload", "application/octet-stream")),
        ])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(list((self.root / "config" / "imports").iterdir()), [])
        duplicate = self.client.post("/api/assets", files=[
            ("files", ("cover.png", b"first", "image/png")),
            ("files", ("COVER.PNG", b"second", "image/png")),
        ])
        self.assertEqual(duplicate.status_code, 422)
        self.assertEqual(list((self.root / "config" / "assets").iterdir()), [])
        asset = self.client.post("/api/assets", files=[("files", ("../client.json", b"{}", "application/json"))])
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(Path(asset.json()["paths"][0]).name, "client.json")

    def test_settings_and_session_errors_are_rejected_before_persistence(self):
        original = self.client.get("/api/settings").json()
        for payload in ({"not_a_setting": True}, {"tts_rate": True}, {"encoding_chain": [1]}, {"symbol_map": {"x": 4}}, {"max_chunk_chars": 30}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.put("/api/settings", json=payload).status_code, 422)
        self.assertEqual(self.client.get("/api/settings").json(), original)
        self.assertFalse((self.root / "config" / "config.json").exists())
        invalid_ui = {"panels": {"tts": {"checked": "not a list"}}}
        self.assertEqual(self.client.post("/api/sessions", json={"ui": invalid_ui}).status_code, 422)
        self.assertEqual(self.client.get("/api/sessions").json(), [])
        self.assertEqual(self.client.post("/api/sessions/not-valid/open").status_code, 422)
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)
        self.assertEqual(self.client.post("/api/jobs/missing/stop").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs/missing/logs").status_code, 404)
        self.assertEqual(self.client.post("/api/jobs", json={"action": "edit", "options": {"text": 42}}).status_code, 422)
        self.assertEqual(self.client.get("/api/jobs").json(), [])

    def test_allowlisted_download_rejects_traversal_and_replaced_symlink(self):
        public = self.root / "result.txt"
        public.write_text("allowed output")
        secret = self.root / "secret.txt"
        secret.write_text("private")
        service = ControlledService()
        service.outputs = [{"path": str(public.resolve()), "name": public.name, "size": public.stat().st_size}]
        with TestClient(create_app(service), base_url="http://localhost:8000") as client:
            self.assertEqual(client.get("/api/outputs/download", params={"path": str(secret)}).status_code, 404)
            response = client.get("/api/outputs/download", params={"path": str(public)})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, "allowed output")
            public.unlink()
            public.symlink_to(secret)
            self.assertEqual(client.get("/api/outputs/download", params={"path": str(public)}).status_code, 404)

    def test_busy_http_mutations_reject_without_touching_workspace(self):
        service = ControlledService()
        with TestClient(create_app(service), base_url="http://127.0.0.1:8000") as client:
            try:
                response = client.post("/api/jobs", json={"action": "normalize", "options": {}})
                self.assertEqual(response.status_code, 202)
                self.assertTrue(service.entered.wait(2))
                requests = [
                    ("POST", "/api/jobs", {"action": "normalize", "options": {}}),
                    ("PUT", "/api/settings", {}),
                    ("POST", "/api/sessions", {"ui": {}}),
                    ("POST", "/api/sessions/new", None),
                    ("POST", "/api/sessions/" + "a" * 32 + "/open", None),
                    ("GET", "/api/grouping?size=10", None),
                ]
                for method, path, body in requests:
                    with self.subTest(path=path):
                        self.assertEqual(client.request(method, path, json=body).status_code, 409)
                self.assertEqual(client.get("/api/state").json()["text"], "before")
                stopped = client.post(f"/api/jobs/{response.json()['id']}/stop")
                self.assertEqual(stopped.json()["status"], "stopping")
            finally:
                service.release.set()


if __name__ == "__main__":
    unittest.main()

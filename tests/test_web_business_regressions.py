"""Business regressions formerly asserted through the desktop window.

Every case runs the real PipelineService, JobManager, HTTP application and
files; fakes stop at the Google account/transport and the Edge-TTS client.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import DEFAULT_TTS_VOICE, Settings
from media.youtube import UploadMetadata
from pipeline.document import PipelineStateError
from tests.test_chapter_groups import numeric_source
from tests.test_youtube import COMPLETE, SESSION_URI, START, Response, ScriptedSession
from tests.web_only_support import (FakeAuth, FakeTtsClients, WebWorkspaceMixin, make_mp3, tts_clients,
                                    video_fingerprint, write_image, youtube_auth)


# One chapter long enough for many TTS chunks, hence many video pages to prepare.
LONG_STORY = "Chương 1: Mưa dài\n" + "\n\n".join(
    f"Đoạn {index}: " + "Trời mưa rất to trên núi Thanh Vân, nàng đứng lặng bên hiên nhà và nhìn xa xăm. " * 8
    for index in range(1, 31)) + "\n"


class BusinessRegressionTests(WebWorkspaceMixin, unittest.TestCase):
    MARKERS = (("Chương 1", "Trời mưa"), ("Chương 2", "Ta là ai"), ("Chương 3", "Nàng đi rồi"))

    def setUp(self):
        self.start_workspace()

    # Helpers ---------------------------------------------------------------
    def group_state(self, index=0):
        return self.state()["groups"][index]

    def group_of(self, text, ids):
        """Map an Edge-TTS request text back to its STORY group."""
        for group_id, markers in zip(ids, self.MARKERS):
            if any(marker in text for marker in markers):
                return group_id
        self.fail(f"unknown TTS text: {text!r}")

    def gate_tts(self, predicate):
        """Hold matching Edge-TTS requests until released; ``started`` fires on the first hold."""
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        async def gate(text):
            if predicate(text):
                started.set()
                while not release.is_set():
                    await asyncio.sleep(0.01)
        return started, release, gate

    @contextmanager
    def gated_tts(self, group_ids):
        """Run one TTS job whose every Edge-TTS request waits until the block exits."""
        started, release, gate = self.gate_tts(lambda text: True)
        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"), gate=gate)):
            job_id = self.submit("tts", {"group_ids": list(group_ids)})
            self.assertTrue(started.wait(30))
            try:
                yield job_id
            finally:
                release.set()
                self.wait(job_id)

    def wait_for_log(self, job_id, text, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(text in row["message"] for row in self.logs(job_id)):
                return
            job = self.client.get(f"/api/jobs/{job_id}").json()
            self.assertNotIn(job["status"], {"completed", "failed", "cancelled"}, job)
            time.sleep(0.005)
        self.fail(f"log {text!r} did not appear within {timeout}s")

    def put_settings(self, values):
        return self.client.put("/api/settings", json=values)

    def settings_json(self):
        return self.client.get("/api/settings").json()

    def saved_config(self):
        return json.loads((self.config_dir / "config.json").read_text(encoding="utf-8"))

    def single_retry(self):
        response = self.put_settings({"tts_retry_count": 1, "tts_fallback_retry_count": 1})
        self.assertEqual(response.status_code, 200, response.text)

    def chapter_story(self, count):
        return "".join(f"Chương {number}\nNàng đi qua cây cầu thứ {number} trong mưa.\n\n"
                       for number in range(1, count + 1))

    def many_line_tts_job(self, chapters):
        """One real group TTS job with one chunk (and one progress log line) per chapter."""
        self.import_story(self.chapter_story(chapters), name="Nhiều chương.txt")
        ids = self.group_story(chapters, title="Nhiều chương")
        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3", seconds=0.1))):
            job = self.run_job("tts", {"group_ids": ids}, timeout=240)
        return job, self.logs(job["id"])

    # YouTube helpers -------------------------------------------------------
    def youtube_ready(self, path="fake.json"):
        response = self.put_settings({"youtube_client_secrets_path": path})
        self.assertEqual(response.status_code, 200, response.text)
        self.auth = FakeAuth(path)

    def youtube_upload(self, group_ids, transport, **options):
        self.auth.transport = transport
        with youtube_auth(self.auth):
            return self.run_job("upload", {"group_ids": list(group_ids), **options}, expect=None)

    def upload_groups(self, group_ids, transport, auth=None, **options):
        """Configure OAuth, then upload with ``auth`` (or a fresh FakeAuth) and this transport."""
        self.youtube_ready()
        self.auth = auth or self.auth
        return self.youtube_upload(group_ids, transport, **options)

    def youtube_job(self, action, transport, **options):
        self.auth.transport = transport
        with youtube_auth(self.auth):
            return self.run_job(action, options, expect=None)

    def youtube_videos(self, count=1):
        self.import_story()
        ids = self.group_story(1)[:count]
        self.video_ready(ids)
        return ids

    def youtube_state(self, index=0):
        return self.state()["groups"][index]["state"]["youtube"]

    def reopen(self):
        """Save the session, restart the application and open the session again."""
        response = self.client.post("/api/sessions", json={"ui": {"screen": "youtube"}})
        self.assertEqual(response.status_code, 200, response.text)
        self.close_app()
        self.open_app()
        response = self.client.post(f"/api/sessions/{response.json()['id']}/open")
        self.assertEqual(response.status_code, 200, response.text)

    @contextmanager
    def fresh_auths(self):
        """Every job builds its own FakeAuth from the configured client path."""
        created = []

        def factory(path):
            created.append((path, FakeAuth(path)))
            return created[-1][1]

        with patch("media.youtube_auth.YouTubeAuth", side_effect=factory):
            yield created

    # Group batches (desktop GroupBatch rows) ------------------------------
    def test_step3_active_ui_creates_groups_not_tts(self):
        self.import_story()
        preview = self.client.get("/api/grouping", params={"size": 10}).json()
        self.assertEqual(len(preview["headings"]), 3)  # 'Detected chapters: 3'
        with patch("cleaning.textclean.clean_text", side_effect=AssertionError("Forbidden in Step 3")):
            ids = self.group_story(10)
        self.assertEqual(len(ids), 1)
        self.assertEqual(self.service.document.chunks, [])
        group = self.state()["groups"][0]
        self.assertNotIn("tts_plan", group["state"])
        self.assertIn("Chương 1", group["chapters"][0]["heading"])
        self.assertIn("Chương 1", Path(group["txt_path"]).read_text(encoding="utf-8"))

    def test_step3_numeric_boundary_confirmation_and_unavailable_boundary(self):
        # 620 is absent but 621 is a reliable group start, so a missing
        # confirmation must not create files and approval uses numeric labels.
        self.import_story(numeric_source({620}), "numeric.txt")
        preview = self.client.get("/api/grouping", params={"size": 20}).json()
        # 'Some chapter numbers are missing.' is the desktop wording for this preview state.
        self.assertTrue(preview["requires_numeric_boundaries"])
        self.assertTrue(any("Numbering gap" in warning for warning in preview["warnings"]), preview["warnings"])
        self.assertIn("601-620", [row["range_label"] for row in preview["groups"]])
        job = self.run_job("group", {"title": "Bắc Tống", "size": 20, "method": "numeric_boundaries"},
                           expect="failed")
        self.assertIn("confirmation", job["error"])
        self.assertFalse(self.state()["groups"])
        self.group_story(20, method="numeric_boundaries",
                         confirmation_fingerprint=preview["confirmation_fingerprint"])
        self.assertEqual([group["range_label"] for group in self.state()["groups"]],
                         ["601-620", "621-640", "641-660", "661-680", "681-700"])

        self.import_story(numeric_source({621}), "unavailable.txt")
        preview = self.client.get("/api/grouping", params={"size": 20}).json()
        self.assertIn("Missing required group-start heading", preview["error"])
        self.assertEqual((preview["groups"], preview["numeric_available"]), ([], False))
        job = self.run_job("group", {"title": "Bắc Tống", "size": 20, "method": "numeric_boundaries",
                                     "confirmation_fingerprint": preview["confirmation_fingerprint"]},
                           expect="failed")
        self.assertIn("Missing required group-start heading", job["error"])
        self.assertFalse(self.state()["groups"])

    def test_defaults_and_select_all_subset_snapshot(self):
        self.import_story()
        ids = self.group_story()
        started, release, gate = self.gate_tts(lambda text: True)
        clients = FakeTtsClients(make_mp3(self.root / "voice.mp3"), gate=gate)
        with tts_clients(clients):
            job_id = self.submit("tts", {"group_ids": [ids[0], ids[2]]})
            self.assertTrue(started.wait(30))
            self.service.settings.tts_voice = "modified after start"
            response = self.client.put("/api/settings", json={"tts_voice": "vi-VN-NamMinhNeural"})
            self.assertEqual(response.status_code, 409, response.text)
            release.set()
            job = self.wait(job_id)
        self.assertEqual(job["status"], "completed", job)
        visited = []
        for text, _ in clients.calls:
            group_id = self.group_of(text, ids)
            if not visited or visited[-1] != group_id:
                visited.append(group_id)
        self.assertEqual(visited, [ids[0], ids[2]])
        self.assertTrue(all(voice == "vi-VN-HoaiMyNeural" for _, voice in clients.calls))
        self.assertEqual(job["progress"]["done"], job["progress"]["total"])
        self.assertEqual([row["group_id"] for row in job["result"]["groups"]], [ids[0], ids[2]])

    def test_group_failure_continues_cancel_stops_future_groups(self):
        self.import_story()
        ids = self.group_story()
        self.single_retry()
        started, release, gate = self.gate_tts(lambda text: self.group_of(text, ids) == ids[1])
        clients = FakeTtsClients(
            make_mp3(self.root / "voice.mp3"), gate=gate,
            fail=lambda text: RuntimeError("Group-specific failure") if self.group_of(text, ids) == ids[0] else None)
        with tts_clients(clients):
            job_id = self.submit("tts", {"group_ids": ids})
            self.assertTrue(started.wait(30))
            self.stop(job_id)
            release.set()
            job = self.wait(job_id)
        self.assertEqual((job["status"], job["result"]["cancelled"]), ("failed", True), job)
        visited = {self.group_of(text, ids) for text, _ in clients.calls}
        self.assertEqual(visited, {ids[0], ids[1]})
        self.assertEqual([(row["group_id"], row["status"]) for row in job["result"]["groups"]],
                         [(ids[0], "failed"), (ids[1], "cancelled")])
        failures = self.state()["groups"][0]["state"]["failures"]
        self.assertIn("Group-specific failure", [row["error_message"] for row in failures])

    def test_tts_incomplete_continues_and_resume_keeps_canonical_files(self):
        self.import_story()
        ids = self.group_story()
        self.single_retry()
        before = [Path(group["txt_path"]).read_bytes() for group in self.state()["groups"]]
        clients = FakeTtsClients(make_mp3(self.root / "voice.mp3"),
                                 fail=lambda text: RuntimeError("service error") if "Trời mưa" in text else None)
        with tts_clients(clients):
            job = self.run_job("tts", {"group_ids": ids}, expect="failed")
            groups = self.state()["groups"]
            self.assertEqual([group["state"]["tts_status"] for group in groups],
                             ["TTS Incomplete", "Completed", "Completed"])
            first = groups[0]
            self.assertFalse(Path(first["output_dir"], first["slug"] + "_audiobook.mp3").exists())
            self.assertFalse(Path(first["output_dir"], "audiobook.mp3").exists())
            self.assertTrue(first["state"]["failures"])
            self.assertEqual(before, [Path(group["txt_path"]).read_bytes() for group in groups])
            self.assertEqual([row["status"] for row in job["result"]["groups"]], ["failed", "completed", "completed"])
            count = len(clients.calls)
            self.run_job("tts", {"group_ids": [ids[1]]})
            self.assertEqual(len(clients.calls), count)
            self.assertEqual(self.state()["groups"][0]["state"]["tts_status"], "TTS Incomplete")
            failed_order = first["state"]["failures"][0]["chunk_number"]
            count = len(clients.calls)
            self.run_job("edit_chunk", {"group_id": ids[0], "order": failed_order, "text": "Corrected speech."})
        first = self.state()["groups"][0]
        self.assertEqual(first["state"]["tts_status"], "Completed")
        self.assertEqual([text for text, _ in clients.calls[count:]], ["Corrected speech."])
        self.assertEqual(before[0], Path(first["txt_path"]).read_bytes())

    def test_zero_audio_partial_merge_rejected_without_dialog(self):
        self.import_story()
        ids = self.group_story()
        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"))) as clients:
            job = self.run_job("merge_partial", {"group_ids": [ids[0]], "allow_partial": True}, expect="failed")
        self.assertEqual(clients.calls, [])
        self.assertIn("valid audio", job["result"]["groups"][0]["error"])
        self.assertFalse(Path(self.state()["groups"][0]["output_dir"], "audiobook.mp3").exists())

    def test_partial_merge_is_explicit_and_records_missing_numbers(self):
        self.import_story()
        ids = self.group_story()
        self.single_retry()
        clients = FakeTtsClients(make_mp3(self.root / "voice.mp3"),
                                 fail=lambda text: None if text.startswith("Chương 1") else RuntimeError("missing"))
        with tts_clients(clients):
            self.run_job("tts", {"group_ids": [ids[0]]}, expect="failed")
            group = self.state()["groups"][0]
            manifest_path = Path(group["output_dir"], "audio_chunks", "manifest.json")
            chunks = json.loads(manifest_path.read_text())["ordered_chunks"]
            self.assertGreater(len(chunks), 1)
            response = self.client.post("/api/jobs", json={"action": "merge_partial",
                                                           "options": {"group_ids": [ids[0]], "allow_partial": False}})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertFalse(Path(group["output_dir"], "audiobook.mp3").exists())
            self.run_job("merge_partial", {"group_ids": [ids[0]], "allow_partial": True})
        state = self.state()["groups"][0]["state"]
        self.assertEqual(state["tts_status"], "Partial")
        self.assertEqual(state["excluded_chunks"], list(range(2, len(chunks) + 1)))
        manifest = json.loads(manifest_path.read_text())
        self.assertTrue(manifest["partial_audiobook"])
        self.assertEqual(manifest["excluded_chunks"], state["excluded_chunks"])

    def test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks(self):
        from PIL import Image

        self.import_story()
        ids = self.group_story()
        covers = {}
        for index, color in ((0, "red"), (2, "blue")):
            covers[index] = write_image(self.root / f"{color}.png", (400, 600), color)
            self.run_job("thumbnail", {"group_ids": [ids[index]], "image_path": str(self.root / f"{color}.png")})
            self.assertEqual(self.state()["groups"][index]["state"]["thumbnail_source"], covers[index])
        groups = self.state()["groups"]
        for group, expected in ((groups[0], (254, 0, 0)), (groups[2], (0, 0, 254))):
            with Image.open(Path(group["output_dir"]) / "thumbnail.jpg") as thumbnail:
                self.assertEqual(thumbnail.size, (1280, 720))
                self.assertEqual(thumbnail.format, "JPEG")
                self.assertEqual(thumbnail.getpixel((10, 10)), expected)
            self.assertIn("thumbnail", group["state"])
        self.assertFalse(Path(groups[1]["output_dir"], "thumbnail.jpg").exists())
        self.assertNotIn("thumbnail", groups[1]["state"])
        self.run_job("thumbnail", {"group_ids": [ids[1]], "image_path": covers[2]})
        self.assertIn("thumbnail", self.state()["groups"][1]["state"])
        # The selected images survive an application restart and session restore.
        session = self.client.post("/api/sessions", json={"ui": {}}).json()["id"]
        self.close_app()
        self.open_app()
        self.assertEqual(self.client.post(f"/api/sessions/{session}/open").status_code, 200)
        restored = self.state()["groups"]
        self.assertEqual(restored[0]["state"]["thumbnail_source"], str((self.root / "red.png").resolve()))
        self.assertEqual(restored[2]["state"]["thumbnail_source"], str((self.root / "blue.png").resolve()))

    def test_damaged_group_does_not_block_entry_or_other_batch_jobs(self):
        self.import_story()
        ids = self.group_story()
        Path(self.state()["groups"][1]["txt_path"]).write_bytes(b"changed")
        self.assertEqual(self.client.get("/api/state").status_code, 200)
        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"))) as clients:
            job = self.run_job("tts", {"group_ids": ids}, expect="failed")
        visited = []
        for text, _ in clients.calls:
            group_id = self.group_of(text, ids)
            if not visited or visited[-1] != group_id:
                visited.append(group_id)
        self.assertEqual(visited, [ids[0], ids[2]])
        summary = job["result"]["groups"]
        self.assertIn("externally modified", summary[1]["error"])
        self.assertEqual(len(summary), 3)

    def test_step3_can_delete_any_group_and_refresh_later_stages(self):
        self.import_story()
        ids = self.group_story()
        damaged = self.state()["groups"][2]
        Path(damaged["txt_path"]).write_bytes(b"changed")
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["groups"]), 3)
        self.run_job("delete_group", {"group_id": ids[2]})
        remaining = self.state()["groups"]
        self.assertEqual(len(remaining), 2)
        self.assertNotIn(ids[2], [group["group_id"] for group in remaining])
        self.assertTrue(Path(damaged["txt_path"]).exists())
        document = self.service.document
        self.assertEqual(document.require_chapter_groups(), document.chapter_groups)
        for group_id in ids[:2]:
            self.run_job("delete_group", {"group_id": group_id})
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["groups"], [])

    def test_step4_busy_blocks_image_selection_and_group_deletion(self):
        self.import_story()
        ids = self.group_story()
        started, release, gate = self.gate_tts(lambda text: True)
        cover = write_image(self.root / "cover.png", (400, 600), "red")
        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"), gate=gate)):
            job_id = self.submit("tts", {"group_ids": [ids[0]]})
            self.assertTrue(started.wait(30))
            for action, options in (("thumbnail", {"group_ids": [ids[1]], "image_path": cover}),
                                    ("delete_group", {"group_id": ids[1]})):
                response = self.client.post("/api/jobs", json={"action": action, "options": options})
                self.assertEqual(response.status_code, 409, response.text)
            release.set()
            self.assertEqual(self.wait(job_id)["status"], "completed")
        groups = self.state()["groups"]
        self.assertEqual(len(groups), 3)
        self.assertNotIn("thumbnail_source", groups[1]["state"])

    def test_progress_visible_and_busy_blocks_other_stages(self):
        self.import_story()
        ids = self.group_story()
        started, release, gate = self.gate_tts(lambda text: "Trời mưa" in text)
        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"), gate=gate)):
            job_id = self.submit("tts", {"group_ids": ids})
            self.assertTrue(started.wait(30))
            deadline = time.monotonic() + 30
            while self.client.get(f"/api/jobs/{job_id}").json()["progress"]["done"] < 500:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            progress = self.client.get(f"/api/jobs/{job_id}").json()["progress"]
            self.assertEqual((progress["done"], progress["total"]), (500, 3000))
            self.assertEqual(progress["done"] % 1000, 500)  # current group 500‰
            self.assertEqual(round(progress["done"] * 1000 / progress["total"]), 167)
            source = self.root / "input" / "Bắc Tống.txt"
            for action, options in (("import", {"paths": [str(source)]}), ("group", {"title": "Bắc Tống", "size": 1}),
                                    ("video", {"group_ids": [ids[0]]})):
                response = self.client.post("/api/jobs", json={"action": action, "options": options})
                self.assertEqual(response.status_code, 409, response.text)
            release.set()
            self.assertEqual(self.wait(job_id)["status"], "completed")

    def test_upload_metadata_frozen_individually_completed_skipped(self):
        self.import_story()
        ids = self.group_story()
        frozen = UploadMetadata("Frozen title", description="saved")
        first = Path(self.state()["groups"][0]["output_dir"], "youtube_upload.json")
        first.write_text(json.dumps({"schema_version": 1, "status": "completed", "video_id": "abc123",
                                     "channel_id": "channel1", "metadata": frozen.__dict__}))
        self.video_ready(ids[1:])
        transport = ScriptedSession(START, COMPLETE, Response(), START, COMPLETE, Response())
        job = self.upload_groups(ids, transport,
                           metadata={"description": "New shared description", "contains_synthetic_media": True},
                           titles={ids[1]: "Individual second title"})
        self.assertEqual(job["status"], "completed", job)
        rows = {row["group_id"]: row for row in job["result"]["groups"]}
        saved = json.loads(first.read_text())["metadata"]
        self.assertEqual(saved["title"], "Frozen title")
        self.assertEqual(saved["description"], "saved")
        self.assertFalse(saved["contains_synthetic_media"])
        created = [call[2]["json"] for call in transport.calls if "json" in call[2]]
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]["snippet"]["title"], "Individual second title")
        self.assertEqual(created[0]["snippet"]["description"], "New shared description")
        self.assertTrue(created[0]["status"]["containsSyntheticMedia"])
        self.assertTrue(created[1]["status"]["containsSyntheticMedia"])
        self.assertEqual(rows[ids[0]]["status"], "skipped")  # 'already uploaded'
        self.assertEqual(rows[ids[0]]["youtube"]["metadata"]["title"], "Frozen title")  # 'using saved metadata'

    def auth_failure_batch(self):
        self.import_story()
        ids = self.group_story()
        self.video_ready(ids[:1])
        return ids, self.upload_groups(ids, ScriptedSession(Response(401)))

    def test_auth_failure_stops_batch_before_later_groups(self):
        ids, job = self.auth_failure_batch()
        rows = job["result"]["groups"]
        self.assertEqual([row["group_id"] for row in rows], [ids[0]])
        self.assertIn("Reconnect", rows[0]["error"])
        self.assertTrue(all(group["state"]["youtube"].get("status") != "completed" for group in self.state()["groups"]))

    @unittest.expectedFailure  # Gap G3: web marks the job 'failed'; no paused queue exists.
    def test_auth_failure_pauses_remaining_queue(self):
        _, job = self.auth_failure_batch()
        # The baseline pauses the batch with all three groups still queued.
        self.assertEqual(job["status"], "paused", job)
        self.assertEqual(len(job["result"].get("queue", [])), 3, job)

    def paused_upload_batch(self):
        self.import_story()
        ids = self.group_story()
        self.video_ready(ids)
        group = self.state()["groups"][0]
        fingerprint = video_fingerprint(Path(group["output_dir"], f"{group['slug']}.mp4"))
        pending = UploadMetadata("Saved title", description="Frozen description")
        state_path = Path(group["output_dir"], "youtube_upload.json")
        state_path.write_text(json.dumps({
            "schema_version": 1, "status": "uploading", "channel_id": "channel1",
            "session_key": "saved-session", "video_id": None, "metadata": pending.__dict__,
            "video_fingerprint": fingerprint, "total_bytes": fingerprint["size"], "bytes_sent": 0,
            "title": "Saved title", "privacy": "private", "playlist_id": None,
        }))
        auth = FakeAuth("fake.json")
        auth.secret_store.set("saved-session", SESSION_URI)
        paused = self.upload_groups(ids, ScriptedSession(Response(401)), auth)
        return ids, auth, state_path, paused

    def test_rerun_after_auth_failure_keeps_frozen_metadata_and_applies_shared_edits(self):
        ids, auth, state_path, paused = self.paused_upload_batch()
        self.assertIn("Reconnect", paused["result"]["groups"][0]["error"])
        self.assertEqual(json.loads(state_path.read_text())["metadata"]["description"], "Frozen description")
        # Shared edits while stopped, then the batch continues after reconnecting.
        transport = ScriptedSession(COMPLETE, Response(), START, COMPLETE, Response(), START, COMPLETE, Response())
        job = self.upload_groups(ids, transport, auth,
                           metadata={"description": "Changed while paused", "contains_synthetic_media": True})
        self.assertEqual(job["status"], "completed", job)
        saved = json.loads(state_path.read_text())["metadata"]
        self.assertEqual(saved["description"], "Frozen description")
        self.assertFalse(saved["contains_synthetic_media"])
        created = [call[2]["json"] for call in transport.calls if "json" in call[2]]
        self.assertEqual([row["snippet"]["description"] for row in created], ["Changed while paused"] * 2)
        self.assertTrue(all(row["status"]["containsSyntheticMedia"] for row in created))

    @unittest.expectedFailure  # Gap G3: web marks the job 'failed'; no paused state to resume.
    def test_paused_batch_shared_edits_affect_only_unstarted_sessions(self):
        _, _, _, paused = self.paused_upload_batch()
        # The first batch must pause (not fail) so it can be resumed.
        self.assertEqual(paused["status"], "paused", paused)

    def test_sequential_upload_engine_continues_after_group_failure(self):
        self.import_story()
        ids = self.group_story()
        self.video_ready(ids[:2])
        job = self.upload_groups(ids[:2], ScriptedSession(Response(403), START, COMPLETE, Response()))
        summary = job["result"]["groups"]
        self.assertEqual(summary[0]["status"], "failed")  # 'Failed'
        self.assertEqual(summary[1]["status"], "completed")
        groups = self.state()["groups"]
        self.assertEqual(json.loads(Path(groups[1]["output_dir"], "youtube_upload.json").read_text())["video_id"],
                         "abc123")
        self.assertFalse(Path(groups[2]["output_dir"], "youtube_upload.json").exists())

    def test_video_current_output_skip_and_sequential_subset(self):
        self.import_story()
        ids = self.group_story()
        self.video_ready([ids[1]])
        cover, qr = self.page_inputs()
        job = self.run_job("video", {"group_ids": [ids[1]], "cover_image": cover, "qr_image": qr}, timeout=240)
        self.assertEqual([(row["group_id"], row["status"]) for row in job["result"]["groups"]],
                         [(ids[1], "skipped")])
        groups = self.state()["groups"]
        self.assertEqual([bool(list(Path(group["output_dir"]).glob("*.mp4"))) for group in groups],
                         [False, True, False])

    def test_video_refuses_to_start_without_both_page_inputs(self):
        self.import_story()
        ids = self.group_story()
        self.media_ready(ids[:1])
        cover, qr = self.page_inputs()
        for options in ({}, {"cover_image": cover}):
            self.run_job("video", {"group_ids": [ids[0]], **options}, expect="failed")
            group = self.state()["groups"][0]
            self.assertNotIn("video", group["state"])
            self.assertFalse(list(Path(group["output_dir"]).glob("*.mp4")))
        self.assertTrue(all(job["status"] in {"completed", "failed", "cancelled"}
                            for job in self.client.get("/api/jobs").json()))  # not busy
        self.run_job("video", {"group_ids": [ids[0]], "cover_image": cover, "qr_image": qr}, timeout=240)
        self.assertIn("video", self.state()["groups"][0]["state"])

    def test_video_process_group_refuses_without_inputs_and_records_them_after(self):
        from media.artifacts import sha256_file
        from media.visuals import available_images

        self.import_story()
        ids = self.group_story()
        self.media_ready(ids[:1])
        self.assertEqual(self.state()["groups"][0]["state"]["tts_status"], "Completed")
        refused = self.run_job("video", {"group_ids": [ids[0]]}, expect="failed")
        self.assertNotIn("video", self.state()["groups"][0]["state"])
        cover, qr = self.page_inputs()
        self.run_job("video", {"group_ids": [ids[0]], "cover_image": cover, "qr_image": qr}, timeout=240)
        group = self.state()["groups"][0]
        folder = Path(group["output_dir"])
        record = json.loads((folder / "visuals.json").read_text())
        self.assertEqual(Path(record["cover"]["file"]).name, "cover.png")
        self.assertEqual(record["cover"]["sha256"], sha256_file(folder / record["cover"]["file"]))
        images = available_images(folder)
        self.assertEqual(Path(images["cover"]).read_bytes(), Path(cover).read_bytes())
        self.assertEqual(Path(images["qr"]).read_bytes(), Path(qr).read_bytes())
        self.assertEqual(group["state"]["visuals"]["sources"],
                         {"cover": str(Path(cover).resolve()), "qr": str(Path(qr).resolve())})
        # The core refusal replaces the desktop "Add both page images" wording (as in #120).
        self.assertIn("Missing the 1:1 (left) image for the video pages", refused["result"]["groups"][0]["error"])

    # Logs ----------------------------------------------------------------
    def test_job_logs_remain_available_across_reads(self):
        source = self.import_story(normalize=False)
        jobs = {"import": self.client.get("/api/jobs").json()[0]["id"]}
        jobs["normalize"] = self.run_job("normalize")["id"]
        ids = self.group_story(1)
        jobs["group"] = self.client.get("/api/jobs").json()[0]["id"]
        failed = self.run_job("import", {"paths": [str(source.with_name("không có.txt"))]}, expect="failed")
        jobs["failed import"] = failed["id"]
        self.assertTrue(ids)

        # Every step's own lines stay readable after later steps ran, in order.
        for action, job_id in jobs.items():
            rows = self.logs(job_id)
            self.assertTrue(rows, action)
            self.assertEqual([row["sequence"] for row in rows], list(range(1, len(rows) + 1)))
            self.assertEqual(rows[0]["message"], action.split()[-1])
            self.assertEqual(self.logs(job_id), rows)  # Repeated reads do not consume lines.
        self.assertEqual(self.logs(jobs["group"])[-1]["message"], "Đã hoàn thành")
        failure = self.logs(jobs["failed import"])
        self.assertEqual(failure[-1]["level"], "error")
        self.assertEqual(failure[-1]["message"], failed["error"])

        # Lines written while nobody was reading are returned after the reader's cursor.
        with self.gated_tts(ids[:1]) as job_id:
            seen = self.logs(job_id)
            self.assertTrue(seen)
        rest = self.logs(job_id, after=seen[-1]["sequence"])
        self.assertTrue(rest)
        self.assertEqual(seen + rest, self.logs(job_id))
        self.assertEqual(rest[-1]["message"], "Đã hoàn thành")

    def test_reading_job_logs_preserves_busy_state(self):
        self.import_story()
        ids = self.group_story(1)
        with self.gated_tts(ids[:1]) as job_id:
            before = self.state()
            for _ in range(3):
                self.assertTrue(self.logs(job_id))
            self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "running")
            self.assertEqual([job["id"] for job in self.client.get("/api/jobs").json()
                              if job["status"] in {"queued", "running", "stopping"}], [job_id])
            # Other steps stay disabled while the job runs.
            busy = self.client.post("/api/jobs", json={"action": "normalize", "options": {}})
            self.assertEqual(busy.status_code, 409, busy.text)
            self.assertEqual(self.client.post("/api/sessions/new").status_code, 409)
            self.assertEqual(self.state(), before)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "completed")

    def test_max_log_lines_bounds_the_shared_buffer(self):
        response = self.put_settings({"max_log_lines": 100})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.settings_json()["max_log_lines"], 100)
        job, rows = self.many_line_tts_job(150)
        self.assertEqual(job["status"], "completed", job)
        total = rows[-1]["sequence"]
        self.assertGreater(total, 150)
        self.assertEqual(len(rows), 100)
        self.assertEqual([row["sequence"] for row in rows], list(range(total - 99, total + 1)))
        self.assertEqual(rows[-1]["message"], "Đã hoàn thành")
        self.assertNotIn("tts", [row["message"] for row in rows])  # The first line was dropped.

    # Settings ------------------------------------------------------------
    def test_legacy_translation_settings_are_ignored_safely(self):
        self.close_app()
        (self.config_dir / "config.json").write_text(json.dumps({
            **self.saved_config(),
            "detect_chinese": True,
            "dictionary_enabled": True,
            "dictionary_paths": ["old.tsv"],
            "gemini_api_key": "secret",
            "ai_enabled": True,
            "ai_batch_size": 40,
        }), encoding="utf-8")
        self.open_app()
        settings = self.settings_json()
        self.assertTrue(settings["detect_chinese"])
        for name in ("dictionary_enabled", "dictionary_paths", "gemini_api_key", "ai_enabled", "ai_batch_size"):
            self.assertNotIn(name, settings)
        self.assertNotIn("secret", settings.values())
        rejected = self.put_settings({"gemini_api_key": "secret"})
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertNotIn("secret", rejected.text)
        # The next save writes only supported settings.
        self.assertEqual(self.put_settings({"zero_pad": 3}).status_code, 200)
        self.assertNotIn("gemini_api_key", self.saved_config())
        self.assertNotIn("dictionary_enabled", self.saved_config())

    def test_collects_changed_values(self):
        response = self.put_settings({
            "zero_pad": 4, "quote_mode": "keep", "symbol_map": {"%": " phần trăm "},
            "tts_voice": "vi-VN-HoaiMyNeural",
        })
        self.assertEqual(response.status_code, 200, response.text)
        for updated in (response.json(), self.settings_json(), Settings.load(self.config_dir / "config.json").to_dict()):
            self.assertEqual(updated["zero_pad"], 4)
            self.assertEqual(updated["quote_mode"], "keep")
            self.assertEqual(updated["symbol_map"], {"%": " phần trăm "})
            self.assertEqual(updated["tts_voice"], "vi-VN-HoaiMyNeural")

    def test_blank_saved_voice_uses_default_and_dialog_rejects_empty_edit(self):
        for saved in ("", "   "):
            self.close_app()
            (self.config_dir / "config.json").write_text(
                json.dumps({**self.saved_config(), "tts_voice": saved}), encoding="utf-8")
            self.open_app()
            self.assertEqual(self.settings_json()["tts_voice"], DEFAULT_TTS_VOICE)

        before = (self.config_dir / "config.json").read_bytes()
        response = self.put_settings({"tts_voice": "   "})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("TTS voice cannot be empty", response.json()["detail"])
        self.assertEqual(self.settings_json()["tts_voice"], DEFAULT_TTS_VOICE)
        self.assertEqual((self.config_dir / "config.json").read_bytes(), before)

    def test_step3_title_history_can_be_remembered_and_removed(self):
        self.assertEqual(self.put_settings({"title_history": ["Old Novel"]}).status_code, 200)
        self.assertEqual(self.settings_json()["title_history"][0], "Old Novel")
        self.import_story()
        self.group_story(1, title="New Novel")
        self.assertEqual(self.settings_json()["title_history"], ["New Novel", "Old Novel"])
        self.assertEqual(self.saved_config()["title_history"], ["New Novel", "Old Novel"])

        response = self.put_settings({"title_history": ["Old Novel"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.settings_json()["title_history"], ["Old Novel"])
        self.assertEqual(self.saved_config()["title_history"], ["Old Novel"])

    def test_runtime_ui_settings_are_applied(self):
        response = self.put_settings({"font_size": 13, "max_log_lines": 321})
        self.assertEqual(response.status_code, 200, response.text)
        settings = self.settings_json()
        self.assertEqual((settings["font_size"], settings["max_log_lines"]), (13, 321))
        job, rows = self.many_line_tts_job(330)
        self.assertEqual(job["status"], "completed", job)
        self.assertGreater(rows[-1]["sequence"], 321)
        self.assertEqual(len(rows), 321)
        export = self.run_job("export", {"format": "json"})
        self.assertEqual(Path(export["result"]["path"]).name, "novel_export.json")

    def test_cleaning_settings_affect_step3(self):
        response = self.put_settings({"symbol_map": {"%": " phần trăm "}, "remove_html": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.import_story("Chương 1\n<p>Giá trị 10%</p>", name="Giá trị.txt")
        ids = self.group_story(1, title="Giá trị")
        self.run_job("prepare", {"group_ids": ids})
        plan = self.state()["groups"][0]["state"]["tts_plan"]
        chunk_text = "\n".join(chunk["text"] for chunk in plan["chunks"])

        self.assertNotIn("<p>", chunk_text)
        self.assertIn("10%", chunk_text)  # TTS profile disables global symbol expansion.

    # Step 2 --------------------------------------------------------------
    def test_step2_is_grouping_and_preserves_chinese_text(self):
        self.import_story("Chương 1\n中文 修炼者.", name="Novel.txt", normalize=False)
        self.run_job("normalize")
        self.run_job("edit", {"text": "Chương 1\n中文 修炼者."})
        state = self.state()
        self.assertTrue(state["stages"]["normalize"]["ok"])
        self.assertEqual(state["text"], "Chương 1\n中文 修炼者.")
        self.assertEqual(self.service.document.require_grouping_input(), "Chương 1\n中文 修炼者.")
        preview = self.client.get("/api/grouping", params={"size": 1}).json()
        self.assertFalse(preview.get("error"), preview)
        self.assertEqual(len(preview["groups"]), 1)

        self.group_story(1, title="Novel")
        group = self.state()["groups"][0]
        self.assertTrue(Path(group["output_dir"]).resolve().is_relative_to(Path(state["input_directory"]).resolve()))
        group_text = Path(group["txt_path"]).read_text(encoding="utf-8")
        self.assertIn("中文 修炼者", group_text)

    # TTS failures/progress -------------------------------------------------
    def test_zero_successes_show_root_error_without_merge_dialog(self):
        self.import_story()
        group_id = self.group_story(1)[0]
        clients = FakeTtsClients(make_mp3(self.root / "voice.mp3"), fail=lambda text: ValueError("Invalid voice ''."))
        with tts_clients(clients):
            job = self.run_job("tts", {"group_ids": [group_id]}, expect="failed")
        self.assertTrue(clients.calls)
        row = job["result"]["groups"][0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("Invalid voice", row["error"])
        group = self.group_state()
        # The group's root error is what the TTS screen shows as its alert.
        self.assertIn("Invalid voice", group["state"]["last_error"])
        self.assertEqual(group["state"]["tts_status"], "TTS Incomplete")
        self.assertNotIn("audiobook", group["state"])
        folder = Path(group["output_dir"])
        self.assertFalse((folder / "audiobook.mp3").exists())
        self.assertEqual(list(folder.rglob("*.mp3")), [])
        # Nothing succeeded, so no partial merge is offered or accepted.
        merge = self.run_job("merge_partial", {"group_ids": [group_id], "allow_partial": True}, expect="failed")
        self.assertIn("Partial merge requires both valid audio chunks and missing chunks",
                      merge["result"]["groups"][0]["error"])
        self.assertFalse((folder / "audiobook.mp3").exists())

    def test_failed_chunk_dialog_shows_original_and_failed_part_text(self):
        response = self.client.put("/api/settings", json={"tts_retry_count": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.import_story()
        group_id = self.group_story(1)[0]
        target = "Trời mưa rất to trên núi Thanh Vân"

        def fail(text):
            return TimeoutError("Timeout > 120s") if target in text else None

        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"), fail=fail)):
            job = self.run_job("tts", {"group_ids": [group_id]}, expect="failed")
        failures = self.group_state()["state"]["failures"]
        self.assertEqual(len(failures), 1, failures)
        failure = failures[0]
        self.assertEqual((failure["error_type"], failure["error_message"]), ("TimeoutError", "Timeout > 120s"))
        self.assertIn(target, failure["original_text"])
        self.assertIn(target, failure["failed_part_text"])
        self.assertEqual(job["result"]["groups"][0]["failures"], failures)
        self.assertTrue(any(f"Lỗi đoạn {failure['chunk_number']}: Timeout > 120s" in row["message"]
                            for row in self.logs(job["id"])))
        # Some chunks succeeded, so the explicit partial merge is available.
        self.run_job("merge_partial", {"group_ids": [group_id], "allow_partial": True})
        state = self.group_state()["state"]
        self.assertEqual(state["tts_status"], "Partial")
        self.assertEqual(state["excluded_chunks"], [failure["chunk_number"]])

    def test_worker_progress_reaches_http_job_snapshot(self):
        response = self.client.put("/api/settings", json={"tts_max_concurrency": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.import_story()
        group_id = self.group_story(3)[0]
        total = self.run_job("prepare", {"group_ids": [group_id]})["result"]["groups"][0]["chunk_count"]
        self.assertGreaterEqual(total, 3)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        clients = None

        async def gate(text):
            if len(clients.calls) == total:
                entered.set()
                await asyncio.to_thread(release.wait, 30)

        clients = FakeTtsClients(make_mp3(self.root / "voice.mp3"), gate=gate)
        label = self.group_state()["label"]
        with tts_clients(clients):
            job_id = self.submit("tts", {"group_ids": [group_id]})
            self.assertTrue(entered.wait(30))
            progress = self.client.get(f"/api/jobs/{job_id}").json()["progress"]
            self.assertEqual(progress, {"done": round((total - 1) / total * 1000), "total": 1000,
                                        "message": f"{label}: Đang xử lý đoạn {total}/{total}"})
            messages = [row["message"] for row in self.logs(job_id)]
            self.assertIn(f"{label}: Đã tạo đoạn {total - 1}/{total}", messages)
            self.assertNotIn(f"{label}: Đã tạo đoạn {total}/{total}", messages)
            release.set()
            job = self.wait(job_id)
        self.assertEqual(job["status"], "completed", job)
        messages = [row["message"] for row in self.logs(job_id)]
        created = [message for message in messages if message.startswith(f"{label}: Đã tạo đoạn ")]
        self.assertEqual(created, [f"{label}: Đã tạo đoạn {order}/{total}" for order in range(1, total + 1)])

    # Video inputs/progress -------------------------------------------------
    def test_step4_uses_current_step3_paths_without_upload_controls(self):
        from hashlib import sha256

        self.import_story()
        group_id = self.group_story(1)[0]
        self.media_ready([group_id])
        # A later Step 3 thumbnail replaces the earlier one; Step 4 must use the current file.
        self.media_ready([group_id], thumbnail_color=(200, 160, 20))
        group = self.group_state()
        media = self.service.document.require_step4_outputs(group_id)
        folder = Path(group["output_dir"]).resolve()
        self.assertEqual(group["state"]["thumbnail"]["path"], str(Path(media.thumbnail_path).resolve()))
        self.assertEqual(group["state"]["audiobook"]["path"], str(Path(media.audiobook_path).resolve()))
        self.assertEqual({Path(media.thumbnail_path).resolve().parent, Path(media.audiobook_path).resolve().parent},
                         {folder})
        cover, qr = self.page_inputs()
        # Step 4 takes no separately uploaded thumbnail/audio; it only uses the group's outputs.
        for option in ("thumbnail_path", "audiobook_path"):
            response = self.client.post("/api/jobs", json={"action": "video", "options": {
                "group_ids": [group_id], "cover_image": cover, "qr_image": qr, option: str(self.root / "x")}})
            self.assertEqual(response.status_code, 422, response.text)
        job = self.run_job("video", {"group_ids": [group_id], "cover_image": cover, "qr_image": qr}, timeout=240)
        self.assertIn(f"{group['label']}: Đang kiểm tra encoder FFmpeg thực tế…",
                      [row["message"] for row in self.logs(job["id"])])
        source = self.group_state()["state"]["video"]["source"]
        self.assertEqual(source["thumbnail_sha256"], sha256(Path(media.thumbnail_path).read_bytes()).hexdigest())
        self.assertEqual(source["audiobook_sha256"], sha256(Path(media.audiobook_path).read_bytes()).hexdigest())

    def test_step5_progress_is_visible_and_video_state_invalidates(self):
        from media.video import parse_progress_line
        from pipeline.document import PipelineStateError

        # FFmpeg's progress keys map to the same elapsed/percentage/speed/ETA values.
        state = {}
        for line in ("out_time_us=25000000", "speed=5x"):
            update = parse_progress_line(state, line, 100.0)
        self.assertEqual(update, {"elapsed": 25.0, "percentage": 25.0, "speed": 5.0, "eta": 15.0})

        self.import_story()
        group_id = self.group_story(1)[0]
        self.media_ready([group_id])
        cover, qr = self.page_inputs()
        job = self.run_job("video", {"group_ids": [group_id], "cover_image": cover, "qr_image": qr}, timeout=240)
        label = self.group_state()["label"]
        pattern = re.compile(rf"^{re.escape(label)}: Video: \d+\.\ds / \d+\.\ds · \d+\.\dx · còn \d+\.\ds$")
        self.assertTrue(any(pattern.match(row["message"]) for row in self.logs(job["id"])))
        video = Path(self.group_state()["state"]["video"]["path"])
        self.assertTrue(video.is_file())
        # Recording a new thumbnail withdraws the finished video's authority.
        self.run_job("thumbnail", {"group_ids": [group_id], "image_path": str(self.root / "thumb-source.png")})
        self.assertNotIn("video", self.group_state()["state"])
        with self.assertRaises(PipelineStateError):
            self.service.document.require_step5_outputs(group_id)

    def test_create_video_is_blocked_until_both_page_images_are_added(self):
        self.import_story()
        group_id = self.group_story(1)[0]
        self.media_ready([group_id])
        cover, _ = self.page_inputs()
        folder = Path(self.group_state()["output_dir"])
        for options, missing in (({}, "the 1:1 (left) image"), ({"cover_image": cover}, "the QR (right) image")):
            job = self.run_job("video", {"group_ids": [group_id], **options}, expect="failed")
            self.assertIn(f"Missing {missing} for the video pages", job["result"]["groups"][0]["error"])
            messages = [row["message"] for row in self.logs(job["id"])]
            self.assertFalse(any("Rendering with" in message or "Prepared page" in message for message in messages))
            self.assertNotIn("video", self.group_state()["state"])
            self.assertEqual(list(folder.glob("*.mp4")), [])
            self.assertFalse((folder / "video_timeline.json").exists())

    def test_cancel_during_async_page_preparation_preserves_old_video(self):
        self.import_story(LONG_STORY, "Mưa dài.txt")
        group_id = self.group_story(1, title="Mưa dài")[0]
        self.media_ready([group_id])
        group = self.group_state()
        output = Path(group["output_dir"]) / f"{group['slug']}.mp4"
        self.assertEqual(Path(self.service.document.require_step4_outputs(group_id).video_path).resolve(),
                         output.resolve())
        output.write_bytes(b"previous completed video")
        cover, qr = self.page_inputs()
        job_id = self.submit("video", {"group_ids": [group_id], "cover_image": cover, "qr_image": qr})
        self.wait_for_log(job_id, "Prepared page 1/")
        self.stop(job_id)
        job = self.wait(job_id, timeout=120)
        self.assertEqual(job["status"], "cancelled", job)
        messages = [row["message"] for row in self.logs(job_id)]
        self.assertFalse(any("Rendering with" in message for message in messages), messages)
        pages = [message for message in messages if "Prepared page" in message]
        # Stopped while pages were still being prepared, before any encoder attempt.
        self.assertLess(len(pages), len(group["state"]["successful_orders"]))
        self.assertEqual(output.read_bytes(), b"previous completed video")
        self.assertEqual(list(output.parent.glob(".*.part.mp4")), [])
        self.assertNotIn("video", self.group_state()["state"])

    # YouTube --------------------------------------------------------------
    def test_connect_uses_changed_oauth_settings_without_reentering_tab(self):
        self.youtube_ready()
        with self.fresh_auths() as created:
            first = self.run_job("youtube_connect")
            response = self.client.put("/api/settings", json={"youtube_client_secrets_path": "new-client.json"})
            self.assertEqual(response.status_code, 200, response.text)
            second = self.run_job("youtube_connect")
        self.assertEqual([path for path, _ in created], ["fake.json", "new-client.json"])
        self.assertIsNot(created[1][1], created[0][1])
        self.assertEqual(first["result"]["account"]["channel_id"], "channel1")
        self.assertEqual(second["result"]["account"]["channel_id"], "channel1")

    def test_configured_oauth_without_saved_login_explains_sign_in(self):
        self.youtube_ready()
        ids = self.youtube_videos()
        transport = ScriptedSession()
        with patch.object(FakeAuth, "restore", return_value=None):
            job = self.youtube_upload(ids, transport)
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("Chưa kết nối YouTube", job["error"])
        self.assertIn("kết nối tài khoản Google", job["error"])
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.youtube_state())
        # Connecting remains available and succeeds.
        connected = self.youtube_job("youtube_connect", ScriptedSession())
        self.assertEqual(connected["status"], "completed", connected)
        self.assertEqual(connected["result"]["account"]["email"], "user@example.com")

    def test_group_connection_error_visible_beside_account(self):
        from media.youtube_auth import YouTubeAuthError

        self.youtube_ready()
        with patch.object(FakeAuth, "connect", side_effect=YouTubeAuthError("OAuth test error")):
            job = self.youtube_job("youtube_connect", ScriptedSession())
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(job["error"], "OAuth test error")
        errors = [row["message"] for row in self.logs(job["id"]) if row["level"] == "error"]
        self.assertEqual(errors, ["OAuth test error"])

    def test_connect_without_config_displays_error_dialog(self):
        # The real YouTubeAuth rejects the missing client configuration before
        # any keyring, browser or network access.
        response = self.client.put("/api/settings", json={"youtube_client_secrets_path": ""})
        self.assertEqual(response.status_code, 200, response.text)
        job = self.run_job("youtube_connect", expect=None)
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("Settings", job["error"])
        self.assertIsNone(job["result"])
        # The workspace is idle again: the same action is accepted and fails the same way.
        self.assertEqual(self.run_job("youtube_connect", expect="failed")["error"], job["error"])

    def test_continue_and_direct_navigation_share_automatic_inputs_and_metadata(self):
        self.youtube_ready()
        ids = self.youtube_videos(2)
        first_read = self.state()["groups"][0]
        connected = self.youtube_job("youtube_connect", ScriptedSession())
        account = connected["result"]["account"]
        self.assertEqual(account["email"], "user@example.com")
        self.assertIn("Audiobooks", account["channel_title"])
        # The automatic inputs read before and after the account step are the same saved state.
        self.assertEqual(self.state()["groups"][0], first_read)
        media = self.service.document.require_step5_outputs(ids[0])
        self.assertEqual(Path(media.video_path).resolve(), Path(first_read["state"]["video"]["path"]).resolve())
        self.assertEqual(Path(media.thumbnail_path).parent.resolve(), Path(first_read["output_dir"]).resolve())
        transport = ScriptedSession(START, COMPLETE, Response())
        job = self.youtube_upload(ids[:1], transport)
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(transport.calls[0][2]["json"]["snippet"]["title"], "Bắc Tống | Chương 1")
        self.assertEqual(transport.calls[1][2]["data"], Path(media.video_path).read_bytes())
        self.assertEqual(transport.calls[2][2]["data"], Path(media.thumbnail_path).read_bytes())
        # A changed Step 3 thumbnail makes the old video stale for every entry path.
        image = write_image(self.root / "new-thumb.png", (1600, 900), (10, 200, 90))
        self.run_job("thumbnail", {"group_ids": ids[1:], "image_path": image})
        stale = ScriptedSession()
        job = self.youtube_upload(ids[1:], stale)
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(job["result"]["groups"][0]["status"], "failed", job)
        self.assertEqual(stale.calls, [])
        self.assertFalse(self.youtube_state(1))
        with self.assertRaises(PipelineStateError):
            self.service.document.require_step5_outputs(ids[1])

    def test_progress_completion_copy_url_and_duplicate_confirmation(self):
        self.youtube_ready()
        ids = self.youtube_videos()
        transport = ScriptedSession(START, COMPLETE, Response())
        job = self.youtube_upload(ids, transport)
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(job["progress"]["done"], job["progress"]["total"])
        messages = [row["message"] for row in self.logs(job["id"])]
        self.assertTrue(any("Đang upload YouTube…" in message for message in messages), messages)
        saved = self.youtube_state()
        self.assertEqual(saved["video_id"], "abc123")
        self.assertEqual(saved["video_url"], "https://www.youtube.com/watch?v=abc123")
        media = self.service.document.require_step5_outputs(ids[0])
        self.assertEqual(transport.calls[1][2]["data"], Path(media.video_path).read_bytes())
        self.assertEqual(transport.calls[2][2]["data"], Path(media.thumbnail_path).read_bytes())
        folder = Path(media.output_dir)
        payload = json.loads((folder / "final.json").read_text(encoding="utf-8"))
        self.assertEqual((folder / "final.txt").read_text(encoding="utf-8"), payload["text"])
        self.assertGreater((folder / "audiobook.mp3").stat().st_size, 0)
        # Without confirmation an uploaded group is never uploaded again.
        unconfirmed = ScriptedSession()
        again = self.youtube_upload(ids, unconfirmed)
        self.assertEqual(again["status"], "completed", again)
        self.assertEqual(again["result"]["groups"][0]["status"], "skipped")
        self.assertEqual(unconfirmed.calls, [])

    @unittest.expectedFailure  # Gap G4: backend/validation.py rejects allow_duplicate with 422.
    def test_confirmed_duplicate_upload_creates_new_video(self):
        self.youtube_ready()
        ids = self.youtube_videos()
        self.assertEqual(self.youtube_upload(ids, ScriptedSession(START, COMPLETE, Response()))["status"], "completed")
        # Explicit confirmation creates a new upload (the web sends allow_duplicate).
        self.auth.transport = ScriptedSession(
            START, Response(data={"id": "def456", "status": {"privacyStatus": "private"}}), Response())
        with youtube_auth(self.auth):
            response = self.client.post("/api/jobs", json={"action": "upload", "options": {
                "group_ids": ids, "allow_duplicate": True}})
            self.assertEqual(response.status_code, 202, response.text)
            confirmed = self.wait(response.json()["id"])
        self.assertEqual(confirmed["status"], "completed", confirmed)
        self.assertEqual(confirmed["result"]["groups"][0]["status"], "completed", confirmed)
        self.assertEqual(self.youtube_state()["video_id"], "def456")

    def test_ai_checkbox_uploads_both_values_and_restores_saved_choice(self):
        self.youtube_ready()
        ids = self.youtube_videos(2)
        transport = ScriptedSession(START, COMPLETE, Response(),
                                    START, Response(data={"id": "def456", "status": {"privacyStatus": "private"}}),
                                    Response())
        job = self.youtube_upload(ids, transport, group_metadata={ids[1]: {"contains_synthetic_media": True}})
        self.assertEqual(job["status"], "completed", job)
        payloads = [call[2]["json"] for call in transport.calls if "json" in call[2]]
        self.assertEqual([payload["status"]["containsSyntheticMedia"] for payload in payloads], [False, True])
        for enabled, index in ((False, 0), (True, 1)):
            with self.subTest(enabled=enabled):
                self.assertIs(self.youtube_state(index)["metadata"]["contains_synthetic_media"], enabled)
        # The saved choice is restored after an application restart.
        self.reopen()
        self.assertIs(self.youtube_state(1)["metadata"]["contains_synthetic_media"], True)
        self.assertIs(self.youtube_state(0)["metadata"]["contains_synthetic_media"], False)

    def test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry(self):
        self.youtube_ready()
        ids = self.youtube_videos()
        job = self.youtube_upload(ids, ScriptedSession(START, COMPLETE, Response(403)))
        self.assertEqual(job["status"], "failed", job)
        saved = self.youtube_state()
        self.assertEqual(saved["video_id"], "abc123")
        self.assertFalse(saved["thumbnail_uploaded"])
        self.assertTrue(saved["thumbnail_error"])
        self.assertEqual(job["result"]["groups"][0]["error"], saved["thumbnail_error"])
        retry = ScriptedSession(Response())
        job = self.youtube_job("youtube_retry_thumbnail", retry, group_id=ids[0])
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(len(retry.calls), 1)
        self.assertTrue(self.youtube_state()["thumbnail_uploaded"])
        # Re-entering (application restart) keeps the uploaded video; no second upload.
        self.reopen()
        self.assertEqual(self.youtube_state()["video_id"], "abc123")
        self.assertEqual(self.youtube_state()["status"], "completed")
        unconfirmed = ScriptedSession()
        again = self.youtube_upload(ids, unconfirmed)
        self.assertEqual(again["result"]["groups"][0]["status"], "skipped", again)
        self.assertEqual(unconfirmed.calls, [])

    def test_bad_metadata_never_starts_worker_and_schedule_requires_private(self):
        self.youtube_ready()
        ids = self.youtube_videos()
        transport = ScriptedSession()
        job = self.youtube_upload(ids, transport, metadata={"title": ""})
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("Title", job["result"]["groups"][0]["error"])
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        job = self.youtube_upload(ids, transport, metadata={
            "title": "Scheduled title", "publish_at": future, "privacy": "public"})
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("Private", job["result"]["groups"][0]["error"])
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.youtube_state())

    def test_standalone_resume_preserves_saved_metadata_and_past_schedule(self):
        from media.youtube import UploadMetadata

        self.youtube_ready()
        ids = self.youtube_videos(2)
        group = self.state()["groups"][0]
        folder = Path(group["output_dir"])
        metadata = UploadMetadata(
            "Saved title", publish_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            contains_synthetic_media=True,
        )
        fingerprint = video_fingerprint(Path(group["state"]["video"]["path"]))
        state = {
            "schema_version": 1, "status": "uploading", "channel_id": "channel1",
            "metadata": metadata.__dict__, "session_key": "resume-key",
            "video_fingerprint": fingerprint, "total_bytes": fingerprint["size"], "bytes_sent": 0,
            "video_id": None, "playlist_id": None, "title": metadata.title, "privacy": "private",
        }
        (folder / "youtube_upload.json").write_text(json.dumps(state))
        self.auth.secret_store.set("resume-key", SESSION_URI)
        transport = ScriptedSession(COMPLETE, Response())
        job = self.youtube_upload(ids[:1], transport,
                                  metadata={"title": "Unsaved edit must not replace resumed metadata"})
        self.assertEqual(job["status"], "completed", job)
        saved = self.youtube_state()
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["metadata"], metadata.__dict__)
        first = transport.calls[0]
        self.assertEqual(first[0], "PUT")
        self.assertEqual(first[2]["headers"]["Content-Range"], f"bytes */{state['total_bytes']}")

        # Reusing the saved metadata restores the AI choice, but an explicit new
        # upload still rejects its past publishing date.
        restored = saved["metadata"]
        self.assertTrue(restored["contains_synthetic_media"])
        fresh = ScriptedSession()
        job = self.youtube_upload(ids[1:], fresh, metadata=restored)
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("future", job["result"]["groups"][0]["error"])
        self.assertEqual(fresh.calls, [])

    def test_api_worker_keeps_ui_responsive_and_cancel_saves_session(self):
        self.youtube_ready()
        ids = self.youtube_videos()
        total = Path(self.state()["groups"][0]["state"]["video"]["path"]).stat().st_size
        half = total // 2
        called, release = threading.Event(), threading.Event()
        thread_ids = []

        def slow_chunk(*args):
            thread_ids.append(threading.get_ident())
            called.set()
            release.wait(10)
            return Response(308, headers={"Range": f"bytes=0-{half - 1}"})

        self.auth.transport = ScriptedSession(START, slow_chunk)
        with youtube_auth(self.auth):
            job_id = self.submit("upload", {"group_ids": ids})
            try:
                self.assertTrue(called.wait(10))
                self.assertNotEqual(thread_ids[0], threading.get_ident())
                # The API keeps answering and rejects a second mutation while busy.
                self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "running")
                self.assertEqual(self.client.get("/api/state").status_code, 200)
                busy = self.client.post("/api/jobs", json={"action": "export", "options": {"format": "json"}})
                self.assertEqual(busy.status_code, 409, busy.text)
                self.assertEqual(self.stop(job_id)["status"], "stopping")
            finally:
                release.set()
            job = self.wait(job_id)
        self.assertEqual(job["status"], "cancelled", job)
        folder = Path(self.state()["groups"][0]["output_dir"])
        state = json.loads((folder / "youtube_upload.json").read_text())
        self.assertEqual(state["status"], "cancelled")
        self.assertEqual(state["bytes_sent"], half)
        self.assertEqual(self.youtube_state()["bytes_sent"], half)
        # Idle again: the saved session resumes from the confirmed position.
        transport = ScriptedSession(Response(308, headers={"Range": f"bytes=0-{half - 1}"}), COMPLETE, Response())
        job = self.youtube_upload(ids, transport)
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(transport.calls[0][2]["headers"]["Content-Range"], f"bytes */{total}")
        self.assertEqual(transport.calls[1][2]["headers"]["Content-Range"], f"bytes {half}-{total - 1}/{total}")
        self.assertEqual(self.youtube_state()["video_id"], "abc123")


if __name__ == "__main__":
    unittest.main()

"""Session restart, provenance, atomic persistence and web session restoration tests."""
import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from media.groups import write_groups, save_job_state
from pipeline.document import PipelineDocument, SourceFile, Diagnostic, StageKey
from pipeline.sessions import SessionError, SessionStore, document_to_dict, missing_artifacts
from tests.test_chapter_groups import document_for
from tests import test_youtube_pipeline as youtube_fixture
from tests.web_only_support import FakeTtsClients, WebWorkspaceMixin, make_mp3, tts_clients


class SessionTests(WebWorkspaceMixin, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SessionStore(self.root / "sessions")
        self.settings = Settings(channel_intro_enabled=False)

    def ready_document(self):
        fixture = youtube_fixture.YouTubePipelineTests()
        fixture.root = self.root
        return fixture.ready_document()

    # Web sessions: the real application, JobManager, SessionStore and global config.
    def web(self):
        self.start_workspace()
        self.store = self.service.sessions

    def save(self, ui):
        response = self.client.post("/api/sessions", json={"ui": ui})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def open(self, session_id):
        return self.client.post(f"/api/sessions/{session_id}/open")

    def ready_groups(self):
        self.import_story()
        ids = self.group_story(1)
        self.video_ready(ids[:1])
        return ids

    def test_roundtrip_retains_text_types_and_validated_media(self):
        document = self.ready_document()
        document.source_bytes = b"\xff\x00source"
        document.source_files = [SourceFile("input.txt", text="Original full text")]
        document.diagnostics = [Diagnostic("fixture", message="Tiếng Việt")]
        session_id = self.store.save(document, {}, {"tab": 3})
        restored, _, ui = self.store.load(session_id)
        self.assertEqual(document_to_dict(restored), document_to_dict(document))
        self.assertEqual(restored.source_files[0].text, "Original full text")
        self.assertEqual(restored.require_step5_outputs(), document.require_step5_outputs())
        self.assertEqual(ui["tab"], 3)
        Path(document.video_path).write_bytes(b"changed media")
        from pipeline.document import PipelineStateError
        with self.assertRaises(PipelineStateError):
            restored.require_step5_outputs()

    def test_atomic_failure_preserves_previous_session(self):
        document = PipelineDocument()
        document.original_input_text = "Saved text"
        session_id = self.store.save(document, {}, {"tab": 0})
        document.original_input_text = "New text"
        with patch("media.artifacts.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(SessionError):
                self.store.save(document, {}, {"tab": 1}, session_id)
        restored, _, _ = self.store.load(session_id)
        self.assertEqual(restored.original_input_text, "Saved text")
        self.assertFalse(list(self.store.root.glob("*.tmp")))

    def test_corrupt_sessions_and_traversal_are_rejected(self):
        self.store.root.mkdir()
        (self.store.root / "corrupt.json").write_text("{")
        self.assertEqual(self.store.list_sessions(), [])
        with self.assertRaises(SessionError):
            self.store.load("../escape")
        document = PipelineDocument()
        session_id = self.store.save(document, {}, {"tab": 0})
        path = self.store.root / f"{session_id}.json"
        payload = json.loads(path.read_text())
        payload["ui"]["tab"] = []
        path.write_text(json.dumps(payload))
        with self.assertRaises(SessionError):
            self.store.load(session_id)

    def test_group_snapshot_recovers_newer_completed_job_state(self):
        document = document_for("Chương 1\nA.\nChương 2\nB.", self.root)
        groups = write_groups(document, self.settings, document.job_title, 1)
        session_id = self.store.save(document, {}, {"tab": 2})
        groups[0].state["tts_status"] = "Completed"
        save_job_state(groups[0])
        restored, _, _ = self.store.load(session_id)
        self.assertEqual(restored.chapter_groups[0].state["tts_status"], "Completed")
        self.assertEqual(restored.require_chapter_groups(), document.require_chapter_groups())


    def test_close_and_reopen_at_step4_without_repeating_previous_stages(self):
        self.web()
        default_voice = self.service.settings.tts_voice
        self.ready_groups()
        response = self.client.put("/api/settings", json={"tts_voice": "vi-VN-NamMinhNeural"})
        self.assertEqual(response.status_code, 200, response.text)
        draft = {"screen": "video", "metadata": {"title": "", "description": "Mô tả chưa upload", "contains_synthetic_media": True}}
        session_id = self.save({"tab": 3, "web_draft": draft})
        before = self.state()
        self.close_app()
        self.assertEqual(self.store.list_sessions()[0]["step"], 4)
        # Global account configuration changes while the application is closed.
        settings = Settings.load()
        settings.tts_voice = default_voice
        settings.youtube_client_secrets_path = "current-global-client.json"
        settings.save(settings._loaded_config_path)
        self.open_app()
        response = self.open(session_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/jobs").json(), [])
        restored = self.state()
        self.assertEqual(self.service.settings.tts_voice, "vi-VN-NamMinhNeural")
        self.assertEqual(self.service.settings.youtube_client_secrets_path, "current-global-client.json")
        self.assertEqual((restored["normalized_text"], restored["stages"]), (before["normalized_text"], before["stages"]))
        self.assertEqual(restored["groups"], before["groups"])
        self.assertEqual(restored["missing_artifacts"], [])
        self.assertEqual(restored["ui_state"]["web_draft"], draft)
        audiobook = restored["groups"][0]["state"]["audiobook"]["path"]
        self.assertIn(audiobook, [row["path"] for row in restored["outputs"]])

    def test_multiple_sessions_restore_edited_text_and_group_selection(self):
        self.web()
        self.import_story()
        self.run_job("edit", {"text": "Chương 1\nĐã sửa.\nChương 2\nB."})
        ids = self.group_story(1)
        first_id = self.save({"tab": 3, "web_draft": {"screen": "video", "selected": [ids[1]]}})
        self.assertEqual(self.client.post("/api/sessions/new").status_code, 200)
        self.import_story("A different story\n", name="Khác.txt", normalize=False)
        second_id = self.save({"tab": 0})
        response = self.open(first_id)
        self.assertEqual(response.status_code, 200, response.text)
        state = self.state()
        self.assertEqual(state["normalized_text"], "Chương 1\nĐã sửa.\nChương 2\nB.")
        self.assertEqual(state["ui_state"]["web_draft"]["selected"], [ids[1]])
        self.assertEqual([group["group_id"] for group in state["groups"]], ids)
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(len(self.client.get("/api/sessions").json()), 2)

    def test_missing_media_keeps_text_and_reports_missing_files(self):
        self.web()
        self.ready_groups()
        session_id = self.save({"tab": 3})
        before = self.state()
        audiobook = before["groups"][0]["state"]["audiobook"]["path"]
        self.close_app()
        Path(audiobook).unlink()
        self.open_app()
        response = self.open(session_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/jobs").json(), [])
        state = self.state()
        self.assertEqual(state["original_text"], before["original_text"])
        self.assertIn(audiobook, state["missing_artifacts"])
        self.assertNotIn(audiobook, [row["path"] for row in state["outputs"]])

    def test_busy_session_cannot_be_replaced(self):
        self.web()
        self.import_story()
        ids = self.group_story(1)
        started, release = threading.Event(), threading.Event()

        async def gate(text):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)

        with tts_clients(FakeTtsClients(make_mp3(self.root / "voice.mp3"), gate=gate)):
            job_id = self.submit("tts", {"group_ids": ids[:1]})
            self.assertTrue(started.wait(30))
            for request in (lambda: self.open("0" * 32), lambda: self.client.post("/api/sessions/new")):
                response = request()
                self.assertEqual(response.status_code, 409, response.text)
            self.assertIn("Chương 1: Mưa", self.state()["original_text"])
            release.set()
            self.assertEqual(self.wait(job_id)["status"], "completed")

    def test_failed_save_retains_document_and_previous_session(self):
        self.web()
        self.import_story()
        session_id = self.save({"tab": 1})
        # The edit job autosaves; that saved session is what a failed save must not damage.
        self.run_job("edit", {"text": "Unsaved edits"})
        saved = (self.store.root / f"{session_id}.json").read_bytes()
        with patch("media.artifacts.os.replace", side_effect=OSError("Disk full")):
            response = self.client.post("/api/sessions", json={"ui": {"tab": 2}})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("Disk full", response.json()["detail"])
        state = self.state()
        self.assertEqual((state["normalized_text"], state["session_id"]), ("Unsaved edits", session_id))
        self.assertEqual((self.store.root / f"{session_id}.json").read_bytes(), saved)
        self.assertFalse(list(self.store.root.glob("*.tmp")))

    def test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id(self):
        self.web()
        self.assertEqual(self.client.get("/api/sessions").json(), [])
        self.close_app()
        self.assertEqual(self.store.list_sessions(), [])
        self.open_app()
        self.store = self.service.sessions
        self.import_story(normalize=False)
        session_id = self.state()["session_id"]
        self.assertIsNotNone(session_id)
        self.run_job("normalize")
        self.run_job("edit", {"text": "User edits"})
        restored, settings, _ = self.store.load(session_id)
        self.assertEqual(restored.normalized_text, "User edits")
        self.assertEqual(len(self.store.list_sessions()), 1)
        self.assertNotIn("youtube_client_secrets_path", settings)
        self.assertNotIn("youtube_title_tags", settings)

    def test_reopening_older_session_keeps_latest_uploaded_story_tags(self):
        self.web()
        self.import_story()
        self.service.settings.remember_uploaded_title_tags("Truyện A", ["old"])
        session_id = self.save({"tab": 0})
        self.service.settings.remember_uploaded_title_tags("Truyện A", ["latest"])
        response = self.open(session_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.service.settings.tags_for_uploaded_title("Truyện A"), ["latest"])
        self.assertEqual(self.state()["youtube_tags"]["history"]["Truyện A"], ["latest"])

    def test_reopening_youtube_page_preserves_unuploaded_tag_draft(self):
        self.web()
        self.import_story()
        self.service.settings.remember_uploaded_title_tags("Bắc Tống", ["tag đã upload"])
        draft = {"screen": "youtube", "tagsText": "tag mới chưa upload", "tagsEdited": True,
                 "metadata": {"title": "", "tags": ["tag mới chưa upload"]}}
        session_id = self.save({"tab": 4, "web_draft": draft})
        self.close_app()
        self.open_app()
        response = self.open(session_id)
        self.assertEqual(response.status_code, 200, response.text)
        state = self.state()
        self.assertEqual(state["ui_state"]["web_draft"], draft)
        self.assertEqual(state["ui_state"]["tab"], 4)
        self.assertEqual(state["youtube_tags"]["current"], ["tag đã upload"])


if __name__ == "__main__":
    unittest.main()

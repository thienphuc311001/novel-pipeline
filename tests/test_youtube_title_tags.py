"""Story title/tag reuse across uploads, batches, and application restarts."""
import json
import unittest
from pathlib import Path

from config.settings import Settings
from media.youtube import UploadMetadata
from tests.test_youtube import COMPLETE, SESSION_URI, START, Response, ScriptedSession
from tests.web_only_support import FakeAuth, WebWorkspaceMixin, video_fingerprint, youtube_auth


class UploadedTitleTagTests(WebWorkspaceMixin, unittest.TestCase):
    """Uploads run as real HTTP jobs; only the Google account/transport is fake."""

    def setUp(self):
        self.start_workspace()
        response = self.client.put("/api/settings", json={"youtube_client_secrets_path": "fake.json"})
        self.assertEqual(response.status_code, 200, response.text)
        self.settings = self.service.settings
        self.auth = FakeAuth("fake.json")

    def saved(self):
        return Settings.load(self.config_dir / "config.json")

    def upload(self, group_ids, transport, **options):
        self.auth.transport = transport
        with youtube_auth(self.auth):
            return self.run_job("upload", {"group_ids": list(group_ids), **options}, expect=None)

    def video_groups(self, count=1):
        ids = self.group_story(1)[:count]
        self.video_ready(ids)
        return ids

    def test_completed_upload_saves_story_tags_and_next_video_loads_them(self):
        self.import_story()
        ids = self.video_groups()
        transport = ScriptedSession(START, COMPLETE, Response())
        job = self.upload(ids, transport, metadata={"tags": ["truyện tiên hiệp", "sách nói"]})
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(transport.calls[0][2]["json"]["snippet"]["tags"], ["truyện tiên hiệp", "sách nói"])
        self.assertEqual(self.settings.youtube_title_tags, {"Bắc Tống": ["truyện tiên hiệp", "sách nói"]})
        self.assertIn("Bắc Tống", self.state()["youtube_tags"]["history"])
        self.assertEqual(self.saved().tags_for_uploaded_title("  BẮC   TỐNG "), ["truyện tiên hiệp", "sách nói"])
        # The next document of the same story starts with those tags as its upload default.
        self.import_story()
        state = self.state()
        self.assertEqual((state["title"], state["groups"]), ("Bắc Tống", []))
        self.assertEqual(state["youtube_tags"]["current"], ["truyện tiên hiệp", "sách nói"])

    def test_failure_does_not_save_draft_tags(self):
        self.import_story()
        ids = self.video_groups()
        job = self.upload(ids, ScriptedSession(Response(400)), metadata={"tags": ["tag chưa upload"]})
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(self.settings.youtube_title_tags, {})
        self.assertEqual(self.saved().youtube_title_tags, {})

    @unittest.expectedFailure  # Gap G2: opening a story does not import tags from a completed upload.
    def test_existing_completed_upload_is_imported_when_its_story_is_opened(self):
        self.import_story()
        self.group_story(1)
        folder = Path(self.state()["groups"][0]["output_dir"])
        (folder / "youtube_upload.json").write_text(json.dumps({
            "schema_version": 1, "status": "completed", "video_id": "old123",
            "metadata": {"title": "Tập cũ", "tags": ["tag cũ"]},
        }))
        session = self.client.post("/api/sessions", json={"ui": {}}).json()["id"]
        self.assertEqual(self.client.post("/api/sessions/new").status_code, 200)
        self.assertEqual(self.client.post(f"/api/sessions/{session}/open").status_code, 200)
        # Opening a session replaces the service's Settings object; assert on the live one.
        self.assertEqual(self.service.settings.tags_for_uploaded_title("Bắc Tống"), ["tag cũ"])
        self.assertEqual(self.saved().tags_for_uploaded_title("Bắc Tống"), ["tag cũ"])

    def test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title(self):
        self.settings.remember_uploaded_title_tags("Truyện A", ["tag A"])
        self.settings.remember_uploaded_title_tags("Truyện B", ["tag B"])
        self.import_story()
        ids = self.video_groups()
        history = self.state()["youtube_tags"]["history"]
        self.assertEqual(history["Truyện B"], ["tag B"])
        transport = ScriptedSession(START, COMPLETE, Response())
        job = self.upload(ids, transport, metadata={"tags": history["Truyện B"]})
        self.assertEqual(job["status"], "completed", job)
        snippet = transport.calls[0][2]["json"]["snippet"]
        self.assertEqual(snippet["tags"], ["tag B"])
        self.assertEqual(snippet["title"], "Bắc Tống | Chương 1")

    def test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags(self):
        self.import_story()
        ids = self.video_groups()
        self.settings.remember_uploaded_title_tags("Bắc Tống", ["tag mới"])
        group = self.state()["groups"][0]
        folder = Path(group["output_dir"])
        fingerprint = video_fingerprint(folder / f"{group['slug']}.mp4")
        state_path = folder / "youtube_upload.json"
        state_path.write_text(json.dumps({
            "schema_version": 1, "status": "uploading", "channel_id": "channel1",
            "session_key": "saved-session", "video_id": None,
            "metadata": UploadMetadata("Tập 1", tags=["tag đã gửi"]).__dict__,
            "video_fingerprint": fingerprint, "total_bytes": fingerprint["size"], "bytes_sent": 0,
            "title": "Tập 1", "privacy": "private", "playlist_id": None,
        }))
        self.auth.secret_store.set("saved-session", SESSION_URI)
        # A new shared tag draft must not change a pending upload's frozen metadata.
        transport = ScriptedSession(COMPLETE, Response())
        job = self.upload(ids, transport, metadata={"tags": ["tag mới"]})
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(transport.calls[0][0], "PUT")
        self.assertEqual(transport.calls[0][2]["headers"]["Content-Range"], f"bytes */{fingerprint['size']}")
        self.assertEqual(json.loads(state_path.read_text())["metadata"]["tags"], ["tag đã gửi"])

        self.settings.remember_uploaded_title_tags("Bắc Tống", ["tag mới"])
        state_path.write_text(json.dumps({
            "schema_version": 1, "status": "rejected", "channel_id": "channel1",
            "metadata": {"title": "Rejected", "tags": ["old rejected tag"]},
        }))
        transport = ScriptedSession(START, COMPLETE, Response())
        job = self.upload(ids, transport)
        self.assertEqual(job["status"], "completed", job)
        self.assertEqual(transport.calls[0][2]["json"]["snippet"]["tags"], ["tag mới"])

    def test_group_upload_uses_story_tags_and_records_confirmed_result(self):
        self.import_story()
        ids = self.video_groups(2)
        self.settings.remember_uploaded_title_tags("Bắc Tống", ["chung", "bắc tống"])
        transport = ScriptedSession(START, COMPLETE, Response(), START, COMPLETE, Response())
        job = self.upload(ids, transport)
        self.assertEqual(job["status"], "completed", job)
        created = [call[2]["json"]["snippet"]["tags"] for call in transport.calls if "json" in call[2]]
        self.assertEqual(created, [["chung", "bắc tống"]] * 2)
        # A confirmed video whose follow-up failed still records the tags it was uploaded with.
        folder = Path(self.state()["groups"][0]["output_dir"])
        saved = json.loads((folder / "youtube_upload.json").read_text())
        saved.update(status="partial", thumbnail_uploaded=False,
                     metadata=dict(saved["metadata"], tags=["tag mới"]))
        (folder / "youtube_upload.json").write_text(json.dumps(saved))
        job = self.upload(ids[:1], ScriptedSession(Response(403)))
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(json.loads((folder / "youtube_upload.json").read_text())["video_id"], "abc123")
        self.assertEqual(self.settings.tags_for_uploaded_title("Bắc Tống"), ["tag mới"])
        self.assertEqual(self.saved().tags_for_uploaded_title("Bắc Tống"), ["tag mới"])

    def test_unrelated_stories_keep_separate_tags_and_bad_config_is_ignored(self):
        self.settings.remember_uploaded_title_tags("Truyện A", ["a"])
        self.settings.remember_uploaded_title_tags("Truyện B", ["b"])
        self.settings.remember_uploaded_title_tags("truyện a", ["a2"])
        self.assertEqual(self.settings.tags_for_uploaded_title("TRUYỆN A"), ["a2"])
        self.assertEqual(self.settings.tags_for_uploaded_title("Truyện B"), ["b"])
        self.assertEqual(len(self.settings.youtube_title_tags), 2)
        loaded = Settings.from_dict({"youtube_title_tags": {"bad": "not tags", "valid": ["one"]}})
        self.assertEqual(loaded.youtube_title_tags, {"valid": ["one"]})


if __name__ == "__main__":
    unittest.main()

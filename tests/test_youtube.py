"""Resumable protocol and duplicate/partial-failure tests without YouTube writes."""

import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from media.youtube import (
    DuplicateUploadError, ResumeUncertainError, UploadCancelled,
    UploadMetadata, YouTubeUploader, YouTubeUploadError, load_upload_state,
)
from media.youtube_auth import YouTubeAuthError


class MemorySecrets:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


class Response:
    def __init__(self, code=200, data=None, headers=None):
        self.status_code = code
        self.data = data or {}
        self.headers = headers or {}

    def json(self):
        return self.data


class ScriptedSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected API call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(method, url, kwargs)
        return response


SESSION_URI = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=PRIVATE_SESSION"
START = Response(headers={"Location": SESSION_URI})
COMPLETE = Response(data={"id": "abc123", "status": {"privacyStatus": "private"}})


class YouTubeUploadTests(unittest.TestCase):
    def test_resume_accepts_already_accepted_past_schedule(self):
        metadata = UploadMetadata('Frozen scheduled title', publish_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
        uploader = self.uploader(ScriptedSession(COMPLETE, Response()))
        key = 'resume-key'
        self.secrets.set(key, SESSION_URI)
        state = {'schema_version': 1, 'status': 'uploading', 'channel_id': 'channel', 'metadata': metadata.__dict__,
                 'video_fingerprint': uploader._fingerprint(self.video), 'session_key': key, 'total_bytes': self.video.stat().st_size,
                 'bytes_sent': 0, 'video_id': None, 'playlist_id': None, 'title': metadata.title, 'privacy': 'private'}
        (self.job / 'youtube_upload.json').write_text(json.dumps(state))
        result = uploader.upload(self.video, self.thumbnail, self.job, metadata, 'channel')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['metadata'], metadata.__dict__)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name)
        self.video = self.job / "Novel_1.mp4"
        self.video.write_bytes(b"v" * (256 * 1024 + 13))
        self.thumbnail = self.job / "cover_youtube.jpg"
        self.thumbnail.write_bytes(b"jpeg")
        self.secrets = MemorySecrets()
        self.metadata = UploadMetadata("Bắc Tống | Chương 1", tags=["truyện", "sách nói"])
        self.progress = []
        self.logs = []

    def uploader(self, session, **kwargs):
        return YouTubeUploader(
            session, self.secrets, progress=self.progress.append, log=self.logs.append,
            chunk_size=256 * 1024, retry_delay=0, **kwargs,
        )

    def upload(self, session, **kwargs):
        return self.uploader(session, **kwargs).upload(
            self.video, self.thumbnail, self.job, self.metadata, "channel1"
        )

    def pending(self, session=None):
        session = session or ScriptedSession(START, TimeoutError("secret=" + SESSION_URI))
        with self.assertRaises(YouTubeUploadError):
            self.upload(session, retry_count=0)
        return load_upload_state(self.job)

    def test_full_workflow_chunk_order_metadata_and_duplicate_gate(self):
        session = ScriptedSession(START, Response(308, headers={"Range": "bytes=0-262143"}), COMPLETE, Response())
        state = self.upload(session)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["video_id"], "abc123")
        self.assertTrue(state["thumbnail_uploaded"])
        self.assertEqual(state, load_upload_state(self.job))
        payload = session.calls[0][2]["json"]
        self.assertEqual(payload["snippet"]["title"], self.metadata.title)
        self.assertEqual(payload["status"]["selfDeclaredMadeForKids"], False)
        put_calls = [call for call in session.calls if call[0] == "PUT"]
        self.assertEqual(put_calls[0][2]["headers"]["Content-Range"], "bytes 0-262143/262157")
        self.assertEqual(put_calls[1][2]["headers"]["Content-Range"], "bytes 262144-262156/262157")
        self.assertEqual(self.progress[-1]["percent"], 100)
        self.assertGreaterEqual(self.progress[-1]["speed_bps"], 0)
        self.assertFalse(self.secrets.values)
        self.assertNotIn("PRIVATE_SESSION", (self.job / "youtube_upload.json").read_text())
        with self.assertRaises(DuplicateUploadError):
            self.upload(ScriptedSession())
        duplicate = ScriptedSession(START, COMPLETE, Response())
        new = self.uploader(duplicate).upload(
            self.video, self.thumbnail, self.job, self.metadata, "channel1", allow_duplicate=True
        )
        self.assertEqual(new["prior_uploads"][0]["video_id"], "abc123")

    def test_interrupted_final_response_checks_session_without_second_insert(self):
        session = ScriptedSession(START, TimeoutError("token=SECRET"), COMPLETE, Response())
        state = self.upload(session)
        self.assertEqual(state["video_id"], "abc123")
        self.assertEqual(len([call for call in session.calls if call[0] == "POST" and call[1].endswith("/videos")]), 1)
        self.assertEqual(session.calls[2][2]["headers"]["Content-Range"], "bytes */262157")
        self.assertNotIn("SECRET", " ".join(self.logs))

    def test_resume_uses_server_position_and_secure_saved_session(self):
        self.pending()
        session = ScriptedSession(Response(308, headers={"Range": "bytes=0-262143"}), COMPLETE, Response())
        state = self.upload(session)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(session.calls[0][0], "PUT")
        self.assertEqual(session.calls[1][2]["headers"]["Content-Range"], "bytes 262144-262156/262157")
        self.assertFalse(any(call[1].endswith("/videos") and call[0] == "POST" for call in session.calls))

    def test_resume_expiry_uncertainty_corrupt_state_and_missing_key_block_insert(self):
        self.pending()
        for failure in (Response(404), Response(410), Response(308, headers={"Range": "bytes=0-9999999"})):
            session = ScriptedSession(failure)
            with self.assertRaises(ResumeUncertainError):
                self.upload(session)
            self.assertEqual(len(session.calls), 1)
        self.secrets.values.clear()
        session = ScriptedSession()
        with self.assertRaises(ResumeUncertainError):
            self.upload(session)
        self.assertFalse(session.calls)
        (self.job / "youtube_upload.json").write_text("corrupt", encoding="utf-8")
        with self.assertRaises(YouTubeUploadError):
            self.upload(session)
        self.assertFalse(session.calls)

    def test_unconfirmed_session_start_never_retries_insert(self):
        session = ScriptedSession(TimeoutError("PRIVATE_SECRET"))
        with self.assertRaises(ResumeUncertainError) as raised:
            self.upload(session)
        self.assertNotIn("PRIVATE_SECRET", str(raised.exception))
        self.assertEqual(load_upload_state(self.job)["status"], "uncertain")
        with self.assertRaises(ResumeUncertainError):
            self.upload(session)
        self.assertEqual(len(session.calls), 1)

    def test_cancel_keeps_immediately_saved_chunks_and_resumes(self):
        cancel = threading.Event()

        def first_chunk(*args):
            cancel.set()
            return Response(308, headers={"Range": "bytes=0-262143"})
        session = ScriptedSession(START, first_chunk)
        with self.assertRaises(UploadCancelled):
            self.upload(session, cancel_event=cancel)
        state = load_upload_state(self.job)
        self.assertEqual(state["status"], "cancelled")
        self.assertEqual(state["bytes_sent"], 262144)
        self.assertIn(state["session_key"], self.secrets.values)
        resumed = ScriptedSession(Response(308, headers={"Range": "bytes=0-262143"}), COMPLETE, Response())
        self.assertEqual(self.upload(resumed)["status"], "completed")

    def test_thumbnail_partial_failure_and_retry_only_thumbnail(self):
        session = ScriptedSession(START, COMPLETE, Response(403))
        state = self.upload(session)
        self.assertEqual(state["status"], "partial")
        self.assertEqual(state["video_id"], "abc123")
        self.assertIn("permission", state["thumbnail_error"])
        retry = ScriptedSession(Response())
        state = self.uploader(retry).retry_thumbnail(self.job, self.thumbnail, "channel1")
        self.assertEqual(state["status"], "completed")
        self.assertEqual(len(retry.calls), 1)
        self.assertTrue(retry.calls[0][1].endswith("/thumbnails/set"))

    def test_playlist_failure_and_membership_recovery_preserve_video_id(self):
        self.metadata.playlist_id = "playlist1"
        session = ScriptedSession(START, COMPLETE, Response(), Response(data={"items": []}), TimeoutError("SECRET"))
        state = self.upload(session)
        self.assertTrue(state["thumbnail_uploaded"])
        self.assertTrue(state["playlist_uncertain"])
        retry = ScriptedSession(Response(data={"items": [{"id": "existing-item"}]}))
        state = self.uploader(retry).retry_playlist(self.job, "channel1")
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["video_id"], "abc123")
        self.assertEqual([call[0] for call in retry.calls], ["GET"])

    def test_permanent_playlist_failure_retry_inserts_only_playlist(self):
        self.metadata.playlist_id = "playlist1"
        session = ScriptedSession(START, COMPLETE, Response(), Response(data={"items": []}), Response(403))
        self.assertEqual(self.upload(session)["status"], "partial")
        retry = ScriptedSession(Response(data={"items": []}), Response(data={"id": "item1"}))
        state = self.uploader(retry).retry_playlist(self.job, "channel1")
        self.assertEqual(state["status"], "completed")
        self.assertTrue(all(call[1].endswith("/playlistItems") for call in retry.calls))

    def test_explicit_playlist_retry_recovers_unconfirmed_insert_after_absence_rechecks(self):
        self.metadata.playlist_id = "playlist1"
        session = ScriptedSession(START, COMPLETE, Response(), Response(data={"items": []}), TimeoutError("SECRET"))
        self.assertEqual(self.upload(session)["status"], "partial")
        retry = ScriptedSession(Response(data={"items": []}), Response(data={"items": []}),
                                Response(data={"items": []}), Response(data={"id": "new-item"}))
        state = self.uploader(retry).retry_playlist(self.job, "channel1")
        self.assertEqual(state["status"], "completed")
        self.assertEqual([call[0] for call in retry.calls], ["GET", "GET", "GET", "POST"])
        self.assertFalse(any(call[1].endswith("/videos") for call in retry.calls))

    def test_auth_network_errors_retry_but_reconnect_errors_stop(self):
        session = ScriptedSession(START, YouTubeAuthError("network", "network"), COMPLETE, Response())
        self.assertEqual(self.upload(session)["status"], "completed")
        (self.job / "youtube_upload.json").unlink()
        session = ScriptedSession(START, YouTubeAuthError("bad token SECRET", "reconnect"))
        with self.assertRaisesRegex(YouTubeUploadError, "Reconnect"):
            self.upload(session)
        self.assertEqual(len(session.calls), 2)

    def test_changed_text_channel_metadata_and_lock_prevent_new_upload(self):
        self.pending()
        session = ScriptedSession()
        self.metadata.title = "Changed title"
        with self.assertRaises(YouTubeUploadError):
            self.upload(session)
        self.metadata.title = "Bắc Tống | Chương 1"
        self.video.write_bytes(b"changed")
        with self.assertRaises(ResumeUncertainError):
            self.upload(session)
        with self.assertRaises(YouTubeUploadError):
            self.uploader(session).upload(self.video, self.thumbnail, self.job, self.metadata, "other-channel")
        self.assertFalse(session.calls)
        from media.youtube import _job_lock
        with _job_lock(self.job):
            with self.assertRaises(YouTubeUploadError):
                self.upload(session)

    def test_validation_scheduling_and_transient_retries_are_bounded(self):
        invalid = [UploadMetadata(""), UploadMetadata("x" * 101), UploadMetadata("title", description="á" * 2501),
                   UploadMetadata("title", privacy="bad"), UploadMetadata("title", tags=["x" * 501]),
                   UploadMetadata("title", publish_at="2020-01-01T00:00:00Z"),
                   UploadMetadata("title", privacy="public", publish_at="2099-01-01T00:00:00Z")]
        for item in invalid:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    item.validate()
        schedule = datetime.now(timezone.utc) + timedelta(days=1)
        metadata = UploadMetadata("title", publish_at=schedule.isoformat(), made_for_kids=True)
        self.assertTrue(metadata.payload()["status"]["publishAt"].endswith("Z"))
        self.assertTrue(metadata.payload()["status"]["selfDeclaredMadeForKids"])
        session = ScriptedSession(START, COMPLETE, Response(503), Response(503), Response())
        self.assertEqual(self.upload(session, retry_count=2)["status"], "completed")
        self.assertEqual(len(session.calls), 5)


if __name__ == "__main__":
    unittest.main()

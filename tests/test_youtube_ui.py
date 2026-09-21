"""Headless UI tests with injected account and API clients, no real uploads."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton

from config.settings import Settings
from pipeline.document import PipelineStateError
from tests.test_youtube import COMPLETE, START, MemorySecrets, Response, ScriptedSession
from tests import test_youtube_pipeline as pipeline_fixture
from ui.main_window import MainWindow


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


class YouTubeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        fixture = pipeline_fixture.YouTubePipelineTests()
        fixture.root = self.root
        self.document = fixture.ready_document()
        self.window = MainWindow(Settings(youtube_client_secrets_path="fake.json"))
        self.window.document = self.document
        self.tab = self.window.stage6_widget
        self.tab.auth_factory = FakeAuth
        self.addCleanup(self.window.close)

    def wait_idle(self):
        deadline = time.monotonic() + 5
        while self.tab.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertFalse(self.tab.busy, "YouTube worker did not complete")
        self.app.processEvents()

    def enter(self):
        self.window._continue_to_stage6()
        self.wait_idle()

    def test_continue_and_direct_navigation_share_automatic_inputs_and_metadata(self):
        self.enter()
        self.assertEqual(self.window.tabs.count(), 5)
        self.assertEqual(self.window.tabs.currentIndex(), 4)
        self.assertEqual(self.tab.video_label.text(), self.document.video_path)
        self.assertEqual(self.tab.thumbnail_label.text(), self.document.thumbnail_path)
        self.assertEqual(self.tab.title_edit.text(), "Bắc Tống | Chương 1")
        self.assertEqual(self.tab.account_label.text(), "user@example.com")
        self.assertIn("Audiobooks", self.tab.channel_label.text())
        self.assertEqual([self.tab.privacy_combo.itemText(i) for i in range(3)], ["Private", "Unlisted", "Public"])
        self.assertTrue(self.tab.upload_btn.isEnabled())
        self.assertFalse(any("select" in btn.text().lower() or "save" in btn.text().lower()
                             for btn in self.tab.findChildren(QPushButton)))
        with patch.object(self.window, "_start_video_detection"):
            self.window.tabs.setCurrentIndex(3)
            self.window.tabs.setCurrentIndex(4)
        self.assertEqual(self.tab.video_label.text(), self.document.video_path)
        self.document.set_thumbnail_output(self.document.thumbnail_path)
        with self.assertRaises(PipelineStateError):
            self.tab.enter()

    def test_progress_completion_copy_url_and_duplicate_confirmation(self):
        self.enter()
        self.tab._progress({"bytes_sent": 28, "total_bytes": 54, "percent": 52, "speed_bps": 11800000})
        self.assertEqual(self.tab.progress.value(), 520)
        self.assertIn("/s", self.tab.status_label.text())
        self.tab.auth.transport = ScriptedSession(START, COMPLETE, Response())
        self.tab.upload()
        self.wait_idle()
        self.assertEqual(self.document.youtube_upload_state["video_id"], "abc123")
        job = Path(self.tab.media.output_dir)
        for alias, source in (("final.txt", self.document.step3_artifacts.txt_path),
                              ("final.json", self.document.step3_artifacts.json_path),
                              ("thumbnail.jpg", self.document.thumbnail_path),
                              ("audiobook.mp3", self.document.audiobook_path)):
            self.assertEqual((job / alias).read_bytes(), Path(source).read_bytes())
        self.assertEqual(self.tab.progress.value(), 1000)
        self.assertFalse(self.tab.upload_btn.isEnabled())
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.tab.progress.isVisible())
        self.assertIs(self.tab.progress.parentWidget(), self.tab)
        self.assertTrue(self.tab.again_btn.isEnabled())
        self.assertIn("This job has already been uploaded", self.tab.result.toPlainText())
        self.tab.copy_url()
        self.assertEqual(self.app.clipboard().text(), "https://www.youtube.com/watch?v=abc123")
        calls = len(self.tab.auth.transport.calls)
        with patch("ui.youtube_tab.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            self.tab.upload_again()
        self.assertEqual(len(self.tab.auth.transport.calls), calls)

    def test_partial_thumbnail_failure_retry_keeps_video_and_saved_state_on_reentry(self):
        self.enter()
        self.tab.auth.transport = ScriptedSession(START, COMPLETE, Response(403))
        self.tab.upload()
        self.wait_idle()
        self.assertTrue(self.tab.retry_thumbnail_btn.isEnabled())
        self.assertIn("Thumbnail", self.tab.result.toPlainText())
        self.tab.auth.transport = ScriptedSession(Response())
        self.tab.retry_stage("thumbnail")
        self.wait_idle()
        self.assertEqual(len(self.tab.auth.transport.calls), 1)
        self.assertFalse(self.tab.retry_thumbnail_btn.isEnabled())
        self.tab.enter()
        self.assertFalse(self.tab.upload_btn.isEnabled())
        self.assertEqual(self.tab.state["video_id"], "abc123")

    def test_bad_metadata_never_starts_worker_and_schedule_requires_private(self):
        self.enter()
        self.tab.title_edit.clear()
        self.tab.upload()
        self.assertFalse(self.tab.busy)
        self.assertFalse(self.tab.auth.transport.calls)
        self.assertIn("Title", self.tab.status_label.text())
        self.tab.title_edit.setText("Scheduled title")
        self.tab.schedule_check.setChecked(True)
        self.tab.privacy_combo.setCurrentIndex(2)
        self.tab.upload()
        self.assertFalse(self.tab.busy)
        self.assertIn("Private", self.tab.status_label.text())

    def test_api_worker_keeps_ui_responsive_and_cancel_saves_session(self):
        self.enter()
        Path(self.document.video_path).write_bytes(b"v" * (8 * 1024 * 1024 + 1))
        self.document.set_video_output(self.document.video_path)
        called = threading.Event()
        release = threading.Event()
        thread_ids = []

        def slow_chunk(*args):
            thread_ids.append(threading.get_ident())
            called.set()
            release.wait(3)
            return Response(308, headers={"Range": "bytes=0-8388607"})

        self.tab.auth.transport = ScriptedSession(START, slow_chunk)
        self.tab.upload()
        deadline = time.monotonic() + 3
        while not called.is_set() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertTrue(called.is_set())
        self.assertNotEqual(thread_ids[0], threading.get_ident())
        self.assertFalse(self.window.tabs.isTabEnabled(0))
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        self.app.processEvents()
        self.assertTrue(ticks)
        self.window.close()
        self.assertTrue(self.tab._cancel.is_set())
        release.set()
        self.wait_idle()
        state = json.loads((Path(self.tab.media.output_dir) / "youtube_upload.json").read_text())
        self.assertEqual(state["status"], "cancelled")
        self.assertEqual(state["bytes_sent"], 8388608)
        self.assertTrue(self.window.tabs.isTabEnabled(0))
        self.assertTrue(self.tab.upload_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()

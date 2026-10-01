"""Story title/tag reuse across uploads, batches, and application restarts."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from media.groups import write_groups
from tests import test_youtube_pipeline as pipeline_fixture
from tests.test_chapter_groups import document_for
from tests.test_youtube import COMPLETE, START, Response, ScriptedSession
from tests.test_youtube_ui import FakeAuth
from ui.grouped_pipeline import UploadBatchPanel
from ui.main_window import MainWindow


class UploadedTitleTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings.load(self.root / "config.json")
        self.settings.youtube_client_secrets_path = "fake.json"

    def _document(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        fixture = pipeline_fixture.YouTubePipelineTests()
        fixture.root = folder
        return fixture.ready_document()

    def _wait(self, tab):
        deadline = time.monotonic() + 5
        while tab.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.001)
        self.assertFalse(tab.busy)
        self.app.processEvents()

    def test_completed_upload_saves_story_tags_and_next_video_loads_them(self):
        first = self._document(self.root / "first")
        window = MainWindow(self.settings)
        self.addCleanup(window.close)
        window.document = first
        tab = window.stage6_widget
        tab.auth_factory = FakeAuth
        tab.enter()
        self._wait(tab)
        tab.tags_edit.setText("truyện tiên hiệp, sách nói")
        tab.auth.transport = ScriptedSession(START, COMPLETE, Response())
        tab.upload()
        self._wait(tab)
        self.assertEqual(self.settings.youtube_title_tags, {"Bắc Tống": ["truyện tiên hiệp", "sách nói"]})
        self.assertEqual(tab.saved_titles_combo.findText("Bắc Tống") >= 0, True)
        self.assertEqual(Settings.load(self.root / "config.json").tags_for_uploaded_title("  BẮC   TỐNG "),
                         ["truyện tiên hiệp", "sách nói"])
        second = self._document(self.root / "second")
        window.document = second
        tab.enter()
        self._wait(tab)
        self.assertEqual(tab.tags_edit.text(), "truyện tiên hiệp, sách nói")
        self.assertEqual(tab.title_edit.text(), "Bắc Tống | Chương 1")

    def test_failure_does_not_save_draft_tags(self):
        document = self._document(self.root / "failed")
        window = MainWindow(self.settings)
        self.addCleanup(window.close)
        window.document = document
        tab = window.stage6_widget
        tab.auth_factory = FakeAuth
        tab.enter()
        self._wait(tab)
        tab.tags_edit.setText("tag chưa upload")
        tab.auth.transport = ScriptedSession(Response(400))
        tab.upload()
        self._wait(tab)
        self.assertEqual(self.settings.youtube_title_tags, {})
        self.assertEqual(Settings.load(self.root / "config.json").youtube_title_tags, {})

    def test_existing_completed_upload_is_imported_when_its_story_is_opened(self):
        document = self._document(self.root / "existing")
        Path(document.step3_artifacts.output_dir, "youtube_upload.json").write_text(json.dumps({
            "schema_version": 1, "status": "completed", "video_id": "old123",
            "metadata": {"title": "Tập cũ", "tags": ["tag cũ"]},
        }))
        window = MainWindow(self.settings)
        self.addCleanup(window.close)
        window.document = document
        tab = window.stage6_widget
        tab.auth_factory = FakeAuth
        tab.enter()
        self._wait(tab)
        self.assertEqual(self.settings.tags_for_uploaded_title("Bắc Tống"), ["tag cũ"])
        self.assertEqual(Settings.load(self.root / "config.json").tags_for_uploaded_title("Bắc Tống"), ["tag cũ"])

    def test_saved_titles_picker_can_reuse_another_story_tags_without_changing_video_title(self):
        self.settings.youtube_client_secrets_path = ""
        self.settings.remember_uploaded_title_tags("Truyện A", ["tag A"])
        self.settings.remember_uploaded_title_tags("Truyện B", ["tag B"])
        document = self._document(self.root / "picker")
        window = MainWindow(self.settings)
        self.addCleanup(window.close)
        window.document = document
        tab = window.stage6_widget
        tab.enter()
        title = tab.title_edit.text()
        tab.saved_titles_combo.setCurrentIndex(tab.saved_titles_combo.findData("Truyện B"))
        self.assertEqual(tab.tags_edit.text(), "tag B")
        self.assertEqual(tab.title_edit.text(), title)

    def test_pending_upload_keeps_frozen_tags_and_rejected_upload_uses_story_tags(self):
        document = document_for("Chương 1\nA.\nChương 2\nB.", self.root)
        groups = write_groups(document, self.settings, document.job_title, 1)
        self.settings.remember_uploaded_title_tags("Bắc Tống", ["tag mới"])
        first = groups[0]
        state_path = Path(first.output_dir) / "youtube_upload.json"
        state_path.write_text(json.dumps({
            "schema_version": 1, "status": "uploading", "channel_id": "channel",
            "session_key": "saved-session", "video_id": None,
            "metadata": {"title": "Tập 1", "tags": ["tag đã gửi"]},
        }))
        panel = UploadBatchPanel(lambda: document, self.settings)
        self.addCleanup(panel.close)
        panel.editor.account = {"channel_id": "channel"}
        panel.refresh()
        self.assertEqual(panel.editor.tags_edit.text(), "tag đã gửi")
        panel.check_all(False)
        panel.groups.item(0).setCheckState(Qt.CheckState.Checked)
        captured = []
        panel.process_group = lambda group: (captured.append(panel.batch_metadata[group.group_id]), panel.group_done("Simulated"))
        panel.start_batch()
        self.assertEqual(captured[0].tags, ["tag đã gửi"])

        state_path.write_text(json.dumps({
            "schema_version": 1, "status": "rejected", "channel_id": "channel",
            "metadata": {"title": "Rejected", "tags": ["old rejected tag"]},
        }))
        panel.refresh()
        self.assertEqual(panel.editor.tags_edit.text(), "tag mới")

    def test_group_upload_uses_story_tags_and_records_confirmed_result(self):
        document = document_for("Chương 1\nA.\nChương 2\nB.", self.root)
        groups = write_groups(document, self.settings, document.job_title, 1)
        self.settings.remember_uploaded_title_tags("Bắc Tống", ["chung", "bắc tống"])
        panel = UploadBatchPanel(lambda: document, self.settings)
        self.addCleanup(panel.close)
        panel.editor.account = {"channel_id": "channel"}
        panel.refresh()
        self.assertEqual(panel.editor.tags_edit.text(), "chung, bắc tống")
        panel.check_all(True)
        captured = []
        def process(group):
            captured.append(panel.batch_metadata[group.group_id])
            panel.group_done("Simulated")
        panel.process_group = process
        panel.start_batch()
        deadline = time.monotonic() + 3
        while panel.busy and time.monotonic() < deadline:
            self.app.processEvents()
        self.assertEqual([row.tags for row in captured], [["chung", "bắc tống"]] * 2)
        panel.current_id = groups[0].group_id
        with patch.object(panel, "group_done"):
            panel.upload_completed({"video_id": "abc123", "status": "partial",
                                    "metadata": {"title": "Tập 1", "tags": ["tag mới"]}})
        self.assertEqual(self.settings.tags_for_uploaded_title("Bắc Tống"), ["tag mới"])
        self.assertEqual(Settings.load(self.root / "config.json").tags_for_uploaded_title("Bắc Tống"), ["tag mới"])

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

"""Session restart, provenance, atomic persistence and UI restoration tests."""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from config.settings import Settings
from media.groups import write_groups, save_job_state
from pipeline.document import PipelineDocument, SourceFile, Diagnostic, StageKey
from pipeline.sessions import SessionError, SessionStore, document_to_dict, missing_artifacts
from tests.test_chapter_groups import document_for
from tests import test_youtube_pipeline as youtube_fixture
from ui.main_window import MainWindow


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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

    def window(self):
        window = MainWindow(self.settings.clone(), enable_sessions=True, session_store=self.store)
        self.addCleanup(window.close)
        return window

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
        first = self.window()
        first.document = self.ready_document()
        first._set_job_editors(first.document.job_title, first.document.job_chapter)
        first.tabs.blockSignals(True)
        first.tabs.setCurrentIndex(3)
        first.tabs.blockSignals(False)
        first.settings.tts_voice = "vi-VN-NamMinhNeural"
        first.stage6_widget.description_edit.setPlainText("Mô tả chưa upload")
        first.stage6_widget.ai_check.setChecked(True)
        first.group6.editor.ai_check.setChecked(True)
        self.assertTrue(first.close())
        session_id = first._session_id
        self.assertEqual(self.store.list_sessions()[0]["step"], 4)
        second = self.window()
        second.settings.youtube_client_secrets_path = "current-global-client.json"
        with patch.object(second, "_start_video_detection"), patch.object(second, "_on_normalize") as normalize:
            self.assertTrue(second._open_session(session_id))
        normalize.assert_not_called()
        self.assertEqual(second.tabs.currentIndex(), 3)
        self.assertEqual(second.settings.tts_voice, "vi-VN-NamMinhNeural")
        self.assertEqual(second.settings.youtube_client_secrets_path, "current-global-client.json")
        self.assertEqual(second.document.require_step5_outputs(), first.document.require_step5_outputs())
        self.assertEqual(second.stage6_widget.description_edit.toPlainText(), "Mô tả chưa upload")
        self.assertTrue(second.stage6_widget.ai_check.isChecked())
        self.assertTrue(second.group6.editor.ai_check.isChecked())
        self.assertEqual(second._video_media.audiobook_path, first.document.audiobook_path)

    def test_multiple_sessions_restore_edited_text_and_group_selection(self):
        first = self.window()
        first.document = document_for("Chương 1\nĐã sửa.\nChương 2\nB.", self.root)
        groups = write_groups(first.document, first.settings, first.document.job_title, 1)
        first._set_job_editors(first.document.job_title, "")
        first._refresh_group_panels()
        first.group5.groups.setCurrentRow(1)
        first.group5.groups.item(1).setCheckState(Qt.CheckState.Checked)
        first.tabs.blockSignals(True)
        first.tabs.setCurrentIndex(3)
        first.tabs.blockSignals(False)
        self.assertTrue(first._save_session())
        first_id = first._session_id
        first._apply_session(PipelineDocument(), {}, {})
        first._session_id = None
        first.document.load_original_input("A different story")
        self.assertTrue(first._save_session())
        second_id = first._session_id
        with patch.object(first, "_enter_stage5", return_value=True):
            self.assertTrue(first._open_session(first_id))
        self.assertEqual(first.document.normalized_text, "Chương 1\nĐã sửa.\nChương 2\nB.")
        self.assertEqual(first.group5.selected_id(), groups[1].group_id)
        self.assertEqual(first.group5.checked_ids(), [groups[1].group_id])
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(len(self.store.list_sessions()), 2)

    def test_missing_media_keeps_text_and_reports_missing_files(self):
        window = self.window()
        document = self.ready_document()
        session_id = self.store.save(document, {}, {"tab": 3})
        Path(document.audiobook_path).unlink()
        with patch.object(window, "_enter_stage5") as enter:
            self.assertTrue(window._open_session(session_id))
        enter.assert_not_called()
        self.assertEqual(window.document.original_input_text, document.original_input_text)
        self.assertIn(document.audiobook_path, missing_artifacts(window.document))
        self.assertIn("Thiếu", window.session_status.text())

    def test_busy_session_cannot_be_replaced(self):
        window = self.window()
        window.document.original_input_text = "Work in progress"
        with patch.object(window, "_session_busy", return_value=True):
            self.assertFalse(window._open_session("0" * 32))
        self.assertEqual(window.document.original_input_text, "Work in progress")

    def test_failed_save_prevents_close_and_retains_document(self):
        window = self.window()
        window.document.original_input_text = "Unsaved edits"
        with patch.object(self.store, "save", side_effect=SessionError("Disk full")), patch.object(window, "_error") as error:
            self.assertFalse(window.close())
        error.assert_called_once_with("Disk full")
        self.assertEqual(window.document.original_input_text, "Unsaved edits")

    def test_empty_startup_does_not_create_sessions_and_autosave_updates_one_id(self):
        window = self.window()
        window._autosave_session()
        self.assertEqual(self.store.list_sessions(), [])
        window.document.original_input_text = "Story"
        window._autosave_session()
        session_id = window._session_id
        window.document.normalized_text = "User edits"
        window._autosave_session()
        restored, settings, _ = self.store.load(session_id)
        self.assertEqual(restored.normalized_text, "User edits")
        self.assertEqual(len(self.store.list_sessions()), 1)
        self.assertNotIn("youtube_client_secrets_path", settings)
        self.assertNotIn("youtube_title_tags", settings)

    def test_reopening_older_session_keeps_latest_uploaded_story_tags(self):
        window = self.window()
        window.document.original_input_text = "Story A"
        window.settings.remember_uploaded_title_tags("Truyện A", ["old"])
        self.assertTrue(window._save_session())
        session_id = window._session_id
        window.settings.remember_uploaded_title_tags("Truyện A", ["latest"])
        self.assertTrue(window._open_session(session_id))
        self.assertEqual(window.settings.tags_for_uploaded_title("Truyện A"), ["latest"])

    def test_reopening_youtube_page_preserves_unuploaded_tag_draft(self):
        first = self.window()
        first.document = self.ready_document()
        first.settings.youtube_title_tags = {"Bắc Tống": ["tag đã upload"]}
        first.stage6_widget.tags_edit.setText("tag mới chưa upload")
        first.tabs.blockSignals(True)
        first.tabs.setCurrentIndex(4)
        first.tabs.blockSignals(False)
        self.assertTrue(first._save_session())
        second = self.window()
        second.settings.youtube_title_tags = {"Bắc Tống": ["tag đã upload"]}
        self.assertTrue(second._open_session(first._session_id))
        self.assertEqual(second.stage6_widget.tags_edit.text(), "tag mới chưa upload")


if __name__ == "__main__":
    unittest.main()

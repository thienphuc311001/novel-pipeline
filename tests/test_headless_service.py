"""Consumer-visible workspace invariants shared by CLI and web."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from config.settings import Settings
from pipeline.document import PipelineStateError
from pipeline.service import PipelineService


class HeadlessWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict("os.environ", {"NOVEL_PIPELINE_CONFIG_DIR": str(self.root / "config")})
        environment.start()
        self.addCleanup(environment.stop)
        self.service = PipelineService(Settings.load())
        self.input = self.root / "story.txt"
        self.input.write_text("Chương 1: Mưa\nTrời mưa.\n\nChương 2\nTa là ai?\n\nChương 3\nNàng đi rồi.\n", encoding="utf-8")

    def perform(self, action, **options):
        return self.service.perform(action, options, cancel_event=Event(), progress=lambda *_: None)

    def load_normalized(self):
        self.perform("import", paths=[str(self.input)])
        self.perform("normalize")

    def test_failed_import_retains_editable_workspace_and_reports_missing_path(self):
        self.load_normalized()
        original = self.service.document
        with self.assertRaisesRegex(PipelineStateError, "missing.txt"):
            self.perform("import", paths=[str(self.root / "missing.txt")])
        self.assertIs(self.service.document, original)
        self.assertIn("Trời mưa", self.service.document.require_grouping_input())

    def test_edits_invalidate_authority_without_deleting_previous_outputs(self):
        self.load_normalized()
        self.perform("group", title="Truyện", size=2)
        files = [Path(group.txt_path) for group in self.service.document.chapter_groups]
        edited = self.service.document.normalized_text.replace("Trời mưa", "Mây tan")
        self.perform("edit", text=edited)
        self.assertEqual(self.service.document.require_grouping_input(), edited)
        with self.assertRaisesRegex(PipelineStateError, "Create chapter group"):
            self.service.document.require_chapter_groups()
        self.assertTrue(all(path.is_file() for path in files))
        self.perform("group", title="Truyện", size=2)
        merged = "".join(Path(group.txt_path).read_text(encoding="utf-8") for group in self.service.document.chapter_groups)
        self.assertEqual(merged, edited)

    def test_numeric_confirmation_belongs_to_exact_selected_size(self):
        self.input.write_text("Chương 1\nMột.\nChương 3\nBa.\nChương 5\nNăm.\n", encoding="utf-8")
        self.load_normalized()
        preview = self.service.preview_grouping(2)
        self.assertTrue(preview["requires_numeric_boundaries"])
        with self.assertRaisesRegex(PipelineStateError, "current user confirmation"):
            self.perform("group", title="Truyện", size=4, method="numeric_boundaries",
                         confirmation_fingerprint=preview["confirmation_fingerprint"])
        self.perform("group", title="Truyện", size=2, method="numeric_boundaries",
                     confirmation_fingerprint=preview["confirmation_fingerprint"])
        self.assertEqual([group.range_label for group in self.service.document.chapter_groups], ["1-2", "3-4", "5"])

    def test_session_restores_story_settings_not_global_account_configuration(self):
        self.load_normalized()
        self.service.settings.chapter_prefix = "Hồi {n}"
        self.service.settings.youtube_client_secrets_path = "/previous/account.json"
        session_id = self.service.save_session({"tab": 2, "web_group_size": 10})
        self.service.settings.chapter_prefix = "Chương {n}"
        self.service.settings.youtube_client_secrets_path = "/current/account.json"
        state = self.service.open_session(session_id)
        self.assertEqual(self.service.settings.chapter_prefix, "Hồi {n}")
        self.assertEqual(self.service.settings.youtube_client_secrets_path, "/current/account.json")
        self.assertEqual(state["ui_state"]["web_group_size"], 10)
        self.assertEqual(state["normalized_text"], self.service.document.normalized_text)

    def test_downloads_exclude_unrelated_and_symlinked_job_files(self):
        self.load_normalized()
        self.perform("group", title="Truyện", size=20)
        group = self.service.document.chapter_groups[0]
        secret = self.root / "secret.json"
        secret.write_text('{"secret":"private"}', encoding="utf-8")
        folder = Path(group.output_dir)
        (folder / "unrelated.json").write_text("{}", encoding="utf-8")
        (folder / "tts_overrides.json").symlink_to(secret)
        paths = {row["path"] for row in self.service.output_files()}
        self.assertIn(str(Path(group.txt_path).resolve()), paths)
        self.assertNotIn(str(secret.resolve()), paths)
        self.assertNotIn(str((folder / "unrelated.json").resolve()), paths)

    def test_export_respects_encoding_filename_and_archive_layout_settings(self):
        import json
        import zipfile
        self.load_normalized()
        self.perform("group", title="Truyện", size=2)
        self.service.settings.filename_template = "reader_{tag}.json"
        self.service.settings.export_encoding = "utf-16"
        text = self.service.document.require_grouping_input()
        txt = Path(self.perform("export", format="txt")["path"])
        self.assertEqual(txt.name, "reader_export.txt")
        self.assertEqual(txt.read_text(encoding="utf-16"), text)
        exported = Path(self.perform("export", format="json")["path"])
        self.assertEqual(json.loads(exported.read_text(encoding="utf-16"))["text"], text)
        for nested in (False, True):
            with self.subTest(nested=nested):
                self.service.settings.zip_folder_per_range = nested
                zipped = self.perform("export", format="zip")["path"]
                with zipfile.ZipFile(zipped) as archive:
                    for group in self.service.document.chapter_groups:
                        name = f"{group.slug}/final.txt" if nested else f"{group.slug}.txt"
                        self.assertEqual(archive.read(name), Path(group.txt_path).read_bytes())

    def test_invalid_settings_leave_persisted_configuration_untouched(self):
        self.service.settings.save()
        path = self.root / "config" / "config.json"
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.update_settings({"min_chunk_chars": 1000, "max_chunk_chars": 700})
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.service.update_settings({"dictionary_enabled": True})


if __name__ == "__main__":
    unittest.main()

"""Offscreen sequential queues, progress, failure recovery, frozen uploads."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from config.settings import Settings
from media.groups import write_groups, save_job_state, edit_failed_chunk
from media.tts import TtsProcessor
from media.video import VideoCapabilities, EncoderCandidate, AudioProbe
from pipeline.document import PipelineStateError
from ui.main_window import MainWindow
from ui.grouped_pipeline import GroupBatchPanel, TtsBatchPanel, UploadBatchPanel, VideoBatchPanel
from tests.test_chapter_groups import document_for, numeric_source
from tests.test_youtube import Response, ScriptedSession, MemorySecrets
from media.youtube import UploadMetadata, YouTubeUploader, YouTubeUploadError


class GroupBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.settings = Settings()
        self.doc = document_for('Preamble.\nChương 1\nA.\nChương 2\nB.\nChương 3\nC.', self.root)
        self.groups = write_groups(self.doc, self.settings, self.doc.job_title, 1)

    def wait_finished(self, panel):
        for _ in range(300):
            QApplication.processEvents()
            if not panel.busy:
                return
            QTest.qWait(10)
        self.fail('Batch did not stop')

    def test_step3_active_ui_creates_groups_not_tts(self):
        window = MainWindow(self.settings)
        window.document = self.doc
        window._set_job_editors('Bắc Tống', '')
        window.stage3_group_size.setCurrentIndex(0)
        self.assertEqual(window._selected_group_size(), 10)
        self.assertIn('Detected chapters: 3', window.stage3_detection_label.text())
        with patch.object(Settings, 'save', return_value=self.root / 'config.json'), patch('cleaning.textclean.clean_text', side_effect=AssertionError('Forbidden in Step 3')):
            window.stage3_create_groups_btn.click()
        self.assertEqual(len(self.doc.chapter_groups), 1)
        self.assertEqual(self.doc.chunks, [])
        window._continue_to_stage4()
        self.assertEqual(window.stage4_stack.currentWidget(), window.group4)
        self.assertFalse(window.group4.checked_ids())
        self.assertIn('Chương 1', window.group4.first_chapter.toPlainText())
        window.close()

    def test_step3_numeric_boundary_confirmation_and_unavailable_boundary(self):
        # 620 is absent but 621 is a reliable group start, so cancellation
        # must not create files and approval must use the numeric labels.
        numeric_doc = document_for(numeric_source({620}), self.root)
        window = MainWindow(self.settings)
        window.document = numeric_doc
        window._set_job_editors('Bắc Tống', '')
        window.stage3_group_size.setCurrentIndex(1)
        window._refresh_group_preview()
        self.assertIn('Some chapter numbers are missing.', window.stage3_output.toPlainText())
        self.assertIn('601-620', window.stage3_output.toPlainText())
        with patch.object(window, '_confirm_numeric_grouping', return_value=False), patch.object(Settings, 'save', return_value=self.root / 'config.json'):
            window._on_create_group_files()
        self.assertFalse(numeric_doc.chapter_groups)
        with patch.object(window, '_confirm_numeric_grouping', return_value=True), patch.object(Settings, 'save', return_value=self.root / 'config.json'):
            window._on_create_group_files()
        self.assertEqual([group.range_label for group in numeric_doc.chapter_groups],
                         ['601-620', '621-640', '641-660', '661-680', '681-700'])
        window.close()

        unavailable_doc = document_for(numeric_source({621}), self.root)
        window = MainWindow(self.settings)
        window.document = unavailable_doc
        window._set_job_editors('Bắc Tống', '')
        window.stage3_group_size.setCurrentIndex(1)
        window._refresh_group_preview()
        self.assertIn('Missing required group-start heading', window.stage3_output.toPlainText())
        self.assertFalse(window.stage3_create_groups_btn.isEnabled())
        window.close()

    def test_defaults_and_select_all_subset_snapshot(self):
        class Panel(GroupBatchPanel):
            def process_group(inner, group):
                inner.visited.append((group.group_id, inner.batch_settings.tts_voice))
                inner.update_progress(.5, 'halfway')
                inner.group_done('Completed')
        panel = Panel(lambda: self.doc, self.settings)
        panel.visited = []
        panel.enter()
        self.assertEqual(panel.checked_ids(), [])
        panel.check_all(True)
        panel.groups.item(1).setCheckState(Qt.CheckState.Unchecked)
        panel.start_batch()
        self.settings.tts_voice = 'modified after start'
        self.wait_finished(panel)
        self.assertEqual([row[0] for row in panel.visited], [self.groups[0].group_id, self.groups[2].group_id])
        self.assertTrue(all(row[1] == 'vi-VN-HoaiMyNeural' for row in panel.visited))
        self.assertEqual(panel.overall_progress.value(), 1000)
        panel.check_all(False)
        self.assertFalse(panel.checked_ids())

    def test_group_failure_continues_cancel_stops_future_groups(self):
        class Panel(GroupBatchPanel):
            def process_group(inner, group):
                inner.visited.append(group.group_id)
                if len(inner.visited) == 1:
                    raise RuntimeError('Group-specific failure')
                inner.cancel()
                inner.group_done('Cancelled')
        panel = Panel(lambda: self.doc, self.settings)
        panel.visited = []
        panel.enter()
        panel.check_all(True)
        panel.start_batch()
        self.wait_finished(panel)
        self.assertEqual(len(panel.visited), 2)
        self.assertIn('Group-specific failure', panel.result.toPlainText())

    def test_tts_incomplete_continues_and_resume_keeps_canonical_files(self):
        panel = TtsBatchPanel(lambda: self.doc, self.settings)
        panel.enter()
        before = [Path(g.txt_path).read_bytes() for g in self.groups]
        calls = []
        class Client:
            def __init__(inner, text):
                inner.text = text
            async def save(inner, path):
                calls.append(inner.text)
                if 'A.' in inner.text:
                    raise RuntimeError('service error')
                Path(path).write_bytes(b'audio')
        original = panel.processor_for
        def factory(group, settings):
            processor = original(group, settings)
            processor.client_factory = lambda text, voice: Client(text)
            processor.retry_count = processor.fallback_retry_count = 1
            processor._ffmpeg_concat = lambda inputs, output: Path(output).write_bytes(b''.join(Path(p).read_bytes() for p in inputs))
            return processor
        panel.processor_for = factory
        panel.check_all(True)
        panel.start_batch()
        self.wait_finished(panel)
        self.assertEqual([g.state['tts_status'] for g in self.groups], ['TTS Incomplete', 'Completed', 'Completed'])
        self.assertFalse(Path(self.groups[0].output_dir, self.groups[0].slug + '_audiobook.mp3').exists())
        self.assertTrue(self.groups[0].state['failures'])
        self.assertEqual(before, [Path(g.txt_path).read_bytes() for g in self.groups])
        count = len(calls)
        panel.start_batch([self.groups[1].group_id])
        self.wait_finished(panel)
        self.assertEqual(len(calls), count)
        self.assertIn('TTS Incomplete', panel.status_for(self.groups[0]))
        first = self.groups[0]
        failed_order = first.state['failures'][0]['chunk_number']
        edit_failed_chunk(self.doc, first.group_id, self.settings, failed_order, 'Corrected speech.')
        count = len(calls)
        panel.start_batch([first.group_id])
        self.wait_finished(panel)
        self.assertEqual(first.state['tts_status'], 'Completed')
        self.assertEqual(calls[count:], ['Corrected speech.'])
        self.assertEqual(before[0], Path(first.txt_path).read_bytes())

    def test_zero_audio_partial_merge_rejected_without_dialog(self):
        panel = TtsBatchPanel(lambda: self.doc, self.settings)
        panel.enter()
        with patch.object(QMessageBox, 'question', side_effect=AssertionError('No audio must not offer merge')):
            panel.merge_partial()
        self.assertIn('valid audio', panel.status.text())

    def test_partial_merge_is_explicit_and_records_missing_numbers(self):
        from media.artifacts import atomic_write_json, sha256_text
        panel = TtsBatchPanel(lambda: self.doc, self.settings)
        panel.enter()
        group = self.groups[0]
        original = panel.processor_for
        def factory(g, settings):
            processor = original(g, settings)
            processor._ffmpeg_concat = lambda inputs, output: Path(output).write_bytes(b'partial mp3')
            return processor
        panel.processor_for = factory
        processor = factory(group, self.settings)
        class Client:
            def __init__(self, text): self.text = text
            async def save(self, path):
                if self.text != processor.chunks[0].text:
                    raise RuntimeError('missing')
                Path(path).write_bytes(b'audio')
        processor.client_factory = lambda text, voice: Client(text)
        processor.retry_count = 1
        processor.run()
        self.assertGreater(len(processor.chunks), 1)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            panel.merge_partial()
        self.assertFalse(Path(group.output_dir, 'audiobook.mp3').exists())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            panel.merge_partial()
            self.wait_finished(panel)
        self.assertEqual(group.state['tts_status'], 'Partial')
        self.assertEqual(group.state['excluded_chunks'], list(range(2, len(processor.chunks) + 1)))
        manifest = json.loads(processor.manifest_path.read_text())
        self.assertTrue(manifest['partial_audiobook'])
        self.assertEqual(manifest['excluded_chunks'], group.state['excluded_chunks'])

    def test_each_highlighted_group_uses_its_own_thumbnail_regardless_of_checks(self):
        from PIL import Image
        panel = TtsBatchPanel(lambda: self.doc, self.settings)
        panel.enter()
        panel.check_all(True)
        for index, color in ((0, 'red'), (2, 'blue')):
            cover = self.root / f'{color}.png'
            Image.new('RGB', (400, 600), color).save(cover)
            panel.groups.setCurrentRow(index)
            with patch('ui.grouped_pipeline.QFileDialog.getOpenFileName', return_value=(str(cover), '')):
                panel.select_cover()
            self.assertEqual(self.groups[index].state['thumbnail_source'], str(cover))
        for group, expected in ((self.groups[0], (254, 0, 0)), (self.groups[2], (0, 0, 254))):
            with Image.open(Path(group.output_dir) / 'thumbnail.jpg') as thumbnail:
                self.assertEqual(thumbnail.size, (1280, 720))
                self.assertEqual(thumbnail.format, 'JPEG')
                self.assertEqual(thumbnail.getpixel((10, 10)), expected)
            self.assertIn('thumbnail', group.state)
        self.assertFalse(Path(self.groups[1].output_dir, 'thumbnail.jpg').exists())
        panel.groups.setCurrentRow(1)
        self.assertTrue(panel.thumbnail.pixmap().isNull())
        self.assertIn('No thumbnail selected', panel.thumbnail.text())
        panel.check_all(False)
        with patch('ui.grouped_pipeline.QFileDialog.getOpenFileName', return_value=(str(cover), '')):
            panel.select_cover()
        self.assertIn('thumbnail', self.groups[1].state)
        # The selected images and previews survive a matching restore.
        from media.groups import restore_groups
        restored = document_for(self.doc.require_grouping_input(), self.root)
        restore_groups(restored, self.settings, self.doc.job_title, 1)
        self.assertEqual(restored.chapter_groups[0].state['thumbnail_source'], str(self.root / 'red.png'))
        self.assertEqual(restored.chapter_groups[2].state['thumbnail_source'], str(self.root / 'blue.png'))

    def test_damaged_group_does_not_block_entry_or_other_batch_jobs(self):
        class Panel(GroupBatchPanel):
            def process_group(inner, group):
                inner.visited.append(group.group_id)
                inner.group_done('Completed')
        panel = Panel(lambda: self.doc, self.settings)
        panel.visited = []
        Path(self.groups[1].txt_path).write_bytes(b'changed')
        panel.enter()
        panel.check_all(True)
        panel.start_batch()
        self.wait_finished(panel)
        self.assertEqual(panel.visited, [self.groups[0].group_id, self.groups[2].group_id])
        self.assertIn('externally modified', panel.summary[1])
        self.assertEqual(len(panel.summary), 3)

    def test_step3_can_delete_any_group_and_refresh_later_stages(self):
        window = MainWindow(self.settings)
        window.document = self.doc
        Path(self.groups[2].txt_path).write_bytes(b'changed')
        window._refresh_group_panels()
        with patch.object(window, '_error', side_effect=AssertionError('A damaged job must not block Step 4')):
            window._continue_to_stage3()
        self.assertEqual(window.tabs.currentIndex(), 2)
        panel = window.group4
        panel.groups.setCurrentRow(2)
        self.assertTrue(panel.first_chapter.toPlainText() == '')
        self.assertTrue(panel.thumbnail.pixmap().isNull())
        self.assertFalse(panel.checked_ids())
        panel.delete_btn.click()
        for stage in (window.group4, window.group5, window.group6):
            self.assertEqual(stage.groups.count(), 2)
            self.assertNotIn(self.groups[2].group_id, [stage.groups.item(i).data(Qt.ItemDataRole.UserRole) for i in range(2)])
        self.assertTrue(Path(self.groups[2].txt_path).exists())
        self.assertEqual(self.doc.require_chapter_groups(), self.doc.chapter_groups)
        window.group6.editor.media = object()
        window.group6.editor.state = {'video_id': 'old-group'}
        while panel.groups.count():
            panel.delete_btn.click()
        self.assertEqual(window.group5.groups.count(), 0)
        self.assertEqual(window.group6.groups.count(), 0)
        self.assertIsNone(window.group6.editor.media)
        self.assertFalse(window.group6.editor.state)
        self.assertEqual(window.group6.editor.thumbnail_label.text(), '—')
        self.assertFalse(panel.cover_btn.isEnabled())
        self.assertFalse(panel.delete_btn.isEnabled())
        self.assertTrue(panel.first_chapter.toPlainText() == '')
        self.assertEqual(window.stage4_stack.currentWidget(), panel)
        with patch.object(window, '_error', side_effect=AssertionError('Empty group management remains accessible')):
            window._continue_to_stage3()
        window.close()

    def test_step4_busy_blocks_image_selection_and_group_deletion(self):
        panel = TtsBatchPanel(lambda: self.doc, self.settings)
        panel.enter()
        panel.running = True
        panel.set_busy(True)
        self.assertFalse(panel.cover_btn.isEnabled())
        self.assertFalse(panel.delete_btn.isEnabled())
        with patch('ui.grouped_pipeline.QFileDialog.getOpenFileName', side_effect=AssertionError('No dialog while busy')):
            panel.select_cover()
            panel.delete_selected_group()
        self.assertEqual(len(self.doc.chapter_groups), 3)
        panel.running = False
        panel.set_busy(False)

    def test_progress_visible_and_busy_blocks_other_stages(self):
        window = MainWindow(self.settings)
        window.document = self.doc
        window._refresh_group_panels()
        window.show()
        window.tabs.setCurrentIndex(3)
        window.group4.selection = [g.group_id for g in self.groups]
        window.group4.update_progress(.5, 'TTS chunks: 5 / 10')
        self.assertEqual(window.group4.progress.value(), 500)
        self.assertEqual(window.group4.overall_progress.value(), 167)
        self.assertFalse(window.group4.progress.isHidden())
        window._set_group_batch_busy(3, True)
        self.assertFalse(window.load_btn.isEnabled())
        self.assertFalse(window.tabs.isTabEnabled(2))
        self.assertFalse(window.tabs.isTabEnabled(5))
        window._set_group_batch_busy(3, False)
        window.close()

    def test_upload_metadata_frozen_individually_completed_skipped(self):
        panel = UploadBatchPanel(lambda: self.doc, self.settings)
        panel.editor.account = {'channel_id': 'channel'}
        panel.refresh()
        frozen = UploadMetadata('Frozen title', description='saved')
        first = self.groups[0]
        Path(first.output_dir, 'youtube_upload.json').write_text(json.dumps({'schema_version': 1, 'status': 'completed', 'video_id': 'abc123', 'channel_id': 'channel', 'metadata': frozen.__dict__}))
        panel.editor.description_edit.setPlainText('New shared description')
        panel.titles[self.groups[1].group_id] = 'Individual second title'
        captured = []
        original = panel.process_group
        def process(group):
            captured.append(panel.batch_metadata[group.group_id])
            if group is first:
                original(group)
            else:
                panel.group_done('Simulated upload')
        panel.process_group = process
        panel.check_all(True)
        panel.start_batch()
        self.wait_finished(panel)
        self.assertEqual(captured[0].title, 'Frozen title')
        self.assertEqual(captured[0].description, 'saved')
        self.assertEqual(captured[1].title, 'Individual second title')
        self.assertEqual(captured[1].description, 'New shared description')
        self.assertIn('already uploaded', panel.result.toPlainText())
        self.assertIn('using saved metadata', panel.status_for(first))

    def test_auth_failure_pauses_remaining_queue(self):
        panel = UploadBatchPanel(lambda: self.doc, self.settings)
        panel.editor.account = {'channel_id': 'channel'}
        class Auth:
            account = None
        panel.editor.auth = Auth()
        panel.refresh()
        panel.process_group = lambda group: panel.group_failed('YouTube authentication failed')
        panel.check_all(True)
        panel.start_batch()
        self.assertTrue(panel.paused)
        self.assertFalse(panel.running)
        self.assertEqual(len(panel.queue), 3)
        self.assertIn('Reconnect', panel.status.text())
        panel.cancel()

    def test_paused_batch_shared_edits_affect_only_unstarted_sessions(self):
        panel = UploadBatchPanel(lambda: self.doc, self.settings)
        panel.editor.account = {'channel_id': 'channel'}
        class Auth:
            account = None
        panel.editor.auth = Auth()
        panel.refresh()
        pending = UploadMetadata('Saved title', description='Frozen description')
        Path(self.groups[0].output_dir, 'youtube_upload.json').write_text(json.dumps({'schema_version': 1, 'status': 'uploading', 'metadata': pending.__dict__, 'session_key': 'key', 'channel_id': 'channel'}))
        panel.process_group = lambda group: panel.group_failed('YouTube authentication failed')
        panel.check_all(True)
        panel.start_batch()
        self.assertTrue(panel.paused)
        panel.editor.description_edit.setPlainText('Changed while paused')
        panel.editor.account = panel.editor.auth.account = {'channel_id': 'channel'}
        captured = []
        panel.process_group = lambda group: (captured.append(panel.batch_metadata[group.group_id]), panel.group_done('Completed'))
        panel.resume_batch()
        self.wait_finished(panel)
        self.assertEqual(captured[0].description, 'Frozen description')
        self.assertEqual(captured[1].description, 'Changed while paused')
        self.assertEqual(captured[2].description, 'Changed while paused')

    def test_sequential_upload_engine_continues_after_group_failure(self):
        from pipeline.document import Step5UploadBundle
        session = ScriptedSession(Response(403), Response(headers={'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=safe'}), Response(data={'id': 'abc123', 'status': {'privacyStatus': 'private'}}), Response())
        secrets = MemorySecrets()
        class Auth:
            account = {'channel_id': 'channel'}
            secret_store = secrets
            def session(inner):
                return session
        panel = UploadBatchPanel(lambda: self.doc, self.settings)
        panel.editor.auth = Auth()
        panel.editor.account = Auth.account
        panel.refresh()
        def media(group_id):
            group = self.doc.require_group_artifacts(group_id)
            video, thumb = Path(group.output_dir) / 'video.mp4', Path(group.output_dir) / 'thumbnail.jpg'
            video.write_bytes(b'video')
            thumb.write_bytes(b'jpeg')
            return Step5UploadBundle(group.title, group.label, group.output_dir, str(video), str(thumb), {}, {})
        with patch.object(self.doc, 'require_step5_outputs', side_effect=media):
            panel.start_batch([self.groups[0].group_id, self.groups[1].group_id])
            self.wait_finished(panel)
        self.assertIn('Failed', panel.summary[0])
        self.assertIn('completed', panel.summary[1])
        self.assertEqual(json.loads(Path(self.groups[1].output_dir, 'youtube_upload.json').read_text())['video_id'], 'abc123')
        self.assertFalse(Path(self.groups[2].output_dir, 'youtube_upload.json').exists())

    def test_video_current_output_skip_and_sequential_subset(self):
        panel = VideoBatchPanel(lambda: self.doc, self.settings)
        panel.capabilities = VideoCapabilities('ffmpeg', 'ffprobe', 'test', 'Linux')
        panel.enter()
        seen = []
        panel.process_group = lambda group: (seen.append(group.group_id), panel.group_done('Skipped — current verified MP4'))
        panel.start_batch([self.groups[1].group_id])
        self.wait_finished(panel)
        self.assertEqual(seen, [self.groups[1].group_id])


class VideoMetadataUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name)
        self.state = {'schema_version': 1, 'status': 'completed', 'video_id': 'abc123', 'channel_id': 'channel', 'metadata': UploadMetadata('Original').__dict__, 'playlist_id': 'playlist', 'thumbnail_uploaded': True}
        Path(self.job, 'youtube_upload.json').write_text(json.dumps(self.state))
        self.current = {'id': 'abc123', 'snippet': {'channelId': 'channel', 'title': 'Old', 'categoryId': '22', 'defaultLanguage': 'vi', 'defaultAudioLanguage': 'vi'}, 'status': {'license': 'creativeCommon', 'embeddable': False, 'publicStatsViewable': False, 'privacyStatus': 'private', 'containsSyntheticMedia': True}}

    def test_metadata_update_preserves_unrelated_fields_and_frozen_insertion(self):
        session = ScriptedSession(Response(data={'items': [self.current]}), Response(data={'id': 'abc123'}))
        result = YouTubeUploader(session, MemorySecrets(), retry_delay=0).update_video_metadata(self.job, 'channel', UploadMetadata('New', description='New description'))
        body = session.calls[1][2]['json']
        self.assertEqual(session.calls[1][0], 'PUT')
        self.assertEqual(body['snippet']['defaultLanguage'], 'vi')
        self.assertEqual(body['snippet']['defaultAudioLanguage'], 'vi')
        self.assertEqual(body['status']['license'], 'creativeCommon')
        self.assertFalse(body['status']['embeddable'])
        self.assertTrue(body['status']['containsSyntheticMedia'])
        self.assertEqual(result['metadata']['title'], 'Original')
        self.assertEqual(result['updated_metadata']['title'], 'New')
        self.assertEqual(result['playlist_id'], 'playlist')

    def test_api_failure_keeps_local_record_unchanged(self):
        session = ScriptedSession(Response(data={'items': [self.current]}), Response(403))
        before = Path(self.job, 'youtube_upload.json').read_bytes()
        with self.assertRaises(YouTubeUploadError):
            YouTubeUploader(session, MemorySecrets(), retry_delay=0).update_video_metadata(self.job, 'channel', UploadMetadata('New'))
        self.assertEqual(before, Path(self.job, 'youtube_upload.json').read_bytes())

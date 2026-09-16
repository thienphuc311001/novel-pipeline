"""Canonical grouping and independent Step 4 plans (no network/GPU)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from media.artifacts import sha256_text
from media.groups import (preview_groups, scan_headings, write_groups, restore_groups, prepare_tts,
                         edit_failed_chunk, record_media, save_job_state, record_video)
from media.video import VideoRenderResult
from pipeline.document import PipelineDocument, PipelineStateError


def document_for(text, folder):
    doc = PipelineDocument()
    doc.original_input_text = "immutable original input"
    doc.normalized_text = "older Step 1 output"
    doc.chinese_review_text = doc.step2_confirmed_output = text
    doc.input_directory = str(folder)
    doc.job_title = "Bắc Tống"
    return doc


class ChapterGroupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings()

    def test_all_heading_formats_are_lossless(self):
        text = 'Preamble  \r\n\r\n' + '\r\n\r\n'.join(
            f'{header}\r\n  "Dialogue!"  \r\n' for header in
            ['Chương 1', 'Chương 01', 'Chương 100: Title', 'Chuong 100', 'Chapter 100', 'Hồi 100', 'Quyển 1'])
        headings, groups, diagnostics = preview_groups(text, self.settings, 2)
        self.assertEqual(len(headings), 7)
        self.assertEqual(headings[1].heading, 'Chương 01')
        self.assertEqual(''.join(text[g['start']:g['end']] for g in groups), text)
        self.assertTrue(diagnostics)
        self.assertEqual(groups[0]['start'], 0)

    def test_group_counts_and_final_remainder(self):
        text = ''.join(f'Chương {i}\nBody.\n\n' for i in range(1, 101))
        for size, expected in [(10, 10), (20, 5), (25, 4), (50, 2), (200, 1), (7, 15)]:
            with self.subTest(size=size):
                _, groups, _ = preview_groups(text, self.settings, size)
                self.assertEqual(len(groups), expected)
                self.assertEqual(sum(len(g['chapters']) for g in groups), 100)
        _, groups, _ = preview_groups(text + 'Chương 101\nB.\nChương 102\nB.\nChương 103\nB.\n', self.settings, 20)
        self.assertEqual(groups[-1]['label'], 'Chương 101-103')
        self.assertEqual(len(groups), 6)

    def test_no_headings_and_invalid_sizes_fail(self):
        for text, size in [('Narrative only.\n' * 1000, 20), ('Chương 1\nB.', 0), ('Chương 1\nB.', -1)]:
            with self.assertRaises(PipelineStateError):
                preview_groups(text, self.settings, size)

    def test_configured_patterns_and_space_titles(self):
        text = 'Chapter 01 Space Title\nB.\nChuong 2 Một tiêu đề\nB.\nQuyển 1\nB.'
        self.assertEqual(len(scan_headings(text, self.settings)), 3)
        self.settings.detect_english = False
        self.assertEqual(len(scan_headings(text, self.settings)), 2)
        self.settings.use_custom_chapter_regex = True
        self.settings.custom_chapter_regex = r'^Section (?P<number>\d+)$'
        self.assertEqual(len(scan_headings('Section 1\nB.', self.settings)), 1)

    def test_files_are_exact_and_step3_never_cleans_or_chunks(self):
        text = 'Foreword\r\n\r\nChương 1\r\n<p>50% & a/b</p>  \r\n\r\nChapter 02: T\r\n"Hello."\r\n'
        doc = document_for(text, self.root)
        with patch('cleaning.textclean.clean_text', side_effect=AssertionError('Step 3 cleaning forbidden')), patch('chunking.splitter.split_chapters', side_effect=AssertionError('Step 3 TTS chunking forbidden')):
            groups = write_groups(doc, self.settings, doc.job_title, 1)
        self.assertEqual(''.join(Path(g.txt_path).read_bytes().decode('utf-8') for g in groups), text)
        self.assertEqual(doc.original_input_text, 'immutable original input')
        self.assertEqual(doc.chunks, [])
        for g in groups:
            data = json.loads(Path(g.json_path).read_text(encoding='utf-8'))
            self.assertNotIn('chunks', data)
            self.assertEqual(data['text'].encode('utf-8'), Path(g.txt_path).read_bytes())
            self.assertEqual(data['text_sha256'], g.text_sha256)
            self.assertTrue(Path(g.txt_path).name == 'final.txt')

    def test_collisions_and_diagnostics_preserve_order(self):
        text = 'Chương 5\nA.\nChương 5\nB.\nChương 2\nC.\nChương 9\nD.'
        doc = document_for(text, self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        self.assertEqual(len({g.output_dir for g in groups}), 4)
        self.assertTrue(groups[1].slug.endswith('_group_002'))
        self.assertEqual([g.chapters[0]['number'] for g in groups], [5, 5, 2, 9])
        diagnostics = preview_groups(text, self.settings, 1)[2]
        self.assertTrue(any('Repeated' in d for d in diagnostics))
        self.assertTrue(any('reset' in d for d in diagnostics))
        self.assertTrue(any('gap' in d for d in diagnostics))

    def test_restore_requires_manifest_source_config_and_files(self):
        text = 'Chương 1\nA.\nChương 2\nB.'
        doc = document_for(text, self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        restored = document_for(text, self.root)
        self.assertEqual([g.group_id for g in restore_groups(restored, self.settings, doc.job_title, 1)], [g.group_id for g in groups])
        with self.assertRaises(PipelineStateError):
            restore_groups(restored, self.settings, doc.job_title, 20)
        Path(groups[0].txt_path).write_bytes(b'changed')
        with self.assertRaises(PipelineStateError):
            restored.require_group_artifacts(groups[0].group_id)
        with self.assertRaises(PipelineStateError):
            restore_groups(document_for(text, self.root), self.settings, doc.job_title, 1)

    def test_output_root_and_explicit_group_id(self):
        doc = document_for('Chương 1\nA.', self.root)
        group = write_groups(doc, self.settings, doc.job_title, 20)[0]
        self.assertEqual(Path(group.output_dir).parent.parent, self.root)
        with self.assertRaises(PipelineStateError):
            doc.require_step4_outputs()
        with self.assertRaises(PipelineStateError):
            doc.require_step5_outputs()
        self.settings.output_dir = str(self.root / 'override')
        group = write_groups(doc, self.settings, doc.job_title, 20)[0]
        self.assertEqual(Path(group.output_dir).parent.parent, self.root / 'override')

    def test_upstream_invalidation_keeps_disk_and_upload_records(self):
        doc = document_for('Chương 1\nA.', self.root)
        group = write_groups(doc, self.settings, doc.job_title, 20)[0]
        marker = Path(group.output_dir) / 'youtube_upload.json'
        marker.write_text('{"video_id":"abc123"}')
        cloned = doc.clone()
        cloned.chapter_groups[0].state['changed'] = True
        self.assertNotIn('changed', doc.chapter_groups[0].state)
        doc.set_job_identity('New title', '')
        self.assertFalse(doc.chapter_groups)
        self.assertTrue(marker.exists())
        self.assertTrue(Path(group.txt_path).exists())
        with self.assertRaises(PipelineStateError):
            doc.require_group_artifacts(group.group_id)

    def test_tts_plans_clean_only_working_copy_and_preserve_preamble(self):
        doc = document_for('Foreword 50%.\n\nChương 1\n<p>"a & b"</p>\n\nChương 2\nOther.', self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        before = [Path(g.txt_path).read_bytes() for g in groups]
        plans = [prepare_tts(doc, g.group_id, self.settings) for g in groups]
        self.assertNotEqual(plans[0][0]['plan_id'], plans[1][0]['plan_id'])
        speech = ' '.join(c.text for c in plans[0][1])
        self.assertIn('Foreword', speech)
        self.assertIn('Chương 1', speech)
        self.assertNotIn('<p>', speech)
        self.assertNotIn('&', speech)
        self.assertEqual(before, [Path(g.txt_path).read_bytes() for g in groups])
        self.assertEqual(plans[0][0], prepare_tts(doc, groups[0].group_id, self.settings)[0])

    def test_edit_only_failed_chunk_and_persist_override(self):
        doc = document_for('Chương 1\nBody.', self.root)
        group = write_groups(doc, self.settings, doc.job_title, 20)[0]
        plan, chunks = prepare_tts(doc, group.group_id, self.settings)
        with self.assertRaises(PipelineStateError):
            edit_failed_chunk(doc, group.group_id, self.settings, 1, 'Fixed.')
        group.state['failures'] = [{'chunk_number': 1}]
        for text in ('', ' ' * 10, 'a' * 1201):
            with self.assertRaises(PipelineStateError):
                edit_failed_chunk(doc, group.group_id, self.settings, 1, text)
        original = Path(group.txt_path).read_bytes()
        edit_failed_chunk(doc, group.group_id, self.settings, 1, 'Fixed speech.')
        self.assertEqual(prepare_tts(doc, group.group_id, self.settings)[1][0].text, 'Fixed speech.')
        self.assertEqual(Path(group.txt_path).read_bytes(), original)
        self.settings.max_chunk_chars = 1000
        self.assertNotEqual(prepare_tts(doc, group.group_id, self.settings)[1][0].text, 'Fixed speech.')

    def test_group_media_isolation_and_video_invalidation(self):
        doc = document_for('Chương 1\nA.\nChương 2\nB.', self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        g = groups[0]
        for kind, filename in [('thumbnail', 'thumbnail.jpg'), ('audiobook', g.slug + '_audiobook.mp3')]:
            path = Path(g.output_dir) / filename
            path.write_bytes(b'nonempty')
            record_media(g, kind, path)
        with self.assertRaises(PipelineStateError):
            doc.require_step4_outputs(g.group_id)
        g.state['tts_status'] = 'Partial'
        save_job_state(g)
        media = doc.require_step4_outputs(g.group_id)
        with self.assertRaises(PipelineStateError):
            doc.require_step4_outputs(groups[1].group_id)
        Path(media.video_path).write_bytes(b'video')
        result = VideoRenderResult(media.video_path, 3, 5, 'libx264', 'CPU', 10, 'copy')
        record_video(doc, g.group_id, result)
        self.assertEqual(doc.require_step5_outputs(g.group_id).video_path, media.video_path)
        record_media(g, 'thumbnail', media.thumbnail_path)
        with self.assertRaises(PipelineStateError):
            doc.require_step5_outputs(g.group_id)

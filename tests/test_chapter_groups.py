"""Canonical grouping and independent Step 3 plans (no network/GPU)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from media.artifacts import sha256_text
from media.groups import (GROUPING_METHOD_NUMERIC, analyze_grouping, preview_groups, scan_headings,
                         write_groups, restore_groups, prepare_tts, edit_failed_chunk, record_media,
                         save_job_state, record_video)
from media.groups import delete_group
from media.video import VideoRenderResult
from pipeline.document import PipelineDocument, PipelineStateError, StageKey


def document_for(text, folder):
    doc = PipelineDocument()
    doc.original_input_text = "immutable original input"
    doc.normalized_text = text
    doc.normalized_revision = 1
    doc.stage(StageKey.NORMALIZE).touch("fixture", "fixture")
    doc.input_directory = str(folder)
    doc.job_title = "Bắc Tống"
    return doc


def numeric_source(omitted=()):
    """Keep every chapter's text while deliberately omitting some headings."""
    missing = set(omitted)
    parts = ["Preamble with  spaces.\r\n\r\n"]
    for number in range(601, 701):
        if number not in missing:
            parts.append(f"Chương {number}\r\n")
        parts.append(f"Body {number}.  \r\n\r\n")
    return "".join(parts)


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

    def test_files_are_exact_and_step2_never_cleans_or_chunks(self):
        text = 'Foreword\r\n\r\nChương 1\r\n<p>50% & a/b</p>  \r\n\r\nChapter 02: T\r\n"Hello."\r\n'
        doc = document_for(text, self.root)
        with patch('cleaning.textclean.clean_text', side_effect=AssertionError('Step 2 cleaning forbidden')), patch('chunking.splitter.split_chapters', side_effect=AssertionError('Step 2 TTS chunking forbidden')):
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
        with self.assertRaisesRegex(PipelineStateError, "missing"):
            write_groups(doc, self.settings, doc.job_title, 1)
        headings = scan_headings(text, self.settings)
        diagnostics = analyze_grouping(text, self.settings, 1).diagnostics
        self.assertEqual([heading.number for heading in headings], [5, 5, 2, 9])
        self.assertTrue(any('Repeated' in d for d in diagnostics))
        self.assertTrue(any('reset' in d for d in diagnostics))
        self.assertTrue(any('gap' in d for d in diagnostics))

    def test_numeric_boundaries_keep_ranges_and_exact_canonical_text(self):
        # 82 detected headings: 602-618 and 620 are absent, but all group
        # starts (601, 621, 641, 661, 681) remain reliable.
        text = numeric_source(set(range(602, 619)) | {620})
        analysis = analyze_grouping(text, self.settings, 20)
        self.assertTrue(analysis.requires_numeric_boundaries)
        self.assertFalse(analysis.numeric_unavailable_reason)
        self.assertEqual(len(analysis.headings), 82)
        self.assertEqual(analysis.expected_count, 100)
        self.assertEqual([item['range_label'] for item in analysis.numeric_groups],
                         ['601-620', '621-640', '641-660', '661-680', '681-700'])
        self.assertEqual([item['number'] for item in analysis.required_group_starts], [601, 621, 641, 661, 681])

        with self.assertRaisesRegex(PipelineStateError, "missing"):
            preview_groups(text, self.settings, 20)
        _, preview, _ = preview_groups(text, self.settings, 20, method=GROUPING_METHOD_NUMERIC)
        self.assertEqual([item['range_label'] for item in preview], ['601-620', '621-640', '641-660', '661-680', '681-700'])
        for size, expected in ((25, ['601-625', '626-650', '651-675', '676-700']),
                               (200, ['601-700'])):
            with self.subTest(size=size):
                _, groups, _ = preview_groups(text, self.settings, size, method=GROUPING_METHOD_NUMERIC)
                self.assertEqual([item['range_label'] for item in groups], expected)

        doc = document_for(text, self.root)
        with self.assertRaisesRegex(PipelineStateError, "confirmation"):
            write_groups(doc, self.settings, doc.job_title, 20, method=GROUPING_METHOD_NUMERIC)
        groups = write_groups(doc, self.settings, doc.job_title, 20, method=GROUPING_METHOD_NUMERIC,
                              confirmation_fingerprint=analysis.numeric_identity_fingerprint)
        self.assertEqual(b''.join(Path(group.txt_path).read_bytes() for group in groups), text.encode('utf-8'))
        self.assertIn('Body 620.', Path(groups[0].txt_path).read_text(encoding='utf-8'))
        self.assertNotIn('Body 620.', Path(groups[1].txt_path).read_text(encoding='utf-8'))
        self.assertNotIn(620, [chapter['number'] for chapter in groups[0].chapters])
        self.assertEqual(groups[1].start, next(h.start for h in analysis.headings if h.number == 621))

        manifest = json.loads(Path(doc.group_manifest_path).read_text(encoding='utf-8'))
        self.assertEqual(manifest['grouping_method'], GROUPING_METHOD_NUMERIC)
        self.assertEqual(manifest['source_revision'], doc.normalized_revision)
        self.assertEqual(manifest['numeric_confirmation']['fingerprint'], analysis.numeric_identity_fingerprint)
        self.assertEqual(manifest['numeric_confirmation']['descriptor'], analysis.numeric_identity_descriptor)
        restored = document_for(text, self.root)
        self.assertEqual([group.group_id for group in restore_groups(restored, self.settings, doc.job_title, 20)],
                         [group.group_id for group in groups])

    def test_numeric_grouping_rejects_missing_or_ambiguous_starts(self):
        missing_start = numeric_source({621})
        duplicate_start = numeric_source(set(range(602, 621))).replace(
            'Chương 621\r\n', 'Chương 621\r\nDuplicate body.\r\nChương 621\r\n', 1)
        reset = 'Chương 601\nA.\nChương 650\nB.\nChương 620\nC.\nChương 700\nD.'
        for text, expected in ((missing_start, 'Missing required group-start'),
                               (duplicate_start, 'duplicate or reset'),
                               (reset, 'duplicate or reset')):
            with self.subTest(expected=expected):
                analysis = analyze_grouping(text, self.settings, 20)
                self.assertTrue(analysis.requires_numeric_boundaries)
                self.assertIn(expected, analysis.numeric_unavailable_reason)
                with self.assertRaisesRegex(PipelineStateError, "unavailable"):
                    preview_groups(text, self.settings, 20, method=GROUPING_METHOD_NUMERIC)

    def test_numeric_confirmation_identity_rejects_stale_source_pattern_and_manifest(self):
        text = numeric_source({620})
        analysis = analyze_grouping(text, self.settings, 20)
        doc = document_for(text, self.root)
        write_groups(doc, self.settings, doc.job_title, 20, method=GROUPING_METHOD_NUMERIC,
                     confirmation_fingerprint=analysis.numeric_identity_fingerprint)

        with self.assertRaises(PipelineStateError):
            restore_groups(document_for(text.replace('Body 620.', 'Changed body 620.'), self.root),
                           self.settings, doc.job_title, 20)
        changed_patterns = Settings(detect_english=False)
        with self.assertRaises(PipelineStateError):
            restore_groups(document_for(text, self.root), changed_patterns, doc.job_title, 20)
        with patch('media.groups.HEADING_SCANNER_VERSION', 'heading-scan-v3'):
            with self.assertRaises(PipelineStateError):
                restore_groups(document_for(text, self.root), self.settings, doc.job_title, 20)

        manifest_path = Path(doc.group_manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['numeric_confirmation']['descriptor']['calculated_ranges'][0] = '601-619'
        manifest['numeric_confirmation']['descriptor']['required_group_starts'][1]['offset'] += 1
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(PipelineStateError):
            restore_groups(document_for(text, self.root), self.settings, doc.job_title, 20)

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
        manifest = json.loads(Path(doc.group_manifest_path).read_text(encoding='utf-8'))
        self.assertEqual(Path(manifest['resolved_output_dir']), self.root.resolve())
        self.assertEqual(Path(manifest['job_output_dir']), self.root / 'Bắc_Tống')
        with self.assertRaises(PipelineStateError):
            doc.require_step4_outputs()
        with self.assertRaises(PipelineStateError):
            doc.require_step5_outputs()

    def test_job_files_always_stay_beside_the_input(self):
        doc = document_for('Chương 1\nA.', self.root)
        # A legacy output override in an old config cannot move the job folder.
        legacy = Settings.from_dict({'output_dir': str(self.root / 'override')})
        self.assertFalse(hasattr(legacy, 'output_dir'))
        group = write_groups(doc, legacy, doc.job_title, 20)[0]
        self.assertEqual(Path(group.output_dir).parent.parent, self.root)
        self.assertFalse((self.root / 'override').exists())
        manifest = json.loads(Path(doc.group_manifest_path).read_text(encoding='utf-8'))
        self.assertEqual(Path(manifest['resolved_output_dir']), self.root.resolve())

    def test_group_files_require_the_step1_input_folder(self):
        doc = document_for('Chương 1\nA.', self.root)
        doc.input_directory = ''
        with self.assertRaisesRegex(PipelineStateError, 'Step 1'):
            write_groups(doc, self.settings, doc.job_title, 20)

    def test_restore_keeps_the_recorded_manifest_folder(self):
        text = 'Chương 1\nÂn Chính Mậu.'
        doc = document_for(text, self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 20)
        recorded_manifest = Path(doc.group_manifest_path)
        elsewhere = document_for(text, self.root / 'other-input')
        elsewhere.group_manifest_path = str(recorded_manifest)

        resumed = restore_groups(elsewhere, self.settings, doc.job_title, 20)

        self.assertEqual([item.group_id for item in resumed], [item.group_id for item in groups])
        self.assertEqual(Path(resumed[0].output_dir).resolve(), Path(groups[0].output_dir).resolve())
        self.assertEqual(Path(elsewhere.group_manifest_path).resolve(), recorded_manifest.resolve())

    def test_delete_damaged_groups_preserves_source_order_files_and_restore(self):
        text = ''.join(f'Chương {number}\nBody {number}.\n' for number in range(1, 5))
        doc = document_for(text, self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        marker = Path(groups[2].output_dir, 'youtube_upload.json')
        marker.write_text('{"video_id":"saved"}')
        Path(groups[2].txt_path).write_bytes(b'externally modified')
        Path(groups[1].json_path).unlink()
        delete_group(doc, groups[2].group_id)
        delete_group(doc, groups[1].group_id)
        self.assertEqual(doc.require_chapter_groups(), [groups[0], groups[3]])
        self.assertEqual([group.order for group in doc.chapter_groups], [1, 4])
        self.assertEqual(doc.require_grouping_input(), text)
        self.assertTrue(marker.exists())
        self.assertEqual(Path(groups[2].txt_path).read_bytes(), b'externally modified')
        with self.assertRaises(PipelineStateError):
            doc.require_group_artifacts(groups[2].group_id)
        with self.assertRaises(PipelineStateError):
            doc.require_step4_outputs(groups[2].group_id)
        with self.assertRaises(PipelineStateError):
            doc.require_step5_outputs(groups[2].group_id)

        restored = document_for(text, self.root)
        active = restore_groups(restored, self.settings, doc.job_title, 1)
        self.assertEqual([group.group_id for group in active], [groups[0].group_id, groups[3].group_id])
        self.assertEqual(restored.require_chapter_groups(), active)
        # Further removal works after restoring deletions made out of order.
        delete_group(restored, groups[0].group_id)
        delete_group(restored, groups[3].group_id)
        self.assertEqual(restored.require_chapter_groups(allow_empty=True), [])
        empty = document_for(text, self.root)
        self.assertEqual(restore_groups(empty, self.settings, doc.job_title, 1), [])
        self.assertEqual(empty.require_chapter_groups(allow_empty=True), [])
        self.assertEqual(len(write_groups(empty, self.settings, doc.job_title, 1)), 4)
        self.assertFalse(empty.deleted_chapter_groups)

    def test_deleted_numeric_group_restores_without_its_missing_files(self):
        text = numeric_source({620})
        doc = document_for(text, self.root)
        analysis = analyze_grouping(text, self.settings, 20)
        groups = write_groups(doc, self.settings, doc.job_title, 20, method=GROUPING_METHOD_NUMERIC,
                              confirmation_fingerprint=analysis.numeric_identity_fingerprint)
        last = groups[-1]
        Path(last.txt_path).unlink()
        Path(last.json_path).unlink()
        delete_group(doc, last.group_id)
        restored = document_for(text, self.root)
        self.assertEqual([group.range_label for group in restore_groups(restored, self.settings, doc.job_title, 20)],
                         ['601-620', '621-640', '641-660', '661-680'])
        self.assertEqual(restored.require_chapter_groups(), restored.chapter_groups)

    def test_delete_is_atomic_and_rejects_changed_or_invalid_manifest(self):
        doc = document_for('Chương 1\nA.\nChương 2\nB.', self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        manifest_path = Path(doc.group_manifest_path)
        before = manifest_path.read_bytes()
        with patch('media.groups.atomic_write_json', side_effect=OSError('Disk full')):
            with self.assertRaisesRegex(PipelineStateError, 'Disk full'):
                delete_group(doc, groups[0].group_id)
        self.assertEqual(doc.chapter_groups, groups)
        self.assertFalse(doc.deleted_chapter_groups)
        self.assertEqual(manifest_path.read_bytes(), before)
        data = json.loads(before)
        data['groups'][0]['start'] += 1
        manifest_path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(PipelineStateError, 'Manifest changed'):
            delete_group(doc, groups[0].group_id)
        self.assertEqual(doc.chapter_groups, groups)
        for deleted in (['unknown'], [groups[0].group_id] * 2, 'invalid', [{}]):
            data = json.loads(before)
            data['deleted_group_ids'] = deleted
            manifest_path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(PipelineStateError, 'deleted-group membership'):
                restore_groups(document_for(doc.require_grouping_input(), self.root), self.settings, doc.job_title, 1)
        data = json.loads(before)
        data['deleted_group_ids'] = [groups[0].group_id]
        data['groups'][0]['text_sha256'] = 'changed'
        manifest_path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(PipelineStateError, 'Manifest group text'):
                restore_groups(document_for(doc.require_grouping_input(), self.root), self.settings, doc.job_title, 1)
        manifest_path.write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(PipelineStateError, 'Manifest must describe'):
            delete_group(doc, groups[0].group_id)

    def test_deleted_group_metadata_is_cloned_and_invalidated(self):
        doc = document_for('Chương 1\nA.\nChương 2\nB.', self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        delete_group(doc, groups[0].group_id)
        clone = doc.clone()
        clone.deleted_chapter_groups[0].state['changed'] = True
        self.assertNotIn('changed', doc.deleted_chapter_groups[0].state)
        doc.set_job_identity('New title', '')
        self.assertFalse(doc.deleted_chapter_groups)

    def test_deletion_does_not_allow_implicit_gaps_or_reordered_jobs(self):
        doc = document_for('Chương 1\nA.\nChương 2\nB.\nChương 3\nC.', self.root)
        groups = write_groups(doc, self.settings, doc.job_title, 1)
        delete_group(doc, groups[1].group_id)
        doc.chapter_groups.reverse()
        with self.assertRaisesRegex(PipelineStateError, 'source order'):
            doc.require_chapter_groups(validate_files=False)
        doc.chapter_groups.reverse()
        doc.deleted_chapter_groups = []
        with self.assertRaisesRegex(PipelineStateError, 'source order'):
            doc.require_chapter_groups(validate_files=False)

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
        self.assertIn('a & b', speech)  # Safe TTS profile preserves semantic symbols.
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
        self.assertEqual(prepare_tts(doc, group.group_id, self.settings)[1][0].text, 'Fixed speech.')
        self.settings.tts_preprocessing = {'sentence_per_line': True}
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
        with self.assertRaisesRegex(PipelineStateError, 'partial'):
            record_video(doc, g.group_id, result)
        from tests.support import create_narration_fixture
        from media.groups import record_tts_provenance
        _, chunks = prepare_tts(doc, g.group_id, self.settings)
        processor = create_narration_fixture(g.output_dir, chunks, media.audiobook_path)
        record_media(g, "audiobook", media.audiobook_path)
        record_tts_provenance(g, processor)
        g.state['tts_status'] = 'Completed'
        record_video(doc, g.group_id, result)
        self.assertEqual(doc.require_step5_outputs(g.group_id).video_path, media.video_path)
        from media.groups import load_job_state
        g.state = load_job_state(g)
        self.assertEqual(doc.require_step5_outputs(g.group_id).video_path, media.video_path)
        record_media(g, 'thumbnail', media.thumbnail_path)
        with self.assertRaises(PipelineStateError):
            doc.require_step5_outputs(g.group_id)

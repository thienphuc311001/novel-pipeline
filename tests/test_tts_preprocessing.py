"""Semantic preservation, idempotence, boundaries and pipeline integration."""
import json
import os
import random
import re
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from cleaning.tts_prepare import prepare_chapter
from cleaning.tts_text_preprocessor import (TTSPreprocessConfig, preprocess_for_tts,
                                           preprocess_with_diagnostics, preprocessing_identity)
from cleaning.tts_boundaries import boundary_positions, meaningful_text, safe_half_split
from chunking.splitter import split_text_by_limit, split_chapter
from config.settings import Settings
from media.groups import prepare_tts, write_groups, edit_failed_chunk
from media.tts import TtsProcessor
from pipeline.document import Chapter, PipelineStateError
from tests.test_chapter_groups import document_for
from tests.web_only_support import FakeTtsClients, WebWorkspaceMixin, make_mp3, tts_clients


CASES = [
    ('Ngươi là ai?Ta không biết.', 'Ngươi là ai? Ta không biết.'),
    ('Không thể nào!Hắn vẫn còn sống.', 'Không thể nào! Hắn vẫn còn sống.'),
    ('Hắn im lặng.....Sau đó quay đi.', 'Hắn im lặng… Sau đó quay đi.'),
    ('Giá là 3.14.Ta biết.', 'Giá là 3.14. Ta biết.'),
    ('Bây giờ là 12:30.Hắn đã đến.', 'Bây giờ là 12:30. Hắn đã đến.'),
    ('Có 10,000 người.', 'Có 10,000 người.'),
    ('“Ngươi là ai?”Hắn hỏi.', "'Ngươi là ai?' Hắn hỏi."),
    ('—Ngươi đến rồi?\n—Đúng.', '— Ngươi đến rồi?\n— Đúng.'),
    ('Ta   không    biết.', 'Ta không biết.'),
    ('Ta đi . Hắn ở lại !', 'Ta đi. Hắn ở lại!'),
    ('Hắn chết!!!!!!!', 'Hắn chết!'),
    ('Ngươi nói gì???????', 'Ngươi nói gì?'),
    ('Ngươi đi đâu?!?!?!?!?!', 'Ngươi đi đâu?!'),
    ('Hắn đi.<br>Ta ở lại.', 'Hắn đi.\nTa ở lại.'),
    ('**Hắn chết rồi.**', 'Hắn chết rồi.'),
    ('https://example.com', ''),
    ('*****', ''),
    ('Ta\u200b đi.', 'Ta đi.'),
    ('\ufeffTa đi.', 'Ta đi.'),
    ('Người&nbsp;đó', 'Người đó'),
    ('Chương 100: Đại chiến.Hắn bước ra.', 'Chương 100: Đại chiến\n\nHắn bước ra.'),
    ('192.168.1.1', '192.168.1.1'),
    ('Python 3.12', 'Python 3.12'),
    ('TP.HCM', 'TP.HCM'),
    ('17/09/2026', '17/09/2026'),
    ('08:30:15', '08:30:15'),
    ('Hắn nhìn về phía 天空.', 'Hắn nhìn về phía 天空.'),
    ('�', '�'),
    ('NgÆ°á»\x9di', 'NgÆ°á»\x9di'),  # Suspicious encoding is diagnosed and preserved.
]


class PreprocessingTests(unittest.TestCase):
    def test_required_examples_and_idempotence(self):
        for number, (source, expected) in enumerate(CASES, 1):
            with self.subTest(number=number):
                result = preprocess_with_diagnostics(source)
                self.assertEqual(result.text, expected)
                self.assertEqual(preprocess_for_tts(result.text), result.text)
                if number >= 27:
                    self.assertTrue(result.warnings)

    def test_full_required_example_and_adjacent_url(self):
        source = '\ufeffChương 327: Đại chiến.....Hắn nhìn lên trời!!!!!!“Không thể nào!”Lâm Phàm hét lên.<br><br>Ngươi là ai?Ta không biết...https://example.com'
        expected = 'Chương 327: Đại chiến\n\nHắn nhìn lên trời!\' Không thể nào!\' Lâm Phàm hét lên.\n\nNgươi là ai? Ta không biết…'
        self.assertEqual(preprocess_for_tts(source), expected)
        self.assertEqual(preprocess_for_tts(expected), expected)
        self.assertEqual(preprocess_for_tts('Ta đi...https://example.com'), 'Ta đi…')
        self.assertEqual(preprocess_for_tts('Ta đi...https://example.com', TTSPreprocessConfig(url_policy='keep')), 'Ta đi… https://example.com')

    def test_double_quote_fallback_matches_step1_policy(self):
        # Defensive fallback for edited/legacy/Step-1-skipped input: dialogue
        # quotes become ASCII single quotes, including fullwidth ＂.
        self.assertEqual(
            preprocess_for_tts('Hắn nói “xin chào” rồi đi “về”.'),
            "Hắn nói 'xin chào' rồi đi 'về'.",
        )
        self.assertEqual(preprocess_for_tts('Cô đáp ＂đi ngay＂.'), "Cô đáp 'đi ngay'.")
        # Technical tokens keep their ASCII double quotes (JSON protection).
        self.assertEqual(
            preprocess_for_tts('{"title":"abc","value":3.14}'),
            '{"title":"abc","value":3.14}',
        )
        result = preprocess_with_diagnostics('Nói “hi”.')
        self.assertEqual(result.text, "Nói 'hi'.")
        self.assertEqual(result.statistics.get("double_quotes_normalized"), 2)
        self.assertEqual(preprocess_for_tts(result.text), result.text)

    def test_protected_structures_and_semantics(self):
        samples = ['3.14', '0.5', '1,000', '1.000.000', '50%', '12:30', '08:30:15',
                   '2026-09-17', '17-09-2026', 'v1.2.3', '192.168.1.1', 'example.com',
                   'TP.HCM', 'P.GS', 'v.v.', 'TS. Nguyễn', 'Mr. Smith', 'J.K. Rowling',
                   'A.B.C.', r'C:\folder\notes', r'literal \n \t \r', 'key:value',
                   '{"title":"abc","value":3.14}', 'không không', 'ta ta',
                   'Hoà Hòa', 'xuyên-không Wi-Fi A-level', 'anh/chị km/h A/B',
                   'Hắn bước vào (không ai chú ý) rồi ngồi xuống.', '[1] [Chú thích]',
                   'A < B và B > C.', 'Tên <test> chưa rõ.', 'l / I / 1 rn / m']
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(preprocess_for_tts(sample), sample)

    def test_unicode_and_entities(self):
        self.assertEqual(preprocess_for_tts('Ngu\u031bo\u031b\u0300i\u00a0\u2009đó\r\n\tTa\x00 đi.\r'), 'Người đó\nTa đi.')
        self.assertEqual(preprocess_for_tts('&amp;lt;p&amp;gt;**Ta đi.**&amp;lt;/p&amp;gt;'), 'Ta đi.')
        for source in (' Chương 100: Đại chiến.Hắn bước ra.', '\u00a0*****', '\u00a0• Kiếm', '****Ta đi.****', '*a **b***', '&#38;lt;p&#38;gt;Ta đi.&#38;lt;/p&#38;gt;', '*\u200b*Ta đi.*\u200b*', '<\u200bb>Ta đi.</b>', '***Ta đi.***', '**Hắn *im lặng*.**', '```python\n{"a":3.14}\n```',
                       '“Câu chưa đóng.', 'Ta . . . Hắn …… đứng dậy.', '🔥🔥❤️😂', 'Ta\u200d đi.'):
            once = preprocess_for_tts(source)
            self.assertEqual(preprocess_for_tts(once), once)
        result = preprocess_with_diagnostics('क्\u200dष 天空 한글 日本 � NgÆ°á»\x9di')
        self.assertIn('\u200d', result.text)
        self.assertEqual(result.statistics['detected_cjk_chars'], 4)
        self.assertGreater(result.statistics['detected_other_script_chars'], 0)
        self.assertTrue(result.warnings)

    def test_valid_vietnamese_diacritics_are_not_mojibake(self):
        source = "\n".join(["Ân Chính Mậu", "Ă Â Đ Ê Ô Ơ Ư", "ấ ầ ẩ ẫ ậ"] * 16) + "\nÂn Chính Mậu"
        result = preprocess_with_diagnostics(source)

        self.assertEqual(result.statistics["detected_mojibake_patterns"], 0)
        self.assertFalse(any("mojibake" in warning for warning in result.warnings))
        self.assertEqual(result.text, source)
        self.assertEqual(result.diagnostics, [])

    def test_mojibake_diagnostics_are_aggregated_and_preserved(self):
        source = "Ân Chính Mậu\nâ€™\nâ€™\nNgÆ°á»\x9di"
        result = preprocess_with_diagnostics(source)

        self.assertEqual(result.statistics["detected_mojibake_patterns"], 4)
        self.assertEqual(result.text, source)
        self.assertEqual(len(result.diagnostics), 4)
        self.assertTrue(any("rule=cp1252-punctuation" in warning and "x2" in warning
                            and "line 2" in warning and "line 3" in warning
                            for warning in result.warnings))
        self.assertTrue(any("rule=latin1-utf8" in warning and "Æ°" in warning
                            and "context=" in warning for warning in result.warnings))
        self.assertTrue(any("rule=latin1-vietnamese" in warning and "á»" in warning
                            and "char" in warning for warning in result.warnings))

    def test_chapter_preparation_keeps_chapter_context_in_diagnostics(self):
        source = "Ân Chính Mậu\nâ€™\nâ€™"
        chapter = Chapter(number=109, header_line="Chương 109", text=source)
        prepared, statistics, warnings = prepare_chapter(chapter, Settings())

        self.assertEqual(statistics["detected_mojibake_patterns"], 2)
        self.assertEqual(prepared.text, source)
        self.assertTrue(any("possible mojibake" in warning and "x2" in warning for warning in warnings))

    def test_policies_and_custom_rules(self):
        text = 'Ta xem https://example.com/a?q=1. Hắn viết abc@gmail.com.'
        self.assertEqual(preprocess_for_tts(text), 'Ta xem. Hắn viết abc@gmail.com.')
        keep = TTSPreprocessConfig(url_policy='keep')
        self.assertEqual(preprocess_for_tts(text, keep), text)
        uppercase = 'HTTP://EXAMPLE.COM/a?x=3.14&y=1,000'
        self.assertEqual(preprocess_for_tts(uppercase, keep), uppercase)
        self.assertEqual(preprocess_for_tts(uppercase), '')
        replace = TTSPreprocessConfig(url_policy='replace', email_policy='replace')
        once = preprocess_for_tts(text, replace)
        self.assertEqual(once, 'Ta xem [đường dẫn]. Hắn viết [email].')
        self.assertEqual(preprocess_for_tts(once, replace), once)
        config = TTSPreprocessConfig(boilerplate_patterns=[r'^Nguồn:.*$'], footnote_patterns=[r'\[\d+\]'])
        self.assertEqual(preprocess_for_tts('Nguồn: abc\nHắn đi [1].\nchapter_id=2', config), 'Hắn đi.')
        self.assertEqual(preprocess_for_tts('Nguồn: abc'), 'Nguồn: abc')
        with self.assertRaises(ValueError):
            TTSPreprocessConfig(url_policy='guess')

    def test_technical_json_emoji_and_comments(self):
        source = '{"a":{"b":"!!!?A"},"c":"..."}'
        self.assertEqual(preprocess_for_tts(source), source)
        self.assertEqual(boundary_positions(source), [])
        family = '👩\u200d👩\u200d👦'
        self.assertEqual(preprocess_for_tts(family), '')
        self.assertEqual(preprocess_for_tts(family, TTSPreprocessConfig(remove_emoji=False)), family)
        self.assertEqual(preprocess_for_tts('Ta <!-- note --> đi.'), 'Ta đi.')
        unclosed = 'Ta <!-- note chưa đóng'
        self.assertEqual(preprocess_for_tts(unclosed), unclosed)

    def test_sentence_per_line(self):
        config = TTSPreprocessConfig(sentence_per_line=True)
        source = 'A. B! C?\n\nGiá 3.14. TS. An đến.'
        expected = 'A.\nB!\nC?\n\nGiá 3.14.\nTS. An đến.'
        self.assertEqual(preprocess_for_tts(source, config), expected)
        self.assertEqual(preprocess_for_tts(expected, config), expected)

    def test_invariants_seeded_mixed_input(self):
        rng = random.Random(17092026)
        parts = ['Ta đi.', 'Hắn đến?Không!', '…', '.....', '!!!???', '“Xin chào.”Hắn nói.',
                 '\n\n\n', '\r', '\ufeff', '\u200b', '\t', '\x00', '天空', '❤️',
                 '3.14', 'TP.HCM', '12:30', '...https://example.com', '**Lặng.**', '<br>', '&amp;nbsp;', '�']
        for sentence_per_line in (False, True):
            config = TTSPreprocessConfig(sentence_per_line=sentence_per_line)
            for _ in range(150):
                source = ' '.join(rng.choices(parts, k=20))
                once = preprocess_for_tts(source, config)
                self.assertEqual(preprocess_for_tts(once, config), once, repr(source))
                self.assertFalse(any(c in once for c in ('\x00', '\r', '\ufeff', '\u200b')))
                self.assertNotRegex(once, r' {2,}|\n{3,}')
        self.assertEqual(preprocess_for_tts(''), '')


class BoundaryTests(unittest.TestCase):
    def test_technical_boundaries(self):
        source = 'Giá 3.14. TS. An đến “12:30?” Hắn dùng TP.HCM và 192.168.1.1.'
        units = [source[:c] for c in boundary_positions(source)]
        self.assertEqual(len(units), 3)
        self.assertTrue(units[0].endswith('3.14.'))
        self.assertTrue(units[1].endswith('?”'))

    def test_lossless_chunking_quotes_numbers_and_empty(self):
        source = ' '.join(['Giá 3.14, có 10,000 người. “Ngươi là ai?” Hắn hỏi.'] * 65)
        plan = split_text_by_limit(source, 600)
        self.assertEqual(' '.join(plan.chunks), source)
        self.assertTrue(all(len(c) <= 600 and meaningful_text(c) for c in plan.chunks))
        self.assertTrue(all(not c.startswith(tuple(',.!?…;:”’)]}')) for c in plan.chunks))
        self.assertFalse(plan.hard_splits)
        self.assertEqual(split_text_by_limit('… !!! —', 600).chunks, [])
        chapter = Chapter(number=1, header_line='Chương 1: Tiêu đề', text=source)
        plan = split_chapter(chapter, 600, include_header=True)
        self.assertEqual(plan.chunks[0], chapter.header_line)

    def test_oversized_protected_heading_and_combining(self):
        with self.assertRaisesRegex(ValueError, 'Protected token'):
            split_text_by_limit('https://example.com/' + 'x' * 601, 600)
        with self.assertRaisesRegex(ValueError, 'heading'):
            split_chapter(Chapter(number=1, header_line='Chương 1 ' + 'a' * 601, text='Body.'), 600, include_header=True)
        plan = split_text_by_limit(('a\u0301' * 700), 600)
        self.assertTrue(plan.hard_splits)
        self.assertEqual(''.join(plan.chunks), 'a\u0301' * 700)
        self.assertTrue(all(not c.startswith('\u0301') for c in plan.chunks))
        self.assertEqual(safe_half_split('192.168.1.1'), ('192.168.1.1', ''))
        first, second = safe_half_split('Giá 3.14. Hắn đã đến. Ta biết.')
        self.assertEqual(first + ' ' + second, 'Giá 3.14. Hắn đã đến. Ta biết.')


class SentencePackingTests(unittest.TestCase):
    def test_pack_sentences_not_short_paragraphs(self):
        from chunking.splitter import split_text_by_limit
        first = 'a' * 299 + '.'
        second = 'b' * 299 + '.'
        third = 'c' * 299 + '.'
        plan = split_text_by_limit(first + '\n\n' + second + ' ' + third, 700)
        self.assertEqual(plan.chunks, [first + '\n\n' + second, third])
        self.assertFalse(plan.hard_splits)

    def test_paragraph_break_inside_sentence_does_not_cut_short_sentence(self):
        from chunking.splitter import split_text_by_limit
        sentence = 'a' * 200 + '\n\n' + 'b' * 299 + '.'
        next_sentence = 'c' * 299 + '.'
        plan = split_text_by_limit(sentence + ' ' + next_sentence, 700)
        self.assertEqual(plan.chunks, [sentence, next_sentence])

    def test_oversized_sentence_uses_words_before_hard_slicing(self):
        from chunking.splitter import split_text_by_limit
        text = 'từ ' * 300 + 'kết thúc.'
        plan = split_text_by_limit(text, 700)
        self.assertGreater(len(plan.chunks), 1)
        self.assertTrue(all(len(c) <= 700 for c in plan.chunks))
        self.assertFalse(plan.hard_splits)


class TtsIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.settings = Settings()
        self.source = 'Lời đầu.\nChương 1: Đại chiến\nNgươi là ai?Ta không biết.....<br>“Hắn sống!”Lâm hét. �\nhttps://example.com'
        self.doc = document_for(self.source, self.root)
        self.group = write_groups(self.doc, self.settings, self.doc.job_title, 20)[0]

    def test_fixed_700_target_ignores_saved_legacy_sizes(self):
        self.settings.max_chunk_chars = 1200
        first, chunks = prepare_tts(self.doc, self.group.group_id, self.settings)
        self.assertEqual(first['config']['limit'], 700)
        self.assertEqual(first['source_revision'], self.doc.normalized_revision)
        self.settings.max_chunk_chars = 2000
        second, same = prepare_tts(self.doc, self.group.group_id, self.settings)
        self.assertEqual(first['plan_id'], second['plan_id'])
        self.assertEqual([c.text for c in chunks], [c.text for c in same])

    def test_group_tts_plan_propagates_chapter_mojibake_diagnostics(self):
        source = "Chương 109\nÂn Chính Mậu\nâ€™\nâ€™"
        document = document_for(source, self.root)
        group = write_groups(document, self.settings, document.job_title, 20)[0]

        plan, _chunks = prepare_tts(document, group.group_id, self.settings)

        self.assertEqual(plan["statistics"]["detected_mojibake_patterns"], 2)
        self.assertTrue(any("Chapter 109:" in warning and "x2" in warning
                            and "rule=cp1252-punctuation" in warning
                            for warning in plan["warnings"]))

    def test_preprocessing_before_chunking_and_resume(self):
        canonical = [Path(self.group.txt_path).read_bytes(), Path(self.group.json_path).read_bytes()]
        plan, chunks = prepare_tts(self.doc, self.group.group_id, self.settings)
        speech = '\n'.join(c.text for c in chunks)
        self.assertIn('Ngươi là ai? Ta không biết…', speech)
        self.assertIn("'Hắn sống!' Lâm hét.", speech)
        self.assertNotIn('https://', speech)
        self.assertTrue(plan['warnings'])
        self.assertEqual(prepare_tts(self.doc, self.group.group_id, self.settings)[0], plan)
        calls = []
        class Client:
            def __init__(self, text): self.text = text
            async def save(self, path):
                calls.append(self.text)
                Path(path).write_bytes(b'audio')
        def run(effective):
            return TtsProcessor(effective, self.root / 'audio', voice='voice', ffmpeg_path='/bin/true',
                                client_factory=lambda t, v: Client(t)).run()
        run(chunks)
        self.assertEqual(calls, [c.text for c in chunks])
        count = len(calls)
        self.assertEqual(len(run(chunks).skipped), len(chunks))
        self.assertEqual(len(calls), count)
        self.settings.tts_preprocessing = {'url_policy': 'keep'}
        changed, effective = prepare_tts(self.doc, self.group.group_id, self.settings)
        self.assertNotEqual(changed['plan_id'], plan['plan_id'])
        run(effective)
        self.assertGreater(len(calls), count)
        self.assertEqual(self.doc.require_grouping_input(), self.source)
        self.assertEqual(canonical, [Path(self.group.txt_path).read_bytes(), Path(self.group.json_path).read_bytes()])

    def test_old_cache_overrides_cancel_and_empty(self):
        plan, chunks = prepare_tts(self.doc, self.group.group_id, self.settings)
        path = Path(self.group.output_dir) / 'tts_chunks.json'
        old = dict(plan, schema_version=1)
        old['chunks'] = [dict(old['chunks'][0], text='bad', text_sha256='bad')]
        path.write_text(json.dumps(old))
        new, _ = prepare_tts(self.doc, self.group.group_id, self.settings)
        self.assertEqual(new, plan)
        self.group.state['failures'] = [{'chunk_number': chunks[-1].order}]
        edit_failed_chunk(self.doc, self.group.group_id, self.settings, chunks[-1].order, 'Đã sửa!Đúng...')
        self.assertEqual(prepare_tts(self.doc, self.group.group_id, self.settings)[1][-1].text, 'Đã sửa! Đúng…')
        with self.assertRaises(PipelineStateError):
            edit_failed_chunk(self.doc, self.group.group_id, self.settings, chunks[-1].order, 'https://example.com')
        self.settings.tts_preprocessing = {'sentence_per_line': True}
        changed, _ = prepare_tts(self.doc, self.group.group_id, self.settings)
        self.assertTrue(any('older plan' in w for w in changed['warnings']))
        before = path.read_bytes()
        event = Event(); event.set()
        with self.assertRaisesRegex(PipelineStateError, 'hủy'):
            prepare_tts(self.doc, self.group.group_id, self.settings, cancel_event=event)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(Exception, 'nội dung'):
            TtsProcessor([], self.root / 'empty', voice='voice', ffmpeg_path='/bin/true').run()

    def test_settings_roundtrip_and_custom_clean(self):
        self.settings.tts_preprocessing = {'url_policy': 'replace', 'email_policy': 'remove'}
        self.settings.custom_rules = [{'pattern': 'không biết', 'replacement': 'chưa biết', 'regex': False}]
        saved = self.root / 'settings.json'
        self.settings.save(saved)
        self.assertEqual(preprocessing_identity(Settings.load(saved)), preprocessing_identity(self.settings))
        _, chunks = prepare_tts(self.doc, self.group.group_id, self.settings)
        self.assertIn('chưa biết', '\n'.join(c.text for c in chunks))
        self.assertEqual(Settings.from_dict({}).tts_preprocessing, {})

class HeadlessLegacyTests(WebWorkspaceMixin, unittest.TestCase):
    """Legacy bundle provenance (core) plus group TTS preparation through real web jobs."""

    def setUp(self):
        self.start_workspace()
        self.settings = self.service.settings

    def group_files(self, group):
        return [Path(group["txt_path"]).read_bytes(), Path(group["json_path"]).read_bytes()]

    def test_legacy_bundle_client_and_old_provenance(self):
        from media.tts_preparation import prepare_legacy_bundle
        from media.artifacts import load_bundle_json
        source = 'Lời đầu.\nChương 1\nNgươi là ai?Ta không biết.....<br>Giá 3.14.'
        doc = document_for(source, self.root)
        doc.job_chapter = 'Chương 1'
        prepared, stats, _ = prepare_legacy_bundle(doc.clone(), self.settings)
        data = load_bundle_json(prepared.step3_artifacts)
        from media.groups import job_preprocessing_identity
        self.assertEqual(data['tts_preparation'], job_preprocessing_identity(prepared, self.settings))
        self.assertEqual(Path(data['resolved_output_dir']), self.root.resolve())
        self.assertIn('Lời đầu.', data['chunks'][0]['text'])
        self.assertIn('Ngươi là ai? Ta không biết…', prepared.cleaned_text)
        self.assertEqual(doc.require_grouping_input(), source)
        # Web TTS speaks the preprocessed group plan; a plan without valid provenance is rebuilt
        # from the upstream canonical text, which itself never changes.
        self.import_story(source, name='Truyện.txt')
        ids = self.group_story(20, title='Truyện')
        group = self.state()['groups'][0]
        canonical = self.group_files(group)
        mp3 = make_mp3(self.root / 'voice.mp3')
        clients = FakeTtsClients(mp3)
        with tts_clients(clients):
            self.run_job('tts', {'group_ids': ids})
        spoken = '\n'.join(text for text, _voice in clients.calls)
        self.assertIn('Ngươi là ai? Ta không biết…', spoken)
        self.assertNotIn('biết.....', spoken)
        plan_path = Path(group['output_dir']) / 'tts_chunks.json'
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        tampered = dict(plan)
        tampered.pop('config')
        plan_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding='utf-8')
        with tts_clients(FakeTtsClients(mp3)):
            self.run_job('tts', {'group_ids': ids})
        self.assertEqual(json.loads(plan_path.read_text(encoding='utf-8')), plan)
        self.assertEqual(self.group_files(group), canonical)
        self.assertEqual(self.service.document.require_grouping_input(), self.state()['text'])

    def test_large_preparation_worker_cancel_and_snapshot(self):
        source = 'Chương 1\n' + ('Ngươi là ai?Ta biết.\n' * 6000)
        self.import_story(source, name='Truyện.txt')
        ids = self.group_story(20, title='Truyện')
        group = self.state()['groups'][0]
        text, canonical = self.state()['text'], self.group_files(group)
        plan_path = Path(group['output_dir']) / 'tts_chunks.json'
        job_id = self.submit('prepare', {'group_ids': ids})
        deadline = time.monotonic() + 30
        while not any(row['message'] == 'prepare' for row in self.logs(job_id)):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.005)
        self.stop(job_id)
        job = self.wait(job_id)
        self.assertEqual(job['status'], 'cancelled', job)
        self.assertIn('Đã hủy chuẩn bị TTS', job['result']['groups'][0]['error'])
        self.assertFalse(plan_path.exists())
        self.assertNotIn('tts_plan', self.state()['groups'][0]['state'])
        self.assertEqual(self.state()['text'], text)
        self.assertEqual(self.group_files(group), canonical)
        # A new run after cancellation prepares the complete plan.
        self.run_job('prepare', {'group_ids': ids}, timeout=120)
        plan = self.state()['groups'][0]['state']['tts_plan']
        self.assertIn('Ngươi là ai? Ta biết.', '\n'.join(chunk['text'] for chunk in plan['chunks']))
        self.assertEqual(self.group_files(group), canonical)

    def change_preprocessing_after_video(self):
        self.import_story()
        ids = self.group_story(20)
        self.video_ready(ids)
        canonical = self.group_files(self.state()['groups'][0])
        response = self.client.put('/api/settings', json={
            'tts_preprocessing': {'url_policy': 'keep', 'sentence_per_line': True}})
        return response, canonical

    def test_config_preprocessing_settings_round_trip(self):
        response, canonical = self.change_preprocessing_after_video()
        self.assertEqual(response.status_code, 200, response.text)
        updated = self.client.get('/api/settings').json()
        self.assertEqual(updated['tts_preprocessing']['url_policy'], 'keep')
        self.assertTrue(updated['tts_preprocessing']['sentence_per_line'])
        # Canonical group text survives the settings change byte for byte.
        group = self.state()['groups'][0]
        self.assertTrue(Path(group['txt_path']).exists())
        self.assertEqual(self.group_files(group), canonical)

    @unittest.expectedFailure  # Gap G1: PUT /api/settings saves only; artifacts are not invalidated.
    def test_config_ui_and_downstream_invalidation(self):
        self.change_preprocessing_after_video()
        # Baseline: a TTS-preprocessing change invalidates finished audio and video.
        group = self.state()['groups'][0]
        self.assertEqual(group['state']['tts_status'], 'TTS Incomplete')
        self.assertNotIn('audiobook', group['state'])
        self.assertNotIn('video', group['state'])

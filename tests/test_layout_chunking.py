"""Layout-aware chunk planning: the rendered page budget is the validity rule.

Every fixture is measured with the renderer's own wrapping implementation, so these
tests fail if the planner and the renderer ever drift apart.  Boundaries are decided
by measured pixel height at one fixed font size — never by a character target.
"""
import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from chunking.splitter import (LayoutChunkError, layout_statistics, split_chapter, split_chapters,
                               split_text_by_limit, verify_chunk_integrity)
from media.text_layout import (DEFAULT_STYLE, LAYOUT_FILL_MAX, LAYOUT_FILL_MIN, LAYOUT_FILL_TARGET,
                               LayoutBudget, header_reserve, layout_identity, page_band, renderer_budget)
from media.video import VideoValidationError
from media.video_pages import page_chapter_label, render_page
from pipeline.document import Chapter


PROSE = 'Hắn bước vào căn phòng tối và nhìn thấy ánh sáng dịu dàng chiếu qua cửa sổ rộng lớn. '
LONG_SENTENCE = ('Hắn bước vào căn phòng tối và nhìn thấy ánh sáng dịu dàng chiếu qua cửa sổ rộng lớn, '
                 'rồi khẽ ngồi xuống bên chiếc bàn trà cũ kỹ trong góc phòng. ')
SHORT_DIALOGUE = ('“Ngươi đến rồi?”\n\n', '“Đã lâu không gặp.”\n\n', '“Ta tưởng ngươi đã chết rồi.”\n\n')
SHORT_PARAGRAPHS = ('Hắn bước đi trong căn phòng tối.', 'Ngươi đến rồi sao, sư huynh?',
                    'Thanh kiếm khẽ rung lên một tiếng.', 'Mưa rơi ướt cả con đường đá.')
TITLE = 'Đường về cố đô'
CHAPTER = 'Chương 601-620'


def dense_paragraph(chars):
    """One prose paragraph trimmed back to a sentence end, as a novel would look."""
    text = (PROSE * 60)[:chars]
    cut = text.rfind('.')
    return text[:cut + 1] if cut > 0 else text


def dialogue_text(rounds=12):
    return ''.join(SHORT_DIALOGUE * rounds)


def stripped(text):
    """Whitespace-free fingerprint: detects dropped, duplicated or reordered text."""
    return ''.join(text.split())


def canonical(text):
    return re.sub(r'\s+', ' ', text).strip()


def page_budget(title=TITLE, chapters=(1, 7, 601), style=DEFAULT_STYLE):
    """The real job budget: measured title plus every page label, like Step 3 uses."""
    labels = [page_chapter_label(number, CHAPTER) for number in chapters]
    return renderer_budget(style, title=title, chapter_labels=[*labels, CHAPTER])


def largest_fitting_count(budget, unit, ceiling=200):
    """How many whole ``unit`` copies fill the page: the real boundary of a page."""
    def fits(count):
        return budget.fits((unit * count).strip())
    if not fits(1):
        return 0
    low, high, best = 1, ceiling, 1
    while low <= high:
        middle = (low + high) // 2
        if fits(middle):
            best, low = middle, middle + 1
        else:
            high = middle - 1
    return best


class LayoutBudgetTests(unittest.TestCase):
    """The page budget follows the renderer, and pixels (not lines) decide."""

    def setUp(self):
        self.budget = LayoutBudget.from_style()
        self.job = page_budget()

    def test_budget_follows_the_renderer_configuration(self):
        self.assertEqual(page_band(DEFAULT_STYLE), 654)
        self.assertEqual(self.budget.body_height, page_band(DEFAULT_STYLE))
        self.assertEqual(self.budget.min_font_size, DEFAULT_STYLE.min_body_size)
        self.assertEqual(self.budget.min_font_size, DEFAULT_STYLE.body_size)
        self.assertEqual(self.budget.body_width, DEFAULT_STYLE.body_width)
        self.assertEqual(self.budget.body_max_lines, DEFAULT_STYLE.body_max_lines)
        # Changing the page grid moves both the renderer and the validation budget.
        self.assertEqual(page_band(replace(DEFAULT_STYLE, body_bottom_margin=94)), 584)
        self.assertEqual(LayoutBudget.from_style(replace(DEFAULT_STYLE, body_max_lines=30)).body_max_lines, 30)

    def test_reserved_header_is_measured_not_the_style_maximum(self):
        # The real one-line title/label reserve is far smaller than the style maxima,
        # so a job validates against the band its pages really offer.
        title_height, chapter_height = header_reserve(DEFAULT_STYLE, title=TITLE,
                                                     chapter_labels=[page_chapter_label(601, CHAPTER), CHAPTER])
        self.assertLess(title_height, DEFAULT_STYLE.title_max_height)
        self.assertLess(chapter_height, DEFAULT_STYLE.chapter_max_height)
        self.assertEqual(self.job.body_height,
                         page_band(DEFAULT_STYLE, title_height=title_height, chapter_height=chapter_height))
        self.assertGreater(self.job.body_height, page_band(DEFAULT_STYLE))

    def test_measurement_matches_the_renderer_acceptance_rule(self):
        dense = dense_paragraph(700)
        measurement = self.job.measure(dense)
        self.assertTrue(measurement.fits)
        self.assertEqual(measurement.reason, "")
        self.assertEqual(measurement.font_size, DEFAULT_STYLE.body_size)
        self.assertEqual(measurement.body_width, DEFAULT_STYLE.body_width)
        self.assertLessEqual(measurement.block_height, self.job.available_height)
        self.assertLess(measurement.block_height / self.job.available_height, LAYOUT_FILL_MIN)
        # Line count is only a sanity guard: the page is rejected by measured pixels.
        overflowing = '\n\n'.join(['Thoại ngắn.'] * 40)
        rejected = self.job.measure(overflowing)
        self.assertFalse(rejected.fits)
        self.assertGreater(rejected.block_height, self.job.available_height)

    def test_layout_identity_tracks_style_font_and_fill_policy(self):
        identity = layout_identity()
        self.assertEqual(identity, self.budget.identity())
        self.assertEqual(identity['body_band'], page_band(DEFAULT_STYLE))
        self.assertEqual(identity['fill_target'], LAYOUT_FILL_TARGET)
        self.assertIn('font_identity', identity)
        self.assertNotEqual(identity, layout_identity(replace(DEFAULT_STYLE, body_width=1200)))
        self.assertNotEqual(identity, layout_identity(replace(DEFAULT_STYLE, min_body_size=30)))
        self.assertNotEqual(identity, layout_identity(replace(DEFAULT_STYLE, line_spacing=1.3)))
        # The job band is part of the identity: a title that wraps to more lines
        # reserves more header space and therefore invalidates the plan.
        wrapping_title = ('Một tựa truyện rất dài và thanh lịch trong ánh sáng hoàng hôn buông xuống '
                          'thành cổ, nơi những con đường đá còn in dấu chân người xưa qua bao mùa mưa nắng')
        self.assertNotEqual(self.job.identity(), page_budget(title=wrapping_title).identity())
        self.assertGreater(page_budget(title=wrapping_title).body_height, 0)
        self.assertLess(page_budget(title=wrapping_title).body_height, self.job.body_height)
        self.assertNotEqual(self.job.fingerprint(), self.budget.fingerprint())
        # The CJK fallback faces are part of the identity: a different fallback face
        # measures brackets differently and would move a chunk boundary.
        self.assertIn('NotoSerifCJK-Regular.ttc:', identity['fallback_identities'][0])
        self.assertIn('NotoSerifCJK-Bold.ttc:', identity['fallback_identities'][1])
        import media.text_layout as text_layout_module
        job_fingerprint = self.job.fingerprint()
        original = text_layout_module.fallback_font_paths
        fallback_regular, fallback_bold = original()
        text_layout_module.fallback_font_paths = lambda: (fallback_bold, fallback_regular)
        try:
            self.assertNotEqual(identity, layout_identity())
            self.assertNotEqual(job_fingerprint, page_budget().fingerprint())
        finally:
            text_layout_module.fallback_font_paths = original


class AdaptiveChunkSizeTests(unittest.TestCase):
    """A/B/C. Chunk size follows the measured page, so it varies with the text."""

    def setUp(self):
        self.budget = page_budget()

    def test_dense_prose_grows_past_the_soft_target_until_the_page_is_full(self):
        # A ~700-character prose block leaves more than a third of the page empty;
        # with the measured page as the rule the planner keeps adding sentences.
        source = dense_paragraph(700) + ' ' + PROSE * 40
        plan = split_text_by_limit(source, 700, layout=self.budget)
        first = plan.chunks[0]
        self.assertGreater(len(first), 700)
        metadata = plan.layouts[0]
        self.assertGreaterEqual(metadata['fill_ratio'], LAYOUT_FILL_MIN)
        self.assertLessEqual(metadata['fill_ratio'], LAYOUT_FILL_MAX)
        self.assertLessEqual(metadata['measured_height'], metadata['body_height'])
        self.assertEqual(metadata['reason'], 'next_unit_would_exceed_page_height')
        self.assertEqual(plan.reasons[0], 'next_unit_would_exceed_page_height')
        self.assertTrue(first.endswith('.'))
        self.assertTrue(all(entry['fill_ratio'] >= LAYOUT_FILL_MIN for entry in plan.layouts[:-1]))
        self.assertEqual(plan.layouts[0]['font_size'], DEFAULT_STYLE.body_size)
        self.assertEqual(plan.layouts[0]['line_count'], plan.layouts[0]['visible_lines'])

    def test_short_dialogue_pages_hold_far_fewer_characters_than_prose(self):
        dialogue_plan = split_text_by_limit(dialogue_text(6), 700, layout=self.budget)
        prose_plan = split_text_by_limit(dense_paragraph(700) + ' ' + PROSE * 40, 700, layout=self.budget)
        self.assertGreater(len(dialogue_plan.chunks), 1)
        self.assertLess(len(dialogue_plan.chunks[0]), len(prose_plan.chunks[0]))
        for chunk in dialogue_plan.chunks:
            self.assertTrue(self.budget.fits(chunk))
        # Dialogue reaches the page height with fewer characters: the page, not a
        # character count, decided the boundary.
        self.assertGreaterEqual(dialogue_plan.layouts[0]['fill_ratio'], LAYOUT_FILL_MIN)
        self.assertLessEqual(dialogue_plan.layouts[0]['measured_height'],
                             dialogue_plan.layouts[0]['body_height'])

    def test_long_paragraph_wraps_in_the_renderer_column(self):
        from media.text_layout import font_paths, load_font, measure_draw, wrap_lines
        draw = measure_draw()
        font = load_font(font_paths()[0], DEFAULT_STYLE.body_size)
        for chunk in split_text_by_limit(LONG_SENTENCE * 20, 700, layout=self.budget).chunks:
            self.assertTrue(self.budget.fits(chunk))
            lines = wrap_lines(draw, chunk, font, DEFAULT_STYLE.body_width)
            self.assertTrue(lines)
            for line in lines:
                self.assertLessEqual(draw.textlength(line, font=font), DEFAULT_STYLE.body_width)

    def test_tight_pages_keep_full_paragraph_structure(self):
        text = '\n\n'.join((SHORT_PARAGRAPHS * 6)[:20])
        plan = split_text_by_limit(text, 700, layout=self.budget)
        self.assertGreater(len(plan.chunks), 1)
        for chunk in plan.chunks:
            self.assertTrue(self.budget.fits(chunk))
            self.assertFalse(chunk != chunk.strip())
        self.assertTrue(any('\n\n' in chunk for chunk in plan.chunks))
        statistics = layout_statistics(plan)
        self.assertGreater(statistics['layout_limited_chunks'], 0)
        self.assertEqual(statistics['layout_overflow_pages'], 0)


class PageBoundaryTests(unittest.TestCase):
    """D/E. The exact page boundary holds and one unit of overflow moves on."""

    def setUp(self):
        self.budget = page_budget()

    def test_largest_fitting_unit_stays_and_the_next_unit_moves_whole(self):
        unit = LONG_SENTENCE
        count = largest_fitting_count(self.budget, unit)
        self.assertGreater(count, 1)
        exact = (unit * count).strip()
        # A candidate that exactly equals the available page height is accepted ...
        self.assertTrue(self.budget.fits(exact))
        self.assertLessEqual(self.budget.measure(exact).block_height, self.budget.available_height)
        # ... and one more whole unit overflows the body area.
        self.assertFalse(self.budget.fits((unit * (count + 1)).strip()))
        plan = split_text_by_limit((unit * (count + 2)).strip(), 700, layout=self.budget)
        self.assertEqual(plan.chunks[0], exact)
        self.assertEqual(plan.reasons[0], 'next_unit_would_exceed_page_height')
        self.assertEqual(plan.chunks[1], (unit * 2).strip())
        self.assertTrue(all(self.budget.fits(chunk) for chunk in plan.chunks))
        self.assertEqual(stripped(''.join(plan.chunks)), stripped((unit * (count + 2)).strip()))

    def test_final_page_may_stay_under_filled_and_is_counted_apart(self):
        plan = split_text_by_limit(dense_paragraph(700) + ' ' + PROSE * 40, 700, layout=self.budget)
        self.assertEqual(plan.reasons[-1], 'end_of_text')
        self.assertTrue(plan.layouts[-1]['final_page'])
        self.assertFalse(plan.layouts[0]['final_page'])
        self.assertEqual(layout_statistics(plan)['layout_overflow_pages'], 0)
        short = split_text_by_limit(dense_paragraph(700) + ' Kết thúc.', 700, layout=self.budget)
        self.assertEqual(short.reasons[-1], 'end_of_text')
        self.assertEqual(layout_statistics(short)['layout_underfilled_pages'], 0)
        self.assertEqual(layout_statistics(short)['layout_final_underfilled_pages'], 1)


class OversizedUnitTests(unittest.TestCase):
    """A unit longer than a page is split through finer semantic boundaries."""

    def setUp(self):
        self.budget = page_budget()

    def test_oversized_sentence_falls_back_to_clause_or_word_boundaries(self):
        plan = split_text_by_limit(LONG_SENTENCE * 20, 700, layout=self.budget)
        self.assertFalse(plan.hard_splits)
        self.assertIn('sentence', plan.strategies)
        for chunk in plan.chunks:
            self.assertTrue(self.budget.fits(chunk))

    def test_long_paragraph_splits_sentence_before_clause_or_words(self):
        text = ('từ ngữ dài dòng trong một câu duy nhất không có dấu ngắt câu ' * 60).strip()
        plan = split_text_by_limit(text, 700, layout=self.budget)
        self.assertGreater(len(plan.chunks), 1)
        self.assertFalse(plan.hard_splits)
        for chunk in plan.chunks:
            self.assertTrue(self.budget.fits(chunk))

    def test_unbreakable_word_uses_the_hard_split_fallback_without_text_loss(self):
        text = 'x' * 3000
        plan = split_text_by_limit(text, 700, layout=self.budget)
        self.assertGreater(len(plan.chunks), 1)
        self.assertTrue(plan.hard_splits)
        self.assertIn('hard_split', plan.reasons)
        for chunk in plan.chunks:
            self.assertTrue(self.budget.fits(chunk))
        self.assertEqual(''.join(plan.chunks), text)

class PreservationTests(unittest.TestCase):
    """H. Chunk reconstruction reproduces the source with no loss or reordering."""

    def setUp(self):
        self.budget = page_budget()

    def check_exact_preservation(self, source):
        plan = split_text_by_limit(source, 700, layout=self.budget)
        reconstructed = ' '.join(plan.chunks)
        self.assertEqual(canonical(reconstructed), canonical(source))
        self.assertEqual(stripped(reconstructed), stripped(source))
        verify_chunk_integrity(source, plan)
        return plan

    def test_paragraph_separator_is_never_destroyed(self):
        plan = self.check_exact_preservation('A.\n\nB.')
        self.assertEqual(plan.chunks, ['A.\n\nB.'])

    def test_dialogue_and_newline_structure_survives_planning(self):
        source = ('— Ngươi đến rồi?\n— Đúng.\n\nHắn im lặng.\n“Thật sao?” hắn hỏi.\n\n'
                  'Ánh sáng tràn qua cửa sổ. ' * 3 + '\n\n— Đi thôi.\n— Khoan đã!')
        plan = self.check_exact_preservation(source)
        self.assertTrue(all(self.budget.fits(chunk) for chunk in plan.chunks))
        for chunk in plan.chunks:
            self.assertFalse(chunk != chunk.strip())
        self.assertTrue(any('\n' in chunk for chunk in plan.chunks))

    def test_mixed_prose_and_dialogue_round_trip(self):
        source = PROSE * 10 + '\n\n' + dialogue_text(4) + '\n\n' + LONG_SENTENCE * 6
        plan = self.check_exact_preservation(source)
        self.assertEqual(layout_statistics(plan)['layout_overflow_pages'], 0)

    def test_corrupted_plan_is_rejected_before_tts(self):
        from chunking.splitter import ChunkPlan
        source = PROSE * 20
        plan = split_text_by_limit(source, 700, layout=self.budget)
        broken = ChunkPlan(chunks=list(plan.chunks), strategies=list(plan.strategies),
                           layouts=list(plan.layouts), reasons=list(plan.reasons))
        broken.chunks[0] = broken.chunks[0][:-20]
        with self.assertRaises(LayoutChunkError) as context:
            verify_chunk_integrity(source, broken)
        self.assertEqual(context.exception.reason, 'text_integrity_violation')
        truncated = ChunkPlan(chunks=list(plan.chunks[:-1]), strategies=list(plan.strategies[:-1]))
        with self.assertRaises(LayoutChunkError):
            verify_chunk_integrity(source, truncated)


class ChapterDefaultsTests(unittest.TestCase):
    """The chapter-level pipeline entry points validate against the page by default."""

    def test_split_chapters_validates_and_carries_layout_metadata(self):
        chapter = Chapter(number=3, header_line='Chương 3', text=dialogue_text(6))
        budget = LayoutBudget.from_style()
        chunks, plan, _ = split_chapters([chapter], 700, include_header=True)
        self.assertEqual(chunks[0].text, 'Chương 3')
        self.assertEqual([c.order for c in chunks], list(range(1, len(chunks) + 1)))
        for chunk in chunks:
            self.assertTrue(budget.fits(chunk.text))
            self.assertIn('visible_lines', chunk.layout)
            self.assertIn('text_sha256', chunk.layout)
            self.assertIn('measured_height', chunk.layout)
            self.assertIn('layout_fingerprint', chunk.layout)
        self.assertEqual(len(plan.layouts), len(plan.chunks))
        self.assertEqual(len(plan.reasons), len(plan.chunks))

    def test_explicit_character_only_planning_still_exists(self):
        text = '\n\n'.join(['Thoại ngắn.'] * 30)
        plan = split_text_by_limit(text, 700)
        # Without a budget, metadata stays shallow and reasons describe the ceiling.
        self.assertNotIn('visible_lines', plan.layouts[0])
        self.assertEqual(plan.reasons, ['character_limit'])
        self.assertTrue(all(layout.get('reason') == 'character_limit' for layout in plan.layouts))
        # 30 short paragraphs pass the character ceiling but overflow the page.
        self.assertFalse(page_budget().fits(plan.chunks[0]))

    def test_planner_follows_an_injected_budget(self):
        strict = LayoutBudget.from_style(replace(DEFAULT_STYLE, body_max_lines=6))
        plan = split_text_by_limit(dense_paragraph(700), 700, layout=strict)
        self.assertGreater(len(plan.chunks), 1)
        for chunk in plan.chunks:
            self.assertTrue(strict.fits(chunk))

    def test_soft_target_is_only_a_comment_when_a_page_still_has_room(self):
        # The same page fills to different character counts: the target is a hint.
        text = PROSE * 40
        small = split_text_by_limit(text, 600, layout=page_budget())
        large = split_text_by_limit(text, 900, layout=page_budget())
        self.assertEqual(small.chunks, large.chunks)



class RendererIntegrationTests(unittest.TestCase):
    """I. Every planned chunk renders through the same shared layout engine."""

    def setUp(self):
        self.budget = page_budget()

    def test_every_planned_chunk_renders_with_the_same_layout_engine(self):
        source = dense_paragraph(700) + '\n\n' + dialogue_text(5) + '\n\n' + LONG_SENTENCE * 8
        plan = split_text_by_limit(source, 700, layout=self.budget)
        self.assertGreater(len(plan.chunks), 2)
        self.assertTrue(all(entry['fill_ratio'] >= LAYOUT_FILL_MIN for entry in plan.layouts[:-1]))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thumbnail = root / 'thumbnail.jpg'
            Image.new('RGB', (1280, 720), (70, 100, 140)).save(thumbnail)
            for index, chunk in enumerate(plan.chunks):
                self.assertTrue(self.budget.fits(chunk))
                layout = render_page(thumbnail, root / f'page_{index}.png', title=TITLE,
                                     chapter=page_chapter_label(601, CHAPTER), text=chunk)
                # One fixed font, no shrinking, and no overflow of the measured band.
                self.assertEqual(layout['font_size'], DEFAULT_STYLE.body_size)
                self.assertLessEqual(layout['measured_height'], layout['body_height'])
                self.assertGreaterEqual(layout['fill_ratio'] + 0.001, plan.layouts[index]['fill_ratio'])

    def test_direct_page_overflow_still_fails_in_the_renderer(self):
        text = '\n\n'.join(['Thoại ngắn.'] * 20)
        self.assertFalse(self.budget.fits(text))
        self.assertGreater(self.budget.measure(text).block_height, self.budget.available_height)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thumbnail = root / 'thumbnail.jpg'
            Image.new('RGB', (1280, 720), (70, 100, 140)).save(thumbnail)
            with self.assertRaisesRegex(VideoValidationError, 'body band'):
                render_page(thumbnail, root / 'overflow.png', title='Truyện', chapter='Chương 1', text=text)
            self.assertFalse((root / 'overflow.png').exists())
            # The line guard still reports pathological input that bypasses pixels.
            with self.assertRaisesRegex(VideoValidationError, 'sanity guard'):
                render_page(thumbnail, root / 'guard.png', title='Truyện', chapter='Chương 1',
                            text='\n\n'.join(['Thoại ngắn.'] * (DEFAULT_STYLE.body_max_lines + 2)))
            self.assertFalse((root / 'guard.png').exists())


class PathologicalUnitTests(unittest.TestCase):
    """J. Units that cannot fit produce a layout error with measured diagnostics."""

    def test_protected_token_reports_layout_facts(self):
        token = 'https://example.com/' + 'x' * 800
        with self.assertRaises(LayoutChunkError) as context:
            split_text_by_limit(token, 700, layout=LayoutBudget.from_style())
        message = str(context.exception)
        for fragment in ('Protected token', 'reason=protected_token_exceeds_limit', 'chars=',
                         'visible_lines=', f'font_size={DEFAULT_STYLE.body_size}px', 'body_width=1150px'):
            self.assertIn(fragment, message)
        self.assertEqual(context.exception.reason, 'protected_token_exceeds_limit')

    def test_unfittable_text_reports_layout_facts(self):
        starved = LayoutBudget.from_style(body_height=0)
        self.assertFalse(starved.fits('Hắn đi.'))
        with self.assertRaises(LayoutChunkError) as context:
            split_text_by_limit('Hắn đi. Ta ở lại.', 700, layout=starved)
        error = context.exception
        self.assertEqual(error.reason, 'text_cannot_fit_page')
        self.assertEqual(error.font_size, DEFAULT_STYLE.body_size)
        self.assertEqual(error.body_width, 1150)
        message = str(error)
        self.assertIn('reason=text_cannot_fit_page', message)
        self.assertIn('visible_lines=', message)
        self.assertIn('font_size=', message)

    def test_chapter_context_is_added_to_layout_errors(self):
        chapter = Chapter(number=42, header_line='Chương 42', text='https://example.com/x' + 'y' * 900)
        with self.assertRaises(LayoutChunkError) as context:
            split_chapter(chapter, 700, include_header=True)
        self.assertEqual(context.exception.chapter, 42)
        self.assertIn('Chương 42', str(context.exception))

class PipelineIntegrationTests(unittest.TestCase):
    """Step 3/4 planning and edited chunks are validated against the rendered page."""

    def test_group_plan_chunks_carry_layout_metadata_and_render_facts(self):
        from config.settings import Settings
        from media.groups import job_layout_budget, prepare_tts, write_groups
        from tests.test_chapter_groups import document_for
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings()
            source = ('Chương 1\n' + (PROSE * 6) + '\n\n'
                      + '“Ngươi đến rồi?”\n\n“Đã lâu không gặp.”\n\n' * 6)
            doc = document_for(source, root)
            group = write_groups(doc, settings, doc.job_title, 20)[0]
            plan, chunks = prepare_tts(doc, group.group_id, settings)
            self.assertGreater(len(chunks), 1)
            budget = job_layout_budget(doc)
            for entry, chunk in zip(plan['chunks'], chunks):
                self.assertTrue(budget.fits(chunk.text), chunk.text[:60])
                self.assertEqual(entry['layout']['font_size'], DEFAULT_STYLE.body_size)
                self.assertEqual(entry['layout']['body_width'], DEFAULT_STYLE.body_width)
                self.assertEqual(entry['layout']['body_height'], budget.body_height)
                self.assertLessEqual(entry['layout']['measured_height'], budget.body_height)
                self.assertIn(entry['layout']['reason'],
                              {'end_of_text', 'character_limit', 'next_unit_would_exceed_page_height',
                               'chapter_heading', 'hard_split', 'user_override', ''})
                self.assertEqual(entry['layout']['layout_fingerprint'], budget.fingerprint())
            self.assertEqual(plan['config']['layout'], budget.identity())
            self.assertEqual(plan['config']['limit'], 700)
            self.assertIn('layout_limited_chunks', plan['statistics'])
            self.assertIn('layout_fill_average', plan['statistics'])
            self.assertEqual(plan['statistics']['layout_overflow_pages'], 0)
            self.assertTrue(any('fill trung bình' in warning for warning in plan['warnings']))
            regenerated, same = prepare_tts(doc, group.group_id, settings)
            self.assertEqual(regenerated, plan)
            self.assertEqual([c.text for c in same], [c.text for c in chunks])

    def test_layout_identity_change_invalidates_the_saved_plan(self):
        from config.settings import Settings
        from media.groups import job_layout_budget, prepare_tts, write_groups
        from tests.test_chapter_groups import document_for
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings()
            doc = document_for('Chương 1\nHắn bước đi trong căn phòng tối.', root)
            group = write_groups(doc, settings, doc.job_title, 20)[0]
            plan, _ = prepare_tts(doc, group.group_id, settings)
            self.assertEqual(plan['config']['layout'], job_layout_budget(doc).identity())
            narrowed = replace(DEFAULT_STYLE, body_width=900)
            self.assertNotEqual(plan['config']['layout'], layout_identity(narrowed))
            # Another font size or body band re-plans instead of reusing stale chunks.
            self.assertNotEqual(plan['config']['layout'], layout_identity(replace(DEFAULT_STYLE, body_size=40)))
            self.assertNotEqual(plan['config']['layout'],
                                page_budget(title=('Một tựa truyện rất dài và thanh lịch trong ánh sáng '
                                                   'hoàng hôn buông xuống thành cổ, nơi những con đường đá '
                                                   'còn in dấu chân người xưa')).identity())

    def test_edited_failed_chunk_is_validated_against_the_page(self):
        from config.settings import Settings
        from media.groups import edit_failed_chunk, prepare_tts, write_groups
        from pipeline.document import PipelineStateError
        from tests.test_chapter_groups import document_for
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings()
            doc = document_for('Chương 1\nNgươi là ai?Ta không biết.', root)
            group = write_groups(doc, settings, doc.job_title, 20)[0]
            _, chunks = prepare_tts(doc, group.group_id, settings)
            group.state['failures'] = [{'chunk_number': chunks[-1].order}]
            # An edit that cannot fit the page is rejected with the measured facts.
            overflow = '\n\n'.join(['“Ngươi đến rồi?”'] * 40)
            with self.assertRaises(PipelineStateError) as context:
                edit_failed_chunk(doc, group.group_id, settings, chunks[-1].order, overflow)
            message = str(context.exception)
            for fragment in ('visible_lines=', f'font_size={DEFAULT_STYLE.body_size}px',
                             'body_width=1150px', 'chars='):
                self.assertIn(fragment, message)
            edit_failed_chunk(doc, group.group_id, settings, chunks[-1].order, 'Đã sửa!')
            self.assertEqual(prepare_tts(doc, group.group_id, settings)[1][-1].text, 'Đã sửa!')

    def test_tts_cache_reuses_audio_only_for_the_exact_chunk_text(self):
        from config.settings import Settings
        from media.groups import prepare_tts, write_groups
        from media.tts import TtsChunk, TtsProcessor
        from tests.test_chapter_groups import document_for
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings()
            doc = document_for('Chương 1\n' + PROSE * 8, root)
            group = write_groups(doc, settings, doc.job_title, 20)[0]
            _, chunks = prepare_tts(doc, group.group_id, settings)
            audio = root / 'audio'
            calls = []

            class _Client:
                def __init__(self, text):
                    self.text = text

                async def save(self, path):
                    calls.append(self.text)
                    Path(path).write_bytes(b'mp3:' + self.text.encode()[:20])

            def processor(effective):
                return TtsProcessor(effective, audio, voice='voice', ffmpeg_path='/bin/true',
                                    client_factory=lambda t, v: _Client(t))

            first = processor(chunks)
            first.run()
            self.assertEqual(len(calls), len(chunks))
            # Unchanged text resumes from the recorded hashes without new requests.
            self.assertEqual(sorted(processor(chunks).run().skipped), [c.order for c in chunks])
            self.assertEqual(len(calls), len(chunks))
            # A chunk number whose text changed can never reuse the old MP3.
            shifted = [TtsChunk(order=c.order, text=(c.text + ' Thêm.' if c.order == 1 else c.text),
                                chapter=c.chapter) for c in chunks]
            result = processor(shifted).run()
            self.assertEqual(result.generated, [1])
            self.assertEqual(sorted(result.skipped), [c.order for c in chunks[1:]])
            self.assertEqual(len(calls), len(chunks) + 1)


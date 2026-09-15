from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chinese.review import ChineseReviewSession, ReviewStatus, split_lossless_sentences
from tests.support import create_dictionary_fixture


class ChineseReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dictionary = create_dictionary_fixture(Path(self.temp.name))
        self.dictionary.ensure_ready()

    def tearDown(self):
        self.dictionary.close()
        self.temp.cleanup()

    def test_sentence_split_is_complete_and_lossless(self):
        text = 'Một câu 大相国寺! "Câu hai?"\nĐoạn 未知。\n\nCuối'
        parts = split_lossless_sentences(text)
        self.assertEqual("".join(parts), text)
        self.assertIn("Một câu 大相国寺!", parts)

    def test_multiple_fragments_are_reviewed_separately(self):
        text = "Hắn nhìn 大相国寺 rồi đọc 未知词."
        session = ChineseReviewSession(text, self.dictionary)
        sentence = session.current_sentence

        self.assertEqual(session.total_sentences, 1)
        self.assertEqual([item.text for item in sentence.fragments], ["大相国寺", "未知", "词"])
        self.assertEqual(session.working_text, text)

    def test_confirm_and_replace_all_update_only_exact_review_fragments(self):
        text = "Tới 大相国寺. Rời 大相国寺 và 大相."
        session = ChineseReviewSession(text, self.dictionary)
        fragment = session.current_sentence.fragments[0]

        count = session.apply(
            fragment.id, "Đại Tướng Quốc Tự", ReviewStatus.CONFIRMED, replace_all=True
        )

        self.assertEqual(count, 2)
        self.assertEqual(session.working_text.count("Đại Tướng Quốc Tự"), 2)
        self.assertIn("大相.", session.working_text)
        self.assertEqual(session.resolved_sentences, 1)
        self.assertEqual(session.remaining_sentences, 1)

    def test_manual_replacement_and_skip_status(self):
        session = ChineseReviewSession("Một 未知. Hai 大相国寺.", self.dictionary)
        first = session.current_sentence.fragments[0]
        session.skip(first.id)
        self.assertEqual(first.status, ReviewStatus.SKIPPED)
        self.assertFalse(session.is_complete)

        session.next()
        second = session.current_sentence.fragments[0]
        session.apply(second.id, "ngôi chùa", ReviewStatus.MANUAL)
        self.assertIn("ngôi chùa", session.working_text)
        self.assertEqual(session.remaining_sentences, 1)

    def test_manual_replacement_with_han_is_rescanned(self):
        session = ChineseReviewSession("Tới 大相国寺.", self.dictionary)
        fragment = session.current_sentence.fragments[0]
        session.apply(fragment.id, "寺 mới", ReviewStatus.MANUAL)

        self.assertFalse(session.is_complete)
        self.assertEqual(session.current_sentence.fragments[0].text, "寺")

    def test_no_dictionary_still_allows_manual_review(self):
        session = ChineseReviewSession("Từ 未知.", None)
        fragment = session.current_sentence.fragments[0]
        self.assertEqual(fragment.suggestions, ())
        session.apply(fragment.id, "chưa biết", ReviewStatus.MANUAL)
        self.assertTrue(session.is_complete)


if __name__ == "__main__":
    unittest.main()

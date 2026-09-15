from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chinese.master_dictionary import MasterDictionary, MasterDictionaryError
from tests.support import create_dictionary_fixture


class MasterDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dictionary = create_dictionary_fixture(self.root)

    def tearDown(self):
        self.dictionary.close()
        self.temp.cleanup()

    def test_native_sources_are_indexed_and_exact_conflicts_are_preserved(self):
        health = self.dictionary.ensure_ready()

        self.assertTrue(health.rebuilt)
        self.assertGreater(health.indexed_entries, 0)
        self.assertEqual(health.indexed_rules, 2)
        self.assertGreater(health.indexed_phonetics, 0)
        self.assertEqual(health.malformed_rows["Names.txt"], 1)

        temple = self.dictionary.lookup_exact("大相国寺")
        self.assertEqual([item.value for item in temple], ["Đại Tướng Quốc Tự"])
        self.assertEqual(temple[0].sources, ("Names",))

        wind = self.dictionary.lookup_exact("清风")
        self.assertEqual({item.value for item in wind}, {"Thanh Phong", "gió mát"})
        thanh_phong = next(item for item in wind if item.value == "Thanh Phong")
        self.assertEqual(
            set(thanh_phong.sources), {"QualityOverrides", "Names", "VietPhrase_2"}
        )

    def test_slash_values_require_distinct_alternatives(self):
        self.dictionary.ensure_ready()
        values = [item.value for item in self.dictionary.lookup_exact("阻挡不了")]
        self.assertEqual(values, ["không ngăn được", "không ngăn trở"])

    def test_longest_exact_match_wins_before_shorter_key(self):
        self.dictionary.ensure_ready()
        matches = self.dictionary.longest_exact_matches("大相国寺")
        self.assertEqual([item.text for item in matches], ["大相国寺"])

    def test_rules_precede_composed_phonetics_and_ambiguity_is_visible(self):
        self.dictionary.ensure_ready()
        sentence = "Trương Tam 的人."
        suggestions = self.dictionary.suggestions_for_unknown(sentence, 12, 14)

        self.assertEqual({item.value for item in suggestions}, {"người Trương Tam", "Trương Tam nhân"})
        self.assertTrue(all(item.kind == "rule" for item in suggestions))

        phonetics = self.dictionary.phonetic_suggestions("大寺")
        self.assertIn("đại tự", {item.value for item in phonetics})

    def test_cache_is_reused_until_a_source_changes(self):
        first = self.dictionary.ensure_ready()
        self.assertTrue(first.rebuilt)
        self.dictionary.close()

        reused = MasterDictionary(self.dictionary.dictionary_dir, self.dictionary.index_path)
        self.assertFalse(reused.ensure_ready().rebuilt)
        reused.close()

        names = self.dictionary.dictionary_dir / "Names.txt"
        names.write_text(names.read_text(encoding="utf-8") + "新名=Tân Danh\n", encoding="utf-8")
        rebuilt = MasterDictionary(self.dictionary.dictionary_dir, self.dictionary.index_path)
        self.assertTrue(rebuilt.ensure_ready().rebuilt)
        self.assertEqual(rebuilt.lookup_exact("新名")[0].value, "Tân Danh")
        rebuilt.close()

    def test_missing_or_invalid_required_file_fails_without_fallback(self):
        (self.dictionary.dictionary_dir / "Names.txt").unlink()
        with self.assertRaisesRegex(MasterDictionaryError, "missing"):
            self.dictionary.ensure_ready()

        self.dictionary = create_dictionary_fixture(self.root)
        (self.dictionary.dictionary_dir / "dict-default.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(MasterDictionaryError, "phienam"):
            self.dictionary.ensure_ready()


if __name__ == "__main__":
    unittest.main()


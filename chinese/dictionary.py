"""Offline Chinese -> Vietnamese dictionary (bundled, extendable).

Two bundled files live in ``chinese/data``:

* ``sino_vietnamese.tsv`` - Hán-Việt reading of single characters, used as a
  fallback so a phrase without a manual/AI translation still gets a readable
  rendering instead of staying in Han characters.
* ``common_terms.tsv`` - phrases with a real Vietnamese translation, which
  always win over character readings.

The dictionary is a *fallback*: a manual translation wins, then an AI
translation, and only when neither exists does the offline dictionary supply a
common term or a Hán-Việt reading.  This precedence is applied in
:func:`resolve_translation` and is what the translation table reports in its
``source`` column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .detector import is_han

DATA_DIR = Path(__file__).resolve().parent / "data"
SINO_FILE = DATA_DIR / "sino_vietnamese.tsv"
TERMS_FILE = DATA_DIR / "common_terms.tsv"

SOURCE_MANUAL = "manual"
SOURCE_DICTIONARY = "dictionary"
SOURCE_AI = "ai"
SOURCE_GLOSS = "sino-viet"
SOURCE_NONE = "none"

SOURCE_LABELS = {
    SOURCE_MANUAL: "Nhập tay",
    SOURCE_DICTIONARY: "Từ điển offline",
    SOURCE_AI: "AI (Gemini)",
    SOURCE_GLOSS: "Âm Hán-Việt",
    SOURCE_NONE: "Chưa dịch",
}

SOURCE_RANK = {
    SOURCE_MANUAL: 4,
    SOURCE_AI: 3,
    SOURCE_DICTIONARY: 2,
    SOURCE_GLOSS: 1,
    SOURCE_NONE: 0,
}


def _parse_tsv(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    primary: Dict[str, str] = {}
    secondary: Dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return primary, secondary
    for line in content.splitlines():
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        key = parts[0].strip()
        if not key:
            continue
        value = parts[1].strip() if len(parts) > 1 else ""
        gloss = parts[2].strip() if len(parts) > 2 else ""
        if value:
            primary[key] = value
        if gloss:
            secondary[key] = gloss
    return primary, secondary


@dataclass
class DictionaryEntry:
    phrase: str
    translation: str
    source: str
    note: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"phrase": self.phrase, "translation": self.translation, "source": self.source, "note": self.note}


@dataclass
class Dictionary:
    """Bundled + user supplied phrase and character dictionaries."""

    terms: Dict[str, str] = field(default_factory=dict)
    readings: Dict[str, str] = field(default_factory=dict)
    glosses: Dict[str, str] = field(default_factory=dict)
    files: List[str] = field(default_factory=list)
    auto_readings: bool = True

    # ------------------------------------------------------------- loading
    @classmethod
    def load(
        cls,
        extra_paths: Optional[Iterable[str]] = None,
        *,
        include_bundled: bool = True,
        auto_readings: bool = True,
    ) -> "Dictionary":
        dictionary = cls(auto_readings=auto_readings)
        if include_bundled:
            dictionary.load_file(SINO_FILE, kind="reading")
            dictionary.load_file(TERMS_FILE, kind="term")
        for path in extra_paths or []:
            dictionary.load_file(Path(path).expanduser(), kind="auto")
        return dictionary

    def load_file(self, path: Path, kind: str = "auto") -> bool:
        if not path or not str(path):
            return False
        if not path.exists():
            return False
        primary, secondary = _parse_tsv(path)
        if not primary:
            return False
        if kind == "term":
            self.terms.update(primary)
        elif kind == "reading":
            self.readings.update(primary)
            self.glosses.update(secondary)
        else:
            for key, value in primary.items():
                if len(key) == 1 and is_han(key):
                    self.readings[key] = value
                else:
                    self.terms[key] = value
            self.glosses.update(secondary)
        self.files.append(str(path))
        return True

    def add_term(self, phrase: str, translation: str) -> None:
        phrase = (phrase or "").strip()
        if phrase and translation:
            self.terms[phrase] = translation.strip()

    # ------------------------------------------------------------ querying
    @property
    def phrase_count(self) -> int:
        return len(self.terms)

    @property
    def reading_count(self) -> int:
        return len(self.readings)

    def lookup_phrase(self, phrase: str) -> Optional[DictionaryEntry]:
        """Exact phrase lookup (longest match handled by the replacer)."""
        key = (phrase or "").strip()
        if not key:
            return None
        if key in self.terms:
            return DictionaryEntry(key, self.terms[key], SOURCE_DICTIONARY)
        if key in self.glosses:
            return DictionaryEntry(key, self.glosses[key], SOURCE_DICTIONARY, note="nghĩa thường dùng")
        if len(key) == 1 and key in self.readings:
            return DictionaryEntry(key, self.readings[key], SOURCE_GLOSS)
        return None

    def reading_of(self, phrase: str) -> str:
        """Hán-Việt reading for a phrase, character by character."""
        if not phrase:
            return ""
        pieces: List[str] = []
        for char in phrase:
            if is_han(char):
                reading = self.readings.get(char)
                if not reading:
                    return ""
                pieces.append(reading)
            elif char.isspace():
                continue
            else:
                pieces.append(char)
        return " ".join(pieces).strip()

    def best_effort(self, phrase: str) -> Optional[DictionaryEntry]:
        """Term first, then Hán-Việt reading, then nothing."""
        entry = self.lookup_phrase(phrase)
        if entry is not None:
            return entry
        if len(phrase.strip()) > 1:
            reading = self.reading_of(phrase)
            if reading:
                return DictionaryEntry(phrase, reading, SOURCE_GLOSS, note="đọc theo âm Hán-Việt")
        return None

    def candidates_for(self, text: str) -> List[DictionaryEntry]:
        """Every phrase of the dictionary that occurs inside *text*."""
        found: List[DictionaryEntry] = []
        for phrase, translation in self.terms.items():
            if phrase and phrase in text:
                found.append(DictionaryEntry(phrase, translation, SOURCE_DICTIONARY))
        for phrase, translation in self.glosses.items():
            if phrase and phrase in text and phrase not in self.terms:
                found.append(DictionaryEntry(phrase, translation, SOURCE_DICTIONARY, note="nghĩa thường dùng"))
        found.sort(key=lambda entry: len(entry.phrase), reverse=True)
        return found

    def summary(self) -> str:
        return (
            f"Từ điển offline: {self.phrase_count} cụm, "
            f"{self.reading_count} ký tự Hán-Việt ({len(self.files)} tệp)."
        )


_CACHE: Dict[Tuple[Tuple[str, ...], bool], Dictionary] = {}


def get_dictionary(extra_paths: Optional[Iterable[str]] = None, *, auto_readings: bool = True) -> Dictionary:
    """Load (and cache) the dictionary for the given extra paths."""
    key = (tuple(sorted(str(p) for p in (extra_paths or []))), auto_readings)
    cached = _CACHE.get(key)
    if cached is None:
        cached = Dictionary.load(extra_paths, auto_readings=auto_readings)
        _CACHE[key] = cached
    return cached


def clear_dictionary_cache() -> None:
    _CACHE.clear()


def resolve_translation(
    phrase: str,
    *,
    manual: Optional[Dict[str, str]] = None,
    ai: Optional[Dict[str, str]] = None,
    dictionary: Optional[Dictionary] = None,
    allow_gloss: bool = True,
) -> DictionaryEntry:
    """Resolve one phrase using the documented precedence.

    manual > AI > offline dictionary (common term, then meaning, then reading).
    The dictionary is only a fallback, so it never overrides a real translation.
    """
    phrase = (phrase or "").strip()
    manual = manual or {}
    ai = ai or {}
    if phrase in manual and manual[phrase].strip():
        return DictionaryEntry(phrase, manual[phrase].strip(), SOURCE_MANUAL)
    if phrase in ai and ai[phrase].strip():
        return DictionaryEntry(phrase, ai[phrase].strip(), SOURCE_AI)
    if dictionary is not None:
        entry = dictionary.best_effort(phrase)
        if entry is not None and (allow_gloss or entry.source != SOURCE_GLOSS):
            return entry
    return DictionaryEntry(phrase, "", SOURCE_NONE)

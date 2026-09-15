"""Persistent translation table (manual edits, AI results, source tracking).

Stored as a small JSON file next to the local configuration so that user edits
survive reruns and pipeline restarts.  Manual edits always outrank AI results,
which outrank the offline dictionary.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from chinese.dictionary import (
    SOURCE_AI,
    SOURCE_DICTIONARY,
    SOURCE_GLOSS,
    SOURCE_MANUAL,
    SOURCE_NONE,
    SOURCE_RANK,
    Dictionary,
)
from config.settings import config_dir

TABLE_FILE_NAME = "translations.json"


@dataclass
class TranslationRecord:
    phrase: str
    translation: str = ""
    source: str = SOURCE_NONE
    count: int = 0
    edited: bool = False
    updated_at: float = 0.0
    chapters: List[int] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "phrase": self.phrase,
            "translation": self.translation,
            "source": self.source,
            "count": self.count,
            "edited": self.edited,
            "updated_at": self.updated_at,
            "chapters": list(self.chapters),
            "locations": list(self.locations),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "TranslationRecord":
        return cls(
            phrase=str(data.get("phrase", "")),
            translation=str(data.get("translation", "")),
            source=str(data.get("source", SOURCE_NONE)),
            count=int(data.get("count", 0) or 0),
            edited=bool(data.get("edited", False)),
            updated_at=float(data.get("updated_at", 0.0) or 0.0),
            chapters=[int(n) for n in data.get("chapters", []) or []],
            locations=[str(item) for item in data.get("locations", []) or []],
            note=str(data.get("note", "")),
        )

    @property
    def translated(self) -> bool:
        return bool(self.translation.strip())

    @property
    def source_label(self) -> str:
        from chinese.dictionary import SOURCE_LABELS

        return SOURCE_LABELS.get(self.source, self.source)


class TranslationStore:
    """The persisted translation table."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else config_dir() / TABLE_FILE_NAME
        self.records: Dict[str, TranslationRecord] = {}
        self.dirty = False

    # -------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "TranslationStore":
        store = cls(path)
        try:
            with open(store.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return store
        items = payload.get("records", payload if isinstance(payload, list) else [])
        if isinstance(items, dict):
            items = list(items.values())
        for item in items or []:
            if not isinstance(item, dict):
                continue
            record = TranslationRecord.from_dict(item)
            if record.phrase:
                store.records[record.phrase] = record
        return store

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path else self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": time.time(),
            "records": [record.to_dict() for record in self.sorted_records()],
        }
        tmp = target.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
        self.dirty = False
        return target

    # ------------------------------------------------------------ accessors
    def __len__(self) -> int:
        return len(self.records)

    def get(self, phrase: str) -> Optional[TranslationRecord]:
        return self.records.get((phrase or "").strip())

    def translation_map(self) -> Dict[str, str]:
        return {phrase: record.translation for phrase, record in self.records.items() if record.translated}

    def source_map(self) -> Dict[str, str]:
        return {phrase: record.source for phrase, record in self.records.items() if record.translated}

    def add(self, phrase: str, translation: str, source: str = SOURCE_MANUAL, **kwargs) -> TranslationRecord:
        phrase = (phrase or "").strip()
        record = self.records.get(phrase)
        if record is None:
            record = TranslationRecord(phrase=phrase)
            self.records[phrase] = record
        if source in (SOURCE_MANUAL, SOURCE_AI) and record.translated and record.edited and source == SOURCE_AI:
            return record  # never overwrite a manual edit with AI output
        record.translation = (translation or "").strip()
        record.source = source if record.translation else SOURCE_NONE
        record.updated_at = time.time()
        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)
        if source == SOURCE_MANUAL:
            record.edited = True
        self.dirty = True
        return record

    def set_manual(self, phrase: str, translation: str) -> TranslationRecord:
        record = self.add(phrase, translation, source=SOURCE_MANUAL if translation.strip() else SOURCE_NONE)
        record.edited = True
        return record

    def merge(self, other: "TranslationStore", *, prefer: str = SOURCE_MANUAL) -> int:
        """Merge another store, keeping the higher priority translation."""
        changes = 0
        for phrase, record in other.records.items():
            existing = self.records.get(phrase)
            if existing is None:
                self.records[phrase] = record
                changes += 1
                continue
            if not record.translated:
                continue
            if not existing.translated:
                existing.translation = record.translation
                existing.source = record.source
                changes += 1
                continue
            if SOURCE_RANK.get(record.source, 0) > SOURCE_RANK.get(existing.source, 0):
                existing.translation = record.translation
                existing.source = record.source
                changes += 1
        self.dirty = self.dirty or changes > 0
        return changes

    def fill_from_dictionary(self, phrases: Iterable[str], dictionary: Dictionary, *, allow_gloss: bool = True) -> int:
        """Fill missing translations from the offline dictionary."""
        filled = 0
        for phrase in phrases:
            phrase = (phrase or "").strip()
            if not phrase:
                continue
            record = self.records.get(phrase)
            if record is not None and record.translated:
                continue
            entry = dictionary.best_effort(phrase)
            if entry is None:
                continue
            if not allow_gloss and entry.source == SOURCE_GLOSS:
                continue
            self.add(phrase, entry.translation, source=entry.source, note=entry.note)
            filled += 1
        return filled

    def sync_records(self, phrases: Sequence[str], *, prune: bool = False) -> None:
        """Make sure every detected phrase has a record (keeps existing data)."""
        for phrase in phrases:
            phrase = (phrase or "").strip()
            if phrase and phrase not in self.records:
                self.records[phrase] = TranslationRecord(phrase=phrase)

    def sorted_records(self, *, by: str = "count") -> List[TranslationRecord]:
        items = list(self.records.values())
        if by == "alphabetical":
            items.sort(key=lambda record: record.phrase)
        elif by == "length":
            items.sort(key=lambda record: (-len(record.phrase), record.phrase))
        elif by == "status":
            items.sort(key=lambda record: (record.source, -record.count, record.phrase))
        else:
            items.sort(key=lambda record: (-record.count, record.phrase))
        return items

    def stats(self) -> Dict[str, object]:
        counts: Dict[str, int] = {}
        for record in self.records.values():
            counts[record.source] = counts.get(record.source, 0) + 1
        return {
            "total": len(self.records),
            "translated": sum(1 for record in self.records.values() if record.translated),
            "manual": counts.get(SOURCE_MANUAL, 0),
            "ai": counts.get(SOURCE_AI, 0),
            "dictionary": counts.get(SOURCE_DICTIONARY, 0) + counts.get(SOURCE_GLOSS, 0),
            "pending": sum(1 for record in self.records.values() if not record.translated),
        }


def build_records(
    groups: Iterable,
    store: TranslationStore,
    *,
    dictionary: Optional[Dictionary] = None,
    per_chapter: Optional[Dict[str, List[int]]] = None,
) -> List[TranslationRecord]:
    """Combine detected phrase groups with the stored table for the UI."""
    records: List[TranslationRecord] = []
    for group in groups:
        phrase = group.phrase
        stored = store.get(phrase)
        record = TranslationRecord(
            phrase=phrase,
            translation=stored.translation if stored else "",
            source=stored.source if stored and stored.translated else SOURCE_NONE,
            count=group.count,
            edited=bool(stored.edited) if stored else False,
            updated_at=stored.updated_at if stored else 0.0,
            chapters=list(group.chapter_numbers),
            locations=group.location_labels(limit=5),
        )
        if not record.translated and dictionary is not None:
            entry = dictionary.best_effort(phrase)
            if entry is not None:
                record.translation = entry.translation
                record.source = entry.source
                record.note = entry.note
        records.append(record)
    return records


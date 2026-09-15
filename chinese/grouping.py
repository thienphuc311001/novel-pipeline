"""Grouping of duplicate Chinese phrases with occurrence counts.

The localization tool groups every identical phrase (and optionally its
containing line) so the translator only types each translation once.  Counts
and source locations are kept per phrase, and the group list is what the
translation table shows.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from .detector import LocatedSegment, is_han


@dataclass
class PhraseGroup:
    """All occurrences of one Chinese phrase."""

    phrase: str
    count: int = 0
    locations: List[LocatedSegment] = field(default_factory=list)
    chapter_numbers: List[int] = field(default_factory=list)
    translated: str = ""
    source: str = "none"
    status: str = "pending"

    @property
    def char_count(self) -> int:
        return len(self.phrase)

    @property
    def location_count(self) -> int:
        return len(self.locations)

    def location_labels(self, limit: int = 5) -> List[str]:
        labels = []
        seen = set()
        for location in self.locations:
            label = location.location_label()
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
            if len(labels) >= limit:
                break
        return labels

    def to_dict(self) -> Dict[str, object]:
        return {
            "phrase": self.phrase,
            "count": self.count,
            "char_count": self.char_count,
            "chapters": list(self.chapter_numbers),
            "locations": [loc.to_dict() for loc in self.locations[:200]],
            "location_count": self.location_count,
            "translated": self.translated,
            "source": self.source,
            "status": self.status,
        }


@dataclass
class GroupingResult:
    groups: List[PhraseGroup] = field(default_factory=list)
    total_occurrences: int = 0
    total_han_chars: int = 0
    unique_phrases: int = 0
    mode: str = "segments"

    def to_dict(self) -> Dict[str, object]:
        return {
            "unique_phrases": self.unique_phrases,
            "total_occurrences": self.total_occurrences,
            "total_han_chars": self.total_han_chars,
            "mode": self.mode,
        }

    def summary(self) -> str:
        return (
            f"{self.unique_phrases} cụm Trung duy nhất, "
            f"{self.total_occurrences} lần xuất hiện, {self.total_han_chars} ký tự Hán."
        )


def group_segments(
    segments: Sequence[LocatedSegment],
    *,
    mode: str = "segments",
    translations: Optional[Dict[str, str]] = None,
    translation_sources: Optional[Dict[str, str]] = None,
) -> GroupingResult:
    """Group identical phrases and attach occurrence counts and locations."""
    translations = translations or {}
    translation_sources = translation_sources or {}
    buckets: Dict[str, PhraseGroup] = {}
    total_chars = 0
    for segment in segments:
        phrase = segment.text.strip()
        if not phrase:
            continue
        group = buckets.get(phrase)
        if group is None:
            group = PhraseGroup(phrase=phrase)
            buckets[phrase] = group
        group.count += 1
        if len(group.locations) < 2000:
            group.locations.append(segment)
        if segment.chapter is not None and segment.chapter not in group.chapter_numbers:
            group.chapter_numbers.append(segment.chapter)
        total_chars += len(phrase)

    groups = list(buckets.values())
    for group in groups:
        translation = translations.get(group.phrase, "")
        group.translated = translation
        group.source = translation_sources.get(group.phrase, "none") if translation else "none"
        if translation:
            group.status = "translated"
        elif group.source == "ai":
            group.status = "ai"
        else:
            group.status = "pending"
        group.chapter_numbers.sort()
    groups.sort(key=lambda g: (-g.count, g.phrase))
    return GroupingResult(
        groups=groups,
        total_occurrences=len(segments),
        total_han_chars=total_chars,
        unique_phrases=len(groups),
        mode=mode,
    )


FILTERS: Dict[str, Callable[[PhraseGroup], bool]] = {
    "all": lambda group: True,
    "pending": lambda group: not group.translated,
    "translated": lambda group: bool(group.translated),
    "long": lambda group: group.char_count >= 3,
}


def filter_groups(
    groups: Iterable[PhraseGroup],
    *,
    query: str = "",
    status: str = "all",
    sort: str = "count",
) -> List[PhraseGroup]:
    """Filter/sort groups for the translation table."""
    predicate = FILTERS.get(status, FILTERS["all"])
    needle = (query or "").strip().lower()
    result = []
    for group in groups:
        if not predicate(group):
            continue
        if needle and needle not in group.phrase.lower() and needle not in (group.translated or "").lower():
            continue
        result.append(group)
    if sort == "alphabetical":
        result.sort(key=lambda g: g.phrase)
    elif sort == "length":
        result.sort(key=lambda g: (-g.char_count, g.phrase))
    elif sort == "status":
        result.sort(key=lambda g: (g.status, -g.count, g.phrase))
    else:
        result.sort(key=lambda g: (-g.count, g.phrase))
    return result

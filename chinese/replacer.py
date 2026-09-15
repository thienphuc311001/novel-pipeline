"""Chinese phrase replacement over the whole working text.

Rules that matter for correctness (kept exactly, they were the reason the
original tool existed):

* Phrases are applied from **longest to shortest** so ``修炼者`` is replaced
  before ``修炼``; without that order a shorter phrase would corrupt the longer
  one into ``tu luyện giả`` -> ``tu luyện`` + leftover ``giả``.
* Only phrases that actually occur are considered.
* A phrase that is a substring of an already applied longer phrase is skipped
  when the longer replacement has already been written (tracked via a
  placeholder pass), so replacements never cascade into each other.
* Replacement runs over the whole working text (and optionally chapter by
  chapter for reporting), never deleting text: an empty translation means the
  phrase is left untouched and reported instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .detector import is_han
from .dictionary import SOURCE_AI, SOURCE_DICTIONARY, SOURCE_GLOSS, SOURCE_MANUAL

PLACEHOLDER_PREFIX = "\u0001NP"
PLACEHOLDER_SUFFIX = "\u0001"
PLACEHOLDER_RE = re.compile(re.escape(PLACEHOLDER_PREFIX) + r"(\d+)" + re.escape(PLACEHOLDER_SUFFIX))


@dataclass
class ReplacementEntry:
    phrase: str
    translation: str
    source: str
    count: int = 0
    skipped_reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "phrase": self.phrase,
            "translation": self.translation,
            "source": self.source,
            "count": self.count,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class ReplacementReport:
    text: str = ""
    entries: List[ReplacementEntry] = field(default_factory=list)
    total_replacements: int = 0
    remaining_chars: int = 0
    remaining_segments: int = 0
    before_chars: int = 0
    after_chars: int = 0

    @property
    def applied(self) -> List[ReplacementEntry]:
        return [entry for entry in self.entries if entry.count]

    @property
    def skipped(self) -> List[ReplacementEntry]:
        return [entry for entry in self.entries if entry.skipped_reason]

    def summary(self) -> str:
        return (
            f"{self.total_replacements} lượt thay thế, {len(self.applied)} cụm được áp dụng"
            + (
                f", còn {self.remaining_chars} ký tự Hán trong {self.remaining_segments} cụm."
                if self.remaining_chars
                else ", không còn ký tự Hán."
            )
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "total_replacements": self.total_replacements,
            "applied_phrases": len(self.applied),
            "remaining_chars": self.remaining_chars,
            "remaining_segments": self.remaining_segments,
            "before_chars": self.before_chars,
            "after_chars": self.after_chars,
            "entries": [entry.to_dict() for entry in self.entries if entry.count or entry.skipped_reason],
        }


def order_phrases_longest_first(phrases: Iterable[str]) -> List[str]:
    """Sort phrases longest first (ties broken alphabetically for stability)."""
    unique = {phrase for phrase in phrases if phrase}
    return sorted(unique, key=lambda phrase: (-len(phrase), phrase))


def _remaining_han(text: str) -> Tuple[int, int]:
    chars = sum(1 for char in text if is_han(char))
    segments = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", text))
    return chars, segments


def replace_phrases(
    text: str,
    translations: Dict[str, str],
    *,
    sources: Optional[Dict[str, str]] = None,
    require_han: bool = True,
    protected: Optional[Sequence[str]] = None,
) -> ReplacementReport:
    """Replace Chinese phrases in *text* from longest phrase to shortest."""
    report = ReplacementReport(text=text or "", before_chars=len(text or ""))
    sources = sources or {}
    if not text:
        return report

    usable: Dict[str, str] = {}
    for phrase, translation in (translations or {}).items():
        if not phrase:
            continue
        if require_han and not any(is_han(char) for char in phrase):
            continue
        if not translation or not str(translation).strip():
            continue
        if phrase not in text:
            continue
        usable[phrase] = str(translation)

    working = text
    placeholders: List[str] = []

    def _store(value: str) -> str:
        placeholders.append(value)
        return f"{PLACEHOLDER_PREFIX}{len(placeholders) - 1}{PLACEHOLDER_SUFFIX}"

    protected_values = list(protected or [])
    for phrase in protected_values:
        count = working.count(phrase)
        if count:
            working = working.replace(phrase, _store(phrase))
            report.entries.append(
                ReplacementEntry(
                    phrase=phrase,
                    translation="",
                    source="protected",
                    count=0,
                    skipped_reason="Cụm được bảo vệ (không dịch theo yêu cầu).",
                )
            )

    for phrase in order_phrases_longest_first(usable.keys()):
        translation = usable[phrase]
        count = working.count(phrase)
        if not count:
            continue
        working = working.replace(phrase, _store(translation))
        report.entries.append(
            ReplacementEntry(
                phrase=phrase,
                translation=translation,
                source=sources.get(phrase, SOURCE_MANUAL),
                count=count,
            )
        )
        report.total_replacements += count

    def _restore(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 0 <= index < len(placeholders):
            return placeholders[index]
        return match.group(0)

    working = PLACEHOLDER_RE.sub(_restore, working)
    leftover = PLACEHOLDER_RE.findall(working)
    if leftover:  # pragma: no cover - defensive, indicates index corruption
        working = PLACEHOLDER_RE.sub("", working)
    # A literal SOH pair that came from the source text is left as-is.
    working = working.replace(PLACEHOLDER_PREFIX, "\u0001").replace(PLACEHOLDER_SUFFIX, "\u0001")

    report.text = working
    report.after_chars = len(working)
    report.remaining_chars, report.remaining_segments = _remaining_han(working)
    return report


def replace_chapter_texts(
    chapters: Sequence,
    translations: Dict[str, str],
    *,
    sources: Optional[Dict[str, str]] = None,
    include_headers: bool = False,
) -> Tuple[ReplacementReport, List[Dict[str, object]]]:
    """Apply phrase replacement to every chapter, reporting per chapter."""
    combined = ReplacementReport()
    per_chapter: List[Dict[str, object]] = []
    all_entries: List[ReplacementEntry] = []
    total = 0
    before_chars = 0
    after_chars = 0
    for chapter in chapters:
        body = chapter.text or ""
        before_chars += len(body)
        result = replace_phrases(body, translations, sources=sources)
        chapter.text = result.text
        chapter.char_count = len(result.text)
        if include_headers and chapter.header_line:
            header_result = replace_phrases(chapter.header_line, translations, sources=sources)
            chapter.header_line = header_result.text
        total += result.total_replacements
        all_entries.extend(result.entries)
        after_chars += len(result.text)
        per_chapter.append(
            {
                "chapter": chapter.number,
                "replacements": result.total_replacements,
                "remaining_chars": result.remaining_chars,
                "before_chars": len(body),
                "after_chars": len(result.text),
            }
        )
    combined.entries = all_entries
    combined.total_replacements = total
    combined.before_chars = before_chars
    combined.after_chars = after_chars
    if after_chars:
        merged = "\n".join(chapter.text or "" for chapter in chapters)
        combined.remaining_chars, combined.remaining_segments = _remaining_han(merged)
    return combined, per_chapter


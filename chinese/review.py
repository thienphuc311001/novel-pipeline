"""Sentence-based, lossless review model for residual Han characters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from .detector import chinese_segments, has_han
from .master_dictionary import MasterDictionary, MasterSuggestion


SENTENCE_ENDINGS = frozenset(".!?…。！？")
CLOSING_PUNCTUATION = frozenset("\"'”’）)]】》〉」』")


class ReviewStatus(str, Enum):
    UNRESOLVED = "Unresolved"
    CONFIRMED = "Confirmed"
    MANUAL = "Manual"
    SKIPPED = "Skipped"


@dataclass
class ReviewFragment:
    id: str
    sentence_id: int
    text: str
    start: int
    end: int
    suggestions: Tuple[MasterSuggestion, ...] = ()
    status: ReviewStatus = ReviewStatus.UNRESOLVED
    selected_suggestion: int = -1

    @property
    def has_suggestion(self) -> bool:
        return bool(self.suggestions)

    @property
    def needs_explicit_choice(self) -> bool:
        return len(self.suggestions) != 1


@dataclass
class ReviewAction:
    sentence_id: int
    fragment: str
    replacement: str
    status: ReviewStatus
    replace_all: bool = False


@dataclass
class ReviewSentence:
    id: int
    text: str
    fragments: List[ReviewFragment] = field(default_factory=list)
    skipped: List[Tuple[str, int]] = field(default_factory=list)

    @property
    def unresolved(self) -> bool:
        return has_han(self.text)

    @property
    def display_text(self) -> str:
        return self.text.strip()


def split_lossless_sentences(text: str) -> List[str]:
    """Split for review while guaranteeing ``''.join(parts) == text``."""
    if not text:
        return []
    parts: List[str] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            parts.append(text[start:index + 1])
            start = index + 1
            index += 1
            continue
        if char in SENTENCE_ENDINGS:
            end = index + 1
            while end < len(text) and text[end] in SENTENCE_ENDINGS:
                end += 1
            while end < len(text) and text[end] in CLOSING_PUNCTUATION:
                end += 1
            parts.append(text[start:end])
            start = end
            index = end
            continue
        index += 1
    if start < len(text):
        parts.append(text[start:])
    return parts


class ChineseReviewSession:
    """Mutable Step 2 review state over lossless sentence units."""

    def __init__(
        self,
        text: str,
        dictionary: Optional[MasterDictionary],
        *,
        source_revision: int = 0,
    ) -> None:
        self.source_text = text or ""
        self.source_revision = source_revision
        self.dictionary = dictionary
        self.sentences = [
            ReviewSentence(index, part)
            for index, part in enumerate(split_lossless_sentences(self.source_text))
        ]
        self.review_sentence_ids = [sentence.id for sentence in self.sentences if sentence.unresolved]
        self.current_position = 0
        self.actions: List[ReviewAction] = []
        self._generation = 0
        self.scan_all()

    def clone(self) -> "ChineseReviewSession":
        clone = object.__new__(ChineseReviewSession)
        clone.source_text = self.source_text
        clone.source_revision = self.source_revision
        clone.dictionary = self.dictionary
        clone.sentences = [
            ReviewSentence(
                sentence.id,
                sentence.text,
                [
                    ReviewFragment(
                        fragment.id,
                        fragment.sentence_id,
                        fragment.text,
                        fragment.start,
                        fragment.end,
                        fragment.suggestions,
                        fragment.status,
                        fragment.selected_suggestion,
                    )
                    for fragment in sentence.fragments
                ],
                list(sentence.skipped),
            )
            for sentence in self.sentences
        ]
        clone.review_sentence_ids = list(self.review_sentence_ids)
        clone.current_position = self.current_position
        clone.actions = list(self.actions)
        clone._generation = self._generation
        return clone

    # ------------------------------------------------------------- scanning
    def scan_all(self) -> None:
        for sentence_id in self.review_sentence_ids:
            self._scan_sentence(self.sentences[sentence_id])
        self._clamp_position()

    def _scan_sentence(self, sentence: ReviewSentence) -> None:
        self._generation += 1
        text = sentence.text
        if not has_han(text):
            sentence.fragments = []
            return

        exact_fragments: List[ReviewFragment] = []
        exact_spans: List[Tuple[int, int]] = []
        runs = chinese_segments(text)
        if self.dictionary is not None:
            for run in runs:
                for match in self.dictionary.longest_exact_matches(run.text):
                    start = run.start + match.start
                    end = run.start + match.end
                    exact_spans.append((start, end))
                    exact_fragments.append(
                        self._fragment(sentence.id, match.text, start, end, match.suggestions)
                    )

        fragments: List[ReviewFragment] = list(exact_fragments)
        occupied = list(exact_spans)
        for run in runs:
            uncovered = self._uncovered_intervals(run.start, run.end, exact_spans)
            for start, end in uncovered:
                suggestions: Tuple[MasterSuggestion, ...] = ()
                fragment_start, fragment_end = start, end
                if self.dictionary is not None:
                    suggestions = self.dictionary.suggestions_for_unknown(
                        text, start, end, blocked_spans=occupied
                    )
                    rule_suggestions = [item for item in suggestions if item.kind == "rule"]
                    if rule_suggestions:
                        first = rule_suggestions[0]
                        assert first.replacement_start is not None and first.replacement_end is not None
                        fragment_start = first.replacement_start
                        fragment_end = first.replacement_end
                        suggestions = tuple(
                            item
                            for item in rule_suggestions
                            if item.replacement_start == fragment_start
                            and item.replacement_end == fragment_end
                        )
                if any(fragment_start < right and fragment_end > left for left, right in occupied):
                    # An exact phrase or a more specific rule owns this span.
                    continue
                occupied.append((fragment_start, fragment_end))
                fragments.append(
                    self._fragment(
                        sentence.id,
                        text[fragment_start:fragment_end],
                        fragment_start,
                        fragment_end,
                        suggestions,
                    )
                )

        fragments.sort(key=lambda item: (item.start, -(item.end - item.start), item.text))
        self._restore_skipped_status(sentence, fragments)
        sentence.fragments = fragments

    def _fragment(
        self,
        sentence_id: int,
        text: str,
        start: int,
        end: int,
        suggestions: Tuple[MasterSuggestion, ...],
    ) -> ReviewFragment:
        fragment = ReviewFragment(
            id=f"s{sentence_id}:g{self._generation}:{start}:{end}",
            sentence_id=sentence_id,
            text=text,
            start=start,
            end=end,
            suggestions=suggestions,
        )
        if len(suggestions) == 1:
            fragment.selected_suggestion = 0
        return fragment

    @staticmethod
    def _uncovered_intervals(
        start: int, end: int, covered: Sequence[Tuple[int, int]]
    ) -> List[Tuple[int, int]]:
        relevant = sorted(
            (max(start, left), min(end, right))
            for left, right in covered
            if left < end and right > start
        )
        result: List[Tuple[int, int]] = []
        cursor = start
        for left, right in relevant:
            if cursor < left:
                result.append((cursor, left))
            cursor = max(cursor, right)
        if cursor < end:
            result.append((cursor, end))
        return result

    @staticmethod
    def _restore_skipped_status(
        sentence: ReviewSentence, fragments: List[ReviewFragment]
    ) -> None:
        unused = list(sentence.skipped)
        for fragment in fragments:
            candidates = [item for item in unused if item[0] == fragment.text]
            if not candidates:
                continue
            closest = min(candidates, key=lambda item: abs(item[1] - fragment.start))
            fragment.status = ReviewStatus.SKIPPED
            unused.remove(closest)

    # -------------------------------------------------------------- access
    @property
    def working_text(self) -> str:
        return "".join(sentence.text for sentence in self.sentences)

    @property
    def total_sentences(self) -> int:
        return len(self.review_sentence_ids)

    @property
    def remaining_sentences(self) -> int:
        return sum(1 for sentence_id in self.review_sentence_ids if self.sentences[sentence_id].unresolved)

    @property
    def resolved_sentences(self) -> int:
        return self.total_sentences - self.remaining_sentences

    @property
    def is_complete(self) -> bool:
        return not has_han(self.working_text)

    @property
    def current_sentence(self) -> Optional[ReviewSentence]:
        if not self.review_sentence_ids:
            return None
        self._clamp_position()
        return self.sentences[self.review_sentence_ids[self.current_position]]

    def progress_text(self) -> str:
        return (
            f"Total sentences: {self.total_sentences}    "
            f"Resolved: {self.resolved_sentences}    "
            f"Remaining: {self.remaining_sentences}"
        )

    def previous(self) -> Optional[ReviewSentence]:
        if self.review_sentence_ids:
            self.current_position = max(0, self.current_position - 1)
        return self.current_sentence

    def next(self) -> Optional[ReviewSentence]:
        if self.review_sentence_ids:
            self.current_position = min(len(self.review_sentence_ids) - 1, self.current_position + 1)
        return self.current_sentence

    def _clamp_position(self) -> None:
        if not self.review_sentence_ids:
            self.current_position = 0
        else:
            self.current_position = max(0, min(self.current_position, len(self.review_sentence_ids) - 1))

    def fragment_by_id(self, fragment_id: str) -> Optional[ReviewFragment]:
        for sentence_id in self.review_sentence_ids:
            for fragment in self.sentences[sentence_id].fragments:
                if fragment.id == fragment_id:
                    return fragment
        return None

    def actions_for_sentence(self, sentence_id: int) -> List[ReviewAction]:
        return [action for action in self.actions if action.sentence_id == sentence_id]

    # -------------------------------------------------------------- actions
    def skip(self, fragment_id: str) -> None:
        fragment = self.fragment_by_id(fragment_id)
        if fragment is None:
            raise ValueError("The selected Chinese fragment is no longer current.")
        fragment.status = ReviewStatus.SKIPPED
        sentence = self.sentences[fragment.sentence_id]
        marker = (fragment.text, fragment.start)
        if marker not in sentence.skipped:
            sentence.skipped.append(marker)
        self.actions.append(
            ReviewAction(fragment.sentence_id, fragment.text, "", ReviewStatus.SKIPPED)
        )

    def apply(
        self,
        fragment_id: str,
        replacement: str,
        status: ReviewStatus,
        *,
        replace_all: bool = False,
    ) -> int:
        replacement = (replacement or "").strip()
        if not replacement:
            raise ValueError("Replacement text cannot be empty.")
        if status not in (ReviewStatus.CONFIRMED, ReviewStatus.MANUAL):
            raise ValueError("A replacement must be Confirmed or Manual.")
        fragment = self.fragment_by_id(fragment_id)
        if fragment is None:
            raise ValueError("The selected Chinese fragment is no longer current.")

        target = fragment.text
        targets: Dict[int, List[ReviewFragment]] = {}
        if replace_all:
            for sentence_id in self.review_sentence_ids:
                for candidate in self.sentences[sentence_id].fragments:
                    if candidate.text == target:
                        targets.setdefault(sentence_id, []).append(candidate)
        else:
            targets[fragment.sentence_id] = [fragment]

        applied = 0
        for sentence_id, candidates in targets.items():
            sentence = self.sentences[sentence_id]
            selected: List[ReviewFragment] = []
            right_edge = len(sentence.text) + 1
            for candidate in sorted(candidates, key=lambda item: (item.start, item.end), reverse=True):
                if candidate.end > right_edge:
                    continue
                sentence.text = (
                    sentence.text[:candidate.start] + replacement + sentence.text[candidate.end:]
                )
                right_edge = candidate.start
                applied += 1
                selected.append(candidate)
                self.actions.append(
                    ReviewAction(sentence_id, target, replacement, status, replace_all)
                )
            if selected:
                sentence.skipped = [item for item in sentence.skipped if item[0] != target]
                self._scan_sentence(sentence)
        return applied

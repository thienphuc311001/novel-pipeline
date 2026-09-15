"""Duplicate chapter detection and resolution with exact priority rules.

Resolution priority (from highest to lowest):
1. Vietnamese candidate over Chinese candidate
2. Candidate with meaningful title/content over bare chapter number
3. Longer and more complete candidate over shorter candidate
4. Original document position (first occurrence wins on tie)

Key behaviors:
- Only removes redundant chapter HEADERS, never the chapter body
- Chinese headers are structural and will be normalized to "Chương X"
- Vietnamese headers with content/title are preserved intact
- All resolution reasons are tracked and reported
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from pipeline.document import Chapter

# Language detection patterns
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ỹà-ỹ]")


@dataclass
class DuplicateVariant:
    """One candidate copy of a chapter number."""
    
    chapter: Chapter
    index: int
    language: str
    has_title: bool
    chars: int
    score: Tuple[int, int, int, int] = (0, 0, 0, 0)
    reason: str = ""


@dataclass
class DuplicateGroup:
    """Group of duplicate chapters with the same number."""
    
    number: int
    kept: Chapter
    discarded: List[Chapter] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    discarded_chars: int = 0


@dataclass
class DuplicateReport:
    """Report of all duplicate resolution actions."""
    
    groups: List[DuplicateGroup] = field(default_factory=list)
    kept: List[Chapter] = field(default_factory=list)
    discarded: List[Chapter] = field(default_factory=list)
    events: List[Dict[str, object]] = field(default_factory=list)

    @property
    def discarded_count(self) -> int:
        return len(self.discarded)

    @property
    def discarded_chars(self) -> int:
        return sum(group.discarded_chars for group in self.groups)

    def summary(self) -> str:
        if not self.groups:
            return "Không phát hiện chương trùng."
        return (
            f"{len(self.groups)} số chương bị trùng, đã loại {self.discarded_count} bản sao "
            f"({self.discarded_chars} ký tự), giữ {len(self.kept)} chương."
        )


def language_of(chapter: Chapter) -> str:
    """Classify a chapter as Vietnamese, Chinese, mixed, or English.
    
    Uses character analysis of both title and body content.
    Returns "vi", "zh", "en", "mixed", or "unknown".
    """
    if chapter.language in ("vi", "en", "zh"):
        return chapter.language
    
    # Analyze both title and body
    body = f"{chapter.title}\n{chapter.text}"
    han = len(HAN_RE.findall(body))
    latin = len(LATIN_RE.findall(body))
    
    # Chinese if mostly Han characters
    if han and han > latin * 0.5:
        return "zh"
    
    # Mixed if has both
    if han and latin:
        return "mixed"
    
    # Vietnamese/English if has Latin
    if latin:
        return "vi"
    
    return "unknown"


def _variant_score(
    chapter: Chapter, 
    index: int, 
    prefer_vietnamese: bool = True
) -> Tuple[int, int, int, int]:
    """Calculate priority score for a chapter variant.
    
    Returns (language_rank, has_title, chars, -index) tuple.
    Higher scores win. Index is negated so earlier occurrence wins on tie.
    
    Priority 1: Language
        - Vietnamese: rank 3
        - Mixed (Vietnamese with some Chinese): rank 2
        - English: rank 1
        - Chinese: rank -1 (when prefer_vietnamese=True), else rank 1
        - Unknown: rank 0
    
    Priority 2: Has title (1 if present, 0 if not)
    Priority 3: Character count (longer wins)
    Priority 4: Original position (earlier wins, achieved by negating index)
    """
    language = language_of(chapter)
    
    # Language rank
    if language == "vi":
        language_rank = 3
    elif language == "mixed":
        language_rank = 2
    elif language == "en":
        language_rank = 1
    elif language == "zh":
        language_rank = -1 if prefer_vietnamese else 1
    else:
        language_rank = 0
    
    # Title presence
    has_title = 1 if (chapter.title or "").strip() else 0
    
    # Character count
    chars = len(chapter.text or "")
    
    # Original position (negated so earlier wins)
    return (language_rank, has_title, chars, -index)


def _format_reason(winner: DuplicateVariant, loser: DuplicateVariant) -> str:
    """Generate human-readable reason for why a variant was discarded."""
    
    # Priority 1: Vietnamese over Chinese
    if loser.language == "zh" and winner.language in ("vi", "mixed", "en"):
        return "Bản tiếng Việt được ưu tiên hơn bản tiếng Trung."
    
    # Priority 2: Has title over no title
    if winner.has_title and not loser.has_title:
        return "Bản giữ lại có tiêu đề, bản bị loại không có tiêu đề."
    
    # Priority 3: Longer content wins
    if loser.chars < winner.chars:
        return f"Bản ngắn hơn ({loser.chars} < {winner.chars} ký tự) nên bị loại."
    
    if loser.chars == winner.chars:
        return "Trùng hoàn toàn; giữ bản xuất hiện trước."
    
    # Default reason
    return "Điểm ưu tiên thấp hơn theo thứ tự ngôn ngữ/tiêu đề/độ dài/vị trí."


def resolve_duplicates(
    chapters: Sequence[Chapter],
    *,
    prefer_vietnamese: bool = True,
) -> DuplicateReport:
    """Group chapters by number and keep the best copy of each.
    
    Applies the exact priority rules specified:
    1. Vietnamese over Chinese
    2. Has title over no title
    3. Longer content over shorter
    4. Earlier position over later
    
    Only removes redundant chapter headers, never the body content.
    """
    report = DuplicateReport()
    
    # Group chapters by number
    buckets: Dict[int, List[Tuple[int, Chapter]]] = {}
    for index, chapter in enumerate(chapters):
        buckets.setdefault(chapter.number, []).append((index, chapter))
    
    # Preserve original chapter order
    ordered_numbers: List[int] = []
    for chapter in chapters:
        if chapter.number not in ordered_numbers:
            ordered_numbers.append(chapter.number)
    
    # Process each chapter number
    for number in ordered_numbers:
        entries = buckets[number]
        
        # No duplicates - keep as is
        if len(entries) == 1:
            report.kept.append(entries[0][1])
            continue
        
        # Score all variants
        scored: List[DuplicateVariant] = []
        for index, chapter in entries:
            score = _variant_score(chapter, index, prefer_vietnamese)
            language = language_of(chapter)
            
            scored.append(
                DuplicateVariant(
                    chapter=chapter,
                    index=index,
                    language=language,
                    has_title=bool((chapter.title or "").strip()),
                    chars=len(chapter.text or ""),
                    score=score,
                )
            )
        
        # Sort by score (highest first)
        scored.sort(key=lambda variant: variant.score, reverse=True)
        
        # Winner is the highest scored variant
        winner = scored[0]
        group = DuplicateGroup(number=number, kept=winner.chapter)
        
        # Process discarded variants
        for variant in scored[1:]:
            reason = _format_reason(winner, variant)
            
            group.discarded.append(variant.chapter)
            group.reasons.append(reason)
            group.discarded_chars += len(variant.chapter.text or "")
            
            report.events.append(
                {
                    "number": number,
                    "kept_chars": winner.chars,
                    "kept_language": winner.language,
                    "kept_has_title": winner.has_title,
                    "kept_source_line": winner.chapter.source_line,
                    "discarded_chars": variant.chars,
                    "discarded_language": variant.language,
                    "discarded_has_title": variant.has_title,
                    "discarded_source_line": variant.chapter.source_line,
                    "reason": reason,
                    "discarded_snippet": (variant.chapter.text or "")[:160],
                }
            )
        
        # Mark duplicates on the winner
        winner.chapter.duplicates_removed = len(group.discarded)
        
        # Add to report
        report.kept.append(winner.chapter)
        report.discarded.extend(group.discarded)
        report.groups.append(group)
    
    return report

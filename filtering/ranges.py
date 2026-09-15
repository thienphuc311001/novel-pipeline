"""Chapter range parsing and chunk filtering.

Range syntax: ``1-20``, ``21-40,45,50-60`` (comma separated, inclusive ends).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from pipeline.document import Chapter, Chunk

RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
SINGLE_RE = re.compile(r"^\s*(\d+)\s*$")


@dataclass
class ChapterRange:
    start: int
    end: int

    @property
    def count(self) -> int:
        return max(0, self.end - self.start + 1)

    def __contains__(self, number: int) -> bool:
        return self.start <= number <= self.end

    def to_string(self) -> str:
        return f"{self.start}-{self.end}" if self.start != self.end else str(self.start)


def parse_ranges(text: str) -> List[ChapterRange]:
    """Parse comma-separated ranges: ``1-20, 25, 30-40``."""
    ranges: List[ChapterRange] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        match = RANGE_RE.match(part)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            if start <= end:
                ranges.append(ChapterRange(start, end))
            continue
        match = SINGLE_RE.match(part)
        if match:
            number = int(match.group(1))
            ranges.append(ChapterRange(number, number))
    return ranges


def validate_range_string(text: str) -> Optional[str]:
    """Return an error message when *text* cannot be parsed as ranges."""
    if not text or not text.strip():
        return "Chuỗi phạm vi đang trống."
    try:
        ranges = parse_ranges(text)
    except (ValueError, TypeError) as error:
        return f"Lỗi phân tích: {error}"
    if not ranges:
        return "Không tìm thấy phạm vi hợp lệ nào."
    return None


def expand_ranges(ranges: Sequence[ChapterRange]) -> Set[int]:
    """Expand range objects into a flat set of chapter numbers."""
    numbers: Set[int] = set()
    for chapter_range in ranges:
        numbers.update(range(chapter_range.start, chapter_range.end + 1))
    return numbers


def generate_blocks(
    start: int, end: int, block_size: int
) -> List[ChapterRange]:
    """Generate consecutive blocks of *block_size* chapters."""
    if start > end or block_size < 1:
        return []
    blocks: List[ChapterRange] = []
    current = start
    while current <= end:
        block_end = min(current + block_size - 1, end)
        blocks.append(ChapterRange(current, block_end))
        current = block_end + 1
    return blocks


def filter_chapters_by_ranges(
    chapters: Sequence[Chapter], ranges: Sequence[ChapterRange]
) -> List[Chapter]:
    """Keep only chapters whose number falls inside one of *ranges*."""
    if not ranges:
        return list(chapters)
    numbers = expand_ranges(ranges)
    return [chapter for chapter in chapters if chapter.number in numbers]


def filter_chunks_by_ranges(
    chunks: Sequence[Chunk], ranges: Sequence[ChapterRange]
) -> List[Chunk]:
    """Keep only chunks whose chapter number falls inside one of *ranges*."""
    if not ranges:
        return list(chunks)
    numbers = expand_ranges(ranges)
    return [chunk for chunk in chunks if chunk.chapter in numbers]


"""Chunk statistics: per chapter counts, totals and size distribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from pipeline.document import Chapter, Chunk


@dataclass
class ChapterChunkStat:
    chapter: int
    title: str = ""
    chunks: int = 0
    characters: int = 0
    min_chars: int = 0
    max_chars: int = 0
    hard_splits: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "chapter": self.chapter,
            "title": self.title,
            "chunks": self.chunks,
            "characters": self.characters,
            "min_chars": self.min_chars,
            "max_chars": self.max_chars,
            "hard_splits": self.hard_splits,
        }


@dataclass
class ChunkStatistics:
    chapter_count: int = 0
    chunk_count: int = 0
    total_characters: int = 0
    average_chars: int = 0
    min_chars: int = 0
    max_chars: int = 0
    hard_splits: int = 0
    per_chapter: List[ChapterChunkStat] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "chapter_count": self.chapter_count,
            "chunk_count": self.chunk_count,
            "total_characters": self.total_characters,
            "average_chars": self.average_chars,
            "min_chars": self.min_chars,
            "max_chars": self.max_chars,
            "hard_splits": self.hard_splits,
            "per_chapter": [item.to_dict() for item in self.per_chapter],
        }

    def summary(self) -> str:
        if not self.chunk_count:
            return "Chưa có đoạn nào."
        return (
            f"{self.chunk_count} đoạn từ {self.chapter_count} chương · "
            f"{self.total_characters} ký tự · trung bình {self.average_chars} "
            f"(min {self.min_chars}, max {self.max_chars})"
            + (f" · {self.hard_splits} đoạn cắt cứng" if self.hard_splits else "")
        )


def chunk_statistics(
    chunks: Sequence[Chunk], chapters: Optional[Sequence[Chapter]] = None
) -> ChunkStatistics:
    stats = ChunkStatistics(chunk_count=len(chunks))
    if chapters:
        stats.chapter_count = len(chapters)
    sizes = [chunk.char_count for chunk in chunks]
    if sizes:
        stats.total_characters = sum(sizes)
        stats.average_chars = int(sum(sizes) / len(sizes))
        stats.min_chars = min(sizes)
        stats.max_chars = max(sizes)
    stats.hard_splits = sum(1 for chunk in chunks if chunk.hard_split)

    buckets: Dict[int, ChapterChunkStat] = {}
    titles = {chapter.number: chapter.display_title() for chapter in chapters or []}
    for chunk in chunks:
        bucket = buckets.get(chunk.chapter)
        if bucket is None:
            bucket = ChapterChunkStat(chapter=chunk.chapter, title=titles.get(chunk.chapter, chunk.chapter_title))
            buckets[chunk.chapter] = bucket
        bucket.chunks += 1
        bucket.characters += chunk.char_count
        if bucket.min_chars == 0 or chunk.char_count < bucket.min_chars:
            bucket.min_chars = chunk.char_count
        bucket.max_chars = max(bucket.max_chars, chunk.char_count)
        if chunk.hard_split:
            bucket.hard_splits += 1
    stats.per_chapter = [buckets[number] for number in sorted(buckets)]
    if not stats.chapter_count:
        stats.chapter_count = len(buckets)
    return stats


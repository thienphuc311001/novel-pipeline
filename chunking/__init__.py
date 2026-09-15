"""Chapter-safe chunk splitting, chunk metadata and statistics."""

from .splitter import (
    BreakStrategy,
    ChunkPlan,
    split_chapter,
    split_chapters,
    split_text_by_limit,
)
from .stats import ChunkStatistics, chunk_statistics

__all__ = [
    "BreakStrategy",
    "ChunkPlan",
    "split_chapter",
    "split_chapters",
    "split_text_by_limit",
    "ChunkStatistics",
    "chunk_statistics",
]

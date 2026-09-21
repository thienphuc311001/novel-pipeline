"""Chapter-safe chunk splitting, chunk metadata and statistics."""

from .splitter import (
    BreakStrategy,
    ChunkPlan,
    LayoutChunkError,
    MAX_CHUNK,
    TTS_CHUNK_SOFT_TARGET,
    chunk_layout_metadata,
    default_layout_budget,
    layout_statistics,
    split_chapter,
    split_chapters,
    split_text_by_limit,
    verify_chunk_integrity,
)
from .stats import ChunkStatistics, chunk_statistics

__all__ = [
    "BreakStrategy",
    "ChunkPlan",
    "LayoutChunkError",
    "MAX_CHUNK",
    "TTS_CHUNK_SOFT_TARGET",
    "chunk_layout_metadata",
    "default_layout_budget",
    "layout_statistics",
    "split_chapter",
    "split_chapters",
    "split_text_by_limit",
    "verify_chunk_integrity",
    "ChunkStatistics",
    "chunk_statistics",
]

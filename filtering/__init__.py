"""Chapter range filtering, selection helpers and repair actions."""

from .ranges import (
    ChapterRange,
    parse_ranges,
    expand_ranges,
    generate_blocks,
    filter_chapters_by_ranges,
    filter_chunks_by_ranges,
    validate_range_string,
)
from .repair import renumber_chunks, repair_chunk_headers

__all__ = [
    "ChapterRange",
    "parse_ranges",
    "expand_ranges",
    "generate_blocks",
    "filter_chapters_by_ranges",
    "filter_chunks_by_ranges",
    "validate_range_string",
    "renumber_chunks",
    "repair_chunk_headers",
]

"""Explicit repair actions: sequential renumbering and header rewriting."""

from __future__ import annotations

from typing import Sequence

from pipeline.document import Chunk


def renumber_chunks(chunks: Sequence[Chunk], start: int = 1) -> int:
    """Renumber chunks sequentially within each chapter (user triggered)."""
    changed = 0
    buckets: dict[int, list[Chunk]] = {}
    for chunk in chunks:
        buckets.setdefault(chunk.chapter, []).append(chunk)
    for chapter_number in sorted(buckets):
        for index, chunk in enumerate(buckets[chapter_number], start=1):
            if chunk.index != index:
                chunk.index = index
                changed += 1
    order = 0
    for chunk in chunks:
        order += 1
        if chunk.order != order:
            chunk.order = order
            changed += 1
    return changed


def repair_chunk_headers(chunks: Sequence[Chunk]) -> int:
    """Recompute ``chapter_title`` and ``parts`` for every chunk (user triggered)."""
    changed = 0
    buckets: dict[int, list[Chunk]] = {}
    for chunk in chunks:
        buckets.setdefault(chunk.chapter, []).append(chunk)
    for chapter_number, chapter_chunks in buckets.items():
        total = len(chapter_chunks)
        for chunk in chapter_chunks:
            if chunk.parts != total:
                chunk.parts = total
                changed += 1
    return changed


"""ZIP batch export with manifest."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from filtering.ranges import ChapterRange, filter_chunks_by_ranges
from pipeline.document import Chunk


def export_zip_batch(
    chunks: Sequence[Chunk],
    ranges: Sequence[ChapterRange],
    path: Path,
    *,
    format: str = "json",
    folder_per_range: bool = False,
    include_manifest: bool = True,
) -> Path:
    """Export multiple chapter ranges as a single ZIP archive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    manifest: List[Dict[str, object]] = []
    
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, chapter_range in enumerate(ranges, start=1):
            filtered = filter_chunks_by_ranges(chunks, [chapter_range])
            if not filtered:
                continue
            
            range_str = chapter_range.to_string()
            folder = f"range_{index:03d}" if folder_per_range else ""
            
            if format == "json":
                filename = f"{range_str}.json" if not folder else f"{folder}/{range_str}.json"
                content = json.dumps(
                    {
                        "range": range_str,
                        "chunks": [chunk.to_dict() for chunk in filtered],
                        "chunk_count": len(filtered),
                        "chapter_count": len({chunk.chapter for chunk in filtered}),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:  # txt
                filename = f"{range_str}.txt" if not folder else f"{folder}/{range_str}.txt"
                lines: List[str] = []
                current_chapter: Optional[int] = None
                for chunk in filtered:
                    if chunk.chapter != current_chapter:
                        if current_chapter is not None:
                            lines.append("\n\n")
                        lines.append(f"=== {chunk.chapter_title or f'Chương {chunk.chapter}'} ===\n\n")
                        current_chapter = chunk.chapter
                    lines.append(chunk.text)
                    lines.append("\n\n")
                content = "".join(lines).rstrip() + "\n"
            
            archive.writestr(filename, content.encode("utf-8"))
            
            manifest.append({
                "index": index,
                "range": range_str,
                "filename": filename,
                "chunks": len(filtered),
                "chapters": len({chunk.chapter for chunk in filtered}),
                "characters": sum(chunk.char_count for chunk in filtered),
            })
        
        if include_manifest:
            manifest_content = json.dumps(
                {"ranges": manifest, "total_ranges": len(ranges)},
                ensure_ascii=False,
                indent=2,
            )
            archive.writestr("manifest.json", manifest_content.encode("utf-8"))
    
    return path


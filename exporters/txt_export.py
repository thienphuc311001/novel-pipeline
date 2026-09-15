"""Plain text export with configurable headers.

Provides clean TXT export that contains ONLY:
- Normalized chapter headers (Chương X or Chương X: Title)
- Chapter body content

No metadata, diagnostics, line numbers, or processing markers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from pipeline.document import Chapter, Chunk


def export_txt(
    chunks: Sequence[Chunk],
    path: Path,
    *,
    include_headers: bool = True,
    chapter_separator: str = "\n\n",
    chunk_separator: str = "\n\n",
) -> Path:
    """Export chunks as plain text with optional headers."""
    parts: list[str] = []
    current_chapter: Optional[int] = None
    
    for chunk in chunks:
        if include_headers and chunk.chapter != current_chapter:
            if current_chapter is not None:
                parts.append(chapter_separator)
            parts.append(f"=== {chunk.chapter_title or f'Chương {chunk.chapter}'} ===\n\n")
            current_chapter = chunk.chapter
        
        parts.append(chunk.text)
        parts.append(chunk_separator)
    
    output = "".join(parts).rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    return path


def export_txt_merged(
    chapters: Sequence[Chapter],
    path: Path,
    *,
    include_headers: bool = True,
    chapter_separator: str = "\n\n\n",
) -> Path:
    """Export chapters as merged plain text.
    
    Standard export for chapters with headers and bodies.
    """
    parts: list[str] = []
    
    for chapter in chapters:
        if include_headers and chapter.header_line:
            parts.append(chapter.header_line)
            parts.append("\n\n")
        parts.append(chapter.text or "")
        parts.append(chapter_separator)
    
    output = "".join(parts).rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    return path


def export_clean_txt(
    chapters: Sequence[Chapter],
    path: Path,
    *,
    chapter_separator: str = "\n\n\n",
) -> Path:
    """Export clean TXT with ONLY normalized headers and content.
    
    This is the canonical "Clean TXT" export that produces output containing:
    - Normalized chapter headers (Chương X or Chương X: Title)
    - Complete chapter body content
    
    Excluded from output:
    - Source line numbers
    - Diagnostics
    - Metadata
    - Processing markers
    - Duplicate information
    - JSON wrappers
    - Internal IDs
    
    Example output:
        Chương 327: Lưu dân không đáng sợ
        
        Đám lao dịch bận rộn trên đường phố...
        
        
        Chương 328: "Tiểu tử hiểu rồi……"
        
        Khấu Quý chắp tay nói với Lý Địch.
    
    The output is reconstructed from the normalized chapter structure,
    not by filtering raw lines, to ensure correctness.
    """
    parts: list[str] = []
    
    for chapter in chapters:
        # Always include the normalized header
        if chapter.header_line:
            parts.append(chapter.header_line)
            parts.append("\n\n")
        
        # Add the complete body content
        body = (chapter.text or "").strip()
        if body:
            parts.append(body)
            parts.append(chapter_separator)
    
    # Final output: join all parts and ensure single trailing newline
    output = "".join(parts).rstrip() + "\n"
    
    # Write to file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    
    return path


def export_chapter_txt(
    chapter: Chapter,
    path: Path,
) -> Path:
    """Export a single chapter as plain text.
    
    Used for per-chapter export or preview.
    """
    parts: list[str] = []
    
    if chapter.header_line:
        parts.append(chapter.header_line)
        parts.append("\n\n")
    
    body = (chapter.text or "").strip()
    if body:
        parts.append(body)
        parts.append("\n")
    
    output = "".join(parts)
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    
    return path

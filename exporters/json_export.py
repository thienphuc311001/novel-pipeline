"""JSON export with metadata and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.document import Chapter, Chunk, Diagnostic, PipelineDocument


def export_json(
    chunks: Sequence[Chunk],
    path: Path,
    *,
    chapters: Optional[Sequence[Chapter]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Export chunks as simple JSON (chunk list only)."""
    output = {
        "chunks": [chunk.to_dict() for chunk in chunks],
        "chunk_count": len(chunks),
        "chapter_count": len({chunk.chapter for chunk in chunks}),
        "total_characters": sum(chunk.char_count for chunk in chunks),
    }
    if metadata:
        output["metadata"] = metadata
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_detailed_json(
    document: PipelineDocument,
    path: Path,
    *,
    include_diagnostics: bool = True,
    include_stage_status: bool = True,
) -> Path:
    """Export complete pipeline state with diagnostics and stage status."""
    output: Dict[str, Any] = {
        "summary": document.summary(),
        "chapters": [chapter.to_dict() for chapter in document.chapters],
        "chunks": [chunk.to_dict() for chunk in document.chunks],
    }
    
    if include_stage_status:
        output["stage_status"] = {
            key: status.to_dict() for key, status in document.stage_status.items()
        }
    
    if include_diagnostics:
        output["diagnostics"] = [diag.to_dict() for diag in document.diagnostics]
        output["diagnostic_summary"] = {
            "total": len(document.diagnostics),
            "errors": document.count_severity("error"),
            "warnings": document.count_severity("warning"),
            "info": document.count_severity("info"),
        }
    
    if document.source_files:
        output["sources"] = [source.to_dict() for source in document.source_files]
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

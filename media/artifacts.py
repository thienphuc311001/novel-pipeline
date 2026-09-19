"""Atomic grouping-stage TXT/JSON artifact creation and validation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pipeline.document import PipelineDocument, PipelineStateError, Step3ArtifactBundle


INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE_RE = re.compile(r"\s+")
UNDERSCORES_RE = re.compile(r"_+")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slugify_job_name(title: str, chapter: str) -> str:
    """Return a readable Unicode-safe folder/file stem for a single job."""
    raw = f"{(title or '').strip()}_{(chapter or '').strip()}"
    value = INVALID_FILENAME_RE.sub("_", raw)
    value = WHITESPACE_RE.sub("_", value)
    value = UNDERSCORES_RE.sub("_", value).strip("._ ")
    return (value or "novel_chapter")[:120].rstrip("._ ") or "novel_chapter"


def artifact_paths(output_root: Path, title: str, chapter: str) -> Dict[str, Path]:
    slug = slugify_job_name(title, chapter)
    directory = output_root.expanduser() / slug
    return {
        "slug": Path(slug),
        "directory": directory,
        "txt": directory / f"{slug}.txt",
        "json": directory / f"{slug}_chunks.json",
        "audio_dir": directory / f"{slug}_audio_chunks",
        "manifest": directory / f"{slug}_audio_chunks" / "manifest.json",
        "audiobook": directory / f"{slug}_audiobook.mp3",
        "video": directory / f"{slug}.mp4",
    }


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, (text or "").encode("utf-8"))


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8"),
    )


def publish_job_file_names(bundle: Step3ArtifactBundle, media, cancel_event) -> None:
    """Expose the requested final job layout while keeping existing filenames.

    Same-folder hard links avoid copying large audiobooks. Filesystems without
    hard links use a cancellable copy. Each alias replaces atomically only after
    its complete contents are available; source artifacts remain authoritative.
    """
    from media.youtube import UploadCancelled

    job = Path(bundle.output_dir).resolve()
    sources = {
        "final.txt": Path(bundle.txt_path), "final.json": Path(bundle.json_path),
        "thumbnail.jpg": Path(media.thumbnail_path), "audiobook.mp3": Path(media.audiobook_path),
    }
    for name, source in sources.items():
        if cancel_event.is_set():
            raise UploadCancelled("Preparation cancelled. Existing job files were preserved.")
        if source.resolve().parent != job or not source.is_file() or source.stat().st_size <= 0:
            raise PipelineStateError("Final job files must come from the current validated pipeline outputs.")
        destination = job / name
        if destination.exists() and os.path.samefile(source, destination):
            continue
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=job)
        os.close(descriptor)
        try:
            os.unlink(temporary)
            try:
                os.link(source, temporary)
            except OSError:
                with source.open("rb") as reader, open(temporary, "wb") as writer:
                    for block in iter(lambda: reader.read(1024 * 1024), b""):
                        if cancel_event.is_set():
                            raise UploadCancelled("Preparation cancelled. Existing job files were preserved.")
                        writer.write(block)
                    writer.flush()
                    os.fsync(writer.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _canonical_cleaned_text(document: PipelineDocument) -> str:
    text = document.cleaned_text
    if text is None:
        raise PipelineStateError("The grouping stage has no cleaned text to materialize.")
    return text.rstrip("\n") + "\n" if text else ""


def write_step3_artifacts(
    document: PipelineDocument,
    output_root: Path,
    *,
    title: str,
    chapter: str,
    chunk_limit: int,
    tts_preparation: Optional[Dict[str, Any]] = None,
) -> Step3ArtifactBundle:
    """Write the exact current grouping state as a paired UTF-8 job bundle."""
    title = (title or "").strip()
    chapter = (chapter or "").strip()
    if not title or not chapter:
        raise ValueError("Title and chapter are required before creating group files.")
    if not document.chunks:
        raise PipelineStateError("No chunks are available to export.")

    paths = artifact_paths(output_root, title, chapter)
    text = _canonical_cleaned_text(document)
    text_hash = sha256_text(text)
    chunks_hash = document.chunk_fingerprint()
    chunks = []
    for chunk in sorted(document.chunks, key=lambda item: item.order):
        item = chunk.to_dict()
        item["text_sha256"] = sha256_text(chunk.text)
        chunks.append(item)

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "title": title,
        "chapter": chapter,
        "source_revision": document.normalized_revision,
        "resolved_output_dir": str(Path(output_root).expanduser().resolve()),
        "cleaned_text_sha256": text_hash,
        "chunks_sha256": chunks_hash,
        "chunk_settings": {
            "max_chars": int(chunk_limit),
            "headers_spoken": True,
        },
        "chunk_count": len(chunks),
        "chapters": [entry.to_dict() for entry in document.chapters],
        "chunks": chunks,
    }
    if tts_preparation is not None:
        payload["tts_preparation"] = tts_preparation
    atomic_write_text(paths["txt"], text)
    atomic_write_json(paths["json"], payload)
    return Step3ArtifactBundle(
        title=title,
        chapter=chapter,
        slug=str(paths["slug"]),
        output_dir=str(paths["directory"]),
        txt_path=str(paths["txt"]),
        json_path=str(paths["json"]),
        source_revision=document.normalized_revision,
        text_sha256=text_hash,
        chunks_sha256=chunks_hash,
        txt_sha256=sha256_file(paths["txt"]),
        json_sha256=sha256_file(paths["json"]),
        chunk_count=len(chunks),
        config=payload["chunk_settings"],
    )


def validate_step3_bundle(bundle: Step3ArtifactBundle) -> None:
    """Raise a useful error when a supposedly authoritative file changed."""
    txt_path = Path(bundle.txt_path)
    json_path = Path(bundle.json_path)
    for path in (txt_path, json_path):
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"missing or empty file: {path.name}")
    if sha256_file(txt_path) != bundle.txt_sha256:
        raise ValueError(f"{txt_path.name} was changed outside the pipeline")
    if sha256_file(json_path) != bundle.json_sha256:
        raise ValueError(f"{json_path.name} was changed outside the pipeline")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid chunk JSON: {error}") from error
    if data.get("cleaned_text_sha256") != bundle.text_sha256:
        raise ValueError("chunk JSON belongs to a different text output")
    if data.get("chunks_sha256") != bundle.chunks_sha256:
        raise ValueError("chunk JSON belongs to different chunks")
    if int(data.get("chunk_count", -1)) != bundle.chunk_count:
        raise ValueError("chunk JSON count does not match the pipeline bundle")


def load_bundle_json(bundle: Step3ArtifactBundle) -> Dict[str, Any]:
    validate_step3_bundle(bundle)
    return json.loads(Path(bundle.json_path).read_text(encoding="utf-8"))

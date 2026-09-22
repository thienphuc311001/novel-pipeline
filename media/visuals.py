"""The two required Step 4 page pictures: the 1:1 cover and the QR image.

The video step never edits these files.  Each chosen picture is copied byte for
byte into ``<job>/visuals/`` and recorded in ``visuals.json`` together with its
sha256, so the page cache, the video source fingerprint and the Step 5 upload
gate all agree on which pictures a rendered video was made from.

A missing, empty, unreadable or changed picture is reported instead of being
silently skipped: Step 4 refuses to render without both inputs.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from media.artifacts import atomic_write_json, sha256_file
from media.video import VideoValidationError

VISUALS_DIRNAME = "visuals"
VISUALS_RECORD = "visuals.json"
VISUAL_ROLES = ("cover", "qr")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
SCHEMA_VERSION = 1
ROLE_LABELS = {"cover": "the 1:1 (left) image", "qr": "the QR (right) image"}


def _validate_source(role, value):
    """Return ``(path, suffix, size)`` for one chosen picture, or fail loudly."""
    path = Path(str(value or "")).expanduser()
    if not path.is_file():
        raise VideoValidationError(f"Missing {ROLE_LABELS[role]} for the video pages: {path}")
    if path.stat().st_size <= 0:
        raise VideoValidationError(f"Empty {ROLE_LABELS[role]}: {path}")
    suffix = path.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise VideoValidationError(
            f"Unsupported {ROLE_LABELS[role]} format ({path.name}); use {'/'.join(IMAGE_SUFFIXES)}.")
    try:
        with Image.open(path) as image:
            size = (int(image.size[0]), int(image.size[1]))
    except (OSError, ValueError) as error:
        raise VideoValidationError(f"Cannot read {ROLE_LABELS[role]} {path}: {error}") from error
    if size[0] < 1 or size[1] < 1:
        raise VideoValidationError(f"Invalid {ROLE_LABELS[role]} size {size}: {path}")
    return path, suffix, size


def record_visuals(job_dir, cover_path, qr_path):
    """Copy both required pictures into ``<job>/visuals/`` and record their exact bytes.

    The copy is byte-identical (never re-encoded), so the recorded sha256 is both
    the page cache key and the proof that a rendered video used these pictures.
    """
    job_dir = Path(job_dir)
    folder = job_dir / VISUALS_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": SCHEMA_VERSION, "job_dir": str(job_dir.resolve())}
    for role, value in zip(VISUAL_ROLES, (cover_path, qr_path)):
        source, suffix, size = _validate_source(role, value)
        target = folder / f"{role}{suffix}"
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        # Drop an earlier copy of this slot that used another extension, so the
        # record and the folder can never disagree about which file is current.
        for stale in folder.glob(f"{role}.*"):
            if stale != target and stale.suffix.lower() in IMAGE_SUFFIXES:
                stale.unlink(missing_ok=True)
        if not target.is_file() or target.stat().st_size <= 0:
            raise VideoValidationError(f"Could not copy {ROLE_LABELS[role]} into the job folder: {target}")
        record[role] = {"file": f"{VISUALS_DIRNAME}/{target.name}", "source": str(source.resolve()),
                        "sha256": sha256_file(target), "size": int(target.stat().st_size),
                        "width": size[0], "height": size[1]}

    atomic_write_json(job_dir / VISUALS_RECORD, record)
    return record


def _read_record(job_dir):
    """Raw ``visuals.json`` when it is a current record, otherwise ``{}``."""
    try:
        data = json.loads((Path(job_dir) / VISUALS_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return {}
    return data


def load_visuals(job_dir):
    """Return both pictures with verified bytes, or explain which one is unusable."""
    job_dir = Path(job_dir)
    record = _read_record(job_dir)
    images = {}
    for role in VISUAL_ROLES:
        row = record.get(role)
        if not isinstance(row, dict):
            raise VideoValidationError(
                f"Step 4 needs both page images ({ROLE_LABELS['cover']} and {ROLE_LABELS['qr']}): "
                f"{ROLE_LABELS[role]} has not been added for this job yet. "
                "Use Add image in the Create Video step and try again.")
        path = (job_dir / str(row.get("file", ""))).resolve()
        try:
            current = sha256_file(path) if path.is_file() else ""
        except OSError:
            current = ""
        if not current or current != row.get("sha256"):
            raise VideoValidationError(
                f"{ROLE_LABELS[role]} changed or was deleted after it was added: {path}. "
                "Add it again in the Create Video step and try again.")
        images[role] = {"path": str(path), "source": str(row.get("source", "")), "sha256": current,
                        "width": int(row.get("width") or 0), "height": int(row.get("height") or 0)}
    return images


def available_images(job_dir):
    """Lenient view for the UI and previews: role -> copied file that still exists."""
    job_dir = Path(job_dir)
    record = _read_record(job_dir)
    images = {}
    for role in VISUAL_ROLES:
        row = record.get(role)
        path = (job_dir / str(row.get("file", ""))) if isinstance(row, dict) else None
        images[role] = str(path) if path is not None and path.is_file() else ""
    return images


def recorded_sources(job_dir):
    """Original picker paths recorded in the job, when those files still exist."""
    job_dir = Path(job_dir)
    record = _read_record(job_dir)
    sources = {}
    for role in VISUAL_ROLES:
        row = record.get(role)
        source = str((row or {}).get("source", "")) if isinstance(row, dict) else ""
        sources[role] = source if source and Path(source).is_file() else ""
    return sources


def visual_input_paths(job_dir):
    """Every recorded picture file that still exists (video input guard)."""
    return [Path(value) for value in available_images(job_dir).values() if value]


def image_summary(path):
    """``cover.png · 1024×1024`` for the Step 4 labels; never raises."""
    path = Path(str(path or ""))
    if not path.is_file():
        return "Not selected"
    try:
        with Image.open(path) as image:
            return f"{path.name} · {image.size[0]}×{image.size[1]}"
    except (OSError, ValueError):
        return str(path)


def prune_visuals(job_dir):
    """Remove every staged visual file and its record for one job folder."""
    job_dir = Path(job_dir)
    for path in available_images(job_dir).values():
        try:
            if path:
                Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        (job_dir / VISUALS_RECORD).unlink(missing_ok=True)
    except OSError:
        pass


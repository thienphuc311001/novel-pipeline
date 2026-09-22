"""Fixed Vietnamese channel intro reused at the start of every audiobook/video.

Spoken text (verbatim, never cleaned)::

    Chào mừng bạn đến với Ghiền Truyện Chữ. Đừng quên nhấn thích và đăng ký
    kênh để ủng hộ mình nhé.

Design:
- TTS audio is generated once per (text, voice) and cached globally under the
  user config dir, then copied byte-identically into each job's
  ``audio_chunks/intro.mp3`` before the final merge.
- Video shows the job's ``thumbnail.jpg`` fullscreen (crop-fit to 1920x1080,
  matching ``render_page`` background behavior, no black padding) for the whole
  intro duration, then normal neon-theater story pages.
- Both stages are fail-closed and backward compatible: manifests without an
  ``intro`` entry keep the old behavior (no intro frame).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from config.settings import DEFAULT_CHANNEL_INTRO_TEXT, config_dir

# Re-export so callers have one import for the fixed text.
CHANNEL_INTRO_TEXT = DEFAULT_CHANNEL_INTRO_TEXT

INTRO_JOB_FILENAME = "intro.mp3"
INTRO_FRAME_PREFIX = "page_00000_intro_"
INTRO_VIDEO_WIDTH = 1920
INTRO_VIDEO_HEIGHT = 1080


def channel_intro_text(settings: Any) -> str:
    raw = str(getattr(settings, "channel_intro_text", "") or "").strip()
    return raw or DEFAULT_CHANNEL_INTRO_TEXT


def channel_intro_enabled(settings: Any) -> bool:
    return bool(getattr(settings, "channel_intro_enabled", True))


def channel_intro_voice(settings: Any) -> str:
    override = str(getattr(settings, "channel_intro_voice", "") or "").strip()
    if override:
        return override
    return str(getattr(settings, "tts_voice", "") or "").strip()


def intro_identity(text: str, voice: str) -> str:
    return hashlib.sha256(f"{text}\0{voice}".encode("utf-8")).hexdigest()


def intro_cache_path(voice: str, text: str, *, cache_dir: Optional[Path] = None) -> Path:
    root = Path(cache_dir).expanduser() if cache_dir else config_dir()
    return root / f"channel_intro_{intro_identity(text, voice)[:16]}.mp3"


def intro_sidecar_path(cache_path: Path) -> Path:
    return Path(cache_path).with_suffix(".json")


def _write_sidecar(cache_path: Path, *, text: str, voice: str) -> Dict[str, Any]:
    from media.artifacts import sha256_file, sha256_text

    payload = {
        "schema_version": 1,
        "text": text,
        "text_sha256": sha256_text(text),
        "voice": voice,
        "mp3_sha256": sha256_file(Path(cache_path)),
    }
    tmp = Path(str(cache_path) + ".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, intro_sidecar_path(cache_path))
    return payload


def _sidecar_valid(cache_path: Path, *, text: str, voice: str) -> bool:
    from media.artifacts import sha256_file, sha256_text

    path = Path(cache_path)
    sidecar = intro_sidecar_path(path)
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return (
            data.get("schema_version") == 1
            and data.get("text") == text
            and data.get("text_sha256") == sha256_text(text)
            and data.get("voice") == voice
            and data.get("mp3_sha256") == sha256_file(path)
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def bundled_intro_path(voice: str, text: str) -> Optional[Path]:
    """Committed fallback MP3 in ``assets/channel_intro/`` for the default voice/text."""
    if text.strip() != DEFAULT_CHANNEL_INTRO_TEXT:
        return None
    candidate = (
        Path(__file__).resolve().parents[1]
        / "assets" / "channel_intro" / f"channel_intro_{voice.strip()}.mp3"
    )
    try:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    except OSError:
        pass
    return None


def _restore_from_bundle(cache_path: Path, *, text: str, voice: str) -> Optional[Path]:
    """Seed the user cache from the committed asset (offline-safe)."""
    from media.artifacts import sha256_file

    bundled = bundled_intro_path(voice, text)
    if bundled is None:
        return None
    # The bundled sidecar (if present) must describe the same text/voice.
    sidecar = bundled.with_suffix(".json")
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        from media.artifacts import sha256_text

        if (
            data.get("text") != text
            or data.get("text_sha256") != sha256_text(text)
            or data.get("voice") != voice
            or data.get("mp3_sha256") != sha256_file(bundled)
        ):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        # Without a valid sidecar, still accept the MP3 bytes as fallback.
        pass
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bundled, cache_path)
    _write_sidecar(cache_path, text=text, voice=voice)
    return cache_path


def ensure_channel_intro_audio(
    text: str,
    voice: str,
    *,
    cache_dir: Optional[Path] = None,
    client_factory: Optional[Callable[[str, str], Any]] = None,
    timeout_seconds: int = 120,
) -> Path:
    """Return the global cached intro MP3, generating it once via Edge-TTS."""
    from media.artifacts import sha256_file

    text = (text or "").strip()
    voice = (voice or "").strip()
    if not text:
        raise ValueError("Channel intro text is empty.")
    if not voice:
        raise ValueError("Channel intro voice is empty.")
    cache_path = intro_cache_path(voice, text, cache_dir=cache_dir)
    if _sidecar_valid(cache_path, text=text, voice=voice):
        return cache_path
    # Offline-safe: a deleted cache is restored from the committed asset
    # without needing network (default text/voice only).
    if cache_dir is None and _restore_from_bundle(cache_path, text=text, voice=voice) is not None:
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if client_factory is None:
        from media.tts import _default_client_factory

        client_factory = _default_client_factory

    async def _save() -> None:
        partial = cache_path.with_suffix(cache_path.suffix + ".part")
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        client = client_factory(text, voice)
        await asyncio.wait_for(client.save(str(partial)), timeout=timeout_seconds)
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("Edge-TTS tạo tệp intro MP3 rỗng.")
        os.replace(partial, cache_path)

    asyncio.run(_save())
    if not cache_path.is_file() or cache_path.stat().st_size <= 0:
        raise RuntimeError("Edge-TTS tạo tệp intro MP3 rỗng.")
    # Validate it is at least readable; hash recorded in sidecar.
    sha256_file(cache_path)
    _write_sidecar(cache_path, text=text, voice=voice)
    return cache_path


def prepare_job_intro(
    audio_dir: Path,
    settings: Any,
    *,
    client_factory: Optional[Callable[[str, str], Any]] = None,
    cache_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Copy the global intro MP3 into ``audio_dir/intro.mp3``.

    Returns ``{"path":..., "text":..., "voice":...}`` or ``None`` when disabled.
    Never re-synthesizes when the job copy already matches the cache.
    """
    from media.artifacts import sha256_file, sha256_text

    if not channel_intro_enabled(settings):
        return None
    text = channel_intro_text(settings)
    voice = channel_intro_voice(settings)
    timeout = int(getattr(settings, "tts_timeout_seconds", 120) or 120)
    cache_path = ensure_channel_intro_audio(
        text, voice, cache_dir=cache_dir, client_factory=client_factory,
        timeout_seconds=max(1, timeout),
    )
    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    target = audio_dir / INTRO_JOB_FILENAME
    try:
        if (
            target.is_file()
            and target.stat().st_size > 0
            and sha256_file(target) == sha256_file(cache_path)
        ):
            pass
        else:
            descriptor, tmp_name = tempfile.mkstemp(prefix=".intro_", suffix=".mp3", dir=audio_dir)
            os.close(descriptor)
            try:
                # Same-folder hard link when possible; copy otherwise.
                try:
                    os.unlink(tmp_name)
                    os.link(cache_path, tmp_name)
                except OSError:
                    shutil.copyfile(cache_path, tmp_name)
                os.replace(tmp_name, target)
            finally:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
    except OSError as error:
        raise RuntimeError(f"Cannot stage channel intro MP3: {error}") from error
    return {
        "path": str(target.resolve()),
        "text": text,
        "text_sha256": sha256_text(text),
        "voice": voice,
        "mp3_sha256": sha256_file(target),
        "file": target.name,
    }


def read_manifest_intro(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Return the validated ``merge.intro`` record with an absolute mp3 path."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        merge = data.get("merge") or {}
        intro = merge.get("intro")
        if not isinstance(intro, dict):
            return None
        audio_dir = Path(manifest_path).resolve().parent
        name = str(intro.get("file") or INTRO_JOB_FILENAME)
        # Fail closed: intro must live inside its own chunk directory.
        candidate = (audio_dir / Path(name).name).resolve()
        if candidate.parent != audio_dir or not candidate.is_file() or candidate.stat().st_size <= 0:
            return None
        from media.artifacts import sha256_file

        if intro.get("mp3_sha256") != sha256_file(candidate):
            return None
        if not str(intro.get("text") or "").strip() or not str(intro.get("voice") or "").strip():
            return None
        return {**intro, "mp3_path": str(candidate)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def intro_frame_path(job_dir: Path, thumbnail_sha256: str) -> Path:
    safe = "".join(c for c in (thumbnail_sha256 or "") if c.isalnum())[:64] or "nothumb"
    return Path(job_dir) / "render_pages" / f"{INTRO_FRAME_PREFIX}{safe}.png"


def render_intro_frame(thumbnail_path: Path, output_path: Path) -> Dict[str, Any]:
    """Render the intro still: thumbnail crop-fit to full 1920x1080, no padding.

    Same fill behavior as ``media.video_pages.render_page`` background
    (``ImageOps.fit(..., LANCZOS)``) so no black bars appear; minimal edge
    cropping is allowed when the source is not exactly 16:9.
    """
    from PIL import Image, ImageOps

    thumbnail_path = Path(thumbnail_path)
    output_path = Path(output_path)
    with Image.open(thumbnail_path) as source:
        frame = ImageOps.fit(
            ImageOps.exif_transpose(source).convert("RGB"),
            (INTRO_VIDEO_WIDTH, INTRO_VIDEO_HEIGHT),
            method=Image.Resampling.LANCZOS,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(prefix=".intro_frame_", suffix=".png", dir=output_path.parent)
    os.close(descriptor)
    try:
        frame.save(tmp_name, format="PNG")
        os.replace(tmp_name, output_path)
    finally:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
    from media.artifacts import sha256_file

    return {
        "kind": "channel_intro_thumbnail",
        "mode": "crop-fit",
        "width": INTRO_VIDEO_WIDTH,
        "height": INTRO_VIDEO_HEIGHT,
        "thumbnail": str(thumbnail_path),
        "page_sha256": sha256_file(output_path),
    }

"""Resumable, ordered Edge-TTS audiobook generation.

This module deliberately has no Qt imports.  The UI hosts it in a worker
thread, while tests can inject a small async client and a fake FFmpeg merger.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from media.artifacts import atomic_write_json, sha256_file


class TtsDependencyError(RuntimeError):
    pass


class TtsConfigurationError(ValueError):
    """Raised for a non-retryable TTS setting."""


@dataclass
class TtsChunk:
    order: int
    text: str
    chapter: int = 0
    text_sha256: str = ""
    # Rendered-layout facts measured before TTS (visible lines, validation font size
    # and body width, planning reason).  Metadata for diagnostics and manifests only;
    # audio resumability still depends on ``text_sha256``.
    layout: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text_sha256:
            self.text_sha256 = sha256((self.text or "").encode("utf-8")).hexdigest()


@dataclass
class TtsFailure:
    chunk_number: int
    original_text: str
    failed_part: str
    error_type: str
    error_message: str
    attempts: int
    failed_part_text: str = ""
    main_error_type: str = ""
    main_error_message: str = ""


@dataclass
class TtsResult:
    audio_dir: str
    manifest_path: str
    generated: List[int] = field(default_factory=list)
    skipped: List[int] = field(default_factory=list)
    failures: List[TtsFailure] = field(default_factory=list)
    cancelled: bool = False
    audiobook_path: str = ""

    @property
    def successful_orders(self) -> List[int]:
        return sorted(set(self.generated + self.skipped))


ClientFactory = Callable[[str, str], Any]
ProgressCallback = Callable[[int, int, str], None]


def _default_client_factory(text: str, voice: str):
    try:
        import edge_tts
    except ImportError as error:  # pragma: no cover - depends on optional package
        raise TtsDependencyError("Thiếu edge-tts. Chạy: pip install -r requirements.txt") from error
    return edge_tts.Communicate(text, voice)


def _chunk_path(audio_dir: Path, order: int) -> Path:
    return audio_dir / f"chunk_{order:05d}.mp3"


def _safe_concat_line(path: Path) -> str:
    # FFmpeg concat demuxer uses a single-quoted path. Escape a literal quote
    # without invoking a shell.
    return "file '" + path.resolve().as_posix().replace("'", "'\\''") + "'\n"


class TtsProcessor:
    """Generate audio chunks with fingerprinted resume and ordered merges."""

    def __init__(
        self,
        chunks: Sequence[TtsChunk],
        audio_dir: Path,
        *,
        voice: str,
        max_concurrency: int = 60,
        timeout_seconds: int = 120,
        retry_count: int = 5,
        fallback_retry_count: int = 3,
        client_factory: ClientFactory = _default_client_factory,
        progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[Event] = None,
        ffmpeg_path: Optional[str] = None,
    ) -> None:
        self.chunks = sorted(chunks, key=lambda item: item.order)
        self.audio_dir = Path(audio_dir)
        self.voice = str(voice or "").strip()
        self.max_concurrency = max(1, int(max_concurrency))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.retry_count = max(1, int(retry_count))
        # Accepted for settings/API compatibility; only full-chunk retries are used.
        self.client_factory = client_factory
        self.progress = progress or (lambda _done, _total, _message: None)
        self.cancel_event = cancel_event or Event()
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        self.manifest_path = self.audio_dir / "manifest.json"
        self._manifest: Dict[str, Any] = {}
        self._manifest_lock: Optional[asyncio.Lock] = None
        self._result = TtsResult(str(self.audio_dir), str(self.manifest_path))
        self._completed = 0

    def validate_dependencies(self) -> None:
        if not self.voice:
            raise TtsConfigurationError(
                "Giọng đọc Edge-TTS đang để trống. Hãy chọn vi-VN-HoaiMyNeural "
                "hoặc một giọng Edge-TTS hợp lệ trong Settings."
            )
        if not self.ffmpeg_path:
            raise TtsDependencyError(
                "Không tìm thấy FFmpeg. Cài FFmpeg và bảo đảm lệnh ffmpeg có trong PATH."
            )
        if self.client_factory is _default_client_factory:
            try:
                _default_client_factory("Kiểm tra giọng đọc.", self.voice)
            except ImportError as error:  # pragma: no cover - optional dependency
                raise TtsDependencyError(
                    "Thiếu edge-tts. Chạy: pip install -r requirements.txt"
                ) from error
            except ValueError as error:
                raise TtsConfigurationError(
                    f"Giọng đọc Edge-TTS không hợp lệ '{self.voice}': {error}"
                ) from error

    def _settings_fingerprint(self) -> Dict[str, Any]:
        return {"voice": self.voice}

    def _load_manifest(self) -> None:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            data = {}
        if not isinstance(data, dict) or data.get("schema_version") != 2 or data.get("settings") != self._settings_fingerprint():
            data = {}
        if not isinstance(data.get("chunks", {}), dict) or not isinstance(data.get("failures", []), list):
            data = {}
        self._manifest = {
            "schema_version": 2,
            "settings": self._settings_fingerprint(),
            "chunks": dict(data.get("chunks") or {}),
            "failures": list(data.get("failures") or []),
        }

    def _is_resumable(self, chunk: TtsChunk) -> bool:
        try:
            record = self._manifest["chunks"].get(str(chunk.order), {})
            path = _chunk_path(self.audio_dir, chunk.order)
            return (
                record.get("order") == chunk.order
                and record.get("file") == path.name
                and record.get("text_sha256") == chunk.text_sha256
                and record.get("text") == chunk.text
                and record.get("request_mode") == "full_chunk"
                and record.get("chapter") == chunk.chapter
                and record.get("voice") == self.voice
                and path.is_file()
                and path.stat().st_size > 0
                and record.get("mp3_sha256") == sha256_file(path)
            )
        except (OSError, AttributeError, TypeError):
            return False

    async def _write_manifest(self) -> None:
        assert self._manifest_lock is not None
        async with self._manifest_lock:
            atomic_write_json(self.manifest_path, self._manifest)

    async def _save_once(self, text: str, output: Path) -> None:
        partial = output.with_suffix(output.suffix + ".part")
        task = None
        try:
            partial.unlink(missing_ok=True)
            client = self.client_factory(text, self.voice)
            task = asyncio.create_task(client.save(str(partial)))
            deadline = time.monotonic() + self.timeout_seconds
            while not task.done():
                if self.cancel_event.is_set():
                    raise RuntimeError("Đã hủy tạo audiobook.")
                if time.monotonic() >= deadline:
                    raise asyncio.TimeoutError("Edge-TTS request timed out.")
                await asyncio.wait({task}, timeout=min(0.2, max(0.0, deadline - time.monotonic())))
            await task
            if not partial.is_file() or partial.stat().st_size <= 0:
                raise RuntimeError("Edge-TTS tạo tệp MP3 rỗng.")
            os.replace(partial, output)
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass

    async def _try_save(self, text: str, output: Path, attempts: int) -> tuple[bool, Optional[Exception], int]:
        last: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            if self.cancel_event.is_set():
                return False, RuntimeError("Đã hủy tạo audiobook."), attempt - 1
            try:
                await self._save_once(text, output)
                return True, None, attempt
            except Exception as error:  # network/service failures are expected
                if isinstance(error, TtsConfigurationError) or (
                    isinstance(error, ValueError) and "voice" in str(error).lower()
                ):
                    raise TtsConfigurationError(str(error)) from error
                last = error
                if attempt < attempts:
                    delay = min(16.0, 0.75 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.45)
                    while delay > 0 and not self.cancel_event.is_set():
                        pause = min(0.2, delay)
                        await asyncio.sleep(pause)
                        delay -= pause
        return False, last, attempts

    def _ffmpeg_concat(self, inputs: Iterable[Path], output: Path) -> None:
        paths = [Path(item) for item in inputs]
        if not paths:
            raise RuntimeError("Không có MP3 hợp lệ để gộp.")
        descriptor, list_name = tempfile.mkstemp(prefix=".concat_", suffix=".txt", dir=self.audio_dir)
        os.close(descriptor)
        temporary = output.with_name(f".{output.stem}.part{output.suffix}")
        try:
            Path(list_name).write_text("".join(_safe_concat_line(path) for path in paths), encoding="utf-8")
            temporary.unlink(missing_ok=True)
            if self.cancel_event.is_set():
                raise RuntimeError("Đã hủy gộp audiobook.")
            process = subprocess.Popen(
                [
                    str(self.ffmpeg_path), "-y", "-f", "concat", "-safe", "0",
                    # Decode each input's gapless metadata and remove concat timestamp gaps.
                    "-i", list_name, "-af", "asetpts=N/SR/TB",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(temporary),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            while True:
                try:
                    _, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if self.cancel_event.is_set():
                        process.terminate()
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise RuntimeError("Đã hủy gộp audiobook.")
            if process.returncode != 0:
                raise RuntimeError(stderr.strip() or "FFmpeg không thể gộp MP3.")
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RuntimeError("FFmpeg tạo audiobook rỗng.")
            if self.cancel_event.is_set():
                raise RuntimeError("Đã hủy gộp audiobook.")
            os.replace(temporary, output)
        finally:
            Path(list_name).unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)

    async def _process_chunk(self, chunk: TtsChunk, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            if self.cancel_event.is_set():
                return
            self.progress(
                self._completed,
                len(self.chunks),
                f"Đang xử lý đoạn {chunk.order}/{len(self.chunks)}",
            )
            if self._is_resumable(chunk):
                self._result.skipped.append(chunk.order)
                self._completed += 1
                self.progress(self._completed, len(self.chunks), f"Bỏ qua đoạn {chunk.order} đã hoàn tất")
                return
            output = _chunk_path(self.audio_dir, chunk.order)
            ok, error, attempts = await self._try_save(chunk.text, output, self.retry_count)
            failure: Optional[TtsFailure] = None
            if not ok and error is not None and not self.cancel_event.is_set():
                failure = TtsFailure(chunk.order, chunk.text, "whole", type(error).__name__, str(error),
                                     attempts, failed_part_text=chunk.text)
            if failure is not None:
                self._result.failures.append(failure)
                self._manifest["failures"] = [asdict(item) for item in self._result.failures]
                await self._write_manifest()
                self._completed += 1
                self.progress(self._completed, len(self.chunks), f"Lỗi đoạn {chunk.order}: {failure.error_message}")
                return
            if self.cancel_event.is_set():
                return
            self._manifest["chunks"][str(chunk.order)] = {
                "order": chunk.order,
                "chapter": chunk.chapter,
                "text": chunk.text,
                "text_sha256": chunk.text_sha256,
                "layout": dict(chunk.layout),
                "request_mode": "full_chunk",
                "mp3_sha256": sha256_file(output),
                "voice": self.voice,
                "file": output.name,
            }
            await self._write_manifest()
            self._result.generated.append(chunk.order)
            self._completed += 1
            self.progress(self._completed, len(self.chunks), f"Đã tạo đoạn {chunk.order}/{len(self.chunks)}")

    async def _run_async(self) -> TtsResult:
        self._load_manifest()
        self._manifest_lock = asyncio.Lock()
        # Keep resumable MP3 records, but make failure diagnostics describe
        # this run rather than an earlier attempt.
        self._manifest["failures"] = []
        self._manifest.pop("merge", None)
        self._manifest["ordered_chunks"] = [asdict(c) for c in self.chunks]
        await self._write_manifest()
        self.progress(0, len(self.chunks), f"Bắt đầu xử lý {len(self.chunks)} đoạn")
        semaphore = asyncio.Semaphore(self.max_concurrency)
        await asyncio.gather(*(self._process_chunk(chunk, semaphore) for chunk in self.chunks))
        self._result.cancelled = self.cancel_event.is_set()
        return self._result

    def run(self) -> TtsResult:
        from cleaning.tts_boundaries import meaningful_text
        if (not self.chunks or any(not meaningful_text(c.text) for c in self.chunks)
                or [c.order for c in self.chunks] != list(range(1, len(self.chunks) + 1))
                or any(c.text_sha256 != sha256(c.text.encode("utf-8")).hexdigest() for c in self.chunks)):
            raise TtsConfigurationError("Không có nội dung đọc được trong TTS chunks.")
        self.validate_dependencies()
        return asyncio.run(self._run_async())

    def merge(self, result: TtsResult, output_path: Path, *, skip_failed: bool = False) -> Path:
        if result.cancelled:
            raise RuntimeError("Đã hủy tạo audiobook; không gộp MP3.")
        if result.failures and not skip_failed:
            raise RuntimeError("Còn đoạn lỗi; chọn gộp bỏ qua hoặc hủy.")
        usable = set(result.successful_orders)
        if not usable.issubset({c.order for c in self.chunks}):
            raise RuntimeError("Unknown chunk order in merge result.")
        if not usable:
            raise RuntimeError("Không có đoạn MP3 thành công để gộp.")
        if not skip_failed and usable != {c.order for c in self.chunks}:
            raise RuntimeError("Missing successful chunk MP3s; resume Step 3 before merging.")
        paths = [_chunk_path(self.audio_dir, chunk.order) for chunk in self.chunks if chunk.order in usable]
        if not self._manifest:
            self._load_manifest()
        if any(not self._is_resumable(c) for c in self.chunks if c.order in usable):
            raise RuntimeError("Chunk MP3 provenance changed; resume Step 3 before merging.")
        self._ffmpeg_concat(paths, Path(output_path))
        self._manifest["ordered_chunks"] = [asdict(c) for c in self.chunks]
        self._manifest["merge"] = {
            "orders": [c.order for c in self.chunks if c.order in usable],
            "chunks": [dict(self._manifest["chunks"][str(c.order)]) for c in self.chunks if c.order in usable],
            "complete": len(usable) == len(self.chunks),
            "file": str(Path(output_path).resolve()),
            "mp3_sha256": sha256_file(Path(output_path)),
        }
        atomic_write_json(self.manifest_path, self._manifest)
        result.audiobook_path = str(output_path)
        return Path(output_path)

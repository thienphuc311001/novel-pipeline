"""Batch translation runner with progress reporting and cancellation.

The runner is intentionally blocking (:meth:`BatchTranslationRunner.run`) and is
meant to be called from a worker thread.  A failed batch never destroys the
offline/manual translations already in the store: the error is recorded, the
next batch continues, and the store is saved at the end.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from chinese.dictionary import SOURCE_AI

from .gemini import GeminiClient, GeminiError, GeminiSettings
from .table import TranslationStore

ProgressCallback = Callable[["TranslationProgress"], None]


@dataclass
class TranslationProgress:
    total_phrases: int = 0
    done_phrases: int = 0
    batch_index: int = 0
    batch_total: int = 0
    current_batch: List[str] = field(default_factory=list)
    message: str = ""
    cancelled: bool = False
    finished: bool = False
    translated: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    failed_phrases: List[str] = field(default_factory=list)

    @property
    def percent(self) -> float:
        if not self.total_phrases:
            return 100.0 if self.finished else 0.0
        return min(100.0, self.done_phrases / self.total_phrases * 100.0)

    def describe(self) -> str:
        return (
            f"Lô {self.batch_index}/{self.batch_total} · {self.done_phrases}/"
            f"{self.total_phrases} cụm ({self.percent:.0f}%)"
        )


@dataclass
class TranslationTask:
    phrases: List[str]
    store: TranslationStore
    settings: GeminiSettings
    batch_size: int = 40
    max_batch_chars: int = 2400
    save_store: bool = True
    overwrite_manual: bool = False

    def pending_phrases(self) -> List[str]:
        """Phrases that still need a translation (manual edits are kept)."""
        pending: List[str] = []
        for phrase in self.phrases:
            phrase = (phrase or "").strip()
            if not phrase:
                continue
            record = self.store.get(phrase)
            if record is not None and record.translated and (record.edited or not self.overwrite_manual):
                continue
            pending.append(phrase)
        return pending


def build_batches(
    phrases: Sequence[str], batch_size: int, max_batch_chars: int
) -> List[List[str]]:
    """Split phrases into batches limited by count *and* total characters."""
    size = max(1, int(batch_size or 1))
    char_budget = max(200, int(max_batch_chars or 200))
    batches: List[List[str]] = []
    current: List[str] = []
    chars = 0
    for phrase in phrases:
        phrase = (phrase or "").strip()
        if not phrase:
            continue
        if current and (len(current) >= size or chars + len(phrase) > char_budget):
            batches.append(current)
            current = []
            chars = 0
        current.append(phrase)
        chars += len(phrase)
    if current:
        batches.append(current)
    return batches


class BatchTranslationRunner:
    """Runs optional AI translation in batches with cancel support."""

    def __init__(
        self,
        task: TranslationTask,
        *,
        on_progress: Optional[ProgressCallback] = None,
        client_factory: Optional[Callable[[GeminiSettings], GeminiClient]] = None,
    ) -> None:
        self.task = task
        self.on_progress = on_progress
        self.client_factory = client_factory or (lambda settings: GeminiClient(settings))
        self._cancel = threading.Event()
        self.progress = TranslationProgress()

    # ------------------------------------------------------------- control
    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def _report(self, message: str = "") -> None:
        if message:
            self.progress.message = message
        if self.on_progress is not None:
            self.on_progress(self.progress)

    # ----------------------------------------------------------------- run
    def run(self) -> TranslationProgress:
        pending = self.task.pending_phrases()
        batches = build_batches(pending, self.task.batch_size, self.task.max_batch_chars)
        self.progress = TranslationProgress(
            total_phrases=len(pending),
            batch_total=len(batches),
        )
        if not pending:
            self.progress.finished = True
            self.progress.message = "Không có cụm nào cần dịch."
            self._report()
            return self.progress

        client = self.client_factory(self.task.settings)
        if not self.task.settings.ready:
            self.progress.errors.append("Chưa cấu hình API key/model Gemini; AI tạm tắt.")
            self.progress.finished = True
            self._report()
            return self.progress

        for index, batch in enumerate(batches, start=1):
            if self._is_cancelled():
                self.progress.cancelled = True
                break
            self.progress.batch_index = index
            self.progress.current_batch = list(batch)
            self._report(f"Đang dịch lô {index}/{len(batches)} ({len(batch)} cụm)...")
            try:
                translations = client.translate_phrases(batch, cancel=self._is_cancelled)
            except GeminiError as error:
                self.progress.errors.append(str(error))
                self.progress.failed_phrases.extend(batch)
                self.progress.done_phrases += len(batch)
                self._report(f"Lỗi lô {index}: {error}")
                continue
            except Exception as error:  # pragma: no cover - defensive
                self.progress.errors.append(f"Lỗi không xác định: {error}")
                self.progress.failed_phrases.extend(batch)
                self.progress.done_phrases += len(batch)
                continue

            for phrase in batch:
                translation = (translations.get(phrase) or "").strip()
                if not translation:
                    self.progress.failed_phrases.append(phrase)
                    continue
                self.task.store.add(phrase, translation, source=SOURCE_AI)
                self.progress.translated[phrase] = translation
            self.progress.done_phrases += len(batch)
            self._report(
                f"Xong lô {index}/{len(batches)} · {len(self.progress.translated)} cụm đã dịch"
            )

        if self.task.save_store:
            try:
                self.task.store.save()
            except OSError as error:
                self.progress.errors.append(f"Không lưu được bảng dịch: {error}")
        self.progress.finished = not self.progress.cancelled
        if self.progress.cancelled:
            self.progress.message = "Đã huỷ dịch AI (các bản dịch đã có vẫn được giữ)."
        elif self.progress.errors:
            self.progress.message = (
                f"Hoàn tất với {len(self.progress.errors)} lỗi; "
                "bản dịch offline/nhập tay vẫn nguyên vẹn."
            )
        else:
            self.progress.message = f"Đã dịch {len(self.progress.translated)} cụm bằng Gemini."
        self._report()
        return self.progress


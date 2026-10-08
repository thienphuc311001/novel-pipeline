"""Single writer workspace with immutable published views for HTTP readers."""
from __future__ import annotations

import copy
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone

from backend.validation import validate_action, validate_settings, validate_ui


class BusyError(RuntimeError):
    pass


class MissingJobError(KeyError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


class _JobLogHandler(logging.Handler):
    def __init__(self, manager, job_id):
        super().__init__()
        self.manager = manager
        self.job_id = job_id
        self.thread_id = threading.get_ident()

    def emit(self, record):
        if record.thread == self.thread_id:
            self.manager.append_log(self.job_id, record.levelname.lower(), record.getMessage())


class JobManager:
    def __init__(self, service):
        self.service = service
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self._snapshot = copy.deepcopy(service.snapshot())
        self._settings = copy.deepcopy(service.settings.to_dict())
        self._jobs = {}
        self._logs = {}
        self._sequences = {}
        self._active = None
        self._cancel = None
        self._worker = None
        self._mutating = False
        self._closed = False
        self._version = 0
        self._state_revision = 0

    def _notify(self):
        self._version += 1
        self.changed.notify_all()

    def _require_idle(self):
        if self._closed:
            raise BusyError("Ứng dụng đang đóng.")
        if self._active is not None or self._mutating:
            raise BusyError("Đang xử lý tác vụ khác. Hãy chờ tác vụ kết thúc.")

    def state(self):
        with self.lock:
            return copy.deepcopy(self._snapshot)

    def settings(self):
        with self.lock:
            return copy.deepcopy(self._settings)

    def jobs(self):
        with self.lock:
            return copy.deepcopy(list(reversed(self._jobs.values())))

    def job(self, job_id):
        with self.lock:
            if job_id not in self._jobs:
                raise MissingJobError(job_id)
            return copy.deepcopy(self._jobs[job_id])

    def event_view(self, after_state_revision=None):
        with self.lock:
            view = {
                "jobs": copy.deepcopy(list(reversed(self._jobs.values()))),
                "state_revision": self._state_revision,
            }
            if after_state_revision != self._state_revision:
                view["state"] = copy.deepcopy(self._snapshot)
            return self._version, self._active is not None, view

    def logs(self, job_id, after=0):
        with self.lock:
            if job_id not in self._logs:
                raise MissingJobError(job_id)
            return copy.deepcopy([row for row in self._logs[job_id] if row["sequence"] > after])

    def append_log(self, job_id, level, message):
        with self.lock:
            sequence = self._sequences[job_id] + 1
            self._sequences[job_id] = sequence
            self._logs[job_id].append({
                "sequence": sequence, "timestamp": _now(), "level": level, "message": str(message),
            })
            self._notify()

    def submit(self, action, options):
        validate_action(action, options)
        options = copy.deepcopy(options)
        with self.lock:
            self._require_idle()
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id, "action": action, "status": "queued", "created_at": _now(),
                "finished_at": None, "progress": {"done": 0, "total": 0, "message": "Đang chờ xử lý"},
                "error": None, "result": None,
            }
            self._jobs[job_id] = job
            self._logs[job_id] = deque(maxlen=max(1, int(self._settings.get("max_log_lines", 2000))))
            self._sequences[job_id] = 0
            self._active = job_id
            self._cancel = threading.Event()
            self._worker = threading.Thread(
                target=self._run, args=(job_id, action, options, self._cancel),
                name=f"pipeline-{job_id[:8]}", daemon=False,
            )
            self._notify()
            response = copy.deepcopy(job)
            try:
                self._worker.start()
            except Exception:
                self._active = None
                job.update(status="failed", finished_at=_now(), error="Không khởi động được tác vụ.")
                self._notify()
                raise
            return response

    def stop(self, job_id):
        with self.lock:
            if job_id not in self._jobs:
                raise MissingJobError(job_id)
            job = self._jobs[job_id]
            if job_id == self._active:
                self._cancel.set()
                job["status"] = "stopping"
                self._notify()
            return copy.deepcopy(job)

    def _run(self, job_id, action, options, cancel):
        handler = _JobLogHandler(self, job_id)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        result = None
        error = None
        status = "failed"

        def progress(done, total, message):
            with self.lock:
                self._jobs[job_id]["progress"] = {
                    "done": int(done), "total": int(total), "message": str(message),
                }
                self._notify()
            if message:
                self.append_log(job_id, "info", message)

        with self.lock:
            if not cancel.is_set():
                self._jobs[job_id]["status"] = "running"
            self._notify()
        try:
            if cancel.is_set():
                result = {"cancelled": True}
            else:
                result = self.service.perform(action, options, cancel_event=cancel, progress=progress)
            if not isinstance(result, dict):
                raise TypeError("Tác vụ không trả về đối tượng kết quả hợp lệ.")
            failed_groups = any(row.get("status") == "failed" for row in result.get("groups", []) if isinstance(row, dict))
            if result.get("status") in {"partial", "failed"} or failed_groups:
                status = "failed"
                error = str(result.get("error") or "Một hoặc nhiều nhóm chưa xử lý thành công.")
            elif cancel.is_set() or result.get("cancelled"):
                status = "cancelled"
            else:
                status = "completed"
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            structured = getattr(exc, "result", None)
            if isinstance(structured, dict):
                result = structured
            status = "failed"
        finally:
            # No other service writer can start until persistence and snapshot capture finish.
            # Readers continue to see the preceding committed snapshot during all file work.
            try:
                if self._has_session_content():
                    self.service.save_session()
            except Exception as exc:
                detail = f"Không lưu được phiên làm việc: {exc}"
                error = f"{error}\n{detail}" if error else detail
                status = "failed"
            try:
                snapshot = copy.deepcopy(self.service.snapshot())
                settings = copy.deepcopy(self.service.settings.to_dict())
            except Exception as exc:
                snapshot = None
                settings = None
                detail = f"Không cập nhật được trạng thái: {exc}"
                error = f"{error}\n{detail}" if error else detail
                status = "failed"
            root_logger.removeHandler(handler)
            if error:
                self.append_log(job_id, "error", error)
            with self.lock:
                if snapshot is not None:
                    self._snapshot = snapshot
                    self._settings = settings
                    self._state_revision += 1
                self._jobs[job_id].update(
                    status=status, result=copy.deepcopy(result), error=error, finished_at=_now(),
                )
                self._active = None
                self._cancel = None
                self._notify()

    def _exclusive(self, operation):
        with self.lock:
            self._require_idle()
            self._mutating = True
        try:
            return copy.deepcopy(operation())
        finally:
            try:
                snapshot = copy.deepcopy(self.service.snapshot())
                settings = copy.deepcopy(self.service.settings.to_dict())
                with self.lock:
                    self._snapshot = snapshot
                    self._settings = settings
                    self._state_revision += 1
            finally:
                with self.lock:
                    self._mutating = False
                    self._notify()

    def _has_session_content(self):
        document = self.service.document
        return bool(self.service.session_id or document.original_input_text or document.source_path)

    def update_settings(self, data):
        validate_settings(data)
        return self._exclusive(lambda: self.service.update_settings(copy.deepcopy(data)))

    def save_session(self, ui):
        validate_ui(ui)
        return self._exclusive(lambda: self.service.save_session(copy.deepcopy(ui)))

    def open_session(self, session_id):
        return self._exclusive(lambda: self.service.open_session(session_id))

    def new_session(self):
        return self._exclusive(self.service.new_session)

    def preview_grouping(self, size):
        return self._exclusive(lambda: self.service.preview_grouping(size))

    def outputs(self):
        with self.lock:
            return copy.deepcopy(self._snapshot.get("outputs", []))

    def close(self):
        with self.lock:
            if self._closed:
                return
            self._closed = True
            if self._active is not None:
                self._cancel.set()
                self._jobs[self._active]["status"] = "stopping"
            worker = self._worker
            self._notify()
        if worker is not None:
            worker.join()
        with self.changed:
            self.changed.wait_for(lambda: not self._mutating)
        # Saving never mutates the user's global desktop defaults.
        if self._has_session_content():
            self.service.save_session()

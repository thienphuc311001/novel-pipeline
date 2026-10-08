"""Behavioral boundaries for single-flight workers and committed HTTP snapshots."""
from __future__ import annotations

import copy
import threading
import unittest
from types import SimpleNamespace

from backend.jobs import BusyError, JobManager, MissingJobError
from config.settings import Settings


class ControlledService:
    """Deterministic service boundary: hold a real worker mid-document mutation."""
    def __init__(self):
        self.settings = Settings(max_log_lines=3)
        self.document = SimpleNamespace(original_input_text="before", source_path="")
        self.session_id = None
        self.ui_state = {}
        self.outputs = []
        self.sessions = SimpleNamespace(list_sessions=lambda: [])
        self.entered = threading.Event()
        self.release = threading.Event()
        self.saving = threading.Event()
        self.save_release = threading.Event()
        self.save_release.set()
        self.cancel = None
        self.error = None
        self.save_error = None
        self.result = {"changed": True}
        self.snapshot_calls = 0
        self.save_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return {
            "text": self.document.original_input_text, "groups": [],
            "outputs": copy.deepcopy(self.outputs), "session_id": self.session_id,
            "ui_state": self.ui_state,
        }

    def perform(self, action, options, *, cancel_event, progress):
        self.cancel = cancel_event
        self.document.original_input_text = "during"
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("Test worker release timed out")
        self.document.original_input_text = "after"
        progress(1, 1, "finished work")
        if self.error:
            raise self.error
        return copy.deepcopy(self.result)

    def save_session(self, ui=None):
        self.saving.set()
        if not self.save_release.wait(5):
            raise RuntimeError("Test save release timed out")
        self.save_calls += 1
        if self.save_error:
            raise self.save_error
        if ui is not None:
            self.ui_state = ui
        self.session_id = "a" * 32
        return self.session_id

    def update_settings(self, data):
        self.settings = Settings.from_dict({**self.settings.to_dict(), **data})
        return self.settings.to_dict()

    def open_session(self, session_id):
        self.session_id = session_id
        return self.snapshot()

    def new_session(self):
        self.document.original_input_text = ""
        self.session_id = None
        return self.snapshot()

    def preview_grouping(self, size):
        return {"groups": [], "size": size}


class JobManagerTests(unittest.TestCase):
    def setUp(self):
        self.service = ControlledService()
        self.manager = JobManager(self.service)
        self.addCleanup(self.cleanup_manager)

    def cleanup_manager(self):
        self.service.release.set()
        self.service.save_release.set()
        self.service.save_error = None
        self.manager.close()

    def submit(self):
        job = self.manager.submit("normalize", {})
        self.assertTrue(self.service.entered.wait(2))
        return job["id"]

    def finish(self, job_id):
        self.service.release.set()
        self.service.save_release.set()
        with self.manager.changed:
            completed = self.manager.changed.wait_for(
                lambda: self.manager.job(job_id)["status"] in {"completed", "failed", "cancelled"}, timeout=3,
            )
        self.assertTrue(completed)
        return self.manager.job(job_id)

    def test_readers_never_snapshot_mutating_document_and_views_are_detached(self):
        job_id = self.submit()
        initial_calls = self.service.snapshot_calls
        self.assertEqual(self.service.document.original_input_text, "during")
        self.assertEqual(self.manager.state()["text"], "before")
        _, live, event = self.manager.event_view()
        self.assertTrue(live)
        self.assertEqual(event["state"]["text"], "before")
        event["state"]["text"] = "tampered"
        self.assertEqual(self.manager.state()["text"], "before")
        self.assertEqual(self.service.snapshot_calls, initial_calls)
        self.assertEqual(self.finish(job_id)["status"], "completed")
        self.assertEqual(self.manager.state()["text"], "after")
        self.assertEqual(self.manager.state()["session_id"], "a" * 32)

    def test_progress_deltas_preserve_state_and_commit_or_reconnect_republish_it(self):
        job_id = self.submit()
        _, _, initial = self.manager.event_view()
        _, _, progress = self.manager.event_view(initial["state_revision"])
        self.assertNotIn("state", progress)
        self.assertEqual(self.manager.state()["text"], "before")
        self.finish(job_id)
        _, _, committed = self.manager.event_view(initial["state_revision"])
        self.assertEqual(committed["state"]["text"], "after")
        _, _, reconnected = self.manager.event_view()
        self.assertEqual(reconnected["state"]["text"], "after")

    def test_single_flight_rejects_jobs_and_all_workspace_mutations(self):
        job_id = self.submit()
        operations = [
            lambda: self.manager.submit("normalize", {}),
            lambda: self.manager.update_settings({}),
            lambda: self.manager.save_session({}),
            lambda: self.manager.open_session("a" * 32),
            self.manager.new_session,
            lambda: self.manager.preview_grouping(20),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(BusyError):
                operation()
        self.finish(job_id)

    def test_stop_stays_stopping_until_worker_persists_and_exits(self):
        self.service.save_release.clear()
        job_id = self.submit()
        stopped = self.manager.stop(job_id)
        self.assertEqual(stopped["status"], "stopping")
        self.assertIsNone(stopped["finished_at"])
        self.assertTrue(self.service.cancel.is_set())
        self.service.release.set()
        self.assertTrue(self.service.saving.wait(2))
        self.assertEqual(self.manager.job(job_id)["status"], "stopping")
        with self.assertRaises(BusyError):
            self.manager.submit("normalize", {})
        self.assertEqual(self.manager.state()["text"], "before")
        job = self.finish(job_id)
        self.assertEqual(job["status"], "cancelled")
        self.assertIsNotNone(job["finished_at"])
        self.assertEqual(self.manager.stop(job_id), job)

    def test_failure_during_stop_is_not_masked_as_completion(self):
        self.service.error = RuntimeError("encoder failed")
        job_id = self.submit()
        self.manager.stop(job_id)
        job = self.finish(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"], "encoder failed")
        self.assertEqual(self.manager.state()["text"], "after")
        self.assertGreater(self.service.save_calls, 0)

    def test_partial_batch_result_preserves_successes_but_fails_job(self):
        self.service.result = {"status": "partial", "groups": [
            {"group_id": "one", "status": "completed"},
            {"group_id": "two", "status": "failed", "error": "broken audio"},
        ]}
        job = self.finish(self.submit())
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["result"], self.service.result)
        self.assertTrue(job["error"])

    def test_save_failure_is_visible_and_never_claimed_completed(self):
        self.service.save_error = OSError("disk full")
        job = self.finish(self.submit())
        self.assertEqual(job["status"], "failed")
        self.assertIn("disk full", job["error"])
        self.assertEqual(self.manager.state()["text"], "after")

    def test_close_cancels_waits_and_saves_after_mutation(self):
        job_id = self.submit()
        closed = threading.Event()
        closer = threading.Thread(target=lambda: (self.manager.close(), closed.set()))
        closer.start()
        self.addCleanup(closer.join, 3)
        self.assertTrue(self.service.cancel.wait(2))
        self.assertFalse(closed.is_set())
        self.assertEqual(self.manager.job(job_id)["status"], "stopping")
        self.service.release.set()
        self.assertTrue(closed.wait(3))
        self.assertEqual(self.manager.job(job_id)["status"], "cancelled")
        self.assertEqual(self.service.document.original_input_text, "after")
        self.assertGreaterEqual(self.service.save_calls, 2)
        with self.assertRaises(BusyError):
            self.manager.submit("normalize", {})

    def test_logs_bound_memory_without_reusing_sequence_numbers(self):
        job_id = self.submit()
        for index in range(6):
            self.manager.append_log(job_id, "info", str(index))
        logs = self.manager.logs(job_id)
        self.assertEqual([row["sequence"] for row in logs], [4, 5, 6])
        self.assertEqual([row["message"] for row in self.manager.logs(job_id, after=5)], ["5"])
        with self.assertRaises(MissingJobError):
            self.manager.logs("unknown")
        self.finish(job_id)

    def test_empty_workspace_does_not_create_session_on_start_or_close(self):
        self.service.document.original_input_text = ""
        self.manager.close()
        self.assertEqual(self.service.save_calls, 0)


if __name__ == "__main__":
    unittest.main()

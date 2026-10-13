"""CI-only contract tests; synthetic records, never a model/application run."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("ci", Path(__file__).with_name("ci_support.py"))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def record(mode="dry-run", verdict="NOT_RUN"):
    return {"mode": mode, "name": "numeral-smoke-check", "verdict": verdict,
        "baseline_commit": ci.runner.BASELINE, "grader_hash": ci.runner.GRADER_SHA256,
        "manifest_hash": ci.runner.MANIFEST_SHA256, "cli_version": ci.CLI_VERSION,
        "sandbox": {"checks": {k: True for k in ci.SANDBOX_CHECKS}, "pytest_available": True},
        "grading_boundary": {k: True for k in ci.GRADE_BOUNDARY},
        "cli": {"offline_dispatcher": {"checks": {k: True for k in ci.DISPATCH_CHECKS},
                 "advertised_tools": ["mcp__eval__" + t["name"] for t in ci.runner.tools.TOOLS]}},
        "tool_boundary": {"tools": [t["name"] for t in ci.runner.tools.TOOLS],
            **{k: True for k in ("path_escape_denied", "non_allowlisted_write_denied", "full_suite_denied", "shell_commit_denied")}},
        "model": "opus" if mode == "dry-run" else ci.OPUS_MODEL,
        "dry_run_status": "PASS", "model_called": False, "grader_called": False,
        "model_invocation_attempted": mode == "live",
        "agent_configuration": {"live_eligible": mode == "live", "verified_loaded": mode == "live"},
        "agent": {"transport_success": True, "timed_out": False},
        "agent_exit_status": 0, "grader_exit_status": 0, "grader_verdict": "PASS"}


class Contracts(unittest.TestCase):
    def test_valid_dry_is_not_eval_pass(self):
        ci.validate_report(record(), "dry-run", 0)
        wrong = record(verdict="PASS")
        with self.assertRaises(ValueError):
            ci.validate_report(wrong, "dry-run", 0)

    def test_missing_or_false_isolation_refuses(self):
        for kind in ("sandbox", "grading_boundary", "cli"):
            data = record()
            data.pop(kind)
            with self.assertRaises(ValueError):
                ci.validate_report(data, "dry-run", 0)
        data = record()
        data["sandbox"]["checks"]["egress_unroutable"] = False
        with self.assertRaises(ValueError):
            ci.validate_report(data, "dry-run", 0)

    def test_native_tool_or_wrong_cli_refuses(self):
        data = record()
        data["cli"]["offline_dispatcher"]["advertised_tools"].append("Bash")
        with self.assertRaises(ValueError):
            ci.validate_report(data, "dry-run", 0)
        data = record()
        data["cli_version"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            ci.validate_report(data, "dry-run", 0)

    def test_live_verdict_exit_pairs(self):
        for verdict, rc in (("PASS", 0), ("FAIL", 1), ("ERROR", 2)):
            with self.subTest(verdict=verdict):
                data = record("live", verdict)
                ci.validate_report(data, "live", rc)
                with self.assertRaises(ValueError):
                    ci.validate_report(data, "live", 99)

    def test_live_no_receipt_or_no_profile_never_pass(self):
        for edit in (lambda d: d["agent"].update(transport_success=False),
                     lambda d: d["agent_configuration"].update(verified_loaded=False),
                     lambda d: d.update(model_invocation_attempted=False),
                     lambda d: d.update(grader_verdict="FAIL")):
            data = record("live", "PASS")
            edit(data)
            with self.assertRaises(ValueError):
                ci.validate_report(data, "live", 0)

    def test_limits_and_error_are_distinct(self):
        self.assertEqual(ci.runner.overall_verdict({"transport_success": False, "timed_out": True}, "FAIL"), "FAIL")
        self.assertEqual(ci.runner.overall_verdict({"transport_success": False, "subtype": "error_max_turns"}, "PASS"), "FAIL")
        self.assertEqual(ci.runner.overall_verdict({"transport_success": False}, "PASS"), "ERROR")
        self.assertEqual(ci.runner.overall_verdict({"transport_success": True}, "ERROR"), "ERROR")

    def test_sanitizer_drops_untrusted_text(self):
        data = record()
        marker = "SYNTHETIC_PRIVATE_VALUE"
        data.update(reason=marker, commands={"agent": marker}, artifact_paths={"report": marker}, model=marker)
        data["agent"] = {"model_usage": marker, "stdout": marker}
        self.assertNotIn(marker, json.dumps(ci.sanitized(data, 0)))
        data["cli"] = []
        data["verdict"] = []
        self.assertEqual(ci.sanitized(data, 2)["verdict"], "ERROR")

    def test_missing_report_and_wrong_contract_are_error(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            raw, rc, output = root / "raw.json", root / "rc", root / "safe"
            self.assertEqual(ci.publish(raw, output, "dry-run", rc), 2)
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["verdict"], "ERROR")
            self.assertFalse(summary["contract_valid"])
            raw.write_text(json.dumps(record()))
            rc.write_text("0")
            self.assertEqual(ci.publish(raw, output, "dry-run", rc), 0)
            self.assertEqual(json.loads((output / "summary.json").read_text())["verdict"], "NOT_RUN")

    def test_environment_guard_fail_closed(self):
        good = {"name": "agent-eval-live", "can_admins_bypass": False,
                "deployment_branch_policy": {"protected_branches": True},
                "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}], "prevent_self_review": True}]}
        ci.environment_gate(good)
        for key in good:
            bad = copy.deepcopy(good)
            bad.pop(key)
            with self.assertRaises(ValueError):
                ci.environment_gate(bad)

    def test_external_timeout_no_false_not_run_claim(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            rc = root / "exit"
            rc.write_text("124")
            self.assertEqual(ci.publish(root / "absent.json", root / "safe", "live", rc), 2)
            summary = json.loads((root / "safe/summary.json").read_text())
            self.assertEqual(summary["verdict"], "ERROR")
            self.assertTrue(summary["external_timeout"])
            self.assertIsNone(summary["model_invocation_attempted"])

    def test_namespace_failure_has_safe_diagnostic(self):
        # A real controller probe handles an external bwrap rejection. Only
        # the OS process boundary is doubled; classification/export stay real.
        result = {"exit_status": 1, "timed_out": False, "output_truncated": False,
                  "seconds": 0.1, "stdout": "", "stderr": "bwrap: Creating new namespace failed: Permission denied"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate, controller = root / "candidate", root / "controller"
            candidate.mkdir()
            controller.mkdir()
            with mock.patch.object(ci.runner.tools, "run_bounded", return_value=result):
                with self.assertRaises(ci.runner.RunnerError) as caught:
                    ci.runner.sandbox_probe("/usr/bin/bwrap", candidate, Path("/usr/bin/python3"), controller, [])
        self.assertEqual(getattr(caught.exception, "code", None), "SANDBOX_NAMESPACE_DENIED")
        data = {"failure_code": caught.exception.code, "sandbox_launch": caught.exception.details["sandbox_launch"],
                "reason": "SYNTHETIC_PRIVATE_VALUE"}
        safe = ci.sanitized(data, 2)
        self.assertEqual(safe.get("failure_code"), "SANDBOX_NAMESPACE_DENIED")
        self.assertEqual(safe.get("sandbox_launch", {}).get("exit_status"), 1)
        self.assertIsNone(safe["sandbox"]["net_namespace_differs"])
        self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", json.dumps(safe))

    def test_unknown_failure_prose_never_exported(self):
        marker = "SYNTHETIC_PRIVATE_VALUE"
        safe = ci.sanitized({"failure_code": marker, "sandbox_launch": {"stderr": marker}}, 2)
        self.assertNotIn(marker, json.dumps(safe))


if __name__ == "__main__":
    unittest.main(verbosity=2)

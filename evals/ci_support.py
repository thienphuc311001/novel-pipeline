"""CI contract checks and allowlist-only artifact export (stdlib, no API calls)."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("runner", ROOT / "run_eval.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
CLI_VERSION = "2.1.296 (Claude Code)"
# Verified 2026-10-13: https://platform.claude.com/docs/en/models/overview
OPUS_MODEL = "claude-opus-5-5"
VERDICTS = {"PASS", "FAIL", "ERROR", "NOT_RUN"}
CHECK_IDS = {"scope", "preservation", "behavior", "process_success", "process_mismatch",
             "regression", "documentation", "no_runtime_file_changes"}
SANDBOX_CHECKS = {"net_namespace_differs", "pid_namespace_differs", "no_credentials_in_env",
                  "host_paths_hidden", "controller_hidden", "candidate_read_only", "host_loopback_blocked",
                  "egress_unroutable", "raw_socket_denied", "pillow_importable"}
DISPATCH_CHECKS = {"exact_mcp_registry", "native_bash_denied", "native_read_denied", "mcp_escape_denied",
                   "allowed_mcp_read_works", "no_private_read", "no_native_side_effect", "cli_completed", "api_key_auth_path"}
GRADE_BOUNDARY = {"grader_read_only", "oracle_read_only", "candidate_read_only", "private_artifacts_hidden",
                  "oracle_resolves_pinned_commit", "grader_digest_matches"}


def require(condition):
    if not condition:
        raise ValueError("CI contract not satisfied")


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 4 * 1024**2)
    result = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(result, dict))
    return result


def validate_files():
    manifest = (ROOT / "numeral-smoke-check.json").read_bytes()
    grader = (ROOT / "graders/numeral_smoke_check.py").read_bytes()
    require(hashlib.sha256(manifest).hexdigest() == runner.MANIFEST_SHA256)
    require(hashlib.sha256(grader).hexdigest() == runner.GRADER_SHA256)
    config = json.loads(manifest)
    require(config["from"] == runner.BASELINE and set(config["may_change"]) == runner.tools.ALLOWLIST)
    for path in [*ROOT.glob("*.py"), *ROOT.joinpath("graders").glob("*.py")]:
        compile(path.read_bytes(), str(path), "exec")  # No pyc/no application imports.


def all_checks(data, expected):
    require(isinstance(data, dict) and set(data) == expected and all(v is True for v in data.values()))


def validate_report(report, mode, exit_code):
    require(type(exit_code) is int and report.get("mode") == mode)
    require(report.get("name") == "numeral-smoke-check" and report.get("baseline_commit") == runner.BASELINE)
    require(report.get("grader_hash") == runner.GRADER_SHA256 and report.get("manifest_hash") == runner.MANIFEST_SHA256)
    require(report.get("cli_version") == CLI_VERSION)
    all_checks(report.get("sandbox", {}).get("checks"), SANDBOX_CHECKS)
    # The approved regression runner is unittest; pytest is supplementary.
    # CI installs it explicitly, but local stdlib-only preflight may lack it.
    require(type(report["sandbox"].get("pytest_available")) is bool)
    all_checks(report.get("grading_boundary"), GRADE_BOUNDARY)
    all_checks(report.get("cli", {}).get("offline_dispatcher", {}).get("checks"), DISPATCH_CHECKS)
    require(sorted(report.get("cli", {}).get("offline_dispatcher", {}).get("advertised_tools", [])) ==
            sorted("mcp__eval__" + t["name"] for t in runner.tools.TOOLS))
    require(report.get("tool_boundary", {}).get("tools") == [t["name"] for t in runner.tools.TOOLS])
    for key in ("path_escape_denied", "non_allowlisted_write_denied", "full_suite_denied", "shell_commit_denied"):
        require(report["tool_boundary"].get(key) is True)
    if mode == "dry-run":
        require(exit_code == 0 and report.get("verdict") == "NOT_RUN" and report.get("dry_run_status") == "PASS")
        require(report.get("model_called") is False and report.get("grader_called") is False)
        require(not report.get("model_invocation_attempted", False))
    else:
        require(report.get("model") == OPUS_MODEL)
        require(report.get("agent_configuration", {}).get("live_eligible") is True)
        require(report.get("agent_configuration", {}).get("verified_loaded") is True)
        require(report.get("model_invocation_attempted") is True)
        require(report.get("verdict") in ("PASS", "FAIL", "ERROR"))
        require(exit_code == {"PASS": 0, "FAIL": 1, "ERROR": 2}[report["verdict"]])
        if report["verdict"] == "PASS":
            require(report.get("agent", {}).get("transport_success") is True)
            require(report.get("agent_exit_status") == 0 and report.get("grader_exit_status") == 0)
            require(report.get("grader_verdict") == "PASS" and not report["agent"].get("timed_out"))


def environment_gate(data):
    """Metadata only; never query secrets. Unavailable reviewer protection fails."""
    require(data.get("name") == "agent-eval-live" and data.get("can_admins_bypass") is False)
    rules = data.get("protection_rules", [])
    require(any(r.get("type") == "required_reviewers" and r.get("reviewers") and
                r.get("prevent_self_review") is True for r in rules))
    require(data.get("deployment_branch_policy") is not None)


def sha(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) else None


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e9 else None


def sanitized(report, exit_code):
    """Discard prose, commands, arbitrary paths and logs, even if they look safe.

    Does not read the authentication env or use a secret-dependent scrubber.
    Verdict alone is never trusted without the separate contract_valid field.
    """
    report = dict(report)
    for key in ("agent_configuration", "agent", "sandbox", "cli", "grading_boundary", "limits"):
        if not isinstance(report.get(key), dict):
            report[key] = {}
    for parent, key in (("cli", "offline_dispatcher"), ("sandbox", "checks")):
        report[parent] = dict(report[parent])
        if not isinstance(report[parent].get(key), dict):
            report[parent][key] = {}
    if not isinstance(report["cli"]["offline_dispatcher"].get("checks"), dict):
        report["cli"]["offline_dispatcher"] = {"checks": {}}
    profile = report["agent_configuration"]
    if not isinstance(profile.get("blockers", []), list):
        profile = dict(profile, blockers=[])
    for key in ("mode", "verdict", "model"):
        if not isinstance(report.get(key), str):
            report[key] = "UNKNOWN"
    result = {"schema_version": 1, "name": "numeral-smoke-check",
        "failure_code": report.get("failure_code") if isinstance(report.get("failure_code"), str) and
            report["failure_code"] in ("SANDBOX_NAMESPACE_DENIED", "SANDBOX_UID_MAP_FAILED", "SANDBOX_MOUNT_FAILED",
                "SANDBOX_EXEC_FAILED", "SANDBOX_LAUNCH_FAILED", "SANDBOX_TIMEOUT", "SANDBOX_BOUNDARY_FAILED", "SANDBOX_PYTHON_FAILED") else None,
        "mode": report.get("mode") if report.get("mode") in ("dry-run", "live") else "UNKNOWN",
        "verdict": report.get("verdict") if report.get("verdict") in VERDICTS else "ERROR",
        "runner_exit_status": exit_code,
        "stage": report.get("stage") if report.get("stage") in ("CONFIG", "FROZEN_INPUTS", "BASELINE_EXPORT",
            "SANDBOX", "CLI_AUDIT", "MCP_BRIDGE", "DRY_RUN_COMPLETE", "LIVE_READINESS_GATE", "AGENT", "GRADER", "LIVE_COMPLETE") else "UNKNOWN",
        "model": report.get("model") if report.get("model") in ("opus", OPUS_MODEL) else "OTHER",
        "cli_version": CLI_VERSION if report.get("cli_version") == CLI_VERSION else "UNVERIFIED",
        "baseline_commit": runner.BASELINE if report.get("baseline_commit") == runner.BASELINE else "UNVERIFIED",
        "model_invocation_attempted": report.get("model_invocation_attempted") if
            type(report.get("model_invocation_attempted")) is bool else False if report.get("model_called") is False else None,
        "dry_run_pass": report.get("dry_run_status") == "PASS",
        "pytest_available_in_sandbox": report["sandbox"].get("pytest_available") is True,
        "profile_live_eligible": profile.get("live_eligible") is True,
        "profile_verified_loaded": profile.get("verified_loaded") is True,
        "agent_config_inventory_hash": sha(profile.get("inventory_hash")),
        "agent_config_source_head": profile.get("source_head") if isinstance(profile.get("source_head"), str) and
            re.fullmatch(r"[a-f0-9]{40}", profile["source_head"]) else None,
        "live_blockers": [c for c in profile.get("blockers", []) if isinstance(c, str) and c in
                          ("CURRENT_AGENT_CONFIG_NOT_LOADED", "CURRENT_PROFILE_BOUNDARIES_NOT_VERIFIED")],
        "seconds": number(report.get("seconds")), "cost_estimate_usd": number(report.get("cost_estimate_usd")),
        "budget_is_estimate_not_billing_cap": True,
        "agent_timed_out": report.get("agent", {}).get("timed_out") is True,
        "grader_timed_out": report.get("grader_timed_out") is True,
        "artifacts": ["summary.json"],
        "hashes": {k: sha(report.get(k)) for k in ("manifest_hash", "prompt_hash", "manifest_prompt_hash",
                   "grader_hash", "bridge_hash", "cli_audit_hash", "baseline_tree_digest")}}
    for name, checks in (("sandbox", SANDBOX_CHECKS), ("grading_boundary", GRADE_BOUNDARY), ("dispatcher", DISPATCH_CHECKS)):
        data = (report.get("sandbox", {}).get("checks", {}) if name == "sandbox" else
                report.get("cli", {}).get("offline_dispatcher", {}).get("checks", {}) if name == "dispatcher" else
                report.get("grading_boundary", {}))
        result[name] = {k: data.get(k) if type(data.get(k)) is bool else None for k in sorted(checks)}
    launch = report.get("sandbox_launch", {})
    if isinstance(launch, dict):
        result["sandbox_launch"] = {k: launch.get(k) if type(launch.get(k)) is bool else None
                                    for k in ("timed_out", "output_truncated")}
        rc = launch.get("exit_status")
        result["sandbox_launch"]["exit_status"] = rc if type(rc) is int and -256 <= rc <= 256 else None
        exception = launch.get("exception_type")
        result["sandbox_launch"]["exception_type"] = exception if exception in (
            "PermissionError", "FileNotFoundError", "ModuleNotFoundError", "ImportError", "SyntaxError", "OSError",
            "ValueError", "RuntimeError", "AttributeError", "NameError") else None
        for key, maximum in (("payload_line", 512), ("errno", 256)):
            value = launch.get(key)
            result["sandbox_launch"][key] = value if type(value) is int and 1 <= value <= maximum else None
        operation = launch.get("operation")
        result["sandbox_launch"]["operation"] = operation if operation in ("capset", "loopback", "rtm_newaddr", "prctl", "unknown option") else None
    result["limits"] = {k: number(report.get("limits", {}).get(k)) for k in
                        ("agent_seconds", "tool_seconds", "grader_seconds", "max_turns", "max_budget_usd")}
    docs = report.get("current_document_status", {})
    result["current_document_status"] = {p: docs.get(p) if isinstance(docs, dict) and
        docs.get(p) in ("Approved", "Draft") else "UNVERIFIED" for p in runner.DOCS}
    return result


def publish(raw, output, mode, exit_file):
    report, rc, valid = {}, 2, False
    try:
        rc = int(exit_file.read_text().strip())
        report = read_json(raw)
        validate_report(report, mode, rc)
        valid = True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    summary = sanitized(report, rc)
    summary["mode"] = mode
    summary["external_timeout"] = rc in (124, 137)
    summary["contract_valid"] = valid
    if not valid:
        summary["verdict"] = "ERROR"
    if not report:
        summary["completion"] = "RUNNER_TIMEOUT" if rc in (124, 137) else "NO_REPORT_CANCELLED_OR_SETUP_ERROR"
    # Independently validate the graded result; never publish its prose.
    if valid and mode == "live":
        try:
            score = read_json(Path(report["artifact_paths"]["grader_report"]))
            require(score.get("verdict") == report["grader_verdict"])
            require(score.get("grader_sha256") == runner.GRADER_SHA256)
            summary["grader_checks"] = [{"id": c["id"], "status": c["status"]} for c in score["checks"]
                                        if c.get("id") in CHECK_IDS and c.get("status") in VERDICTS]
            if summary["verdict"] == "PASS":
                require({c["id"] for c in summary["grader_checks"]} == CHECK_IDS)
                require(all(c["status"] == "PASS" for c in summary["grader_checks"]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            summary.update(verdict="ERROR", contract_valid=False)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("CI report contract valid." if summary["contract_valid"] else "CI report missing or contract invalid.")
    return 0 if summary["contract_valid"] and summary["verdict"] in ("PASS", "NOT_RUN") else 2 if summary["verdict"] == "ERROR" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "publish", "live-gate", "environment-gate"))
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    parser.add_argument("--exit-file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate_files()
        elif args.command == "publish":
            return publish(args.raw, args.output, args.mode, args.exit_file)
        elif args.command == "live-gate":
            report = read_json(args.raw)
            validate_report(report, "dry-run", 0)
            require(report["agent_configuration"].get("live_eligible") is True)
            require(report["agent_configuration"].get("verified_loaded") is True)
        else:
            environment_gate(read_json(args.raw))
        print("CI gate passed.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, AttributeError):
        print("CI gate refused: configuration, protection or verification evidence missing.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

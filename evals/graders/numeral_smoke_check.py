#!/usr/bin/env python3
"""Trusted, stdlib-only grader for the numeral-smoke-check Agent task.

This grades the files left by an Agent, not its final message. It is a custom
local eval manifest/runner contract, not a claimed built-in Claude Code schema.

Controller protocol (do not run this from an Agent-writable copy):
1. Before starting the Agent, copy this file and the JSON manifest to an external
   controller directory. Pin their SHA-256 in the CI job/approval record. Mount
   them and a trusted Git mirror read-only to the grader, inaccessible to the
   Agent. The mirror must contain BASELINE; never use candidate .git as authority.
2. Export BASELINE to a fresh candidate directory; optionally initialize Git
   there for the Agent. No eval/oracle files, venv, user config or credentials
   belong in that directory. Use an already provisioned external interpreter.
   Give the Agent the frozen manifest's prompt, and only that fresh directory
   as its writable repository. Keep agent output/logs outside the directory.
3. Terminate the Agent and its processes. Snapshot/mount candidate read-only.
   Run the frozen grader from outside it (absolute paths):
       /external/python -I -B /controller/numeral_smoke_check.py \
           --trusted-repo /controller/repo.git --candidate /run/candidate \
           --python /external/python > /controller/result.json
4. Require grader exit 0 AND verdict PASS, plus a successful Agent run receipt
   with pinned model/CLI, prompt/grader hashes, limits, duration and usage. A
   reference patch PASS is grader calibration, not measured Agent performance.

Exit 0 = all gates PASS; 1 = candidate FAIL; 2 = harness/environment ERROR.
FAIL/ERROR is never a successful eval. Python 3.11+; Linux/POSIX runner required
for process-group cleanup. Each child has a 30s default deadline; regression
module (only tests.test_verify) has a 120s default deadline.

Security boundary: Python socket patches are observable offline checks, NOT an
adversarial sandbox. Candidate Python/tests are untrusted. The CI controller must
isolate processes with no egress, no secrets, read-only oracle/inputs and a
separate writable scratch area. The Agent's paid model access is a separate
controlled channel. CLI tool permissions and file allowlists are not an OS
sandbox. Native networking, ctypes, forged observations and hostile Python
require that external boundary; this first grader does not claim to solve them.

Future CI (not implemented here): use a fresh non-interactive Claude Code
session, reviewed tool permissions, a fixed model/version, max turns/budget and
job timeout. Persist Agent exit/result/usage independently of grader verdict;
record per-check failure rates and cost, repeat trials before setting thresholds.
Do not use --bare without explicitly supplying project guidance: bare mode
skips CLAUDE.md. Validate flags against the installed CLI before paid execution.
Official references: https://code.claude.com/docs/en/headless and
https://code.claude.com/docs/en/cli-reference . No API calls are made by this file.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BASELINE = "405c0251e2b5a06862cbf32f9acb9ebd53c11dee"
ALLOWLIST = frozenset(("verify.py", "tests/test_verify.py", "INSTALL.md"))
CASES = (("九十八", 98), ("一百零五", 105), ("两万三千", 23000),
         ("一二", None), ("十十", None))
EXPECTED = dict(CASES)
INPUTS = [text for text, _ in CASES]
OTHER = ("test_imports", "test_chapter_detection", "test_chunking")
ORDER = (OTHER[0], "test_chinese_numerals", OTHER[1], OTHER[2])
REQUIRED_TESTS = frozenset((
    "test_numerals_matching_cases_pass", "test_numerals_mismatch_at_each_position_fails",
    "test_main_numeral_mismatch_returns_one", "test_main_all_checks_success_returns_zero",
    "test_main_other_check_failures_continue", "test_main_converter_exception_returns_one",
    "test_summary_messages_are_scoped", "test_process_success_runs_actual_script",
    "test_process_mismatch_runs_main_guard_and_exits_one", "test_repeated_runs_do_not_leak_fault_or_config",
))  # Approved plan §5 T1–T10 method identities; not supplied by candidate.
SUCCESS = "Smoke checks reported success. Full application validation was not performed."
FAILURE = "One or more smoke checks failed. Review the results above."
COUNT = "Smoke checks reporting success: {passed}/{total}"
NETWORK = "EVAL_NETWORK_BLOCKED"
OBSERVATION = "NUMERAL_EVAL_OBSERVATION "
PAYLOAD = "NUMERAL_EVAL_PAYLOAD "


class HarnessError(RuntimeError):
    """No usable measurement; never counted as PASS or bug regression RED."""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def secret_path(relative):
    # Inspect names only: never open credential files, even when out of scope.
    return any(part == ".env" or part.startswith(".env.") or
               part in ("id_rsa", "id_ed25519", "credentials.json", "token.json", "tokens.json") or
               (part.startswith("client_secret") and part.endswith(".json"))
               for part in Path(relative).parts)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def run_git(repo, *arguments):
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C.UTF-8"}
    try:
        completed = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *arguments],
                                   capture_output=True, check=False, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"trusted Git read failed: {type(exc).__name__}") from exc
    if completed.returncode:
        raise HarnessError("trusted Git read failed; check mirror and pinned baseline")
    return completed.stdout


def baseline_tree(repo):
    require(run_git(repo, "rev-parse", "--verify", BASELINE + "^{commit}").decode().strip() == BASELINE,
            "pinned baseline did not resolve exactly")
    tree = {}
    for record in run_git(repo, "ls-tree", "-rz", BASELINE).split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        relative = encoded_path.decode("utf-8")
        if secret_path(relative) or mode not in ("100644", "100755") or kind != "blob":
            raise HarnessError("baseline contains credential paths/symlinks/submodules; review export policy")
        tree[relative] = (mode, oid)
    return tree


def candidate_tree(root):
    tree, rejected = {}, []
    def unreadable(error):
        raise HarnessError("candidate inventory could not read a directory") from error
    for directory, directories, files in os.walk(root, followlinks=False, onerror=unreadable):
        here = Path(directory)
        # .git is optional Agent bookkeeping, never an oracle. Everything else,
        # including ignored/untracked files, is compared. No cache whitelist.
        if here == root and ".git" in directories:
            directories.remove(".git")
        for name in list(directories):
            item = here / name
            if item.is_symlink():
                rejected.append(item.relative_to(root).as_posix())
                directories.remove(name)
        for name in files:
            item = here / name
            relative = item.relative_to(root).as_posix()
            if relative == ".git":
                continue
            if secret_path(relative) or item.is_symlink() or not stat.S_ISREG(item.lstat().st_mode):
                rejected.append(relative)
                continue
            if item.stat().st_size > 32 * 1024 * 1024:
                rejected.append(relative)
                continue
            mode = "100755" if item.stat().st_mode & stat.S_IXUSR else "100644"
            tree[relative] = (mode, git_blob(item.read_bytes()))
    require(not rejected, "unsafe/unexpected file paths (contents not read): " + ", ".join(rejected))
    return tree


def scope_gate(candidate, baseline):
    changed = sorted(p for p in baseline.keys() | candidate.keys() if baseline.get(p) != candidate.get(p))
    require(not set(changed) - ALLOWLIST, "outside allowlist: " + ", ".join(set(changed) - ALLOWLIST))
    require(all(p in candidate for p in ALLOWLIST), "required product/test/document file missing")
    require(set(changed) == ALLOWLIST, "task must change verify.py and INSTALL.md and add tests/test_verify.py")
    require(all(candidate[p][0] == baseline.get(p, ("100644", ""))[0] for p in ALLOWLIST),
            "unexpected executable-bit changes")
    return {"changed": changed, "tracked_baseline_files": len(baseline)}


def structure_gate(root, old_source):
    old, new = ast.parse(old_source), ast.parse((root / "verify.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in new.body if isinstance(n, ast.FunctionDef)}
    originals = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
    require(set(functions) == set(originals), "preserve the existing five callable interfaces; no new hooks")
    for name in functions:
        require(ast.dump(functions[name].args) == ast.dump(originals[name].args), f"changed interface: {name}")
    for name in OTHER:
        require(ast.dump(functions[name]) == ast.dump(originals[name]), f"unrelated checker changed: {name}")
    # This task approves only changes inside the numeral checker and main's text.
    def outer(tree):
        return [ast.dump(n) for n in tree.body if not isinstance(n, ast.FunctionDef)]
    require(outer(new) == outer(old), "changed imports/module scope/__main__ guard")
    fixture = [n for n in ast.walk(functions["test_chinese_numerals"])
               if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tests" for t in n.targets)]
    require(len(fixture) == 1 and tuple(ast.literal_eval(fixture[0].value)) == CASES,
            "existing five independent expected fixtures must remain unchanged")
    imports = [n for n in ast.walk(functions["test_chinese_numerals"]) if isinstance(n, ast.ImportFrom)]
    require(any(n.module == "chapters" and any(a.name == "chinese_to_int" and a.asname is None
                for a in n.names) for n in imports), "preserve function-local chapters converter binding")
    old_main, new_main = originals["main"], functions["main"]
    replacements = {"Results: ": "Smoke checks reporting success: ", " tests passed": "",
                    "✅ All tests passed - Application is ready!": "✅ " + SUCCESS,
                    "❌ Some tests failed - Check errors above": "❌ " + FAILURE}
    for node in ast.walk(old_main):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = replacements.get(node.value, node.value)
        if isinstance(node, ast.JoinedStr):
            node.values = [part for part in node.values if not (
                isinstance(part, ast.Constant) and part.value == " tests passed")]
    # Allow decoration around the approved messages; not a runner redesign.
    def strip_decoration(function):
        for node in ast.walk(function):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for message in (SUCCESS, FAILURE):
                    if node.value in tuple(prefix + message for prefix in ("", "✅ ", "❌ ", "✓ ", "✗ ")):
                        node.value = message
    strip_decoration(old_main)
    strip_decoration(new_main)
    require(ast.dump(old_main) == ast.dump(new_main), "main runner changed beyond approved D3 messages")
    tests = ast.parse((root / "tests/test_verify.py").read_text(encoding="utf-8"))
    require(any(isinstance(n, ast.ClassDef) and any(
        (isinstance(b, ast.Attribute) and b.attr == "TestCase") or
        (isinstance(b, ast.Name) and b.id == "TestCase") for b in n.bases) for n in tests.body),
        "new regression module must use unittest.TestCase")
    imports = set()
    for node in ast.walk(tests):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
            require(not (node.module == "verify" and any(a.name.startswith("test_") or a.name == "*"
                        for a in node.names)), "import verify as a module to avoid pytest collection pollution")
    project_modules = {p.stem if p.is_file() else p.name for p in root.iterdir()}
    require(not imports - sys.stdlib_module_names - project_modules, "new tests import a non-stdlib dependency")
    return {"fixtures": 5, "checks": 4, "entry_point_preserved": True}


def documentation_gate(root, old_source):
    # Mechanical prerequisite, not a substitute for Technical Lead prose review (AR3).
    new = (root / "INSTALL.md").read_text(encoding="utf-8")
    require(new != old_source, "INSTALL.md unchanged")
    before, after = old_source.split("## Tests and migration parity", 1)
    previous, suffix = after.split("## Troubleshooting", 1)
    require(new.startswith(before + "## Tests and migration parity"), "INSTALL change outside target section")
    current, end = new[len(before + "## Tests and migration parity"):].split("## Troubleshooting", 1)
    require(end == suffix and current.startswith(previous), "INSTALL existing guidance must be retained")
    added = current[len(previous):].lower()
    require("python verify.py" in added and "repository root" in added, "missing root invocation guidance")
    require("`0`" in added and "`1`" in added and "failure" in added and "exception" in added,
            "missing success/failure/caught-exception exit contract")
    require("smoke" in added and "application" in added and "tts" in added and "youtube" in added
            and ("not" in added or "limited" in added), "missing application/provider limits")
    return {"mechanical_document_checks": "PASS", "semantic_review": "Technical Lead required"}


def install_guard(expected_verify):
    """Observe real candidate calls; block/probe Python network primitives."""
    attempts = [0]
    def blocked(*args, **kwargs):
        attempts[0] += 1
        raise RuntimeError(NETWORK)
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    probes = 0
    for method in ("connect", "connect_ex", "create_connection", "getaddrinfo"):
        with socket.socket() as sock:
            try:
                if method in ("connect", "connect_ex"):
                    getattr(sock, method)(("127.0.0.1", 9))
                elif method == "create_connection":
                    socket.create_connection(("127.0.0.1", 9), timeout=1)
                else:
                    socket.getaddrinfo("localhost", 9)
            except RuntimeError as exc:
                probes += str(exc) == NETWORK
    require(probes == 4 and attempts[0] == 4, "Python network guard probes failed")
    attempts[0] = 0
    observed = {"main_calls": 0, "main_returns": [], "checker_returns": [], "checks": []}
    def profile(frame, event, arg):
        if frame.f_code.co_filename != str(expected_verify):
            return
        name = frame.f_code.co_name
        if event == "call" and name in ORDER:
            observed["checks"].append(name)
        if name == "main" and event == "call":
            observed["main_calls"] += 1
        if event == "return" and name in ("main", "test_chinese_numerals"):
            key = "main_returns" if name == "main" else "checker_returns"
            observed[key].append({"type": type(arg).__name__, "value": arg if type(arg) in (int, bool, type(None))
                                  else "unsupported", "module": frame.f_globals.get("__name__")})
    sys.setprofile(profile)
    def report():
        sys.setprofile(None)
        active = (socket.socket.connect is blocked and socket.socket.connect_ex is blocked and
                  socket.create_connection is blocked and socket.getaddrinfo is blocked)
        observed.update(probes=probes, network_attempts=attempts[0], guard_active=active)
        print(OBSERVATION + json.dumps(observed, ensure_ascii=False), file=sys.stderr, flush=True)
    return report


def summary(output, passed):
    counts = re.findall(r"^(?:Smoke checks reporting success: (\d+)/(\d+)|Results: (\d+)/(\d+) tests passed)$",
                        output, flags=re.M)
    require(len(counts) == 1 and tuple(int(x) for x in counts[0] if x) == (passed, 4), "wrong check-level count")
    require(COUNT.format(passed=passed, total=4) in output, "missing approved D3 count")
    message, absent = (SUCCESS, FAILURE) if passed == 4 else (FAILURE, SUCCESS)
    require(message in output and absent not in output, "wrong approved summary branch")
    require("application is ready" not in output.lower(), "whole-application readiness claim")


def diagnostics(output, values):
    lines = re.findall(r"^\s*([✓✗]) chinese_to_int\('([^']*)'\) = (.*?) \(expected (.*?)\)$", output, re.M)
    want = [("✓" if values[t] == expected else "✗", t, str(values[t]), str(expected)) for t, expected in CASES]
    require(lines == want, "input/actual/expected diagnostics or case evaluation order changed")


def behavior_probe(root):
    sys.path.insert(0, str(root))
    import chapters
    import chapters.numerals
    verify = importlib.import_module("verify")
    require(Path(verify.__file__).resolve() == root / "verify.py", "wrong verify module")
    require(Path(chapters.__file__).resolve().parent == root / "chapters", "wrong chapters module")
    original = chapters.chinese_to_int
    require(original is chapters.numerals.chinese_to_int, "converter re-export drift")
    checks = []
    def gate(name, function):
        try:
            details = function()
            checks.append({"id": name, "status": "PASS", "evidence": details})
        except AssertionError as exc:
            checks.append({"id": name, "status": "FAIL", "reason": str(exc)})
    def checker(overrides=None, raises=False):
        ledger, out = [], io.StringIO()
        values = {**EXPECTED, **(overrides or {})}
        def convert(text):
            ledger.append(text)
            if raises:
                raise RuntimeError("synthetic converter failure")
            return values[text]
        with mock.patch.object(chapters, "chinese_to_int", convert), contextlib.redirect_stdout(out):
            result = verify.test_chinese_numerals()
        return result, ledger, out.getvalue(), values
    def matching():
        require([original(t) for t in INPUTS] == list(EXPECTED.values()), "real converter no longer matches oracle")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = verify.test_chinese_numerals()
        require(result is True, "real matching checker must return True")
        diagnostics(out.getvalue(), EXPECTED)
        return {"real_converter_cases": 5, "checker": True}
    gate("matching", matching)
    def mismatches():
        # Fixed oracle + extra drift values: detect special casing of a single sentinel.
        variants = (("九十八", 97), ("一百零五", 104), ("两万三千", 22999),
                    ("一二", 12), ("十十", 20), ("九十八", None),
                    ("九十八", -713), ("十十", 123456))
        for text, value in variants:
            result, ledger, output, values = checker({text: value})
            require(result is False, f"checker false positive: {text} -> {value!r}; returned {result!r}")
            require(ledger == INPUTS, "mismatch short-circuited or reordered converter calls")
            diagnostics(output, values)
        return {"mismatch_scenarios": len(variants), "calls_per_scenario": 5}
    gate("mismatches", mismatches)
    def main_run(overrides=None, failure_name=None, exception=False, converter_exception=False):
        ledger, out, err = [], io.StringIO(), io.StringIO()
        values = {**EXPECTED, **(overrides or {})}
        def convert(text):
            ledger.append("convert:" + text)
            if converter_exception:
                raise RuntimeError("synthetic converter failure")
            return values[text]
        def other(name):
            def run():
                ledger.append(name)
                if name == failure_name and exception:
                    raise RuntimeError("synthetic check failure")
                return name != failure_name
            return run
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(chapters, "chinese_to_int", convert))
            for name in OTHER:
                stack.enter_context(mock.patch.object(verify, name, other(name)))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            rc = verify.main()  # Neither checker nor main is replaced.
        failed = bool(overrides) or failure_name is not None or converter_exception
        require(type(rc) is int and rc == int(failed), f"real main wrong signal/type: {rc!r}")
        expected_ledger = [OTHER[0], *("convert:" + t for t in (INPUTS[:1] if converter_exception else INPUTS)),
                           OTHER[1], OTHER[2]]
        require(ledger == expected_ledger, "check/converter call count/order or continuation changed")
        summary(out.getvalue(), 3 if failed else 4)
        if exception or converter_exception:
            require("Traceback" in err.getvalue() and "RuntimeError: synthetic" in err.getvalue(),
                    "main exception boundary/traceback changed")
        else:
            diagnostics(out.getvalue(), values)
        return rc
    def aggregate():
        require(main_run() == 0, "success exit")
        require(main_run({"九十八": 97}) == 1, "mismatch exit")
        for name in OTHER:
            main_run(failure_name=name)
            main_run(failure_name=name, exception=True)
        return {"main_scenarios": 8, "exact_int_exit_codes": [0, 1]}
    gate("aggregation", aggregate)
    def exception_boundary():
        try:
            checker(raises=True)
        except RuntimeError as exc:
            require(str(exc) == "synthetic converter failure", "wrong converter exception")
        else:
            raise AssertionError("checker swallowed converter exception")
        main_run(converter_exception=True)
        # Fresh matching call after injection contexts: no leaked binding.
        require(chapters.chinese_to_int is original, "converter patch leaked")
        matching()
        return {"helper_propagates": True, "main_catches_and_continues": True, "restored": True}
    gate("exception_and_restore", exception_boundary)
    return {"checks": checks}


def regression_probe(root):
    sys.path.insert(0, str(root))
    module = importlib.import_module("tests.test_verify")
    require(Path(module.__file__).resolve() == root / "tests/test_verify.py", "wrong regression module")
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    def identities(test):
        if isinstance(test, unittest.TestSuite):
            return [identity for child in test for identity in identities(child)]
        return [test.id()]
    ids = identities(suite)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {"ids": ids, "run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "failure_records": [{"id": test.id(), "traceback": detail} for test, detail in result.failures],
            "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses), "successful": result.wasSuccessful(),
            "output": stream.getvalue()[-20000:]}


def worker(mode, candidate):
    root = Path(candidate).resolve()
    report = None
    try:
        report = install_guard(root / "verify.py")
        data = behavior_probe(root) if mode == "behavior" else regression_probe(root)
        data.update(python_version=sys.version.split()[0], python_executable=sys.executable)
        print(PAYLOAD + json.dumps(data, ensure_ascii=False), flush=True)
    except Exception as exc:
        print(PAYLOAD + json.dumps({"error": type(exc).__name__, "reason": str(exc)}), flush=True)
        return 78
    finally:
        if report is not None:
            report()
    return 0


def safe_env(scratch):
    # Do not copy os.environ: secrets/provider settings never reach candidate.
    return {"PATH": os.defpath, "HOME": str(scratch / "home"), "XDG_CONFIG_HOME": str(scratch / "xdg"),
            "XDG_CACHE_HOME": str(scratch / "cache"), "TMPDIR": str(scratch),
            "NOVEL_PIPELINE_CONFIG_DIR": str(scratch / "config"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"}


def bounded_run(command, root, env, timeout):
    # Temp output files avoid unbounded memory capture; terminate the whole group.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            child = subprocess.Popen(command, cwd=root, env=env, stdout=out, stderr=err, start_new_session=True)
        except OSError as exc:
            raise HarnessError(f"child launch failed: {type(exc).__name__}") from exc
        try:
            code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise HarnessError(f"child exceeded {timeout}s") from exc
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        for stream in (out, err):
            if stream.tell() > 1024 * 1024:
                raise HarnessError("child output exceeded 1 MiB; CI also needs disk/resource quotas")
            stream.seek(0)
        try:
            return code, out.read().decode("utf-8"), err.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HarnessError("child output is not UTF-8") from exc


def records(text, prefix):
    return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]


def observation(stderr):
    found = records(stderr, OBSERVATION)
    if len(found) != 1:
        raise HarnessError("missing/duplicate external observer record")
    observed = found[0]
    if observed["probes"] != 4 or observed["network_attempts"] != 0 or observed["guard_active"] is not True:
        raise HarnessError("Python network guard inactive or candidate attempted network")
    return observed


def probe_process(root, python, mode, timeout):
    with tempfile.TemporaryDirectory(prefix="numeral-eval-probe-") as temporary:
        scratch = Path(temporary)
        code, out, err = bounded_run([str(python), "-I", "-B", str(Path(__file__).resolve()),
                                     "--worker", mode, "--candidate", str(root)],
                                    root, safe_env(scratch), timeout)
        observed = observation(err)
        data = records(out, PAYLOAD)
        if code != 0 or len(data) != 1 or "error" in data[0]:
            raise HarnessError(f"{mode} worker failed (exit {code}): " + str(data or err[-1500:]))
        return data[0], observed


def script_process(root, python, injection, timeout):
    with tempfile.TemporaryDirectory(prefix="numeral-eval-script-") as temporary:
        scratch = Path(temporary)
        bootstrap = scratch / "bootstrap"
        bootstrap.mkdir()
        # Trusted module loaded from the external grader, never candidate imports.
        (bootstrap / "sitecustomize.py").write_text(
            "import atexit, importlib.util, os\n"
            "try:\n"
            "    spec = importlib.util.spec_from_file_location('_trusted_numeral_grader', os.environ['EVAL_GRADER'])\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    spec.loader.exec_module(module)\n"
            "    atexit.register(module.install_guard(module.Path(os.environ['EVAL_VERIFY'])))\n"
            "except Exception:\n"
            "    os._exit(78)\n", encoding="utf-8")
        env = safe_env(scratch)
        env.update(PYTHONPATH=str(bootstrap), EVAL_GRADER=str(Path(__file__).resolve()),
                   EVAL_VERIFY=str(root / "verify.py"))
        sentinel = -987654319
        if injection:
            launcher = (
                "import sys\n"
                "try:\n"
                "    import runpy\n"
                "    sys.path.insert(0, sys.argv[1])\n"
                "    import chapters\n"
                "    original = chapters.chinese_to_int\n"
                f"    def convert(text):\n        return {sentinel} if text == '九十八' else original(text)\n"
                "    chapters.chinese_to_int = convert\n"
                "    target = sys.argv[1] + '/verify.py'\n"
                "    sys.argv = [target]\n"
                "except Exception:\n    sys.exit(78)\n"
                "try:\n    runpy.run_path(target, run_name='__main__')\n"
                "except Exception:\n    sys.exit(79)\n")
            compile(launcher, "<eval-launcher>", "exec")
            command = [str(python), "-B", "-c", launcher, str(root)]
        else:
            command = [str(python), "-B", str(root / "verify.py")]
        code, out, err = bounded_run(command, root, env, timeout)
        if code in (78, 79):
            raise HarnessError(f"script bootstrap/launcher failed (exit {code})")
        observed = observation(err)
        expected = 1 if injection else 0
        require(type(code) is int and code == expected, f"actual script exit {code}, expected {expected}")
        require(observed["main_calls"] == 1 and observed["main_returns"] ==
                [{"type": "int", "value": expected, "module": "__main__"}], "no real __main__ main()/int return witness")
        require(observed["checks"] == list(ORDER), "child did not run all four real checks in order")
        summary(out, 3 if injection else 4)
        diagnostics(out, {**EXPECTED, **({"九十八": sentinel} if injection else {})})
        require("All imports successful" in out and "Detected 3 chapters" in out and
                "Hard split test" in out and "Sentence-aware test" in out, "real smoke phase evidence missing")
        require("Traceback" not in err, "exit caused by uncaught/setup/unrelated exception")
        return {"path": "runpy.__main__" if injection else "direct_script", "exit": code,
                "observation": observed, "stdout": out, "stderr": err}


def regression_gate(root, python, old_verify, timeout):
    # Never let tests/verify from the real workspace be overwritten. The same
    # candidate tests run GREEN, then with only verify.py replaced by trusted bug.
    with tempfile.TemporaryDirectory(prefix="numeral-eval-regression-") as temporary:
        copy = Path(temporary) / "candidate"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns(".git"))
        before = candidate_tree(copy)
        green, seen = probe_process(copy, python, "regression", timeout)
        require(candidate_tree(copy) == before, "Agent tests changed files during GREEN replay")
        require(REQUIRED_TESTS <= {test.rsplit(".", 1)[-1] for test in green["ids"]},
                "missing approved plan T1–T10 regression method(s)")
        require(green["run"] > 0 and green["successful"] and green["failures"] == green["errors"] == 0,
                "candidate regression tests did not GREEN: " + green["output"][-4000:])
        require(green["skipped"] == green["expected_failures"] == green["unexpected_successes"] == 0,
                "skip/expectedFailure cannot substitute for regression evidence")
        for key, values in (("checker_returns", [("bool", True), ("bool", False)]),
                            ("main_returns", [("int", 0), ("int", 1)])):
            for kind, value in values:
                require(any(r["type"] == kind and r["value"] == value for r in seen[key]),
                        f"Agent tests lack real {key} {kind}/{value} coverage")
        (copy / "verify.py").write_text(old_verify, encoding="utf-8")
        red, red_seen = probe_process(copy, python, "regression", timeout)
        require(red["ids"] == green["ids"] and red["run"] == green["run"] and not red["successful"]
                and red["failures"] > 0 and red["errors"] == 0,
                "regression must FAIL assertions on original bug, not ERROR/no tests: " + red["output"][-4000:])
        require(red["skipped"] == red["expected_failures"] == red["unexpected_successes"] == 0,
                "baseline skips/expected failures are not RED evidence")
        require(any(re.search(r"^AssertionError: (?:True is not False|0 != 1|1 != 0|True != False|False != True)\b",
                              record["traceback"], re.M) for record in red["failure_records"]),
                "RED lacks Boolean/exit-signal assertion evidence (message-only RED rejected)")
        require(any(r["type"] == "bool" and r["value"] is True for r in red_seen["checker_returns"]),
                "RED did not observe buggy real checker")
        after = candidate_tree(copy)
        require(all(before.get(p) == after.get(p) for p in before.keys() | after.keys() if p != "verify.py"),
                "Agent tests changed regression copy files")
        return {"green": green, "red": red, "real_call_observations": seen,
                "red_is_posthoc_replay": True, "chronological_agent_red_green": "not proven by this grader"}


def grade(args):
    if os.name != "posix":
        raise HarnessError("first runner supports POSIX process groups only")
    root, trusted, grader = Path(args.candidate).absolute(), Path(args.trusted_repo).resolve(), Path(__file__).resolve()
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise HarnessError("candidate must be an existing absolute directory without symlink parents")
    if trusted.is_relative_to(root) or grader.is_relative_to(root):
        raise HarnessError("trusted mirror AND executed grader must be outside candidate")
    python = Path(args.python).absolute()  # Preserve venv symlink semantics.
    if not python.is_file() or python.is_relative_to(root):
        raise HarnessError("provide an existing external Python interpreter")
    baseline = baseline_tree(trusted)
    old_verify = run_git(trusted, "show", BASELINE + ":verify.py").decode("utf-8")
    old_install = run_git(trusted, "show", BASELINE + ":INSTALL.md").decode("utf-8")
    initial = candidate_tree(root)
    report = {"name": "numeral-smoke-check", "baseline": BASELINE, "candidate": str(root),
              "python": str(python), "grader_sha256": hashlib.sha256(grader.read_bytes()).hexdigest(),
              "candidate_tree_digest": hashlib.sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest(),
              "controller_command": sys.argv,
              "measurement": "candidate artifact; controller Agent-run receipt required", "checks": []}
    def gate(name, function):
        try:
            evidence = function()
            report["checks"].append({"id": name, "status": "PASS", "evidence": evidence})
        except (AssertionError, SyntaxError) as exc:
            report["checks"].append({"id": name, "status": "FAIL", "reason": str(exc)})
        except (HarnessError, ValueError, KeyError, OSError) as exc:
            report["checks"].append({"id": name, "status": "ERROR", "reason": str(exc)})
    gate("scope", lambda: scope_gate(initial, baseline))
    if report["checks"][-1]["status"] == "PASS":
        gate("preservation", lambda: structure_gate(root, old_verify))
    # Fail closed before executing an out-of-scope or structurally altered tree.
    if all(c["status"] == "PASS" for c in report["checks"]):
        def behavior():
            data, seen = probe_process(root, python, "behavior", args.timeout)
            for check in data["checks"]:
                require(check["status"] == "PASS", check["id"] + ": " + check.get("reason", ""))
            return {"results": data["checks"], "observation": seen}
        gate("behavior", behavior)
        gate("process_success", lambda: script_process(root, python, False, args.timeout))
        gate("process_mismatch", lambda: script_process(root, python, True, args.timeout))
        gate("regression", lambda: regression_gate(root, python, old_verify, args.regression_timeout))
        gate("documentation", lambda: documentation_gate(root, old_install))
        gate("no_runtime_file_changes", lambda: require(candidate_tree(root) == initial,
                                                       "candidate files changed during grading"))
    statuses = {c["status"] for c in report["checks"]}
    report["verdict"] = "ERROR" if "ERROR" in statuses else "FAIL" if "FAIL" in statuses else "PASS"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[report["verdict"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--trusted-repo")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--regression-timeout", type=int, default=120)
    parser.add_argument("--worker", choices=("behavior", "regression"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker, args.candidate)
    if not args.trusted_repo or min(args.timeout, args.regression_timeout) <= 0:
        parser.error("--trusted-repo and positive timeouts required")
    try:
        return grade(args)
    except (HarnessError, AssertionError, OSError, ValueError) as exc:
        print(json.dumps({"name": "numeral-smoke-check", "verdict": "ERROR", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

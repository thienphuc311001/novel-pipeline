#!/usr/bin/env python3
"""Run the frozen numeral-smoke-check task; Linux, Python stdlib, Bubblewrap.

Safe first run (no model/API calls):
    python -I -B evals/run_eval.py --dry-run --model sonnet
Live is a separate explicit operator action, never performed by --dry-run:
    python -I -B evals/run_eval.py --live --model FULL_MODEL_ID \
        --max-turns 20 --max-budget-usd 1 --agent-timeout 900

Live requires external Anthropic API authentication in the trusted CLI's env.
Live is currently BLOCKED: the requested current-repository CLAUDE.md/Skills/
Hooks profile has not been verified with this MCP-only execution architecture.
Dry-run PASS means infrastructure validation, not profile readiness or eval PASS.
The runner never opens .env/key/token/login files; dry-run does not inspect auth.
Only live passes ANTHROPIC_API_KEY to the trusted model client. The MCP server and
candidate code receive no credential value. CLI estimated budget can overshoot
and is NOT an absolute billing cap. No dependencies/containers are installed.

Security design: Claude is a trusted model transport outside the candidate
namespace, with built-in tools disabled. Only the frozen stdio MCP bridge's nine
tools are exposed. Candidate file tools validate paths/allowlist; candidate code
runs in Bubblewrap with network/PID/filesystem isolation and read-only source.
API transport is separate from candidate network access. No raw Bash, git write,
commit, push, deploy, external directories or arbitrary MCP servers are exposed.
Dry-run exercises those boundaries, including a host-only loopback listener.

Agent termination -> close tool phase under lock -> fresh frozen snapshot ->
grader in a separate namespace with read-only snapshot/oracle/grader. There is
no Agent-active grading phase. Existing grader limitations concerning hostile
Python introspection/forged observations remain; this runner does not rewrite
that grader or claim that OS isolation proves its semantic correctness.

All artifacts are in a new private directory outside every registered worktree.
The source repo/worktrees are only read. Reports retain NOT_RUN for dry-run;
live PASS requires both a successful CLI receipt and independent grader PASS.
Exit: 0=dry-run valid/live PASS; 1=live FAIL; 2=config/isolation/environment ERROR.
No GitHub Actions workflow or paid run is created automatically.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import importlib.util
import json
import math
import mmap
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

_bridge_spec = importlib.util.spec_from_file_location("_eval_sandbox_tools", Path(__file__).with_name("sandbox_tools.py"))
tools = importlib.util.module_from_spec(_bridge_spec)
_bridge_spec.loader.exec_module(tools)

BASELINE = "405c0251e2b5a06862cbf32f9acb9ebd53c11dee"
GRADER_SHA256 = "4fb8b0cd34f75f1b4b0e31f974e2d067d3aed366db15afc737d63525c5e291cb"
MANIFEST_SHA256 = "ab9c955a639b6f97961830e6eceb3135c2c29091039123b99a10b703d656cc3a"
DOCS = ("intent/verify-smoke-check/intent.md", "intent/verify-smoke-check/spec.md", "intent/verify-smoke-check/plan.md")
REQUIRED_FLAGS = ("--print", "--bare", "--restricted", "--tools", "--allowedTools", "--permission-mode",
                  "--permission-prompts", "--strict-mcp-config", "--mcp-config", "--setting-sources",
                  "--settings", "--disable-slash-commands", "--no-chrome", "--no-session-persistence",
                  "--output-format", "--model", "--max-budget-usd")


class RunnerError(RuntimeError):
    pass


def ensure(condition, message):
    if not condition:
        raise RunnerError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def git(repo, *args, input=None):
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C.UTF-8"}
    try:
        cp = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args], env=env,
                            input=input, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError("trusted local Git read/export failed") from exc
    ensure(cp.returncode == 0, "Git operation failed; check trusted repo/baseline")
    return cp.stdout


def tree_digest(root):
    entries = []
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            ensure(not (Path(directory) / name).is_symlink(), "symlink directory in candidate")
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            ensure(not tools.reject_secret_name(relative) and not path.is_symlink() and path.is_file(),
                   "unsafe candidate path; content not read")
            ensure(path.stat().st_size <= 32 * 1024**2, "candidate file exceeds scope limit")
            entries.append((relative, bool(path.stat().st_mode & 0o100), digest(path.read_bytes())))
    return digest(json.dumps(sorted(entries)).encode())


def cli_command(cli, model, turns, budget, mcp):
    return [str(cli), "--print", "--bare", "--restricted", "--tools", "",
            "--allowedTools", *("mcp__eval__" + t["name"] for t in tools.TOOLS),
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--strict-mcp-config", "--mcp-config", str(mcp), "--setting-sources", "",
            "--settings", '{"permissions":{"defaultMode":"dontAsk"}}',
            "--disable-slash-commands", "--no-chrome", "--no-session-persistence",
            "--output-format", "json", "--model", model,
            "--max-turns", str(turns), "--max-budget-usd", str(budget)]


def agent_configuration(source, baseline_export):
    """Inventory requested config separately from immutable task input.

    Settings filenames are inventoried without reading credential-bearing
    settings. No copying config into the prompt is called native Skills/Hooks
    loading. Enabling it needs a separately reviewed loader and boundary audit.
    """
    paths = [source / "CLAUDE.md", source / "AGENTS.md"]
    skills = source / ".claude/skills"
    if skills.is_dir():
        paths.extend(sorted(skills.rglob("SKILL.md")))
    files = {}
    for path in paths:
        ensure(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(source),
               "unsafe/missing current Agent configuration")
        ensure(path.stat().st_size <= tools.MAX_TEXT, "Agent configuration exceeds text bound")
        files[path.relative_to(source).as_posix()] = digest(path.read_bytes())
    settings = sorted(p.relative_to(source).as_posix() for p in (source / ".claude").glob("settings*.json"))
    return {"requested_profile": "current-repository CLAUDE.md/Skills/Hooks",
            "source_head": git(source, "rev-parse", "HEAD").decode().strip(),
            "current_files": files, "inventory_hash": digest(json.dumps({"files": files, "settings": settings}, sort_keys=True).encode()),
            "settings_files_not_opened": settings,
            "hooks": "no repository settings*.json found" if not settings else "not audited/loaded",
            "baseline_claude_hash": digest((baseline_export / "CLAUDE.md").read_bytes()),
            "executed_profile": "baseline documentation via explicit MCP Read; Skills/Hooks disabled",
            "verified_loaded": False, "live_eligible": False,
            "blockers": ["CURRENT_AGENT_CONFIG_NOT_LOADED", "CURRENT_PROFILE_BOUNDARIES_NOT_VERIFIED"]}


def validate_config(args):
    ensure(sys.platform == "linux" and sys.version_info >= (3, 11), "Linux and Python 3.11+ required")
    ensure(args.baseline == BASELINE, "baseline must equal the calibrated pinned commit")
    ensure(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,150}", args.model) is not None, "invalid model identifier")
    ensure(1 <= args.max_turns <= 100 and 1 <= args.agent_timeout <= 3600 and
           1 <= args.tool_timeout <= 120 and 1 <= args.grader_timeout <= 600, "invalid turn/timeout bounds")
    ensure(math.isfinite(args.max_budget_usd) and 0 < args.max_budget_usd <= 100, "budget must be finite, positive and <=100 USD")
    source = Path(args.repo).resolve()
    ensure(source.is_dir(), "trusted source repository missing")
    worktrees = [source]
    for line in git(source, "worktree", "list", "--porcelain").decode().splitlines():
        if line.startswith("worktree "):
            worktrees.append(Path(line[9:]).resolve())
    parent = Path(args.output_dir).resolve() if args.output_dir else Path(tempfile.gettempdir()).resolve()
    ensure(not any(parent.is_relative_to(p) for p in worktrees), "artifact directory must be outside all worktrees")
    ensure(not parent.exists() or parent.is_dir(), "artifact parent is not a directory")
    return source, parent, worktrees


def export_baseline(source, baseline, root):
    ensure(git(source, "rev-parse", "--verify", baseline + "^{commit}").decode().strip() == baseline,
           "baseline commit absent or not exact")
    objects = {baseline}
    for record in git(source, "ls-tree", "-rtz", baseline).split(b"\0"):
        if not record:
            continue
        meta, relative = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        relative = relative.decode("utf-8")
        ensure(not tools.reject_secret_name(relative), "secret/control path in baseline; export refused without reading contents")
        ensure(mode in ("040000", "100644", "100755") and kind in ("tree", "blob"), "unsupported baseline symlink/submodule")
        objects.add(oid)
    objects.add(git(source, "rev-parse", baseline + "^{tree}").decode().strip())
    archive = git(source, "archive", "--format=tar", baseline)
    ensure(len(archive) <= 128 * 1024**2, "baseline export too large")
    root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        for member in tf.getmembers():
            item = Path(member.name)
            ensure((member.isfile() or member.isdir()) and not item.is_absolute() and ".." not in item.parts and
                   not tools.reject_secret_name(item), "unsafe tar member")
            # Python 3.11-compatible explicit extraction; no links/devices and no
            # tar ownership/absolute paths. Avoid relying on 3.12's filter API.
            target = root / item
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tf.extractfile(member).read())
                os.chmod(target, 0o755 if member.mode & 0o100 else 0o644)
    for relative in DOCS:
        content = (root / relative).read_text(encoding="utf-8")
        ensure(re.search(r"^\*\*Status:\*\*\s*Approved\b", content, re.M), relative + " is not Approved")
    return objects


def freeze_oracle(source, objects, destination):
    # Copy only objects needed for this commit/tree; no remote config, credentials,
    # source .git path, hooks, hardlinks or unrelated history are shared.
    destination.mkdir()
    git(destination, "init", "--bare", "--quiet", "--template=")
    packed = git(source, "pack-objects", "--stdout", input=("\n".join(sorted(objects)) + "\n").encode())
    git(destination, "index-pack", "--stdin", input=packed)
    ensure(git(destination, "rev-parse", "--verify", BASELINE + "^{commit}").decode().strip() == BASELINE,
           "frozen oracle missing baseline")


def sandbox_probe(bwrap, candidate, python, controller, forbidden):
    before = tree_digest(candidate)
    sentinel = controller / "host-only-sentinel.txt"
    sentinel.write_text("SYNTHETIC ISOLATION SENTINEL", encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        source = r'''
import errno,json,os,socket,importlib.util
from pathlib import Path
checks={}
checks['net_namespace_differs']=os.readlink('/proc/self/ns/net') != HOST_NET
checks['pid_namespace_differs']=os.readlink('/proc/self/ns/pid') != HOST_PID
checks['no_credentials_in_env']=not any(k in os.environ for k in ('ANTHROPIC_API_KEY','AWS_SECRET_ACCESS_KEY','OPENAI_API_KEY'))
try:
    __import__('PIL.Image')
    checks['pillow_importable']=True
except ImportError:
    checks['pillow_importable']=False
checks['host_paths_hidden']=all(not Path(p).exists() for p in FORBIDDEN)
checks['controller_hidden']=not Path('/controller/numeral_smoke_check.py').exists() and not Path('/controller/oracle.git').exists()
try:
    Path('/candidate/__sandbox_write_probe__').write_text('synthetic')
    checks['candidate_read_only']=False
except OSError as e:
    checks['candidate_read_only']=e.errno==errno.EROFS
try:
    socket.create_connection(('127.0.0.1',PORT),timeout=1).close()
    checks['host_loopback_blocked']=False
except OSError:
    checks['host_loopback_blocked']=True
try:
    socket.create_connection(('192.0.2.1',443),timeout=1).close()
    checks['egress_unroutable']=False
except OSError as e:
    checks['egress_unroutable']=e.errno in (errno.ENETUNREACH,errno.EHOSTUNREACH)
try:
    socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_RAW).close()
    checks['raw_socket_denied']=False
except PermissionError:
    checks['raw_socket_denied']=True
print(json.dumps({'checks':checks,'python':__import__('sys').version.split()[0],
                  'pytest_available':importlib.util.find_spec('pytest') is not None}))
'''
        prefix = "HOST_NET=" + repr(os.readlink("/proc/self/ns/net")) + "\nHOST_PID=" + repr(os.readlink("/proc/self/ns/pid"))
        prefix += "\nFORBIDDEN=" + repr([str(sentinel), *(str(p) for p in forbidden), str(Path.home()),
                                       f"/proc/{os.getpid()}/environ"])
        prefix += "\nPORT=" + str(port) + "\n"
        result = tools.run_bounded(tools.sandbox_command(bwrap, candidate, python,
                                   ["{python}", "-I", "-B", "-c", prefix + source]), 15)
    ensure(result["exit_status"] == 0 and not result["timed_out"], "sandbox probe could not start: " + result["stderr"][:300])
    evidence = json.loads(result["stdout"])
    ensure(evidence["checks"] and all(v is True for v in evidence["checks"].values()), "sandbox isolation probe failed")
    ensure(tree_digest(candidate) == before, "sandbox modified candidate during preflight")
    return evidence


def inspect_cli(cli, bwrap, candidate, python, audit_file, bridge_file):
    ensure(cli.is_file() and os.access(cli, os.X_OK), "Claude CLI missing/not executable")
    mounts = [(cli, "/runtime/claude")]
    def offline(arguments):
        return tools.run_bounded(tools.sandbox_command(bwrap, candidate, python,
                                 ["/runtime/claude", *arguments], mounts), 25, address_space=False)
    version = offline(["--version"])
    help_result = offline(["--help"])
    ensure(version["exit_status"] == help_result["exit_status"] == 0, "Claude CLI version/help failed in isolated preflight")
    help_text = help_result["stdout"]
    ensure(all(flag in help_text for flag in REQUIRED_FLAGS), "Claude CLI lacks required permission/non-interactive flags")
    # Hidden --max-turns exists in this installed native CLI. Help by itself
    # does not validate flags; use a real parser with EOF/no prompt, offline.
    with cli.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        ensure(data.find(b"--max-turns <") >= 0, "cannot substantiate hidden --max-turns in installed CLI")
    command = cli_command(Path("/runtime/claude"), "sonnet", 1, 0.01, '{"mcpServers":{}}')
    parser_probe = offline(command[1:])
    combined = parser_probe["stdout"] + parser_probe["stderr"]
    ensure(not parser_probe["timed_out"] and parser_probe["exit_status"] != 0 and
           "Input must be provided" in combined and "unknown option" not in combined.lower(),
           "offline CLI parser verification inconclusive: " + combined[:500])
    negative = offline(["--eval-runner-invalid-option"])
    ensure(negative["exit_status"] != 0 and "unknown option" in (negative["stderr"] + negative["stdout"]).lower(),
           "CLI parser negative control failed")
    audit = tools.run_bounded(tools.sandbox_command(bwrap, candidate, python,
        ["{python}", "-I", "-B", "/runtime/audit_cli.py"],
        [*mounts, (audit_file, "/runtime/audit_cli.py"), (bridge_file, "/runtime/sandbox_tools.py")]),
        60, address_space=False)
    ensure(audit["exit_status"] == 0 and not audit["timed_out"] and not audit["output_truncated"],
           "offline CLI dispatcher audit failed; no real API/model used")
    dispatcher = json.loads(audit["stdout"])
    ensure(dispatcher["checks"] and all(v is True for v in dispatcher["checks"].values()),
           "actual CLI registry/dispatcher boundary failed")
    return {"version": version["stdout"].strip(), "binary_sha256": digest(cli.read_bytes()),
            "flags_supported": [*REQUIRED_FLAGS, "--max-turns"], "parser_probe": "EOF/no prompt; offline; no model called",
            "offline_dispatcher": dispatcher,
            "help": help_text}


def grading_mounts(controller):
    # Do not expose CLI logs, CLI HOME, MCP config or model receipt to candidate
    # code during grading. These two inputs exist only in the grading phase.
    return [(controller / "numeral_smoke_check.py", "/controller/numeral_smoke_check.py"),
            (controller / "oracle.git", "/controller/oracle.git")]


def probe_grading_mounts(bwrap, candidate, python, controller):
    program = r'''
import errno,hashlib,json,os,subprocess
from pathlib import Path
checks={}
for name,path in [('grader','/controller/numeral_smoke_check.py'),('oracle','/controller/oracle.git/config'),
                  ('candidate','/candidate/verify.py')]:
    try:
        fd=os.open(path,os.O_WRONLY)
        os.close(fd)
        checks[name+'_read_only']=False
    except OSError as exc:
        checks[name+'_read_only']=exc.errno==errno.EROFS
checks['private_artifacts_hidden']=not Path('/controller/mcp.json').exists() and not Path('/controller/cli-home').exists()
p=subprocess.run(['git','--no-replace-objects','-C','/controller/oracle.git','rev-parse','--verify',EXPECTED+'^{commit}'],capture_output=True,text=True)
checks['oracle_resolves_pinned_commit']=p.returncode==0 and p.stdout.strip()==EXPECTED
checks['grader_digest_matches']=hashlib.sha256(Path('/controller/numeral_smoke_check.py').read_bytes()).hexdigest()==GRADER_HASH
print(json.dumps(checks))
'''
    prefix = "EXPECTED=" + repr(BASELINE) + "\nGRADER_HASH=" + repr(GRADER_SHA256) + "\n"
    result = tools.run_bounded(tools.sandbox_command(bwrap, candidate, python,
        ["{python}", "-I", "-B", "-c", prefix + program], grading_mounts(controller)), 15)
    ensure(result["exit_status"] == 0 and not result["timed_out"], "grading namespace preflight failed")
    checks = json.loads(result["stdout"])
    ensure(checks and all(value is True for value in checks.values()), "grading inputs are not isolated/read-only")
    return checks


def probe_bridge(bridge_file, bridge_config, controller):
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "dry-run", "version": "1"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "Read", "arguments": {"path": "../controller/numeral_smoke_check.py"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "Write", "arguments": {"path": "chapters/numerals.py", "content": "forbidden"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "RunTests", "arguments": {"tests": []}}},
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "Bash", "arguments": {"command": "git commit"}}},
    ]
    env = {"PATH": os.defpath, "HOME": str(controller / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
    cp = subprocess.run([sys.executable, "-I", "-B", str(bridge_file), "--config", str(bridge_config)],
                        input="".join(json.dumps(m) + "\n" for m in messages), capture_output=True,
                        text=True, encoding="utf-8", env=env, timeout=20)
    ensure(cp.returncode == 0, "stdio MCP bridge self-check failed")
    responses = [json.loads(line) for line in cp.stdout.splitlines()]
    ensure(len(responses) == len(messages), "MCP bridge response count mismatch")
    names = [t["name"] for t in responses[1]["result"]["tools"]]
    ensure(names == [t["name"] for t in tools.TOOLS] and all(r["result"]["isError"] is True for r in responses[2:]),
           "MCP tool whitelist/path/write/test/commit boundary failed")
    return {"tools": names, "path_escape_denied": True, "non_allowlisted_write_denied": True,
            "full_suite_denied": True, "shell_commit_denied": True, "stdio_protocol": "2025-06-18"}


def close_phase(controller):
    with (controller / "phase.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        save_json(controller / "phase.json", {"phase": "closed"})


def overall_verdict(agent, grader_verdict):
    if grader_verdict == "ERROR":
        return "ERROR"
    if agent["transport_success"]:
        return grader_verdict
    if agent.get("timed_out") or agent.get("subtype") in ("error_max_turns", "error_max_budget_usd"):
        return "FAIL"  # Task not completed within the explicitly configured limits.
    return "ERROR"  # Invalid receipt/authentication/transport is not task-quality evidence.


def run_agent(command, prompt, candidate, controller, timeout):
    # Authentication is inspected/passed ONLY after the operator explicitly
    # selected --live and all isolation probes passed. Never log values.
    ensure("ANTHROPIC_API_KEY" in os.environ, "live requires externally supplied Anthropic API authentication")
    env = {"PATH": os.defpath, "HOME": str(controller / "cli-home"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1"}
    (controller / "cli-home").mkdir()
    output, errors = controller / "agent.stdout.json", controller / "agent.stderr.txt"
    started = time.monotonic()
    with output.open("wb") as out, errors.open("wb") as err:
        process = subprocess.Popen(command, cwd=candidate, env=env, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                   start_new_session=True)
        timed_out = False
        try:
            save_json(controller / "agent-started.json", {"started": True, "pid": process.pid})
            process.communicate(input=prompt.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            close_phase(controller)
    receipt = None
    if output.stat().st_size <= 4 * 1024**2:
        try:
            receipt = json.loads(output.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            pass
    success = (process.returncode == 0 and not timed_out and isinstance(receipt, dict) and
               receipt.get("type") == "result" and receipt.get("subtype") == "success" and receipt.get("is_error") is False)
    cost = receipt.get("total_cost_usd") if isinstance(receipt, dict) else None
    if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        cost = None
    return {"exit_status": process.returncode, "timed_out": timed_out, "seconds": round(time.monotonic() - started, 3),
            "transport_success": success, "subtype": receipt.get("subtype") if isinstance(receipt, dict) else None,
            "cost_estimate_usd": cost, "cost_is_estimate_not_bill": True,
            "model_usage": receipt.get("modelUsage") if isinstance(receipt, dict) else None,
            "stdout_path": str(output), "stderr_path": str(errors)}


def execute(args):
    started = time.monotonic()
    run_root, report_path = None, None
    report = {"mode": "live" if args.live else "dry-run", "name": "numeral-smoke-check", "verdict": "NOT_RUN",
              "stage": "CONFIG",
              "model": args.model, "baseline_commit": args.baseline, "cli_version": None,
              "prompt_hash": None, "grader_hash": None, "agent_exit_status": None, "grader_exit_status": None,
              "cost_estimate_usd": None, "cost_limit_is_estimate_not_absolute_billing_cap": True,
              "started_at": datetime.now(timezone.utc).isoformat(), "artifact_paths": {},
              "limits": {"agent_seconds": args.agent_timeout, "tool_seconds": args.tool_timeout,
                         "grader_seconds": args.grader_timeout, "max_turns": args.max_turns, "max_budget_usd": args.max_budget_usd}}
    try:
        source, parent, worktrees = validate_config(args)
        parent.mkdir(parents=True, exist_ok=True)
        run_root = parent / ("numeral-eval-" + uuid.uuid4().hex)
        run_root.mkdir(mode=0o700)
        controller = run_root / "controller"
        controller.mkdir(mode=0o700)
        report_path = controller / "report.json"
        report["artifact_paths"] = {"run_root": str(run_root), "report": str(report_path), "controller": str(controller)}
        root = Path(__file__).resolve().parent
        report["stage"] = "FROZEN_INPUTS"
        manifest_file, grader_file = root / "numeral-smoke-check.json", root / "graders/numeral_smoke_check.py"
        manifest_bytes, grader_bytes = manifest_file.read_bytes(), grader_file.read_bytes()
        manifest = json.loads(manifest_bytes)
        ensure(set(manifest) == {"name", "source", "from", "prompt", "may_change", "checks"} and
               manifest["name"] == report["name"] and manifest["from"] == BASELINE and
               set(manifest["may_change"]) == tools.ALLOWLIST and isinstance(manifest["prompt"], str), "invalid eval manifest contract")
        ensure(digest(manifest_bytes) == MANIFEST_SHA256, "manifest differs from calibrated digest; separate review required")
        ensure(digest(grader_bytes) == GRADER_SHA256, "grader differs from calibrated digest; separate review required")
        compile(grader_bytes, str(grader_file), "exec")
        ast.parse(grader_bytes)
        report.update(manifest_hash=digest(manifest_bytes), grader_hash=digest(grader_bytes))
        frozen_grader = controller / "numeral_smoke_check.py"
        frozen_grader.write_bytes(grader_bytes)
        (controller / "manifest.json").write_bytes(manifest_bytes)
        bridge_file = controller / "sandbox_tools.py"
        bridge_file.write_bytes((root / "sandbox_tools.py").read_bytes())
        audit_file = controller / "audit_cli.py"
        audit_file.write_bytes((root / "audit_cli.py").read_bytes())
        report["cli_audit_hash"] = digest(audit_file.read_bytes())
        report["bridge_hash"] = digest(bridge_file.read_bytes())
        baseline_export = run_root / "baseline"
        report["stage"] = "BASELINE_EXPORT"
        objects = export_baseline(source, BASELINE, baseline_export)
        candidate = run_root / "candidate"
        shutil.copytree(baseline_export, candidate)
        initial = tree_digest(candidate)
        ensure(initial == tree_digest(baseline_export), "candidate is not an exact baseline export")
        oracle = controller / "oracle.git"
        freeze_oracle(source, objects, oracle)
        report["baseline_tree_digest"] = initial
        report["approved_documents"] = {p: digest((baseline_export / p).read_bytes()) for p in DOCS}
        report["agent_configuration"] = agent_configuration(source, baseline_export)
        report["current_document_status"] = {}
        for relative in DOCS:
            status = re.search(r"^\*\*Status:\*\*\s*(Approved|Draft)\b", (source / relative).read_text(encoding="utf-8"), re.M)
            report["current_document_status"][relative] = status.group(1) if status else "UNVERIFIED"
        python = Path(args.python).absolute()
        report["stage"] = "SANDBOX"
        bwrap = Path(args.bwrap or shutil.which("bwrap") or "/missing/bwrap").resolve()
        ensure(bwrap.is_file() and os.access(bwrap, os.X_OK), "Bubblewrap sandbox missing/not executable; live refused")
        ensure(python.is_file() and os.access(python, os.X_OK), "external Python missing/not executable")
        cli = Path(args.claude or shutil.which("claude") or "/missing/claude").resolve()
        ensure(not cli.is_relative_to(candidate) and not python.is_relative_to(candidate), "CLI/interpreter cannot be candidate-controlled")
        report["sandbox"] = sandbox_probe(bwrap, candidate, python, controller, [*worktrees, frozen_grader, oracle])
        report["grading_boundary"] = probe_grading_mounts(bwrap, candidate, python, controller)
        report["stage"] = "CLI_AUDIT"
        cli_info = inspect_cli(cli, bwrap, candidate, python, audit_file, bridge_file)
        (controller / "claude-help.txt").write_text(cli_info.pop("help"), encoding="utf-8")
        report["cli"] = cli_info
        report["cli_version"] = cli_info["version"]
        config = {"candidate": str(candidate), "baseline_export": str(baseline_export), "controller": str(controller),
                  "baseline_commit": BASELINE, "python": str(python), "bwrap": str(bwrap), "tool_timeout": args.tool_timeout,
                  "audit_role": "preflight",
                  "python_in_sandbox": str(python) if python.is_relative_to(Path('/usr')) else '/runtime/venv/bin/' + python.name}
        bridge_config = controller / "bridge-config.json"
        save_json(bridge_config, config)
        save_json(controller / "phase.json", {"phase": "agent"})
        report["stage"] = "MCP_BRIDGE"
        report["tool_boundary"] = probe_bridge(bridge_file, bridge_config, controller)
        config["audit_role"] = "agent"
        save_json(bridge_config, config)
        ensure(tree_digest(candidate) == initial, "dry-run tools mutated candidate")
        mcp = controller / "mcp.json"
        save_json(mcp, {"mcpServers": {"eval": {"command": sys.executable,
            "args": ["-I", "-B", str(bridge_file), "--config", str(bridge_config)],
            "env": {"ANTHROPIC_API_KEY": "", "PYTHONDONTWRITEBYTECODE": "1"}}}})
        effective_prompt = manifest["prompt"] + "\n\nRunner execution contract: This is an exact exported baseline, without .git. "
        effective_prompt += ("Use only the eval MCP tools. WorkspaceInfo supplies baseline identity; Diff replaces git diff. "
            "Read CLAUDE.md and the approved documents explicitly (bare mode skips auto-discovery). "
            "Write/Edit can change only the three authorized files. RunTests executes selected unittest IDs or the approved pytest subset; "
            "RunSmoke runs verify.py. The interpreter and config are already isolated by those tools. "
            "No arbitrary shell or Python -c is exposed; put regression helpers in the authorized test file. "
            "Tools preserve runtime observations outside candidate. Do not create logs/artifacts inside candidate. No commit/push/deploy.")
        report["prompt_hash"] = digest(effective_prompt.encode("utf-8"))
        report["manifest_prompt_hash"] = digest(manifest["prompt"].encode("utf-8"))
        (controller / "prompt.txt").write_text(effective_prompt, encoding="utf-8")
        command = cli_command(cli, args.model, args.max_turns, args.max_budget_usd, mcp)
        grader_command = tools.sandbox_command(bwrap, candidate, python,
            ["{python}", "-I", "-B", "/controller/numeral_smoke_check.py", "--trusted-repo", "/controller/oracle.git",
             "--candidate", "/candidate", "--python", "{python}"], grading_mounts(controller))
        report["commands"] = {"agent": command, "agent_prompt_source": "stdin from frozen prompt.txt", "grader": grader_command}
        report["artifact_paths"].update(candidate=str(candidate), baseline=str(baseline_export), oracle=str(oracle),
            grader=str(frozen_grader), prompt=str(controller / "prompt.txt"), mcp_config=str(mcp))
        report["remaining_validation"] = ["No paid/end-to-end Claude session validated by dry-run",
            "Current CLAUDE.md/Skills/Hooks loading and boundaries not verified; Live blocked",
            "Operator must select available full model ID and external API authentication before live",
            "CLI budget is an estimate; CI/job/billing controls remain external",
            "Existing grader is not a proof against adversarial Python introspection; documentation still needs semantic review"]
        ensure(digest(frozen_grader.read_bytes()) == GRADER_SHA256 and digest(bridge_file.read_bytes()) == report["bridge_hash"],
               "frozen grader/bridge changed during preflight")
        if not args.live:
            report["stage"] = "DRY_RUN_COMPLETE"
            close_phase(controller)
            report["dry_run_status"] = "PASS"
            report["model_called"] = False
            report["grader_called"] = False
            report["live_readiness"] = "BLOCKED: current Agent configuration loading not verified; no authentication/model availability inspected"
            result_code = 0
        else:
            report["stage"] = "LIVE_READINESS_GATE"
            # Fail closed BEFORE inspecting or passing any API credential.
            # No operator/env flag bypasses this missing loading evidence.
            ensure(report["agent_configuration"]["live_eligible"] is True,
                   "Live blocked: current repository CLAUDE.md/Skills/Hooks loading and boundaries not verified")
            ensure(args.model not in ("sonnet", "opus", "haiku", "fable"), "live requires an explicit full model ID, not a moving alias")
            ensure(digest(cli.read_bytes()) == cli_info["binary_sha256"], "CLI binary changed since preflight")
            report["stage"] = "AGENT"
            report["agent"] = run_agent(command, effective_prompt, candidate, controller, args.agent_timeout)
            report["model_invocation_attempted"] = True
            report["agent_exit_status"] = report["agent"]["exit_status"]
            report["cost_estimate_usd"] = report["agent"]["cost_estimate_usd"]
            snapshot = run_root / "frozen-candidate"
            shutil.copytree(candidate, snapshot)
            frozen_digest = tree_digest(snapshot)
            ensure(tree_digest(candidate) == frozen_digest, "candidate changed while freezing")
            ensure(digest(frozen_grader.read_bytes()) == GRADER_SHA256 and digest(bridge_file.read_bytes()) == report["bridge_hash"],
                   "grader/bridge integrity changed; refuse scoring")
            # Only the snapshot enters this namespace. No active Agent/MCP phase.
            grader_command = tools.sandbox_command(bwrap, snapshot, python,
                ["{python}", "-I", "-B", "/controller/numeral_smoke_check.py", "--trusted-repo", "/controller/oracle.git",
                 "--candidate", "/candidate", "--python", "{python}"], grading_mounts(controller))
            report["commands"]["grader"] = grader_command
            # Regression replay copies baseline fonts (largest ~27 MiB). Keep
            # the original grader intact; permit its bounded <=32 MiB files.
            report["stage"] = "GRADER"
            scored = tools.run_bounded(grader_command, args.grader_timeout, file_size=32 * 1024**2)
            (controller / "grader.stdout.json").write_text(scored["stdout"], encoding="utf-8")
            (controller / "grader.stderr.txt").write_text(scored["stderr"], encoding="utf-8")
            report["grader_exit_status"] = scored["exit_status"]
            report["grader_timed_out"] = scored["timed_out"]
            ensure(not scored["timed_out"], "grader deadline exceeded")
            ensure(not scored["output_truncated"], "grader output exceeded capture bound")
            verdict = json.loads(scored["stdout"])
            ensure(verdict.get("verdict") in ("PASS", "FAIL", "ERROR") and scored["exit_status"] ==
                   {"PASS": 0, "FAIL": 1, "ERROR": 2}[verdict["verdict"]], "grader output/exit contract invalid")
            ensure(tree_digest(snapshot) == frozen_digest and digest(frozen_grader.read_bytes()) == GRADER_SHA256,
                   "frozen candidate/grader mutated during scoring")
            report["grader_verdict"] = verdict["verdict"]
            report["artifact_paths"].update(frozen_candidate=str(snapshot), grader_report=str(controller / "grader.stdout.json"),
                                             agent_output=report["agent"]["stdout_path"], agent_errors=report["agent"]["stderr_path"])
            report["verdict"] = overall_verdict(report["agent"], verdict["verdict"])
            report["stage"] = "LIVE_COMPLETE"
            result_code = {"PASS": 0, "FAIL": 1, "ERROR": 2}[report["verdict"]]
    except (RunnerError, OSError, ValueError, KeyError, SyntaxError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        attempted = run_root is not None and (run_root / 'controller/agent-started.json').exists()
        report.update(verdict="ERROR", reason=str(exc) or type(exc).__name__, model_invocation_attempted=attempted)
        if not attempted:
            report["model_called"] = False
        result_code = 2
    finally:
        if run_root is not None and (run_root / "controller/phase.json").exists():
            close_phase(run_root / "controller")
        report["seconds"] = round(time.monotonic() - started, 3)
        if report_path:
            save_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return result_code


def main():
    # External CI timeout must unwind run_agent/run_bounded cleanup, rather
    # than orphaning the authenticated CLI in its separate process group.
    def terminated(signum, frame):
        raise KeyboardInterrupt("controller terminated by external timeout")
    signal.signal(signal.SIGTERM, terminated)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--model", default="sonnet", help="dry-run may use alias; live requires full model ID")
    parser.add_argument("--claude", help="explicit trusted CLI executable")
    parser.add_argument("--bwrap", help="explicit Bubblewrap executable; no insecure fallback")
    parser.add_argument("--python", default=sys.executable, help="existing external /usr Python or POSIX venv")
    parser.add_argument("--output-dir", help="external artifact parent; defaults to system temp; keeps reports")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-budget-usd", type=float, default=1)
    parser.add_argument("--agent-timeout", type=int, default=900)
    parser.add_argument("--tool-timeout", type=int, default=30)
    parser.add_argument("--grader-timeout", type=int, default=300)
    return execute(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())

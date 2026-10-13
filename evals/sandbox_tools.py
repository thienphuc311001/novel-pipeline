"""Private stdio MCP bridge for run_eval.py; never install in the candidate.

The model has no built-in file/shell/network tools. This trusted bridge exposes
bounded candidate-only operations. Executable candidate code runs with a
read-only candidate in a fresh Bubblewrap filesystem/PID/network namespace.
Only this bridge can write the three allowlisted files, through Write/Edit.
The authenticated Claude client is a separate trusted model transport; its
credentials and network are never passed to candidate execution. This is Linux
isolation for evals, not a claim of protection against kernel vulnerabilities.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import time

ALLOWLIST = frozenset(("verify.py", "tests/test_verify.py", "INSTALL.md"))
MODULES = ("tests.test_verify", "tests.test_chapter_clock_lines", "tests.test_headless_service")
PYTEST_FILES = ("tests/test_verify.py", "tests/test_chapter_normalization.py",
                "tests/test_chapter_clock_lines.py", "tests/test_headless_service.py")
MAX_TEXT = 256 * 1024
MAX_MESSAGE = 1024 * 1024


def reject_secret_name(path):
    return any(p == ".env" or p.startswith(".env.") or p in (
        ".git", "id_rsa", "id_ed25519", "credentials.json", "token.json", "tokens.json") or
        (p.startswith("client_secret") and p.endswith(".json")) for p in Path(path).parts)


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("provide a nonempty relative candidate path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or reject_secret_name(path):
        raise ValueError("path outside the candidate policy")
    item = root / path
    for parent in (item, *item.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlinks are not accessible")
    if not item.resolve().is_relative_to(root):
        raise ValueError("path escapes candidate")
    return item


def read_text(path):
    if not path.is_file() or path.stat().st_size > MAX_TEXT:
        raise ValueError("not a bounded text file")
    data = path.read_bytes()
    if b"\0" in data:
        raise ValueError("binary files are not exposed")
    return data.decode("utf-8")


def sandbox_command(bwrap, candidate, python, command, mounts=()):
    """No host /home, /tmp, /etc, /run, /sys or host /proc is mounted."""
    if sys.platform != "linux":
        raise ValueError("Bubblewrap backend requires Linux")
    result = [str(bwrap), "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
              "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
              "--dir", "/home", "--dir", "/home/eval", "--dir", "/runtime", "--dir", "/controller",
              "--ro-bind", str(candidate), "/candidate"]
    # Keep the host distro's public runtime aliases, not host private files.
    for directory in ("bin", "sbin", "lib", "lib64"):
        host = Path("/") / directory
        if host.is_symlink():
            result += ["--symlink", os.readlink(host), "/" + directory]
        elif host.is_dir():
            result += ["--ro-bind", str(host), "/" + directory]
    python = Path(python).absolute()  # Preserve a venv's invocation path.
    if python.is_relative_to(Path("/usr")):
        sandbox_python = str(python)
    elif python.parent.name == "bin" and (python.parent.parent / "pyvenv.cfg").is_file():
        result += ["--ro-bind", str(python.parent.parent), "/runtime/venv"]
        sandbox_python = "/runtime/venv/bin/" + python.name
    else:
        raise ValueError("Python must be under /usr or in an explicit POSIX venv")
    for source, destination in mounts:
        result += ["--ro-bind", str(source), str(destination)]
    result += ["--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/home/eval",
               "--setenv", "XDG_CONFIG_HOME", "/tmp/xdg", "--setenv", "XDG_CACHE_HOME", "/tmp/cache",
               "--setenv", "NOVEL_PIPELINE_CONFIG_DIR", "/tmp/config", "--setenv", "TMPDIR", "/tmp",
               "--setenv", "LANG", "C.UTF-8", "--setenv", "LC_ALL", "C.UTF-8",
               "--setenv", "PYTHONUTF8", "1", "--setenv", "PYTHONIOENCODING", "utf-8",
               "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "PYTHONNOUSERSITE", "1",
               "--setenv", "QT_QPA_PLATFORM", "offscreen", "--chdir", "/candidate", "--"]
    return result + [sandbox_python if item == "{python}" else str(item) for item in command]


def limits(address_space=True, file_size=4 * 1024 * 1024):
    # Bounded logs, memory and fork count; external CI still supplies job quotas.
    def set_limit(kind, desired):
        hard = resource.getrlimit(kind)[1]
        value = desired if hard == resource.RLIM_INFINITY else min(hard, desired)
        resource.setrlimit(kind, (value, value))
    set_limit(resource.RLIMIT_FSIZE, file_size)
    if address_space:
        set_limit(resource.RLIMIT_AS, 2 * 1024**3)
    # RLIMIT_NPROC counts the real user's existing host threads too. A tiny
    # value rejects namespace creation on desktop hosts before eval starts.
    set_limit(resource.RLIMIT_NPROC, 4096)
    set_limit(resource.RLIMIT_NOFILE, 256)


def run_bounded(command, timeout, *, stdin=None, address_space=True, file_size=4 * 1024 * 1024):
    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(command, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=out, stderr=err, start_new_session=True,
                                   preexec_fn=lambda: limits(address_space, file_size))
        timed_out = False
        try:
            process.communicate(input=stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        truncated = out.tell() > MAX_MESSAGE or err.tell() > MAX_MESSAGE
        out.seek(0)
        err.seek(0)
        return {"exit_status": process.returncode, "timed_out": timed_out,
                "output_truncated": truncated,
                "seconds": round(time.monotonic() - started, 3),
                "stdout": out.read(MAX_MESSAGE).decode("utf-8", errors="replace"),
                "stderr": err.read(MAX_MESSAGE).decode("utf-8", errors="replace")}


def schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


STRING = {"type": "string"}
TOOLS = [
    {"name": "WorkspaceInfo", "description": "Baseline identity, scope and runtime of this exported candidate; no Git operations.", "inputSchema": schema()},
    {"name": "Read", "description": "Read a bounded UTF-8 file inside candidate using a relative path.",
     "inputSchema": schema({"path": STRING, "offset": {"type": "integer", "minimum": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, ("path",))},
    {"name": "Glob", "description": "List candidate paths matching a glob; never follows symlinks or secret paths.", "inputSchema": schema({"pattern": STRING})},
    {"name": "Grep", "description": "Literal string search in bounded candidate text files; no arbitrary regex execution.", "inputSchema": schema({"query": STRING, "pattern": STRING}, ("query",))},
    {"name": "Write", "description": "Write UTF-8 text to exactly one of the three authorized product files.", "inputSchema": schema({"path": STRING, "content": STRING}, ("path", "content"))},
    {"name": "Edit", "description": "Replace exactly one literal occurrence in an allowlisted file.", "inputSchema": schema({"path": STRING, "old": STRING, "new": STRING}, ("path", "old", "new"))},
    {"name": "Diff", "description": "Review changes in the three authorized files against exported baseline.", "inputSchema": schema()},
    {"name": "RunTests", "description": "Run selected unittest IDs or a bounded pytest subset offline in Bubblewrap. No shell; no discovery/full suite.",
     "inputSchema": schema({"tests": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 30}, "runner": {"enum": ["unittest", "pytest"]}}, ("tests",))},
    {"name": "RunSmoke", "description": "Execute real verify.py offline with read-only candidate and isolated scratch.", "inputSchema": schema()},
]


class Bridge:
    def __init__(self, config):
        self.root = Path(config["candidate"]).resolve()
        self.baseline = Path(config["baseline_export"]).resolve()
        self.controller = Path(config["controller"]).resolve()
        self.config = config
        previous = [int(p.stem[5:]) for p in self.controller.glob("tool-*.json") if p.stem[5:].isdigit()]
        self.sequence = max(previous, default=0)

    def files(self, pattern):
        if not isinstance(pattern, str) or ".." in Path(pattern).parts or pattern.startswith("/"):
            raise ValueError("use a relative glob")
        found = []
        for directory, directories, files in os.walk(self.root, followlinks=False):
            here = Path(directory)
            directories[:] = [d for d in directories if not (here / d).is_symlink() and not reject_secret_name(d)]
            for name in sorted(files):
                relative = (here / name).relative_to(self.root).as_posix()
                if not reject_secret_name(relative) and not (here / name).is_symlink() and (
                        fnmatch.fnmatchcase(relative, pattern) or pattern.startswith("**/") and fnmatch.fnmatchcase(relative, pattern[3:])):
                    found.append(relative)
        return sorted(found)[:1000]

    def write(self, relative, content):
        if relative not in ALLOWLIST or not isinstance(content, str) or len(content.encode("utf-8")) > MAX_TEXT:
            raise ValueError("write outside allowlist or content limit")
        target = safe_path(self.root, relative)
        if not target.parent.is_dir() or target.exists() and not target.is_file():
            raise ValueError("invalid target")
        mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
        descriptor, temporary = tempfile.mkstemp(prefix="write-", dir=self.controller)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
            os.chmod(temporary, mode)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return {"path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    def call(self, name, arguments):
        with (self.controller / "phase.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if json.loads((self.controller / "phase.json").read_text())["phase"] != "agent":
                return {"content": [{"type": "text", "text": "Agent phase closed"}], "isError": True}
            return self._call(name, arguments)

    def _call(self, name, arguments):
        self.sequence += 1
        started = time.monotonic()
        try:
            result = self.dispatch(name, arguments)
            error = False
        except (ValueError, TypeError, OSError, UnicodeError) as exc:
            result, error = {"error": str(exc)}, True
        artifact = self.controller / f"tool-{self.sequence:04d}.json"
        artifact.write_text(json.dumps({"tool": name, "audit_role": self.config.get("audit_role", "agent"),
            "arguments_hash": hashlib.sha256(
            json.dumps(arguments, sort_keys=True).encode()).hexdigest(), "at": datetime.now(timezone.utc).isoformat(),
            "candidate_files": {p: hashlib.sha256((self.root / p).read_bytes()).hexdigest()
                                if (self.root / p).is_file() else None for p in sorted(ALLOWLIST)},
            "seconds": round(time.monotonic() - started, 3),
            "result": result, "is_error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": error}

    def dispatch(self, name, a):
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if not spec or not isinstance(a, dict) or set(a) - set(spec["inputSchema"]["properties"]) or any(
                required not in a for required in spec["inputSchema"]["required"]):
            raise ValueError("unsupported tool/arguments")
        if name == "WorkspaceInfo":
            return {"root": "/candidate", "baseline": self.config["baseline_commit"], "may_change": sorted(ALLOWLIST),
                    "python": self.config["python_in_sandbox"], "git": "not mounted; use Diff", "network": "unshared",
                    "tools": [t["name"] for t in TOOLS]}
        if name == "Read":
            offset, limit = a.get("offset", 1), a.get("limit", 250)
            if type(offset) is not int or type(limit) is not int or offset < 1 or not 1 <= limit <= 500:
                raise ValueError("invalid line range")
            lines = read_text(safe_path(self.root, a["path"])).splitlines()
            return {"path": a["path"], "total_lines": len(lines), "lines": [f"{i + offset}: {line}" for i, line in enumerate(lines[offset-1:offset-1+limit])]}
        if name == "Glob":
            return self.files(a.get("pattern", "**/*"))
        if name == "Grep":
            if not isinstance(a["query"], str) or not a["query"] or len(a["query"]) > 1000:
                raise ValueError("invalid literal query")
            matches = []
            for relative in self.files(a.get("pattern", "**/*")):
                try:
                    lines = read_text(safe_path(self.root, relative)).splitlines()
                except (ValueError, UnicodeError):
                    continue
                for number, line in enumerate(lines, 1):
                    if a["query"] in line:
                        matches.append({"path": relative, "line": number, "text": line[:1000]})
                        if len(matches) == 200:
                            return matches
            return matches
        if name == "Write":
            return self.write(a["path"], a["content"])
        if name == "Edit":
            if a["path"] not in ALLOWLIST or not all(isinstance(a[k], str) for k in ("old", "new")) or not a["old"]:
                raise ValueError("invalid edit")
            content = read_text(safe_path(self.root, a["path"]))
            if content.count(a["old"]) != 1:
                raise ValueError("old text must match exactly once")
            return self.write(a["path"], content.replace(a["old"], a["new"], 1))
        if name == "Diff":
            differences = []
            for relative in sorted(ALLOWLIST):
                old_path, new_path = self.baseline / relative, self.root / relative
                old = read_text(old_path).splitlines(keepends=True) if old_path.exists() else []
                new = read_text(safe_path(self.root, relative)).splitlines(keepends=True) if new_path.exists() else []
                differences.append("".join(difflib.unified_diff(old, new, "baseline/"+relative, "candidate/"+relative)))
            return {"diff": "".join(differences)[:MAX_TEXT]}
        if name == "RunTests":
            tests, runner = a["tests"], a.get("runner", "unittest")
            if not isinstance(tests, list) or not 1 <= len(tests) <= 30 or not all(isinstance(t, str) for t in tests):
                raise ValueError("select bounded tests")
            if runner == "unittest" and all(any(t == m or t.startswith(m + ".") for m in MODULES) and
                                           re.fullmatch(r"[A-Za-z0-9_.]+", t) for t in tests):
                command = ["{python}", "-B", "-m", "unittest", "-v", *tests]
            elif runner == "pytest" and all(t in PYTEST_FILES for t in tests):
                command = ["{python}", "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", *tests]
            else:
                raise ValueError("test selection outside approved bounded subset")
        elif name == "RunSmoke":
            command = ["{python}", "-B", "/candidate/verify.py"]
        else:
            raise ValueError("unsupported tool")
        result = run_bounded(sandbox_command(self.config["bwrap"], self.root, self.config["python"], command),
                             self.config["tool_timeout"])
        result["command"] = command
        return result


def serve(config):
    bridge = Bridge(config)
    for raw in iter(lambda: sys.stdin.buffer.readline(MAX_MESSAGE + 1), b""):
        request = None
        if len(raw) > MAX_MESSAGE:
            raise ValueError("MCP message too large")
        try:
            request = json.loads(raw)
            method, identifier = request.get("method"), request.get("id")
            if identifier is None:
                continue  # initialized/cancel notifications do not execute code.
            params = request.get("params", {})
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "isolated-eval-tools", "version": "1.0"}}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = bridge.call(params.get("name"), params.get("arguments", {}))
            elif method == "ping":
                result = {}
            else:
                raise ValueError("unsupported MCP method")
            response = {"jsonrpc": "2.0", "id": identifier, "result": result}
        except (ValueError, TypeError, AttributeError) as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(locals().get("request"), dict) else None,
                        "error": {"code": -32602, "message": str(exc)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    options = parser.parse_args()
    serve(json.loads(Path(options.config).read_text(encoding="utf-8")))

"""Web-only runtime oracles: no desktop boundary, Qt-free imports, real backend and CLI.

Every child process runs the current (fresh venv) interpreter with an explicit
allowlisted environment and its own HOME/TMPDIR/config directory. Children that
record imports install a meta-path finder that refuses and logs any attempt to
import PyQt6 or the retired ``ui`` package before the real entry point runs.
"""
from __future__ import annotations

import ast
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PACKAGES = ("backend", "pipeline", "chapters", "cleaning", "chunking", "filtering", "media", "config", "exporters")
RETIRED_ROOTS = ("PyQt6", "ui")
SKIPPED_DIRS = {".git", "node_modules", "__pycache__", "dist", "venv", ".venv", ".pytest_cache"}
CHILD_TIMEOUT = 30
FORBIDDEN_ENV = re.compile(r"^(QT_.*|DISPLAY|WAYLAND_DISPLAY|PYTHONPATH|PYTHONHOME|GOOGLE_.*|.*TOKEN.*|.*SECRET.*|.*KEY.*)$", re.IGNORECASE)
HOST_DETAIL = "Chỉ cho phép truy cập từ máy cục bộ."
ORIGIN_DETAIL = "Nguồn truy cập không được phép."

# Refuses and records PyQt6/ui imports, reports the child environment, then runs
# the named module exactly as ``python -m <module> <args>`` would.
BOOTSTRAP = r"""
import importlib.abc, importlib.metadata, importlib.util, json, os, runpy, sys
record = os.environ["WEB_ONLY_IMPORT_RECORD"]
def note(entry):
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("PyQt6", "ui"):
            note({"blocked": name})
            raise ImportError("retired desktop import: " + name)
        return None
installed = sorted(d.metadata["Name"] for d in importlib.metadata.distributions()
                   if (d.metadata["Name"] or "").lower().startswith("pyqt"))
note({"env": sorted(os.environ), "pyqt_spec": importlib.util.find_spec("PyQt6") is not None,
      "pyqt_distributions": installed, "executable": sys.executable})
sys.meta_path.insert(0, Blocker())
module = sys.argv[1]
sys.argv = [module] + sys.argv[2:]
runpy.run_module(module, run_name="__main__", alter_sys=True)
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def child_env(base: Path, **extra):
    """Explicit allowlist; nothing is copied from the parent environment."""
    for name in ("home", "tmp", "config", "xdg-config", "xdg-cache"):
        (base / name).mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": "/usr/bin:/bin", "HOME": str(base / "home"), "TMPDIR": str(base / "tmp"),
        "XDG_CONFIG_HOME": str(base / "xdg-config"), "XDG_CACHE_HOME": str(base / "xdg-cache"),
        "USER": "webonly", "LOGNAME": "webonly", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
        "NOVEL_PIPELINE_CONFIG_DIR": str(base / "config"), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", **extra,
    }
    leaked = [name for name in env if FORBIDDEN_ENV.match(name)]
    if leaked:
        raise AssertionError(f"forbidden child variables: {leaked}")
    return env


def recorded_command(module, *args):
    return [sys.executable, "-B", "-c", BOOTSTRAP, module, *args]


def read_record(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def raw_request(port, method, path, headers, timeout=10):
    """Send one request with headers exactly as given (no implicit Host)."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in headers:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, body
    finally:
        connection.close()


def listening_sockets(port):
    """(family, address) pairs in LISTEN state for ``port`` in this net namespace."""
    found = []
    for family, table in (("tcp", "/proc/net/tcp"), ("tcp6", "/proc/net/tcp6")):
        try:
            lines = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            address, hex_port = fields[1].rsplit(":", 1)
            if int(hex_port, 16) == port and fields[3] == "0A":
                found.append((family, address))
    return found


class BackendProcess:
    """A real ``backend`` child bound to a free loopback port, always reaped."""

    def __init__(self, test, base: Path, command_for_port):
        self.test, self.base, self.command_for_port = test, base, command_for_port
        self.process = self.port = self.log_path = None

    def start(self, **env_extra):
        last_log = ""
        for attempt in range(3):  # bounded retry of the free-port race
            self.port = free_port()
            self.log_path = self.base / f"backend-{attempt}.log"
            log = self.log_path.open("wb")
            self.process = subprocess.Popen(
                self.command_for_port(self.port), cwd=ROOT, env=child_env(self.base, **env_extra),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            log.close()
            self.test.addCleanup(self.stop)
            deadline = time.monotonic() + CHILD_TIMEOUT
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    break
                try:
                    status, _, _ = raw_request(self.port, "GET", "/api/health", [("Host", f"127.0.0.1:{self.port}")], timeout=2)
                    if status == 200:
                        return self
                except OSError:
                    pass
                time.sleep(0.2)
            last_log = self.log_path.read_text(encoding="utf-8", errors="replace")
            exited = self.process.poll() is not None
            self.stop()
            if not exited:
                raise AssertionError(f"ERROR: backend did not become healthy within {CHILD_TIMEOUT}s:\n{last_log}")
            if "address already in use" not in last_log.lower():
                break
        raise AssertionError(f"ERROR: backend exited before health:\n{last_log}")

    def log(self):
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self):
        process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass


class WebOnlyRuntimeTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="web-only-runtime-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def run_child(self, command, base, timeout=CHILD_TIMEOUT, **env_extra):
        try:
            return subprocess.run(command, cwd=ROOT, env=child_env(base, **env_extra), stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise AssertionError(f"ERROR: child timed out after {timeout}s: {command[:4]}") from error

    def assert_graceful_exit(self, server):
        # Uvicorn finishes shutdown, then re-raises the SIGTERM it handled.
        self.assertIn(server.process.returncode, (0, -signal.SIGTERM), server.log())
        self.assertIn("Application shutdown complete.", server.log())
        self.assertEqual(listening_sockets(server.port), [])

    def assert_qt_free_record(self, record_path):
        entries = read_record(record_path)
        self.assertTrue(entries, "import recorder did not run")
        header = entries[0]
        self.assertEqual(header["executable"], sys.executable)
        self.assertFalse(header["pyqt_spec"], "PyQt6 is importable in the runtime environment")
        self.assertEqual(header["pyqt_distributions"], [])
        leaked = [name for name in header["env"] if FORBIDDEN_ENV.match(name)]
        self.assertEqual(leaked, [])
        self.assertEqual([entry["blocked"] for entry in entries if "blocked" in entry], [])

    def test_desktop_boundary_removed(self):
        present = [name for name in ("app.py", "requirements-desktop.txt", "ui") if (ROOT / name).exists()]
        declarations = [
            f"{path.name}:{number}" for path in sorted(ROOT.glob("requirements*.txt"))
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"pyqt|requirements-desktop", line.split("#", 1)[0], re.IGNORECASE)
        ]
        importers = []
        for directory, dirs, files in os.walk(ROOT):
            dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                path = Path(directory, name)
                tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
                for node in ast.walk(tree):
                    names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                             else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
                    if any(module.split(".")[0] in RETIRED_ROOTS for module in names):
                        importers.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        guidance = [
            f"{name}:{number}" for name in ("README.md", "INSTALL.md", "USAGE.md", "CLAUDE.md")
            for number, line in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"python[0-9.]*\s+app\.py|requirements-desktop|QT_QPA_PLATFORM", line)
        ]
        self.assertEqual(
            {"present": present, "declarations": declarations, "importers": importers, "guidance": guidance},
            {"present": [], "declarations": [], "importers": [], "guidance": []},
        )

    def test_supported_modules_import_without_qt(self):
        modules = []
        for package in SUPPORTED_PACKAGES:
            for path in sorted((ROOT / package).rglob("*.py")):
                parts = path.relative_to(ROOT).with_suffix("").parts
                if parts[-1] == "__main__":
                    continue
                modules.append(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
        self.assertIn("backend.app", modules)
        self.assertIn("pipeline.cli", modules)
        record = self.base / "imports.jsonl"
        script = self.base / "import_all.py"
        script.write_text(
            "import importlib, json, sys\n"
            f"modules = {modules!r}\n"
            "for name in modules:\n    importlib.import_module(name)\n"
            "loaded = sorted(m for m in sys.modules if m.split('.')[0] in ('PyQt6', 'ui'))\n"
            "print(json.dumps({'imported': len(modules), 'retired_loaded': loaded}))\n",
            encoding="utf-8",
        )
        # runpy executes the generated module by path after the blocker is installed.
        command = [sys.executable, "-B", "-c", BOOTSTRAP.replace(
            "runpy.run_module(module, run_name=\"__main__\", alter_sys=True)",
            "sys.path.insert(0, os.getcwd()); runpy.run_path(module, run_name=\"__main__\")"), str(script)]
        result = self.run_child(command, self.base, WEB_ONLY_IMPORT_RECORD=str(record))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report, {"imported": len(modules), "retired_loaded": []})
        self.assert_qt_free_record(record)

    def test_real_backend_health_without_qt(self):
        record = self.base / "backend-imports.jsonl"
        server = BackendProcess(self, self.base, lambda port: recorded_command("backend", "--port", str(port)))
        server.start(WEB_ONLY_IMPORT_RECORD=str(record))
        host = [("Host", f"127.0.0.1:{server.port}")]
        status, headers, body = raw_request(server.port, "GET", "/api/health", host)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})
        status, _, body = raw_request(server.port, "GET", "/api/state", host)
        self.assertEqual(status, 200, body)
        self.assertIn("groups", json.loads(body))
        self.assertEqual(listening_sockets(server.port), [("tcp", "0100007F")])
        server.stop()
        self.assert_graceful_exit(server)
        self.assert_qt_free_record(record)
        self.assertFalse(any((self.base / "config").glob("**/*.tmp")))

    def test_real_backend_host_origin_policy(self):
        server = BackendProcess(self, self.base, lambda port: [sys.executable, "-B", "-m", "backend", "--port", str(port)])
        server.start()
        port = server.port
        self.assertIn(f"Uvicorn running on http://127.0.0.1:{port}", server.log())
        self.assertEqual(listening_sockets(port), [("tcp", "0100007F")])
        outcomes = []

        def check(label, method, path, headers, expected, detail=None, acao=None):
            status, response_headers, body = raw_request(port, method, path, headers)
            outcomes.append((label, path, status))
            message = f"{label} {method} {path}: {status} {body[:200]!r}"
            if expected == "non-2xx":
                self.assertFalse(200 <= status < 300, message)
                return status
            self.assertEqual(status, expected, message)
            if detail is not None:
                self.assertEqual(json.loads(body)["detail"], detail, message)
                self.assertNotIn("access-control-allow-origin", response_headers, message)
            if acao is not None:
                self.assertEqual(response_headers.get("access-control-allow-origin"), acao, message)
            return status

        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}"):
            check(f"accepted host {host}", "GET", "/api/health", [("Host", host)], 200)
        for host, origin in ((f"127.0.0.1:{port}", f"http://127.0.0.1:{port}"),
                             (f"localhost:{port}", f"http://localhost:{port}"),
                             (f"127.0.0.1:{port}", "http://localhost:5173"),
                             (f"127.0.0.1:{port}", "http://127.0.0.1:5173")):
            check(f"accepted origin {origin}", "GET", "/api/health", [("Host", host), ("Origin", origin)], 200)
        check("dev preflight", "OPTIONS", "/api/jobs",
              [("Host", f"127.0.0.1:{port}"), ("Origin", "http://localhost:5173"),
               ("Access-Control-Request-Method", "POST")], 200, acao="http://localhost:5173")
        for host in ("evil.example", "localhost.evil.example", "127.0.0.1.evil.example",
                     f"[::1]:{port}", "localhost:0", "localhost:70000"):
            for path in ("/api/health", "/"):
                check(f"rejected host {host}", "GET", path, [("Host", host)], 403, detail=HOST_DETAIL)
        good_host = ("Host", f"127.0.0.1:{port}")
        rejected_origins = [
            [("Origin", "null")], [("Origin", "https://evil.example")], [("Origin", "http://localhost:9999")],
            [("Origin", f"https://127.0.0.1:{port}")], [("Origin", f"http://127.0.0.1:{port}/evil")],
            [("Origin", f"http://user@127.0.0.1:{port}")], [("Origin", f"http://localhost:{port}")],
            [("Origin", f"http://127.0.0.1:{port}"), ("Origin", f"http://127.0.0.1:{port}")],
        ]
        for origins in rejected_origins:
            for path in ("/api/health", "/"):
                check(f"rejected origin {[value for _, value in origins]}", "GET", path,
                      [good_host, *origins], 403, detail=ORIGIN_DETAIL)
        missing = check("missing host", "GET", "/api/health", [], "non-2xx")
        duplicate = check("two hosts", "GET", "/api/health", [good_host, good_host], "non-2xx")
        print(json.dumps({"port": port, "cases": len(outcomes), "missing_host_status": missing,
                          "two_hosts_status": duplicate, "outcomes": outcomes}, ensure_ascii=False))
        server.stop()
        self.assert_graceful_exit(server)

    def test_cli_fixture_pipeline_without_qt(self):
        result = self.run_child([sys.executable, "-B", "-m", "pipeline", "--help"], self.base / "help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("run", result.stdout)
        story = self.base / "input" / "story.txt"
        story.parent.mkdir()
        chapters = [f"Chương {number}\nNội dung chương {number} — 第{number}章." for number in range(1, 6)]
        story.write_text("\n\n".join(chapters) + "\n", encoding="utf-8")
        original = story.read_bytes()
        record = self.base / "cli-imports.jsonl"
        run_base = self.base / "run"
        result = self.run_child(
            recorded_command("pipeline", "run", str(story), "--title", "Truyện thử", "--group-size", "2", "--export", "json"),
            run_base, WEB_ONLY_IMPORT_RECORD=str(record),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual([entry["action"] for entry in report["results"]], ["import", "normalize", "group", "export"])
        self.assertEqual(len(report["results"][2]["group_ids"]), 3)
        exported = Path(report["results"][3]["path"])
        self.assertTrue(exported.is_relative_to(story.parent.resolve()), exported)
        payload = json.loads(exported.read_text(encoding="utf-8"))
        headings = [line for line in payload["text"].splitlines() if line.startswith("Chương")]
        self.assertEqual(headings, [f"Chương {number}" for number in range(1, 6)])
        self.assertIn("第3章", payload["text"])
        self.assertEqual(story.read_bytes(), original)
        self.assertTrue(report["session_id"])
        self.assertTrue(any((run_base / "config").rglob("*.json")))
        self.assert_qt_free_record(record)


if __name__ == "__main__":
    unittest.main()

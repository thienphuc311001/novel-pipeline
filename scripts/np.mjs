#!/usr/bin/env node
import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import concurrently from "concurrently";

const args = process.argv.slice(2);
if (args.length !== 2 || args[0] !== "run" || args[1] !== "dev") {
  const help = args.length === 1 && ["--help", "-h"].includes(args[0]);
  console[help ? "log" : "error"]("Usage: np run dev\nStart the local FastAPI backend and Vite frontend together.");
  process.exit(help ? 0 : 1);
}

const root = fileURLToPath(new URL("../", import.meta.url));
const windows = process.platform === "win32";
const venvPython = join(root, ".venv", windows ? "Scripts/python.exe" : "bin/python");
const python = existsSync(venvPython) ? venvPython : windows ? "python" : "python3";

console.log("Frontend: http://127.0.0.1:5173\nBackend:  http://127.0.0.1:8765\nCtrl+C stops both servers.");
const { result } = concurrently(
  [
    {
      name: "backend",
      command: windows ? '"%NP_DEV_PYTHON%" -m backend --port 8765' : '"$NP_DEV_PYTHON" -m backend --port 8765',
      env: { NP_DEV_PYTHON: python },
    },
    { name: "frontend", command: "npm --prefix frontend run dev" },
  ],
  { cwd: root, prefix: "name", killOthersOn: ["failure", "success"] },
);
await result.catch(() => { process.exitCode = 1; });

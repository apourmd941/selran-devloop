#!/usr/bin/env python3
"""Small local progress UI for Selran loop runs.

The UI wraps cli/autoloop, captures stdout/stderr, and exposes a localhost
dashboard with run status, parsed phase progress, and live logs.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
AUTOLOOP = ROOT / "cli" / "autoloop"
DEFAULT_PORT = 8768
MAX_LOG_LINES = 4000

WORKFLOW_STEPS = [
    {
        "id": "cartographer",
        "name": "Cartographer",
        "items": [
            {"name": "Stage 1", "detail": "tag propagation"},
            {"name": "Stage 2", "detail": "spec refs"},
            {"name": "Stage 3", "detail": "qualified names + git blame"},
            {"name": "Stage 4", "detail": "call graph", "optional": True},
        ],
    },
    {
        "id": "pre-commit-verification",
        "name": "Pre Commit Verification",
        "items": [
            {"name": "tests"},
            {"name": "lint/type/build"},
            {"name": "smoke harness"},
        ],
    },
    {
        "id": "app-audit",
        "name": "App Audit",
        "items": [
            {"name": "baseline"},
            {"name": "checklist"},
            {"name": "AUDIT_LOG"},
        ],
    },
    {
        "id": "audit-fix",
        "name": "Audit Fix",
        "items": [
            {"name": "order"},
            {"name": "fix"},
            {"name": "verify"},
        ],
    },
    {
        "id": "loop",
        "name": "Loop",
        "items": [
            {"name": "repeat"},
            {"name": "report"},
            {"name": "review gate"},
        ],
    },
]

RUNS: dict[str, dict] = {}
RUN_LOCK = threading.RLock()
PROCS: dict[str, subprocess.Popen] = {}


def now() -> float:
    return time.time()


def new_run(payload: dict) -> tuple[dict, str | None]:
    repo = str(payload.get("repo") or "").strip()
    mode = str(payload.get("mode") or "dry-run").strip()
    base = str(payload.get("base") or "").strip()
    scope = str(payload.get("scope") or "").strip()

    if mode not in {"dry-run", "host", "sandbox"}:
        return {}, "mode must be dry-run, host, or sandbox"
    if not repo:
        return {}, "repo is required"

    repo_path = Path(repo).expanduser()
    if not repo_path.exists():
        return {}, f"repo not found: {repo_path}"
    if not (repo_path / ".git").exists():
        try:
            subprocess.check_output(
                ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            return {}, f"not a git repo: {repo_path}"

    run_id = uuid.uuid4().hex[:12]
    cmd = [str(AUTOLOOP), "run", str(repo_path)]
    if base:
        cmd.extend(["--base", base])
    if scope:
        cmd.extend(["--scope", scope])
    if mode == "dry-run":
        cmd.append("--dry-run")
    elif mode == "host":
        cmd.append("--host")

    run = {
        "id": run_id,
        "repo": str(repo_path),
        "mode": mode,
        "base": base,
        "scope": scope,
        "command": cmd,
        "status": "queued",
        "phase": "Queued",
        "step_index": 0,
        "steps": build_steps(),
        "progress": 0,
        "started_at": now(),
        "ended_at": None,
        "exit_code": None,
        "open_findings": None,
        "fixed": None,
        "deferred": None,
        "stop_reason": None,
        "report": None,
        "logs": [],
        "cancel_requested": False,
    }
    mark_step(run, 0, "active")

    with RUN_LOCK:
        RUNS[run_id] = run

    thread = threading.Thread(target=run_worker, args=(run_id,), daemon=True)
    thread.start()
    return snapshot_run(run), None


def mark_step(run: dict, index: int, status: str = "active") -> None:
    index = max(0, min(index, len(WORKFLOW_STEPS) - 1))
    run["step_index"] = index
    for i, step in enumerate(run["steps"]):
        if i < index and step["status"] not in {"failed", "canceled"}:
            step["status"] = "complete"
        elif i == index:
            step["status"] = status
        elif step["status"] not in {"failed", "canceled"}:
            step["status"] = "pending"
    refresh_step_items(run)
    run["phase"] = WORKFLOW_STEPS[index]["name"]
    run["progress"] = max(run.get("progress", 0), int((index / len(WORKFLOW_STEPS)) * 100))


def complete_steps(run: dict, status: str = "complete") -> None:
    for step in run["steps"]:
        if step["status"] not in {"failed", "canceled"}:
            step["status"] = status
    refresh_step_items(run)
    run["progress"] = 100 if status == "complete" else run.get("progress", 0)


def build_steps() -> list[dict]:
    steps = []
    for step in WORKFLOW_STEPS:
        steps.append(
            {
                "id": step["id"],
                "name": step["name"],
                "status": "pending",
                "items": [
                    {
                        "name": item["name"],
                        "detail": item.get("detail", ""),
                        "optional": bool(item.get("optional")),
                        "status": "optional" if item.get("optional") else "pending",
                    }
                    for item in step.get("items", [])
                ],
            }
        )
    return steps


def refresh_step_items(run: dict) -> None:
    for step in run["steps"]:
        status = step.get("status")
        for item in step.get("items", []):
            if item.get("optional"):
                item["status"] = "optional"
            elif status == "complete":
                item["status"] = "complete"
            elif status == "active":
                item["status"] = "active"
            elif status in {"failed", "canceled"}:
                item["status"] = status
            else:
                item["status"] = "pending"


def append_log(run: dict, line: str) -> None:
    run["logs"].append({"t": now(), "line": line.rstrip("\n")})
    if len(run["logs"]) > MAX_LOG_LINES:
        run["logs"] = run["logs"][-MAX_LOG_LINES:]
    parse_progress(run, line)


def parse_progress(run: dict, line: str) -> None:
    lower = line.lower()
    if "[autoloop] repo=" in lower:
        run["phase"] = "Loop setup"
        run["progress"] = max(run["progress"], 8)
    elif "dry-run: running the driver" in lower or "host mode:" in lower or "running the loop" in lower:
        mark_step(run, 0)
        run["progress"] = max(run["progress"], 18)
    elif "building sandbox image" in lower:
        mark_step(run, 4)
        run["phase"] = "Building sandbox"
        run["progress"] = max(run["progress"], 12)
    elif "[devloop] === iteration" in lower:
        mark_step(run, 0)
        run["progress"] = max(run["progress"], 22)
    elif "cartographer" in lower:
        mark_step(run, 0)
        run["progress"] = max(run["progress"], 24)
    elif "pre-commit" in lower or "smoke harness" in lower:
        mark_step(run, 1)
        run["progress"] = max(run["progress"], 38)
    elif "audit turn" in lower or "app-audit" in lower:
        mark_step(run, 2)
        run["progress"] = max(run["progress"], 48)
    elif "open findings" in lower:
        match = re.search(r"open findings:\s*(\d+|none)", lower)
        if match and match.group(1).isdigit():
            run["open_findings"] = int(match.group(1))
        mark_step(run, 2)
        run["progress"] = max(run["progress"], 58)
    elif "fix turn" in lower or "audit-fix" in lower:
        mark_step(run, 3)
        run["progress"] = max(run["progress"], 66)
    elif "fixed=" in lower and "open=" in lower:
        fixed = re.search(r"fixed=(\d+)", lower)
        deferred = re.search(r"deferred=(\d+)", lower)
        open_n = re.search(r"open=(\d+)", lower)
        if fixed:
            run["fixed"] = int(fixed.group(1))
        if deferred:
            run["deferred"] = int(deferred.group(1))
        if open_n:
            run["open_findings"] = int(open_n.group(1))
        mark_step(run, 3)
        run["progress"] = max(run["progress"], 70)
    elif "run report" in lower:
        mark_step(run, 4)
        run["progress"] = max(run["progress"], 84)
    elif "report written" in lower:
        mark_step(run, 4)
        run["progress"] = max(run["progress"], 90)
    elif "dry-run complete" in lower or "no commits produced" in lower or "open the pr" in lower:
        mark_step(run, 4)
        run["progress"] = max(run["progress"], 96)


def run_worker(run_id: str) -> None:
    with RUN_LOCK:
        run = RUNS[run_id]
        run["status"] = "running"
        cmd = list(run["command"])

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except Exception as exc:
        with RUN_LOCK:
            run = RUNS[run_id]
            append_log(run, f"failed to start: {exc}")
            run["status"] = "failed"
            run["exit_code"] = 127
            run["ended_at"] = now()
            mark_step(run, run.get("step_index", 0), "failed")
        return

    with RUN_LOCK:
        PROCS[run_id] = proc

    assert proc.stdout is not None
    for line in proc.stdout:
        with RUN_LOCK:
            append_log(RUNS[run_id], line)

    code = proc.wait()
    with RUN_LOCK:
        run = RUNS[run_id]
        run["exit_code"] = code
        run["ended_at"] = now()
        run["report"] = extract_report(run)
        if run["report"] and run["report"].get("stop_reason"):
            run["stop_reason"] = run["report"]["stop_reason"]
        if run["cancel_requested"]:
            run["status"] = "canceled"
            mark_step(run, run.get("step_index", 0), "canceled")
        elif code == 0:
            run["status"] = "complete"
            complete_steps(run)
            run["phase"] = "Complete"
        else:
            run["status"] = "failed"
            mark_step(run, run.get("step_index", 0), "failed")
            run["phase"] = "Failed"
        PROCS.pop(run_id, None)


def extract_report(run: dict) -> dict | None:
    text = "\n".join(item["line"] for item in run["logs"])
    decoder = json.JSONDecoder()
    found = None
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        if isinstance(obj, dict) and "stop_reason" in obj and "iterations" in obj:
            found = obj
    return found


def snapshot_run(run: dict, include_logs: bool = True) -> dict:
    snap = dict(run)
    snap["command"] = " ".join(shell_quote(part) for part in run["command"])
    if not include_logs:
        snap["logs"] = []
    return snap


def shell_quote(value: str) -> str:
    if re.search(r"[^A-Za-z0-9_./:=+-]", value):
        return "'" + value.replace("'", "'\\''") + "'"
    return value


def cancel_run(run_id: str) -> bool:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        proc = PROCS.get(run_id)
        if not run:
            return False
        run["cancel_requested"] = True
        append_log(run, "cancel requested")
    if proc and proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
            threading.Timer(5.0, kill_if_running, args=(proc,)).start()
        except Exception:
            pass
    return True


def kill_if_running(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "LoopUI/0.2"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.replace("__DEVLOOP_ROOT__", html.escape(str(ROOT), quote=True))
            self.send_html(body)
        elif parsed.path == "/api/runs":
            with RUN_LOCK:
                runs = [snapshot_run(run, include_logs=False) for run in RUNS.values()]
            runs.sort(key=lambda item: item["started_at"], reverse=True)
            self.send_json({"runs": runs})
        elif parsed.path.startswith("/api/runs/"):
            run_id = parsed.path.rsplit("/", 1)[-1]
            with RUN_LOCK:
                run = RUNS.get(run_id)
                if not run:
                    self.send_json({"error": "not found"}, status=404)
                else:
                    self.send_json(snapshot_run(run))
        elif parsed.path == "/api/config":
            qs = parse_qs(parsed.query)
            repo = qs.get("repo", [""])[0]
            self.send_json({"default_repo": repo, "root": str(ROOT)})
        else:
            self.send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/runs":
            payload = self.read_json()
            run, error = new_run(payload)
            if error:
                self.send_json({"error": error}, status=400)
            else:
                self.send_json({"run": run}, status=201)
        elif parsed.path.startswith("/api/runs/") and parsed.path.endswith("/cancel"):
            run_id = parsed.path.split("/")[-2]
            if cancel_run(run_id):
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "not found"}, status=404)
        else:
            self.send_json({"error": "not found"}, status=404)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def read_json(self) -> dict:
        size = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(size) if size else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def find_port(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no open port near {start}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Selran loop progress UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = parser.parse_args()

    if not AUTOLOOP.exists():
        print(f"autoloop not found: {AUTOLOOP}", file=sys.stderr)
        return 2

    port = find_port(args.port)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Loop UI: {url}", flush=True)
    if not args.no_open:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down", flush=True)
    finally:
        server.server_close()
    return 0


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Loop UI</title>
  <style>
    /* Styled to ui/design-system.md — technical-minimal, forest-green identity.
       No webfonts (system stacks only); dark/light via prefers-color-scheme. */
    :root {
      color-scheme: light dark;
      --bg: #FBFBFA;
      --panel: #ffffff;
      --ink: #1A1C1A;
      --muted: #646A64;
      --line: #E4E4DE;
      --accent: #1F7A4D;       /* the "runs until green" identity */
      --blue: #1F7A4D;         /* primary actions use the green accent, not generic blue */
      --green: #1F7A4D;
      --amber: #9A7B0A;
      --red: #B3261E;
      --shadow: 0 8px 24px rgba(17, 24, 39, 0.06);
      --violet: #2F6DB3;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #121413; --panel: #1A1D1B; --ink: #E7E9E5; --muted: #9AA09A;
        --line: #2C302D; --accent: #4FB07C; --blue: #4FB07C; --green: #4FB07C;
        --amber: #CFAE3D; --red: #E5685F; --violet: #6EA8E0;
        --shadow: 0 8px 24px rgba(0,0,0,0.4);
      }
    }
    @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      letter-spacing: 0;
      -webkit-font-smoothing: antialiased;
    }
    .shell {
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 100vh;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,0.86);
      backdrop-filter: blur(10px);
      position: sticky;
      top: 0;
      z-index: 3;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }
    .status-pill {
      min-width: 92px;
      text-align: center;
      padding: 6px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      background: #fff;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
      width: min(1440px, 100%);
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .controls {
      padding: 18px;
      align-self: start;
      position: sticky;
      top: 78px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin: 14px 0 6px;
      text-transform: uppercase;
    }
    input, textarea, button {
      font: inherit;
      letter-spacing: 0;
    }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 10px 11px;
      outline: none;
    }
    textarea {
      min-height: 78px;
      resize: vertical;
    }
    input:focus, textarea:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 3px rgba(47,111,237,0.14);
    }
    .segmented {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      border: 1px solid var(--line);
      border-radius: 7px;
      overflow: hidden;
      background: #fff;
    }
    .segmented button {
      border: 0;
      border-right: 1px solid var(--line);
      background: transparent;
      padding: 9px 8px;
      color: var(--muted);
      cursor: pointer;
      font-weight: 700;
    }
    .segmented button:last-child { border-right: 0; }
    .segmented button.active {
      background: #eaf1ff;
      color: #1648a8;
    }
    .actions {
      display: flex;
      gap: 10px;
      margin-top: 16px;
    }
    .primary, .secondary, .danger {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border-radius: 6px;
      min-height: 40px;
      padding: 0 14px;
      border: 1px solid transparent;
      cursor: pointer;
      font-weight: 800;
    }
    .primary { background: var(--blue); color: #fff; }
    .secondary { background: #fff; color: var(--ink); border-color: var(--line); }
    .danger { background: #fff; color: var(--red); border-color: #efb6b6; }
    button:disabled {
      cursor: not-allowed;
      opacity: 0.55;
    }
    .content {
      display: grid;
      gap: 18px;
    }
    .run-head {
      padding: 18px;
      display: grid;
      gap: 16px;
    }
    .summary-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px;
      min-height: 72px;
    }
    .metric b {
      display: block;
      font-size: 20px;
      margin-top: 3px;
    }
    .metric span {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .bar {
      height: 10px;
      overflow: hidden;
      border-radius: 999px;
      background: #e8edf3;
    }
    .bar > div {
      width: 0%;
      height: 100%;
      background: linear-gradient(90deg, var(--blue), var(--green));
      transition: width 180ms ease;
    }
    .steps {
      display: grid;
      grid-template-columns: repeat(5, minmax(130px, 1fr));
      gap: 8px;
    }
    .step {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 9px;
      color: var(--muted);
      min-height: 142px;
    }
    .step strong {
      display: block;
      color: var(--ink);
      font-size: 13px;
    }
    .step.active { border-color: var(--blue); background: #f2f6ff; }
    .step.complete { border-color: #a7d8c4; background: #f0fbf6; }
    .step.failed { border-color: #efb6b6; background: #fff4f4; }
    .step.canceled { border-color: #e9cc91; background: #fff8ea; }
    .substeps {
      display: grid;
      gap: 5px;
      margin-top: 9px;
    }
    .substep {
      display: grid;
      grid-template-columns: 8px minmax(0, 1fr);
      gap: 7px;
      align-items: start;
      color: var(--muted);
      font-size: 11px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      margin-top: 5px;
      background: #c7cfdb;
    }
    .substep.active .dot { background: var(--blue); }
    .substep.complete .dot { background: var(--green); }
    .substep.failed .dot { background: var(--red); }
    .substep.canceled .dot { background: var(--amber); }
    .substep.optional .dot { background: var(--violet); }
    .substep b {
      color: var(--ink);
      font-weight: 700;
    }
    .log-panel {
      overflow: hidden;
    }
    .log-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }
    .log {
      margin: 0;
      min-height: 460px;
      max-height: calc(100vh - 360px);
      overflow: auto;
      padding: 14px;
      background: #111820;
      color: #dce8f5;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .muted {
      color: var(--muted);
    }
    .error {
      color: var(--red);
      margin-top: 10px;
      min-height: 20px;
    }
    .command {
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      word-break: break-word;
    }
    @media (max-width: 920px) {
      main {
        grid-template-columns: 1fr;
      }
      .controls {
        position: static;
      }
      .summary-row, .steps {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>Loop</h1>
      <div id="topStatus" class="status-pill">Idle</div>
    </header>
    <main>
      <section class="controls">
        <label for="repo">Repo</label>
        <input id="repo" value="__DEVLOOP_ROOT__">

        <label for="base">Base branch</label>
        <input id="base" placeholder="current branch">

        <label>Mode</label>
        <div class="segmented" id="mode">
          <button data-mode="dry-run" class="active" title="Plumbing test with no API calls or changes">Dry run</button>
          <button data-mode="host" title="Live loop on this Mac">Host</button>
          <button data-mode="sandbox" title="Live loop in Docker">Sandbox</button>
        </div>

        <label for="scope">Scope</label>
        <textarea id="scope" placeholder="latest audit scope"></textarea>

        <div class="actions">
          <button id="start" class="primary" title="Start run">
            <span>Start</span>
          </button>
          <button id="cancel" class="danger" title="Cancel run" disabled>
            <span>Cancel</span>
          </button>
        </div>
        <div id="error" class="error"></div>
      </section>

      <div class="content">
        <section class="run-head">
          <div>
            <div class="muted" id="phase">No run selected</div>
            <div class="command" id="command"></div>
          </div>
          <div class="bar"><div id="barFill"></div></div>
          <div class="summary-row">
            <div class="metric"><span>Status</span><b id="status">Idle</b></div>
            <div class="metric"><span>Open</span><b id="openFindings">-</b></div>
            <div class="metric"><span>Fixed</span><b id="fixed">-</b></div>
            <div class="metric"><span>Elapsed</span><b id="elapsed">0s</b></div>
          </div>
          <div id="steps" class="steps"></div>
        </section>

        <section class="log-panel">
          <div class="log-toolbar">
            <strong>Runner Log</strong>
            <button id="clearLog" class="secondary">Clear</button>
          </div>
          <pre id="log" class="log"></pre>
        </section>
      </div>
    </main>
  </div>

  <script>
    const state = {
      mode: "dry-run",
      currentRunId: null,
      poll: null,
      lastRun: null
    };

    const $ = (id) => document.getElementById(id);
    const modeButtons = [...document.querySelectorAll("#mode button")];

    modeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        state.mode = btn.dataset.mode;
        modeButtons.forEach((b) => b.classList.toggle("active", b === btn));
      });
    });

    $("start").addEventListener("click", startRun);
    $("cancel").addEventListener("click", cancelRun);
    $("clearLog").addEventListener("click", () => { $("log").textContent = ""; });

    renderSteps([]);
    setInterval(() => {
      if (state.lastRun) renderRun(state.lastRun);
    }, 1000);

    async function startRun() {
      setError("");
      const payload = {
        repo: $("repo").value.trim(),
        base: $("base").value.trim(),
        scope: $("scope").value.trim(),
        mode: state.mode
      };
      try {
        const res = await fetch("/api/runs", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "could not start run");
        state.currentRunId = data.run.id;
        state.lastRun = data.run;
        renderRun(data.run);
        $("start").disabled = true;
        $("cancel").disabled = false;
        if (state.poll) clearInterval(state.poll);
        state.poll = setInterval(fetchRun, 900);
        fetchRun();
      } catch (err) {
        setError(err.message);
      }
    }

    async function fetchRun() {
      if (!state.currentRunId) return;
      const res = await fetch(`/api/runs/${state.currentRunId}`);
      const run = await res.json();
      if (!res.ok) {
        setError(run.error || "run not found");
        clearInterval(state.poll);
        return;
      }
      state.lastRun = run;
      renderRun(run);
      if (!["queued", "running"].includes(run.status)) {
        clearInterval(state.poll);
        $("start").disabled = false;
        $("cancel").disabled = true;
      }
    }

    async function cancelRun() {
      if (!state.currentRunId) return;
      await fetch(`/api/runs/${state.currentRunId}/cancel`, {method: "POST"});
      fetchRun();
    }

    function renderRun(run) {
      $("topStatus").textContent = run.status;
      $("status").textContent = title(run.status);
      $("phase").textContent = run.stop_reason || run.phase || "Running";
      $("command").textContent = run.command || "";
      $("openFindings").textContent = value(run.open_findings);
      $("fixed").textContent = value(run.fixed);
      $("elapsed").textContent = elapsed(run);
      $("barFill").style.width = `${run.progress || 0}%`;
      renderSteps(run.steps || []);
      renderLogs(run.logs || []);
    }

    function renderSteps(steps) {
      const source = steps.length ? steps : defaultSteps();
      $("steps").innerHTML = source.map((step) => `
        <div class="step ${step.status}">
          <strong>${escapeHtml(step.name)}</strong>
          <span>${escapeHtml(title(step.status))}</span>
          <div class="substeps">
            ${(step.items || []).map((item) => `
              <div class="substep ${item.status}">
                <span class="dot"></span>
                <span><b>${escapeHtml(item.name)}</b>${item.detail ? `: ${escapeHtml(item.detail)}` : ""}${item.optional ? " (optional)" : ""}</span>
              </div>
            `).join("")}
          </div>
        </div>
      `).join("");
    }

    function defaultSteps() {
      return [
        {name: "Cartographer", status: "pending", items: [
          {name: "Stage 1", detail: "tag propagation", status: "pending"},
          {name: "Stage 2", detail: "spec refs", status: "pending"},
          {name: "Stage 3", detail: "qualified names + git blame", status: "pending"},
          {name: "Stage 4", detail: "call graph", optional: true, status: "optional"}
        ]},
        {name: "Pre Commit Verification", status: "pending", items: [
          {name: "tests", status: "pending"},
          {name: "lint/type/build", status: "pending"},
          {name: "smoke harness", status: "pending"}
        ]},
        {name: "App Audit", status: "pending", items: [
          {name: "baseline", status: "pending"},
          {name: "checklist", status: "pending"},
          {name: "AUDIT_LOG", status: "pending"}
        ]},
        {name: "Audit Fix", status: "pending", items: [
          {name: "order", status: "pending"},
          {name: "fix", status: "pending"},
          {name: "verify", status: "pending"}
        ]},
        {name: "Loop", status: "pending", items: [
          {name: "repeat", status: "pending"},
          {name: "report", status: "pending"},
          {name: "review gate", status: "pending"}
        ]}
      ];
    }

    function renderLogs(logs) {
      const text = logs.map((item) => item.line).join("\n");
      const el = $("log");
      const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
      el.textContent = text;
      if (nearBottom) el.scrollTop = el.scrollHeight;
    }

    function elapsed(run) {
      const end = run.ended_at || Date.now() / 1000;
      const seconds = Math.max(0, Math.round(end - run.started_at));
      if (seconds < 60) return `${seconds}s`;
      const minutes = Math.floor(seconds / 60);
      const rest = seconds % 60;
      return `${minutes}m ${rest}s`;
    }

    function value(v) {
      return v === null || v === undefined ? "-" : String(v);
    }

    function title(value) {
      if (!value) return "";
      return String(value).replace(/[-_]/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function setError(message) {
      $("error").textContent = message || "";
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
import secrets
from pathlib import Path
from typing import Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.text import Text
from rich.layout import Layout
import re


REPO_ROOT = Path.cwd()
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"
GATEWAY_URL = "http://localhost:9000"
BRIDGE_HEALTH = "http://127.0.0.1:8787/health"
BOOTSTRAP_LOG = REPO_ROOT / ".aida" / "bootstrap-start.log"
SERVICES_TO_POLL = [
    "taiga-back",
    "gateway",
    "taiga-front",
    "postgres",
    "rabbit",
    "redis",
]


def _run(cmd: list[str] | str, check: bool = True) -> int:
    proc = subprocess.run(cmd, shell=isinstance(cmd, str))
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.returncode


def _http_status(url: str, timeout: float = 2.0) -> Optional[int]:
    try:
        r = subprocess.run([
            "curl", "-s", "-o", "/dev/null", "-m", str(int(timeout)), "-w", "%{http_code}", url
        ], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return int(r.stdout.strip())
    except Exception:
        pass
    return None


def _elapsed_str(start_ts: float) -> str:
    delta = int(time.time() - start_ts)
    return f"{delta//60:02d}m{delta%60:02d}s"


@dataclass
class Readiness:
    root_ok: bool = False
    auth_present: bool = False
    api_ok: bool = False
    bridge_ok: bool = False

    @property
    def gateway_ready(self) -> bool:
        return self.root_ok and self.api_ok


def _poll_readiness(readiness: Readiness) -> None:
    status_root = _http_status(f"{GATEWAY_URL}/")
    readiness.root_ok = (status_root == 200)
    status_api = _http_status(f"{GATEWAY_URL}/api/v1")
    readiness.api_ok = (status_api == 200)
    status_auth = _http_status(f"{GATEWAY_URL}/api/v1/auth")
    readiness.auth_present = (status_auth in (401, 405))
    status_bridge = _http_status(BRIDGE_HEALTH)
    readiness.bridge_ok = (status_bridge == 200)


def _tail_logs(service: str, line_queue: queue.Queue[str], stop_event: threading.Event) -> None:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "logs", "-f", service]
    try:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
            for line in iter(proc.stdout.readline, ""):
                if stop_event.is_set():
                    break
                if line:
                    line_queue.put(line.rstrip())
    except FileNotFoundError:
        return


def _resolve_container_id(service: str) -> Optional[str]:
    try:
        r = subprocess.run([
            "docker", "compose", "-f", str(COMPOSE_FILE), "ps", "-q", service
        ], capture_output=True, text=True)
        cid = (r.stdout or "").strip()
        return cid or None
    except Exception:
        return None


def _tail_container_logs(service: str, line_queue: queue.Queue[str], stop_event: threading.Event) -> None:
    cid: Optional[str] = None
    # Wait for container id to appear
    deadline = time.time() + 300
    while not cid and time.time() < deadline and not stop_event.is_set():
        cid = _resolve_container_id(service)
        if cid:
            break
        time.sleep(0.5)
    if not cid:
        return


def _tail_compose_logs_all(line_queue: queue.Queue[str], stop_event: threading.Event, analyzer: LogAnalyzer) -> None:
    # Resilient tailer: reconnect if no output or process exits unexpectedly
    while not stop_event.is_set():
        cmd = [
            "docker", "compose", "-f", str(COMPOSE_FILE),
            "logs", "-f", "--since", "0s", "--timestamps"
        ]
        had_output = False
        try:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
                start_attach = time.time()
                for line in iter(proc.stdout.readline, ""):
                    if stop_event.is_set():
                        break
                    if not line:
                        # If no output for a while after attach, break to retry
                        if (time.time() - start_attach) > 5 and not had_output:
                            break
                        continue
                    had_output = True
                    s = line.rstrip()
                    line_queue.put(s)
                    if "taiga_back" in s or "taiga-back" in s:
                        analyzer.process_line(s)
        except FileNotFoundError:
            # Docker not available yet; back off and retry
            time.sleep(1.0)


def _poll_last_lines(line_queue: queue.Queue[str], stop_event: threading.Event, analyzer: LogAnalyzer) -> None:
    # Defensive poller: fetch the last line from each service periodically
    while not stop_event.is_set():
        for svc in SERVICES_TO_POLL:
            if stop_event.is_set():
                break
            try:
                r = subprocess.run([
                    "docker", "compose", "-f", str(COMPOSE_FILE),
                    "logs", "--tail", "1", "--timestamps", svc
                ], capture_output=True, text=True)
                out = (r.stdout or "").strip()
                if out:
                    # Use only the last non-empty line
                    s = out.splitlines()[-1]
                    line_queue.put(s)
                    if "taiga_back" in s or "taiga-back" in s:
                        analyzer.process_line(s)
            except Exception:
                pass
        # Poll interval
        time.sleep(1.0)
        # If we exit the with-block without stop_event, retry after a short backoff
        if not stop_event.is_set():
            time.sleep(1.0)
    cmd = ["docker", "logs", "-f", "--tail", "50", cid]
    try:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
            for line in iter(proc.stdout.readline, ""):
                if stop_event.is_set():
                    break
                if line:
                    line_queue.put(line.rstrip())
    except FileNotFoundError:
        return


def _latest_line(q: queue.Queue[str]) -> str:
    last = ""
    try:
        while True:
            last = q.get_nowait()
    except queue.Empty:
        pass
    return last


class LogAnalyzer:
    def __init__(self) -> None:
        self.migrations_applied: int = 0
        self.last_migration: str = ""
        self.phase: str = "Starting"
        self._rx_apply = re.compile(r"Applying\s+([\w\.]+)")
        self._rx_api_start = re.compile(r"Starting\s+Taiga\s+API|gunicorn|Booting worker", re.I)

    def process_line(self, line: str) -> None:
        m = self._rx_apply.search(line)
        if m:
            self.migrations_applied += 1
            self.last_migration = m.group(1)
            self.phase = "Running migrations"
            return
        if self._rx_api_start.search(line):
            self.phase = "Starting API"

    def render_status(self, elapsed: str, readiness: Readiness) -> Text:
        # Build a single concise status line beneath the bar
        parts: list[str] = []
        if self.phase == "Running migrations" and self.last_migration:
            parts.append(f"Running migrations: {self.last_migration} — {self.migrations_applied} applied")
        elif readiness.gateway_ready:
            parts.append("Gateway ready (/:200, /api/v1:200); finalizing startup…")
        else:
            parts.append(self.phase)
        # Append readiness flags tersely
        flags = []
        flags.append("root=OK" if readiness.root_ok else "root=…")
        flags.append("api=OK" if readiness.api_ok else "api=…")
        return Text(f"{parts[0]}    [" + ", ".join(flags) + f"]    Elapsed {elapsed}")


def _ensure_compose_file() -> None:
    if not COMPOSE_FILE.exists():
        print(f"Compose file not found at {COMPOSE_FILE}", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AIDA Bootstrap (clean progress UI)")
    p.add_argument("--bootstrap", action="store_true", help="Run full destructive bootstrap: reset + start")
    p.add_argument("--reset", action="store_true", help="Perform reset before start")
    p.add_argument("--no-reset", action="store_true", help="Do not reset; start only")
    p.add_argument("--admin-user", default="user")
    p.add_argument("--admin-email", default="user@localhost")
    p.add_argument("--admin-pass", default=None)
    p.add_argument("--timeout", type=int, default=900, help="Timeout seconds")
    args = p.parse_args(argv or sys.argv[1:])

    _ensure_compose_file()
    REPO_ROOT.joinpath(".aida").mkdir(parents=True, exist_ok=True)

    do_reset = args.bootstrap or (args.reset and not args.no_reset)
    start_ts = time.time()

    console = Console()
    line_queue: queue.Queue[str] = queue.Queue(maxsize=512)
    stop_event = threading.Event()
    readiness = Readiness()

    # Tail backend logs in background
    analyzer = LogAnalyzer()
    def tail_back_analyze() -> None:
        # Prefer container logs for reliability
        try:
            for_fn = _tail_container_logs
            # Bridge to analyzer
            q: queue.Queue[str] = line_queue
            for_fn("taiga-back", q, stop_event)
        finally:
            pass

    def tail_gateway() -> None:
        _tail_container_logs("gateway", line_queue, stop_event)

    t_all = threading.Thread(target=_tail_compose_logs_all, args=(line_queue, stop_event, analyzer), daemon=True)
    t_poll = threading.Thread(target=_poll_last_lines, args=(line_queue, stop_event, analyzer), daemon=True)
    t_all.start()
    t_poll.start()

    # Progress UI setup
    progress = Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("{task.description}", style="bold"),
        BarColumn(bar_width=None),
        TextColumn("{task.percentage:>3.0f}%"),
    )
    task_id = progress.add_task("Initializing...", total=100)

    # Live layout: progress bar + status line
    status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
    log_line = Text("Log: (waiting for container logs…)")
    def render_group() -> Panel:
        return Panel(
            Group(progress, status_line, log_line),
            title="AIDA Bootstrap"
        )

    used_admin_pass: Optional[str] = None

    with Live(render_group(), console=console, refresh_per_second=10) as live:
        # Unified log file
        with open(BOOTSTRAP_LOG, "w", encoding="utf-8") as lf:
            # Phase: Reset (optional) — run asynchronously and show progress
            if do_reset:
                progress.update(task_id, description="Resetting Taiga data and local state", completed=0)
                cmd = [
                    "aida-setup", "--reset", "--force", "--yes",
                    "--admin-user", args.admin_user,
                    "--admin-email", args.admin_email,
                ]
                if args.admin_pass:
                    used_admin_pass = args.admin_pass
                else:
                    used_admin_pass = secrets.token_urlsafe(16)
                cmd.extend(["--admin-pass", used_admin_pass])
                reset_proc = subprocess.Popen(cmd, stdout=lf, stderr=lf)
                deadline = time.time() + int(args.timeout)
                while reset_proc.poll() is None and time.time() < deadline:
                    cur = min(15, int(progress.tasks[task_id].completed) + 1)
                    progress.update(task_id, completed=cur)
                    status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
                    # If migrations have begun, advance to next phase visuals even if reset still running
                    if analyzer.migrations_applied > 0 and progress.tasks[task_id].completed < 25:
                        progress.update(task_id, completed=25, description="TX1: Gateway check (GET / → 200)")
                    live.update(render_group())
                    time.sleep(0.3)
                rc_reset = reset_proc.poll()
                if rc_reset not in (0, None):
                    progress.update(task_id, completed=15, description=f"Reset failed (code {rc_reset}) — see .aida/bootstrap-start.log")
                    status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
                    live.update(render_group())
                    return 1
                progress.update(task_id, completed=15)
                status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
                live.update(render_group())

            # Phase: Start services (aida-start) with logs redirected
            progress.update(task_id, description="Starting services (Taiga + Bridge)", completed=20)
            start_proc = subprocess.Popen(["aida-start"], stdout=lf, stderr=lf)
            progress.update(task_id, completed=max(25, int(progress.tasks[task_id].completed)))
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            live.update(render_group())

        # Phase: TX1 - Gateway /
        progress.update(task_id, description="TX1: Gateway check (GET / → 200)", completed=30)
        deadline = time.time() + int(args.timeout)
        while time.time() < deadline and not readiness.root_ok:
            _poll_readiness(readiness)
            latest = _latest_line(line_queue)
            cur = min(60, progress.tasks[task_id].completed + 1)
            progress.update(task_id, completed=cur, description=f"Gateway check: / → {('200 OK' if readiness.root_ok else '...')} | {latest[-80:] if latest else ''}")
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            if latest:
                log_line = Text(f"Log: {latest[-120:]}")
            else:
                # Keep last shown line; do not revert to placeholder
                pass
            live.update(render_group())
            time.sleep(1.0)

        # Phase: TX2 - API /api/v1
        progress.update(task_id, description="TX2: API check (GET /api/v1 → 200)", completed=65)
        while time.time() < deadline and not readiness.api_ok:
            _poll_readiness(readiness)
            latest = _latest_line(line_queue)
            cur = min(85, progress.tasks[task_id].completed + 1)
            progress.update(task_id, completed=cur, description=f"API check: /api/v1 → {('200 OK' if readiness.api_ok else '...')} | {latest[-80:] if latest else ''}")
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            if latest:
                log_line = Text(f"Log: {latest[-120:]}")
            live.update(render_group())
            time.sleep(1.0)

        # Phase: TX4 - Bridge health
        progress.update(task_id, description="TX4: Bridge check (GET /health → 200)", completed=86)
        while time.time() < deadline and not readiness.bridge_ok:
            _poll_readiness(readiness)
            latest = _latest_line(line_queue)
            cur = min(95, progress.tasks[task_id].completed + 1)
            progress.update(task_id, completed=cur, description=f"Bridge check: /health → {('200' if readiness.bridge_ok else '...')} | {latest[-80:] if latest else ''}")
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            if latest:
                log_line = Text(f"Log: {latest[-120:]}")
            live.update(render_group())
            time.sleep(1.0)

        stop_event.set()

        rc = start_proc.wait()
        if not (readiness.gateway_ready and readiness.bridge_ok):
            progress.update(task_id, completed=100, description="Bootstrap finished with warnings — see .aida/bootstrap-start.log")
        elif rc != 0:
            progress.update(task_id, completed=100, description=f"aida-start exited with {rc} — see .aida/bootstrap-start.log")
        else:
            progress.update(task_id, completed=100, description="All services ready — Taiga and Bridge are up")

        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        live.update(render_group())

    console.print(f"[bold]Done in[/bold] {_elapsed_str(start_ts)}")
    console.print("Open Taiga:   http://localhost:9000")
    console.print("AIDA Bridge:  http://127.0.0.1:8787")
    console.print(f"Logs: {BOOTSTRAP_LOG}")
    if used_admin_pass:
        console.print(f"Admin account: user / {used_admin_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



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
import json
from collections import defaultdict
import random
import requests
from aidamatic.taiga.pyclient import TaigaPyClient, slugify, detect_repo_name


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
    # Treat Taiga API reachable if projects endpoint returns 200/401/403
    status_projects = _http_status(f"{GATEWAY_URL}/api/v1/projects")
    readiness.api_ok = status_projects in (200, 401, 403)
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
                # Ignore transient errors and continue polling
                pass
        # Poll interval
        time.sleep(1.0)


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
            parts.append("Gateway ready (/:200, /api/v1/projects:200/401/403); finalizing startup…")
        else:
            parts.append(self.phase)
        # Append readiness flags tersely
        flags = []
        flags.append("root=OK" if readiness.root_ok else "root=…")
        flags.append("api=ready" if readiness.api_ok else "api=…")
        return Text(f"{parts[0]}    [" + ", ".join(flags) + f"]    Elapsed {elapsed}")


def _ensure_compose_file() -> None:
    if not COMPOSE_FILE.exists():
        print(f"Compose file not found at {COMPOSE_FILE}", file=sys.stderr)
        raise SystemExit(2)


def _get_services_health() -> dict[str, str]:
    """Return service->health by parsing `docker compose ps --format json`."""
    health: dict[str, str] = {}
    try:
        p = subprocess.run([
            "docker", "compose", "-f", str(COMPOSE_FILE), "ps", "--format", "json"
        ], capture_output=True, text=True, timeout=10)
        if p.returncode != 0 or not p.stdout:
            return health
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                svc = obj.get("Service") or obj.get("Name") or ""
                h = obj.get("Health") or ""
                if svc:
                    health[svc] = h
            except Exception:
                continue
    except Exception:
        pass
    return health


def _http_probe(url: str, timeout_s: float = 3.0) -> tuple[Optional[int], Optional[int]]:
    """Return (status_code, latency_ms) for a GET probe or (None, None) on error."""
    try:
        t0 = time.time()
        resp = requests.get(url, timeout=timeout_s)
        dt = int((time.time() - t0) * 1000)
        return resp.status_code, dt
    except Exception:
        return None, None


class TokenBucket:
    def __init__(self, rate_per_s: float = 1.0, burst: int = 3) -> None:
        self.rate_per_s = max(0.001, rate_per_s)
        self.capacity = max(1.0, float(burst))
        self.tokens = self.capacity
        self.last_refill = time.time()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_s)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

def _sleep_with_jitter(base_s: float, low_ms: int = 100, high_ms: int = 300) -> None:
    jitter = random.uniform(low_ms / 1000.0, high_ms / 1000.0)
    time.sleep(max(0.0, base_s) + jitter)


def _ensure_taiga_user(username: str, password: str, email: str) -> None:
    """Create or update a Taiga user inside the taiga-back container.
    Makes the user a staff/superuser and sets the given password.
    """
    # Build a manage.py shell command executed via the container's venv
    djangocmd = (
        "cd /taiga-back && "
        "/opt/venv/bin/python manage.py shell -c \""
        "from django.contrib.auth import get_user_model; "
        "U=get_user_model(); "
        f"username={repr(username)}; email={repr(email)}; password={repr(password)}; "
        "user, _ = U.objects.get_or_create(username=username, defaults={'email': email}); "
        "user.email=email; user.is_superuser=True; user.is_staff=True; "
        "user.set_password(password); user.save(); print('OK')\""
    )
    last_err = None
    for svc in ("taiga_back", "taiga-back"):
        try:
            p = subprocess.run([
                "docker", "compose", "-f", str(COMPOSE_FILE),
                "exec", "-T", svc, "sh", "-lc", djangocmd
            ], capture_output=True, text=True, timeout=120)
            if p.returncode == 0 and "OK" in (p.stdout or ""):
                return
            last_err = f"rc={p.returncode} out={p.stdout.strip()} err={p.stderr.strip()}"
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"ensure user failed: {last_err}")


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

    # Live layout: progress bar + state + status + log + evidence
    status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
    last_log_line: str = ""
    state_name: str = "S0: Init"
    state_started: float = time.time()
    evidence_text: Text = Text("")
    backend_last_seen_ts: Optional[float] = None
    event_counters: dict[str, int] = defaultdict(int)
    http_bucket = TokenBucket(rate_per_s=1.0, burst=3)
    log_queue: "queue.Queue[str]" = queue.Queue()

    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _append_log(line: str) -> None:
        try:
            log_queue.put_nowait(f"[{_ts()}] {line}")
        except Exception:
            pass

    def _read_last_log_line() -> Optional[str]:
        try:
            p = Path(BOOTSTRAP_LOG)
            if not p.exists():
                return None
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                # Read all and take last non-empty; file is flushed per line by writer
                lines = f.readlines()
                for line in reversed(lines):
                    s = line.strip()
                    if s:
                        return s
            return None
        except Exception:
            return None

    def _log_event(state: str, key: str, **fields: object) -> None:
        attempt = event_counters.get(key, 0) + 1
        event_counters[key] = attempt
        kv = " ".join(f"{k}={fields[k]}" for k in fields)
        _append_log(f"EVENT state={state} key={key} attempt={attempt} {kv}")

    def _write_progress_json() -> None:
        try:
            prog = {
                "timestamp": _ts(),
                "state": state_name,
                "counters": dict(event_counters),
            }
            pj = Path(BOOTSTRAP_LOG).parent / "progress.json"
            with open(pj, "w", encoding="utf-8") as f:
                json.dump(prog, f, indent=2)
        except Exception:
            pass

    def _set_state(name: str) -> None:
        nonlocal state_name, state_started
        if state_name != name:
            state_name = name
            state_started = time.time()
            _append_log(f"STATE -> {name}")
            _log_event(name, "state_enter")
            _write_progress_json()

    def _fmt_evidence(s: str) -> Text:
        return Text(s)

    def _get_taiga_back_container_id() -> Optional[str]:
        try:
            p = subprocess.run([
                "docker", "compose", "-f", str(COMPOSE_FILE), "ps", "-q", "taiga-back"
            ], capture_output=True, text=True, timeout=10)
            cid = p.stdout.strip()
            return cid or None
        except Exception:
            return None

    def _taiga_back_cpu_percent(cid: Optional[str]) -> Optional[float]:
        if not cid:
            return None
        try:
            p = subprocess.run([
                "docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", cid
            ], capture_output=True, text=True, timeout=5)
            out = (p.stdout or "").strip().replace("%", "").strip()
            return float(out) if out else None
        except Exception:
            return None

    def _taiga_back_tcp_open() -> Optional[bool]:
        try:
            script = (
                "import socket,sys; s=socket.socket(); s.settimeout(1); "
                "sys.exit(0 if s.connect_ex(('127.0.0.1',8000))==0 else 1)"
            )
            p = subprocess.run([
                "docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "taiga-back",
                "python", "-c", script
            ], capture_output=True, text=True, timeout=6)
            # returncode 0 means port open
            return p.returncode == 0
        except Exception:
            return None

    def render_group() -> Panel:
        state_elapsed = int(time.time() - state_started)
        state_text = Text(f"State: {state_name} ({state_elapsed}s)")
        last_from_file = _read_last_log_line()
        log_text = Text(f"Log: {last_from_file[-120:]}") if last_from_file else Text("Log: (waiting for container logs…)")
        ev_text = evidence_text if evidence_text.plain else Text("Evidence: …")
        return Panel(
            Group(progress, state_text, status_line, ev_text, log_text),
            title="AIDA Bootstrap"
        )

    used_admin_pass: Optional[str] = None

    def _fail(rc: int) -> int:
        progress.update(task_id, completed=100, description="Bootstrap failed — see .aida/bootstrap-start.log")
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        live.update(render_group())
        return rc

    # Single writer to ensure strict ordering across threads
    def _log_writer() -> None:
        try:
            with open(BOOTSTRAP_LOG, "w", encoding="utf-8") as _f:
                while not stop_event.is_set() or not log_queue.empty():
                    try:
                        line = log_queue.get(timeout=0.5)
                    except Exception:
                        continue
                    _f.write(line + "\n")
                    _f.flush()
        except Exception:
            pass
    lw_thread = threading.Thread(target=_log_writer, daemon=True)
    lw_thread.start()

    live = Live(render_group(), console=console, refresh_per_second=10)
    live.start()

    # Unified log start markers
    _append_log("BOOTSTRAP start")
    _log_event("S0: Init", "bootstrap_start")
    _write_progress_json()
    # Phase: Reset (optional) — run asynchronously and show progress
    if do_reset:
        _set_state("S0: Reset")
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
        _append_log("RESET start")
        _log_event("S0: Reset", "reset_start")
        reset_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        reset_warned: bool = False
        def _read_reset(stream):
            nonlocal reset_warned, last_log_line, backend_last_seen_ts
            for raw in stream:
                line = raw.rstrip("\n")
                _append_log(f"RESET: {line}")
                last_log_line = line
                if "taiga-back" in line or "taiga_back" in line:
                    backend_last_seen_ts = time.time()
                if "Applying" in line and "OK" in line:
                    _log_event("S0: Reset", "migration_applied")
                    _write_progress_json()
                if line.lower().startswith("creating user "):
                    _log_event("S0: Reset", "user_seeded")
                    _write_progress_json()
                if "Identity reconcile skipped" in line or "did not become ready in time" in line:
                    reset_warned = True
        tr_out = threading.Thread(target=_read_reset, args=(reset_proc.stdout,), daemon=True)
        tr_err = threading.Thread(target=_read_reset, args=(reset_proc.stderr,), daemon=True)
        tr_out.start(); tr_err.start()
        deadline_global = time.time() + int(args.timeout)
        while reset_proc.poll() is None and time.time() < deadline_global:
            cur = min(15, int(progress.tasks[task_id].completed) + 1)
            progress.update(task_id, completed=cur)
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            latest = _latest_line(line_queue)
            if latest and latest != last_log_line:
                last_log_line = latest
                if "taiga-back" in latest or "taiga_back" in latest:
                    backend_last_seen_ts = time.time()
            if analyzer.migrations_applied > 0 and progress.tasks[task_id].completed < 25:
                progress.update(task_id, completed=25, description="Reset: migrations running")
            evidence_text = _fmt_evidence("Evidence: reset running…")
            _log_event("S0: Reset", "tick")
            _write_progress_json()
            live.update(render_group())
            time.sleep(0.3)
        rc_reset = reset_proc.poll()
        if rc_reset not in (0, None):
            progress.update(task_id, completed=15, description=f"Reset failed (code {rc_reset}) — see .aida/bootstrap-start.log")
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            evidence_text = _fmt_evidence("Evidence: reset failed")
            _append_log(f"RESET fail code={rc_reset}")
            _log_event("S0: Reset", "reset_fail", code=rc_reset)
            _write_progress_json()
            live.update(render_group())
            return _fail(1)
        if reset_warned:
            progress.update(task_id, completed=15, description="Reset failed — identity reconcile skipped (backend auth not ready)")
            status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
            _append_log("RESET fail reconcile skipped")
            _log_event("S0: Reset", "reset_fail_reconcile")
            _write_progress_json()
            live.update(render_group())
            return _fail(2)
        progress.update(task_id, completed=15)
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        _append_log("RESET complete")
        _log_event("S0: Reset", "reset_complete")
        _write_progress_json()
        live.update(render_group())

    # Phase: Start services (aida-start) with logs redirected
    _set_state("S1: Infra health")
    progress.update(task_id, description="Starting services (Taiga + Bridge)", completed=20)
    start_proc = subprocess.Popen(
        ["aida-start", "--no-reset"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    def _read_start(stream):
        nonlocal last_log_line
        for raw in stream:
            line = raw.rstrip("\n")
            _append_log(f"START: {line}")
            last_log_line = line
    ts_out = threading.Thread(target=_read_start, args=(start_proc.stdout,), daemon=True)
    ts_err = threading.Thread(target=_read_start, args=(start_proc.stderr,), daemon=True)
    ts_out.start(); ts_err.start()
    _append_log("START services")
    _log_event("S1: Infra health", "start_services")
    _write_progress_json()
    progress.update(task_id, completed=max(25, int(progress.tasks[task_id].completed)))
    status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
    latest = _latest_line(line_queue)
    if latest and latest != last_log_line:
        last_log_line = latest
        if "taiga-back" in latest or "taiga_back" in latest:
            backend_last_seen_ts = time.time()
    evidence_text = _fmt_evidence("Evidence: starting services")
    live.update(render_group())

    # S1: Infra-healthy (postgres/rabbit/redis)
    _set_state("S1: Infra health")
    progress.update(task_id, description="S1: Waiting for infra health (postgres/rabbit/redis)", completed=28)
    s1_deadline = time.time() + 180
    prev_health: dict[str, str] = {}
    while time.time() < s1_deadline:
        health = _get_services_health()
        pg = (health.get("taiga_postgres") or health.get("postgres") or "").lower()
        rb = (health.get("taiga_rabbit") or health.get("rabbit") or "").lower()
        rd = (health.get("taiga_redis") or health.get("redis") or "").lower()
        ok = ("healthy" in pg) and ("healthy" in rb) and ("healthy" in rd)
        latest = _latest_line(line_queue)
        if latest and latest != last_log_line:
            last_log_line = latest
            if "taiga-back" in latest or "taiga_back" in latest:
                backend_last_seen_ts = time.time()
        progress.update(task_id, description=f"S1: Infra health — postgres={pg or 'unknown'} rabbit={rb or 'unknown'} redis={rd or 'unknown'}", completed=30 if not ok else 35)
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        evidence_text = _fmt_evidence("Evidence: infra checks running")
        # Log transitions to healthy once per service
        for svc, status in (("postgres", pg), ("rabbit", rb), ("redis", rd)):
            if prev_health.get(svc) != status and status:
                _log_event("S1: Infra health", f"{svc}_{status}")
        prev_health = {"postgres": pg, "rabbit": rb, "redis": rd}
        _write_progress_json()
        live.update(render_group())
        if ok:
            _append_log(f"S1 infra healthy postgres={pg or 'unknown'} rabbit={rb or 'unknown'} redis={rd or 'unknown'}")
            break
        time.sleep(1.0)

    # S2: Backend starting — deterministic probes
    _set_state("S2: Backend starting")
    s2_deadline = time.time() + 300
    while time.time() < s2_deadline:
        t0 = time.time()
        tcp_open = _taiga_back_tcp_open()
        dt = int((time.time() - t0) * 1000)
        cid = _get_taiga_back_container_id()
        cpu = _taiga_back_cpu_percent(cid)
        mig = analyzer.migrations_applied
        age = int(time.time() - backend_last_seen_ts) if backend_last_seen_ts else None
        latest = _latest_line(line_queue)
        if latest and latest != last_log_line:
            last_log_line = latest
            if "taiga-back" in latest or "taiga_back" in latest:
                backend_last_seen_ts = time.time()
        ev_parts = []
        ev_parts.append(f"tcp:8000={'open' if tcp_open else 'closed' if tcp_open is not None else 'unknown'}")
        ev_parts.append(f"cpu={cpu:.1f}%" if cpu is not None else "cpu=…")
        ev_parts.append(f"migrations={mig}")
        ev_parts.append(f"backend_log_age={age}s" if age is not None else "backend_log_age=…")
        evidence_text = _fmt_evidence("Evidence: " + ", ".join(ev_parts))
        _log_event("S2: Backend starting", "tcp_check", open=bool(tcp_open) if tcp_open is not None else None, ms=dt, cpu=cpu if cpu is not None else "…", age_s=age if age is not None else "…")
        _write_progress_json()
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        progress.update(task_id, completed=max(38, int(progress.tasks[task_id].completed)))
        live.update(render_group())
        if tcp_open:
            _append_log("S2 backend tcp:8000 open")
            break
        # Stall rule: if no new backend logs for >60s and cpu low for 30s, abort early
        if (age is not None and age > 60) and (cpu is not None and cpu < 5.0):
            progress.update(task_id, description="Backend appears stalled — aborting with diagnostics")
            live.update(render_group())
            _append_log(f"S2 stall backend_log_age={age}s cpu={(cpu if cpu is not None else '…')}")
            _log_event("S2: Backend starting", "stall", age_s=age, cpu=cpu)
            _write_progress_json()
            return _fail(10)
        time.sleep(1.0)
    else:
        progress.update(task_id, description="S2 timeout — backend did not open tcp:8000")
        live.update(render_group())
        _append_log("S2 timeout no tcp:8000")
        _log_event("S2: Backend starting", "timeout")
        _write_progress_json()
        return _fail(11)

    # Phase: TX1 - Gateway /
    _set_state("S3: Gateway")
    progress.update(task_id, description="TX1: Gateway check (GET / → 200)", completed=40)
    deadline = time.time() + int(args.timeout)
    last_code_root: Optional[int] = None
    backoff_s: float = 1.0
    while time.time() < deadline and not readiness.root_ok:
        # rate-limit probes; rely on logs otherwise
        if not http_bucket.allow():
            _sleep_with_jitter(0.2)
            continue
        latest = _latest_line(line_queue)
        if latest and latest != last_log_line:
            last_log_line = latest
            if "taiga-back" in latest or "taiga_back" in latest:
                backend_last_seen_ts = time.time()
        cur = min(60, progress.tasks[task_id].completed + 1)
        code_root, ms_root = _http_probe(f"{GATEWAY_URL}/")
        if code_root is not None and code_root != last_code_root:
            _append_log(f"TX1 / -> {code_root}")
        _log_event("S3: Gateway", "http_probe", url="/", code=code_root if code_root is not None else "…", ms=ms_root if ms_root is not None else "…")
        _write_progress_json()
        last_code_root = code_root if code_root is not None else last_code_root
        code_txt = code_root if code_root is not None else "..."
        progress.update(task_id, completed=cur, description=f"TX1: / → {code_txt} | {last_log_line[-80:] if last_log_line else ''}")
        evidence_text = _fmt_evidence(f"Evidence: / → {code_txt}")
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        live.update(render_group())
        # set readiness and adaptive backoff
        if code_root == 200:
            readiness.root_ok = True
            break
        if code_root in (502, 504):
            backoff_s = max(backoff_s, 15.0)
        else:
            backoff_s = min(10.0, backoff_s * 2.0)
        _sleep_with_jitter(backoff_s)
    if not readiness.root_ok:
        progress.update(task_id, description=f"Gateway not ready — last code {last_code_root if last_code_root is not None else '…'}")
        live.update(render_group())
        _append_log(f"S3 fail last_code={last_code_root if last_code_root is not None else '…'}")
        _log_event("S3: Gateway", "fail", last_code=last_code_root if last_code_root is not None else "…")
        _write_progress_json()
        return _fail(12)

    # Phase: TX2 - API /api/v1/projects (or users fallback)
    _set_state("S4: Reconcile (API ready)")
    progress.update(task_id, description="TX2: API check (GET /api/v1/projects → 200/401/403)", completed=65)
    last_api_code: Optional[int] = None
    s4_attempts: int = 0
    s4_backoff_s: float = 1.0
    while time.time() < deadline and not readiness.api_ok:
        if not http_bucket.allow():
            _sleep_with_jitter(0.2)
            continue
        latest = _latest_line(line_queue)
        if latest and latest != last_log_line:
            last_log_line = latest
            if "taiga-back" in latest or "taiga_back" in latest:
                backend_last_seen_ts = time.time()
        cur = min(85, progress.tasks[task_id].completed + 1)
        s4_attempts += 1
        status_val, ms_proj = _http_probe(f"{GATEWAY_URL}/api/v1/projects")
        if status_val is None:
            status_val, ms_proj = _http_probe(f"{GATEWAY_URL}/api/v1/users")
        if status_val is not None and status_val != last_api_code:
            _append_log(f"TX2 /api ready -> {status_val}")
        _log_event("S4: Reconcile (API ready)", "http_probe", url="/api", code=status_val if status_val is not None else "…", ms=ms_proj if ms_proj is not None else "…")
        _write_progress_json()
        last_api_code = status_val if status_val is not None else last_api_code
        status_txt = status_val if status_val is not None else "..."
        progress.update(task_id, completed=cur, description=f"TX2: /api/v1/projects → {status_txt} | {last_log_line[-80:] if last_log_line else ''}")
        evidence_text = _fmt_evidence(f"Evidence: /api ready → {status_txt}")
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        live.update(render_group())
        if status_val in (200, 401, 403):
            readiness.api_ok = True
            break
        if s4_attempts >= 20:
            break
        # adaptive backoff with jitter
        if status_val in (502, 504):
            s4_backoff_s = max(s4_backoff_s, 15.0)
        else:
            s4_backoff_s = min(10.0, s4_backoff_s * 2.0)
        _sleep_with_jitter(s4_backoff_s)
    if not readiness.api_ok:
        progress.update(task_id, description=f"API not ready — last code {last_api_code if last_api_code is not None else '…'}")
        live.update(render_group())
        _append_log(f"S4 fail last_code={last_api_code if last_api_code is not None else '…'}")
        _log_event("S4: Reconcile (API ready)", "fail", last_code=last_api_code if last_api_code is not None else "…")
        _write_progress_json()
        return _fail(13)

    # S4: Reconcile identities and ensure project via python-taiga
    try:
        _append_log("RECONCILE start")
        client = TaigaPyClient(host=GATEWAY_URL)
        admin_user = args.admin_user if hasattr(args, "admin_user") else "user"
        admin_pass = used_admin_pass or os.environ.get("TAIGA_ADMIN_PASSWORD", "")
        auth_res = client.authenticate(admin_user, admin_pass)
        client.persist_auth("user", auth_res)
        repo_name = detect_repo_name()
        proj = client.get_or_create_project(repo_name, slugify(repo_name), enable_kanban=True)
        client.persist_identities(proj)
        _append_log(f"RECONCILE success project={proj.slug}")
        evidence_text = _fmt_evidence(f"Evidence: project={proj.slug}")
        live.update(render_group())
    except Exception as e:
        msg = str(e)
        _append_log(f"RECONCILE first attempt failed: {msg}")
        # If invalid credentials, ensure user and retry once
        if "invalid_credentials" in msg or "No active account" in msg:
            try:
                email = (args.admin_email if hasattr(args, "admin_email") and args.admin_email else f"{admin_user}@localhost")
                _append_log("ENSURE_USER start")
                _ensure_taiga_user(admin_user, admin_pass, email)
                _append_log("ENSURE_USER done; retry auth")
                client = TaigaPyClient(host=GATEWAY_URL)
                auth_res = client.authenticate(admin_user, admin_pass)
                client.persist_auth("user", auth_res)
                repo_name = detect_repo_name()
                proj = client.get_or_create_project(repo_name, slugify(repo_name), enable_kanban=True)
                client.persist_identities(proj)
                _append_log(f"RECONCILE success project={proj.slug}")
                evidence_text = _fmt_evidence(f"Evidence: project={proj.slug}")
                live.update(render_group())
            except Exception as e2:
                _append_log(f"RECONCILE fail {e2}")
                progress.update(task_id, description=f"Reconcile failed — {e2}")
                live.update(render_group())
                return _fail(15)
        else:
            _append_log(f"RECONCILE fail {e}")
            progress.update(task_id, description=f"Reconcile failed — {e}")
            live.update(render_group())
            return _fail(15)

    # Phase: TX4 - Bridge health
    _set_state("S5: Bridge")
    progress.update(task_id, description="TX4: Bridge check (GET /health → 200)", completed=86)
    last_bridge_code: Optional[int] = None
    s5_backoff_seq = [2.0, 3.0, 5.0]
    s5_idx = 0
    while time.time() < deadline and not readiness.bridge_ok:
        if not http_bucket.allow():
            _sleep_with_jitter(0.2)
            continue
        latest = _latest_line(line_queue)
        if latest and latest != last_log_line:
            last_log_line = latest
        cur = min(95, progress.tasks[task_id].completed + 1)
        code_b, ms_b = _http_probe(BRIDGE_HEALTH)
        if code_b is not None and code_b != last_bridge_code:
            _append_log(f"TX4 /health -> {code_b}")
        _log_event("S5: Bridge", "http_probe", url="/health", code=code_b if code_b is not None else "…", ms=ms_b if ms_b is not None else "…")
        _write_progress_json()
        if code_b is not None:
            last_bridge_code = code_b
        codeb_txt = code_b if code_b is not None else "..."
        progress.update(task_id, completed=cur, description=f"TX4: /health → {codeb_txt} | {last_log_line[-80:] if last_log_line else ''}")
        evidence_text = _fmt_evidence(f"Evidence: /health → {codeb_txt}")
        status_line = analyzer.render_status(_elapsed_str(start_ts), readiness)
        live.update(render_group())
        if code_b == 200:
            readiness.bridge_ok = True
            break
        s5_idx = min(s5_idx + 1, len(s5_backoff_seq) - 1)
        _sleep_with_jitter(s5_backoff_seq[s5_idx])
    if not readiness.bridge_ok:
        progress.update(task_id, description=f"Bridge not ready — last code {last_bridge_code if last_bridge_code is not None else '…'}")
        live.update(render_group())
        _append_log(f"S5 fail last_code={last_bridge_code if last_bridge_code is not None else '…'}")
        _log_event("S5: Bridge", "fail", last_code=last_bridge_code if last_bridge_code is not None else "…")
        _write_progress_json()
        return _fail(14)

    _append_log("BOOTSTRAP success")
    _log_event("S5: Bridge", "success")
    _write_progress_json()
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
    live.stop()

    console.print(f"[bold]Done in[/bold] {_elapsed_str(start_ts)}")
    console.print("Open Taiga:   http://localhost:9000")
    console.print("AIDA Bridge:  http://127.0.0.1:8787")
    console.print(f"Logs: {BOOTSTRAP_LOG}")
    if used_admin_pass:
        console.print(f"Admin account: user / {used_admin_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



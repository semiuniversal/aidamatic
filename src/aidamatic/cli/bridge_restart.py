import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AIDA_DIR = REPO_ROOT / ".aida"
PORTS_FILE = AIDA_DIR / "ports.json"
BRIDGE_PID = AIDA_DIR / "bridge.pid"
BRIDGE_LOG = AIDA_DIR / "bridge.log"


def is_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.settimeout(timeout)
		try:
			return sock.connect_ex((host, port)) == 0
		except Exception:
			return False


def load_bridge_port(default_port: int = 8787) -> int:
	try:
		import json
		data = json.loads(PORTS_FILE.read_text(encoding="utf-8"))
		return int(data.get("bridge", default_port))
	except Exception:
		return default_port


def save_bridge_port(port: int) -> None:
	try:
		import json
		AIDA_DIR.mkdir(parents=True, exist_ok=True)
		data = {}
		if PORTS_FILE.exists():
			data = json.loads(PORTS_FILE.read_text(encoding="utf-8"))
		data["bridge"] = int(port)
		PORTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
	except Exception:
		pass


def kill_if_running(pid: int) -> None:
	try:
		os.kill(pid, 0)
		os.kill(pid, signal.SIGTERM)
		time.sleep(0.2)
		try:
			os.kill(pid, signal.SIGKILL)
		except Exception:
			pass
	except Exception:
		pass


def ensure_stopped(port: int) -> None:
	# Kill by pidfile
	if BRIDGE_PID.exists():
		try:
			pid = int(BRIDGE_PID.read_text())
			kill_if_running(pid)
		except Exception:
			pass
		try:
			BRIDGE_PID.unlink()
		except Exception:
			pass
	# If port still held, attempt a generic kill using ss+lsof if available
	if is_port_open("127.0.0.1", port):
		try:
			# Linux: find pid via ss
			out = subprocess.run(["bash", "-lc", f"ss -ltnp | awk '/:{port}\\b/ {{print $NF}}'"], capture_output=True, text=True)
			text = (out.stdout or "").strip()
			import re
			m = re.search(r"pid=(\d+)", text)
			if m:
				kill_if_running(int(m.group(1)))
		except Exception:
			pass


def wait_health(port: int, timeout_s: float = 10.0) -> bool:
	import urllib.request
	start = time.time()
	while time.time() - start < timeout_s:
		try:
			with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as resp:
				if resp.status == 200:
					return True
		except Exception:
			pass
		time.sleep(0.2)
	return False


def start_bridge(port: int) -> int:
	AIDA_DIR.mkdir(parents=True, exist_ok=True)
	env = os.environ.copy()
	env["AIDA_BRIDGE_PORT"] = str(port)
	# Prefer console entry
	cmd = [sys.executable, "-m", "aidamatic.bridge.app"]
	if shutil_which("aida-bridge"):
		cmd = ["aida-bridge", "--port", str(port)]
	with BRIDGE_LOG.open("a", encoding="utf-8") as logf:
		proc = subprocess.Popen(cmd, stdout=logf, stderr=logf, env=env)
		BRIDGE_PID.write_text(str(proc.pid))
	return proc.pid


def shutil_which(name: str) -> bool:
	try:
		import shutil
		return shutil.which(name) is not None
	except Exception:
		return False


def main(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Restart AIDA Bridge deterministically and wait for health=200")
	p.add_argument("--port", type=int, default=8787, help="Bridge port (default 8787)")
	args = p.parse_args(argv or sys.argv[1:])

	port = args.port or load_bridge_port(8787)
	save_bridge_port(port)
	ensure_stopped(port)
	pid = start_bridge(port)
	ok = wait_health(port, timeout_s=12.0)
	print(f"bridge pid={pid} port={port} healthy={ok}")
	return 0 if ok else 1


if __name__ == "__main__":
	sys.exit(main())

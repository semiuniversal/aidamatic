import os
import signal
import time
import socket
from pathlib import Path
import subprocess

AIDA_DIR = Path.cwd() / ".aida"
BRIDGE_PID = AIDA_DIR / "bridge.pid"


def run(cmd):
	return subprocess.run(cmd, check=False, capture_output=True, text=True)


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.settimeout(timeout)
		try:
			return sock.connect_ex((host, port)) == 0
		except Exception:
			return False


def bridge_health_ok() -> bool:
	try:
		resp = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:8787/health"]) 
		return resp.returncode == 0 and resp.stdout.strip() == "200"
	except Exception:
		return False


def find_pid_on_port(port: int) -> int | None:
	# Try lsof, then ss
	res = run(["bash", "-lc", f"command -v lsof >/dev/null 2>&1 && lsof -ti :{port} || true"]) 
	if res.returncode == 0 and res.stdout.strip():
		try:
			return int(res.stdout.strip().splitlines()[0])
		except Exception:
			pass
	res = run(["bash", "-lc", f"command -v ss >/dev/null 2>&1 && ss -ltnp '( sport = :{port} )' || true"]) 
	if res.returncode == 0 and "pid=" in res.stdout:
		# parse pid=1234
		for token in res.stdout.split():
			if token.startswith("pid="):
				val = token.split("=",1)[1].strip('",)')
				try:
					return int(val)
				except Exception:
					continue
	return None


def kill_pid(pid: int, timeout: float = 5.0) -> None:
	try:
		os.kill(pid, signal.SIGTERM)
	except Exception:
		return
	end = time.time() + timeout
	while time.time() < end:
		try:
			os.kill(pid, 0)
			time.sleep(0.2)
		except ProcessLookupError:
			return
	# force
	try:
		os.kill(pid, signal.SIGKILL)
	except Exception:
		pass


def main() -> int:
	stopped_bridge = False
	# Stop bridge via pid file if present
	if BRIDGE_PID.exists():
		try:
			pid = int(BRIDGE_PID.read_text().strip())
			kill_pid(pid)
			BRIDGE_PID.unlink(missing_ok=True)
			stopped_bridge = True
			print("Stopped AIDA Bridge (pid file)")
		except Exception:
			pass
	# If still responding or port in use, attempt port-based kill
	if bridge_health_ok() or is_port_open("127.0.0.1", 8787):
		pid = find_pid_on_port(8787)
		if pid:
			kill_pid(pid)
			stopped_bridge = True
			print(f"Stopped AIDA Bridge (port pid={pid})")
	# Wait until closed
	deadline = time.time() + 5
	while time.time() < deadline and (bridge_health_ok() or is_port_open("127.0.0.1", 8787)):
		time.sleep(0.2)
	# Bring Taiga down
	run(["aida-taiga-down"])  
	print("Taiga stack stopped")
	if not stopped_bridge:
		print("Bridge was not running or already stopped")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

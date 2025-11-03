import os
import sys
import json
import time
import socket
import getpass
import subprocess
from urllib.request import urlopen
from urllib.error import URLError
from pathlib import Path
from typing import Optional

AIDA_DIR = Path.cwd() / ".aida"
DOCKER_ENV = Path.cwd() / "docker" / ".env"
ENV_EXAMPLE = Path.cwd() / "docker" / "env.example"
BRIDGE_PID = AIDA_DIR / "bridge.pid"
BRIDGE_LOG = AIDA_DIR / "bridge.log"
STATUS_MAP = AIDA_DIR / "status-map.json"

DEFAULT_STATUS_MAP = {
	"issue": {"in_progress": "In progress", "review": "Ready for test", "done": "Done", "blocked": "Blocked"},
	"userstory": {"in_progress": "In progress", "review": "Ready for test", "done": "Done", "blocked": "Blocked"},
	"task": {"in_progress": "In progress", "review": "Ready for test", "done": "Done", "blocked": "Blocked"},
}


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
	return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def system_running() -> bool:
	try:
		r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:9000/"], capture_output=True, text=True)
		if r.returncode == 0 and r.stdout.strip() == "200":
			return True
	except Exception:
		pass
	try:
		p = run(["docker", "compose", "-f", "docker/docker-compose.yml", "ps"], capture=True)
		return "taiga_gateway" in p.stdout and "Up" in p.stdout
	except Exception:
		return False


def prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
	suffix = "[Y/n]" if default_yes else "[y/N]"
	ans = input(f"{prompt} {suffix} ").strip().lower()
	if not ans:
		return default_yes
	return ans.startswith("y")


def ensure_env_with_port() -> None:
	DOCKER_ENV.parent.mkdir(parents=True, exist_ok=True)
	if not DOCKER_ENV.exists():
		content = ENV_EXAMPLE.read_text() if ENV_EXAMPLE.exists() else ""
		DOCKER_ENV.write_text(content)
	def set_kv(key: str, val: str) -> None:
		lines = DOCKER_ENV.read_text().splitlines()
		found = False
		for i, line in enumerate(lines):
			if line.startswith(f"{key}="):
				lines[i] = f"{key}={val}"
				found = True
				break
		if not found:
			lines.append(f"{key}={val}")
		DOCKER_ENV.write_text("\n".join(lines) + "\n")
	set_kv("TAIGA_SITES_DOMAIN", "localhost:9000")
	set_kv("TAIGA_SITES_SCHEME", "http")
	set_kv("TAIGA_FRONTEND_URL", "http://localhost:9000")
	set_kv("TAIGA_BACKEND_URL", "http://localhost:9000/api/v1")
	set_kv("TAIGA_EVENTS_URL", "ws://localhost:9000/events")


def ensure_status_map() -> None:
	if not STATUS_MAP.exists():
		AIDA_DIR.mkdir(parents=True, exist_ok=True)
		STATUS_MAP.write_text(json.dumps(DEFAULT_STATUS_MAP, indent=2))


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.settimeout(timeout)
		try:
			return sock.connect_ex((host, port)) == 0
		except Exception:
			return False


def bridge_responding() -> bool:
	try:
		with urlopen("http://127.0.0.1:8787/health", timeout=0.8) as resp:
			return resp.status == 200
	except Exception:
		return False


def wait_for_bridge(timeout_seconds: int = 20) -> bool:
	deadline = time.time() + timeout_seconds
	while time.time() < deadline:
		if bridge_responding():
			return True
		time.sleep(0.5)
	return False


def start_bridge_background() -> None:
	AIDA_DIR.mkdir(parents=True, exist_ok=True)
	if bridge_responding():
		return
	if is_port_open("127.0.0.1", 8787):
		if not prompt_yes_no("Port 8787 is in use but the bridge did not respond. Continue without starting the bridge?", default_yes=False):
			print("Aborted.")
			sys.exit(1)
		return
	if BRIDGE_PID.exists():
		try:
			pid = int(BRIDGE_PID.read_text().strip())
			os.kill(pid, 0)
			return
		except Exception:
			try:
				BRIDGE_PID.unlink()
			except Exception:
				pass
	with open(BRIDGE_LOG, "a", encoding="utf-8") as logf:
		proc = subprocess.Popen([sys.executable, "-m", "aidamatic.bridge.app"], stdout=logf, stderr=logf)
		BRIDGE_PID.write_text(str(proc.pid))
	if not wait_for_bridge():
		print("Warning: AIDA Bridge did not become ready on http://127.0.0.1:8787/health within timeout.")


def main() -> int:
	print("AIDA start\n")
	if system_running():
		print("Taiga appears to be running. Continuing without reset...")

	ensure_env_with_port()
	ensure_status_map()

	admin_user: Optional[str] = None
	admin_email: Optional[str] = None
	admin_pass: Optional[str] = None

	# Safe start: never prompt to reset here; use `aida-setup --reset` instead
	if not system_running():
		print("\nStarting Taiga stack...")
		run(["aida-taiga-up"])  # prints URLs
		try:
			wait_timeout = os.environ.get("AIDA_TAIGA_WAIT", "180")
			run(["aida-taiga-wait", "--timeout", wait_timeout])
		except Exception:
			pass

	# Ensure auth uses the same credentials we just created
	if admin_user and admin_pass:
		os.environ["TAIGA_ADMIN_USER"] = admin_user
		os.environ["TAIGA_ADMIN_PASSWORD"] = admin_pass

	# Seed ide profile from default auth/token if present (non-destructive)
	try:
		base = Path.cwd() / ".aida"
		base.mkdir(parents=True, exist_ok=True)
		default_auth = base / "auth.json"
		ide_auth = base / "auth.ide.json"
		if default_auth.exists() and not ide_auth.exists():
			ide_auth.write_text(default_auth.read_text())
			root = Path.cwd()
			tkn = root / ".taiga_token"
			ide_tkn = root / ".taiga_token.ide"
			if tkn.exists() and not ide_tkn.exists():
				ide_tkn.write_text(tkn.read_text())
			# update identities.json with username/email
			try:
				data = json.loads(default_auth.read_text() or "{}")
				ident_path = base / "identities.json"
				ident = {}
				if ident_path.exists():
					ident = json.loads(ident_path.read_text() or "{}")
				ide = ident.get("ide") or {}
				if data.get("username"): ide["username"] = data.get("username")
				if data.get("email"): ide["email"] = data.get("email")
				ident["ide"] = ide
				ident_path.write_text(json.dumps(ident, indent=2))
			except Exception:
				pass
	except Exception:
		pass

	print("\nAuthenticating to Taiga (cached profiles)...")
	try:
		ident_path = Path.cwd() / ".aida" / "identities.json"
		if ident_path.exists():
			ident = json.loads(ident_path.read_text())
			ide_node = (ident.get("ide") or ident.get("developer") or {})
			ide_user = ide_node.get("username")
			ide_pass = ide_node.get("password")
			if ide_user and ide_pass:
				os.environ["TAIGA_ADMIN_USER"] = ide_user
				os.environ["TAIGA_ADMIN_PASSWORD"] = ide_pass
				run(["aida-taiga-auth", "--profile", "ide", "--activate", "--switch-user"])  # activate ide
			scr_user = (ident.get("scrum") or {}).get("username")
			scr_pass = (ident.get("scrum") or {}).get("password")
			if scr_user and scr_pass:
				os.environ["TAIGA_ADMIN_USER"] = scr_user
				os.environ["TAIGA_ADMIN_PASSWORD"] = scr_pass
				run(["aida-taiga-auth", "--profile", "scrum", "--switch-user"])  # background profile
		else:
			print("No cached identities found. Run: aida-setup --init")
	except subprocess.CalledProcessError:
		print("Authentication failed using cached identities. Run: aida-setup --init")


	print("Starting AIDA Bridge on http://127.0.0.1:8787 ...")
	start_bridge_background()

	print("\nDone. Useful commands:")
	print("  aida-projects-list        # list your projects")
	print("  aida-items-list --type issue --assigned-to-me")
	print("  aida-item --comment 'Hello' ; aida-item --status to=in_progress")
	print("  aida-sync                 # push comment/status to Taiga")
	print("\nOpen Taiga:   http://localhost:9000")
	print("AIDA Bridge:  http://127.0.0.1:8787")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

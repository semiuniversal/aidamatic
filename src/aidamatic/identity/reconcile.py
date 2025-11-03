import json
import os
import random
import string
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

AIDA_DIR = Path(".aida")
IDENTITIES_FILE = AIDA_DIR / "identities.json"
AUTH_DIR = AIDA_DIR

DEFAULT_GATEWAY = os.environ.get("TAIGA_BASE_URL", "http://localhost:9000")
DOCKER_COMPOSE_FILE = str(Path("docker") / "docker-compose.yml")


def _load_identities() -> Dict[str, Dict[str, str]]:
	if not IDENTITIES_FILE.exists():
		return {}
	return json.loads(IDENTITIES_FILE.read_text())


def wait_for_backend_ready(timeout_seconds: int = 360, interval_seconds: int = 3) -> None:
	"""Block until taiga-back auth endpoint responds with 401 (ready)."""
	deadline = time.time() + timeout_seconds
	cmd = [
		"docker", "compose", "-f", DOCKER_COMPOSE_FILE,
		"exec", "-T", "taiga-back",
		"curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
		"http://127.0.0.1:8000/api/v1/auth",
	]
	while time.time() < deadline:
		proc = subprocess.run(cmd, capture_output=True, text=True)
		if proc.returncode == 0 and proc.stdout.strip() == "401":
			return
		time.sleep(interval_seconds)
	raise RuntimeError("Taiga backend auth endpoint did not become ready in time")


def _rand_password(length: int = 16) -> str:
	alphabet = string.ascii_letters + string.digits
	return "".join(random.choice(alphabet) for _ in range(length))


def _ensure_user_in_backend(username: str, email: str, password: str) -> None:
	cmd = [
		"docker", "compose", "-f", DOCKER_COMPOSE_FILE, "exec", "-T", "taiga-back", "sh", "-lc",
		"/opt/venv/bin/python manage.py shell -c \"from django.contrib.auth import get_user_model as g; U=g();\n"
		"u,_=U.objects.get_or_create(username=\\\"%s\\\", defaults={\\\"email\\\":\\\"%s\\\"});\n" % (username, email) +
		"u.is_active=True; u.set_password(\\\"%s\\\"); u.save(); print(\\\"ok\\\")\"" % password,
	]
	subprocess.run(cmd, check=True)


def _auth_token(base_url: str, username: str, password: str) -> Optional[str]:
	import requests  # local import to avoid hard dep if unused
	resp = requests.post(
		f"{base_url}/api/v1/auth",
		headers={"Content-Type": "application/json"},
		json={"type": "normal", "username": username, "password": password},
		timeout=10,
	)
	if resp.ok:
		return (resp.json() or {}).get("auth_token")
	return None


def _write_auth_profile(profile: str, base_url: str, token: str, username: str) -> None:
	AUTH_DIR.mkdir(parents=True, exist_ok=True)
	(auth_path := AUTH_DIR / f"auth.{profile}.json").write_text(
		json.dumps({
			"profile": profile,
			"base_url": base_url,
			"token": token,
			"username": username,
		}, indent=2)
	)


def reconcile_and_verify(profiles: Tuple[str, ...] = ("ide", "scrum"), base_url: Optional[str] = None) -> None:
	"""Ensure non-human identities exist with cached passwords and cache fresh tokens.

	- Reads .aida/identities.json for username/email/password per profile (ide/scrum)
	- Creates/updates users in Taiga with those passwords
	- Authenticates via gateway and writes .aida/auth.<profile>.json
	"""
	base = base_url or DEFAULT_GATEWAY
	wait_for_backend_ready()
	identities = _load_identities()
	for profile in profiles:
		meta = identities.get(profile, {})
		username = meta.get("username", profile)
		email = meta.get("email", f"{profile}@local")
		password = meta.get("password") or _rand_password()
		# Keep generated password in identities.json if missing
		if "password" not in meta:
			meta["password"] = password
			identities[profile] = meta
			AIDA_DIR.mkdir(parents=True, exist_ok=True)
			IDENTITIES_FILE.write_text(json.dumps(identities, indent=2))

		_ensure_user_in_backend(username=username, email=email, password=password)
		token = _auth_token(base, username, password)
		if not token:
			raise RuntimeError(f"Failed to authenticate profile '{profile}' at {base}")
		_write_auth_profile(profile, base, token, username)

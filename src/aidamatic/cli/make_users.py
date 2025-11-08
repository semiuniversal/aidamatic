import argparse
import json
import os
import secrets
import string
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"
AIDA_DIR = REPO_ROOT / ".aida"


def gen_password(length: int = 16) -> str:
	alphabet = string.ascii_letters + string.digits
	return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_taiga_user(username: str, password: str, email: str) -> bool:
	"""Create Taiga user if missing (superuser/staff). Returns True if created, False if existed.
	Existing users keep their current password (no reset).
	"""
	djangocmd = (
		"cd /taiga-back && "
		"/opt/venv/bin/python manage.py shell -c \""
		"from django.contrib.auth import get_user_model; "
		"U=get_user_model(); "
		f"username={repr(username)}; email={repr(email)}; password={repr(password)}; "
		"user, created = U.objects.get_or_create(username=username, defaults={'email': email}); "
		"if created: "
		"    user.email=email; user.is_superuser=True; user.is_staff=True; user.set_password(password); user.save(); print('CREATED') "
		"else: "
		"    # keep existing password, just ensure flags and email if empty \n"
		"    changed=False \n"
		"    if not user.email: user.email=email; changed=True \n"
		"    if not user.is_superuser: user.is_superuser=True; changed=True \n"
		"    if not user.is_staff: user.is_staff=True; changed=True \n"
		"    if changed: user.save() \n"
		"    print('EXISTING')"
		"\""
	)
	last_err = None
	for svc in ("taiga_back", "taiga-back"):
		try:
			p = subprocess.run([
				"docker", "compose", "-f", str(COMPOSE_FILE),
				"exec", "-T", svc, "sh", "-lc", djangocmd
			], capture_output=True, text=True, timeout=120)
			out = (p.stdout or "").strip()
			if p.returncode == 0 and ("CREATED" in out or "EXISTING" in out):
				return "CREATED" in out
			last_err = f"rc={p.returncode} out={out} err={(p.stderr or '').strip()}"
		except Exception as e:
			last_err = str(e)
	raise SystemExit(f"ensure user failed: {last_err}")


def persist_auth_stub(username: str, password: str) -> None:
	AIDA_DIR.mkdir(parents=True, exist_ok=True)
	path = AIDA_DIR / f"auth.{username}.json"
	try:
		path.write_text(json.dumps({"username": username, "password": password}, indent=2), encoding="utf-8")
	except Exception:
		pass


def main(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Ensure Taiga users exist (ide, scrum by default)")
	p.add_argument("--users", default="ide,scrum", help="Comma-separated usernames to ensure")
	p.add_argument("--email-domain", default="localhost", help="Email domain to use for generated users")
	args = p.parse_args(argv or sys.argv[1:])

	if not COMPOSE_FILE.exists():
		print(f"Compose file not found at {COMPOSE_FILE}", file=sys.stderr)
		return 2

	users = [u.strip() for u in args.users.split(",") if u.strip()]
	for uname in users:
		pwd = gen_password(12)
		email = f"{uname}@{args.email_domain}"
		created = ensure_taiga_user(uname, pwd, email)
		if created:
			persist_auth_stub(uname, pwd)
		print(f"OK user={uname} created={created}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

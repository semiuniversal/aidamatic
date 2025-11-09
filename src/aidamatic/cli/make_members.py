import argparse
import sys
import subprocess
from pathlib import Path
import json
import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"
API = "http://localhost:9000/api/v1"
AIDA_DIR = REPO_ROOT / ".aida"


def _load_token() -> str:
	data = json.loads((AIDA_DIR / "auth.user.json").read_text(encoding="utf-8"))
	return data["token"]


def _api_get(path: str, token: str, params: dict | None = None):
	headers = {"Authorization": f"Bearer {token}"}
	r = requests.get(f"{API}{path}", headers=headers, params=params or {}, timeout=10)
	r.raise_for_status()
	return r.json()


def _resolve_role_id_by_name(project_slug: str, role_name: str) -> int | None:
	try:
		token = _load_token()
		projs = _api_get("/projects", token, params={"slug": project_slug})
		proj = projs[0] if isinstance(projs, list) and projs else None
		if not proj:
			return None
		roles = _api_get("/roles", token, params={"project": int(proj["id"])})
		for role in roles or []:
			if (role.get("name") or "").lower() == role_name.lower():
				return int(role.get("id"))
		return None
	except Exception:
		return None


def ensure_membership_via_django(project_slug: str, username: str, role_id: int) -> None:
	djangocmd = (
		"cd /taiga-back && "
		"/opt/venv/bin/python manage.py shell -c \""
		"from django.contrib.auth import get_user_model; "
		"from taiga.projects.models import Project, Membership; "
		"U=get_user_model(); "
		f"p=Project.objects.get(slug={repr(project_slug)}); "
		f"u=U.objects.get(username={repr(username)}); "
		"m=Membership.objects.filter(project=p, user=u).first(); "
		f"\nif not m: m=Membership.objects.create(project=p, user=u, role_id={int(role_id)}); changed=True \n"
		"else: \n"
		f"    changed = (m.role_id != {int(role_id)}) \n"
		f"    \nif changed: m.role_id={int(role_id)}; m.save() \n"
		"print('OK')\""
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
	raise SystemExit(f"ensure membership failed: {last_err}")


def main(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Ensure project memberships for users (defaults: ide,scrum → Back)")
	p.add_argument("--project-slug", default=Path.cwd().name, help="Project slug (default: current folder name)")
	p.add_argument("--users", default="ide,scrum", help="Comma-separated usernames to add")
	p.add_argument("--role-id", type=int, default=4, help="Role id to assign (default: 4=Back)")
	p.add_argument("--role-name", default="", help="Optional role name to resolve and use instead of --role-id")
	args = p.parse_args(argv or sys.argv[1:])

	if not COMPOSE_FILE.exists():
		print(f"Compose file not found at {COMPOSE_FILE}", file=sys.stderr)
		return 2

	role_id = args.role_id
	if args.role_name.strip():
		resolved = _resolve_role_id_by_name(args.project_slug, args.role_name.strip())
		if resolved:
			role_id = int(resolved)
		else:
			print(f"Warning: role name '{args.role_name}' not found; falling back to role_id={role_id}", file=sys.stderr)

	for uname in [u.strip() for u in args.users.split(",") if u.strip()]:
		ensure_membership_via_django(args.project_slug, uname, role_id)
		print(f"OK member={uname} role_id={role_id}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

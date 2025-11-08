import argparse
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"


def ensure_membership_via_django(project_slug: str, username: str, role_id: int) -> None:
	djangocmd = (
		"cd /taiga-back && "
		"/opt/venv/bin/python manage.py shell -c \""
		"from django.contrib.auth import get_user_model; "
		"from taiga.projects.models import Project, Membership; "
		"U=get_user_model(); "
		f"p=Project.objects.get(slug={repr(project_slug)}); "
		f"u=U.objects.get(username={repr(username)}); "
		f"m,created=Membership.objects.get_or_create(project=p, user=u, defaults={{'role_id': {int(role_id)}}}); "
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
	args = p.parse_args(argv or sys.argv[1:])

	if not COMPOSE_FILE.exists():
		print(f"Compose file not found at {COMPOSE_FILE}", file=sys.stderr)
		return 2

	for uname in [u.strip() for u in args.users.split(",") if u.strip()]:
		ensure_membership_via_django(args.project_slug, uname, args.role_id)
		print(f"OK member={uname} role_id={args.role_id}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

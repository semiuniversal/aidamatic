import argparse
import json
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
AIDA_DIR = REPO_ROOT / ".aida"
API = "http://localhost:9000/api/v1"


def load_token() -> str:
	path = AIDA_DIR / "auth.user.json"
	data = json.loads(path.read_text(encoding="utf-8"))
	return data["token"]


def api_get(path: str, token: str, params: dict | None = None) -> requests.Response:
	headers = {"Authorization": f"Bearer {token}"}
	return requests.get(f"{API}{path}", headers=headers, params=params or {}, timeout=10)


def api_post(path: str, token: str, payload: dict) -> requests.Response:
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
	return requests.post(f"{API}{path}", headers=headers, json=payload, timeout=15)


def api_patch(path: str, token: str, payload: dict) -> requests.Response:
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
	return requests.patch(f"{API}{path}", headers=headers, json=payload, timeout=15)


def get_me(token: str) -> dict:
	r = api_get("/users/me", token)
	r.raise_for_status()
	return r.json()


def get_project_by_slug(token: str, slug: str) -> dict | None:
	r = api_get("/projects", token, params={"slug": slug})
	if r.ok and isinstance(r.json(), list):
		items = r.json()
		return items[0] if items else None
	return None


def ensure_project(token: str, name: str, slug: str, set_owner: bool = True) -> dict:
	proj = get_project_by_slug(token, slug)
	if proj:
		return proj
	payload = {
		"name": name,
		"slug": slug,
		"description": name,
		"creation_template": 1,
		"is_kanban_activated": True,
		"is_backlog_activated": True,
		"is_wiki_activated": True,
		"is_issues_activated": True,
	}
	r = api_post("/projects", token, payload)
	if not r.ok:
		raise SystemExit(f"project create failed {r.status_code}: {r.text}")
	proj = r.json()
	if set_owner:
		me = get_me(token)
		api_patch(f"/projects/{proj['id']}", token, {"owner": int(me["id"])})
	return proj


def main(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Ensure a Taiga project exists for the current folder")
	p.add_argument("--name", default=Path.cwd().name, help="Project name")
	p.add_argument("--slug", default=Path.cwd().name, help="Project slug")
	p.add_argument("--no-set-owner", action="store_true", help="Do not set owner to current user")
	args = p.parse_args(argv or sys.argv[1:])

	token = load_token()
	proj = ensure_project(token, args.name, args.slug, set_owner=(not args.__dict__["--no-set-owner"] if False else (not args.no_set_owner)))
	print(json.dumps(proj, indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())

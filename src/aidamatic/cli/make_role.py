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


def get_project_by_slug(token: str, slug: str) -> dict | None:
	r = api_get("/projects", token, params={"slug": slug})
	if r.ok and isinstance(r.json(), list):
		items = r.json()
		return items[0] if items else None
	return None


def get_roles(token: str, project_id: int) -> list:
	r = api_get("/roles", token, params={"project": project_id})
	return r.json() if r.ok else []


def ensure_role(token: str, project_id: int, target_name: str, source_name: str = "Back") -> dict:
	roles = get_roles(token, project_id)
	for role in roles:
		if (role.get("name") or "").lower() == target_name.lower():
			return role
	# Find source for permissions
	source = None
	for role in roles:
		if (role.get("name") or "").lower() == source_name.lower():
			source = role
			break
	if source is None and roles:
		# fallback: pick first non-owner/admin
		source = next((r for r in roles if "owner" not in (r.get("name") or "").lower() and "admin" not in (r.get("name") or "").lower()), roles[0])
	payload = {"project": project_id, "name": target_name}
	if isinstance(source, dict) and "permissions" in source:
		payload["permissions"] = source["permissions"]
	r = api_post("/roles", token, payload)
	if r.ok:
		return r.json()
	# Fallback: rename Stakeholder to target_name
	stake = next((r for r in roles if (r.get("name") or "").lower() == "stakeholder"), None)
	if stake is not None:
		r2 = api_patch(f"/roles/{int(stake['id'])}", token, {"name": target_name})
		if r2.ok:
			return {**stake, "name": target_name}
	raise SystemExit(f"failed to ensure role '{target_name}': {r.status_code} {r.text}")


def main(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Ensure a role exists for a project (idempotent)")
	p.add_argument("--project-slug", default=Path.cwd().name, help="Project slug (default: current folder)")
	p.add_argument("--name", default="Scrum", help="Target role name to ensure")
	p.add_argument("--source", default="Back", help="Source role name to copy permissions from when creating")
	args = p.parse_args(argv or sys.argv[1:])

	token = load_token()
	proj = get_project_by_slug(token, args.project_slug)
	if not proj:
		raise SystemExit(f"project not found for slug: {args.project_slug}")
	role = ensure_role(token, int(proj["id"]), args.name, args.source)
	print(json.dumps(role, indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())

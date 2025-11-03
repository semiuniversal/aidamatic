import argparse
import json
import os
import re
import subprocess
import sys
from typing import Tuple

from aidamatic.taiga.client import TaigaClient


def slugify(name: str) -> str:
	name = name.strip().lower()
	name = re.sub(r"[^a-z0-9-]+", "-", name)
	name = re.sub(r"-+", "-", name).strip("-")
	return name or "project"


def _git(cmd: list[str]) -> str:
	try:
		out = subprocess.run(["git", *cmd], check=True, capture_output=True, text=True)
		return out.stdout.strip()
	except Exception:
		return ""


def infer_project_from_context() -> Tuple[str, str]:
	"""Infer (name, slug) from git remote or folder without scanning IDE internals."""
	# 1) Try remote.origin.url repo name
	remote = _git(["config", "--get", "remote.origin.url"]) or ""
	repo = ""
	if remote:
		# handles git@host:org/name.git or https://host/org/name.git
		repo = remote.rsplit("/", 1)[-1]
		repo = repo[:-4] if repo.endswith(".git") else repo
	# 2) Try git top-level folder
	top = _git(["rev-parse", "--show-toplevel"]) or ""
	folder_from_git = os.path.basename(top) if top else ""
	# 3) Fallback to cwd folder
	cwd_folder = os.path.basename(os.getcwd())

	name = repo or folder_from_git or cwd_folder or "Project"
	slug = slugify(name)
	return name, slug


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Create a new Kanban project based on the current folder or git repo")
	p.add_argument("--name", help="Project name (default: inferred from git/cwd)", required=False)
	p.add_argument("--slug", help="Project slug (default: inferred)", required=False)
	p.add_argument("--public", action="store_true", help="Make project public (default: private)")
	return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	inferred_name, inferred_slug = infer_project_from_context()
	name = args.name or inferred_name
	slug = args.slug or inferred_slug
	is_private = not args.public

	client = TaigaClient.from_env()
	existing = client.get_project_by_slug(slug)
	if existing:
		print(f"Project already exists: {existing.get('name')} ({existing.get('slug')}) id={existing.get('id')}")
		return 0
	created = client.create_project(
		name=name,
		slug=slug,
		is_private=is_private,
		description=f"Project for folder {os.path.basename(os.getcwd())}",
		is_kanban=True,
	)
	print(f"Created project: {created.get('name')} ({created.get('slug')}) id={created.get('id')}")

	# Add ide and scrum users as members if identities.json is present
	try:
		ident_path = os.path.join(os.getcwd(), ".aida", "identities.json")
		if os.path.isfile(ident_path):
			ident = json.load(open(ident_path, "r", encoding="utf-8"))
			proj_id = int(created.get("id"))
			roles = client.get_roles(proj_id) or []
			role_id = None
			for r in roles:
				if (r.get("name") or "").lower() == "member":
					role_id = int(r.get("id")); break
			if role_id is None and roles:
				role_id = int(roles[0].get("id"))
			for key in ("ide", "scrum", "developer"):
				u = (ident.get(key) or {}).get("username")
				if not u or role_id is None:
					continue
				user = client.get_user_by_username(u)
				if user:
					client.create_membership(proj_id, int(user.get("id")), role_id)
					print(f"Added {key} '{u}' to project {slug}")
	except Exception:
		pass

	return 0


if __name__ == "__main__":
	sys.exit(main())

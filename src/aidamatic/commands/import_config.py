import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from aidamatic.taiga.client import TaigaClient


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Import/provision Taiga project from JSON config")
	p.add_argument("--input", default="taiga-config.json", help="Input file path")
	p.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
	return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	data = json.loads(Path(args.input).read_text(encoding="utf-8"))
	project = (data or {}).get("project", {})
	name = project.get("name")
	slug = project.get("slug")
	is_private = bool(project.get("is_private", True))
	description = project.get("description") or ""

	client = TaigaClient.from_env()
	existing = client.get_project_by_slug(slug) if slug else None

	plan: Dict[str, Any] = {
		"exists": bool(existing),
		"create_project": not bool(existing),
		"name": name,
		"slug": slug,
		"is_private": is_private,
	}
	print(json.dumps({"plan": plan}, indent=2))

	if args.apply:
		if existing:
			print("Project exists; no create needed.")
		else:
			created = client.create_project(name=name, slug=slug, is_private=is_private, description=description)
			print(json.dumps({"created": {"id": created.get("id"), "slug": created.get("slug"), "name": created.get("name")}}, indent=2))

	return 0


if __name__ == "__main__":
	sys.exit(main())

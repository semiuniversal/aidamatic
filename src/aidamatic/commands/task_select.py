import argparse
import json
import os
import sys

from aidamatic.assignment import save_assignment
from aidamatic.taiga.client import TaigaClient, ENV_BASE, DEFAULT_BASE_URL


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Select current project and persist to .aida/assignment.json")
	g = p.add_mutually_exclusive_group(required=True)
	g.add_argument("--slug", help="Project slug")
	g.add_argument("--id", type=int, help="Project id")
	p.add_argument("--tag", help="Validate that project includes this tag (optional)")
	return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	client = TaigaClient.from_env()
	proj = None
	if args.slug:
		proj = client.get_project_by_slug(args.slug)
		if not proj:
			raise SystemExit(f"Project slug not found: {args.slug}")
	else:
		resp = client.get(f"/api/v1/projects/{args.id}")
		resp.raise_for_status()
		proj = resp.json()

	if args.tag:
		tags = proj.get("tags") or []
		if args.tag not in tags:
			raise SystemExit(f"Project missing required tag '{args.tag}': {tags}")

	base_url = os.environ.get(ENV_BASE, DEFAULT_BASE_URL)
	path = save_assignment(project_id=int(proj["id"]), slug=str(proj.get("slug")), name=str(proj.get("name")), base_url=base_url)
	print(json.dumps({"selected": {"id": proj["id"], "slug": proj.get("slug"), "name": proj.get("name"), "file": path}}, indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())

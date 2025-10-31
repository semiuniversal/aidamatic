import argparse
import json
import os
import sys
from typing import Any, Dict

from aidamatic.taiga.client import TaigaClient
from aidamatic.taiga.models import TaigaExport, build_project_config


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Export Taiga project configuration to JSON")
	p.add_argument("--slug", help="Project slug to export", required=False)
	p.add_argument("--id", type=int, help="Project id to export", required=False)
	p.add_argument("--output", default="taiga-config.json", help="Output file path")
	p.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
	return p.parse_args(argv)


def resolve_project(client: TaigaClient, slug: str | None, proj_id: int | None) -> Dict[str, Any]:
	if slug:
		proj = client.get_project_by_slug(slug)
		if not proj:
			raise SystemExit(f"Project with slug '{slug}' not found")
		return proj
	if proj_id is not None:
		resp = client.get(f"/api/v1/projects/{proj_id}")
		resp.raise_for_status()
		return resp.json()
	# Fallback: pick the first project (for quick smoke testing)
	projects = client.list_projects()
	if not projects:
		raise SystemExit("No projects found")
	return projects[0]


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	client = TaigaClient.from_env()

	proj = resolve_project(client, args.slug, args.id)
	pid = int(proj.get("id"))
	memberships = client.get_memberships(pid)
	issue_statuses = client.get_issue_statuses(pid)
	issue_types = client.get_issue_types(pid)
	us_statuses = client.get_userstory_statuses(pid)

	export = TaigaExport(project=build_project_config(proj, memberships, issue_statuses, issue_types, us_statuses))
	data = export.model_dump(mode="json")

	os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
	with open(args.output, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2 if args.pretty else None, ensure_ascii=False)
	print(f"Wrote {args.output}")
	return 0


if __name__ == "__main__":
	sys.exit(main())

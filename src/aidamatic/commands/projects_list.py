import argparse
import json
import sys
from typing import List

from aidamatic.taiga.client import TaigaClient


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="List Taiga projects (identity-scoped, active-only by default)")
	p.add_argument("--all", action="store_true", help="Include archived projects")
	p.add_argument("--json", action="store_true", help="Output JSON instead of table")
	p.add_argument("--tag", help="Filter by tag (client-side contains)", required=False)
	return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	client = TaigaClient.from_env()
	me = client.get_me()
	projects = client.list_projects_filtered(member_id=me.get("id"), is_archived=None if args.all else False)
	if args.tag:
		projects = [p for p in projects if args.tag in (p.get("tags") or [])]
	if args.json:
		print(json.dumps(projects, indent=2))
		return 0
	# table
	rows: List[str] = []
	rows.append("ID\tSLUG\tNAME\tARCHIVED")
	for p in projects:
		rows.append(f"{p.get('id')}\t{p.get('slug')}\t{p.get('name')}\t{p.get('is_archived')}")
	print("\n".join(rows))
	return 0


if __name__ == "__main__":
	sys.exit(main())

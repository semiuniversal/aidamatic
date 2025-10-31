import argparse
import json
import sys
from typing import List

from aidamatic.assignment import load_assignment
from aidamatic.taiga.client import TaigaClient


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="List items in the selected project (identity-scoped by default)")
	p.add_argument("--type", choices=["issue", "userstory", "task"], default="issue")
	p.add_argument("--assigned-to-me", action="store_true", help="Only items assigned to me")
	p.add_argument("--json", action="store_true", help="Output JSON")
	return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	assignment = load_assignment()
	if not assignment:
		raise SystemExit("No assignment selected. Run aida-task-select.")
	client = TaigaClient.from_env()
	me = client.get_me()
	params = {"project": assignment.project_id}
	if args.assigned_to_me:
		params["assigned_to"] = me.get("id")
	endpoint = {
		"issue": "/api/v1/issues",
		"userstory": "/api/v1/userstories",
		"task": "/api/v1/tasks",
	}[args.type]
	resp = client.get(endpoint, params=params)
	resp.raise_for_status()
	items = resp.json() if isinstance(resp.json(), list) else []
	if args.json:
		print(json.dumps(items, indent=2))
		return 0
	rows: List[str] = []
	rows.append("ID\tREF\tSUBJECT\tASSIGNEE")
	for it in items:
		assignee = (it.get("assigned_to_extra_info") or {}).get("username") if isinstance(it.get("assigned_to_extra_info"), dict) else it.get("assigned_to")
		rows.append(f"{it.get('id')}\t{it.get('ref')}\t{it.get('subject')}\t{assignee}")
	print("\n".join(rows))
	return 0


if __name__ == "__main__":
	sys.exit(main())

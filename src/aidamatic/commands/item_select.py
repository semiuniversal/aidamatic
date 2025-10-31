import argparse
import json
import os
import sys

from aidamatic.assignment import save_assignment, load_assignment
from aidamatic.taiga.client import TaigaClient, ENV_BASE, DEFAULT_BASE_URL


def parse_args(argv: list[str]) -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Select an item in the current project")
	p.add_argument("--type", choices=["issue", "userstory", "task"], required=True)
	g = p.add_mutually_exclusive_group(required=True)
	g.add_argument("--id", type=int, help="Item id")
	g.add_argument("--ref", type=int, help="Item ref (per-project reference)")
	return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv or sys.argv[1:])
	assignment = load_assignment()
	if not assignment:
		print("No assignment selected. Run aida-task-select.", file=sys.stderr)
		return 1
	client = TaigaClient.from_env()
	endpoint = {
		"issue": "/api/v1/issues",
		"userstory": "/api/v1/userstories",
		"task": "/api/v1/tasks",
	}[args.type]
	params = {"project": assignment.project_id}
	if args.id is not None:
		item_resp = client.get(f"{endpoint}/{args.id}")
		if item_resp.status_code == 404:
			print(f"Item not found by id {args.id}", file=sys.stderr)
			return 1
		if not item_resp.ok:
			print(f"Failed to fetch item id {args.id}: {item_resp.status_code}", file=sys.stderr)
			try:
				print(item_resp.text, file=sys.stderr)
			except Exception:
				pass
			return 1
		item = item_resp.json()
	else:
		params["ref"] = args.ref
		resp = client.get(endpoint, params=params)
		if not resp.ok:
			print(f"Failed to query items by ref {args.ref}: {resp.status_code}", file=sys.stderr)
			try:
				print(resp.text, file=sys.stderr)
			except Exception:
				pass
			return 1
		candidates = [i for i in resp.json() if i.get("ref") == args.ref]
		if not candidates:
			print(f"Item not found by ref {args.ref}", file=sys.stderr)
			return 1
		item = candidates[0]

	base_url = os.environ.get(ENV_BASE, DEFAULT_BASE_URL)
	path = save_assignment(
		project_id=assignment.project_id,
		slug=assignment.slug,
		name=assignment.name,
		base_url=base_url,
		item_type=args.type,
		item_id=int(item.get("id")),
		item_ref=int(item.get("ref") or 0) if item.get("ref") is not None else None,
		item_subject=str(item.get("subject")) if item.get("subject") is not None else None,
	)
	print(json.dumps({"selected_item": {"type": args.type, "id": item.get("id"), "ref": item.get("ref"), "subject": item.get("subject"), "file": path}}, indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())

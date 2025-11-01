import argparse
import json
import os
import subprocess
import sys
from typing import Optional

import requests

BRIDGE = os.environ.get("AIDA_BRIDGE", "http://127.0.0.1:8787")


def main(argv: Optional[list[str]] = None) -> int:
	p = argparse.ArgumentParser(description="Suggest and optionally select the next task (safe confirm)")
	p.add_argument("--type", default="issue", choices=["issue"], help="Item type (default: issue)")
	p.add_argument("--profile", default="developer", help="Profile to consider as 'me' (default: developer)")
	p.add_argument("--yes", action="store_true", help="Auto-confirm selection without prompting")
	p.add_argument("--json", action="store_true", help="Output suggestion JSON and exit (no prompt)")
	args = p.parse_args(argv or sys.argv[1:])

	url = f"{BRIDGE}/task/next"
	r = requests.get(url, params={"item_type": args.type, "profile": args.profile})
	if r.status_code == 404:
		print("No suitable next item. Adjust Taiga or create work.", file=sys.stderr)
		return 1
	if not r.ok:
		print(r.text, file=sys.stderr)
		r.raise_for_status()
	sug = r.json()
	if args.json:
		print(json.dumps(sug, indent=2))
		return 0
	print(f"Next candidate: [{sug.get('item_type')}] id={sug.get('id')} ref={sug.get('ref')} status={sug.get('status')}\n  {sug.get('subject')}")
	if not args.yes:
		resp = input("Proceed to select this item? [Y/n] ").strip().lower()
		if resp and not resp.startswith("y"):
			print("Aborted.")
			return 0
	# Select via existing CLI
	item_id = str(sug.get("id"))
	cmd = [sys.executable, "-m", "aidamatic.commands.item_select", "--type", args.type, "--id", item_id]
	# Fallback to console script if available
	try:
		return subprocess.call(["aida-item-select", "--type", args.type, "--id", item_id])
	except FileNotFoundError:
		return subprocess.call(cmd)


if __name__ == "__main__":
	sys.exit(main())


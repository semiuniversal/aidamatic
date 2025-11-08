import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run(cmd: list[str]) -> None:
	res = subprocess.run(cmd, check=True)
	if res.returncode != 0:
		raise subprocess.CalledProcessError(res.returncode, cmd)


def compose(args: list[str]) -> None:
	root = Path.cwd()
	compose_file = root / "docker" / "docker-compose.yml"
	cmd = ["docker", "compose", "-f", str(compose_file)] + args
	run(cmd)


def system_running() -> bool:
	try:
		ping = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:9000/"], capture_output=True, text=True)
		return ping.stdout.strip() == "200"
	except Exception:
		return False


def bind_cached_identities() -> None:
	ident_path = Path.cwd() / ".aida" / "identities.json"
	if not ident_path.exists():
		print("No cached identities found. Bootstrap will handle reconcile.")
		return
	try:
		json.loads(ident_path.read_text())
	except Exception:
		print("Invalid identities.json; ignoring.")


def do_init() -> int:
	if not system_running():
		print("Starting Taiga stack (compose up -d)...")
		compose(["up", "-d"])
	print("Initialization complete. Use aida-bootstrap for full startup.")
	return 0


def do_reset(args) -> int:
	if not args.force:
		print("Refusing to reset without --force. This is a destructive operation.")
		return 1
	if not getattr(args, "yes", False):
		confirm = input("Type RESET to confirm destructive reset: ").strip()
		if confirm != "RESET":
			print("Reset aborted.")
			return 1
	print("\nPerforming full reset (docker compose down -v; up -d)...")
	try:
		compose(["down", "-v"])  # destructive: removes volumes
		compose(["up", "-d"])    # start fresh stack
		print("Reset complete.")
		return 0
	except subprocess.CalledProcessError as e:
		print(f"Reset failed: {e}")
		return 1


def main() -> int:
	parser = argparse.ArgumentParser(prog="aida-setup", description="Initialize or reset AIDA environment safely")
	sub = parser.add_mutually_exclusive_group()
	sub.add_argument("--init", action="store_true", help="Non-destructive initialization (default)")
	sub.add_argument("--reset", action="store_true", help="Destructive reset (requires --force and confirmation)")
	parser.add_argument("--force", action="store_true", help="Required for --reset")
	parser.add_argument("--yes", action="store_true", help="Skip interactive confirmations (for automation)")
	parser.add_argument("--admin-user", help="(unused) kept for compatibility", default=None)
	parser.add_argument("--admin-email", help="(unused) kept for compatibility", default=None)
	parser.add_argument("--admin-pass", help="(unused) kept for compatibility", default=None)
	args = parser.parse_args()
	if args.reset:
		return do_reset(args)
	return do_init()


if __name__ == "__main__":
	sys.exit(main())

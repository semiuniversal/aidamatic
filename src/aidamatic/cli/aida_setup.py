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


def system_running() -> bool:
	try:
		ping = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:9000/"], capture_output=True, text=True)
		return ping.stdout.strip() == "200"
	except Exception:
		return False


def bind_cached_identities() -> None:
	ident_path = Path.cwd() / ".aida" / "identities.json"
	if not ident_path.exists():
		print("No cached identities found. To bootstrap identities, run: aida-setup --reset")
		return
	try:
		ident = json.loads(ident_path.read_text())
		dev_user = (ident.get("developer") or {}).get("username")
		dev_pass = (ident.get("developer") or {}).get("password")
		if dev_user and dev_pass:
			os.environ["TAIGA_ADMIN_USER"] = dev_user
			os.environ["TAIGA_ADMIN_PASSWORD"] = dev_pass
			run(["aida-taiga-auth", "--profile", "developer", "--activate", "--switch-user"])  # active default
		scrum_user = (ident.get("scrum") or {}).get("username")
		scrum_pass = (ident.get("scrum") or {}).get("password")
		if scrum_user and scrum_pass:
			os.environ["TAIGA_ADMIN_USER"] = scrum_user
			os.environ["TAIGA_ADMIN_PASSWORD"] = scrum_pass
			run(["aida-taiga-auth", "--profile", "scrum", "--switch-user"])  # background profile
	except subprocess.CalledProcessError:
		print("Cached identity auth failed. Consider running: aida-setup --reset")


def do_init() -> int:
	if not system_running():
		print("Starting Taiga stack...")
		run(["aida-taiga-up"])  # prints URLs
		try:
			wait_timeout = os.environ.get("AIDA_TAIGA_WAIT", "180")
			run(["aida-taiga-wait", "--timeout", wait_timeout])
		except Exception:
			pass
	print("Binding cached identities (developer active; scrum background)...")
	bind_cached_identities()
	(Path.cwd() / ".aida" / "initialized").write_text("ok")
	print("Initialization complete.")
	return 0


def do_reset(args) -> int:
	if not args.force:
		print("Refusing to reset without --force. This is a destructive operation.")
		return 1
	confirm = input("Type RESET to confirm destructive reset: ").strip()
	if confirm != "RESET":
		print("Reset aborted.")
		return 1
	admin_user: str = args.admin_user or (input("Admin username [admin]: ").strip() or "admin")
	admin_email_default = f"{admin_user}@localhost"
	admin_email: str = args.admin_email or (input(f"Admin email [{admin_email_default}]: ").strip() or admin_email_default)
	admin_pass: str = args.admin_pass or getpass.getpass(f"Admin password for {admin_user}: ")
	print("\nPerforming full reset...")
	run([
		"aida-taiga-reset",
		"--admin-user", admin_user,
		"--admin-email", admin_email,
		"--admin-pass", admin_pass,
	])
	print("Binding cached identities after reset...")
	bind_cached_identities()
	(Path.cwd() / ".aida" / "initialized").write_text("ok")
	print("Reset complete.")
	return 0


def main() -> int:
	parser = argparse.ArgumentParser(prog="aida-setup", description="Initialize or reset AIDA environment safely")
	sub = parser.add_mutually_exclusive_group()
	sub.add_argument("--init", action="store_true", help="Non-destructive initialization (default)")
	sub.add_argument("--reset", action="store_true", help="Destructive reset (requires --force and confirmation)")
	parser.add_argument("--force", action="store_true", help="Required for --reset")
	parser.add_argument("--admin-user", help="Admin username for --reset")
	parser.add_argument("--admin-email", help="Admin email for --reset")
	parser.add_argument("--admin-pass", help="Admin password for --reset")
	args = parser.parse_args()
	if args.reset:
		return do_reset(args)
	return do_init()


if __name__ == "__main__":
	sys.exit(main())

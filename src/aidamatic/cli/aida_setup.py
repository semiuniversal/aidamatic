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


def wait_for_taiga_ready(context: str) -> None:
	wait_timeout = os.environ.get("AIDA_TAIGA_WAIT", "360")
	print(f"Waiting for Taiga backend to be ready ({context})...")
	run(["aida-taiga-wait", "--timeout", wait_timeout])


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
		# Authenticate non-human profiles (ide, scrum). Human 'user' is not cached with password.
		ide_node = (ident.get("ide") or ident.get("developer") or {})
		ide_user = ide_node.get("username")
		ide_pass = ide_node.get("password")
		if ide_user and ide_pass:
			os.environ["TAIGA_ADMIN_USER"] = ide_user
			os.environ["TAIGA_ADMIN_PASSWORD"] = ide_pass
			run(["aida-taiga-auth", "--profile", "ide", "--switch-user"])  # cache token
		scrum_user = (ident.get("scrum") or {}).get("username")
		scrum_pass = (ident.get("scrum") or {}).get("password")
		if scrum_user and scrum_pass:
			os.environ["TAIGA_ADMIN_USER"] = scrum_user
			os.environ["TAIGA_ADMIN_PASSWORD"] = scrum_pass
			run(["aida-taiga-auth", "--profile", "scrum", "--switch-user"])  # cache token
	except subprocess.CalledProcessError:
		print("Cached identity auth failed. Consider running: aida-setup --reset")


def do_init() -> int:
	if not system_running():
		print("Starting Taiga stack...")
		run(["aida-taiga-up"])  # prints URLs
	wait_for_taiga_ready("init")
	print("Binding cached identities (ide active; scrum background)...")
	bind_cached_identities()
	# Reconcile and verify tokens post-bind
	try:
		from aidamatic.identity.reconcile import reconcile_and_verify
		reconcile_and_verify()
	except Exception as e:
		print(f"[WARN] Identity reconcile skipped during init: {e}")
	(Path.cwd() / ".aida" / "initialized").write_text("ok")
	print("Initialization complete.")
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
	admin_user: str = args.admin_user or (input("User username [user]: ").strip() or "user")
	admin_email_default = f"{admin_user}@localhost"
	admin_email: str = args.admin_email or (input(f"User email [{admin_email_default}]: ").strip() or admin_email_default)
	admin_pass: str = args.admin_pass or getpass.getpass(f"User password for {admin_user} (admin privileges): ")
	print("\nPerforming full reset...")
	run([
		"aida-taiga-reset",
		"--admin-user", admin_user,
		"--admin-email", admin_email,
		"--admin-pass", admin_pass,
	])
	wait_for_taiga_ready("reset")
	print("Binding cached identities after reset (user active; scrum background)...")
	bind_cached_identities()
	# Reconcile and verify tokens post-reset
	try:
		from aidamatic.identity.reconcile import reconcile_and_verify
		reconcile_and_verify()
	except Exception as e:
		print(f"[WARN] Identity reconcile skipped during reset: {e}")
	(Path.cwd() / ".aida" / "initialized").write_text("ok")
	print("Reset complete.")
	return 0


def main() -> int:
	parser = argparse.ArgumentParser(prog="aida-setup", description="Initialize or reset AIDA environment safely")
	sub = parser.add_mutually_exclusive_group()
	sub.add_argument("--init", action="store_true", help="Non-destructive initialization (default)")
	sub.add_argument("--reset", action="store_true", help="Destructive reset (requires --force and confirmation)")
	parser.add_argument("--force", action="store_true", help="Required for --reset")
	parser.add_argument("--yes", action="store_true", help="Skip interactive confirmations (for automation)")
	parser.add_argument("--admin-user", help="Admin username for --reset")
	parser.add_argument("--admin-email", help="Admin email for --reset")
	parser.add_argument("--admin-pass", help="Admin password for --reset")
	args = parser.parse_args()
	if args.reset:
		return do_reset(args)
	return do_init()


if __name__ == "__main__":
	sys.exit(main())

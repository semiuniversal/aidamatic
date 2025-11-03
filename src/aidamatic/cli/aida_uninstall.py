import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], check: bool = True) -> int:
	try:
		res = subprocess.run(cmd, check=check)
		return res.returncode
	except subprocess.CalledProcessError as exc:
		return exc.returncode


def rm_path(p: Path) -> None:
	if p.is_symlink() or p.is_file():
		try:
			p.unlink()
		except Exception:
			pass
	elif p.is_dir():
		try:
			shutil.rmtree(p, ignore_errors=True)
		except Exception:
			pass


def main() -> int:
	parser = argparse.ArgumentParser(prog="aida-uninstall", description="Completely remove local AIDA installation and data")
	parser.add_argument("--yes", action="store_true", help="Do not prompt for confirmation")
	parser.add_argument("--keep-docker", action="store_true", help="Do not remove Docker volumes/containers")
	parser.add_argument("--remove-venv", action="store_true", help="Remove the .venv directory (run from outside the venv)")
	parser.add_argument("--remove-env-file", action="store_true", help="Also remove docker/.env")
	args = parser.parse_args()

	cwd = Path.cwd()
	compose_yml = cwd / "docker" / "docker-compose.yml"

	if not args.yes:
		ans = input("This will remove Docker data and local AIDA state. Type UNINSTALL to proceed: ").strip()
		if ans != "UNINSTALL":
			print("Aborted.")
			return 1

	# Stop and remove Docker stack and volumes (unless kept)
	if not args.keep_docker and compose_yml.exists():
		print("Stopping and removing Docker stack (with volumes)...")
		run(["docker", "compose", "-f", str(compose_yml), "down", "-v", "--remove-orphans"], check=False)

	# Purge local AIDA state
	print("Removing local AIDA state...")
	rm_path(cwd / ".aida")
	for token in cwd.glob(".taiga_token*"):
		try:
			token.unlink()
		except Exception:
			pass
	if args.remove_env_file:
		rm_path(cwd / "docker" / ".env")

	# Optionally remove venv
	if args.remove_venv:
		venv_dir = cwd / ".venv"
		active = Path(sys.executable).resolve().is_relative_to(venv_dir.resolve()) if venv_dir.exists() else False
		if active:
			print("Refusing to remove .venv from within the active virtual environment. Run from a parent shell.")
		else:
			print("Removing virtual environment .venv...")
			rm_path(venv_dir)

	print("Uninstall complete.")
	print("To bootstrap again: ./setup.sh --bootstrap")
	return 0


if __name__ == "__main__":
	sys.exit(main())

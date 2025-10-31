import os
import subprocess
import sys
from typing import List

SCRIPTS_DIR = os.path.join(os.getcwd(), "scripts")


def _run(script: str, argv: List[str]) -> int:
	script_path = os.path.join(SCRIPTS_DIR, script)
	if not os.path.isfile(script_path):
		print(f"Missing script: {script_path}", file=sys.stderr)
		return 2
	cmd = ["bash", script_path, *argv]
	proc = subprocess.run(cmd)
	return proc.returncode


def taiga_up() -> int:
	return _run("taiga-up.sh", sys.argv[1:])


def taiga_down() -> int:
	return _run("taiga-down.sh", sys.argv[1:])


def taiga_auth() -> int:
	return _run("taiga-auth.sh", sys.argv[1:])


def taiga_api() -> int:
	return _run("taiga-api.sh", sys.argv[1:])


def taiga_wait() -> int:
	return _run("taiga-wait.sh", sys.argv[1:])


def taiga_clean() -> int:
	return _run("taiga-clean.sh", sys.argv[1:])


def taiga_reset() -> int:
	return _run("taiga-reset.sh", sys.argv[1:])

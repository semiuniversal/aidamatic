import argparse
import json
import sys
from typing import Any

import requests

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def run_server(argv: list[str] | None = None) -> int:
	from aidamatic.bridge.app import run as run_app
	p = argparse.ArgumentParser(description="Run AIDA Bridge (localhost only)")
	p.add_argument("--host", default=DEFAULT_HOST)
	p.add_argument("--port", type=int, default=DEFAULT_PORT)
	args = p.parse_args(argv or sys.argv[1:])
	run_app(host=args.host, port=args.port)
	return 0


def post_comment(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Post a task comment via AIDA Bridge")
	p.add_argument("--text", required=True)
	p.add_argument("--host", default=DEFAULT_HOST)
	p.add_argument("--port", type=int, default=DEFAULT_PORT)
	args = p.parse_args(argv or sys.argv[1:])
	url = f"http://{args.host}:{args.port}/task/comment"
	r = requests.post(url, json={"text": args.text})
	if not r.ok:
		print(r.text, file=sys.stderr)
		r.raise_for_status()
	print(json.dumps(r.json(), indent=2))
	return 0


def post_status(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Change task status via AIDA Bridge (outbox event)")
	p.add_argument("--to", required=True)
	p.add_argument("--host", default=DEFAULT_HOST)
	p.add_argument("--port", type=int, default=DEFAULT_PORT)
	args = p.parse_args(argv or sys.argv[1:])
	url = f"http://{args.host}:{args.port}/task/status"
	r = requests.post(url, json={"to": args.to})
	if not r.ok:
		print(r.text, file=sys.stderr)
		r.raise_for_status()
	print(json.dumps(r.json(), indent=2))
	return 0

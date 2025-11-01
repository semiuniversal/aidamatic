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


def sync_outbox_cmd(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Trigger outbox sync via AIDA Bridge")
	p.add_argument("--host", default=DEFAULT_HOST)
	p.add_argument("--port", type=int, default=DEFAULT_PORT)
	p.add_argument("--dry-run", action="store_true")
	args = p.parse_args(argv or sys.argv[1:])
	url = f"http://{args.host}:{args.port}/sync/outbox"
	r = requests.post(url, params={"dry_run": str(args.dry_run).lower()})
	if not r.ok:
		print(r.text, file=sys.stderr)
		r.raise_for_status()
	print(json.dumps(r.json(), indent=2))
	return 0


def doc_cmd(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Docs inbox helper (add text/file or list)")
	group = p.add_mutually_exclusive_group()
	group.add_argument("--text", help="Add a text note")
	group.add_argument("--file", help="Path to a file to add")
	p.add_argument("--name", help="Override name for text/file")
	p.add_argument("--tag", action="append", help="Tag(s) to attach")
	p.add_argument("--list", action="store_true", help="List docs instead of adding")
	p.add_argument("--json", action="store_true", help="List in JSON")
	p.add_argument("--host", default=DEFAULT_HOST)
	p.add_argument("--port", type=int, default=DEFAULT_PORT)
	args = p.parse_args(argv or sys.argv[1:])
	base = f"http://{args.host}:{args.port}"
	if args.list or (not args.text and not args.file):
		url = f"{base}/docs"
		r = requests.get(url)
		if not r.ok:
			print(r.text, file=sys.stderr)
			r.raise_for_status()
		data = r.json()
		if args.json:
			print(json.dumps(data, indent=2))
		else:
			print("ID\tNAME\tBYTES\tTAGS")
			for d in data:
				tags = ",".join(d.get("tags") or [])
				print(f"{d.get('id')}\t{d.get('name')}\t{d.get('bytes')}\t{tags}")
		return 0
	if args.text:
		url = f"{base}/docs"
		tags = args.tag or []
		r = requests.post(url, json={"text": args.text, "name": args.name, "tags": tags})
		if not r.ok:
			print(r.text, file=sys.stderr)
			r.raise_for_status()
		print(json.dumps(r.json(), indent=2))
		return 0
	if args.file:
		url = f"{base}/docs/upload"
		files = {"file": open(args.file, "rb")}
		data = {}
		if args.name:
			data["name"] = args.name
		if args.tag:
			data["tags"] = ",".join(args.tag)
		r = requests.post(url, files=files, data=data)
		if not r.ok:
			print(r.text, file=sys.stderr)
			r.raise_for_status()
		print(json.dumps(r.json(), indent=2))
		return 0
	return 0


def chat_cmd(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description="Chat skeleton helper (send or thread)")
	group = p.add_mutually_exclusive_group(required=True)
	group.add_argument("--send", help="Send a user message")
	group.add_argument("--thread", action="store_true", help="Show thread")
	p.add_argument("--role", default="user", choices=["user", "assistant", "system"], help="Role for --send")
	p.add_argument("--tail", type=int, help="Limit messages from end")
	p.add_argument("--json", action="store_true")
	p.add_argument("--host", default=DEFAULT_HOST)
	p.add_argument("--port", type=int, default=DEFAULT_PORT)
	args = p.parse_args(argv or sys.argv[1:])
	base = f"http://{args.host}:{args.port}"
	if args.send is not None:
		r = requests.post(f"{base}/chat/send", json={"role": args.role, "text": args.send})
		if not r.ok:
			print(r.text, file=sys.stderr)
			r.raise_for_status()
		print(json.dumps(r.json(), indent=2))
		return 0
	params = {}
	if args.tail:
		params["tail"] = args.tail
	r = requests.get(f"{base}/chat/thread", params=params)
	if not r.ok:
		print(r.text, file=sys.stderr)
		r.raise_for_status()
	data = r.json()
	if args.json:
		print(json.dumps(data, indent=2))
	else:
		for m in data:
			print(f"[{m.get('ts')}] {m.get('role')}: {m.get('text')}")
	return 0

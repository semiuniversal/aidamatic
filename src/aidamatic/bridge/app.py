from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from aidamatic.assignment import load_assignment
from aidamatic.taiga.client import TaigaClient

APP = FastAPI(title="AIDA Bridge", version="0.1.0")

AIDA_DIR = Path(os.getcwd()) / ".aida"
OUTBOX_DIR = AIDA_DIR / "outbox"


class ProjectDTO(BaseModel):
	id: int
	slug: Optional[str] = None
	name: Optional[str] = None
	is_archived: Optional[bool] = None
	tags: Optional[List[str]] = None


class CommentReq(BaseModel):
	text: str = Field(min_length=1, max_length=4000)


class StatusReq(BaseModel):
	to: str = Field(min_length=1, max_length=128)


class HistoryItem(BaseModel):
	id: str
	type: str
	project_id: int
	slug: Optional[str]
	name: Optional[str]
	timestamp: str
	payload: dict


@APP.get("/health")
async def health() -> dict:
	return {"status": "ok"}


@APP.get("/projects", response_model=List[ProjectDTO])
async def projects(all: bool = Query(False), tag: Optional[str] = Query(None)) -> List[ProjectDTO]:
	client = TaigaClient.from_env()
	me = client.get_me()
	items = client.list_projects_filtered(member_id=me.get("id"), is_archived=None if all else False)
	if tag:
		items = [p for p in items if tag in (p.get("tags") or [])]
	return [
		ProjectDTO(id=int(p["id"]), slug=p.get("slug"), name=p.get("name"), is_archived=p.get("is_archived"), tags=p.get("tags"))
		for p in items
	]


@APP.get("/task/current")
async def task_current() -> dict:
	assignment = load_assignment()
	if not assignment:
		raise HTTPException(status_code=404, detail="No assignment selected. Run aida-task-select.")
	return {
		"project_id": assignment.project_id,
		"slug": assignment.slug,
		"name": assignment.name,
		"base_url": assignment.base_url,
		"selected_at": assignment.selected_at,
		"item": {
			"type": assignment.item_type,
			"id": assignment.item_id,
			"ref": assignment.item_ref,
			"subject": assignment.item_subject,
		},
	}


def _ensure_outbox() -> None:
	OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def _write_outbox(event_type: str, project_id: int, slug: Optional[str], name: Optional[str], payload: dict) -> HistoryItem:
	_ensure_outbox()
	ts = datetime.now(timezone.utc).isoformat()
	content = json.dumps({"t": event_type, "p": project_id, "s": slug, "n": name, "ts": ts, "payload": payload}, sort_keys=True).encode("utf-8")
	cid = hashlib.sha1(content).hexdigest()  # content-hash for idempotency
	path = OUTBOX_DIR / f"{ts}-{cid}.json"
	if not path.exists():
		path.write_text(content.decode("utf-8"), encoding="utf-8")
	return HistoryItem(id=cid, type=event_type, project_id=project_id, slug=slug, name=name, timestamp=ts, payload=payload)


@APP.post("/task/comment", response_model=HistoryItem)
async def task_comment(req: CommentReq) -> HistoryItem:
	assignment = load_assignment()
	if not assignment:
		raise HTTPException(status_code=409, detail="No assignment selected. Run aida-task-select.")
	payload = {"text": req.text}
	return _write_outbox("comment", assignment.project_id, assignment.slug, assignment.name, payload)


@APP.post("/task/status", response_model=HistoryItem)
async def task_status(req: StatusReq) -> HistoryItem:
	assignment = load_assignment()
	if not assignment:
		raise HTTPException(status_code=409, detail="No assignment selected. Run aida-task-select.")
	payload = {"to": req.to}
	return _write_outbox("status", assignment.project_id, assignment.slug, assignment.name, payload)


@APP.get("/task/history", response_model=List[HistoryItem])
async def task_history(limit: int = Query(50, ge=1, le=500)) -> List[HistoryItem]:
	_ensure_outbox()
	files = sorted(OUTBOX_DIR.glob("*.json"), reverse=True)[:limit]
	results: List[HistoryItem] = []
	for f in files:
		try:
			obj = json.loads(f.read_text(encoding="utf-8"))
			event_type = obj.get("t")
			cid = f.stem.split("-")[-1]
			results.append(
				HistoryItem(
					id=cid,
					type=str(event_type),
					project_id=int(obj.get("p")),
					slug=obj.get("s"),
					name=obj.get("n"),
					timestamp=str(obj.get("ts")),
					payload=obj.get("payload") or {},
				)
			)
		except Exception:
			continue
	return results


# Uvicorn entry (run only via `aida-bridge`)

def run(host: str = "127.0.0.1", port: int = 8787) -> None:
	import uvicorn
	uvicorn.run(APP, host=host, port=port, log_level="info")

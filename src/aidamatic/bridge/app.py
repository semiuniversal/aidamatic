from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Header
from pydantic import BaseModel, Field

from aidamatic.assignment import load_assignment
from aidamatic.taiga.client import TaigaClient
from aidamatic.sync.outbox_worker import sync_outbox, SyncState, STATE_FILE

APP = FastAPI(title="AIDA Bridge", version="0.1.0")

AIDA_DIR = Path(os.getcwd()) / ".aida"
OUTBOX_DIR = AIDA_DIR / "outbox"
DOCS_DIR = AIDA_DIR / "docs"
DOCS_INDEX = AIDA_DIR / "docs.jsonl"
CHAT_FILE = AIDA_DIR / "chat.jsonl"


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


class DocAddJSON(BaseModel):
	text: Optional[str] = None
	name: Optional[str] = None
	tags: Optional[List[str]] = None


class DocEntry(BaseModel):
	id: str
	name: str
	path: str
	bytes: int
	hash: str
	tags: List[str] = []
	added_at: str


class ChatSend(BaseModel):
	role: str = Field(pattern="^(user|assistant|system)$")
	text: str = Field(min_length=1)


class ChatMsg(BaseModel):
	role: str
	text: str
	ts: str


class NextSuggestion(BaseModel):
	item_type: str
	id: int
	ref: Optional[int] = None
	subject: Optional[str] = None
	status: Optional[str] = None
	assigned_to: Optional[int] = None
	priority: Optional[int] = None


def _require_profile(profile_q: Optional[str], profile_h: Optional[str]) -> str:
	prof = (profile_h or "").strip() or (profile_q or "").strip()
	if not prof:
		raise HTTPException(status_code=409, detail="No profile specified. Pass header X-AIDA-Profile or ?profile=")
	return prof


@APP.get("/health")
async def health() -> dict:
	return {"status": "ok"}


@APP.get("/projects", response_model=List[ProjectDTO])
async def projects(all: bool = Query(False), tag: Optional[str] = Query(None), profile: Optional[str] = Query(None), x_profile: Optional[str] = Header(None, alias="X-AIDA-Profile")) -> List[ProjectDTO]:
	prof = _require_profile(profile, x_profile)
	client = TaigaClient.from_profile(prof)
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


def _write_outbox(event_type: str, project_id: int, slug: Optional[str], name: Optional[str], payload: dict, profile: str) -> HistoryItem:
	_ensure_outbox()
	ts = datetime.now(timezone.utc).isoformat()
	# include selected item snapshot when available
	assignment = load_assignment()
	item = None
	if assignment and assignment.item_id:
		item = {
			"type": assignment.item_type,
			"id": assignment.item_id,
			"ref": assignment.item_ref,
			"subject": assignment.item_subject,
		}
	record = {"t": event_type, "p": project_id, "s": slug, "n": name, "ts": ts, "payload": payload, "item": item, "profile": profile}
	content = json.dumps(record, sort_keys=True).encode("utf-8")
	cid = hashlib.sha1(content).hexdigest()  # content-hash for idempotency
	path = OUTBOX_DIR / f"{ts}-{cid}.json"
	if not path.exists():
		path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
	return HistoryItem(id=cid, type=event_type, project_id=project_id, slug=slug, name=name, timestamp=ts, payload=payload)


@APP.post("/task/comment", response_model=HistoryItem)
async def task_comment(req: CommentReq, profile: Optional[str] = Query(None), x_profile: Optional[str] = Header(None, alias="X-AIDA-Profile")) -> HistoryItem:
	assignment = load_assignment()
	if not assignment:
		raise HTTPException(status_code=409, detail="No assignment selected. Run aida-task-select.")
	prof = _require_profile(profile, x_profile)
	payload = {"text": req.text}
	return _write_outbox("comment", assignment.project_id, assignment.slug, assignment.name, payload, prof)


@APP.post("/task/status", response_model=HistoryItem)
async def task_status(req: StatusReq, profile: Optional[str] = Query(None), x_profile: Optional[str] = Header(None, alias="X-AIDA-Profile")) -> HistoryItem:
	assignment = load_assignment()
	if not assignment:
		raise HTTPException(status_code=409, detail="No assignment selected. Run aida-task-select.")
	prof = _require_profile(profile, x_profile)
	payload = {"to": req.to}
	return _write_outbox("status", assignment.project_id, assignment.slug, assignment.name, payload, prof)


# ---- Docs inbox ----

def _append_jsonl(path: Path, obj: dict) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("a", encoding="utf-8") as f:
		f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _hash_bytes(data: bytes) -> str:
	return hashlib.sha1(data).hexdigest()


def _save_doc_bytes(name: str, data: bytes, tags: Optional[List[str]]) -> DocEntry:
	DOCS_DIR.mkdir(parents=True, exist_ok=True)
	h = _hash_bytes(data)
	ts = datetime.now(timezone.utc).isoformat()
	safe_name = name or "note.txt"
	file_path = DOCS_DIR / f"{h[:8]}-{safe_name}"
	if not file_path.exists():
		file_path.write_bytes(data)
	entry = DocEntry(
		id=h,
		name=safe_name,
		path=str(file_path),
		bytes=len(data),
		hash=h,
		tags=tags or [],
		added_at=ts,
	)
	_append_jsonl(DOCS_INDEX, entry.model_dump())
	return entry


@APP.post("/docs", response_model=DocEntry)
async def docs_add_json(req: DocAddJSON) -> DocEntry:
	if not req.text:
		raise HTTPException(status_code=400, detail="text is required (for uploads use /docs/upload)")
	data = req.text.encode("utf-8")
	name = req.name or "note.txt"
	return _save_doc_bytes(name=name, data=data, tags=req.tags or [])


@APP.post("/docs/upload", response_model=DocEntry)
async def docs_upload(file: UploadFile = File(...), tags: Optional[str] = Form(None), name: Optional[str] = Form(None)) -> DocEntry:
	content = await file.read()
	parsed_tags: List[str] = []
	if tags:
		parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]
	return _save_doc_bytes(name=name or file.filename, data=content, tags=parsed_tags)


@APP.get("/docs", response_model=List[DocEntry])
async def docs_list(tag: Optional[str] = Query(None)) -> List[DocEntry]:
	entries: List[DocEntry] = []
	if DOCS_INDEX.exists():
		for line in DOCS_INDEX.read_text(encoding="utf-8").splitlines():
			try:
				obj = json.loads(line)
				entry = DocEntry(**obj)
				entries.append(entry)
			except Exception:
				continue
	if tag:
		entries = [e for e in entries if tag in (e.tags or [])]
	return entries


# ---- Chat skeleton ----

@APP.post("/chat/send", response_model=ChatMsg)
async def chat_send(req: ChatSend) -> ChatMsg:
	ts = datetime.now(timezone.utc).isoformat()
	msg = ChatMsg(role=req.role, text=req.text, ts=ts)
	_append_jsonl(CHAT_FILE, msg.model_dump())
	return msg


@APP.get("/chat/thread", response_model=List[ChatMsg])
async def chat_thread(tail: Optional[int] = Query(None, ge=1)) -> List[ChatMsg]:
	msgs: List[ChatMsg] = []
	if CHAT_FILE.exists():
		for line in CHAT_FILE.read_text(encoding="utf-8").splitlines():
			try:
				obj = json.loads(line)
				msgs.append(ChatMsg(**obj))
			except Exception:
				continue
	if tail is not None:
		msgs = msgs[-tail:]
	return msgs


# ---- Next item suggestion ----

@APP.get("/task/next", response_model=NextSuggestion)
async def task_next(item_type: str = Query("issue"), profile: Optional[str] = Query(None), x_profile: Optional[str] = Header(None, alias="X-AIDA-Profile")) -> NextSuggestion:
	assignment = load_assignment()
	if not assignment or not assignment.project_id:
		raise HTTPException(status_code=409, detail="No project selected. Run aida-task-select.")
	prof = _require_profile(profile, x_profile)
	project_id = int(assignment.project_id)
	# Use requested profile to scope identity
	dev_client = TaigaClient.from_profile(prof)
	if not dev_client or not dev_client.get_me().get("id"):
		raise HTTPException(status_code=409, detail=f"Profile '{prof}' is not authenticated. Run aida-taiga-auth --profile {prof} --activate")
	dev_id = int(dev_client.get_me().get("id"))
	client = TaigaClient.from_profile(prof)
	if item_type != "issue":
		raise HTTPException(status_code=400, detail="Only item_type=issue is supported for now.")
	resp = client.get("/api/v1/issues", params={"project": project_id})
	resp.raise_for_status()
	issues = resp.json() if isinstance(resp.json(), list) else []
	# Filter open (status_extra_info.is_closed == False)
	open_issues = []
	for it in issues:
		sei = it.get("status_extra_info") or {}
		if sei.get("is_closed"):
			continue
		open_issues.append(it)
	if not open_issues:
		raise HTTPException(status_code=404, detail="No open items found. Adjust Taiga or create work.")
	# Prefer assigned to profile user, then unassigned
	prefer = [i for i in open_issues if (i.get("assigned_to") == dev_id)]
	if not prefer:
		prefer = [i for i in open_issues if (i.get("assigned_to") in (None, 0))]
	# Simple sort by priority then created_date
	def score(it: dict) -> tuple:
		return (int(it.get("priority") or 0), str(it.get("created_date") or ""))
	prefer.sort(key=score)
	candidate = prefer[0] if prefer else None
	if not candidate:
		raise HTTPException(status_code=404, detail="No suitable next item. Adjust assignment or status in Taiga.")
	return NextSuggestion(
		item_type="issue",
		id=int(candidate.get("id")),
		ref=candidate.get("ref"),
		subject=candidate.get("subject"),
		status=(candidate.get("status_extra_info") or {}).get("name"),
		assigned_to=candidate.get("assigned_to"),
		priority=candidate.get("priority"),
	)


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


@APP.post("/sync/outbox")
async def sync_outbox_now(dry_run: bool = False) -> dict:
	result = sync_outbox(dry_run=dry_run)
	return result


@APP.get("/sync/state")
async def sync_state() -> dict:
	if not STATE_FILE.exists():
		return {"processed": 0, "errors": []}
	data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
	return {"processed": len(data.get("processed", [])), "errors": data.get("errors", [])}


# Uvicorn entry (run only via `aida-bridge`)

def run(host: str = "127.0.0.1", port: int = 8787) -> None:
	import uvicorn
	uvicorn.run(APP, host=host, port=port, log_level="info")

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aidamatic.taiga.client import TaigaClient

AIDA_DIR = Path(os.getcwd()) / ".aida"
OUTBOX_DIR = AIDA_DIR / "outbox"
SYNC_DIR = AIDA_DIR / "sync"
STATE_FILE = SYNC_DIR / "state.json"
STATUS_MAP_FILE = AIDA_DIR / "status-map.json"


@dataclass
class SyncState:
	processed: List[str]
	errors: List[Dict[str, Any]]

	@classmethod
	def load(cls) -> "SyncState":
		if not STATE_FILE.exists():
			return SyncState(processed=[], errors=[])
		data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
		return SyncState(processed=data.get("processed", []), errors=data.get("errors", []))

	def save(self) -> None:
		SYNC_DIR.mkdir(parents=True, exist_ok=True)
		STATE_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _load_status_map() -> Dict[str, Dict[str, str]]:
	# { "issue": { "in_progress": "In progress", ... }, "userstory": {...}, "task": {...} }
	if not STATUS_MAP_FILE.exists():
		return {}
	try:
		return json.loads(STATUS_MAP_FILE.read_text(encoding="utf-8"))
	except Exception:
		return {}


def _resolve_status_id(client: TaigaClient, project_id: int, item_type: str, generic_to: str) -> Optional[int]:
	mapping = _load_status_map().get(item_type, {})
	name = mapping.get(generic_to)
	if not name:
		return None
	if item_type == "issue":
		statuses = client.get_issue_statuses(project_id)
	elif item_type == "userstory":
		statuses = client.get_userstory_statuses(project_id)
	else:
		statuses = client.get_userstory_statuses(project_id)  # task often reuses US statuses; adjust if needed
	for s in statuses:
		if s.get("name") == name:
			return int(s.get("id")) if s.get("id") is not None else None
	return None


def _post_comment(client: TaigaClient, item_type: str, item_id: int, text: str) -> Dict[str, Any]:
	return client.post_item_comment(item_type=item_type, item_id=item_id, text=text)


def _update_status(client: TaigaClient, project_id: int, item_type: str, item_id: int, generic_to: str) -> Dict[str, Any]:
	status_id = _resolve_status_id(client, project_id, item_type, generic_to)
	if status_id is None:
		raise RuntimeError(f"No status mapping for {item_type}:{generic_to}")
	return client.update_item_status(item_type=item_type, item_id=item_id, status_id=status_id)


def _client_for_event(obj: dict) -> TaigaClient:
	prof = (obj.get("profile") or "").strip()
	if prof:
		return TaigaClient.from_profile(prof)
	return TaigaClient.from_env()


def sync_outbox(dry_run: bool = False, limit: int = 100) -> Dict[str, Any]:
	state = SyncState.load()
	OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
	files = sorted(OUTBOX_DIR.glob("*.json"))[:limit]
	processed_now: List[str] = []
	errors_now: List[Dict[str, Any]] = []

	for f in files:
		try:
			obj = json.loads(f.read_text(encoding="utf-8"))
			cid = f.stem.split("-")[-1]
			if cid in state.processed:
				continue
			client = _client_for_event(obj)
			etype = obj.get("t")
			project_id = int(obj.get("p"))
			item = obj.get("item") or {}
			item_type = item.get("type")
			item_id = item.get("id")
			if not item_type or not item_id:
				raise RuntimeError("Outbox event missing item details; select an item before posting events")
			if etype == "comment":
				text = (obj.get("payload") or {}).get("text", "")
				if not dry_run:
					_post_comment(client, item_type=item_type, item_id=int(item_id), text=text)
			elif etype == "status":
				to = (obj.get("payload") or {}).get("to")
				if not to:
					raise RuntimeError("Status event missing 'to'")
				if not dry_run:
					_update_status(client, project_id=project_id, item_type=item_type, item_id=int(item_id), generic_to=str(to))
			else:
				raise RuntimeError(f"Unsupported event type: {etype}")
			processed_now.append(cid)
		except Exception as exc:
			errors_now.append({"file": str(f), "error": str(exc)})
			continue

	# Update state
	state.processed.extend(processed_now)
	state.errors.extend(errors_now)
	state.save()
	return {"processed": len(processed_now), "errors": errors_now}

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional

ASSIGNMENT_FILE_ENV = "AIDA_ASSIGNMENT_FILE"
DEFAULT_ASSIGNMENT_FILE = os.path.join(os.getcwd(), ".aida", "assignment.json")


@dataclass
class Assignment:
	project_id: int
	slug: str
	name: str
	base_url: str
	selected_at: str
	item_type: Optional[str] = None  # issue|userstory|task
	item_id: Optional[int] = None
	item_ref: Optional[int] = None
	item_subject: Optional[str] = None


def get_assignment_path() -> str:
	return os.environ.get(ASSIGNMENT_FILE_ENV, DEFAULT_ASSIGNMENT_FILE)


def save_assignment(project_id: int, slug: str, name: str, base_url: str,
					 item_type: Optional[str] = None, item_id: Optional[int] = None,
					 item_ref: Optional[int] = None, item_subject: Optional[str] = None) -> str:
	path = get_assignment_path()
	dirname = os.path.dirname(path)
	os.makedirs(dirname, exist_ok=True)
	assignment = Assignment(
		project_id=project_id,
		slug=slug,
		name=name,
		base_url=base_url,
		selected_at=datetime.now(timezone.utc).isoformat(),
		item_type=item_type,
		item_id=item_id,
		item_ref=item_ref,
		item_subject=item_subject,
	)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(asdict(assignment), f, indent=2)
	return path


def load_assignment() -> Optional[Assignment]:
	path = get_assignment_path()
	if not os.path.isfile(path):
		return None
	with open(path, "r", encoding="utf-8") as f:
		data = json.load(f)
	return Assignment(**data)

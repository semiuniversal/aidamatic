from typing import List, Optional
from pydantic import BaseModel, Field


class Member(BaseModel):
	username: Optional[str] = None
	email: Optional[str] = None
	role: Optional[str] = None


class WorkflowStatus(BaseModel):
	name: str
	slug: Optional[str] = None
	type: Optional[str] = None  # e.g., issue/userstory


class ProjectConfig(BaseModel):
	id: Optional[int] = None
	slug: Optional[str] = None
	name: str
	description: Optional[str] = None
	is_private: Optional[bool] = True
	members: List[Member] = Field(default_factory=list)
	issue_statuses: List[WorkflowStatus] = Field(default_factory=list)
	issue_types: List[str] = Field(default_factory=list)
	userstory_statuses: List[WorkflowStatus] = Field(default_factory=list)
	tags: List[str] = Field(default_factory=list)


class TaigaExport(BaseModel):
	version: str = "v1"
	project: ProjectConfig


def build_project_config(api_project: dict, memberships: list, issue_statuses: list, issue_types: list, us_statuses: list) -> ProjectConfig:
	members: List[Member] = []
	for m in memberships:
		user = m.get("user", {}) if isinstance(m.get("user"), dict) else {}
		members.append(
			Member(
				username=user.get("username"),
				email=user.get("email"),
				role=(m.get("role", {}) or {}).get("name") if isinstance(m.get("role"), dict) else None,
			)
		)

	def _status_list(raw: list, status_type: str) -> List[WorkflowStatus]:
		out: List[WorkflowStatus] = []
		for s in raw or []:
			name = s.get("name")
			if not name:
				continue
			out.append(WorkflowStatus(name=name, slug=s.get("slug"), type=status_type))
		return out

	return ProjectConfig(
		id=api_project.get("id"),
		slug=api_project.get("slug"),
		name=api_project.get("name") or api_project.get("slug") or "",
		description=api_project.get("description"),
		is_private=api_project.get("is_private", True),
		members=members,
		issue_statuses=_status_list(issue_statuses, "issue"),
		issue_types=[t.get("name") for t in (issue_types or []) if t.get("name")],
		userstory_statuses=_status_list(us_statuses, "userstory"),
		tags=[t for t in (api_project.get("tags") or []) if isinstance(t, str)],
	)

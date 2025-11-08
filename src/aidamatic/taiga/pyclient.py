from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
	from taiga import TaigaAPI  # type: ignore
except Exception as _e:  # pragma: no cover
	TaigaAPI = None  # noqa: N816


AIDA_DIR = Path.cwd() / ".aida"
AIDA_DIR.mkdir(exist_ok=True)


@dataclass
class AuthResult:
	username: str
	token: str
	user_id: int


@dataclass
class ProjectResult:
	id: int
	name: str
	slug: str


class TaigaPyClient:
	"""Thin wrapper around python-taiga with minimal, explicit surface area.

	All methods raise exceptions on failure with actionable messages for callers.
	"""

	def __init__(self, host: str = "http://localhost:9000") -> None:
		if TaigaAPI is None:
			raise RuntimeError(
				"python-taiga is not installed. Add 'python-taiga==0.8.6' to dependencies."
			)
		self.host = host.rstrip("/")
		self._api: Optional[TaigaAPI] = None  # type: ignore

	def authenticate(self, username: str, password: str) -> AuthResult:
		api = TaigaAPI(host=self.host)  # type: ignore
		api.auth(username=username, password=password)
		me = api.me()
		# python-taiga stores token internally; expose it for persistence
		token = getattr(api, "token", None)
		if not token:
			raise RuntimeError("Taiga auth did not yield a token")
		self._api = api
		return AuthResult(username=username, token=token, user_id=int(me.id))

	def me(self) -> dict:
		api = self._require_api()
		user = api.me()
		return {"id": int(user.id), "username": user.username}

	def get_or_create_project(self, name: str, slug: str, enable_kanban: bool = True) -> ProjectResult:
		api = self._require_api()
		project = None
		try:
			project = api.projects.get_by_slug(slug)
		except Exception:
			project = None
		if project is None:
			project = api.projects.create(name, slug)
			# Enable Kanban when requested (best-effort; may vary by Taiga version)
			if enable_kanban:
				setattr(project, "is_kanban_activated", True)
				try:
					project.update()
				except Exception:
					pass
		return ProjectResult(id=int(project.id), name=project.name, slug=project.slug)

	def persist_auth(self, profile: str, auth: AuthResult) -> None:
		"""Write `.aida/auth.<profile>.json` with token and user id."""
		path = AIDA_DIR / f"auth.{profile}.json"
		data = {"username": auth.username, "token": auth.token, "user_id": auth.user_id}
		self._write_json(path, data)

	def persist_identities(self, project: ProjectResult) -> None:
		path = AIDA_DIR / "identities.json"
		payload = {
			"project": {"id": project.id, "slug": project.slug, "name": project.name}
		}
		# Merge if exists
		if path.exists():
			try:
				existing = json.loads(path.read_text(encoding="utf-8"))
				if isinstance(existing, dict):
					existing.update(payload)
					payload = existing
			except Exception:
				pass
		self._write_json(path, payload)

	def _require_api(self) -> TaigaAPI:  # type: ignore
		if self._api is None:
			raise RuntimeError("Client not authenticated; call authenticate() first")
		return self._api

	@staticmethod
	def _write_json(path: Path, data: dict) -> None:
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def slugify(name: str) -> str:
	allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
	s = name.strip().lower().replace(" ", "-")
	return "".join(ch for ch in s if ch in allowed) or "project"


def detect_repo_name() -> str:
	root = Path(os.getcwd())
	return root.name

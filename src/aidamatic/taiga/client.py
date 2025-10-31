import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = "http://localhost:9000"
ENV_TOKEN = "TAIGA_TOKEN"
ENV_BASE = "TAIGA_BASE_URL"


class TaigaClient:
	"""Minimal Taiga API client with token auth and basic helpers.

	This client targets the Taiga v1 REST API used by local instances.
	It prefers the TAIGA_TOKEN environment variable. If absent, it will
	attempt to invoke `scripts/taiga-auth.sh` to obtain a token.
	"""

	def __init__(self, base_url: str, token: str, timeout_s: float = 15.0) -> None:
		self.base_url = base_url.rstrip("/")
		self.token = token
		self.timeout_s = timeout_s
		self.session = requests.Session()
		self.session.headers.update({
			"Authorization": f"Bearer {self.token}",
			"Accept": "application/json",
		})

	@classmethod
	def from_env(cls) -> "TaigaClient":
		base_url = os.environ.get(ENV_BASE, DEFAULT_BASE_URL)
		token = os.environ.get(ENV_TOKEN)
		if not token:
			# Attempt to fetch via local script for dev convenience
			script_path = os.path.join(os.getcwd(), "scripts", "taiga-auth.sh")
			if os.path.isfile(script_path) and os.access(script_path, os.X_OK):
				try:
					proc = subprocess.run([script_path], check=True, capture_output=True, text=True)
					token = proc.stdout.strip()
				except Exception as exc:
					raise RuntimeError("Failed to obtain TAIGA_TOKEN via taiga-auth.sh") from exc
			else:
				raise RuntimeError("TAIGA_TOKEN is not set and scripts/taiga-auth.sh is not available")
		return cls(base_url=base_url, token=token)

	def _url(self, path: str) -> str:
		if path.startswith("http://") or path.startswith("https://"):
			return path
		return f"{self.base_url}{path if path.startswith('/') else '/' + path}"

	def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
		return self.session.get(self._url(path), params=params or {}, timeout=self.timeout_s)

	def post(self, path: str, json: Optional[Dict[str, Any]] = None) -> requests.Response:
		headers = {"Content-Type": "application/json"}
		return self.session.post(self._url(path), json=json or {}, headers=headers, timeout=self.timeout_s)

	# --- Identity & projects ---
	def get_me(self) -> Dict[str, Any]:
		resp = self.get("/api/v1/users/me")
		resp.raise_for_status()
		return resp.json()

	def list_projects(self) -> List[Dict[str, Any]]:
		# All visible projects for token; caller may filter
		r = self.get("/api/v1/projects")
		r.raise_for_status()
		data = r.json()
		return data if isinstance(data, list) else []

	def list_projects_filtered(self, member_id: Optional[int] = None, is_archived: Optional[bool] = None) -> List[Dict[str, Any]]:
		params: Dict[str, Any] = {}
		if member_id is not None:
			params["member"] = member_id
		if is_archived is not None:
			params["is_archived"] = str(is_archived).lower()
		resp = self.get("/api/v1/projects", params=params)
		resp.raise_for_status()
		data = resp.json()
		return data if isinstance(data, list) else []

	def get_project_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
		# Try filtered query to reduce results
		me = None
		try:
			me = self.get_me()
		except Exception:
			me = None
		projects = self.list_projects_filtered(member_id=(me or {}).get("id"), is_archived=False)
		for p in projects:
			if p.get("slug") == slug:
				return p
		# Fallback to unfiltered list if not found
		for p in self.list_projects():
			if p.get("slug") == slug:
				return p
		return None

	def get_memberships(self, project_id: int) -> List[Dict[str, Any]]:
		resp = self.get("/api/v1/memberships", params={"project": project_id})
		if resp.status_code == 404:
			return []
		resp.raise_for_status()
		data = resp.json()
		return data if isinstance(data, list) else []

	def get_issue_statuses(self, project_id: int) -> List[Dict[str, Any]]:
		resp = self.get("/api/v1/issue-statuses", params={"project": project_id})
		return resp.json() if resp.ok else []

	def get_issue_types(self, project_id: int) -> List[Dict[str, Any]]:
		resp = self.get("/api/v1/issue-types", params={"project": project_id})
		return resp.json() if resp.ok else []

	def get_userstory_statuses(self, project_id: int) -> List[Dict[str, Any]]:
		resp = self.get("/api/v1/userstory-statuses", params={"project": project_id})
		return resp.json() if resp.ok else []

	def create_project(self, name: str, slug: Optional[str] = None, is_private: bool = True, description: str = "") -> Dict[str, Any]:
		payload: Dict[str, Any] = {
			"name": name,
			"is_private": is_private,
			"description": description,
		}
		if slug:
			payload["slug"] = slug
		resp = self.post("/api/v1/projects", json=payload)
		resp.raise_for_status()
		return resp.json()

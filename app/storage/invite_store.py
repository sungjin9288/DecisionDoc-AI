"""app/storage/invite_store.py — Team member invitation links."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from app.storage.base import BaseJsonStore

_log = logging.getLogger("decisiondoc.invite")


class InviteStore(BaseJsonStore):
    def __init__(self, tenant_id: str) -> None:
        super().__init__()
        self._tenant_id = tenant_id
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self._path_val = (
            data_dir / "tenants" / tenant_id / "invites.json"
        )
        self._path_val.parent.mkdir(parents=True, exist_ok=True)

    def _get_path(self) -> Path:
        return self._path_val

    def create(
        self,
        invite_id: str,
        email: str,
        role: str,
        created_by: str,
        expires_days: int = 7,
        job_title: str = "",
        assigned_ai_profiles: list[str] | None = None,
    ) -> dict:
        with self._lock:
            data = self._load()
            data[invite_id] = {
                "invite_id": invite_id,
                "tenant_id": self._tenant_id,
                "email": email,
                "role": role,
                "created_by": created_by,
                "created_at": datetime.now().isoformat(),
                "expires_at": (
                    datetime.now() + timedelta(days=expires_days)
                ).isoformat(),
                "job_title": job_title,
                "assigned_ai_profiles": list(assigned_ai_profiles or []),
                "is_active": True,
                "used_at": None,
            }
            self._save(data)
            return data[invite_id]

    def get(self, invite_id: str) -> dict | None:
        with self._lock:
            data = self._load()
            invite = data.get(invite_id)
            if not invite or invite.get("tenant_id") != self._tenant_id:
                return None
            if datetime.fromisoformat(invite["expires_at"]) < datetime.now():
                invite["is_active"] = False
            return invite

    def mark_used(self, invite_id: str) -> None:
        with self._lock:
            data = self._load()
            invite = data.get(invite_id)
            if invite and invite.get("tenant_id") == self._tenant_id:
                data[invite_id]["is_active"] = False
                data[invite_id]["used_at"] = datetime.now().isoformat()
                self._save(data)

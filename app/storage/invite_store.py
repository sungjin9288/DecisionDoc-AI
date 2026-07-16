"""app/storage/invite_store.py — Team member invitation links."""
from __future__ import annotations

import logging
import json
import os
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.invite")
_Result = TypeVar("_Result")


_invite_locks: dict[Path, threading.RLock] = {}
_invite_locks_guard = threading.Lock()


class InviteStoreError(ValueError):
    """Raised when persisted invitation state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _invite_locks_guard:
        return _invite_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InviteStoreError(f"Duplicate key in invite state: {key!r}")
        result[key] = value
    return result


class InviteStore:
    """Thread-safe invitation state scoped to a single tenant."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "invites.json"
        )
        self._path_val = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_path(self._path_val)

    def _validate_record(self, invite_id: str, record: object) -> None:
        if not isinstance(record, dict):
            raise InviteStoreError("Invalid invite record")
        stored_tenant_id = record.get("tenant_id")
        if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
            raise InviteStoreError("Invalid invite identity")
        if stored_tenant_id != self._tenant_id:
            return
        required_strings = (
            "invite_id",
            "tenant_id",
            "email",
            "role",
            "created_by",
            "created_at",
            "expires_at",
        )
        if any(not isinstance(record.get(field), str) for field in required_strings):
            raise InviteStoreError("Invalid invite record")
        if record["invite_id"] != invite_id or not record["invite_id"]:
            raise InviteStoreError("Invalid invite identity")
        if record["role"] not in {"admin", "member", "viewer"}:
            raise InviteStoreError("Invalid invite role")
        if not isinstance(record.get("is_active"), bool):
            raise InviteStoreError("Invalid invite active state")
        used_at = record.get("used_at")
        if used_at is not None and not isinstance(used_at, str):
            raise InviteStoreError("Invalid invite use timestamp")
        if not isinstance(record.get("job_title", ""), str):
            raise InviteStoreError("Invalid invite job title")
        profiles = record.get("assigned_ai_profiles", [])
        if not isinstance(profiles, list) or any(
            not isinstance(profile, str) for profile in profiles
        ):
            raise InviteStoreError("Invalid invite AI profiles")
        try:
            datetime.fromisoformat(record["created_at"])
            datetime.fromisoformat(record["expires_at"])
            if used_at is not None:
                datetime.fromisoformat(used_at)
        except ValueError as exc:
            raise InviteStoreError("Invalid invite timestamp") from exc

    def _validate_state(self, data: object) -> dict[str, dict]:
        if not isinstance(data, dict):
            raise InviteStoreError("Invalid invite state document")
        for invite_id, record in data.items():
            if not isinstance(invite_id, str):
                raise InviteStoreError("Invalid invite record")
            self._validate_record(invite_id, record)
        return data

    def _load(self) -> dict[str, dict]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return {}
        if not raw.strip():
            raise InviteStoreError("Invalid invite state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise InviteStoreError("Invalid invite state document") from exc
        return self._validate_state(data)

    def _save(self, data: dict[str, dict]) -> None:
        self._validate_state(data)
        self._backend.write_text(
            self._relative_path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

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
        if (
            not isinstance(invite_id, str)
            or not invite_id
            or not isinstance(email, str)
            or not isinstance(role, str)
            or not isinstance(created_by, str)
            or not isinstance(job_title, str)
            or not isinstance(expires_days, int)
        ):
            raise InviteStoreError("Invalid invite record")
        if assigned_ai_profiles is not None and (
            not isinstance(assigned_ai_profiles, list)
            or any(not isinstance(profile, str) for profile in assigned_ai_profiles)
        ):
            raise InviteStoreError("Invalid invite AI profiles")
        now = datetime.now()
        with self._lock:
            data = self._load()
            if invite_id in data:
                raise ValueError(f"초대 ID가 이미 존재합니다: {invite_id}")
            invite = {
                "invite_id": invite_id,
                "tenant_id": self._tenant_id,
                "email": email,
                "role": role,
                "created_by": created_by,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(days=expires_days)).isoformat(),
                "job_title": job_title,
                "assigned_ai_profiles": list(assigned_ai_profiles or []),
                "is_active": True,
                "used_at": None,
            }
            self._validate_record(invite_id, invite)
            data[invite_id] = invite
            self._save(data)
            return data[invite_id]

    def get(self, invite_id: str) -> dict | None:
        with self._lock:
            data = self._load()
            invite = data.get(invite_id)
            if not invite or invite.get("tenant_id") != self._tenant_id:
                return None
            expires_at = datetime.fromisoformat(invite["expires_at"])
            if expires_at < datetime.now(expires_at.tzinfo):
                invite["is_active"] = False
            return invite

    def accept(
        self,
        invite_id: str,
        create_account: Callable[[dict], _Result],
    ) -> _Result | None:
        """Create one account and consume the invitation in the same lock."""
        with self._lock:
            data = self._load()
            invite = data.get(invite_id)
            if not invite or invite.get("tenant_id") != self._tenant_id:
                return None
            expires_at = datetime.fromisoformat(invite["expires_at"])
            if not invite["is_active"] or expires_at < datetime.now(expires_at.tzinfo):
                return None

            result = create_account(dict(invite))
            invite["is_active"] = False
            invite["used_at"] = datetime.now().isoformat()
            self._save(data)
            return result

    def mark_used(self, invite_id: str) -> None:
        with self._lock:
            data = self._load()
            invite = data.get(invite_id)
            if invite and invite.get("tenant_id") == self._tenant_id:
                data[invite_id]["is_active"] = False
                data[invite_id]["used_at"] = datetime.now().isoformat()
                self._save(data)

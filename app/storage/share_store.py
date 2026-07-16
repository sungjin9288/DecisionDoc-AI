"""Tenant-scoped storage for public document share links."""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


_share_locks: dict[Path, threading.RLock] = {}
_share_locks_guard = threading.Lock()


class ShareStoreError(ValueError):
    """Raised when persisted share-link state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _share_locks_guard:
        return _share_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ShareStoreError(f"Duplicate key in share state: {key!r}")
        result[key] = value
    return result


def _is_elapsed(timestamp: str) -> bool:
    expires_at = datetime.fromisoformat(timestamp)
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    return expires_at < now


@dataclass
class ShareLink:
    share_id: str
    tenant_id: str
    request_id: str
    title: str
    created_by: str
    created_at: str
    expires_at: str
    access_count: int = 0
    last_accessed_at: str = ""
    is_active: bool = True
    revoked_at: str = ""
    revoked_by: str = ""
    revoked_by_username: str = ""
    bundle_id: str = ""
    project_id: str = ""
    project_document_id: str = ""
    source_fingerprint: str = ""
    decision_council_document_status: str = ""
    decision_council_document_status_tone: str = ""
    decision_council_document_status_copy: str = ""
    decision_council_document_status_summary: str = ""
    procurement_review_document_status: str = ""
    procurement_review_document_status_tone: str = ""
    procurement_review_document_status_copy: str = ""
    procurement_review_document_status_summary: str = ""


class ShareStore:
    """Thread-safe public share-link state scoped to a single tenant."""

    _optional_string_fields = (
        "last_accessed_at",
        "revoked_at",
        "revoked_by",
        "revoked_by_username",
        "bundle_id",
        "project_id",
        "project_document_id",
        "source_fingerprint",
        "decision_council_document_status",
        "decision_council_document_status_tone",
        "decision_council_document_status_copy",
        "decision_council_document_status_summary",
        "procurement_review_document_status",
        "procurement_review_document_status_tone",
        "procurement_review_document_status_copy",
        "procurement_review_document_status_summary",
    )

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self.tenant_id = require_tenant_id(tenant_id)
        resolved_data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._relative_path = str(Path("tenants") / self.tenant_id / "shares.json")
        self._path = resolved_data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=resolved_data_dir)
        self._lock = _lock_for_path(self._path)

    def _get_path(self) -> Path:
        return self._path

    def _owns(self, link: dict[str, Any]) -> bool:
        stored_tenant_id = link.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self.tenant_id

    def _validate_record(
        self,
        stored_key: object,
        link: object,
    ) -> dict[str, Any]:
        if not isinstance(stored_key, str) or not stored_key:
            raise ShareStoreError("Invalid share identity")
        if not isinstance(link, dict):
            raise ShareStoreError("Invalid share record")

        stored_tenant_id = link.get("tenant_id")
        if stored_tenant_id is not None:
            if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                raise ShareStoreError("Invalid share identity")
            if stored_tenant_id != self.tenant_id:
                return link

        required_strings = (
            "share_id",
            "request_id",
            "title",
            "created_by",
            "created_at",
            "expires_at",
        )
        if any(not isinstance(link.get(field), str) for field in required_strings):
            raise ShareStoreError("Invalid share record")
        if any(not link[field] for field in ("share_id", "request_id", "created_by")):
            raise ShareStoreError("Invalid share identity")
        if link["share_id"] != stored_key:
            raise ShareStoreError("Invalid share identity")

        for field in self._optional_string_fields:
            if field in link and not isinstance(link[field], str):
                raise ShareStoreError("Invalid share record")

        access_count = link.get("access_count")
        if (
            isinstance(access_count, bool)
            or not isinstance(access_count, int)
            or access_count < 0
        ):
            raise ShareStoreError("Invalid share access count")
        if not isinstance(link.get("is_active"), bool):
            raise ShareStoreError("Invalid share lifecycle state")
        if link.get("revoked_at") and link["is_active"]:
            raise ShareStoreError("Invalid share lifecycle state")

        try:
            datetime.fromisoformat(link["created_at"])
            datetime.fromisoformat(link["expires_at"])
            for field in ("last_accessed_at", "revoked_at"):
                timestamp = link.get(field, "")
                if timestamp:
                    datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ShareStoreError("Invalid share timestamp") from exc
        return link

    def _validate_state(self, data: object) -> dict[str, dict[str, Any]]:
        if not isinstance(data, dict):
            raise ShareStoreError("Invalid share state document")

        share_ids: set[str] = set()
        for stored_key, link in data.items():
            self._validate_record(stored_key, link)
            if not self._owns(link):
                continue
            share_id = link["share_id"]
            if share_id in share_ids:
                raise ShareStoreError("Duplicate share identity")
            share_ids.add(share_id)
        return data

    def _load(self) -> dict[str, dict[str, Any]]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return {}
        if not raw.strip():
            raise ShareStoreError("Invalid share state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ShareStoreError("Invalid share state document") from exc
        return self._validate_state(data)

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self._validate_state(data)
        self._backend.write_text(
            self._relative_path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def create(
        self,
        request_id: str,
        title: str,
        created_by: str,
        bundle_id: str = "",
        project_id: str = "",
        project_document_id: str = "",
        source_fingerprint: str = "",
        expires_days: int = 7,
        decision_council_document_status: str = "",
        decision_council_document_status_tone: str = "",
        decision_council_document_status_copy: str = "",
        decision_council_document_status_summary: str = "",
        procurement_review_document_status: str = "",
        procurement_review_document_status_tone: str = "",
        procurement_review_document_status_copy: str = "",
        procurement_review_document_status_summary: str = "",
    ) -> ShareLink:
        if isinstance(expires_days, bool) or not isinstance(expires_days, int):
            raise ShareStoreError("Invalid share expiry")

        created_at = datetime.now()
        link = ShareLink(
            share_id=secrets.token_urlsafe(16),
            tenant_id=self.tenant_id,
            request_id=request_id,
            title=title,
            created_by=created_by,
            created_at=created_at.isoformat(),
            expires_at=(created_at + timedelta(days=expires_days)).isoformat(),
            bundle_id=bundle_id,
            project_id=project_id,
            project_document_id=project_document_id,
            source_fingerprint=source_fingerprint,
            decision_council_document_status=decision_council_document_status,
            decision_council_document_status_tone=decision_council_document_status_tone,
            decision_council_document_status_copy=decision_council_document_status_copy,
            decision_council_document_status_summary=decision_council_document_status_summary,
            procurement_review_document_status=procurement_review_document_status,
            procurement_review_document_status_tone=procurement_review_document_status_tone,
            procurement_review_document_status_copy=procurement_review_document_status_copy,
            procurement_review_document_status_summary=procurement_review_document_status_summary,
        )
        record = self._validate_record(link.share_id, asdict(link))

        with self._lock:
            data = self._load()
            if link.share_id in data:
                raise ShareStoreError("Duplicate share identity")
            data[link.share_id] = record
            self._save(data)
        return link

    def get(self, share_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._load()
        stored_link = data.get(share_id)
        if not stored_link or not self._owns(stored_link):
            return None

        link = dict(stored_link)
        if link["is_active"] is False:
            link["lifecycle_status"] = (
                "revoked" if link.get("revoked_at") else "inactive"
            )
        elif _is_elapsed(link["expires_at"]):
            link["is_active"] = False
            link["lifecycle_status"] = "expired"
        else:
            link["lifecycle_status"] = "active"
        return link

    def increment_access(self, share_id: str) -> None:
        with self._lock:
            data = self._load()
            link = data.get(share_id)
            if not link or not self._owns(link):
                return
            link["access_count"] += 1
            link["last_accessed_at"] = datetime.now().isoformat()
            self._save(data)

    def revoke(
        self,
        share_id: str,
        user_id: str,
        *,
        allow_admin_override: bool = False,
        actor_name: str = "",
    ) -> bool:
        with self._lock:
            data = self._load()
            link = data.get(share_id)
            if not link or not self._owns(link):
                return False
            if link["created_by"] != user_id and not allow_admin_override:
                return False
            link["is_active"] = False
            if not link.get("revoked_at"):
                link["revoked_at"] = datetime.now().isoformat()
                link["revoked_by"] = user_id
                link["revoked_by_username"] = actor_name or user_id
            self._save(data)
            return True

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._load()
        return [
            link
            for link in data.values()
            if self._owns(link) and link["created_by"] == user_id
        ]

"""
Document sharing store.
Generates shareable links for generated documents.
"""
import secrets
import threading
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.storage.base import BaseJsonStore

_log = logging.getLogger("decisiondoc.share")


@dataclass
class ShareLink:
    share_id: str
    tenant_id: str
    request_id: str
    title: str
    created_by: str
    created_at: str
    expires_at: str        # ISO datetime
    access_count: int = 0
    is_active: bool = True
    bundle_id: str = ""


class ShareStore(BaseJsonStore):
    def __init__(self, tenant_id: str):
        super().__init__()
        self.tenant_id = tenant_id
        self._path = (
            Path("data") / "tenants" / tenant_id / "shares.json"
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _get_path(self) -> Path:
        return self._path

    def create(
        self,
        tenant_id: str,
        request_id: str,
        title: str,
        created_by: str,
        bundle_id: str = "",
        expires_days: int = 7,
    ) -> ShareLink:
        share_id = secrets.token_urlsafe(16)
        expires_at = (
            datetime.now() + timedelta(days=expires_days)
        ).isoformat()

        link = ShareLink(
            share_id=share_id,
            tenant_id=tenant_id,
            request_id=request_id,
            title=title,
            created_by=created_by,
            created_at=datetime.now().isoformat(),
            expires_at=expires_at,
            bundle_id=bundle_id,
        )

        with self._lock:
            data = self._load()
            data[share_id] = {
                "share_id": share_id,
                "tenant_id": tenant_id,
                "request_id": request_id,
                "title": title,
                "created_by": created_by,
                "created_at": link.created_at,
                "expires_at": expires_at,
                "access_count": 0,
                "is_active": True,
                "bundle_id": bundle_id,
            }
            self._save(data)

        return link

    def get(self, share_id: str) -> dict | None:
        with self._lock:
            data = self._load()
            link = data.get(share_id)
            if not link:
                return None
            # Mark expired
            if datetime.fromisoformat(link["expires_at"]) < datetime.now():
                link["is_active"] = False
            return link

    def increment_access(self, share_id: str) -> None:
        with self._lock:
            data = self._load()
            if share_id in data:
                data[share_id]["access_count"] = (
                    data[share_id].get("access_count", 0) + 1
                )
                self._save(data)

    def revoke(self, share_id: str, user_id: str) -> bool:
        with self._lock:
            data = self._load()
            link = data.get(share_id)
            if not link:
                return False
            if link.get("created_by") != user_id:
                return False
            data[share_id]["is_active"] = False
            self._save(data)
            return True

    def list_by_user(self, user_id: str) -> list[dict]:
        with self._lock:
            data = self._load()
            return [
                v for v in data.values()
                if v.get("created_by") == user_id
            ]

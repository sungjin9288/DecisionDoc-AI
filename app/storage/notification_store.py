"""app/storage/notification_store.py — Per-tenant notification storage.

Storage: data/tenants/{tenant_id}/notifications.json  (list of dicts)
Thread-safe via threading.Lock per store instance.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path

from app.storage.base import atomic_write_text

_log = logging.getLogger("decisiondoc.notification_store")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Constants ──────────────────────────────────────────────────────────────────

EVENT_TYPES: dict[str, str] = {
    "approval_requested": "결재 요청",
    "approval_review_done": "검토 완료",
    "approval_changes_requested": "수정 요청",
    "approval_approved": "승인 완료",
    "approval_rejected": "반려",
    "mention": "멘션",
    "project_doc_added": "문서 추가",
    "system": "시스템",
}


# ── Data model ─────────────────────────────────────────────────────────────────


@dataclass
class Notification:
    notification_id: str
    tenant_id: str
    recipient_id: str
    event_type: str          # one of EVENT_TYPES keys
    title: str
    body: str
    context_type: str        # "approval" | "project" | "message" | "system"
    context_id: str          # e.g. approval_id, project_id, message_id
    is_read: bool
    created_at: str
    sent_email: bool
    sent_slack: bool


# ── Serialization ──────────────────────────────────────────────────────────────


def _notif_from_dict(d: dict) -> Notification:
    return Notification(
        notification_id=d["notification_id"],
        tenant_id=d.get("tenant_id", ""),
        recipient_id=d.get("recipient_id", ""),
        event_type=d.get("event_type", "system"),
        title=d.get("title", ""),
        body=d.get("body", ""),
        context_type=d.get("context_type", "system"),
        context_id=d.get("context_id", ""),
        is_read=d.get("is_read", False),
        created_at=d.get("created_at", ""),
        sent_email=d.get("sent_email", False),
        sent_slack=d.get("sent_slack", False),
    )


# ── NotificationStore ─────────────────────────────────────────────────────────


class NotificationStore:
    """Thread-safe, file-backed notification store scoped to a single tenant."""

    def __init__(self, tenant_id: str) -> None:
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        tenant_dir = data_dir / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "notifications.json"
        self._lock = threading.Lock()
        if not self._path.exists():
            self._write([])

    # ── internal helpers ───────────────────────────────────────────────────

    def _read(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, data: list[dict]) -> None:
        atomic_write_text(
            self._path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    # ── public API ─────────────────────────────────────────────────────────

    def create(
        self,
        tenant_id: str,
        recipient_id: str,
        event_type: str,
        title: str,
        body: str,
        context_type: str,
        context_id: str,
    ) -> Notification:
        """Create and persist a new notification."""
        notif = Notification(
            notification_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            recipient_id=recipient_id,
            event_type=event_type,
            title=title,
            body=body,
            context_type=context_type,
            context_id=context_id,
            is_read=False,
            created_at=_now_iso(),
            sent_email=False,
            sent_slack=False,
        )
        with self._lock:
            data = self._read()
            data.append(asdict(notif))
            self._write(data)
        return notif

    def get_for_user(
        self,
        recipient_id: str,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Return notifications for a user, newest first."""
        with self._lock:
            data = self._read()
        items = [d for d in data if d.get("recipient_id") == recipient_id]
        if unread_only:
            items = [d for d in items if not d.get("is_read", False)]
        # Sort newest first
        items.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return [_notif_from_dict(d) for d in items[:limit]]

    def get_unread_count(self, recipient_id: str) -> int:
        """Count unread notifications for a user."""
        with self._lock:
            data = self._read()
        return sum(
            1 for d in data
            if d.get("recipient_id") == recipient_id and not d.get("is_read", False)
        )

    def mark_read(self, notification_id: str, recipient_id: str) -> bool:
        """Mark a single notification as read. Returns True if found."""
        with self._lock:
            data = self._read()
            found = False
            for d in data:
                if (
                    d.get("notification_id") == notification_id
                    and d.get("recipient_id") == recipient_id
                ):
                    d["is_read"] = True
                    found = True
                    break
            if found:
                self._write(data)
        return found

    def mark_all_read(self, recipient_id: str) -> int:
        """Mark all notifications for a user as read. Returns count updated."""
        with self._lock:
            data = self._read()
            count = 0
            for d in data:
                if d.get("recipient_id") == recipient_id and not d.get("is_read", False):
                    d["is_read"] = True
                    count += 1
            if count:
                self._write(data)
        return count

    def mark_email_sent(self, notification_id: str) -> None:
        """Record that an email was sent for this notification."""
        with self._lock:
            data = self._read()
            for d in data:
                if d.get("notification_id") == notification_id:
                    d["sent_email"] = True
                    break
            self._write(data)

    def mark_slack_sent(self, notification_id: str) -> None:
        """Record that a Slack message was sent for this notification."""
        with self._lock:
            data = self._read()
            for d in data:
                if d.get("notification_id") == notification_id:
                    d["sent_slack"] = True
                    break
            self._write(data)

    def delete_for_user(self, user_id: str) -> int:
        """Delete all notifications belonging to a withdrawn user.

        Returns the count of deleted notifications.
        """
        with self._lock:
            data = self._read()
            original = len(data)
            data = [d for d in data if d.get("recipient_id") != user_id]
            deleted = original - len(data)
            if deleted:
                self._write(data)
                _log.info(
                    "[NotificationStore] Deleted %d notifications for user %s",
                    deleted,
                    user_id,
                )
        return deleted

    def delete_old(self, days: int = 30) -> int:
        """Delete notifications older than *days*. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()
        with self._lock:
            data = self._read()
            original = len(data)
            data = [d for d in data if d.get("created_at", "") >= cutoff_iso]
            deleted = original - len(data)
            if deleted:
                self._write(data)
        return deleted


# ── per-tenant singleton factory ───────────────────────────────────────────────

_notification_stores: dict[str, NotificationStore] = {}
_ns_lock = threading.Lock()


def get_notification_store(tenant_id: str) -> NotificationStore:
    """Return a shared NotificationStore instance for the given tenant."""
    with _ns_lock:
        if tenant_id not in _notification_stores:
            _notification_stores[tenant_id] = NotificationStore(tenant_id)
        return _notification_stores[tenant_id]

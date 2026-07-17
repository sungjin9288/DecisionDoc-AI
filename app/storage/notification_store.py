"""app/storage/notification_store.py — Per-tenant notification storage.

Storage: data/tenants/{tenant_id}/notifications.json  (list of dicts)
Process-local locks reduce contention; backend CAS preserves worker-safe updates.
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
from typing import Any, Callable, TypeVar

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.notification_store")

_notification_locks: dict[Path, threading.RLock] = {}
_notification_locks_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")


class NotificationStoreError(ValueError):
    """Raised when persisted notification state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _notification_locks_guard:
        return _notification_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NotificationStoreError(
                f"Duplicate key in notification state: {key!r}"
            )
        result[key] = value
    return result


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
    required_strings = (
        "notification_id",
        "tenant_id",
        "recipient_id",
        "event_type",
        "title",
        "body",
        "context_type",
        "context_id",
        "created_at",
    )
    if any(not isinstance(d.get(field), str) for field in required_strings):
        raise NotificationStoreError("Invalid notification record")
    if any(
        not d[field]
        for field in (
            "notification_id",
            "tenant_id",
            "recipient_id",
            "event_type",
            "context_type",
            "created_at",
        )
    ):
        raise NotificationStoreError("Invalid notification identity")
    boolean_fields = ("is_read", "sent_email", "sent_slack")
    if any(not isinstance(d.get(field), bool) for field in boolean_fields):
        raise NotificationStoreError("Invalid notification delivery state")
    return Notification(
        notification_id=d["notification_id"],
        tenant_id=d["tenant_id"],
        recipient_id=d["recipient_id"],
        event_type=d["event_type"],
        title=d["title"],
        body=d["body"],
        context_type=d["context_type"],
        context_id=d["context_id"],
        is_read=d["is_read"],
        created_at=d["created_at"],
        sent_email=d["sent_email"],
        sent_slack=d["sent_slack"],
    )


# ── NotificationStore ─────────────────────────────────────────────────────────


class NotificationStore:
    """Thread-safe notification state scoped to a single tenant."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        resolved_data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._tenant_id = require_tenant_id(tenant_id)
        self._backend = backend or get_state_backend(data_dir=resolved_data_dir)
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "notifications.json"
        )
        self._path = resolved_data_dir / self._relative_path
        self._lock = _lock_for_path(self._path)

    # ── internal helpers ───────────────────────────────────────────────────

    def _read_state(self) -> tuple[str | None, list[dict]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise NotificationStoreError(
                "Invalid notification state document"
            ) from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw)

    def _decode_records(self, raw: str) -> list[dict]:
        if not raw.strip():
            raise NotificationStoreError("Invalid notification state document")
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise NotificationStoreError("Invalid notification state document") from exc
        if not isinstance(records, list):
            raise NotificationStoreError("Invalid notification state document")
        self._validate_records(records)
        return records

    def _read(self) -> list[dict]:
        return self._read_state()[1]

    @staticmethod
    def _mutation_ids(record: dict) -> list[str]:
        mutation_ids = record.get(_MUTATION_IDS_FIELD, [])
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise NotificationStoreError("Invalid notification mutation history")
        return list(mutation_ids)

    def _record_mutation(
        self,
        record: dict,
        *,
        previous: dict | None,
        mutation_id: str,
    ) -> dict:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    def _validate_records(self, records: list[dict]) -> None:
        notification_ids: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise NotificationStoreError("Invalid notification record")
            if not self._owns(record):
                continue
            notification = _notif_from_dict(record)
            self._mutation_ids(record)
            if notification.notification_id in notification_ids:
                raise NotificationStoreError("Duplicate notification identity")
            notification_ids.add(notification.notification_id)

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        records: list[dict],
        committed: Callable[[list[dict]], bool],
    ) -> bool:
        self._validate_records(records)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        try:
            if expected is None:
                return self._backend.write_text_if_absent(
                    self._relative_path,
                    payload,
                )
            return self._backend.replace_text_if_equal(
                self._relative_path,
                expected=expected,
                replacement=payload,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_text(self._relative_path)
            except (StateBackendError, UnicodeError):
                observed = None
            if observed == payload:
                return True
            if observed is not None:
                try:
                    observed_records = self._decode_records(observed)
                except NotificationStoreError:
                    pass
                else:
                    if committed(observed_records):
                        return True
            raise NotificationStoreError(
                "Failed to persist notification state"
            ) from exc

    def _mutate(
        self,
        change: Callable[[list[dict]], tuple[_MutationResult, bool]],
        *,
        committed: Callable[[list[dict]], bool],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, records = self._read_state()
            result, changed = change(records)
            if not changed:
                return result
            if self._persist_if_current(
                expected=expected,
                records=records,
                committed=committed,
            ):
                return result
        raise NotificationStoreError(
            "Notification state changed too many times to persist safely"
        )

    def _owns(self, record: dict) -> bool:
        return record.get("tenant_id") == self._tenant_id

    # ── public API ─────────────────────────────────────────────────────────

    def create(
        self,
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
            tenant_id=self._tenant_id,
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
        _notif_from_dict(asdict(notif))
        mutation_id = uuid.uuid4().hex
        persisted = self._record_mutation(
            asdict(notif),
            previous=None,
            mutation_id=mutation_id,
        )

        def apply(records: list[dict]) -> tuple[Notification, bool]:
            if any(
                self._owns(record)
                and record.get("notification_id") == notif.notification_id
                for record in records
            ):
                raise NotificationStoreError("Duplicate notification identity")
            records.append(persisted)
            return notif, True

        def was_committed(records: list[dict]) -> bool:
            return any(
                self._owns(record)
                and record.get("notification_id") == notif.notification_id
                and mutation_id in self._mutation_ids(record)
                for record in records
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

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
        items = [
            record
            for record in data
            if self._owns(record) and record.get("recipient_id") == recipient_id
        ]
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
            1
            for record in data
            if self._owns(record)
            and record.get("recipient_id") == recipient_id
            and not record.get("is_read", False)
        )

    def mark_read(self, notification_id: str, recipient_id: str) -> bool:
        """Mark a single notification as read. Returns True if found."""
        mutation_id = uuid.uuid4().hex

        def apply(records: list[dict]) -> tuple[bool, bool]:
            for index, record in enumerate(records):
                if (
                    self._owns(record)
                    and record.get("notification_id") == notification_id
                    and record.get("recipient_id") == recipient_id
                ):
                    updated = dict(record)
                    updated["is_read"] = True
                    records[index] = self._record_mutation(
                        updated,
                        previous=record,
                        mutation_id=mutation_id,
                    )
                    return True, True
            return False, False

        def was_committed(records: list[dict]) -> bool:
            return any(
                self._owns(record)
                and record.get("notification_id") == notification_id
                and mutation_id in self._mutation_ids(record)
                for record in records
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def mark_all_read(self, recipient_id: str) -> int:
        """Mark all notifications for a user as read. Returns count updated."""
        mutation_id = uuid.uuid4().hex
        changed_ids: set[str] = set()

        def apply(records: list[dict]) -> tuple[int, bool]:
            changed_ids.clear()
            for index, record in enumerate(records):
                if (
                    self._owns(record)
                    and record.get("recipient_id") == recipient_id
                    and not record.get("is_read", False)
                ):
                    notification_id = record["notification_id"]
                    updated = dict(record)
                    updated["is_read"] = True
                    records[index] = self._record_mutation(
                        updated,
                        previous=record,
                        mutation_id=mutation_id,
                    )
                    changed_ids.add(notification_id)
            return len(changed_ids), bool(changed_ids)

        def was_committed(records: list[dict]) -> bool:
            committed_ids = {
                record.get("notification_id")
                for record in records
                if self._owns(record)
                and mutation_id in self._mutation_ids(record)
            }
            return changed_ids <= committed_ids

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def mark_email_sent(self, notification_id: str) -> None:
        """Record that an email was sent for this notification."""
        self._mark_delivery_sent(notification_id, field="sent_email")

    def mark_slack_sent(self, notification_id: str) -> None:
        """Record that a Slack message was sent for this notification."""
        self._mark_delivery_sent(notification_id, field="sent_slack")

    def _mark_delivery_sent(self, notification_id: str, *, field: str) -> None:
        mutation_id = uuid.uuid4().hex

        def apply(records: list[dict]) -> tuple[None, bool]:
            for index, record in enumerate(records):
                if (
                    self._owns(record)
                    and record.get("notification_id") == notification_id
                ):
                    updated = dict(record)
                    updated[field] = True
                    records[index] = self._record_mutation(
                        updated,
                        previous=record,
                        mutation_id=mutation_id,
                    )
                    return None, True
            return None, False

        def was_committed(records: list[dict]) -> bool:
            return any(
                self._owns(record)
                and record.get("notification_id") == notification_id
                and mutation_id in self._mutation_ids(record)
                for record in records
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def delete_for_user(self, user_id: str) -> int:
        """Delete all notifications belonging to a withdrawn user.

        Returns the count of deleted notifications.
        """
        deleted_ids: set[str] = set()

        def apply(records: list[dict]) -> tuple[int, bool]:
            deleted_ids.clear()
            deleted_ids.update(
                record["notification_id"]
                for record in records
                if self._owns(record) and record.get("recipient_id") == user_id
            )
            if not deleted_ids:
                return 0, False
            records[:] = [
                record
                for record in records
                if not self._owns(record) or record.get("recipient_id") != user_id
            ]
            return len(deleted_ids), True

        def was_committed(records: list[dict]) -> bool:
            remaining_ids = {
                record.get("notification_id")
                for record in records
                if self._owns(record)
            }
            return deleted_ids.isdisjoint(remaining_ids)

        with self._lock:
            deleted = self._mutate(apply, committed=was_committed)
            if deleted:
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
        deleted_ids: set[str] = set()

        def apply(records: list[dict]) -> tuple[int, bool]:
            deleted_ids.clear()
            deleted_ids.update(
                record["notification_id"]
                for record in records
                if self._owns(record)
                and record.get("created_at", "") < cutoff_iso
            )
            if not deleted_ids:
                return 0, False
            records[:] = [
                record
                for record in records
                if not self._owns(record)
                or record.get("notification_id") not in deleted_ids
            ]
            return len(deleted_ids), True

        def was_committed(records: list[dict]) -> bool:
            remaining_ids = {
                record.get("notification_id")
                for record in records
                if self._owns(record)
            }
            return deleted_ids.isdisjoint(remaining_ids)

        with self._lock:
            return self._mutate(apply, committed=was_committed)


# ── per-tenant singleton factory ───────────────────────────────────────────────


def get_notification_store(
    tenant_id: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> NotificationStore:
    """Return a notification store for the given tenant."""
    if backend is not None:
        return NotificationStore(tenant_id, data_dir=data_dir, backend=backend)

    resolved_data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data")).resolve()
    storage_kind = os.getenv("DECISIONDOC_STATE_STORAGE") or os.getenv(
        "DECISIONDOC_STORAGE", "local"
    )
    bucket = os.getenv("DECISIONDOC_STATE_S3_BUCKET") or os.getenv(
        "DECISIONDOC_S3_BUCKET", ""
    )
    prefix = os.getenv("DECISIONDOC_STATE_S3_PREFIX") or os.getenv(
        "DECISIONDOC_S3_PREFIX", ""
    )
    cache_key = (
        require_tenant_id(tenant_id),
        str(resolved_data_dir),
        storage_kind,
        bucket,
        prefix,
    )

    with _ns_lock:
        store = _notification_stores.get(cache_key)
        if store is None:
            store = NotificationStore(cache_key[0], data_dir=resolved_data_dir)
            _notification_stores[cache_key] = store
        return store


_notification_stores: dict[tuple[str, str, str, str, str], NotificationStore] = {}
_ns_lock = threading.Lock()

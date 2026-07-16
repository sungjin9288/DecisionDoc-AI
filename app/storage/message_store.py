"""app/storage/message_store.py — Tenant-scoped team messaging with @mention support.

Storage: data/tenants/{tenant_id}/messages.json
Thread-safe within one process across stores that share a data root.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


_message_locks: dict[Path, threading.RLock] = {}
_message_locks_guard = threading.Lock()


class MessageStoreError(ValueError):
    """Raised when persisted message state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _message_locks_guard:
        return _message_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MessageStoreError(f"Duplicate key in message state: {key!r}")
        result[key] = value
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_MENTION_RE = re.compile(r"@(\S+)")


@dataclass
class Message:
    message_id: str
    tenant_id: str
    author_id: str
    author_name: str
    content: str          # raw content with @username mentions
    mentions: list[str]   # list of mentioned user_ids (resolved at write time)
    context_type: str     # "general" | "approval" | "project" | "document"
    context_id: str       # approval_id / project_id / request_id
    created_at: str
    edited_at: str | None
    is_deleted: bool


def _parse_mention_names(content: str) -> list[str]:
    """Return list of raw @mention strings (without @) from content."""
    return _MENTION_RE.findall(content)


class MessageStore:
    """Thread-safe message state scoped to a single tenant."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        root = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._backend = backend or get_state_backend(data_dir=root)
        self._relative_path = str(Path("tenants") / self._tenant_id / "messages.json")
        self._path = root / self._relative_path
        self._lock = _lock_for_path(self._path)

    # ── internal helpers ──────────────────────────────────────────────────

    def _read(self) -> list[dict]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return []
        if not raw.strip():
            raise MessageStoreError("Invalid message state document")
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise MessageStoreError("Invalid message state document") from exc
        if not isinstance(records, list):
            raise MessageStoreError("Invalid message state document")

        message_ids: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise MessageStoreError("Invalid message record")
            if record.get("tenant_id") != self._tenant_id:
                continue
            message = self._to_message(record)
            if message.message_id in message_ids:
                raise MessageStoreError("Duplicate message identity")
            message_ids.add(message.message_id)
        return records

    def _write(self, data: list[dict]) -> None:
        self._backend.write_text(
            self._relative_path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def _to_message(self, d: dict) -> Message:
        required_strings = (
            "message_id",
            "tenant_id",
            "author_id",
            "author_name",
            "content",
            "context_type",
            "context_id",
            "created_at",
        )
        if any(not isinstance(d.get(field), str) for field in required_strings):
            raise MessageStoreError("Invalid message record")
        identity_fields = (
            "message_id",
            "tenant_id",
            "author_id",
            "context_type",
            "created_at",
        )
        if any(not d[field] for field in identity_fields):
            raise MessageStoreError("Invalid message identity")
        mentions = d.get("mentions")
        if not isinstance(mentions, list) or any(
            not isinstance(mention, str) for mention in mentions
        ):
            raise MessageStoreError("Invalid message mentions")
        edited_at = d.get("edited_at")
        if edited_at is not None and not isinstance(edited_at, str):
            raise MessageStoreError("Invalid message edit timestamp")
        if not isinstance(d.get("is_deleted"), bool):
            raise MessageStoreError("Invalid message deletion state")
        return Message(
            message_id=d["message_id"],
            tenant_id=d["tenant_id"],
            author_id=d["author_id"],
            author_name=d["author_name"],
            content=d["content"],
            mentions=mentions,
            context_type=d["context_type"],
            context_id=d["context_id"],
            created_at=d["created_at"],
            edited_at=edited_at,
            is_deleted=d["is_deleted"],
        )

    def _owns(self, record: dict) -> bool:
        return record.get("tenant_id") == self._tenant_id

    # ── mention resolution ────────────────────────────────────────────────

    def _resolve_mentions(self, content: str) -> list[str]:
        """Resolve @username strings to user_ids via UserStore.

        Falls back to storing the raw username string if user not found
        (e.g. in tests or when UserStore is unavailable).
        """
        names = _parse_mention_names(content)
        if not names:
            return []
        try:
            from app.storage.user_store import get_user_store
            store = get_user_store(self._tenant_id)
            resolved: list[str] = []
            for name in names:
                user = store.get_by_username(name)
                if user:
                    resolved.append(user.user_id)
                else:
                    resolved.append(name)  # store raw name as fallback
            return list(dict.fromkeys(resolved))  # deduplicate while preserving order
        except Exception:
            return names

    # ── public API ────────────────────────────────────────────────────────

    def post(
        self,
        author_id: str,
        author_name: str,
        content: str,
        context_type: str,
        context_id: str,
    ) -> Message:
        """Post a new message, auto-resolving @mention strings to user_ids."""
        mentions = self._resolve_mentions(content)
        msg = Message(
            message_id=str(uuid.uuid4()),
            tenant_id=self._tenant_id,
            author_id=author_id,
            author_name=author_name,
            content=content,
            mentions=mentions,
            context_type=context_type,
            context_id=context_id,
            created_at=_now_iso(),
            edited_at=None,
            is_deleted=False,
        )
        self._to_message(asdict(msg))
        with self._lock:
            data = self._read()
            data.append(asdict(msg))
            self._write(data)
        return msg

    def get_thread(
        self,
        context_type: str,
        context_id: str,
        limit: int = 50,
    ) -> list[Message]:
        """Return the most recent `limit` non-deleted messages for a context thread."""
        with self._lock:
            data = self._read()
        msgs = [
            self._to_message(m)
            for m in data
            if self._owns(m)
            and m["context_type"] == context_type
            and m["context_id"] == context_id
            and not m["is_deleted"]
        ]
        return msgs[-limit:]

    def get_mentions(self, user_id: str, limit: int = 20) -> list[Message]:
        """Return the most recent `limit` messages where user_id is mentioned."""
        with self._lock:
            data = self._read()
        msgs = [
            self._to_message(m)
            for m in data
            if self._owns(m) and user_id in m["mentions"] and not m["is_deleted"]
        ]
        return msgs[-limit:]

    def edit(self, message_id: str, author_id: str, new_content: str) -> Message:
        """Edit a message. Only the original author may edit."""
        if not isinstance(new_content, str):
            raise MessageStoreError("Invalid message content")
        with self._lock:
            data = self._read()
            for i, m in enumerate(data):
                if self._owns(m) and m["message_id"] == message_id:
                    if m["author_id"] != author_id:
                        raise PermissionError(
                            "본인이 작성한 메시지만 수정할 수 있습니다."
                        )
                    data[i]["content"] = new_content
                    data[i]["edited_at"] = _now_iso()
                    self._write(data)
                    return self._to_message(data[i])
        raise ValueError(f"메시지를 찾을 수 없습니다: {message_id}")

    def delete(self, message_id: str, author_id: str) -> None:
        """Soft-delete a message. Only the original author may delete."""
        with self._lock:
            data = self._read()
            for i, m in enumerate(data):
                if self._owns(m) and m["message_id"] == message_id:
                    if m["author_id"] != author_id:
                        raise PermissionError(
                            "본인이 작성한 메시지만 삭제할 수 있습니다."
                        )
                    data[i]["is_deleted"] = True
                    self._write(data)
                    return
        raise ValueError(f"메시지를 찾을 수 없습니다: {message_id}")

    def get_unread_count(self, user_id: str, since: str) -> int:
        """Count unread mentions since the given ISO timestamp."""
        with self._lock:
            data = self._read()
        return sum(
            1
            for m in data
            if self._owns(m)
            and user_id in m["mentions"]
            and not m["is_deleted"]
            and m["created_at"] > since
        )


# ── per-tenant factory ─────────────────────────────────────────────────────────

_msg_stores: dict[tuple[str, str, str, str, str], MessageStore] = {}
_ms_lock = threading.Lock()


def get_message_store(
    tenant_id: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> MessageStore:
    """Return a shared MessageStore instance for the given tenant."""
    if backend is not None:
        return MessageStore(tenant_id, data_dir=data_dir, backend=backend)

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

    with _ms_lock:
        store = _msg_stores.get(cache_key)
        if store is None:
            store = MessageStore(cache_key[0], data_dir=resolved_data_dir)
            _msg_stores[cache_key] = store
        return store

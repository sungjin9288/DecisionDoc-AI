"""app/storage/message_store.py — Tenant-scoped team messaging with @mention support.

Storage: data/tenants/{tenant_id}/messages.json
Thread-safe via threading.Lock per store instance.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.storage.base import atomic_write_text


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
    """Thread-safe, file-backed message store scoped to a single tenant."""

    def __init__(self, tenant_dir: Path) -> None:
        self._path = tenant_dir / "messages.json"
        self._lock = threading.Lock()
        tenant_dir.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write([])

    # ── internal helpers ──────────────────────────────────────────────────

    def _read(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, data: list[dict]) -> None:
        atomic_write_text(self._path, json.dumps(data, ensure_ascii=False, indent=2))

    def _to_message(self, d: dict) -> Message:
        return Message(**d)

    # ── mention resolution ────────────────────────────────────────────────

    def _resolve_mentions(
        self, content: str, tenant_id: str
    ) -> list[str]:
        """Resolve @username strings to user_ids via UserStore.

        Falls back to storing the raw username string if user not found
        (e.g. in tests or when UserStore is unavailable).
        """
        names = _parse_mention_names(content)
        if not names:
            return []
        try:
            from app.storage.user_store import get_user_store
            store = get_user_store(tenant_id)
            resolved: list[str] = []
            for name in names:
                user = store.get_by_username(tenant_id, name)
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
        tenant_id: str,
        author_id: str,
        author_name: str,
        content: str,
        context_type: str,
        context_id: str,
    ) -> Message:
        """Post a new message, auto-resolving @mention strings to user_ids."""
        mentions = self._resolve_mentions(content, tenant_id)
        msg = Message(
            message_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
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
        with self._lock:
            data = self._read()
            data.append(asdict(msg))
            self._write(data)
        return msg

    def get_thread(
        self,
        tenant_id: str,
        context_type: str,
        context_id: str,
        limit: int = 50,
    ) -> list[Message]:
        """Return the most recent `limit` non-deleted messages for a context thread."""
        with self._lock:
            data = self._read()
        msgs = [
            self._to_message(m) for m in data
            if m["tenant_id"] == tenant_id
            and m["context_type"] == context_type
            and m["context_id"] == context_id
            and not m["is_deleted"]
        ]
        return msgs[-limit:]

    def get_mentions(self, tenant_id: str, user_id: str, limit: int = 20) -> list[Message]:
        """Return the most recent `limit` messages where user_id is mentioned."""
        with self._lock:
            data = self._read()
        msgs = [
            self._to_message(m) for m in data
            if m["tenant_id"] == tenant_id
            and user_id in m["mentions"]
            and not m["is_deleted"]
        ]
        return msgs[-limit:]

    def edit(self, message_id: str, author_id: str, new_content: str) -> Message:
        """Edit a message. Only the original author may edit."""
        with self._lock:
            data = self._read()
            for i, m in enumerate(data):
                if m["message_id"] == message_id:
                    if m["author_id"] != author_id:
                        raise PermissionError("본인이 작성한 메시지만 수정할 수 있습니다.")
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
                if m["message_id"] == message_id:
                    if m["author_id"] != author_id:
                        raise PermissionError("본인이 작성한 메시지만 삭제할 수 있습니다.")
                    data[i]["is_deleted"] = True
                    self._write(data)
                    return
        raise ValueError(f"메시지를 찾을 수 없습니다: {message_id}")

    def get_unread_count(self, tenant_id: str, user_id: str, since: str) -> int:
        """Count unread mentions since the given ISO timestamp."""
        with self._lock:
            data = self._read()
        return sum(
            1 for m in data
            if m["tenant_id"] == tenant_id
            and user_id in m["mentions"]
            and not m["is_deleted"]
            and m["created_at"] > since
        )


# ── per-tenant factory ─────────────────────────────────────────────────────────

_msg_stores: dict[str, MessageStore] = {}
_ms_lock = threading.Lock()


def get_message_store(tenant_id: str) -> MessageStore:
    """Return a shared MessageStore instance for the given tenant."""
    with _ms_lock:
        if tenant_id not in _msg_stores:
            import os
            data_dir = Path(os.getenv("DATA_DIR", "./data"))
            tenant_dir = data_dir / "tenants" / tenant_id
            _msg_stores[tenant_id] = MessageStore(tenant_dir)
        return _msg_stores[tenant_id]

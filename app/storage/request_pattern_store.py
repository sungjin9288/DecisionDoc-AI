"""RequestPatternStore — append-only JSONL log of bundle generation requests.

Each tenant keeps a separate log of requests and whether they matched an existing
bundle. Unmatched requests accumulate until BundleAutoExpander analyses them.

Storage: data/tenants/{tenant_id}/request_patterns.jsonl

Record shape:
    {
        "record_id": str,
        "tenant_id": str,
        "timestamp":  str,       # ISO-8601 UTC
        "raw_input":  str,       # title + goal, truncated to 200 chars
        "bundle_id":  str | None,
        "matched":    bool,
    }
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.storage.request_pattern")
_path_locks: dict[Path, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _lock_for_path(path: Path) -> threading.Lock:
    with _path_locks_guard:
        return _path_locks.setdefault(path.resolve(), threading.Lock())


class RequestPatternStore:
    """Thread-safe, append-only JSONL store for request pattern tracking."""

    def __init__(self, data_dir: Path, *, tenant_id: str) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        tenant_dir = Path(data_dir) / "tenants" / self._tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "request_patterns.jsonl"
        self._lock = _lock_for_path(self._path)

    # ── Public API ────────────────────────────────────────────────────────

    def record_request(
        self,
        raw_input: str,
        bundle_id: str | None,
        matched: bool,
    ) -> str:
        """Append one request record. Returns the generated record_id."""
        record_id = str(uuid.uuid4())
        record = {
            "record_id": record_id,
            "tenant_id": self._tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_input": raw_input[:200],
            "bundle_id": bundle_id,
            "matched": matched,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            current = ""
            if self._path.exists():
                current = self._path.read_text(encoding="utf-8")
            if current and not current.endswith("\n"):
                current += "\n"
            atomic_write_text(self._path, current + line + "\n")
        return record_id

    def get_unmatched(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return up to `limit` most recent unmatched (matched=False) records."""
        all_records = self._read_all()
        unmatched = [r for r in all_records if not r.get("matched", True)]
        return unmatched[-limit:]

    def get_all(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return up to `limit` most recent records (matched + unmatched)."""
        all_records = self._read_all()
        return all_records[-limit:]

    def clear_unmatched(self) -> int:
        """Rewrite the JSONL file keeping only matched records.

        Returns the number of unmatched records removed.
        """
        with self._lock:
            all_records = self._read_records_unlocked()
            removed = sum(
                1
                for record in all_records
                if self._owns(record) and not record.get("matched", True)
            )
            if removed == 0:
                return 0
            retained = [
                record
                for record in all_records
                if not self._owns(record) or record.get("matched", True)
            ]
            content = "".join(
                json.dumps(record, ensure_ascii=False) + "\n"
                for record in retained
            )
            atomic_write_text(self._path, content)
        return removed

    # ── Internal helpers ──────────────────────────────────────────────────

    def _read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                record
                for record in self._read_records_unlocked()
                if self._owns(record)
            ]

    def _owns(self, record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        stored_tenant_id = record.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self._tenant_id

    def _read_records_unlocked(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        records: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                _log.warning("Skipping malformed request pattern record: %s", exc)
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

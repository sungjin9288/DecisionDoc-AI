"""RequestPatternStore — append-only JSONL log of bundle generation requests.

Each line records one user request with whether it was matched to an existing bundle.
Unmatched requests accumulate until BundleAutoExpander analyses them.

Record shape:
    {
        "record_id": str,
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

_log = logging.getLogger("decisiondoc.storage.request_pattern")


class RequestPatternStore:
    """Thread-safe, append-only JSONL store for request pattern tracking."""

    def __init__(self, data_dir: Path) -> None:
        self._path = Path(data_dir) / "request_patterns.jsonl"
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_input": raw_input[:200],
            "bundle_id": bundle_id,
            "matched": matched,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
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
        all_records = self._read_all()
        matched = [r for r in all_records if r.get("matched", True)]
        removed = len(all_records) - len(matched)
        if removed == 0:
            return 0
        with self._lock:
            with self._path.open("w", encoding="utf-8") as f:
                for r in matched:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return removed

    # ── Internal helpers ──────────────────────────────────────────────────

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        with self._lock:
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
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _log.warning("Skipping malformed request pattern record: %s", exc)
                continue
        return records

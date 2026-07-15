"""finetune_store.py — OpenAI fine-tune 데이터셋 저장소.

고품질 생성 결과를 OpenAI fine-tuning format으로 축적합니다.

Storage layout:
    data/tenants/{tenant_id}/finetune/dataset.jsonl   — JSONL records (one per line)
    data/tenants/{tenant_id}/finetune/metadata.json   — stats and export history

Record shape per line:
    {
      "messages": [
        {"role": "system",    "content": "<bundle prompt>"},
        {"role": "user",      "content": "<title>\\n목표: <goal>\\n컨텍스트: <context>"},
        {"role": "assistant", "content": "<generated markdown>"},
      ],
      "metadata": {
        "bundle_id": str,
        "request_id": str,
        "heuristic_score": float,
        "llm_score": float | None,
        "user_rating": int | None,
        "collected_at": str,
        "source": "high_rating" | "high_eval_score" | "ab_test_winner"
      }
    }
"""
from __future__ import annotations

import json
import functools
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.storage.finetune")


class FineTuneStore:
    """Thread-safe JSONL store for OpenAI fine-tuning dataset collection."""

    def __init__(self, data_dir: Path, *, tenant_id: str) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._dir = Path(data_dir) / "tenants" / self._tenant_id / "finetune"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dataset_path = self._dir / "dataset.jsonl"
        self._meta_path    = self._dir / "metadata.json"
        self._lock = threading.Lock()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_meta(self) -> dict[str, Any]:
        if not self._meta_path.exists():
            return {"export_count": 0, "exports": []}
        try:
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"export_count": 0, "exports": []}
        if not isinstance(meta, dict):
            return {"export_count": 0, "exports": []}
        stored_tenant_id = meta.get("tenant_id")
        if stored_tenant_id is not None and stored_tenant_id != self._tenant_id:
            return {"export_count": 0, "exports": []}
        return meta

    def _save_meta(self, meta: dict[str, Any]) -> None:
        payload = {**meta, "tenant_id": self._tenant_id}
        atomic_write_text(
            self._meta_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _assert_meta_owned(self) -> None:
        if not self._meta_path.exists():
            return
        try:
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(meta, dict):
            return
        stored_tenant_id = meta.get("tenant_id")
        if stored_tenant_id is not None and stored_tenant_id != self._tenant_id:
            raise ValueError("Fine-tune metadata tenant does not match store tenant")

    def _owns(self, record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            return False
        stored_tenant_id = metadata.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self._tenant_id

    def _read_records_raw(self) -> list[dict[str, Any]]:
        """Return all raw records from dataset.jsonl (no lock — caller holds lock)."""
        if not self._dataset_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self._dataset_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _log.warning("Skipping malformed fine-tune record: %s", exc)
        return records

    def _read_owned_records(self) -> list[dict[str, Any]]:
        return [record for record in self._read_records_raw() if self._owns(record)]

    def _seen_request_ids(self) -> set[str]:
        """Collect already-stored request_ids for deduplication."""
        ids: set[str] = set()
        for rec in self._read_owned_records():
            rid = rec.get("metadata", {}).get("request_id")
            if rid:
                ids.add(rid)
        return ids

    # ── Public API ────────────────────────────────────────────────────────

    def save_record(
        self,
        messages: list[dict[str, str]],
        metadata: dict[str, Any],
    ) -> bool:
        """Append one fine-tune record.

        Deduplicates by ``metadata['request_id']``.
        Returns True if saved, False if skipped (duplicate or invalid).
        """
        request_id = metadata.get("request_id", "")
        if not request_id:
            return False
        supplied_tenant_id = metadata.get("tenant_id")
        if supplied_tenant_id is not None and supplied_tenant_id != self._tenant_id:
            raise ValueError("Fine-tune record tenant does not match store tenant")

        with self._lock:
            if request_id in self._seen_request_ids():
                return False  # already stored

            stored_metadata = {
                **metadata,
                "tenant_id": self._tenant_id,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
            record = {"messages": messages, "metadata": stored_metadata}
            line = json.dumps(record, ensure_ascii=False)
            with self._dataset_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True

    def get_stats(self) -> dict[str, Any]:
        """Return dataset statistics.

        Keys: total_records, per_bundle_count, avg_heuristic,
              last_collected, export_count.
        """
        with self._lock:
            records = self._read_owned_records()
            meta = self._load_meta()

        total = len(records)
        per_bundle: dict[str, int] = {}
        h_scores: list[float] = []
        last_collected: str | None = None

        for rec in records:
            m = rec.get("metadata", {})
            bid = m.get("bundle_id", "unknown")
            per_bundle[bid] = per_bundle.get(bid, 0) + 1
            hs = m.get("heuristic_score")
            if hs is not None:
                h_scores.append(float(hs))
            ts = m.get("collected_at")
            if ts and (last_collected is None or ts > last_collected):
                last_collected = ts

        avg_h: float | None = round(sum(h_scores) / len(h_scores), 3) if h_scores else None

        return {
            "total_records":    total,
            "per_bundle_count": per_bundle,
            "avg_heuristic":    avg_h,
            "last_collected":   last_collected,
            "export_count":     meta.get("export_count", 0),
        }

    def export_for_training(
        self,
        bundle_id: str | None = None,
        min_records: int = 10,
    ) -> str | None:
        """Export filtered records to a timestamped JSONL file for training.

        Writes only the ``messages`` field (strips ``metadata``).
        Returns the file path on success, None if fewer than ``min_records``.
        """
        with self._lock:
            records = self._read_owned_records()
            filtered = [
                record
                for record in records
                if bundle_id is None
                or record.get("metadata", {}).get("bundle_id") == bundle_id
            ]
            if len(filtered) < min_records:
                return None

            self._assert_meta_owned()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            suffix = f"_{bundle_id}" if bundle_id else ""
            filename = f"export{suffix}_{timestamp}.jsonl"
            export_path = self._dir / filename
            lines = [
                json.dumps({"messages": record["messages"]}, ensure_ascii=False)
                for record in filtered
            ]
            atomic_write_text(export_path, "\n".join(lines) + "\n")

            meta = self._load_meta()
            meta["export_count"] = meta.get("export_count", 0) + 1
            meta.setdefault("exports", []).append({
                "filename": filename,
                "bundle_id": bundle_id,
                "record_count": len(filtered),
                "exported_at": datetime.now(timezone.utc).isoformat(),
            })
            self._save_meta(meta)

        return str(export_path)

    def get_export_path(self, filename: str) -> Path | None:
        """Return an existing export owned by this tenant."""
        with self._lock:
            exports = self._load_meta().get("exports", [])
        if not isinstance(exports, list):
            return None
        declared_filenames = {
            item.get("filename")
            for item in exports
            if isinstance(item, dict)
        }
        if filename not in declared_filenames:
            return None
        path = self._dir / filename
        return path if path.is_file() else None

    def get_records(
        self,
        bundle_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` records, optionally filtered by bundle_id."""
        with self._lock:
            records = self._read_owned_records()
        if bundle_id:
            records = [
                r for r in records
                if r.get("metadata", {}).get("bundle_id") == bundle_id
            ]
        return records[-limit:]

    def clear_dataset(self) -> int:
        """Delete all records. Returns count of removed records."""
        with self._lock:
            records = self._read_records_raw()
            owned = [record for record in records if self._owns(record)]
            remaining = [record for record in records if not self._owns(record)]
            if remaining:
                payload = "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in remaining
                )
                atomic_write_text(self._dataset_path, payload)
            elif self._dataset_path.exists():
                self._dataset_path.unlink()
        return len(owned)


@functools.lru_cache(maxsize=50)
def get_finetune_store(tenant_id: str) -> FineTuneStore:
    """Return a cached FineTuneStore for the given tenant."""
    return FineTuneStore(Path(os.getenv("DATA_DIR", "./data")), tenant_id=tenant_id)


def clear_finetune_store_cache() -> None:
    """Invalidate the store factory cache after tenant or data-dir changes."""
    get_finetune_store.cache_clear()

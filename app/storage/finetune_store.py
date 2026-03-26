"""finetune_store.py — OpenAI fine-tune 데이터셋 저장소.

고품질 생성 결과를 OpenAI fine-tuning format으로 축적합니다.

Storage layout:
    data/finetune/dataset.jsonl   — JSONL records (one per line)
    data/finetune/metadata.json   — stats and export history

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
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.storage.finetune")


class FineTuneStore:
    """Thread-safe JSONL store for OpenAI fine-tuning dataset collection."""

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir) / "finetune"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dataset_path = self._dir / "dataset.jsonl"
        self._meta_path    = self._dir / "metadata.json"
        self._lock = threading.Lock()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_meta(self) -> dict[str, Any]:
        if not self._meta_path.exists():
            return {"export_count": 0, "exports": []}
        try:
            return json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"export_count": 0, "exports": []}

    def _save_meta(self, meta: dict[str, Any]) -> None:
        self._meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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

    def _seen_request_ids(self) -> set[str]:
        """Collect already-stored request_ids for deduplication."""
        ids: set[str] = set()
        for rec in self._read_records_raw():
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

        with self._lock:
            if request_id in self._seen_request_ids():
                return False  # already stored

            metadata["collected_at"] = datetime.now(timezone.utc).isoformat()
            record = {"messages": messages, "metadata": metadata}
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
            records = self._read_records_raw()
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
            records = self._read_records_raw()

        filtered = [
            r for r in records
            if bundle_id is None or r.get("metadata", {}).get("bundle_id") == bundle_id
        ]

        if len(filtered) < min_records:
            return None

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        suffix = f"_{bundle_id}" if bundle_id else ""
        filename = f"export{suffix}_{ts}.jsonl"
        export_path = self._dir / filename

        lines = [
            json.dumps({"messages": r["messages"]}, ensure_ascii=False)
            for r in filtered
        ]
        export_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Update metadata
        with self._lock:
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

    def get_records(
        self,
        bundle_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` records, optionally filtered by bundle_id."""
        with self._lock:
            records = self._read_records_raw()
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
            count = len(records)
            if self._dataset_path.exists():
                self._dataset_path.unlink()
        return count

"""Tenant-scoped evaluation result storage."""

from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class EvalStoreError(RuntimeError):
    """Raised when persisted evaluation state cannot be trusted."""


_eval_stores: dict[tuple[Any, ...], "EvalStore"] = {}
_eval_stores_guard = threading.Lock()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvalStoreError(f"Duplicate key in evaluation state: {key!r}")
        result[key] = value
    return result


@dataclass
class EvalRecord:
    """One document-generation evaluation result."""

    request_id: str
    bundle_id: str
    timestamp: str
    heuristic_score: float
    llm_score: float | None
    issues: list[str]
    doc_scores: dict[str, float]
    llm_feedbacks: list[str] = field(default_factory=list)
    tenant_id: str | None = None


class EvalStore:
    """Read and append evaluation evidence for one tenant."""

    _BASE_FIELDS = {
        "request_id",
        "bundle_id",
        "timestamp",
        "heuristic_score",
        "llm_score",
        "issues",
        "doc_scores",
    }
    _OPTIONAL_FIELDS = {"llm_feedbacks", "tenant_id"}

    def __init__(
        self,
        data_dir: Path,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir)
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "eval_results.jsonl"
        )
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=self._relative_path,
        )

    @staticmethod
    def _identifier(value: object, *, field_name: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise EvalStoreError(f"Invalid evaluation {field_name}")
        return value

    @staticmethod
    def _score(
        value: object,
        *,
        field_name: str,
        minimum: float,
        maximum: float,
    ) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not minimum <= value <= maximum
        ):
            raise EvalStoreError(f"Invalid evaluation {field_name}")
        return float(value)

    def _owns(self, record: object) -> bool:
        return isinstance(record, dict) and record.get("tenant_id") in {
            None,
            self._tenant_id,
        }

    def _validate_owned(self, record: dict[str, Any], *, legacy: bool) -> None:
        allowed_fields = self._BASE_FIELDS | self._OPTIONAL_FIELDS
        if legacy:
            allowed_fields -= {"tenant_id"}
        if not self._BASE_FIELDS.issubset(record) or not set(record).issubset(
            allowed_fields
        ):
            raise EvalStoreError("Invalid evaluation record fields")
        if not legacy and record.get("tenant_id") != self._tenant_id:
            raise EvalStoreError("Evaluation tenant ownership mismatch")

        self._identifier(record.get("request_id"), field_name="request identity")
        self._identifier(record.get("bundle_id"), field_name="bundle identity")
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise EvalStoreError("Invalid evaluation timestamp")
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise EvalStoreError("Invalid evaluation timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise EvalStoreError("Invalid evaluation timestamp")

        self._score(
            record.get("heuristic_score"),
            field_name="heuristic score",
            minimum=0.0,
            maximum=1.0,
        )
        llm_score = record.get("llm_score")
        if llm_score is not None:
            self._score(
                llm_score,
                field_name="LLM score",
                minimum=0.0,
                maximum=5.0,
            )

        issues = record.get("issues")
        feedbacks = record.get("llm_feedbacks", [])
        if not isinstance(issues, list) or any(
            not isinstance(item, str) for item in issues
        ):
            raise EvalStoreError("Invalid evaluation issues")
        if not isinstance(feedbacks, list) or any(
            not isinstance(item, str) for item in feedbacks
        ):
            raise EvalStoreError("Invalid evaluation LLM feedbacks")

        doc_scores = record.get("doc_scores")
        if not isinstance(doc_scores, dict):
            raise EvalStoreError("Invalid evaluation document scores")
        for doc_key, score in doc_scores.items():
            self._identifier(doc_key, field_name="document identity")
            self._score(
                score,
                field_name="document score",
                minimum=0.0,
                maximum=1.0,
            )

    def _load_raw(self) -> list[dict[str, Any]]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None or raw == "":
            return []

        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                raise EvalStoreError(
                    f"Invalid blank line in evaluation state at line {line_number}"
                )
            try:
                record = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, EvalStoreError) as exc:
                raise EvalStoreError(
                    f"Invalid evaluation state document at line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise EvalStoreError(f"Invalid evaluation record at line {line_number}")

            stored_tenant_id = record.get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise EvalStoreError("Invalid evaluation tenant identity")
                if stored_tenant_id != self._tenant_id:
                    records.append(record)
                    continue
            self._validate_owned(record, legacy=stored_tenant_id is None)
            records.append(record)
        return records

    def _save(self, records: list[dict[str, Any]]) -> None:
        text = "".join(
            f"{json.dumps(record, ensure_ascii=False, separators=(',', ':'))}\n"
            for record in records
        )
        self._backend.write_text(
            self._relative_path,
            text,
            content_type="application/x-ndjson; charset=utf-8",
        )

    def append(self, record: EvalRecord) -> None:
        """Append one validated evaluation result."""
        if record.tenant_id is not None and record.tenant_id != self._tenant_id:
            raise ValueError("Eval record tenant does not match store tenant")
        payload = {**asdict(record), "tenant_id": self._tenant_id}
        try:
            self._validate_owned(payload, legacy=False)
        except EvalStoreError as exc:
            raise ValueError(str(exc)) from exc

        with self._lock:
            records = self._load_raw()
            records.append(payload)
            self._save(records)

    def load_all(self) -> list[EvalRecord]:
        """Load all trusted evaluation records owned by this tenant."""
        with self._lock:
            records = self._load_raw()
        return [EvalRecord(**record) for record in records if self._owns(record)]

    def summary(self) -> dict[str, Any]:
        records = self.load_all()
        if not records:
            return {"total": 0, "avg_heuristic": None, "by_bundle": {}}

        by_bundle: dict[str, list[float]] = {}
        for record in records:
            by_bundle.setdefault(record.bundle_id, []).append(record.heuristic_score)
        return {
            "total": len(records),
            "avg_heuristic": round(
                sum(record.heuristic_score for record in records) / len(records),
                3,
            ),
            "by_bundle": {
                bundle_id: {
                    "count": len(scores),
                    "avg": round(sum(scores) / len(scores), 3),
                    "min": round(min(scores), 3),
                    "max": round(max(scores), 3),
                }
                for bundle_id, scores in by_bundle.items()
            },
            "recent": [
                asdict(record)
                for record in sorted(
                    records,
                    key=lambda item: item.timestamp,
                    reverse=True,
                )[:10]
            ],
        }

    def get_bundle_history(
        self,
        bundle_id: str,
        limit: int = 50,
    ) -> list[EvalRecord]:
        records = [
            record for record in self.load_all() if record.bundle_id == bundle_id
        ]
        return sorted(records, key=lambda item: item.timestamp, reverse=True)[:limit]

    def get_all_stats(self) -> dict[str, Any]:
        records = self.load_all()
        if not records:
            return {
                "total_count": 0,
                "avg_heuristic": None,
                "avg_llm": None,
                "low_quality_count": 0,
            }

        llm_scores = [
            record.llm_score for record in records if record.llm_score is not None
        ]
        return {
            "total_count": len(records),
            "avg_heuristic": round(
                sum(record.heuristic_score for record in records) / len(records),
                3,
            ),
            "avg_llm": (
                round(sum(llm_scores) / len(llm_scores), 3) if llm_scores else None
            ),
            "low_quality_count": sum(
                1 for record in records if record.heuristic_score < 0.6
            ),
        }

    def get_per_bundle_stats(self) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[EvalRecord]] = {}
        for record in self.load_all():
            grouped.setdefault(record.bundle_id, []).append(record)

        result: dict[str, dict[str, Any]] = {}
        for bundle_id, records in grouped.items():
            ordered = sorted(records, key=lambda item: item.timestamp)
            llm_scores = [
                record.llm_score for record in ordered if record.llm_score is not None
            ]
            result[bundle_id] = {
                "count": len(ordered),
                "avg_heuristic": round(
                    sum(record.heuristic_score for record in ordered) / len(ordered),
                    3,
                ),
                "avg_llm": (
                    round(sum(llm_scores) / len(llm_scores), 3) if llm_scores else None
                ),
                "last_timestamp": ordered[-1].timestamp,
                "recent_scores": [record.heuristic_score for record in ordered[-10:]],
            }
        return result


def get_eval_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> EvalStore:
    """Return a cached store for one tenant and one state backend."""
    tenant_id = require_tenant_id(tenant_id)
    root = Path(data_dir or os.getenv("DATA_DIR", "./data"))
    explicit_backend = backend is not None
    selected_backend = backend or get_state_backend(data_dir=root)
    key = (
        tenant_id,
        root.resolve(),
        *state_backend_identity(
            selected_backend,
            data_dir=root,
            explicit_backend=explicit_backend,
        ),
    )
    with _eval_stores_guard:
        store = _eval_stores.get(key)
        if store is None:
            store = EvalStore(
                root,
                tenant_id=tenant_id,
                backend=selected_backend,
            )
            _eval_stores[key] = store
        return store


def clear_eval_store_cache() -> None:
    with _eval_stores_guard:
        _eval_stores.clear()

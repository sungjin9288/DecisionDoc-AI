"""Tenant-scoped A/B prompt experiment state."""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class ABTestStoreError(RuntimeError):
    """Raised when persisted A/B experiment state cannot be trusted."""


_ab_test_stores: dict[tuple[Any, ...], "ABTestStore"] = {}
_ab_test_stores_guard = threading.Lock()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ABTestStoreError(f"Duplicate key in A/B test state: {key!r}")
        result[key] = value
    return result


class ABTestStore:
    """Read and update prompt experiments owned by one tenant."""

    _RECORD_FIELDS = {
        "bundle_id",
        "tenant_id",
        "status",
        "variant_a_hint",
        "variant_b_hint",
        "min_samples",
        "generation_count",
        "created_at",
        "concluded_at",
        "winner",
        "winner_avg_score",
        "results",
    }
    _RESULT_FIELDS = {
        "heuristic_score",
        "llm_score",
        "recorded_at",
    }
    _VARIANTS = {"variant_a", "variant_b"}

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
            Path("tenants") / self._tenant_id / "ab_tests.json"
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
            raise ABTestStoreError(f"Invalid A/B test {field_name}")
        return value

    @staticmethod
    def _hint(value: object, *, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ABTestStoreError(f"Invalid A/B test {field_name}")
        return value

    @staticmethod
    def _timestamp(value: object, *, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise ABTestStoreError(f"Invalid A/B test {field_name}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ABTestStoreError(f"Invalid A/B test {field_name}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ABTestStoreError(f"Invalid A/B test {field_name}")
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
            raise ABTestStoreError(f"Invalid A/B test {field_name}")
        return float(value)

    def _owns(self, record: object) -> bool:
        return isinstance(record, dict) and record.get("tenant_id") in {
            None,
            self._tenant_id,
        }

    def _validate_result(self, result: object) -> None:
        if not isinstance(result, dict) or set(result) != self._RESULT_FIELDS:
            raise ABTestStoreError("Invalid A/B test result fields")
        self._score(
            result.get("heuristic_score"),
            field_name="heuristic score",
            minimum=0.0,
            maximum=1.0,
        )
        llm_score = result.get("llm_score")
        if llm_score is not None:
            self._score(
                llm_score,
                field_name="LLM score",
                minimum=0.0,
                maximum=5.0,
            )
        self._timestamp(result.get("recorded_at"), field_name="result timestamp")

    def _validate_owned(
        self,
        storage_key: str,
        record: dict[str, Any],
        *,
        legacy: bool,
    ) -> None:
        expected_fields = self._RECORD_FIELDS - ({"tenant_id"} if legacy else set())
        if set(record) != expected_fields:
            raise ABTestStoreError("Invalid A/B test record fields")

        bundle_id = self._identifier(
            record.get("bundle_id"),
            field_name="bundle identity",
        )
        if storage_key != bundle_id:
            raise ABTestStoreError("A/B test storage identity mismatch")
        if not legacy and record.get("tenant_id") != self._tenant_id:
            raise ABTestStoreError("A/B test tenant ownership mismatch")

        status = record.get("status")
        if status not in {"active", "concluded"}:
            raise ABTestStoreError("Invalid A/B test status")
        self._hint(record.get("variant_a_hint"), field_name="variant A hint")
        self._hint(record.get("variant_b_hint"), field_name="variant B hint")

        min_samples = record.get("min_samples")
        generation_count = record.get("generation_count")
        if (
            isinstance(min_samples, bool)
            or not isinstance(min_samples, int)
            or min_samples < 1
        ):
            raise ABTestStoreError("Invalid A/B test minimum sample count")
        if (
            isinstance(generation_count, bool)
            or not isinstance(generation_count, int)
            or generation_count < 0
        ):
            raise ABTestStoreError("Invalid A/B test generation count")

        self._timestamp(record.get("created_at"), field_name="creation timestamp")
        concluded_at = record.get("concluded_at")
        winner = record.get("winner")
        winner_avg_score = record.get("winner_avg_score")
        if status == "active":
            if concluded_at is not None or winner is not None or winner_avg_score is not None:
                raise ABTestStoreError("Active A/B test has conclusion fields")
        else:
            self._timestamp(concluded_at, field_name="conclusion timestamp")
            if winner not in self._VARIANTS:
                raise ABTestStoreError("Invalid A/B test winner")
            self._score(
                winner_avg_score,
                field_name="winner average score",
                minimum=0.0,
                maximum=1.0,
            )

        results = record.get("results")
        if not isinstance(results, dict) or set(results) != self._VARIANTS:
            raise ABTestStoreError("Invalid A/B test result buckets")
        for variant in sorted(self._VARIANTS):
            variant_results = results[variant]
            if not isinstance(variant_results, list):
                raise ABTestStoreError("Invalid A/B test result list")
            for result in variant_results:
                self._validate_result(result)

    def _load(self) -> dict[str, Any]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise ABTestStoreError("A/B test state could not be read") from exc
        if raw is None:
            return {}
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, ABTestStoreError) as exc:
            raise ABTestStoreError("Invalid A/B test state document") from exc
        if not isinstance(data, dict):
            raise ABTestStoreError("Invalid A/B test state")

        for storage_key, record in data.items():
            self._identifier(storage_key, field_name="storage identity")
            if not isinstance(record, dict):
                raise ABTestStoreError("Invalid A/B test record")
            stored_tenant_id = record.get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise ABTestStoreError("Invalid A/B test tenant identity")
                if stored_tenant_id != self._tenant_id:
                    continue
            self._validate_owned(
                storage_key,
                record,
                legacy=stored_tenant_id is None,
            )
        return data

    def _persist(self, data: dict[str, Any]) -> None:
        try:
            self._backend.write_text(
                self._relative_path,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        except StateBackendError as exc:
            raise ABTestStoreError("A/B test state could not be written") from exc

    def create_test(
        self,
        bundle_id: str,
        variant_a_hint: str,
        variant_b_hint: str,
        min_samples: int = 5,
    ) -> None:
        """Create or replace one tenant-owned experiment."""
        try:
            self._identifier(bundle_id, field_name="bundle identity")
            self._hint(variant_a_hint, field_name="variant A hint")
            self._hint(variant_b_hint, field_name="variant B hint")
        except ABTestStoreError as exc:
            raise ValueError(str(exc)) from exc
        if (
            isinstance(min_samples, bool)
            or not isinstance(min_samples, int)
            or min_samples < 1
        ):
            raise ValueError("Invalid A/B test minimum sample count")

        record = {
            "bundle_id": bundle_id,
            "tenant_id": self._tenant_id,
            "status": "active",
            "variant_a_hint": variant_a_hint,
            "variant_b_hint": variant_b_hint,
            "min_samples": min_samples,
            "generation_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "concluded_at": None,
            "winner": None,
            "winner_avg_score": None,
            "results": {"variant_a": [], "variant_b": []},
        }
        self._validate_owned(bundle_id, record, legacy=False)
        with self._lock:
            data = self._load()
            existing = data.get(bundle_id)
            if existing is not None and not self._owns(existing):
                raise ABTestStoreError("Foreign A/B test must be preserved")
            data[bundle_id] = record
            self._persist(data)

    def get_active_test(self, bundle_id: str) -> dict[str, Any] | None:
        """Return the active experiment for a bundle, if one exists."""
        with self._lock:
            record = self._load().get(bundle_id)
            if self._owns(record) and record.get("status") == "active":
                return record
            return None

    def get_next_variant(self, bundle_id: str) -> str | None:
        """Assign the next variant and persist the round-robin counter."""
        with self._lock:
            data = self._load()
            record = data.get(bundle_id)
            if not self._owns(record) or record.get("status") != "active":
                return None
            generation_count = record["generation_count"]
            variant = "variant_a" if generation_count % 2 == 0 else "variant_b"
            record["generation_count"] = generation_count + 1
            self._validate_owned(
                bundle_id,
                record,
                legacy="tenant_id" not in record,
            )
            self._persist(data)
            return variant

    def record_result(
        self,
        bundle_id: str,
        variant: str,
        heuristic_score: float,
        llm_score: float | None = None,
    ) -> None:
        """Append one validated evaluation result to an active experiment."""
        if variant not in self._VARIANTS:
            raise ValueError("Invalid A/B test variant")
        result = {
            "heuristic_score": heuristic_score,
            "llm_score": llm_score,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._validate_result(result)
        except ABTestStoreError as exc:
            raise ValueError(str(exc)) from exc

        with self._lock:
            data = self._load()
            record = data.get(bundle_id)
            if not self._owns(record) or record.get("status") != "active":
                return
            record["results"][variant].append(result)
            self._validate_owned(
                bundle_id,
                record,
                legacy="tenant_id" not in record,
            )
            self._persist(data)

    def evaluate_and_conclude(self, bundle_id: str) -> str | None:
        """Conclude an experiment once both variants have enough results."""
        with self._lock:
            data = self._load()
            record = data.get(bundle_id)
            if not self._owns(record) or record.get("status") != "active":
                return None

            min_samples = record["min_samples"]
            a_results = record["results"]["variant_a"]
            b_results = record["results"]["variant_b"]
            if len(a_results) < min_samples or len(b_results) < min_samples:
                return None

            a_average = sum(item["heuristic_score"] for item in a_results) / len(a_results)
            b_average = sum(item["heuristic_score"] for item in b_results) / len(b_results)
            winner = "variant_a" if a_average >= b_average else "variant_b"
            winner_average = a_average if winner == "variant_a" else b_average

            from app.storage.prompt_override_store import PromptOverrideStore

            PromptOverrideStore(
                self._data_dir,
                tenant_id=self._tenant_id,
                backend=self._backend,
            ).save_override(
                bundle_id=bundle_id,
                override_hint=record[f"{winner}_hint"],
                trigger_reason="ab_test_winner",
                avg_score_before=0.0,
            )

            record["status"] = "concluded"
            record["concluded_at"] = datetime.now(timezone.utc).isoformat()
            record["winner"] = winner
            record["winner_avg_score"] = round(winner_average, 3)
            self._validate_owned(
                bundle_id,
                record,
                legacy="tenant_id" not in record,
            )
            self._persist(data)
            return winner

    def list_active_tests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                record
                for record in self._load().values()
                if self._owns(record) and record.get("status") == "active"
            ]

    def list_concluded_tests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                record
                for record in self._load().values()
                if self._owns(record) and record.get("status") == "concluded"
            ]

    def list_tests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record for record in self._load().values() if self._owns(record)]

    def delete_test(self, bundle_id: str) -> None:
        with self._lock:
            data = self._load()
            if not self._owns(data.get(bundle_id)):
                return
            data.pop(bundle_id)
            self._persist(data)


def get_ab_test_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> ABTestStore:
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
    with _ab_test_stores_guard:
        store = _ab_test_stores.get(key)
        if store is None:
            store = ABTestStore(
                root,
                tenant_id=tenant_id,
                backend=selected_backend,
            )
            _ab_test_stores[key] = store
        return store


def clear_ab_test_store_cache() -> None:
    """Invalidate cached A/B stores after application configuration changes."""
    with _ab_test_stores_guard:
        _ab_test_stores.clear()

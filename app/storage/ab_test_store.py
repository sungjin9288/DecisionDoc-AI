"""Tenant-scoped A/B prompt experiment state."""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.storage.conditional_state import mutate_with_retry, persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class ABTestStoreError(RuntimeError):
    """Raised when persisted A/B experiment state cannot be trusted."""


class ABTestConflictError(ABTestStoreError):
    """Raised when an A/B lifecycle transition conflicts with active work."""


_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64
_INCARNATION_ID_FIELD = "_incarnation_id"
_MUTATION_IDS_FIELD = "_mutation_ids"
_PENDING_CONCLUSION_FIELD = "_pending_conclusion"
_PRIVATE_RECORD_FIELDS = {
    _INCARNATION_ID_FIELD,
    _MUTATION_IDS_FIELD,
    _PENDING_CONCLUSION_FIELD,
}


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
    _PENDING_CONCLUSION_FIELDS = {
        "operation_id",
        "winner",
        "winner_avg_score",
        "override_hint",
        "concluded_at",
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
        record_fields = set(record)
        if (
            not expected_fields.issubset(record_fields)
            or record_fields - expected_fields - _PRIVATE_RECORD_FIELDS
        ):
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
        self._incarnation_id(record)
        mutation_ids = self._mutation_ids(record)
        pending = record.get(_PENDING_CONCLUSION_FIELD)
        if pending is not None:
            if status != "active":
                raise ABTestStoreError(
                    "Concluded A/B test has a pending conclusion"
                )
            self._validate_pending_conclusion(
                pending,
                record=record,
                mutation_ids=mutation_ids,
            )

    @staticmethod
    def _conclusion_values(
        record: dict[str, Any],
    ) -> tuple[str, float, str] | None:
        min_samples = record["min_samples"]
        a_results = record["results"]["variant_a"]
        b_results = record["results"]["variant_b"]
        if len(a_results) < min_samples or len(b_results) < min_samples:
            return None
        a_average = sum(item["heuristic_score"] for item in a_results) / len(a_results)
        b_average = sum(item["heuristic_score"] for item in b_results) / len(b_results)
        winner = "variant_a" if a_average >= b_average else "variant_b"
        winner_average = a_average if winner == "variant_a" else b_average
        return winner, round(winner_average, 3), record[f"{winner}_hint"]

    def _validate_pending_conclusion(
        self,
        pending: object,
        *,
        record: dict[str, Any],
        mutation_ids: list[str],
    ) -> None:
        if (
            not isinstance(pending, dict)
            or set(pending) != self._PENDING_CONCLUSION_FIELDS
        ):
            raise ABTestStoreError("Invalid A/B test pending conclusion")
        operation_id = self._identifier(
            pending.get("operation_id"),
            field_name="conclusion operation identity",
        )
        if operation_id not in mutation_ids:
            raise ABTestStoreError(
                "A/B test pending conclusion has no mutation receipt"
            )
        if pending.get("winner") not in self._VARIANTS:
            raise ABTestStoreError("Invalid A/B test pending winner")
        self._score(
            pending.get("winner_avg_score"),
            field_name="pending winner average score",
            minimum=0.0,
            maximum=1.0,
        )
        self._hint(
            pending.get("override_hint"),
            field_name="pending winner hint",
        )
        self._timestamp(
            pending.get("concluded_at"),
            field_name="pending conclusion timestamp",
        )
        expected = self._conclusion_values(record)
        if expected is None or (
            pending["winner"],
            pending["winner_avg_score"],
            pending["override_hint"],
        ) != expected:
            raise ABTestStoreError(
                "A/B test pending conclusion does not match persisted results"
            )

    def _decode_state(self, raw: str) -> dict[str, Any]:
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

    def _read_state(self) -> tuple[str | None, dict[str, Any]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise ABTestStoreError("A/B test state could not be read") from exc
        if raw is None:
            return None, {}
        return raw, self._decode_state(raw)

    def _load(self) -> dict[str, Any]:
        return self._read_state()[1]

    @staticmethod
    def _incarnation_id(record: dict[str, Any]) -> str | None:
        incarnation_id = record.get(_INCARNATION_ID_FIELD)
        if incarnation_id is not None and (
            not isinstance(incarnation_id, str) or not incarnation_id
        ):
            raise ABTestStoreError("Invalid A/B test incarnation")
        return incarnation_id

    @staticmethod
    def _mutation_ids(record: dict[str, Any]) -> list[str]:
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
            raise ABTestStoreError("Invalid A/B test mutation history")
        return list(mutation_ids)

    def _record_mutation(
        self,
        record: dict[str, Any],
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    @staticmethod
    def _public_record(record: dict[str, Any]) -> dict[str, Any]:
        public = dict(record)
        for field in _PRIVATE_RECORD_FIELDS:
            public.pop(field, None)
        return public

    def _persist_if_current(
        self,
        expected: str | None,
        data: dict[str, Any],
        committed: Callable[[dict[str, Any]], bool],
    ) -> bool:
        for storage_key, record in data.items():
            if self._owns(record):
                self._validate_owned(
                    storage_key,
                    record,
                    legacy="tenant_id" not in record,
                )
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=payload,
                decode=self._decode_state,
                committed=committed,
                decode_errors=(ABTestStoreError,),
            )
        except StateBackendError as exc:
            raise ABTestStoreError("A/B test state could not be written") from exc

    def _mutate(
        self,
        change: Callable[
            [dict[str, Any]],
            tuple[Any, bool],
        ],
        *,
        committed: Callable[[dict[str, Any]], bool],
    ) -> Any:
        return mutate_with_retry(
            read=self._read_state,
            change=change,
            persist=self._persist_if_current,
            committed=committed,
            max_attempts=_MAX_MUTATION_ATTEMPTS,
            conflict_error=lambda: ABTestStoreError(
                "A/B test state changed too many times to persist safely"
            ),
        )

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

        mutation_id = uuid.uuid4().hex
        incarnation_id = uuid.uuid4().hex
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
            _INCARNATION_ID_FIELD: incarnation_id,
        }

        def apply(data: dict[str, Any]) -> tuple[None, bool]:
            existing = data.get(bundle_id)
            if existing is not None and not self._owns(existing):
                raise ABTestStoreError("Foreign A/B test must be preserved")
            if (
                self._owns(existing)
                and existing.get(_PENDING_CONCLUSION_FIELD) is not None
            ):
                raise ABTestStoreError(
                    "A/B test conclusion is already in progress"
                )
            data[bundle_id] = self._record_mutation(
                record,
                previous=existing,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, Any]) -> bool:
            existing = data.get(bundle_id)
            return (
                self._owns(existing)
                and mutation_id in self._mutation_ids(existing)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def get_active_test(self, bundle_id: str) -> dict[str, Any] | None:
        """Return the active experiment for a bundle, if one exists."""
        with self._lock:
            record = self._load().get(bundle_id)
            if self._owns(record) and record.get("status") == "active":
                return self._public_record(record)
            return None

    def get_next_assignment(
        self,
        bundle_id: str,
    ) -> tuple[str, str, str | None] | None:
        """Atomically assign a variant, its hint, and the experiment identity."""
        mutation_id = uuid.uuid4().hex
        legacy_incarnation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(
            data: dict[str, Any],
        ) -> tuple[tuple[str, str, str | None] | None, bool]:
            nonlocal target_bound, target_incarnation
            record = data.get(bundle_id)
            if not self._owns(record) or record.get("status") != "active":
                return None, False
            incarnation_id = self._incarnation_id(record)
            pending = record.get(_PENDING_CONCLUSION_FIELD)
            if pending is not None:
                variant = pending["winner"]
                return (
                    variant,
                    record[f"{variant}_hint"],
                    incarnation_id,
                ), False
            incarnation_id = incarnation_id or legacy_incarnation_id
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return None, False
            generation_count = record["generation_count"]
            variant = "variant_a" if generation_count % 2 == 0 else "variant_b"
            updated = dict(record)
            updated["generation_count"] = generation_count + 1
            updated[_INCARNATION_ID_FIELD] = incarnation_id
            data[bundle_id] = self._record_mutation(
                updated,
                previous=record,
                mutation_id=mutation_id,
            )
            return (
                variant,
                record[f"{variant}_hint"],
                incarnation_id,
            ), True

        def was_committed(data: dict[str, Any]) -> bool:
            record = data.get(bundle_id)
            return (
                self._owns(record)
                and self._incarnation_id(record) == target_incarnation
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def get_next_variant(self, bundle_id: str) -> str | None:
        """Assign the next variant and return its name."""
        assignment = self.get_next_assignment(bundle_id)
        return assignment[0] if assignment is not None else None

    def record_result(
        self,
        bundle_id: str,
        variant: str,
        heuristic_score: float,
        llm_score: float | None = None,
        *,
        experiment_id: str | None = None,
    ) -> bool:
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

        mutation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(data: dict[str, Any]) -> tuple[bool, bool]:
            nonlocal target_bound, target_incarnation
            record = data.get(bundle_id)
            if not self._owns(record) or record.get("status") != "active":
                return False, False
            if (
                experiment_id is not None
                and self._incarnation_id(record) != experiment_id
            ):
                return False, False
            if record.get(_PENDING_CONCLUSION_FIELD) is not None:
                return False, False
            incarnation_id = self._incarnation_id(record)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return False, False
            if mutation_id in self._mutation_ids(record):
                return True, False
            updated = dict(record)
            updated_results = {
                name: list(items)
                for name, items in record["results"].items()
            }
            updated_results[variant].append(result)
            updated["results"] = updated_results
            data[bundle_id] = self._record_mutation(
                updated,
                previous=record,
                mutation_id=mutation_id,
            )
            return True, True

        def was_committed(data: dict[str, Any]) -> bool:
            record = data.get(bundle_id)
            return (
                self._owns(record)
                and self._incarnation_id(record) == target_incarnation
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def evaluate_and_conclude(
        self,
        bundle_id: str,
        *,
        experiment_id: str | None = None,
    ) -> str | None:
        """Conclude an experiment once both variants have enough results."""
        from app.storage.ab_test_conclusion import evaluate_and_conclude

        return evaluate_and_conclude(
            self,
            bundle_id,
            experiment_id=experiment_id,
        )

    def _list_tests(self, status: str | None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._public_record(record)
                for record in self._load().values()
                if self._owns(record)
                and (status is None or record.get("status") == status)
            ]

    def list_active_tests(self) -> list[dict[str, Any]]:
        return self._list_tests("active")

    def list_concluded_tests(self) -> list[dict[str, Any]]:
        return self._list_tests("concluded")

    def list_tests(self) -> list[dict[str, Any]]:
        return self._list_tests(None)

    def delete_test(self, bundle_id: str) -> None:
        target_incarnation: str | None = None
        target_bound = False

        def apply(data: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_bound, target_incarnation
            record = data.get(bundle_id)
            if not self._owns(record):
                return None, False
            if record.get(_PENDING_CONCLUSION_FIELD) is not None:
                raise ABTestConflictError(
                    "A/B test conclusion is in progress and cannot be reset"
                )
            incarnation_id = self._incarnation_id(record)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return None, False
            data.pop(bundle_id)
            return None, True

        def was_committed(data: dict[str, Any]) -> bool:
            record = data.get(bundle_id)
            return not (
                self._owns(record)
                and self._incarnation_id(record) == target_incarnation
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)


def get_ab_test_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> ABTestStore:
    """Return a cached store for one tenant and one state backend."""
    from app.storage.ab_test_store_factory import get_cached_ab_test_store

    return get_cached_ab_test_store(
        tenant_id,
        data_dir,
        backend=backend,
    )


def clear_ab_test_store_cache() -> None:
    """Invalidate cached A/B stores after application configuration changes."""
    from app.storage.ab_test_store_factory import clear_cached_ab_test_stores

    clear_cached_ab_test_stores()

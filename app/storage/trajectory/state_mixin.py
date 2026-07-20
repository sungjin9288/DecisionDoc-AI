"""Conditional state authority for DocumentOps trajectories."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import mutate_with_retry, persist_text_if_current
from app.storage.state_backend import StateBackendError

_APPEND_ID_FIELD = "_append_id"
_INCARNATION_FIELD = "_incarnation"
_REVIEW_MUTATION_IDS_FIELD = "_review_mutation_ids"
_PRIVATE_RECORD_FIELDS = {
    _APPEND_ID_FIELD,
    _INCARNATION_FIELD,
    _REVIEW_MUTATION_IDS_FIELD,
}
_REVIEW_FIELDS = {
    "human_feedback",
    "human_review_history",
    "human_review_status",
}
_IDENTITY_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_REVIEW_MUTATIONS = 64
_TRAJECTORY_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"
_MutationResult = TypeVar("_MutationResult")


class TrajectoryStoreError(RuntimeError):
    """Raised when persisted trajectory state cannot be trusted."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrajectoryStoreError(f"Duplicate key in trajectory state: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise TrajectoryStoreError(f"Invalid numeric value in trajectory state: {value}")


class TrajectoryStateMixin:
    """Read and mutate one tenant trajectory JSONL object with bounded CAS."""

    def _read_records_unlocked(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            self._public_record(record)
            for record in self._owned_records(
                self._read_raw_records_unlocked(tenant_id),
                tenant_id,
            )
        ]

    def _read_raw_records_unlocked(self, tenant_id: str) -> list[dict[str, Any]]:
        return self._read_record_state(tenant_id)[1]

    def _read_record_state(
        self,
        tenant_id: str,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        relative_path = self._jsonl_relative_path(tenant_id)
        try:
            raw = self._backend.read_text(relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise TrajectoryStoreError("Trajectory state could not be read") from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw, tenant_id=tenant_id)

    def _decode_records(
        self,
        raw: str,
        *,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        if not raw:
            raise TrajectoryStoreError("Trajectory state is blank")

        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                raise TrajectoryStoreError(
                    f"Blank trajectory record at line {line_number}"
                )
            try:
                record = json.loads(
                    line,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_nonfinite,
                )
            except (
                json.JSONDecodeError,
                TypeError,
                TrajectoryStoreError,
            ) as exc:
                raise TrajectoryStoreError(
                    f"Invalid trajectory record at line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise TrajectoryStoreError(
                    f"Trajectory record at line {line_number} is not an object"
                )
            records.append(record)

        self._validate_records(records, tenant_id=tenant_id)
        return records

    def _validate_records(
        self,
        records: list[dict[str, Any]],
        *,
        tenant_id: str,
    ) -> None:
        for record in records:
            stored_tenant = record.get("tenant_id")
            if stored_tenant is not None and (
                not isinstance(stored_tenant, str) or not stored_tenant
            ):
                raise TrajectoryStoreError("Invalid trajectory tenant identity")
            if stored_tenant not in (None, tenant_id):
                continue

            trajectory_id = record.get("trajectory_id")
            if not isinstance(trajectory_id, str) or not trajectory_id:
                raise TrajectoryStoreError("Invalid trajectory identity")
            self._validate_private_record_fields(record)

    @staticmethod
    def _validate_private_record_fields(record: dict[str, Any]) -> None:
        for field_name in (_APPEND_ID_FIELD, _INCARNATION_FIELD):
            value = record.get(field_name)
            if value is not None and (
                not isinstance(value, str) or _IDENTITY_PATTERN.fullmatch(value) is None
            ):
                raise TrajectoryStoreError(
                    f"Invalid trajectory private field: {field_name}"
                )

        mutation_ids = record.get(_REVIEW_MUTATION_IDS_FIELD)
        if mutation_ids is None:
            return
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_REVIEW_MUTATIONS
            or any(
                not isinstance(mutation_id, str)
                or _IDENTITY_PATTERN.fullmatch(mutation_id) is None
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise TrajectoryStoreError("Invalid trajectory review mutation history")

    def _serialize_records(
        self,
        records: list[dict[str, Any]],
        *,
        tenant_id: str,
    ) -> str:
        self._validate_records(records, tenant_id=tenant_id)
        self._validate_mutation_identities(records, tenant_id=tenant_id)
        try:
            lines = [
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                for record in records
            ]
        except (TypeError, ValueError) as exc:
            raise TrajectoryStoreError(
                "Trajectory state could not be serialized"
            ) from exc
        return "\n".join(lines) + "\n"

    def _validate_mutation_identities(
        self,
        records: list[dict[str, Any]],
        *,
        tenant_id: str,
    ) -> None:
        all_ids = [
            record.get("trajectory_id")
            for record in records
            if isinstance(record.get("trajectory_id"), str) and record["trajectory_id"]
        ]
        owned_ids = {
            record["trajectory_id"]
            for record in records
            if self._owns_record(record, tenant_id)
            and isinstance(record.get("trajectory_id"), str)
            and record["trajectory_id"]
        }
        for trajectory_id in owned_ids:
            if all_ids.count(trajectory_id) != 1:
                raise TrajectoryStoreError(
                    f"Duplicate trajectory identity: {trajectory_id}"
                )

    def _persist_records_if_current(
        self,
        *,
        tenant_id: str,
        expected: str | None,
        records: list[dict[str, Any]],
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> bool:
        replacement = self._serialize_records(records, tenant_id=tenant_id)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._jsonl_relative_path(tenant_id),
                expected=expected,
                replacement=replacement,
                decode=lambda raw: self._decode_records(
                    raw,
                    tenant_id=tenant_id,
                ),
                committed=committed,
                decode_errors=(TrajectoryStoreError,),
                content_type=_TRAJECTORY_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            raise TrajectoryStoreError(
                "Trajectory state could not be persisted"
            ) from exc

    def _mutate_records(
        self,
        *,
        tenant_id: str,
        change: Callable[
            [list[dict[str, Any]]],
            tuple[_MutationResult, bool],
        ],
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> _MutationResult:
        return mutate_with_retry(
            read=lambda: self._read_record_state(tenant_id),
            change=change,
            persist=lambda expected, records, was_committed: (
                self._persist_records_if_current(
                    tenant_id=tenant_id,
                    expected=expected,
                    records=records,
                    committed=was_committed,
                )
            ),
            committed=committed,
            max_attempts=_MAX_MUTATION_ATTEMPTS,
            conflict_error=lambda: TrajectoryStoreError(
                "Trajectory state changed too many times to persist safely"
            ),
        )

    @staticmethod
    def _public_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.items()
            if key not in _PRIVATE_RECORD_FIELDS
        }

    @staticmethod
    def _owns_record(record: dict[str, Any], tenant_id: str) -> bool:
        return record.get("tenant_id") in (None, tenant_id)

    def _owned_records(
        self,
        records: list[dict[str, Any]],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for record in records:
            trajectory_id = record.get("trajectory_id")
            if not isinstance(trajectory_id, str) or not trajectory_id:
                continue
            counts[trajectory_id] = counts.get(trajectory_id, 0) + 1
        return [
            record
            for record in records
            if self._owns_record(record, tenant_id)
            and isinstance(record.get("trajectory_id"), str)
            and bool(record["trajectory_id"])
            and counts[record["trajectory_id"]] == 1
        ]

    def _find_owned_record(
        self,
        records: list[dict[str, Any]],
        tenant_id: str,
        trajectory_id: str,
    ) -> dict[str, Any] | None:
        matches = [
            record for record in records if record.get("trajectory_id") == trajectory_id
        ]
        if len(matches) != 1 or not self._owns_record(matches[0], tenant_id):
            return None
        return matches[0]

    def _record_identity(
        self,
        record: dict[str, Any],
        *,
        tenant_id: str,
    ) -> str:
        incarnation = record.get(_INCARNATION_FIELD)
        if (
            isinstance(incarnation, str)
            and _IDENTITY_PATTERN.fullmatch(incarnation) is not None
        ):
            return incarnation

        seed = {
            key: value
            for key, value in record.items()
            if key not in _PRIVATE_RECORD_FIELDS | _REVIEW_FIELDS
        }
        try:
            encoded = json.dumps(
                [tenant_id, seed],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TrajectoryStoreError(
                "Trajectory identity could not be derived"
            ) from exc
        return hashlib.sha256(encoded).hexdigest()[:32]

    @staticmethod
    def _same_trajectory_content(
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> bool:
        def creation_content(record: dict[str, Any]) -> dict[str, Any]:
            return {
                key: value
                for key, value in record.items()
                if key
                not in _PRIVATE_RECORD_FIELDS
                | _REVIEW_FIELDS
                | {"created_at", "tenant_id"}
            }

        return creation_content(first) == creation_content(second)

    @staticmethod
    def _review_mutation_ids(record: dict[str, Any]) -> list[str]:
        value = record.get(_REVIEW_MUTATION_IDS_FIELD)
        return list(value) if isinstance(value, list) else []

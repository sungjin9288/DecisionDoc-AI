"""Conditional mutation support for tenant-scoped project state."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Callable, TypeVar

from app.storage.state_backend import StateBackendError
from app.tenant import require_tenant_id


class ProjectStoreError(RuntimeError):
    """Raised when persisted project state cannot be trusted."""


_MutationResult = TypeVar("_MutationResult")
_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectStoreError(f"Duplicate key in project state: {key!r}")
        result[key] = value
    return result


class ProjectStateMutationMixin:
    """Provide CAS retry and uncertain-commit reconciliation to ProjectStore."""

    def _read_state(self, tenant_id: str) -> tuple[str | None, list[dict]]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise ProjectStoreError("Invalid project state document") from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw)

    @staticmethod
    def _decode_records(raw: str) -> list[dict]:
        if not raw.strip():
            raise ProjectStoreError("Invalid project state document")
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ProjectStoreError) as exc:
            raise ProjectStoreError("Invalid project state document") from exc
        if not isinstance(records, list):
            raise ProjectStoreError("Invalid project state document")
        return records

    def _load(self, tenant_id: str) -> list[dict]:
        return self._read_state(tenant_id)[1]

    @staticmethod
    def _mutation_ids(record: dict) -> list[str]:
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
            raise ProjectStoreError("Invalid project mutation history")
        return list(mutation_ids)

    def _record_project(
        self,
        project: Any,
        *,
        previous: dict | None,
        mutation_id: str,
    ) -> dict:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        record = asdict(project)
        record[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return record

    def _persist_if_current(
        self,
        tenant_id: str,
        *,
        expected: str | None,
        records: list[dict],
        committed: Callable[[list[dict]], bool] | None = None,
    ) -> bool:
        self._owned_records(records, tenant_id=tenant_id)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        relative_path = self._relative_path(tenant_id)
        try:
            if expected is None:
                return self._backend.write_text_if_absent(relative_path, payload)
            return self._backend.replace_text_if_equal(
                relative_path,
                expected=expected,
                replacement=payload,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_text(relative_path)
            except StateBackendError:
                observed = None
            if observed == payload:
                return True
            if observed is not None and committed is not None:
                try:
                    observed_records = self._decode_records(observed)
                    self._owned_records(observed_records, tenant_id=tenant_id)
                except ProjectStoreError:
                    pass
                else:
                    if committed(observed_records):
                        return True
            raise ProjectStoreError("Failed to persist project state") from exc

    def _mutate_state(
        self,
        tenant_id: str,
        change: Callable[[list[dict]], tuple[_MutationResult, bool]],
        *,
        committed: Callable[[list[dict]], bool] | None = None,
    ) -> _MutationResult:
        tenant_id = require_tenant_id(tenant_id)
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, records = self._read_state(tenant_id)
            self._owned_records(records, tenant_id=tenant_id)
            result, changed = change(records)
            if not changed:
                return result
            if self._persist_if_current(
                tenant_id,
                expected=expected,
                records=records,
                committed=committed,
            ):
                return result
        raise ProjectStoreError("Project state changed too many times to persist safely")

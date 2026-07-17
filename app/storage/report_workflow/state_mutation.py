"""Conditional mutation support for tenant-scoped report workflow state."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any, Callable

from app.storage.report_workflow.models import ReportWorkflowRecord, _now_iso
from app.storage.state_backend import StateBackendError
from app.tenant import require_tenant_id


class ReportWorkflowStoreError(RuntimeError):
    """Raised when persisted report workflow state cannot be trusted."""


_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportWorkflowStoreError(
                f"Duplicate key in report workflow state: {key!r}"
            )
        result[key] = value
    return result


class ReportWorkflowStateMutationMixin:
    """Persist report workflow changes with conditional create and CAS retries."""

    def _read_state(self, tenant_id: str) -> tuple[str | None, list[Any]]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise ReportWorkflowStoreError(
                "Invalid report workflow state document"
            ) from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw)

    @staticmethod
    def _decode_records(raw: str) -> list[Any]:
        if not raw.strip():
            raise ReportWorkflowStoreError(
                "Invalid report workflow state document"
            )
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ReportWorkflowStoreError) as exc:
            raise ReportWorkflowStoreError(
                "Invalid report workflow state document"
            ) from exc
        if not isinstance(records, list):
            raise ReportWorkflowStoreError(
                "Invalid report workflow state document"
            )
        return records

    def _load(self, tenant_id: str) -> list[Any]:
        return self._read_state(tenant_id)[1]

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
            raise ReportWorkflowStoreError(
                "Invalid report workflow mutation history"
            )
        return list(mutation_ids)

    def _record_workflow(
        self,
        record: ReportWorkflowRecord,
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = asdict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    def _persist_if_current(
        self,
        tenant_id: str,
        *,
        expected: str | None,
        records: list[Any],
        committed: Callable[[list[Any]], bool] | None = None,
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
                except ReportWorkflowStoreError:
                    pass
                else:
                    if committed(observed_records):
                        return True
            raise ReportWorkflowStoreError(
                "Failed to persist report workflow state"
            ) from exc

    def _mutate_state(
        self,
        tenant_id: str,
        change: Callable[[list[Any]], tuple[ReportWorkflowRecord, bool]],
        *,
        committed: Callable[[list[Any]], bool],
    ) -> ReportWorkflowRecord:
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
        raise ReportWorkflowStoreError(
            "Report workflow state changed too many times to persist safely"
        )

    def _mutate_workflow(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        change: Callable[[ReportWorkflowRecord], bool],
    ) -> ReportWorkflowRecord:
        tenant_id = require_tenant_id(tenant_id)
        mutation_id = uuid.uuid4().hex

        def apply(records: list[Any]) -> tuple[ReportWorkflowRecord, bool]:
            found = self._find_in_records(
                report_workflow_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                raise KeyError(
                    f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}"
                )
            index, record = found
            if not change(record):
                return record, False
            record.updated_at = _now_iso()
            self._validate_record(record)
            records[index] = self._record_workflow(
                record,
                previous=records[index],
                mutation_id=mutation_id,
            )
            return record, True

        def mutation_committed(records: list[Any]) -> bool:
            found = self._find_in_records(
                report_workflow_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                return False
            index, _ = found
            return mutation_id in self._mutation_ids(records[index])

        with self._lock(tenant_id):
            return self._mutate_state(
                tenant_id,
                apply,
                committed=mutation_committed,
            )

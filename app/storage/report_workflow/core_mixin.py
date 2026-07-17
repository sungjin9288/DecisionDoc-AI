"""Core report workflow setup, record lookup, and public read/create methods."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.storage.state_backend import (
    StateBackend,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id

from app.storage.report_workflow.models import (
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    _now_iso,
)
from app.storage.report_workflow.state_mutation import ReportWorkflowStoreError


def _require_workflow_id(report_workflow_id: object) -> str:
    if not isinstance(report_workflow_id, str) or not report_workflow_id.strip():
        raise ValueError("Invalid report_workflow_id")
    return report_workflow_id


class ReportWorkflowCoreMixin:
    """Init, tenant-scoped file plumbing, and basic CRUD."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "report_workflows.json")

    def _lock(self, tenant_id: str):
        relative_path = self._relative_path(tenant_id)
        return state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=relative_path,
        )

    def _owned_records(
        self,
        records: list[Any],
        *,
        tenant_id: str,
    ) -> list[tuple[int, ReportWorkflowRecord]]:
        tenant_id = require_tenant_id(tenant_id)
        owned: list[tuple[int, ReportWorkflowRecord]] = []
        workflow_ids: set[str] = set()
        for index, raw_record in enumerate(records):
            if not isinstance(raw_record, dict):
                continue
            if raw_record.get("tenant_id") != tenant_id:
                continue
            try:
                self._mutation_ids(raw_record)
                record = self._from_dict(raw_record)
            except (ReportWorkflowStoreError, TypeError, ValueError) as exc:
                raise ReportWorkflowStoreError(
                    "Invalid owned report workflow record"
                ) from exc
            if record.report_workflow_id in workflow_ids:
                raise ReportWorkflowStoreError("Duplicate report workflow records")
            workflow_ids.add(record.report_workflow_id)
            owned.append((index, record))
        return owned

    def _find(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
    ) -> tuple[int, ReportWorkflowRecord] | None:
        tenant_id = require_tenant_id(tenant_id)
        report_workflow_id = _require_workflow_id(report_workflow_id)
        return self._find_in_records(
            report_workflow_id,
            records=self._load(tenant_id),
            tenant_id=tenant_id,
        )

    def _find_in_records(
        self,
        report_workflow_id: str,
        *,
        records: list[Any],
        tenant_id: str,
    ) -> tuple[int, ReportWorkflowRecord] | None:
        report_workflow_id = _require_workflow_id(report_workflow_id)
        for index, record in self._owned_records(records, tenant_id=tenant_id):
            if record.report_workflow_id == report_workflow_id:
                return index, record
        return None

    def create(
        self,
        *,
        tenant_id: str,
        title: str,
        goal: str = "",
        client: str = "",
        report_type: str = "proposal_presentation",
        audience: str = "",
        owner: str = "",
        pm_reviewer: str = "",
        executive_approver: str = "",
        source_bundle_id: str = "presentation_kr",
        source_request_id: str = "",
        slide_count: int = 6,
        attachments_context: str = "",
        source_refs: list[str] | None = None,
        learning_opt_in: bool = False,
    ) -> ReportWorkflowRecord:
        tenant_id = require_tenant_id(tenant_id)
        now = _now_iso()
        record = ReportWorkflowRecord(
            report_workflow_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            title=title,
            goal=goal,
            client=client,
            report_type=report_type,
            audience=audience,
            owner=owner,
            pm_reviewer=pm_reviewer,
            executive_approver=executive_approver,
            status=ReportWorkflowStatus.PLANNING_REQUIRED.value,
            source_bundle_id=source_bundle_id or "presentation_kr",
            source_request_id=source_request_id,
            slide_count=max(1, min(int(slide_count or 6), 40)),
            attachments_context=attachments_context,
            source_refs=list(source_refs or []),
            learning_opt_in=learning_opt_in,
            created_at=now,
            updated_at=now,
        )
        self._validate_record(record)
        mutation_id = uuid.uuid4().hex

        def append_record(
            records: list[Any],
        ) -> tuple[ReportWorkflowRecord, bool]:
            records.append(
                self._record_workflow(
                    record,
                    previous=None,
                    mutation_id=mutation_id,
                )
            )
            return record, True

        def mutation_committed(records: list[Any]) -> bool:
            found = self._find_in_records(
                record.report_workflow_id,
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
                append_record,
                committed=mutation_committed,
            )

    def get(self, report_workflow_id: str, *, tenant_id: str) -> ReportWorkflowRecord | None:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            return result[1] if result else None

    def list_by_tenant(self, tenant_id: str, status: str | None = None) -> list[ReportWorkflowRecord]:
        tenant_id = require_tenant_id(tenant_id)
        with self._lock(tenant_id):
            records = [
                record
                for _, record in self._owned_records(
                    self._load(tenant_id),
                    tenant_id=tenant_id,
                )
            ]
        if status:
            records = [rec for rec in records if rec.status == status]
        return sorted(records, key=lambda rec: rec.created_at, reverse=True)

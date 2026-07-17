"""Core report workflow persistence: init, tenant path/load/save plumbing,
record lookup (``_find``/``_flush``), and the ``create``/``get``/
``list_by_tenant`` public entry points."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id

from app.storage.report_workflow.models import (
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    _now_iso,
)


class ReportWorkflowStoreError(RuntimeError):
    """Raised when persisted report workflow state cannot be trusted."""


def _require_workflow_id(report_workflow_id: object) -> str:
    if not isinstance(report_workflow_id, str) or not report_workflow_id.strip():
        raise ValueError("Invalid report_workflow_id")
    return report_workflow_id


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportWorkflowStoreError(
                f"Duplicate key in report workflow state: {key!r}"
            )
        result[key] = value
    return result


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

    def _load(self, tenant_id: str) -> list[Any]:
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise ReportWorkflowStoreError(
                "Invalid report workflow state document"
            ) from exc
        if raw is None:
            return []
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

    def _save(self, tenant_id: str, records: list[Any]) -> None:
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        try:
            self._backend.write_text(self._relative_path(tenant_id), payload)
        except StateBackendError as exc:
            raise ReportWorkflowStoreError(
                "Failed to persist report workflow state"
            ) from exc

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
                record = self._from_dict(raw_record)
            except (TypeError, ValueError) as exc:
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
    ) -> tuple[str, list[Any], int, ReportWorkflowRecord] | None:
        tenant_id = require_tenant_id(tenant_id)
        report_workflow_id = _require_workflow_id(report_workflow_id)
        records = self._load(tenant_id)
        for index, record in self._owned_records(records, tenant_id=tenant_id):
            if record.report_workflow_id == report_workflow_id:
                return tenant_id, records, index, record
        return None

    def _flush(
        self,
        tenant_id: str,
        records: list[Any],
        idx: int,
        rec: ReportWorkflowRecord,
    ) -> ReportWorkflowRecord:
        rec.updated_at = _now_iso()
        self._validate_record(rec)
        records[idx] = asdict(rec)
        self._save(tenant_id, records)
        return rec

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
        with self._lock(tenant_id):
            records = self._load(tenant_id)
            self._owned_records(records, tenant_id=tenant_id)
            now = _now_iso()
            rec = ReportWorkflowRecord(
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
            self._validate_record(rec)
            records.append(asdict(rec))
            self._save(tenant_id, records)
            return rec

    def get(self, report_workflow_id: str, *, tenant_id: str) -> ReportWorkflowRecord | None:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            return result[3] if result else None

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

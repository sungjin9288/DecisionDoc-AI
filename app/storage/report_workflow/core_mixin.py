"""Core report workflow persistence: init, tenant path/load/save plumbing,
record lookup (``_find``/``_flush``), and the ``create``/``get``/
``list_by_tenant`` public entry points."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path

from app.storage.base import atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend

from app.storage.report_workflow.models import (
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    _now_iso,
)


class ReportWorkflowCoreMixin:
    """Init, tenant-scoped file plumbing, and basic CRUD."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        super().__init__()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _get_path(self) -> Path:
        return self._base / "tenants"

    def _path(self, tenant_id: str) -> Path:
        p = self._base / "tenants" / tenant_id
        if self._backend.kind == "local":
            p.mkdir(parents=True, exist_ok=True)
        return p / "report_workflows.json"

    def _relative_path(self, tenant_id: str) -> str:
        return str(Path("tenants") / tenant_id / "report_workflows.json")

    def _load(self, tenant_id: str) -> list[dict]:
        raw = self._backend.read_text(self._relative_path(tenant_id))
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self, tenant_id: str, records: list[dict]) -> None:
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        if self._backend.kind == "local":
            atomic_write_text(self._path(tenant_id), payload)
            return
        self._backend.write_text(self._relative_path(tenant_id), payload)

    def _find(
        self,
        report_workflow_id: str,
        tenant_id: str | None = None,
    ) -> tuple[str, list[dict], int, ReportWorkflowRecord] | None:
        if tenant_id is not None:
            records = self._load(tenant_id)
            for idx, raw in enumerate(records):
                if raw.get("report_workflow_id") == report_workflow_id:
                    rec = self._from_dict(raw)
                    if rec.tenant_id != tenant_id:
                        return None
                    return tenant_id, records, idx, rec
            return None

        tenant_paths = self._backend.list_prefix("tenants/")
        tenant_ids = sorted(
            {
                Path(path).parts[1]
                for path in tenant_paths
                if len(Path(path).parts) >= 3 and Path(path).parts[0] == "tenants"
            }
        )
        for tid in tenant_ids:
            records = self._load(tid)
            for idx, raw in enumerate(records):
                if raw.get("report_workflow_id") == report_workflow_id:
                    return tid, records, idx, self._from_dict(raw)
        return None

    def _flush(
        self,
        tenant_id: str,
        records: list[dict],
        idx: int,
        rec: ReportWorkflowRecord,
    ) -> ReportWorkflowRecord:
        rec.updated_at = _now_iso()
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
        with self._lock:
            records = self._load(tenant_id)
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
            records.append(asdict(rec))
            self._save(tenant_id, records)
            return rec

    def get(self, report_workflow_id: str, tenant_id: str | None = None) -> ReportWorkflowRecord | None:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            return result[3] if result else None

    def list_by_tenant(self, tenant_id: str, status: str | None = None) -> list[ReportWorkflowRecord]:
        with self._lock:
            records = [self._from_dict(raw) for raw in self._load(tenant_id)]
        if status:
            records = [rec for rec in records if rec.status == status]
        return sorted(records, key=lambda rec: rec.created_at, reverse=True)

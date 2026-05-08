"""Service layer for DecisionDoc-native DocumentOps agent workflows."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.document_ops_agent import DocumentOpsAgent
from app.agents.schemas import DocumentOpsRequest, DocumentOpsResult
from app.services.document_ops_training_adapter import (
    training_adapter_contract_summary,
    training_execution_rehearsal_summary,
)
from app.storage.trajectory_store import TrajectoryStore


class DocumentOpsService:
    """Run DocumentOps tasks and optionally persist reviewed trajectory data."""

    def __init__(
        self,
        *,
        agent: DocumentOpsAgent,
        trajectory_store: TrajectoryStore,
    ) -> None:
        self._agent = agent
        self._trajectory_store = trajectory_store

    def run(
        self,
        payload: dict[str, Any],
        *,
        tenant_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        req = DocumentOpsRequest.model_validate(payload)
        result = self._agent.run(req, request_id=request_id)
        body = self._serialize_result(result)
        trajectory_id = ""
        trajectory_saved = False
        if req.capture_trajectory and result.trajectory:
            trajectory_id = self._trajectory_store.save(result.trajectory, tenant_id=tenant_id)
            trajectory_saved = True
        body["trajectory_id"] = trajectory_id or ((result.trajectory or {}).get("trajectory_id") or "")
        body["trajectory_saved"] = trajectory_saved
        return body

    def list_trajectories(
        self,
        *,
        tenant_id: str,
        task_type: str | None = None,
        human_review_status: str | None = None,
        accepted_only: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        records = self._trajectory_store.get_records(
            tenant_id=tenant_id,
            task_type=task_type,
            human_review_status=human_review_status,
            accepted_only=accepted_only,
            limit=limit,
        )
        return {"trajectories": records, "total": len(records)}

    def review_trajectory(
        self,
        trajectory_id: str,
        *,
        tenant_id: str,
        accepted: bool,
        reviewer: str = "",
        notes: str = "",
        quality_score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._trajectory_store.mark_reviewed(
            trajectory_id,
            tenant_id=tenant_id,
            accepted=accepted,
            reviewer=reviewer,
            notes=notes,
            quality_score=quality_score,
            metadata=metadata,
        )

    def stats(self, *, tenant_id: str) -> dict[str, Any]:
        return self._trajectory_store.get_stats(tenant_id=tenant_id)

    def export_sft_messages(
        self,
        *,
        tenant_id: str,
        task_type: str | None = None,
        min_records: int = 1,
        accepted_only: bool = True,
        include_metadata: bool = True,
    ) -> str | None:
        return self._trajectory_store.export_sft_messages(
            tenant_id=tenant_id,
            task_type=task_type,
            min_records=min_records,
            accepted_only=accepted_only,
            include_metadata=include_metadata,
        )

    def list_sft_exports(
        self,
        *,
        tenant_id: str,
        task_type: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        exports = self._trajectory_store.list_sft_exports(
            tenant_id=tenant_id,
            task_type=task_type,
            limit=limit,
        )
        return {"exports": exports, "total": len(exports)}

    def list_reviewed_sft_exports(
        self,
        *,
        tenant_id: str,
        task_type: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        exports = self._trajectory_store.list_reviewed_sft_exports(
            tenant_id=tenant_id,
            task_type=task_type,
            limit=limit,
        )
        return {"exports": exports, "total": len(exports), "reviewed_only": True}

    def list_dataset_freezes(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        freezes = self._trajectory_store.list_dataset_freezes(
            tenant_id=tenant_id,
            limit=limit,
        )
        return {"freezes": freezes, "total": len(freezes)}

    def list_training_approvals(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        approvals = self._trajectory_store.list_training_approvals(
            tenant_id=tenant_id,
            limit=limit,
        )
        return {"training_approvals": approvals, "total": len(approvals)}

    def training_readiness_summary(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._trajectory_store.training_readiness_summary(
            tenant_id=tenant_id,
            limit=limit,
        )

    def training_execution_plan_preview(
        self,
        *,
        tenant_id: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._trajectory_store.training_execution_plan_preview(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )

    def list_training_execution_requests(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        requests = self._trajectory_store.list_training_execution_requests(
            tenant_id=tenant_id,
            limit=limit,
        )
        return {"training_execution_requests": requests, "total": len(requests)}

    def request_training_execution_from_plan(
        self,
        *,
        tenant_id: str,
        requester: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        notes: str = "",
        limit: int = 50,
        start_training: bool = False,
        upload_dataset: bool = False,
        call_provider_api: bool = False,
    ) -> dict[str, Any]:
        return self._trajectory_store.request_training_execution_from_plan(
            tenant_id=tenant_id,
            requester=requester,
            provider=provider,
            base_model=base_model,
            notes=notes,
            limit=limit,
            start_training=start_training,
            upload_dataset=upload_dataset,
            call_provider_api=call_provider_api,
        )

    def training_pre_execution_audit_checklist(
        self,
        *,
        tenant_id: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._trajectory_store.training_pre_execution_audit_checklist(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )

    def list_training_pre_execution_audits(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        audits = self._trajectory_store.list_training_pre_execution_audits(
            tenant_id=tenant_id,
            limit=limit,
        )
        return {"training_pre_execution_audits": audits, "total": len(audits)}

    def export_training_pre_execution_audit(
        self,
        *,
        tenant_id: str,
        auditor: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        notes: str = "",
        limit: int = 50,
        start_training: bool = False,
        upload_dataset: bool = False,
        call_provider_api: bool = False,
    ) -> dict[str, Any]:
        return self._trajectory_store.export_training_pre_execution_audit(
            tenant_id=tenant_id,
            auditor=auditor,
            provider=provider,
            base_model=base_model,
            notes=notes,
            limit=limit,
            start_training=start_training,
            upload_dataset=upload_dataset,
            call_provider_api=call_provider_api,
        )

    def get_training_pre_execution_audit_path(self, filename: str, *, tenant_id: str) -> Path | None:
        return self._trajectory_store.get_training_pre_execution_audit_path(filename, tenant_id=tenant_id)

    def training_governance_dashboard_summary(
        self,
        *,
        tenant_id: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._trajectory_store.training_governance_dashboard_summary(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )

    def reviewer_signoff_summary(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._trajectory_store.reviewer_signoff_summary(
            tenant_id=tenant_id,
            limit=limit,
        )

    def reviewer_signoff_summary_export(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        summary = self.reviewer_signoff_summary(tenant_id=tenant_id, limit=limit)
        return {
            "report_type": "document_ops_phase27_reviewer_signoff_summary_export",
            "tenant_id": tenant_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "read_only": True,
            "export_format": "json",
            "summary": summary,
            "guard_flags": {
                "training_execution_allowed": False,
                "provider_api_calls_allowed": False,
                "external_upload_allowed": False,
                "provider_job_started": False,
                "model_promotion_allowed": False,
            },
            "side_effect_boundary": {
                "server_file_written": False,
                "actual_reviewer_approval_recorded_by_export": False,
                "training_execution_started": False,
                "external_dataset_uploaded": False,
                "provider_fine_tune_api_called": False,
                "provider_job_created": False,
                "model_promoted": False,
            },
        }

    def training_provider_adapter_contract(
        self,
        *,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
    ) -> dict[str, Any]:
        return training_adapter_contract_summary(
            provider=provider,
            base_model=base_model,
        )

    def training_provider_execution_rehearsal(
        self,
        *,
        tenant_id: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        governance_summary = self.training_governance_dashboard_summary(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )
        adapter_contract = self.training_provider_adapter_contract(
            provider=provider,
            base_model=base_model,
        )
        return training_execution_rehearsal_summary(
            governance_summary=governance_summary,
            adapter_contract=adapter_contract,
        )

    def get_sft_export_path(self, filename: str, *, tenant_id: str) -> Path | None:
        return self._trajectory_store.get_sft_export_path(filename, tenant_id=tenant_id)

    def get_reviewed_sft_export_path(self, filename: str, *, tenant_id: str) -> Path | None:
        return self._trajectory_store.get_reviewed_sft_export_path(filename, tenant_id=tenant_id)

    def freeze_sft_export(
        self,
        filename: str,
        *,
        tenant_id: str,
        reviewer: str,
        notes: str = "",
        sample_limit: int = 5,
        training_allowed: bool = False,
    ) -> dict[str, Any] | None:
        return self._trajectory_store.freeze_sft_export(
            filename,
            tenant_id=tenant_id,
            reviewer=reviewer,
            notes=notes,
            sample_limit=sample_limit,
            training_allowed=training_allowed,
        )

    def approve_training_from_freeze(
        self,
        manifest_id: str,
        *,
        tenant_id: str,
        approver: str,
        eval_plan: dict[str, Any],
        notes: str = "",
        dry_run: bool = True,
        start_training: bool = False,
    ) -> dict[str, Any] | None:
        return self._trajectory_store.approve_training_from_freeze(
            manifest_id,
            tenant_id=tenant_id,
            approver=approver,
            eval_plan=eval_plan,
            notes=notes,
            dry_run=dry_run,
            start_training=start_training,
        )

    def report_sft_export_quality(
        self,
        *,
        tenant_id: str,
        task_type: str | None = None,
        min_records: int = 1,
        accepted_only: bool = True,
        include_metadata: bool = True,
        sample_limit: int = 5,
    ) -> dict[str, Any]:
        return self._trajectory_store.report_sft_export_quality(
            tenant_id=tenant_id,
            task_type=task_type,
            min_records=min_records,
            accepted_only=accepted_only,
            include_metadata=include_metadata,
            sample_limit=sample_limit,
        )

    def inspect_sft_export_quality(
        self,
        filename: str,
        *,
        tenant_id: str,
        sample_limit: int = 5,
    ) -> dict[str, Any] | None:
        return self._trajectory_store.inspect_sft_export_quality(
            filename,
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )

    def preview_sft_export(
        self,
        *,
        tenant_id: str,
        task_type: str | None = None,
        min_records: int = 1,
        accepted_only: bool = True,
        include_metadata: bool = True,
        sample_limit: int = 5,
    ) -> dict[str, Any]:
        return self._trajectory_store.preview_sft_export(
            tenant_id=tenant_id,
            task_type=task_type,
            min_records=min_records,
            accepted_only=accepted_only,
            include_metadata=include_metadata,
            sample_limit=sample_limit,
        )

    @staticmethod
    def _serialize_result(result: DocumentOpsResult) -> dict[str, Any]:
        return result.model_dump()

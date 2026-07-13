"""Internal DocumentOps agent endpoints."""
from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from app.auth.api_key import require_api_key
from app.auth.ops_key import require_ops_key
from app.dependencies import get_tenant_id, get_username
from app.maintenance.mode import require_not_maintenance
from app.schemas import (
    DocumentOpsAgentRunRequest,
    DocumentOpsDatasetFreezeRequest,
    DocumentOpsTrainingAuditExportRequest,
    DocumentOpsTrajectoryExportPreviewRequest,
    DocumentOpsTrajectoryExportRequest,
    DocumentOpsTrajectoryReviewRequest,
    DocumentOpsTrainingApprovalRequest,
    DocumentOpsTrainingExecutionRequest,
)

router = APIRouter(prefix="/api/agent/document-ops", tags=["document-ops-agent"])


def _service(request: Request):
    return request.app.state.document_ops_service


def _safe_download_filename_part(value: str, *, fallback: str = "system") -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip(".-")
    return (safe or fallback)[:80]


@router.post("/run", dependencies=[Depends(require_not_maintenance), Depends(require_api_key)])
def run_document_ops_agent(payload: DocumentOpsAgentRunRequest, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        return _service(request).run(
            payload.model_dump(),
            tenant_id=tenant_id,
            request_id=request.state.request_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trajectories", dependencies=[Depends(require_api_key)])
def list_document_ops_trajectories(
    request: Request,
    task_type: str | None = None,
    human_review_status: str | None = None,
    accepted_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return _service(request).list_trajectories(
        tenant_id=get_tenant_id(request),
        task_type=task_type,
        human_review_status=human_review_status,
        accepted_only=accepted_only,
        limit=limit,
    )


@router.get("/trajectories/stats", dependencies=[Depends(require_api_key)])
def get_document_ops_trajectory_stats(request: Request) -> dict:
    return _service(request).stats(tenant_id=get_tenant_id(request))


@router.get("/trajectories/freezes", dependencies=[Depends(require_ops_key)])
def list_document_ops_dataset_freezes(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).list_dataset_freezes(
        tenant_id=get_tenant_id(request),
        limit=limit,
    )


@router.get("/trajectories/training-approvals", dependencies=[Depends(require_ops_key)])
def list_document_ops_training_approvals(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).list_training_approvals(
        tenant_id=get_tenant_id(request),
        limit=limit,
    )


@router.get("/trajectories/training-readiness", dependencies=[Depends(require_ops_key)])
def get_document_ops_training_readiness(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).training_readiness_summary(
        tenant_id=get_tenant_id(request),
        limit=limit,
    )


@router.get("/trajectories/training-plan/preview", dependencies=[Depends(require_ops_key)])
def preview_document_ops_training_plan(
    request: Request,
    provider: str = Query(default="provider_agnostic", min_length=1, max_length=80),
    base_model: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).training_execution_plan_preview(
        tenant_id=get_tenant_id(request),
        provider=provider,
        base_model=base_model,
        limit=limit,
    )


@router.get("/trajectories/training-execution-requests", dependencies=[Depends(require_ops_key)])
def list_document_ops_training_execution_requests(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).list_training_execution_requests(
        tenant_id=get_tenant_id(request),
        limit=limit,
    )


@router.post("/trajectories/training-execution-requests", dependencies=[Depends(require_ops_key)])
def request_document_ops_training_execution(
    payload: DocumentOpsTrainingExecutionRequest,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    try:
        return _service(request).request_training_execution_from_plan(
            tenant_id=get_tenant_id(request),
            requester=payload.requester,
            provider=payload.provider,
            base_model=payload.base_model,
            notes=payload.notes,
            limit=limit,
            start_training=payload.start_training,
            upload_dataset=payload.upload_dataset,
            call_provider_api=payload.call_provider_api,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trajectories/training-audit/checklist", dependencies=[Depends(require_ops_key)])
def get_document_ops_training_pre_execution_audit_checklist(
    request: Request,
    provider: str = Query(default="provider_agnostic", min_length=1, max_length=80),
    base_model: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).training_pre_execution_audit_checklist(
        tenant_id=get_tenant_id(request),
        provider=provider,
        base_model=base_model,
        limit=limit,
    )


@router.get("/trajectories/training-governance/summary", dependencies=[Depends(require_ops_key)])
def get_document_ops_training_governance_summary(
    request: Request,
    provider: str = Query(default="provider_agnostic", min_length=1, max_length=80),
    base_model: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).training_governance_dashboard_summary(
        tenant_id=get_tenant_id(request),
        provider=provider,
        base_model=base_model,
        limit=limit,
    )


@router.get("/trajectories/reviewer-signoff/summary", dependencies=[Depends(require_ops_key)])
def get_document_ops_reviewer_signoff_summary(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).reviewer_signoff_summary(
        tenant_id=get_tenant_id(request),
        limit=limit,
    )


@router.get("/trajectories/reviewer-signoff/summary/download", dependencies=[Depends(require_ops_key)])
def download_document_ops_reviewer_signoff_summary(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> Response:
    tenant_id = get_tenant_id(request)
    payload = _service(request).reviewer_signoff_summary_export(
        tenant_id=tenant_id,
        limit=limit,
    )
    filename = (
        "reviewer_signoff_summary_"
        f"{_safe_download_filename_part(tenant_id)}_"
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/trajectories/training-provider-adapter/contract", dependencies=[Depends(require_ops_key)])
def get_document_ops_training_provider_adapter_contract(
    request: Request,
    provider: str = Query(default="provider_agnostic", min_length=1, max_length=80),
    base_model: str | None = Query(default=None, max_length=120),
) -> dict:
    return _service(request).training_provider_adapter_contract(
        provider=provider,
        base_model=base_model,
    )


@router.get("/trajectories/training-provider-adapter/rehearsal", dependencies=[Depends(require_ops_key)])
def get_document_ops_training_provider_execution_rehearsal(
    request: Request,
    provider: str = Query(default="provider_agnostic", min_length=1, max_length=80),
    base_model: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).training_provider_execution_rehearsal(
        tenant_id=get_tenant_id(request),
        provider=provider,
        base_model=base_model,
        limit=limit,
    )


@router.get("/trajectories/training-audits", dependencies=[Depends(require_ops_key)])
def list_document_ops_training_pre_execution_audits(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).list_training_pre_execution_audits(
        tenant_id=get_tenant_id(request),
        limit=limit,
    )


@router.post("/trajectories/training-audit/export", dependencies=[Depends(require_ops_key)])
def export_document_ops_training_pre_execution_audit(
    payload: DocumentOpsTrainingAuditExportRequest,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    try:
        return _service(request).export_training_pre_execution_audit(
            tenant_id=get_tenant_id(request),
            auditor=payload.auditor,
            provider=payload.provider,
            base_model=payload.base_model,
            notes=payload.notes,
            limit=limit,
            start_training=payload.start_training,
            upload_dataset=payload.upload_dataset,
            call_provider_api=payload.call_provider_api,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trajectories/training-audits/{filename}/download", dependencies=[Depends(require_ops_key)])
def download_document_ops_training_pre_execution_audit(filename: str, request: Request) -> FileResponse:
    audit_path = _service(request).get_training_pre_execution_audit_path(
        filename,
        tenant_id=get_tenant_id(request),
    )
    if audit_path is None:
        raise HTTPException(status_code=404, detail="Training pre-execution audit file not found.")
    return FileResponse(
        path=audit_path,
        media_type="application/json",
        filename=filename,
    )


@router.post("/trajectories/freezes/{manifest_id}/training-approval", dependencies=[Depends(require_ops_key)])
def approve_document_ops_training_from_freeze(
    manifest_id: str,
    payload: DocumentOpsTrainingApprovalRequest,
    request: Request,
) -> dict:
    try:
        approval = _service(request).approve_training_from_freeze(
            manifest_id,
            tenant_id=get_tenant_id(request),
            approver=payload.approver,
            eval_plan=payload.eval_plan,
            notes=payload.notes,
            dry_run=payload.dry_run,
            start_training=payload.start_training,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Dataset freeze manifest not found.")
    return approval


@router.get("/trajectories/exports", dependencies=[Depends(require_ops_key)])
def list_document_ops_trajectory_exports(
    request: Request,
    task_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).list_sft_exports(
        tenant_id=get_tenant_id(request),
        task_type=task_type,
        limit=limit,
    )


@router.get("/trajectories/reviewed-sft-exports", dependencies=[Depends(require_ops_key)])
def list_document_ops_reviewed_sft_exports(
    request: Request,
    task_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return _service(request).list_reviewed_sft_exports(
        tenant_id=get_tenant_id(request),
        task_type=task_type,
        limit=limit,
    )


@router.get("/trajectories/exports/{filename}", dependencies=[Depends(require_ops_key)])
def download_document_ops_trajectory_export(filename: str, request: Request) -> FileResponse:
    try:
        export_path = _service(request).get_sft_export_path(
            filename,
            tenant_id=get_tenant_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if export_path is None:
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(
        path=export_path,
        media_type="application/x-ndjson",
        filename=filename,
    )


@router.get("/trajectories/reviewed-sft-exports/{filename}/download", dependencies=[Depends(require_ops_key)])
def download_document_ops_reviewed_sft_export(filename: str, request: Request) -> FileResponse:
    try:
        export_path = _service(request).get_reviewed_sft_export_path(
            filename,
            tenant_id=get_tenant_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if export_path is None:
        raise HTTPException(status_code=404, detail="Reviewed SFT export file not found.")
    return FileResponse(
        path=export_path,
        media_type="application/x-ndjson",
        filename=filename,
    )


@router.get("/trajectories/exports/{filename}/quality-report", dependencies=[Depends(require_ops_key)])
def inspect_document_ops_trajectory_export_quality(
    filename: str,
    request: Request,
    sample_limit: int = Query(default=5, ge=0, le=25),
) -> dict:
    try:
        report = _service(request).inspect_sft_export_quality(
            filename,
            tenant_id=get_tenant_id(request),
            sample_limit=sample_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=404, detail="Export file not found.")
    return report


@router.post("/trajectories/exports/{filename}/freeze", dependencies=[Depends(require_ops_key)])
def freeze_document_ops_trajectory_export(
    filename: str,
    payload: DocumentOpsDatasetFreezeRequest,
    request: Request,
) -> dict:
    try:
        manifest = _service(request).freeze_sft_export(
            filename,
            tenant_id=get_tenant_id(request),
            reviewer=payload.reviewer,
            notes=payload.notes,
            sample_limit=payload.sample_limit,
            training_allowed=payload.training_allowed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if manifest is None:
        raise HTTPException(status_code=404, detail="Export file not found.")
    return manifest


@router.post("/trajectories/export/preview", dependencies=[Depends(require_ops_key)])
def preview_document_ops_trajectory_export(
    payload: DocumentOpsTrajectoryExportPreviewRequest,
    request: Request,
) -> dict:
    return _service(request).preview_sft_export(
        tenant_id=get_tenant_id(request),
        task_type=payload.task_type,
        min_records=payload.min_records,
        accepted_only=payload.accepted_only,
        include_metadata=payload.include_metadata,
        sample_limit=payload.sample_limit,
    )


@router.post("/trajectories/export/quality-report", dependencies=[Depends(require_ops_key)])
def report_document_ops_trajectory_export_quality(
    payload: DocumentOpsTrajectoryExportPreviewRequest,
    request: Request,
) -> dict:
    return _service(request).report_sft_export_quality(
        tenant_id=get_tenant_id(request),
        task_type=payload.task_type,
        min_records=payload.min_records,
        accepted_only=payload.accepted_only,
        include_metadata=payload.include_metadata,
        sample_limit=payload.sample_limit,
    )


@router.post("/trajectories/export", dependencies=[Depends(require_ops_key)])
def export_document_ops_trajectories(
    payload: DocumentOpsTrajectoryExportRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    export_path = _service(request).export_sft_messages(
        tenant_id=tenant_id,
        task_type=payload.task_type,
        min_records=payload.min_records,
        accepted_only=payload.accepted_only,
        include_metadata=payload.include_metadata,
    )
    filename = os.path.basename(export_path) if export_path else None
    return {
        "exported": export_path is not None,
        "filename": filename,
        "tenant_id": tenant_id,
        "task_type": payload.task_type,
    }


@router.post("/trajectories/{trajectory_id}/review", dependencies=[Depends(require_api_key)])
def review_document_ops_trajectory(
    trajectory_id: str,
    payload: DocumentOpsTrajectoryReviewRequest,
    request: Request,
) -> dict:
    reviewer = payload.reviewer.strip() or get_username(request)
    try:
        updated = _service(request).review_trajectory(
            trajectory_id,
            tenant_id=get_tenant_id(request),
            accepted=payload.accepted,
            reviewer=reviewer,
            notes=payload.notes,
            quality_score=payload.quality_score,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="trajectory not found")
    return updated

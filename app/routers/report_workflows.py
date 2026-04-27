"""Report workflow endpoints for staged report production."""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id, get_username
from app.maintenance.mode import require_not_maintenance
from app.schemas import (
    CreateReportWorkflowRequest,
    GenerateReportWorkflowVisualAssetsRequest,
    GenerateReportSlidesRequest,
    PromoteReportWorkflowRequest,
    ReportWorkflowActionRequest,
    SelectReportSlideVisualAssetRequest,
    UpdateReportSlideVisualAssetsRequest,
)

router = APIRouter(tags=["report-workflows"])


def _actor(request: Request, payload_username: str = "") -> str:
    return payload_username.strip() or get_username(request) or "anonymous"


def _get_store(request: Request):
    return request.app.state.report_workflow_store


def _get_service(request: Request):
    return request.app.state.report_workflow_service


def _handle_store_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _redact_visual_asset_payload(value):
    if isinstance(value, list):
        return [_redact_visual_asset_payload(item) for item in value]
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key == "content_base64":
                redacted["has_content_base64"] = bool(item)
                redacted["content_base64_len"] = len(str(item or ""))
                continue
            redacted[key] = _redact_visual_asset_payload(item)
        return redacted
    return value


def _workflow_list_item(rec) -> dict:
    raw = asdict(rec)
    visual_assets = raw.get("visual_assets") if isinstance(raw.get("visual_assets"), list) else []
    item = _redact_visual_asset_payload(raw)
    item["visual_asset_count"] = len(visual_assets)
    return item


@router.post(
    "/report-workflows",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def create_report_workflow(payload: CreateReportWorkflowRequest, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    store = _get_store(request)
    rec = store.create(
        tenant_id=tenant_id,
        title=payload.title,
        goal=payload.goal,
        client=payload.client,
        report_type=payload.report_type,
        audience=payload.audience,
        owner=payload.owner or get_username(request),
        source_bundle_id=payload.source_bundle_id,
        source_request_id=payload.source_request_id,
        slide_count=payload.slide_count,
        attachments_context=payload.attachments_context,
        source_refs=payload.source_refs,
        learning_opt_in=payload.learning_opt_in,
    )
    return asdict(rec)


@router.get("/report-workflows", dependencies=[Depends(require_api_key)])
def list_report_workflows(request: Request, status: str | None = None) -> dict:
    tenant_id = get_tenant_id(request)
    records = _get_store(request).list_by_tenant(tenant_id, status=status)
    return {"report_workflows": [_workflow_list_item(rec) for rec in records], "total": len(records)}


@router.get("/report-workflows/{report_workflow_id}", dependencies=[Depends(require_api_key)])
def get_report_workflow(report_workflow_id: str, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    rec = _get_store(request).get(report_workflow_id, tenant_id=tenant_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="보고서 워크플로우를 찾을 수 없습니다.")
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/planning/generate",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_report_planning(report_workflow_id: str, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).generate_planning(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/planning/request-changes",
    dependencies=[Depends(require_api_key)],
)
def request_report_planning_changes(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_store(request).request_planning_changes(
            report_workflow_id,
            author=_actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/planning/approve",
    dependencies=[Depends(require_api_key)],
)
def approve_report_planning(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_store(request).approve_planning(
            report_workflow_id,
            author=_actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/slides/generate",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_report_slides(
    report_workflow_id: str,
    request: Request,
    payload: GenerateReportSlidesRequest = GenerateReportSlidesRequest(),
) -> dict:
    del payload
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).generate_slides(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/slides/{slide_id}/request-changes",
    dependencies=[Depends(require_api_key)],
)
def request_report_slide_changes(
    report_workflow_id: str,
    slide_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_store(request).request_slide_changes(
            report_workflow_id,
            slide_id,
            author=_actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/slides/{slide_id}/approve",
    dependencies=[Depends(require_api_key)],
)
def approve_report_slide(
    report_workflow_id: str,
    slide_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_store(request).approve_slide(
            report_workflow_id,
            slide_id,
            author=_actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.put(
    "/report-workflows/{report_workflow_id}/slides/{slide_id}/visual-assets",
    dependencies=[Depends(require_api_key)],
)
def update_report_slide_visual_assets(
    report_workflow_id: str,
    slide_id: str,
    payload: UpdateReportSlideVisualAssetsRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_store(request).update_slide_visual_assets(
            report_workflow_id,
            slide_id,
            visual_prompt=payload.visual_prompt,
            reference_refs=payload.reference_refs,
            generated_asset_ids=payload.generated_asset_ids,
            selected_asset_id=payload.selected_asset_id,
            selected_asset=payload.selected_asset,
            author=_actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/slides/{slide_id}/visual-assets/select",
    dependencies=[Depends(require_api_key)],
)
def select_report_slide_visual_asset(
    report_workflow_id: str,
    slide_id: str,
    payload: SelectReportSlideVisualAssetRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_store(request).select_slide_visual_asset(
            report_workflow_id,
            slide_id,
            asset_id=payload.asset_id,
            author=_actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/visual-assets/generate",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_report_workflow_visual_assets(
    report_workflow_id: str,
    payload: GenerateReportWorkflowVisualAssetsRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        result = _get_service(request).generate_visual_assets(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
            author=_actor(request, payload.username),
            max_assets=payload.max_assets,
            select_first=payload.select_first,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    rec = result["report_workflow"]
    assets = result["assets"]
    return {
        "report_workflow": asdict(rec),
        "count": len(assets),
        "assets": assets,
    }


@router.post(
    "/report-workflows/{report_workflow_id}/final/submit",
    dependencies=[Depends(require_api_key)],
)
def submit_report_final(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).submit_final(
            report_workflow_id,
            author=_actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/final/approve",
    dependencies=[Depends(require_api_key)],
)
def approve_report_final(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).approve_final(
            report_workflow_id,
            author=_actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/final/pm-approve",
    dependencies=[Depends(require_api_key)],
)
def approve_report_final_pm(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).approve_final_step(
            report_workflow_id,
            stage="pm_review",
            author=_actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/final/executive-approve",
    dependencies=[Depends(require_api_key)],
)
def approve_report_final_executive(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).approve_final_step(
            report_workflow_id,
            stage="executive_review",
            author=_actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.post(
    "/report-workflows/{report_workflow_id}/final/request-changes",
    dependencies=[Depends(require_api_key)],
)
def request_report_final_changes(
    report_workflow_id: str,
    payload: ReportWorkflowActionRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).request_final_changes(
            report_workflow_id,
            author=_actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)


@router.get(
    "/report-workflows/{report_workflow_id}/export/pptx",
    dependencies=[Depends(require_api_key)],
)
def export_report_workflow_pptx(report_workflow_id: str, request: Request) -> Response:
    tenant_id = get_tenant_id(request)
    rec = _get_store(request).get(report_workflow_id, tenant_id=tenant_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="보고서 워크플로우를 찾을 수 없습니다.")
    try:
        pptx_bytes = _get_service(request).build_pptx_export(report_workflow_id, tenant_id=tenant_id)
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", rec.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"report_workflow.pptx\"; "
                f"filename*=UTF-8''{encoded_title}.pptx"
            )
        },
    )


@router.post(
    "/report-workflows/{report_workflow_id}/promote",
    dependencies=[Depends(require_api_key)],
)
def promote_report_workflow(
    report_workflow_id: str,
    payload: PromoteReportWorkflowRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        rec = _get_service(request).promote_final_artifacts(
            report_workflow_id,
            tenant_id=tenant_id,
            project_id=payload.project_id,
            promote_to_knowledge=payload.promote_to_knowledge,
            tags=payload.tags,
            quality_tier=payload.quality_tier,
            success_state=payload.success_state,
            source_organization=payload.source_organization,
            reference_year=payload.reference_year,
            notes=payload.notes,
        )
    except (KeyError, ValueError) as exc:
        _handle_store_error(exc)
    return asdict(rec)

"""Core lifecycle routes for staged report production."""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id, get_username
from app.maintenance.mode import require_not_maintenance
from app.routers._report_workflow_shared import (
    actor,
    get_document_ops_service,
    get_service,
    get_store,
    handle_store_error,
    workflow_list_item,
)
from app.schemas import (
    CreateReportWorkflowRequest,
    GenerateReportSlidesRequest,
    GenerateReportWorkflowVisualAssetsRequest,
    PromoteReportWorkflowRequest,
    ReportWorkflowActionRequest,
    ReportWorkflowDevelopQualityPreviewRequest,
    SelectReportSlideVisualAssetRequest,
    UpdateReportSlideVisualAssetsRequest,
)
from app.services.generation.context_store import (
    record_direct_provider_usage,
)

collection_router = APIRouter()
workflow_router = APIRouter()
promotion_router = APIRouter()


@collection_router.post(
    "/report-workflows",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def create_report_workflow(payload: CreateReportWorkflowRequest, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    record = get_store(request).create(
        tenant_id=tenant_id,
        title=payload.title,
        goal=payload.goal,
        client=payload.client,
        report_type=payload.report_type,
        audience=payload.audience,
        owner=payload.owner or get_username(request),
        pm_reviewer=payload.pm_reviewer,
        executive_approver=payload.executive_approver,
        source_bundle_id=payload.source_bundle_id,
        source_request_id=payload.source_request_id,
        slide_count=payload.slide_count,
        attachments_context=payload.attachments_context,
        source_refs=payload.source_refs,
        learning_opt_in=payload.learning_opt_in,
    )
    return asdict(record)


@collection_router.get("/report-workflows", dependencies=[Depends(require_api_key)])
def list_report_workflows(request: Request, status: str | None = None) -> dict:
    tenant_id = get_tenant_id(request)
    records = get_store(request).list_by_tenant(tenant_id, status=status)
    return {
        "report_workflows": [workflow_list_item(record) for record in records],
        "total": len(records),
    }


@workflow_router.get(
    "/report-workflows/{report_workflow_id}",
    dependencies=[Depends(require_api_key)],
)
def get_report_workflow(report_workflow_id: str, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    record = get_store(request).get(report_workflow_id, tenant_id=tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="보고서 워크플로우를 찾을 수 없습니다.")
    return asdict(record)


@workflow_router.post(
    "/report-workflows/{report_workflow_id}/develop-quality/preview",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def preview_report_workflow_develop_quality(
    report_workflow_id: str,
    payload: ReportWorkflowDevelopQualityPreviewRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        result = get_service(request).preview_develop_quality_improvement(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
            document_ops_service=get_document_ops_service(request),
            focus=payload.focus,
            additional_notes=payload.additional_notes,
            capture_trajectory=payload.capture_trajectory,
            record_provider_usage=lambda provider: record_direct_provider_usage(
                request,
                provider,
                bundle_id="report-workflow.develop-quality-preview",
            ),
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return result


@workflow_router.post(
    "/report-workflows/{report_workflow_id}/planning/generate",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_report_planning(report_workflow_id: str, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        record = get_service(request).generate_planning(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
            record_provider_usage=lambda provider: record_direct_provider_usage(
                request,
                provider,
                bundle_id="report-workflow.planning",
            ),
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_store(request).request_planning_changes(
            report_workflow_id,
            author=actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_store(request).approve_planning(
            report_workflow_id,
            author=actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_service(request).generate_slides(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
            record_provider_usage=lambda provider: record_direct_provider_usage(
                request,
                provider,
                bundle_id="report-workflow.slides",
            ),
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_store(request).request_slide_changes(
            report_workflow_id,
            slide_id,
            author=actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_store(request).approve_slide(
            report_workflow_id,
            slide_id,
            author=actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.put(
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
        record = get_store(request).update_slide_visual_assets(
            report_workflow_id,
            slide_id,
            visual_prompt=payload.visual_prompt,
            reference_refs=payload.reference_refs,
            generated_asset_ids=payload.generated_asset_ids,
            selected_asset_id=payload.selected_asset_id,
            selected_asset=payload.selected_asset,
            author=actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_store(request).select_slide_visual_asset(
            report_workflow_id,
            slide_id,
            asset_id=payload.asset_id,
            author=actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        result = get_service(request).generate_visual_assets(
            report_workflow_id,
            tenant_id=tenant_id,
            request_id=request.state.request_id,
            author=actor(request, payload.username),
            max_assets=payload.max_assets,
            select_first=payload.select_first,
            record_provider_usage=lambda provider, usage: record_direct_provider_usage(
                request,
                provider,
                bundle_id="report-workflow.visual-assets",
                extra_tokens=usage,
            ),
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    record = result["report_workflow"]
    assets = result["assets"]
    return {
        "report_workflow": asdict(record),
        "count": len(assets),
        "assets": assets,
    }


@workflow_router.post(
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
        record = get_service(request).submit_final(
            report_workflow_id,
            author=actor(request, payload.username),
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_service(request).approve_final(
            report_workflow_id,
            author=actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_service(request).approve_final_step(
            report_workflow_id,
            stage="pm_review",
            author=actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_service(request).approve_final_step(
            report_workflow_id,
            stage="executive_review",
            author=actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.post(
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
        record = get_service(request).request_final_changes(
            report_workflow_id,
            author=actor(request, payload.username),
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return asdict(record)


@workflow_router.get(
    "/report-workflows/{report_workflow_id}/export/pptx",
    dependencies=[Depends(require_api_key)],
)
def export_report_workflow_pptx(report_workflow_id: str, request: Request) -> Response:
    tenant_id = get_tenant_id(request)
    record = get_store(request).get(report_workflow_id, tenant_id=tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="보고서 워크플로우를 찾을 수 없습니다.")
    try:
        pptx_bytes = get_service(request).build_pptx_export(
            report_workflow_id,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", record.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": (
                'attachment; filename="report_workflow.pptx"; '
                f"filename*=UTF-8''{encoded_title}.pptx"
            )
        },
    )


@workflow_router.get(
    "/report-workflows/{report_workflow_id}/export/snapshot",
    dependencies=[Depends(require_api_key)],
)
def export_report_workflow_snapshot(report_workflow_id: str, request: Request) -> Response:
    tenant_id = get_tenant_id(request)
    record = get_store(request).get(report_workflow_id, tenant_id=tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="보고서 워크플로우를 찾을 수 없습니다.")
    try:
        snapshot = get_service(request).build_export_snapshot(
            report_workflow_id,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", record.title)[:100] or "report_workflow"
    encoded_title = urllib.parse.quote(f"{safe_title}-snapshot", safe="")
    return Response(
        content=json.dumps(snapshot, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="report_workflow_snapshot.json"; '
                f"filename*=UTF-8''{encoded_title}.json"
            )
        },
    )


@promotion_router.post(
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
        record = get_service(request).promote_final_artifacts(
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
        handle_store_error(exc)
    return asdict(record)

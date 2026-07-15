"""Quality correction and pilot export routes for report workflows."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id
from app.routers._report_workflow_shared import (
    actor,
    get_service,
    handle_store_error,
    record_quality_pilot_state,
)
from app.schemas import (
    ReportQualityCorrectionArtifactRequest,
    ReportQualityPilotExportRequest,
    ReportQualityPilotPreviewRequest,
)
from app.services.report_quality_pilot_package import prepare_pilot_review_package_delivery
from app.services.report_quality_pilot_receipt import (
    RECEIPT_HEADER,
    RECEIPT_SHA256_HEADER,
    build_pilot_export_receipt,
    encode_pilot_export_receipt,
    pilot_export_receipt_sha256,
    serialize_pilot_export_receipt,
)

collection_router = APIRouter()
workflow_router = APIRouter()


@collection_router.get(
    "/report-workflows/learning/correction-artifacts",
    dependencies=[Depends(require_api_key)],
)
def list_report_quality_correction_artifacts(
    request: Request,
    ready_only: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = 50,
) -> dict:
    tenant_id = get_tenant_id(request)
    return get_service(request).list_quality_correction_artifacts(
        tenant_id=tenant_id,
        ready_only=ready_only,
        offset=offset,
        limit=limit,
    )


@collection_router.get(
    "/report-workflows/learning/correction-artifacts/export",
    dependencies=[Depends(require_api_key)],
)
def export_report_quality_correction_artifacts(
    request: Request,
    ready_only: bool = True,
    limit: int = 200,
) -> Response:
    tenant_id = get_tenant_id(request)
    body = get_service(request).export_quality_correction_artifacts_jsonl(
        tenant_id=tenant_id,
        ready_only=ready_only,
        limit=limit,
    )
    filename = "report_quality_correction_artifacts.jsonl"
    return Response(
        content=body,
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{filename}"
            )
        },
    )


@collection_router.post(
    "/report-workflows/learning/correction-artifacts/pilot-export/preview",
    dependencies=[Depends(require_api_key)],
)
def preview_report_quality_correction_pilot(
    payload: ReportQualityPilotPreviewRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        preview = get_service(request).preview_quality_correction_pilot_export(
            payload.artifact_ids,
            tenant_id=tenant_id,
        )
        record_quality_pilot_state(request, preview, preview_verified=False)
        return preview
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    raise HTTPException(status_code=500, detail="correction artifact pilot preview failed")


@collection_router.post(
    "/report-workflows/learning/correction-artifacts/pilot-export",
    dependencies=[Depends(require_api_key)],
)
def export_report_quality_correction_pilot(
    payload: ReportQualityPilotExportRequest,
    request: Request,
) -> Response:
    tenant_id = get_tenant_id(request)
    try:
        prepared = get_service(request).confirm_quality_correction_pilot_export(
            payload.artifact_ids,
            tenant_id=tenant_id,
            preview_sha256=payload.preview_sha256,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    body = prepared["jsonl"]
    preview = prepared["preview"]
    body_sha256 = preview["export_sha256"]
    filename = preview["filename"]
    receipt = build_pilot_export_receipt(
        preview=preview,
        tenant_id=tenant_id,
        request_id=request.state.request_id,
    )
    receipt_bytes = serialize_pilot_export_receipt(receipt)
    record_quality_pilot_state(request, preview, preview_verified=True)
    return Response(
        content=body,
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{filename}"
            ),
            "X-DecisionDoc-Pilot-Artifact-Count": str(len(payload.artifact_ids)),
            "X-DecisionDoc-Pilot-SHA256": body_sha256,
            "X-DecisionDoc-Pilot-Preview-Verified": "true",
            "X-DecisionDoc-Training-Authorized": "false",
            RECEIPT_HEADER: encode_pilot_export_receipt(receipt_bytes),
            RECEIPT_SHA256_HEADER: pilot_export_receipt_sha256(receipt_bytes),
        },
    )


@collection_router.post(
    "/report-workflows/learning/correction-artifacts/pilot-export/package",
    dependencies=[Depends(require_api_key)],
)
def package_report_quality_correction_pilot(
    payload: ReportQualityPilotExportRequest,
    request: Request,
) -> Response:
    tenant_id = get_tenant_id(request)
    try:
        prepared = get_service(request).confirm_quality_correction_pilot_export(
            payload.artifact_ids,
            tenant_id=tenant_id,
            preview_sha256=payload.preview_sha256,
        )
        delivery = prepare_pilot_review_package_delivery(
            jsonl=prepared["jsonl"],
            preview=prepared["preview"],
            tenant_id=tenant_id,
            request_id=request.state.request_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)

    record_quality_pilot_state(
        request,
        prepared["preview"],
        preview_verified=True,
        action="pilot_package",
    )
    return Response(
        content=delivery["content"],
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{delivery["filename"]}"; '
                f"filename*=UTF-8''{delivery['filename']}"
            ),
            **delivery["headers"],
        },
    )


@collection_router.get(
    "/report-workflows/learning/correction-artifacts/{artifact_id}",
    dependencies=[Depends(require_api_key)],
)
def get_report_quality_correction_artifact(artifact_id: str, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        return get_service(request).get_quality_correction_artifact(
            artifact_id,
            tenant_id=tenant_id,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    raise HTTPException(status_code=500, detail="correction artifact lookup failed")


@workflow_router.post(
    "/report-workflows/{report_workflow_id}/learning/correction-artifact/preview",
    dependencies=[Depends(require_api_key)],
)
def preview_report_quality_correction_artifact(
    report_workflow_id: str,
    payload: ReportQualityCorrectionArtifactRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    correction = payload.model_dump()
    correction["username"] = actor(request, payload.username)
    if not correction.get("reviewer"):
        correction["reviewer"] = correction["username"]
    try:
        return get_service(request).preview_quality_correction_artifact(
            report_workflow_id,
            tenant_id=tenant_id,
            correction=correction,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    raise HTTPException(status_code=500, detail="correction artifact preview failed")


@workflow_router.post(
    "/report-workflows/{report_workflow_id}/learning/correction-artifact",
    dependencies=[Depends(require_api_key)],
)
def save_report_quality_correction_artifact(
    report_workflow_id: str,
    payload: ReportQualityCorrectionArtifactRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    correction_actor = actor(request, payload.username)
    correction = payload.model_dump()
    correction["username"] = correction_actor
    if not correction.get("reviewer"):
        correction["reviewer"] = correction_actor
    try:
        result = get_service(request).save_quality_correction_artifact(
            report_workflow_id,
            tenant_id=tenant_id,
            correction=correction,
            actor=correction_actor,
        )
    except (KeyError, ValueError) as exc:
        handle_store_error(exc)
    return {
        "report_workflow": asdict(result["report_workflow"]),
        "artifact": result["artifact"],
        "validation": result["validation"],
        "preview_fingerprint": result["preview_fingerprint"],
        "persisted": result["persisted"],
    }

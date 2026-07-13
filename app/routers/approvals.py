"""app/routers/approvals.py — Approval workflow endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

import json as _json
import re
import urllib.parse
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id
from app.routers.projects._provenance import (
    lookup_project_document as _lookup_approval_project_document,
    project_document_freshness_values as _freshness_values,
    project_document_source_fingerprint as _approval_source_fingerprint,
)
from app.schemas import (
    ApprovalActionRequest,
    CreateApprovalRequest,
    GovDocOptions,
    UpdateApprovalDocsRequest,
)
from app.services.docx_service import build_docx
from app.services.excel_service import build_excel
from app.services.hwp_service import build_hwp

router = APIRouter(tags=["approvals"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _emit_approval_event(request: Request, approval_id: str, status: str) -> None:
    try:
        from app.services.event_bus import get_event_bus
        tenant_id = getattr(request.state, "tenant_id", "system") or "system"
        get_event_bus().publish(tenant_id, "approval_updated", {
            "approval_id": approval_id,
            "status": status,
        })
    except Exception:
        pass

def _resolve_gov_options(gov_options_dict: dict | None) -> GovDocOptions | None:
    """Convert a raw dict (from JSON payload) into a ``GovDocOptions`` instance.

    Returns ``None`` when ``gov_options_dict`` is ``None`` or empty so that
    downstream build functions can use their own defaults.
    """
    if not gov_options_dict:
        return None
    try:
        return GovDocOptions(**gov_options_dict)
    except (TypeError, ValueError):
        return None


def _load_pdf_builder():
    try:
        from app.services.pdf_service import build_pdf as _build_pdf
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export is not available in this deployment.",
        ) from exc
    return _build_pdf


def _sync_project_document_approval_state(
    request: Request,
    *,
    tenant_id: str,
    request_id: str,
    approval_id: str,
    approval_status: str,
) -> None:
    project_store = request.app.state.project_store
    try:
        for proj in project_store.list_by_tenant(tenant_id):
            project_store.update_document_approval(
                proj.project_id,
                request_id=request_id,
                approval_id=approval_id,
                approval_status=approval_status,
                tenant_id=tenant_id,
            )
    except Exception:
        pass


def _require_approval_project_document(
    request: Request,
    *,
    tenant_id: str,
    project_id: str,
    project_document_id: str,
    request_id: str,
    bundle_id: str,
) -> dict | None:
    binding_status, document = _lookup_approval_project_document(
        request,
        tenant_id=tenant_id,
        project_id=project_id,
        project_document_id=project_document_id,
        request_id=request_id,
        bundle_id=bundle_id,
    )
    if binding_status == "not_linked":
        return None
    if binding_status == "missing":
        raise HTTPException(
            status_code=404,
            detail={
                "code": "approval_project_document_not_found",
                "message": "현재 tenant에서 결재 대상 프로젝트 문서를 찾을 수 없습니다.",
            },
        )
    if binding_status == "mismatch":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approval_project_document_mismatch",
                "message": "결재 요청의 project, document, request, bundle 식별자가 일치하지 않습니다.",
            },
        )
    return document


def _resolve_approval_project_binding(
    request: Request,
    *,
    tenant_id: str,
    project_id: str,
    project_document_id: str,
    request_id: str,
) -> tuple[str, str]:
    if project_id or project_document_id or not request_id:
        return project_id, project_document_id

    matches = [
        (project.project_id, document.doc_id)
        for project in request.app.state.project_store.list_by_tenant(tenant_id)
        for document in project.documents
        if document.request_id == request_id
    ]
    if not matches:
        return "", ""
    if len(matches) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approval_project_document_binding_required",
                "message": "같은 request ID를 사용하는 프로젝트 문서가 여러 개입니다. project와 document 식별자를 지정해야 합니다.",
            },
        )
    return matches[0]


def _approval_binding_copy(status: str) -> tuple[str, str, str]:
    if status == "current":
        return "success", "프로젝트 문서 연결 확인", "현재 tenant의 원본 프로젝트 문서와 결재 기록이 일치합니다."
    if status == "missing":
        return "danger", "원본 프로젝트 문서 없음", "결재 기록이 참조한 프로젝트 문서를 현재 tenant에서 찾을 수 없습니다."
    if status == "mismatch":
        return "danger", "원본 프로젝트 문서 불일치", "결재 기록의 project, document, request, bundle 식별자가 현재 원본과 일치하지 않습니다."
    return "muted", "프로젝트 문서 연결 없음", "일반 결재 또는 legacy 기록으로 프로젝트 문서 freshness를 재검증하지 않습니다."


def _serialize_approval_record(record, request: Request, *, tenant_id: str) -> dict:
    payload = asdict(record)
    binding_status, document = _lookup_approval_project_document(
        request,
        tenant_id=tenant_id,
        project_id=record.project_id,
        project_document_id=record.project_document_id,
        request_id=record.request_id,
        bundle_id=record.bundle_id,
    )
    binding_tone, binding_copy, binding_summary = _approval_binding_copy(binding_status)
    payload["project_document_binding_status"] = binding_status
    payload["project_document_binding_status_tone"] = binding_tone
    payload["project_document_binding_status_copy"] = binding_copy
    payload["project_document_binding_status_summary"] = binding_summary

    current_values = _freshness_values(document)
    for field, current_value in current_values.items():
        source_value = str(payload.get(f"source_{field}") or "").strip()
        payload[field] = current_value or source_value

    freshness_warning_present = (
        binding_status in {"missing", "mismatch"}
        or any(
            payload.get(field) and payload.get(field) != "current"
            for field in (
                "decision_council_document_status",
                "procurement_review_document_status",
            )
        )
    )
    payload["freshness_warning_present"] = freshness_warning_present
    payload["freshness_acknowledgement_required"] = (
        freshness_warning_present
        and record.status != "approved"
        and not record.freshness_acknowledged
    )
    current_source_fingerprint = _approval_source_fingerprint(
        request,
        tenant_id=tenant_id,
        project_id=record.project_id,
        binding_status=binding_status,
        document=document,
    )
    payload["current_source_fingerprint"] = current_source_fingerprint
    payload["post_approval_source_changed"] = bool(
        record.status == "approved"
        and record.approved_source_fingerprint
        and current_source_fingerprint != record.approved_source_fingerprint
    )
    payload["source_change_acknowledgement_required"] = payload[
        "post_approval_source_changed"
    ]
    return payload


def _record_approval_freshness_audit(request: Request, payload: dict, *, acknowledged: bool) -> None:
    request.state.approval_project_id = payload.get("project_id") or ""
    request.state.approval_project_document_id = payload.get("project_document_id") or ""
    request.state.approval_document_binding_status = (
        payload.get("project_document_binding_status") or ""
    )
    request.state.approval_decision_council_document_status = (
        payload.get("decision_council_document_status") or ""
    )
    request.state.approval_procurement_review_document_status = (
        payload.get("procurement_review_document_status") or ""
    )
    request.state.approval_freshness_acknowledged = acknowledged


def _record_approval_download_freshness_audit(
    request: Request,
    payload: dict,
    *,
    acknowledged: bool,
) -> None:
    _record_approval_freshness_audit(request, payload, acknowledged=False)
    request.state.approval_post_approval_source_changed = bool(
        payload.get("post_approval_source_changed")
    )
    request.state.approval_source_change_acknowledged = acknowledged


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/approvals", dependencies=[Depends(require_api_key)])
def create_approval_endpoint(payload: CreateApprovalRequest, request: Request) -> dict:
    """Create a new approval workflow record (기안 단계)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    project_id, project_document_id = _resolve_approval_project_binding(
        request,
        tenant_id=tenant_id,
        project_id=payload.project_id,
        project_document_id=payload.project_document_id,
        request_id=payload.request_id,
    )
    project_document = _require_approval_project_document(
        request,
        tenant_id=tenant_id,
        project_id=project_id,
        project_document_id=project_document_id,
        request_id=payload.request_id,
        bundle_id=payload.bundle_id,
    )
    freshness = _freshness_values(project_document)
    rec = approval_store.create(
        tenant_id=tenant_id,
        request_id=payload.request_id,
        bundle_id=payload.bundle_id,
        title=payload.title,
        drafter=payload.drafter,
        docs=payload.docs,
        gov_options=payload.gov_options,
        project_id=project_id,
        project_document_id=project_document_id,
        **freshness,
    )
    _sync_project_document_approval_state(
        request,
        tenant_id=tenant_id,
        request_id=rec.request_id,
        approval_id=rec.approval_id,
        approval_status=rec.status,
    )
    response = _serialize_approval_record(rec, request, tenant_id=tenant_id)
    _record_approval_freshness_audit(request, response, acknowledged=False)
    return response


@router.get("/approvals", dependencies=[Depends(require_api_key)])
def list_approvals_endpoint(
    request: Request,
    status: str | None = None,
    role: str | None = None,
    username: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List approvals for the current tenant, optionally filtered."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    if username and role:
        records = approval_store.list_by_user(tenant_id, username, role)
    else:
        records = approval_store.list_by_tenant(tenant_id, status=status)
    total = len(records)
    limit = max(1, min(limit, 200))
    paginated = records[offset: offset + limit]
    return {
        "approvals": [asdict(r) for r in paginated],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/approvals/{approval_id}", dependencies=[Depends(require_api_key)])
def get_approval_endpoint(approval_id: str, request: Request) -> dict:
    """Get a single approval record."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    rec = approval_store.get(approval_id, tenant_id=tenant_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"결재 문서를 찾을 수 없습니다: {approval_id}")
    return _serialize_approval_record(rec, request, tenant_id=tenant_id)


@router.post("/approvals/{approval_id}/submit", dependencies=[Depends(require_api_key)])
async def submit_for_review_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """기안 → 검토 (또는 수정 요청 → 재검토): submit for review."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    try:
        rec = approval_store.submit_for_review(
            approval_id,
            reviewer=payload.reviewer or payload.username,
            tenant_id=tenant_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        from app.services.notification_service import NotificationService
        await NotificationService(tenant_id).notify_approval_event(
            rec, "approval_requested", actor_name, payload.comment or ""
        )
    except Exception:
        pass
    _sync_project_document_approval_state(
        request,
        tenant_id=tenant_id,
        request_id=rec.request_id,
        approval_id=approval_id,
        approval_status=rec.status,
    )
    return asdict(rec)


@router.post("/approvals/{approval_id}/review/approve", dependencies=[Depends(require_api_key)])
async def approve_review_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """검토자 승인 (sets reviewer_approved=True, status stays in_review)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    try:
        rec = approval_store.approve_review(
            approval_id,
            author=payload.username,
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        from app.services.notification_service import NotificationService
        await NotificationService(tenant_id).notify_approval_event(
            rec, "approval_review_done", actor_name, payload.comment or ""
        )
    except Exception:
        pass
    _emit_approval_event(request, approval_id, "review_approved")
    return asdict(rec)


@router.post("/approvals/{approval_id}/review/request-changes", dependencies=[Depends(require_api_key)])
async def request_changes_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """검토자 수정 요청 (in_review → changes_requested)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    try:
        rec = approval_store.request_changes(
            approval_id,
            author=payload.username,
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        from app.services.notification_service import NotificationService
        await NotificationService(tenant_id).notify_approval_event(
            rec, "approval_changes_requested", actor_name, payload.comment or ""
        )
    except Exception:
        pass
    _sync_project_document_approval_state(
        request,
        tenant_id=tenant_id,
        request_id=rec.request_id,
        approval_id=approval_id,
        approval_status=rec.status,
    )
    _emit_approval_event(request, approval_id, "changes_requested")
    return asdict(rec)


@router.post("/approvals/{approval_id}/approve", dependencies=[Depends(require_api_key)])
async def final_approve_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """최종 결재 승인 (in_review → approved, 검토자 승인 선행 필수)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    current = approval_store.get(approval_id, tenant_id=tenant_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"결재 문서를 찾을 수 없습니다: {approval_id}")
    freshness = _serialize_approval_record(current, request, tenant_id=tenant_id)
    freshness_acknowledged = (
        payload.freshness_acknowledged and freshness["freshness_warning_present"]
    )
    _record_approval_freshness_audit(
        request,
        freshness,
        acknowledged=freshness_acknowledged,
    )
    if freshness["freshness_acknowledgement_required"] and not freshness_acknowledged:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approval_document_freshness_acknowledgement_required",
                "message": "현재 원본과 다른 결재 문서입니다. 상태를 확인하고 명시적으로 승인해야 합니다.",
                "project_document_binding_status": freshness["project_document_binding_status"],
                "decision_council_document_status": freshness[
                    "decision_council_document_status"
                ],
                "procurement_review_document_status": freshness[
                    "procurement_review_document_status"
                ],
            },
        )
    if payload.approver:
        try:
            approval_store.submit_for_approval(
                approval_id,
                approver=payload.approver,
                tenant_id=tenant_id,
            )
        except (KeyError, ValueError):
            pass
    try:
        rec = approval_store.approve_final(
            approval_id,
            author=payload.username,
            comment=payload.comment,
            tenant_id=tenant_id,
            freshness_acknowledged=freshness_acknowledged,
            approved_source_fingerprint=freshness["current_source_fingerprint"],
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _sync_project_document_approval_state(
        request,
        tenant_id=tenant_id,
        request_id=rec.request_id,
        approval_id=approval_id,
        approval_status=rec.status,
    )
    try:
        from app.services.notification_service import NotificationService
        await NotificationService(tenant_id).notify_approval_event(
            rec, "approval_approved", actor_name, payload.comment or ""
        )
    except Exception:
        pass
    _emit_approval_event(request, approval_id, "approved")
    return _serialize_approval_record(rec, request, tenant_id=tenant_id)


@router.post("/approvals/{approval_id}/reject", dependencies=[Depends(require_api_key)])
async def reject_approval_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """결재 반려 (in_review → rejected)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    try:
        rec = approval_store.reject(
            approval_id,
            author=payload.username,
            comment=payload.comment,
            tenant_id=tenant_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _sync_project_document_approval_state(
        request,
        tenant_id=tenant_id,
        request_id=rec.request_id,
        approval_id=approval_id,
        approval_status=rec.status,
    )
    try:
        from app.services.notification_service import NotificationService
        await NotificationService(tenant_id).notify_approval_event(
            rec, "approval_rejected", actor_name, payload.comment or ""
        )
    except Exception:
        pass
    _emit_approval_event(request, approval_id, "rejected")
    return asdict(rec)


@router.put("/approvals/{approval_id}/docs", dependencies=[Depends(require_api_key)])
def update_approval_docs_endpoint(approval_id: str, payload: UpdateApprovalDocsRequest, request: Request) -> dict:
    """Update documents after revision (기안자 수정 후 업데이트).

    Finalized approvals (status=approved or rejected) are immutable.
    """
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    rec = approval_store.get(approval_id, tenant_id=tenant_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="결재 문서를 찾을 수 없습니다.")
    if rec.status in ("approved", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"이미 {rec.status} 처리된 문서는 수정할 수 없습니다.",
        )
    try:
        updated = approval_store.update_docs(approval_id, payload.docs, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(updated)


@router.get("/approvals/{approval_id}/download/{fmt}", dependencies=[Depends(require_api_key)])
async def download_approved_doc_endpoint(
    approval_id: str,
    fmt: str,
    request: Request,
    source_change_acknowledged: bool = False,
) -> Response:
    """Download approved document. Only works when status=approved.
    Uses doc_snapshot (immutable approved version) + stored gov_options."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    rec = approval_store.get(approval_id, tenant_id=tenant_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"결재 문서를 찾을 수 없습니다: {approval_id}")
    if rec.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"승인된 문서만 다운로드할 수 있습니다. 현재 상태: {rec.status}"
        )
    freshness = _serialize_approval_record(rec, request, tenant_id=tenant_id)
    source_change_acknowledged = bool(
        source_change_acknowledged and freshness["post_approval_source_changed"]
    )
    _record_approval_download_freshness_audit(
        request,
        freshness,
        acknowledged=source_change_acknowledged,
    )
    if freshness["source_change_acknowledgement_required"] and not source_change_acknowledged:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "approved_document_source_change_acknowledgement_required",
                "message": "최종 승인 이후 원본 상태가 변경되었습니다. 현재 상태를 확인하고 다운로드해야 합니다.",
                "project_document_binding_status": freshness[
                    "project_document_binding_status"
                ],
                "decision_council_document_status": freshness[
                    "decision_council_document_status"
                ],
                "procurement_review_document_status": freshness[
                    "procurement_review_document_status"
                ],
            },
        )
    try:
        docs = _json.loads(rec.doc_snapshot)
    except Exception:
        docs = []
    gov_opts = _resolve_gov_options(rec.gov_options)
    title = rec.title
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    fmt_lower = fmt.lower().lstrip(".")
    if fmt_lower == "docx":
        content = build_docx(docs, title=title, gov_options=gov_opts)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif fmt_lower == "pdf":
        build_pdf = _load_pdf_builder()
        content = await build_pdf(docs, title=title, gov_options=gov_opts)
        media_type = "application/pdf"
        ext = "pdf"
    elif fmt_lower in ("hwp", "hwpx"):
        content = build_hwp(docs, title=title, gov_options=gov_opts)
        media_type = "application/hwp+zip"
        ext = "hwpx"
    elif fmt_lower in ("excel", "xlsx"):
        content = build_excel(docs, title=title)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식: {fmt}")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="approved.{ext}"; '
                f"filename*=UTF-8''{encoded_title}_approved.{ext}"
            )
        },
    )

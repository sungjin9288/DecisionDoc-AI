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
from app.schemas import (
    ApprovalActionRequest,
    CreateApprovalRequest,
    GovDocOptions,
    UpdateApprovalDocsRequest,
)
from app.services.docx_service import build_docx
from app.services.excel_service import build_excel
from app.services.hwp_service import build_hwp
from app.services.pdf_service import build_pdf

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/approvals", dependencies=[Depends(require_api_key)])
def create_approval_endpoint(payload: CreateApprovalRequest, request: Request) -> dict:
    """Create a new approval workflow record (기안 단계)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    rec = approval_store.create(
        tenant_id=tenant_id,
        request_id=payload.request_id,
        bundle_id=payload.bundle_id,
        title=payload.title,
        drafter=payload.drafter,
        docs=payload.docs,
        gov_options=payload.gov_options,
    )
    _sync_project_document_approval_state(
        request,
        tenant_id=tenant_id,
        request_id=rec.request_id,
        approval_id=rec.approval_id,
        approval_status=rec.status,
    )
    return asdict(rec)


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
    approval_store = request.app.state.approval_store
    rec = approval_store.get(approval_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"결재 문서를 찾을 수 없습니다: {approval_id}")
    return asdict(rec)


@router.post("/approvals/{approval_id}/submit", dependencies=[Depends(require_api_key)])
async def submit_for_review_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """기안 → 검토 (또는 수정 요청 → 재검토): submit for review."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    try:
        rec = approval_store.submit_for_review(approval_id, reviewer=payload.reviewer or payload.username)
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
        rec = approval_store.approve_review(approval_id, author=payload.username, comment=payload.comment)
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
        rec = approval_store.request_changes(approval_id, author=payload.username, comment=payload.comment)
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
    if payload.approver:
        try:
            approval_store.submit_for_approval(approval_id, approver=payload.approver)
        except (KeyError, ValueError):
            pass
    try:
        rec = approval_store.approve_final(approval_id, author=payload.username, comment=payload.comment)
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
    return asdict(rec)


@router.post("/approvals/{approval_id}/reject", dependencies=[Depends(require_api_key)])
async def reject_approval_endpoint(approval_id: str, payload: ApprovalActionRequest, request: Request) -> dict:
    """결재 반려 (in_review → rejected)."""
    tenant_id = get_tenant_id(request)
    approval_store = request.app.state.approval_store
    actor_name = getattr(request.state, "username", payload.username or "")
    try:
        rec = approval_store.reject(approval_id, author=payload.username, comment=payload.comment)
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
async def download_approved_doc_endpoint(approval_id: str, fmt: str, request: Request) -> Response:
    """Download approved document. Only works when status=approved.
    Uses doc_snapshot (immutable approved version) + stored gov_options."""
    approval_store = request.app.state.approval_store
    rec = approval_store.get(approval_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"결재 문서를 찾을 수 없습니다: {approval_id}")
    if rec.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"승인된 문서만 다운로드할 수 있습니다. 현재 상태: {rec.status}"
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

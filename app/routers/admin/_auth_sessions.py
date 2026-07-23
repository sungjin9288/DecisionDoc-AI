"""Read-only administration for tenant authentication-session retention."""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from app.dependencies import get_tenant_id, require_admin
from app.schemas.auth import (
    AuthSessionRetentionRecheckRequest,
    AuthSessionRetentionReviewDispositionRequest,
)
from app.storage.auth_session_retention import (
    AUTH_SESSION_RETENTION_DEFAULT_DAYS,
    AuthSessionRetentionContractError,
    build_retention_review_disposition_receipt,
    canonical_retention_json_bytes,
)
from app.storage.auth_session_store import (
    AUTH_SESSION_RETENTION_MAX_DAYS,
    AUTH_SESSION_RETENTION_MIN_DAYS,
    AUTH_SESSION_RETENTION_POLICY_DAYS,
    AuthSessionStore,
    AuthSessionStoreError,
    get_auth_session_store,
)


logger = logging.getLogger("decisiondoc.auth")
router = APIRouter()


@router.get(
    "/admin/auth-sessions/retention-preview",
    dependencies=[Depends(require_admin)],
)
def preview_auth_session_retention(
    request: Request,
    retention_days: Annotated[
        int,
        Query(
            ge=AUTH_SESSION_RETENTION_MIN_DAYS,
            le=AUTH_SESSION_RETENTION_MAX_DAYS,
        ),
    ] = AUTH_SESSION_RETENTION_DEFAULT_DAYS,
) -> JSONResponse:
    """Return redacted cleanup candidates without authorizing deletion."""
    tenant_id = get_tenant_id(request)
    try:
        preview = get_auth_session_store(
            tenant_id,
            data_dir=request.app.state.data_dir,
            backend=request.app.state.state_backend,
        ).preview_retention(retention_days=retention_days)
    except (AuthSessionStoreError, ValueError) as exc:
        logger.error(
            "[Auth] Session retention preview failed - failing CLOSED.",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=503,
            detail="로그인 세션 보존 상태를 일시적으로 확인할 수 없습니다.",
        ) from exc

    request.state.auth_session_retention_days = preview["retention_days"]
    request.state.auth_session_retention_inspected_count = preview[
        "inspected_sessions"
    ]
    request.state.auth_session_retention_eligible_count = preview[
        "eligible_sessions"
    ]
    request.state.auth_session_retention_read_only = True
    return JSONResponse(content=preview, headers={"Cache-Control": "no-store"})


@router.get(
    "/admin/auth-sessions/retention-comparison",
    dependencies=[Depends(require_admin)],
)
def compare_auth_session_retention(request: Request) -> JSONResponse:
    """Compare fixed cleanup policies against one redacted inspection."""
    tenant_id = get_tenant_id(request)
    try:
        comparison = get_auth_session_store(
            tenant_id,
            data_dir=request.app.state.data_dir,
            backend=request.app.state.state_backend,
        ).compare_retention_policies()
    except AuthSessionStoreError as exc:
        logger.error(
            "[Auth] Session retention comparison failed - failing CLOSED.",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=503,
            detail="로그인 세션 보존 정책을 일시적으로 비교할 수 없습니다.",
        ) from exc

    request.state.auth_session_retention_policy_days = comparison["policy_days"]
    request.state.auth_session_retention_inspected_count = comparison[
        "inspected_sessions"
    ]
    request.state.auth_session_retention_eligible_counts = [
        policy["eligible_sessions"] for policy in comparison["policies"]
    ]
    request.state.auth_session_retention_read_only = True
    request.state.auth_session_retention_snapshot_atomic = False
    return JSONResponse(content=comparison, headers={"Cache-Control": "no-store"})


@router.get(
    "/admin/auth-sessions/retention-handoff",
    dependencies=[Depends(require_admin)],
)
def download_auth_session_retention_handoff(
    request: Request,
    retention_days: Annotated[
        int,
        Query(),
    ] = AUTH_SESSION_RETENTION_POLICY_DAYS[0],
) -> Response:
    """Download one read-only retention comparison for human review."""
    if retention_days not in AUTH_SESSION_RETENTION_POLICY_DAYS:
        raise HTTPException(
            status_code=422,
            detail=(
                "retention_days must be one of "
                f"{', '.join(map(str, AUTH_SESSION_RETENTION_POLICY_DAYS))}"
            ),
        )
    tenant_id = get_tenant_id(request)
    try:
        store = get_auth_session_store(
            tenant_id,
            data_dir=request.app.state.data_dir,
            backend=request.app.state.state_backend,
        )
        handoff = store.build_retention_review_handoff(retention_days=retention_days)
        body = AuthSessionStore.serialize_retention_review_handoff(handoff)
    except (AuthSessionStoreError, ValueError) as exc:
        logger.error(
            "[Auth] Session retention handoff failed - failing CLOSED.",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=503,
            detail="로그인 세션 보존 검토 자료를 일시적으로 만들 수 없습니다.",
        ) from exc

    comparison = handoff["comparison"]
    request.state.auth_session_retention_days = retention_days
    request.state.auth_session_retention_policy_days = comparison["policy_days"]
    request.state.auth_session_retention_inspected_count = comparison[
        "inspected_sessions"
    ]
    request.state.auth_session_retention_eligible_counts = [
        policy["eligible_sessions"] for policy in comparison["policies"]
    ]
    request.state.auth_session_retention_read_only = True
    request.state.auth_session_retention_snapshot_atomic = False
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                'attachment; filename="auth-session-retention-review-handoff-'
                f"{retention_days}d.json\""
            ),
            "X-DecisionDoc-Auth-Session-Retention-Handoff-SHA256": (
                hashlib.sha256(body).hexdigest()
            ),
        },
    )


@router.post(
    "/admin/auth-sessions/retention-handoff/recheck",
    dependencies=[Depends(require_admin)],
)
def recheck_auth_session_retention_handoff(
    request: Request,
    payload: AuthSessionRetentionRecheckRequest,
) -> Response:
    """Recheck one tenant-bound review handoff without changing session state."""
    tenant_id = get_tenant_id(request)
    store = get_auth_session_store(
        tenant_id,
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )
    try:
        receipt = store.recheck_retention_review_handoff(
            source_handoff=payload.source_handoff,
            source_handoff_sha256=payload.source_handoff_sha256,
        )
        body = AuthSessionStore.serialize_retention_recheck_receipt(receipt)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="로그인 세션 보존 검토 자료를 검증하지 못했습니다.",
        ) from exc
    except AuthSessionStoreError as exc:
        logger.error(
            "[Auth] Session retention recheck failed - failing CLOSED.",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=503,
            detail="로그인 세션 보존 상태를 일시적으로 재확인할 수 없습니다.",
        ) from exc

    current_handoff = receipt["current_handoff"]
    comparison = current_handoff["comparison"]
    selected_policy_days = current_handoff["selected_policy_days"]
    selected_policy = next(
        policy
        for policy in comparison["policies"]
        if policy["retention_days"] == selected_policy_days
    )
    request.state.auth_session_retention_days = selected_policy_days
    request.state.auth_session_retention_inspected_count = comparison[
        "inspected_sessions"
    ]
    request.state.auth_session_retention_eligible_count = selected_policy[
        "eligible_sessions"
    ]
    request.state.auth_session_retention_aggregate_status = receipt["aggregate_status"]
    request.state.auth_session_retention_read_only = True
    request.state.auth_session_retention_snapshot_atomic = False
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                'attachment; filename="auth-session-retention-recheck-receipt-'
                f"{selected_policy_days}d.json\""
            ),
            "X-DecisionDoc-Auth-Session-Retention-Recheck-Receipt-SHA256": (
                hashlib.sha256(body).hexdigest()
            ),
        },
    )


@router.post(
    "/admin/auth-sessions/retention-handoff/review-disposition",
    dependencies=[Depends(require_admin)],
)
def download_auth_session_retention_review_disposition(
    request: Request,
    payload: AuthSessionRetentionReviewDispositionRequest,
) -> Response:
    """Issue a deterministic operator disposition record without state mutation."""
    tenant_id = get_tenant_id(request)
    try:
        receipt = build_retention_review_disposition_receipt(
            source_recheck_receipt=payload.source_recheck_receipt,
            source_recheck_receipt_sha256=payload.source_recheck_receipt_sha256,
            expected_tenant_id=tenant_id,
            review_disposition=payload.review_disposition,
        )
    except AuthSessionRetentionContractError as exc:
        raise HTTPException(
            status_code=422,
            detail="로그인 세션 보존 재확인 영수증을 검증하지 못했습니다.",
        ) from exc

    body = canonical_retention_json_bytes(receipt)
    body_sha256 = hashlib.sha256(body).hexdigest()
    request.state.auth_session_retention_review_disposition = {
        "selected_policy_days": receipt["selected_policy_days"],
        "aggregate_status": receipt["aggregate_status"],
        "review_disposition": receipt["review_disposition"],
        "source_recheck_receipt_sha256": receipt["source_recheck_receipt_sha256"],
        "receipt_sha256": body_sha256,
        "review_only": True,
    }
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                "attachment; filename=\"auth-session-retention-review-disposition-"
                f"receipt-{receipt['selected_policy_days']}d.json\""
            ),
            "X-DecisionDoc-Auth-Session-Retention-Review-Disposition-Receipt-SHA256": (
                body_sha256
            ),
        },
    )

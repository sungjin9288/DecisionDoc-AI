"""Read-only administration for tenant authentication-session retention."""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from app.dependencies import get_tenant_id, require_admin
from app.storage.auth_session_store import (
    AUTH_SESSION_RETENTION_DEFAULT_DAYS,
    AUTH_SESSION_RETENTION_MAX_DAYS,
    AUTH_SESSION_RETENTION_MIN_DAYS,
    AUTH_SESSION_RETENTION_POLICY_DAYS,
    AuthSessionStore,
    AuthSessionStoreError,
    get_auth_session_store,
)


logger = logging.getLogger("decisiondoc.auth")
router = APIRouter()


@router.get("/admin/auth-sessions/retention-preview")
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
    require_admin(request)
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


@router.get("/admin/auth-sessions/retention-comparison")
def compare_auth_session_retention(request: Request) -> JSONResponse:
    """Compare fixed cleanup policies against one redacted inspection."""
    require_admin(request)
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


@router.get("/admin/auth-sessions/retention-handoff")
def download_auth_session_retention_handoff(
    request: Request,
    retention_days: Annotated[
        int,
        Query(),
    ] = AUTH_SESSION_RETENTION_POLICY_DAYS[0],
) -> Response:
    """Download one read-only retention comparison for human review."""
    require_admin(request)
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

"""Read-only administration for tenant authentication-session retention."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies import get_tenant_id, require_admin
from app.storage.auth_session_store import (
    AUTH_SESSION_RETENTION_DEFAULT_DAYS,
    AUTH_SESSION_RETENTION_MAX_DAYS,
    AUTH_SESSION_RETENTION_MIN_DAYS,
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

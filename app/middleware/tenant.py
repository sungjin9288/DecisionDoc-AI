"""tenant.py — Tenant resolution middleware.

Resolves the active tenant from the X-Tenant-ID request header.
Falls back to SYSTEM_TENANT_ID when the header is absent.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.tenant import SYSTEM_TENANT_ID

_log = logging.getLogger("decisiondoc.middleware.tenant")


def install_tenant_middleware(app: FastAPI, tenant_store: "Any") -> None:
    """Register tenant resolution middleware on the FastAPI app.

    Args:
        app: The FastAPI application instance.
        tenant_store: A TenantStore instance used to validate tenant IDs.
    """
    from typing import Any  # local to avoid circular

    @app.middleware("http")
    async def tenant_middleware(request: Request, call_next):  # type: ignore[override]
        tenant_id = request.headers.get("X-Tenant-ID", SYSTEM_TENANT_ID)

        # Step 1: Check JWT tenant_id BEFORE tenant-store lookup.
        # This ensures TENANT_MISMATCH is returned when the header is spoofed,
        # rather than the less-informative "Unknown or inactive tenant" error.
        jwt_tenant_id = ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                from app.services.auth_service import verify_token
                payload = verify_token(token)
                if payload:
                    jwt_tenant_id = payload.get("tenant_id", "")
                    if (jwt_tenant_id and
                            tenant_id != SYSTEM_TENANT_ID and
                            tenant_id != jwt_tenant_id):
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": "테넌트 ID가 인증 토큰과 일치하지 않습니다.",
                                "code": "TENANT_MISMATCH",
                            },
                        )
                    # Always use JWT's tenant_id when authenticated
                    if jwt_tenant_id:
                        tenant_id = jwt_tenant_id
            except Exception:
                pass  # Let auth middleware handle invalid tokens

        # Step 2: Validate the resolved tenant exists and is active.
        if tenant_id != SYSTEM_TENANT_ID:
            tenant = tenant_store.get_tenant(tenant_id)
            if not tenant or not tenant.is_active:
                _log.warning("Rejected request for unknown/inactive tenant: %s", tenant_id)
                return JSONResponse(
                    status_code=403,
                    content={"error": f"Unknown or inactive tenant: {tenant_id!r}"},
                )
        else:
            # System tenant — always valid; look up record for custom hints
            tenant = tenant_store.get_tenant(SYSTEM_TENANT_ID)

        request.state.tenant_id = tenant_id
        request.state.tenant = tenant

        return await call_next(request)

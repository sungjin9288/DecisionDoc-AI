"""app/middleware/billing.py — Usage limit enforcement middleware."""
from __future__ import annotations

import logging
from fastapi import Request
from fastapi.responses import JSONResponse

_log = logging.getLogger("decisiondoc.billing")

METERED_ENDPOINTS = {
    "POST /generate/stream",
    "POST /generate/sketch",
    "POST /generate/with-attachments",
    "POST /generate/from-documents",
}


async def billing_middleware(request: Request, call_next):
    """Check usage limits before allowing generation requests."""
    path = request.url.path
    method = request.method
    endpoint_key = f"{method} {path}"

    if endpoint_key not in METERED_ENDPOINTS:
        return await call_next(request)

    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return await call_next(request)

    try:
        from app.storage.billing_store import get_billing_store
        from app.storage.usage_store import UsageStore

        billing = get_billing_store(tenant_id)
        usage = UsageStore()

        account = billing.get_account(tenant_id)
        plan = billing.get_plan(tenant_id)
        limit_check = usage.check_limit(tenant_id, plan)

        # Enterprise + trialing: always pass
        if plan.plan_id == "enterprise" or account.status == "trialing":
            return await call_next(request)

        # Block if over limit
        if not limit_check["within_limit"]:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "사용량 한도를 초과했습니다.",
                    "code": "LIMIT_EXCEEDED",
                    "plan": plan.plan_id,
                    "limit": limit_check["generations_limit"],
                    "used": limit_check["generations_used"],
                    "upgrade_url": "/billing/upgrade",
                },
            )

        # Warn if approaching limit (80%)
        if limit_check["percent_used"] >= 80:
            request.state.usage_warning = {
                "percent_used": limit_check["percent_used"],
                "generations_remaining": max(
                    0, limit_check["generations_limit"] - limit_check["generations_used"]
                ),
            }

    except Exception as exc:
        _log.warning("[BillingMiddleware] Error checking limits: %s", exc)

    return await call_next(request)


def install_billing_middleware(app) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=billing_middleware)

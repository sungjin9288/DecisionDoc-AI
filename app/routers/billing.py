"""app/routers/billing.py — Billing & subscription endpoints.

Extracted from app/main.py.
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException, Request

from app.dependencies import get_tenant_id, require_auth
from app.schemas import CheckoutRequest, PlanOverrideRequest

router = APIRouter(tags=["billing"])


@router.get("/billing/status")
async def get_billing_status(request: Request):
    require_auth(request)
    tenant_id = get_tenant_id(request)
    from app.storage.billing_store import get_billing_store
    from app.storage.usage_store import UsageStore

    billing = get_billing_store(tenant_id)
    usage = UsageStore()
    account = billing.get_account(tenant_id)
    plan = billing.get_plan(tenant_id)
    summary = usage.get_current_month(tenant_id)
    limit_check = usage.check_limit(tenant_id, plan)
    return {
        "plan": {
            "plan_id": plan.plan_id,
            "plan_name": plan.plan_name,
            "status": account.status,
        },
        "usage": {
            "generations_used": limit_check["generations_used"],
            "generations_limit": plan.monthly_generations,
            "tokens_used": limit_check["tokens_used"],
            "tokens_limit": plan.monthly_tokens,
            "percent_used": limit_check["percent_used"],
            "current_cost_usd": summary.total_cost_usd if summary else 0,
        },
        "features": plan.features,
        "card_last4": account.card_last4,
        "card_brand": account.card_brand,
        "period_end": account.current_period_end,
    }


@router.get("/billing/usage")
async def get_usage_history(request: Request, days: int = 30):
    from app.storage.usage_store import UsageStore

    tenant_id = get_tenant_id(request)
    store = UsageStore()
    summary = store.get_current_month(tenant_id)
    return {
        "daily": store.get_daily_usage(tenant_id, days=days),
        "summary": dataclasses.asdict(summary) if summary else None,
    }


@router.get("/billing/plans")
async def list_plans():
    from app.storage.billing_store import PREDEFINED_PLANS

    return {
        "plans": [
            {
                "plan_id": p.plan_id,
                "plan_name": p.plan_name,
                "base_price_usd": p.base_price_usd,
                "monthly_generations": p.monthly_generations,
                "monthly_tokens": p.monthly_tokens,
                "max_users": p.max_users,
                "features": p.features,
                "billing_cycle": p.billing_cycle,
            }
            for p in PREDEFINED_PLANS.values()
        ]
    }


@router.post("/billing/checkout")
async def create_checkout(request: Request, body: CheckoutRequest):
    require_auth(request)
    tenant_id = get_tenant_id(request)
    from app.services.billing_service import create_checkout_session

    base_url = str(request.base_url).rstrip("/")
    try:
        url = await create_checkout_session(
            tenant_id=tenant_id,
            plan_id=body.plan_id,
            success_url=f"{base_url}/billing/success?plan={body.plan_id}",
            cancel_url=f"{base_url}/?billing=canceled",
        )
        return {"checkout_url": url}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        from app.services.billing_service import handle_webhook

        result = await handle_webhook(payload, signature)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/billing/cancel")
async def cancel_billing(request: Request):
    require_auth(request)
    tenant_id = get_tenant_id(request)
    from app.services.billing_service import cancel_subscription

    success = await cancel_subscription(tenant_id)
    if not success:
        raise HTTPException(status_code=400, detail="구독 취소 중 오류가 발생했습니다.")
    return {"message": "구독이 현재 기간 종료 시 해지됩니다."}


@router.post("/admin/billing/override")
async def override_plan(request: Request, body: PlanOverrideRequest):
    if getattr(request.state, "user_role", "") != "admin":
        raise HTTPException(status_code=403)
    tenant_id = get_tenant_id(request)
    from app.storage.billing_store import get_billing_store

    get_billing_store(tenant_id).update_plan(tenant_id, body.plan_id)
    return {"message": f"플랜이 {body.plan_id}로 변경되었습니다."}

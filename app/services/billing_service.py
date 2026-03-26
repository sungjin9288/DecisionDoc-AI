"""app/services/billing_service.py — Stripe billing integration."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import httpx

_log = logging.getLogger("decisiondoc.billing")
STRIPE_API_BASE = "https://api.stripe.com/v1"


async def create_checkout_session(
    tenant_id: str,
    plan_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    api_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")

    from app.storage.billing_store import get_billing_store, PREDEFINED_PLANS
    plan = PREDEFINED_PLANS.get(plan_id)
    if not plan or not plan.stripe_price_id:
        raise ValueError(f"No Stripe price configured for plan: {plan_id}")

    billing = get_billing_store(tenant_id)
    account = billing.get_account(tenant_id)

    params = {
        "mode": "subscription",
        "line_items[0][price]": plan.stripe_price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[tenant_id]": tenant_id,
        "metadata[plan_id]": plan_id,
    }
    if account.stripe_customer_id:
        params["customer"] = account.stripe_customer_id
    else:
        params["customer_creation"] = "always"

    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{STRIPE_API_BASE}/checkout/sessions",
            data=params,
            auth=(api_key, ""),
        )
        res.raise_for_status()
        return res.json()["url"]


async def handle_webhook(payload: bytes, signature: str) -> dict:
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    if not webhook_secret:
        if is_production:
            raise ValueError("STRIPE_WEBHOOK_SECRET not configured in production")
        _log.warning(
            "[Billing] Webhook signature verification SKIPPED (no secret set). "
            "Set STRIPE_WEBHOOK_SECRET in production!"
        )
    else:
        # Always verify when secret is present
        _verify_stripe_signature(payload, signature, webhook_secret)

    event = json.loads(payload)
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    from app.storage.billing_store import get_billing_store

    if event_type == "checkout.session.completed":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        plan_id = data.get("metadata", {}).get("plan_id")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        if tenant_id and plan_id:
            b = get_billing_store(tenant_id)
            b.update_plan(tenant_id, plan_id)
            b.update_stripe_info(tenant_id, customer_id, subscription_id, None, None)
            b.set_status(tenant_id, "active")
            _log.info("[Billing] Plan upgraded: %s → %s", tenant_id, plan_id)

    elif event_type == "invoice.paid":
        _log.info("[Billing] Invoice paid: %s", data.get("subscription"))

    elif event_type == "customer.subscription.deleted":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        if tenant_id:
            b = get_billing_store(tenant_id)
            b.update_plan(tenant_id, "free")
            b.set_status(tenant_id, "canceled")
            _log.info("[Billing] Subscription canceled: %s", tenant_id)

    elif event_type == "invoice.payment_failed":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        if tenant_id:
            get_billing_store(tenant_id).set_status(tenant_id, "past_due")
            _log.warning("[Billing] Payment failed: %s", tenant_id)

    return {"received": True}


async def cancel_subscription(tenant_id: str) -> bool:
    api_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not api_key:
        return False
    from app.storage.billing_store import get_billing_store
    account = get_billing_store(tenant_id).get_account(tenant_id)
    if not account.stripe_subscription_id:
        return False
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{STRIPE_API_BASE}/subscriptions/{account.stripe_subscription_id}",
            data={"cancel_at_period_end": "true"},
            auth=(api_key, ""),
        )
        return res.status_code == 200


def _verify_stripe_signature(payload: bytes, signature: str, secret: str) -> None:
    import time
    parts = {p[:2]: p[3:] for p in signature.split(",")}
    timestamp = parts.get("t", "")
    sig = parts.get("v1", "")
    if not timestamp or not sig:
        raise ValueError("Invalid Stripe signature format")
    # Reject events older than 5 minutes (replay attack prevention)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError("Stripe webhook timestamp too old (possible replay attack)")
    except ValueError as e:
        if "replay" in str(e):
            raise
        raise ValueError("Invalid timestamp in Stripe signature") from e
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.{payload.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Stripe signature mismatch")

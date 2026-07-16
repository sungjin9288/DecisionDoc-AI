"""app/services/billing_service.py — Stripe billing integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path

import httpx

from app.storage.state_backend import StateBackend

_log = logging.getLogger("decisiondoc.billing")
STRIPE_API_BASE = "https://api.stripe.com/v1"


async def create_checkout_session(
    tenant_id: str,
    plan_id: str,
    success_url: str,
    cancel_url: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> str:
    api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")

    from app.storage.billing_store import get_billing_store, PREDEFINED_PLANS

    plan = PREDEFINED_PLANS.get(plan_id)
    price_id = (
        os.getenv(f"STRIPE_{plan_id.upper()}_PRICE_ID", "").strip()
        if plan is not None
        else ""
    ) or ((plan.stripe_price_id or "").strip() if plan is not None else "")
    if not plan or not price_id:
        raise ValueError(f"No Stripe price configured for plan: {plan_id}")

    billing = get_billing_store(tenant_id, data_dir=data_dir, backend=backend)
    account = billing.get_account()

    params = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[tenant_id]": tenant_id,
        "metadata[plan_id]": plan_id,
        "subscription_data[metadata][tenant_id]": tenant_id,
        "subscription_data[metadata][plan_id]": plan_id,
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


async def handle_webhook(
    payload: bytes,
    signature: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> dict:
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    environment_names = {
        os.getenv("DECISIONDOC_ENV", "").strip().lower(),
        os.getenv("ENVIRONMENT", "").strip().lower(),
    }
    is_production = bool(environment_names & {"prod", "production"})

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
    if not isinstance(event, dict):
        raise ValueError("Invalid Stripe webhook event")
    event_type = event.get("type", "")
    event_data = event.get("data", {})
    if not isinstance(event_data, dict):
        raise ValueError("Invalid Stripe webhook event data")
    data = event_data.get("object", {})
    if not isinstance(data, dict):
        raise ValueError("Invalid Stripe webhook object")

    from app.storage.billing_store import get_billing_store

    if event_type == "checkout.session.completed":
        metadata = _webhook_metadata(data)
        tenant_id = _required_webhook_string(metadata.get("tenant_id"), "tenant identity")
        plan_id = _required_webhook_string(metadata.get("plan_id"), "plan identity")
        customer_id = _required_webhook_string(data.get("customer"), "customer identity")
        subscription_id = _required_webhook_string(
            data.get("subscription"),
            "subscription identity",
        )
        b = get_billing_store(tenant_id, data_dir=data_dir, backend=backend)
        b.apply_subscription_update(
            plan_id=plan_id,
            status="active",
            customer_id=customer_id,
            subscription_id=subscription_id,
        )
        _log.info("[Billing] Plan upgraded: %s → %s", tenant_id, plan_id)

    elif event_type == "invoice.paid":
        _log.info("[Billing] Invoice paid: %s", data.get("subscription"))

    elif event_type == "customer.subscription.deleted":
        tenant_id = _required_webhook_string(
            _webhook_metadata(data).get("tenant_id"),
            "tenant identity",
        )
        b = get_billing_store(tenant_id, data_dir=data_dir, backend=backend)
        b.apply_subscription_update(plan_id="free", status="canceled")
        _log.info("[Billing] Subscription canceled: %s", tenant_id)

    elif event_type == "invoice.payment_failed":
        tenant_id = _required_webhook_string(
            _webhook_metadata(data).get("tenant_id"),
            "tenant identity",
        )
        get_billing_store(
            tenant_id,
            data_dir=data_dir,
            backend=backend,
        ).set_status("past_due")
        _log.warning("[Billing] Payment failed: %s", tenant_id)

    return {"received": True}


def _webhook_metadata(data: dict) -> dict:
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Invalid Stripe webhook metadata")
    return metadata


def _required_webhook_string(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Invalid Stripe webhook {field}")
    return value


async def cancel_subscription(
    tenant_id: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> bool:
    api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not api_key:
        return False
    from app.storage.billing_store import get_billing_store

    account = get_billing_store(
        tenant_id,
        data_dir=data_dir,
        backend=backend,
    ).get_account()
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

    timestamp = ""
    signatures: list[str] = []
    for part in signature.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator or not value:
            continue
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp or not signatures:
        raise ValueError("Invalid Stripe signature format")
    # Reject events older than 5 minutes (replay attack prevention)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError(
                "Invalid Stripe webhook timestamp: too old (possible replay attack)"
            )
    except ValueError as e:
        if "replay" in str(e):
            raise
        raise ValueError("Invalid timestamp in Stripe signature") from e
    expected = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise ValueError("Stripe signature mismatch")

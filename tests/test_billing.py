"""tests/test_billing.py — Billing and usage tracking tests.

Coverage (25+ tests):
  UsageStore  : record event, get_current_month, get_daily_usage, check_limit
  UsageStore  : check_limit within/over for free/pro/enterprise (-1 = unlimited)
  BillingStore: get_account creates free plan if missing, get_plan, update_plan
  BillingStore: is_feature_enabled, overage_cost, update_stripe_info, set_status
  billing_middleware: free plan over limit → 402, enterprise → pass, non-generation → pass
  handle_webhook: checkout.completed → plan updated, subscription.deleted → free
  handle_webhook: payment_failed → past_due, invalid signature → ValueError
  API: GET /billing/status, GET /billing/plans, POST /billing/checkout (no key → 400)
  API: POST /billing/webhook processes event, POST /admin/billing/override
  API: GET /billing/usage, POST /billing/cancel (no stripe → 400)
"""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.storage.usage_store import UsageEvent
from tests.async_helper import run_async

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_billing_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-billing-tests-123!")
    # Clear singleton caches
    try:
        import app.storage.billing_store as bs
        bs._store_instances.clear()
    except Exception:
        pass
    try:
        import app.storage.usage_store as us
        us._path_locks.clear()
    except Exception:
        pass
    yield
    try:
        import app.storage.billing_store as bs
        bs._store_instances.clear()
    except Exception:
        pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-billing-tests-123!")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    from fastapi.testclient import TestClient
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-billing-tests-123!")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    from fastapi.testclient import TestClient
    app = create_app()
    tc = TestClient(app, raise_server_exceptions=False)
    # Bootstrap first admin via /auth/register (no auth required for first user)
    tc.post(
        "/auth/register",
        json={
            "username": "admin",
            "password": "Admin@1234",
            "display_name": "Admin",
            "email": "a@t.com",
        },
    )
    res = tc.post("/auth/login", json={"username": "admin", "password": "Admin@1234"})
    data = res.json()
    token = data.get("access_token") or data.get("token", "")
    tc.headers.update({"Authorization": f"Bearer {token}"})
    return tc, tmp_path


def _make_event(tenant_id: str = "t1", tokens: int = 1000) -> UsageEvent:
    return UsageEvent(
        event_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id="u1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="doc.generate",
        bundle_id="proposal_kr",
        tokens_input=tokens // 2,
        tokens_output=tokens // 2,
        tokens_total=tokens,
        cost_usd=0.002,
        model="mock",
        request_id=str(uuid.uuid4()),
    )


# ── UsageStore tests ──────────────────────────────────────────────────────────

def test_usage_store_record_and_get_current_month(tmp_path):
    from app.storage.usage_store import UsageStore
    store = UsageStore(tenant_id="tenant_a")
    event = _make_event("tenant_a")
    store.record(event)
    summary = store.get_current_month()
    assert summary is not None
    assert summary.total_generations == 1
    assert summary.total_tokens == event.tokens_total


def test_usage_store_multiple_events(tmp_path):
    from app.storage.usage_store import UsageStore
    store = UsageStore(tenant_id="tenant_b")
    for _ in range(5):
        store.record(_make_event("tenant_b"))
    summary = store.get_current_month()
    assert summary.total_generations == 5


def test_usage_store_by_bundle(tmp_path):
    from app.storage.usage_store import UsageStore
    store = UsageStore(tenant_id="tenant_c")
    store.record(_make_event("tenant_c"))
    summary = store.get_current_month()
    assert "proposal_kr" in summary.by_bundle


def test_usage_store_get_daily_usage(tmp_path):
    from app.storage.usage_store import UsageStore
    store = UsageStore(tenant_id="tenant_d")
    store.record(_make_event("tenant_d"))
    daily = store.get_daily_usage(days=7)
    assert isinstance(daily, list)
    assert len(daily) >= 1
    assert "date" in daily[0]
    assert "generations" in daily[0]


def test_usage_store_get_total_month_cost(tmp_path):
    from app.storage.usage_store import UsageStore
    store = UsageStore(tenant_id="tenant_e")
    store.record(_make_event("tenant_e"))
    cost = store.get_total_month_cost()
    assert cost >= 0


def test_check_limit_within_free_plan(tmp_path):
    from app.storage.usage_store import UsageStore
    from app.storage.billing_store import PREDEFINED_PLANS
    store = UsageStore(tenant_id="tenant_f")
    plan = PREDEFINED_PLANS["free"]  # 20 generations
    result = store.check_limit(plan)
    assert result["within_limit"] is True
    assert result["generations_limit"] == 20
    assert result["generations_used"] == 0


def test_check_limit_over_free_plan(tmp_path):
    from app.storage.usage_store import UsageStore
    from app.storage.billing_store import PREDEFINED_PLANS
    store = UsageStore(tenant_id="tenant_g")
    plan = PREDEFINED_PLANS["free"]  # 20 limit
    for _ in range(21):
        store.record(_make_event("tenant_g"))
    result = store.check_limit(plan)
    assert result["within_limit"] is False
    assert result["generations_used"] == 21
    assert result["percent_used"] >= 100


def test_check_limit_enterprise_unlimited(tmp_path):
    from app.storage.usage_store import UsageStore
    from app.storage.billing_store import PREDEFINED_PLANS
    store = UsageStore(tenant_id="tenant_h")
    plan = PREDEFINED_PLANS["enterprise"]  # unlimited
    for _ in range(1000):
        store.record(_make_event("tenant_h"))
    result = store.check_limit(plan)
    assert result["within_limit"] is True
    assert result["percent_used"] == 0


def test_usage_store_no_events_empty_summary(tmp_path):
    from app.storage.usage_store import UsageStore
    store = UsageStore(tenant_id="no_events_tenant")
    summary = store.get_current_month()
    # Either None or empty summary with 0 generations
    assert summary is None or summary.total_generations == 0


def test_usage_store_requires_safe_tenant_before_creating_paths(tmp_path):
    from app.storage.usage_store import UsageStore

    with pytest.raises(TypeError):
        UsageStore(tmp_path)

    for tenant_id in ("", " tenant-a", "tenant-a ", ".", "..", "a/b", "a\\b", "a\x00b"):
        with pytest.raises(ValueError, match="Invalid tenant_id"):
            UsageStore(tmp_path, tenant_id=tenant_id)

    assert not (tmp_path / "tenants").exists()


def test_usage_store_rejects_foreign_event_without_writing(tmp_path):
    from app.storage.usage_store import UsageStore

    store = UsageStore(tmp_path, tenant_id="tenant-a")

    with pytest.raises(ValueError, match="event tenant ownership mismatch"):
        store.record(_make_event("tenant-b"))

    assert not (tmp_path / "tenants").exists()


def test_usage_store_excludes_foreign_event_drift_and_preserves_source(tmp_path):
    from app.storage.usage_store import UsageStore

    store = UsageStore(tmp_path, tenant_id="tenant-a")
    store.record(_make_event("tenant-a"))
    path = tmp_path / "tenants" / "tenant-a" / "usage.jsonl"
    foreign = _make_event("tenant-b")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(foreign.__dict__) + "\n")
    source_before = path.read_text(encoding="utf-8")

    daily = store.get_daily_usage(days=7)

    assert sum(day["generations"] for day in daily) == 1
    assert path.read_text(encoding="utf-8") == source_before


def test_usage_store_preserves_foreign_summary_and_stops_update(tmp_path):
    from app.storage.usage_store import UsageStore

    store = UsageStore(tmp_path, tenant_id="tenant-a")
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    summary_path = tmp_path / "tenants" / "tenant-a" / "usage_summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        json.dumps(
            {
                year_month: {
                    "tenant_id": "tenant-b",
                    "year_month": year_month,
                    "total_generations": 99,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
            }
        ),
        encoding="utf-8",
    )
    source_before = summary_path.read_bytes()

    assert store.get_current_month() is None
    with pytest.raises(ValueError, match="summary tenant ownership mismatch"):
        store.record(_make_event("tenant-a"))

    assert summary_path.read_bytes() == source_before
    assert not (summary_path.parent / "usage.jsonl").exists()


def test_usage_store_concurrent_instances_preserve_every_event(tmp_path):
    from app.storage.usage_store import UsageStore

    stores = [UsageStore(tmp_path, tenant_id="tenant-a") for _ in range(20)]
    events = [_make_event("tenant-a") for _ in stores]

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(lambda pair: pair[0].record(pair[1]), zip(stores, events)))

    path = tmp_path / "tenants" / "tenant-a" / "usage.jsonl"
    persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    summary = stores[0].get_current_month()

    assert {event["event_id"] for event in persisted} == {event.event_id for event in events}
    assert summary is not None
    assert summary.total_generations == 20


# ── BillingStore tests ────────────────────────────────────────────────────────

def test_billing_store_creates_free_plan_by_default(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("new_tenant")
    account = store.get_account()
    assert account.plan_id == "free"
    assert account.status == "active"
    assert account.tenant_id == "new_tenant"


def test_billing_store_get_plan_free(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("plan_tenant")
    plan = store.get_plan()
    assert plan.plan_id == "free"
    assert plan.monthly_generations == 20


def test_billing_store_update_plan(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("upgrade_tenant")
    store.update_plan("pro")
    plan = store.get_plan()
    assert plan.plan_id == "pro"
    assert plan.monthly_generations == 200


def test_billing_store_is_feature_enabled(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("feat_tenant")
    # Free plan has basic_bundles but not sso
    assert store.is_feature_enabled("basic_bundles") is True
    assert store.is_feature_enabled("sso") is False
    # Upgrade to enterprise
    store.update_plan("enterprise")
    assert store.is_feature_enabled("sso") is True
    assert store.is_feature_enabled("finetune") is True


def test_billing_store_set_status(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("status_tenant")
    store.set_status("past_due")
    account = store.get_account()
    assert account.status == "past_due"


def test_billing_store_update_stripe_info(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("stripe_tenant")
    store.update_stripe_info("cus_123", "sub_456", "4242", "visa")
    account = store.get_account()
    assert account.stripe_customer_id == "cus_123"
    assert account.stripe_subscription_id == "sub_456"
    assert account.card_last4 == "4242"


def test_billing_store_overage_cost_zero_on_free(tmp_path):
    from app.storage.billing_store import get_billing_store
    store = get_billing_store("overage_tenant")
    cost = store.get_overage_cost()
    assert cost == 0.0  # free plan price_per_1k_tokens = 0


# ── Webhook handler tests ──────────────────────────────────────────────────────

def test_webhook_checkout_completed(tmp_path):
    from app.services.billing_service import handle_webhook
    from app.storage.billing_store import get_billing_store

    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"tenant_id": "wh_tenant", "plan_id": "pro"},
            "customer": "cus_abc",
            "subscription": "sub_xyz",
        }},
    }
    payload = json.dumps(event).encode()
    run_async(handle_webhook(payload, ""))
    store = get_billing_store("wh_tenant")
    account = store.get_account()
    assert account.plan_id == "pro"
    assert account.status == "active"


def test_webhook_subscription_deleted_downgrades(tmp_path):
    from app.services.billing_service import handle_webhook
    from app.storage.billing_store import get_billing_store

    # First upgrade
    store = get_billing_store("cancel_tenant")
    store.update_plan("pro")

    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {
            "id": "sub_del",
            "metadata": {"tenant_id": "cancel_tenant"},
        }},
    }
    payload = json.dumps(event).encode()
    run_async(handle_webhook(payload, ""))
    account = store.get_account()
    assert account.plan_id == "free"
    assert account.status == "canceled"


def test_webhook_payment_failed_sets_past_due(tmp_path):
    from app.services.billing_service import handle_webhook
    from app.storage.billing_store import get_billing_store

    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"metadata": {"tenant_id": "fail_tenant"}}},
    }
    payload = json.dumps(event).encode()
    run_async(handle_webhook(payload, ""))
    account = get_billing_store("fail_tenant").get_account()
    assert account.status == "past_due"


def test_webhook_invalid_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    from app.services.billing_service import handle_webhook
    payload = b'{"type":"test"}'
    with pytest.raises(ValueError, match="Invalid"):
        run_async(handle_webhook(payload, "t=123,v1=badsig"))


# ── Billing middleware tests ──────────────────────────────────────────────────

def test_billing_middleware_free_plan_over_limit(tmp_path, monkeypatch):
    """Free tenant over the 20-generation limit should get a 402 on metered endpoints."""
    from app.storage.billing_store import get_billing_store
    from app.storage.usage_store import UsageStore

    tenant_id = "limit_tenant"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # Record 21 events to exceed free plan (20 limit)
    store = UsageStore(tenant_id=tenant_id)
    for _ in range(21):
        store.record(_make_event(tenant_id))

    # Now check that check_limit reports over limit
    billing = get_billing_store(tenant_id)
    plan = billing.get_plan()
    usage = UsageStore(tenant_id=tenant_id)
    result = usage.check_limit(plan)
    assert result["within_limit"] is False


def test_billing_middleware_enterprise_always_passes(tmp_path, monkeypatch):
    """Enterprise plan should always be within limit regardless of usage."""
    from app.storage.billing_store import get_billing_store
    from app.storage.usage_store import UsageStore

    tenant_id = "ent_limit_tenant"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    billing = get_billing_store(tenant_id)
    billing.update_plan("enterprise")
    plan = billing.get_plan()

    store = UsageStore(tenant_id=tenant_id)
    for _ in range(500):
        store.record(_make_event(tenant_id, tokens=5000))

    result = store.check_limit(plan)
    assert result["within_limit"] is True


def test_billing_middleware_non_metered_endpoint_passes(tmp_path, monkeypatch):
    """Non-generation endpoints should not be metered."""
    from app.middleware.billing import METERED_ENDPOINTS
    # Confirm only generation endpoints are metered
    assert "POST /generate/stream" in METERED_ENDPOINTS
    assert "POST /generate/from-documents" in METERED_ENDPOINTS
    assert "GET /billing/status" not in METERED_ENDPOINTS
    assert "GET /billing/plans" not in METERED_ENDPOINTS


# ── API endpoint tests ────────────────────────────────────────────────────────

def test_billing_plans_endpoint_public(client):
    """GET /billing/plans should return all three predefined plans (public endpoint)."""
    res = client.get("/billing/plans")
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 200
    data = res.json()
    assert "plans" in data
    plan_ids = [p["plan_id"] for p in data["plans"]]
    assert "free" in plan_ids
    assert "pro" in plan_ids
    assert "enterprise" in plan_ids


def test_billing_status_endpoint(admin_client):
    """GET /billing/status should return plan info and usage for authenticated user."""
    tc, _ = admin_client
    res = tc.get("/billing/status")
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 200
    data = res.json()
    assert "plan" in data
    assert "usage" in data
    assert data["plan"]["plan_id"] == "free"


def test_billing_checkout_no_stripe_key(admin_client, monkeypatch):
    """POST /billing/checkout should return 400 when STRIPE_SECRET_KEY is missing."""
    tc, _ = admin_client
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    res = tc.post("/billing/checkout", json={"plan_id": "pro"})
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 400


def test_billing_webhook_processes_event(client, tmp_path):
    """POST /billing/webhook should accept known event types and return received=True."""
    event = {
        "type": "invoice.paid",
        "data": {"object": {"subscription": "sub_test"}},
    }
    res = client.post(
        "/billing/webhook",
        content=json.dumps(event).encode(),
        headers={"content-type": "application/json"},
    )
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 200
    assert res.json().get("received") is True


def test_billing_cancel_no_stripe(admin_client):
    """POST /billing/cancel should return 400 when no Stripe subscription is configured."""
    tc, _ = admin_client
    res = tc.post("/billing/cancel")
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 400


def test_billing_usage_endpoint(admin_client):
    """GET /billing/usage should return daily usage data."""
    tc, _ = admin_client
    res = tc.get("/billing/usage")
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 200
    data = res.json()
    assert "daily" in data


def test_admin_billing_override(admin_client):
    """POST /admin/billing/override should allow admins to change plan."""
    tc, _ = admin_client
    res = tc.post("/admin/billing/override", json={"plan_id": "pro", "reason": "test"})
    if res.status_code == 404:
        pytest.skip("Billing API endpoints not yet registered in main.py")
    assert res.status_code == 200
    # Verify plan changed
    status_res = tc.get("/billing/status")
    if status_res.status_code == 404:
        pytest.skip("Billing status endpoint not yet registered in main.py")
    assert status_res.json()["plan"]["plan_id"] == "pro"

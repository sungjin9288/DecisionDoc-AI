from __future__ import annotations

import ast
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.billing_store import (
    BillingStore,
    BillingStoreError,
    get_billing_store,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    """Expose lost updates when independent stores do not share a lock."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}


def _s3_backend(
    client: _MemoryS3Client | None = None,
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


def _record(tenant_id: str = "alpha") -> dict:
    return {
        "tenant_id": tenant_id,
        "plan_id": "free",
        "status": "active",
        "trial_ends_at": None,
        "current_period_start": "2026-07-01T00:00:00+00:00",
        "current_period_end": "2026-08-01T00:00:00+00:00",
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "card_last4": None,
        "card_brand": None,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }


def _json_record(**changes: object) -> str:
    record = {**_record(), **changes}
    return json.dumps(record)


@pytest.fixture(autouse=True)
def _clear_billing_state_caches() -> None:
    import app.storage.billing_store as billing_store

    billing_store._store_instances.clear()
    billing_store._billing_locks.clear()
    yield
    billing_store._store_instances.clear()
    billing_store._billing_locks.clear()


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_billing_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        BillingStore(tenant_id, data_dir=tmp_path)
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        get_billing_store(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_billing_state_is_ephemeral_and_scoped_to_data_root(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = get_billing_store("alpha", data_dir=first_root)
    same_first = get_billing_store("alpha", data_dir=first_root)
    second = get_billing_store("alpha", data_dir=second_root)

    assert first is same_first
    assert first is not second
    assert first.get_account().plan_id == "free"
    assert second.get_account().plan_id == "free"
    assert not (first_root / "tenants").exists()
    assert not (second_root / "tenants").exists()


def test_factory_cache_is_scoped_to_explicit_backend(tmp_path: Path) -> None:
    first_backend = LocalStateBackend(tmp_path)
    second_backend = LocalStateBackend(tmp_path)

    first = get_billing_store("alpha", data_dir=tmp_path, backend=first_backend)
    same_first = get_billing_store("alpha", data_dir=tmp_path, backend=first_backend)
    second = get_billing_store("alpha", data_dir=tmp_path, backend=second_backend)

    assert first is same_first
    assert first is not second


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{not-json",
        "[]",
        '{"tenant_id":"alpha","tenant_id":"other"}',
        json.dumps({key: value for key, value in _record().items() if key != "status"}),
        _json_record(unexpected="field"),
        _json_record(tenant_id="other"),
        _json_record(plan_id="unknown"),
        _json_record(status="pending"),
        _json_record(current_period_start="not-a-timestamp"),
        _json_record(
            current_period_start="2026-07-01T00:00:00",
            current_period_end="2026-08-01T00:00:00",
        ),
        _json_record(
            current_period_start="2026-07-01T00:00:00",
            current_period_end="2026-08-01T00:00:00+00:00",
        ),
        _json_record(
            current_period_start="2026-08-01T00:00:00+00:00",
            current_period_end="2026-07-01T00:00:00+00:00",
        ),
        _json_record(card_last4="12ab"),
        _json_record(stripe_customer_id=" "),
        _json_record(updated_at="2026-06-30T23:59:59+00:00"),
    ],
)
def test_untrusted_billing_state_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw: str,
) -> None:
    path = tmp_path / "tenants/alpha/billing.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = BillingStore("alpha", data_dir=tmp_path)

    operations = (
        store.get_account,
        store.get_plan,
        lambda: store.update_plan("pro"),
        lambda: store.update_stripe_info("cus_1", "sub_1", "4242", "visa"),
        lambda: store.set_status("past_due"),
        lambda: store.apply_subscription_update(
            plan_id="pro",
            status="active",
            customer_id="cus_1",
            subscription_id="sub_1",
        ),
        lambda: store.is_feature_enabled("basic_bundles"),
        store.get_overage_cost,
    )

    for operation in operations:
        with pytest.raises(BillingStoreError):
            operation()
        assert path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    [
        ("update_plan", ("unknown",), {}),
        ("update_plan", ("pro", []), {}),
        ("update_plan", ("pro", {"stripe_customer_id": ""}), {}),
        ("update_plan", ("pro", {"unknown": "cus_1"}), {}),
        ("update_stripe_info", ("cus_1", "sub_1", "12ab", "visa"), {}),
        ("set_status", ("pending",), {}),
        (
            "apply_subscription_update",
            (),
            {"plan_id": "pro", "status": "active", "customer_id": ""},
        ),
        ("is_feature_enabled", (1,), {}),
    ],
)
def test_invalid_billing_updates_are_rejected_before_writing(
    tmp_path: Path,
    method_name: str,
    args: tuple,
    kwargs: dict,
) -> None:
    store = BillingStore("alpha", data_dir=tmp_path)

    with pytest.raises(ValueError):
        getattr(store, method_name)(*args, **kwargs)

    assert not (tmp_path / "tenants").exists()


def test_independent_local_stores_preserve_concurrent_updates(tmp_path: Path) -> None:
    first = BillingStore(
        "alpha",
        data_dir=tmp_path / "first-context",
        backend=_SlowLocalBackend(tmp_path),
    )
    second = BillingStore(
        "alpha",
        data_dir=tmp_path / "second-context",
        backend=_SlowLocalBackend(tmp_path),
    )
    third = BillingStore(
        "alpha",
        data_dir=tmp_path / "third-context",
        backend=_SlowLocalBackend(tmp_path),
    )

    updates = (
        lambda: first.update_plan("pro"),
        lambda: second.update_stripe_info("cus_1", "sub_1", "4242", "visa"),
        lambda: third.set_status("past_due"),
    )
    with ThreadPoolExecutor(max_workers=len(updates)) as executor:
        futures = [executor.submit(update) for update in updates]
        for future in futures:
            future.result()

    account = BillingStore("alpha", data_dir=tmp_path).get_account()
    assert account.plan_id == "pro"
    assert account.status == "past_due"
    assert account.stripe_customer_id == "cus_1"
    assert account.stripe_subscription_id == "sub_1"
    assert account.card_last4 == "4242"
    assert account.card_brand == "visa"


def test_billing_store_round_trips_through_s3_backend(tmp_path: Path) -> None:
    backend, client = _s3_backend()
    store = BillingStore("alpha", data_dir=tmp_path, backend=backend)

    assert store.get_account().plan_id == "free"
    assert client.objects == {}

    store.apply_subscription_update(
        plan_id="pro",
        status="active",
        customer_id="cus_1",
        subscription_id="sub_1",
    )

    reloaded = BillingStore("alpha", data_dir=tmp_path, backend=backend).get_account()
    assert reloaded.plan_id == "pro"
    assert reloaded.status == "active"
    assert reloaded.stripe_customer_id == "cus_1"
    assert reloaded.stripe_subscription_id == "sub_1"
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/billing.json")
    assert json.loads(client.objects[key])["tenant_id"] == "alpha"
    assert not (tmp_path / "tenants").exists()


def test_corrupt_s3_billing_state_is_preserved(tmp_path: Path) -> None:
    backend, client = _s3_backend()
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/billing.json")
    client.objects[key] = b"{not-json"

    with pytest.raises(BillingStoreError):
        BillingStore("alpha", data_dir=tmp_path, backend=backend).update_plan("pro")

    assert client.objects[key] == b"{not-json"


def test_independent_s3_stores_preserve_concurrent_updates(tmp_path: Path) -> None:
    client = _MemoryS3Client(read_delay=0.005)
    first_backend, _ = _s3_backend(client)
    second_backend, _ = _s3_backend(client)
    third_backend, _ = _s3_backend(client)
    first = BillingStore("alpha", data_dir=tmp_path / "first", backend=first_backend)
    second = BillingStore("alpha", data_dir=tmp_path / "second", backend=second_backend)
    third = BillingStore("alpha", data_dir=tmp_path / "third", backend=third_backend)

    updates = (
        lambda: first.update_plan("pro"),
        lambda: second.update_stripe_info("cus_1", "sub_1", "4242", "visa"),
        lambda: third.set_status("past_due"),
    )
    with ThreadPoolExecutor(max_workers=len(updates)) as executor:
        futures = [executor.submit(update) for update in updates]
        for future in futures:
            future.result()

    account = BillingStore(
        "alpha",
        data_dir=tmp_path,
        backend=first_backend,
    ).get_account()
    assert account.plan_id == "pro"
    assert account.status == "past_due"
    assert account.stripe_customer_id == "cus_1"
    assert account.stripe_subscription_id == "sub_1"
    assert account.card_last4 == "4242"
    assert account.card_brand == "visa"


@pytest.mark.parametrize(
    "source_path",
    [
        Path("app/middleware/billing.py"),
        Path("app/routers/billing.py"),
        Path("app/services/billing_service.py"),
    ],
)
def test_runtime_billing_store_calls_keep_application_state_context(
    source_path: Path,
) -> None:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_billing_store"
    ]

    assert calls
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"data_dir", "backend"} <= keywords


def test_generation_usage_billing_call_keeps_generation_data_root() -> None:
    source_path = Path("app/services/generation/context_store.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_billing_store"
    ]

    assert len(calls) == 1
    assert {keyword.arg for keyword in calls[0].keywords} >= {"data_dir"}


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("JWT_SECRET_KEY", "billing-integrity-test-secret-key-32")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(*, role: str = "admin") -> dict[str, str]:
    from app.services.auth_service import create_access_token

    token = create_access_token("user-1", "system", role, "billing-user")
    return {"Authorization": f"Bearer {token}"}


def test_billing_middleware_runs_after_tenant_and_auth_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    middleware_names = [
        getattr(item.kwargs.get("dispatch"), "__name__", "")
        for item in client.app.user_middleware
    ]

    billing_index = middleware_names.index("billing_middleware")
    assert middleware_names.index("tenant_middleware") < billing_index
    assert middleware_names.index("auth_middleware") < billing_index


def test_metered_request_fails_closed_when_billing_state_is_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/billing.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/stream",
        json={"title": "Billing isolation", "goal": "Preserve billing authority"},
        headers=_headers(role="member"),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "BILLING_STATE_UNAVAILABLE"
    assert path.read_bytes() == b"{not-json"


def test_metered_request_enforces_current_tenant_usage_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.storage.usage_store import UsageEvent, UsageStore

    client = _client(tmp_path, monkeypatch)
    usage = UsageStore(tmp_path, tenant_id="system")
    for index in range(21):
        usage.record(
            UsageEvent(
                event_id=f"event-{index}",
                tenant_id="system",
                user_id="user-1",
                timestamp="2026-07-16T00:00:00+00:00",
                event_type="doc.generate",
                bundle_id="tech_decision",
                tokens_input=1,
                tokens_output=1,
                tokens_total=2,
                cost_usd=0,
                model="mock",
                request_id=f"request-{index}",
            )
        )

    response = client.post(
        "/generate/stream",
        json={"title": "Billing limit", "goal": "Enforce current usage"},
        headers=_headers(role="member"),
    )

    assert response.status_code == 402
    assert response.json()["code"] == "LIMIT_EXCEEDED"
    assert response.json()["plan"] == "free"
    assert response.json()["used"] == 21


def test_billing_api_preserves_corrupt_state_across_read_and_write_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/billing.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)
    headers = _headers()
    from app.storage.billing_store import PREDEFINED_PLANS

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_local_only")
    monkeypatch.setattr(PREDEFINED_PLANS["pro"], "stripe_price_id", "price_local_only")
    webhook = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": "system", "plan_id": "pro"},
                "customer": "cus_1",
                "subscription": "sub_1",
            }
        },
    }

    responses = (
        client.get("/billing/status", headers=headers),
        client.post(
            "/admin/billing/override",
            json={"plan_id": "pro", "reason": "integrity test"},
            headers=headers,
        ),
        client.post(
            "/billing/checkout",
            json={"plan_id": "pro"},
            headers=headers,
        ),
        client.post("/billing/webhook", json=webhook, headers=headers),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert path.read_bytes() == b"{not-json"


def test_admin_override_rejects_unknown_plan_without_creating_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/billing/override",
        json={"plan_id": "unknown", "reason": "integrity test"},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert not (tmp_path / "tenants/system/billing.json").exists()


def test_mock_webhook_lifecycle_updates_billing_state_without_stripe_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    headers = _headers()
    checkout = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": "system", "plan_id": "pro"},
                "customer": "cus_1",
                "subscription": "sub_1",
            }
        },
    }
    canceled = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"tenant_id": "system"}}},
    }

    checkout_response = client.post("/billing/webhook", json=checkout, headers=headers)
    upgraded = client.get("/billing/status", headers=headers)
    cancel_response = client.post("/billing/webhook", json=canceled, headers=headers)
    downgraded = client.get("/billing/status", headers=headers)

    assert checkout_response.status_code == 200
    assert upgraded.status_code == 200
    assert upgraded.json()["plan"] == {
        "plan_id": "pro",
        "plan_name": "프로",
        "status": "active",
    }
    assert cancel_response.status_code == 200
    assert downgraded.status_code == 200
    assert downgraded.json()["plan"] == {
        "plan_id": "free",
        "plan_name": "무료",
        "status": "canceled",
    }


def test_signed_webhook_bypasses_jwt_only_after_signature_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.billing_service import handle_webhook
    from tests.async_helper import run_async

    payload = json.dumps(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"tenant_id": "system", "plan_id": "pro"},
                    "customer": "cus_signed",
                    "subscription": "sub_signed",
                }
            },
        },
        separators=(",", ":"),
    ).encode()

    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", " ")
    with pytest.raises(ValueError, match="not configured in production"):
        run_async(handle_webhook(payload, "", data_dir=tmp_path))

    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    secret = "whsec_local_contract"
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@example.com",
            "password": "AdminPass1!",
        },
    )
    unsigned = client.post("/billing/webhook", content=payload)

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    timestamp = str(int(time.time()))
    digest = hmac.new(
        secret.encode(),
        f"{timestamp}.{payload.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    signature = f"t={timestamp},v1=rotated-secret-signature,v1={digest}"

    accepted = client.post(
        "/billing/webhook",
        content=payload,
        headers={"stripe-signature": signature},
    )
    rejected = client.post(
        "/billing/webhook",
        content=payload,
        headers={"stripe-signature": f"t={timestamp},v1=invalid"},
    )
    malformed_payload = b"[]"
    malformed_digest = hmac.new(
        secret.encode(),
        f"{timestamp}.{malformed_payload.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    malformed = client.post(
        "/billing/webhook",
        content=malformed_payload,
        headers={"stripe-signature": f"t={timestamp},v1={malformed_digest}"},
    )
    missing_metadata_payload = (
        b'{"type":"checkout.session.completed","data":{"object":{"metadata":{}}}}'
    )
    missing_metadata_digest = hmac.new(
        secret.encode(),
        f"{timestamp}.{missing_metadata_payload.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    missing_metadata = client.post(
        "/billing/webhook",
        content=missing_metadata_payload,
        headers={"stripe-signature": f"t={timestamp},v1={missing_metadata_digest}"},
    )

    assert unsigned.status_code == 401
    assert accepted.status_code == 200, accepted.text
    assert rejected.status_code == 400
    assert malformed.status_code == 400
    assert missing_metadata.status_code == 400
    account = BillingStore("system", data_dir=tmp_path).get_account()
    assert account.plan_id == "pro"
    assert account.stripe_customer_id == "cus_signed"


def test_checkout_uses_configured_price_and_subscription_metadata_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.billing_service import create_checkout_session
    from tests.async_helper import run_async

    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"url": "https://checkout.stripe.test/session"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, url: str, *, data: dict, auth: tuple[str, str]):
            captured.update({"url": url, "data": data, "auth": auth})
            return _Response()

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_local_contract")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_local_contract")
    monkeypatch.setattr(
        "app.services.billing_service.httpx.AsyncClient",
        lambda: _Client(),
    )

    url = run_async(
        create_checkout_session(
            tenant_id="system",
            plan_id="pro",
            success_url="http://testserver/billing/success",
            cancel_url="http://testserver/billing/cancel",
            data_dir=tmp_path,
        )
    )

    assert url == "https://checkout.stripe.test/session"
    assert captured["auth"] == ("sk_test_local_contract", "")
    assert captured["data"] == {
        "mode": "subscription",
        "line_items[0][price]": "price_pro_local_contract",
        "line_items[0][quantity]": "1",
        "success_url": "http://testserver/billing/success",
        "cancel_url": "http://testserver/billing/cancel",
        "metadata[tenant_id]": "system",
        "metadata[plan_id]": "pro",
        "subscription_data[metadata][tenant_id]": "system",
        "subscription_data[metadata][plan_id]": "pro",
        "customer_creation": "always",
    }

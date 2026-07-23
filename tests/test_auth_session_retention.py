from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

from fastapi.testclient import TestClient


TEST_JWT_SECRET_KEY = "test-secret-key-retention-tests-32chars"


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "ops-secret")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET_KEY)

    from app.main import create_app

    return TestClient(create_app())


def _register_and_login(client: TestClient) -> dict:
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    return client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).json()


def _auth(login: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {login['access_token']}"}


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _recheck_receipt(client: TestClient, login: dict, *, retention_days: int = 90) -> dict:
    source = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": retention_days},
    )
    assert source.status_code == 200
    response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": source.json(),
            "source_handoff_sha256": _canonical_sha256(source.json()),
        },
    )
    assert response.status_code == 200
    return response.json()


def _seed_old_sessions(client: TestClient, login: dict, monkeypatch):
    import app.storage.auth_session_store as auth_session_module
    from app.services.auth_service import verify_token
    from app.storage.auth_session_store import AuthSessionStore

    claims = verify_token(login["access_token"])
    assert claims is not None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    clock = [now - timedelta(days=100)]
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: clock[0])
    store = AuthSessionStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )

    expired = store.create(user_id=claims["sub"], credential_version=0)
    assert store.set_label(
        expired,
        user_id=claims["sub"],
        credential_version=0,
        label="private expired label",
    )
    revoked = store.create(user_id=claims["sub"], credential_version=0)
    assert store.set_label(
        revoked,
        user_id=claims["sub"],
        credential_version=0,
        label="private revoked label",
    )
    clock[0] = now - timedelta(days=80)
    assert store.revoke(revoked, user_id=claims["sub"])
    clock[0] = now
    return now, claims, expired, revoked


def test_auth_session_retention_preview_returns_redacted_read_only_summary(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    now, claims, expired, revoked = _seed_old_sessions(client, login, monkeypatch)
    prefix = "tenants/system/auth_sessions"
    backend = client.app.state.state_backend
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}

    response = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(login),
        params={"retention_days": 30},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "contract_version": "auth-session-retention-preview.v1",
        "generated_at": now.isoformat(),
        "retention_days": 30,
        "eligible_before": (now - timedelta(days=30)).isoformat(),
        "inspected_sessions": 4,
        "eligible_sessions": 2,
        "eligible_by_reason": {"expired": 1, "revoked": 1},
        "active_sessions": 2,
        "retained_inactive_sessions": 0,
        "oldest_eligible_inactive_at": (now - timedelta(days=80)).isoformat(),
        "read_only": True,
        "deletion_authorized": False,
    }
    serialized = json.dumps(response.json(), ensure_ascii=False)
    for private_value in (
        expired,
        revoked,
        claims["sub"],
        "private expired label",
        "private revoked label",
        login["access_token"],
        login["refresh_token"],
    ):
        assert private_value not in serialized
    assert {path: backend.read_text(path) for path in paths} == original

def test_auth_session_retention_preview_requires_admin_or_ops_key(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    created = client.post(
        "/admin/users",
        headers=_auth(admin),
        json={
            "username": "member",
            "display_name": "Member",
            "email": "member@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member = client.post(
        "/auth/login",
        json={"username": "member", "password": "MemberPass1!"},
    ).json()

    unauthenticated = client.get("/admin/auth-sessions/retention-preview")
    forbidden = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(member),
    )
    ops = client.get(
        "/admin/auth-sessions/retention-preview",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )

    assert unauthenticated.status_code == 401
    assert forbidden.status_code == 403
    assert ops.status_code == 200
    assert ops.json()["retention_days"] == 30
    assert ops.json()["read_only"] is True
    assert ops.json()["deletion_authorized"] is False


def test_auth_session_retention_comparison_returns_one_redacted_inspection(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    now, claims, expired, revoked = _seed_old_sessions(client, login, monkeypatch)
    prefix = "tenants/system/auth_sessions"
    backend = client.app.state.state_backend
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}

    response = client.get(
        "/admin/auth-sessions/retention-comparison",
        headers=_auth(login),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["contract_version"] == "auth-session-retention-comparison.v1"
    assert payload["generated_at"] == now.isoformat()
    assert payload["policy_days"] == [30, 90, 180, 365]
    assert payload["inspected_sessions"] == 4
    assert payload["active_sessions"] == 2
    assert [policy["eligible_sessions"] for policy in payload["policies"]] == [
        2,
        0,
        0,
        0,
    ]
    assert payload["read_only"] is True
    assert payload["deletion_authorized"] is False
    assert payload["snapshot_atomic"] is False
    assert payload["requires_recheck_before_mutation"] is True
    serialized = json.dumps(payload, ensure_ascii=False)
    for private_value in (
        expired,
        revoked,
        claims["sub"],
        "private expired label",
        "private revoked label",
        login["access_token"],
        login["refresh_token"],
    ):
        assert private_value not in serialized
    assert {path: backend.read_text(path) for path in paths} == original

def test_auth_session_retention_comparison_requires_admin_or_ops_key(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    created = client.post(
        "/admin/users",
        headers=_auth(admin),
        json={
            "username": "member-comparison",
            "display_name": "Member",
            "email": "member-comparison@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member = client.post(
        "/auth/login",
        json={"username": "member-comparison", "password": "MemberPass1!"},
    ).json()

    unauthenticated = client.get("/admin/auth-sessions/retention-comparison")
    forbidden = client.get(
        "/admin/auth-sessions/retention-comparison",
        headers=_auth(member),
    )
    ops = client.get(
        "/admin/auth-sessions/retention-comparison",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )

    assert unauthenticated.status_code == 401
    assert forbidden.status_code == 403
    assert ops.status_code == 200
    assert ops.json()["policy_days"] == [30, 90, 180, 365]


def test_auth_session_retention_preview_validates_query_and_fails_closed_on_corrupt_state(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)

    too_short = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(admin),
        params={"retention_days": 0},
    )
    too_long = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(admin),
        params={"retention_days": 3651},
    )
    corrupt_path = f"tenants/system/auth_sessions/{'f' * 32}.json"
    corrupt = '{"session_id":"duplicate","session_id":"forged"}'
    assert client.app.state.state_backend.write_text_if_absent(corrupt_path, corrupt)
    failed = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(admin),
        params={"retention_days": 30},
    )

    assert too_short.status_code == 422
    assert too_long.status_code == 422
    assert failed.status_code == 503
    assert client.app.state.state_backend.read_text(corrupt_path) == corrupt


def test_auth_session_retention_comparison_fails_closed_on_corrupt_state(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    corrupt_path = f"tenants/system/auth_sessions/{'f' * 32}.json"
    corrupt = '{"session_id":"duplicate","session_id":"forged"}'
    assert client.app.state.state_backend.write_text_if_absent(corrupt_path, corrupt)

    failed = client.get(
        "/admin/auth-sessions/retention-comparison",
        headers=_auth(admin),
    )

    assert failed.status_code == 503
    assert client.app.state.state_backend.read_text(corrupt_path) == corrupt


def test_auth_session_retention_handoff_download_is_redacted_and_hash_bound(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    now, claims, expired, revoked = _seed_old_sessions(client, login, monkeypatch)
    prefix = "tenants/system/auth_sessions"
    backend = client.app.state.state_backend
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}

    response = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": 90},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        'attachment; filename="auth-session-retention-review-handoff-90d.json"'
    )
    assert response.headers["x-decisiondoc-auth-session-retention-handoff-sha256"] == (
        hashlib.sha256(response.content).hexdigest()
    )
    handoff = response.json()
    canonical_comparison = json.dumps(
        handoff["comparison"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert handoff["contract_version"] == "auth-session-retention-review-handoff.v2"
    assert handoff["tenant_id"] == "system"
    assert handoff["selected_policy_days"] == 90
    assert handoff["comparison"]["generated_at"] == now.isoformat()
    assert handoff["comparison_sha256"] == hashlib.sha256(canonical_comparison).hexdigest()
    assert handoff["review_only"] is True
    assert handoff["policy_change_authorized"] is False
    assert handoff["deletion_authorized"] is False
    assert handoff["scheduler_authorized"] is False
    assert handoff["snapshot_atomic"] is False
    assert handoff["requires_recheck_before_mutation"] is True
    assert handoff["handoff_persisted"] is False
    serialized = response.text
    for private_value in (
        expired,
        revoked,
        claims["sub"],
        "private expired label",
        "private revoked label",
        login["access_token"],
        login["refresh_token"],
    ):
        assert private_value not in serialized
    assert {path: backend.read_text(path) for path in paths} == original


def test_auth_session_retention_handoff_requires_allowed_policy_and_healthy_state(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    created = client.post(
        "/admin/users",
        headers=_auth(admin),
        json={
            "username": "member-handoff",
            "display_name": "Member",
            "email": "member-handoff@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member = client.post(
        "/auth/login",
        json={"username": "member-handoff", "password": "MemberPass1!"},
    ).json()

    unauthorized = client.get("/admin/auth-sessions/retention-handoff")
    forbidden = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(member),
    )
    allowed = [
        client.get(
            "/admin/auth-sessions/retention-handoff",
            headers=_auth(admin),
            params={"retention_days": retention_days},
        )
        for retention_days in (30, 90, 180, 365)
    ]
    ops = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        params={"retention_days": 365},
    )
    invalid_policy = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(admin),
        params={"retention_days": 31},
    )
    corrupt_path = f"tenants/system/auth_sessions/{'f' * 32}.json"
    corrupt = '{"session_id":"duplicate","session_id":"forged"}'
    assert client.app.state.state_backend.write_text_if_absent(corrupt_path, corrupt)
    failed = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        params={"retention_days": 30},
    )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403
    assert [
        response.json()["selected_policy_days"] for response in allowed
    ] == [30, 90, 180, 365]
    assert ops.status_code == 200
    assert ops.json()["selected_policy_days"] == 365
    assert invalid_policy.status_code == 422
    assert failed.status_code == 503
    assert client.app.state.state_backend.read_text(corrupt_path) == corrupt


def test_auth_session_retention_recheck_is_hash_bound_read_only_and_tenant_scoped(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    _, claims, expired, revoked = _seed_old_sessions(client, login, monkeypatch)
    backend = client.app.state.state_backend
    prefix = "tenants/system/auth_sessions"
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}

    source_response = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": 90},
    )
    source_handoff = source_response.json()
    source_handoff_sha256 = hashlib.sha256(
        json.dumps(
            source_handoff,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": source_handoff,
            "source_handoff_sha256": source_handoff_sha256,
        },
    )

    assert source_response.status_code == 200
    assert source_handoff["contract_version"] == "auth-session-retention-review-handoff.v2"
    assert source_handoff["tenant_id"] == "system"
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        'attachment; filename="auth-session-retention-recheck-receipt-90d.json"'
    )
    assert response.headers[
        "x-decisiondoc-auth-session-retention-recheck-receipt-sha256"
    ] == hashlib.sha256(response.content).hexdigest()
    receipt = response.json()
    assert response.content == json.dumps(
        receipt,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert receipt["contract_version"] == "auth-session-retention-recheck-receipt.v1"
    assert receipt["source_handoff"] == source_handoff
    assert receipt["source_handoff_sha256"] == source_handoff_sha256
    assert receipt["aggregate_status"] == "unchanged"
    assert receipt["source_aggregate_fingerprint_sha256"] == receipt[
        "current_aggregate_fingerprint_sha256"
    ]
    assert receipt["aggregate_only"] is True
    assert receipt["review_only"] is True
    assert receipt["policy_change_authorized"] is False
    assert receipt["deletion_authorized"] is False
    assert receipt["scheduler_authorized"] is False
    assert receipt["snapshot_atomic"] is False
    assert receipt["requires_recheck_before_mutation"] is True
    assert receipt["recheck_persisted"] is False
    serialized = json.dumps(receipt, ensure_ascii=False)
    for private_value in (
        expired,
        revoked,
        claims["sub"],
        "private expired label",
        "private revoked label",
        login["access_token"],
        login["refresh_token"],
    ):
        assert private_value not in serialized
    assert {path: backend.read_text(path) for path in paths} == original

    from app.storage.auth_session_store import AuthSessionStore

    store = AuthSessionStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=backend,
    )
    store.create(user_id=claims["sub"], credential_version=0)
    changed_state = {
        path: backend.read_text(path) for path in backend.list_prefix(prefix)
    }
    changed_response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": source_handoff,
            "source_handoff_sha256": source_handoff_sha256,
        },
    )

    assert changed_response.status_code == 200
    assert changed_response.json()["aggregate_status"] == "changed"
    assert {
        path: backend.read_text(path) for path in backend.list_prefix(prefix)
    } == changed_state


def test_auth_session_retention_recheck_rejects_invalid_source_and_allows_ops_key(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    source_handoff = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(admin),
        params={"retention_days": 30},
    ).json()
    source_handoff_sha256 = hashlib.sha256(
        json.dumps(
            source_handoff,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    def canonical_sha256(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    payload = {
        "contract_version": "auth-session-retention-recheck-request.v1",
        "source_handoff": source_handoff,
        "source_handoff_sha256": source_handoff_sha256,
    }
    created = client.post(
        "/admin/users",
        headers=_auth(admin),
        json={
            "username": "member-recheck",
            "display_name": "Member",
            "email": "member-recheck@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member = client.post(
        "/auth/login",
        json={"username": "member-recheck", "password": "MemberPass1!"},
    ).json()
    legacy = dict(source_handoff)
    legacy["contract_version"] = "auth-session-retention-review-handoff.v1"
    legacy.pop("tenant_id", None)
    legacy_payload = {
        **payload,
        "source_handoff": legacy,
        "source_handoff_sha256": hashlib.sha256(
            json.dumps(
                legacy,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    foreign = {**source_handoff, "tenant_id": "other-tenant"}
    foreign_payload = {
        **payload,
        "source_handoff": foreign,
        "source_handoff_sha256": hashlib.sha256(
            json.dumps(
                foreign,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    authority_drift = {**source_handoff, "deletion_authorized": True}
    authority_drift_payload = {
        **payload,
        "source_handoff": authority_drift,
        "source_handoff_sha256": canonical_sha256(authority_drift),
    }
    nested_schema_drift = json.loads(json.dumps(source_handoff))
    nested_schema_drift["comparison"]["policies"][0]["session_ids"] = [
        "private-session"
    ]
    nested_schema_drift_payload = {
        **payload,
        "source_handoff": nested_schema_drift,
        "source_handoff_sha256": canonical_sha256(nested_schema_drift),
    }

    unauthorized = client.post("/admin/auth-sessions/retention-handoff/recheck", json=payload)
    unauthorized_malformed = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        json={"unexpected": True},
    )
    forbidden = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(member),
        json=payload,
    )
    forbidden_malformed = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(member),
        json={"unexpected": True},
    )
    malformed = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json={**payload, "unexpected": True},
    )
    hash_drift = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json={**payload, "source_handoff_sha256": "0" * 64},
    )
    legacy_response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json=legacy_payload,
    )
    foreign_response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json=foreign_payload,
    )
    authority_response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json=authority_drift_payload,
    )
    nested_schema_response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json=nested_schema_drift_payload,
    )
    ops = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        json=payload,
    )
    corrupt_path = f"tenants/system/auth_sessions/{'f' * 32}.json"
    corrupt = '{"session_id":"duplicate","session_id":"forged"}'
    assert client.app.state.state_backend.write_text_if_absent(corrupt_path, corrupt)
    corrupt_response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json=payload,
    )

    assert unauthorized.status_code == 401
    assert unauthorized_malformed.status_code == 401
    assert forbidden.status_code == 403
    assert forbidden_malformed.status_code == 403
    assert malformed.status_code == 422
    assert hash_drift.status_code == 422
    assert legacy_response.status_code == 422
    assert foreign_response.status_code == 422
    assert authority_response.status_code == 422
    assert nested_schema_response.status_code == 422
    assert ops.status_code == 200
    assert corrupt_response.status_code == 503
    assert client.app.state.state_backend.read_text(corrupt_path) == corrupt


def test_auth_session_retention_get_auth_runs_before_malformed_query_validation(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    created = client.post(
        "/admin/users",
        headers=_auth(admin),
        json={
            "username": "member-retention-query",
            "display_name": "Member",
            "email": "member-retention-query@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member = client.post(
        "/auth/login",
        json={"username": "member-retention-query", "password": "MemberPass1!"},
    ).json()

    unauthenticated_preview = client.get(
        "/admin/auth-sessions/retention-preview",
        params={"retention_days": "not-an-integer"},
    )
    unauthenticated_handoff = client.get(
        "/admin/auth-sessions/retention-handoff",
        params={"retention_days": "not-an-integer"},
    )
    forbidden_preview = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(member),
        params={"retention_days": "not-an-integer"},
    )
    forbidden_handoff = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(member),
        params={"retention_days": "not-an-integer"},
    )

    assert unauthenticated_preview.status_code == 401
    assert unauthenticated_handoff.status_code == 401
    assert forbidden_preview.status_code == 403
    assert forbidden_handoff.status_code == 403


def test_auth_session_retention_review_disposition_is_deterministic_and_read_only(
    tmp_path,
    monkeypatch,
):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    _, claims, expired, revoked = _seed_old_sessions(client, login, monkeypatch)
    backend = client.app.state.state_backend
    prefix = "tenants/system/auth_sessions"
    source_recheck_receipt = _recheck_receipt(client, login)
    source_recheck_receipt_sha256 = _canonical_sha256(source_recheck_receipt)
    original = {
        path: backend.read_text(path) for path in backend.list_prefix(prefix)
    }
    payload = {
        "contract_version": "auth-session-retention-review-disposition-request.v1",
        "source_recheck_receipt": source_recheck_receipt,
        "source_recheck_receipt_sha256": source_recheck_receipt_sha256,
        "review_disposition": "acknowledged_unchanged",
    }

    import app.routers.admin._auth_sessions as auth_session_router

    def unexpected_session_store(*args, **kwargs):
        raise AssertionError("H118 must not read authentication-session state")

    monkeypatch.setattr(
        auth_session_router,
        "get_auth_session_store",
        unexpected_session_store,
    )

    first = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(login),
        json=payload,
    )
    second = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(login),
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["x-content-type-options"] == "nosniff"
    assert first.headers["content-disposition"] == (
        'attachment; filename="auth-session-retention-review-disposition-receipt-90d.json"'
    )
    assert first.headers[
        "x-decisiondoc-auth-session-retention-review-disposition-receipt-sha256"
    ] == hashlib.sha256(first.content).hexdigest()
    receipt = first.json()
    assert set(receipt) == {
        "contract_version",
        "tenant_id",
        "source_recheck_receipt",
        "source_recheck_receipt_sha256",
        "current_handoff_sha256",
        "current_aggregate_fingerprint_sha256",
        "selected_policy_days",
        "aggregate_status",
        "review_disposition",
        "disposition_binding_sha256",
        "receipt_status",
        "review_only",
        "reviewer_identity_bound",
        "approval_granted",
        "execution_authorized",
        "policy_change_authorized",
        "deletion_authorized",
        "scheduler_authorized",
        "mass_revoke_authorized",
        "snapshot_atomic",
        "requires_recheck_before_mutation",
        "decision_receipt_persisted",
    }
    assert receipt["contract_version"] == (
        "auth-session-retention-review-disposition-receipt.v1"
    )
    assert receipt["tenant_id"] == "system"
    assert receipt["source_recheck_receipt"] == source_recheck_receipt
    assert receipt["source_recheck_receipt_sha256"] == source_recheck_receipt_sha256
    assert receipt["current_handoff_sha256"] == source_recheck_receipt[
        "current_handoff_sha256"
    ]
    assert receipt["current_aggregate_fingerprint_sha256"] == source_recheck_receipt[
        "current_aggregate_fingerprint_sha256"
    ]
    assert receipt["selected_policy_days"] == 90
    assert receipt["aggregate_status"] == "unchanged"
    assert receipt["review_disposition"] == "acknowledged_unchanged"
    assert receipt["disposition_binding_sha256"] == _canonical_sha256(
        {
            "tenant_id": "system",
            "source_recheck_receipt_sha256": source_recheck_receipt_sha256,
            "current_handoff_sha256": source_recheck_receipt[
                "current_handoff_sha256"
            ],
            "current_aggregate_fingerprint_sha256": source_recheck_receipt[
                "current_aggregate_fingerprint_sha256"
            ],
            "selected_policy_days": 90,
            "aggregate_status": "unchanged",
            "review_disposition": "acknowledged_unchanged",
        }
    )
    assert receipt["receipt_status"] == "issued"
    assert receipt["review_only"] is True
    assert receipt["reviewer_identity_bound"] is False
    assert receipt["approval_granted"] is False
    assert receipt["execution_authorized"] is False
    assert receipt["policy_change_authorized"] is False
    assert receipt["deletion_authorized"] is False
    assert receipt["scheduler_authorized"] is False
    assert receipt["mass_revoke_authorized"] is False
    assert receipt["snapshot_atomic"] is False
    assert receipt["requires_recheck_before_mutation"] is True
    assert receipt["decision_receipt_persisted"] is False
    serialized = first.text
    for private_value in (
        expired,
        revoked,
        claims["sub"],
        "private expired label",
        "private revoked label",
        login["access_token"],
        login["refresh_token"],
    ):
        assert private_value not in serialized
    assert {
        path: backend.read_text(path) for path in backend.list_prefix(prefix)
    } == original


def test_auth_session_retention_review_disposition_rejects_tampering_and_invalid_matrix(
    tmp_path,
    monkeypatch,
):
    from app.services.auth_service import verify_token
    from app.storage.auth_session_store import AuthSessionStore

    client = _make_client(tmp_path, monkeypatch)
    admin = _register_and_login(client)
    source_recheck_receipt = _recheck_receipt(client, admin)
    source_recheck_receipt_sha256 = _canonical_sha256(source_recheck_receipt)
    payload = {
        "contract_version": "auth-session-retention-review-disposition-request.v1",
        "source_recheck_receipt": source_recheck_receipt,
        "source_recheck_receipt_sha256": source_recheck_receipt_sha256,
        "review_disposition": "acknowledged_unchanged",
    }
    created = client.post(
        "/admin/users",
        headers=_auth(admin),
        json={
            "username": "member-disposition",
            "display_name": "Member",
            "email": "member-disposition@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member = client.post(
        "/auth/login",
        json={"username": "member-disposition", "password": "MemberPass1!"},
    ).json()
    nested_hash_drift = json.loads(json.dumps(source_recheck_receipt))
    nested_hash_drift["current_aggregate_fingerprint_sha256"] = "0" * 64
    foreign_tenant = json.loads(json.dumps(source_recheck_receipt))
    foreign_tenant["current_handoff"]["tenant_id"] = "other-tenant"
    authority_drift = json.loads(json.dumps(source_recheck_receipt))
    authority_drift["current_handoff"]["deletion_authorized"] = True

    unauthenticated_malformed = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        json={"unexpected": True},
    )
    forbidden_malformed = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(member),
        json={"unexpected": True},
    )
    malformed = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={**payload, "unexpected": True},
    )
    external_hash_drift = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={**payload, "source_recheck_receipt_sha256": "0" * 64},
    )
    nested_hash_response = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={
            **payload,
            "source_recheck_receipt": nested_hash_drift,
            "source_recheck_receipt_sha256": _canonical_sha256(nested_hash_drift),
        },
    )
    foreign_tenant_response = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={
            **payload,
            "source_recheck_receipt": foreign_tenant,
            "source_recheck_receipt_sha256": _canonical_sha256(foreign_tenant),
        },
    )
    authority_response = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={
            **payload,
            "source_recheck_receipt": authority_drift,
            "source_recheck_receipt_sha256": _canonical_sha256(authority_drift),
        },
    )
    invalid_unchanged_disposition = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={**payload, "review_disposition": "new_handoff_required"},
    )

    claims = verify_token(admin["access_token"])
    assert claims is not None
    store = AuthSessionStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    store.create(user_id=claims["sub"], credential_version=0)
    source_handoff = source_recheck_receipt["source_handoff"]
    changed_recheck = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(admin),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": source_handoff,
            "source_handoff_sha256": _canonical_sha256(source_handoff),
        },
    )
    assert changed_recheck.status_code == 200
    assert changed_recheck.json()["aggregate_status"] == "changed"
    changed_payload = {
        "contract_version": "auth-session-retention-review-disposition-request.v1",
        "source_recheck_receipt": changed_recheck.json(),
        "source_recheck_receipt_sha256": _canonical_sha256(changed_recheck.json()),
        "review_disposition": "acknowledged_unchanged",
    }
    invalid_changed_disposition = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json=changed_payload,
    )
    allowed_changed_disposition = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(admin),
        json={**changed_payload, "review_disposition": "new_handoff_required"},
    )

    assert unauthenticated_malformed.status_code == 401
    assert forbidden_malformed.status_code == 403
    assert malformed.status_code == 422
    assert external_hash_drift.status_code == 422
    assert nested_hash_response.status_code == 422
    assert foreign_tenant_response.status_code == 422
    assert authority_response.status_code == 422
    assert invalid_unchanged_disposition.status_code == 422
    assert invalid_changed_disposition.status_code == 422
    assert allowed_changed_disposition.status_code == 200

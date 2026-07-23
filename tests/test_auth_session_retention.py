from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

"""tests/test_auth.py — Tests for user accounts, JWT auth, and team messaging.

Coverage:
  UserStore unit     : create, duplicate, verify_password, wrong_password,
                       list, update, deactivate, change_password, weak_password
  JWT service unit   : create/verify access token, expired token, invalid token,
                       refresh token type
  Auth middleware    : public paths, current role/active state, missing token → 401,
                       viewer write restrictions, realtime query-token authority
  Login endpoint     : success returns tokens+user, wrong password, inactive user
  Register endpoint  : first user → admin, second call → 403
  Message tests      : post + get_thread, mention parsing, unread count
  Admin endpoints    : create user, list users, non-admin → 403
  Token refresh      : new access token returned
  /auth/me           : profile returned
"""
from __future__ import annotations

import queue

import pytest
from fastapi.testclient import TestClient

from tests.async_helper import run_async

TEST_JWT_SECRET_KEY = "test-secret-key-auth-tests-32chars!!"
TEST_JWT_EXPIRY_SECRET_KEY = "test-secret-key-auth-expiry-32chars!"


# ── Client factory ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET_KEY)
    from app.main import create_app

    return TestClient(create_app())


def _register_and_login(client: TestClient) -> dict:
    """Register the first admin user and return the login response dict."""
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


class _EventRequest:
    def __init__(self, *, disconnect_after: int | None = None):
        self.disconnect_after = disconnect_after
        self.checks = 0

    async def is_disconnected(self):
        self.checks += 1
        return self.disconnect_after is not None and self.checks > self.disconnect_after


class _RecordingEventBus:
    def __init__(self):
        self.unsubscribed = []

    def unsubscribe(self, tenant_id, subscription):
        self.unsubscribed.append((tenant_id, subscription))


def _collect_event_stream(events, request, subscription):
    bus = _RecordingEventBus()

    async def collect():
        return [
            chunk
            async for chunk in events._stream_events(
                request,
                token="test-access-token",
                tenant_id="tenant-a",
                bus=bus,
                subscription=subscription,
            )
        ]

    return run_async(collect()), bus


# ── UserStore unit tests ───────────────────────────────────────────────────────


def test_user_store_create(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    user = store.create("alice", "Alice", "alice@test.com", "password123", UserRole.ADMIN)
    assert user.user_id
    assert user.username == "alice"
    assert user.role == UserRole.ADMIN
    assert user.is_active is True
    assert user.password_hash != "password123"  # bcrypt-hashed


def test_user_store_duplicate_username_raises(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    store.create("bob", "Bob", "bob@test.com", "password123", UserRole.MEMBER)
    with pytest.raises(ValueError, match="이미 존재"):
        store.create("bob", "Bob2", "bob2@test.com", "password123", UserRole.MEMBER)


def test_user_store_verify_password(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    user = store.create("carol", "Carol", "carol@test.com", "SecurePass1!", UserRole.MEMBER)
    assert store.verify_password(user.user_id, "SecurePass1!") is True
    assert store.verify_password(user.user_id, "WrongPass!") is False


def test_user_store_wrong_password_returns_false(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    user = store.create("dave", "Dave", "dave@test.com", "password123", UserRole.MEMBER)
    assert store.verify_password(user.user_id, "COMPLETELY_WRONG") is False


def test_user_store_lists_only_its_tenant(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    tenant_a = UserStore(tmp_path / "tenant_a")
    tenant_b = UserStore(tmp_path / "tenant_b")
    tenant_a.create("u1", "U1", "u1@test.com", "password123", UserRole.MEMBER)
    tenant_a.create("u2", "U2", "u2@test.com", "password123", UserRole.ADMIN)
    tenant_b.create("u3", "U3", "u3@test.com", "password123", UserRole.MEMBER)

    users_a = tenant_a.list_users()
    assert len(users_a) == 2

    users_b = tenant_b.list_users()
    assert len(users_b) == 1


def test_user_store_update(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    user = store.create("eve", "Eve", "eve@test.com", "password123", UserRole.MEMBER)
    updated = store.update(user.user_id, display_name="Eveline", email="eveline@test.com")
    assert updated.display_name == "Eveline"
    assert updated.email == "eveline@test.com"


def test_user_store_deactivate(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    user = store.create("frank", "Frank", "frank@test.com", "password123", UserRole.MEMBER)
    store.deactivate(user.user_id)
    found = store.get_by_id(user.user_id)
    assert found is not None
    assert found.is_active is False


def test_user_store_change_password(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    user = store.create("grace", "Grace", "grace@test.com", "OldPass123!", UserRole.MEMBER)
    assert user.credential_version == 0
    result = store.change_password(user.user_id, "OldPass123!", "NewPass456!")
    assert result is True
    assert store.verify_password(user.user_id, "NewPass456!") is True
    assert store.verify_password(user.user_id, "OldPass123!") is False
    changed_user = store.get_by_id(user.user_id)
    assert changed_user is not None
    assert changed_user.credential_version == 1


def test_user_store_password_too_short_raises(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path / "t1")
    with pytest.raises(ValueError):
        store.create("helen", "Helen", "h@test.com", "short", UserRole.MEMBER)


# ── JWT service unit tests ─────────────────────────────────────────────────────


def test_jwt_create_and_verify_access_token():
    from app.services.auth_service import create_access_token, verify_token

    token = create_access_token("uid-1", "t1", "admin", "alice")
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "uid-1"
    assert payload["tenant_id"] == "t1"
    assert payload["role"] == "admin"
    assert payload["username"] == "alice"
    assert payload["type"] == "access"


def test_jwt_expired_token_returns_none(monkeypatch):
    import jwt

    from app.config import get_jwt_secret_key
    from app.services.auth_service import ALGORITHM, verify_token
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_EXPIRY_SECRET_KEY)
    expired_payload = {
        "sub": "uid-1",
        "tenant_id": "t1",
        "role": "admin",
        "username": "alice",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
    }
    token = jwt.encode(expired_payload, get_jwt_secret_key(), algorithm=ALGORITHM)
    assert verify_token(token) is None


def test_jwt_invalid_token_returns_none():
    from app.services.auth_service import verify_token

    assert verify_token("not.a.valid.token") is None
    assert verify_token("") is None
    assert verify_token("totally-garbage") is None


def test_jwt_refresh_token_type():
    from app.services.auth_service import create_refresh_token, verify_token

    token = create_refresh_token("uid-2", "t1")
    payload = verify_token(token)
    assert payload is not None
    assert payload["type"] == "refresh"
    assert payload["sub"] == "uid-2"
    assert payload["tenant_id"] == "t1"
    assert "role" not in payload  # refresh tokens do not carry role


# ── Auth middleware tests ──────────────────────────────────────────────────────


def test_health_is_public_even_when_users_exist(tmp_path, monkeypatch):
    """/health is always accessible without auth."""
    client = _make_client(tmp_path, monkeypatch)
    # Register a user so the tenant has users (auth enforcement kicks in)
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    res = client.get("/health")
    assert res.status_code == 200


def test_auth_login_endpoint_is_public(tmp_path, monkeypatch):
    """/auth/login does not require a token — invalid creds returns 401 (not unauth 401)."""
    client = _make_client(tmp_path, monkeypatch)
    # Register so the tenant has users
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    # Login with wrong creds should still reach the handler (not blocked by middleware)
    res = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert res.status_code == 401  # credential error, not middleware block


def test_events_endpoint_is_public_even_when_users_exist(tmp_path, monkeypatch):
    """/events must stay public because the EventSource client authenticates via query token."""
    from app.middleware.auth import PUBLIC_PATHS

    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )

    assert "/events" in PUBLIC_PATHS


def test_events_endpoint_rejects_missing_and_invalid_query_tokens(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    missing = client.get("/events")
    invalid = client.get("/events?token=invalid")

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.headers["www-authenticate"] == "Bearer"


def test_events_query_token_requires_access_scope_and_valid_tenant(monkeypatch):
    from fastapi import HTTPException

    from app.routers import events
    from app.services.auth_service import create_access_token, create_refresh_token

    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-events-32chars!")
    access_token = create_access_token(
        user_id="user-a",
        tenant_id="tenant-a",
        role="viewer",
        username="user-a",
    )
    refresh_token = create_refresh_token(user_id="user-a", tenant_id="tenant-a")

    assert events._resolve_event_tenant_id(access_token) == "tenant-a"
    with pytest.raises(HTTPException) as refresh_error:
        events._resolve_event_tenant_id(refresh_token)
    assert refresh_error.value.status_code == 401

    monkeypatch.setattr(events, "verify_token", lambda token: {"type": "access"})
    with pytest.raises(HTTPException) as missing_tenant_error:
        events._resolve_event_tenant_id("signed-without-tenant")
    assert missing_tenant_error.value.status_code == 401


def test_events_reject_existing_access_token_after_user_deactivation(
    tmp_path,
    monkeypatch,
):
    from fastapi import HTTPException

    from app.routers import events
    from app.storage.user_store import get_user_store

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    token = login["access_token"]
    current_user = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert events._resolve_event_tenant_id(token, data_dir=tmp_path) == "system"

    get_user_store("system", data_dir=tmp_path).update(
        current_user["user_id"],
        is_active=False,
    )

    with pytest.raises(HTTPException) as inactive_error:
        events._resolve_event_tenant_id(token, data_dir=tmp_path)
    assert inactive_error.value.status_code == 401


def test_open_events_stream_closes_after_access_authority_is_revoked(monkeypatch):
    from app.routers import events

    def reject_access(*args, **kwargs):
        raise events._event_auth_error()

    monkeypatch.setattr(events, "_AUTH_RECHECK_INTERVAL", 0.0)
    monkeypatch.setattr(events, "_resolve_event_tenant_id", reject_access)
    subscription = queue.SimpleQueue()
    subscription.put_nowait(
        {
            "event_type": "notification",
            "data": {"private_message": "must-not-be-delivered"},
        }
    )
    chunks, bus = _collect_event_stream(events, _EventRequest(), subscription)

    assert chunks == [
        'event: auth_revoked\ndata: {"reason":"access_invalidated","refresh_allowed":true}\n\n'
    ]
    assert bus.unsubscribed == [("tenant-a", subscription)]


def test_open_events_stream_fails_closed_when_auth_authority_is_unavailable(monkeypatch):
    from fastapi import HTTPException

    from app.routers import events

    def fail_access_read(*args, **kwargs):
        raise HTTPException(status_code=503, detail="auth unavailable")

    monkeypatch.setattr(events, "_AUTH_RECHECK_INTERVAL", 0.0)
    monkeypatch.setattr(events, "_resolve_event_tenant_id", fail_access_read)
    subscription = queue.SimpleQueue()
    subscription.put_nowait(
        {
            "event_type": "message_posted",
            "data": {"private_message": "must-not-be-delivered"},
        }
    )
    chunks, bus = _collect_event_stream(events, _EventRequest(), subscription)

    assert chunks == [
        'event: auth_unavailable\ndata: {"reason":"authority_unavailable","retryable":true}\n\n'
    ]
    assert bus.unsubscribed == [("tenant-a", subscription)]


def test_open_events_stream_keeps_delivering_for_current_access(monkeypatch):
    from app.routers import events

    monkeypatch.setattr(events, "_AUTH_RECHECK_INTERVAL", 0.0)
    monkeypatch.setattr(
        events,
        "_resolve_event_tenant_id",
        lambda *args, **kwargs: "tenant-a",
    )
    subscription = queue.SimpleQueue()
    subscription.put_nowait(
        {
            "event_type": "notification",
            "data": {"notification_id": "notification-1"},
        }
    )
    chunks, bus = _collect_event_stream(
        events,
        _EventRequest(disconnect_after=1),
        subscription,
    )

    assert chunks == [
        'event: notification\ndata: {"notification_id": "notification-1"}\n\n'
    ]
    assert bus.unsubscribed == [("tenant-a", subscription)]


def test_missing_token_returns_401_when_users_exist(tmp_path, monkeypatch):
    """After users are registered, requests without JWT are rejected."""
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    res = client.get("/auth/me")  # no Authorization header
    assert res.status_code == 401


def test_viewer_blocked_on_write_endpoint(tmp_path, monkeypatch):
    """Viewer role is blocked from write (POST/PUT/PATCH/DELETE) endpoints."""
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    # Create a viewer user
    client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "viewer1",
            "display_name": "Viewer",
            "email": "v@test.com",
            "password": "ViewerPass1!",
            "role": "viewer",
        },
    )
    viewer_login = client.post(
        "/auth/login", json={"username": "viewer1", "password": "ViewerPass1!"}
    ).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_login['access_token']}"}

    # Viewer cannot POST to /feedback (a write endpoint not in the allowlist)
    res = client.post(
        "/feedback",
        headers=viewer_headers,
        json={"bundle_id": "x", "bundle_type": "tech_decision", "rating": 5},
    )
    assert res.status_code == 403


def test_viewer_allowed_on_get_endpoints(tmp_path, monkeypatch):
    """Viewer role can call read (GET) endpoints."""
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    # Create a viewer
    client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "viewer2",
            "display_name": "Viewer2",
            "email": "v2@test.com",
            "password": "ViewerPass2!",
            "role": "viewer",
        },
    )
    viewer_login = client.post(
        "/auth/login", json={"username": "viewer2", "password": "ViewerPass2!"}
    ).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_login['access_token']}"}

    res = client.get("/auth/me", headers=viewer_headers)
    assert res.status_code == 200


def test_viewer_can_logout_its_current_session(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
    client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "viewer_logout",
            "display_name": "Viewer Logout",
            "email": "viewer-logout@test.com",
            "password": "ViewerPass2!",
            "role": "viewer",
        },
    )
    viewer_login = client.post(
        "/auth/login",
        json={"username": "viewer_logout", "password": "ViewerPass2!"},
    ).json()

    response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {viewer_login['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["session_revoked"] is True


def test_role_change_applies_to_existing_access_token(tmp_path, monkeypatch):
    """Persisted role changes must take effect before an access token expires."""
    from app.storage.user_store import get_user_store

    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
    current_user = client.get("/auth/me", headers=admin_headers).json()

    get_user_store("system", data_dir=tmp_path).update(
        current_user["user_id"],
        role="viewer",
    )

    response = client.get("/admin/users", headers=admin_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "관리자 권한이 필요합니다."


def test_inactive_user_cannot_reuse_existing_access_token(tmp_path, monkeypatch):
    """Deactivation must revoke an already-issued access token immediately."""
    from app.storage.user_store import get_user_store

    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
    current_user = client.get("/auth/me", headers=admin_headers).json()

    get_user_store("system", data_dir=tmp_path).update(
        current_user["user_id"],
        is_active=False,
    )

    response = client.get("/auth/me", headers=admin_headers)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_auth_routes_keep_using_the_app_selected_user_store(tmp_path, monkeypatch):
    """Later environment drift must not split auth routes from middleware state."""
    from app.services.auth_service import verify_token
    from app.storage.auth_session_store import get_auth_session_store
    from app.storage.user_store import get_user_store

    client = _make_client(tmp_path, monkeypatch)
    foreign_data_dir = tmp_path / "foreign-data"
    monkeypatch.setenv("DATA_DIR", str(foreign_data_dir))

    registered = client.post(
        "/auth/register",
        json={
            "username": "selected-store-admin",
            "display_name": "Selected Store Admin",
            "email": "selected-store-admin@test.com",
            "password": "AdminPass1!",
        },
    )
    assert registered.status_code == 200

    app_user = get_user_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    ).get_by_username("selected-store-admin")
    foreign_user = get_user_store(
        "system",
        data_dir=foreign_data_dir,
    ).get_by_username("selected-store-admin")

    assert app_user is not None
    assert foreign_user is None

    login = client.post(
        "/auth/login",
        json={
            "username": "selected-store-admin",
            "password": "AdminPass1!",
        },
    )
    assert login.status_code == 200
    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["user_id"] == app_user.user_id
    claims = verify_token(login.json()["access_token"])
    assert claims is not None
    assert get_auth_session_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    ).is_current(
        claims["session_id"],
        user_id=claims["sub"],
        credential_version=claims["credential_version"],
    )
    assert get_auth_session_store(
        "system",
        data_dir=foreign_data_dir,
    ).is_current(
        claims["session_id"],
        user_id=claims["sub"],
        credential_version=claims["credential_version"],
    ) is False


# ── Login endpoint tests ───────────────────────────────────────────────────────


def test_login_success_returns_tokens_and_user(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@test.com",
            "password": "AlicePass1!",
        },
    )
    res = client.post("/auth/login", json={"username": "alice", "password": "AlicePass1!"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["username"] == "alice"
    assert data["user"]["role"] == "admin"  # first registered user is always admin
    assert data["user"]["job_title"] == ""
    assert data["user"]["assigned_ai_profiles"] == ["proposal_bd", "delivery_pm", "executive"]
    assert [profile["key"] for profile in data["user"]["available_ai_profiles"]] == [
        "proposal_bd",
        "delivery_pm",
        "executive",
    ]


def test_login_tokens_share_one_persisted_auth_session(tmp_path, monkeypatch):
    from app.services.auth_service import verify_token
    from app.storage.auth_session_store import AuthSessionStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    access_claims = verify_token(login["access_token"])
    refresh_claims = verify_token(login["refresh_token"])

    assert access_claims is not None
    assert refresh_claims is not None
    assert access_claims["session_id"] == refresh_claims["session_id"]

    store = AuthSessionStore(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )
    assert store.is_current(
        access_claims["session_id"],
        user_id=access_claims["sub"],
        credential_version=access_claims["credential_version"],
    )


def test_login_wrong_password_returns_401(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "bob",
            "display_name": "Bob",
            "email": "bob@test.com",
            "password": "BobPass123!",
        },
    )
    res = client.post("/auth/login", json={"username": "bob", "password": "WRONG"})
    assert res.status_code == 401


def test_login_inactive_user_returns_401(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    # Create a member user
    client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "inactive_user",
            "display_name": "Inactive",
            "email": "inactive@test.com",
            "password": "InactivePass1!",
            "role": "member",
        },
    )
    # Fetch user_id and deactivate
    users = client.get("/admin/users", headers=admin_headers).json()["users"]
    inactive = next(u for u in users if u["username"] == "inactive_user")
    client.patch(
        f"/admin/users/{inactive['user_id']}",
        headers=admin_headers,
        json={"is_active": False},
    )

    res = client.post(
        "/auth/login", json={"username": "inactive_user", "password": "InactivePass1!"}
    )
    assert res.status_code == 401


# ── Register endpoint tests ────────────────────────────────────────────────────


def test_register_first_user_becomes_admin(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    res = client.post(
        "/auth/register",
        json={
            "username": "firstuser",
            "display_name": "First",
            "email": "first@test.com",
            "password": "FirstPass1!",
        },
    )
    assert res.status_code == 200
    assert "access_token" in res.json()

    # Confirm the user has admin role
    login = client.post(
        "/auth/login", json={"username": "firstuser", "password": "FirstPass1!"}
    ).json()
    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
    ).json()
    assert me["role"] == "admin"


def test_register_second_call_returns_403(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    res = client.post(
        "/auth/register",
        json={
            "username": "other",
            "display_name": "Other",
            "email": "other@test.com",
            "password": "OtherPass1!",
        },
    )
    assert res.status_code == 403


# ── Token refresh tests ────────────────────────────────────────────────────────


def test_refresh_token_returns_new_access_token(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    client.post(
        "/auth/register",
        json={
            "username": "tokenuser",
            "display_name": "Token",
            "email": "t@test.com",
            "password": "TokenPass1!",
        },
    )
    login = client.post(
        "/auth/login", json={"username": "tokenuser", "password": "TokenPass1!"}
    ).json()
    res = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_logout_revokes_only_the_authenticated_session(tmp_path, monkeypatch):
    from app.services.auth_service import verify_token

    client = _make_client(tmp_path, monkeypatch)
    first = _register_and_login(client)
    second = client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).json()

    first_claims = verify_token(first["access_token"])
    second_claims = verify_token(second["access_token"])
    assert first_claims is not None
    assert second_claims is not None
    assert first_claims["session_id"] != second_claims["session_id"]

    logged_out = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )

    first_access = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    first_refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    second_access = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    second_refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": second["refresh_token"]},
    )

    assert logged_out.status_code == 200
    assert logged_out.json() == {
        "message": "현재 로그인 세션이 종료되었습니다.",
        "session_revoked": True,
    }
    assert first_access.status_code == 401
    assert first_refresh.status_code == 401
    assert second_access.status_code == 200
    assert second_refresh.status_code == 200


def test_logout_revokes_realtime_event_authority(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from app.routers import events

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    assert events._resolve_event_tenant_id(
        login["access_token"],
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    ) == "system"

    logged_out = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert logged_out.status_code == 200

    with pytest.raises(HTTPException) as revoked:
        events._resolve_event_tenant_id(
            login["access_token"],
            data_dir=tmp_path,
            backend=client.app.state.state_backend,
        )
    assert revoked.value.status_code == 401


def test_corrupt_auth_session_state_fails_closed_without_rewrite(
    tmp_path,
    monkeypatch,
):
    from fastapi import HTTPException

    from app.routers import events
    from app.services.auth_service import verify_token

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    claims = verify_token(login["access_token"])
    assert claims is not None
    session_path = (
        tmp_path
        / "tenants"
        / "system"
        / "auth_sessions"
        / f"{claims['session_id']}.json"
    )
    corrupt = b'{"contract_version":"auth-session.v1","session_id":"duplicate","session_id":"forged"}'
    session_path.write_bytes(corrupt)

    access = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    with pytest.raises(HTTPException) as event_access:
        events._resolve_event_tenant_id(
            login["access_token"],
            data_dir=tmp_path,
            backend=client.app.state.state_backend,
        )

    assert access.status_code == 503
    assert access.json()["code"] == "AUTH_UNAVAILABLE"
    assert refresh.status_code == 503
    assert event_access.value.status_code == 503
    assert session_path.read_bytes() == corrupt


def test_sessionless_legacy_token_remains_valid_but_cannot_claim_logout(
    tmp_path,
    monkeypatch,
):
    from app.services.auth_service import create_access_token, verify_token

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    claims = verify_token(login["access_token"])
    assert claims is not None
    legacy_token = create_access_token(
        claims["sub"],
        claims["tenant_id"],
        claims["role"],
        claims["username"],
        credential_version=claims["credential_version"],
    )

    before = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {legacy_token}"},
    )
    logout_response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {legacy_token}"},
    )
    after = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {legacy_token}"},
    )

    assert before.status_code == 200
    assert logout_response.status_code == 409
    assert "기존 로그인 세션" in logout_response.json()["detail"]
    assert after.status_code == 200


def test_invalid_refresh_token_returns_401(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    # Register so auth is enforced
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    res = client.post("/auth/refresh", json={"refresh_token": "not-a-valid-token"})
    assert res.status_code == 401


def test_password_change_rotates_credentials_and_revokes_existing_tokens(
    tmp_path,
    monkeypatch,
):
    from app.services.auth_service import verify_token

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    old_access_token = login["access_token"]
    old_refresh_token = login["refresh_token"]

    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {old_access_token}"},
        json={
            "old_password": "AdminPass1!",
            "new_password": "RotatedPass2!",
        },
    )

    assert changed.status_code == 200
    changed_data = changed.json()
    new_access_token = changed_data["access_token"]
    new_refresh_token = changed_data["refresh_token"]
    assert new_access_token != old_access_token
    assert new_refresh_token != old_refresh_token
    assert verify_token(new_access_token)["credential_version"] == 1
    assert verify_token(new_refresh_token)["credential_version"] == 1

    old_access = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    old_refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    new_access = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    new_refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )

    assert old_access.status_code == 401
    assert old_refresh.status_code == 401
    assert new_access.status_code == 200
    assert new_refresh.status_code == 200
    assert verify_token(new_refresh.json()["access_token"])["credential_version"] == 1
    assert client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).status_code == 401
    rotated_login = client.post(
        "/auth/login",
        json={"username": "admin", "password": "RotatedPass2!"},
    )
    assert rotated_login.status_code == 200
    assert verify_token(rotated_login.json()["access_token"])["credential_version"] == 1
    assert verify_token(rotated_login.json()["refresh_token"])["credential_version"] == 1


@pytest.mark.parametrize(
    ("token_type", "credential_version"),
    [
        ("access", True),
        ("access", "0"),
        ("refresh", -1),
    ],
)
def test_signed_token_with_invalid_credential_version_is_rejected(
    tmp_path,
    monkeypatch,
    token_type,
    credential_version,
):
    import jwt

    from app.config import get_jwt_secret_key
    from app.services.auth_service import ALGORITHM, verify_token

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    user_id = verify_token(login["access_token"])["sub"]
    payload = {
        "sub": user_id,
        "tenant_id": "system",
        "credential_version": credential_version,
        "type": token_type,
    }
    if token_type == "access":
        payload.update({"role": "admin", "username": "admin"})
    token = jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)

    if token_type == "access":
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    else:
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": token},
        )

    assert response.status_code == 401


@pytest.mark.parametrize("token_type", ["access", "refresh"])
def test_signed_token_with_invalid_session_identity_is_rejected(
    tmp_path,
    monkeypatch,
    token_type,
):
    import jwt

    from app.config import get_jwt_secret_key
    from app.services.auth_service import ALGORITHM, verify_token

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    current = verify_token(login["access_token"])
    assert current is not None
    payload = {
        "sub": current["sub"],
        "tenant_id": current["tenant_id"],
        "credential_version": current["credential_version"],
        "session_id": "not-a-canonical-session-id",
        "type": token_type,
    }
    if token_type == "access":
        payload.update({"role": current["role"], "username": current["username"]})
    token = jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)

    if token_type == "access":
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    else:
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": token},
        )

    assert response.status_code == 401


def test_persisted_session_is_checked_before_fresh_install_compatibility(tmp_path):
    from app.services.auth_service import resolve_persisted_user
    from app.storage.auth_session_store import AuthSessionStore

    store = AuthSessionStore("system", data_dir=tmp_path)
    session_id = store.create(user_id="removed-user", credential_version=0)
    token_user = {
        "sub": "removed-user",
        "username": "removed-user",
        "role": "admin",
        "tenant_id": "system",
        "credential_version": 0,
        "session_id": session_id,
        "type": "access",
    }

    current, users_exist = resolve_persisted_user(token_user, data_dir=tmp_path)
    assert current == token_user
    assert users_exist is False

    assert store.revoke(session_id, user_id="removed-user") is True
    revoked, users_exist = resolve_persisted_user(token_user, data_dir=tmp_path)
    assert revoked is None
    assert users_exist is False


# ── /auth/me tests ─────────────────────────────────────────────────────────────


def test_auth_me_returns_profile(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"
    assert "email" in data
    assert "avatar_color" in data
    assert data["job_title"] == ""
    assert [profile["key"] for profile in data["available_ai_profiles"]] == [
        "proposal_bd",
        "delivery_pm",
        "executive",
    ]


def test_auth_me_patch_updates_display_name_and_email(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    res = client.patch(
        "/auth/me",
        headers=headers,
        json={"display_name": "안성진 관리자", "email": "sungjin-admin@test.com"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["display_name"] == "안성진 관리자"
    assert data["email"] == "sungjin-admin@test.com"

    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["display_name"] == "안성진 관리자"
    assert me_res.json()["email"] == "sungjin-admin@test.com"


# ── Admin endpoint tests ───────────────────────────────────────────────────────


def test_admin_create_user(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    res = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": "newmember",
            "display_name": "New Member",
            "email": "member@test.com",
            "password": "MemberPass1!",
            "role": "member",
            "job_title": "PM",
            "assigned_ai_profiles": ["delivery_pm"],
        },
    )
    assert res.status_code == 200
    assert "user_id" in res.json()
    users = client.get("/admin/users", headers=headers).json()["users"]
    created = next(user for user in users if user["username"] == "newmember")
    assert created["job_title"] == "PM"
    assert created["assigned_ai_profiles"] == ["delivery_pm"]


def test_member_login_only_receives_assigned_ai_profiles_and_bundle_scope(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    create_res = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "pmmember",
            "display_name": "PM Member",
            "email": "pm@test.com",
            "password": "MemberPass1!",
            "role": "member",
            "job_title": "프로젝트 매니저",
            "assigned_ai_profiles": ["delivery_pm"],
        },
    )
    assert create_res.status_code == 200

    member_login = client.post(
        "/auth/login", json={"username": "pmmember", "password": "MemberPass1!"}
    )
    assert member_login.status_code == 200
    member_data = member_login.json()
    assert member_data["user"]["job_title"] == "프로젝트 매니저"
    assert member_data["user"]["assigned_ai_profiles"] == ["delivery_pm"]
    assert [profile["key"] for profile in member_data["user"]["available_ai_profiles"]] == [
        "delivery_pm"
    ]

    member_headers = {"Authorization": f"Bearer {member_data['access_token']}"}
    me_res = client.get("/auth/me", headers=member_headers)
    assert me_res.status_code == 200
    assert me_res.json()["assigned_ai_profiles"] == ["delivery_pm"]

    bundles = client.get("/bundles", headers=member_headers).json()
    bundle_ids = {bundle["id"] for bundle in bundles}
    assert "performance_plan_kr" in bundle_ids
    assert "tech_decision" not in bundle_ids
    assert "proposal_kr" not in bundle_ids


def test_admin_list_users_returns_all_tenant_users(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    res = client.get("/admin/users", headers=headers)
    assert res.status_code == 200
    users = res.json()["users"]
    assert len(users) >= 1
    assert any(u["username"] == "admin" for u in users)


def test_non_admin_cannot_list_users(tmp_path, monkeypatch):
    """Member role is blocked from admin-only endpoints."""
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    # Create a member user
    client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "member1",
            "display_name": "Member",
            "email": "m@test.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    member_login = client.post(
        "/auth/login", json={"username": "member1", "password": "MemberPass1!"}
    ).json()
    member_headers = {"Authorization": f"Bearer {member_login['access_token']}"}

    res = client.get("/admin/users", headers=member_headers)
    assert res.status_code == 403


# ── Message tests ─────────────────────────────────────────────────────────────


def test_message_post_and_get_thread(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    res = client.post("/messages", headers=headers, json={"content": "Hello team!"})
    assert res.status_code == 200
    msg = res.json()["message"]
    assert msg["content"] == "Hello team!"
    assert msg["is_deleted"] is False

    thread_res = client.get("/messages", headers=headers)
    assert thread_res.status_code == 200
    messages = thread_res.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello team!"


def test_message_mention_parsing(tmp_path):
    """@mention strings are parsed from content into the mentions list."""
    from app.storage.message_store import _parse_mention_names

    # Use content without trailing punctuation so the regex captures clean names
    names = _parse_mention_names("Hello @bob and @carol please review")
    assert "bob" in names
    assert "carol" in names
    assert len(names) == 2


def test_message_no_mentions_when_content_is_plain(tmp_path):
    from app.storage.message_store import _parse_mention_names

    names = _parse_mention_names("Hello team! No mentions here.")
    assert names == []


def test_message_unread_count_endpoint(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    admin_login = _register_and_login(client)
    headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    # Post a message without any @mention
    client.post("/messages", headers=headers, json={"content": "No mentions here"})

    res = client.get("/messages/unread-count", headers=headers)
    assert res.status_code == 200
    assert "unread_count" in res.json()
    assert isinstance(res.json()["unread_count"], int)

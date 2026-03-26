"""tests/test_auth.py — Tests for user accounts, JWT auth, and team messaging.

Coverage (31 tests):
  UserStore unit     : create, duplicate, verify_password, wrong_password,
                       list, update, deactivate, change_password, weak_password
  JWT service unit   : create/verify access token, expired token, invalid token,
                       refresh token type
  Auth middleware    : public paths, missing token → 401, viewer POST → 403,
                       viewer GET allowed
  Login endpoint     : success returns tokens+user, wrong password, inactive user
  Register endpoint  : first user → admin, second call → 403
  Message tests      : post + get_thread, mention parsing, unread count
  Admin endpoints    : create user, list users, non-admin → 403
  Token refresh      : new access token returned
  /auth/me           : profile returned
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Client factory ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-auth-tests")
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


# ── UserStore unit tests ───────────────────────────────────────────────────────


def test_user_store_create(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    user = store.create("t1", "alice", "Alice", "alice@test.com", "password123", UserRole.ADMIN)
    assert user.user_id
    assert user.username == "alice"
    assert user.role == UserRole.ADMIN
    assert user.is_active is True
    assert user.password_hash != "password123"  # bcrypt-hashed


def test_user_store_duplicate_username_raises(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    store.create("t1", "bob", "Bob", "bob@test.com", "password123", UserRole.MEMBER)
    with pytest.raises(ValueError, match="이미 존재"):
        store.create("t1", "bob", "Bob2", "bob2@test.com", "password123", UserRole.MEMBER)


def test_user_store_verify_password(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    user = store.create("t1", "carol", "Carol", "carol@test.com", "SecurePass1!", UserRole.MEMBER)
    assert store.verify_password(user.user_id, "SecurePass1!") is True
    assert store.verify_password(user.user_id, "WrongPass!") is False


def test_user_store_wrong_password_returns_false(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    user = store.create("t1", "dave", "Dave", "dave@test.com", "password123", UserRole.MEMBER)
    assert store.verify_password(user.user_id, "COMPLETELY_WRONG") is False


def test_user_store_list_by_tenant(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    store.create("tenant_a", "u1", "U1", "u1@test.com", "password123", UserRole.MEMBER)
    store.create("tenant_a", "u2", "U2", "u2@test.com", "password123", UserRole.ADMIN)
    store.create("tenant_b", "u3", "U3", "u3@test.com", "password123", UserRole.MEMBER)

    users_a = store.list_by_tenant("tenant_a")
    assert len(users_a) == 2

    users_b = store.list_by_tenant("tenant_b")
    assert len(users_b) == 1


def test_user_store_update(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    user = store.create("t1", "eve", "Eve", "eve@test.com", "password123", UserRole.MEMBER)
    updated = store.update(user.user_id, display_name="Eveline", email="eveline@test.com")
    assert updated.display_name == "Eveline"
    assert updated.email == "eveline@test.com"


def test_user_store_deactivate(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    user = store.create("t1", "frank", "Frank", "frank@test.com", "password123", UserRole.MEMBER)
    store.deactivate(user.user_id)
    found = store.get_by_id(user.user_id)
    assert found is not None
    assert found.is_active is False


def test_user_store_change_password(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    user = store.create("t1", "grace", "Grace", "grace@test.com", "OldPass123!", UserRole.MEMBER)
    result = store.change_password(user.user_id, "OldPass123!", "NewPass456!")
    assert result is True
    assert store.verify_password(user.user_id, "NewPass456!") is True
    assert store.verify_password(user.user_id, "OldPass123!") is False


def test_user_store_password_too_short_raises(tmp_path):
    from app.storage.user_store import UserRole, UserStore

    store = UserStore(tmp_path)
    with pytest.raises(ValueError):
        store.create("t1", "helen", "Helen", "h@test.com", "short", UserRole.MEMBER)


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

    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-expiry")
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
        },
    )
    assert res.status_code == 200
    assert "user_id" in res.json()


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

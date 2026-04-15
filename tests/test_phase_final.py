"""tests/test_phase_final.py — Final improvement tests.

Coverage:
  BaseJsonStore    : atomic write, corrupt file graceful
  InviteStore      : create/get/mark_used lifecycle
  Invite endpoints : admin-only, 404 for unknown
  G2B search       : endpoint shape
  Share expiry     : expired link deactivated
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-phase-final-32chars!")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


# ── BaseJsonStore ─────────────────────────────────────────────────────────────

def test_base_store_atomic_write(tmp_path):
    from app.storage.base import BaseJsonStore
    from pathlib import Path

    class TestStore(BaseJsonStore):
        def __init__(self, path):
            super().__init__()
            self._p = Path(path)

        def _get_path(self):
            return self._p

    store = TestStore(tmp_path / "test.json")
    store._save({"key": "value"})
    loaded = store._load()
    assert loaded == {"key": "value"}


def test_base_store_handles_corrupt_file(tmp_path):
    from app.storage.base import BaseJsonStore
    from pathlib import Path

    class TestStore(BaseJsonStore):
        def __init__(self, path):
            super().__init__()
            self._p = Path(path)

        def _get_path(self):
            return self._p

    p = tmp_path / "corrupt.json"
    p.write_text("{ invalid json !!!")
    store = TestStore(str(p))
    result = store._load()
    assert result == {}


def test_base_store_list_empty(tmp_path):
    from app.storage.base import BaseJsonStore
    from pathlib import Path

    class ListStore(BaseJsonStore):
        def __init__(self, path):
            super().__init__()
            self._p = Path(path)

        def _get_path(self):
            return self._p

        def _empty(self):
            return []

    store = ListStore(tmp_path / "list.json")
    assert store._load() == []


# ── InviteStore ───────────────────────────────────────────────────────────────

def test_invite_store_create_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.invite_store import InviteStore
    store = InviteStore("test-inv-tenant")
    store.create("inv-001", "test-inv-tenant", "test@test.com", "member", "admin")
    invite = store.get("inv-001")
    assert invite is not None
    assert invite["email"] == "test@test.com"
    assert invite["is_active"] is True


def test_invite_store_mark_used(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.invite_store import InviteStore
    store = InviteStore("test-used-tenant")
    store.create("inv-002", "test-used-tenant", "used@test.com", "member", "admin")
    store.mark_used("inv-002")
    invite = store.get("inv-002")
    assert invite["is_active"] is False


def test_invite_store_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.invite_store import InviteStore
    store = InviteStore("test-missing-tenant")
    assert store.get("nonexistent-id") is None


# ── Invite endpoints ──────────────────────────────────────────────────────────

def test_invite_requires_admin(client):
    res = client.post("/admin/invite", json={"email": "test@test.com", "role": "member"})
    assert res.status_code in (401, 403)


def test_invite_page_not_found(client):
    res = client.get("/invite/nonexistent-invite-id")
    assert res.status_code == 404


def test_invite_page_public_for_valid_invite(client):
    admin = client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "관리자",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    assert admin.status_code == 200
    token = admin.json()["access_token"]
    invite = client.post(
        "/admin/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "viewer@test.com", "role": "viewer"},
    )
    assert invite.status_code == 200
    invite_id = invite.json()["invite_id"]

    res = client.get(f"/invite/{invite_id}")
    assert res.status_code == 200
    assert "초대" in res.text


def test_invite_accept_not_found(client):
    res = client.post(
        "/invite/nonexistent-id/accept",
        json={"username": "u", "display_name": "n", "password": "pass1234"},
    )
    assert res.status_code == 404


def test_invite_accept_public_for_valid_invite(client):
    admin = client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "관리자",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    assert admin.status_code == 200
    token = admin.json()["access_token"]
    invite = client.post(
        "/admin/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "member@test.com", "role": "member"},
    )
    assert invite.status_code == 200
    invite_id = invite.json()["invite_id"]

    res = client.post(
        f"/invite/{invite_id}/accept",
        json={
            "username": "member1",
            "display_name": "팀원",
            "password": "MemberPass1!",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "계정이 생성되었습니다."
    assert body["user"]["role"] == "member"


# ── G2B search ────────────────────────────────────────────────────────────────

def test_g2b_search_returns_results(client):
    res = client.get("/g2b/search?q=AI&days=7&limit=3")
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert "total" in data


# ── Share expiry ──────────────────────────────────────────────────────────────

def test_shared_link_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.share_store import ShareStore
    store = ShareStore("test-expiry-tenant")
    data = store._load()
    data["expired-id"] = {
        "share_id": "expired-id",
        "tenant_id": "test-expiry-tenant",
        "request_id": "req-x",
        "title": "만료 테스트",
        "created_by": "user1",
        "created_at": "2020-01-01T00:00:00",
        "expires_at": "2020-01-08T00:00:00",
        "access_count": 0,
        "is_active": True,
        "bundle_id": "",
    }
    store._save(data)
    link = store.get("expired-id")
    assert link["is_active"] is False

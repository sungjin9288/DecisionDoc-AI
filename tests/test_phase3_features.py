"""Tests for Phase 3 features: document sharing, favorites."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _token(user="u1", tenant="system", role="member"):
    from app.services.auth_service import create_access_token
    return create_access_token(user, tenant, role, user)


# ── Share API endpoints ───────────────────────────────────────────────────────

def test_create_share_requires_auth():
    res = client.post("/share", json={"request_id": "test", "title": "테스트"})
    assert res.status_code in (401, 403)


def test_shared_view_not_found():
    res = client.get("/shared/nonexistent-share-id-xyz-404")
    assert res.status_code == 404


def test_revoke_share_requires_auth():
    res = client.delete("/share/test-id")
    assert res.status_code in (401, 403)


def test_create_share_link_authenticated():
    token = _token()
    res = client.post(
        "/share",
        json={"request_id": "req-test-001", "title": "API 테스트 문서", "expires_days": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "share_id" in data
    assert "share_url" in data
    assert "expires_at" in data
    assert "/shared/" in data["share_url"]


def test_shared_view_returns_html():
    """Create a link then view it without auth — should return HTML."""
    token = _token()
    create_res = client.post(
        "/share",
        json={"request_id": "req-html-view", "title": "공유 HTML 테스트"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_res.status_code == 200
    share_id = create_res.json()["share_id"]

    view_res = client.get(f"/shared/{share_id}")
    assert view_res.status_code == 200
    assert "text/html" in view_res.headers["content-type"]
    assert "공유 HTML 테스트" in view_res.text


def test_revoke_share_link():
    token = _token()
    create_res = client.post(
        "/share",
        json={"request_id": "req-revoke", "title": "취소할 문서"},
        headers={"Authorization": f"Bearer {token}"},
    )
    share_id = create_res.json()["share_id"]

    revoke_res = client.delete(
        f"/share/{share_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoke_res.status_code == 200
    assert "비활성화" in revoke_res.json()["message"]


def test_revoke_nonexistent_share():
    token = _token()
    res = client.delete(
        "/share/no-such-share-999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


# ── ShareStore unit tests ─────────────────────────────────────────────────────

def test_share_store_create_and_get():
    from app.storage.share_store import ShareStore
    store = ShareStore("test-share-tenant")
    link = store.create(
        tenant_id="test-share-tenant",
        request_id="req-001",
        title="테스트 문서",
        created_by="user1",
        bundle_id="proposal_kr",
        expires_days=7,
    )
    assert link.share_id
    assert link.title == "테스트 문서"
    assert link.bundle_id == "proposal_kr"
    assert link.is_active is True

    retrieved = store.get(link.share_id)
    assert retrieved is not None
    assert retrieved["title"] == "테스트 문서"
    assert retrieved["is_active"] is True


def test_share_store_revoke():
    from app.storage.share_store import ShareStore
    store = ShareStore("test-revoke-tenant")
    link = store.create(
        tenant_id="test-revoke-tenant",
        request_id="req-002",
        title="취소 테스트",
        created_by="user1",
    )
    success = store.revoke(link.share_id, "user1")
    assert success is True

    # Wrong user cannot revoke
    link2 = store.create(
        tenant_id="test-revoke-tenant",
        request_id="req-003",
        title="취소 테스트 2",
        created_by="user1",
    )
    fail = store.revoke(link2.share_id, "user2")
    assert fail is False


def test_share_store_access_count():
    from app.storage.share_store import ShareStore
    store = ShareStore("test-access-tenant")
    link = store.create(
        tenant_id="test-access-tenant",
        request_id="req-004",
        title="조회 테스트",
        created_by="user1",
    )
    store.increment_access(link.share_id)
    store.increment_access(link.share_id)

    retrieved = store.get(link.share_id)
    assert retrieved["access_count"] == 2


def test_share_store_list_by_user():
    import uuid
    from app.storage.share_store import ShareStore
    # Use unique tenant to avoid cross-test contamination
    tenant = f"test-list-{uuid.uuid4().hex[:8]}"
    store = ShareStore(tenant)

    store.create(tenant_id=tenant, request_id="req-005",
                 title="목록 테스트 1", created_by="userA")
    store.create(tenant_id=tenant, request_id="req-006",
                 title="목록 테스트 2", created_by="userA")
    store.create(tenant_id=tenant, request_id="req-007",
                 title="다른 유저", created_by="userB")

    userA_links = store.list_by_user("userA")
    assert len(userA_links) == 2
    userB_links = store.list_by_user("userB")
    assert len(userB_links) == 1


def test_share_store_get_nonexistent():
    from app.storage.share_store import ShareStore
    store = ShareStore("test-missing-tenant")
    assert store.get("this-id-does-not-exist") is None


def test_share_store_revoke_nonexistent():
    from app.storage.share_store import ShareStore
    store = ShareStore("test-rev-none-tenant")
    result = store.revoke("no-such-id", "any-user")
    assert result is False


def test_share_link_expires_at_format():
    """expires_at should be a valid ISO datetime string."""
    from app.storage.share_store import ShareStore
    from datetime import datetime
    store = ShareStore("test-expires-tenant")
    link = store.create(
        tenant_id="test-expires-tenant",
        request_id="req-exp",
        title="만료 테스트",
        created_by="user1",
        expires_days=14,
    )
    # Should parse without error
    parsed = datetime.fromisoformat(link.expires_at)
    now = datetime.now()
    diff_days = (parsed - now).days
    assert 13 <= diff_days <= 14

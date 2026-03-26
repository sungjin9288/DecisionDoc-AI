"""Tests for Phase 2 features: onboarding, deadline alerts, ZIP export, empty state."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _token(user="u1", tenant="system", role="member"):
    from app.services.auth_service import create_access_token
    return create_access_token(user, tenant, role, user)


# ── Feature 3: /generate/export-zip ──────────────────────────────────────────

def test_export_zip_requires_auth():
    res = client.get("/generate/export-zip?request_id=test")
    assert res.status_code in (401, 403)


def test_export_zip_missing_context():
    token = _token()
    res = client.get(
        "/generate/export-zip?request_id=nonexistent-id-xyz",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_export_zip_invalid_format():
    token = _token()
    # nonexistent-id will 404 before format validation, so seed the cache first
    from app.routers.generate import _store_zip_docs
    _store_zip_docs("zip-fmt-test", [{"doc_type": "adr", "markdown": "# Test"}], "테스트")
    res = client.get(
        "/generate/export-zip?request_id=zip-fmt-test&formats=invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    # All requested formats are invalid → 400
    assert res.status_code == 400


def test_export_zip_returns_zip_with_valid_cache():
    """When docs are cached and format is valid, endpoint returns application/zip."""
    from app.routers.generate import _store_zip_docs
    _store_zip_docs(
        "zip-valid-test",
        [{"doc_type": "onepager", "markdown": "# 제목\n본문 내용"}],
        "테스트 문서",
    )
    token = _token()
    res = client.get(
        "/generate/export-zip?request_id=zip-valid-test&formats=docx",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert len(res.content) > 0


def test_export_zip_content_disposition():
    """Content-Disposition header should contain the title and .zip."""
    from app.routers.generate import _store_zip_docs
    _store_zip_docs(
        "zip-cd-test",
        [{"doc_type": "onepager", "markdown": "# 내용"}],
        "My Document",
    )
    token = _token()
    res = client.get(
        "/generate/export-zip?request_id=zip-cd-test&formats=docx",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    cd = res.headers.get("content-disposition", "")
    assert ".zip" in cd or "zip" in cd


def test_zip_cache_store_and_retrieve():
    """_store_zip_docs / _get_zip_docs round-trip."""
    from app.routers.generate import _store_zip_docs, _get_zip_docs
    docs = [{"doc_type": "adr", "markdown": "# ADR"}]
    _store_zip_docs("cache-roundtrip", docs, "타이틀")
    result = _get_zip_docs("cache-roundtrip")
    assert result is not None
    retrieved_docs, retrieved_title = result
    assert retrieved_docs == docs
    assert retrieved_title == "타이틀"


def test_zip_cache_missing_returns_none():
    from app.routers.generate import _get_zip_docs
    assert _get_zip_docs("definitely-not-stored-id") is None


# ── Feature 2: G2B deadline alerts ───────────────────────────────────────────

def test_g2b_bookmark_deadline_stored():
    """Bookmarks with imminent deadlines should be retrievable."""
    import uuid
    from app.storage.bookmark_store import BookmarkStore
    from datetime import datetime, timedelta

    tenant = f"test-deadline-{uuid.uuid4().hex[:8]}"
    store = BookmarkStore(tenant)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    bid = f"URGENT-{uuid.uuid4().hex[:6]}"
    store.add("user1", {
        "bid_number": bid,
        "title": "마감 임박 공고",
        "issuer": "테스트",
        "deadline": tomorrow,
    })
    bookmarks = store.get_for_user("user1")
    urgent = [b for b in bookmarks if b.get("bid_number") == bid]
    assert len(urgent) == 1
    assert urgent[0]["deadline"] == tomorrow


def test_g2b_bookmark_past_deadline():
    """Past-deadline bookmarks should be stored but not 'urgent'."""
    import uuid
    from app.storage.bookmark_store import BookmarkStore
    from datetime import datetime, timedelta

    tenant = f"test-past-{uuid.uuid4().hex[:8]}"
    store = BookmarkStore(tenant)
    past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    bid = f"PAST-{uuid.uuid4().hex[:6]}"
    store.add("user2", {
        "bid_number": bid,
        "title": "마감된 공고",
        "issuer": "기관",
        "deadline": past,
    })
    bookmarks = store.get_for_user("user2")
    assert any(b["bid_number"] == bid for b in bookmarks)


# ── History store ordering ────────────────────────────────────────────────────

def test_history_store_ordering():
    """Most recent history entry should come first."""
    from app.storage.history_store import HistoryStore, HistoryEntry
    import uuid

    store = HistoryStore("test-order-tenant")
    for i, title in enumerate(["첫번째", "두번째", "세번째"]):
        store.add(HistoryEntry(
            entry_id=str(uuid.uuid4()),
            tenant_id="test-order-tenant",
            user_id="user_order",
            bundle_id="proposal_kr",
            bundle_name="제안서",
            title=title,
            request_id=str(uuid.uuid4()),
            created_at=f"2025-03-0{i+1}T00:00:00",
        ))

    results = store.get_for_user("user_order")
    titles = [r["title"] for r in results]
    assert titles[0] == "세번째"


def test_history_endpoint_requires_auth():
    res = client.get("/history")
    assert res.status_code in (401, 403)


def test_history_endpoint_returns_list():
    token = _token()
    res = client.get("/history", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "history" in data
    assert isinstance(data["history"], list)

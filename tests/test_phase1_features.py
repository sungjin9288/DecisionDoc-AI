"""Tests for Phase 1 features: server-side history, G2B bookmarks, endpoints."""
import uuid
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.history_store import HistoryEntry, HistoryStore
from app.storage.bookmark_store import BookmarkStore

client = TestClient(app)

# ── HistoryStore unit tests ────────────────────────────────────────────────────

def test_history_store_add_and_get(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    entry = HistoryEntry(
        entry_id=str(uuid.uuid4()),
        tenant_id="t1",
        user_id="u1",
        bundle_id="adr",
        bundle_name="ADR",
        title="Test ADR",
        request_id="req-001",
        created_at="2026-03-01T00:00:00",
    )
    store.add(entry)
    items = store.get_for_user("u1")
    assert len(items) == 1
    assert items[0]["title"] == "Test ADR"


def test_history_store_delete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    eid = str(uuid.uuid4())
    entry = HistoryEntry(
        entry_id=eid,
        tenant_id="t1",
        user_id="u1",
        bundle_id="adr",
        bundle_name="ADR",
        title="To delete",
        request_id="req-002",
        created_at="2026-03-01T00:00:00",
    )
    store.add(entry)
    store.delete(eid, "u1")
    assert store.get_for_user("u1") == []


def test_history_store_cap_at_50(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    for i in range(55):
        store.add(HistoryEntry(
            entry_id=str(uuid.uuid4()),
            tenant_id="t1",
            user_id="u1",
            bundle_id="adr",
            bundle_name="ADR",
            title=f"Entry {i}",
            request_id=f"req-{i:03d}",
            created_at="2026-03-01T00:00:00",
        ))
    items = store.get_for_user("u1", limit=100)
    assert len(items) == 50


def test_history_store_user_isolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    for uid in ("alice", "bob"):
        store.add(HistoryEntry(
            entry_id=str(uuid.uuid4()),
            tenant_id="t1",
            user_id=uid,
            bundle_id="adr",
            bundle_name="ADR",
            title=f"Entry by {uid}",
            request_id=f"req-{uid}",
            created_at="2026-03-01T00:00:00",
        ))
    assert len(store.get_for_user("alice")) == 1
    assert len(store.get_for_user("bob")) == 1


# ── BookmarkStore unit tests ───────────────────────────────────────────────────

def test_bookmark_store_add_and_get(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = BookmarkStore("t1")
    ann = {"bid_number": "20260101-001", "title": "AI 시스템 구축", "issuer": "행안부"}
    store.add("u1", ann)
    bookmarks = store.get_for_user("u1")
    assert len(bookmarks) == 1
    assert bookmarks[0]["bid_number"] == "20260101-001"
    assert "bookmarked_at" in bookmarks[0]


def test_bookmark_store_deduplication(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = BookmarkStore("t1")
    ann = {"bid_number": "20260101-001", "title": "AI"}
    store.add("u1", ann)
    store.add("u1", ann)  # duplicate
    assert len(store.get_for_user("u1")) == 1


def test_bookmark_store_remove(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = BookmarkStore("t1")
    store.add("u1", {"bid_number": "BID-001", "title": "Test"})
    store.remove("u1", "BID-001")
    assert store.get_for_user("u1") == []


def test_bookmark_store_is_bookmarked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = BookmarkStore("t1")
    store.add("u1", {"bid_number": "BID-X", "title": "Test"})
    assert store.is_bookmarked("u1", "BID-X") is True
    assert store.is_bookmarked("u1", "BID-Y") is False


def test_bookmark_store_user_isolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = BookmarkStore("t1")
    store.add("alice", {"bid_number": "BID-A", "title": "Alice entry"})
    assert len(store.get_for_user("alice")) == 1
    assert len(store.get_for_user("bob")) == 0


# ── History API endpoint tests ────────────────────────────────────────────────

def _auth_headers():
    """Create a test JWT token for API calls."""
    from app.services.auth_service import create_access_token
    token = create_access_token(
        user_id="testuser", tenant_id="system", role="admin", username="testuser"
    )
    return {"Authorization": f"Bearer {token}"}


def test_history_get_returns_history_key():
    res = client.get("/history", headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert "history" in data
    assert isinstance(data["history"], list)


def test_history_delete_nonexistent_returns_200():
    res = client.delete("/history/nonexistent-id", headers=_auth_headers())
    assert res.status_code == 200  # delete is idempotent


# ── Bookmark API endpoint tests ───────────────────────────────────────────────

def test_g2b_bookmarks_get_returns_bookmarks_key():
    res = client.get("/g2b/bookmarks", headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert "bookmarks" in data
    assert isinstance(data["bookmarks"], list)


def test_g2b_bookmarks_post_and_delete():
    headers = _auth_headers()
    ann = {"bid_number": "TEST-BID-001", "title": "테스트 공고", "issuer": "테스트기관"}
    # Add
    res = client.post("/g2b/bookmarks", json=ann, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "bookmark" in data
    assert data["bookmark"]["bid_number"] == "TEST-BID-001"
    # Verify appears in list
    res2 = client.get("/g2b/bookmarks", headers=headers)
    bids = [b["bid_number"] for b in res2.json()["bookmarks"]]
    assert "TEST-BID-001" in bids
    # bookmarked_at should be in the stored list entry
    stored = next(b for b in res2.json()["bookmarks"] if b["bid_number"] == "TEST-BID-001")
    assert "bookmarked_at" in stored
    # Delete
    res3 = client.delete("/g2b/bookmarks/TEST-BID-001", headers=headers)
    assert res3.status_code == 200

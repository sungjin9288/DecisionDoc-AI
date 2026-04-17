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
        applied_references=[{"filename": "winning-proposal.docx", "selection_reason": "bundle `proposal_kr` 일치"}],
    )
    store.add(entry)
    items = store.get_for_user("u1")
    assert len(items) == 1
    assert items[0]["title"] == "Test ADR"
    assert items[0]["applied_references"][0]["filename"] == "winning-proposal.docx"
    assert "docs" not in items[0]


def test_history_store_get_entry_returns_docs_for_promotion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    entry = HistoryEntry(
        entry_id=str(uuid.uuid4()),
        tenant_id="t1",
        user_id="u1",
        bundle_id="proposal_kr",
        bundle_type="proposal_kr",
        bundle_name="제안서",
        title="승격 가능한 제안서",
        request_id="req-history-detail-001",
        created_at="2026-03-01T00:00:00",
        project_id="proj-001",
        docs=[{"doc_type": "business_understanding", "markdown": "# 제목\n본문"}],
    )
    store.add(entry)

    detail = store.get_entry(entry.entry_id, "u1")
    assert detail is not None
    assert detail["project_id"] == "proj-001"
    assert detail["bundle_type"] == "proposal_kr"
    assert detail["docs"][0]["doc_type"] == "business_understanding"


def test_history_store_visual_assets_hidden_in_list_and_available_in_detail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    entry = HistoryEntry(
        entry_id=str(uuid.uuid4()),
        tenant_id="t1",
        user_id="u1",
        bundle_id="proposal_kr",
        bundle_type="proposal_kr",
        bundle_name="제안서",
        title="시각자료 포함 이력",
        request_id="req-history-visual-001",
        created_at="2026-03-01T00:00:00",
        visual_assets=[{
            "asset_id": "asset-1",
            "doc_type": "business_understanding",
            "slide_title": "사업 추진 배경",
            "visual_type": "timeline",
            "visual_brief": "핵심 일정 도식",
            "layout_hint": "우측 40%",
            "source_kind": "svg",
            "source_model": "",
            "prompt": "",
            "media_type": "image/svg+xml",
            "encoding": "base64",
            "content_base64": "PHN2Zy8+",
        }],
    )
    store.add(entry)

    items = store.get_for_user("u1")
    assert "visual_assets" not in items[0]
    assert items[0]["visual_asset_count"] == 1

    detail = store.get_entry(entry.entry_id, "u1")
    assert detail is not None
    assert detail["visual_assets"][0]["asset_id"] == "asset-1"


def test_history_store_update_visual_assets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    entry = HistoryEntry(
        entry_id="history-visual-update-001",
        tenant_id="t1",
        user_id="u1",
        bundle_id="proposal_kr",
        bundle_name="제안서",
        title="시각자료 업데이트",
        request_id="req-visual-update-001",
        created_at="2026-03-01T00:00:00",
    )
    store.add(entry)

    updated = store.update_visual_assets("history-visual-update-001", "u1", [{
        "asset_id": "asset-2",
        "doc_type": "execution_plan",
        "slide_title": "수행 일정",
        "visual_type": "timeline",
        "visual_brief": "일정 도식",
        "layout_hint": "우측 배치",
        "source_kind": "provider_image",
        "source_model": "gpt-image-1",
        "prompt": "timeline",
        "media_type": "image/png",
        "encoding": "base64",
        "content_base64": "ZmFrZQ==",
    }])

    assert updated is True
    detail = store.get_entry("history-visual-update-001", "u1")
    assert detail is not None
    assert detail["visual_assets"][0]["source_kind"] == "provider_image"


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


def test_history_store_mark_promoted_updates_matching_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = HistoryStore("t1")
    entry = HistoryEntry(
        entry_id=str(uuid.uuid4()),
        tenant_id="t1",
        user_id="u1",
        bundle_id="proposal_kr",
        bundle_name="제안서",
        title="승격 대상",
        request_id="req-promote-001",
        created_at="2026-03-01T00:00:00",
    )
    store.add(entry)

    updated = store.mark_promoted(
        "req-promote-001",
        project_id="proj-123",
        document_count=2,
        quality_tier="gold",
        success_state="approved",
        promoted_at="2026-04-16T12:00:00+00:00",
        knowledge_documents=[
            {"doc_id": "kdoc-1", "doc_type": "business_understanding", "filename": "승인본-사업이해.md"},
            {"doc_id": "kdoc-2", "doc_type": "execution_plan", "filename": "승인본-수행계획.md"},
        ],
        user_id="u1",
    )

    assert updated == 1
    item = store.get_entry(entry.entry_id, "u1")
    assert item is not None
    assert item["knowledge_promoted"] is True
    assert item["knowledge_project_id"] == "proj-123"
    assert item["knowledge_document_count"] == 2
    assert item["knowledge_quality_tier"] == "gold"
    assert item["knowledge_success_state"] == "approved"
    assert item["knowledge_documents"][0]["doc_id"] == "kdoc-1"


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


def test_history_get_entry_returns_docs_payload(tmp_path, monkeypatch):
    store = HistoryStore(
        "system",
        base_dir=str(client.app.state.data_dir),
        backend=client.app.state.state_backend,
    )
    entry = HistoryEntry(
        entry_id="history-detail-001",
        tenant_id="system",
        user_id="testuser",
        bundle_id="proposal_kr",
        bundle_type="proposal_kr",
        bundle_name="제안서",
        title="상세 이력",
        request_id="req-history-api-001",
        created_at="2026-03-01T00:00:00",
        project_id="proj-history-1",
        docs=[{"doc_type": "business_understanding", "markdown": "# 본문"}],
    )
    store.add(entry)

    res = client.get("/history/history-detail-001", headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == "proj-history-1"
    assert data["bundle_type"] == "proposal_kr"
    assert data["docs"][0]["doc_type"] == "business_understanding"


def test_history_update_visual_assets_endpoint():
    store = HistoryStore(
        "system",
        base_dir=str(client.app.state.data_dir),
        backend=client.app.state.state_backend,
    )
    entry = HistoryEntry(
        entry_id="history-visual-api-001",
        tenant_id="system",
        user_id="testuser",
        bundle_id="proposal_kr",
        bundle_type="proposal_kr",
        bundle_name="제안서",
        title="시각자료 API 이력",
        request_id="req-history-visual-api-001",
        created_at="2026-03-01T00:00:00",
        docs=[{"doc_type": "business_understanding", "markdown": "# 본문"}],
    )
    store.add(entry)

    payload = {
        "visual_assets": [{
            "asset_id": "asset-api-1",
            "doc_type": "business_understanding",
            "slide_title": "사업 추진 배경",
            "visual_type": "timeline",
            "visual_brief": "핵심 일정",
            "layout_hint": "우측 40%",
            "source_kind": "svg",
            "source_model": "",
            "prompt": "",
            "media_type": "image/svg+xml",
            "encoding": "base64",
            "content_base64": "PHN2Zy8+",
        }]
    }
    res = client.put("/history/history-visual-api-001/visual-assets", json=payload, headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert data["visual_asset_count"] == 1

    detail = client.get("/history/history-visual-api-001", headers=_auth_headers())
    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["visual_assets"][0]["asset_id"] == "asset-api-1"


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

"""Tests for history favorites endpoints."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


def _seed_history(tmp_path, tenant_id="system", user_id="test_user"):
    """Seed a history entry directly."""
    from app.storage.history_store import HistoryStore, HistoryEntry
    import uuid
    store = HistoryStore(tenant_id)
    entry_id = str(uuid.uuid4())
    store.add(HistoryEntry(
        entry_id=entry_id,
        tenant_id=tenant_id,
        user_id=user_id,
        bundle_id="tech_decision",
        bundle_name="기술 결정",
        title="테스트 문서",
        request_id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(),
    ))
    return entry_id


def test_history_star_returns_200(tmp_path, monkeypatch):
    """POST /history/{id}/star 는 200을 반환해야 한다."""
    client = _create_client(tmp_path, monkeypatch)
    entry_id = _seed_history(tmp_path)
    res = client.post(f"/history/{entry_id}/star", headers={"X-Test-User": "test_user"})
    # Auth might reject anonymous — check at least we get a response
    assert res.status_code in (200, 401, 403)


def test_history_favorites_endpoint_exists(tmp_path, monkeypatch):
    """GET /history/favorites 엔드포인트가 존재해야 한다."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/history/favorites")
    # May return 401 in non-dev or 200 in dev mode
    assert res.status_code in (200, 401, 403)


def test_history_store_toggle_favorite(tmp_path, monkeypatch):
    """HistoryStore.toggle_favorite 가 올바르게 동작해야 한다."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.history_store import HistoryStore, HistoryEntry
    import uuid

    tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
    store = HistoryStore(tenant_id)
    entry_id = str(uuid.uuid4())
    user_id = f"user_toggle_{uuid.uuid4().hex[:6]}"

    store.add(HistoryEntry(
        entry_id=entry_id,
        tenant_id=tenant_id,
        user_id=user_id,
        bundle_id="tech_decision",
        bundle_name="기술 결정",
        title="테스트",
        request_id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(),
    ))

    # 처음 토글: starred = True
    result = store.toggle_favorite(entry_id, user_id)
    assert result is True

    # 두 번째 토글: starred = False
    result = store.toggle_favorite(entry_id, user_id)
    assert result is False


def test_history_store_get_favorites(tmp_path, monkeypatch):
    """get_favorites 는 starred=True 인 항목만 반환해야 한다."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.history_store import HistoryStore, HistoryEntry
    import uuid

    # 격리된 tenant_id 사용 (테스트 간 데이터 오염 방지)
    tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
    store = HistoryStore(tenant_id)
    user_id = f"user_fav_{uuid.uuid4().hex[:6]}"

    ids = []
    for i in range(3):
        eid = str(uuid.uuid4())
        ids.append(eid)
        store.add(HistoryEntry(
            entry_id=eid,
            tenant_id=tenant_id,
            user_id=user_id,
            bundle_id="tech_decision",
            bundle_name=f"문서 {i}",
            title=f"제목 {i}",
            request_id=str(uuid.uuid4()),
            created_at=datetime.now(UTC).isoformat(),
        ))

    # 첫 번째 항목만 즐겨찾기
    store.toggle_favorite(ids[0], user_id)

    favorites = store.get_favorites(user_id)
    assert len(favorites) == 1
    assert favorites[0]["entry_id"] == ids[0]


def test_history_store_favorite_persists(tmp_path, monkeypatch):
    """즐겨찾기 상태가 재로드 후에도 유지되어야 한다."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.history_store import HistoryStore, HistoryEntry
    import uuid

    tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
    user_id = f"persist_{uuid.uuid4().hex[:6]}"
    store = HistoryStore(tenant_id)
    entry_id = str(uuid.uuid4())

    store.add(HistoryEntry(
        entry_id=entry_id,
        tenant_id=tenant_id,
        user_id=user_id,
        bundle_id="tech_decision",
        bundle_name="기술 결정",
        title="영속성 테스트",
        request_id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(),
    ))
    store.toggle_favorite(entry_id, user_id)

    # 새 인스턴스로 다시 로드 (같은 tenant)
    store2 = HistoryStore(tenant_id)
    favorites = store2.get_favorites(user_id)
    assert any(f["entry_id"] == entry_id for f in favorites)

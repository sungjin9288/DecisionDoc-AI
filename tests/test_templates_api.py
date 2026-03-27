"""Tests for /templates CRUD endpoints."""
import uuid
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


_VALID_PAYLOAD = {
    "name": "기술 결정 템플릿",
    "bundle_id": "tech_decision",
    "form_data": {"title": "결제 시스템 MSA 전환", "goal": "장애 격리 및 배포 속도 개선"},
}


def test_create_template_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/templates", json=_VALID_PAYLOAD)
    assert res.status_code == 200


def test_create_template_has_template_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/templates", json=_VALID_PAYLOAD).json()
    assert "template_id" in data
    assert data["template_id"]


def test_create_template_has_name(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/templates", json=_VALID_PAYLOAD).json()
    assert "name" in data
    assert data["name"] == _VALID_PAYLOAD["name"]


def test_create_template_missing_name(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/templates", json={"bundle_id": "tech_decision"})
    assert res.status_code == 422


def test_create_template_missing_bundle_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/templates", json={"name": "My Template"})
    assert res.status_code == 422


def test_create_template_empty_name(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/templates", json={"name": "", "bundle_id": "tech_decision"})
    assert res.status_code == 422


def test_list_templates_returns_list(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/templates").json()
    assert isinstance(data, list)


def test_list_templates_includes_created(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = client.post("/templates", json=_VALID_PAYLOAD).json()
    template_id = created["template_id"]
    listing = client.get("/templates").json()
    assert isinstance(listing, list)
    ids = [t["template_id"] for t in listing]
    assert template_id in ids


def test_get_template_by_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = client.post("/templates", json=_VALID_PAYLOAD).json()
    template_id = created["template_id"]
    res = client.get(f"/templates/{template_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["template_id"] == template_id
    assert data["name"] == _VALID_PAYLOAD["name"]


def test_get_template_not_found(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/templates/nonexistent-id-xyz-12345")
    assert res.status_code == 404


def test_delete_template(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = client.post("/templates", json=_VALID_PAYLOAD).json()
    template_id = created["template_id"]
    res = client.delete(f"/templates/{template_id}")
    assert res.status_code == 200
    data = res.json()
    assert data.get("deleted") is True


def test_delete_template_not_found(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.delete("/templates/nonexistent-id-xyz-12345")
    assert res.status_code == 404


def test_delete_removes_from_list(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = client.post("/templates", json=_VALID_PAYLOAD).json()
    template_id = created["template_id"]
    client.delete(f"/templates/{template_id}")
    listing = client.get("/templates").json()
    ids = [t["template_id"] for t in listing]
    assert template_id not in ids


def test_create_template_with_form_data(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    form_data = {"title": "API 게이트웨이 도입", "goal": "보안 강화", "background": "기존 직접 연결 방식의 문제"}
    payload = {"name": "API 게이트웨이 템플릿", "bundle_id": "tech_decision", "form_data": form_data}
    created = client.post("/templates", json=payload).json()
    template_id = created["template_id"]
    res = client.get(f"/templates/{template_id}")
    assert res.status_code == 200
    data = res.json()
    assert data.get("form_data") == form_data


def test_template_store_directly(tmp_path, monkeypatch):
    """Unit test TemplateStore.add(), list_for_user(), get(), delete()."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.template_store import TemplateStore, TemplateEntry

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    tenant_id = "system"
    store = TemplateStore(tenant_id)

    entry = TemplateEntry(
        template_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name="직접 저장 템플릿",
        bundle_id="tech_decision",
        bundle_name="기술 결정",
        form_data={"title": "DB 샤딩 전략"},
    )
    store.add(entry)

    # list_for_user should return the entry
    results = store.list_for_user(user_id)
    assert len(results) == 1
    assert results[0]["template_id"] == entry.template_id
    assert results[0]["name"] == "직접 저장 템플릿"

    # get() should return the same entry
    got = store.get(entry.template_id, user_id)
    assert got is not None
    assert got["template_id"] == entry.template_id

    # delete() should remove it
    deleted = store.delete(entry.template_id, user_id)
    assert deleted is True

    # list_for_user should be empty now
    assert store.list_for_user(user_id) == []

    # get() should return None
    assert store.get(entry.template_id, user_id) is None

    # deleting again returns False
    assert store.delete(entry.template_id, user_id) is False

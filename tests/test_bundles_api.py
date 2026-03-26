"""Tests for enhanced /bundles and /generate/summary endpoints."""
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


# ─── GET /bundles (enhanced) ──────────────────────────────────────────────────

def test_bundles_list_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/bundles")
    assert res.status_code == 200


def test_bundles_list_is_array(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/bundles").json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_bundles_search_by_keyword(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/bundles?q=기술").json()
    # Should return some results
    assert isinstance(data, list)


def test_bundles_search_no_match(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/bundles?q=xyzqwerty12345_nomatch").json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_bundles_category_filter(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    # Get all bundles to find a valid category
    all_bundles = client.get("/bundles").json()
    if not all_bundles:
        return
    category = all_bundles[0].get("category")
    if not category:
        return
    filtered = client.get(f"/bundles?category={category}").json()
    assert isinstance(filtered, list)
    assert all(b.get("category") == category for b in filtered)


# ─── GET /bundles/{bundle_id} ─────────────────────────────────────────────────

def test_bundle_detail_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/bundles/tech_decision")
    assert res.status_code == 200


def test_bundle_detail_has_required_fields(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/bundles/tech_decision").json()
    assert "id" in data
    assert "name_ko" in data
    assert "doc_keys" in data
    assert "doc_schema_keys" in data


def test_bundle_detail_id_matches(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/bundles/tech_decision").json()
    assert data["id"] == "tech_decision"


def test_bundle_detail_doc_schema_keys_is_list(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/bundles/tech_decision").json()
    assert isinstance(data["doc_schema_keys"], list)
    if data["doc_schema_keys"]:
        first = data["doc_schema_keys"][0]
        assert "doc_key" in first
        assert "json_schema_keys" in first


def test_bundle_detail_not_found(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/bundles/nonexistent_bundle_xyz")
    assert res.status_code == 404


def test_bundle_detail_proposal_kr(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/bundles/proposal_kr")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "proposal_kr"


# ─── POST /generate/summary ───────────────────────────────────────────────────

_SAMPLE_DOC = """## 기술 결정 개요

결제 시스템을 MSA(Microservice Architecture)로 전환합니다.

## 배경

현재 모놀리식 아키텍처로 인해 배포 주기가 길고 장애 격리가 어렵습니다.
월 운영비 절감과 팀 자율성 향상이 주요 목표입니다.

## 결정

서비스 경계를 Payment, User, Notification 3개로 분리하고,
API Gateway 패턴을 적용합니다.
"""


def test_summary_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/summary", json={"content": _SAMPLE_DOC})
    assert res.status_code == 200


def test_summary_has_summary_field(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/summary", json={"content": _SAMPLE_DOC}).json()
    assert "summary" in data
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0


def test_summary_has_length_info(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/summary", json={"content": _SAMPLE_DOC}).json()
    assert "original_length" in data
    assert "summary_length" in data
    assert data["original_length"] > 0


def test_summary_missing_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/summary", json={})
    assert res.status_code == 422


def test_summary_empty_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/summary", json={"content": ""})
    assert res.status_code == 422


def test_summary_with_audience(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/summary", json={
        "content": _SAMPLE_DOC,
        "audience": "임원",
        "max_sentences": 2,
    }).json()
    assert data.get("audience") == "임원"
    assert data.get("summary") is not None


def test_summary_too_long_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    huge = "A " * 11000  # ~22000 chars
    res = client.post("/generate/summary", json={"content": huge})
    assert res.status_code == 422


def test_summary_has_request_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/summary", json={"content": _SAMPLE_DOC}).json()
    assert "request_id" in data
    assert data["request_id"]

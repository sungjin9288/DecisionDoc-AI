"""Tests for POST /generate/translate and POST /generate/related endpoints."""
import pytest
from fastapi.testclient import TestClient

_SAMPLE_DOC = (
    "# 기술 의사결정 기록\n\n"
    "## 배경\n본 문서는 데이터베이스 선택 결정을 기록합니다.\n\n"
    "## 결정\nPostgreSQL을 주 데이터베이스로 선택합니다.\n\n"
    "## 이유\n- 트랜잭션 지원\n- 풍부한 생태계\n- 팀의 기존 경험\n"
)


def _create_client(tmp_path, monkeypatch, *, with_auth=False):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    if with_auth:
        monkeypatch.setenv("DECISIONDOC_API_KEYS", "test-key")
    else:
        monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
        monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return _create_client(tmp_path, monkeypatch)


# ── /generate/translate ────────────────────────────────────────────────────────

def test_translate_returns_200(client):
    res = client.post(
        "/generate/translate",
        json={"content": _SAMPLE_DOC, "target_lang": "en"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 200


def test_translate_has_expected_fields(client):
    res = client.post(
        "/generate/translate",
        json={"content": _SAMPLE_DOC, "target_lang": "en"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    data = res.json()
    assert "translated_content" in data
    assert "target_lang" in data
    assert "original_length" in data
    assert "translated_length" in data
    assert "request_id" in data


def test_translate_target_lang_ko(client):
    res = client.post(
        "/generate/translate",
        json={"content": "This is a technical decision record.", "target_lang": "ko"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 200
    assert res.json()["target_lang"] == "ko"


def test_translate_default_lang_is_en(client):
    res = client.post(
        "/generate/translate",
        json={"content": _SAMPLE_DOC},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 200
    assert res.json()["target_lang"] == "en"


def test_translate_original_length_correct(client):
    res = client.post(
        "/generate/translate",
        json={"content": _SAMPLE_DOC, "target_lang": "en"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.json()["original_length"] == len(_SAMPLE_DOC.strip())


def test_translate_missing_content(client):
    res = client.post(
        "/generate/translate",
        json={"target_lang": "en"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 422


def test_translate_empty_content(client):
    res = client.post(
        "/generate/translate",
        json={"content": "", "target_lang": "en"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 422


def test_translate_invalid_target_lang(client):
    res = client.post(
        "/generate/translate",
        json={"content": _SAMPLE_DOC, "target_lang": "fr"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 422


def test_translate_too_long_content(client):
    res = client.post(
        "/generate/translate",
        json={"content": "a" * 20001, "target_lang": "en"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 422


def test_translate_requires_auth(tmp_path, monkeypatch):
    c = _create_client(tmp_path, monkeypatch, with_auth=True)
    res = c.post(
        "/generate/translate",
        json={"content": _SAMPLE_DOC, "target_lang": "en"},
    )
    assert res.status_code == 401


# ── /generate/related ──────────────────────────────────────────────────────────

def test_related_returns_200(client):
    res = client.post(
        "/generate/related",
        json={"bundle_id": "tech_decision", "title": "데이터베이스 선택", "goal": "최적의 DB 선택"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 200


def test_related_has_expected_fields(client):
    res = client.post(
        "/generate/related",
        json={"bundle_id": "tech_decision"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    data = res.json()
    assert "current_bundle_id" in data
    assert "related" in data
    assert "request_id" in data
    assert isinstance(data["related"], list)


def test_related_current_bundle_id_matches(client):
    res = client.post(
        "/generate/related",
        json={"bundle_id": "tech_decision"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.json()["current_bundle_id"] == "tech_decision"


def test_related_excludes_current_bundle(client):
    res = client.post(
        "/generate/related",
        json={"bundle_id": "tech_decision"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    related_ids = [r["bundle_id"] for r in res.json()["related"]]
    assert "tech_decision" not in related_ids


def test_related_max_five_results(client):
    res = client.post(
        "/generate/related",
        json={"bundle_id": "tech_decision"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert len(res.json()["related"]) <= 5


def test_related_has_required_item_fields(client):
    res = client.post(
        "/generate/related",
        json={"bundle_id": "tech_decision"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    for item in res.json()["related"]:
        assert "bundle_id" in item
        assert "name_ko" in item
        assert "relevance_score" in item


def test_related_missing_bundle_id(client):
    res = client.post(
        "/generate/related",
        json={"title": "테스트"},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert res.status_code == 422


def test_related_requires_auth(tmp_path, monkeypatch):
    c = _create_client(tmp_path, monkeypatch, with_auth=True)
    res = c.post(
        "/generate/related",
        json={"bundle_id": "tech_decision"},
    )
    assert res.status_code == 401

"""Tests for GET /version and POST /generate/validate endpoints."""
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch, *, procurement_enabled: bool = False):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv(
        "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED",
        "1" if procurement_enabled else "0",
    )
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


# ─── /version ─────────────────────────────────────────────────────────────────

def test_version_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.get("/version")
    assert res.status_code == 200


def test_version_has_required_fields(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    assert "version" in data
    assert "api_version" in data
    assert "environment" in data
    assert "provider" in data
    assert "features" in data


def test_version_api_version_is_v1(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    assert data["api_version"] == "v1"


def test_version_default_app_version_is_1_1_8(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    assert data["version"] == "1.1.8"


def test_version_features_is_dict(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    features = data["features"]
    assert isinstance(features, dict)
    assert "search" in features
    assert "cache" in features
    assert "procurement_copilot" in features
    assert "realtime_events" in features


def test_version_procurement_flag_defaults_to_false(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, procurement_enabled=False)
    data = client.get("/version").json()
    assert data["features"]["procurement_copilot"] is False


def test_version_procurement_flag_reflects_env(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, procurement_enabled=True)
    data = client.get("/version").json()
    assert data["features"]["procurement_copilot"] is True


def test_version_realtime_events_enabled_by_default_in_dev(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    assert data["features"]["realtime_events"] is True


def test_version_realtime_events_disabled_by_default_on_lambda(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "decisiondoc-ai-prod")
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    assert data["features"]["realtime_events"] is False


def test_version_is_public_even_when_users_exist(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    register = client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@test.com",
            "password": "AdminPass1!",
        },
    )
    assert register.status_code == 200

    response = client.get("/version")
    assert response.status_code == 200
    assert "features" in response.json()


def test_version_provider_is_mock(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.get("/version").json()
    assert data["provider"] == "mock"


# ─── /generate/validate ───────────────────────────────────────────────────────

def test_validate_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/validate", json={"title": "테스트 제목", "goal": "테스트 목표"})
    assert res.status_code == 200


def test_validate_valid_payload(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={
        "title": "결제 시스템 MSA 전환",
        "goal": "유지보수성 향상 및 월 운영비 30% 절감",
        "bundle_type": "tech_decision",
    }).json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_validate_missing_title(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={"title": "", "goal": "목표"}).json()
    assert data["valid"] is False
    title_errors = [e for e in data["errors"] if e["field"] == "title"]
    assert len(title_errors) > 0


def test_validate_missing_goal(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={"title": "제목입니다", "goal": ""}).json()
    assert data["valid"] is False
    goal_errors = [e for e in data["errors"] if e["field"] == "goal"]
    assert len(goal_errors) > 0


def test_validate_invalid_bundle_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={
        "title": "제목입니다",
        "goal": "목표입니다",
        "bundle_type": "invalid_bundle_xyz",
    }).json()
    assert data["valid"] is False
    bundle_errors = [e for e in data["errors"] if e["field"] == "bundle_type"]
    assert len(bundle_errors) > 0


def test_validate_short_title(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={"title": "ab", "goal": "목표입니다"}).json()
    assert data["valid"] is False
    errors = [e for e in data["errors"] if e.get("code") == "too_short" and e["field"] == "title"]
    assert len(errors) > 0


def test_validate_has_warnings_without_context(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={
        "title": "결제 시스템 전환",
        "goal": "유지보수성 향상",
        "bundle_type": "tech_decision",
    }).json()
    assert data["valid"] is True
    # context 없으면 warning 있어야 함
    assert isinstance(data["warnings"], list)
    assert len(data["warnings"]) > 0


def test_validate_has_request_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={"title": "제목", "goal": "목표"}).json()
    assert "request_id" in data
    assert data["request_id"]


def test_validate_both_missing(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/validate", json={}).json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 2

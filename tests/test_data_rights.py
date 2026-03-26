"""
Tests for personal data rights endpoints:
  GET  /auth/my-data        (개인정보 열람권 §35)
  POST /auth/export-my-data (개인정보 이동권 §35의2)
  DELETE /auth/withdraw     (회원 탈퇴 §36)
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-data-rights-32chars!!")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app
    tc = TestClient(create_app(), raise_server_exceptions=False)

    # Register user
    r = tc.post("/auth/register", json={
        "username": "rights_user",
        "display_name": "권리 테스터",
        "email": "rights@test.com",
        "password": "TestPassword123!",
    })
    assert r.status_code in (200, 201), f"Register failed: {r.text}"

    # Login
    r = tc.post("/auth/login", json={
        "username": "rights_user",
        "password": "TestPassword123!",
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]

    return tc, token


def test_get_my_data_returns_200(auth_client):
    """GET /auth/my-data returns 200 for authenticated user."""
    tc, token = auth_client
    r = tc.get("/auth/my-data",
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_get_my_data_structure(auth_client):
    """GET /auth/my-data returns expected structure."""
    tc, token = auth_client
    data = tc.get("/auth/my-data",
                  headers={"Authorization": f"Bearer {token}"}).json()
    assert "user_info" in data
    assert "activity_logs" in data
    assert "data_retention_policy" in data
    assert data["user_info"]["username"] == "rights_user"


def test_get_my_data_requires_auth(auth_client):
    """GET /auth/my-data returns 401/403 without token."""
    tc, _ = auth_client
    r = tc.get("/auth/my-data")
    assert r.status_code in (401, 403)


def test_export_my_data_returns_json_file(auth_client):
    """POST /auth/export-my-data returns downloadable JSON."""
    tc, token = auth_client
    r = tc.post("/auth/export-my-data",
                headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    assert "attachment" in r.headers.get("content-disposition", "")


def test_export_my_data_valid_json(auth_client):
    """POST /auth/export-my-data content is valid JSON."""
    import json
    tc, token = auth_client
    r = tc.post("/auth/export-my-data",
                headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = json.loads(r.content)
    assert "user_info" in data


def test_withdraw_wrong_password(auth_client):
    """DELETE /auth/withdraw with wrong password returns 400."""
    import json as _json
    tc, token = auth_client
    r = tc.request(
        "DELETE",
        "/auth/withdraw",
        content=_json.dumps({"password": "wrongpassword"}),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_withdraw_success(auth_client):
    """DELETE /auth/withdraw with correct password deactivates account."""
    import json as _json
    tc, token = auth_client
    r = tc.request(
        "DELETE",
        "/auth/withdraw",
        content=_json.dumps({"password": "TestPassword123!", "reason": "테스트"}),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "탈퇴" in data.get("message", "")
    assert "deleted_at" in data


def test_withdraw_requires_auth(auth_client):
    """DELETE /auth/withdraw returns 401/403 without token."""
    import json as _json
    tc, _ = auth_client
    r = tc.request(
        "DELETE",
        "/auth/withdraw",
        content=_json.dumps({"password": "TestPassword123!"}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code in (401, 403)

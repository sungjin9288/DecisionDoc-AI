"""tests/test_infrastructure.py — Infrastructure tests: health, security headers, rate limiting.

Coverage (12 tests):
  Health         : GET /health returns 200 with status field
  Security headers: X-Frame-Options, X-Content-Type-Options, CSP
  PWA            : /offline.html, /manifest.json, /sw.js
  CORS           : unknown origin not reflected
  Tenant mismatch: JWT tenant != header tenant -> 403
  Rate limiting  : 11th login attempt -> 429
  Swagger        : hidden in production
"""
from __future__ import annotations

import re
import os
import time
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-infra-tests-32chars!")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    try:
        import app.middleware.rate_limit as rl
        rl.clear_attempts_for_test()
    except Exception:
        pass
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health_endpoint_returns_200(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert "status" in res.json()


# ── Security headers ──────────────────────────────────────────────────────────

def test_security_headers_x_frame_options(client):
    res = client.get("/health")
    assert res.headers.get("x-frame-options", "").upper() == "DENY"


def test_security_headers_x_content_type(client):
    res = client.get("/health")
    assert res.headers.get("x-content-type-options", "").lower() == "nosniff"


def test_security_headers_csp(client):
    res = client.get("/health")
    csp = res.headers.get("content-security-policy", "")
    assert "default-src" in csp
    assert "script-src" in csp
    assert "'unsafe-inline'" in csp
    assert "frame-ancestors" in csp
    assert "cdn.jsdelivr.net" not in csp


def test_root_html_avoids_external_cdn_scripts(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "cdn.jsdelivr.net" not in res.text
    assert "tailwindcss.com" not in res.text
    assert "fonts.googleapis.com" not in res.text


def test_index_html_avoids_double_quoted_inline_json_stringify_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert re.search(r"""on(?:click|keydown)\s*=\s*".*JSON\.stringify""", content) is None


def test_favicon_stays_public_even_after_user_registration(client):
    register = client.post(
        "/auth/register",
        json={
            "username": "infra-admin",
            "display_name": "Infra Admin",
            "email": "infra@example.com",
            "password": "InfraPass123!",
        },
    )
    assert register.status_code == 200

    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("image/")


# ── PWA endpoints ─────────────────────────────────────────────────────────────

def test_offline_html_accessible(client):
    res = client.get("/offline.html")
    assert res.status_code == 200


def test_manifest_json_accessible(client):
    res = client.get("/manifest.json")
    assert res.status_code == 200


def test_sw_js_has_service_worker_header(client):
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "service-worker-allowed" in res.headers


# ── CORS ──────────────────────────────────────────────────────────────────────

def test_cors_unknown_origin_not_reflected(client):
    res = client.options(
        "/billing/plans",
        headers={
            "Origin": "https://evil.attacker.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = res.headers.get("access-control-allow-origin", "")
    assert "evil.attacker.com" not in acao


# ── Rate limiting ─────────────────────────────────────────────────────────────

def test_rate_limit_login_triggers_429(client):
    """Pre-fill rate limit state then verify the next attempt is rejected."""
    try:
        import app.middleware.rate_limit as rl
    except ImportError:
        pytest.skip("rate_limit middleware not found")

    # TestClient peer IP is testclient (or 127.0.0.1); without TRUSTED_PROXIES,
    # XFF is ignored, so use the actual peer IP for rate-limit state.
    test_ip = "testclient"
    with rl._lock:
        rl._login_attempts[test_ip] = [time.time()] * rl.LOGIN_MAX_ATTEMPTS

    res = client.post(
        "/auth/login",
        json={"username": "x", "password": "y"},
    )
    with rl._lock:
        rl._login_attempts.pop(test_ip, None)

    assert res.status_code == 429
    data = res.json()
    assert data.get("code") == "TOO_MANY_REQUESTS" or "retry_after" in data


# ── Swagger in production ─────────────────────────────────────────────────────

def test_swagger_hidden_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-infra-tests-32chars!")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-infra-api-key")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    tc = TestClient(create_app(), raise_server_exceptions=False)
    assert tc.get("/docs").status_code == 404
    assert tc.get("/redoc").status_code == 404


# ── Tenant mismatch ───────────────────────────────────────────────────────────

def test_tenant_mismatch_blocked(tmp_path, monkeypatch):
    """JWT with tenant_a but X-Tenant-ID = tenant_b -> 403."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-infra-tests-32chars!")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    from app.services.auth_service import create_access_token
    tc = TestClient(create_app(), raise_server_exceptions=False)
    token = create_access_token("user1", "tenant_a", "member", "user1")
    res = tc.get(
        "/bundles",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "tenant_b"},
    )
    assert res.status_code == 403
    assert res.json().get("code") == "TENANT_MISMATCH"

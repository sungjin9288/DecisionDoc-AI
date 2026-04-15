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


def test_root_html_includes_ai_rank_roster(client):
    res = client.get("/")
    assert res.status_code == 200
    assert 'id="ai-rank-roster"' in res.text
    assert "관리자가 배정하는 업무 AI" in res.text
    assert "Executive Approver" in res.text
    assert "Proposal / BD Lead" in res.text
    assert "Delivery Lead / PM" in res.text
    assert 'id="ai-rank-status-action"' in res.text
    assert "업무 AI briefing" in res.text
    assert 'data-procurement-brief-action="' in res.text
    assert "procurement-role-brief-avatar" in res.text
    assert "Recent Activity" in res.text
    assert "procurement-role-brief-log-time" in res.text
    assert 'id="project-procurement-override-reason"' in res.text
    assert 'id="project-procurement-override-submit"' in res.text
    assert "Override / 예외 진행 사유" in res.text
    assert "quality loop input" in res.text
    assert "Recent override history" in res.text
    assert "이전 사유를 다시 쓰려면 항목을 클릭하세요." in res.text
    assert "procurement-override-history-list" in res.text
    assert "useProcurementOverrideHistoryItem" in res.text
    assert "procurement-override-guidance" in res.text
    assert "focusProcurementOverrideReason" in res.text
    assert 'data-procurement-override-history-index="' in res.text
    assert 'class="ai-rank-card proposal_bd"' in res.text
    assert 'class="ai-rank-card delivery_pm"' in res.text
    assert "제안/영업 AI" in res.text
    assert "PM AI" in res.text
    assert 'id="sketch-again-btn"' in res.text
    assert 'id="ppt-doc-btn"' in res.text
    assert 'id="sketch-pages"' in res.text
    assert 'id="sketch-page-cards"' in res.text
    assert 'id="results-storyboard"' in res.text
    assert 'id="results-storyboard-cards"' in res.text
    assert 'id="storyboard-refresh-btn"' in res.text
    assert 'id="storyboard-ppt-btn"' in res.text
    assert "slide-card is-clickable" in res.text
    assert "slide-card-badges" in res.text
    assert "slide-card-badge kind" in res.text
    assert "slide-card-badge readiness" in res.text
    assert "slide-card-meter" in res.text
    assert "slide-card-meter-fill" in res.text
    assert "slide-card-coverage-note" in res.text
    assert "coverage" in res.text
    assert "왜 이 점수인가?" in res.text
    assert "핵심어" in res.text
    assert "본문 반영" in res.text
    assert "연결 확인" in res.text
    assert "초안 기준" in res.text
    assert "doc-section-focus" in res.text
    assert "PPT 문서로 재구성" in res.text
    assert "페이지 스케치" in res.text


def test_root_html_exposes_profile_entry_and_removes_dark_toggle(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "⚙️ 내 정보" in res.text
    assert 'id="profile-modal"' in res.text
    assert 'id="profile-form"' in res.text
    assert "➕ 계정 직접 생성" in res.text
    assert 'id="location-user-create-modal"' in res.text
    assert 'id="location-user-edit-modal"' in res.text
    assert 'id="location-user-edit-form"' in res.text
    assert "🔗 초대 링크 발급" in res.text
    assert "권한/배정 수정" in res.text
    assert "최근 로그인" in res.text
    assert "활성 상태" in res.text
    assert "openLocationUserEditModal" in res.text
    assert 'id="dark-toggle"' not in res.text
    assert "toggleDark()" not in res.text
    assert "prompt('표시 이름을 입력하세요:'" not in res.text
    assert "prompt('활성 상태를 입력하세요 (active / inactive):'" not in res.text


def test_index_html_avoids_double_quoted_inline_json_stringify_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert re.search(r"""on(?:click|keydown)\s*=\s*".*JSON\.stringify""", content) is None


def test_nginx_configs_keep_sse_and_attachment_generation_on_long_timeouts():
    primary = open("nginx/nginx.conf", encoding="utf-8").read()
    ssl_variant = open("nginx/nginx.ssl.conf", encoding="utf-8").read()

    for content in (primary, ssl_variant):
        assert "/events" in content
        assert "with-attachments" in content
        assert "from-documents" in content
        assert "proxy_read_timeout" in content
        assert "300s" in content


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

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
    assert 'id="results-ppt-guide"' in res.text
    assert 'id="results-ppt-guide-meta"' in res.text
    assert 'id="results-ppt-guide-cards"' in res.text
    assert 'id="results-reference-guide"' in res.text
    assert 'id="results-reference-guide-meta"' in res.text
    assert 'id="results-reference-guide-cards"' in res.text
    assert 'id="visual-assets-btn"' in res.text
    assert 'id="results-visual-assets"' in res.text
    assert 'id="results-visual-assets-meta"' in res.text
    assert 'id="results-visual-assets-cards"' in res.text
    assert "PPT 페이지 설계" in res.text
    assert "이번 생성에 반영된 우선 참조" in res.text
    assert "생성된 시각자료" in res.text
    assert "slide_outline" in res.text
    assert "renderResultsPptGuide" in res.text
    assert "renderResultsAppliedReferences" in res.text
    assert "renderResultsVisualAssets" in res.text
    assert "generateVisualAssetsForResults" in res.text
    assert "_normalizeVisualAssets" in res.text
    assert "_persistCurrentVisualAssetsSnapshot" in res.text
    assert "_resetVisualAssetsForFreshResult" in res.text
    assert "_fetchJsonWithProviderRetry" in res.text
    assert "_extractRetryAfterSeconds" in res.text
    assert "_extractProviderErrorCode" in res.text
    assert "_waitForProviderRetry" in res.text
    assert "AI provider quota is exhausted." in res.text
    assert "buildEditedExportDocsPayload" in res.text
    assert "권장 시각자료" in res.text
    assert "시각자료 배치" in res.text
    assert "applied_references" in res.text
    assert "/generate/visual-assets" in res.text
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
    assert 'id="knowledge-promote-btn"' in res.text
    assert 'id="knowledge-promote-modal"' in res.text
    assert 'id="knowledge-promote-form"' in res.text
    assert 'id="knowledge-promote-submit-btn"' in res.text
    assert 'id="knowledge-metadata-modal"' in res.text
    assert 'id="knowledge-metadata-form"' in res.text
    assert 'id="knowledge-metadata-submit-btn"' in res.text
    assert "승인본으로 학습" in res.text
    assert "openKnowledgePromoteModal" in res.text
    assert "submitKnowledgePromotion" in res.text
    assert "openKnowledgeMetadataModal" in res.text
    assert "submitKnowledgeMetadataUpdate" in res.text
    assert "메타 수정" in res.text
    assert "ranked_documents" in res.text
    assert "우선 참조 후보" in res.text
    assert "선정 이유" in res.text
    assert "점수 구성" in res.text
    assert "knowledge_scope" in res.text
    assert "_formatKnowledgeScope" in res.text
    assert "참조 Scope" in res.text
    assert "knowledge-context-bundle" in res.text
    assert "knowledge-context-org" in res.text
    assert "knowledge-context-workflow" in res.text
    assert "_buildKnowledgeContextPreviewDefaults" in res.text
    assert "applied_scope" in res.text
    assert "ranking_summary" in res.text
    assert "Ranking Summary" in res.text
    assert "서버 적용 필터" in res.text
    assert "knowledge-temporal-graph-btn" in res.text
    assert "knowledge-temporal-graph-modal" in res.text
    assert "previewKnowledgeTemporalGraph" in res.text
    assert "knowledge-temporal-graph-bundle" in res.text
    assert "knowledge-temporal-graph-org" in res.text
    assert "knowledge-temporal-graph-workflow" in res.text
    assert "_readKnowledgeTemporalGraphInputs" in res.text
    assert "요청 필터" in res.text
    assert "copyKnowledgeTemporalGraphJson" in res.text
    assert "downloadKnowledgeTemporalGraphJson" in res.text
    assert "_knowledgeTemporalGraphLastData" in res.text
    assert "graph 관계" in res.text
    assert "graph boost" in res.text
    assert "Temporal Graph Summary" in res.text
    assert "Relationships" in res.text
    assert "_formatKnowledgeMatchedTerms" in res.text
    assert "matched terms" in res.text
    assert "Matched Terms" in res.text
    assert "report_workflow_id" in res.text
    assert "참조 문서:" in res.text
    assert "_formatAppliedReferenceSummary" in res.text
    assert "openHistoryReferenceModal" in res.text
    assert "openServerHistoryEntry" in res.text
    assert "history-reference-modal" in res.text
    assert "히스토리 참조 근거" in res.text
    assert "근거 보기" in res.text
    assert "history-open-server-btn" in res.text
    assert "promoteServerHistoryEntry" in res.text
    assert "history-promote-server-btn" in res.text
    assert "history-promote-btn" in res.text
    assert "buildPostDeployProviderRouteSummary" in res.text
    assert "buildPostDeploySmokeFailureSummary" in res.text
    assert "buildPostDeploySmokeResultsSummary" in res.text
    assert "getPostDeploySmokeResultsAvailability" in res.text
    assert "buildPostDeploySmokeResultsSummary(details, { title: 'Smoke checks', showEmpty: true })" in res.text
    assert "{ title: 'Smoke checks', showEmpty: true }" in res.text
    assert "{ compact: true, title: 'Smoke checks', showEmpty: true }" in res.text
    assert "buildOpsPostDeploySmokeResultDiffRows" in res.text
    assert "getPostDeploySmokeFailureState" in res.text
    assert "getPostDeploySmokeResults" in res.text
    assert "parsePostDeploySmokeResultLine" in res.text
    assert "normalizePostDeploySmokeResultDetail" in res.text
    assert "resetOpsPostDeployDetailCache" in res.text
    assert "buildOpsPostDeployProviderRouteDiffRows" in res.text
    assert "getPostDeployRouteCheckMeta" in res.text
    assert "ops-post-deploy-provider-routes" in res.text
    assert "ops-post-deploy-smoke-failure" in res.text
    assert "ops-post-deploy-smoke-failure-badge" in res.text
    assert "ops-post-deploy-smoke-results" in res.text
    assert "ops-post-deploy-smoke-results-empty" in res.text
    assert "ops-post-deploy-smoke-results-count" in res.text
    assert "ops-post-deploy-smoke-results-diff-row" in res.text
    assert "ops-post-deploy-provider-route-status" in res.text
    assert "ops-post-deploy-provider-route-diff-row" in res.text
    assert "ops-post-deploy-provider-policy" in res.text
    assert "ops-post-deploy-provider-policy-status" in res.text
    assert "ops-post-deploy-provider-policy-issues" in res.text
    assert "ops-post-deploy-provider-policy-diff-row" in res.text
    assert "Provider route" in res.text
    assert "Provider route 차이" in res.text
    assert "Quality-first readiness" in res.text
    assert "Quality-first 차이" in res.text
    assert "Smoke failure" in res.text
    assert "Smoke checks" in res.text
    assert "Smoke checks 차이" in res.text
    assert "저장된 smoke summary가 없습니다." in res.text
    assert "legacy report라 저장된 smoke summary가 없습니다." in res.text
    assert "buildPostDeployProviderPolicySummary" in res.text
    assert "buildOpsPostDeployProviderPolicyDiffRows" in res.text
    assert "getPostDeployPolicyCheckMeta" in res.text
    assert "resetOpsPostDeployDetailCache();" in res.text
    assert "knowledge-promote-docs-btn" in res.text
    assert "openPromotedKnowledgeDocsModal" in res.text
    assert "학습 문서 보기" in res.text
    assert "학습 문서:" in res.text
    assert "knowledge_documents" in res.text
    assert "_markLocalHistoryPromoted" in res.text
    assert "_renderHistoryPromotionBadge" in res.text
    assert "_applyKnowledgePromotionState" in res.text
    assert "visual_assets: _normalizeVisualAssets(result.visual_assets)" in res.text
    assert "lastVisualAssets = _normalizeVisualAssets(result.visual_assets)" in res.text
    assert "lastVisualAssets   = _normalizeVisualAssets(item.visual_assets)" in res.text
    assert "_syncCurrentVisualAssetsToServerHistory" in res.text
    assert "/visual-assets" in res.text
    assert "승인본 학습 완료" in res.text
    assert "이미 학습된 승인본" in res.text
    assert "already_promoted" in res.text
    assert "승인본 학습" in res.text
    assert "gold" in res.text
    assert "수주" in res.text


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
    assert "exportDocument('pptx',  'ppt-btn'" in res.text
    assert "downloadBatchResult('${bundleId}','pptx')" in res.text
    assert "downloadBatchResult('${bundleId}','hwp')" in res.text


def test_index_html_expands_attachment_accept_lists_for_structured_docs():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert ".json,.jsonl,.ndjson" in content
    assert ".yaml,.yml" in content
    assert ".xml,.html,.htm,.rtf" in content
    assert ".odt,.ods,.odp,.zip" in content
    assert ".png,.jpg,.jpeg,.webp" in content


def test_index_html_blocks_legacy_hwp_uploads_in_generation_flows():
    content = open("app/static/index.html", encoding="utf-8").read()
    attachment_match = re.search(r'<input type="file" id="f-attachments"[^>]*accept="([^"]+)"', content)
    from_documents_match = re.search(
        r'<input type="file" id="from-documents-file-input"[^>]*accept="([^"]+)"',
        content,
    )
    assert attachment_match is not None
    assert from_documents_match is not None
    attachment_accept = attachment_match.group(1)
    from_documents_accept = from_documents_match.group(1)
    assert "LEGACY_BINARY_HWP_WARNING" in content
    assert "filterLegacyBinaryHwpFiles" in content
    assert "구형 .hwp 파일은 직접 분석하지 못합니다." in content
    assert ".hwpx" in attachment_accept
    assert ".hwpx" in from_documents_accept
    assert ".hwp," not in attachment_accept and not attachment_accept.endswith(".hwp")
    assert ".hwp," not in from_documents_accept and not from_documents_accept.endswith(".hwp")


def test_index_html_rfp_parse_uses_auth_headers():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert re.search(
        r"fetch\('/attachments/parse-rfp',\s*\{\s*method:\s*'POST',\s*headers:\s*getAuthHeaders\(\),\s*body:\s*fd,?\s*\}\)",
        content,
    )


def test_index_html_avoids_double_quoted_inline_json_stringify_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert re.search(r"""on(?:click|keydown)\s*=\s*".*JSON\.stringify""", content) is None


def test_nginx_configs_keep_sse_and_attachment_generation_on_long_timeouts():
    primary = open("nginx/nginx.conf", encoding="utf-8").read()
    ssl_variant = open("nginx/nginx.ssl.conf", encoding="utf-8").read()

    for content in (primary, ssl_variant):
        assert "/events" in content
        assert "pptx" in content
        assert "export-edited" in content
        assert "with-attachments" in content
        assert "from-documents" in content
        assert "proxy_read_timeout" in content
        assert "600s" in content
        assert "300s" in content
        assert re.search(r"with-attachments[\s\S]*proxy_read_timeout\s+600s;", content)
        assert re.search(r"from-documents[\s\S]*proxy_read_timeout\s+600s;", content)
        assert re.search(r"location\s*/\s*\{[\s\S]*proxy_read_timeout\s+300s;", content)


def test_dockerfile_sets_shared_playwright_browser_path_for_non_root_runtime():
    dockerfile = open("Dockerfile", encoding="utf-8").read()
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile
    assert "mkdir -p /app/data /ms-playwright" in dockerfile
    assert "chown -R decisiondoc:decisiondoc /app /ms-playwright" in dockerfile


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

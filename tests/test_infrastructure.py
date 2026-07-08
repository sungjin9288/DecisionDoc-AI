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

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import tomllib

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
    assert "frame-ancestors" in csp
    assert "cdn.jsdelivr.net" not in csp
    # Non-HTML responses carry no nonce (nothing inline to protect).
    assert "'nonce-" not in csp


def _script_src(csp: str) -> str:
    """Return the script-src directive segment from a CSP header string."""
    for part in csp.split(";"):
        if "script-src" in part:
            return part.strip()
    return ""


def _extract_csp_nonce(csp: str) -> str | None:
    m = re.search(r"'nonce-([^']+)'", csp)
    return m.group(1) if m else None


@pytest.fixture
def nonce_client(client, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_CSP_NONCE_ENFORCED", "1")
    return client


def test_csp_nonce_enabled_by_default(client):
    """Default HTML responses carry nonce-backed script-src without unsafe-inline."""
    res = client.get("/")
    assert res.status_code == 200
    csp = res.headers.get("content-security-policy", "")
    header_nonce = _extract_csp_nonce(csp)
    assert header_nonce
    assert "'unsafe-inline'" not in _script_src(csp)
    assert f'<script nonce="{header_nonce}">' in res.text


def test_csp_nonce_can_be_disabled_for_local_diagnostics(client, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_CSP_NONCE_ENFORCED", "0")
    res = client.get("/")
    assert res.status_code == 200
    csp = res.headers.get("content-security-policy", "")
    assert "'nonce-" not in csp
    assert "'unsafe-inline'" in _script_src(csp)
    assert '<script nonce="' not in res.text


def test_csp_root_has_nonce_and_matches_inline_scripts(nonce_client):
    """(a)+(b): served HTML carries a nonce that matches every inline <script>."""
    res = nonce_client.get("/")
    assert res.status_code == 200
    csp = res.headers.get("content-security-policy", "")
    header_nonce = _extract_csp_nonce(csp)
    assert header_nonce, "CSP script-src must include a 'nonce-...' source"

    # Every inline <script> in the served HTML must carry the header nonce.
    html_nonces = re.findall(r'<script nonce="([^"]+)"', res.text)
    assert html_nonces, "index.html must contain inline <script> tags with a nonce"
    assert all(n == header_nonce for n in html_nonces)

    # No un-nonced bare inline <script> should remain in the served response.
    assert "<script>" not in res.text


def test_csp_nonce_differs_per_request(nonce_client):
    """(c): each request receives a distinct, freshly generated nonce."""
    n1 = _extract_csp_nonce(nonce_client.get("/").headers.get("content-security-policy", ""))
    n2 = _extract_csp_nonce(nonce_client.get("/").headers.get("content-security-policy", ""))
    assert n1 and n2
    assert n1 != n2


def test_csp_offline_page_has_nonce(nonce_client):
    """The PWA offline fallback is served with a per-request nonce too."""
    res = nonce_client.get("/offline.html")
    assert res.status_code == 200
    assert _extract_csp_nonce(res.headers.get("content-security-policy", ""))


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
    assert "search backend" in res.text
    assert "backend=" in res.text
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
    assert "_knowledgeTemporalGraphLastFilter" in res.text
    assert "_buildKnowledgeTemporalGraphQuery" in res.text
    assert "_filenameFromContentDisposition" in res.text
    assert "/temporal-graph/export" in res.text
    assert "Artifact 다운로드" in res.text
    assert "관계 그래프 artifact를 다운로드했습니다." in res.text
    assert "knowledge-temporal-graph-visual" in res.text
    assert "_renderKnowledgeTemporalGraphVisual" in res.text
    assert "_knowledgeGraphTypeMeta" in res.text
    assert "_truncateKnowledgeGraphLabel" in res.text
    assert "Graph View" in res.text
    assert "Knowledge temporal graph visual" in res.text
    assert "knowledgeGraphArrow" in res.text
    assert "아직 연결된 Knowledge 관계가 없습니다" in res.text
    assert "승인본 학습 또는 참조 문서를 등록하면" in res.text
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


def test_root_html_exposes_report_workflow_quality_artifact_ui(client):
    res = client.get("/")
    assert res.status_code == 200
    assert 'id="rw-quality-artifact-panel"' in res.text
    assert 'id="rw-quality-reviewer"' in res.text
    assert 'id="rw-quality-after-summary"' in res.text
    assert 'id="rw-quality-forbidden-scan"' in res.text
    assert 'id="rw-quality-privacy-scan"' in res.text
    assert 'id="rw-quality-human-status"' in res.text
    assert 'id="rw-quality-result"' in res.text
    assert 'id="rw-quality-artifact-summary"' in res.text
    assert "REPORT_WORKFLOW_QUALITY_DIMENSIONS" in res.text
    assert "buildReportWorkflowQualityCorrectionPayload" in res.text
    assert "previewReportWorkflowQualityArtifact" in res.text
    assert "saveReportWorkflowQualityArtifact" in res.text
    assert "loadReportWorkflowQualityArtifacts" in res.text
    assert "downloadReportWorkflowQualityArtifacts" in res.text
    assert "learning/correction-artifact/preview" in res.text
    assert "learning/correction-artifact" in res.text
    assert "learning/correction-artifacts/export" in res.text
    assert "Ready JSONL" in res.text
    assert "metadata-only before/after 교정 데이터" in res.text
    assert "Provider fine-tune이나 dataset upload는 실행하지 않습니다." in res.text
    assert "승인된 기획안/장표 원문을 학습 후보로 저장" not in res.text


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
    assert 'data-batch-format="pptx"' in res.text
    assert 'data-batch-format="hwp"' in res.text
    assert "downloadBatchResult(target.dataset.batchDownload || '', target.dataset.batchFormat || '')" in res.text


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


def test_index_html_document_ops_downloads_reviewed_sft_jsonl_exports():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Reviewed SFT JSONL" in content
    assert "/api/agent/document-ops/trajectories/reviewed-sft-exports?" in content
    assert "/api/agent/document-ops/trajectories/reviewed-sft-exports/${encodeURIComponent(filename)}/download" in content
    assert "getOpsAccessHeaders()" in content
    assert "accepted-only" in content


def test_index_html_document_ops_supports_develop_quality_improvement_mode():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Develop 품질 개선" in content
    assert "develop_quality_improvement" in content
    assert "develop-document-improver" in content
    assert "current_draft: taskType === 'develop_quality_improvement' ? goal : ''" in content
    assert "renderDocumentOpsImprovementSummary(data)" in content
    assert "Quality critique" in content
    assert "Revision tasks" in content


def test_index_html_report_workflow_exposes_develop_quality_preview():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "runReportWorkflowDevelopPreview" in content
    assert "/develop-quality/preview" in content
    assert "Develop 품질 개선 preview" in content
    assert "capture_trajectory: false" in content
    assert "applyReportWorkflowDevelopPreviewToQualityArtifact" in content
    assert "applyReportWorkflowDevelopPreviewAndPreviewArtifact" in content
    assert "품질 artifact에 반영" in content
    assert "반영 후 Artifact preview" in content
    assert "previewReportWorkflowQualityArtifact(workflowId)" in content
    assert "저장 전 reviewer checklist" in content
    assert "reportWorkflowQualityChecklistItems" in content
    assert "REPORT_WORKFLOW_QUALITY_GATE_MINIMUMS" in content
    assert "REPORT_WORKFLOW_QUALITY_PLACEHOLDER_MARKERS" in content
    assert "Placeholder scan" in content
    assert "focusReportWorkflowQualityField" in content
    assert "reportWorkflowQualityFieldIdFromValidationError" in content
    assert "reportWorkflowQualityFocusedField" in content
    assert "수정 위치" in content
    assert "Review packet JSON" in content
    assert "buildReportWorkflowQualityReviewPacket" in content
    assert "decisiondoc_report_quality_review_packet.v1" in content
    assert "preview_artifact: preview?.artifact || null" in content
    assert "server_file_written: false" in content
    assert "provider_fine_tune_api_call_authorized: false" in content
    assert "initReportWorkflowQualityChecklist" in content
    assert "자동 승인이나 저장 없이" in content
    assert "rw-quality-change-issue" in content
    assert "rw-quality-after-summary" in content
    assert "develop_quality_improvement" in content
    assert "develop-document-improver" in content


def test_index_html_document_ops_shows_read_only_training_readiness():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Readiness Summary" in content
    assert "loadDocumentOpsTrainingReadiness()" in content
    assert "/api/agent/document-ops/trajectories/training-readiness?limit=20" in content
    assert "read-only · no training · no upload" in content
    assert "provider_job_started_count" in content


def test_index_html_document_ops_shows_dry_run_training_plan_preview():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Execution Plan Preview" in content
    assert "previewDocumentOpsTrainingPlan()" in content
    assert "/api/agent/document-ops/trajectories/training-plan/preview?" in content
    assert "provider-agnostic · dry-run · no provider API calls · no upload" in content
    assert "Execution steps" in content


def test_index_html_document_ops_shows_training_execution_request_records():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Execution Request Records" in content
    assert "requestDocumentOpsTrainingExecution()" in content
    assert "/api/agent/document-ops/trajectories/training-execution-requests" in content
    assert "record-only · two-person guard · no training · no upload · no provider calls" in content
    assert "two_person_guard_satisfied" in content


def test_index_html_document_ops_shows_pre_execution_audit_checklist_export():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Pre-Execution Audit Checklist" in content
    assert "loadDocumentOpsTrainingAuditChecklist()" in content
    assert "exportDocumentOpsTrainingAudit()" in content
    assert "/api/agent/document-ops/trajectories/training-audit/checklist?" in content
    assert "/api/agent/document-ops/trajectories/training-audit/export" in content
    assert "human-review packet · no training · no upload · no provider calls" in content


def test_index_html_document_ops_shows_training_governance_dashboard_summary():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Governance Dashboard Summary" in content
    assert "loadDocumentOpsTrainingGovernanceSummary()" in content
    assert "/api/agent/document-ops/trajectories/training-governance/summary?" in content
    assert "read-only aggregate · no training · no upload · no provider calls" in content
    assert "No-side-effect guard" in content


def test_index_html_document_ops_shows_reviewer_signoff_summary():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Reviewer Sign-Off Summary" in content
    assert "loadDocumentOpsReviewerSignoffSummary()" in content
    assert "downloadDocumentOpsReviewerSignoffSummary()" in content
    assert 'id="document-ops-download-fallback"' in content
    assert "/api/agent/document-ops/trajectories/reviewer-signoff/summary?" in content
    assert "/api/agent/document-ops/trajectories/reviewer-signoff/summary/download?" in content
    assert "read-only sign-off evidence · no training · no upload · no provider calls" in content
    assert "Reviewer sign-off summary JSON" in content
    assert "fallbackContainerId: 'document-ops-download-fallback'" in content
    assert "actual_reviewer_approval_recorded_by_summary" in content


def test_index_html_document_ops_shows_training_adapter_contract_stub():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Provider Adapter Contract" in content
    assert "loadDocumentOpsTrainingAdapterContract()" in content
    assert "/api/agent/document-ops/trajectories/training-provider-adapter/contract?" in content
    assert "stub-only · disabled by default · no training · no upload · no provider calls" in content
    assert "Forbidden in stub" in content


def test_index_html_document_ops_shows_training_execution_rehearsal():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Training Execution Rehearsal" in content
    assert "loadDocumentOpsTrainingRehearsal()" in content
    assert "/api/agent/document-ops/trajectories/training-provider-adapter/rehearsal?" in content
    assert "dry-run rehearsal · validates governance artifacts · no training · no upload · no provider calls" in content
    assert "side_effect" in content


def test_index_html_exports_current_generated_docs_before_regenerating():
    content = open("app/static/index.html", encoding="utf-8").read()
    export_blob_fn = re.search(
        r"async function _buildExportedBlob\(format\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    export_document_fn = re.search(
        r"async function exportDocument\(format, btnId, icon, ext, label\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    assert export_blob_fn is not None
    assert export_document_fn is not None
    assert "generatedDocs.length === 0" in export_blob_fn.group("body")
    assert "preferEdited: hasEdits" in export_blob_fn.group("body")
    assert "fetch('/generate/export-edited'" in export_blob_fn.group("body")
    assert "No rendered docs yet" in export_document_fn.group("body")
    assert "const endpoint = { docx: '/generate/docx'" in export_document_fn.group("body")


def test_index_html_keeps_blob_url_and_shows_download_fallback():
    content = open("app/static/index.html", encoding="utf-8").read()
    trigger_fn = re.search(
        r"function _triggerBrowserDownload\(blob, filename, label, options = \{\}\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    export_document_fn = re.search(
        r"async function exportDocument\(format, btnId, icon, ext, label\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    assert trigger_fn is not None
    assert export_document_fn is not None
    assert "EXPORT_DOWNLOAD_URL_TTL_MS = 5 * 60 * 1000" in content
    assert "export-download-fallback" in content
    assert "_showExportDownloadFallback(url, filename, label, options?.fallbackContainerId)" in trigger_fn.group("body")
    assert "URL.revokeObjectURL(url)" not in export_document_fn.group("body")
    assert "_triggerBrowserDownload(blob, filename, label)" in export_document_fn.group("body")


def test_index_html_result_download_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    block_start = content.index("function renderDownloadButtons(requestId, title)")
    block_end = content.index("async function exportZip(requestId)", block_start)
    block = content[block_start:block_end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'id="result-docx-btn" type="button" data-result-export="docx"',
        'id="result-hwp-btn" type="button" data-result-export="hwp"',
        'id="result-pdf-btn" type="button" data-result-export="pdf"',
        'id="result-excel-btn" type="button" data-result-export="excel"',
        'data-result-export-zip data-request-id="${safeId}"',
        'data-result-share data-request-id="${safeId}" data-title="${safeTitle}"',
    ):
        assert marker in block
    assert "onclick=\"exportDocument" not in block
    assert "onclick=\"exportZip" not in block
    assert "onclick=\"shareDocument" not in block


def test_index_html_result_download_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "const RESULT_EXPORT_ACTIONS = {",
        "docx: { format: 'docx', buttonId: 'result-docx-btn'",
        "function wireResultDownloadActions(container)",
        "wireResultDownloadActions(container);",
        "container.querySelectorAll('[data-result-export]').forEach",
        "const action = RESULT_EXPORT_ACTIONS[btn.dataset.resultExport || ''];",
        "exportDocument(action.format, action.buttonId, action.icon, action.extension, action.label);",
        "container.querySelector('[data-result-export-zip]')?.addEventListener('click', event => {",
        "exportZip(event.currentTarget.dataset.requestId || '');",
        "container.querySelector('[data-result-share]')?.addEventListener('click', event => {",
        "shareDocument(target.dataset.requestId || '', target.dataset.title || '');",
    ):
        assert marker in content


def test_index_html_recovers_or_resets_invalid_auth_session_on_401():
    content = open("app/static/index.html", encoding="utf-8").read()
    retry_fetch_fn = re.search(
        r"async function _fetchJsonWithProviderRetry\(fetcher,[\s\S]*?\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    hydrate_fn = re.search(
        r"async function hydrateCurrentUserProfile\(\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    parse_error_fn = re.search(
        r"async function parseApiErrorResponse\(res\) \{(?P<body>[\s\S]*?)\n  \}",
        content,
    )
    assert retry_fetch_fn is not None
    assert hydrate_fn is not None
    assert parse_error_fn is not None
    assert "function handleInvalidAuthSession" in content
    assert "async function recoverAuthSessionOnce" in content
    assert "localStorage.removeItem('dd_access_token')" in content
    assert "localStorage.removeItem('dd_refresh_token')" in content
    assert "res.status === 401" in retry_fetch_fn.group("body")
    assert "await recoverAuthSessionOnce()" in retry_fetch_fn.group("body")
    assert "handleInvalidAuthSession()" in retry_fetch_fn.group("body")
    assert "retry = await fetch('/auth/me'" in hydrate_fn.group("body")
    assert "handleInvalidAuthSession()" in parse_error_fn.group("body")


def test_index_html_rfp_parse_uses_auth_headers():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert re.search(
        r"fetch\('/attachments/parse-rfp',\s*\{\s*method:\s*'POST',\s*headers:\s*getAuthHeaders\(\),\s*body:\s*fd,?\s*\}\)",
        content,
    )


def test_index_html_avoids_double_quoted_inline_json_stringify_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert re.search(r"""on(?:click|keydown)\s*=\s*".*JSON\.stringify""", content) is None


def test_index_html_page_tabs_use_event_listeners_not_inline_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    nav_match = re.search(r'<nav id="page-nav"[\s\S]*?</nav>', content)
    assert nav_match is not None
    nav = nav_match.group(0)

    assert re.search(r"\son[a-zA-Z]+\s*=", nav) is None
    assert "document.querySelectorAll('.page-tab').forEach" in content
    assert "window.switchPage(btn.dataset.page || 'generate')" in content


def test_index_html_local_llm_setup_guide_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    setup_start = content.index('<div class="setup-tabs">')
    setup_end = content.index('<div id="local-llm-guide-content"></div>')
    setup_tabs = content[setup_start:setup_end]
    guide_start = content.index("function _showSetupGuide")
    guide_end = content.index("function _copyEnvConfig")
    guide_block = content[guide_start:guide_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", setup_tabs) is None
    assert 'data-setup-guide="ollama"' in setup_tabs
    assert 'data-setup-guide="vllm"' in setup_tabs
    assert 'data-setup-guide="lmstudio"' in setup_tabs
    assert "btn.dataset.setupGuide || 'ollama'" in content
    assert re.search(r"\son[a-zA-Z]+\s*=", guide_block) is None
    assert "data-copy-env-config" in guide_block
    assert "_copyEnvConfig(event.currentTarget)" in guide_block


def test_index_html_sso_tabs_use_event_listeners_not_inline_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    tabs_match = re.search(r'<div class="sso-tabs"[\s\S]*?</div>', content)
    assert tabs_match is not None
    tabs = tabs_match.group(0)

    assert re.search(r"\son[a-zA-Z]+\s*=", tabs) is None
    assert 'data-provider="disabled"' in tabs
    assert 'data-provider="ldap"' in tabs
    assert 'data-provider="saml"' in tabs
    assert 'data-provider="gcloud"' in tabs
    assert "tab.addEventListener('click'" in content
    assert "switchSSOProvider(tab.dataset.provider || 'disabled')" in content


def test_index_html_header_menu_and_notifications_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    hero_start = content.index('<div class="hero">')
    hero_end = content.index('<div id="tenant-selector">')
    header_block = content[hero_start:hero_end]
    notification_start = content.index("function renderNotifications")
    notification_end = content.index("async function handleNotifClick")
    notification_block = content[notification_start:notification_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", header_block) is None
    assert 'data-user-menu-action="profile"' in header_block
    assert 'data-user-menu-action="logout"' in header_block
    assert "data-notif-mark-all-read" in header_block
    assert "$id('user-info')?.addEventListener('click', toggleUserMenu)" in content
    assert "openMyProfileModal();" in content
    assert "logout();" in content
    assert "$id('notif-bell')?.addEventListener('click', toggleNotifPanel)" in content
    assert "document.querySelector('[data-notif-mark-all-read]')?.addEventListener('click', markAllNotifRead)" in content
    assert re.search(r"\son[a-zA-Z]+\s*=", notification_block) is None
    assert 'data-notification-id="${escapeHtml(n.notification_id)}"' in notification_block
    assert "item.addEventListener('click', () => handleNotifClick(item.dataset.notificationId || ''))" in notification_block


def test_index_html_profile_modal_uses_event_listeners_not_inline_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    modal_start = content.index('<div id="profile-modal"')
    modal_end = content.index('<svg class="wave"')
    modal_block = content[modal_start:modal_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", modal_block) is None
    assert modal_block.count("data-profile-close") == 2
    assert '<form id="profile-form" class="profile-form">' in modal_block
    assert "$id('profile-modal')?.addEventListener('click'" in content
    assert "event.target === event.currentTarget" in content
    assert "document.querySelectorAll('[data-profile-close]').forEach" in content
    assert "$id('profile-form')?.addEventListener('submit', saveMyProfile)" in content


def test_index_html_ai_rank_cards_use_event_listeners_not_inline_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()
    roster_start = content.index('<section id="ai-rank-roster"')
    roster_end = content.index('<!-- Step progress indicator -->')
    roster_block = content[roster_start:roster_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", roster_block) is None
    assert 'data-ai-rank="executive"' in roster_block
    assert 'data-ai-rank="proposal_bd"' in roster_block
    assert 'data-ai-rank="delivery_pm"' in roster_block
    assert "card.addEventListener('click', () => activateAiRank(card.dataset.aiRank))" in content
    assert "card.addEventListener('keydown', event =>" in content
    assert "event.key !== 'Enter' && event.key !== ' '" in content
    assert "$id('ai-rank-status-action')?.addEventListener('click', runActiveAiRankAction)" in content


def test_index_html_generation_quick_controls_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    controls_start = content.index("<!-- Server-side generation history section -->")
    controls_end = content.index("<!-- Template controls (PU-1) -->")
    controls_block = content[controls_start:controls_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", controls_block) is None
    assert 'id="history-section-close"' in controls_block
    assert 'id="inline-style-select"' in controls_block
    assert 'id="project-select"' in controls_block
    assert 'id="knowledge-badge"' in controls_block
    assert 'id="create-project-inline-btn"' in controls_block
    assert 'data-g2b-tab="url"' in controls_block
    assert 'data-g2b-tab="search"' in controls_block
    assert 'data-g2b-tab="bookmarks"' in controls_block
    assert "data-g2b-fetch" in controls_block
    assert "data-g2b-search" in controls_block
    assert "data-open-from-documents" in controls_block
    assert "data-open-from-pdf" in controls_block
    assert "$id('history-section-close')?.addEventListener('click'" in content
    assert "$id('inline-style-select')?.addEventListener('change'" in content
    assert "$id('project-select')?.addEventListener('change'" in content
    assert "$id('knowledge-badge')?.addEventListener('click', () => switchPage('knowledge-page'))" in content
    assert "$id('create-project-inline-btn')?.addEventListener('click', showCreateProjectModal)" in content
    assert "btn.addEventListener('click', () => switchG2BTab(btn.dataset.g2bTab || 'url', btn))" in content
    assert "fetchG2BAnnouncement(event.currentTarget)" in content
    assert "searchG2B(event.currentTarget)" in content
    assert "document.querySelector('[data-open-from-documents]')?.addEventListener('click', openFromDocumentsModal)" in content
    assert "document.querySelector('[data-open-from-pdf]')?.addEventListener('click', openFromPdfModal)" in content
    assert "$id('rfp-parse-btn')?.addEventListener('click', parseRFP)" in content


def test_index_html_g2b_dynamic_results_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    search_start = content.index("function _renderG2BSearchResults")
    search_end = content.index("async function oneClickProposal", search_start)
    search_block = content[search_start:search_end]
    bookmarks_start = content.index("async function loadG2BBookmarks")
    bookmarks_end = content.index("async function removeG2BBookmark", bookmarks_start)
    bookmarks_block = content[bookmarks_start:bookmarks_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", search_block) is None
    assert re.search(r"\son[a-zA-Z]+\s*=", bookmarks_block) is None
    for marker in (
        "data-g2b-select-bid",
        "data-g2b-oneclick-bid",
        "data-g2b-bookmark-bid",
        "data-g2b-bookmark-select",
        "data-g2b-bookmark-remove",
    ):
        assert marker in content


def test_index_html_g2b_dynamic_result_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "function wireG2BSearchResultActions(container) {" in content
    assert "container.querySelectorAll('[data-g2b-select-bid]').forEach" in content
    assert "selectG2BResult(item.dataset.g2bSelectBid || '')" in content
    assert "item.addEventListener('keydown', event =>" in content
    assert "event.key !== 'Enter' && event.key !== ' '" in content
    assert "oneClickProposal(btn.dataset.g2bOneclickBid || '')" in content
    assert "toggleG2BBookmark(btn.dataset.g2bBookmarkBid || '', btn)" in content
    assert "function wireG2BBookmarkActions(container) {" in content
    assert "selectG2BResult(btn.dataset.g2bBookmarkSelect || '')" in content
    assert "removeG2BBookmark(btn.dataset.g2bBookmarkRemove || '', btn)" in content


def test_index_html_batch_results_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    block_start = content.index("function createBatchResultsPanel")
    block_end = content.index("function viewBatchResult", block_start)
    block = content[block_start:block_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", block) is None
    for marker in (
        "data-batch-close",
        "data-batch-view",
        "data-batch-download",
        "data-batch-format=\"docx\"",
        "data-batch-format=\"pdf\"",
        "data-batch-format=\"pptx\"",
        "data-batch-format=\"hwp\"",
    ):
        assert marker in block


def test_index_html_batch_result_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "panel.querySelector('[data-batch-close]')?.addEventListener('click', () => {" in content
    assert "panel.style.display = 'none';" in content
    assert "function wireBatchResultActions(container) {" in content
    assert "container.querySelector('[data-batch-view]')?.addEventListener('click', event => {" in content
    assert "viewBatchResult(event.currentTarget.dataset.batchView || '');" in content
    assert "container.querySelectorAll('[data-batch-download]').forEach" in content
    assert "downloadBatchResult(target.dataset.batchDownload || '', target.dataset.batchFormat || '');" in content


def test_index_html_bundle_empty_and_related_modal_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    bundle_start = content.index("function renderBundleGrid")
    bundle_end = content.index("/* ── Select bundle", bundle_start)
    bundle_block = content[bundle_start:bundle_end]
    related_start = content.index("function _showRelatedModal")
    related_end = content.index("window._applyRelatedBundle", related_start)
    related_block = content[related_start:related_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", bundle_block) is None
    assert re.search(r"\son[a-zA-Z]+\s*=", related_block) is None
    assert "data-bundle-refresh" in bundle_block
    assert "data-related-bundle-id" in related_block
    assert 'id="related-close-btn" type="button"' in related_block


def test_index_html_bundle_empty_and_related_modal_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "grid.querySelector('[data-bundle-refresh]')?.addEventListener('click', loadBundles)" in content
    assert "modal.querySelector('#related-close-btn')?.addEventListener('click', close)" in content
    assert "modal.querySelectorAll('[data-related-bundle-id]').forEach" in content
    assert "window._applyRelatedBundle(item.dataset.relatedBundleId || '')" in content
    assert "item.addEventListener('mouseenter', () => {" in content
    assert "item.style.borderColor = 'var(--p1,#6366f1)';" in content
    assert "item.addEventListener('mouseleave', () => {" in content
    assert "item.style.borderColor = 'var(--border,#e5e7eb)';" in content


def test_index_html_rfp_result_modal_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    modal_start = content.index("function showRFPParseResult")
    modal_end = content.index("function rfpFillField")
    modal_block = content[modal_start:modal_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", modal_block) is None
    assert "data-rfp-fill-target" in modal_block
    assert "data-rfp-fill-value" in modal_block
    assert "data-rfp-close" in modal_block
    assert "overlay.querySelectorAll('[data-rfp-fill-target]').forEach" in modal_block
    assert "rfpFillField(btn.dataset.rfpFillTarget || '', btn.dataset.rfpFillValue || '', btn)" in modal_block
    assert "overlay.querySelector('[data-rfp-close]')?.addEventListener('click', () => overlay.remove())" in modal_block


def test_index_html_knowledge_page_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    page_start = content.index('<section id="knowledge-page"')
    page_end = content.index("<!-- ── 단계형 보고서 워크플로우")
    page_block = content[page_start:page_end]

    assert re.search(r"\son[a-zA-Z]+\s*=", page_block) is None
    assert 'id="knowledge-project-select"' in page_block
    assert 'id="knowledge-project-refresh-btn"' in page_block
    assert 'id="knowledge-upload-area"' in page_block
    assert 'id="knowledge-file-input"' in page_block
    assert 'id="knowledge-file-pick-btn"' in page_block
    assert 'id="knowledge-context-preview-btn"' in page_block
    assert 'id="knowledge-temporal-graph-btn"' in page_block
    assert 'data-close-modal="knowledge-context-modal"' in page_block
    assert 'data-close-modal="knowledge-temporal-graph-modal"' in page_block
    assert "data-preview-knowledge-context-inputs" in page_block
    assert "data-preview-knowledge-graph-inputs" in page_block
    assert "data-copy-knowledge-graph-json" in page_block
    assert "data-download-knowledge-graph-json" in page_block
    assert "data-knowledge-promote-close" in page_block
    assert "data-knowledge-metadata-close" in page_block
    assert '<form id="knowledge-promote-form">' in page_block
    assert '<form id="knowledge-metadata-form">' in page_block


def test_index_html_knowledge_page_listener_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "$id('knowledge-project-select')?.addEventListener('change'" in content
    assert "$id('knowledge-project-refresh-btn')?.addEventListener('click', loadKnowledgeProjectSelector)" in content
    assert "knowledgeUploadArea.addEventListener('click'" in content
    assert "knowledgeUploadArea.addEventListener('dragover'" in content
    assert "knowledgeUploadArea.addEventListener('drop', knowledgeDrop)" in content
    assert "$id('knowledge-file-input')?.addEventListener('change'" in content
    assert "$id('knowledge-file-pick-btn')?.addEventListener('click'" in content
    assert "$id('knowledge-context-preview-btn')?.addEventListener('click', () => previewKnowledgeContext())" in content
    assert "$id('knowledge-temporal-graph-btn')?.addEventListener('click', () => previewKnowledgeTemporalGraph())" in content
    assert "document.querySelectorAll('[data-close-modal]').forEach" in content
    assert "document.querySelector('[data-preview-knowledge-context-inputs]')?.addEventListener('click'" in content
    assert "document.querySelector('[data-preview-knowledge-graph-inputs]')?.addEventListener('click'" in content
    assert "document.querySelector('[data-copy-knowledge-graph-json]')?.addEventListener('click', copyKnowledgeTemporalGraphJson)" in content
    assert "document.querySelector('[data-download-knowledge-graph-json]')?.addEventListener('click', downloadKnowledgeTemporalGraphJson)" in content
    assert "document.querySelectorAll('[data-knowledge-promote-close]').forEach" in content
    assert "$id('knowledge-promote-form')?.addEventListener('submit', submitKnowledgePromotion)" in content
    assert "document.querySelectorAll('[data-knowledge-metadata-close]').forEach" in content
    assert "$id('knowledge-metadata-form')?.addEventListener('submit', submitKnowledgeMetadataUpdate)" in content


def test_index_html_knowledge_doc_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    start = content.index("async function loadKnowledgeDocs(projectId)")
    end = content.index("function _knowledgeFileIcon(filename)", start)
    block = content[start:end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-knowledge-doc-action="metadata"',
        'data-knowledge-doc-action="delete"',
        'data-project-id="${escapeHtml(projectId)}"',
        'data-doc-id="${escapeHtml(doc.doc_id)}"',
        "wireKnowledgeDocActions(list);",
        "function wireKnowledgeDocActions(list)",
        "list.querySelectorAll('[data-knowledge-doc-action]').forEach",
        "await openKnowledgeMetadataModal(projectId, docId);",
        "await deleteKnowledgeDoc(projectId, docId);",
    ):
        assert marker in block


def test_index_html_locations_page_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    page_start = content.index('<section id="locations-page"')
    page_match = re.search(r'<section id="locations-page"[\s\S]*?\n</section>', content[page_start:])
    assert page_match is not None
    page_block = page_match.group(0)

    assert not re.search(r"\son[a-zA-Z]+\s*=", page_block)
    for action in (
        "open-create-location",
        "close-create-location",
        "close-api-key",
        "close-users",
        "close-create-user",
        "close-edit-user",
        "close-procurement-summary",
    ):
        assert f'data-location-action="{action}"' in page_block
    assert 'data-location-backdrop-action="close-create-user"' in page_block
    assert 'data-location-backdrop-action="close-edit-user"' in page_block
    assert '<form id="create-location-form">' in page_block
    assert '<form id="location-user-create-form">' in page_block
    assert '<form id="location-user-edit-form">' in page_block


def test_index_html_locations_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "const LOCATION_ACTIONS = {" in content
    for mapping in (
        "'open-create-location': () => showLocationModal('create-location-modal')",
        "'close-create-location': () => hideLocationModal('create-location-modal')",
        "'close-api-key': () => hideLocationModal('location-key-modal')",
        "'close-users': () => hideLocationModal('location-users-modal')",
        "'close-create-user': closeLocationCreateUserModal",
        "'close-edit-user': closeLocationUserEditModal",
        "'close-procurement-summary': () => window.closeLocationProcurementSummary?.()",
    ):
        assert mapping in content
    assert "document.querySelectorAll('[data-location-action]').forEach" in content
    assert "const action = LOCATION_ACTIONS[el.dataset.locationAction || ''];" in content
    assert "document.querySelectorAll('[data-location-backdrop-action]').forEach" in content
    assert "if (event.target !== event.currentTarget) return;" in content
    assert "$id('create-location-form')?.addEventListener('submit', createLocation)" in content
    assert "$id('location-user-create-form')?.addEventListener('submit', submitLocationCreateUser)" in content
    assert "$id('location-user-edit-form')?.addEventListener('submit', submitLocationUserEdit)" in content
    assert "$id('location-user-create-role')?.addEventListener('change', syncLocationCreateUserRoleDefaults)" in content


def test_index_html_has_no_inline_event_handlers():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert not re.search(r"\son[a-zA-Z]+\s*=", content)


def test_index_html_location_dynamic_and_procurement_actions_are_delegated():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function runLocationDynamicAction(button)",
        "function runLocationProcurementSummaryAction(button)",
        "document.addEventListener('click', event => {",
        "event.target.closest?.('[data-location-dynamic-action]')",
        "event.target.closest?.(",
        "[data-location-procurement-open],",
        "window.openProjectFromProcurementSummaryFromButton?.(button)",
        "window.copyProjectProcurementSummaryLinkFromButton?.(button)",
        "window.copyLocationProcurementSummaryLink?.()",
        "window.openLocationProcurementSharedLinkFromButton?.(button)",
        "window.copyLocationProcurementSharedLinkFromButton?.(button)",
        "window.revokeLocationProcurementShareFromButton?.(button)",
        "window.applyLocationProcurementTriagePreset?.(data.locationProcurementPreset)",
        "window.applyLocationProcurementTriagePreset?.('stale_share_review')",
        "window.setLocationProcurementCandidateOrder?.(data.locationProcurementOrder)",
        "window.setLocationProcurementCandidateScope?.(data.locationProcurementScopeCta)",
        "window.setLocationProcurementCandidateScope?.(data.locationProcurementScope)",
        "window.toggleLocationProcurementCandidateStatusFilter?.(data.locationProcurementStatusFilter)",
        "window.clearLocationProcurementCandidateStatusFilters?.()",
        "window.toggleLocationProcurementActivityActionFilter?.(data.locationProcurementActivityFilter)",
        "window.clearLocationProcurementActivityActionFilters?.()",
        'data-location-dynamic-action="open-key"',
        'data-location-dynamic-action="open-users"',
        'data-location-dynamic-action="open-procurement-summary"',
        'data-location-dynamic-action="rotate-key"',
        'data-location-dynamic-action="edit-user-assignment"',
        'data-location-dynamic-action="stale-share-review"',
        'data-location-dynamic-action="copy-stale-share-focus-review-link"',
        'data-location-procurement-share-open="true"',
        'data-location-procurement-share-copy="true"',
        'data-location-procurement-stale-share-review-preset="true"',
        'data-location-procurement-scope-cta="unresolved_only"',
    ):
        assert marker in content


def test_index_html_bundle_recommendation_close_uses_event_listener():
    content = open("app/static/index.html", encoding="utf-8").read()
    start = content.index("function showBundleRecommendation(bundleIds)")
    end = content.index("// Wire up recommendation triggers", start)
    block = content[start:end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    assert "const closeButton = document.createElement('button')" in block
    assert "closeButton.addEventListener('click', () => badge.remove())" in block
    assert "badge.replaceChildren('✨ ', title, ` ${names.join(', ')} `, closeButton)" in block


def test_index_html_upload_modals_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    page_start = content.index('<div id="from-documents-modal"')
    page_end = content.index("<!-- ── 번들 비교 모달", page_start)
    modal_block = content[page_start:page_end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", modal_block)
    assert 'data-upload-modal-backdrop="documents"' in modal_block
    assert 'data-upload-modal-backdrop="pdf"' in modal_block
    assert 'data-upload-modal-action="close-documents"' in modal_block
    assert 'data-upload-modal-action="close-pdf"' in modal_block
    assert 'id="from-documents-dropzone"' in modal_block
    assert 'id="from-pdf-dropzone"' in modal_block
    assert '<input type="file" id="from-documents-file-input"' in modal_block
    assert '<input type="file" id="from-pdf-file-input"' in modal_block
    assert 'id="from-documents-submit-btn" type="button"' in modal_block
    assert 'id="from-pdf-submit-btn" type="button"' in modal_block


def test_index_html_upload_modal_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "const UPLOAD_MODAL_ACTIONS = {" in content
    assert "'close-documents': closeFromDocumentsModal" in content
    assert "'close-pdf': closeFromPdfModal" in content
    assert "document.querySelectorAll('[data-upload-modal-action]').forEach" in content
    assert "const action = UPLOAD_MODAL_ACTIONS[el.dataset.uploadModalAction || ''];" in content
    assert "document.querySelectorAll('[data-upload-modal-backdrop]').forEach" in content
    assert "if (event.target !== event.currentTarget) return;" in content
    assert "wireUploadDropzone('from-documents-dropzone', 'from-documents-file-input', fromDocumentsHandleDrop)" in content
    assert "wireUploadDropzone('from-pdf-dropzone', 'from-pdf-file-input', fromPdfHandleDrop)" in content
    assert "$id('from-documents-file-input')?.addEventListener('change', event => fromDocumentsFilesSelected(event.currentTarget))" in content
    assert "$id('from-pdf-file-input')?.addEventListener('change', event => fromPdfFileSelected(event.currentTarget))" in content
    assert "$id('from-documents-submit-btn')?.addEventListener('click', submitFromDocuments)" in content
    assert "$id('from-pdf-submit-btn')?.addEventListener('click', submitFromPdf)" in content


def test_index_html_static_shell_controls_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    slices = [
        ('<div id="project-page"', "<!-- ── 지식 관리"),
        ('<section id="approval-page"', "<!-- ── 스타일 관리"),
        ('<div id="style-page"', "<!-- ── 거점 관리"),
        ('<div id="history-panel"', "<!-- ── 문서 → 초안 생성 모달"),
    ]
    for start_marker, end_marker in slices:
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        block = content[start:end]
        assert not re.search(r"\son[a-zA-Z]+\s*=", block)

    ops_start = content.index('id="ops-window"')
    ops_end = content.index('id="ops-reason"', ops_start)
    assert not re.search(r"\son[a-zA-Z]+\s*=", content[ops_start:ops_end])

    for marker in (
        'id="project-search-btn"',
        'id="project-create-btn"',
        'id="approval-search-btn"',
        'id="style-create-btn"',
        'id="history-search-input"',
        'id="history-star-filter"',
        'id="ops-window"',
    ):
        assert marker in content


def test_index_html_static_shell_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "$id('project-search-btn')?.addEventListener('click', loadProjects)" in content
    assert "$id('project-create-btn')?.addEventListener('click', showCreateProjectModal)" in content
    assert "$id('approval-search-btn')?.addEventListener('click', loadApprovals)" in content
    assert "$id('style-create-btn')?.addEventListener('click', showCreateStyleModal)" in content
    assert "$id('history-search-input')?.addEventListener('input', event => {" in content
    assert "loadServerHistory(event.currentTarget.value);" in content
    assert "$id('history-star-filter')?.addEventListener('click', toggleHistoryStarFilter)" in content
    assert "$id('ops-window')?.addEventListener('input', event => {" in content
    assert "if (label) label.textContent = event.currentTarget.value;" in content


def test_index_html_share_auth_approval_project_modals_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function showShareModal(shareUrl, expiresAt, title, source = null)", "function copyShareUrl",),
        ("function showLoginScreen()", "function showRegisterScreen",),
        ("function showRegisterScreen(e)", "async function submitRegister",),
        ("function showApprovalRequestModal(source = null)", "async function submitApprovalRequest",),
        ("function showCreateProjectModal()", "async function createProject",),
        ("function renderProjectList(projects)", "async function parseApiErrorResponse",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        "data-share-copy",
        "data-share-close",
        "data-auth-register",
        "data-auth-login-return",
        "data-approval-modal-cancel",
        "data-approval-modal-submit",
        "data-project-modal-cancel",
        "data-project-modal-submit",
        "data-project-empty-create",
        'data-project-open="${escapeHtml(p.project_id)}"',
    ):
        assert marker in block


def test_index_html_share_auth_approval_project_modal_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function wireShareModalActions(modal, source = null)",
        "modal.querySelector('[data-share-copy]')?.addEventListener('click', copyShareUrl)",
        "modal.querySelector('[data-share-close]')?.addEventListener('click', () => modal.remove())",
        "handleProjectDocumentDecisionCouncilFollowUp(source?.projectId || '', source?.docId || '')",
        "screen.querySelector('[data-auth-register]')?.addEventListener('click', showRegisterScreen)",
        "screen.querySelector('[data-auth-login-return]')?.addEventListener('click', e => {",
        "function wireApprovalRequestModalActions(overlay, source)",
        "overlay.querySelector('[data-approval-modal-cancel]')?.addEventListener('click', close)",
        "overlay.querySelector('[data-approval-modal-submit]')?.addEventListener('click', submitApprovalRequest)",
        "function wireProjectCreateModalActions(modal)",
        "modal.querySelector('[data-project-modal-cancel]')?.addEventListener('click', () => modal.remove())",
        "modal.querySelector('[data-project-modal-submit]')?.addEventListener('click', createProject)",
        "function wireProjectListActions(container)",
        "container.querySelector('[data-project-empty-create]')?.addEventListener('click', showCreateProjectModal)",
        "container.querySelectorAll('[data-project-open]').forEach",
        "openProjectDetailFromList(card.dataset.projectOpen || '')",
    ):
        assert marker in content


def test_index_html_project_meeting_and_procurement_role_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderProjectMeetingRecordingList(projectId, recordings)", "function setProcurementActionStatus",),
        ("function getProcurementRoleBoardItems(project, decision, docs)", "function getVisibleProcurementRoleItems",),
        ("function renderProcurementRoleBoard(project, decision, docs)", "function getProcurementRoleRecentLog",),
        ("function renderProcurementRoleBriefPanel(project, decision, docs)", "window.selectProcurementRoleBrief",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        "data-meeting-recording-transcribe",
        "data-meeting-recording-approve",
        "data-meeting-recording-generate",
        "data-procurement-role-action",
        "data-procurement-brief-tab",
        "data-procurement-brief-action",
        "actionKey: !hasOpportunity ? 'focus-url' : 'refresh-decision'",
        "actionKey: canDownstream ? 'generate-bundle' : 'scroll-url'",
        "actionKey: overrideRequired",
    ):
        assert marker in block


def test_index_html_project_meeting_and_procurement_role_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function wireMeetingRecordingActions(container, projectId)",
        "submitMeetingRecordingUpload(projectId)",
        "transcribeMeetingRecording(projectId, btn.dataset.meetingRecordingTranscribe || '')",
        "approveMeetingRecording(projectId, btn.dataset.meetingRecordingApprove || '')",
        "generateMeetingRecordingDocuments(projectId, btn.dataset.meetingRecordingGenerate || '')",
        "function runProcurementRoleAction(btn)",
        "document.getElementById('project-procurement-url-input')?.focus()",
        "refreshProjectProcurementDecision(projectId)",
        "generateProjectProcurementBundle(projectId, btn.dataset.bundleId || '')",
        "window.selectProcurementRoleBrief?.(card.dataset.procurementRole || '')",
        "window.selectProcurementRoleBrief?.(btn.dataset.procurementBriefTab || '')",
        "runProcurementRoleAction(btn)",
        "wireMeetingRecordingActions(container, p.project_id);",
        "wireProcurementRoleActions(container);",
    ):
        assert marker in content


def test_index_html_project_detail_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderProcurementDecisionCouncilPanel(project, decision, docs, councilSession)", "function renderProjectProcurementRemediationStrip",),
        ("function renderProjectProcurementRemediationStrip(project, decision)", "function renderProcurementOverridePanel",),
        ("function renderProcurementOverridePanel(project, decision)", "function getProcurementBundleDefaults",),
        ("function renderProjectDetail(p, procurementDecision = null, options = {})", "function _renderBundleBreakdown",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-project-detail-action="decision-council-run"',
        'data-project-detail-action="procurement-generate"',
        "procurement-remediation-retry",
        "procurement-remediation-review",
        'data-project-detail-action="procurement-override-focus"',
        'data-project-detail-action="procurement-override-history"',
        'data-project-detail-action="procurement-override-save"',
        'data-project-detail-action="hide"',
        'data-project-detail-action="voice-brief-import"',
        'data-project-detail-action="procurement-import"',
        'data-project-detail-action="doc-approval"',
        'data-project-detail-action="doc-share"',
        'data-project-detail-action="doc-download"',
    ):
        assert marker in block


def test_index_html_project_detail_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function runProjectDetailAction(btn, fallbackProjectId)",
        "window.hideProjectDetail?.();",
        "returnToLocationProcurementSummary(projectId)",
        "downloadYearlyArchive(Number(btn.dataset.fiscalYear || 0))",
        "submitVoiceBriefImport(projectId)",
        "submitProjectProcurementImport(projectId)",
        "runProjectDecisionCouncil(projectId)",
        "retryProjectProcurementRemediation(projectId)",
        "dismissProjectProcurementRemediationContext(projectId)",
        "useProcurementOverrideHistoryItem(btn, Number(btn.dataset.procurementOverrideHistoryIndex || 0))",
        "handleProjectDocumentDecisionCouncilFollowUp(projectId, docId)",
        "downloadProjectDoc(projectId, docId, btn.dataset.format || '')",
        "function wireProjectDetailActions(container, projectId)",
        "container.querySelectorAll('[data-project-detail-action]').forEach",
        "wireProjectDetailActions(container, p.project_id);",
    ):
        assert marker in content


def test_index_html_project_search_and_dashboard_retry_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("// Project search with debounce", "/* ── Dashboard state",),
        ("async function loadDashboard()", "/* ── Fine-tune dataset card",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-project-open="${escapeHtml(r.project_id)}"',
        "wireProjectListActions(container);",
        "data-dashboard-retry",
        "wireDashboardRetry(tbody);",
        "wireDashboardRetry(feedList);",
    ):
        assert marker in block


def test_index_html_dashboard_retry_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function wireDashboardRetry(container)",
        "container?.querySelectorAll('[data-dashboard-retry]').forEach",
        "btn.addEventListener('click', loadDashboard)",
    ):
        assert marker in content


def test_index_html_style_profile_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    start = content.index("function renderStyleList(profiles)")
    end = content.index("async function saveBundleOverride(profileId)", start)
    block = content[start:end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-style-action="create"',
        'data-style-profile-id="${escapeHtml(p.profile_id)}"',
        "function wireStyleListActions(listEl)",
        "data-style-tone-autosave",
        'data-style-detail-action="back"',
        'data-style-detail-action="set-default"',
        'data-style-detail-action="delete"',
        'data-style-detail-action="pick-file"',
        'data-style-detail-action="remove-example"',
        'data-style-detail-action="remove-bundle"',
        'data-style-detail-action="add-bundle"',
        "wireStyleDetailActions(container, p.profile_id);",
        "data-style-modal-close",
        "data-style-create-submit",
        "data-style-bundle-save",
    ):
        assert marker in block


def test_index_html_style_profile_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "listEl.querySelector('[data-style-action=\"create\"]')?.addEventListener('click', showCreateStyleModal)",
        "listEl.querySelectorAll('[data-style-profile-id]').forEach",
        "loadStyleDetail(card.dataset.styleProfileId || '')",
        "function wireStyleDetailActions(container, profileId)",
        "'set-default': () => setDefaultStyle(profileId)",
        "'pick-file': () => document.getElementById('style-file-input')?.click()",
        "removeStyleExample(profileId, btn.dataset.exampleId || '')",
        "removeBundleOverride(profileId, btn.dataset.bundleId || '')",
        "autoSaveTone(profileId)",
        "analyzeStyleDocuments(profileId)",
        "function wireCreateStyleModalActions(modal)",
        "modal.querySelector('[data-style-create-submit]')?.addEventListener('click', submitCreateStyleProfile)",
        "function wireBundleOverrideModalActions(modal, profileId)",
        "modal.querySelector('[data-style-bundle-save]')?.addEventListener('click', () => saveBundleOverride(profileId))",
    ):
        assert marker in content


def test_index_html_approval_dynamic_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderApprovalList(approvals)", "async function loadApprovalDetail",),
        ("function renderApprovalDetail(a)", "function approvalActionBodyFromButton",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-approval-open="${escapeHtml(a.approval_id)}"',
        "wireApprovalListActions(container);",
        "data-approval-back",
        'data-approval-download-format="${fmt}"',
        'data-approval-flow-action="submit"',
        'data-approval-flow-action="review/approve"',
        'data-approval-flow-action="review/request-changes"',
        'data-approval-flow-action="approve"',
        'data-approval-flow-action="reject"',
        'data-approval-body-key="reviewer"',
        'data-approval-body-key="comment"',
        "wireApprovalDetailActions(container);",
    ):
        assert marker in block


def test_index_html_approval_dynamic_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function wireApprovalListActions(container)",
        "container.querySelectorAll('[data-approval-open]').forEach",
        "item.addEventListener('keydown', event => {",
        "loadApprovalDetail(item.dataset.approvalOpen || '')",
        "function approvalActionBodyFromButton(btn)",
        "function wireApprovalDetailActions(container)",
        "container.querySelector('[data-approval-back]')?.addEventListener('click'",
        "container.querySelectorAll('[data-approval-download-format]').forEach",
        "downloadApprovedDoc(btn.dataset.approvalId || '', btn.dataset.approvalDownloadFormat || '')",
        "container.querySelectorAll('[data-approval-flow-action]').forEach",
        "approvalActionBodyFromButton(btn)",
    ):
        assert marker in content


def test_index_html_history_dynamic_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    local_start = content.index("function renderHistoryList()")
    local_end = content.index("$id('history-toggle-btn').addEventListener", local_start)
    server_start = content.index("async function loadServerHistory")
    server_end = content.index("function reuseHistoryEntry(item)", server_start)

    history_block = content[local_start:local_end] + content[server_start:server_end]
    assert not re.search(r"\son[a-zA-Z]+\s*=", history_block)
    for marker in (
        "data-history-clear",
        "data-history-star",
        "data-history-reuse",
        "data-history-delete",
    ):
        assert marker in history_block
    assert "JSON.stringify(item).replace" not in history_block


def test_index_html_history_dynamic_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "const _serverHistoryEntriesById = new Map();",
        "function rememberServerHistoryEntries(items)",
        "function getServerHistoryEntry(entryId)",
        "rememberServerHistoryEntries(items);",
        "list.querySelector('[data-history-clear]')?.addEventListener('click', clearHistory)",
        "list.querySelectorAll('[data-history-star]').forEach",
        "toggleHistoryStar(btn.dataset.entryId || '', btn);",
        "list.querySelectorAll('[data-history-reuse]').forEach",
        "const item = getServerHistoryEntry(btn.dataset.entryId || '');",
        "if (item) reuseHistoryEntry(item);",
        "list.querySelectorAll('[data-history-delete]').forEach",
        "deleteServerHistory(btn.dataset.entryId || '');",
    ):
        assert marker in content


def test_index_html_message_thread_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    block_start = content.index("function renderMessageThread(container, messages, contextType, contextId)")
    block_end = content.index("async function sendMessage(contextType, contextId)", block_start)
    block = content[block_start:block_end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    assert "data-message-input" in block
    assert "data-message-send" in block
    assert 'id="msg-input-${escapeHtml(contextId)}"' in block


def test_index_html_message_thread_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "container.querySelector('[data-message-input]')?.addEventListener('keydown', event => {",
        "if (event.key !== 'Enter') return;",
        "sendMessage(contextType, contextId);",
        "container.querySelector('[data-message-send]')?.addEventListener('click', () => {",
    ):
        assert marker in content


def test_index_html_onboarding_wizard_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    block_start = content.index("function showOnboardingWizard()")
    block_end = content.index("/* ── G2B deadline alerts", block_start)
    block = content[block_start:block_end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-onboard-use-case="consulting"',
        'data-onboard-use-case="internal"',
        'data-onboard-use-case="both"',
        'data-onboard-style="default-official"',
        'data-onboard-style="default-consulting"',
        'data-onboard-style="default-internal"',
        'id="onboard-skip" type="button"',
        'id="onboard-next" type="button"',
    ):
        assert marker in block
    assert "event.currentTarget" not in block


def test_index_html_onboarding_wizard_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "function wireOnboardStepActions()",
        "overlay.querySelectorAll('[data-onboard-use-case]').forEach",
        "window.selectUseCase(btn.dataset.onboardUseCase || '', btn);",
        "overlay.querySelectorAll('[data-onboard-style]').forEach",
        "window.selectOnboardStyle(btn.dataset.onboardStyle || '', btn);",
        "if (selectedButton) selectedButton.classList.add('selected');",
        "$id('onboard-skip')?.addEventListener('click', finishOnboarding)",
        "$id('onboard-next')?.addEventListener('click', () => window.nextOnboardStep())",
    ):
        assert marker in content


def test_index_html_ops_static_controls_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    compare_start = content.index('<div id="compare-modal"')
    compare_end = content.index("<!-- ── 비교 결과", compare_start)
    assert not re.search(r"\son[a-zA-Z]+\s*=", content[compare_start:compare_end])

    ops_start = content.index('id="audit-log-search-btn"')
    ops_end = content.index('id="billing-panel"', ops_start)
    ops_block = content[ops_start:ops_end]
    assert not re.search(r"\son[a-zA-Z]+\s*=", ops_block)
    for marker in (
        'id="compare-modal-close-btn"',
        'id="audit-log-search-btn"',
        'id="audit-log-export-btn"',
        'id="sso-refresh-btn"',
        'id="billing-refresh-btn"',
    ):
        assert marker in content


def test_index_html_ops_static_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "$id('compare-modal-close-btn')?.addEventListener('click', () => {" in content
    assert "$id('compare-modal').style.display = 'none';" in content
    assert "$id('audit-log-search-btn')?.addEventListener('click', () => {" in content
    assert "action: document.getElementById('audit-action-filter')?.value || ''" in content
    assert "result: document.getElementById('audit-result-filter')?.value || ''" in content
    assert "$id('audit-log-export-btn')?.addEventListener('click', exportAuditLogs)" in content
    assert "$id('sso-refresh-btn')?.addEventListener('click', loadSSOConfig)" in content
    assert "$id('billing-refresh-btn')?.addEventListener('click', loadBillingStatus)" in content


def test_index_html_sso_billing_dynamic_controls_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    block_start = content.index("// ── SSO Login Buttons")
    block_end = content.index("async function cancelBilling()", block_start)
    block = content[block_start:block_end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        "data-sso-ldap-login",
        'data-sso-action="test-ldap"',
        'data-sso-action="save-ldap"',
        'data-sso-action="save-saml"',
        'data-sso-action="save-gcloud"',
        "data-billing-plan-id",
        "data-billing-cancel",
    ):
        assert marker in block


def test_index_html_sso_billing_dynamic_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "container.querySelector('[data-sso-ldap-login]')?.addEventListener('click', submitLDAPLogin)" in content
    assert "function wireSSOFormActions(container) {" in content
    assert "'test-ldap': testLDAPConnection" in content
    assert "'save-ldap': saveLDAPConfig" in content
    assert "'save-saml': saveSAMLConfig" in content
    assert "'save-gcloud': saveGCloudConfig" in content
    assert "container.querySelectorAll('[data-sso-action]').forEach" in content
    assert "if (action) btn.addEventListener('click', action);" in content
    assert "function wireBillingActions(panel) {" in content
    assert "panel.querySelectorAll('[data-billing-plan-id]').forEach" in content
    assert "btn.addEventListener('click', () => startCheckout(btn.dataset.billingPlanId || ''));" in content
    assert "panel.querySelector('[data-billing-cancel]')?.addEventListener('click', cancelBilling)" in content


def test_index_html_report_workflow_page_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    page_start = content.index('<section id="report-workflow-page"')
    page_match = re.search(r'<section id="report-workflow-page"[\s\S]*?\n</section>', content[page_start:])
    assert page_match is not None
    page_block = page_match.group(0)

    assert not re.search(r"\son[a-zA-Z]+\s*=", page_block)
    assert 'data-report-workflow-action="load"' in page_block
    assert 'data-report-workflow-action="create"' in page_block


def test_index_html_report_workflow_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "const REPORT_WORKFLOW_ACTIONS = {" in content
    assert "load: loadReportWorkflows" in content
    assert "create: createReportWorkflow" in content
    assert "document.querySelectorAll('[data-report-workflow-action]').forEach" in content
    assert "const action = REPORT_WORKFLOW_ACTIONS[btn.dataset.reportWorkflowAction || ''];" in content
    assert "if (action) action();" in content


def test_index_html_report_workflow_list_and_artifacts_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderReportWorkflowQualityArtifactSummary(data)", "async function loadReportWorkflowQualityArtifacts",),
        ("async function loadReportWorkflows()", "async function createReportWorkflow",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-rw-quality-artifacts-action="load"',
        'data-rw-quality-artifacts-action="download"',
        'data-report-workflow-select="${escapeHtml(item.report_workflow_id)}"',
    ):
        assert marker in block


def test_index_html_report_workflow_list_and_artifacts_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "const REPORT_WORKFLOW_QUALITY_ARTIFACT_ACTIONS = {",
        "load: loadReportWorkflowQualityArtifacts",
        "download: downloadReportWorkflowQualityArtifacts",
        "wireReportWorkflowQualityArtifactActions(el);",
        "function wireReportWorkflowQualityArtifactActions(container)",
        "container.querySelectorAll('[data-rw-quality-artifacts-action]').forEach",
        "const action = REPORT_WORKFLOW_QUALITY_ARTIFACT_ACTIONS[btn.dataset.rwQualityArtifactsAction || ''];",
        "wireReportWorkflowListActions(list);",
        "function wireReportWorkflowListActions(list)",
        "list.querySelectorAll('[data-report-workflow-select]').forEach",
        "selectReportWorkflow(btn.dataset.reportWorkflowSelect || '')",
    ):
        assert marker in content


def test_index_html_report_workflow_detail_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    start = content.index("function renderReportWorkflowDetail(item)")
    end = content.index("function renderReportWorkflowRoleLine(item)", start)
    block = content[start:end]

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-rw-detail-action="workflow-action"',
        'data-report-workflow-id="${workflowId}"',
        'data-rw-action-path="planning/generate"',
        'data-rw-action-path="planning/approve"',
        'data-rw-action-path="slides/generate"',
        'data-rw-action-body="empty-object"',
        'data-rw-action-path="final/submit"',
        'data-rw-action-path="final/pm-approve"',
        'data-rw-action-path="final/executive-approve"',
        'data-rw-detail-action="planning-change"',
        'data-rw-detail-action="final-change"',
        'data-rw-detail-action="visual-assets"',
        'data-rw-detail-action="download-pptx"',
        'data-rw-detail-action="download-snapshot"',
        'data-rw-detail-action="develop-preview"',
        "wireReportWorkflowDetailActions(el);",
    ):
        assert marker in block


def test_index_html_report_workflow_detail_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "const REPORT_WORKFLOW_DETAIL_ACTIONS = {",
        "'planning-change': requestReportWorkflowPlanningChange",
        "'final-change': requestReportWorkflowFinalChange",
        "'visual-assets': generateReportWorkflowVisualAssets",
        "'download-pptx': downloadReportWorkflowPptx",
        "'download-snapshot': downloadReportWorkflowSnapshot",
        "'develop-preview': runReportWorkflowDevelopPreview",
        "function wireReportWorkflowDetailActions(container)",
        "container.querySelectorAll('[data-rw-detail-action]').forEach",
        "const workflowId = btn.dataset.reportWorkflowId || '';",
        "const detailAction = btn.dataset.rwDetailAction || '';",
        "const actionPath = btn.dataset.rwActionPath || '';",
        "runReportWorkflowAction(workflowId, actionPath, {});",
        "runReportWorkflowAction(workflowId, actionPath);",
        "const action = REPORT_WORKFLOW_DETAIL_ACTIONS[detailAction];",
        "if (action) action(workflowId, btn);",
    ):
        assert marker in content


def test_index_html_report_workflow_quality_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderReportWorkflowDevelopPreview(data)", "async function runReportWorkflowDevelopPreview",),
        ("function renderReportWorkflowPromotion(item)", "function reportWorkflowLatestQualityArtifact",),
        ("function renderReportWorkflowQualityLearning(item)", "function reportWorkflowSplitLines",),
        ("function renderReportWorkflowQualityReviewChecklist(previewResult = null)", "function refreshReportWorkflowQualityReviewChecklist",),
        ("function renderReportWorkflowQualityValidation(result)", "function reportWorkflowQualityReviewPacketBoundary",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-rw-detail-action="apply-develop-preview"',
        'data-rw-detail-action="develop-preview-artifact"',
        'data-rw-detail-action="open-project"',
        'data-rw-detail-action="open-knowledge"',
        'data-rw-detail-action="promote"',
        'data-rw-detail-action="quality-preview"',
        'data-rw-detail-action="quality-review-packet"',
        'data-rw-detail-action="quality-save"',
        'data-rw-detail-action="focus-quality-field"',
    ):
        assert marker in block


def test_index_html_report_workflow_quality_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "'apply-develop-preview': applyReportWorkflowDevelopPreviewToQualityArtifact",
        "'develop-preview-artifact': applyReportWorkflowDevelopPreviewAndPreviewArtifact",
        "'promote': promoteReportWorkflow",
        "'quality-preview': previewReportWorkflowQualityArtifact",
        "'quality-review-packet': downloadReportWorkflowQualityReviewPacket",
        "'quality-save': saveReportWorkflowQualityArtifact",
        "'open-project': (_workflowId, btn) => openReportWorkflowProject(btn.dataset.projectId || '', btn.dataset.projectDocId || '')",
        "'open-knowledge': (_workflowId, btn) => openReportWorkflowKnowledge(btn.dataset.projectId || '')",
        "'focus-quality-field': (_workflowId, btn) => focusReportWorkflowQualityField(btn.dataset.focusTargetId || '')",
        "if (action) action(workflowId, btn);",
        "wireReportWorkflowDetailActions(resultEl);",
        "wireReportWorkflowDetailActions(el);",
    ):
        assert marker in content


def test_index_html_report_workflow_slide_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderReportWorkflowSlides(slides, item)", "function reportWorkflowVisualAssetDataUri",),
        ("function renderReportWorkflowSlideVisualWorkspace(slide, item, finalLocked)", "async function runReportWorkflowAction",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        'data-rw-detail-action="workflow-action"',
        'data-rw-action-path="slides/${escapeHtml(slide.slide_id)}/approve"',
        'data-rw-detail-action="slide-change"',
        'data-rw-detail-action="slide-edit-assets"',
        'data-rw-detail-action="slide-select-asset"',
        'data-slide-id="${escapeHtml(slide.slide_id)}"',
        'data-asset-id="${escapeHtml(assetId)}"',
    ):
        assert marker in block


def test_index_html_report_workflow_slide_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "'slide-change': (workflowId, btn) => requestReportWorkflowSlideChange(workflowId, btn.dataset.slideId || '')",
        "'slide-edit-assets': (workflowId, btn) => editReportWorkflowSlideVisualAssets(workflowId, btn.dataset.slideId || '')",
        "'slide-select-asset': (workflowId, btn) => selectReportWorkflowSlideVisualAsset(workflowId, btn.dataset.slideId || '', btn.dataset.assetId || '')",
        "if (action) action(workflowId, btn);",
    ):
        assert marker in content


def test_index_html_document_ops_page_uses_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    page_start = content.index('<section id="document-ops-page"')
    page_match = re.search(r'<section id="document-ops-page"[\s\S]*?\n</section>', content[page_start:])
    assert page_match is not None
    page_block = page_match.group(0)

    assert not re.search(r"\son[a-zA-Z]+\s*=", page_block)
    for action in (
        "load-trajectories",
        "preview-export",
        "export-trajectories",
        "load-exports",
        "load-readiness",
        "preview-plan",
        "request-execution",
        "load-audit-checklist",
        "export-audit",
        "load-governance",
        "load-signoff",
        "download-signoff",
        "load-adapter-contract",
        "load-rehearsal",
        "run-agent",
    ):
        assert f'data-docops-action="{action}"' in page_block


def test_index_html_document_ops_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    assert "const DOCUMENT_OPS_ACTIONS = {" in content
    for mapping in (
        "'load-trajectories': loadDocumentOpsTrajectories",
        "'preview-export': previewDocumentOpsExport",
        "'export-trajectories': exportDocumentOpsTrajectories",
        "'load-readiness': loadDocumentOpsTrainingReadiness",
        "'request-execution': requestDocumentOpsTrainingExecution",
        "'load-audit-checklist': loadDocumentOpsTrainingAuditChecklist",
        "'export-audit': exportDocumentOpsTrainingAudit",
        "'load-signoff': loadDocumentOpsReviewerSignoffSummary",
        "'download-signoff': downloadDocumentOpsReviewerSignoffSummary",
        "'load-rehearsal': loadDocumentOpsTrainingRehearsal",
        "'run-agent': runDocumentOpsAgent",
    ):
        assert mapping in content
    assert "document.querySelectorAll('[data-docops-action]').forEach" in content
    assert "const action = DOCUMENT_OPS_ACTIONS[btn.dataset.docopsAction || ''];" in content
    assert "if (action) action();" in content


def test_index_html_document_ops_dynamic_actions_use_event_listeners():
    content = open("app/static/index.html", encoding="utf-8").read()
    blocks = []
    for start_marker, end_marker in (
        ("function renderDocumentOpsTrajectoryCard(item)", "async function reviewDocumentOpsTrajectory",),
        ("function renderDocumentOpsExports(data)", "async function downloadDocumentOpsExport",),
        ("function renderDocumentOpsTrainingExecutionRequests(data)", "async function loadDocumentOpsTrainingAuditChecklist",),
        ("function renderDocumentOpsTrainingAuditChecklist(data, auditList)", "async function downloadDocumentOpsTrainingAudit",),
    ):
        start = content.index(start_marker)
        end = content.index(end_marker, start)
        blocks.append(content[start:end])
    block = "\n".join(blocks)

    assert not re.search(r"\son[a-zA-Z]+\s*=", block)
    for marker in (
        "data-docops-trajectory-review=\"true\"",
        "data-docops-trajectory-review=\"false\"",
        "data-docops-export-download=\"${escapeHtml(filename)}\"",
        "data-docops-training-execution-refresh",
        "data-docops-training-audit-download=\"${escapeHtml(item?.audit_file || '')}\"",
        "data-docops-training-audit-export",
        "data-docops-training-audit-refresh",
        "data-docops-training-audit-download=\"${escapeHtml(data.audit_file)}\"",
    ):
        assert marker in block


def test_index_html_document_ops_dynamic_action_wiring_exists():
    content = open("app/static/index.html", encoding="utf-8").read()

    for marker in (
        "wireDocumentOpsTrajectoryReviewActions(el);",
        "function wireDocumentOpsTrajectoryReviewActions(container)",
        "container.querySelectorAll('[data-docops-trajectory-review]').forEach",
        "btn.dataset.docopsTrajectoryReview === 'true'",
        "wireDocumentOpsExportDownloadActions(el);",
        "function wireDocumentOpsExportDownloadActions(container)",
        "downloadDocumentOpsExport(btn.dataset.docopsExportDownload || '')",
        "el.querySelector('[data-docops-training-execution-refresh]')?.addEventListener('click', loadDocumentOpsTrainingExecutionRequests)",
        "wireDocumentOpsTrainingAuditActions(el);",
        "function wireDocumentOpsTrainingAuditActions(container)",
        "downloadDocumentOpsTrainingAudit(btn.dataset.docopsTrainingAuditDownload || '')",
        "container.querySelector('[data-docops-training-audit-export]')?.addEventListener('click', exportDocumentOpsTrainingAudit)",
        "container.querySelector('[data-docops-training-audit-refresh]')?.addEventListener('click', loadDocumentOpsTrainingAuditChecklist)",
    ):
        assert marker in content


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


def test_dockerfile_uses_pinned_playwright_for_browser_install():
    dockerfile = open("Dockerfile", encoding="utf-8").read()
    copy_packages_index = dockerfile.index("COPY --from=builder /install /usr/local")
    install_browser_index = dockerfile.index("python -m playwright install chromium --with-deps")

    assert copy_packages_index < install_browser_index
    assert "pip install --no-cache-dir playwright" not in dockerfile


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


# ── CSP nonce helpers (unit) ────────────────────────────────────────────────

def test_generate_csp_nonce_is_unique_and_urlsafe():
    from app.middleware.security_headers import generate_csp_nonce

    nonces = {generate_csp_nonce() for _ in range(100)}
    assert len(nonces) == 100  # cryptographically distinct
    for n in nonces:
        assert n and all(c.isalnum() or c in "-_" for c in n)


def test_apply_csp_nonce_stamps_bare_inline_scripts_only():
    from app.main import _apply_csp_nonce

    html = (
        '<script>a()</script>'
        '<script src="/static/app.js"></script>'
        '<script>b()</script>'
    )
    out = _apply_csp_nonce(html, "N0NCE")
    # Bare inline blocks receive the nonce.
    assert out.count('<script nonce="N0NCE">') == 2
    # External src script is untouched.
    assert '<script src="/static/app.js"></script>' in out
    # No bare inline <script> left.
    assert "<script>" not in out


def test_build_csp_omits_nonce_when_absent():
    from app.middleware.security_headers import _build_csp

    csp = _build_csp(None)
    assert "'nonce-" not in csp
    assert "script-src 'self' 'unsafe-inline'" in csp


def test_build_csp_includes_nonce_when_present():
    from app.middleware.security_headers import _build_csp

    csp = _build_csp("abc123")
    assert "'nonce-abc123'" in csp
    assert "script-src 'self' 'nonce-abc123'" in csp
    # With a nonce present, 'unsafe-inline' is dropped from script-src — CSP L2+
    # browsers would ignore it anyway, so listing it would only mislead.
    assert "'unsafe-inline'" not in csp.split("style-src")[0]


def test_completion_readiness_local_receipts_and_prod_env_stay_gitignored():
    if shutil.which("git") is None:
        pytest.skip("git is required to verify ignore rules")

    root = Path(__file__).resolve().parents[1]
    for path in (
        ".env.prod",
        "reports/completion-readiness/latest.json",
        "reports/completion-readiness/latest-check.json",
    ):
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path],
            check=False,
            cwd=root,
        )
        assert completed.returncode == 0, f"{path} must remain gitignored"


def test_completion_readiness_runbook_keeps_external_proof_boundaries():
    root = Path(__file__).resolve().parents[1]
    runbook = (root / "docs" / "completion-readiness-runbook.md").read_text(encoding="utf-8")

    required_markers = (
        "python3 scripts/check_completion_readiness.py --print-env-template",
        "reports/completion-readiness/latest.json",
        "python3 scripts/check_completion_readiness_result.py",
        "DECISIONDOC_PROVIDER=openai",
        "DECISIONDOC_PROVIDER=gemini",
        "DECISIONDOC_PROVIDER=claude",
        "test_live_openai_gemini_fallback_chain_ok",
        "python3 scripts/run_stage_procurement_smoke.py",
        "python3 scripts/run_deployed_smoke.py",
        "provider API, G2B live API, AWS runtime",
        "bid submission, legal approval, contractual commitment",
    )
    for marker in required_markers:
        assert marker in runbook

    docs_to_link = (
        "README.md",
        "docs/development-plan.md",
        "docs/roadmap.md",
        "docs/evidence-gallery.md",
        "docs/evidence-checklist.md",
        "docs/contribution-note.md",
        "docs/project-card.md",
        "docs/resume-bullets.md",
    )
    for doc_path in docs_to_link:
        text = (root / doc_path).read_text(encoding="utf-8")
        assert "completion-readiness-runbook.md" in text, f"{doc_path} must link the completion runbook"


def test_live_workflow_covers_completion_readiness_provider_proofs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "live.yml").read_text(encoding="utf-8")
    runbook = (root / "docs" / "completion-readiness-runbook.md").read_text(encoding="utf-8")

    required_workflow_markers = (
        "- openai",
        "- gemini",
        "- claude",
        "- openai,gemini",
        "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}",
        "Missing ANTHROPIC_API_KEY secret",
        "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1",
        "test_live_openai_gemini_fallback_chain_ok",
    )
    for marker in required_workflow_markers:
        assert marker in workflow

    required_runbook_markers = (
        "gh workflow run live.yml --ref main -f provider=openai",
        "gh workflow run live.yml --ref main -f provider=gemini",
        "gh workflow run live.yml --ref main -f provider=claude",
        "gh workflow run live.yml --ref main -f provider='openai,gemini'",
    )
    for marker in required_runbook_markers:
        assert marker in runbook


def test_ruff_facade_ignores_cover_only_compatibility_modules():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    ignores = config["tool"]["ruff"]["lint"]["per-file-ignores"]
    expected_facades = {
        "app/routers/generate/__init__.py",
        "app/routers/projects/__init__.py",
        "app/services/attachment/__init__.py",
        "app/services/attachment_service.py",
        "app/services/generation/__init__.py",
        "app/services/generation_service.py",
        "app/services/pptx/__init__.py",
        "app/services/pptx_service.py",
        "app/services/procurement_decision_package/__init__.py",
        "app/services/procurement_decision_package_service.py",
        "app/services/procurement_decision_service.py",
        "app/services/report_workflow/__init__.py",
        "app/services/report_workflow_service.py",
        "app/storage/knowledge/__init__.py",
        "app/storage/knowledge_store.py",
        "app/storage/report_workflow/__init__.py",
        "app/storage/trajectory/__init__.py",
        "app/storage/trajectory_store.py",
    }

    assert set(ignores) == expected_facades
    assert all(rules == ["F401"] for rules in ignores.values())

    for path in expected_facades:
        text = (root / path).read_text(encoding="utf-8")
        assert "facade" in text or "re-export" in text or "re-exports" in text


def test_procurement_demo_defaults_use_system_temp_dir():
    from app.services.procurement_decision_package.constants import (
        DEFAULT_DECISION_PACKAGE_OUTPUT_BASE,
        DEFAULT_DEMO_DATA_DIR,
        DEFAULT_DEMO_OUT_DIR,
    )

    temp_dir = Path(tempfile.gettempdir())
    assert DEFAULT_DEMO_DATA_DIR == temp_dir / "decisiondoc-procurement-package-demo-data"
    assert DEFAULT_DEMO_OUT_DIR == temp_dir / "decisiondoc-procurement-package-demo-output"
    assert DEFAULT_DECISION_PACKAGE_OUTPUT_BASE == temp_dir / "decisiondoc-procurement-decision-packages"

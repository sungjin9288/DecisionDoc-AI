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

import json
import os
import re
import subprocess
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


def test_index_html_document_ops_downloads_reviewed_sft_jsonl_exports():
    content = open("app/static/index.html", encoding="utf-8").read()
    assert "Reviewed SFT JSONL" in content
    assert "/api/agent/document-ops/trajectories/reviewed-sft-exports?" in content
    assert "/api/agent/document-ops/trajectories/reviewed-sft-exports/${encodeURIComponent(filename)}/download" in content
    assert "getOpsAccessHeaders()" in content
    assert "accepted-only" in content


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


def test_phase18_browser_qa_evidence_artifact_documents_no_training_flow():
    content = open(
        "docs/specs/hermes_decisiondoc_agent/PHASE18_BROWSER_QA_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    assert "Phase 18 Local Browser QA Checklist and Evidence" in content
    assert "http://127.0.0.1:8767/?ops=1" in content
    assert "Reviewed JSONL" in content
    assert "Readiness" in content
    assert "Plan preview" in content
    assert "Request record" in content
    assert "Audit checklist" in content
    assert "Governance" in content
    assert "Adapter" in content
    assert "Rehearsal" in content
    assert "training_execution_allowed=false" in content
    assert "provider_api_calls_allowed=false" in content
    assert "external_upload_allowed=false" in content
    assert "provider_job_started=false" in content
    assert "model_promotion_allowed=false" in content
    assert "all rehearsal side_effect=false" in content
    assert "provider fine-tune API calls" in content


def test_phase19_browser_qa_result_records_observed_no_training_pass():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase18_browser_governance_qa/BROWSER_QA_REPORT.md",
        encoding="utf-8",
    ).read()
    result = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase18_browser_governance_qa/browser_qa_result.json",
            encoding="utf-8",
        )
    )

    assert "Phase 18 Browser Governance QA Report" in report
    assert "Result: PASS" in report
    assert "no provider fine-tune API call" in report
    assert result["result"] == "pass"
    assert result["seed"]["governance_status"] == "governance_ready_for_human_review"
    assert result["seed"]["rehearsal_status"] == "rehearsal_ready"
    assert result["ui_checks"]["reviewed_jsonl_artifact_visible"] is True
    assert result["ui_checks"]["governance_ready"] is True
    assert result["ui_checks"]["rehearsal_ready"] is True
    assert all(value is False for value in result["guard_flags"].values())
    assert all(value is False for value in result["side_effect_boundary"].values())


def test_phase29_release_handoff_refresh_packages_reviewer_signoff_artifacts():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/RELEASE_HANDOFF_INDEX.md",
        encoding="utf-8",
    ).read()
    manifest = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json",
            encoding="utf-8",
        )
    )
    artifact_ids = {item["id"] for item in manifest["artifacts"]}
    coverage = manifest["phase_coverage"]

    assert "Phase 29 DocumentOps Reviewer Sign-Off Release Handoff Refresh" in report
    assert "READY_FOR_HUMAN_REVIEWER_USE_NO_TRAINING_AUTHORIZATION" in report
    assert "Phase 21-28 Coverage" in report
    assert "Sign-off summary" in report
    assert "Sign-off JSON" in report
    assert "server-side reviewer sign-off JSON export artifact writes" in report
    assert "This handoff does not approve" in report
    assert "Sign-Off Checklist" in report
    assert "provider fine-tune API calls" in report
    assert manifest["report_type"] == "document_ops_phase29_reviewer_signoff_handoff_refresh"
    assert manifest["status"] == (
        "production_browser_uat_passed_with_download_runtime_limitation_no_training_authorization"
    )
    assert manifest["release_boundary"]["reviewer_signoff_ready"] is True
    assert manifest["release_boundary"]["human_reviewer_use_ready"] is True
    assert manifest["release_boundary"]["actual_reviewer_approval_recorded"] is True
    assert manifest["release_boundary"]["training_execution_authorized"] is False
    assert manifest["release_boundary"]["production_smoke_completed"] is True
    assert manifest["release_boundary"]["production_browser_uat_completed"] is True
    assert manifest["release_boundary"]["server_side_export_artifact_write_authorized"] is False
    assert manifest["release_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert manifest["observed_browser_qa_summary"]["phase26_result"] == "pass"
    assert manifest["observed_browser_qa_summary"]["phase28_result"] == "pass"
    assert manifest["observed_browser_qa_summary"]["phase28_browser_json_blob_received"] is True
    assert manifest["observed_browser_qa_summary"]["phase28_download_fallback_visible"] is True
    assert manifest["observed_browser_qa_summary"]["phase28_native_download_event_supported"] is False
    assert {"product_pm_reviewer", "ml_ai_owner", "compliance_security_reviewer", "release_owner"} <= set(
        manifest["required_reviewers"]
    )
    assert {
        "analysis",
        "architecture",
        "training_dataset_plan",
        "implementation_plan",
        "status",
        "phase18_browser_checklist_template",
        "phase19_browser_qa_report",
        "phase19_browser_qa_result",
        "phase21_signoff_markdown_template",
        "phase21_signoff_json_template",
        "phase22_signoff_validator",
        "phase23_pending_signoff_generator",
        "phase24_signoff_summary_reporter",
        "phase25_signoff_summary_endpoint_ui",
        "phase25_signoff_summary_service",
        "phase25_signoff_summary_store",
        "phase25_phase27_documentops_ui",
        "phase26_signoff_summary_browser_qa_report",
        "phase26_signoff_summary_browser_qa_result",
        "phase28_signoff_json_download_browser_qa_report",
        "phase28_signoff_json_download_browser_qa_result",
        "phase29_release_handoff_index",
        "phase29_handoff_manifest",
        "phase30_operator_packet_guide",
        "phase30_operator_packet_checklist",
        "phase31_signoff_import_helper_guide",
        "phase31_signoff_import_helper",
        "phase32_imported_signoff_browser_qa_report",
        "phase32_imported_signoff_browser_qa_result",
        "phase33_operator_release_packet_summary",
        "phase33_operator_release_packet_summary_json",
        "phase34_staging_readiness_dry_run_guide",
        "phase34_staging_readiness_dry_run_contract",
        "phase34_staging_readiness_probe",
        "phase35_observed_staging_probe_evidence_guide",
        "phase35_observed_staging_probe_evidence_contract",
        "phase35_observed_staging_probe_archive_helper",
        "phase36_observed_probe_execution_workflow_guide",
        "phase36_observed_probe_execution_workflow_contract",
        "phase36_observed_probe_execution_workflow_runner",
        "phase37_deployed_probe_failure_evidence_report",
        "phase37_deployed_probe_failure_evidence_json",
        "phase38_observed_probe_retry_evidence_report",
        "phase38_observed_probe_retry_evidence_json",
        "phase39_remote_runtime_gap_evidence_report",
        "phase39_remote_runtime_gap_evidence_json",
        "phase40_production_signoff_completion_evidence_report",
        "phase40_production_signoff_completion_evidence_json",
        "phase41_production_post_deploy_smoke_evidence_report",
        "phase41_production_post_deploy_smoke_evidence_json",
        "phase42_production_browser_uat_evidence_report",
        "phase42_production_browser_uat_evidence_json",
    } <= artifact_ids
    assert {f"phase{phase}" for phase in range(21, 29)} <= set(coverage)
    assert coverage["phase21"]["training_authorized"] is False
    assert coverage["phase26"]["result"] == "pass"
    assert coverage["phase27"]["server_side_export_artifact_written"] is False
    assert coverage["phase28"]["result"] == "pass"
    assert coverage["phase28"]["native_os_download_verified"] is False
    assert coverage["phase30"]["training_authorized"] is False
    assert coverage["phase30"]["provider_fine_tune_api_called"] is False
    assert coverage["phase31"]["training_authorized"] is False
    assert coverage["phase31"]["external_dataset_upload_authorized"] is False
    assert coverage["phase31"]["server_side_generated_approval_record"] is False
    assert coverage["phase32"]["result"] == "pass"
    assert coverage["phase32"]["training_authorized"] is False
    assert coverage["phase32"]["server_side_generated_approval_record"] is False
    assert coverage["phase33"]["training_authorized"] is False
    assert coverage["phase33"]["provider_fine_tune_api_called"] is False
    assert coverage["phase33"]["staging_run_completed"] is False
    assert coverage["phase33"]["production_smoke_completed"] is False
    assert coverage["phase34"]["training_authorized"] is False
    assert coverage["phase34"]["provider_fine_tune_api_called"] is False
    assert coverage["phase34"]["server_side_export_artifact_written"] is False
    assert coverage["phase34"]["probe_script_ready"] is True
    assert coverage["phase34"]["fixture_probe_verified"] is True
    assert coverage["phase34"]["real_staging_probe_completed"] is False
    assert coverage["phase35"]["training_authorized"] is False
    assert coverage["phase35"]["provider_fine_tune_api_called"] is False
    assert coverage["phase35"]["server_side_export_artifact_written"] is False
    assert coverage["phase35"]["archive_helper_verified"] is True
    assert coverage["phase35"]["observed_staging_probe_completed"] is False
    assert coverage["phase36"]["training_authorized"] is False
    assert coverage["phase36"]["provider_fine_tune_api_called"] is False
    assert coverage["phase36"]["server_side_export_artifact_written"] is False
    assert coverage["phase36"]["workflow_ready"] is True
    assert coverage["phase36"]["real_staging_probe_completed"] is False
    assert coverage["phase36"]["observed_staging_evidence_archived"] is False
    assert coverage["phase37"]["training_authorized"] is False
    assert coverage["phase37"]["provider_fine_tune_api_called"] is False
    assert coverage["phase37"]["server_side_export_artifact_written"] is False
    assert coverage["phase37"]["deployed_health_reachable"] is True
    assert coverage["phase37"]["ops_key_required"] is True
    assert coverage["phase37"]["ops_key_authenticated"] is False
    assert coverage["phase37"]["expected_record_ids_available"] is False
    assert coverage["phase38"]["training_authorized"] is False
    assert coverage["phase38"]["provider_fine_tune_api_called"] is False
    assert coverage["phase38"]["server_side_export_artifact_written"] is False
    assert coverage["phase38"]["wrapper_output_dir_hardened"] is True
    assert coverage["phase38"]["deployed_health_reachable"] is True
    assert coverage["phase38"]["ops_key_required"] is True
    assert coverage["phase38"]["ops_key_authenticated"] is False
    assert coverage["phase38"]["expected_record_ids_available"] is False
    assert coverage["phase39"]["training_authorized"] is False
    assert coverage["phase39"]["provider_fine_tune_api_called"] is False
    assert coverage["phase39"]["server_side_export_artifact_written"] is False
    assert coverage["phase39"]["deployed_ops_key_runtime_valid"] is True
    assert coverage["phase39"]["document_ops_reviewer_signoff_route_deployed"] is False
    assert coverage["phase39"]["signoff_storage_present"] is False
    assert coverage["phase39"]["expected_record_ids_available"] is False
    assert coverage["phase40"]["training_authorized"] is False
    assert coverage["phase40"]["provider_fine_tune_api_called"] is False
    assert coverage["phase40"]["server_side_export_artifact_written"] is False
    assert coverage["phase40"]["actual_reviewer_approval_recorded"] is True
    assert coverage["phase40"]["actual_reviewer_approval_generated_by_workflow"] is False
    assert coverage["phase40"]["ops_key_authenticated"] is True
    assert coverage["phase40"]["document_ops_reviewer_signoff_route_deployed"] is True
    assert coverage["phase40"]["signoff_storage_present"] is True
    assert coverage["phase40"]["expected_record_ids_available"] is True
    assert coverage["phase40"]["observed_staging_probe_completed"] is True
    assert coverage["phase40"]["observed_staging_evidence_archived"] is True
    assert coverage["phase40"]["result"] == "pass"
    assert coverage["phase41"]["training_authorized"] is False
    assert coverage["phase41"]["provider_fine_tune_api_called"] is False
    assert coverage["phase41"]["provider_job_creation_authorized"] is False
    assert coverage["phase41"]["model_promotion_authorized"] is False
    assert coverage["phase41"]["normal_generation_provider_calls_made"] is True
    assert coverage["phase41"]["runtime_bundles_created"] is True
    assert coverage["phase41"]["report_workflow_records_created"] is True
    assert coverage["phase41"]["project_document_promoted"] is True
    assert coverage["phase41"]["pptx_export_response_generated"] is True
    assert coverage["phase41"]["post_deploy_report_written"] is True
    assert coverage["phase41"]["deployed_smoke_passed"] is True
    assert coverage["phase41"]["report_workflow_smoke_passed"] is True
    assert coverage["phase41"]["production_smoke_completed"] is True
    assert coverage["phase41"]["result"] == "pass"
    assert coverage["phase42"]["training_authorized"] is False
    assert coverage["phase42"]["provider_fine_tune_api_called"] is False
    assert coverage["phase42"]["provider_job_creation_authorized"] is False
    assert coverage["phase42"]["model_promotion_authorized"] is False
    assert coverage["phase42"]["normal_generation_provider_calls_made"] is True
    assert coverage["phase42"]["ui_document_generation_completed"] is True
    assert coverage["phase42"]["download_clicks_without_console_errors"] is True
    assert coverage["phase42"]["native_download_event_supported"] is False
    assert coverage["phase42"]["native_os_download_verified"] is False
    assert coverage["phase42"]["backend_export_integrity_passed"] is True
    assert coverage["phase42"]["report_workflow_ui_passed"] is True
    assert coverage["phase42"]["global_generation_status_stale_after_result_visible"] is True
    assert coverage["phase42"]["production_browser_uat_completed"] is True
    assert coverage["phase42"]["result"] == "pass_with_download_runtime_limitation"
    assert manifest["observed_browser_qa_summary"]["phase32_imported_records_visible"] is True
    assert manifest["observed_browser_qa_summary"]["phase32_downloaded_json_contains_imported_records"] is True
    assert manifest["observed_browser_qa_summary"]["phase42_result"] == "pass_with_download_runtime_limitation"
    assert manifest["observed_browser_qa_summary"]["phase42_document_generation_ui_passed"] is True
    assert manifest["observed_browser_qa_summary"]["phase42_report_workflow_ui_passed"] is True
    assert manifest["observed_browser_qa_summary"]["phase42_download_clicks_without_console_errors"] is True
    assert manifest["observed_browser_qa_summary"]["phase42_backend_export_integrity_passed"] is True
    assert manifest["observed_browser_qa_summary"]["phase42_native_download_event_supported"] is False
    assert manifest["observed_browser_qa_summary"]["phase42_native_os_download_verified"] is False
    assert manifest["staging_readiness_summary"]["phase33_status"] == (
        "operator_release_packet_ready_no_training_authorization"
    )
    assert manifest["staging_readiness_summary"]["phase31_import_helper_verified"] is True
    assert manifest["staging_readiness_summary"]["phase32_observed_browser_qa_passed"] is True
    assert manifest["staging_readiness_summary"]["ops_key_required"] is True
    assert manifest["staging_readiness_summary"]["phase34_probe_script_ready"] is True
    assert manifest["staging_readiness_summary"]["phase34_fixture_probe_verified"] is True
    assert manifest["staging_readiness_summary"]["phase34_real_staging_probe_completed"] is False
    assert manifest["staging_readiness_summary"]["phase35_archive_helper_verified"] is True
    assert manifest["staging_readiness_summary"]["phase35_observed_staging_probe_completed"] is False
    assert manifest["staging_readiness_summary"]["phase36_workflow_ready"] is True
    assert manifest["staging_readiness_summary"]["phase36_real_staging_probe_completed"] is False
    assert manifest["staging_readiness_summary"]["phase36_observed_staging_evidence_archived"] is False
    assert manifest["staging_readiness_summary"]["phase37_deployed_health_reachable"] is True
    assert manifest["staging_readiness_summary"]["phase37_ops_key_authenticated"] is False
    assert manifest["staging_readiness_summary"]["phase37_expected_record_ids_available"] is False
    assert manifest["staging_readiness_summary"]["phase37_observed_staging_probe_completed"] is False
    assert manifest["staging_readiness_summary"]["phase38_wrapper_output_dir_hardened"] is True
    assert manifest["staging_readiness_summary"]["phase38_deployed_health_reachable"] is True
    assert manifest["staging_readiness_summary"]["phase38_ops_key_authenticated"] is False
    assert manifest["staging_readiness_summary"]["phase38_expected_record_ids_available"] is False
    assert manifest["staging_readiness_summary"]["phase38_observed_staging_probe_completed"] is False
    assert manifest["staging_readiness_summary"]["phase39_deployed_ops_key_runtime_valid"] is True
    assert manifest["staging_readiness_summary"]["phase39_document_ops_reviewer_signoff_route_deployed"] is False
    assert manifest["staging_readiness_summary"]["phase39_signoff_storage_present"] is False
    assert manifest["staging_readiness_summary"]["phase39_expected_record_ids_available"] is False
    assert manifest["staging_readiness_summary"]["phase39_observed_staging_probe_completed"] is False
    assert manifest["staging_readiness_summary"]["phase40_deployed_health_reachable"] is True
    assert manifest["staging_readiness_summary"]["phase40_ops_key_authenticated"] is True
    assert (
        manifest["staging_readiness_summary"]["phase40_document_ops_reviewer_signoff_route_deployed"]
        is True
    )
    assert manifest["staging_readiness_summary"]["phase40_signoff_storage_present"] is True
    assert manifest["staging_readiness_summary"]["phase40_expected_record_ids_available"] is True
    assert manifest["staging_readiness_summary"]["phase40_observed_staging_probe_completed"] is True
    assert manifest["staging_readiness_summary"]["phase40_observed_staging_evidence_archived"] is True
    assert manifest["staging_readiness_summary"]["phase40_json_download_server_file_written"] is False
    assert manifest["staging_readiness_summary"]["phase40_production_signoff_probe_completed"] is True
    assert manifest["staging_readiness_summary"]["phase41_deployed_smoke_passed"] is True
    assert manifest["staging_readiness_summary"]["phase41_report_workflow_smoke_passed"] is True
    assert manifest["staging_readiness_summary"]["phase41_normal_generation_provider_calls_made"] is True
    assert manifest["staging_readiness_summary"]["phase41_runtime_bundles_created"] is True
    assert manifest["staging_readiness_summary"]["phase41_post_deploy_report_written"] is True
    assert manifest["staging_readiness_summary"]["phase41_restricted_training_side_effects_clear"] is True
    assert manifest["staging_readiness_summary"]["phase42_document_generation_ui_passed"] is True
    assert manifest["staging_readiness_summary"]["phase42_report_workflow_ui_passed"] is True
    assert manifest["staging_readiness_summary"]["phase42_download_clicks_without_console_errors"] is True
    assert manifest["staging_readiness_summary"]["phase42_backend_export_integrity_passed"] is True
    assert manifest["staging_readiness_summary"]["phase42_native_download_event_supported"] is False
    assert manifest["staging_readiness_summary"]["phase42_native_os_download_verified"] is False
    assert manifest["staging_readiness_summary"]["phase42_global_generation_status_stale_after_result_visible"] is True
    assert manifest["staging_readiness_summary"]["phase42_production_browser_uat_completed"] is True
    assert manifest["staging_readiness_summary"]["staging_run_completed"] is False
    assert manifest["staging_readiness_summary"]["production_smoke_completed"] is True
    assert manifest["staging_readiness_summary"]["training_authorized"] is False
    assert all(os.path.exists(item["path"]) for item in manifest["artifacts"])
    assert all(step["side_effect"] is False for step in manifest["reviewer_use_steps"])
    assert all(value is False for value in manifest["guard_flags"].values())
    assert all(value is False for value in manifest["side_effect_boundary"].values())


def test_phase30_operator_reviewer_signoff_packet_guide_documents_operational_flow():
    guide = open(
        "docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/OPERATOR_PACKET_GUIDE.md",
        encoding="utf-8",
    ).read()
    checklist = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/operator_packet_checklist.json",
            encoding="utf-8",
        )
    )
    step_ids = {item["id"] for item in checklist["steps"]}

    assert "Phase 30 Operator Reviewer Sign-Off Packet Guide" in guide
    assert "OPERATOR_PACKET_READY_NO_TRAINING_AUTHORIZATION" in guide
    assert "generate_pending_signoff_record.py" in guide
    assert "validate_signoff_record.py" in guide
    assert "summarize_signoff_records.py" in guide
    assert "import_signoff_record.py" in guide
    assert 'DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/*.json' in guide
    assert "Sign-off summary" in guide
    assert "Sign-off JSON" in guide
    assert "does not authorize model training" in guide
    assert "does not authorize dataset upload" in guide
    assert "does not authorize provider fine-tune API calls" in guide
    assert "server-side reviewer JSON artifact write" in guide
    assert "ready_for_training_execution" in guide

    assert checklist["report_type"] == "document_ops_phase30_operator_reviewer_signoff_packet_checklist"
    assert checklist["phase"] == 30
    assert checklist["status"] == "operator_packet_ready_no_training_authorization"
    assert {"product_pm_reviewer", "ml_ai_owner", "compliance_security_reviewer", "release_owner"} <= set(
        checklist["required_reviewers"]
    )
    assert {
        "create_packet_directory",
        "generate_pending_signoff_record",
        "collect_human_reviewer_entries",
        "validate_completed_record",
        "summarize_packet_records",
        "copy_records_for_documentops_inspection",
        "inspect_documentops_signoff_summary",
        "inspect_documentops_signoff_json",
    } <= step_ids
    assert all(os.path.exists(path) for path in checklist["packet_artifacts"])
    assert "docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py" in checklist[
        "packet_artifacts"
    ]
    assert all(item["side_effect"] is False for item in checklist["steps"])
    assert checklist["pass_criteria"]["validator_valid_true"] is True
    assert checklist["pass_criteria"]["summary_has_no_boundary_violations"] is True
    assert all(value is False for value in checklist["authorization_boundary"].values())
    assert all(value is False for value in checklist["side_effect_boundary"].values())


def test_phase31_signoff_import_helper_copies_pending_and_completed_records_safely(tmp_path):
    generator_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py"
    import_path = "docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py"
    summary_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py"
    template_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json"
    data_dir = tmp_path / "data"
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    generated = subprocess.run(
        [
            "python",
            generator_path,
            "--output-dir",
            str(source_dir),
            "--record-id",
            "dsr_phase31pending",
            "--created-at",
            "2026-05-08T19:40:00+09:00",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert generated.returncode == 0
    pending_path = source_dir / "dsr_phase31pending_pending_signoff.json"

    dry_run = subprocess.run(
        [
            "python",
            import_path,
            str(pending_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "system",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    dry_run_body = json.loads(dry_run.stdout)
    assert dry_run.returncode == 0
    assert dry_run_body["dry_run"] is True
    assert dry_run_body["side_effect_boundary"]["tenant_local_record_copied"] is False
    assert not (data_dir / "tenants" / "system" / "trajectory_reviewer_signoffs").exists()

    pending_import = subprocess.run(
        [
            "python",
            import_path,
            str(pending_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "system",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    pending_body = json.loads(pending_import.stdout)
    pending_dest = type(tmp_path)(pending_body["destination_path"])
    assert pending_import.returncode == 0
    assert pending_body["report_type"] == "document_ops_phase31_reviewer_signoff_import_result"
    assert pending_body["record_state"] == "pending_manual_signoff_no_training_authorization"
    assert pending_body["validation_valid"] is False
    assert pending_body["import_boundary"]["server_side_generated_approval_record"] is False
    assert pending_body["import_boundary"]["training_execution_authorized"] is False
    assert pending_body["side_effect_boundary"]["tenant_local_record_copied"] is True
    assert pending_body["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert pending_dest.exists()
    assert json.load(open(pending_dest, encoding="utf-8"))["signoff_record_id"] == "dsr_phase31pending"

    completed = json.load(open(template_path, encoding="utf-8"))
    completed["status"] = "manual_signoff_complete"
    completed["signoff_record_id"] = "dsr_phase31done"
    completed["created_at"] = "2026-05-08T19:45:00+09:00"
    completed["signoff_boundary"]["actual_reviewer_approval_recorded"] = True
    for key in completed["completion_rule"]:
        completed["completion_rule"][key] = True
    for reviewer in completed["required_reviewers"]:
        reviewer["reviewer_name"] = f"{reviewer['reviewer_role']} name"
        reviewer["reviewer_title_or_team"] = "DocumentOps governance review"
        reviewer["reviewed_at"] = "2026-05-08T19:50:00+09:00"
        reviewer["decision"] = "sign_off_ready_for_human_review"
        reviewer["notes"] = "Completed human review while preserving no-training boundary."
        for ack in reviewer["required_acknowledgements"]:
            reviewer["required_acknowledgements"][ack] = True
    completed_path = source_dir / "completed.json"
    completed_path.write_text(json.dumps(completed), encoding="utf-8")

    completed_import = subprocess.run(
        [
            "python",
            import_path,
            str(completed_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "system",
            "--output-filename",
            "dsr_phase31done_completed_signoff.json",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    completed_body = json.loads(completed_import.stdout)
    completed_dest = type(tmp_path)(completed_body["destination_path"])
    assert completed_import.returncode == 0
    assert completed_body["record_state"] == "manual_signoff_complete_no_training_authorization"
    assert completed_body["validation_valid"] is True
    assert completed_body["source_sha256"] == completed_body["copied_sha256"]
    assert completed_body["import_boundary"]["actual_reviewer_approval_recorded_by_import"] is False
    assert completed_body["import_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert completed_dest.exists()

    signoff_dir = data_dir / "tenants" / "system" / "trajectory_reviewer_signoffs"
    summarized = subprocess.run(
        [
            "python",
            summary_path,
            str(signoff_dir),
            "--generated-at",
            "2026-05-08T19:55:00+09:00",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    summary = json.loads(summarized.stdout)
    records = {item["signoff_record_id"]: item for item in summary["records"]}
    assert summarized.returncode == 0
    assert summary["record_count"] == 2
    assert summary["overall_status"] == "pending_manual_signoff_no_training_authorization"
    assert summary["aggregate"]["completed_record_count"] == 1
    assert summary["aggregate"]["pending_record_count"] == 1
    assert records["dsr_phase31done"]["completed_validation"]["valid"] is True
    assert records["dsr_phase31pending"]["completed_validation"]["valid"] is False
    assert all(value is False for value in summary["side_effect_boundary"].values())


def test_phase31_signoff_import_helper_rejects_path_traversal_and_generated_approval(tmp_path):
    generator_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py"
    import_path = "docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py"
    template_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json"
    data_dir = tmp_path / "data"
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    generated = subprocess.run(
        [
            "python",
            generator_path,
            "--output-dir",
            str(source_dir),
            "--record-id",
            "dsr_phase31guard",
            "--created-at",
            "2026-05-08T20:00:00+09:00",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert generated.returncode == 0
    pending_path = source_dir / "dsr_phase31guard_pending_signoff.json"

    bad_filename = subprocess.run(
        [
            "python",
            import_path,
            str(pending_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "system",
            "--output-filename",
            "../escape.json",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    bad_filename_body = json.loads(bad_filename.stderr)
    assert bad_filename.returncode == 1
    assert bad_filename_body["ok"] is False
    assert "path separators" in bad_filename_body["error"]

    bad_tenant = subprocess.run(
        [
            "python",
            import_path,
            str(pending_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "../evil",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    bad_tenant_body = json.loads(bad_tenant.stderr)
    assert bad_tenant.returncode == 1
    assert bad_tenant_body["ok"] is False
    assert "tenant id must match" in bad_tenant_body["error"]

    template = json.load(open(template_path, encoding="utf-8"))
    generated_approval = json.loads(json.dumps(template))
    generated_approval["status"] = "manual_signoff_complete"
    generated_approval["signoff_record_id"] = "dsr_phase31fake"
    generated_approval["created_at"] = "2026-05-08T20:05:00+09:00"
    generated_approval["signoff_boundary"]["actual_reviewer_approval_recorded"] = True
    fake_approval_path = source_dir / "fake_completed_approval.json"
    fake_approval_path.write_text(json.dumps(generated_approval), encoding="utf-8")
    rejected_approval = subprocess.run(
        [
            "python",
            import_path,
            str(fake_approval_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "system",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    rejected_approval_body = json.loads(rejected_approval.stderr)
    assert rejected_approval.returncode == 1
    assert rejected_approval_body["ok"] is False
    assert "record is not importable" in rejected_approval_body["error"]
    assert "decision must not be pending" in rejected_approval_body["error"]

    boundary_break = json.load(open(pending_path, encoding="utf-8"))
    boundary_break["signoff_boundary"]["provider_fine_tune_api_call_authorized"] = True
    boundary_break_path = source_dir / "boundary_break.json"
    boundary_break_path.write_text(json.dumps(boundary_break), encoding="utf-8")
    rejected_boundary = subprocess.run(
        [
            "python",
            import_path,
            str(boundary_break_path),
            "--data-dir",
            str(data_dir),
            "--tenant-id",
            "system",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    rejected_boundary_body = json.loads(rejected_boundary.stderr)
    assert rejected_boundary.returncode == 1
    assert rejected_boundary_body["ok"] is False
    assert "protected signoff_boundary" in rejected_boundary_body["error"]
    assert not (data_dir / "tenants" / "evil").exists()
    assert not (data_dir / "escape.json").exists()


def test_phase32_imported_signoff_browser_qa_result_records_observed_pass():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/BROWSER_QA_REPORT.md",
        encoding="utf-8",
    ).read()
    result = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/browser_qa_result.json",
            encoding="utf-8",
        )
    )

    assert "Phase 32 Imported Reviewer Sign-Off Browser QA Report" in report
    assert "Result: PASS" in report
    assert "import_signoff_record.py" in report
    assert "tenant_local_record_copied=true" in report
    assert "server_side_generated_approval_record=false" in report
    assert "provider_fine_tune_api_call_authorized=false" in report
    assert "Sign-off summary" in report
    assert "Sign-off JSON" in report
    assert result["report_type"] == "document_ops_phase32_imported_signoff_browser_qa_result"
    assert result["phase"] == 32
    assert result["result"] == "pass"
    assert result["import_helper"]["pending_signoff_record_id"] == "dsr_phase32pending"
    assert result["import_helper"]["completed_signoff_record_id"] == "dsr_phase32done"
    assert result["import_helper"]["tenant_local_record_copied"] is True
    assert result["import_helper"]["actual_reviewer_approval_recorded_by_import"] is False
    assert result["import_helper"]["server_side_generated_approval_record"] is False
    assert result["api_checkpoints"]["summary"]["status_code"] == 200
    assert result["api_checkpoints"]["summary"]["record_count"] == 2
    assert result["api_checkpoints"]["summary"]["pending_record_visible_in_payload"] is True
    assert result["api_checkpoints"]["summary"]["completed_record_visible_in_payload"] is True
    assert result["api_checkpoints"]["download"]["status_code"] == 200
    assert result["api_checkpoints"]["download"]["server_file_written"] is False
    assert result["ui_checks"]["reviewer_signoff_summary_visible"] is True
    assert result["ui_checks"]["completed_record_visible"] is True
    assert result["ui_checks"]["pending_record_visible"] is True
    assert result["ui_checks"]["signoff_blocker_visible"] is True
    assert result["ui_checks"]["downloaded_json_contains_imported_records"] is True
    assert result["ui_checks"]["download_fallback_visible"] is True
    assert result["ui_checks"]["success_notification_visible"] is True
    assert result["ui_checks"]["no_training_notification_visible"] is True
    assert result["ui_checks"]["browser_action_errors"] == []
    assert all(value is False for value in result["guard_flags"].values())
    assert result["side_effect_boundary"]["tenant_local_record_copied_by_import_helper"] is True
    for key, value in result["side_effect_boundary"].items():
        if key != "tenant_local_record_copied_by_import_helper":
            assert value is False


def test_phase33_operator_release_packet_summary_packages_staging_readiness():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase33_operator_release_packet_summary/RELEASE_PACKET_SUMMARY.md",
        encoding="utf-8",
    ).read()
    summary = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase33_operator_release_packet_summary/release_packet_summary.json",
            encoding="utf-8",
        )
    )
    artifact_paths = {item["path"] for item in summary["release_packet_artifacts"]}
    flow_actions = {item["action"] for item in summary["operator_flow"]}
    criteria = summary["staging_readiness_criteria"]

    assert "Phase 33 Operator Release Packet Summary" in report
    assert "OPERATOR_RELEASE_PACKET_READY_NO_TRAINING_AUTHORIZATION" in report
    assert "Phase 30" in report
    assert "Phase 31" in report
    assert "Phase 32" in report
    assert "Staging-Readiness Criteria" in report
    assert "does not approve model training" in report
    assert "provider fine-tune API calls" in report
    assert "Phase 34" in report
    assert summary["report_type"] == "document_ops_phase33_operator_release_packet_summary"
    assert summary["phase"] == 33
    assert summary["status"] == "operator_release_packet_ready_no_training_authorization"
    assert {"product_pm_reviewer", "ml_ai_owner", "compliance_security_reviewer", "release_owner"} <= set(
        summary["required_reviewers"]
    )
    assert {
        "docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/OPERATOR_PACKET_GUIDE.md",
        "docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/operator_packet_checklist.json",
        "docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/IMPORT_HELPER.md",
        "docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py",
        "docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/BROWSER_QA_REPORT.md",
        "docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/browser_qa_result.json",
    } <= artifact_paths
    assert all(os.path.exists(path) for path in artifact_paths)
    assert {
        "read_release_boundary",
        "create_or_collect_reviewer_signoff_records",
        "validate_completed_records_locally",
        "import_records_with_phase31_helper_for_environment_inspection",
        "inspect_documentops_signoff_summary_and_json",
    } <= flow_actions
    assert all(step["current_packet_side_effect"] is False for step in summary["operator_flow"])
    assert criteria["local_import_helper_verified"] is True
    assert criteria["observed_browser_qa_passed"] is True
    assert criteria["ops_key_required"] is True
    assert criteria["tenant_local_record_scope"] is True
    assert criteria["server_generated_approval_blocked"] is True
    assert criteria["staging_run_completed"] is False
    assert criteria["production_smoke_completed"] is False
    assert criteria["training_authorized"] is False
    assert criteria["external_dataset_upload_authorized"] is False
    assert criteria["provider_fine_tune_api_call_authorized"] is False
    assert summary["approval_boundary"]["human_reviewer_signoff_still_required"] is True
    assert summary["approval_boundary"]["generated_reviewer_approval_allowed"] is False
    assert all(value is False for value in summary["guard_flags"].values())
    assert all(value is False for value in summary["side_effect_boundary"].values())


def test_phase34_staging_readiness_dry_run_probe_contract_and_fixture_pass(tmp_path):
    guide = open(
        "docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/STAGING_READINESS_DRY_RUN.md",
        encoding="utf-8",
    ).read()
    contract = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/staging_readiness_dry_run.json",
            encoding="utf-8",
        )
    )
    script_path = "docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/run_staging_readiness_probe.py"
    summary = {
        "report_type": "document_ops_phase25_signoff_summary_endpoint",
        "read_only": True,
        "record_count": 2,
        "records": [
            {"signoff_record_id": "dsr_phase34done"},
            {"signoff_record_id": "dsr_phase34pending"},
        ],
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
        "aggregate": {
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "side_effect_boundary": {
            "actual_reviewer_approval_recorded_by_summary": False,
            "training_execution_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "model_promoted": False,
        },
    }
    download = {
        "report_type": "document_ops_phase27_reviewer_signoff_summary_export",
        "read_only": True,
        "export_format": "json",
        "server_file_written": False,
        "summary": summary,
        "guard_flags": {
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
        },
        "side_effect_boundary": {
            "actual_reviewer_approval_recorded_by_export": False,
            "training_execution_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "server_file_written": False,
            "model_promoted": False,
        },
    }
    summary_path = tmp_path / "summary.json"
    download_path = tmp_path / "download.json"
    output_path = tmp_path / "phase34_probe_result.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    download_path.write_text(json.dumps(download), encoding="utf-8")

    probe = subprocess.run(
        [
            "python",
            script_path,
            "--summary-fixture",
            str(summary_path),
            "--download-fixture",
            str(download_path),
            "--expect-record-id",
            "dsr_phase34done",
            "--expect-record-id",
            "dsr_phase34pending",
            "--output",
            str(output_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    result = json.loads(probe.stdout)
    written_result = json.load(open(output_path, encoding="utf-8"))

    assert "Phase 34 Staging-Readiness Dry-Run" in guide
    assert "STAGING_READINESS_PROBE_READY_NO_TRAINING_AUTHORIZATION" in guide
    assert "GET /health" in guide
    assert "X-DecisionDoc-Ops-Key" in guide
    assert "server_file_written=false" in guide
    assert "does not start model training" in guide
    assert contract["report_type"] == "document_ops_phase34_staging_readiness_dry_run"
    assert contract["phase"] == 34
    assert contract["status"] == "staging_readiness_probe_ready_no_training_authorization"
    assert contract["environment_probe_status"]["real_staging_probe_completed"] is False
    assert contract["environment_probe_status"]["production_smoke_completed"] is False
    assert contract["probe_script"].endswith("run_staging_readiness_probe.py")
    assert all(item["side_effect"] is False for item in contract["read_only_probe_requests"])
    assert contract["pass_criteria"]["ops_key_required"] is True
    assert contract["pass_criteria"]["download_server_file_written_false"] is True
    assert contract["probe_result_requirements"]["training_authorized"] is False
    assert contract["probe_result_requirements"]["provider_fine_tune_api_call_authorized"] is False
    assert all(value is False for value in contract["guard_flags"].values())
    assert all(value is False for value in contract["side_effect_boundary"].values())
    assert probe.returncode == 0
    assert result == written_result
    assert result["report_type"] == "document_ops_phase34_staging_readiness_probe_result"
    assert result["phase"] == 34
    assert result["status"] == "pass"
    assert result["checkpoints"]["summary_auth_required"]["passed"] is True
    assert result["checkpoints"]["summary"]["record_count"] == 2
    assert result["checkpoints"]["download"]["server_file_written"] is False
    assert result["readiness"]["ops_key_required"] is True
    assert result["readiness"]["imported_signoff_visible"] is True
    assert result["readiness"]["json_download_contains_records"] is True
    assert result["readiness"]["download_json_in_memory_or_browser_blob_only"] is True
    assert result["readiness"]["guard_flags_clear"] is True
    assert result["readiness"]["staging_probe_completed"] is True
    assert result["readiness"]["production_smoke_completed"] is False
    assert result["readiness"]["training_authorized"] is False
    assert result["readiness"]["external_dataset_upload_authorized"] is False
    assert result["readiness"]["provider_fine_tune_api_call_authorized"] is False
    assert result["failures"] == []
    assert all(value is False for value in result["guard_flags"].values())
    assert all(value is False for value in result["side_effect_boundary"].values())


def test_phase35_observed_staging_probe_evidence_archive_helper_validates_results(tmp_path):
    guide = open(
        "docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/OBSERVED_STAGING_PROBE_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    contract = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/observed_staging_probe_evidence.json",
            encoding="utf-8",
        )
    )
    archive_helper = (
        "docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/"
        "archive_staging_probe_result.py"
    )
    probe_result = {
        "report_type": "document_ops_phase34_staging_readiness_probe_result",
        "phase": 34,
        "status": "pass",
        "observed_at": "2026-05-09T00:55:00+09:00",
        "target": {
            "base_url": "https://admin.decisiondoc.kr",
            "tenant_id": "system",
            "expected_record_ids": ["dsr_phase35done", "dsr_phase35pending"],
        },
        "checkpoints": {
            "health": {"status_code": 200},
            "summary_auth_required": {"status_code": 401, "passed": True},
            "summary": {
                "status_code": 200,
                "report_type": "document_ops_phase25_signoff_summary_endpoint",
                "record_count": 2,
                "observed_record_ids": ["dsr_phase35done", "dsr_phase35pending"],
                "passed": True,
            },
            "download": {
                "status_code": 200,
                "content_type": "application/json",
                "content_disposition": "attachment; filename=\"reviewer_signoff_summary_system.json\"",
                "report_type": "document_ops_phase27_reviewer_signoff_summary_export",
                "record_count": 2,
                "observed_record_ids": ["dsr_phase35done", "dsr_phase35pending"],
                "server_file_written": False,
                "passed": True,
            },
        },
        "readiness": {
            "ops_key_required": True,
            "imported_signoff_visible": True,
            "json_download_contains_records": True,
            "download_json_in_memory_or_browser_blob_only": True,
            "guard_flags_clear": True,
            "staging_probe_completed": True,
            "production_smoke_completed": False,
            "training_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "guard_flags": {
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "server_side_generated_approval_record": False,
        },
        "side_effect_boundary": {
            "actual_reviewer_approval_recorded_by_probe": False,
            "training_execution_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "provider_job_polled": False,
            "model_candidate_emitted": False,
            "model_promoted": False,
            "server_side_generated_approval_record": False,
            "server_side_export_artifact_written": False,
        },
        "failures": [],
    }
    probe_path = tmp_path / "phase34_probe_result.json"
    probe_path.write_text(json.dumps(probe_result), encoding="utf-8")
    output_dir = tmp_path / "archive"

    archived = subprocess.run(
        [
            "python",
            archive_helper,
            str(probe_path),
            "--output-dir",
            str(output_dir),
            "--output-filename",
            "phase35-observed-staging-probe-evidence.json",
            "--evidence-owner",
            "release_owner",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    archived_body = json.loads(archived.stdout)
    archive_path = output_dir / "phase35-observed-staging-probe-evidence.json"
    archive = json.load(open(archive_path, encoding="utf-8"))

    fixture_result = json.loads(json.dumps(probe_result))
    fixture_result["target"]["base_url"] = "fixture://phase34"
    fixture_path = tmp_path / "fixture_probe_result.json"
    fixture_path.write_text(json.dumps(fixture_result), encoding="utf-8")
    rejected = subprocess.run(
        [
            "python",
            archive_helper,
            str(fixture_path),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    rejected_body = json.loads(rejected.stderr)

    assert "Phase 35 Observed Staging Probe Evidence" in guide
    assert "OBSERVED_STAGING_PROBE_ARCHIVE_READY_NO_TRAINING_AUTHORIZATION" in guide
    assert "DECISIONDOC_OPS_KEY" in guide
    assert "does not start model training" in guide
    assert contract["report_type"] == "document_ops_phase35_observed_staging_probe_evidence"
    assert contract["phase"] == 35
    assert contract["status"] == "observed_staging_probe_pending_missing_runtime_credentials"
    assert contract["environment_probe_status"]["real_staging_probe_completed"] is False
    assert contract["environment_probe_status"]["archive_helper_verified_with_fixture"] is True
    assert contract["archive_acceptance_criteria"]["fixture_probe_rejected"] is True
    assert contract["readiness"]["observed_staging_probe_completed"] is False
    assert contract["readiness"]["observed_staging_evidence_archive_ready"] is True
    assert contract["readiness"]["training_authorized"] is False
    assert all(value is False for value in contract["guard_flags"].values())
    assert all(value is False for value in contract["side_effect_boundary"].values())
    assert archived.returncode == 0
    assert archived_body["ok"] is True
    assert archived_body["status"] == "observed_staging_probe_archived_no_training_authorization"
    assert archive["report_type"] == "document_ops_phase35_observed_staging_probe_evidence_archive"
    assert archive["phase"] == 35
    assert archive["source_probe"]["report_type"] == "document_ops_phase34_staging_readiness_probe_result"
    assert archive["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert archive["checkpoint_summary"]["ops_key_required"] is True
    assert archive["checkpoint_summary"]["summary_record_count"] == 2
    assert archive["checkpoint_summary"]["download_server_file_written"] is False
    assert archive["readiness"]["observed_staging_probe_completed"] is True
    assert archive["readiness"]["production_smoke_completed"] is False
    assert archive["readiness"]["training_authorized"] is False
    assert all(value is False for value in archive["archive_boundary"].values())
    assert rejected.returncode == 1
    assert rejected_body["ok"] is False
    assert any("fixture probe results cannot be archived" in error for error in rejected_body["errors"])


def test_phase36_observed_probe_execution_workflow_preflights_runtime_inputs(tmp_path):
    guide = open(
        "docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/OBSERVED_PROBE_EXECUTION_WORKFLOW.md",
        encoding="utf-8",
    ).read()
    contract = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/observed_probe_execution_workflow.json",
            encoding="utf-8",
        )
    )
    runner = (
        "docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/"
        "run_observed_probe_workflow.py"
    )
    env_file = tmp_path / "phase36.env"
    env_file.write_text(
        "\n".join(
            [
                "DECISIONDOC_OPS_KEY=phase36-secret-value",
                "PHASE36_BASE_URL=https://admin.decisiondoc.kr",
                "PHASE36_EXPECT_RECORD_IDS=dsr_phase36done,dsr_phase36pending",
                "PHASE36_TENANT_ID=system",
            ]
        ),
        encoding="utf-8",
    )
    clean_env = os.environ.copy()
    for key in (
        "DECISIONDOC_OPS_KEY",
        "PHASE36_BASE_URL",
        "PHASE35_BASE_URL",
        "SMOKE_BASE_URL",
        "PHASE36_EXPECT_RECORD_IDS",
        "PHASE34_EXPECT_RECORD_IDS",
        "PHASE36_TENANT_ID",
    ):
        clean_env.pop(key, None)
    ready = subprocess.run(
        [
            "python",
            runner,
            "--env-file",
            str(env_file),
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=clean_env,
    )
    ready_body = json.loads(ready.stdout)
    missing = subprocess.run(
        [
            "python",
            runner,
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=clean_env,
    )
    missing_body = json.loads(missing.stdout)

    assert "Phase 36 Observed Probe Execution Workflow" in guide
    assert "OBSERVED_PROBE_EXECUTION_WORKFLOW_READY_NO_TRAINING_AUTHORIZATION" in guide
    assert "never prints the ops key" in guide
    assert "does not import sign-off records" in guide
    assert contract["report_type"] == "document_ops_phase36_observed_probe_execution_workflow"
    assert contract["phase"] == 36
    assert contract["status"] == "observed_probe_execution_workflow_ready_no_training_authorization"
    assert contract["environment_probe_status"]["env_file_ops_key_available"] is True
    assert contract["environment_probe_status"]["base_url_available"] is False
    assert contract["environment_probe_status"]["expected_record_ids_available"] is False
    assert contract["required_runtime_inputs"]["base_url"] is True
    assert contract["required_runtime_inputs"]["ops_key"] is True
    assert contract["required_runtime_inputs"]["expected_record_ids"] is True
    assert contract["readiness"]["workflow_ready"] is True
    assert contract["readiness"]["observed_staging_probe_completed"] is False
    assert contract["readiness"]["training_authorized"] is False
    assert all(value is False for value in contract["guard_flags"].values())
    assert all(value is False for value in contract["side_effect_boundary"].values())
    assert ready.returncode == 0
    assert ready_body["report_type"] == "document_ops_phase36_observed_probe_execution_preflight_result"
    assert ready_body["status"] == "ready_for_observed_probe_execution"
    assert ready_body["runtime"]["base_url"] == "https://admin.decisiondoc.kr"
    assert ready_body["runtime"]["ops_key_available"] is True
    assert ready_body["runtime"]["expected_record_ids"] == ["dsr_phase36done", "dsr_phase36pending"]
    assert ready_body["missing_inputs"] == []
    assert ready_body["readiness"]["observed_probe_can_run"] is True
    assert ready_body["readiness"]["training_authorized"] is False
    assert "phase36-secret-value" not in ready.stdout
    assert missing.returncode == 1
    assert missing_body["status"] == "blocked_missing_runtime_inputs"
    assert {"base_url", "DECISIONDOC_OPS_KEY", "expected_signoff_record_ids"} <= set(
        missing_body["missing_inputs"]
    )
    assert missing_body["readiness"]["observed_probe_can_run"] is False


def test_phase36_observed_probe_workflow_creates_output_dir_before_probe(tmp_path):
    runner = (
        "docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/"
        "run_observed_probe_workflow.py"
    )
    env_file = tmp_path / "phase36.env"
    env_file.write_text(
        "\n".join(
            [
                "DECISIONDOC_OPS_KEY=phase36-secret-value",
                "PHASE36_TENANT_ID=system",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "missing" / "phase36-output"

    result = subprocess.run(
        [
            "python",
            runner,
            "--env-file",
            str(env_file),
            "--base-url",
            "http://127.0.0.1:9",
            "--expect-record-id",
            "dsr_phase36done",
            "--output-dir",
            str(output_dir),
            "--timeout",
            "0.1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    body = json.loads(result.stdout)

    assert result.returncode == 1
    assert output_dir.is_dir()
    assert (output_dir / "phase34-staging-readiness.json").exists()
    assert (output_dir / "phase36-observed-probe-workflow-result.json").exists()
    assert body["status"] == "phase34_probe_failed"
    assert body["probe_result"]["report_type"] == "document_ops_phase34_staging_readiness_probe_result"
    assert body["readiness"]["observed_staging_probe_completed"] is False
    assert "FileNotFoundError" not in result.stdout
    assert "FileNotFoundError" not in result.stderr
    assert "phase36-secret-value" not in result.stdout


def test_phase37_deployed_probe_failure_evidence_records_ops_key_auth_blocker():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase37_deployed_probe_failure_evidence/DEPLOYED_PROBE_FAILURE_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    evidence = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase37_deployed_probe_failure_evidence/deployed_probe_failure_evidence.json",
            encoding="utf-8",
        )
    )

    assert "Phase 37 Deployed Probe Failure Evidence" in report
    assert "DEPLOYED_PROBE_BLOCKED_OPS_KEY_AUTH_FAILED_NO_TRAINING_AUTHORIZATION" in report
    assert "GET /health" in report
    assert "401" in report
    assert "did not start model training" in report
    assert "deployed `DECISIONDOC_OPS_KEY`" in report
    assert evidence["report_type"] == "document_ops_phase37_deployed_probe_failure_evidence"
    assert evidence["phase"] == 37
    assert evidence["status"] == "deployed_probe_blocked_ops_key_auth_failed_no_training_authorization"
    assert evidence["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert evidence["target"]["ops_key_source"] == ".github-actions.env"
    assert evidence["target"]["ops_key_value_recorded"] is False
    assert evidence["checkpoint_summary"]["health_status_code"] == 200
    assert evidence["checkpoint_summary"]["summary_without_ops_key_status_code"] == 401
    assert evidence["checkpoint_summary"]["summary_with_env_file_ops_key_status_code"] == 401
    assert evidence["checkpoint_summary"]["download_with_env_file_ops_key_status_code"] == 401
    assert evidence["readiness"]["deployed_health_reachable"] is True
    assert evidence["readiness"]["ops_key_required"] is True
    assert evidence["readiness"]["ops_key_authenticated"] is False
    assert evidence["readiness"]["expected_record_ids_available"] is False
    assert evidence["readiness"]["observed_staging_probe_completed"] is False
    assert evidence["readiness"]["observed_staging_evidence_archived"] is False
    assert evidence["readiness"]["training_authorized"] is False
    assert evidence["inferred_blocker"]["type"] == "deployed_ops_key_mismatch_or_missing_runtime_secret"
    assert "Provide the current deployed ops key" in evidence["next_step"]
    assert all(value is False for value in evidence["guard_flags"].values())
    assert all(value is False for value in evidence["side_effect_boundary"].values())


def test_phase38_observed_probe_retry_records_wrapper_fix_and_remaining_ops_key_blocker():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase38_observed_probe_retry/DEPLOYED_PROBE_RETRY_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    evidence = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase38_observed_probe_retry/deployed_probe_retry_evidence.json",
            encoding="utf-8",
        )
    )

    assert "Phase 38 Observed Probe Retry Evidence" in report
    assert "DEPLOYED_PROBE_RETRIED_OPS_KEY_AUTH_FAILED_NO_TRAINING_AUTHORIZATION" in report
    assert "output directory before invoking the Phase 34 probe" in report
    assert "did not start model training" in report
    assert evidence["report_type"] == "document_ops_phase38_observed_probe_retry_evidence"
    assert evidence["phase"] == 38
    assert evidence["status"] == "deployed_probe_retried_ops_key_auth_failed_no_training_authorization"
    assert evidence["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert evidence["target"]["expected_record_ids"] == ["dsr_phase32done", "dsr_phase32pending"]
    assert evidence["target"]["ops_key_value_recorded"] is False
    assert evidence["wrapper_result"]["output_dir_created_before_probe"] is True
    assert evidence["wrapper_result"]["preflight_status"] == "ready_for_observed_probe_execution"
    assert evidence["wrapper_result"]["probe_output_written"] is True
    assert evidence["wrapper_result"]["workflow_output_written"] is True
    assert evidence["checkpoint_summary"]["health_status_code"] == 200
    assert evidence["checkpoint_summary"]["summary_without_ops_key_status_code"] == 401
    assert evidence["checkpoint_summary"]["summary_with_env_file_ops_key_status_code"] == 401
    assert evidence["checkpoint_summary"]["download_with_env_file_ops_key_status_code"] == 401
    assert evidence["readiness"]["deployed_health_reachable"] is True
    assert evidence["readiness"]["ops_key_required"] is True
    assert evidence["readiness"]["ops_key_authenticated"] is False
    assert evidence["readiness"]["observed_staging_probe_completed"] is False
    assert evidence["inferred_blocker"]["type"] == "deployed_ops_key_mismatch_or_missing_runtime_secret"
    assert all(value is False for value in evidence["guard_flags"].values())
    assert all(value is False for value in evidence["side_effect_boundary"].values())


def test_phase39_remote_runtime_gap_records_route_and_signoff_storage_blockers():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase39_remote_runtime_gap/REMOTE_RUNTIME_GAP_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    evidence = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase39_remote_runtime_gap/remote_runtime_gap_evidence.json",
            encoding="utf-8",
        )
    )

    assert "Phase 39 Remote Runtime Gap Evidence" in report
    assert "REMOTE_RUNTIME_GAP_IDENTIFIED_NO_TRAINING_AUTHORIZATION" in report
    assert "Using the deployed ops key in memory changed" in report
    assert "did not deploy code" in report
    assert evidence["report_type"] == "document_ops_phase39_remote_runtime_gap_evidence"
    assert evidence["phase"] == 39
    assert evidence["status"] == "remote_runtime_gap_identified_no_training_authorization"
    assert evidence["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert evidence["credential_findings"]["deployed_ops_key_present"] is True
    assert evidence["credential_findings"]["deployed_ops_key_value_recorded"] is False
    assert evidence["credential_findings"]["deployed_ops_key_used_in_memory_only"] is True
    assert evidence["credential_findings"]["local_probe_key_matches_deployed"] is False
    assert evidence["checkpoint_summary"]["health_status_code"] == 200
    assert evidence["checkpoint_summary"]["summary_without_ops_key_status_code"] == 401
    assert evidence["checkpoint_summary"]["summary_with_deployed_ops_key_status_code"] == 404
    assert evidence["checkpoint_summary"]["download_with_deployed_ops_key_status_code"] == 404
    assert evidence["checkpoint_summary"]["summary_safe_body"] == {"detail": "Not Found"}
    assert evidence["remote_runtime"]["remote_commit"] == "011aec5"
    assert evidence["remote_runtime"]["document_ops_route_ref_files"] == 0
    assert evidence["remote_runtime"]["signoff_dir_present"] is False
    assert evidence["readiness"]["deployed_ops_key_runtime_valid"] is True
    assert evidence["readiness"]["document_ops_reviewer_signoff_route_deployed"] is False
    assert evidence["readiness"]["signoff_storage_present"] is False
    assert evidence["inferred_blocker"]["type"] == (
        "deployed_code_missing_document_ops_reviewer_signoff_routes_and_records"
    )
    assert all(value is False for value in evidence["guard_flags"].values())
    assert all(value is False for value in evidence["side_effect_boundary"].values())


def test_phase40_production_signoff_completion_evidence_records_deployed_probe_pass():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase40_production_signoff_completion_evidence/PRODUCTION_SIGNOFF_COMPLETION_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    evidence = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase40_production_signoff_completion_evidence/production_signoff_completion_evidence.json",
            encoding="utf-8",
        )
    )

    assert "Phase 40 Production Sign-Off Completion Evidence" in report
    assert "PRODUCTION_SIGNOFF_COMPLETION_OBSERVED_NO_TRAINING_AUTHORIZATION" in report
    assert "reviewer sign-off summary with deployed ops key" in report
    assert "did not upload datasets" in report
    assert evidence["report_type"] == "document_ops_phase40_production_signoff_completion_evidence"
    assert evidence["phase"] == 40
    assert evidence["status"] == "production_signoff_completion_observed_no_training_authorization"
    assert evidence["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert evidence["target"]["expected_record_ids"] == [
        "dsr_phase41prod_pending",
        "dsr_phase41prod_done",
    ]
    assert evidence["credential_findings"]["deployed_ops_key_present"] is True
    assert evidence["credential_findings"]["deployed_ops_key_used_in_memory_only"] is True
    assert evidence["credential_findings"]["ops_key_value_recorded"] is False
    assert evidence["checkpoint_summary"]["health_status_code"] == 200
    assert evidence["checkpoint_summary"]["summary_without_ops_key_status_code"] == 401
    assert evidence["checkpoint_summary"]["summary_status_code"] == 200
    assert evidence["checkpoint_summary"]["download_status_code"] == 200
    assert evidence["checkpoint_summary"]["summary_record_count"] == 2
    assert evidence["checkpoint_summary"]["download_record_count"] == 2
    assert evidence["checkpoint_summary"]["download_server_file_written"] is False
    assert set(evidence["checkpoint_summary"]["summary_observed_record_ids"]) == {
        "dsr_phase41prod_pending",
        "dsr_phase41prod_done",
    }
    assert set(evidence["checkpoint_summary"]["download_observed_record_ids"]) == {
        "dsr_phase41prod_pending",
        "dsr_phase41prod_done",
    }
    assert evidence["imported_records"]["completed_record"]["signoff_record_id"] == "dsr_phase41prod_done"
    assert evidence["imported_records"]["completed_record"]["validation_valid"] is True
    assert evidence["imported_records"]["completed_record"]["validation_error_count"] == 0
    assert evidence["imported_records"]["completed_record"]["actual_reviewer_approval_recorded"] is True
    assert evidence["imported_records"]["pending_record"]["signoff_record_id"] == "dsr_phase41prod_pending"
    assert evidence["probe_artifacts"]["phase36_workflow_status"] == (
        "observed_probe_archived_no_training_authorization"
    )
    assert evidence["remote_runtime"]["remote_commit"] == "daad0bc8c601"
    assert evidence["remote_runtime"]["signoff_dir_present"] is True
    assert evidence["readiness"]["ops_key_authenticated"] is True
    assert evidence["readiness"]["document_ops_reviewer_signoff_route_deployed"] is True
    assert evidence["readiness"]["signoff_storage_present"] is True
    assert evidence["readiness"]["expected_record_ids_available"] is True
    assert evidence["readiness"]["observed_staging_probe_completed"] is True
    assert evidence["readiness"]["observed_staging_evidence_archived"] is True
    assert evidence["readiness"]["production_smoke_completed"] is False
    assert evidence["readiness"]["training_authorized"] is False
    assert evidence["readiness"]["provider_fine_tune_api_call_authorized"] is False
    assert all(value is False for value in evidence["guard_flags"].values())
    assert evidence["side_effect_boundary"]["signoff_record_imported"] is True
    assert evidence["side_effect_boundary"]["local_archive_written"] is True
    assert evidence["side_effect_boundary"]["local_probe_result_written"] is True
    assert evidence["side_effect_boundary"]["training_execution_started"] is False
    assert evidence["side_effect_boundary"]["external_dataset_uploaded"] is False
    assert evidence["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert evidence["side_effect_boundary"]["provider_job_created"] is False
    assert evidence["side_effect_boundary"]["model_promoted"] is False
    assert evidence["side_effect_boundary"]["server_side_export_artifact_written"] is False
    assert evidence["side_effect_boundary"]["server_side_generated_approval_record"] is False


def test_phase41_production_post_deploy_smoke_evidence_records_generation_and_workflow_pass():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase41_production_post_deploy_smoke_evidence/PRODUCTION_POST_DEPLOY_SMOKE_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    evidence = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase41_production_post_deploy_smoke_evidence/production_post_deploy_smoke_evidence.json",
            encoding="utf-8",
        )
    )

    assert "Phase 41 Production Post-Deploy Smoke Evidence" in report
    assert "PRODUCTION_POST_DEPLOY_SMOKE_PASSED_NO_TRAINING_AUTHORIZATION" in report
    assert "intentionally exercised normal production document-generation paths" in report
    assert "Still not allowed and not observed" in report
    assert evidence["report_type"] == "document_ops_phase41_production_post_deploy_smoke_evidence"
    assert evidence["phase"] == 41
    assert evidence["status"] == "production_post_deploy_smoke_passed_no_training_authorization"
    assert evidence["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert evidence["target"]["smoke_timeout_sec"] == 180
    assert evidence["post_deploy_report"]["sha256"] == (
        "604adb69d21e9b5bb62dbccc2a41fec6256817cc38474a4bb7e6e785ab29abb0"
    )
    assert evidence["checkpoint_summary"]["status"] == "passed"
    assert evidence["checkpoint_summary"]["health_status_code"] == 200
    assert evidence["checkpoint_summary"]["docker_compose_ps_passed"] is True
    assert evidence["checkpoint_summary"]["nginx_config_test_passed"] is True
    assert evidence["checkpoint_summary"]["deployed_smoke_passed"] is True
    assert evidence["checkpoint_summary"]["report_workflow_smoke_passed"] is True
    assert evidence["checkpoint_summary"]["provider_policy_quality_first"] == "ok"
    assert all(value == "ok" for value in evidence["checkpoint_summary"]["provider_route_checks"].values())
    assert evidence["provider_routes"]["generation"] == "claude,openai,gemini"
    assert evidence["document_generation_smoke"]["generate_no_key_status"] == 401
    assert evidence["document_generation_smoke"]["generate_auth_status"] == 200
    assert evidence["document_generation_smoke"]["generate_export_auth_status"] == 200
    assert evidence["document_generation_smoke"]["generate_export_files"] == 4
    assert evidence["document_generation_smoke"]["with_attachments_no_key_status"] == 401
    assert evidence["document_generation_smoke"]["with_attachments_auth_status"] == 200
    assert evidence["document_generation_smoke"]["with_attachments_files"] == 1
    assert evidence["document_generation_smoke"]["with_attachments_docs"] == 4
    assert evidence["document_generation_smoke"]["from_documents_no_key_status"] == 401
    assert evidence["document_generation_smoke"]["from_documents_auth_status"] == 200
    assert evidence["document_generation_smoke"]["from_documents_files"] == 1
    assert evidence["document_generation_smoke"]["from_documents_docs"] == 2
    assert evidence["report_workflow_smoke"]["report_workflow_no_key_status"] == 401
    assert evidence["report_workflow_smoke"]["report_workflow_auth_status"] == 200
    assert evidence["report_workflow_smoke"]["slides_generate_before_planning_status"] == 400
    assert evidence["report_workflow_smoke"]["planning_generate_status"] == 200
    assert evidence["report_workflow_smoke"]["planning_generate_slide_plans"] == 2
    assert evidence["report_workflow_smoke"]["slides_generate_count"] == 2
    assert evidence["report_workflow_smoke"]["final_submit_before_slide_approvals_status"] == 400
    assert evidence["report_workflow_smoke"]["slide_approvals"] == 2
    assert evidence["report_workflow_smoke"]["final_submit_after_slide_approvals_status"] == 200
    assert evidence["report_workflow_smoke"]["executive_approve_before_pm_status"] == 400
    assert evidence["report_workflow_smoke"]["pm_approve_status"] == 200
    assert evidence["report_workflow_smoke"]["executive_approve_after_pm_status"] == 200
    assert evidence["report_workflow_smoke"]["project_create_status"] == 200
    assert evidence["report_workflow_smoke"]["promote_status"] == 200
    assert evidence["report_workflow_smoke"]["pptx_export_status"] == 200
    assert evidence["report_workflow_smoke"]["pptx_export_bytes"] > 0
    assert evidence["report_workflow_smoke"]["snapshot_export_status"] == 200
    assert evidence["report_workflow_smoke"]["snapshot_export_version"] == (
        "decisiondoc_report_workflow_snapshot.v1"
    )
    assert evidence["allowed_runtime_side_effects"]["normal_generation_provider_calls_made"] is True
    assert evidence["allowed_runtime_side_effects"]["runtime_bundles_created"] is True
    assert evidence["allowed_runtime_side_effects"]["report_workflow_records_created"] is True
    assert evidence["allowed_runtime_side_effects"]["project_document_promoted"] is True
    assert evidence["allowed_runtime_side_effects"]["pptx_export_response_generated"] is True
    assert evidence["allowed_runtime_side_effects"]["post_deploy_report_written"] is True
    assert all(value is False for value in evidence["restricted_side_effect_boundary"].values())


def test_phase42_production_browser_uat_evidence_records_ui_export_and_workflow_checks():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase42_production_browser_uat_evidence/PRODUCTION_BROWSER_UAT_EVIDENCE.md",
        encoding="utf-8",
    ).read()
    evidence = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase42_production_browser_uat_evidence/production_browser_uat_evidence.json",
            encoding="utf-8",
        )
    )

    assert "Phase 42 Production Browser UAT Evidence" in report
    assert "PRODUCTION_BROWSER_UAT_PASSED_WITH_DOWNLOAD_RUNTIME_LIMITATION_NO_TRAINING_AUTHORIZATION" in report
    assert "Codex in-app browser does not support native download events" in report
    assert "Report Workflow UI UAT" in report
    assert evidence["report_type"] == "document_ops_phase42_production_browser_uat_evidence"
    assert evidence["phase"] == 42
    assert evidence["status"] == (
        "production_browser_uat_passed_with_download_runtime_limitation_no_training_authorization"
    )
    assert evidence["target"]["base_url"] == "https://admin.decisiondoc.kr"
    assert evidence["browser_runtime"]["runtime"] == "Codex in-app browser"
    assert evidence["browser_runtime"]["session_user"] == "안성진 · PM"
    assert evidence["browser_runtime"]["download_event_supported"] is False
    assert "Downloads are not supported" in evidence["browser_runtime"]["download_error"]
    assert evidence["checkpoint_summary"]["status"] == "passed_with_download_runtime_limitation"
    assert evidence["checkpoint_summary"]["document_generation_ui_passed"] is True
    assert evidence["checkpoint_summary"]["download_clicks_without_console_errors"] is True
    assert evidence["checkpoint_summary"]["backend_export_integrity_passed"] is True
    assert evidence["checkpoint_summary"]["report_workflow_ui_passed"] is True
    assert evidence["checkpoint_summary"]["native_os_download_verified"] is False
    assert evidence["document_generation_ui"]["status"] == "passed"
    assert evidence["document_generation_ui"]["clicked_generate"] is True
    assert evidence["document_generation_ui"]["clicked_sketch_accept"] is True
    assert evidence["document_generation_ui"]["sketch_rendered"] is True
    assert evidence["document_generation_ui"]["generated_heading_visible"] is True
    assert evidence["document_generation_ui"]["fallback_generation_label_visible"] is True
    assert evidence["document_generation_ui"]["individual_download_controls_visible"] is True
    assert evidence["document_generation_ui"]["input"]["title"] == "HWPX 운영 검증 20260504"
    assert {"PPT 다운로드", "HWP", "PDF", "결재 요청"} <= set(
        evidence["document_generation_ui"]["result_action_buttons_visible"]
    )
    assert all(item["clicked"] is True for item in evidence["download_click_checks"].values())
    assert all(item["console_errors"] == [] for item in evidence["download_click_checks"].values())
    assert all(item["download_event"] is False for item in evidence["download_click_checks"].values())
    assert evidence["backend_export_integrity"]["pdf"]["status"] == 200
    assert evidence["backend_export_integrity"]["pdf"]["valid_magic"] is True
    assert evidence["backend_export_integrity"]["pdf"]["content_type"] == "application/pdf"
    assert evidence["backend_export_integrity"]["pptx"]["status"] == 200
    assert evidence["backend_export_integrity"]["pptx"]["valid_zip"] is True
    assert evidence["backend_export_integrity"]["pptx"]["required_entries_present"] is True
    assert "ppt/slides/slide1.xml" in evidence["backend_export_integrity"]["pptx"]["slide_entries"]
    assert evidence["backend_export_integrity"]["hwp"]["status"] == 200
    assert evidence["backend_export_integrity"]["hwp"]["valid_zip"] is True
    assert evidence["backend_export_integrity"]["hwp"]["required_entries_present"] is True
    assert "Contents/section0.xml" in evidence["backend_export_integrity"]["hwp"]["required_entries"]
    assert evidence["report_workflow_ui"]["status"] == "passed"
    assert evidence["report_workflow_ui"]["report_workflow_tab_visible"] is True
    assert evidence["report_workflow_ui"]["stepper_visible"] is True
    assert evidence["report_workflow_ui"]["project_creation_form_visible"] is True
    assert evidence["report_workflow_ui"]["planning_section_visible"] is True
    assert evidence["report_workflow_ui"]["slides_section_visible"] is True
    assert evidence["report_workflow_ui"]["final_section_visible"] is True
    assert evidence["report_workflow_ui"]["final_status"] == "final_approved"
    assert evidence["report_workflow_ui"]["slide_approval_count"] == evidence["report_workflow_ui"]["slide_count"]
    assert evidence["report_workflow_ui"]["workflow_pptx_export_button_visible"] is True
    assert evidence["report_workflow_ui"]["snapshot_export_button_visible"] is True
    assert evidence["report_workflow_ui"]["project_document_saved"] is True
    assert evidence["report_workflow_ui"]["learning_opt_in_disabled"] is True
    assert evidence["follow_ups"]["global_generation_status_stale_after_result_visible"] is True
    assert evidence["follow_ups"]["native_download_event_supported"] is False
    assert evidence["follow_ups"]["manual_os_download_open_check_required_if_release_requires_local_files"] is True
    assert evidence["allowed_runtime_side_effects"]["ui_document_generation_completed"] is True
    assert evidence["allowed_runtime_side_effects"]["normal_generation_provider_calls_made"] is True
    assert evidence["allowed_runtime_side_effects"]["production_export_endpoint_called"] is True
    assert evidence["allowed_runtime_side_effects"]["report_workflow_ui_inspected"] is True
    assert all(value is False for value in evidence["restricted_side_effect_boundary"].values())


def test_phase21_manual_reviewer_signoff_template_preserves_no_training_boundary():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/SIGNOFF_RECORD_TEMPLATE.md",
        encoding="utf-8",
    ).read()
    template = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json",
            encoding="utf-8",
        )
    )
    reviewers = {item["reviewer_role"]: item for item in template["required_reviewers"]}

    assert "Phase 21 Manual Reviewer Sign-Off Record Template" in report
    assert "TEMPLATE_ONLY_NO_ACTUAL_SIGNOFF" in report
    assert "does not authorize model training" in report
    assert "does not authorize dataset upload" in report
    assert "does not authorize provider fine-tune API calls" in report
    assert template["status"] == "template_only_no_actual_signoff"
    assert template["signoff_boundary"]["actual_reviewer_approval_recorded"] is False
    assert template["signoff_boundary"]["training_execution_authorized"] is False
    assert template["signoff_boundary"]["external_dataset_upload_authorized"] is False
    assert template["signoff_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert template["signoff_boundary"]["provider_job_creation_authorized"] is False
    assert template["signoff_boundary"]["model_promotion_authorized"] is False
    assert {"product_pm_reviewer", "ml_ai_owner", "compliance_security_reviewer", "release_owner"} <= set(reviewers)
    assert all(item["decision"] == "pending" for item in template["required_reviewers"])
    assert all(item["reviewer_name"] == "" for item in template["required_reviewers"])
    assert all(item["reviewed_at"] == "" for item in template["required_reviewers"])
    assert all(
        ack is False
        for item in template["required_reviewers"]
        for ack in item["required_acknowledgements"].values()
    )
    assert template["completion_rule"]["manual_signoff_complete"] is False


def test_phase22_signoff_validator_accepts_completed_records_and_rejects_boundary_breaks(tmp_path):
    template_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json"
    validator_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py"
    record = json.load(open(template_path, encoding="utf-8"))

    record["status"] = "manual_signoff_complete"
    record["signoff_boundary"]["actual_reviewer_approval_recorded"] = True
    for key in record["completion_rule"]:
        record["completion_rule"][key] = True
    for reviewer in record["required_reviewers"]:
        reviewer["reviewer_name"] = f"{reviewer['reviewer_role']} name"
        reviewer["reviewer_title_or_team"] = "DocumentOps governance review"
        reviewer["reviewed_at"] = "2026-05-08T10:00:00+09:00"
        reviewer["decision"] = "sign_off_ready_for_human_review"
        reviewer["notes"] = "Reviewed required evidence and no-training boundary."
        for ack in reviewer["required_acknowledgements"]:
            reviewer["required_acknowledgements"][ack] = True

    complete_path = tmp_path / "completed_signoff.json"
    complete_path.write_text(json.dumps(record), encoding="utf-8")
    completed = subprocess.run(
        ["python", validator_path, str(complete_path)],
        check=False,
        text=True,
        capture_output=True,
    )
    completed_body = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert completed_body["valid"] is True
    assert completed_body["error_count"] == 0
    assert {"product_pm_reviewer", "ml_ai_owner", "compliance_security_reviewer", "release_owner"} <= set(
        completed_body["reviewer_roles"]
    )

    broken = json.loads(json.dumps(record))
    broken["signoff_boundary"]["provider_fine_tune_api_call_authorized"] = True
    broken_path = tmp_path / "broken_signoff.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")
    rejected = subprocess.run(
        ["python", validator_path, str(broken_path)],
        check=False,
        text=True,
        capture_output=True,
    )
    rejected_body = json.loads(rejected.stdout)
    assert rejected.returncode == 1
    assert rejected_body["valid"] is False
    assert "signoff_boundary.provider_fine_tune_api_call_authorized must remain false" in rejected_body["errors"]


def test_phase23_pending_signoff_generator_creates_fillable_no_training_record(tmp_path):
    generator_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py"
    validator_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py"
    record_id = "dsr_phase23test"
    created_at = "2026-05-08T10:30:00+09:00"

    generated = subprocess.run(
        [
            "python",
            generator_path,
            "--output-dir",
            str(tmp_path),
            "--record-id",
            record_id,
            "--created-at",
            created_at,
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    generated_body = json.loads(generated.stdout)
    output_path = tmp_path / f"{record_id}_pending_signoff.json"
    record = json.load(open(output_path, encoding="utf-8"))

    assert generated.returncode == 0
    assert generated_body["ok"] is True
    assert generated_body["record_id"] == record_id
    assert generated_body["status"] == "pending_manual_signoff"
    assert generated_body["training_execution_authorized"] is False
    assert generated_body["provider_fine_tune_api_call_authorized"] is False
    assert record["report_type"] == "document_ops_phase23_pending_manual_reviewer_signoff_record"
    assert record["signoff_record_id"] == record_id
    assert record["created_at"] == created_at
    assert record["status"] == "pending_manual_signoff"
    assert record["generation_boundary"]["actual_reviewer_approval_recorded"] is False
    assert record["generation_boundary"]["training_execution_started"] is False
    assert record["generation_boundary"]["provider_fine_tune_api_called"] is False
    assert record["signoff_boundary"]["actual_reviewer_approval_recorded"] is False
    assert record["signoff_boundary"]["training_execution_authorized"] is False
    assert record["signoff_boundary"]["external_dataset_upload_authorized"] is False
    assert record["signoff_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert record["signoff_boundary"]["provider_job_creation_authorized"] is False
    assert record["signoff_boundary"]["model_promotion_authorized"] is False
    assert all(item["decision"] == "pending" for item in record["required_reviewers"])
    assert all(item["reviewer_name"] == "" for item in record["required_reviewers"])
    assert all(item["reviewed_at"] == "" for item in record["required_reviewers"])
    assert all(
        ack is False
        for item in record["required_reviewers"]
        for ack in item["required_acknowledgements"].values()
    )
    assert record["completion_rule"]["manual_signoff_complete"] is False

    validation = subprocess.run(
        ["python", validator_path, str(output_path)],
        check=False,
        text=True,
        capture_output=True,
    )
    validation_body = json.loads(validation.stdout)
    assert validation.returncode == 1
    assert validation_body["valid"] is False
    assert any("decision must not be pending" in error for error in validation_body["errors"])


def test_phase24_signoff_summary_reports_reviewer_completion_without_training_authorization(tmp_path):
    generator_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py"
    summary_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py"
    template_path = "docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json"
    pending_id = "dsr_phase24pending"
    completed_id = "dsr_phase24done"

    generated = subprocess.run(
        [
            "python",
            generator_path,
            "--output-dir",
            str(tmp_path),
            "--record-id",
            pending_id,
            "--created-at",
            "2026-05-08T11:00:00+09:00",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert generated.returncode == 0

    completed = json.load(open(template_path, encoding="utf-8"))
    completed["report_type"] = "document_ops_phase24_completed_manual_reviewer_signoff_record_fixture"
    completed["status"] = "manual_signoff_complete"
    completed["signoff_record_id"] = completed_id
    completed["created_at"] = "2026-05-08T11:10:00+09:00"
    completed["signoff_boundary"]["actual_reviewer_approval_recorded"] = True
    for key in completed["completion_rule"]:
        completed["completion_rule"][key] = True
    for reviewer in completed["required_reviewers"]:
        reviewer["reviewer_name"] = f"{reviewer['reviewer_role']} name"
        reviewer["reviewer_title_or_team"] = "DocumentOps governance review"
        reviewer["reviewed_at"] = "2026-05-08T11:15:00+09:00"
        reviewer["decision"] = "sign_off_ready_for_human_review"
        reviewer["notes"] = "Completed human review while preserving no-training boundary."
        for ack in reviewer["required_acknowledgements"]:
            reviewer["required_acknowledgements"][ack] = True
    completed_path = tmp_path / f"{completed_id}_completed_signoff.json"
    completed_path.write_text(json.dumps(completed), encoding="utf-8")

    report_path = tmp_path / "phase24_signoff_summary.json"
    summarized = subprocess.run(
        [
            "python",
            summary_path,
            str(tmp_path),
            "--generated-at",
            "2026-05-08T11:20:00+09:00",
            "--output",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    summary = json.loads(summarized.stdout)
    written_summary = json.load(open(report_path, encoding="utf-8"))
    records = {item["signoff_record_id"]: item for item in summary["records"]}

    assert summarized.returncode == 0
    assert summary == written_summary
    assert summary["report_type"] == "document_ops_phase24_signoff_record_summary"
    assert summary["generated_at"] == "2026-05-08T11:20:00+09:00"
    assert summary["record_count"] == 2
    assert summary["overall_status"] == "pending_manual_signoff_no_training_authorization"
    assert summary["aggregate"]["completed_record_count"] == 1
    assert summary["aggregate"]["pending_record_count"] == 1
    assert summary["aggregate"]["all_protected_training_flags_false"] is True
    assert summary["aggregate"]["training_execution_authorized"] is False
    assert summary["aggregate"]["external_dataset_upload_authorized"] is False
    assert summary["aggregate"]["provider_fine_tune_api_call_authorized"] is False
    assert summary["aggregate"]["provider_job_creation_authorized"] is False
    assert summary["aggregate"]["model_promotion_authorized"] is False
    assert all(value is False for value in summary["side_effect_boundary"].values())

    assert records[pending_id]["record_status"] == "pending_manual_signoff_no_training_authorization"
    assert records[pending_id]["reviewers_complete_count"] == 0
    assert records[pending_id]["pending_reviewer_count"] == 4
    assert records[pending_id]["completed_validation"]["valid"] is False
    assert records[pending_id]["boundary"]["training_execution_authorized"] is False
    assert records[pending_id]["boundary"]["provider_fine_tune_api_call_authorized"] is False

    assert records[completed_id]["record_status"] == "manual_signoff_complete_no_training_authorization"
    assert records[completed_id]["reviewers_complete_count"] == 4
    assert records[completed_id]["pending_reviewer_count"] == 0
    assert records[completed_id]["completed_validation"]["valid"] is True
    assert records[completed_id]["boundary"]["actual_reviewer_approval_recorded"] is True
    assert records[completed_id]["boundary"]["training_execution_authorized"] is False
    assert records[completed_id]["boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert all(item["complete"] is True for item in records[completed_id]["reviewers"])


def test_phase26_reviewer_signoff_browser_qa_result_records_observed_no_training_pass():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/BROWSER_QA_REPORT.md",
        encoding="utf-8",
    ).read()
    result = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/browser_qa_result.json",
            encoding="utf-8",
        )
    )

    assert "Phase 26 Reviewer Sign-Off Browser QA Report" in report
    assert "Result: PASS" in report
    assert "Reviewer Sign-Off Summary" in report
    assert "provider fine-tune APIs" in report
    assert result["result"] == "pass"
    assert result["seed"]["pending_signoff_record_id"] == "dsr_phase26pending"
    assert result["seed"]["completed_signoff_record_id"] == "dsr_phase26done"
    assert result["api_checkpoint"]["read_only"] is True
    assert result["api_checkpoint"]["overall_status"] == "pending_manual_signoff_no_training_authorization"
    assert result["ui_checks"]["reviewer_signoff_summary_visible"] is True
    assert result["ui_checks"]["completed_record_visible"] is True
    assert result["ui_checks"]["pending_record_visible"] is True
    assert result["ui_checks"]["signoff_blocker_visible"] is True
    assert result["ui_checks"]["browser_console_errors"] == []
    assert all(value is False for value in result["guard_flags"].values())
    assert all(value is False for value in result["side_effect_boundary"].values())


def test_phase28_reviewer_signoff_json_download_browser_qa_result_records_blob_received():
    report = open(
        "docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/BROWSER_QA_REPORT.md",
        encoding="utf-8",
    ).read()
    result = json.load(
        open(
            "docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/browser_qa_result.json",
            encoding="utf-8",
        )
    )

    assert "Phase 28 Reviewer Sign-Off JSON Download Browser QA Report" in report
    assert "Result: PASS" in report
    assert "Downloads are not supported by Codex In-app Browser" in report
    assert "server_file_written=false" in report
    assert result["result"] == "pass"
    assert result["seed"]["pending_signoff_record_id"] == "dsr_phase28pending"
    assert result["seed"]["completed_signoff_record_id"] == "dsr_phase28done"
    assert result["api_checkpoint"]["status_code"] == 200
    assert result["api_checkpoint"]["report_type"] == "document_ops_phase27_reviewer_signoff_summary_export"
    assert result["api_checkpoint"]["pending_record_visible_in_payload"] is True
    assert result["api_checkpoint"]["completed_record_visible_in_payload"] is True
    assert result["ui_checks"]["signoff_json_button_visible"] is True
    assert result["ui_checks"]["json_blob_received_by_browser"] is True
    assert result["ui_checks"]["download_fallback_visible"] is True
    assert result["ui_checks"]["success_notification_visible"] is True
    assert result["ui_checks"]["native_download_event_supported"] is False
    assert result["ui_checks"]["current_port_console_errors"] == []
    assert all(value is False for value in result["guard_flags"].values())
    assert all(value is False for value in result["side_effect_boundary"].values())


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

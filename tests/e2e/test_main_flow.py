"""Playwright E2E tests — core user flows."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid
from urllib import request as urllib_request

import pytest

pytestmark = pytest.mark.e2e


def _wait_until_any_visible(page, selectors: list[str], *, timeout_ms: int = 30000) -> str:
    """Poll locators until one becomes visible without using page-side eval."""
    deadline = timeout_ms // 250
    for _ in range(deadline):
        for selector in selectors:
            if page.locator(selector).is_visible():
                return selector
        page.wait_for_timeout(250)
    raise AssertionError(f"None of the selectors became visible: {selectors}")


def _wait_until_text_contains(page, selector: str, expected: str, *, timeout_ms: int = 5000) -> str:
    """Poll a locator's text until it contains the expected value."""
    deadline = max(timeout_ms // 250, 1)
    locator = page.locator(selector)
    for _ in range(deadline):
        if expected in locator.inner_text():
            return locator.inner_text()
        page.wait_for_timeout(250)
    raise AssertionError(f"{selector} did not contain {expected!r} within {timeout_ms}ms")


def _governance_inventory_payload(*, attention_required: bool) -> dict:
    directories = {
        "exports": "trajectory_exports",
        "freezes": "trajectory_freezes",
        "training_approvals": "trajectory_training_approvals",
        "training_execution_requests": "trajectory_training_execution_requests",
        "training_pre_execution_audits": "trajectory_training_audits",
    }
    collections = {
        name: {
            "directory": directory,
            "counts": {},
            "artifacts": [],
            "returned": 0,
            "truncated": False,
        }
        for name, directory in directories.items()
    }
    if attention_required:
        collections["exports"]["artifacts"] = [
            {
                "filename": "sft_tampered.jsonl",
                "relative_path": "tenants/system/trajectory_exports/sft_tampered.jsonl",
                "status": "referenced_tampered",
                "content_inspected": True,
            }
        ]
        collections["exports"]["returned"] = 1
        collections["training_pre_execution_audits"]["artifacts"] = [
            {
                "filename": "orphan.json",
                "relative_path": "tenants/system/trajectory_training_audits/orphan.json",
                "status": "unreferenced",
                "content_inspected": False,
            }
        ]
        collections["training_pre_execution_audits"]["returned"] = 1

    return {
        "report_type": "document_ops_governance_artifact_inventory",
        "tenant_id": "system",
        "backend": "local",
        "status": "attention_required" if attention_required else "clean",
        "read_only": True,
        "metadata": {
            "relative_path": "tenants/system/trajectory_metadata.json",
            "exists": True,
        },
        "counts": {
            "authoritative_references": 2,
            "observed_objects": 3 if attention_required else 2,
            "referenced_verified": 1 if attention_required else 2,
            "referenced_missing": 0,
            "referenced_tampered": 1 if attention_required else 0,
            "invalid_reference": 0,
            "unreferenced": 1 if attention_required else 0,
        },
        "collections": collections,
        "observation_boundary": {
            "metadata_snapshot_atomic": True,
            "multi_object_snapshot_atomic": False,
            "concurrent_writes_may_require_recheck": True,
        },
        "cleanup_boundary": {
            "automatic_cleanup_allowed": False,
            "objects_deleted": False,
            "manual_recheck_required": True,
        },
    }


def _governance_summary_payload(export_filename: str) -> dict:
    return {
        "report_type": "document_ops_training_governance_dashboard_summary",
        "read_only": True,
        "status": "governance_ready_for_human_review",
        "counts": {
            "reviewed_sft_exports": 1,
            "dataset_freezes": 0,
            "dry_run_training_approvals": 0,
            "training_execution_requests": 0,
            "pre_execution_audit_exports": 0,
        },
        "latest": {
            "reviewed_sft_export": {
                "filename": export_filename,
            }
        },
        "guard_counts": {},
        "artifact_chain": {},
        "audit_chain": {},
        "audit_checklist": {},
        "blockers": [],
        "no_side_effects": True,
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
    }


def _governance_signoff_payload(*, complete: bool) -> dict:
    status = (
        "manual_signoff_complete_no_training_authorization"
        if complete
        else "pending_manual_signoff_no_training_authorization"
    )
    return {
        "report_type": "document_ops_reviewer_signoff_summary",
        "read_only": True,
        "overall_status": status,
        "record_count": 1,
        "records": [
            {
                "signoff_record_id": "signoff-e2e",
                "filename": "signoff-e2e.json",
                "created_at": "2026-07-20T13:55:00+00:00",
                "record_status": status,
                "reviewers": [{"role": "reviewer", "complete": complete}],
                "reviewers_complete_count": 1 if complete else 0,
                "pending_reviewer_count": 0 if complete else 1,
                "changes_requested_count": 0,
                "blocked_count": 0,
                "completed_validation": {"valid": complete},
                "boundary": {
                    "training_execution_authorized": False,
                    "provider_fine_tune_api_call_authorized": False,
                },
            }
        ],
        "aggregate": {
            "completed_record_count": 1 if complete else 0,
            "pending_record_count": 0 if complete else 1,
            "manual_follow_up_record_count": 0,
            "boundary_violation_count": 0,
            "all_protected_training_flags_false": True,
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
        "blockers": [] if complete else ["reviewer_signoff_pending"],
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
    }


def _governance_overview_payload(
    *,
    attention_required: bool,
    signoff_complete: bool,
    export_filename: str,
) -> dict:
    status = (
        "artifact_integrity_attention"
        if attention_required
        else "review_evidence_ready"
        if signoff_complete
        else "reviewer_signoff_pending"
    )
    state_fingerprint = ("a" if attention_required else "b") * 64
    return {
        "report_type": "document_ops_governance_review_overview",
        "tenant_id": "system",
        "generated_at": "2026-07-20T14:00:00+00:00",
        "read_only": True,
        "status": status,
        "checks": [
            {
                "id": "artifact_integrity",
                "status": "attention" if attention_required else "passed",
                "summary": "권위 reference 2개, 검증 완료 1개, 문제 2개"
                if attention_required
                else "권위 reference 2개, 검증 완료 2개, 문제 0개",
            },
            {
                "id": "governance_chain",
                "status": "passed",
                "summary": "governance blocker 0개",
            },
            {
                "id": "reviewer_signoff",
                "status": "passed" if signoff_complete else "attention",
                "summary": "완료 1개, pending 0개, follow-up 0개"
                if signoff_complete
                else "완료 0개, pending 1개, follow-up 0개",
            },
        ],
        "next_review_action": (
            "권위 metadata와 selected backend artifact 차이를 먼저 확인하세요."
            if attention_required
            else "세 read-only 검토가 각각 통과했습니다."
            if signoff_complete
            else "Tenant-local reviewer sign-off를 완료하세요."
        ),
        "observation_boundary": {
            "source_reports_read_independently": True,
            "combined_snapshot_atomic": False,
            "manual_recheck_required": True,
        },
        "recheck_evidence": {
            "fingerprint_algorithm": "sha256",
            "review_state_fingerprint": state_fingerprint,
            "sources": [
                {
                    "source": "training_governance",
                    "report_type": "document_ops_training_governance_dashboard_summary",
                    "generated_at": "2026-07-20T13:59:57+00:00",
                    "fingerprint": "c" * 64,
                },
                {
                    "source": "artifact_inventory",
                    "report_type": "document_ops_governance_artifact_inventory",
                    "generated_at": None,
                    "fingerprint": ("d" if attention_required else "e") * 64,
                },
                {
                    "source": "reviewer_signoff",
                    "report_type": "document_ops_phase25_signoff_summary_endpoint",
                    "generated_at": "2026-07-20T13:59:59+00:00",
                    "fingerprint": ("f" if signoff_complete else "0") * 64,
                },
            ],
            "volatile_fields_excluded": ["source_report.generated_at"],
            "persisted": False,
        },
        "authorization_boundary": {
            "dataset_upload_authorized": False,
            "provider_api_call_authorized": False,
            "training_execution_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "training_governance_summary": _governance_summary_payload(export_filename),
        "artifact_inventory": _governance_inventory_payload(
            attention_required=attention_required
        ),
        "reviewer_signoff_summary": _governance_signoff_payload(
            complete=signoff_complete
        ),
    }


def _generate_to_results(page, title: str, goal: str) -> None:
    """Drive the current 2-step generate flow until results are visible."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.locator(".bundle-card").first.click()
    page.fill("#f-title", title)
    page.fill("#f-goal", goal)
    page.click("#generate-btn")
    visible = _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)
    if visible == "#sketch-panel":
        page.click("#sketch-confirm-btn")
    page.wait_for_selector("#results", state="visible", timeout=30000)


def _create_project_with_document(page, name: str = "조달 UI 테스트") -> str:
    return page.evaluate(
        """async ({ name }) => {
          const token = localStorage.getItem('dd_access_token');
          const headers = {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          };
          const created = await fetch('/projects', {
            method: 'POST',
            headers,
            body: JSON.stringify({ name, fiscal_year: 2026 }),
          });
          if (!created.ok) throw new Error(`project create failed: ${created.status}`);
          const project = await created.json();
          const added = await fetch(`/projects/${project.project_id}/documents`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              request_id: 'req-e2e-procurement',
              bundle_id: 'bid_decision_kr',
              title: '입찰 의사결정 문서',
              docs: [{ doc_type: 'go_no_go_memo', markdown: '# 결정 요약' }],
            }),
          });
          if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
          return project.project_id;
        }""",
        {"name": name},
    )


def _create_tenant_member_auth(page, *, tenant_id: str, username: str) -> dict[str, str]:
    return page.evaluate(
        """async ({ tenantId, username }) => {
          const token = localStorage.getItem('dd_access_token');
          const headers = {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          };
          const tenantResponse = await fetch('/admin/tenants', {
            method: 'POST',
            headers,
            body: JSON.stringify({ tenant_id: tenantId, display_name: `E2E ${tenantId}` }),
          });
          if (!tenantResponse.ok) throw new Error(`tenant create failed: ${tenantResponse.status}`);

          const inviteResponse = await fetch('/admin/invite', {
            method: 'POST',
            headers,
            body: JSON.stringify({
              tenant_id: tenantId,
              email: `${username}@test.local`,
              role: 'member',
              send_email: false,
            }),
          });
          if (!inviteResponse.ok) throw new Error(`invite create failed: ${inviteResponse.status}`);
          const invite = await inviteResponse.json();

          const acceptResponse = await fetch(`/invite/${invite.invite_id}/accept`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              username,
              display_name: 'Tenant E2E Member',
              password: 'MemberPass1!',
            }),
          });
          if (!acceptResponse.ok) throw new Error(`invite accept failed: ${acceptResponse.status}`);
          return acceptResponse.json();
        }""",
        {"tenantId": tenant_id, "username": username},
    )


# ── 기본 페이지 ──────────────────────────────────────────────────────────────

def test_page_loads(page):
    """Page title must contain 'DecisionDoc' and #bundle-grid must be visible."""
    page.wait_for_selector("#bundle-grid", timeout=5000)
    assert "DecisionDoc" in page.title()


def test_tenant_context_follows_authenticated_user_and_rejects_denied_switches(page):
    suffix = uuid.uuid4().hex[:10]
    tenant_id = f"e2e-tenant-{suffix}"
    invited_username = f"tenant_member_{suffix}"
    auth = _create_tenant_member_auth(
        page,
        tenant_id=tenant_id,
        username=invited_username,
    )

    base_url = page.url.split("?", 1)[0]
    page.goto(f"{base_url}?ops=1")
    page.wait_for_selector(
        f'#tenant-select option[value="{tenant_id}"]',
        state="attached",
        timeout=10000,
    )
    page.locator("#tenant-select").select_option(tenant_id)
    _wait_until_text_contains(
        page,
        "#notification-container",
        "이 계정으로는 선택한 테넌트에 접근할 수 없습니다.",
        timeout_ms=10000,
    )
    assert page.locator("#tenant-select").input_value() == "system"
    assert page.evaluate("_currentTenantId") == "system"
    assert page.evaluate("localStorage.getItem('dd_tenant_id')") == "system"

    assert page.evaluate(
        """() => {
          _documentOpsReviewDrafts.set(documentOpsReviewDraftKey('same-tenant-review'), {
            notes: 'logout 전에 작성한 검토 메모',
            scoreText: '0.8',
          });
          logout();
          return _documentOpsReviewDrafts.size === 0;
        }"""
    )

    page.evaluate(
        """({ accessToken, refreshToken }) => {
          localStorage.setItem('dd_tenant_id', 'system');
          localStorage.setItem('dd_access_token', accessToken);
          localStorage.setItem('dd_refresh_token', refreshToken);
        }""",
        {"accessToken": auth["access_token"], "refreshToken": auth["refresh_token"]},
    )
    page.goto(base_url)
    page.wait_for_selector("body.auth-ready", timeout=10000)

    assert page.evaluate("_currentTenantId") == tenant_id
    assert page.evaluate("localStorage.getItem('dd_tenant_id')") == tenant_id
    assert page.evaluate("getAuthHeaders()['X-Tenant-ID']") == tenant_id
    assert page.evaluate(
        """async () => {
          const response = await fetch('/api/agent/document-ops/trajectories/stats', {
            headers: getAuthHeaders(),
          });
          return response.status;
        }"""
    ) == 200


def test_tenant_context_storage_failure_preserves_current_evidence(page):
    operation_id = "agent-run:11111111-2222-4333-8444-555555555555"

    result = page.evaluate(
        """async ({ operationId }) => {
          const previousTenantId = _currentTenantId;
          const nextTenantId = 'tenant-storage-write-failure';
          const storagePrototype = Object.getPrototypeOf(localStorage);
          const originalSetItem = storagePrototype.setItem;
          const originalFetch = window.fetch;
          originalSetItem.call(localStorage, 'dd_tenant_id', previousTenantId);

          const pendingRecovery = {
            tenantId: previousTenantId,
            operationId,
            payload: { title: '현재 tenant에서 작성 중인 요청' },
          };
          const recoveryPromise = Promise.resolve(null);
          _documentOpsReviewDrafts.clear();
          _documentOpsReviewDrafts.set('storage-failure-draft', {
            notes: '저장 실패 뒤에도 보존할 검토 메모',
            scoreText: '0.8',
          });
          rememberDocumentOpsPendingRunMarker(previousTenantId, operationId);
          _documentOpsPendingRunRecovery = pendingRecovery;
          _documentOpsRunRecoveryPromise = recoveryPromise;

          storagePrototype.setItem = function(key, value) {
            if (this === localStorage && key === 'dd_tenant_id') {
              throw new Error('tenant storage unavailable');
            }
            return originalSetItem.call(this, key, value);
          };
          window.fetch = async input => {
            if (String(input) === '/bundles') return { ok: true, status: 200 };
            return originalFetch(input);
          };

          try {
            const encodedClaims = btoa(JSON.stringify({ tenant_id: nextTenantId }));
            const syncResult = syncTenantContextFromAccessToken(`e30.${encodedClaims}.signature`);
            const syncCurrentTenantId = _currentTenantId;
            const syncStoredTenantId = localStorage.getItem('dd_tenant_id');

            _currentTenantId = previousTenantId;
            const switchResult = await changeTenantContext(nextTenantId);
            return {
              previousTenantId,
              syncResult,
              syncCurrentTenantId,
              syncStoredTenantId,
              switchResult,
              switchCurrentTenantId: _currentTenantId,
              switchStoredTenantId: localStorage.getItem('dd_tenant_id'),
              draftPreserved: _documentOpsReviewDrafts.has('storage-failure-draft'),
              markerAfterSwitch: readDocumentOpsPendingRunMarker(previousTenantId),
              pendingRecoveryPreserved: _documentOpsPendingRunRecovery === pendingRecovery,
              recoveryPromisePreserved: _documentOpsRunRecoveryPromise === recoveryPromise,
            };
          } finally {
            storagePrototype.setItem = originalSetItem;
            window.fetch = originalFetch;
            _documentOpsReviewDrafts.clear();
            clearDocumentOpsPendingRunMarker('', previousTenantId);
            _documentOpsPendingRunRecovery = null;
            _documentOpsRunRecoveryPromise = null;
            _currentTenantId = previousTenantId;
            originalSetItem.call(localStorage, 'dd_tenant_id', previousTenantId);
          }
        }""",
        {"operationId": operation_id},
    )

    previous_tenant_id = result["previousTenantId"]
    assert result == {
        "previousTenantId": previous_tenant_id,
        "syncResult": False,
        "syncCurrentTenantId": previous_tenant_id,
        "syncStoredTenantId": previous_tenant_id,
        "switchResult": False,
        "switchCurrentTenantId": previous_tenant_id,
        "switchStoredTenantId": previous_tenant_id,
        "draftPreserved": True,
        "markerAfterSwitch": {
            "schema_version": "document_ops_agent_pending_run_marker_v1",
            "tenant_id": previous_tenant_id,
            "operation_id": operation_id,
        },
        "pendingRecoveryPreserved": True,
        "recoveryPromisePreserved": True,
    }


def test_auth_refresh_tenant_commit_failure_restores_previous_session(page):
    operation_id = "agent-run:22222222-3333-4444-8555-666666666666"

    result = page.evaluate(
        """async ({ operationId }) => {
          const previousTenantId = _currentTenantId;
          const nextTenantId = 'tenant-refresh-write-failure';
          const previousAccessToken = 'previous-access-token';
          const previousRefreshToken = 'previous-refresh-token';
          const previousUser = { sub: 'previous-user', tenant_id: previousTenantId };
          const storagePrototype = Object.getPrototypeOf(localStorage);
          const originalSetItem = storagePrototype.setItem;
          const originalFetch = window.fetch;
          originalSetItem.call(localStorage, 'dd_tenant_id', previousTenantId);
          originalSetItem.call(localStorage, 'dd_access_token', previousAccessToken);
          originalSetItem.call(localStorage, 'dd_refresh_token', previousRefreshToken);

          const pendingRecovery = {
            tenantId: previousTenantId,
            operationId,
            payload: { title: 'refresh 실패 뒤에도 보존할 요청' },
          };
          const recoveryPromise = Promise.resolve(null);
          _currentUser = previousUser;
          _documentOpsReviewDrafts.clear();
          _documentOpsReviewDrafts.set('refresh-storage-failure-draft', {
            notes: 'refresh 실패 뒤에도 보존할 검토 메모',
            scoreText: '0.9',
          });
          rememberDocumentOpsPendingRunMarker(previousTenantId, operationId);
          _documentOpsPendingRunRecovery = pendingRecovery;
          _documentOpsRunRecoveryPromise = recoveryPromise;

          const encodedClaims = btoa(JSON.stringify({
            sub: 'next-user',
            tenant_id: nextTenantId,
          }));
          const nextAccessToken = `e30.${encodedClaims}.signature`;
          storagePrototype.setItem = function(key, value) {
            if (this === localStorage && key === 'dd_tenant_id') {
              throw new Error('tenant storage unavailable');
            }
            return originalSetItem.call(this, key, value);
          };
          window.fetch = async input => {
            if (String(input) === '/auth/refresh') {
              return {
                ok: true,
                json: async () => ({ access_token: nextAccessToken }),
              };
            }
            return originalFetch(input);
          };

          try {
            const refreshResult = await refreshAccessToken();
            return {
              previousTenantId,
              refreshResult,
              currentTenantId: _currentTenantId,
              storedTenantId: localStorage.getItem('dd_tenant_id'),
              storedAccessToken: localStorage.getItem('dd_access_token'),
              storedRefreshToken: localStorage.getItem('dd_refresh_token'),
              previousUserPreserved: _currentUser === previousUser,
              draftPreserved: _documentOpsReviewDrafts.has('refresh-storage-failure-draft'),
              markerPreserved: readDocumentOpsPendingRunMarker(previousTenantId),
              pendingRecoveryPreserved: _documentOpsPendingRunRecovery === pendingRecovery,
              recoveryPromisePreserved: _documentOpsRunRecoveryPromise === recoveryPromise,
            };
          } finally {
            storagePrototype.setItem = originalSetItem;
            window.fetch = originalFetch;
            _documentOpsReviewDrafts.clear();
            clearDocumentOpsPendingRunMarker('', previousTenantId);
            _documentOpsPendingRunRecovery = null;
            _documentOpsRunRecoveryPromise = null;
            _currentUser = null;
            _currentTenantId = previousTenantId;
            originalSetItem.call(localStorage, 'dd_tenant_id', previousTenantId);
            localStorage.removeItem('dd_access_token');
            localStorage.removeItem('dd_refresh_token');
          }
        }""",
        {"operationId": operation_id},
    )

    previous_tenant_id = result["previousTenantId"]
    assert result == {
        "previousTenantId": previous_tenant_id,
        "refreshResult": "storage_failed",
        "currentTenantId": previous_tenant_id,
        "storedTenantId": previous_tenant_id,
        "storedAccessToken": "previous-access-token",
        "storedRefreshToken": "previous-refresh-token",
        "previousUserPreserved": True,
        "draftPreserved": True,
        "markerPreserved": {
            "schema_version": "document_ops_agent_pending_run_marker_v1",
            "tenant_id": previous_tenant_id,
            "operation_id": operation_id,
        },
        "pendingRecoveryPreserved": True,
        "recoveryPromisePreserved": True,
    }


def test_auth_recovery_storage_failure_preserves_session_evidence(page):
    operation_id = "agent-run:33333333-4444-4555-8666-777777777777"

    result = page.evaluate(
        """async ({ operationId }) => {
          const previousTenantId = _currentTenantId;
          const nextTenantId = 'tenant-recovery-write-failure';
          const previousAccessToken = 'previous-recovery-access-token';
          const previousRefreshToken = 'previous-recovery-refresh-token';
          const previousUser = { sub: 'previous-recovery-user', tenant_id: previousTenantId };
          const storagePrototype = Object.getPrototypeOf(localStorage);
          const originalSetItem = storagePrototype.setItem;
          const originalFetch = window.fetch;
          originalSetItem.call(localStorage, 'dd_tenant_id', previousTenantId);
          originalSetItem.call(localStorage, 'dd_access_token', previousAccessToken);
          originalSetItem.call(localStorage, 'dd_refresh_token', previousRefreshToken);

          const pendingRecovery = {
            tenantId: previousTenantId,
            operationId,
            payload: { title: '상위 recovery 실패 뒤에도 보존할 요청' },
          };
          const recoveryPromise = Promise.resolve(null);
          _currentUser = previousUser;
          _documentOpsReviewDrafts.clear();
          _documentOpsReviewDrafts.set('recovery-storage-failure-draft', {
            notes: '상위 recovery 실패 뒤에도 보존할 검토 메모',
            scoreText: '0.91',
          });
          rememberDocumentOpsPendingRunMarker(previousTenantId, operationId);
          _documentOpsPendingRunRecovery = pendingRecovery;
          _documentOpsRunRecoveryPromise = recoveryPromise;

          const encodedClaims = btoa(JSON.stringify({
            sub: 'next-recovery-user',
            tenant_id: nextTenantId,
          }));
          const nextAccessToken = `e30.${encodedClaims}.signature`;
          storagePrototype.setItem = function(key, value) {
            if (this === localStorage && key === 'dd_tenant_id') {
              throw new Error('tenant storage unavailable');
            }
            return originalSetItem.call(this, key, value);
          };

          let refreshRequests = 0;
          window.fetch = async input => {
            if (String(input) === '/auth/refresh') {
              refreshRequests += 1;
              return {
                ok: true,
                json: async () => ({ access_token: nextAccessToken }),
              };
            }
            return originalFetch(input);
          };

          let fetchAttempts = 0;
          const fetcher = async () => {
            fetchAttempts += 1;
            return {
              ok: false,
              status: 401,
              json: async () => ({ code: 'UNAUTHORIZED' }),
            };
          };

          try {
            let errorCode = '';
            try {
              await _fetchJsonWithProviderRetry(fetcher);
            } catch (error) {
              errorCode = error.code || '';
            }
            return {
              previousTenantId,
              errorCode,
              fetchAttempts,
              refreshRequests,
              currentTenantId: _currentTenantId,
              storedTenantId: localStorage.getItem('dd_tenant_id'),
              storedAccessToken: localStorage.getItem('dd_access_token'),
              storedRefreshToken: localStorage.getItem('dd_refresh_token'),
              previousUserPreserved: _currentUser === previousUser,
              draftPreserved: _documentOpsReviewDrafts.has('recovery-storage-failure-draft'),
              markerPreserved: readDocumentOpsPendingRunMarker(previousTenantId),
              pendingRecoveryPreserved: _documentOpsPendingRunRecovery === pendingRecovery,
              recoveryPromisePreserved: _documentOpsRunRecoveryPromise === recoveryPromise,
            };
          } finally {
            storagePrototype.setItem = originalSetItem;
            window.fetch = originalFetch;
            _documentOpsReviewDrafts.clear();
            clearDocumentOpsPendingRunMarker('', previousTenantId);
            _documentOpsPendingRunRecovery = null;
            _documentOpsRunRecoveryPromise = null;
            _currentUser = null;
            _currentTenantId = previousTenantId;
            originalSetItem.call(localStorage, 'dd_tenant_id', previousTenantId);
            localStorage.removeItem('dd_access_token');
            localStorage.removeItem('dd_refresh_token');
          }
        }""",
        {"operationId": operation_id},
    )

    previous_tenant_id = result["previousTenantId"]
    assert result == {
        "previousTenantId": previous_tenant_id,
        "errorCode": "AUTH_SESSION_STORAGE_FAILED",
        "fetchAttempts": 1,
        "refreshRequests": 1,
        "currentTenantId": previous_tenant_id,
        "storedTenantId": previous_tenant_id,
        "storedAccessToken": "previous-recovery-access-token",
        "storedRefreshToken": "previous-recovery-refresh-token",
        "previousUserPreserved": True,
        "draftPreserved": True,
        "markerPreserved": {
            "schema_version": "document_ops_agent_pending_run_marker_v1",
            "tenant_id": previous_tenant_id,
            "operation_id": operation_id,
        },
        "pendingRecoveryPreserved": True,
        "recoveryPromisePreserved": True,
    }


def test_auth_recovery_retries_refreshed_session_and_clears_invalid_session(page):
    operation_id = "agent-run:44444444-5555-4666-8777-888888888888"

    result = page.evaluate(
        """async ({ operationId }) => {
          const tenantId = _currentTenantId;
          const originalFetch = window.fetch;
          const encodedClaims = btoa(JSON.stringify({
            sub: 'refreshed-user',
            tenant_id: tenantId,
          }));
          const nextAccessToken = `e30.${encodedClaims}.signature`;
          localStorage.setItem('dd_refresh_token', 'valid-refresh-token');

          let refreshRequests = 0;
          window.fetch = async input => {
            if (String(input) === '/auth/refresh') {
              refreshRequests += 1;
              return {
                ok: true,
                status: 200,
                json: async () => ({ access_token: nextAccessToken }),
              };
            }
            return originalFetch(input);
          };

          let successfulFetchAttempts = 0;
          const recoveredPayload = await _fetchJsonWithProviderRetry(async () => {
            successfulFetchAttempts += 1;
            if (successfulFetchAttempts === 1) {
              return {
                ok: false,
                status: 401,
                json: async () => ({ code: 'UNAUTHORIZED' }),
              };
            }
            return {
              ok: true,
              status: 200,
              json: async () => ({ recovered: true }),
            };
          });
          const accessTokenUpdated = localStorage.getItem('dd_access_token') === nextAccessToken;
          const currentUserUpdated = _currentUser?.sub === 'refreshed-user';

          _documentOpsReviewDrafts.set('invalid-refresh-draft', {
            notes: '유효하지 않은 세션과 함께 정리할 메모',
            scoreText: '0.2',
          });
          rememberDocumentOpsPendingRunMarker(tenantId, operationId);
          _documentOpsPendingRunRecovery = { tenantId, operationId };
          _documentOpsRunRecoveryPromise = Promise.resolve(null);
          localStorage.setItem('dd_refresh_token', 'invalid-refresh-token');
          window.fetch = async input => {
            if (String(input) === '/auth/refresh') {
              refreshRequests += 1;
              return { ok: false, status: 401 };
            }
            return originalFetch(input);
          };

          let invalidErrorCode = '';
          try {
            await _fetchJsonWithProviderRetry(async () => ({
              ok: false,
              status: 401,
              json: async () => ({ code: 'UNAUTHORIZED' }),
            }));
          } catch (error) {
            invalidErrorCode = error.code || '';
          }

          const observed = {
            recoveredPayload,
            successfulFetchAttempts,
            refreshRequests,
            accessTokenUpdated,
            currentUserUpdated,
            invalidErrorCode,
            storedAccessToken: localStorage.getItem('dd_access_token'),
            storedRefreshToken: localStorage.getItem('dd_refresh_token'),
            currentUser: _currentUser,
            draftPreserved: _documentOpsReviewDrafts.has('invalid-refresh-draft'),
            markerPreserved: readDocumentOpsPendingRunMarker(tenantId),
            pendingRecovery: _documentOpsPendingRunRecovery,
            recoveryPromise: _documentOpsRunRecoveryPromise,
          };

          window.fetch = originalFetch;
          _documentOpsReviewDrafts.clear();
          clearDocumentOpsPendingRunMarker('', tenantId);
          _documentOpsPendingRunRecovery = null;
          _documentOpsRunRecoveryPromise = null;
          _currentUser = null;
          _currentTenantId = tenantId;
          localStorage.setItem('dd_tenant_id', tenantId);
          localStorage.removeItem('dd_access_token');
          localStorage.removeItem('dd_refresh_token');
          return observed;
        }""",
        {"operationId": operation_id},
    )

    assert result == {
        "recoveredPayload": {"recovered": True},
        "successfulFetchAttempts": 2,
        "refreshRequests": 2,
        "accessTokenUpdated": True,
        "currentUserUpdated": True,
        "invalidErrorCode": "UNAUTHORIZED",
        "storedAccessToken": None,
        "storedRefreshToken": None,
        "currentUser": None,
        "draftPreserved": False,
        "markerPreserved": None,
        "pendingRecovery": None,
        "recoveryPromise": None,
    }


def test_generate_landing_shows_ai_rank_roster(page):
    page.wait_for_selector("#ai-rank-roster", timeout=5000)
    assert page.locator("#ai-rank-roster").is_visible()
    assert page.locator("#ai-rank-roster .ai-rank-card").count() == 3
    assert page.locator("#ai-rank-roster .ai-rank-card .ai-rank-title", has_text="최종 승인 AI").count() == 1
    assert page.locator("#ai-rank-roster .ai-rank-card .ai-rank-title", has_text="제안/영업 AI").count() == 1
    assert page.locator("#ai-rank-roster .ai-rank-card .ai-rank-title", has_text="PM AI").count() == 1


def test_ai_rank_roster_bd_action_opens_g2b_search(page):
    page.wait_for_selector("#ai-rank-roster", timeout=5000)
    page.locator('[data-ai-rank="proposal_bd"]').click()
    page.locator("#ai-rank-status-action").click()

    page.wait_for_selector('#category-filter .cat-btn.active[data-cat="gov"]', timeout=5000)
    page.wait_for_selector("#g2b-search-tab", state="visible", timeout=5000)
    assert page.locator("#g2b-content").is_visible()
    assert page.locator("#g2b-search-input").evaluate("el => document.activeElement === el")
    assert page.input_value("#f-audience") == "mixed"


def test_ai_rank_roster_pm_action_focuses_project_context(page):
    page.wait_for_selector("#ai-rank-roster", timeout=5000)
    page.locator('[data-ai-rank="delivery_pm"]').click()
    page.locator("#ai-rank-status-action").click()

    page.wait_for_selector('#category-filter .cat-btn.active[data-cat="gov"]', timeout=5000)
    assert page.input_value("#f-audience") == "technical"
    assert page.locator('#tone-chips .chip.active').get_attribute("data-tone") == "detailed"
    assert page.locator("#project-select").evaluate("el => document.activeElement === el")


def test_login_screen_bootstrap_has_no_sso_reference_error(playwright, live_server):
    console_messages: list[str] = []
    browser = playwright.chromium.launch()
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.on("console", lambda msg: console_messages.append(msg.text))

    pg.goto(live_server["base_url"])
    pg.wait_for_selector("#login-screen", timeout=10000)
    html = pg.content()

    assert pg.evaluate("document.body.classList.contains('auth-pending')")
    assert pg.locator("#login-form").count() == 1
    assert not pg.locator(".hero").is_visible()
    assert not pg.locator("#page-nav").is_visible()
    assert not pg.locator("#main-content").is_visible()
    assert not pg.locator("#mobile-bottom-nav").is_visible()
    assert "cdn.jsdelivr.net" not in html

    pg.get_by_role("link", name="관리자 계정 만들기").click()
    pg.wait_for_selector("#register-form", timeout=5000)
    assert pg.get_by_role("heading", name="관리자 계정 만들기").inner_text() == "관리자 계정 만들기"

    assert not any(
        "addSSOLoginButtons is not defined" in message
        for message in console_messages
    )
    assert not any(
        "Password field is not contained in a form" in message
        for message in console_messages
    )
    assert not any(
        "autocomplete attributes" in message
        for message in console_messages
    )
    assert not any(
        "Password forms should have" in message
        for message in console_messages
    )
    assert not any(
        "[PWA] SW registered" in message
        for message in console_messages
    )
    assert not any(
        "cdn.tailwindcss.com should not be used in production" in message
        for message in console_messages
    )
    assert not any(
        "Executing inline event handler violates" in message
        for message in console_messages
    )

    ctx.close()
    browser.close()


def test_ops_dashboard_post_deploy_panel_renders_with_ops_key(playwright, live_server):
    console_messages: list[str] = []
    browser = playwright.chromium.launch()
    ctx = browser.new_context()
    ctx.add_init_script("localStorage.setItem('onboarding_done', '1');")
    pg = ctx.new_page()
    pg.on("console", lambda msg: console_messages.append(msg.text))

    pg.goto(f"{live_server['base_url']}?ops=1")
    pg.wait_for_selector("#ops-panel", timeout=10000)
    pg.wait_for_selector("#ops-post-deploy-report", timeout=10000)

    assert "Ops Key 또는 admin 로그인 세션이 있어야 배포 리포트를 조회할 수 있습니다." in pg.locator(
        "#ops-post-deploy-report"
    ).inner_text()
    assert "Admin 로그인 후 SSO 설정을 불러올 수 있습니다." in pg.locator(
        "#sso-form-container"
    ).inner_text()
    assert "Admin 로그인 후 요금제 정보를 확인할 수 있습니다." in pg.locator(
        "#billing-panel"
    ).inner_text()
    assert "admin 로그인 없이도 아래 `Ops Key` 입력으로 배포 리포트 조회와 운영 조사 기능을 사용할 수 있습니다." in pg.locator(
        "#login-screen"
    ).inner_text()

    pg.fill("#ops-key-input", live_server["ops_key"])
    pg.evaluate(
        """async () => {
          localStorage.setItem('dd_ops_key', document.querySelector('#ops-key-input')?.value || '');
          await window.loadOpsPostDeployReports();
        }"""
    )

    pg.wait_for_function(
        "() => document.querySelector('#ops-post-deploy-report')?.innerText.includes('Latest report')"
    )
    panel_text = pg.locator("#ops-post-deploy-report").inner_text()
    assert "post-deploy-20260414T041000Z.json" in panel_text
    assert "post-deploy-20260414T031000Z.json" in panel_text
    assert "health" in panel_text
    assert "smoke" in panel_text
    assert "Smoke checks" in panel_text
    assert "Report Workflow smoke" in panel_text
    assert "2 checks" in panel_text
    assert "3 checks" in panel_text
    assert "0 checks" in panel_text
    assert "POST /generate/with-attachments (auth) -> 200 files=1 docs=4" in panel_text
    assert "PASS GET /export/snapshot -> 200 export_version=decisiondoc_report_workflow_snapshot.v1" in panel_text
    assert "legacy report라 저장된 smoke summary가 없습니다." in panel_text
    assert "legacy report라 저장된 Report Workflow smoke summary가 없습니다." in panel_text
    assert "https://admin.decisiondoc.kr" in panel_text
    assert "JSON 보기" in panel_text
    assert "JSON 다운로드" in panel_text
    assert pg.locator("#ops-post-deploy-failures-only").count() == 1
    assert pg.locator("#ops-post-deploy-search").count() == 1

    pg.fill("#ops-post-deploy-search", "031000")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          const detail = document.querySelector('#ops-post-deploy-detail');
          const buttons = document.querySelectorAll('[data-report-detail-btn]');
          return report?.innerText.includes('1 / 2건')
            && buttons.length === 1
            && detail?.innerText.includes('post-deploy-20260414T031000Z.json');
        }"""
    )
    assert pg.locator('[data-report-detail-btn="post-deploy-20260414T031000Z.json"]').count() == 1

    pg.fill("#ops-post-deploy-search", "snapshot")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          const detail = document.querySelector('#ops-post-deploy-detail');
          const buttons = document.querySelectorAll('[data-report-detail-btn]');
          return report?.innerText.includes('1 / 2건')
            && buttons.length === 1
            && detail?.innerText.includes('post-deploy-20260414T041000Z.json')
            && report?.innerText.includes('Report Workflow smoke');
        }"""
    )

    pg.fill("#ops-post-deploy-search", "031000")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          const detail = document.querySelector('#ops-post-deploy-detail');
          const buttons = document.querySelectorAll('[data-report-detail-btn]');
          return report?.innerText.includes('1 / 2건')
            && buttons.length === 1
            && detail?.innerText.includes('post-deploy-20260414T031000Z.json');
        }"""
    )
    assert pg.locator("#ops-post-deploy-run-btn").count() == 1
    assert pg.locator("#ops-post-deploy-run-skip-smoke").count() == 1
    assert pg.locator("#ops-post-deploy-compare-left").count() == 1
    assert pg.locator("#ops-post-deploy-compare-right").count() == 1

    pg.select_option("#ops-post-deploy-compare-left", "post-deploy-20260414T041000Z.json")
    pg.select_option("#ops-post-deploy-compare-right", "post-deploy-20260414T031000Z.json")
    pg.click("#ops-post-deploy-compare-run-btn")
    pg.wait_for_function(
        """() => {
          const compare = document.querySelector('#ops-post-deploy-compare-result');
          return compare?.innerText.includes('체크 차이') && compare?.innerText.includes('smoke');
        }"""
    )
    compare_text = pg.locator("#ops-post-deploy-compare-result").inner_text()
    assert "exit 17" in compare_text
    assert "Smoke checks 차이" in compare_text
    assert "Report Workflow smoke 차이" in compare_text
    assert "Smoke checks" in compare_text
    assert "Report Workflow smoke" in compare_text
    assert "2 checks" in compare_text
    assert "3 checks" in compare_text
    assert "0 checks" in compare_text
    assert "legacy report라 저장된 smoke summary가 없습니다." in compare_text
    assert "legacy report라 저장된 Report Workflow smoke summary가 없습니다." in compare_text

    pg.click("#ops-post-deploy-clear-filters-btn")
    pg.wait_for_function(
        "() => document.querySelectorAll('[data-report-detail-btn]').length === 2"
    )

    pg.check("#ops-post-deploy-failures-only")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          const detail = document.querySelector('#ops-post-deploy-detail');
          const buttons = document.querySelectorAll('[data-report-detail-btn]');
          return report?.innerText.includes('1 / 2건')
            && report?.innerText.includes('필터 적용됨')
            && buttons.length === 1
            && detail?.innerText.includes('post-deploy-20260414T031000Z.json');
        }"""
    )
    assert "docker compose ps failed with exit code 17" in pg.locator(
        "#ops-post-deploy-report"
    ).inner_text()

    pg.click("#ops-post-deploy-clear-filters-btn")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          return document.querySelectorAll('[data-report-detail-btn]').length === 2
            && !report?.innerText.includes('필터 적용됨');
        }"""
    )

    pg.get_by_role("button", name="JSON 보기").click()
    pg.wait_for_selector("#ops-post-deploy-raw pre", timeout=5000)
    raw_json = pg.locator("#ops-post-deploy-raw").inner_text()
    assert '"latest_report": "post-deploy-20260414T041000Z.json"' in raw_json
    assert '"status": "passed"' in raw_json
    assert '"name": "health"' in raw_json
    assert '"report_workflow_smoke_results_available": true' in raw_json

    pg.get_by_role("button", name="JSON 숨기기").click()
    assert not pg.locator("#ops-post-deploy-raw").is_visible()

    detail_text = pg.locator("#ops-post-deploy-detail").inner_text()
    assert "선택한 리포트" in detail_text
    assert "post-deploy-20260414T041000Z.json" in detail_text
    assert "smoke 포함" in detail_text
    assert "Smoke checks" in detail_text
    assert "Report Workflow smoke" in detail_text
    assert "2 checks" in detail_text
    assert "3 checks" in detail_text
    assert "POST /generate/with-attachments (auth) -> 200 files=1 docs=4" in detail_text
    assert "PASS GET /export/snapshot -> 200 export_version=decisiondoc_report_workflow_snapshot.v1" in detail_text

    pg.locator('[data-report-detail-btn="post-deploy-20260414T031000Z.json"]').click()
    pg.wait_for_function(
        "() => document.querySelector('#ops-post-deploy-detail')?.innerText.includes('post-deploy-20260414T031000Z.json')"
    )
    selected_detail = pg.locator("#ops-post-deploy-detail").inner_text()
    assert "post-deploy-20260414T031000Z.json" in selected_detail
    assert "docker compose ps failed with exit code 17" in selected_detail
    assert "실패" in selected_detail
    assert "exit 17" in selected_detail
    assert "Smoke checks" in selected_detail
    assert "Report Workflow smoke" in selected_detail
    assert "0 checks" in selected_detail
    assert "legacy report라 저장된 smoke summary가 없습니다." in selected_detail
    assert "legacy report라 저장된 Report Workflow smoke summary가 없습니다." in selected_detail
    assert not console_messages

    ctx.close()
    browser.close()


def test_bundle_selection_enables_generate_button(page):
    """Clicking a bundle card must enable the generate button."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    assert page.locator("#generate-btn").is_disabled()
    page.locator(".bundle-card").first.click()
    assert not page.locator("#generate-btn").is_disabled()


def test_document_ops_agent_run_keeps_the_latest_result_and_observes_stale_completion(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingRuns = [];
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          const agentResult = (suffix, taskType) => ({
            skill_name: `skill-${suffix}`,
            task_type: taskType,
            provider_name: 'mock',
            plan: [`plan-${suffix}`],
            draft: `draft-${suffix}`,
            qa: {
              hard_gate_pass: true,
              scores: { completeness: 1 },
              gate_issues: [],
            },
            evidence_status: {
              confirmed: [`confirmed-${suffix}`],
              assumptions: [],
              gaps: [],
              source_references: [],
            },
            quality_warnings: [],
            trajectory_id: `trajectory-${suffix}`,
            trajectory_saved: true,
          });
          const setRunInput = (title, taskType) => {
            document.querySelector('#docops-title').value = title;
            document.querySelector('#docops-task-type').value = taskType;
          };
          try {
            window.fetch = (input, options) => {
              const url = String(input || '');
              if (url === '/api/agent/document-ops/run') {
                return new Promise(resolve => pendingRuns.push(resolve));
              }
              if (url.startsWith('/api/agent/document-ops/run-operations/')) {
                const operationId = decodeURIComponent(url.split('/').pop());
                return Promise.resolve(response({
                  schema_version: 'document_ops_agent_operation_status_v1',
                  operation_id: operationId,
                  status: 'failed',
                  started_at: '2026-07-21T00:00:00+00:00',
                  completed_at: '2026-07-21T00:00:01+00:00',
                  replay_available: false,
                  next_action: 'inspect_evidence_before_new_operation',
                  read_only: true,
                  provider_call_authorized: false,
                  result_included: false,
                }));
              }
              if (url === '/api/agent/document-ops/trajectories/stats') {
                return Promise.resolve(response({
                  total_records: 2,
                  accepted_records: 0,
                  pending_records: 2,
                  export_count: 0,
                }));
              }
              if (url.startsWith('/api/agent/document-ops/trajectories?')) {
                return Promise.resolve(response({
                  trajectories: [],
                  total: 0,
                  offset: 0,
                  returned: 0,
                  has_more: false,
                  order: 'newest',
                }));
              }
              return nativeFetch(input, options);
            };

            setRunInput('older run', 'decision_brief');
            const olderSuccess = runDocumentOpsAgent();
            setRunInput('newer run', 'evidence_gap_review');
            const newerSuccess = runDocumentOpsAgent();
            while (pendingRuns.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingRuns[1](response(agentResult('new', 'evidence_gap_review')));
            await newerSuccess;
            const currentText = document.querySelector('#document-ops-result').textContent;

            const taskFilter = document.querySelector('#docops-trajectory-task-filter');
            taskFilter.value = 'decision_brief';
            pendingRuns[0](response(agentResult('old', 'decision_brief')));
            await olderSuccess;
            const afterOlderSuccess = document.querySelector('#document-ops-result').textContent;
            const filterAfterOlderSuccess = taskFilter.value;
            const notificationAfterOlderSuccess = document.querySelector(
              '#notification-container',
            ).textContent;

            setRunInput('older failing run', 'develop_quality_improvement');
            const olderFailure = runDocumentOpsAgent();
            setRunInput('newest run', 'policy_planning_brief');
            const newestSuccess = runDocumentOpsAgent();
            while (pendingRuns.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingRuns[3](response(agentResult('newest', 'policy_planning_brief')));
            await newestSuccess;
            pendingRuns[2](response({ detail: 'stale agent failure' }, 503));
            await olderFailure;
            const finalText = document.querySelector('#document-ops-result').textContent;
            const finalNotifications = document.querySelector(
              '#notification-container',
            ).textContent;

            return {
              currentText,
              afterOlderSuccess,
              filterAfterOlderSuccess,
              notificationAfterOlderSuccess,
              finalText,
              finalNotifications,
            };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "draft-new" in result["currentText"]
    assert "draft-old" not in result["currentText"]
    assert "draft-new" in result["afterOlderSuccess"]
    assert "draft-old" not in result["afterOlderSuccess"]
    assert result["filterAfterOlderSuccess"] == "decision_brief"
    assert "이전 DocumentOps 실행의 trajectory 저장을 완료했습니다." in result["notificationAfterOlderSuccess"]
    assert "draft-newest" in result["finalText"]
    assert "Agent 실행 실패" not in result["finalText"]
    assert "stale agent failure" not in result["finalText"]
    assert "이전 DocumentOps 실행이 실패했습니다." in result["finalNotifications"]


def test_document_ops_agent_button_sends_one_retry_identity_for_captured_run(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingRuns = [];
          const requestBodies = [];
          const response = body => new Response(
            JSON.stringify(body),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
          const agentResult = {
            skill_name: 'decision-brief',
            task_type: 'decision_brief',
            provider_name: 'mock',
            plan: ['plan'],
            draft: 'captured agent result',
            qa: { hard_gate_pass: true, scores: {}, gate_issues: [] },
            evidence_status: {
              confirmed: [], assumptions: [], gaps: [], source_references: [],
            },
            quality_warnings: [],
            trajectory_id: 'trajectory-operation',
            trajectory_saved: true,
          };
          try {
            window.fetch = (input, options = {}) => {
              const url = String(input || '');
              const method = String(options?.method || 'GET').toUpperCase();
              if (url === '/api/agent/document-ops/run' && method === 'POST') {
                requestBodies.push(JSON.parse(String(options?.body || '{}')));
                return new Promise(resolve => pendingRuns.push(resolve));
              }
              if (url === '/api/agent/document-ops/trajectories/stats') {
                return Promise.resolve(response({
                  total_records: 1,
                  accepted_records: 0,
                  pending_records: 1,
                  export_count: 0,
                }));
              }
              if (url.startsWith('/api/agent/document-ops/trajectories?')) {
                return Promise.resolve(response({
                  trajectories: [], total: 0, offset: 0, returned: 0,
                  has_more: false, order: 'newest',
                }));
              }
              return nativeFetch(input, options);
            };

            document.querySelector('#docops-title').value = 'Captured retry identity';
            document.querySelector('#docops-capture-trajectory').checked = true;
            const button = document.querySelector('[data-docops-action="run-agent"]');
            button.click();
            button.click();
            await new Promise(resolve => setTimeout(resolve, 25));
            const capturedCount = pendingRuns.length;
            const disabledDuring = button.disabled;
            pendingRuns.shift()(response(agentResult));
            while (button.disabled) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            document.querySelector('#docops-capture-trajectory').checked = false;
            button.click();
            await new Promise(resolve => setTimeout(resolve, 25));
            pendingRuns.shift()(response({
              ...agentResult,
              trajectory_id: '',
              trajectory_saved: false,
            }));
            while (button.disabled) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            return {
              capturedCount,
              operationId: requestBodies[0]?.operation_id || '',
              uncapturedHasOperationId: Object.hasOwn(requestBodies[1] || {}, 'operation_id'),
              disabledDuring,
              disabledAfter: button.disabled,
            };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert result["capturedCount"] == 1
    assert result["operationId"].startswith("agent-run:")
    assert len(result["operationId"].split(":", 1)[1]) == 36
    assert result["uncapturedHasOperationId"] is False
    assert result["disabledDuring"] is True
    assert result["disabledAfter"] is False


def test_document_ops_agent_recovers_a_lost_success_with_the_same_operation_identity(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const previousTenant = _currentTenantId;
          const originalTenant = 'tenant-recovery-original';
          _currentTenantId = originalTenant;
          const postBodies = [];
          let statusReads = 0;
          let statusTenant = '';
          let replayTenant = '';
          const response = body => new Response(
            JSON.stringify(body),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
          const agentResult = {
            skill_name: 'decision-brief',
            task_type: 'decision_brief',
            provider_name: 'mock',
            plan: ['plan'],
            draft: 'recovered exact replay',
            qa: { hard_gate_pass: true, scores: {}, gate_issues: [] },
            evidence_status: {
              confirmed: [], assumptions: [], gaps: [], source_references: [],
            },
            quality_warnings: [],
            trajectory_id: 'trajectory-recovered',
            trajectory_saved: true,
          };
          try {
            window.fetch = (input, options = {}) => {
              const url = String(input || '');
              const method = String(options?.method || 'GET').toUpperCase();
              if (url === '/api/agent/document-ops/run' && method === 'POST') {
                postBodies.push(JSON.parse(String(options?.body || '{}')));
                if (postBodies.length === 1) {
                  _currentTenantId = 'tenant-switched-during-recovery';
                  return Promise.reject(new TypeError('Failed to fetch'));
                }
                replayTenant = String(options?.headers?.['X-Tenant-ID'] || '');
                _currentTenantId = originalTenant;
                return Promise.resolve(response({
                  ...agentResult,
                  operation_id: postBodies[1].operation_id,
                  operation_replayed: true,
                }));
              }
              if (url.startsWith('/api/agent/document-ops/run-operations/')) {
                statusReads += 1;
                statusTenant = String(options?.headers?.['X-Tenant-ID'] || '');
                return Promise.resolve(response({
                  schema_version: 'document_ops_agent_operation_status_v1',
                  operation_id: postBodies[0].operation_id,
                  status: 'succeeded',
                  started_at: '2026-07-21T00:00:00+00:00',
                  completed_at: '2026-07-21T00:00:01+00:00',
                  replay_available: true,
                  next_action: 'replay_exact_request',
                  read_only: true,
                  provider_call_authorized: false,
                  result_included: false,
                }));
              }
              if (url === '/api/agent/document-ops/trajectories/stats') {
                return Promise.resolve(response({
                  total_records: 1,
                  accepted_records: 0,
                  pending_records: 1,
                  export_count: 0,
                }));
              }
              if (url.startsWith('/api/agent/document-ops/trajectories?')) {
                return Promise.resolve(response({
                  trajectories: [], total: 0, offset: 0, returned: 0,
                  has_more: false, order: 'newest',
                }));
              }
              return nativeFetch(input, options);
            };

            document.querySelector('#docops-title').value = 'Recover lost response';
            document.querySelector('#docops-capture-trajectory').checked = true;
            const button = document.querySelector('[data-docops-action="run-agent"]');
            button.click();
            while (button.disabled) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            return {
              postCount: postBodies.length,
              sameOperationId: postBodies[0].operation_id === postBodies[1].operation_id,
              samePayload: JSON.stringify(postBodies[0]) === JSON.stringify(postBodies[1]),
              statusReads,
              originalTenant,
              statusTenant,
              replayTenant,
              resultText: document.querySelector('#document-ops-result').textContent,
              disabledAfter: button.disabled,
            };
          } finally {
            window.fetch = nativeFetch;
            _currentTenantId = previousTenant;
          }
        }"""
    )

    assert result["postCount"] == 2
    assert result["sameOperationId"] is True
    assert result["samePayload"] is True
    assert result["statusReads"] == 1
    assert result["statusTenant"] == result["originalTenant"]
    assert result["replayTenant"] == result["originalTenant"]
    assert "recovered exact replay" in result["resultText"]
    assert "replay" in result["resultText"]
    assert result["disabledAfter"] is False


def test_document_ops_agent_rechecks_pending_operation_before_exact_replay(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const postBodies = [];
          const statusCacheModes = [];
          let statusReads = 0;
          const response = body => new Response(
            JSON.stringify(body),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
          try {
            window.fetch = (input, options = {}) => {
              const url = String(input || '');
              const method = String(options?.method || 'GET').toUpperCase();
              if (url === '/api/agent/document-ops/run' && method === 'POST') {
                postBodies.push(JSON.parse(String(options?.body || '{}')));
                if (postBodies.length === 1) {
                  return Promise.reject(new TypeError('Failed to fetch'));
                }
                return Promise.resolve(response({
                  skill_name: 'decision-brief',
                  task_type: 'decision_brief',
                  provider_name: 'mock',
                  plan: ['plan'],
                  draft: 'recovered after status recheck',
                  qa: { hard_gate_pass: true, scores: {}, gate_issues: [] },
                  evidence_status: {
                    confirmed: [], assumptions: [], gaps: [], source_references: [],
                  },
                  quality_warnings: [],
                  trajectory_id: 'trajectory-rechecked',
                  trajectory_saved: true,
                  operation_id: postBodies[1].operation_id,
                  operation_replayed: true,
                }));
              }
              if (url.startsWith('/api/agent/document-ops/run-operations/')) {
                statusReads += 1;
                statusCacheModes.push(options?.cache || '');
                const requestedOperationId = postBodies[0].operation_id;
                if (statusReads === 1) {
                  return Promise.resolve(response({
                    schema_version: 'document_ops_agent_operation_status_v1',
                    operation_id: 'agent-run:another-operation',
                    status: 'succeeded',
                    started_at: '2026-07-21T00:00:00+00:00',
                    completed_at: '2026-07-21T00:00:01+00:00',
                    replay_available: true,
                    next_action: 'replay_exact_request',
                    read_only: true,
                    provider_call_authorized: false,
                    result_included: false,
                  }));
                }
                const running = statusReads === 2;
                return Promise.resolve(response({
                  schema_version: 'document_ops_agent_operation_status_v1',
                  operation_id: requestedOperationId,
                  status: running ? 'running' : 'succeeded',
                  started_at: '2026-07-21T00:00:00+00:00',
                  completed_at: running ? null : '2026-07-21T00:00:01+00:00',
                  replay_available: !running,
                  next_action: running ? 'wait_and_recheck' : 'replay_exact_request',
                  read_only: true,
                  provider_call_authorized: false,
                  result_included: false,
                }));
              }
              return nativeFetch(input, options);
            };

            document.querySelector('#docops-title').value = 'Do not retry running operation';
            document.querySelector('#docops-capture-trajectory').checked = true;
            const button = document.querySelector('[data-docops-action="run-agent"]');
            button.click();
            while (button.disabled) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            const firstPostCount = postBodies.length;
            const firstRecoveryVisible = !!document.querySelector('[data-docops-run-recovery]');
            const firstMarker = readDocumentOpsPendingRunMarker();

            button.click();
            while (button.disabled) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            const runningPostCount = postBodies.length;
            const runningText = document.querySelector('#document-ops-result').textContent;
            const recoveryButton = document.querySelector('[data-docops-run-recovery]');
            recoveryButton.click();
            button.click();
            while (document.querySelector('[data-docops-run-recovery]') || button.disabled) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            return {
              postCount: postBodies.length,
              firstPostCount,
              runningPostCount,
              sameOperationId: postBodies[0].operation_id === postBodies[1].operation_id,
              samePayload: JSON.stringify(postBodies[0]) === JSON.stringify(postBodies[1]),
              statusReads,
              statusCacheModes,
              firstRecoveryVisible,
              firstMarker,
              runningText,
              resultText: document.querySelector('#document-ops-result').textContent,
              recoveryVisibleAfterSuccess: !!document.querySelector('[data-docops-run-recovery]'),
              markerAfterSuccess: {
                parsed: readDocumentOpsPendingRunMarker(),
                shared: localStorage.getItem(
                  documentOpsPendingRunMarkerKey(_currentTenantId),
                ),
                tab: sessionStorage.getItem(
                  documentOpsPendingRunMarkerKey(_currentTenantId),
                ),
              },
              disabledAfter: button.disabled,
            };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert result["firstPostCount"] == 1
    assert result["firstRecoveryVisible"] is True
    assert result["firstMarker"] == {
        "schema_version": "document_ops_agent_pending_run_marker_v1",
        "tenant_id": "system",
        "operation_id": result["firstMarker"]["operation_id"],
    }
    assert result["firstMarker"]["operation_id"].startswith("agent-run:")
    assert result["runningPostCount"] == 1
    assert "status=running" in result["runningText"]
    assert "next_action=wait_and_recheck" in result["runningText"]
    assert result["postCount"] == 2
    assert result["sameOperationId"] is True
    assert result["samePayload"] is True
    assert result["statusReads"] == 3
    assert result["statusCacheModes"] == ["no-store", "no-store", "no-store"]
    assert "recovered after status recheck" in result["resultText"]
    assert result["recoveryVisibleAfterSuccess"] is False
    assert result["markerAfterSuccess"] == {"parsed": None, "shared": None, "tab": None}
    assert result["disabledAfter"] is False


def test_document_ops_agent_reload_marker_blocks_new_post_until_explicit_release(page):
    operation_id = "agent-run:11111111-2222-4333-8444-555555555555"
    tenant_id = page.evaluate("() => _currentTenantId")
    marker = {
        "schema_version": "document_ops_agent_pending_run_marker_v1",
        "tenant_id": tenant_id,
        "operation_id": operation_id,
    }
    status_reads: list[str] = []
    post_bodies: list[dict] = []

    def handle_status(route, request):
        status_reads.append(request.url)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "schema_version": "document_ops_agent_operation_status_v1",
                    "operation_id": operation_id,
                    "status": "succeeded",
                    "started_at": "2026-07-21T00:00:00+00:00",
                    "completed_at": "2026-07-21T00:00:01+00:00",
                    "replay_available": True,
                    "next_action": "replay_exact_request",
                    "read_only": True,
                    "provider_call_authorized": False,
                    "result_included": False,
                }
            ),
        )

    def handle_run(route, request):
        post_bodies.append(request.post_data_json or {})
        route.fulfill(status=500, content_type="application/json", body='{"detail":"unexpected"}')

    page.route("**/api/agent/document-ops/run-operations/**", handle_status)
    page.route("**/api/agent/document-ops/run", handle_run)
    page.evaluate(
        "marker => sessionStorage.setItem('dd_document_ops_pending_run_v1', JSON.stringify(marker))",
        marker,
    )

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(".bundle-card", timeout=10000)
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_selector("[data-docops-run-release]", timeout=5000)

    assert len(status_reads) == 1
    assert post_bodies == []
    assert page.evaluate(
        "() => JSON.parse(sessionStorage.getItem('dd_document_ops_pending_run_v1'))"
    ) == marker
    result_text = page.locator("#document-ops-result").inner_text()
    assert operation_id in result_text
    assert "원본 payload는 browser storage에 저장하지 않았습니다" in result_text

    page.evaluate("() => runDocumentOpsAgent()")
    assert len(status_reads) == 2
    assert post_bodies == []

    dialog_messages: list[str] = []

    def accept_release(dialog):
        dialog_messages.append(dialog.message)
        dialog.accept()

    page.once("dialog", accept_release)
    page.locator("[data-docops-run-release]").click()

    assert dialog_messages
    assert "backend 실행을 취소하지 않습니다" in dialog_messages[0]
    assert page.evaluate(
        "() => sessionStorage.getItem('dd_document_ops_pending_run_v1')"
    ) is None
    assert page.evaluate(
        "() => localStorage.getItem('dd_document_ops_pending_run_v1')"
    ) is None
    assert "상태 확인을 종료했습니다" in page.locator("#document-ops-result").inner_text()
    assert post_bodies == []

    invalid_marker_results = page.evaluate(
        """marker => {
          const markerKey = documentOpsPendingRunMarkerKey(marker.tenant_id);
          const invalidMarkers = [
            { ...marker, schema_version: 'wrong-schema' },
            { ...marker, tenant_id: 'wrong-tenant' },
            { ...marker, operation_id: 'agent-run:not-a-browser-uuid' },
            { ...marker, payload: { title: 'must-not-persist' } },
          ];
          return invalidMarkers.map(invalidMarker => {
            sessionStorage.setItem(markerKey, JSON.stringify(invalidMarker));
            const parsed = readDocumentOpsPendingRunMarker();
            return {
              parsed,
              stored: sessionStorage.getItem(markerKey),
            };
          });
        }""",
        marker,
    )
    assert invalid_marker_results == [
        {"parsed": None, "stored": None},
        {"parsed": None, "stored": None},
        {"parsed": None, "stored": None},
        {"parsed": None, "stored": None},
    ]

    tab_fallback_result = page.evaluate(
        """({ tenantId, operationId }) => {
          const storagePrototype = Object.getPrototypeOf(localStorage);
          const originalGetItem = storagePrototype.getItem;
          const originalSetItem = storagePrototype.setItem;
          const originalRemoveItem = storagePrototype.removeItem;
          const isSharedStorage = storage => storage === localStorage;
          storagePrototype.getItem = function(key) {
            if (isSharedStorage(this)) throw new Error('shared storage unavailable');
            return originalGetItem.call(this, key);
          };
          storagePrototype.setItem = function(key, value) {
            if (isSharedStorage(this)) throw new Error('shared storage unavailable');
            return originalSetItem.call(this, key, value);
          };
          storagePrototype.removeItem = function(key) {
            if (isSharedStorage(this)) throw new Error('shared storage unavailable');
            return originalRemoveItem.call(this, key);
          };
          try {
            const markerKey = documentOpsPendingRunMarkerKey(tenantId);
            const remembered = rememberDocumentOpsPendingRunMarker(tenantId, operationId);
            const parsed = readDocumentOpsPendingRunMarker();
            const shared = originalGetItem.call(
              localStorage,
              markerKey,
            );
            const tab = JSON.parse(originalGetItem.call(
              sessionStorage,
              markerKey,
            ));
            const cleared = clearDocumentOpsPendingRunMarker(operationId);
            return {
              remembered,
              parsed,
              shared,
              tab,
              cleared,
              tabAfter: originalGetItem.call(
                sessionStorage,
                markerKey,
              ),
            };
          } finally {
            storagePrototype.getItem = originalGetItem;
            storagePrototype.setItem = originalSetItem;
            storagePrototype.removeItem = originalRemoveItem;
          }
        }""",
        {"tenantId": tenant_id, "operationId": operation_id},
    )
    assert tab_fallback_result == {
        "remembered": True,
        "parsed": marker,
        "shared": None,
        "tab": marker,
        "cleared": True,
        "tabAfter": None,
    }

    unavailable_storage_result = page.evaluate(
        """({ tenantId, operationId }) => {
          const storagePrototype = Object.getPrototypeOf(sessionStorage);
          const originalGetItem = storagePrototype.getItem;
          const originalSetItem = storagePrototype.setItem;
          const originalRemoveItem = storagePrototype.removeItem;
          storagePrototype.getItem = () => { throw new Error('storage unavailable'); };
          storagePrototype.setItem = () => { throw new Error('storage unavailable'); };
          storagePrototype.removeItem = () => { throw new Error('storage unavailable'); };
          try {
            return {
              read: readDocumentOpsPendingRunMarker(),
              remembered: rememberDocumentOpsPendingRunMarker(tenantId, operationId),
              cleared: clearDocumentOpsPendingRunMarker(operationId),
            };
          } finally {
            storagePrototype.getItem = originalGetItem;
            storagePrototype.setItem = originalSetItem;
            storagePrototype.removeItem = originalRemoveItem;
          }
        }""",
        {"tenantId": tenant_id, "operationId": operation_id},
    )
    assert unavailable_storage_result == {
        "read": None,
        "remembered": False,
        "cleared": False,
    }


def test_document_ops_agent_shared_marker_survives_tab_close_and_blocks_another_tab(page):
    context = page.context
    base_url = page.url.split("?", 1)[0]
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)
    page.evaluate(
        """() => {
          const nativeFetch = window.fetch;
          window.__docopsFirstPostBodies = [];
          window.fetch = (input, options) => {
            const url = String(input || '');
            if (url === '/api/agent/document-ops/run') {
              window.__docopsFirstPostBodies.push(JSON.parse(options.body));
              return new Promise(() => {});
            }
            return nativeFetch(input, options);
          };
          document.querySelector('#docops-title').value = 'Cross-tab pending run';
          document.querySelector('#docops-capture-trajectory').checked = true;
          void runDocumentOpsAgent();
        }"""
    )
    page.wait_for_function("() => readDocumentOpsPendingRunMarker() !== null")

    marker = page.evaluate(
        """() => ({
          parsed: readDocumentOpsPendingRunMarker(),
          shared: JSON.parse(
            localStorage.getItem(
              documentOpsPendingRunMarkerKey(_currentTenantId),
            ) || 'null',
          ),
          postCount: window.__docopsFirstPostBodies.length,
        })"""
    )
    assert marker["postCount"] == 1
    assert marker["shared"] == marker["parsed"]
    assert marker["shared"]["operation_id"].startswith("agent-run:")

    page.close()
    second_page = context.new_page()
    second_page.goto(base_url)
    second_page.wait_for_selector(".bundle-card", timeout=10000)
    second_page.evaluate(
        """() => {
          const nativeFetch = window.fetch;
          window.__docopsSecondPostBodies = [];
          window.__docopsStatusReads = [];
          const response = body => new Response(
            JSON.stringify(body),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
          window.fetch = (input, options) => {
            const url = String(input || '');
            if (url.startsWith('/api/agent/document-ops/run-operations/')) {
              const operationId = decodeURIComponent(url.split('/').pop());
              window.__docopsStatusReads.push(operationId);
              return Promise.resolve(response({
                schema_version: 'document_ops_agent_operation_status_v1',
                operation_id: operationId,
                status: 'running',
                started_at: '2026-07-21T00:00:00+00:00',
                completed_at: null,
                replay_available: false,
                next_action: 'wait_and_recheck',
                read_only: true,
                provider_call_authorized: false,
                result_included: false,
              }));
            }
            if (url === '/api/agent/document-ops/run') {
              window.__docopsSecondPostBodies.push(JSON.parse(options.body));
              return Promise.resolve(response({ detail: 'unexpected Agent POST' }));
            }
            return nativeFetch(input, options);
          };
        }"""
    )
    second_page.locator('[data-page="document-ops-page"]').click()
    second_page.wait_for_selector("[data-docops-run-release]", timeout=5000)

    second_result = second_page.evaluate(
        """() => ({
          marker: readDocumentOpsPendingRunMarker(),
          statusReads: [...window.__docopsStatusReads],
          postCount: window.__docopsSecondPostBodies.length,
          resultText: document.querySelector('#document-ops-result').textContent,
        })"""
    )
    assert second_result["marker"] == marker["shared"]
    assert second_result["statusReads"] == [marker["shared"]["operation_id"]]
    assert second_result["postCount"] == 0
    assert "status=running" in second_result["resultText"]

    second_page.evaluate("() => runDocumentOpsAgent()")
    assert second_page.evaluate("() => window.__docopsStatusReads.length") == 2
    assert second_page.evaluate("() => window.__docopsSecondPostBodies.length") == 0

    second_page.once("dialog", lambda dialog: dialog.accept())
    second_page.locator("[data-docops-run-release]").click()
    assert second_page.evaluate(
        "() => localStorage.getItem(documentOpsPendingRunMarkerKey(_currentTenantId))"
    ) is None
    second_page.close()


def test_document_ops_agent_cross_tab_claim_starts_one_post(page):
    context = page.context
    second_page = context.new_page()
    second_page.goto(page.url.split("?", 1)[0])
    second_page.wait_for_selector(".bundle-card", timeout=10000)

    setup_script = """() => {
      const nativeFetch = window.fetch;
      window.__docopsClaimPosts = [];
      window.__docopsClaimStatusReads = [];
      const response = body => new Response(
        JSON.stringify(body),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
      window.fetch = (input, options) => {
        const url = String(input || '');
        if (url === '/api/agent/document-ops/run') {
          window.__docopsClaimPosts.push(JSON.parse(options.body));
          return new Promise(() => {});
        }
        if (url.startsWith('/api/agent/document-ops/run-operations/')) {
          const operationId = decodeURIComponent(url.split('/').pop());
          window.__docopsClaimStatusReads.push(operationId);
          return Promise.resolve(response({
            schema_version: 'document_ops_agent_operation_status_v1',
            operation_id: operationId,
            status: 'running',
            started_at: '2026-07-21T00:00:00+00:00',
            completed_at: null,
            replay_available: false,
            next_action: 'wait_and_recheck',
            read_only: true,
            provider_call_authorized: false,
            result_included: false,
          }));
        }
        return nativeFetch(input, options);
      };
      document.querySelector('#docops-title').value = 'Atomic cross-tab claim';
      document.querySelector('#docops-capture-trajectory').checked = true;
    }"""
    for current_page in (page, second_page):
        current_page.locator('[data-page="document-ops-page"]').click()
        current_page.wait_for_timeout(250)
        current_page.evaluate(setup_script)

    page.evaluate("() => { void runDocumentOpsAgent(); }")
    second_page.evaluate("() => { void runDocumentOpsAgent(); }")
    for _ in range(50):
        post_count = sum(
            current_page.evaluate("() => window.__docopsClaimPosts.length")
            for current_page in (page, second_page)
        )
        status_count = sum(
            current_page.evaluate("() => window.__docopsClaimStatusReads.length")
            for current_page in (page, second_page)
        )
        if post_count == 1 and status_count == 1:
            break
        page.wait_for_timeout(100)

    snapshots = [
        current_page.evaluate(
            """() => ({
              marker: readDocumentOpsPendingRunMarker(),
              posts: [...window.__docopsClaimPosts],
              statusReads: [...window.__docopsClaimStatusReads],
              resultText: document.querySelector('#document-ops-result').textContent,
            })"""
        )
        for current_page in (page, second_page)
    ]
    assert sum(len(snapshot["posts"]) for snapshot in snapshots) == 1
    assert sum(len(snapshot["statusReads"]) for snapshot in snapshots) == 1
    assert snapshots[0]["marker"] == snapshots[1]["marker"]

    owner_index = 0 if snapshots[0]["posts"] else 1
    blocked_index = 1 - owner_index
    owner_page = (page, second_page)[owner_index]
    blocked_page = (page, second_page)[blocked_index]
    assert snapshots[blocked_index]["statusReads"] == [
        snapshots[owner_index]["posts"][0]["operation_id"]
    ]
    assert "status=running" in snapshots[blocked_index]["resultText"]

    owner_page.close()
    blocked_page.once("dialog", lambda dialog: dialog.accept())
    blocked_page.locator("[data-docops-run-release]").click()
    assert blocked_page.evaluate(
        "() => localStorage.getItem(documentOpsPendingRunMarkerKey(_currentTenantId))"
    ) is None
    if not blocked_page.is_closed():
        blocked_page.close()


def test_document_ops_agent_pending_markers_are_isolated_by_tenant(page):
    tenant_a = "marker-tenant-a"
    tenant_b = "marker-tenant-b"
    operation_a = "agent-run:11111111-2222-4333-8444-555555555555"
    operation_b = "agent-run:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    operation_c = "agent-run:99999999-8888-4777-8666-555555555555"

    result = page.evaluate(
        """({ tenantA, tenantB, operationA, operationB, operationC }) => {
          const markerPrefix = 'dd_document_ops_pending_run_v1';
          const clearTestMarkers = storage => {
            Object.keys(storage)
              .filter(key => key === markerPrefix || key.startsWith(`${markerPrefix}:`))
              .forEach(key => storage.removeItem(key));
          };
          clearTestMarkers(localStorage);
          clearTestMarkers(sessionStorage);
          try {
            const rememberedA = rememberDocumentOpsPendingRunMarker(tenantA, operationA);
            const markerA = readDocumentOpsPendingRunMarker(tenantA);
            const markerBeforeB = readDocumentOpsPendingRunMarker(tenantB);
            const markerAAfterBRead = readDocumentOpsPendingRunMarker(tenantA);

            const rememberedB = rememberDocumentOpsPendingRunMarker(tenantB, operationB);
            const scopedResult = {
              rememberedA,
              markerA,
              markerBeforeB,
              markerAAfterBRead,
              rememberedB,
              markerAAfterBWrite: readDocumentOpsPendingRunMarker(tenantA),
              markerB: readDocumentOpsPendingRunMarker(tenantB),
            };
            const clearedA = clearDocumentOpsPendingRunMarker(operationA, tenantA);
            const markerAAfterClear = readDocumentOpsPendingRunMarker(tenantA);
            const markerBAfterAClear = readDocumentOpsPendingRunMarker(tenantB);

            clearTestMarkers(localStorage);
            clearTestMarkers(sessionStorage);
            localStorage.setItem(markerPrefix, JSON.stringify(markerA));
            const scopedMarker = { ...markerA, operation_id: operationC };
            sessionStorage.setItem(
              documentOpsPendingRunMarkerKey(tenantA),
              JSON.stringify(scopedMarker),
            );
            return {
              ...scopedResult,
              clearedA,
              markerAAfterClear,
              markerBAfterAClear,
              legacyMarkerBeforeB: readDocumentOpsPendingRunMarker(tenantB),
              legacyMarkerAfterB: JSON.parse(localStorage.getItem(markerPrefix)),
              scopedMarkerOverLegacy: readDocumentOpsPendingRunMarker(tenantA),
            };
          } finally {
            clearTestMarkers(localStorage);
            clearTestMarkers(sessionStorage);
          }
        }""",
        {
            "tenantA": tenant_a,
            "tenantB": tenant_b,
            "operationA": operation_a,
            "operationB": operation_b,
            "operationC": operation_c,
        },
    )

    marker_a = {
        "schema_version": "document_ops_agent_pending_run_marker_v1",
        "tenant_id": tenant_a,
        "operation_id": operation_a,
    }
    marker_b = {
        "schema_version": "document_ops_agent_pending_run_marker_v1",
        "tenant_id": tenant_b,
        "operation_id": operation_b,
    }
    marker_c = {
        "schema_version": "document_ops_agent_pending_run_marker_v1",
        "tenant_id": tenant_a,
        "operation_id": operation_c,
    }
    assert result == {
        "rememberedA": True,
        "markerA": marker_a,
        "markerBeforeB": None,
        "markerAAfterBRead": marker_a,
        "rememberedB": True,
        "markerAAfterBWrite": marker_a,
        "markerB": marker_b,
        "clearedA": True,
        "markerAAfterClear": None,
        "markerBAfterAClear": marker_b,
        "legacyMarkerBeforeB": None,
        "legacyMarkerAfterB": marker_a,
        "scopedMarkerOverLegacy": marker_c,
    }


def test_document_ops_trajectory_search_does_not_render_old_results_during_debounce(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingLists = [];
          const listResponse = (title, query) => new Response(JSON.stringify({
            trajectories: [{
              trajectory_id: `trajectory-${query}`,
              title,
              task_type: 'decision_brief',
              draft_preview: `${title} draft`,
              human_review_status: 'pending',
              qa: { hard_gate_pass: true, overall_score: 1 },
            }],
            total: 1,
            offset: 0,
            returned: 1,
            has_more: false,
            order: 'newest',
          }), { status: 200, headers: { 'Content-Type': 'application/json' } });
          try {
            window.fetch = (input, options) => {
              const url = String(input || '');
              if (url.startsWith('/api/agent/document-ops/trajectories?')) {
                return new Promise(resolve => pendingLists.push(resolve));
              }
              return nativeFetch(input, options);
            };

            const queryInput = document.querySelector('#docops-trajectory-query');
            queryInput.value = 'old';
            const oldRequest = loadDocumentOpsTrajectoryList(0);
            while (pendingLists.length < 1) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            queryInput.value = 'new';
            queryInput.dispatchEvent(new Event('input', { bubbles: true }));
            pendingLists[0](listResponse('stale search result', 'old'));
            await oldRequest;
            const duringDebounce = document.querySelector('#document-ops-trajectories').textContent;

            while (pendingLists.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 10));
            }
            pendingLists[1](listResponse('current search result', 'new'));
            for (let attempt = 0; attempt < 100; attempt += 1) {
              const text = document.querySelector('#document-ops-trajectories').textContent;
              if (text.includes('current search result')) break;
              await new Promise(resolve => setTimeout(resolve, 10));
            }
            const finalText = document.querySelector('#document-ops-trajectories').textContent;
            return { duringDebounce, finalText };
          } finally {
            clearTimeout(_documentOpsTrajectorySearchTimer);
            _documentOpsTrajectorySearchTimer = null;
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "stale search result" not in result["duringDebounce"]
    assert "current search result" in result["finalText"]
    assert "stale search result" not in result["finalText"]


def test_document_ops_trajectory_history_searches_filters_and_paginates_without_mobile_overflow(page, tmp_path):
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    created_ids = page.evaluate(
        """async () => {
          const token = localStorage.getItem('dd_access_token');
          const headers = {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          };
          const ids = [];
          for (let index = 1; index <= 13; index += 1) {
            const response = await fetch('/api/agent/document-ops/run', {
              method: 'POST',
              headers,
              body: JSON.stringify({
                task_type: index <= 9 ? 'decision_brief' : 'evidence_gap_review',
                requirements: { title: `브라우저 이력 ${index}` },
                capture_trajectory: true,
              }),
            });
            if (!response.ok) throw new Error(`trajectory create failed: ${response.status}`);
            ids.push((await response.json()).trajectory_id);
          }
          for (const index of [9, 11]) {
            const response = await fetch(`/api/agent/document-ops/trajectories/${ids[index]}/review`, {
              method: 'POST',
              headers,
              body: JSON.stringify({ accepted: true, expected_review_version: 0, reviewer: 'e2e-reviewer' }),
            });
            if (!response.ok) throw new Error(`trajectory review failed: ${response.status}`);
          }
          return ids;
        }"""
    )

    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)
    assert page_errors == []
    trajectory_text = page.locator("#document-ops-trajectories").inner_text()
    assert "trajectory 로드 실패" not in trajectory_text, trajectory_text
    _wait_until_text_contains(page, "#document-ops-trajectories", "13건 중 1-10", timeout_ms=10000)
    cards = page.locator("#document-ops-trajectories [data-docops-trajectory-card]")
    assert cards.count() == 10
    assert "브라우저 이력 13" in cards.first.inner_text()
    assert created_ids[-1] in cards.first.inner_text()
    assert page.get_by_role("button", name="이전 trajectory 페이지").is_disabled()
    assert not page.get_by_role("button", name="다음 trajectory 페이지").is_disabled()
    page.screenshot(path=str(tmp_path / "document-ops-trajectory-desktop.png"), full_page=True)

    page.fill("#docops-trajectory-query", "브라우저 이력 2")
    _wait_until_text_contains(page, "#document-ops-trajectories", "1건 중 1-1", timeout_ms=10000)
    assert cards.count() == 1
    assert "브라우저 이력 2" in cards.first.inner_text()

    page.fill("#docops-trajectory-query", "E2E-REVIEWER")
    _wait_until_text_contains(page, "#document-ops-trajectories", "2건 중 1-2", timeout_ms=10000)
    assert cards.count() == 2
    assert "브라우저 이력 12" in cards.first.inner_text()

    page.fill("#docops-trajectory-query", "")
    _wait_until_text_contains(page, "#document-ops-trajectories", "13건 중 1-10", timeout_ms=10000)
    page.select_option("#docops-trajectory-order", "oldest")
    _wait_until_text_contains(page, "#document-ops-trajectories", "13건 중 1-10", timeout_ms=10000)
    assert "브라우저 이력 1" in cards.first.inner_text()
    page.get_by_role("button", name="다음 trajectory 페이지").click()
    _wait_until_text_contains(page, "#document-ops-trajectories", "13건 중 11-13", timeout_ms=10000)
    assert "브라우저 이력 11" in cards.first.inner_text()

    page.select_option("#docops-trajectory-order", "newest")
    _wait_until_text_contains(page, "#document-ops-trajectories", "13건 중 1-10", timeout_ms=10000)
    assert "브라우저 이력 13" in cards.first.inner_text()

    page.get_by_role("button", name="다음 trajectory 페이지").click()
    _wait_until_text_contains(page, "#document-ops-trajectories", "13건 중 11-13", timeout_ms=10000)
    assert cards.count() == 3
    assert "브라우저 이력 3" in cards.first.inner_text()
    assert not page.get_by_role("button", name="이전 trajectory 페이지").is_disabled()
    assert page.get_by_role("button", name="다음 trajectory 페이지").is_disabled()

    page.evaluate(
        """() => {
          window.__documentOpsNativeFetch = window.fetch;
          window.fetch = async (...args) => {
            const response = await window.__documentOpsNativeFetch(...args);
            const url = String(args[0] || '');
            if (url.includes('task_type=evidence_gap_review') && !url.includes('human_review_status=accepted')) {
              await new Promise(resolve => setTimeout(resolve, 300));
            }
            return response;
          };
        }"""
    )
    page.select_option("#docops-trajectory-task-filter", "evidence_gap_review")
    page.select_option("#docops-trajectory-review-filter", "accepted")
    _wait_until_text_contains(page, "#document-ops-trajectories", "2건 중 1-2", timeout_ms=10000)
    page.wait_for_timeout(500)
    assert cards.count() == 2
    assert "브라우저 이력 12" in cards.first.inner_text()
    page.evaluate(
        """() => {
          window.fetch = window.__documentOpsNativeFetch;
          delete window.__documentOpsNativeFetch;
        }"""
    )

    page.evaluate(
        """async () => {
          document.querySelector('#docops-trajectory-task-filter').value = '';
          document.querySelector('#docops-trajectory-review-filter').value = 'pending';
          _documentOpsTrajectoryOffset = 0;
          await loadDocumentOpsTrajectoryList(0);
        }"""
    )
    _wait_until_text_contains(page, "#document-ops-trajectories", "11건 중 1-10", timeout_ms=10000)
    page.get_by_role("button", name="다음 trajectory 페이지").click()
    _wait_until_text_contains(page, "#document-ops-trajectories", "11건 중 11-11", timeout_ms=10000)
    assert cards.count() == 1
    assert "브라우저 이력 1" in cards.first.inner_text()

    page.evaluate(
        """async trajectoryId => {
          const token = localStorage.getItem('dd_access_token');
          const response = await fetch(`/api/agent/document-ops/trajectories/${trajectoryId}/review`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ accepted: true, expected_review_version: 0, reviewer: 'e2e-page-reviewer' }),
          });
          if (!response.ok) throw new Error(`trajectory review failed: ${response.status}`);
          await loadDocumentOpsTrajectoryList();
        }""",
        created_ids[0],
    )
    _wait_until_text_contains(page, "#document-ops-trajectories", "10건 중 1-10", timeout_ms=10000)
    assert cards.count() == 10

    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(tmp_path / "document-ops-trajectory-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    assert console_errors == []


def test_document_ops_governance_overview_rechecks_all_read_only_evidence(
    page,
    live_server,
    tmp_path,
):
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    overview_requests: list[dict[str, str]] = []
    attention_payload = _governance_overview_payload(
        attention_required=True,
        signoff_complete=False,
        export_filename="attention-export.jsonl",
    )
    ready_payload = _governance_overview_payload(
        attention_required=False,
        signoff_complete=True,
        export_filename="current-export.jsonl",
    )

    def handle_overview(route):
        request = route.request
        overview_requests.append(
            {
                "method": request.method,
                "ops_key": request.headers.get("x-decisiondoc-ops-key", ""),
                "authorization": request.headers.get("authorization", ""),
            }
        )
        payload = attention_payload if len(overview_requests) == 1 else ready_payload
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    page.route(
        "**/api/agent/document-ops/trajectories/governance/overview?*",
        handle_overview,
    )
    page.locator('[data-page="document-ops-page"]').click()
    page.fill("#docops-ops-key-input", live_server["ops_key"])
    page.locator('[data-docops-action="load-governance"]').click()

    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "ARTIFACT CHECK NEEDED",
        timeout_ms=10000,
    )
    overview_panel = page.locator("#document-ops-governance-overview")
    inventory_panel = page.locator("#document-ops-governance-artifact-inventory")
    signoff_panel = page.locator("#document-ops-reviewer-signoff-summary")
    assert "문제 2개" in overview_panel.inner_text()
    assert "첫 관측입니다." in overview_panel.inner_text()
    assert "combined snapshot atomic=false" in overview_panel.inner_text()
    assert "external authorization all false=true" in overview_panel.inner_text()
    inventory_text = inventory_panel.inner_text()
    assert "sft_tampered.jsonl" in inventory_text
    assert "orphan.json" in inventory_text
    assert "참조 파일 변조" in inventory_text
    assert "권위 metadata에 없는 파일" in inventory_text
    assert "어떤 파일도 삭제하지 않습니다." in inventory_text
    assert inventory_panel.locator("[data-docops-artifact-issue]").count() == 2
    assert "SIGN-OFF PENDING" in signoff_panel.inner_text()
    assert overview_panel.get_by_role(
        "button",
        name="governance review 상태 다시 확인",
    ).count() == 1
    assert len(overview_requests) == 1
    first_request = overview_requests[0]
    assert first_request["method"] == "GET"
    assert first_request["ops_key"] == live_server["ops_key"]
    assert first_request["authorization"].startswith("Bearer ")

    overview_panel.get_by_role(
        "button",
        name="governance review 상태 다시 확인",
    ).click()
    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "REVIEW EVIDENCE READY",
        timeout_ms=10000,
    )
    assert (
        "권위 metadata와 현재 backend artifact가 일치합니다."
        in inventory_panel.inner_text()
    )
    assert "직전 재확인 이후 검토 상태가 달라졌습니다." in overview_panel.inner_text()
    assert "SIGN-OFF COMPLETE" in signoff_panel.inner_text()
    assert inventory_panel.locator("[data-docops-artifact-issue]").count() == 0
    assert len(overview_requests) == 2
    assert all(request["method"] == "GET" for request in overview_requests)
    assert all(
        request["ops_key"] == live_server["ops_key"]
        for request in overview_requests
    )

    current_state = page.evaluate(
        """async ({ staleOverview, currentOverview }) => {
          const nativeFetch = window.fetch;
          const currentTenantId = _currentTenantId;
          const pendingResponses = [];
          let holdResponses = true;
          const isOverview = url => url.includes('/governance/overview?');
          const responseFor = payload => new Response(
            JSON.stringify(payload),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
          try {
            window.fetch = (input, options) => {
              const url = String(input || '');
              if (!isOverview(url)) {
                return nativeFetch(input, options);
              }
              if (holdResponses) {
                return new Promise(resolve => pendingResponses.push(resolve));
              }
              return Promise.resolve(responseFor(currentOverview));
            };

            _currentTenantId = 'stale-tenant';
            const staleLoad = loadDocumentOpsGovernance();
            while (pendingResponses.length < 1) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            holdResponses = false;
            _currentTenantId = currentTenantId;
            await loadDocumentOpsGovernance();
            pendingResponses.forEach(resolve => resolve(responseFor(staleOverview)));
            await staleLoad;

            return {
              overviewText: document.querySelector('#document-ops-governance-overview')?.textContent || '',
              summaryText: document.querySelector('#document-ops-training-governance-summary')?.textContent || '',
              inventoryText: document.querySelector('#document-ops-governance-artifact-inventory')?.textContent || '',
              signoffText: document.querySelector('#document-ops-reviewer-signoff-summary')?.textContent || '',
            };
          } finally {
            window.fetch = nativeFetch;
            _currentTenantId = currentTenantId;
          }
        }""",
        {
            "staleOverview": _governance_overview_payload(
                attention_required=True,
                signoff_complete=False,
                export_filename="stale-export.jsonl",
            ),
            "currentOverview": ready_payload,
        },
    )
    assert "REVIEW EVIDENCE READY" in current_state["overviewText"]
    assert "ARTIFACT CHECK NEEDED" not in current_state["overviewText"]
    assert "직전 재확인과 검토 상태가 동일합니다." in current_state["overviewText"]
    assert "current-export.jsonl" in current_state["summaryText"]
    assert "stale-export.jsonl" not in current_state["summaryText"]
    assert "ARTIFACTS CLEAN" in current_state["inventoryText"]
    assert "sft_tampered.jsonl" not in current_state["inventoryText"]
    assert "SIGN-OFF COMPLETE" in current_state["signoffText"]

    page.route(
        "**/api/agent/document-ops/trajectories/export",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "exported": True,
                    "filename": "new-reviewed-export.jsonl",
                }
            ),
        ),
    )
    page.locator('[data-docops-action="export-trajectories"]').click()
    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "RECHECK REQUIRED",
        timeout_ms=10000,
    )
    assert (
        "새 reviewed SFT export가 생성되었습니다."
        in overview_panel.inner_text()
    )
    assert (
        overview_panel.get_attribute("data-governance-fresh")
        == "false"
    )
    overview_panel.get_by_role(
        "button",
        name="governance review 상태 다시 확인",
    ).click()
    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "REVIEW EVIDENCE READY",
        timeout_ms=10000,
    )
    assert overview_panel.get_attribute("data-governance-fresh") == "true"
    assert "직전 재확인과 검토 상태가 동일합니다." in overview_panel.inner_text()

    page.select_option("#docops-training-provider", "openai")
    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "RECHECK REQUIRED",
        timeout_ms=10000,
    )
    assert "Planning provider 조건이 변경되었습니다." in overview_panel.inner_text()
    overview_panel.get_by_role(
        "button",
        name="governance review 상태 다시 확인",
    ).click()
    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "REVIEW EVIDENCE READY",
        timeout_ms=10000,
    )
    assert overview_panel.get_attribute("data-governance-fresh") == "true"
    assert len(overview_requests) == 4

    page.screenshot(
        path=str(tmp_path / "document-ops-governance-overview-desktop.png"),
        full_page=True,
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(
        path=str(tmp_path / "document-ops-governance-overview-mobile.png"),
        full_page=True,
    )
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    assert page.evaluate(
        """() => {
          _documentOpsGovernanceObservation = {
            tenantId: _currentTenantId,
            fingerprint: 'f'.repeat(64),
          };
          logout();
          return _documentOpsGovernanceObservation === null;
        }"""
    )
    assert console_errors == []
    assert page_errors == []


def test_document_ops_governance_view_is_visible_in_redacted_audit_history(
    page,
    live_server,
):
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.locator('[data-page="document-ops-page"]').click()
    page.fill("#docops-ops-key-input", live_server["ops_key"])
    page.locator('[data-docops-action="load-governance"]').click()
    _wait_until_text_contains(
        page,
        "#document-ops-governance-overview",
        "FIRST OBSERVATION",
        timeout_ms=10000,
    )

    page.evaluate(
        """async () => {
          document.querySelector('#ops-panel').style.display = 'block';
          document.querySelector('#audit-action-filter').value = 'document_ops.governance_view';
          await loadAuditLogs({ action: 'document_ops.governance_view' }, 0);
        }"""
    )
    audit_text = page.locator("#audit-log-table").inner_text()
    assert "document_ops.governance_view" in audit_text
    assert "surface=governance_overview" in audit_text
    assert "status=" in audit_text
    assert "read_only=true" in audit_text
    assert "fingerprint_persisted=false" in audit_text
    assert "review_state_fingerprint" not in audit_text
    assert "training_governance_summary" not in audit_text
    assert "reviewer_signoff_summary" not in audit_text
    assert console_errors == []
    assert page_errors == []


def test_document_ops_stats_keeps_the_latest_same_tenant_response(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pending = [];
          const statsUrl = '/api/agent/document-ops/trajectories/stats';
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          try {
            window.fetch = (input, options) => {
              if (String(input || '') !== statsUrl) {
                return nativeFetch(input, options);
              }
              return new Promise(resolve => pending.push(resolve));
            };

            const olderSuccess = loadDocumentOpsStats();
            const newerSuccess = loadDocumentOpsStats();
            while (pending.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[1](response({
              total_records: 2,
              accepted_records: 2,
              pending_records: 0,
              export_count: 1,
            }));
            await newerSuccess;
            pending[0](response({
              total_records: 2,
              accepted_records: 1,
              pending_records: 1,
              export_count: 0,
            }));
            await olderSuccess;
            const successText = document.querySelector('#document-ops-stats').textContent;

            const olderFailure = loadDocumentOpsStats();
            const newestSuccess = loadDocumentOpsStats();
            while (pending.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[3](response({
              total_records: 3,
              accepted_records: 3,
              pending_records: 0,
              export_count: 2,
            }));
            await newestSuccess;
            pending[2](response({ detail: 'stale failure' }, 503));
            await olderFailure;
            const finalText = document.querySelector('#document-ops-stats').textContent;

            return { successText, finalText };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "accepted 2" in result["successText"]
    assert "pending 0" in result["successText"]
    assert "exports 1" in result["successText"]
    assert "accepted 3" in result["finalText"]
    assert "pending 0" in result["finalText"]
    assert "exports 2" in result["finalText"]
    assert "stats 로드 실패" not in result["finalText"]


def test_document_ops_exports_keep_the_latest_same_tenant_response(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingExports = [];
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          try {
            window.fetch = (input, options) => {
              const url = String(input || '');
              if (url.includes('/api/agent/document-ops/trajectories/reviewed-sft-exports?')) {
                return new Promise(resolve => pendingExports.push(resolve));
              }
              if (url === '/api/agent/document-ops/trajectories/freezes?limit=200') {
                return Promise.resolve(response({ freezes: [] }));
              }
              return nativeFetch(input, options);
            };

            document.querySelector('#docops-task-type').value = 'decision_brief';
            const olderSuccess = loadDocumentOpsExports();
            document.querySelector('#docops-task-type').value = 'evidence_gap_review';
            const newerSuccess = loadDocumentOpsExports();
            while (pendingExports.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingExports[1](response({
              total: 1,
              exports: [{
                filename: 'new-evidence-gap.jsonl',
                record_count: 2,
                size_bytes: 120,
                content_sha256: 'b'.repeat(64),
                exists: true,
              }],
            }));
            await newerSuccess;
            pendingExports[0](response({
              total: 1,
              exports: [{
                filename: 'old-decision-brief.jsonl',
                record_count: 1,
                size_bytes: 80,
                content_sha256: 'a'.repeat(64),
                exists: true,
              }],
            }));
            await olderSuccess;
            const successText = document.querySelector('#document-ops-export-list').textContent;

            const olderFailure = loadDocumentOpsExports();
            const newestSuccess = loadDocumentOpsExports();
            while (pendingExports.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingExports[3](response({
              total: 1,
              exports: [{
                filename: 'newest-evidence-gap.jsonl',
                record_count: 3,
                size_bytes: 160,
                content_sha256: 'c'.repeat(64),
                exists: true,
              }],
            }));
            await newestSuccess;
            pendingExports[2](response({ detail: 'stale failure' }, 503));
            await olderFailure;
            const finalText = document.querySelector('#document-ops-export-list').textContent;
            const notifications = document.querySelector('#notification-container').textContent;

            const changedDuringRead = loadDocumentOpsExports();
            while (pendingExports.length < 5) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            const taskInput = document.querySelector('#docops-task-type');
            taskInput.value = 'policy_planning_brief';
            taskInput.dispatchEvent(new Event('change', { bubbles: true }));
            pendingExports[4](response({
              total: 1,
              exports: [{
                filename: 'wrong-task-after-change.jsonl',
                record_count: 1,
                size_bytes: 80,
                content_sha256: 'd'.repeat(64),
                exists: true,
              }],
            }));
            await changedDuringRead;
            const staleText = document.querySelector('#document-ops-export-list').textContent;

            return { successText, finalText, notifications, staleText };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "new-evidence-gap.jsonl" in result["successText"]
    assert "old-decision-brief.jsonl" not in result["successText"]
    assert "newest-evidence-gap.jsonl" in result["finalText"]
    assert "Export 목록 로드 실패" not in result["finalText"]
    assert "stale failure" not in result["notifications"]
    assert "RECHECK REQUIRED" in result["staleText"]
    assert "wrong-task-after-change.jsonl" not in result["staleText"]


def _document_ops_export_preview(task_type: str, suffix: str) -> dict[str, object]:
    return {
        "task_type": task_type,
        "would_export": True,
        "candidate_count": 1,
        "eligible_count": 1,
        "blocked_count": 0,
        "estimated_jsonl_lines": 1,
        "quality_score_summary": {"avg": 0.9},
        "blocker_summary": {},
        "sample_records": [
            {
                "trajectory_id": f"trajectory-{suffix}",
                "task_type": task_type,
                "skill": "policy-planning",
                "quality_score": 0.9,
                "blockers": [],
            }
        ],
        "blocked_samples": [],
    }


def _document_ops_training_plan(provider: str, base_model: str, suffix: str) -> dict[str, object]:
    return {
        "status": "preview_ready",
        "job_spec": {
            "provider": provider,
            "base_model": base_model,
            "objective": f"objective-{suffix}",
            "dataset": {
                "export_filename": f"export-{suffix}.jsonl",
                "record_count": 1,
                "freeze_manifest_id": f"freeze-{suffix}",
            },
            "evaluation": {
                "suite": "document_ops_offline_eval",
                "required_metrics": {"schema_valid_rate": 1},
            },
            "training_parameters": {"epochs": 1},
            "execution_steps": [
                {"step": f"validate-{suffix}", "status": "dry_run_pass"}
            ],
        },
        "blockers": [],
    }


@pytest.mark.parametrize(
    "case",
    [
        {
            "loader": "export-preview",
            "container_id": "document-ops-export-preview",
            "url_prefix": "/api/agent/document-ops/trajectories/export/preview",
            "older": _document_ops_export_preview("decision_brief", "old"),
            "newer": _document_ops_export_preview("evidence_gap_review", "new"),
            "newest": _document_ops_export_preview("policy_planning_brief", "newest"),
            "new_marker": "trajectory-new",
            "old_marker": "trajectory-old",
            "newest_marker": "trajectory-newest",
            "failure_label": "Export preview 실패",
            "stale_error": "stale export preview failure",
            "change_target": "task",
        },
        {
            "loader": "training-plan",
            "container_id": "document-ops-training-plan-preview",
            "url_prefix": "/api/agent/document-ops/trajectories/training-plan/preview?",
            "older": _document_ops_training_plan("openai", "old-model", "old"),
            "newer": _document_ops_training_plan("gemini", "new-model", "new"),
            "newest": _document_ops_training_plan("openai", "newest-model", "newest"),
            "new_marker": "export-new.jsonl",
            "old_marker": "export-old.jsonl",
            "newest_marker": "export-newest.jsonl",
            "failure_label": "Training plan preview 실패",
            "stale_error": "stale training plan failure",
            "change_target": "provider",
        },
    ],
    ids=("export-preview", "training-plan"),
)
def test_document_ops_previews_keep_the_current_input_context(page, case):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async scenario => {
          const nativeFetch = window.fetch;
          const pending = [];
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          const loadPreview = scenario.loader === 'export-preview'
            ? previewDocumentOpsExport
            : previewDocumentOpsTrainingPlan;
          const taskInput = document.querySelector('#docops-task-type');
          const providerInput = document.querySelector('#docops-training-provider');
          const modelInput = document.querySelector('#docops-training-base-model');
          const setContext = (taskType, provider, baseModel) => {
            taskInput.value = taskType;
            providerInput.value = provider;
            modelInput.value = baseModel;
          };
          try {
            window.fetch = (input, options) => {
              if (!String(input || '').startsWith(scenario.url_prefix)) {
                return nativeFetch(input, options);
              }
              return new Promise(resolve => pending.push(resolve));
            };

            setContext('decision_brief', 'openai', 'old-model');
            const olderSuccess = loadPreview();
            setContext('evidence_gap_review', 'gemini', 'new-model');
            const newerSuccess = loadPreview();
            while (pending.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[1](response(scenario.newer));
            await newerSuccess;
            pending[0](response(scenario.older));
            await olderSuccess;
            const container = document.querySelector(`#${scenario.container_id}`);
            const successText = container.textContent;

            setContext('develop_quality_improvement', 'claude', 'older-failure');
            const olderFailure = loadPreview();
            setContext('policy_planning_brief', 'openai', 'newest-model');
            const newestSuccess = loadPreview();
            while (pending.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[3](response(scenario.newest));
            await newestSuccess;
            pending[2](response({ detail: scenario.stale_error }, 503));
            await olderFailure;
            const finalText = container.textContent;
            const notifications = document.querySelector('#notification-container').textContent;

            if (scenario.change_target === 'task') {
              taskInput.value = 'decision_brief';
              taskInput.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
              providerInput.value = 'gemini';
              providerInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
            const staleText = container.textContent;

            return { successText, finalText, notifications, staleText };
          } finally {
            window.fetch = nativeFetch;
          }
        }""",
        case,
    )

    assert case["new_marker"] in result["successText"]
    assert case["old_marker"] not in result["successText"]
    assert case["newest_marker"] in result["finalText"]
    assert case["failure_label"] not in result["finalText"]
    assert case["stale_error"] not in result["notifications"]
    assert "RECHECK REQUIRED" in result["staleText"]
    assert case["newest_marker"] not in result["staleText"]


def test_document_ops_readiness_keeps_the_latest_same_tenant_response(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pending = [];
          const readinessUrl = '/api/agent/document-ops/trajectories/training-readiness?limit=20';
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          const readiness = (manifestId, exportFilename) => ({
            status: 'ready_for_training_decision',
            blockers: [],
            reviewed_export_count: 1,
            freeze_count: 1,
            dry_run_training_approval_count: 0,
            latest_export_quality: { schema_invalid_count: 0 },
            eval_plan_coverage: {
              latest: {
                suite: 'document_ops_offline_eval',
                required_metric_count: 2,
                required_metric_names: ['schema_valid_rate', 'source_reference_coverage'],
              },
            },
            latest_reviewed_export: { filename: exportFilename },
            latest_dataset_freeze: { manifest_id: manifestId, exists: true },
            latest_training_approval: {},
            artifact_chain: {
              freeze_integrity_verified: true,
              freeze_matches_latest_export: true,
              approval_integrity_verified: null,
              approval_matches_latest_freeze: false,
              approval_guard_clean: null,
            },
            training_guard: {
              no_training_started: true,
              training_started_count: 0,
              provider_job_started_count: 0,
              model_promotion_allowed_count: 0,
              external_upload_started: false,
            },
          });
          try {
            window.fetch = (input, options) => {
              if (String(input || '') !== readinessUrl) {
                return nativeFetch(input, options);
              }
              return new Promise(resolve => pending.push(resolve));
            };

            const olderSuccess = loadDocumentOpsTrainingReadiness();
            const newerSuccess = loadDocumentOpsTrainingReadiness();
            while (pending.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[1](response(readiness('freeze-new', 'new.jsonl')));
            await newerSuccess;
            pending[0](response(readiness('freeze-old', 'old.jsonl')));
            await olderSuccess;
            const successText = document.querySelector(
              '#document-ops-training-readiness',
            ).textContent;
            const successManifest = document.querySelector(
              '[data-docops-training-approve]',
            )?.dataset.docopsTrainingApprove || '';

            const olderFailure = loadDocumentOpsTrainingReadiness();
            const newestSuccess = loadDocumentOpsTrainingReadiness();
            while (pending.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[3](response(readiness('freeze-newest', 'newest.jsonl')));
            await newestSuccess;
            pending[2](response({ detail: 'stale readiness failure' }, 503));
            await olderFailure;
            const finalText = document.querySelector(
              '#document-ops-training-readiness',
            ).textContent;
            const finalManifest = document.querySelector(
              '[data-docops-training-approve]',
            )?.dataset.docopsTrainingApprove || '';
            const notifications = document.querySelector(
              '#notification-container',
            ).textContent;

            return {
              successText,
              successManifest,
              finalText,
              finalManifest,
              notifications,
            };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "new.jsonl" in result["successText"]
    assert "old.jsonl" not in result["successText"]
    assert result["successManifest"] == "freeze-new"
    assert "newest.jsonl" in result["finalText"]
    assert "Training readiness 로드 실패" not in result["finalText"]
    assert result["finalManifest"] == "freeze-newest"
    assert "stale readiness failure" not in result["notifications"]


def test_document_ops_execution_requests_keep_the_latest_same_tenant_response(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingReads = [];
          const requestsUrl = '/api/agent/document-ops/trajectories/training-execution-requests?limit=20';
          const createUrl = '/api/agent/document-ops/trajectories/training-execution-requests';
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          const records = requestId => ({
            training_execution_requests: [{
              request_id: requestId,
              requester: 'browser-requester',
              prior_training_approver: 'browser-approver',
              provider: 'openai',
              base_model: 'gpt-test-base',
              manifest_id: requestId.replace('request', 'freeze'),
              integrity_verified: true,
              two_person_guard_satisfied: true,
              training_execution_allowed: false,
              provider_api_calls_allowed: false,
              provider_job_started: false,
              external_upload_started: false,
              model_promotion_allowed: false,
            }],
          });
          try {
            window.fetch = (input, options = {}) => {
              const url = String(input || '');
              const method = String(options?.method || 'GET').toUpperCase();
              if (url === createUrl && method === 'POST') {
                return Promise.resolve(response({ request_id: 'request-saved' }));
              }
              if (url === requestsUrl) {
                return new Promise(resolve => pendingReads.push(resolve));
              }
              return nativeFetch(input, options);
            };

            const olderSuccess = loadDocumentOpsTrainingExecutionRequests();
            const newerSuccess = loadDocumentOpsTrainingExecutionRequests();
            while (pendingReads.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingReads[1](response(records('request-new')));
            await newerSuccess;
            pendingReads[0](response(records('request-old')));
            await olderSuccess;
            const successText = document.querySelector(
              '#document-ops-training-execution-requests',
            ).textContent;

            const olderFailure = loadDocumentOpsTrainingExecutionRequests();
            const newestSuccess = loadDocumentOpsTrainingExecutionRequests();
            while (pendingReads.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingReads[3](response(records('request-newest')));
            await newestSuccess;
            pendingReads[2](response({ detail: 'stale execution request failure' }, 503));
            await olderFailure;
            const finalText = document.querySelector(
              '#document-ops-training-execution-requests',
            ).textContent;

            const readBeforeSave = loadDocumentOpsTrainingExecutionRequests();
            while (pendingReads.length < 5) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            document.querySelector('#docops-execution-requester').value = 'browser-requester';
            const save = requestDocumentOpsTrainingExecution();
            while (pendingReads.length < 6) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingReads[5](response(records('request-saved')));
            await save;
            pendingReads[4](response(records('request-before-save')));
            await readBeforeSave;
            const savedText = document.querySelector(
              '#document-ops-training-execution-requests',
            ).textContent;

            return { successText, finalText, savedText };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "request-new" in result["successText"]
    assert "request-old" not in result["successText"]
    assert "request-newest" in result["finalText"]
    assert "Training execution request 목록 실패" not in result["finalText"]
    assert "request-saved" in result["savedText"]
    assert "request-before-save" not in result["savedText"]


def test_document_ops_execution_request_button_is_single_flight(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingRequests = [];
          const requestBodies = [];
          let listReadCount = 0;
          const createUrl = '/api/agent/document-ops/trajectories/training-execution-requests';
          const listUrl = `${createUrl}?limit=20`;
          const response = body => new Response(
            JSON.stringify(body),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
          try {
            window.fetch = (input, options = {}) => {
              const url = String(input || '');
              const method = String(options?.method || 'GET').toUpperCase();
              if (url === createUrl && method === 'POST') {
                requestBodies.push(JSON.parse(String(options?.body || '{}')));
                return new Promise(resolve => pendingRequests.push(resolve));
              }
              if (url === listUrl && method === 'GET') {
                listReadCount += 1;
                return Promise.resolve(response({
                  training_execution_requests: [],
                  total: 0,
                }));
              }
              return nativeFetch(input, options);
            };

            document.querySelector('#docops-execution-requester').value = 'browser-requester';
            const button = document.querySelector('[data-docops-action="request-execution"]');
            button.click();
            button.click();
            await new Promise(resolve => setTimeout(resolve, 25));

            const requestCount = pendingRequests.length;
            const disabledDuring = button.disabled;
            pendingRequests.forEach((resolve, index) => {
              resolve(response({ request_id: `request-single-flight-${index}` }));
            });
            while (listReadCount < requestCount) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            await new Promise(resolve => setTimeout(resolve, 0));

            return {
              requestCount,
              operationId: requestBodies[0]?.operation_id || '',
              disabledDuring,
              disabledAfter: button.disabled,
            };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert result["requestCount"] == 1
    assert result["operationId"].startswith("execution:")
    assert len(result["operationId"].split(":", 1)[1]) == 36
    assert result["disabledDuring"] is True
    assert result["disabledAfter"] is False


def _document_ops_adapter_contract(provider: str, base_model: str) -> dict[str, object]:
    return {
        "provider": provider,
        "base_model": base_model,
        "adapter_status": f"{provider}-{base_model}",
        "execution_enabled": False,
        "config_valid": True,
        "config_errors": [],
        "config_warnings": [],
        "adapter_contract": {
            "required_methods": ["prepare_job_spec"],
            "forbidden_in_stub": ["execute_training"],
        },
    }


def _document_ops_training_rehearsal(
    provider: str,
    base_model: str,
    suffix: str,
) -> dict[str, object]:
    return {
        "status": "rehearsal_ready",
        "provider": provider,
        "base_model": base_model,
        "artifact_references": {
            "dataset_freeze": {"manifest_id": f"freeze-{suffix}"},
            "pre_execution_audit": {"audit_id": f"audit-{suffix}"},
        },
        "rehearsal_steps": [
            {
                "step": f"validate-{suffix}",
                "status": "dry_run_pass",
                "side_effect": False,
                "mode": "dry_run",
            }
        ],
        "blockers": [],
    }


@pytest.mark.parametrize(
    "case",
    [
        {
            "loader": "contract",
            "container_id": "document-ops-training-adapter-contract",
            "url_prefix": "/api/agent/document-ops/trajectories/training-provider-adapter/contract?",
            "older": _document_ops_adapter_contract("openai", "old-model"),
            "newer": _document_ops_adapter_contract("gemini", "new-model"),
            "newest": _document_ops_adapter_contract("openai", "newest-model"),
            "success_markers": ["gemini", "new-model"],
            "old_marker": "old-model",
            "newest_marker": "newest-model",
            "failure_label": "Training adapter contract 실패",
            "stale_error": "stale adapter failure",
            "change_target": "provider",
        },
        {
            "loader": "rehearsal",
            "container_id": "document-ops-training-rehearsal",
            "url_prefix": "/api/agent/document-ops/trajectories/training-provider-adapter/rehearsal?",
            "older": _document_ops_training_rehearsal("openai", "old-model", "old"),
            "newer": _document_ops_training_rehearsal("gemini", "new-model", "new"),
            "newest": _document_ops_training_rehearsal("openai", "newest-model", "newest"),
            "success_markers": ["freeze-new", "audit-new"],
            "old_marker": "freeze-old",
            "newest_marker": "freeze-newest",
            "failure_label": "Training execution rehearsal 실패",
            "stale_error": "stale rehearsal failure",
            "change_target": "model",
        },
    ],
    ids=("adapter-contract", "training-rehearsal"),
)
def test_document_ops_training_provider_evidence_keeps_the_latest_planning_response(page, case):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async scenario => {
          const nativeFetch = window.fetch;
          const pending = [];
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          const loadEvidence = scenario.loader === 'contract'
            ? loadDocumentOpsTrainingAdapterContract
            : loadDocumentOpsTrainingRehearsal;
          try {
            window.fetch = (input, options) => {
              if (!String(input || '').startsWith(scenario.url_prefix)) {
                return nativeFetch(input, options);
              }
              return new Promise(resolve => pending.push(resolve));
            };

            const providerInput = document.querySelector('#docops-training-provider');
            const modelInput = document.querySelector('#docops-training-base-model');
            providerInput.value = 'openai';
            modelInput.value = 'old-model';
            const olderSuccess = loadEvidence();
            providerInput.value = 'gemini';
            modelInput.value = 'new-model';
            const newerSuccess = loadEvidence();
            while (pending.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[1](response(scenario.newer));
            await newerSuccess;
            pending[0](response(scenario.older));
            await olderSuccess;
            const container = document.querySelector(`#${scenario.container_id}`);
            const successText = container.textContent;

            providerInput.value = 'claude';
            modelInput.value = 'older-failure';
            const olderFailure = loadEvidence();
            providerInput.value = 'openai';
            modelInput.value = 'newest-model';
            const newestSuccess = loadEvidence();
            while (pending.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pending[3](response(scenario.newest));
            await newestSuccess;
            pending[2](response({ detail: scenario.stale_error }, 503));
            await olderFailure;
            const finalText = container.textContent;
            const notifications = document.querySelector('#notification-container').textContent;

            const changedInput = scenario.change_target === 'provider' ? providerInput : modelInput;
            changedInput.value = scenario.change_target === 'provider' ? 'gemini' : 'changed-model';
            changedInput.dispatchEvent(new Event(
              scenario.change_target === 'provider' ? 'change' : 'input',
              { bubbles: true },
            ));
            const staleText = container.textContent;

            return { successText, finalText, notifications, staleText };
          } finally {
            window.fetch = nativeFetch;
          }
        }""",
        case,
    )

    for marker in case["success_markers"]:
        assert marker in result["successText"]
    assert case["old_marker"] not in result["successText"]
    assert case["newest_marker"] in result["finalText"]
    assert case["failure_label"] not in result["finalText"]
    assert case["stale_error"] not in result["notifications"]
    assert "RECHECK REQUIRED" in result["staleText"]
    assert case["newest_marker"] not in result["staleText"]


def test_document_ops_audit_checklist_keeps_the_latest_planning_response(page):
    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)

    result = page.evaluate(
        """async () => {
          const nativeFetch = window.fetch;
          const pendingChecklists = [];
          const pendingAudits = [];
          const response = (body, status = 200) => new Response(
            JSON.stringify(body),
            { status, headers: { 'Content-Type': 'application/json' } },
          );
          const checklist = (requestId, freezeId) => ({
            status: 'ready_for_human_pre_execution_review',
            checklist: [{ id: 'latest_request', passed: true }],
            blockers: [],
            human_review_packet: {
              latest_request_id: requestId,
              dataset: {
                freeze_manifest_id: freezeId,
                export_filename: `${requestId}.jsonl`,
              },
              evaluation: {
                suite: 'document_ops_offline_eval',
                required_metrics: { schema_valid_rate: 1 },
              },
            },
          });
          const audits = auditId => ({
            training_pre_execution_audits: [{
              audit_id: auditId,
              audit_file: `${auditId}.json`,
              auditor: 'browser-auditor',
              request_id: auditId.replace('audit', 'request'),
              manifest_id: auditId.replace('audit', 'freeze'),
              integrity_verified: true,
              exists: true,
              training_execution_allowed: false,
              provider_api_calls_allowed: false,
              provider_job_started: false,
              external_upload_started: false,
              model_promotion_allowed: false,
            }],
          });
          try {
            window.fetch = (input, options) => {
              const url = String(input || '');
              if (url.includes('/training-audit/checklist?')) {
                return new Promise(resolve => pendingChecklists.push(resolve));
              }
              if (url === '/api/agent/document-ops/trajectories/training-audits?limit=20') {
                return new Promise(resolve => pendingAudits.push(resolve));
              }
              if (url === '/api/agent/document-ops/trajectories/training-audit/export') {
                return Promise.resolve(response({
                  audit_id: 'audit-exported',
                  audit_file: 'audit-exported.json',
                  audit_gate: {
                    auditor: 'browser-auditor',
                    requester: 'browser-requester',
                    prior_training_approver: 'browser-approver',
                  },
                  execution_guard: {
                    training_execution_allowed: false,
                    external_upload_started: false,
                    provider_job_started: false,
                    model_promotion_allowed: false,
                  },
                }));
              }
              return nativeFetch(input, options);
            };

            document.querySelector('#docops-training-provider').value = 'openai';
            document.querySelector('#docops-training-base-model').value = 'old-model';
            const olderSuccess = loadDocumentOpsTrainingAuditChecklist();
            document.querySelector('#docops-training-provider').value = 'gemini';
            document.querySelector('#docops-training-base-model').value = 'new-model';
            const newerSuccess = loadDocumentOpsTrainingAuditChecklist();
            while (pendingChecklists.length < 2 || pendingAudits.length < 2) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingChecklists[1](response(checklist('request-new', 'freeze-new')));
            pendingAudits[1](response(audits('audit-new')));
            await newerSuccess;
            pendingChecklists[0](response(checklist('request-old', 'freeze-old')));
            pendingAudits[0](response(audits('audit-old')));
            await olderSuccess;
            const successText = document.querySelector(
              '#document-ops-training-audit-checklist',
            ).textContent;

            const providerInput = document.querySelector('#docops-training-provider');
            providerInput.value = 'claude';
            providerInput.dispatchEvent(new Event('change', { bubbles: true }));
            const staleText = document.querySelector(
              '#document-ops-training-audit-checklist',
            ).textContent;
            const staleExportPresent = Boolean(
              document.querySelector('[data-docops-training-audit-export]'),
            );

            providerInput.value = 'openai';
            document.querySelector('#docops-training-base-model').value = 'stale-model';
            const olderFailure = loadDocumentOpsTrainingAuditChecklist();
            providerInput.value = 'gemini';
            document.querySelector('#docops-training-base-model').value = 'newest-model';
            const newestSuccess = loadDocumentOpsTrainingAuditChecklist();
            while (pendingChecklists.length < 4 || pendingAudits.length < 4) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            pendingChecklists[3](response(checklist('request-newest', 'freeze-newest')));
            pendingAudits[3](response(audits('audit-newest')));
            await newestSuccess;
            pendingChecklists[2](response({ detail: 'stale audit failure' }, 503));
            pendingAudits[2](response(audits('audit-stale')));
            await olderFailure;
            const finalText = document.querySelector(
              '#document-ops-training-audit-checklist',
            ).textContent;
            const notifications = document.querySelector(
              '#notification-container',
            ).textContent;

            const lateChecklist = loadDocumentOpsTrainingAuditChecklist();
            while (pendingChecklists.length < 5 || pendingAudits.length < 5) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            document.querySelector('#docops-auditor').value = 'browser-auditor';
            await exportDocumentOpsTrainingAudit();
            pendingChecklists[4](response(checklist('request-late', 'freeze-late')));
            pendingAudits[4](response(audits('audit-late')));
            await lateChecklist;
            const exportText = document.querySelector(
              '#document-ops-training-audit-checklist',
            ).textContent;

            return {
              successText,
              staleText,
              staleExportPresent,
              finalText,
              notifications,
              exportText,
            };
          } finally {
            window.fetch = nativeFetch;
          }
        }"""
    )

    assert "request-new" in result["successText"]
    assert "audit-new" in result["successText"]
    assert "request-old" not in result["successText"]
    assert "audit-old" not in result["successText"]
    assert "RECHECK REQUIRED" in result["staleText"]
    assert result["staleExportPresent"] is False
    assert "request-newest" in result["finalText"]
    assert "audit-newest" in result["finalText"]
    assert "Pre-execution audit checklist 실패" not in result["finalText"]
    assert "stale audit failure" not in result["notifications"]
    assert "audit-exported" in result["exportText"]
    assert "request-late" not in result["exportText"]


def test_document_ops_trajectory_detail_records_explicit_human_review(page, tmp_path):
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    created = page.evaluate(
        """async () => {
          const token = localStorage.getItem('dd_access_token');
          const response = await fetch('/api/agent/document-ops/run', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
              task_type: 'develop_quality_improvement',
              requirements: {
                title: '브라우저 상세 검토',
                draft: '근거와 승인 질문이 섞인 초안을 분리하고 마지막 확인 문장까지 검토합니다.',
                goal: '전체 trajectory 근거를 확인한 뒤 사람이 품질을 판정합니다.',
              },
              source_references: [{ id: 'browser-detail-source' }],
              capture_trajectory: true,
            }),
          });
          if (!response.ok) throw new Error(`trajectory create failed: ${response.status}`);
          return response.json();
        }"""
    )

    page.locator('[data-page="document-ops-page"]').click()
    page.wait_for_timeout(250)
    assert page_errors == []
    trajectory_text = page.locator("#document-ops-trajectories").inner_text()
    assert "trajectory 로드 실패" not in trajectory_text, trajectory_text
    assert page.evaluate(
        """async () => {
          const originalFetch = window.fetch;
          const originalTenantId = _currentTenantId;
          const statsBefore = document.querySelector('#document-ops-stats').textContent;
          let resolveFetch;
          try {
            window.fetch = () => new Promise(resolve => { resolveFetch = resolve; });
            _currentTenantId = 'delayed-tenant';
            const pendingStats = loadDocumentOpsStats();
            _currentTenantId = 'current-tenant';
            resolveFetch(new Response(JSON.stringify({
              total_records: 99999,
              accepted_records: 99999,
              pending_records: 0,
              export_count: 0,
            }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
            await pendingStats;
            return document.querySelector('#document-ops-stats').textContent === statsBefore;
          } finally {
            window.fetch = originalFetch;
            _currentTenantId = originalTenantId;
          }
        }"""
    )
    card_selector = f'[data-docops-trajectory-card][data-trajectory-id="{created["trajectory_id"]}"]'
    page.wait_for_selector(card_selector, timeout=10000)
    card = page.locator(card_selector)
    assert "browser-detail-source" not in card.inner_text()
    detail_url = f"**/api/agent/document-ops/trajectories/{created['trajectory_id']}"
    detail_attempts = {"count": 0}

    def handle_detail_request(route):
        detail_attempts["count"] += 1
        if detail_attempts["count"] == 1:
            route.fulfill(status=200, content_type="application/json", body="{")
        else:
            route.continue_()

    page.route(detail_url, handle_detail_request)
    card.locator("summary", has_text="검토 근거와 전체 초안").click()
    _wait_until_text_contains(page, card_selector, "상세 로드 실패", timeout_ms=10000)
    card.get_by_role("button", name="상세 다시 불러오기").click()

    detail = card.locator("[data-docops-trajectory-detail]")
    _wait_until_text_contains(
        page,
        f"{card_selector} [data-docops-trajectory-detail-content]",
        "browser-detail-source",
        timeout_ms=10000,
    )
    page.unroute(detail_url, handle_detail_request)
    assert detail_attempts["count"] == 2
    assert "browser-detail-source" in detail.inner_text()
    assert "QA gate" in detail.inner_text()
    assert "전체 초안" in detail.inner_text()
    assert created["trajectory"]["request_id"] in detail.inner_text()
    assert card.locator("[data-docops-full-draft]").inner_text() == created["draft"]

    page.fill("#docops-reviewer", "browser-reviewer")
    card.locator("[data-docops-review-notes]").fill("전체 초안과 근거 상태를 확인하고 승인합니다.")
    assert page.evaluate(
        "trajectoryId => _documentOpsReviewDrafts.get(documentOpsReviewDraftKey(trajectoryId))",
        created["trajectory_id"],
    ) == {
        "notes": "전체 초안과 근거 상태를 확인하고 승인합니다.",
        "scoreText": "",
    }
    assert page.evaluate(
        """trajectoryId => {
          const originalTenantId = _currentTenantId;
          _currentTenantId = 'other-tenant';
          const isolated = !_documentOpsReviewDrafts.has(documentOpsReviewDraftKey(trajectoryId));
          _currentTenantId = originalTenantId;
          return isolated;
        }""",
        created["trajectory_id"],
    )
    card.locator("[data-docops-review-notes]").fill("")
    assert page.evaluate(
        "trajectoryId => !_documentOpsReviewDrafts.has(documentOpsReviewDraftKey(trajectoryId))",
        created["trajectory_id"],
    )
    card.locator("[data-docops-review-notes]").fill("전체 초안과 근거 상태를 확인하고 승인합니다.")
    card.locator('[data-docops-trajectory-review="true"]').click()
    assert "pending" in card.inner_text()
    assert page.locator("#notification-container .notif-warn", has_text="승인하려면 사람 품질 점수를 입력하세요.").is_visible()

    page.evaluate("async () => loadDocumentOpsTrajectories()")
    page.wait_for_selector(card_selector, timeout=10000)
    card = page.locator(card_selector)
    card.locator("summary", has_text="검토 근거와 전체 초안").click()
    _wait_until_text_contains(
        page,
        f"{card_selector} [data-docops-trajectory-detail-content]",
        "browser-detail-source",
        timeout_ms=10000,
    )
    assert card.locator("[data-docops-review-notes]").input_value() == "전체 초안과 근거 상태를 확인하고 승인합니다."
    assert card.locator("[data-docops-review-score]").input_value() == ""

    card.locator("[data-docops-review-score]").fill("0.88")
    page.evaluate(
        """async trajectoryId => {
          const token = localStorage.getItem('dd_access_token');
          const response = await fetch(`/api/agent/document-ops/trajectories/${trajectoryId}/review`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
              accepted: false,
              expected_review_version: 0,
              reviewer: 'competing-reviewer',
              notes: '동시 검토에서 먼저 저장된 반려 의견입니다.',
              quality_score: 0.55,
            }),
          });
          if (!response.ok) throw new Error(`competing review failed: ${response.status}`);
        }""",
        created["trajectory_id"],
    )
    card.locator('[data-docops-trajectory-review="true"]').click()
    _wait_until_text_contains(
        page,
        "#notification-container",
        "다른 검토가 먼저 저장되었습니다. 최신 기록을 다시 불러왔고 입력한 메모와 점수는 보존했습니다.",
        timeout_ms=10000,
    )
    assert page.locator(
        "#notification-container .notif-warn",
        has_text="다른 검토가 먼저 저장되었습니다. 최신 기록을 다시 불러왔고 입력한 메모와 점수는 보존했습니다.",
    ).is_visible()
    _wait_until_text_contains(page, card_selector, "rejected", timeout_ms=10000)

    card = page.locator(card_selector)
    _wait_until_text_contains(
        page,
        f"{card_selector} [data-docops-current-review]",
        "competing-reviewer",
        timeout_ms=10000,
    )
    assert card.locator("[data-docops-trajectory-detail]").get_attribute("open") is not None
    assert card.locator("[data-docops-review-notes]").input_value() == "전체 초안과 근거 상태를 확인하고 승인합니다."
    assert card.locator("[data-docops-review-score]").input_value() == "0.88"
    assert page.evaluate(
        "trajectoryId => _documentOpsReviewDrafts.get(documentOpsReviewDraftKey(trajectoryId))",
        created["trajectory_id"],
    ) == {
        "notes": "전체 초안과 근거 상태를 확인하고 승인합니다.",
        "scoreText": "0.88",
    }
    card.locator('[data-docops-trajectory-review="true"]').click()
    _wait_until_text_contains(page, card_selector, "accepted", timeout_ms=10000)

    card = page.locator(card_selector)
    card.locator("summary", has_text="검토 근거와 전체 초안").click()
    _wait_until_text_contains(
        page,
        f"{card_selector} [data-docops-current-review]",
        "browser-reviewer",
        timeout_ms=10000,
    )
    review_text = card.locator("[data-docops-current-review]").inner_text()
    assert "browser-reviewer" in review_text
    assert "품질 0.88" in review_text
    assert "전체 초안과 근거 상태를 확인하고 승인합니다." in review_text
    assert "competing-reviewer" in card.locator("[data-docops-trajectory-detail]").inner_text()
    page.locator("#notification-container .notification button").evaluate_all(
        "buttons => buttons.forEach(button => button.click())"
    )
    page.screenshot(path=str(tmp_path / "document-ops-trajectory-detail-desktop.png"), full_page=True)

    reviewed = page.evaluate(
        """async trajectoryId => {
          const token = localStorage.getItem('dd_access_token');
          const response = await fetch('/api/agent/document-ops/trajectories?offset=0&limit=500', {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          });
          if (!response.ok) throw new Error(`trajectory list failed: ${response.status}`);
          const data = await response.json();
          return data.trajectories.find(item => item.trajectory_id === trajectoryId);
        }""",
        created["trajectory_id"],
    )
    assert reviewed["human_feedback"]["reviewer"] == "browser-reviewer"
    assert reviewed["human_feedback"]["quality_score"] == 0.88
    assert reviewed["human_feedback"]["notes"] == "전체 초안과 근거 상태를 확인하고 승인합니다."
    assert reviewed["human_feedback"]["review_version"] == 2
    assert reviewed["human_review_history"][0]["reviewer"] == "competing-reviewer"
    assert page.evaluate(
        "trajectoryId => !_documentOpsReviewDrafts.has(documentOpsReviewDraftKey(trajectoryId))",
        created["trajectory_id"],
    )

    page.evaluate(
        """async () => {
          document.querySelector('#ops-panel').style.display = 'block';
          document.querySelector('#audit-action-filter').value = 'document_ops.trajectory_review';
          await loadAuditLogs({ action: 'document_ops.trajectory_review' }, 0);
        }"""
    )
    audit_text = page.locator("#audit-log-table").inner_text()
    assert "document_ops.trajectory_review" in audit_text
    assert "status=accepted" in audit_text
    assert "decision=accepted" in audit_text
    assert "reviewer=browser-reviewer" in audit_text
    assert "version=2" in audit_text
    assert "expected=0" in audit_text
    assert "current=1" in audit_text
    assert "score=0.88" in audit_text
    assert "전체 초안과 근거 상태를 확인하고 승인합니다." not in audit_text
    page.evaluate("document.querySelector('#ops-panel').style.display = 'none'")

    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(tmp_path / "document-ops-trajectory-detail-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    expected_conflicts = [message for message in console_errors if "409 (Conflict)" in message]
    unexpected_console_errors = [message for message in console_errors if message not in expected_conflicts]
    assert len(expected_conflicts) == 1
    assert unexpected_console_errors == []


# ── 생성 플로우 ───────────────────────────────────────────────────────────────

def test_generate_flow_produces_results(page):
    """Select bundle → fill form → generate → results section must appear with tabs."""
    _generate_to_results(page, "E2E 테스트", "E2E 목표")
    assert page.locator("#tab-bar .tab-btn").count() > 0


def test_export_flow(page):
    """After generation, clicking export-btn must show success text."""
    _generate_to_results(page, "내보내기 테스트", "내보내기 목표")
    page.click("#export-btn")
    _wait_until_text_contains(page, "#export-btn", "완료", timeout_ms=5000)


def test_generate_from_documents_modal_flow(page, tmp_path):
    """JWT-authenticated browser session should generate docs from uploaded files."""
    sample = tmp_path / "upload-notes.txt"
    sample.write_text(
        "Project title: E2E upload flow\n"
        "Goal: Verify browser upload generation\n"
        "Constraints: Preserve auditability.\n",
        encoding="utf-8",
    )

    page.locator(".bundle-card").first.click()
    page.get_by_role("button", name="📚 문서로 초안 생성").click()
    page.wait_for_selector("#from-documents-modal", state="visible", timeout=5000)
    page.set_input_files("#from-documents-file-input", str(sample))
    page.fill("#from-documents-title", "업로드 기반 생성")
    page.fill("#from-documents-goal", "브라우저에서 업로드 후 문서를 생성한다.")
    page.click("#from-documents-submit-btn")

    page.wait_for_selector("#from-documents-modal", state="hidden", timeout=30000)
    page.wait_for_selector("#results", state="visible", timeout=30000)
    assert page.locator("#tab-bar .tab-btn").count() == 2
    assert page.locator("#tab-bar .tab-btn").nth(0).inner_text() == "adr"
    assert page.locator("#tab-bar .tab-btn").nth(1).inner_text() == "onepager"
    assert page.locator("#doc-pane").is_visible()


def test_results_flow_can_reopen_page_sketch(page):
    _generate_to_results(page, "페이지 스케치 테스트", "문서 구성을 다시 확인")
    page.wait_for_selector("#results-storyboard", state="visible", timeout=30000)
    assert page.locator("#results-storyboard-cards .slide-card").count() > 0
    assert page.locator("#results-storyboard-cards .slide-card-badge").count() >= 3
    assert page.locator("#results-storyboard-cards .slide-card-meter-fill").count() > 0
    assert page.locator("#results-storyboard-cards .slide-card-coverage-note").count() > 0
    assert "왜 이 점수인가?" in page.locator("#results-storyboard-cards .slide-card-coverage-note").first.inner_text()
    page.locator("#results-storyboard-cards .slide-card").first.click()
    page.wait_for_selector("#doc-pane .doc-section-focus", timeout=5000)
    page.click("#sketch-again-btn")
    page.wait_for_selector("#sketch-panel", state="visible", timeout=30000)
    assert page.locator("#sketch-page-cards .slide-card").count() > 0


def test_results_flow_can_recompose_as_ppt_bundle(page):
    _generate_to_results(page, "PPT 재구성 테스트", "발표 자료로 다시 구성")
    page.wait_for_selector("#results-storyboard", state="visible", timeout=30000)
    page.click("#storyboard-ppt-btn")
    page.wait_for_selector('.bundle-card.selected[data-id="presentation_kr"]', timeout=5000)
    page.wait_for_selector("#sketch-panel", state="visible", timeout=30000)
    page.wait_for_selector("#sketch-slides", state="visible", timeout=30000)
    assert page.locator("#sketch-slide-cards .slide-card").count() > 0


# ── 로컬스토리지 ──────────────────────────────────────────────────────────────

def test_localStorage_form_draft_saved(page):
    """Typing in the title field must persist the draft to localStorage."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.fill("#f-title", "저장 테스트")
    page.fill("#f-goal", "목표")
    raw = page.evaluate("localStorage.getItem('dd_form_draft')")
    assert raw is not None
    draft = json.loads(raw)
    assert draft["title"] == "저장 테스트"


def test_history_saved_after_generate(page):
    """After a successful generate, dd_history must contain the latest entry."""
    _generate_to_results(page, "이력 테스트", "이력 확인")
    raw = page.evaluate("localStorage.getItem('dd_history')")
    assert raw is not None
    history = json.loads(raw)
    assert len(history) >= 1
    assert history[0]["title"] == "이력 테스트"


# ── 스케치 플로우 ─────────────────────────────────────────────────────────────

def test_sketch_or_results_appears_on_generate(page):
    """Either sketch panel or results must appear after clicking generate."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.locator(".bundle-card").first.click()
    page.fill("#f-title", "스케치 테스트")
    page.fill("#f-goal", "스케치 목표 확인")
    page.click("#generate-btn")
    _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)


def test_results_panel_has_content_after_generate(page):
    """Results panel must contain non-empty text after generation completes."""
    _generate_to_results(page, "구성안 테스트", "섹션 구성 확인")
    content = page.locator("#results").inner_text()
    assert len(content.strip()) > 0


# ── 번역 모달 ─────────────────────────────────────────────────────────────────

def test_translate_button_visible_after_generate(page):
    """translate-btn must exist in DOM after a successful generation."""
    _generate_to_results(page, "번역 버튼 테스트", "버튼 가시성 확인")
    assert page.locator("#translate-btn").count() > 0


def test_translate_button_click_opens_modal(page):
    """Clicking translate-btn must show the translation modal."""
    _generate_to_results(page, "번역 API 테스트", "API 호출 확인")

    translate_btn = page.locator("#translate-btn")
    if translate_btn.count() == 0:
        pytest.skip("translate-btn not found")
    translate_btn.click()
    page.wait_for_selector("#translate-modal", state="visible", timeout=5000)
    assert page.locator("#translate-content").inner_text().strip()


# ── AI 검토 모달 ──────────────────────────────────────────────────────────────

def test_review_button_visible_after_generate(page):
    """review-btn must exist in DOM after a successful generation."""
    _generate_to_results(page, "검토 버튼 테스트", "버튼 가시성 확인")
    assert page.locator("#review-btn").count() > 0


def test_review_button_click_opens_modal(page):
    """Clicking review-btn must show the review modal."""
    _generate_to_results(page, "검토 API 테스트", "검토 API 호출 확인")

    review_btn = page.locator("#review-btn")
    if review_btn.count() == 0:
        pytest.skip("review-btn not found")
    review_btn.click()
    page.wait_for_selector("#review-modal", state="visible", timeout=5000)
    assert page.locator("#review-modal").inner_text().strip()


# ── 다크모드 ──────────────────────────────────────────────────────────────────

def test_dark_mode_toggle(page):
    """Clicking dark-mode-toggle must flip the 'dark' class on body."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    toggle = page.locator("#dark-mode-toggle")
    if toggle.count() == 0:
        pytest.skip("dark-mode-toggle not present")
    initial = page.evaluate("document.body.classList.contains('dark')")
    toggle.click()
    after = page.evaluate("document.body.classList.contains('dark')")
    assert after != initial


# ── 키보드 단축키 ─────────────────────────────────────────────────────────────

def test_keyboard_shortcut_ctrl_enter_triggers_generate(page):
    """Ctrl+Enter with a bundle selected and title filled must start generation."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.locator(".bundle-card").first.click()
    page.fill("#f-title", "단축키 테스트")
    page.fill("#f-goal", "Ctrl+Enter 확인")
    page.keyboard.press("Control+Enter")
    visible = _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)
    if visible == "#sketch-panel":
        page.click("#sketch-confirm-btn")
    page.wait_for_selector("#results", state="visible", timeout=30000)
    content = page.locator("#results").inner_text()
    assert len(content.strip()) > 0


def test_project_detail_shows_procurement_panel_and_doc_actions(page, live_server):
    project_id = _create_project_with_document(page)
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project }) => {
          renderProjectDetail(project, null, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": project},
    )

    page.wait_for_selector("#project-procurement-url-input", timeout=10000)
    assert page.locator("text=Public Procurement Go/No-Go Copilot").count() >= 1
    assert page.locator("text=의사결정 문서 생성").count() >= 1
    assert page.locator("text=결재 요청").count() >= 1
    assert page.locator("text=공유").count() >= 1


def test_project_detail_shows_procurement_ai_role_board(page, live_server):
    project_id = _create_project_with_document(page, name="조달 AI 역할 상황판")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    procurement_decision = {
        "opportunity": {
            "title": "AI 민원상담 플랫폼 구축",
            "issuer": "조달청",
            "budget": "3억원",
            "deadline": "2026-04-01",
            "source_id": "R26BK01398367",
        },
        "hard_filters": [],
        "checklist_items": [{"title": "파트너 확약", "status": "action_needed"}],
        "missing_data": ["파트너 확약서"],
        "soft_fit_score": 72,
        "recommendation": {
            "value": "CONDITIONAL_GO",
            "summary": "핵심 역량은 부합하지만 파트너 확약이 필요합니다.",
        },
        "notes": (
            "[override_reason ts=2026-03-29T00:00:00+00:00 actor=exec-review]\n"
            "예산 집행 우선순위 재조정으로 조건부 재검토\n"
            "[/override_reason]\n\n"
            "[override_reason ts=2026-03-31T00:00:00+00:00 actor=bd-lead]\n"
            "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행\n"
            "[/override_reason]"
        ),
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision }) => {
          renderProjectDetail(project, procurementDecision, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": project, "procurementDecision": procurement_decision},
    )

    page.wait_for_selector(".procurement-role-board", timeout=10000)
    page.wait_for_selector(".procurement-owner-strip", timeout=10000)
    page.wait_for_selector("#procurement-role-brief", timeout=10000)
    assert "최종 승인 AI" in page.locator(".procurement-owner-pill", has_text="Current").inner_text()
    assert "결재 흐름" in page.locator(".procurement-owner-pill", has_text="Next").inner_text()
    assert page.locator('[data-procurement-handoff-step="delivery_pm"].done').count() == 1
    assert page.locator('[data-procurement-handoff-step="executive"].active').count() == 1
    assert page.locator(".procurement-role-card").count() == 3
    assert page.locator('.procurement-role-card[data-procurement-role="executive"].active').count() == 1
    assert page.locator("#procurement-role-brief.executive").count() == 1
    assert page.locator(".procurement-role-brief-avatar.executive").count() == 1
    assert "최종 승인 AI 브리핑" in page.locator(".procurement-role-brief-title").inner_text()
    assert "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행" in page.locator("#project-procurement-override-reason").input_value()
    assert "최근 작성자 bd-lead" in page.locator(".procurement-override-meta").inner_text()
    assert page.locator("#project-procurement-override-submit", has_text="Override 사유 저장").count() == 1
    assert page.locator(".procurement-override-history-item").count() == 2
    assert "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행" in page.locator(".procurement-override-history-list").inner_text()
    assert "예산 집행 우선순위 재조정으로 조건부 재검토" in page.locator(".procurement-override-history-list").inner_text()
    assert page.locator('.procurement-override-history-item.active').count() == 1
    page.locator('[data-procurement-override-history-index="1"]').click()
    assert "예산 집행 우선순위 재조정으로 조건부 재검토" in page.locator("#project-procurement-override-reason").input_value()
    assert page.locator('[data-procurement-override-history-index="1"].active').count() == 1
    assert page.locator('[data-procurement-brief-action="executive"]', has_text="결재 요청").count() == 1
    assert page.locator(".procurement-role-brief-section", has_text="Recent Activity").count() == 1
    assert page.locator(".procurement-role-brief-log li", has_text="Approval").count() == 1
    assert page.locator(".procurement-role-brief-log-time").count() >= 3
    assert page.locator(".procurement-role-card", has_text="제안/영업 AI").locator("button", has_text="판단 갱신").count() == 1
    assert page.locator(".procurement-role-card", has_text="PM AI").locator("button", has_text="수행계획 생성").count() == 1
    assert page.locator(".procurement-role-card", has_text="최종 승인 AI").locator("button", has_text="결재 요청").count() == 1
    page.locator('[data-procurement-role="proposal_bd"]').click()
    page.locator('[data-procurement-brief-tab="proposal_bd"]').click()
    assert "제안/영업 AI 브리핑" in page.locator(".procurement-role-brief-title").inner_text()
    assert page.locator('[data-procurement-brief-action="proposal_bd"]', has_text="판단 갱신").count() == 1
    assert page.locator('.procurement-role-card[data-procurement-role="proposal_bd"].active').count() == 1
    assert page.locator("#procurement-role-brief.proposal_bd").count() == 1
    page.locator('[data-procurement-brief-tab="delivery_pm"]').click()
    assert "PM AI 브리핑" in page.locator(".procurement-role-brief-title").inner_text()
    assert page.locator('[data-procurement-brief-action="delivery_pm"]', has_text="수행계획 생성").count() == 1
    assert page.locator(".procurement-role-brief-avatar.delivery_pm").count() == 1
    assert page.locator("#procurement-role-brief.delivery_pm").count() == 1


def test_project_detail_shows_override_guidance_for_no_go_downstream(page, live_server):
    project_id = _create_project_with_document(page, name="조달 Override Guidance")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    project["documents"].append(
        {
            "doc_id": "proposal-downstream-doc",
            "bundle_id": "proposal_kr",
            "title": "예외 진행 제안서",
            "generated_at": "2026-03-31T08:30:00+00:00",
        }
    )
    procurement_decision = {
        "opportunity": {
            "title": "데이터 거버넌스 고도화",
            "issuer": "행정안전부",
            "budget": "4억원",
            "deadline": "2026-04-15",
            "source_id": "R26BK01999999",
        },
        "hard_filters": [{"blocking": True, "status": "fail", "code": "capability_gap"}],
        "checklist_items": [{"title": "필수 레퍼런스 보강", "status": "action_needed"}],
        "missing_data": ["파트너 확약서"],
        "soft_fit_score": 41,
        "recommendation": {
            "value": "NO_GO",
            "summary": "핵심 capability gap이 있어 현재는 NO_GO가 적절합니다.",
        },
        "notes": "",
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision }) => {
          renderProjectDetail(project, procurementDecision, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": project, "procurementDecision": procurement_decision},
    )

    page.wait_for_selector(".procurement-override-guidance.warning", timeout=10000)
    assert "NO_GO 예외 진행 사유 기록 필요" in page.locator(".procurement-override-guidance").inner_text()
    assert "최종 승인 AI가 NO_GO 예외 진행 사유를 먼저 기록" in page.locator(".procurement-owner-head").inner_text()
    assert page.locator(".procurement-role-card", has_text="최종 승인 AI").locator("button", has_text="Override 사유 기록").count() == 1
    assert page.locator('[data-procurement-brief-action="executive"]', has_text="Override 사유 기록").count() == 1
    assert "Override required" in page.locator(".procurement-role-brief-meta").inner_text()
    page.locator(".procurement-override-guidance button", has_text="사유 입력으로 이동").click()
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"


def test_project_detail_shows_decision_council_panel_and_provenance(page, live_server):
    project_id = _create_project_with_document(page, name="Decision Council UI")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    project["documents"][0]["source_decision_council_session_id"] = "council-session-ui"
    project["documents"][0]["source_decision_council_session_revision"] = 2
    project["documents"][0]["source_decision_council_direction"] = "proceed_with_conditions"
    project["documents"][0]["approval_status"] = "in_review"
    project["documents"].append(
        {
            "doc_id": "proposal-council-doc-ui",
            "request_id": "req-e2e-proposal-council",
            "bundle_id": "proposal_kr",
            "title": "입찰 제안서 초안",
            "generated_at": "2026-04-02T10:00:00+00:00",
            "approval_status": "draft",
            "source_decision_council_session_id": "council-session-ui",
            "source_decision_council_session_revision": 2,
            "source_decision_council_direction": "proceed_with_conditions",
        }
    )

    procurement_decision = {
        "opportunity": {
            "title": "공공데이터 품질 고도화 사업",
            "issuer": "행정안전부",
            "budget": "5억원",
            "deadline": "2026-05-10",
            "source_id": "R26BK05550001",
        },
        "hard_filters": [],
        "checklist_items": [{"title": "컨소시엄 파트너 확약", "status": "action_needed"}],
        "missing_data": ["최근 3년 공공 레퍼런스 확인서"],
        "soft_fit_score": 76,
        "recommendation": {
            "value": "CONDITIONAL_GO",
            "summary": "핵심 역량은 부합하지만 증빙 보완이 선행되어야 합니다.",
        },
        "notes": "",
    }
    council_session = {
        "session_id": "council-session-ui",
        "session_key": f"{project_id}:public_procurement:bid_decision_kr",
        "session_revision": 2,
        "tenant_id": "system",
        "project_id": project_id,
        "use_case": "public_procurement",
        "target_bundle_type": "bid_decision_kr",
        "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
        "goal": "입찰 참여 여부와 조건, 리스크를 경영진이 빠르게 검토할 수 있게 정리한다.",
        "context": "전략 고객 유지 관점에서 파트너 협의가 병행 중이다.",
        "constraints": "대외 확정 표현 없이 조건부 진행 근거만 정리한다.",
        "source_procurement_decision_id": "decision-ui-1",
        "source_snapshot_ids": ["snap-ui-1"],
        "created_at": "2026-04-02T09:00:00+00:00",
        "updated_at": "2026-04-02T09:00:00+00:00",
        "role_opinions": [
            {
                "role": "Requirement Analyst",
                "stance": "support",
                "summary": "요구사항과 당사 capability는 대체로 부합합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Risk Reviewer",
                "stance": "caution",
                "summary": "증빙 미확보 상태를 확정 사실처럼 쓰면 안 됩니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Domain Strategist",
                "stance": "support",
                "summary": "조건만 닫히면 전략적으로 진행 가치가 있습니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Compliance Reviewer",
                "stance": "caution",
                "summary": "컨소시엄 및 실적 증빙은 별도 gate로 남겨야 합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Drafting Lead",
                "stance": "support",
                "summary": "조건, 리스크, 열린 질문을 분리해 decision memo로 정리해야 합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
        ],
        "disagreements": [
            "전략 가치는 높지만 증빙 미확보를 확정 사실처럼 다루면 안 된다는 이견이 남아 있습니다.",
        ],
        "risks": [
            "컨소시엄 파트너 확약이 아직 확정되지 않았습니다.",
            "최근 3년 공공 레퍼런스 증빙이 필요합니다.",
        ],
        "consensus": {
            "alignment": "mixed",
            "recommended_direction": "proceed_with_conditions",
            "summary": "Council은 조건부 진행을 권고하며, 보완 조건과 리스크를 분리해 전달해야 한다고 봅니다.",
            "strategy_options": [
                "조건부 Go로 정리하고 보완 조건을 별도 gate로 제시",
            ],
            "disagreements": [
                "전략 가치와 증빙 리스크 사이의 균형을 어떻게 표현할지 의견이 갈립니다.",
            ],
            "top_risks": [
                "파트너 확약 누락",
            ],
            "conditions": [
                "컨소시엄 파트너 확약을 문서화해야 합니다.",
            ],
            "open_questions": [
                "최근 3년 공공 레퍼런스 확인서는 확보됐는가?",
            ],
        },
        "handoff": {
            "target_bundle_type": "bid_decision_kr",
            "recommended_direction": "proceed_with_conditions",
            "drafting_brief": "조건부 진행 방향과 보완 gate를 분리한 bid_decision_kr를 작성합니다.",
            "must_include": [
                "최종 권고 방향: proceed_with_conditions",
            ],
            "must_address": [
                "컨소시엄 파트너 확약",
                "최근 3년 공공 레퍼런스 증빙",
            ],
            "must_not_claim": [
                "파트너 확약이 완료됐다고 단정하지 말 것",
            ],
            "open_questions": [
                "최근 3년 공공 레퍼런스 확인서는 확보됐는가?",
            ],
            "source_procurement_decision_id": "decision-ui-1",
        },
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision, councilSession }) => {
          renderProjectDetail(project, procurementDecision, {
            procurementEnabled: true,
            decisionCouncilSession: councilSession,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {
            "project": project,
            "procurementDecision": procurement_decision,
            "councilSession": council_session,
        },
    )

    page.wait_for_selector(".decision-council-panel", timeout=10000)
    assert page.locator(".decision-council-panel", has_text="Decision Council v1").count() == 1
    assert "입찰 참여 여부와 조건, 리스크" in page.locator("#project-decision-council-goal").input_value()
    assert page.locator('[data-decision-council-session="council-session-ui"]').count() == 1
    assert page.locator(".decision-council-chip.warning", has_text="조건부 진행").count() >= 1
    assert page.locator(".decision-council-role-card").count() == 5
    assert page.locator(".decision-council-linked-doc", has_text="현재 council handoff").count() == 2
    assert page.locator(".decision-council-linked-doc", has_text="proposal_kr").count() == 1
    assert page.locator(".doc-item .tag", has_text="Council v1 r2").count() == 2
    assert page.locator(".doc-item .tag", has_text="조건부 진행").count() == 2
    assert page.locator('[data-decision-council-doc-status="current"]', has_text="현재 council 기준").count() == 2
    assert page.locator('[data-decision-council-doc-followup]').count() == 0


def test_project_detail_marks_stale_decision_council_and_blocks_generate(page, live_server):
    project_id = _create_project_with_document(page, name="Decision Council Stale UI")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    project["documents"][0]["source_decision_council_session_id"] = "council-session-stale-ui"
    project["documents"][0]["source_decision_council_session_revision"] = 1
    project["documents"][0]["source_decision_council_direction"] = "proceed"
    project["documents"].append(
        {
            "doc_id": "proposal-council-doc-stale-ui",
            "request_id": "req-e2e-stale-proposal-council",
            "bundle_id": "proposal_kr",
            "title": "이전 council 기준 제안서",
            "generated_at": "2026-04-01T09:30:00+00:00",
            "approval_status": "draft",
            "source_decision_council_session_id": "council-session-stale-ui",
            "source_decision_council_session_revision": 1,
            "source_decision_council_direction": "proceed",
        }
    )
    procurement_decision = {
        "opportunity": {
            "title": "공공 AI 분석 사업",
            "issuer": "조달청",
            "budget": "6억원",
            "deadline": "2026-06-15",
            "source_id": "R26BK07770003",
        },
        "hard_filters": [],
        "checklist_items": [{"title": "레퍼런스 증빙 최신화", "status": "action_needed"}],
        "missing_data": ["최신 공공 구축 실적 확인"],
        "soft_fit_score": 61,
        "recommendation": {
            "value": "NO_GO",
            "summary": "현재 기준으로는 즉시 진행보다 재검토가 필요합니다.",
        },
        "notes": "",
    }
    council_session = {
        "session_id": "council-session-stale-ui",
        "session_key": f"{project_id}:public_procurement:bid_decision_kr",
        "session_revision": 1,
        "tenant_id": "system",
        "project_id": project_id,
        "use_case": "public_procurement",
        "target_bundle_type": "bid_decision_kr",
        "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
        "goal": "이전 recommendation 기준의 전략 방향을 정리한다.",
        "context": "",
        "constraints": "",
        "source_procurement_decision_id": "decision-stale-ui",
        "source_procurement_updated_at": "2026-04-01T09:00:00+00:00",
        "source_procurement_recommendation_value": "GO",
        "source_procurement_missing_data_count": 0,
        "source_procurement_action_needed_count": 0,
        "source_procurement_blocking_hard_filter_count": 0,
        "source_snapshot_ids": ["snap-stale-ui"],
        "created_at": "2026-04-01T09:00:00+00:00",
        "updated_at": "2026-04-01T09:00:00+00:00",
        "current_procurement_binding_status": "stale",
        "current_procurement_binding_reason_code": "procurement_updated",
        "current_procurement_binding_summary": "현재 procurement recommendation 또는 checklist가 council 실행 이후 갱신되어 다시 실행해야 합니다.",
        "current_procurement_updated_at": "2026-04-03T09:00:00+00:00",
        "current_procurement_recommendation_value": "NO_GO",
        "current_procurement_missing_data_count": 1,
        "current_procurement_action_needed_count": 1,
        "current_procurement_blocking_hard_filter_count": 0,
        "role_opinions": [
            {
                "role": "Requirement Analyst",
                "stance": "support",
                "summary": "이전 상태 기준에서는 진행 근거가 충분했습니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Risk Reviewer",
                "stance": "caution",
                "summary": "최신 증빙 기준으로는 재검토가 필요합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Domain Strategist",
                "stance": "support",
                "summary": "전략 가치는 있으나 최신 recommendation을 따라야 합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Compliance Reviewer",
                "stance": "caution",
                "summary": "현재 checklist와 맞지 않는 표현은 stale입니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Drafting Lead",
                "stance": "caution",
                "summary": "다시 실행 전에는 최신 bid_decision_kr handoff로 쓰면 안 됩니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
        ],
        "disagreements": ["현재 checklist와 이전 council 방향이 어긋납니다."],
        "risks": ["최신 실적 증빙이 미확인입니다."],
        "consensus": {
            "alignment": "mixed",
            "recommended_direction": "proceed",
            "summary": "이전 실행 시점에는 진행 방향으로 정리됐습니다.",
            "strategy_options": ["이전 판단 기준 유지"],
            "disagreements": [],
            "top_risks": ["최신 실적 증빙 미확인"],
            "conditions": [],
            "open_questions": [],
        },
        "handoff": {
            "target_bundle_type": "bid_decision_kr",
            "recommended_direction": "proceed",
            "drafting_brief": "이전 recommendation 기준의 bid_decision_kr 작성",
            "must_include": [],
            "must_address": ["최신 실적 증빙"],
            "must_not_claim": [],
            "open_questions": [],
            "source_procurement_decision_id": "decision-stale-ui",
        },
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision, councilSession }) => {
          renderProjectDetail(project, procurementDecision, {
            procurementEnabled: true,
            decisionCouncilSession: councilSession,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {
            "project": project,
            "procurementDecision": procurement_decision,
            "councilSession": council_session,
        },
    )

    page.wait_for_selector('[data-decision-council-binding="stale"]', timeout=10000)
    assert page.locator('[data-decision-council-binding="stale"]', has_text="현재 procurement 기준과 council handoff가 어긋났습니다.").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="council 기준 2026-04-01 → 현재 procurement 2026-04-03").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="당시 권고안 GO → 현재 NO_GO").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="현재 action needed 1건").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="현재 missing data 1건").count() == 1
    assert page.locator(".decision-council-chip.danger", has_text="Stale handoff").count() >= 1
    assert page.locator("#project-decision-council-run-submit", has_text="Decision Council 다시 실행").count() == 1
    assert page.locator('[data-decision-council-generate]').is_disabled()
    assert page.locator('[data-decision-council-generate-proposal]').is_disabled()
    assert page.locator(".decision-council-linked-doc", has_text="이전 council 기준").count() == 2
    assert page.locator(".decision-council-linked-doc", has_text="proposal_kr 문서는 이 이전 council 기준").count() == 1
    assert page.locator('[data-decision-council-doc-status="stale_procurement"]', has_text="현재 procurement 대비 이전 council 기준").count() == 2
    stale_doc = page.locator(".doc-item").filter(
        has=page.locator('[data-decision-council-doc-status="stale_procurement"]')
    ).first
    stale_doc.locator('[data-decision-council-doc-followup="stale_procurement"]').click()
    assert page.locator("#project-decision-council-run-submit").evaluate("el => document.activeElement === el")
    page.evaluate(
        """() => {
          window.__lastCouncilDocGuard = '';
          window.confirm = (message) => {
            window.__lastCouncilDocGuard = message;
            return false;
          };
        }"""
    )
    stale_doc.locator("button", has_text="결재 요청").click()
    page.wait_for_timeout(200)
    assert "현재 procurement 대비 이전 council 기준" in page.evaluate("window.__lastCouncilDocGuard")
    assert page.locator(".approval-modal-overlay").count() == 0
    page.evaluate("() => { window.confirm = () => true; }")
    stale_doc.locator("button", has_text="결재 요청").click()
    page.wait_for_selector(".approval-modal-overlay", timeout=5000)
    assert page.locator('[data-approval-decision-council-warning="stale_procurement"]', has_text="현재 procurement 대비 이전 council 기준").count() == 1
    assert page.locator('[data-approval-decision-council-followup="stale_procurement"]', has_text="Council 다시 실행").count() == 1
    page.locator('[data-approval-decision-council-followup="stale_procurement"]').click()
    page.wait_for_selector(".approval-modal-overlay", state="hidden", timeout=5000)
    assert page.locator("#project-decision-council-run-submit").evaluate("el => document.activeElement === el")
    page.evaluate("() => { window.confirm = () => true; }")
    stale_doc.locator("button", has_text="결재 요청").click()
    page.wait_for_selector(".approval-modal-overlay", timeout=5000)
    page.locator(".approval-modal-overlay button", has_text="취소").click()
    page.wait_for_selector(".approval-modal-overlay", state="hidden", timeout=5000)
    stale_doc.locator("button", has_text="공유").click()
    page.wait_for_selector("#share-url-input", timeout=5000)
    # This fixture mutates only the browser-side project object. The share
    # response must use the unchanged server-side project document as authority.
    assert page.locator('[data-share-decision-council-warning="stale_procurement"]').count() == 0
    shared_path = page.locator("#share-url-input").input_value()
    page.goto(f"{live_server['base_url']}{shared_path}")
    page.wait_for_selector(".share-header", timeout=5000)
    assert page.locator('[data-shared-decision-council-warning="stale_procurement"]').count() == 0


def test_project_detail_decision_council_run_posts_goal_and_refreshes(page, live_server):
    project_id = _create_project_with_document(page, name="Decision Council Run")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    procurement_decision = {
        "opportunity": {
            "title": "AI 민원 분석 사업",
            "issuer": "조달청",
            "budget": "4억원",
            "deadline": "2026-06-01",
            "source_id": "R26BK06660002",
        },
        "hard_filters": [],
        "checklist_items": [],
        "missing_data": [],
        "soft_fit_score": 84,
        "recommendation": {
            "value": "GO",
            "summary": "즉시 진행 가능한 상태입니다.",
        },
        "notes": "",
    }

    captured: list[dict] = []

    def handle_council_run(route):
        captured.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "session_id": "council-run-ui",
                    "session_key": f"{project_id}:public_procurement:bid_decision_kr",
                    "session_revision": 1,
                    "tenant_id": "system",
                    "project_id": project_id,
                    "use_case": "public_procurement",
                    "target_bundle_type": "bid_decision_kr",
                    "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
                    "goal": captured[0]["goal"],
                    "context": captured[0].get("context", ""),
                    "constraints": captured[0].get("constraints", ""),
                    "source_procurement_decision_id": "decision-run-ui",
                    "source_snapshot_ids": [],
                    "created_at": "2026-04-02T10:00:00+00:00",
                    "updated_at": "2026-04-02T10:00:00+00:00",
                    "operation": "created",
                    "role_opinions": [],
                    "disagreements": [],
                    "risks": [],
                    "consensus": {
                        "alignment": "aligned",
                        "recommended_direction": "proceed",
                        "summary": "즉시 진행 방향으로 합의했습니다.",
                        "strategy_options": [],
                        "disagreements": [],
                        "top_risks": [],
                        "conditions": [],
                        "open_questions": [],
                    },
                    "handoff": {
                        "target_bundle_type": "bid_decision_kr",
                        "recommended_direction": "proceed",
                        "drafting_brief": "즉시 진행 판단을 정리합니다.",
                        "must_include": [],
                        "must_address": [],
                        "must_not_claim": [],
                        "open_questions": [],
                        "source_procurement_decision_id": "decision-run-ui",
                    },
                }
            ),
        )

    page.route(f"**/projects/{project_id}/decision-council/run", handle_council_run)
    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision }) => {
          renderProjectDetail(project, procurementDecision, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
          window.__decisionCouncilReloaded = '';
          window.loadProjectDetail = async (projectId) => {
            window.__decisionCouncilReloaded = projectId;
          };
        }""",
        {"project": project, "procurementDecision": procurement_decision},
    )

    page.fill("#project-decision-council-goal", "입찰 진행 방향을 경영진 보고용으로 정리한다.")
    page.fill("#project-decision-council-context", "전략 고객 유지 맥락이 있다.")
    page.fill("#project-decision-council-constraints", "대외 확정 표현은 금지한다.")
    page.locator("#project-decision-council-run-submit").click()

    page.wait_for_selector("#project-decision-council-status.success", timeout=10000)
    assert "자동 반영" in page.locator("#project-decision-council-status").inner_text()
    assert captured[0]["goal"] == "입찰 진행 방향을 경영진 보고용으로 정리한다."
    assert captured[0]["context"] == "전략 고객 유지 맥락이 있다."
    assert captured[0]["constraints"] == "대외 확정 표현은 금지한다."
    assert page.evaluate("window.__decisionCouncilReloaded") == project_id


def test_project_detail_blocks_no_go_downstream_until_override_reason(page, live_server):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementChecklistItem,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="조달 Downstream Guard")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-001",
                title="공공 데이터 운영 고도화",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            checklist_items=[
                ProcurementChecklistItem(
                    category="staffing",
                    title="전담 PM 확보",
                    status="action_needed",
                    severity="high",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="핵심 운영 실적 부족으로 예외 승인 없이는 downstream 진행 불가",
            ),
        )
    )
    page.evaluate("switchPage('project-page')")
    page.evaluate("(projectId) => loadProjectDetail(projectId)", project_id)

    page.wait_for_selector(".procurement-override-guidance.warning", timeout=10000)
    page.wait_for_selector('[data-procurement-bundle="proposal_kr"]:not([disabled])', timeout=10000)
    page.locator('[data-procurement-bundle="proposal_kr"]').click()

    _wait_until_text_contains(
        page,
        "#project-procurement-status",
        "override 사유를 먼저 저장하세요",
        timeout_ms=10000,
    )
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"


def test_locations_page_shows_procurement_quality_summary(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="거점 조달 품질 요약")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-001",
                title="거점 조달 품질 요약",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 사유 없이는 downstream 진행 불가",
            ),
        )
    )
    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="procurement.downstream_blocked",
            resource_type="procurement",
            resource_id=project_id,
            resource_name="",
            result="failure",
            detail={
                "project_id": project_id,
                "bundle_type": "proposal_kr",
                "error_code": "procurement_override_reason_required",
                "recommendation": "NO_GO",
            },
            session_id="sess-e2e-procurement-summary",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Blocked downstream 시도",
        timeout_ms=10000,
    )
    assert "Blocked downstream 시도" in modal.inner_text()
    assert "최근 override reason 미기입으로 차단된 downstream 시도는" in modal.inner_text()
    assert "Override 필요로 downstream 차단" in modal.inner_text()
    assert "procurement_override_reason_required" in modal.inner_text()


def test_locations_page_stale_share_risk_strip_opens_review_preset(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore
    from app.storage.project_store import ProjectStore
    from app.storage.share_store import ShareStore
    from app.storage.tenant_store import TenantStore

    project_id = _create_project_with_document(page, name="거점 stale share 위험 카드")
    TenantStore(Path(os.environ["DATA_DIR"])).create_tenant("t-clean-location", "정상 거점")
    project_store = ProjectStore(base_dir=os.environ["DATA_DIR"])
    project = project_store.get(project_id, tenant_id="system")
    assert project is not None
    assert project.documents
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-STALE-001",
                title="거점 stale share 위험 카드",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="stale public share 노출 확인 필요",
            ),
        )
    )
    share_store = ShareStore("system")
    share = share_store.create(
        request_id="req-e2e-loc-stale-share",
        title="거점 stale share",
        created_by="e2e_admin",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
    )
    share_store.increment_access(share.share_id)
    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="share.create",
            resource_type="share",
            resource_id=share.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project_id,
                "share_project_document_id": project.documents[0].doc_id,
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            },
            session_id="sess-e2e-loc-stale-share",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.evaluate(
        """() => {
          window.__openedSharedUrl = null;
          window.__copiedSharedUrl = null;
          window.confirm = () => true;
          window.open = (url) => {
            window.__openedSharedUrl = url;
            return null;
          };
          Object.defineProperty(window.navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: (text) => {
                window.__copiedSharedUrl = text;
                return Promise.resolve();
              },
            },
          });
        }"""
    )
    tenant_order = page.locator('[data-location-procurement]').evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement'))"
    )
    assert tenant_order.index("system") < tenant_order.index("t-clean-location")
    card_selector = '.location-card:has([data-location-procurement="system"])'
    card = page.locator(".location-card").filter(
        has=page.locator('[data-location-procurement="system"]')
    ).first
    _wait_until_text_contains(
        page,
        card_selector,
        "stale public 노출 1개가 남아 있습니다.",
        timeout_ms=10000,
    )
    card_text = card.inner_text()
    assert "공개 중 1개" in card_text
    assert "최근 public 열람 1개" in card_text
    assert "우선 확인: 입찰 의사결정 문서" in card_text
    assert "현재 procurement 대비 이전 council 기준" in card_text
    assert "활성 공유 링크 · 조회 1회" in card_text
    assert "최근 위험 관측: e2e_admin" in card_text
    assert "영향 링크 1개" in card_text
    card.locator('button:has-text("공유 링크 복사")').click()
    copied_url = page.evaluate("() => window.__copiedSharedUrl")
    assert copied_url is not None
    assert copied_url.endswith(f"/shared/{share.share_id}")
    card.locator('button:has-text("외부 공유 review 링크")').click()
    tenant_review_url = page.evaluate("() => window.__copiedSharedUrl")
    assert tenant_review_url is not None
    assert "location_procurement_tenant=system" in tenant_review_url
    assert "location_procurement_activity_actions=share.create%2Cshare.view" in tenant_review_url
    assert "location_procurement_focus_project" not in tenant_review_url
    card.locator('button:has-text("위험 문서 review 링크")').click()
    focused_review_url = page.evaluate("() => window.__copiedSharedUrl")
    assert focused_review_url is not None
    assert "location_procurement_tenant=system" in focused_review_url
    assert f"location_procurement_focus_project={project_id}" in focused_review_url
    assert "location_procurement_activity_actions=share.create%2Cshare.view" in focused_review_url
    card.locator('button:has-text("공유 링크 열기")').click()
    assert page.evaluate("() => window.__openedSharedUrl") == f"/shared/{share.share_id}"
    card.locator('[data-location-procurement-stale-share-focus-review="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"].active', timeout=5000)
    page.wait_for_selector(f'[data-location-procurement-focus="{project_id}"]', timeout=5000)
    focused_text = page.locator(f'[data-location-procurement-focus="{project_id}"]').inner_text()
    assert "외부 공유 위험" in focused_text
    assert "활성 공유 링크" in focused_text
    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    page.locator('[data-location-procurement-stale-share-review="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-activity-filter="share.create"].active', timeout=5000)
    modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "외부 공유 재확인 queue" in modal_text
    assert "현재 procurement 대비 이전 council 기준" in modal_text
    assert "활성 공유 링크" in modal_text
    page.evaluate("closeLocationProcurementSummary()")
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    card = page.locator(".location-card").filter(
        has=page.locator('[data-location-procurement="system"]')
    ).first
    card.locator('button:has-text("공유 링크 비활성화")').click()
    page.wait_for_function(
        """() => {
          const trigger = document.querySelector('[data-location-procurement="system"]');
          if (!trigger) return false;
          const card = trigger.closest('.location-card');
          return Boolean(card) && !card.innerText.includes('stale public 노출');
        }""",
        timeout=10000,
    )
    updated_card_text = page.locator(".location-card").filter(
        has=page.locator('[data-location-procurement="system"]')
    ).first.inner_text()
    assert "stale public 노출" not in updated_card_text
    shared_status = page.evaluate(
        """async (shareId) => {
          const res = await fetch(`/shared/${shareId}`);
          return res.status;
        }""",
        share.share_id,
    )
    assert shared_status == 404


def test_location_procurement_summary_opens_project_override_flow(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="거점 모달 점프 테스트")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-002",
                title="거점 모달 점프 테스트",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 사유 기록이 필요한 상태",
            ),
        )
    )

    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="procurement.downstream_blocked",
            resource_type="procurement",
            resource_id=project_id,
            resource_name="",
            result="failure",
            detail={
                "project_id": project_id,
                "bundle_type": "proposal_kr",
                "error_code": "procurement_override_reason_required",
                "recommendation": "NO_GO",
            },
            session_id="sess-e2e-procurement-jump",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.evaluate(
        """() => {
          window.__copiedProjectProcurementLink = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => { window.__copiedProjectProcurementLink = text; },
            },
          });
        }"""
    )
    page.locator(
        f'#location-procurement-modal .location-procurement-event [data-location-procurement-copy-project-link="{project_id}"]'
    ).first.click()
    copied_from_summary = page.evaluate("window.__copiedProjectProcurementLink")
    assert copied_from_summary is not None
    assert f"project_id={project_id}" in copied_from_summary
    assert "project_procurement_context=" in copied_from_summary
    assert "project_procurement_return_tenant=system" in copied_from_summary
    summary_url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert summary_url_state["location_procurement_tenant"] == "system"
    assert "project_id" not in summary_url_state
    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    page.locator('[data-location-procurement="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Remediation 링크 공유",
        timeout_ms=10000,
    )
    modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "tenant summary" in modal_text
    assert "blocked remediation" in modal_text
    assert "Remediation handoff queue" in modal_text
    assert "공유됨, 아직 미열람" in modal_text
    page.locator('[data-location-procurement-preset="handoff_review"]').click()
    page.wait_for_selector('[data-location-procurement-preset="handoff_review"].active', timeout=5000)
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.remediation_link_copied"].active',
        timeout=5000,
    )
    handoff_url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert handoff_url_state["location_procurement_activity_actions"] == (
        "procurement.remediation_link_copied,procurement.remediation_link_opened"
    )
    page.locator(
        f'#location-procurement-modal .location-procurement-candidate[data-location-procurement-project="{project_id}"] [data-location-procurement-open="{project_id}"]'
    ).first.click()

    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.wait_for_selector("#project-procurement-override-reason", timeout=10000)
    page.wait_for_selector(
        '[data-project-procurement-remediation="blocked_event"]',
        timeout=10000,
    )
    assert page.locator("#project-detail").inner_text().find("거점 모달 점프 테스트") >= 0
    remediation = page.locator("#project-procurement-remediation-strip")
    assert "Blocked downstream remediation 필요" in remediation.inner_text()
    assert "거점 조달 품질 요약" in remediation.inner_text()
    assert "proposal_kr" not in remediation.inner_text()
    assert "제안서 생성 시도가 override 사유 미기입으로 차단되었습니다." in remediation.inner_text()
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"
    url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert url_state["project_id"] == project_id
    assert url_state["project_procurement_return_tenant"] == "system"
    assert "project_procurement_context" in url_state
    assert "location_procurement_tenant" not in url_state
    page.evaluate("window.__copiedProjectProcurementLink = null;")
    page.locator(f'[data-project-procurement-copy-link="{project_id}"]').click()
    copied_project_link = page.evaluate("window.__copiedProjectProcurementLink")
    assert copied_project_link is not None
    assert f"project_id={project_id}" in copied_project_link
    assert "project_procurement_context=" in copied_project_link
    assert "project_procurement_return_tenant=system" in copied_project_link
    page.evaluate(
        """() => {
          _currentProjectDetail = null;
          _projectProcurementRemediationContext = null;
          _projectProcurementSummaryReturnContext = null;
          const detailEl = document.getElementById('project-detail');
          const listEl = document.getElementById('project-list');
          if (detailEl) detailEl.style.display = 'none';
          if (listEl) listEl.style.display = 'block';
          switchPage('locations-page');
        }"""
    )
    assert page.evaluate("restoreProjectProcurementDetailFromUrl()") is True
    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.wait_for_selector(
        '[data-project-procurement-remediation="blocked_event"]',
        timeout=10000,
    )
    page.wait_for_selector(
        '[data-project-procurement-return="system"]',
        timeout=10000,
    )
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"
    page.evaluate(
        """() => {
          _locationProcurementCandidateOrder = 'stale_unresolved';
          _locationProcurementCandidateScope = 'resolved_only';
          _locationProcurementCandidateStatusFilters = ['resolved'];
          _locationProcurementActivityActionFilters = ['procurement.downstream_resolved'];
        }"""
    )
    page.locator('[data-project-procurement-return="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Blocked downstream 시도",
        timeout_ms=10000,
    )
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Remediation 링크 열람",
        timeout_ms=10000,
    )
    returned_url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert returned_url_state["location_procurement_tenant"] == "system"
    assert returned_url_state["location_procurement_focus_project"] == project_id
    assert "project_id" not in returned_url_state
    assert "location_procurement_candidate_scope" not in returned_url_state
    assert "location_procurement_candidate_statuses" not in returned_url_state
    returned_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "shared link restore" in returned_modal_text
    assert "열람 기준" in returned_modal_text
    assert "열람됨, 미해소" in returned_modal_text
    page.locator(
        f'#location-procurement-modal .location-procurement-event [data-location-procurement-open="{project_id}"]'
    ).first.click()
    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.locator(f'[data-procurement-remediation-dismiss="{project_id}"]').click()
    assert page.locator("#project-procurement-remediation-strip").count() == 0


def test_location_procurement_summary_blocked_event_retries_after_override_reason(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="거점 모달 재시도 테스트")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])

    def seed_resolved_candidate(name: str, source_id: str) -> str:
        candidate_project_id = _create_project_with_document(page, name=name)
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=candidate_project_id,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="reference_gap",
                        label="유사 레퍼런스",
                        status="fail",
                        blocking=True,
                        reason="유사 실적 부족",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="기존 override 이후 resolved 상태",
                ),
            )
        )
        page.evaluate(
            """async ({ projectId }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const added = await fetch(`/projects/${projectId}/documents`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  request_id: `req-${projectId}-proposal`,
                  bundle_id: 'proposal_kr',
                  title: '기존 예외 진행 제안서',
                  docs: [{ doc_type: 'proposal', markdown: '# 기존 제안서' }],
                }),
              });
              if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
            }""",
            {"projectId": candidate_project_id},
        )
        audit_store = AuditStore("system")
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.downstream_blocked",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="failure",
                detail={
                    "project_id": candidate_project_id,
                    "bundle_type": "proposal_kr",
                    "error_code": "procurement_override_reason_required",
                    "recommendation": "NO_GO",
                },
                session_id=f"sess-{candidate_project_id}-blocked",
            )
        )
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.downstream_resolved",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="success",
                detail={
                    "project_id": candidate_project_id,
                    "bundle_type": "proposal_kr",
                    "recommendation": "NO_GO",
                },
                session_id=f"sess-{candidate_project_id}-resolved",
            )
        )
        return candidate_project_id

    seed_resolved_candidate("가-해소 후보 1", "R26-E2E-LOC-101")
    seed_resolved_candidate("가-해소 후보 2", "R26-E2E-LOC-102")
    seed_resolved_candidate("가-해소 후보 3", "R26-E2E-LOC-103")
    seed_resolved_candidate("가-해소 후보 4", "R26-E2E-LOC-104")

    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-003",
                title="거점 모달 재시도 테스트",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 사유 저장 후 retry가 필요한 상태",
            ),
        )
    )
    page.evaluate(
        """async ({ projectId }) => {
          const token = localStorage.getItem('dd_access_token');
          const headers = {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          };
          const added = await fetch(`/projects/${projectId}/documents`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              request_id: 'req-e2e-procurement-rfp-analysis',
              bundle_id: 'rfp_analysis_kr',
              title: '선행 RFP 분석',
              docs: [{ doc_type: 'rfp_analysis', markdown: '# 선행 분석' }],
            }),
          });
          if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
        }""",
        {"projectId": project_id},
    )

    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="procurement.downstream_blocked",
            resource_type="procurement",
            resource_id=project_id,
            resource_name="",
            result="failure",
            detail={
                "project_id": project_id,
                "bundle_type": "proposal_kr",
                "error_code": "procurement_override_reason_required",
                "recommendation": "NO_GO",
            },
            session_id="sess-e2e-procurement-retry",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.evaluate(
        """() => {
          window.__copiedProjectProcurementLink = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => { window.__copiedProjectProcurementLink = text; },
            },
          });
        }"""
    )
    page.locator(
        f'#location-procurement-modal .location-procurement-event [data-location-procurement-copy-project-link="{project_id}"]'
    ).first.click()
    copied_link = page.evaluate("window.__copiedProjectProcurementLink")
    assert copied_link is not None
    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    page.evaluate(
        """(copiedLink) => {
          const url = new URL(copiedLink, window.location.origin);
          history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
          _currentProjectDetail = null;
          _projectProcurementRemediationContext = null;
          _projectProcurementSummaryReturnContext = null;
          const detailEl = document.getElementById('project-detail');
          const listEl = document.getElementById('project-list');
          if (detailEl) detailEl.style.display = 'none';
          if (listEl) listEl.style.display = 'block';
          switchPage('locations-page');
        }""",
        copied_link,
    )
    assert page.evaluate("restoreProjectProcurementDetailFromUrl()") is True
    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.evaluate("focusProcurementOverrideReason()")
    page.wait_for_selector("#project-procurement-override-reason", state="visible", timeout=10000)
    assert page.locator(".doc-item").count() == 2

    page.fill(
        "#project-procurement-override-reason",
        "전략 고객 유지 목적상 proposal 초안까지는 예외 검토를 진행합니다.",
    )
    page.click("#project-procurement-override-submit")

    _wait_until_text_contains(
        page,
        "#project-procurement-status",
        "같은 화면에서 다시 시도할 수 있습니다.",
        timeout_ms=10000,
    )
    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    page.locator('[data-location-procurement-scope="unresolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    assert "Retry 대기" in modal.inner_text()
    assert "운영 기준" in modal.inner_text()
    assert "가장 오래 미해소 follow-up" in modal.inner_text()
    assert "미해소 follow-up" in modal.inner_text()
    assert "현재 미해소 queue 기준 candidate는 1개" in modal.inner_text()
    assert "최근 blocked downstream 이후 override 사유는 저장되었고, 아직 retry 완료는 확인되지 않았습니다." in modal.inner_text()
    assert "가-해소 후보" not in modal.inner_text()
    oldest_button = page.get_by_role("button", name="가장 오래 미해소 열기")
    assert oldest_button.is_visible()
    oldest_button.click()
    page.wait_for_selector("#project-procurement-remediation-strip", timeout=10000)
    remediation = page.locator("#project-procurement-remediation-strip")
    assert "retry 완료가 확인되지 않았습니다." in remediation.inner_text()
    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    candidate_button = page.locator(
        f'#location-procurement-modal .location-procurement-candidate [data-location-procurement-open="{project_id}"]'
    ).first
    assert "retry" in candidate_button.inner_text().lower()
    candidate_button.click()

    page.wait_for_selector("#project-procurement-remediation-strip", timeout=10000)
    remediation = page.locator("#project-procurement-remediation-strip")
    remediation_text = remediation.inner_text()
    assert (
        "retry 완료가 확인되지 않았습니다." in remediation_text
        or "현재 override 사유가 저장되어 있습니다." in remediation_text
    )
    retry_button = remediation.locator("button").first
    retry_label = retry_button.inner_text()
    assert "제안서" in retry_label
    assert "다시 시도" in retry_label
    assert page.locator('[data-project-procurement-return="system"]').is_visible()

    retry_button.click()

    page.locator(".doc-item").nth(2).wait_for(timeout=15000)
    page.wait_for_selector("#project-procurement-remediation-strip", state="detached", timeout=10000)
    assert page.locator(".doc-item").count() == 3

    page.locator('[data-project-procurement-return="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Override 후 downstream 완료",
        timeout_ms=10000,
    )
    focus_card = page.locator(f'[data-location-procurement-focus="{project_id}"]')
    assert focus_card.is_visible()
    assert "방금 확인한 프로젝트" in focus_card.inner_text()
    assert "거점 모달 재시도 테스트" in focus_card.inner_text()
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    assert "현재 미해소 queue 기준 candidate는 0개" in modal.inner_text()
    assert "queue 밖 candidate는" in modal.inner_text()
    assert "방금 확인한 프로젝트 이벤트는 context 유지를 위해 함께 표시합니다." in modal.inner_text()
    assert "Remediation handoff queue" in modal.inner_text()
    assert "열람 후 해소" in modal.inner_text()
    resolved_only_button = page.get_by_role("button", name="해소됨 candidate 보기")
    assert resolved_only_button.is_visible()
    assert "현재 미해소 override candidate가 없습니다." in modal.inner_text()
    assert "해소됨" in modal.inner_text()
    assert "Override 후 downstream 완료" in modal.inner_text()
    assert "override 이후 downstream까지 다시 이어진 건은 5건" in modal.inner_text()
    page.locator('[data-location-procurement-preset="handoff_review"]').click()
    page.wait_for_selector('[data-location-procurement-preset="handoff_review"].active', timeout=5000)
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.remediation_link_copied"].active',
        timeout=5000,
    )
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.remediation_link_opened"].active',
        timeout=5000,
    )
    handoff_focus_card = page.locator(f'[data-location-procurement-focus="{project_id}"]')
    assert "열람 후 해소" in handoff_focus_card.inner_text()

    page.locator('[data-location-procurement-scope="resolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="resolved_only"].active', timeout=5000)
    highlighted_candidate = page.locator(
        f'#location-procurement-modal .location-procurement-candidate.highlighted[data-location-procurement-project="{project_id}"]'
    ).first
    assert highlighted_candidate.is_visible()
    assert "방금 확인한 프로젝트" in highlighted_candidate.inner_text()
    assert "해소됨" in highlighted_candidate.inner_text()


def test_location_procurement_summary_can_toggle_stale_first_override_candidates(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    audit_store = AuditStore("system")

    def seed_no_go_candidate(
        name: str,
        source_id: str,
        override_reason: str,
        *,
        resolved: bool = False,
    ) -> str:
        candidate_project_id = _create_project_with_document(page, name=name)
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=candidate_project_id,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="capability_gap",
                        label="핵심 수행역량",
                        status="fail",
                        blocking=True,
                        reason="필수 운영 실적 부족",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="override 사유 저장 후 retry 대기 상태",
                ),
            )
        )
        page.evaluate(
            """async ({ projectId }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const added = await fetch(`/projects/${projectId}/documents`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  request_id: `req-${projectId}-rfp-analysis`,
                  bundle_id: 'rfp_analysis_kr',
                  title: '선행 RFP 분석',
                  docs: [{ doc_type: 'rfp_analysis', markdown: '# 선행 분석' }],
                }),
              });
              if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
            }""",
            {"projectId": candidate_project_id},
        )
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.downstream_blocked",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="failure",
                detail={
                    "project_id": candidate_project_id,
                    "bundle_type": "proposal_kr",
                    "error_code": "procurement_override_reason_required",
                    "recommendation": "NO_GO",
                },
                session_id=f"sess-{candidate_project_id}-blocked",
            )
        )
        page.evaluate(
            """async ({ projectId, reason }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const saved = await fetch(`/projects/${projectId}/procurement/override-reason`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ reason }),
              });
              if (!saved.ok) throw new Error(`override save failed: ${saved.status}`);
            }""",
            {"projectId": candidate_project_id, "reason": override_reason},
        )
        if resolved:
            audit_store.append(
                AuditLog(
                    log_id=str(uuid.uuid4()),
                    tenant_id="system",
                    timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    user_id="ops-admin",
                    username="ops_admin",
                    user_role="admin",
                    ip_address="127.0.0.1",
                    user_agent="playwright",
                    action="procurement.downstream_resolved",
                    resource_type="procurement",
                    resource_id=candidate_project_id,
                    resource_name="",
                    result="success",
                    detail={
                        "project_id": candidate_project_id,
                        "bundle_type": "proposal_kr",
                        "recommendation": "NO_GO",
                    },
                    session_id=f"sess-{candidate_project_id}-resolved",
                )
            )
        return candidate_project_id

    def seed_monitor_candidate(name: str, source_id: str) -> str:
        candidate_project_id = _create_project_with_document(page, name=name)
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=candidate_project_id,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="reference_gap",
                        label="유사 레퍼런스",
                        status="fail",
                        blocking=True,
                        reason="추가 운영 검토가 필요한 상태",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="운영 모니터링 상태",
                ),
            )
        )
        page.evaluate(
            """async ({ projectId }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const added = await fetch(`/projects/${projectId}/documents`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  request_id: `req-${projectId}-proposal`,
                  bundle_id: 'proposal_kr',
                  title: '후속 제안서 초안',
                  docs: [{ doc_type: 'proposal', markdown: '# monitor proposal' }],
                }),
              });
              if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
            }""",
            {"projectId": candidate_project_id},
        )
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.evaluate",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="success",
                detail={"project_id": candidate_project_id},
                session_id=f"sess-{candidate_project_id}-monitor",
            )
        )
        return candidate_project_id

    older_project_id = seed_no_go_candidate(
        "나-오래된 retry 후보",
        "R26-E2E-LOC-201",
        "먼저 저장된 override 사유입니다.",
    )
    page.wait_for_timeout(50)
    newer_project_id = seed_no_go_candidate(
        "가-최근 retry 후보",
        "R26-E2E-LOC-202",
        "나중에 저장된 override 사유입니다.",
    )
    page.wait_for_timeout(50)
    resolved_project_id = seed_no_go_candidate(
        "다-resolved 후보",
        "R26-E2E-LOC-203",
        "이미 retry 완료된 override 사유입니다.",
        resolved=True,
    )
    page.wait_for_timeout(50)
    monitor_project_id = seed_monitor_candidate(
        "라-monitor 후보",
        "R26-E2E-LOC-204",
    )

    page.evaluate(
        """() => {
          localStorage.removeItem('dd_location_procurement_summary_prefs');
          if (typeof clearLocationProcurementSummaryUrlState === 'function') {
            clearLocationProcurementSummaryUrlState();
          }
          if (typeof clearProjectProcurementDetailUrlState === 'function') {
            clearProjectProcurementDetailUrlState();
          }
        }"""
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert candidate_order.index(newer_project_id) < candidate_order.index(older_project_id)
    assert resolved_project_id in candidate_order
    assert page.locator('[data-location-procurement-order="latest_followup"].active').count() == 1

    page.locator('[data-location-procurement-order="stale_unresolved"]').click()
    page.wait_for_selector('[data-location-procurement-order="stale_unresolved"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert candidate_order.index(older_project_id) < candidate_order.index(newer_project_id)
    assert candidate_order.index(newer_project_id) < candidate_order.index(resolved_project_id)

    page.locator('[data-location-procurement-scope="unresolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]
    assert "현재 미해소 queue 기준 candidate는" in modal.inner_text()
    assert "queue 밖 candidate는" in modal.inner_text()
    assert page.get_by_role("button", name="전체 candidate 보기").is_visible()
    assert page.get_by_role("button", name="review backlog 보기").is_visible()
    ready_to_retry_filter = page.locator('[data-location-procurement-status-filter="ready_to_retry"]')
    assert ready_to_retry_filter.count() == 1
    assert "Retry 대기" in ready_to_retry_filter.inner_text()
    assert page.locator('[data-location-procurement-scope="monitor_only"]').count() == 1
    assert page.locator('[data-location-procurement-preset="retry_queue"]').count() == 1
    assert page.locator('[data-location-procurement-preset="resolved_review"]').count() == 1
    page.locator('[data-location-procurement-preset="resolved_review"]').click()
    page.wait_for_selector('[data-location-procurement-preset="resolved_review"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-scope="resolved_only"].active', timeout=5000)
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.downstream_resolved"].active',
        timeout=5000,
    )
    assert "세부 활동: Override 후 downstream 완료" in modal.inner_text()
    page.locator('[data-location-procurement-preset="retry_queue"]').click()
    page.wait_for_selector('[data-location-procurement-preset="retry_queue"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-status-filter="ready_to_retry"].active', timeout=5000)
    assert "세부 상태: Retry 대기" in modal.inner_text()
    assert modal.inner_text().count("Retry 대기") >= 2
    assert page.locator(
        f'#location-procurement-modal .location-procurement-candidate[data-location-procurement-project="{resolved_project_id}"]'
    ).count() == 0

    page.get_by_role("button", name="review backlog 보기").click()
    page.wait_for_selector('[data-location-procurement-scope="review_only"].active', timeout=5000)
    assert "세부 상태: 전체 상태" in modal.inner_text()
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert older_project_id not in candidate_order
    assert newer_project_id not in candidate_order
    assert resolved_project_id in candidate_order
    assert "현재 review backlog 기준 candidate는" in modal.inner_text()
    assert "현재 범위 활동:" in modal.inner_text()
    assert "현재 범위 queue KPI" in modal.inner_text()
    assert "현재 범위 candidate" in modal.inner_text()
    assert page.get_by_role("button", name="미해소 candidate 보기").is_visible()
    assert page.locator('[data-location-procurement-status-filter="resolved"]').count() == 1
    assert page.locator('[data-location-procurement-status-filter="monitor"]').count() == 1
    assert "해소됨 (" in modal.inner_text()
    assert "모니터링 (" in modal.inner_text()
    assert page.locator('[data-location-procurement-activity-filter="procurement.downstream_resolved"]').count() == 1
    page.locator('[data-location-procurement-activity-filter="procurement.downstream_resolved"]').click()
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.downstream_resolved"].active',
        timeout=5000,
    )
    assert "세부 활동: Override 후 downstream 완료" in modal.inner_text()
    event_titles = page.locator("#location-procurement-modal .location-procurement-event-title").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert event_titles
    assert set(event_titles) == {"Override 후 downstream 완료"}
    assert page.locator('[data-location-procurement-activity-clear="true"]').count() == 1
    page.locator('[data-location-procurement-activity-clear="true"]').click()
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.downstream_resolved"]:not(.active)',
        timeout=5000,
    )
    page.locator('[data-location-procurement-status-filter="monitor"]').click()
    page.wait_for_selector('[data-location-procurement-status-filter="monitor"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert older_project_id not in candidate_order
    assert newer_project_id not in candidate_order
    assert resolved_project_id not in candidate_order
    assert monitor_project_id in candidate_order
    assert "세부 상태: 모니터링" in modal.inner_text()
    assert "현재 범위 활동:" in modal.inner_text()
    assert "현재 범위 queue KPI" in modal.inner_text()
    assert "현재 범위 blocked" in modal.inner_text()
    assert page.locator('[data-location-procurement-status-clear="true"]').count() == 1
    page.locator('[data-location-procurement-status-clear="true"]').click()
    page.wait_for_selector('[data-location-procurement-status-filter="monitor"]:not(.active)', timeout=5000)

    page.locator('[data-location-procurement-scope="monitor_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="monitor_only"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_monitor = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_monitor == [monitor_project_id]
    assert "현재 모니터링 review 기준 candidate가 없습니다." not in modal.inner_text()
    assert page.get_by_role("button", name="미해소 candidate 보기").is_visible()

    page.locator('[data-location-procurement-scope="unresolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]

    page.locator(
        f'#location-procurement-modal .location-procurement-candidate [data-location-procurement-open="{older_project_id}"]'
    ).first.click()
    page.wait_for_selector("#project-procurement-remediation-strip", timeout=10000)
    remediation = page.locator("#project-procurement-remediation-strip")
    remediation_text = remediation.inner_text()
    assert (
        "retry 완료가 확인되지 않았습니다." in remediation_text
        or "현재 override 사유가 저장되어 있습니다." in remediation_text
    )
    assert "나-오래된 retry 후보" in page.locator("#project-detail").inner_text()
    assert page.locator('[data-project-procurement-return="system"]').is_visible()

    page.locator('[data-project-procurement-return="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    assert page.locator('[data-location-procurement-order="stale_unresolved"].active').count() == 1
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]
    assert page.locator(
        f'#location-procurement-modal .location-procurement-candidate [data-location-procurement-open="{newer_project_id}"]'
    ).count() >= 1
    assert page.locator(
        f'#location-procurement-modal .location-procurement-candidate[data-location-procurement-project="{resolved_project_id}"]'
    ).count() == 0
    page.locator('[data-location-procurement-preset="retry_queue"]').click()
    page.wait_for_selector('[data-location-procurement-preset="retry_queue"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-status-filter="ready_to_retry"].active', timeout=5000)
    stored_preferences = page.evaluate(
        """() => {
          const raw = JSON.parse(localStorage.getItem('dd_location_procurement_summary_prefs') || '{}');
          return raw.system || null;
        }"""
    )
    url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert stored_preferences == {
        "candidateView": "stale_unresolved",
        "candidateScope": "unresolved_only",
        "candidateStatusFilters": ["ready_to_retry"],
        "activityActionFilters": [],
    }
    assert url_state["location_procurement_tenant"] == "system"
    assert url_state["location_procurement_candidate_view"] == "stale_unresolved"
    assert url_state["location_procurement_candidate_scope"] == "unresolved_only"
    assert url_state["location_procurement_candidate_statuses"] == "ready_to_retry"
    assert "location_procurement_activity_actions" not in url_state
    page.evaluate(
        """() => {
          window.__copiedLocationProcurementLink = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => { window.__copiedLocationProcurementLink = text; },
            },
          });
        }"""
    )
    page.locator('[data-location-procurement-copy-link="true"]').first.click()
    copied_link = page.evaluate("window.__copiedLocationProcurementLink")
    assert copied_link is not None
    assert "location_procurement_tenant=system" in copied_link
    assert "location_procurement_candidate_view=stale_unresolved" in copied_link
    assert "location_procurement_candidate_scope=unresolved_only" in copied_link
    assert "location_procurement_candidate_statuses=ready_to_retry" in copied_link
    saved_search = page.evaluate("location.search")

    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    cleared_search = page.evaluate("location.search")
    assert "location_procurement_tenant" not in cleared_search
    page.evaluate(
        """() => {
          _locationProcurementSummaryModalState = null;
          _locationProcurementCandidateOrder = 'latest_followup';
          _locationProcurementCandidateScope = 'all';
          _locationProcurementCandidateStatusFilters = [];
          _locationProcurementActivityActionFilters = [];
        }"""
    )
    page.evaluate("(savedSearch) => history.replaceState({}, '', location.pathname + savedSearch)", saved_search)
    page.evaluate("restoreLocationProcurementSummaryFromUrl()")
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    assert page.locator('[data-location-procurement-order="stale_unresolved"].active').count() == 1
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    assert page.locator('[data-location-procurement-status-filter="ready_to_retry"].active').count() == 1
    assert page.locator('[data-location-procurement-preset="retry_queue"].active').count() == 1
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]


def test_location_procurement_summary_stale_share_review_preset_filters_share_activity(page):
    page.evaluate("switchPage('locations-page')")
    page.evaluate(
        """() => {
          const data = {
            tenant: { tenant_id: 'system', display_name: 'System' },
            procurement: {
              decision: { projects_with_procurement_state: 1, avg_soft_fit_score: 0.71 },
              handoff: {
                remediation_queue_count: 0,
                remediation_queue_status_counts: {},
                remediation_queue: [],
                approval_status_counts: {},
              },
              sharing: {
                stale_external_share_queue_count: 1,
                recovered_external_share_count: 1,
                active_stale_external_share_queue_count: 1,
                active_accessed_stale_external_share_queue_count: 1,
                active_unaccessed_stale_external_share_queue_count: 0,
                inactive_stale_external_share_queue_count: 0,
                active_stale_external_share_link_count: 1,
                active_accessed_stale_external_share_link_count: 1,
                active_unaccessed_stale_external_share_link_count: 0,
                revoked_stale_external_share_link_count: 0,
                expired_stale_external_share_link_count: 0,
                inactive_stale_external_share_link_count: 0,
                missing_stale_external_share_link_count: 0,
                missing_stale_external_share_record_count: 0,
                stale_external_share_status_counts: { source_changed: 1 },
                stale_external_share_queue: [
                  {
                    project_id: 'proj-stale-share',
                    project_name: '외부 공유 프로젝트',
                    project_document_id: 'doc-stale-share-1',
                    project_document_title: 'Stale council 기반 의사결정 문서',
                    bundle_type: 'bid_decision_kr',
                    share_risk_status: 'source_changed',
                    share_risk_status_tone: 'danger',
                    share_risk_status_copy: '공유 이후 원본 상태 변경',
                    share_risk_status_summary: '공유 링크 생성 이후 현재 원본 기준이 달라졌습니다.',
                    decision_council_document_status: 'current',
                    decision_council_document_status_tone: 'success',
                    decision_council_document_status_copy: '현재 council 기준',
                    decision_council_document_status_summary: '현재 council revision과 일치합니다.',
                    source_binding_status: 'current',
                    post_share_source_changed: true,
                    latest_shared_at: '2026-03-31T00:40:00+00:00',
                    latest_shared_by_username: 'admin',
                    latest_risk_observed_at: '2026-04-02T09:15:00+00:00',
                    latest_risk_observed_by_username: 'public-viewer',
                    latest_risk_action: 'share.view',
                    stale_share_count: 1,
                    share_id: 'share-stale-001',
                    share_url: '/shared/share-stale-001',
                    share_record_found: true,
                    share_is_active: true,
                    share_lifecycle_status: 'active',
                    active_stale_share_count: 1,
                    active_accessed_stale_share_count: 1,
                    active_unaccessed_stale_share_count: 0,
                    revoked_stale_share_count: 0,
                    expired_stale_share_count: 0,
                    share_access_count: 2,
                    share_last_accessed_at: '2026-04-02T09:15:00+00:00',
                    share_expires_at: '2026-04-07T00:00:00+00:00',
                  },
                ],
              },
              outcomes: {
                override_candidate_count: 0,
                override_candidates_needing_followup: 0,
                override_candidate_status_counts: {},
                scope_override_candidate_status_counts: {},
                override_candidate_view: 'latest_followup',
                override_candidate_scope: 'all',
                override_candidate_status_filters: [],
                override_candidates: [],
                visible_override_candidate_count: 0,
                visible_recent_event_count: 1,
                projects_with_downstream_handoff: 0,
              },
              activity: {
                action_counts: { 'share.create': 1, 'share.view': 1 },
                scope_action_counts: { 'share.create': 1, 'share.view': 1 },
                visible_action_counts: { 'share.create': 1, 'share.view': 1 },
                activity_action_filters: [],
                recent_events: [
                  {
                    timestamp: '2026-03-31T00:40:00+00:00',
                    action: 'share.view',
                    result: 'success',
                    resource_type: 'share',
                    linked_project_id: 'proj-stale-share',
                    linked_project_name: '외부 공유 프로젝트',
                    linked_approval_id: null,
                    error_code: null,
                    bundle_type: 'bid_decision_kr',
                    recommendation: null,
                    procurement_operation: null,
                    procurement_context_kind: null,
                    share_decision_council_document_status: 'current',
                    share_decision_council_document_status_copy: '현재 council 기준',
                    share_decision_council_document_status_summary: '현재 council revision과 일치합니다.',
                    share_source_binding_status: 'current',
                    share_post_share_source_changed: true,
                    share_project_document_id: 'doc-stale-share-1',
                  },
                ],
              },
            },
          };
          const modal = document.getElementById('location-procurement-modal');
          const body = document.getElementById('location-procurement-modal-body');
          _locationProcurementSummaryModalState = {
            data,
            focusProjectId: '',
            tenantId: '',
            candidateView: 'latest_followup',
            candidateScope: 'all',
            candidateStatusFilters: [],
            activityActionFilters: [],
          };
          _locationProcurementCandidateOrder = 'latest_followup';
          _locationProcurementCandidateScope = 'all';
          _locationProcurementCandidateStatusFilters = [];
          _locationProcurementActivityActionFilters = [];
          window.__openedSharedUrl = null;
          window.__copiedSharedUrl = null;
          window.open = (url) => {
            window.__openedSharedUrl = url;
            return null;
          };
          Object.defineProperty(window.navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: (text) => {
                window.__copiedSharedUrl = text;
                return Promise.resolve();
              },
            },
          });
          modal.style.display = 'flex';
          body.innerHTML = renderLocationProcurementSummary(data, '');
        }"""
    )

    page.wait_for_timeout(200)
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"]', state="visible", timeout=5000)
    pre_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "현재 stale public 노출이 남아 있는 공유 링크는 1개입니다." in pre_modal_text
    assert "최근 public 열람이 확인된 stale 링크는 1개입니다." in pre_modal_text
    page.locator('button:has-text("외부 공유 review 열기")').click()
    assert page.locator('[data-location-procurement-preset="stale_share_review"]').count() == 1
    assert page.locator('[data-location-procurement-preset="stale_share_review"]').inner_text() == '외부 공유 review (1)'
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-activity-filter="share.create"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-activity-filter="share.view"].active', timeout=5000)
    modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "외부 공유 재확인 queue" in modal_text
    assert "활성 링크 1" in modal_text
    assert "최근 public 열람 있음 1" in modal_text
    assert "아직 열람 없음 0" in modal_text
    assert "비활성 링크 0" in modal_text
    assert "risk audit 2" in modal_text
    assert "복구 확인 1" in modal_text
    assert "원본 연결/변경 1" in modal_text
    assert "Stale council 기반 의사결정 문서" in modal_text
    assert "활성 공유 링크" in modal_text
    assert "최근 public 열람 있음" in modal_text
    assert "외부 공유 위험:" in modal_text
    assert "공유 이후 원본 상태 변경" in modal_text
    assert "공유 생성: admin · 2026-03-31 · 영향 링크 1개" in modal_text
    assert "공유 링크 상태: 활성 공유 링크 · 조회 2회 · 최근 열람 2026-04-02 · 2026-04-07 만료" in modal_text
    assert "공유 링크 원본 변경 확인" in modal_text
    assert "공유 링크 생성 이후 현재 원본 기준이 달라졌습니다." in modal_text
    page.locator('#location-procurement-modal-body button:has-text("공유 링크 복사")').click()
    copied_url = page.evaluate("() => window.__copiedSharedUrl")
    assert copied_url is not None
    assert copied_url.endswith("/shared/share-stale-001")
    page.locator('#location-procurement-modal-body button:has-text("공유 링크 열기")').click()
    assert page.evaluate("() => window.__openedSharedUrl") == "/shared/share-stale-001"
    page.evaluate(
        """() => {
          const state = _locationProcurementSummaryModalState;
          const sharing = state.data.procurement.sharing;
          const item = sharing.stale_external_share_queue[0];
          sharing.active_stale_external_share_queue_count = 0;
          sharing.active_accessed_stale_external_share_queue_count = 0;
          sharing.inactive_stale_external_share_queue_count = 1;
          sharing.active_stale_external_share_link_count = 0;
          sharing.active_accessed_stale_external_share_link_count = 0;
          sharing.active_unaccessed_stale_external_share_link_count = 0;
          sharing.revoked_stale_external_share_link_count = 1;
          sharing.expired_stale_external_share_link_count = 0;
          item.share_is_active = false;
          item.share_lifecycle_status = 'revoked';
          item.active_stale_share_count = 0;
          item.active_accessed_stale_share_count = 0;
          item.revoked_stale_share_count = 1;
          item.share_revoked_at = '2026-04-03T10:30:00+00:00';
          item.share_revoked_by = 'u-admin';
          item.share_revoked_by_username = 'admin';
          document.getElementById('location-procurement-modal-body').innerHTML =
            renderLocationProcurementSummary(state.data, '');
        }"""
    )
    revoked_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "운영자 비활성화 1" in revoked_modal_text
    assert "만료 0" in revoked_modal_text
    assert "운영자 비활성화 · 조회 2회 · 비활성화 admin · 2026-04-03" in revoked_modal_text
    assert page.locator('[data-location-procurement-share-open="true"]').count() == 0
    assert page.locator('[data-location-procurement-share-copy="true"]').count() == 0
    assert page.locator('[data-location-procurement-share-id]').count() == 0
    page.evaluate(
        """() => {
          const state = _locationProcurementSummaryModalState;
          const sharing = state.data.procurement.sharing;
          const item = sharing.stale_external_share_queue[0];
          sharing.revoked_stale_external_share_link_count = 0;
          sharing.expired_stale_external_share_link_count = 1;
          item.share_lifecycle_status = 'expired';
          item.revoked_stale_share_count = 0;
          item.expired_stale_share_count = 1;
          item.share_revoked_at = null;
          item.share_revoked_by = null;
          item.share_revoked_by_username = null;
          document.getElementById('location-procurement-modal-body').innerHTML =
            renderLocationProcurementSummary(state.data, '');
        }"""
    )
    expired_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "운영자 비활성화 0" in expired_modal_text
    assert "만료 1" in expired_modal_text
    assert "만료된 공유 링크 · 조회 2회" in expired_modal_text
    page.evaluate(
        """() => {
          const state = _locationProcurementSummaryModalState;
          state.data.procurement.sharing.stale_external_share_queue_count = 0;
          state.data.procurement.sharing.active_stale_external_share_queue_count = 0;
          state.data.procurement.sharing.active_accessed_stale_external_share_queue_count = 0;
          state.data.procurement.sharing.recovered_external_share_count = 2;
          state.data.procurement.sharing.stale_external_share_status_counts = {};
          state.data.procurement.sharing.stale_external_share_queue = [];
          document.getElementById('location-procurement-modal-body').innerHTML =
            renderLocationProcurementSummary(state.data, '');
        }"""
    )
    recovered_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "현재 외부 공유 재확인 queue가 없습니다." in recovered_modal_text
    assert "2개 링크가 queue에서 해소됐습니다." in recovered_modal_text


def test_g2b_search_result_click_selects_announcement(page):
    page.evaluate(
        """() => {
          const g2bContent = document.getElementById('g2b-content');
          const searchTab = document.getElementById('g2b-search-tab');
          if (g2bContent) g2bContent.style.display = 'block';
          if (searchTab) searchTab.style.display = 'block';
          _g2bLastResults = [{
            bid_number: '20250317001-00',
            title: 'AI 기반 공공서비스 구축',
            issuer: '조달청',
            budget: '3억원',
            deadline: '2026-04-01',
            detail_url: 'https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20250317001-00',
          }];
          _renderG2BSearchResults(_g2bLastResults);
        }"""
    )

    page.wait_for_selector("#g2b-search-results .g2b-result-item", state="visible", timeout=10000)
    page.locator("#g2b-search-results .g2b-result-item").first.click()

    assert page.input_value("#f-title") == "AI 기반 공공서비스 구축"
    assert "20250317001-00" in page.input_value("#f-context")


def test_g2b_oneclick_proposal_button_handles_hyphenated_bid_number(page):
    page.evaluate(
        """() => {
          const g2bContent = document.getElementById('g2b-content');
          const searchTab = document.getElementById('g2b-search-tab');
          if (g2bContent) g2bContent.style.display = 'block';
          if (searchTab) searchTab.style.display = 'block';
          _g2bLastResults = [{
            bid_number: '20250317001-00',
            title: 'AI 기반 공공서비스 구축',
            issuer: '조달청',
            budget: '3억원',
            deadline: '2026-04-01',
            detail_url: 'https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20250317001-00',
          }];
          _renderG2BSearchResults(_g2bLastResults);
        }"""
    )

    page.wait_for_selector("#g2b-search-results .g2b-oneclick-btn", state="visible", timeout=10000)
    page.locator("#g2b-search-results .g2b-oneclick-btn").first.click()

    assert page.input_value("#f-title") == "AI 기반 공공서비스 구축"
    assert "20250317001-00" in page.input_value("#f-context")

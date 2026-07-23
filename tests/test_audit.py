"""tests/test_audit.py — Tests for the ISMS audit logging system.

Coverage:
  AuditStore unit   : append, query filters (action/user/result/date/ip),
                      get_failed_logins, get_user_activity, get_session_activity,
                      get_stats, export_csv, corrupted-line recovery,
                      append-only (no delete/modify methods present)
  Middleware helpers: _resolve_action (login/401/403/admin paths),
                      _path_matches (pattern matching),
                      _infer_resource_type, _extract_resource_id
  Middleware E2E    : login success → user.login logged,
                      401 response → user.login_fail logged,
                      403 response → access.blocked logged,
                      admin path → audit entry created
  API endpoints     : GET /admin/audit-logs (admin only, filters),
                      GET /admin/audit-logs/stats,
                      GET /admin/audit-logs/failed-logins (suspicious IP grouping),
                      GET /admin/audit-logs/export (CSV),
                      non-admin → 403
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-secret-key-audit-tests-32chars!!"


# ── Client helpers ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET_KEY)
    from app.main import create_app
    return TestClient(create_app())


def _register_and_login(client, username="admin", password="AdminPass1!", email="admin@test.com"):
    client.post("/auth/register", json={
        "username": username, "display_name": username.title(),
        "email": email, "password": password,
    })
    return client.post("/auth/login", json={"username": username, "password": password}).json()


def _auth(login_resp):
    return {"Authorization": f"Bearer {login_resp['access_token']}"}


def _make_audit_log(tenant_id="system", action="doc.generate", result="success",
                    user_id="u1", username="alice", ip="1.2.3.4",
                    session_id="sess1", detail=None, **kwargs):
    from app.storage.audit_store import AuditLog
    import uuid
    return AuditLog(
        log_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        user_id=user_id,
        username=username,
        user_role="member",
        ip_address=ip,
        user_agent="test-agent",
        action=action,
        resource_type="document",
        resource_id="res-1",
        resource_name="테스트 문서",
        result=result,
        detail=detail or {},
        session_id=session_id,
        **kwargs,
    )


# ── AuditStore unit tests ──────────────────────────────────────────────────────


def test_audit_store_append(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("tenant1")
    log = _make_audit_log(tenant_id="tenant1")
    store.append(log)
    entries = store.query()
    assert len(entries) == 1
    assert entries[0]["action"] == "doc.generate"


def test_audit_store_append_only_no_delete(tmp_path):
    """AuditStore must not expose any delete or modify methods."""
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("tenant1")
    assert not hasattr(store, "delete"), "AuditStore must not have a delete method"
    assert not hasattr(store, "update"), "AuditStore must not have an update method"
    assert not hasattr(store, "clear"), "AuditStore must not have a clear method"


def test_audit_store_append_is_jsonl(tmp_path):
    """Each log entry is a single line of valid JSON."""
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("tenant1")
    store.append(_make_audit_log(tenant_id="tenant1", action="user.login"))
    store.append(_make_audit_log(tenant_id="tenant1", action="user.logout"))
    lines = store._path.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "log_id" in obj
        assert "action" in obj


def test_audit_store_query_filter_by_action(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", action="user.login"))
    store.append(_make_audit_log(tenant_id="t1", action="doc.generate"))
    store.append(_make_audit_log(tenant_id="t1", action="user.login"))
    results = store.query(filters={"action": "user.login"})
    assert len(results) == 2
    assert all(r["action"] == "user.login" for r in results)


def test_audit_store_query_filter_by_user(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", user_id="u1"))
    store.append(_make_audit_log(tenant_id="t1", user_id="u2"))
    results = store.query(filters={"user_id": "u1"})
    assert len(results) == 1
    assert results[0]["user_id"] == "u1"


def test_audit_store_query_filter_by_result(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", result="success"))
    store.append(_make_audit_log(tenant_id="t1", result="blocked"))
    store.append(_make_audit_log(tenant_id="t1", result="blocked"))
    results = store.query(filters={"result": "blocked"})
    assert len(results) == 2


def test_audit_store_query_filter_by_date(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")

    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    new_ts = datetime.now(timezone.utc).isoformat()

    def _log_at(ts):
        log = _make_audit_log(tenant_id="t1")
        log.timestamp = ts
        store.append(log)

    _log_at(old_ts)
    _log_at(new_ts)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    results = store.query(filters={"date_from": cutoff})
    assert len(results) == 1
    assert results[0]["timestamp"] >= cutoff


def test_audit_store_query_date_only_end_includes_full_day(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore

    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    results = store.query(filters={"date_from": today, "date_to": today})

    assert len(results) == 1


def test_audit_store_query_filter_by_ip(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", ip="10.0.0.1"))
    store.append(_make_audit_log(tenant_id="t1", ip="10.0.0.2"))
    results = store.query(filters={"ip_address": "10.0.0.1"})
    assert len(results) == 1
    assert results[0]["ip_address"] == "10.0.0.1"


def test_audit_store_get_failed_logins(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", action="user.login_fail"))
    store.append(_make_audit_log(tenant_id="t1", action="user.login"))
    store.append(_make_audit_log(tenant_id="t1", action="user.login_fail"))
    results = store.get_failed_logins(hours=24)
    assert len(results) == 2
    assert all(r["action"] == "user.login_fail" for r in results)


def test_audit_store_get_user_activity(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", user_id="u1"))
    store.append(_make_audit_log(tenant_id="t1", user_id="u2"))
    store.append(_make_audit_log(tenant_id="t1", user_id="u1"))
    results = store.get_user_activity("u1", days=30)
    assert len(results) == 2


def test_audit_store_get_session_activity(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", session_id="sess-A"))
    store.append(_make_audit_log(tenant_id="t1", session_id="sess-B"))
    store.append(_make_audit_log(tenant_id="t1", session_id="sess-A"))
    results = store.get_session_activity("sess-A")
    assert len(results) == 2


def test_audit_store_get_stats(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", action="user.login", result="success"))
    store.append(_make_audit_log(tenant_id="t1", action="doc.generate", result="success"))
    store.append(_make_audit_log(tenant_id="t1", action="access.blocked", result="blocked"))
    stats = store.get_stats(days=30)
    assert stats["total_actions"] == 3
    assert stats["blocked_count"] == 1
    assert "user.login" in stats["by_action_type"]


def test_audit_store_export_csv(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", action="user.login", username="alice"))
    date_from = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    date_to = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    csv_str = store.export_csv(date_from, date_to)
    assert "log_id" in csv_str  # header present
    assert "user.login" in csv_str
    assert "alice" in csv_str


def test_audit_store_export_csv_preserves_full_pilot_evidence(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore

    store = AuditStore("t1")
    store.append(_make_audit_log(
        tenant_id="t1",
        action="report_quality.pilot_export",
        username="=HYPERLINK(\"https://example.invalid\")",
        detail={
            "request_id": "pilot-request-1234",
            "pilot_sha256": "a" * 64,
            "pilot_artifact_count": 3,
            "pilot_preview_verified": True,
            "training_execution_started": False,
        },
    ))
    for index in range(1000):
        store.append(_make_audit_log(
            tenant_id="t1",
            action="doc.view",
            user_id=f"user-{index}",
        ))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = list(csv.DictReader(io.StringIO(store.export_csv(today, today))))

    assert len(rows) == 1001
    pilot = rows[0]
    assert pilot["tenant_id"] == "t1"
    assert pilot["username"].startswith("'=")
    assert pilot["request_id"] == "pilot-request-1234"
    assert pilot["pilot_sha256"] == "a" * 64
    assert pilot["pilot_artifact_count"] == "3"
    assert pilot["pilot_preview_verified"] == "True"
    assert json.loads(pilot["detail_json"])["training_execution_started"] is False


def test_audit_store_export_csv_applies_action_and_result_filters(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore

    store = AuditStore("t1")
    store.append(_make_audit_log(
        tenant_id="t1",
        action="report_quality.pilot_export",
        result="success",
    ))
    store.append(_make_audit_log(
        tenant_id="t1",
        action="report_quality.pilot_export",
        result="blocked",
    ))
    store.append(_make_audit_log(tenant_id="t1", action="doc.view", result="success"))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = list(csv.DictReader(io.StringIO(store.export_csv(
        today,
        today,
        action="report_quality.pilot_export",
        result="success",
    ))))

    assert [(row["action"], row["result"]) for row in rows] == [
        ("report_quality.pilot_export", "success"),
    ]


def test_audit_store_corrupted_line_stops_read_and_append(tmp_path):
    """Corrupted JSONL evidence is preserved and never repaired during reads."""
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore, AuditStoreError
    store = AuditStore("t1")
    log = _make_audit_log(tenant_id="t1", action="user.login")
    store.append(log)
    with store._path.open("a", encoding="utf-8") as stream:
        stream.write("NOT VALID JSON{{{\n")
    corrupted_bytes = store._path.read_bytes()

    with pytest.raises(AuditStoreError, match="Invalid audit log entry at line 2"):
        store._read_all()
    with pytest.raises(AuditStoreError, match="Invalid audit log entry at line 2"):
        store.append(_make_audit_log(tenant_id="t1"))

    assert store._path.read_bytes() == corrupted_bytes


def test_audit_store_find_latest_entry_bypasses_query_cap(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditLog, AuditStore

    store = AuditStore("t1")
    store.append(
        AuditLog(
            log_id="log-project-a",
            tenant_id="t1",
            timestamp="2026-03-31T00:00:00+00:00",
            user_id="u1",
            username="alice",
            user_role="member",
            ip_address="1.2.3.4",
            user_agent="test-agent",
            action="procurement.import",
            resource_type="procurement",
            resource_id="project-a",
            resource_name="Focused project",
            result="success",
            detail={},
            session_id="sess1",
        )
    )
    for index in range(1001):
        store.append(
            AuditLog(
                log_id=f"log-{index}",
                tenant_id="t1",
                timestamp=f"2026-03-31T01:{index // 60:02d}:{index % 60:02d}+00:00",
                user_id="u1",
                username="alice",
                user_role="member",
                ip_address="1.2.3.4",
                user_agent="test-agent",
                action="procurement.evaluate",
                resource_type="procurement",
                resource_id=f"project-{index + 1}",
                resource_name="Busy project",
                result="success",
                detail={},
                session_id="sess1",
            )
        )

    capped_results = store.query()
    assert len(capped_results) == 1000
    assert all(entry["resource_id"] != "project-a" for entry in capped_results)

    latest_entry = store.find_latest_entry(
        actions={"procurement.import", "procurement.evaluate"},
        resource_ids={"project-a"},
    )
    assert latest_entry is not None
    assert latest_entry["action"] == "procurement.import"
    assert latest_entry["resource_id"] == "project-a"


def test_audit_store_query_all_is_not_capped(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditLog, AuditStore

    store = AuditStore("t1")
    for index in range(1002):
        store.append(
            AuditLog(
                log_id=f"log-{index}",
                tenant_id="t1",
                timestamp=f"2026-03-31T01:{index // 60:02d}:{index % 60:02d}+00:00",
                user_id="u1",
                username="alice",
                user_role="member",
                ip_address="1.2.3.4",
                user_agent="test-agent",
                action="procurement.evaluate",
                resource_type="procurement",
                resource_id=f"project-{index}",
                resource_name="Busy project",
                result="success",
                detail={},
                session_id="sess1",
            )
        )

    assert len(store.query()) == 1000
    assert len(store.query_all()) == 1002


# ── Middleware helper unit tests ───────────────────────────────────────────────


def test_resolve_action_login_success():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/auth/login", 200) == "user.login"


def test_resolve_action_login_fail_401():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/auth/login", 401) == "user.login_fail"


def test_resolve_action_401_non_login():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("GET", "/admin/users", 401) == "access.unauthorized"


def test_resolve_action_403():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("GET", "/admin/anything", 403) == "access.blocked"


def test_resolve_action_approval_submit():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/approvals/abc-123/submit", 200) == "approval.submit"


def test_resolve_action_approval_approve():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/approvals/abc-123/approve", 200) == "approval.approve"


def test_resolve_action_public_share_view():
    from app.middleware.audit import _resolve_action

    assert _resolve_action("GET", "/shared/share-token-123", 200) == "share.view"


def test_resolve_action_procurement_import():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/imports/g2b-opportunity", 200) == "procurement.import"


def test_resolve_action_procurement_evaluate():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/procurement/evaluate", 200) == "procurement.evaluate"


def test_resolve_action_procurement_recommend():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/procurement/recommend", 200) == "procurement.recommend"


def test_resolve_action_procurement_review_packet_export():
    from app.middleware.audit import _resolve_action
    assert (
        _resolve_action("POST", "/projects/proj-1/procurement/review-packet", 200)
        == "procurement.review_packet_export"
    )


def test_resolve_action_report_quality_pilot_flows():
    from app.middleware.audit import _resolve_action
    from app.storage.audit_store import ACTION_TYPES

    base_path = "/report-workflows/learning/correction-artifacts/pilot-export"
    assert _resolve_action("POST", f"{base_path}/preview", 200) == "report_quality.pilot_preview"
    assert _resolve_action("POST", f"{base_path}/package", 200) == "report_quality.pilot_package"
    assert _resolve_action("POST", base_path, 200) == "report_quality.pilot_export"
    assert (
        _resolve_action(
            "POST",
            "/report-workflows/learning/correction-artifacts/pilot-package/verify",
            200,
        )
        == "report_quality.pilot_package_verify"
    )
    assert ACTION_TYPES["report_quality.pilot_preview"] == "보고서 품질 파일럿 사전 검토"
    assert ACTION_TYPES["report_quality.pilot_export"] == "보고서 품질 파일럿 내보내기"
    assert ACTION_TYPES["report_quality.pilot_package"] == "보고서 품질 파일럿 검토 패키지"
    assert (
        ACTION_TYPES["report_quality.pilot_package_verify"]
        == "보고서 품질 파일럿 수신 패키지 검증"
    )


def test_resolve_action_explicit_document_ops_events_preserves_access_failures():
    from app.middleware.audit import _resolve_action
    from app.storage.audit_store import ACTION_TYPES

    detail_path = "/api/agent/document-ops/trajectories/trj_123"
    assert _resolve_action(
        "GET",
        detail_path,
        200,
        explicit_action="document_ops.trajectory_view",
    ) == "document_ops.trajectory_view"
    assert _resolve_action(
        "POST",
        f"{detail_path}/review",
        400,
        explicit_action="document_ops.trajectory_review",
    ) == "document_ops.trajectory_review"
    assert _resolve_action(
        "GET",
        detail_path,
        401,
        explicit_action="document_ops.trajectory_view",
    ) == "access.unauthorized"
    assert _resolve_action("GET", "/api/agent/document-ops/trajectories/stats", 200) == ""
    assert ACTION_TYPES["document_ops.trajectory_view"] == "DocumentOps 이력 상세 조회"
    assert ACTION_TYPES["document_ops.trajectory_review"] == "DocumentOps 사람 검토"
    assert (
        ACTION_TYPES["document_ops.agent_run_operation_view"]
        == "DocumentOps Agent 실행 상태 조회"
    )
    assert (
        _resolve_action(
            "GET",
            "/api/agent/document-ops/trajectories/governance/overview",
            200,
            explicit_action="document_ops.governance_view",
        )
        == "document_ops.governance_view"
    )
    assert (
        ACTION_TYPES["document_ops.governance_view"]
        == "DocumentOps governance 조회"
    )
    assert (
        ACTION_TYPES["document_ops.governance_handoff_download"]
        == "DocumentOps governance handoff 다운로드"
    )


def test_resolve_action_procurement_review_inbox_view():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("GET", "/procurement/reviews", 200) == "procurement.review_inbox_view"


def test_procurement_review_inbox_view_is_audited_with_queue_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client, username="review-auditor")

    response = client.get("/procurement/reviews", headers=_auth(login))

    assert response.status_code == 200
    from app.storage.audit_store import AuditStore
    entries = AuditStore("system").query(
        filters={"action": "procurement.review_inbox_view"},
    )
    assert len(entries) == 1
    assert entries[0]["detail"]["review_total"] == 0
    assert entries[0]["detail"]["review_pending_count"] == 0
    assert entries[0]["detail"]["review_completed_count"] == 0


def test_resolve_action_procurement_review_completed():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "POST",
        "/projects/proj-1/procurement/reviews/abc123/complete",
        200,
    ) == "procurement.review_completed"


def test_resolve_action_procurement_reviewed_package_download():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "GET",
        "/projects/proj-1/procurement/reviews/abc123/reviewed-package",
        200,
    ) == "procurement.reviewed_package_download"


def test_resolve_action_decision_council_run():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/decision-council/run", 200) == "decision_council.run"


def test_resolve_action_procurement_override_reason():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/procurement/override-reason", 200) == "procurement.override_reason"


def test_resolve_action_procurement_remediation_link_copied():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "POST",
        "/projects/proj-1/procurement/remediation-link-copy",
        200,
    ) == "procurement.remediation_link_copied"


def test_resolve_action_procurement_remediation_link_opened():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "POST",
        "/projects/proj-1/procurement/remediation-link-open",
        200,
    ) == "procurement.remediation_link_opened"


def test_resolve_action_procurement_downstream_blocked():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "POST",
        "/generate/stream",
        409,
        error_code="procurement_override_reason_required",
    ) == "procurement.downstream_blocked"


def test_resolve_action_procurement_downstream_resolved():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "POST",
        "/generate/stream",
        200,
        procurement_action="downstream_resolved",
    ) == "doc.generate"


def test_resolve_action_decision_council_handoff_used():
    from app.middleware.audit import _resolve_action
    assert _resolve_action(
        "POST",
        "/generate/stream",
        200,
        decision_council_handoff_used=True,
    ) == "doc.generate"


def test_resolve_supplemental_actions_for_generate_success():
    from app.middleware.audit import _resolve_supplemental_actions
    assert _resolve_supplemental_actions(
        "POST",
        "/generate/stream",
        200,
        procurement_action="downstream_resolved",
        procurement_review_handoff_used=True,
        decision_council_handoff_used=True,
    ) == [
        "procurement.downstream_resolved",
        "procurement.review_handoff_used",
        "decision_council.handoff_used",
    ]


def test_resolve_supplemental_action_for_new_procurement_review():
    from app.middleware.audit import _resolve_supplemental_actions
    assert _resolve_supplemental_actions(
        "POST",
        "/projects/proj-1/procurement/review-packet",
        200,
        procurement_review_started=True,
    ) == ["procurement.review_started"]


def test_resolve_action_share_create():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/share", 200) == "share.create"


def test_resolve_action_share_revoke():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("DELETE", "/share/share-123", 200) == "share.revoke"


def test_path_matches():
    from app.middleware.audit import _path_matches
    assert _path_matches("/approvals/abc-123/submit", "/approvals/{id}/submit")
    assert _path_matches("/admin/users/u-456", "/admin/users/{id}")
    assert not _path_matches("/approvals/abc/approve", "/approvals/{id}/submit")


def test_infer_resource_type():
    from app.middleware.audit import _infer_resource_type
    assert _infer_resource_type("/approvals/123/submit") == "approval"
    assert _infer_resource_type("/projects/proj-1/procurement") == "procurement"
    assert _infer_resource_type("/share") == "share"
    assert _infer_resource_type("/admin/users") == "user"
    assert _infer_resource_type("/generate/stream") == "document"
    assert _infer_resource_type("/styles/abc") == "style"


def test_extract_resource_id():
    from app.middleware.audit import _extract_resource_id
    uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert _extract_resource_id(f"/approvals/{uid}/submit") == uid
    assert _extract_resource_id("/auth/login") == ""


# ── Middleware E2E tests (via TestClient) ──────────────────────────────────────


def test_audit_login_success_logged(tmp_path, monkeypatch):
    """Successful login creates a user.login audit entry."""
    client = _make_client(tmp_path, monkeypatch)
    _register_and_login(client)

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    results = store.query(filters={"action": "user.login"})
    assert len(results) >= 1
    assert results[0]["result"] == "success"


def test_audit_login_fail_logged(tmp_path, monkeypatch):
    """Failed login (wrong password) creates a user.login_fail audit entry."""
    client = _make_client(tmp_path, monkeypatch)
    _register_and_login(client)
    # Attempt login with wrong password
    client.post("/auth/login", json={"username": "admin", "password": "WrongPass!"})

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    results = store.query(filters={"action": "user.login_fail"})
    assert len(results) >= 1
    assert results[0]["result"] == "blocked"


def test_audit_logout_records_action_without_session_credentials(tmp_path, monkeypatch):
    """Server-side logout is auditable without copying bearer authority."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    response = client.post("/auth/logout", headers=_auth(login))

    from app.services.auth_service import verify_token
    from app.storage.audit_store import AuditStore

    claims = verify_token(login["access_token"])
    results = AuditStore("system").query(filters={"action": "user.logout"})
    serialized = json.dumps(results, ensure_ascii=False)

    assert response.status_code == 200
    assert claims is not None
    assert len(results) >= 1
    assert results[0]["result"] == "success"
    assert login["access_token"] not in serialized
    assert login["refresh_token"] not in serialized
    assert claims["session_id"] not in serialized


def test_audit_session_inventory_and_revoke_do_not_copy_session_credentials(
    tmp_path,
    monkeypatch,
):
    """Self-service session controls are auditable without stored bearer IDs."""
    client = _make_client(tmp_path, monkeypatch)
    first = _register_and_login(client)
    second = client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).json()
    third = client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).json()

    from app.services.auth_service import verify_token
    from app.storage.audit_store import AuditStore

    second_claims = verify_token(second["access_token"])
    assert second_claims is not None
    listed = client.get("/auth/sessions", headers=_auth(first))
    label = "감사 로그에 남기지 않을 기기 이름"
    labeled = client.patch(
        "/auth/sessions/label",
        headers=_auth(first),
        json={"session_id": second_claims["session_id"], "label": label},
    )
    revoked = client.post(
        "/auth/sessions/revoke",
        headers=_auth(first),
        json={"session_id": second_claims["session_id"]},
    )
    bulk_revoked = client.post(
        "/auth/sessions/revoke-others",
        headers=_auth(first),
        json={"confirm": True},
    )
    all_revoked = client.post(
        "/auth/sessions/revoke-all",
        headers=_auth(first),
        json={"confirm": True},
    )
    results = AuditStore("system").query()
    session_entries = [
        entry
        for entry in results
        if entry["action"] in {
            "user.session_list",
            "user.session_label_update",
            "user.session_revoke",
            "user.session_revoke_others",
            "user.session_revoke_all",
        }
    ]
    serialized = json.dumps(session_entries, ensure_ascii=False)

    assert listed.status_code == 200
    assert labeled.status_code == 200
    assert revoked.status_code == 200
    assert bulk_revoked.status_code == 200
    assert all_revoked.status_code == 200
    assert {entry["action"] for entry in session_entries} == {
        "user.session_list",
        "user.session_label_update",
        "user.session_revoke",
        "user.session_revoke_others",
        "user.session_revoke_all",
    }
    assert first["access_token"] not in serialized
    assert first["refresh_token"] not in serialized
    assert second["access_token"] not in serialized
    assert second["refresh_token"] not in serialized
    assert third["access_token"] not in serialized
    assert third["refresh_token"] not in serialized
    assert second_claims["session_id"] not in serialized
    assert label not in serialized
    bulk_entry = next(
        entry
        for entry in session_entries
        if entry["action"] == "user.session_revoke_others"
    )
    assert bulk_entry["detail"]["revoked_sessions"] == 2
    all_entry = next(
        entry
        for entry in session_entries
        if entry["action"] == "user.session_revoke_all"
    )
    assert all_entry["detail"]["revoked_sessions"] == 1


def test_audit_auth_session_retention_preview_records_only_aggregate_evidence(
    tmp_path,
    monkeypatch,
):
    import app.storage.auth_session_store as auth_session_module
    from app.services.auth_service import verify_token
    from app.storage.audit_store import AuditStore
    from app.storage.auth_session_store import AuthSessionStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    claims = verify_token(login["access_token"])
    assert claims is not None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    clock = [now - timedelta(days=100)]
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: clock[0])
    store = AuthSessionStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    candidate_user_id = "candidate-user"
    session_id = store.create(user_id=candidate_user_id, credential_version=0)
    label = "audit-private-label"
    assert store.set_label(
        session_id,
        user_id=candidate_user_id,
        credential_version=0,
        label=label,
    )
    clock[0] = now

    response = client.get(
        "/admin/auth-sessions/retention-preview",
        headers=_auth(login),
        params={"retention_days": 30},
    )
    entries = AuditStore("system").query(
        filters={"action": "auth_session.retention_preview"}
    )
    serialized = json.dumps(entries, ensure_ascii=False)

    assert response.status_code == 200
    assert len(entries) == 1
    assert entries[0]["detail"]["retention_days"] == 30
    assert entries[0]["detail"]["inspected_sessions"] == 3
    assert entries[0]["detail"]["eligible_sessions"] == 1
    assert entries[0]["detail"]["read_only"] is True
    assert session_id not in serialized
    assert candidate_user_id not in serialized
    assert label not in serialized
    assert login["access_token"] not in serialized
    assert login["refresh_token"] not in serialized


def test_audit_auth_session_retention_comparison_records_only_aggregate_evidence(
    tmp_path,
    monkeypatch,
):
    import app.storage.auth_session_store as auth_session_module
    from app.storage.audit_store import AuditStore
    from app.storage.auth_session_store import AuthSessionStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    clock = [now - timedelta(days=100)]
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: clock[0])
    store = AuthSessionStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    candidate_user_id = "comparison-candidate-user"
    session_id = store.create(user_id=candidate_user_id, credential_version=0)
    label = "comparison-private-label"
    assert store.set_label(
        session_id,
        user_id=candidate_user_id,
        credential_version=0,
        label=label,
    )
    clock[0] = now

    response = client.get(
        "/admin/auth-sessions/retention-comparison",
        headers=_auth(login),
    )
    entries = AuditStore("system").query(
        filters={"action": "auth_session.retention_comparison"}
    )
    serialized = json.dumps(entries, ensure_ascii=False)

    assert response.status_code == 200
    assert len(entries) == 1
    assert entries[0]["detail"]["policy_days"] == [30, 90, 180, 365]
    assert entries[0]["detail"]["inspected_sessions"] == 3
    assert entries[0]["detail"]["eligible_sessions_by_policy"] == [1, 0, 0, 0]
    assert entries[0]["detail"]["read_only"] is True
    assert entries[0]["detail"]["snapshot_atomic"] is False
    assert session_id not in serialized
    assert candidate_user_id not in serialized
    assert label not in serialized
    assert login["access_token"] not in serialized
    assert login["refresh_token"] not in serialized


def test_audit_auth_session_retention_handoff_records_only_review_aggregate(
    tmp_path,
    monkeypatch,
):
    import app.storage.auth_session_store as auth_session_module
    from app.storage.audit_store import AuditStore
    from app.storage.auth_session_store import AuthSessionStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    clock = [now - timedelta(days=100)]
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: clock[0])
    store = AuthSessionStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    candidate_user_id = "handoff-candidate-user"
    session_id = store.create(user_id=candidate_user_id, credential_version=0)
    label = "handoff-private-label"
    assert store.set_label(
        session_id,
        user_id=candidate_user_id,
        credential_version=0,
        label=label,
    )
    clock[0] = now

    response = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": 90},
    )
    entries = AuditStore("system").query(
        filters={"action": "auth_session.retention_handoff"}
    )
    serialized = json.dumps(entries, ensure_ascii=False)

    assert response.status_code == 200
    assert len(entries) == 1
    assert entries[0]["user_id"] == ""
    assert entries[0]["username"] == ""
    assert entries[0]["session_id"] == ""
    assert entries[0]["detail"] == {
        "method": "GET",
        "path": "/admin/auth-sessions/retention-handoff",
        "status_code": 200,
        "duration_ms": entries[0]["detail"]["duration_ms"],
        "retention_days": 90,
        "policy_days": [30, 90, 180, 365],
        "inspected_sessions": 3,
        "eligible_sessions_by_policy": [1, 0, 0, 0],
        "read_only": True,
        "snapshot_atomic": False,
    }
    assert session_id not in serialized
    assert candidate_user_id not in serialized
    assert label not in serialized
    assert login["access_token"] not in serialized
    assert login["refresh_token"] not in serialized


def test_audit_auth_session_retention_recheck_records_only_current_aggregate(
    tmp_path,
    monkeypatch,
):
    from app.storage.audit_store import AuditStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client, username="retention-operator")
    source = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": 90},
    ).json()
    source_sha256 = hashlib.sha256(
        json.dumps(
            source,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    from app.services.auth_service import verify_token

    claims = verify_token(login["access_token"])
    response = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": source,
            "source_handoff_sha256": source_sha256,
        },
    )
    entries = AuditStore("system").query(
        filters={"action": "auth_session.retention_recheck"}
    )
    serialized = json.dumps(entries, ensure_ascii=False)

    assert response.status_code == 200
    assert len(entries) == 1
    assert claims is not None
    assert entries[0]["user_id"] == ""
    assert entries[0]["username"] == ""
    assert entries[0]["session_id"] == ""
    assert entries[0]["detail"] == {
        "method": "POST",
        "path": "/admin/auth-sessions/retention-handoff/recheck",
        "status_code": 200,
        "duration_ms": entries[0]["detail"]["duration_ms"],
        "retention_days": 90,
        "inspected_sessions": 2,
        "eligible_sessions": 0,
        "aggregate_status": "unchanged",
        "read_only": True,
        "snapshot_atomic": False,
    }
    assert source_sha256 not in serialized
    assert "source_handoff" not in serialized
    assert claims["sub"] not in serialized
    assert claims["session_id"] not in serialized
    assert "retention-operator" not in serialized
    assert login["access_token"] not in serialized
    assert login["refresh_token"] not in serialized


def test_audit_auth_session_retention_review_disposition_records_bound_aggregate_only(
    tmp_path,
    monkeypatch,
):
    from app.storage.audit_store import AuditStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client, username="review-disposition-operator")
    source = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": 90},
    ).json()
    source_sha256 = hashlib.sha256(
        json.dumps(
            source,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    recheck = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": source,
            "source_handoff_sha256": source_sha256,
        },
    )
    assert recheck.status_code == 200
    recheck_receipt = recheck.json()
    recheck_receipt_sha256 = hashlib.sha256(recheck.content).hexdigest()

    from app.services.auth_service import verify_token

    claims = verify_token(login["access_token"])
    response = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers={**_auth(login), "User-Agent": "private-retention-review-agent"},
        json={
            "contract_version": "auth-session-retention-review-disposition-request.v1",
            "source_recheck_receipt": recheck_receipt,
            "source_recheck_receipt_sha256": recheck_receipt_sha256,
            "review_disposition": "acknowledged_unchanged",
        },
    )
    entries = AuditStore("system").query(
        filters={"action": "auth_session.retention_review_disposition"}
    )
    serialized = json.dumps(entries, ensure_ascii=False)

    assert response.status_code == 200
    assert len(entries) == 1
    assert claims is not None
    assert entries[0]["user_id"] == ""
    assert entries[0]["username"] == ""
    assert entries[0]["session_id"] == ""
    assert entries[0]["ip_address"] == ""
    assert entries[0]["user_agent"] == ""
    assert entries[0]["detail"] == {
        "method": "POST",
        "path": "/admin/auth-sessions/retention-handoff/review-disposition",
        "status_code": 200,
        "duration_ms": entries[0]["detail"]["duration_ms"],
        "selected_policy_days": 90,
        "aggregate_status": "unchanged",
        "review_disposition": "acknowledged_unchanged",
        "source_recheck_receipt_sha256": recheck_receipt_sha256,
        "receipt_sha256": hashlib.sha256(response.content).hexdigest(),
        "review_only": True,
    }
    for forbidden_value in (
        source_sha256,
        json.dumps(recheck_receipt, ensure_ascii=False),
        claims["sub"],
        claims["session_id"],
        "review-disposition-operator",
        "private-retention-review-agent",
        login["access_token"],
        login["refresh_token"],
    ):
        assert forbidden_value not in serialized


def test_audit_h119_retention_registry_keeps_reviewer_but_redacts_session_network_and_receipt(
    tmp_path,
    monkeypatch,
):
    from app.services.auth_service import verify_token
    from app.storage.audit_store import AuditStore

    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client, username="registry-audited-reviewer")
    handoff = client.get(
        "/admin/auth-sessions/retention-handoff",
        headers=_auth(login),
        params={"retention_days": 90},
    ).json()
    recheck = client.post(
        "/admin/auth-sessions/retention-handoff/recheck",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-recheck-request.v1",
            "source_handoff": handoff,
            "source_handoff_sha256": hashlib.sha256(
                json.dumps(handoff, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
    ).json()
    disposition = client.post(
        "/admin/auth-sessions/retention-handoff/review-disposition",
        headers=_auth(login),
        json={
            "contract_version": "auth-session-retention-review-disposition-request.v1",
            "source_recheck_receipt": recheck,
            "source_recheck_receipt_sha256": hashlib.sha256(
                json.dumps(recheck, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "review_disposition": "acknowledged_unchanged",
        },
    ).json()
    claims = verify_token(login["access_token"])
    response = client.post(
        "/admin/auth-sessions/retention-review-dispositions",
        headers={**_auth(login), "User-Agent": "private-h119-reviewer-agent"},
        json={
            "contract_version": "auth-session-retention-review-disposition-record-request.v1",
            "operation_id": "f8c788a7-1d1b-4d09-a1f6-f642e6fd49f1",
            "source_disposition_receipt": disposition,
            "source_disposition_receipt_sha256": hashlib.sha256(
                json.dumps(disposition, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
    )
    entries = AuditStore("system").query(
        filters={"action": "auth_session.retention_registry_create"}
    )
    serialized = json.dumps(entries, ensure_ascii=False)

    assert response.status_code == 201
    assert claims is not None
    assert len(entries) == 1
    assert entries[0]["user_id"] == claims["sub"]
    assert entries[0]["username"] == "registry-audited-reviewer"
    assert entries[0]["user_role"] == "admin"
    assert entries[0]["session_id"] == ""
    assert entries[0]["ip_address"] == ""
    assert entries[0]["user_agent"] == ""
    assert entries[0]["detail"]["operation_id"] == "f8c788a7-1d1b-4d09-a1f6-f642e6fd49f1"
    assert entries[0]["detail"]["replay"] is False
    for forbidden_value in (
        claims["session_id"],
        "private-h119-reviewer-agent",
        login["access_token"],
        login["refresh_token"],
        json.dumps(disposition, ensure_ascii=False),
    ):
        assert forbidden_value not in serialized


def test_audit_403_access_blocked_logged(tmp_path, monkeypatch):
    """Accessing an admin endpoint without admin role logs access.blocked."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    # Register a non-admin member
    client.post("/admin/users", headers=_auth(login), json={
        "username": "member1", "display_name": "Member",
        "email": "m@test.com", "password": "MemberPass1!", "role": "member",
    })
    member_login = client.post("/auth/login", json={"username": "member1", "password": "MemberPass1!"}).json()

    # Member tries to access admin endpoint → 403
    client.get("/admin/audit-logs", headers=_auth(member_login))

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    results = store.query(filters={"action": "access.blocked"})
    assert len(results) >= 1


def test_audit_admin_path_logged(tmp_path, monkeypatch):
    """Any request to /admin/ is audited."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    client.get("/admin/users", headers=_auth(login))

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    # At least one entry for /admin/ path
    all_entries = store.query()
    admin_entries = [e for e in all_entries if "/admin/" in e.get("detail", {}).get("path", "")]
    assert len(admin_entries) >= 1


def test_audit_share_create_and_revoke_logged(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    headers = _auth(login)
    project = client.post(
        "/projects",
        headers=headers,
        json={"name": "공유 감사 프로젝트", "fiscal_year": 2026},
    ).json()
    document = client.post(
        f"/projects/{project['project_id']}/documents",
        headers=headers,
        json={
            "request_id": "req-share-audit",
            "bundle_id": "bid_decision_kr",
            "title": "공유 감사 로그 테스트",
            "docs": [{"doc_type": "go_no_go_memo", "markdown": "# 공유 감사"}],
        },
    ).json()

    created = client.post(
        "/share",
        headers=headers,
        json={
            "request_id": "req-share-audit",
            "title": "공유 감사 로그 테스트",
            "bundle_id": "bid_decision_kr",
            "expires_days": 7,
            "project_id": project["project_id"],
            "project_document_id": document["doc_id"],
        },
    )
    assert created.status_code == 200
    share_id = created.json()["share_id"]

    viewed = client.get(f"/shared/{share_id}")
    assert viewed.status_code == 200

    revoked = client.delete(f"/share/{share_id}", headers=headers)
    assert revoked.status_code == 200

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    create_entries = store.query(filters={"action": "share.create"})
    assert len(create_entries) >= 1
    latest_create = create_entries[0]
    assert latest_create["resource_id"] == share_id
    assert latest_create["detail"]["bundle_type"] == "bid_decision_kr"
    assert latest_create["detail"]["project_id"] == project["project_id"]
    assert latest_create["detail"]["share_project_document_id"] == document["doc_id"]
    assert latest_create["detail"]["share_source_binding_status"] == "current"
    assert latest_create["detail"]["share_post_share_source_changed"] is False

    latest_view = store.query(filters={"action": "share.view"})[0]
    assert latest_view["resource_id"] == share_id
    assert latest_view["detail"]["share_source_binding_status"] == "current"
    assert latest_view["detail"]["share_post_share_source_changed"] is False

    latest_revoke = store.query(filters={"action": "share.revoke"})[0]
    assert latest_revoke["resource_id"] == share_id
    assert latest_revoke["detail"]["project_id"] == project["project_id"]
    assert latest_revoke["detail"]["bundle_type"] == "bid_decision_kr"
    assert latest_revoke["detail"]["share_project_document_id"] == document["doc_id"]
    assert latest_revoke["detail"]["share_revoked_by"] == login["user"]["user_id"]
    assert latest_revoke["detail"]["share_revoked_by_username"] == login["user"]["username"]
    assert latest_revoke["detail"]["share_revoked_at"]


def test_audit_procurement_import_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    pid = client.post("/projects", json={"name": "조달 감사 로그", "fiscal_year": 2026}).json()["project_id"]

    from app.services.g2b_collector import G2BAnnouncement

    fake = G2BAnnouncement(
        bid_number="20260326001-00",
        title="조달 감사 로그 테스트 사업",
        issuer="행정안전부",
        budget="2억원",
        announcement_date="2026-03-26",
        deadline="2026-04-30 18:00",
        bid_type="일반경쟁",
        category="용역",
        detail_url="https://www.g2b.go.kr/notice/20260326001-00",
        attachments=[],
        raw_text="공고 전문",
        source="scrape",
    )

    with patch(
        "app.services.g2b_collector.fetch_announcement_detail",
        new=AsyncMock(return_value=fake),
    ):
        response = client.post(
            f"/projects/{pid}/imports/g2b-opportunity",
            json={"url_or_number": "20260326001-00"},
        )

    assert response.status_code == 200

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    entries = store.query(filters={"action": "procurement.import"})
    assert len(entries) >= 1
    assert entries[0]["result"] == "success"


def test_audit_procurement_downstream_block_logged_with_project_link(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )

    project_store = client.app.state.project_store
    procurement_store = client.app.state.procurement_store
    project = project_store.create("system", "차단 감사 로그 프로젝트")
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-AUDIT-001",
                title="차단 감사 로그 사업",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="eligibility_gap",
                    label="참여 자격",
                    status="fail",
                    blocking=True,
                    reason="필수 실적 미충족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override reason 없이는 downstream 진행 불가",
            ),
        )
    )

    response = client.post(
        "/generate/stream",
        json={
            "title": "blocked proposal",
            "goal": "감사 로그 확인",
            "context": "NO_GO downstream 차단 감사를 확인한다.",
            "bundle_type": "proposal_kr",
            "project_id": project.project_id,
        },
    )
    assert response.status_code == 409

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    entries = store.query(filters={"action": "procurement.downstream_blocked"})
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["result"] == "failure"
    assert latest["resource_type"] == "procurement"
    assert latest["resource_id"] == project.project_id
    assert latest["detail"]["error_code"] == "procurement_override_reason_required"
    assert latest["detail"]["project_id"] == project.project_id
    assert latest["detail"]["bundle_type"] == "proposal_kr"
    assert latest["detail"]["recommendation"] == "NO_GO"


def test_audit_logs_procurement_downstream_resolved_after_override_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )

    project = client.app.state.project_store.create(
        "system",
        "해소 감사 로그 사업",
        fiscal_year=2026,
    )
    procurement_store = client.app.state.procurement_store
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-AUDIT-002",
                title="해소 감사 로그 사업",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="eligibility_gap",
                    label="참여 자격",
                    status="fail",
                    blocking=True,
                    reason="필수 실적 미충족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override reason 저장 후 downstream 진행 가능",
            ),
        )
    )

    override_response = client.post(
        f"/projects/{project.project_id}/procurement/override-reason",
        json={"reason": "전략 고객 유지 목적상 proposal 초안까지 진행"},
        headers=_auth(login),
    )
    assert override_response.status_code == 200

    with client.stream(
        "POST",
        "/generate/stream",
        json={
            "title": "resolved proposal",
            "goal": "감사 로그 해소 확인",
            "context": "NO_GO override 이후 downstream 해소 감사를 확인한다.",
            "bundle_type": "proposal_kr",
            "project_id": project.project_id,
        },
        headers=_auth(login),
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    generate_entries = store.query(filters={"action": "doc.generate"})
    assert len(generate_entries) >= 1
    assert generate_entries[0]["detail"]["project_id"] == project.project_id
    assert generate_entries[0]["detail"]["procurement_operation"] == "override_reason_present"
    entries = store.query(filters={"action": "procurement.downstream_resolved"})
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["result"] == "success"
    assert latest["resource_type"] == "procurement"
    assert latest["resource_id"] == project.project_id
    assert latest["detail"]["project_id"] == project.project_id
    assert latest["detail"]["bundle_type"] == "proposal_kr"
    assert latest["detail"]["recommendation"] == "NO_GO"
    assert latest["detail"]["procurement_operation"] == "override_reason_present"


def test_audit_logs_procurement_remediation_link_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )

    project = client.app.state.project_store.create(
        "system",
        "공유 감사 로그 사업",
        fiscal_year=2026,
    )
    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-AUDIT-003",
                title="공유 감사 로그 사업",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="blocked remediation link copy audit 확인",
            ),
        )
    )

    response = client.post(
        f"/projects/{project.project_id}/procurement/remediation-link-copy",
        json={
            "source": "location_summary",
            "context_kind": "blocked_event",
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        },
        headers=_auth(login),
    )
    assert response.status_code == 200
    assert response.json() == {
        "project_id": project.project_id,
        "project_name": "공유 감사 로그 사업",
        "logged": True,
        "source": "location_summary",
        "context_kind": "blocked_event",
    }

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    entries = store.query(filters={"action": "procurement.remediation_link_copied"})
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["result"] == "success"
    assert latest["resource_type"] == "procurement"
    assert latest["resource_id"] == project.project_id
    assert latest["detail"]["project_id"] == project.project_id
    assert latest["detail"]["bundle_type"] == "proposal_kr"
    assert latest["detail"]["error_code"] == "procurement_override_reason_required"
    assert latest["detail"]["recommendation"] == "NO_GO"
    assert latest["detail"]["procurement_operation"] == "location_summary"
    assert latest["detail"]["procurement_context_kind"] == "blocked_event"


def test_audit_logs_procurement_remediation_link_open(tmp_path, monkeypatch):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    project = client.app.state.project_store.create(
        "system",
        "열람 감사 로그 사업",
        fiscal_year=2026,
    )
    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-AUDIT-004",
                title="열람 감사 로그 사업",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="shared remediation link restore audit 확인",
            ),
        )
    )

    response = client.post(
        f"/projects/{project.project_id}/procurement/remediation-link-open",
        json={
            "source": "url_restore",
            "context_kind": "blocked_event",
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        },
        headers=_auth(login),
    )
    assert response.status_code == 200
    assert response.json() == {
        "project_id": project.project_id,
        "project_name": "열람 감사 로그 사업",
        "logged": True,
        "source": "url_restore",
        "context_kind": "blocked_event",
    }

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    entries = store.query(filters={"action": "procurement.remediation_link_opened"})
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["result"] == "success"
    assert latest["resource_type"] == "procurement"
    assert latest["resource_id"] == project.project_id
    assert latest["detail"]["project_id"] == project.project_id
    assert latest["detail"]["bundle_type"] == "proposal_kr"
    assert latest["detail"]["error_code"] == "procurement_override_reason_required"
    assert latest["detail"]["recommendation"] == "NO_GO"
    assert latest["detail"]["procurement_operation"] == "url_restore"
    assert latest["detail"]["procurement_context_kind"] == "blocked_event"


def test_audit_logs_decision_council_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    project = client.app.state.project_store.create(
        "system",
        "Decision Council 감사 로그 사업",
        fiscal_year=2026,
    )

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )

    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-COUNCIL-AUDIT-001",
                title="Decision Council 감사 로그 사업",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="CONDITIONAL_GO",
                summary="보완 후 진행 가능",
            ),
        )
    )

    response = client.post(
        f"/projects/{project.project_id}/decision-council/run",
        json={"goal": "입찰 방향을 정리한다."},
    )
    assert response.status_code == 200
    session = response.json()

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    entries = store.query(filters={"action": "decision_council.run"})
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["result"] == "success"
    assert latest["resource_type"] == "decision_council"
    assert latest["resource_id"] == session["session_id"]
    assert latest["detail"]["project_id"] == project.project_id
    assert latest["detail"]["decision_council_session_id"] == session["session_id"]
    assert latest["detail"]["decision_council_target_bundle"] == "bid_decision_kr"
    assert latest["detail"]["decision_council_direction"] == "proceed_with_conditions"


def test_audit_logs_decision_council_handoff_used_on_generate(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    project = client.app.state.project_store.create(
        "system",
        "Decision Council handoff 감사 로그",
        fiscal_year=2026,
    )

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )

    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-COUNCIL-AUDIT-002",
                title="Decision Council handoff 감사 로그",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="GO",
                summary="즉시 진행 가능한 상태",
            ),
        )
    )

    council = client.post(
        f"/projects/{project.project_id}/decision-council/run",
        json={"goal": "bid_decision_kr handoff를 확인한다."},
    )
    assert council.status_code == 200
    session = council.json()

    with client.stream(
        "POST",
        "/generate/stream",
        json={
            "title": "Decision Council handoff 감사",
            "goal": "Council handoff 감사 로그 확인",
            "bundle_type": "bid_decision_kr",
            "project_id": project.project_id,
        },
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    generate_entries = store.query(filters={"action": "doc.generate"})
    assert len(generate_entries) >= 1
    assert generate_entries[0]["detail"]["decision_council_handoff_used"] is True
    entries = store.query(filters={"action": "decision_council.handoff_used"})
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["result"] == "success"
    assert latest["resource_type"] == "decision_council"
    assert latest["resource_id"] == session["session_id"]
    assert latest["detail"]["project_id"] == project.project_id
    assert latest["detail"]["bundle_type"] == "bid_decision_kr"
    assert latest["detail"]["decision_council_handoff_used"] is True
    assert latest["detail"]["decision_council_session_revision"] == session["session_revision"]
    assert latest["detail"]["decision_council_direction"] == "proceed"
    assert latest["detail"]["decision_council_target_bundle"] == "bid_decision_kr"
    assert latest["detail"]["decision_council_applied_bundle"] == "bid_decision_kr"


def test_audit_logs_stale_decision_council_skip_reason_on_generate(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    project = client.app.state.project_store.create(
        "system",
        "Decision Council stale skip 감사 로그",
        fiscal_year=2026,
    )

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )

    initial = client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-COUNCIL-AUDIT-STALE-001",
                title="Decision Council stale skip 감사 로그",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="GO",
                summary="초기 recommendation",
            ),
        )
    )

    council = client.post(
        f"/projects/{project.project_id}/decision-council/run",
        json={"goal": "stale council skip를 확인한다."},
    )
    assert council.status_code == 200

    updated = client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-COUNCIL-AUDIT-STALE-001",
                title="Decision Council stale skip 감사 로그",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="업데이트 이후 recommendation",
            ),
        )
    )
    assert updated.updated_at != initial.updated_at

    with client.stream(
        "POST",
        "/generate/stream",
        json={
            "title": "Decision Council stale skip 감사",
            "goal": "stale council skip reason 감사 로그 확인",
            "bundle_type": "bid_decision_kr",
            "project_id": project.project_id,
        },
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    generate_entries = store.query(filters={"action": "doc.generate"})
    assert len(generate_entries) >= 1
    matching = [
        entry for entry in generate_entries
        if entry["detail"].get("decision_council_handoff_skipped_reason") == "stale_procurement_context"
    ]
    assert len(matching) >= 1
    latest = matching[0]
    assert latest["detail"].get("decision_council_handoff_used") is not True


def test_audit_logs_decision_council_handoff_used_on_proposal_generate(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    client = _make_client(tmp_path, monkeypatch)
    project = client.app.state.project_store.create(
        "system",
        "Decision Council proposal 감사 로그",
        fiscal_year=2026,
    )

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )

    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project.project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="PROC-COUNCIL-AUDIT-PROPOSAL-001",
                title="Decision Council proposal 감사 로그",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="CONDITIONAL_GO",
                summary="보완 후 proposal 진행 가능",
            ),
        )
    )

    council = client.post(
        f"/projects/{project.project_id}/decision-council/run",
        json={"goal": "proposal_kr handoff를 확인한다."},
    )
    assert council.status_code == 200
    session = council.json()

    with client.stream(
        "POST",
        "/generate/stream",
        json={
            "title": "Decision Council proposal 감사",
            "goal": "Council handoff proposal 감사 로그 확인",
            "bundle_type": "proposal_kr",
            "project_id": project.project_id,
        },
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    generate_entries = store.query(filters={"action": "doc.generate"})
    matching_generate = [
        entry for entry in generate_entries
        if entry["detail"].get("project_id") == project.project_id
        and entry["detail"].get("bundle_type") == "proposal_kr"
    ]
    assert matching_generate
    assert matching_generate[0]["detail"]["decision_council_handoff_used"] is True
    assert matching_generate[0]["detail"]["decision_council_target_bundle"] == "bid_decision_kr"
    assert matching_generate[0]["detail"]["decision_council_applied_bundle"] == "proposal_kr"

    entries = store.query(filters={"action": "decision_council.handoff_used"})
    matching = [
        entry for entry in entries
        if entry["detail"].get("project_id") == project.project_id
        and entry["detail"].get("bundle_type") == "proposal_kr"
    ]
    assert matching
    latest = matching[0]
    assert latest["resource_type"] == "decision_council"
    assert latest["resource_id"] == session["session_id"]
    assert latest["detail"]["decision_council_target_bundle"] == "bid_decision_kr"
    assert latest["detail"]["decision_council_applied_bundle"] == "proposal_kr"


# ── API endpoint tests ─────────────────────────────────────────────────────────


def test_api_audit_logs_admin_only(tmp_path, monkeypatch):
    """GET /admin/audit-logs requires admin role."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    # Register member
    client.post("/admin/users", headers=_auth(login), json={
        "username": "viewer1", "display_name": "Viewer",
        "email": "v@test.com", "password": "ViewerPass1!", "role": "viewer",
    })
    viewer_login = client.post("/auth/login", json={"username": "viewer1", "password": "ViewerPass1!"}).json()
    res = client.get("/admin/audit-logs", headers=_auth(viewer_login))
    assert res.status_code == 403


def test_api_audit_logs_returns_logs(tmp_path, monkeypatch):
    """Admin can query audit logs."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    # Generate some audit entries via login
    client.post("/auth/login", json={"username": "admin", "password": "AdminPass1!"})

    res = client.get("/admin/audit-logs", headers=_auth(login))
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert "total" in data
    assert isinstance(data["logs"], list)


def test_api_audit_logs_filter_by_action(tmp_path, monkeypatch):
    """Admin can filter audit logs by action."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res = client.get(
        "/admin/audit-logs",
        params={"action": "user.login", "date_from": today, "date_to": today},
        headers=_auth(login),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["logs"]
    assert all(log["action"] == "user.login" for log in data["logs"])


def test_api_audit_logs_paginates_filtered_results(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    from app.storage.audit_store import AuditStore

    store = AuditStore("system")
    for index in range(55):
        store.append(_make_audit_log(
            tenant_id="system",
            action="report_quality.pilot_export",
            user_id=f"quality-owner-{index}",
        ))

    first = client.get(
        "/admin/audit-logs",
        params={"action": "report_quality.pilot_export", "offset": 0, "limit": 50},
        headers=_auth(login),
    )
    second = client.get(
        "/admin/audit-logs",
        params={"action": "report_quality.pilot_export", "offset": 50, "limit": 50},
        headers=_auth(login),
    )

    assert first.status_code == 200
    assert first.json()["total"] == 55
    assert first.json()["offset"] == 0
    assert first.json()["limit"] == 50
    assert first.json()["has_more"] is True
    assert len(first.json()["logs"]) == 50

    assert second.status_code == 200
    assert second.json()["total"] == 55
    assert second.json()["offset"] == 50
    assert second.json()["has_more"] is False
    assert len(second.json()["logs"]) == 5

    assert client.get(
        "/admin/audit-logs",
        params={"offset": -1, "limit": 50},
        headers=_auth(login),
    ).status_code == 422
    assert client.get(
        "/admin/audit-logs",
        params={"offset": 0, "limit": 1001},
        headers=_auth(login),
    ).status_code == 422


def test_api_audit_stats(tmp_path, monkeypatch):
    """GET /admin/audit-logs/stats returns summary dict."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    res = client.get("/admin/audit-logs/stats", headers=_auth(login))
    assert res.status_code == 200
    data = res.json()
    assert "total_actions" in data
    assert "by_action_type" in data
    assert "failed_count" in data
    assert "blocked_count" in data


def test_api_audit_export_csv(tmp_path, monkeypatch):
    """GET /admin/audit-logs/export returns CSV content."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    res = client.get(
        f"/admin/audit-logs/export?date_from={yesterday}&date_to={today}",
        headers=_auth(login),
    )
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert rows
    assert "detail_json" in rows[0]


def test_api_audit_export_csv_filters_pilot_evidence(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    store.append(_make_audit_log(
        tenant_id="system",
        action="report_quality.pilot_export",
        result="success",
        detail={
            "request_id": "pilot-request-api",
            "pilot_sha256": "b" * 64,
            "pilot_artifact_count": 4,
            "pilot_preview_verified": True,
        },
    ))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res = client.get(
        "/admin/audit-logs/export",
        params={
            "date_from": today,
            "date_to": today,
            "action": "report_quality.pilot_export",
            "result": "success",
        },
        headers=_auth(login),
    )

    assert res.status_code == 200
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert len(rows) == 1
    assert rows[0]["request_id"] == "pilot-request-api"
    assert rows[0]["pilot_sha256"] == "b" * 64
    assert rows[0]["pilot_artifact_count"] == "4"
    assert rows[0]["pilot_preview_verified"] == "True"


def test_api_audit_failed_logins(tmp_path, monkeypatch):
    """GET /admin/audit-logs/failed-logins returns failure analysis."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    # Generate some failed logins
    for _ in range(3):
        client.post("/auth/login", json={"username": "admin", "password": "WrongPass!"})

    res = client.get("/admin/audit-logs/failed-logins", headers=_auth(login))
    assert res.status_code == 200
    data = res.json()
    assert "total_failures" in data
    assert "unique_ips" in data
    assert "suspicious_ips" in data
    assert data["total_failures"] >= 3


def test_api_audit_failed_logins_suspicious_ip(tmp_path, monkeypatch):
    """IPs with 5+ failures appear in suspicious_ips list."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)

    # Directly append 6 failed logins from the same IP via AuditStore
    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    for _ in range(6):
        store.append(_make_audit_log(
            tenant_id="system", action="user.login_fail",
            result="blocked", ip="5.5.5.5",
        ))

    res = client.get("/admin/audit-logs/failed-logins?hours=24", headers=_auth(login))
    data = res.json()
    suspicious = [s["ip"] for s in data["suspicious_ips"]]
    assert "5.5.5.5" in suspicious

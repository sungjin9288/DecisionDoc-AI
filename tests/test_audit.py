"""tests/test_audit.py — Tests for the ISMS audit logging system.

Coverage (24 tests):
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

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
                    session_id="sess1", **kwargs):
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
        detail={},
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
    entries = store.query("tenant1")
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
    results = store.query("t1", filters={"action": "user.login"})
    assert len(results) == 2
    assert all(r["action"] == "user.login" for r in results)


def test_audit_store_query_filter_by_user(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", user_id="u1"))
    store.append(_make_audit_log(tenant_id="t1", user_id="u2"))
    results = store.query("t1", filters={"user_id": "u1"})
    assert len(results) == 1
    assert results[0]["user_id"] == "u1"


def test_audit_store_query_filter_by_result(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", result="success"))
    store.append(_make_audit_log(tenant_id="t1", result="blocked"))
    store.append(_make_audit_log(tenant_id="t1", result="blocked"))
    results = store.query("t1", filters={"result": "blocked"})
    assert len(results) == 2


def test_audit_store_query_filter_by_date(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    import uuid
    from app.storage.audit_store import AuditLog
    store = AuditStore("t1")

    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    new_ts = datetime.now(timezone.utc).isoformat()

    def _log_at(ts):
        from dataclasses import asdict
        log = _make_audit_log(tenant_id="t1")
        d = asdict(log)
        d["timestamp"] = ts
        line = json.dumps(d) + "\n"
        with store._path.open("a") as f:
            f.write(line)

    _log_at(old_ts)
    _log_at(new_ts)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    results = store.query("t1", filters={"date_from": cutoff})
    assert len(results) == 1
    assert results[0]["timestamp"] >= cutoff


def test_audit_store_query_filter_by_ip(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", ip="10.0.0.1"))
    store.append(_make_audit_log(tenant_id="t1", ip="10.0.0.2"))
    results = store.query("t1", filters={"ip_address": "10.0.0.1"})
    assert len(results) == 1
    assert results[0]["ip_address"] == "10.0.0.1"


def test_audit_store_get_failed_logins(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", action="user.login_fail"))
    store.append(_make_audit_log(tenant_id="t1", action="user.login"))
    store.append(_make_audit_log(tenant_id="t1", action="user.login_fail"))
    results = store.get_failed_logins("t1", hours=24)
    assert len(results) == 2
    assert all(r["action"] == "user.login_fail" for r in results)


def test_audit_store_get_user_activity(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    store.append(_make_audit_log(tenant_id="t1", user_id="u1"))
    store.append(_make_audit_log(tenant_id="t1", user_id="u2"))
    store.append(_make_audit_log(tenant_id="t1", user_id="u1"))
    results = store.get_user_activity("t1", "u1", days=30)
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
    stats = store.get_stats("t1", days=30)
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
    csv_str = store.export_csv("t1", date_from, date_to)
    assert "log_id" in csv_str  # header present
    assert "user.login" in csv_str
    assert "alice" in csv_str


def test_audit_store_corrupted_line_recovery(tmp_path):
    """Corrupted JSONL lines are skipped; a corruption event is appended."""
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.audit_store import AuditStore
    store = AuditStore("t1")
    # Write a valid line then a corrupt line
    log = _make_audit_log(tenant_id="t1", action="user.login")
    from dataclasses import asdict
    store._path.write_text(
        json.dumps(asdict(log)) + "\n" + "NOT VALID JSON{{{\n"
    )
    entries = store._read_all()
    # Only the valid entry plus the auto-appended corruption event
    assert len(entries) >= 1
    actions = [e["action"] for e in entries]
    assert "user.login" in actions


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

    capped_results = store.query("t1")
    assert len(capped_results) == 1000
    assert all(entry["resource_id"] != "project-a" for entry in capped_results)

    latest_entry = store.find_latest_entry(
        "t1",
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

    assert len(store.query("t1")) == 1000
    assert len(store.query_all("t1")) == 1002


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


def test_resolve_action_procurement_import():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/imports/g2b-opportunity", 200) == "procurement.import"


def test_resolve_action_procurement_evaluate():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/procurement/evaluate", 200) == "procurement.evaluate"


def test_resolve_action_procurement_recommend():
    from app.middleware.audit import _resolve_action
    assert _resolve_action("POST", "/projects/proj-1/procurement/recommend", 200) == "procurement.recommend"


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
        decision_council_handoff_used=True,
    ) == ["procurement.downstream_resolved", "decision_council.handoff_used"]


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
    results = store.query("system", filters={"action": "user.login"})
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
    results = store.query("system", filters={"action": "user.login_fail"})
    assert len(results) >= 1
    assert results[0]["result"] == "blocked"


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
    results = store.query("system", filters={"action": "access.blocked"})
    assert len(results) >= 1


def test_audit_admin_path_logged(tmp_path, monkeypatch):
    """Any request to /admin/ is audited."""
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    client.get("/admin/users", headers=_auth(login))

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    # At least one entry for /admin/ path
    all_entries = store.query("system")
    admin_entries = [e for e in all_entries if "/admin/" in e.get("detail", {}).get("path", "")]
    assert len(admin_entries) >= 1


def test_audit_share_create_and_revoke_logged(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    headers = _auth(login)

    created = client.post(
        "/share",
        headers=headers,
        json={
            "request_id": "req-share-audit",
            "title": "공유 감사 로그 테스트",
            "bundle_id": "bid_decision_kr",
            "expires_days": 7,
            "project_id": "proj-share-audit",
            "project_document_id": "doc-share-audit",
            "decision_council_document_status": "stale_procurement",
            "decision_council_document_status_tone": "danger",
            "decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
            "decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 이 공유 문서는 최신 council/procurement 기준과 일치하지 않습니다.",
        },
    )
    assert created.status_code == 200
    share_id = created.json()["share_id"]

    revoked = client.delete(f"/share/{share_id}", headers=headers)
    assert revoked.status_code == 200

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    create_entries = store.query("system", filters={"action": "share.create"})
    assert len(create_entries) >= 1
    latest_create = create_entries[0]
    assert latest_create["detail"]["bundle_type"] == "bid_decision_kr"
    assert latest_create["detail"]["project_id"] == "proj-share-audit"
    assert latest_create["detail"]["share_project_document_id"] == "doc-share-audit"
    assert latest_create["detail"]["share_decision_council_document_status"] == "stale_procurement"
    assert latest_create["detail"]["share_decision_council_document_status_tone"] == "danger"
    assert latest_create["detail"]["share_decision_council_document_status_copy"] == "현재 procurement 대비 이전 council 기준"
    assert len(store.query("system", filters={"action": "share.revoke"})) >= 1


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
    entries = store.query("system", filters={"action": "procurement.import"})
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
    entries = store.query("system", filters={"action": "procurement.downstream_blocked"})
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
    generate_entries = store.query("system", filters={"action": "doc.generate"})
    assert len(generate_entries) >= 1
    assert generate_entries[0]["detail"]["project_id"] == project.project_id
    assert generate_entries[0]["detail"]["procurement_operation"] == "override_reason_present"
    entries = store.query("system", filters={"action": "procurement.downstream_resolved"})
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
    entries = store.query("system", filters={"action": "procurement.remediation_link_copied"})
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
    entries = store.query("system", filters={"action": "procurement.remediation_link_opened"})
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
    entries = store.query("system", filters={"action": "decision_council.run"})
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
    generate_entries = store.query("system", filters={"action": "doc.generate"})
    assert len(generate_entries) >= 1
    assert generate_entries[0]["detail"]["decision_council_handoff_used"] is True
    entries = store.query("system", filters={"action": "decision_council.handoff_used"})
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
    generate_entries = store.query("system", filters={"action": "doc.generate"})
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
    generate_entries = store.query("system", filters={"action": "doc.generate"})
    matching_generate = [
        entry for entry in generate_entries
        if entry["detail"].get("project_id") == project.project_id
        and entry["detail"].get("bundle_type") == "proposal_kr"
    ]
    assert matching_generate
    assert matching_generate[0]["detail"]["decision_council_handoff_used"] is True
    assert matching_generate[0]["detail"]["decision_council_target_bundle"] == "bid_decision_kr"
    assert matching_generate[0]["detail"]["decision_council_applied_bundle"] == "proposal_kr"

    entries = store.query("system", filters={"action": "decision_council.handoff_used"})
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

    res = client.get("/admin/audit-logs?action=user.login", headers=_auth(login))
    assert res.status_code == 200
    data = res.json()
    assert all(log["action"] == "user.login" for log in data["logs"])


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
    assert "log_id" in res.text  # CSV header


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

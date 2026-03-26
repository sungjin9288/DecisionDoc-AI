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


# ── Client helpers ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-audit-tests-x32")
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
        },
    )
    assert created.status_code == 200
    share_id = created.json()["share_id"]

    revoked = client.delete(f"/share/{share_id}", headers=headers)
    assert revoked.status_code == 200

    from app.storage.audit_store import AuditStore
    store = AuditStore("system")
    assert len(store.query("system", filters={"action": "share.create"})) >= 1
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

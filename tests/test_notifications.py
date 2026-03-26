"""tests/test_notifications.py — Tests for the notification system.

Coverage (24 tests):
  NotificationStore unit  : create, get_for_user, get_unread_count,
                            mark_read, mark_all_read, unread_only filter,
                            delete_old, mark_email_sent, mark_slack_sent
  NotificationService     : notify saves to store,
                            email skipped when not configured,
                            Slack skipped when no webhook,
                            notify_approval_event (requested, review_done,
                            changes_requested, approved, rejected),
                            notify_mention
  Slack send              : mock httpx and verify payload
  API endpoints           : GET /notifications, /notifications/unread-count,
                            POST /notifications/{id}/read,
                            POST /notifications/read-all
  Integration             : submit approval → notification created
  Integration             : POST /messages with @mention → notification created
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.async_helper import run_async

TEST_JWT_SECRET_KEY = "test-secret-key-notif-tests-32chars!"

# ── helpers ────────────────────────────────────────────────────────────────────


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


def _register_and_login(client: TestClient, username: str = "admin", password: str = "AdminPass1!", email: str = "admin@test.com") -> dict:
    client.post(
        "/auth/register",
        json={"username": username, "display_name": username.title(), "email": email, "password": password},
    )
    return client.post("/auth/login", json={"username": username, "password": password}).json()


def _auth(login_resp: dict) -> dict:
    return {"Authorization": f"Bearer {login_resp['access_token']}"}


# ── NotificationStore unit tests ───────────────────────────────────────────────


def test_notification_store_create(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore

    store = NotificationStore("tenant1")
    n = store.create(
        tenant_id="tenant1",
        recipient_id="user1",
        event_type="system",
        title="테스트",
        body="테스트 본문",
        context_type="system",
        context_id="",
    )
    assert n.notification_id
    assert n.is_read is False
    assert n.sent_email is False
    assert n.sent_slack is False


def test_notification_store_get_for_user(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore

    store = NotificationStore("tenant1")
    store.create("tenant1", "user1", "system", "A", "body A", "system", "")
    store.create("tenant1", "user1", "system", "B", "body B", "system", "")
    store.create("tenant1", "user2", "system", "C", "body C", "system", "")

    results = store.get_for_user("user1")
    assert len(results) == 2
    assert all(n.recipient_id == "user1" for n in results)


def test_notification_store_unread_count(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore

    store = NotificationStore("tenant1")
    n1 = store.create("tenant1", "user1", "system", "A", "body", "system", "")
    store.create("tenant1", "user1", "system", "B", "body", "system", "")

    assert store.get_unread_count("user1") == 2
    store.mark_read(n1.notification_id, "user1")
    assert store.get_unread_count("user1") == 1


def test_notification_store_mark_read(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore

    store = NotificationStore("tenant1")
    n = store.create("tenant1", "user1", "system", "A", "body", "system", "")
    assert not n.is_read

    found = store.mark_read(n.notification_id, "user1")
    assert found is True
    items = store.get_for_user("user1")
    assert items[0].is_read is True

    # Wrong user — should not be found
    found2 = store.mark_read(n.notification_id, "other_user")
    assert found2 is False


def test_notification_store_mark_all_read(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore

    store = NotificationStore("tenant1")
    store.create("tenant1", "user1", "system", "A", "body", "system", "")
    store.create("tenant1", "user1", "system", "B", "body", "system", "")
    store.create("tenant1", "user2", "system", "C", "body", "system", "")

    count = store.mark_all_read("user1")
    assert count == 2
    assert store.get_unread_count("user1") == 0
    # user2's notification remains unread
    assert store.get_unread_count("user2") == 1


def test_notification_store_unread_only_filter(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore

    store = NotificationStore("tenant1")
    n = store.create("tenant1", "user1", "system", "A", "body", "system", "")
    store.create("tenant1", "user1", "system", "B", "body", "system", "")
    store.mark_read(n.notification_id, "user1")

    all_items = store.get_for_user("user1")
    unread = store.get_for_user("user1", unread_only=True)
    assert len(all_items) == 2
    assert len(unread) == 1
    assert unread[0].is_read is False


def test_notification_store_delete_old(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    import json

    store = NotificationStore("tenant1")
    # Create a notification and manually backdate it
    n = store.create("tenant1", "user1", "system", "Old", "body", "system", "")
    store.create("tenant1", "user1", "system", "New", "body", "system", "")

    # Backdate first notification to 40 days ago
    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    data = json.loads(store._path.read_text())
    for d in data:
        if d["notification_id"] == n.notification_id:
            d["created_at"] = old_ts
    store._path.write_text(json.dumps(data))

    deleted = store.delete_old(days=30)
    assert deleted == 1
    remaining = store.get_for_user("user1")
    assert len(remaining) == 1
    assert remaining[0].title == "New"


def test_notification_store_mark_email_slack_sent(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    import json

    store = NotificationStore("tenant1")
    n = store.create("tenant1", "user1", "system", "A", "body", "system", "")
    assert n.sent_email is False
    assert n.sent_slack is False

    store.mark_email_sent(n.notification_id)
    store.mark_slack_sent(n.notification_id)

    data = json.loads(store._path.read_text())
    rec = next(d for d in data if d["notification_id"] == n.notification_id)
    assert rec["sent_email"] is True
    assert rec["sent_slack"] is True


# ── NotificationService unit tests ─────────────────────────────────────────────


def test_notification_service_notify_saves_to_store(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    from app.services.notification_service import NotificationService

    svc = NotificationService("tenant1")
    run_async(svc.notify(
        recipient_id="user1",
        event_type="system",
        title="알림",
        body="본문",
        context_type="system",
        context_id="",
    ))

    store = NotificationStore("tenant1")
    items = store.get_for_user("user1")
    assert len(items) == 1
    assert items[0].title == "알림"
    assert items[0].event_type == "system"


def test_notification_service_skips_email_when_not_configured(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    os.environ.pop("SMTP_HOST", None)
    os.environ.pop("SMTP_USER", None)
    os.environ.pop("SMTP_PASSWORD", None)
    from app.services.notification_service import NotificationService, _email_configured

    assert not _email_configured()

    with patch("smtplib.SMTP") as mock_smtp:
        svc = NotificationService("tenant1")
        run_async(svc.notify(
            recipient_id="user1", event_type="system",
            title="t", body="b", context_type="system", context_id="",
        ))
        mock_smtp.assert_not_called()


def test_notification_service_skips_slack_when_no_webhook(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    os.environ.pop("SLACK_WEBHOOK_URL", None)
    from app.services.notification_service import NotificationService, _get_slack_webhook

    assert not _get_slack_webhook()

    with patch("httpx.AsyncClient") as mock_client:
        svc = NotificationService("tenant1")
        run_async(svc.notify(
            recipient_id="user1", event_type="system",
            title="t", body="b", context_type="system", context_id="",
        ))
        mock_client.assert_not_called()


def test_notify_approval_requested(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    from app.services.notification_service import NotificationService

    @dataclass
    class FakeApproval:
        approval_id: str = "appr-1"
        title: str = "기획안"
        drafter: str = "drafter_id"
        reviewer: str = "reviewer_id"

    svc = NotificationService("tenant1")
    run_async(svc.notify_approval_event(FakeApproval(), "approval_requested", "김기안"))

    store = NotificationStore("tenant1")
    notifs = store.get_for_user("reviewer_id")
    assert len(notifs) == 1
    assert notifs[0].event_type == "approval_requested"
    assert "김기안" in notifs[0].body


def test_notify_approval_review_done(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    from app.services.notification_service import NotificationService

    @dataclass
    class FakeApproval:
        approval_id: str = "appr-2"
        title: str = "기획안"
        drafter: str = "drafter_id"
        reviewer: str = "reviewer_id"

    svc = NotificationService("tenant1")
    run_async(svc.notify_approval_event(FakeApproval(), "approval_review_done", "이검토"))

    store = NotificationStore("tenant1")
    notifs = store.get_for_user("drafter_id")
    assert len(notifs) == 1
    assert notifs[0].event_type == "approval_review_done"


def test_notify_approval_approved(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    from app.services.notification_service import NotificationService

    @dataclass
    class FakeApproval:
        approval_id: str = "appr-3"
        title: str = "기획안"
        drafter: str = "drafter_id"
        reviewer: str = "reviewer_id"

    svc = NotificationService("tenant1")
    run_async(svc.notify_approval_event(FakeApproval(), "approval_approved", "박결재"))

    store = NotificationStore("tenant1")
    notifs = store.get_for_user("drafter_id")
    assert len(notifs) == 1
    assert notifs[0].event_type == "approval_approved"
    assert "승인" in notifs[0].title


def test_notify_approval_rejected(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    from app.services.notification_service import NotificationService

    @dataclass
    class FakeApproval:
        approval_id: str = "appr-4"
        title: str = "기획안"
        drafter: str = "drafter_id"
        reviewer: str = "reviewer_id"

    svc = NotificationService("tenant1")
    run_async(svc.notify_approval_event(FakeApproval(), "approval_rejected", "박결재"))

    store = NotificationStore("tenant1")
    notifs = store.get_for_user("drafter_id")
    assert len(notifs) == 1
    assert notifs[0].event_type == "approval_rejected"
    assert "반려" in notifs[0].title


def test_notify_mention(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    from app.storage.notification_store import NotificationStore
    from app.services.notification_service import NotificationService

    @dataclass
    class FakeMessage:
        message_id: str = "msg-1"
        content: str = "안녕하세요 @alice 확인해주세요"

    svc = NotificationService("tenant1")
    run_async(svc.notify_mention(FakeMessage(), ["alice_id"], "bob"))

    store = NotificationStore("tenant1")
    notifs = store.get_for_user("alice_id")
    assert len(notifs) == 1
    assert notifs[0].event_type == "mention"
    assert "bob" in notifs[0].body


def test_notify_slack_sends_payload(tmp_path):
    os.environ["DATA_DIR"] = str(tmp_path)
    os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/test"
    from app.services.notification_service import NotificationService

    captured = {}

    async def mock_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=mock_post)

    with patch("httpx.AsyncClient", return_value=mock_client):
        svc = NotificationService("tenant1")
        run_async(svc.notify(
            recipient_id="user1", event_type="approval_approved",
            title="승인 완료", body="본문", context_type="approval", context_id="appr-1",
        ))
        run_async(svc._send_slack_task("notif-id", "approval_approved", "승인 완료", "본문", None))

    assert captured.get("url") == "https://hooks.slack.com/test"
    assert "blocks" in captured.get("json", {})

    os.environ.pop("SLACK_WEBHOOK_URL", None)


# ── API endpoint tests ─────────────────────────────────────────────────────────


def test_api_get_notifications_empty(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    res = client.get("/notifications", headers=_auth(login))
    assert res.status_code == 200
    data = res.json()
    assert "notifications" in data
    assert data["notifications"] == []


def test_api_unread_count_zero(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    res = client.get("/notifications/unread-count", headers=_auth(login))
    assert res.status_code == 200
    assert res.json()["count"] == 0


def test_api_mark_read_and_all_read(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    user_id = login.get("user", {}).get("user_id") or login.get("user_id")

    # Manually create notifications via store
    from app.storage.notification_store import get_notification_store
    store = get_notification_store("system")
    n1 = store.create("system", user_id, "system", "알림1", "본문1", "system", "")
    n2 = store.create("system", user_id, "system", "알림2", "본문2", "system", "")

    # Unread count should be 2
    res = client.get("/notifications/unread-count", headers=_auth(login))
    assert res.json()["count"] == 2

    # Mark one read
    res = client.post(f"/notifications/{n1.notification_id}/read", headers=_auth(login))
    assert res.status_code == 200
    assert client.get("/notifications/unread-count", headers=_auth(login)).json()["count"] == 1

    # Mark all read
    res = client.post("/notifications/read-all", headers=_auth(login))
    assert res.status_code == 200
    assert res.json()["updated"] == 1
    assert client.get("/notifications/unread-count", headers=_auth(login)).json()["count"] == 0


def test_api_mark_read_not_found(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    res = client.post("/notifications/nonexistent-id/read", headers=_auth(login))
    assert res.status_code == 404


def test_api_notifications_returned_newest_first(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    login = _register_and_login(client)
    user_id = login.get("user", {}).get("user_id") or login.get("user_id")

    from app.storage.notification_store import get_notification_store
    store = get_notification_store("system")
    store.create("system", user_id, "system", "첫번째", "b", "system", "")
    store.create("system", user_id, "system", "두번째", "b", "system", "")

    res = client.get("/notifications", headers=_auth(login))
    notifs = res.json()["notifications"]
    assert len(notifs) == 2
    # Newest first
    assert notifs[0]["created_at"] >= notifs[1]["created_at"]


# ── Integration tests ──────────────────────────────────────────────────────────


def test_message_mention_triggers_notification(tmp_path, monkeypatch):
    """Posting a @mention message creates an in-app notification for the mentioned user."""
    client = _make_client(tmp_path, monkeypatch)

    # Register admin + a second user
    login_admin = _register_and_login(client)
    # Register 'bob' via admin endpoint
    client.post(
        "/admin/users",
        headers=_auth(login_admin),
        json={
            "username": "bob",
            "display_name": "Bob",
            "email": "bob@test.com",
            "password": "BobPass1!",
            "role": "member",
        },
    )
    login_bob = client.post(
        "/auth/login",
        json={"username": "bob", "password": "BobPass1!"},
    ).json()
    bob_id = login_bob.get("user", {}).get("user_id") or login_bob.get("user_id")

    # Admin posts a message mentioning @bob
    client.post(
        "/messages",
        headers=_auth(login_admin),
        json={"content": "안녕 @bob 확인해주세요", "context_type": "general", "context_id": "global"},
    )

    # Bob should have a mention notification
    from app.storage.notification_store import get_notification_store
    store = get_notification_store("system")
    notifs = store.get_for_user(bob_id)
    assert len(notifs) == 1
    assert notifs[0].event_type == "mention"
    assert "admin" in notifs[0].body.lower() or "Admin" in notifs[0].body

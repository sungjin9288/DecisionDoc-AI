from __future__ import annotations

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.message_store import MessageStore, MessageStoreError, get_message_store
from app.storage.notification_store import NotificationStore, NotificationStoreError
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    """Expose lost updates when independent stores do not share a lock."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}


def _s3_backend(
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _notification_record(
    notification_id: str,
    *,
    tenant_id: str = "alpha",
) -> dict:
    return {
        "notification_id": notification_id,
        "tenant_id": tenant_id,
        "recipient_id": "user-1",
        "event_type": "system",
        "title": "Notification",
        "body": "Body",
        "context_type": "system",
        "context_id": "context-1",
        "is_read": False,
        "created_at": "2026-07-16T00:00:00+00:00",
        "sent_email": False,
        "sent_slack": False,
    }


def _message_record(message_id: str, *, tenant_id: str = "alpha") -> dict:
    return {
        "message_id": message_id,
        "tenant_id": tenant_id,
        "author_id": "user-1",
        "author_name": "Alice",
        "content": "Message",
        "mentions": [],
        "context_type": "general",
        "context_id": "global",
        "created_at": "2026-07-16T00:00:00+00:00",
        "edited_at": None,
        "is_deleted": False,
    }


@pytest.mark.parametrize("store_type", [MessageStore, NotificationStore])
@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_collaboration_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    store_type: type[MessageStore] | type[NotificationStore],
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store_type(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_collaboration_state_read_has_no_side_effect(tmp_path: Path) -> None:
    message_store = MessageStore("alpha", data_dir=tmp_path)
    notification_store = NotificationStore("alpha", data_dir=tmp_path)

    assert message_store.get_thread("general", "global") == []
    assert notification_store.get_for_user("user-1") == []
    assert not message_store._path.exists()
    assert not notification_store._path.exists()


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("", "Invalid message state document"),
        ("{not-json", "Invalid message state document"),
        ("{}", "Invalid message state document"),
        ("[null]", "Invalid message record"),
        (
            '[{"message_id":"first","message_id":"second"}]',
            "Invalid message state document",
        ),
        (
            json.dumps([{**_message_record("invalid"), "mentions": "user-1"}]),
            "Invalid message mentions",
        ),
        (
            json.dumps([_message_record("duplicate"), _message_record("duplicate")]),
            "Duplicate message identity",
        ),
    ],
)
def test_untrusted_message_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: str,
    error: str,
) -> None:
    path = tmp_path / "tenants/alpha/messages.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = MessageStore("alpha", data_dir=tmp_path)

    with pytest.raises(MessageStoreError, match=error):
        store.get_thread("general", "global")
    with pytest.raises(MessageStoreError, match=error):
        store.post("user-1", "Alice", "New", "general", "global")

    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("", "Invalid notification state document"),
        ("{not-json", "Invalid notification state document"),
        ("{}", "Invalid notification state document"),
        ("[null]", "Invalid notification record"),
        (
            '[{"notification_id":"first","notification_id":"second"}]',
            "Invalid notification state document",
        ),
        (
            json.dumps([{**_notification_record("invalid"), "is_read": "false"}]),
            "Invalid notification delivery state",
        ),
        (
            json.dumps(
                [
                    _notification_record("duplicate"),
                    _notification_record("duplicate"),
                ]
            ),
            "Duplicate notification identity",
        ),
    ],
)
def test_untrusted_notification_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: str,
    error: str,
) -> None:
    path = tmp_path / "tenants/alpha/notifications.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = NotificationStore("alpha", data_dir=tmp_path)

    with pytest.raises(NotificationStoreError, match=error):
        store.get_for_user("user-1")
    with pytest.raises(NotificationStoreError, match=error):
        store.create("user-1", "system", "New", "Body", "system", "context-1")

    assert path.read_bytes() == original_bytes


def test_foreign_collaboration_records_remain_hidden_and_preserved(
    tmp_path: Path,
) -> None:
    message_path = tmp_path / "tenants/alpha/messages.json"
    notification_path = tmp_path / "tenants/alpha/notifications.json"
    message_path.parent.mkdir(parents=True)
    message_path.write_text(
        json.dumps([_message_record("foreign-message", tenant_id="beta")]),
        encoding="utf-8",
    )
    notification_path.write_text(
        json.dumps([_notification_record("foreign-notification", tenant_id="beta")]),
        encoding="utf-8",
    )

    message_store = MessageStore("alpha", data_dir=tmp_path)
    notification_store = NotificationStore("alpha", data_dir=tmp_path)
    message_store.post("user-1", "Alice", "Owned", "general", "global")
    notification_store.create(
        "user-1", "system", "Owned", "Body", "system", "context-1"
    )

    assert [item.content for item in message_store.get_thread("general", "global")] == [
        "Owned"
    ]
    assert [item.title for item in notification_store.get_for_user("user-1")] == [
        "Owned"
    ]
    assert (
        json.loads(message_path.read_text(encoding="utf-8"))[0]["tenant_id"] == "beta"
    )
    assert (
        json.loads(notification_path.read_text(encoding="utf-8"))[0]["tenant_id"]
        == "beta"
    )


def test_invalid_caller_records_are_rejected_before_write(tmp_path: Path) -> None:
    message_store = MessageStore("alpha", data_dir=tmp_path)
    notification_store = NotificationStore("alpha", data_dir=tmp_path)

    with pytest.raises(MessageStoreError, match="Invalid message record"):
        message_store.post(None, "Alice", "Message", "general", "global")
    with pytest.raises(NotificationStoreError, match="Invalid notification record"):
        notification_store.create(
            "user-1", "system", None, "Body", "system", "context-1"
        )

    assert not message_store._path.exists()
    assert not notification_store._path.exists()


def test_independent_local_message_stores_preserve_concurrent_posts(
    tmp_path: Path,
) -> None:
    stores = [
        MessageStore("alpha", data_dir=tmp_path, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]

    def post(index: int) -> None:
        stores[index].post("user-1", "Alice", f"Message {index}", "general", "global")

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(post, range(20)))

    messages = MessageStore("alpha", data_dir=tmp_path).get_thread(
        "general", "global", limit=50
    )
    assert {message.content for message in messages} == {
        f"Message {index}" for index in range(20)
    }


def test_independent_local_notification_stores_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    stores = [
        NotificationStore(
            "alpha",
            data_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def create(index: int) -> None:
        stores[index].create(
            "user-1", "system", f"Notification {index}", "Body", "system", "context-1"
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(create, range(20)))

    notifications = NotificationStore("alpha", data_dir=tmp_path).get_for_user("user-1")
    assert {notification.title for notification in notifications} == {
        f"Notification {index}" for index in range(20)
    }


def test_message_and_notification_round_trip_through_fake_s3() -> None:
    backend, client = _s3_backend()
    message_store = MessageStore("alpha", data_dir="/virtual/data", backend=backend)
    notification_store = NotificationStore(
        "alpha", data_dir=Path("/virtual/data"), backend=backend
    )

    message_store.post("user-1", "Alice", "S3 message", "general", "global")
    notification_store.create(
        "user-1", "system", "S3 notification", "Body", "system", "context-1"
    )

    message_key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/messages.json",
    )
    notification_key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/notifications.json",
    )
    assert message_key in client.objects
    assert notification_key in client.objects
    messages = MessageStore(
        "alpha", data_dir="/virtual/data", backend=backend
    ).get_thread("general", "global")
    notifications = NotificationStore(
        "alpha", data_dir=Path("/virtual/data"), backend=backend
    ).get_for_user("user-1")
    assert [message.content for message in messages] == ["S3 message"]
    assert [notification.title for notification in notifications] == ["S3 notification"]


def test_untrusted_fake_s3_collaboration_state_is_preserved() -> None:
    backend, client = _s3_backend()
    message_key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/messages.json",
    )
    notification_key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/notifications.json",
    )
    client.objects[message_key] = b"{not-json"
    client.objects[notification_key] = b"{not-json"
    message_store = MessageStore("alpha", data_dir="/virtual/data", backend=backend)
    notification_store = NotificationStore(
        "alpha", data_dir="/virtual/data", backend=backend
    )

    with pytest.raises(MessageStoreError, match="Invalid message state document"):
        message_store.post("user-1", "Alice", "New", "general", "global")
    with pytest.raises(
        NotificationStoreError,
        match="Invalid notification state document",
    ):
        notification_store.create(
            "user-1", "system", "New", "Body", "system", "context-1"
        )

    assert client.objects[message_key] == b"{not-json"
    assert client.objects[notification_key] == b"{not-json"


def test_independent_fake_s3_message_stores_preserve_concurrent_posts() -> None:
    backend, _ = _s3_backend(read_delay=0.005)
    stores = [
        MessageStore("alpha", data_dir="/virtual/data", backend=backend)
        for _ in range(20)
    ]

    def post(index: int) -> None:
        stores[index].post("user-1", "Alice", f"Message {index}", "general", "global")

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(post, range(20)))
    messages = MessageStore(
        "alpha", data_dir="/virtual/data", backend=backend
    ).get_thread("general", "global", limit=50)
    assert {message.content for message in messages} == {
        f"Message {index}" for index in range(20)
    }


def test_independent_fake_s3_notification_stores_preserve_concurrent_creates() -> None:
    backend, _ = _s3_backend(read_delay=0.005)

    stores = [
        NotificationStore("alpha", data_dir=Path("/virtual/data"), backend=backend)
        for _ in range(20)
    ]

    def create(index: int) -> None:
        stores[index].create(
            "user-1", "system", f"Notification {index}", "Body", "system", "context-1"
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(create, range(20)))
    notifications = NotificationStore(
        "alpha", data_dir=Path("/virtual/data"), backend=backend
    ).get_for_user("user-1")
    assert {notification.title for notification in notifications} == {
        f"Notification {index}" for index in range(20)
    }


def test_message_store_factory_separates_data_roots(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = get_message_store("alpha", data_dir=first_root)
    second = get_message_store("alpha", data_dir=second_root)
    first.post("user-1", "Alice", "First root", "general", "global")

    assert first is not second
    assert second.get_thread("general", "global") == []


def test_message_routes_pass_the_application_state_backend() -> None:
    source_path = Path("app/routers/messages.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_message_store"
    ]

    assert len(calls) == 6
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"data_dir", "backend"} <= keywords

    notification_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "NotificationService"
    ]
    assert len(notification_calls) == 1
    notification_keywords = {keyword.arg for keyword in notification_calls[0].keywords}
    assert {"data_dir", "backend"} <= notification_keywords


def test_collaboration_api_reports_corrupt_state_as_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("JWT_SECRET_KEY", "collaboration-integrity-test-secret-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@example.com",
            "password": "AdminPass1!",
        },
    )
    login = client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    tenant_dir = tmp_path / "tenants/system"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    message_path = tenant_dir / "messages.json"
    notification_path = tenant_dir / "notifications.json"
    message_path.write_text("{not-json", encoding="utf-8")
    notification_path.write_text("{not-json", encoding="utf-8")

    message_response = client.get("/messages", headers=headers)
    edit_response = client.patch(
        "/messages/message-1",
        headers=headers,
        json={"content": "Updated"},
    )
    notification_response = client.get("/notifications", headers=headers)

    assert message_response.status_code == 500
    assert message_response.json()["code"] == "INTERNAL_ERROR"
    assert edit_response.status_code == 500
    assert edit_response.json()["code"] == "INTERNAL_ERROR"
    assert notification_response.status_code == 500
    assert notification_response.json()["code"] == "INTERNAL_ERROR"
    assert message_path.read_bytes() == b"{not-json"
    assert notification_path.read_bytes() == b"{not-json"

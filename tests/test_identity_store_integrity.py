from __future__ import annotations

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.invite_store import InviteStore, InviteStoreError
from app.storage.state_backend import LocalStateBackend, S3StateBackend
from app.storage.user_store import (
    UserRole,
    UserStore,
    UserStoreError,
    get_user_store,
)


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


def _user_record(
    user_id: str,
    *,
    tenant_id: str = "alpha",
    username: str = "alice",
) -> dict:
    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "username": username,
        "display_name": "Alice",
        "email": "alice@example.com",
        "password_hash": "test-hash",
        "role": "member",
        "is_active": True,
        "created_at": "2026-07-16T00:00:00+00:00",
        "last_login": None,
        "avatar_color": "#000000",
        "job_title": "",
        "assigned_ai_profiles": [],
    }


def _invite_record(
    invite_id: str,
    *,
    tenant_id: str = "alpha",
) -> dict:
    return {
        "invite_id": invite_id,
        "tenant_id": tenant_id,
        "email": "invitee@example.com",
        "role": "member",
        "created_by": "admin-1",
        "created_at": "2026-07-16T00:00:00",
        "expires_at": "2026-07-23T00:00:00",
        "job_title": "",
        "assigned_ai_profiles": [],
        "is_active": True,
        "used_at": None,
    }


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_identity_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        get_user_store(tenant_id, data_dir=tmp_path)
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        InviteStore(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_identity_state_read_has_no_side_effect(tmp_path: Path) -> None:
    user_store = UserStore(tmp_path / "tenants/alpha")
    invite_store = InviteStore("alpha", data_dir=tmp_path)

    assert user_store.list_users() == []
    assert user_store.has_any_users() is False
    assert invite_store.get("missing") is None
    assert not user_store._path.exists()
    assert not invite_store._path_val.exists()


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("", "Invalid user state document"),
        ("{not-json", "Invalid user state document"),
        ("[]", "Invalid user state document"),
        ('{"user-1":null}', "Invalid user record"),
        (
            '{"user-1":{"tenant_id":"alpha","user_id":"first","user_id":"second"}}',
            "Invalid user state document",
        ),
        (
            json.dumps({"user-1": {**_user_record("different")}}),
            "Invalid user identity",
        ),
        (
            json.dumps(
                {
                    "user-1": _user_record("user-1", username="same"),
                    "user-2": _user_record("user-2", username="same"),
                }
            ),
            "Duplicate username",
        ),
    ],
)
def test_untrusted_user_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    error: str,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    path = tmp_path / "tenants/alpha/users.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = UserStore(path.parent)

    with pytest.raises(UserStoreError, match=error):
        store.list_users()
    with pytest.raises(UserStoreError, match=error):
        store.create("new-user", "New", "new@example.com", "Password1")

    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("", "Invalid invite state document"),
        ("{not-json", "Invalid invite state document"),
        ("[]", "Invalid invite state document"),
        ('{"invite-1":null}', "Invalid invite record"),
        (
            '{"invite-1":{"tenant_id":"alpha","invite_id":"first","invite_id":"second"}}',
            "Invalid invite state document",
        ),
        (
            json.dumps({"invite-1": {**_invite_record("different")}}),
            "Invalid invite identity",
        ),
        (
            json.dumps(
                {"invite-1": {**_invite_record("invite-1"), "role": "owner"}}
            ),
            "Invalid invite role",
        ),
    ],
)
def test_untrusted_invite_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: str,
    error: str,
) -> None:
    path = tmp_path / "tenants/alpha/invites.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = InviteStore("alpha", data_dir=tmp_path)

    with pytest.raises(InviteStoreError, match=error):
        store.get("invite-1")
    with pytest.raises(InviteStoreError, match=error):
        store.create("invite-2", "new@example.com", "member", "admin-1")

    assert path.read_bytes() == original_bytes


def test_foreign_identity_records_remain_hidden_and_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    user_path = tmp_path / "tenants/alpha/users.json"
    invite_path = tmp_path / "tenants/alpha/invites.json"
    user_path.parent.mkdir(parents=True)
    user_path.write_text(
        json.dumps({"foreign-user": {"tenant_id": "beta"}}),
        encoding="utf-8",
    )
    invite_path.write_text(
        json.dumps({"foreign-invite": {"tenant_id": "beta"}}),
        encoding="utf-8",
    )

    user_store = UserStore(user_path.parent)
    invite_store = InviteStore("alpha", data_dir=tmp_path)
    user_store.create("alice", "Alice", "alice@example.com", "Password1")
    invite_store.create("owned-invite", "invitee@example.com", "member", "admin-1")

    assert [user.username for user in user_store.list_users()] == ["alice"]
    assert invite_store.get("foreign-invite") is None
    assert invite_store.get("owned-invite") is not None
    assert json.loads(user_path.read_text(encoding="utf-8"))["foreign-user"] == {
        "tenant_id": "beta"
    }
    assert json.loads(invite_path.read_text(encoding="utf-8"))["foreign-invite"] == {
        "tenant_id": "beta"
    }


def test_identity_store_rejects_invalid_caller_record_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    user_store = UserStore(tmp_path / "tenants/alpha")
    invite_store = InviteStore("alpha", data_dir=tmp_path)

    with pytest.raises(UserStoreError, match="Invalid user record"):
        user_store.create("", "Alice", "alice@example.com", "Password1")
    with pytest.raises(InviteStoreError, match="Invalid invite record"):
        invite_store.create("", "invitee@example.com", "member", "admin-1")

    assert not user_store._path.exists()
    assert not invite_store._path_val.exists()


def test_independent_local_user_stores_preserve_concurrent_creates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    tenant_dir = tmp_path / "tenants/alpha"
    stores = [
        UserStore(tenant_dir, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]

    def create(index: int) -> None:
        stores[index].create(
            f"user-{index}",
            f"User {index}",
            f"user-{index}@example.com",
            "Password1",
            UserRole.MEMBER,
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(create, range(20)))

    users = UserStore(tenant_dir).list_users()
    assert {user.username for user in users} == {
        f"user-{index}" for index in range(20)
    }


def test_independent_local_invite_stores_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    stores = [
        InviteStore("alpha", data_dir=tmp_path, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]

    def create(index: int) -> None:
        stores[index].create(
            f"invite-{index}",
            f"invite-{index}@example.com",
            "member",
            "admin-1",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(create, range(20)))

    invites = json.loads(
        (tmp_path / "tenants/alpha/invites.json").read_text(encoding="utf-8")
    )
    assert set(invites) == {f"invite-{index}" for index in range(20)}


def test_independent_identity_stores_reject_concurrent_duplicate_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    tenant_dir = tmp_path / "tenants/alpha"
    user_stores = [
        UserStore(tenant_dir, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]
    invite_stores = [
        InviteStore("alpha", data_dir=tmp_path, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]

    def create_user(index: int) -> bool:
        try:
            user_stores[index].create(
                "same-user",
                "Same User",
                "same@example.com",
                "Password1",
            )
            return True
        except ValueError:
            return False

    def create_invite(index: int) -> bool:
        try:
            invite_stores[index].create(
                "same-invite",
                "same@example.com",
                "member",
                "admin-1",
            )
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=20) as executor:
        user_results = list(executor.map(create_user, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        invite_results = list(executor.map(create_invite, range(20)))

    assert user_results.count(True) == 1
    assert invite_results.count(True) == 1
    assert len(UserStore(tenant_dir).list_users()) == 1
    assert InviteStore("alpha", data_dir=tmp_path).get("same-invite") is not None


def test_wrong_current_password_keeps_existing_result_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "stored-hash")
    monkeypatch.setattr(
        "app.storage.user_store._check_password",
        lambda plain, hashed: plain == "correct" and hashed == "stored-hash",
    )
    store = UserStore(tmp_path / "tenants/alpha")
    user = store.create("alice", "Alice", "alice@example.com", "Password1")

    assert store.change_password(user.user_id, "wrong", "short") is False


def test_concurrent_invite_acceptance_creates_one_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    creator = InviteStore("alpha", data_dir=tmp_path)
    creator.create("invite-1", "invitee@example.com", "member", "admin-1")
    stores = [InviteStore("alpha", data_dir=tmp_path) for _ in range(20)]
    user_store = UserStore(tmp_path / "tenants/alpha")

    def accept(index: int):
        return stores[index].accept(
            "invite-1",
            lambda invite: user_store.create(
                f"user-{index}",
                f"User {index}",
                invite["email"],
                "Password1",
            ),
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(accept, range(20)))

    assert sum(result is not None for result in results) == 1
    assert len(user_store.list_users()) == 1
    invite = creator.get("invite-1")
    assert invite is not None
    assert invite["is_active"] is False
    assert invite["used_at"] is not None


def test_user_and_invite_round_trip_through_fake_s3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    backend, client = _s3_backend()
    user_store = UserStore(Path("/virtual/data/tenants/alpha"), backend=backend)
    invite_store = InviteStore("alpha", data_dir="/virtual/data", backend=backend)

    user_store.create("alice", "Alice", "alice@example.com", "Password1")
    invite_store.create("invite-1", "invitee@example.com", "member", "admin-1")

    user_key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/users.json")
    invite_key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/invites.json")
    assert user_key in client.objects
    assert invite_key in client.objects
    assert (
        UserStore(Path("/virtual/data/tenants/alpha"), backend=backend)
        .get_by_username("alice")
        .username
        == "alice"
    )
    assert (
        InviteStore("alpha", data_dir="/virtual/data", backend=backend)
        .get("invite-1")["email"]
        == "invitee@example.com"
    )


def test_untrusted_fake_s3_identity_state_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    backend, client = _s3_backend()
    user_key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/users.json")
    invite_key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/invites.json")
    client.objects[user_key] = b"{not-json"
    client.objects[invite_key] = b"{not-json"
    user_store = UserStore(Path("/virtual/data/tenants/alpha"), backend=backend)
    invite_store = InviteStore("alpha", data_dir="/virtual/data", backend=backend)

    with pytest.raises(UserStoreError, match="Invalid user state document"):
        user_store.create("alice", "Alice", "alice@example.com", "Password1")
    with pytest.raises(InviteStoreError, match="Invalid invite state document"):
        invite_store.create("invite-1", "invitee@example.com", "member", "admin-1")

    assert client.objects[user_key] == b"{not-json"
    assert client.objects[invite_key] == b"{not-json"


def test_independent_fake_s3_identity_stores_preserve_concurrent_creates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.storage.user_store._hash_password", lambda _: "test-hash")
    backend, client = _s3_backend(read_delay=0.005)
    user_stores = [
        UserStore(Path("/virtual/data/tenants/alpha"), backend=backend)
        for _ in range(20)
    ]
    invite_stores = [
        InviteStore("alpha", data_dir="/virtual/data", backend=backend)
        for _ in range(20)
    ]

    def create_user(index: int) -> None:
        user_stores[index].create(
            f"user-{index}",
            f"User {index}",
            f"user-{index}@example.com",
            "Password1",
        )

    def create_invite(index: int) -> None:
        invite_stores[index].create(
            f"invite-{index}",
            f"invite-{index}@example.com",
            "member",
            "admin-1",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(create_user, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(create_invite, range(20)))

    users = UserStore(
        Path("/virtual/data/tenants/alpha"), backend=backend
    ).list_users()
    invites = json.loads(
        client.objects[
            ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/invites.json")
        ]
    )
    assert {user.username for user in users} == {
        f"user-{index}" for index in range(20)
    }
    assert set(invites) == {f"invite-{index}" for index in range(20)}


def test_invite_routes_pass_the_application_state_backend() -> None:
    source_path = Path("app/routers/admin/_invite.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "InviteStore"
    ]

    assert len(calls) == 3
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"data_dir", "backend"} <= keywords


def test_identity_api_fails_closed_on_corrupt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("JWT_SECRET_KEY", "identity-integrity-test-secret-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    tenant_dir = tmp_path / "tenants/system"
    tenant_dir.mkdir(parents=True)
    user_path = tenant_dir / "users.json"
    invite_path = tenant_dir / "invites.json"
    user_path.write_text("{not-json", encoding="utf-8")
    invite_path.write_text("{not-json", encoding="utf-8")
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    register_response = client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@example.com",
            "password": "AdminPass1!",
        },
    )
    user_path.write_text("{}", encoding="utf-8")
    invite_response = client.get("/invite/invite-1")

    assert register_response.status_code == 500
    assert register_response.json()["code"] == "INTERNAL_ERROR"
    assert invite_response.status_code == 500
    assert invite_response.json()["code"] == "INTERNAL_ERROR"
    assert user_path.read_bytes() == b"{}"
    assert invite_path.read_bytes() == b"{not-json"

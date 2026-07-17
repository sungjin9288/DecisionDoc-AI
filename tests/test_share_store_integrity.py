from __future__ import annotations

import ast
import hashlib
import json
import threading
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.storage.share_store import ShareStore, ShareStoreError
from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)


class _SlowLocalBackend(LocalStateBackend):
    """Expose lost updates when independent stores do not share a lock."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _ConflictingLocalBackend(LocalStateBackend):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.attempts = 0

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = relative_path, text, content_type
        self.attempts += 1
        return False


class _FailingConditionalBackend(LocalStateBackend):
    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = relative_path, text, content_type
        raise StateBackendError("simulated conditional write failure")


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay
        self._lock = threading.Lock()
        self._fail_after_conditional_write = False
        self._after_failed_conditional_write: Callable[[], None] | None = None

    @staticmethod
    def _etag(data: bytes) -> str:
        return f'"{hashlib.sha256(data).hexdigest()}"'

    @staticmethod
    def _error(code: str) -> Exception:
        error = Exception(code)
        error.response = {"Error": {"Code": code}}
        return error

    def fail_after_next_conditional_write(
        self,
        *,
        after_write: Callable[[], None] | None = None,
    ) -> None:
        self._fail_after_conditional_write = True
        self._after_failed_conditional_write = after_write

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        IfNoneMatch: str | None = None,
        IfMatch: str | None = None,
    ) -> None:
        _ = ContentType
        with self._lock:
            current = self.objects.get((Bucket, Key))
            if IfNoneMatch == "*" and current is not None:
                raise self._error("PreconditionFailed")
            if IfMatch is not None and (
                current is None or self._etag(current) != IfMatch
            ):
                raise self._error("PreconditionFailed")
            self.objects[(Bucket, Key)] = Body
            fail_after_write = (
                self._fail_after_conditional_write
                and (IfNoneMatch is not None or IfMatch is not None)
            )
            if fail_after_write:
                self._fail_after_conditional_write = False
                after_failed_write = self._after_failed_conditional_write
                self._after_failed_conditional_write = None
            else:
                after_failed_write = None
        if fail_after_write:
            if after_failed_write is not None:
                after_failed_write()
            raise self._error("InternalError")

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            raise self._error("NoSuchKey")
        time.sleep(self.read_delay)
        return {"Body": _Body(data), "ETag": self._etag(data)}


def _s3_backend(
    *,
    read_delay: float = 0.0,
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = client or _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _record(
    share_id: str,
    *,
    tenant_id: str | None = "alpha",
    created_by: str = "user-1",
) -> dict:
    record = {
        "share_id": share_id,
        "request_id": f"request-{share_id}",
        "title": f"Share {share_id}",
        "created_by": created_by,
        "created_at": "2026-07-16T00:00:00+00:00",
        "expires_at": "2030-07-16T00:00:00+00:00",
        "access_count": 0,
        "last_accessed_at": "",
        "is_active": True,
        "revoked_at": "",
        "revoked_by": "",
        "revoked_by_username": "",
        "bundle_id": "proposal_kr",
    }
    if tenant_id is not None:
        record["tenant_id"] = tenant_id
    return record


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_share_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        ShareStore(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_share_state_read_has_no_side_effect(tmp_path: Path) -> None:
    store = ShareStore("alpha", data_dir=tmp_path)

    assert store.get("missing") is None
    assert store.list_by_user("user-1") == []
    assert not store._path.exists()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{not-json",
        "[]",
        '{"share-1":{},"share-1":{}}',
        '{"share-1":[]}',
        json.dumps({"stored-key": _record("different-id")}),
        json.dumps({"share-1": {**_record("share-1"), "access_count": -1}}),
        json.dumps({"share-1": {**_record("share-1"), "access_count": True}}),
        json.dumps({"share-1": {**_record("share-1"), "is_active": "yes"}}),
        json.dumps(
            {
                "share-1": {
                    **_record("share-1"),
                    "revoked_at": "2026-07-16T00:00:00+00:00",
                    "is_active": True,
                }
            }
        ),
        json.dumps({"share-1": {**_record("share-1"), "expires_at": "later"}}),
    ],
)
def test_untrusted_share_state_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw: str,
) -> None:
    path = tmp_path / "tenants/alpha/shares.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = ShareStore("alpha", data_dir=tmp_path)

    with pytest.raises(ShareStoreError):
        store.get("share-1")
    with pytest.raises(ShareStoreError):
        store.create("request-new", "New", "user-1")
    with pytest.raises(ShareStoreError):
        store.increment_access("share-1")
    with pytest.raises(ShareStoreError):
        store.revoke("share-1", "user-1")

    assert path.read_bytes() == original_bytes


def test_foreign_share_remains_hidden_and_preserved(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/shares.json"
    path.parent.mkdir(parents=True)
    foreign = {"tenant_id": "beta", "opaque": {"keep": True}}
    path.write_text(json.dumps({"foreign-share": foreign}), encoding="utf-8")
    store = ShareStore("alpha", data_dir=tmp_path)

    created = store.create("request-owned", "Owned", "user-1")

    assert store.get("foreign-share") is None
    assert [item["share_id"] for item in store.list_by_user("user-1")] == [
        created.share_id
    ]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["foreign-share"] == foreign


def test_legacy_share_without_tenant_remains_path_owned(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/shares.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"legacy-share": _record("legacy-share", tenant_id=None)}),
        encoding="utf-8",
    )
    store = ShareStore("alpha", data_dir=tmp_path)

    store.increment_access("legacy-share")
    legacy = store.get("legacy-share")

    assert legacy is not None
    assert legacy.get("tenant_id") is None
    assert legacy["access_count"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_id", ""),
        ("title", []),
        ("created_by", ""),
        ("bundle_id", 1),
        ("expires_days", True),
    ],
)
def test_invalid_share_input_is_rejected_before_write(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    arguments = {
        "request_id": "request-1",
        "title": "Share",
        "created_by": "user-1",
        field: value,
    }
    store = ShareStore("alpha", data_dir=tmp_path)

    with pytest.raises(ValueError):
        store.create(**arguments)

    assert not store._path.exists()


def test_share_store_rejects_generated_identity_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ShareStore("alpha", data_dir=tmp_path)
    first = store.create("request-1", "First", "user-1")
    original_bytes = store._path.read_bytes()
    monkeypatch.setattr(
        "app.storage.share_store.secrets.token_urlsafe", lambda _: first.share_id
    )

    with pytest.raises(ShareStoreError, match="Duplicate share identity"):
        store.create("request-2", "Second", "user-2")

    assert store._path.read_bytes() == original_bytes


def test_missing_share_mutations_do_not_rewrite_state(tmp_path: Path) -> None:
    store = ShareStore("alpha", data_dir=tmp_path)
    store.create("request-1", "Share", "user-1")
    original_bytes = store._path.read_bytes()

    store.increment_access("missing")
    assert store.revoke("missing", "user-1") is False

    assert store._path.read_bytes() == original_bytes


def test_timezone_aware_expired_share_read_does_not_rewrite_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tenants/alpha/shares.json"
    path.parent.mkdir(parents=True)
    expired = {
        **_record("expired"),
        "expires_at": "2020-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps({"expired": expired}), encoding="utf-8")
    original_bytes = path.read_bytes()

    result = ShareStore("alpha", data_dir=tmp_path).get("expired")

    assert result is not None
    assert result["is_active"] is False
    assert result["lifecycle_status"] == "expired"
    assert path.read_bytes() == original_bytes


def test_independent_local_share_stores_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    stores = [
        ShareStore(
            "alpha",
            data_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def create(index: int) -> str:
        return (
            stores[index]
            .create(
                f"request-{index}",
                f"Share {index}",
                "user-1",
            )
            .share_id
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        share_ids = set(executor.map(create, range(20)))

    shares = ShareStore("alpha", data_dir=tmp_path).list_by_user("user-1")
    assert {item["share_id"] for item in shares} == share_ids


def test_independent_local_share_stores_preserve_concurrent_access_counts(
    tmp_path: Path,
) -> None:
    creator = ShareStore("alpha", data_dir=tmp_path)
    share = creator.create("request-1", "Share", "user-1")
    stores = [
        ShareStore(
            "alpha",
            data_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(lambda store: store.increment_access(share.share_id), stores))

    assert creator.get(share.share_id)["access_count"] == 20


def test_share_round_trip_through_fake_s3() -> None:
    backend, client = _s3_backend()
    store = ShareStore("alpha", data_dir="/virtual/data", backend=backend)
    share = store.create("request-1", "Share", "user-1")
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/shares.json")

    assert key in client.objects
    reloaded = ShareStore(
        "alpha",
        data_dir="/virtual/data",
        backend=backend,
    ).get(share.share_id)
    assert reloaded is not None
    assert reloaded["title"] == "Share"


def test_untrusted_fake_s3_share_state_is_preserved() -> None:
    backend, client = _s3_backend()
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/shares.json")
    client.objects[key] = b"{not-json"
    store = ShareStore("alpha", data_dir="/virtual/data", backend=backend)

    with pytest.raises(ShareStoreError, match="Invalid share state document"):
        store.create("request-1", "Share", "user-1")

    assert client.objects[key] == b"{not-json"


def test_independent_fake_s3_share_stores_preserve_concurrent_mutations() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    stores = [
        ShareStore(
            "alpha",
            data_dir=f"/virtual/worker-{index}",
            backend=_s3_backend(client=client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def create(index: int) -> str:
        return (
            stores[index]
            .create(
                f"request-{index}",
                f"Share {index}",
                "user-1",
            )
            .share_id
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        share_ids = list(executor.map(create, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(lambda store: store.increment_access(share_ids[0]), stores))

    reloaded = ShareStore(
        "alpha",
        data_dir="/virtual/reload",
        backend=_s3_backend(client=client)[0],
    )
    assert len(reloaded.list_by_user("user-1")) == 20
    assert reloaded.get(share_ids[0])["access_count"] == 20


def test_share_mutation_reconciles_commit_then_successor_create() -> None:
    client = _MemoryS3Client()
    bootstrap = ShareStore(
        "alpha",
        data_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    shared = bootstrap.create("request-1", "Shared", "user-1")
    primary = ShareStore(
        "alpha",
        data_dir="/virtual/primary",
        backend=_s3_backend(client=client)[0],
    )
    successor = ShareStore(
        "alpha",
        data_dir="/virtual/successor",
        backend=_s3_backend(client=client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    successor_ids: list[str] = []
    client.fail_after_next_conditional_write(
        after_write=lambda: successor_ids.append(
            successor.create("request-2", "Successor", "user-2").share_id
        )
    )

    primary.increment_access(shared.share_id)

    assert bootstrap.get(shared.share_id)["access_count"] == 1
    assert len(successor_ids) == 1
    assert bootstrap.get(successor_ids[0]) is not None


def test_share_disjoint_access_and_revoke_updates_are_preserved() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    bootstrap = ShareStore(
        "alpha",
        data_dir="/virtual/bootstrap",
        backend=_s3_backend(client=client)[0],
    )
    shared = bootstrap.create("request-1", "Shared", "user-1")
    access_store = ShareStore(
        "alpha",
        data_dir="/virtual/access",
        backend=_s3_backend(client=client)[0],
    )
    revoke_store = ShareStore(
        "alpha",
        data_dir="/virtual/revoke",
        backend=_s3_backend(client=client)[0],
    )
    access_store._lock = nullcontext()
    revoke_store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=2) as executor:
        access_result, revoke_result = executor.map(
            lambda action: action(),
            (
                lambda: access_store.increment_access(shared.share_id),
                lambda: revoke_store.revoke(shared.share_id, "user-1"),
            ),
        )

    reloaded = bootstrap.get(shared.share_id)
    assert access_result is None
    assert revoke_result is True
    assert reloaded is not None
    assert reloaded["access_count"] == 1
    assert reloaded["is_active"] is False
    assert reloaded["lifecycle_status"] == "revoked"


def test_share_mutation_stops_after_bounded_conflicts(tmp_path: Path) -> None:
    backend = _ConflictingLocalBackend(tmp_path)
    store = ShareStore("alpha", data_dir=tmp_path, backend=backend)

    with pytest.raises(
        ShareStoreError,
        match="Share state changed too many times to persist safely",
    ):
        store.create("request-1", "Shared", "user-1")

    assert backend.attempts == 32


def test_share_mutation_wraps_backend_failure(tmp_path: Path) -> None:
    store = ShareStore(
        "alpha",
        data_dir=tmp_path,
        backend=_FailingConditionalBackend(tmp_path),
    )

    with pytest.raises(ShareStoreError, match="Failed to persist share state"):
        store.create("request-1", "Shared", "user-1")


def test_share_mutation_receipts_are_private_bounded_and_fail_closed(
    tmp_path: Path,
) -> None:
    store = ShareStore("alpha", data_dir=tmp_path)
    shared = store.create("request-1", "Shared", "user-1")
    for _ in range(70):
        store.increment_access(shared.share_id)

    public = store.get(shared.share_id)
    listed = store.list_by_user("user-1")
    persisted_state = json.loads(store._path.read_text(encoding="utf-8"))
    persisted = persisted_state[shared.share_id]
    assert public is not None
    assert "_mutation_ids" not in public
    assert all("_mutation_ids" not in link for link in listed)
    assert len(persisted["_mutation_ids"]) == 64

    persisted["_mutation_ids"] = [f"mutation-{index}" for index in range(65)]
    store._path.write_text(
        json.dumps(persisted_state, ensure_ascii=False),
        encoding="utf-8",
    )
    original_bytes = store._path.read_bytes()

    with pytest.raises(ShareStoreError, match="Invalid share mutation history"):
        store.get(shared.share_id)
    with pytest.raises(ShareStoreError, match="Invalid share mutation history"):
        store.increment_access(shared.share_id)
    assert store._path.read_bytes() == original_bytes


def test_share_routes_pass_the_application_state_backend() -> None:
    source_paths = (
        Path("app/routers/history.py"),
        Path("app/routers/admin/_procurement_quality.py"),
        Path("app/routers/admin/_procurement_quality_location.py"),
    )
    calls = []
    for source_path in source_paths:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        calls.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ShareStore"
        )

    assert len(calls) == 5
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"data_dir", "backend"} <= keywords


def test_share_api_reports_corrupt_state_as_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    path = tmp_path / "tenants/system/shares.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    token = _token("user-1")

    public_response = client.get("/shared/share-1")
    create_response = client.post(
        "/share",
        json={"request_id": "request-1", "title": "Share"},
        headers={"Authorization": f"Bearer {token}"},
    )
    revoke_response = client.delete(
        "/share/share-1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert public_response.status_code == 500
    assert public_response.json()["code"] == "INTERNAL_ERROR"
    assert create_response.status_code == 500
    assert create_response.json()["code"] == "INTERNAL_ERROR"
    assert revoke_response.status_code == 500
    assert revoke_response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("JWT_SECRET_KEY", "share-integrity-test-secret-key-32")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _token(user_id: str) -> str:
    from app.services.auth_service import create_access_token

    return create_access_token(user_id, "system", "member", user_id)

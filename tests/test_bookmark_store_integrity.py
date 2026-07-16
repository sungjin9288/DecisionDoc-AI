from __future__ import annotations

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.bookmark_store import BookmarkStore, BookmarkStoreError
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _Body:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def read(self) -> bytes:
        return self._raw


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
        raw = self.objects.get((Bucket, Key))
        if raw is None:
            error = RuntimeError("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(raw)}


def _s3_backend(
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client()
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


def _path(root: Path) -> Path:
    return root / "tenants/alpha/g2b_bookmarks.json"


def _s3_key() -> tuple[str, str]:
    return "unit-bucket", "decisiondoc-ai/state/tenants/alpha/g2b_bookmarks.json"


def _owned_bookmark(bid_number: str = "BID-1") -> dict:
    return {
        "bid_number": bid_number,
        "title": f"Announcement {bid_number}",
        "bookmarked_at": "2026-07-17T00:00:00+00:00",
        "_bookmark_owner": {"tenant_id": "alpha", "user_id": "user-1"},
    }


def test_missing_bookmark_reads_do_not_create_local_or_s3_state(
    tmp_path: Path,
) -> None:
    local = BookmarkStore(base_dir=str(tmp_path), tenant_id="alpha")
    backend, client = _s3_backend()
    remote = BookmarkStore(
        base_dir="/virtual/data",
        tenant_id="alpha",
        backend=backend,
    )

    assert local.get_for_user("user-1") == []
    assert local.is_bookmarked("user-1", "BID-1") is False
    assert remote.get_for_user("user-1") == []
    assert not (tmp_path / "tenants").exists()
    assert client.objects == {}


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{not-json",
        b"[]",
        b'{"user-1":[],"user-1":[]}',
        b"\xff\xfe",
    ],
)
def test_invalid_bookmark_document_stops_every_operation_without_replacement(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = BookmarkStore(base_dir=str(tmp_path), tenant_id="alpha")

    with pytest.raises(BookmarkStoreError):
        store.get_for_user("user-1")
    with pytest.raises(BookmarkStoreError):
        store.add("user-1", {"bid_number": "BID-NEW", "title": "New"})
    with pytest.raises(BookmarkStoreError):
        store.remove("user-1", "BID-1")

    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "state",
    [
        {" user-1": []},
        {"user-1": {}},
        {"user-1": ["not-an-object"]},
        {"user-1": [{"title": "Missing identity"}]},
        {"user-1": [{**_owned_bookmark(), "bookmarked_at": False}]},
        {"user-1": [_owned_bookmark(), _owned_bookmark()]},
    ],
)
def test_invalid_owned_bookmark_state_fails_closed(
    tmp_path: Path,
    state: dict,
) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    original = json.dumps(state).encode()
    path.write_bytes(original)
    store = BookmarkStore(base_dir=str(tmp_path), tenant_id="alpha")

    with pytest.raises(BookmarkStoreError):
        store.get_for_user("user-1")
    with pytest.raises(BookmarkStoreError):
        store.add("user-1", {"bid_number": "BID-NEW"})

    assert path.read_bytes() == original


def test_foreign_and_untrusted_owner_records_remain_hidden_and_preserved(
    tmp_path: Path,
) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    foreign = {
        "bid_number": "BID-SHARED",
        "title": "Foreign",
        "_bookmark_owner": {"tenant_id": "beta", "user_id": "user-1"},
    }
    untrusted = {
        "bid_number": "BID-UNTRUSTED",
        "title": "Untrusted owner",
        "_bookmark_owner": None,
    }
    path.write_text(json.dumps({"user-1": [foreign, untrusted]}), encoding="utf-8")
    store = BookmarkStore(base_dir=str(tmp_path), tenant_id="alpha")

    created = store.add("user-1", {"bid_number": "BID-SHARED", "title": "Owned"})

    assert created["title"] == "Owned"
    assert [item["title"] for item in store.get_for_user("user-1")] == ["Owned"]
    persisted = json.loads(path.read_text(encoding="utf-8"))["user-1"]
    assert persisted[1:] == [foreign, untrusted]


def test_legacy_ownerless_bookmark_remains_readable_and_unchanged(
    tmp_path: Path,
) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    legacy = {
        "bid_number": "BID-LEGACY",
        "title": "Legacy",
        "bookmarked_at": "2026-07-16T00:00:00",
    }
    path.write_text(json.dumps({"user-1": [legacy]}), encoding="utf-8")
    store = BookmarkStore(base_dir=str(tmp_path), tenant_id="alpha")

    assert store.get_for_user("user-1") == [legacy]
    store.add("user-1", {"bid_number": "BID-NEW", "title": "New"})

    persisted = json.loads(path.read_text(encoding="utf-8"))["user-1"]
    assert persisted[1] == legacy
    assert "_bookmark_owner" not in persisted[1]


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    [
        ("add-missing-bid", "Invalid bid_number"),
        ("add-non-object", "Invalid announcement"),
        ("remove-blank-bid", "Invalid bid_number"),
        ("lookup-blank-bid", "Invalid bid_number"),
    ],
)
def test_invalid_bookmark_input_is_rejected_before_state_creation(
    tmp_path: Path,
    operation: str,
    expected_error: str,
) -> None:
    store = BookmarkStore(base_dir=str(tmp_path), tenant_id="alpha")

    with pytest.raises(ValueError, match=expected_error):
        if operation == "add-missing-bid":
            store.add("user-1", {"title": "Missing bid"})
        elif operation == "add-non-object":
            store.add("user-1", [])  # type: ignore[arg-type]
        elif operation == "remove-blank-bid":
            store.remove("user-1", " ")
        else:
            store.is_bookmarked("user-1", "")

    assert not (tmp_path / "tenants").exists()


def test_fake_s3_corruption_is_preserved() -> None:
    backend, client = _s3_backend()
    client.objects[_s3_key()] = b"{not-json"
    store = BookmarkStore(
        base_dir="/virtual/data",
        tenant_id="alpha",
        backend=backend,
    )

    with pytest.raises(BookmarkStoreError):
        store.add("user-1", {"bid_number": "BID-NEW"})

    assert client.objects[_s3_key()] == b"{not-json"


def test_independent_local_and_s3_stores_preserve_concurrent_bookmarks(
    tmp_path: Path,
) -> None:
    local_stores = [
        BookmarkStore(
            base_dir=str(tmp_path),
            tenant_id="alpha",
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    client = _MemoryS3Client(read_delay=0.005)
    s3_stores = [
        BookmarkStore(
            base_dir="/virtual/data",
            tenant_id="alpha",
            backend=_s3_backend(client)[0],
        )
        for _ in range(20)
    ]

    def add(store: BookmarkStore, index: int) -> None:
        store.add(
            "user-1",
            {"bid_number": f"BID-{index}", "title": f"Announcement {index}"},
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add, local_stores, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add, s3_stores, range(20)))

    expected = {f"BID-{index}" for index in range(20)}
    assert {
        item["bid_number"] for item in local_stores[0].get_for_user("user-1")
    } == expected
    assert {
        item["bid_number"] for item in s3_stores[0].get_for_user("user-1")
    } == expected


def test_bookmark_routes_use_the_selected_state_backend() -> None:
    tree = ast.parse(Path("app/routers/history.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "BookmarkStore"
    ]

    assert len(calls) == 3
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert {"base_dir", "tenant_id", "backend"} <= keywords


def test_bookmark_api_reports_corrupt_state_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/g2b_bookmarks.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {_token('user-1')}"}

    responses = (
        client.get("/g2b/bookmarks", headers=headers),
        client.post(
            "/g2b/bookmarks",
            json={"bid_number": "BID-NEW", "title": "New"},
            headers=headers,
        ),
        client.delete("/g2b/bookmarks/BID-1", headers=headers),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert path.read_bytes() == b"{not-json"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("JWT_SECRET_KEY", "bookmark-integrity-test-secret-key-32")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _token(user_id: str) -> str:
    from app.services.auth_service import create_access_token

    return create_access_token(user_id, "system", "member", user_id)

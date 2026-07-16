from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.storage.audit_store import AuditLog, AuditStore, AuditStoreError
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    """Expose lost updates when store instances do not share a lock."""

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

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
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


def _log(log_id: str, *, tenant_id: str = "alpha") -> AuditLog:
    return AuditLog(
        log_id=log_id,
        tenant_id=tenant_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        user_id="user-1",
        username="Alice",
        user_role="member",
        ip_address="127.0.0.1",
        user_agent="audit-integrity-test",
        action="doc.view",
        resource_type="document",
        resource_id="document-1",
        resource_name="Document",
        result="success",
        detail={"request_id": log_id},
        session_id="session-1",
    )


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        AuditStore(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_reading_missing_audit_state_does_not_create_a_file(tmp_path: Path) -> None:
    store = AuditStore("alpha", data_dir=tmp_path)

    assert store.query_all() == []
    assert not store._path.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("log_id", "", "Invalid audit log identity"),
        ("result", "unknown", "Invalid audit log result"),
        ("detail", [], "Invalid audit log detail"),
    ],
)
def test_store_rejects_invalid_caller_evidence_before_write(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    store = AuditStore("alpha", data_dir=tmp_path)
    log = _log("invalid")
    setattr(log, field, value)

    with pytest.raises(AuditStoreError, match=message):
        store.append(log)

    assert not store._path.exists()


@pytest.mark.parametrize(
    "raw",
    [
        "{not-json\n",
        "[]\n",
        '{"log_id":"first","log_id":"second"}\n',
        json.dumps({**_log("foreign").__dict__, "tenant_id": "beta"}) + "\n",
        json.dumps({**_log("missing-detail").__dict__, "detail": None}) + "\n",
    ],
)
def test_untrusted_audit_state_stops_read_and_append_without_replacement(
    tmp_path: Path,
    raw: str,
) -> None:
    path = tmp_path / "tenants/alpha/audit_logs.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = AuditStore("alpha", data_dir=tmp_path)

    with pytest.raises(AuditStoreError, match="Invalid audit log entry at line 1"):
        store.query_all()
    with pytest.raises(AuditStoreError, match="Invalid audit log entry at line 1"):
        store.append(_log("blocked"))

    assert path.read_bytes() == original_bytes


def test_duplicate_audit_identity_stops_append_without_replacement(
    tmp_path: Path,
) -> None:
    store = AuditStore("alpha", data_dir=tmp_path)
    store.append(_log("duplicate"))
    duplicate_line = store._path.read_text(encoding="utf-8")
    store._path.write_text(duplicate_line * 2, encoding="utf-8")
    duplicate_bytes = store._path.read_bytes()

    with pytest.raises(AuditStoreError, match="Duplicate audit log identity"):
        store.query_all()
    with pytest.raises(AuditStoreError, match="Duplicate audit log identity"):
        store.append(_log("blocked"))

    assert store._path.read_bytes() == duplicate_bytes


def test_store_rejects_reusing_an_existing_audit_identity(tmp_path: Path) -> None:
    store = AuditStore("alpha", data_dir=tmp_path)
    store.append(_log("same-id"))
    original_bytes = store._path.read_bytes()

    with pytest.raises(AuditStoreError, match="Duplicate audit log identity"):
        store.append(_log("same-id"))

    assert store._path.read_bytes() == original_bytes


def test_append_preserves_an_existing_byte_prefix_without_trailing_newline(
    tmp_path: Path,
) -> None:
    store = AuditStore("alpha", data_dir=tmp_path)
    store.append(_log("first"))
    first_line = store._path.read_bytes().rstrip(b"\n")
    store._path.write_bytes(first_line)

    store.append(_log("second"))

    persisted = store._path.read_bytes()
    assert persisted.startswith(first_line)
    assert persisted[len(first_line):].startswith(b"\n")
    assert [entry["log_id"] for entry in store.query_all()] == ["second", "first"]


def test_independent_store_instances_preserve_concurrent_appends(
    tmp_path: Path,
) -> None:
    stores = [
        AuditStore(
            "alpha",
            data_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def append(index: int) -> None:
        stores[index].append(_log(f"log-{index}"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(append, range(20)))

    entries = AuditStore("alpha", data_dir=tmp_path).query_all()
    assert {entry["log_id"] for entry in entries} == {
        f"log-{index}" for index in range(20)
    }


def test_fake_s3_round_trip_preserves_append_order_and_identity() -> None:
    backend, client = _s3_backend()
    store = AuditStore("alpha", data_dir="/virtual/data", backend=backend)
    store.append(_log("first"))
    store.append(_log("second"))
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/audit_logs.jsonl",
    )

    assert key in client.objects
    persisted = [
        json.loads(line)["log_id"]
        for line in client.objects[key].decode().splitlines()
    ]
    reloaded = AuditStore(
        "alpha",
        data_dir="/virtual/data",
        backend=backend,
    ).query_all()
    assert persisted == ["first", "second"]
    assert [entry["log_id"] for entry in reloaded] == ["second", "first"]


def test_independent_fake_s3_stores_preserve_concurrent_appends() -> None:
    backend, _ = _s3_backend(read_delay=0.005)
    stores = [
        AuditStore("alpha", data_dir="/virtual/data", backend=backend)
        for _ in range(20)
    ]

    def append(index: int) -> None:
        stores[index].append(_log(f"log-{index}"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(append, range(20)))

    entries = AuditStore(
        "alpha",
        data_dir="/virtual/data",
        backend=backend,
    ).query_all()
    assert {entry["log_id"] for entry in entries} == {
        f"log-{index}" for index in range(20)
    }


def test_forged_fake_s3_audit_state_is_preserved_and_rejected() -> None:
    backend, client = _s3_backend()
    store = AuditStore("alpha", data_dir="/virtual/data", backend=backend)
    store.append(_log("owned"))
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/audit_logs.jsonl",
    )
    record = json.loads(client.objects[key])
    record["tenant_id"] = "beta"
    client.objects[key] = (json.dumps(record) + "\n").encode()
    forged_bytes = client.objects[key]

    with pytest.raises(AuditStoreError, match="Invalid audit log entry at line 1"):
        store.query_all()
    with pytest.raises(AuditStoreError, match="Invalid audit log entry at line 1"):
        store.append(_log("blocked"))

    assert client.objects[key] == forged_bytes

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage.approval_store import ApprovalStore
from app.storage.project_store import ProjectStore
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    """Make overlapping read-modify-write sequences deterministic in tests."""

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
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}


def _s3_backend() -> tuple[S3StateBackend, _MemoryS3Client]:
    client = _MemoryS3Client()
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _create_approval(store: ApprovalStore, tenant_id: str, index: int = 0):
    return store.create(
        tenant_id,
        request_id=f"request-{index}",
        bundle_id="tech_decision",
        title=f"Approval {index}",
        drafter="drafter",
        docs=[{"doc_type": "adr", "markdown": "# Decision"}],
    )


@pytest.mark.parametrize(
    "tenant_id",
    ["", " ", " tenant-a", "tenant-a ", ".", "..", "tenant/a", "tenant\\a", "tenant\x00a"],
)
def test_project_and_approval_stores_reject_unsafe_tenant_before_write(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    project_store = ProjectStore(base_dir=str(tmp_path))
    approval_store = ApprovalStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        project_store.create(tenant_id, name="Unsafe")
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        _create_approval(approval_store, tenant_id)

    assert not (tmp_path / "projects.json").exists()
    assert not (tmp_path / "approvals.json").exists()


@pytest.mark.parametrize("store_kind", ["project", "approval"])
@pytest.mark.parametrize(
    "raw",
    [
        "{not-json",
        '{"unexpected":"object"}',
        '[{"tenant_id":"alpha","record_id":"first","record_id":"second"}]',
    ],
)
def test_invalid_state_document_stops_read_and_write_without_replacement(
    tmp_path: Path,
    store_kind: str,
    raw: str,
) -> None:
    tenant_dir = tmp_path / "tenants/alpha"
    tenant_dir.mkdir(parents=True)
    path = tenant_dir / f"{store_kind}s.json"
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()

    if store_kind == "project":
        store = ProjectStore(base_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid project state document"):
            store.list_by_tenant("alpha")
        with pytest.raises(ValueError, match="Invalid project state document"):
            store.create("alpha", name="New project")
    else:
        store = ApprovalStore(base_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid approval state document"):
            store.list_by_tenant("alpha")
        with pytest.raises(ValueError, match="Invalid approval state document"):
            _create_approval(store, "alpha")
    assert path.read_bytes() == original_bytes


def test_project_store_excludes_foreign_and_malformed_records_without_removing_them(
    tmp_path: Path,
) -> None:
    store = ProjectStore(base_dir=str(tmp_path))
    owned = store.create("alpha", name="Owned")
    path = tmp_path / "tenants/alpha/projects.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    foreign = {**records[0], "project_id": "foreign", "tenant_id": "beta"}
    malformed = {"tenant_id": "alpha", "name": "Missing identity"}
    records.extend([foreign, malformed])
    path.write_text(json.dumps(records), encoding="utf-8")

    assert [project.project_id for project in store.list_by_tenant("alpha")] == [
        owned.project_id
    ]
    created = store.create("alpha", name="Second owned")

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted[1:3] == [foreign, malformed]
    assert {persisted[0]["project_id"], persisted[3]["project_id"]} == {
        owned.project_id,
        created.project_id,
    }


def test_approval_store_excludes_foreign_and_malformed_records_without_removing_them(
    tmp_path: Path,
) -> None:
    store = ApprovalStore(base_dir=str(tmp_path))
    owned = _create_approval(store, "alpha")
    path = tmp_path / "tenants/alpha/approvals.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    foreign = {**records[0], "approval_id": "foreign", "tenant_id": "beta"}
    malformed = {"tenant_id": "alpha", "title": "Missing identity"}
    records.extend([foreign, malformed])
    path.write_text(json.dumps(records), encoding="utf-8")

    assert [record.approval_id for record in store.list_by_tenant("alpha")] == [
        owned.approval_id
    ]
    created = _create_approval(store, "alpha", index=1)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted[1:3] == [foreign, malformed]
    assert {persisted[0]["approval_id"], persisted[3]["approval_id"]} == {
        owned.approval_id,
        created.approval_id,
    }


@pytest.mark.parametrize("store_kind", ["project", "approval"])
def test_duplicate_owned_record_stops_mutation_without_replacement(
    tmp_path: Path,
    store_kind: str,
) -> None:
    if store_kind == "project":
        store = ProjectStore(base_dir=str(tmp_path))
        store.create("alpha", name="Owned")
        path = tmp_path / "tenants/alpha/projects.json"
    else:
        store = ApprovalStore(base_dir=str(tmp_path))
        _create_approval(store, "alpha")
        path = tmp_path / "tenants/alpha/approvals.json"

    records = json.loads(path.read_text(encoding="utf-8"))
    records.append(dict(records[0]))
    path.write_text(json.dumps(records), encoding="utf-8")
    duplicate_bytes = path.read_bytes()

    if store_kind == "project":
        with pytest.raises(ValueError, match="Duplicate project records"):
            store.create("alpha", name="Blocked")
    else:
        with pytest.raises(ValueError, match="Duplicate approval records"):
            _create_approval(store, "alpha", index=1)
    assert path.read_bytes() == duplicate_bytes


def test_independent_project_store_instances_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    backend = _SlowLocalBackend(tmp_path)
    stores = [ProjectStore(base_dir=str(tmp_path), backend=backend) for _ in range(20)]

    def create(index: int) -> str:
        return stores[index].create("alpha", name=f"Project {index}").project_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(create, range(20)))

    persisted = ProjectStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    assert len(created) == 20
    assert {project.project_id for project in persisted} == created


def test_independent_approval_store_instances_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    backend = _SlowLocalBackend(tmp_path)
    stores = [ApprovalStore(base_dir=str(tmp_path), backend=backend) for _ in range(20)]

    def create(index: int) -> str:
        return _create_approval(stores[index], "alpha", index).approval_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(create, range(20)))

    persisted = ApprovalStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    assert len(created) == 20
    assert {record.approval_id for record in persisted} == created


def test_project_store_rejects_forged_s3_record_identity() -> None:
    backend, client = _s3_backend()
    store = ProjectStore(base_dir="/virtual/data", backend=backend)
    project = store.create("alpha", name="Owned")
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/projects.json")
    records = json.loads(client.objects[key])
    records[0]["tenant_id"] = "beta"
    client.objects[key] = json.dumps(records).encode()
    forged_bytes = client.objects[key]

    assert store.get(project.project_id, tenant_id="alpha") is None
    assert store.list_by_tenant("alpha") == []
    with pytest.raises(KeyError):
        store.update(project.project_id, tenant_id="alpha", name="Overwritten")
    assert client.objects[key] == forged_bytes


def test_approval_store_rejects_forged_s3_record_identity() -> None:
    backend, client = _s3_backend()
    store = ApprovalStore(base_dir="/virtual/data", backend=backend)
    approval = _create_approval(store, "alpha")
    key = ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/approvals.json")
    records = json.loads(client.objects[key])
    records[0]["tenant_id"] = "beta"
    client.objects[key] = json.dumps(records).encode()
    forged_bytes = client.objects[key]

    assert store.get(approval.approval_id, tenant_id="alpha") is None
    assert store.list_by_tenant("alpha") == []
    with pytest.raises(KeyError):
        store.update(approval.approval_id, tenant_id="alpha", drafter="Overwritten")
    assert client.objects[key] == forged_bytes

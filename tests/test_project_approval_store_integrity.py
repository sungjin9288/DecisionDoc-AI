from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.approval_store import ApprovalStore, ApprovalStoreError
from app.storage.project_store import ProjectStore, ProjectStoreError
from app.storage.state_backend import LocalStateBackend, S3StateBackend, StateBackendError


class _SlowLocalBackend(LocalStateBackend):
    """Make overlapping read-modify-write sequences deterministic in tests."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _FailingLocalBackend(LocalStateBackend):
    def __init__(self, root: Path, *, operation: str) -> None:
        super().__init__(root)
        self._operation = operation

    def read_text(self, relative_path: str) -> str | None:
        if self._operation == "read":
            raise StateBackendError("simulated read failure")
        return super().read_text(relative_path)

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        if self._operation == "write":
            raise StateBackendError("simulated write failure")
        super().write_text(relative_path, text, content_type=content_type)


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._read_delay = read_delay

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        time.sleep(self._read_delay)
        return {"Body": _Body(data)}


def _s3_backend(
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = client or _MemoryS3Client()
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _state_path(tmp_path: Path, store_kind: str, tenant_id: str = "alpha") -> Path:
    return tmp_path / f"tenants/{tenant_id}/{store_kind}s.json"


def _s3_key(store_kind: str, tenant_id: str = "alpha") -> tuple[str, str]:
    return (
        "unit-bucket",
        f"decisiondoc-ai/state/tenants/{tenant_id}/{store_kind}s.json",
    )


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


def test_missing_project_and_approval_reads_do_not_create_local_or_s3_state(
    tmp_path: Path,
) -> None:
    backend, client = _s3_backend()

    assert ProjectStore(base_dir=str(tmp_path)).list_by_tenant("alpha") == []
    assert ApprovalStore(base_dir=str(tmp_path)).list_by_tenant("alpha") == []
    assert ProjectStore(base_dir="/virtual/projects", backend=backend).list_by_tenant(
        "alpha"
    ) == []
    assert ApprovalStore(base_dir="/virtual/approvals", backend=backend).list_by_tenant(
        "alpha"
    ) == []

    assert not (tmp_path / "tenants").exists()
    assert client.objects == {}


@pytest.mark.parametrize("store_kind", ["project", "approval"])
@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{not-json",
        b'{"unexpected":"object"}',
        b'[{"tenant_id":"alpha","record_id":"first","record_id":"second"}]',
        b"\xff\xfe",
    ],
)
def test_invalid_state_document_stops_read_and_write_without_replacement(
    tmp_path: Path,
    store_kind: str,
    raw: bytes,
) -> None:
    tenant_dir = tmp_path / "tenants/alpha"
    tenant_dir.mkdir(parents=True)
    path = tenant_dir / f"{store_kind}s.json"
    path.write_bytes(raw)
    original_bytes = path.read_bytes()

    if store_kind == "project":
        store = ProjectStore(base_dir=str(tmp_path))
        with pytest.raises(ProjectStoreError, match="Invalid project state document"):
            store.list_by_tenant("alpha")
        with pytest.raises(ProjectStoreError, match="Invalid project state document"):
            store.create("alpha", name="New project")
    else:
        store = ApprovalStore(base_dir=str(tmp_path))
        with pytest.raises(ApprovalStoreError, match="Invalid approval state document"):
            store.list_by_tenant("alpha")
        with pytest.raises(ApprovalStoreError, match="Invalid approval state document"):
            _create_approval(store, "alpha")
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("store_kind", ["project", "approval"])
@pytest.mark.parametrize("raw", [b"{not-json", b"\xff\xfe"])
def test_fake_s3_state_corruption_is_preserved(store_kind: str, raw: bytes) -> None:
    backend, client = _s3_backend()
    key = _s3_key(store_kind)
    client.objects[key] = raw

    if store_kind == "project":
        store = ProjectStore(base_dir="/virtual/project-state", backend=backend)
        with pytest.raises(ProjectStoreError):
            store.create("alpha", name="Blocked")
    else:
        store = ApprovalStore(base_dir="/virtual/approval-state", backend=backend)
        with pytest.raises(ApprovalStoreError):
            _create_approval(store, "alpha")

    assert client.objects[key] == raw


@pytest.mark.parametrize("store_kind", ["project", "approval"])
@pytest.mark.parametrize("operation", ["read", "write"])
def test_backend_failures_are_normalized_without_creating_state(
    tmp_path: Path,
    store_kind: str,
    operation: str,
) -> None:
    backend = _FailingLocalBackend(tmp_path, operation=operation)

    if store_kind == "project":
        store = ProjectStore(base_dir=str(tmp_path), backend=backend)
        with pytest.raises(ProjectStoreError):
            store.create("alpha", name="Blocked")
    else:
        store = ApprovalStore(base_dir=str(tmp_path), backend=backend)
        with pytest.raises(ApprovalStoreError):
            _create_approval(store, "alpha")

    assert not (tmp_path / "tenants").exists()


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
def test_identity_bearing_owned_corruption_fails_closed(
    tmp_path: Path,
    store_kind: str,
) -> None:
    if store_kind == "project":
        store = ProjectStore(base_dir=str(tmp_path))
        store.create("alpha", name="Owned")
        path = _state_path(tmp_path, store_kind)
        records = json.loads(path.read_text(encoding="utf-8"))
        records[0]["documents"] = "not-a-list"
        error_type = ProjectStoreError

        def read():
            return store.list_by_tenant("alpha")

        def write():
            return store.create("alpha", name="Blocked")
    else:
        store = ApprovalStore(base_dir=str(tmp_path))
        _create_approval(store, "alpha")
        path = _state_path(tmp_path, store_kind)
        records = json.loads(path.read_text(encoding="utf-8"))
        records[0]["status"] = "unknown"
        error_type = ApprovalStoreError

        def read():
            return store.list_by_tenant("alpha")

        def write():
            return _create_approval(store, "alpha", index=1)

    path.write_text(json.dumps(records), encoding="utf-8")
    corrupted = path.read_bytes()

    with pytest.raises(error_type, match=f"Invalid owned {store_kind} record"):
        read()
    with pytest.raises(error_type, match=f"Invalid owned {store_kind} record"):
        write()
    assert path.read_bytes() == corrupted


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
        with pytest.raises(ProjectStoreError, match="Duplicate project records"):
            store.create("alpha", name="Blocked")
    else:
        with pytest.raises(ApprovalStoreError, match="Duplicate approval records"):
            _create_approval(store, "alpha", index=1)
    assert path.read_bytes() == duplicate_bytes


def test_independent_project_store_instances_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    backend = _SlowLocalBackend(tmp_path)
    local_stores = [
        ProjectStore(base_dir=str(tmp_path), backend=backend)
        for _ in range(20)
    ]
    client = _MemoryS3Client(read_delay=0.005)
    s3_stores = [
        ProjectStore(
            base_dir=f"/virtual/project-state-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]

    def create(store: ProjectStore, index: int) -> str:
        return store.create("alpha", name=f"Project {index}").project_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        local_created = set(executor.map(create, local_stores, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        s3_created = set(executor.map(create, s3_stores, range(20)))

    persisted = ProjectStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    remote = ProjectStore(
        base_dir="/another/virtual/root",
        backend=_s3_backend(client)[0],
    ).list_by_tenant("alpha")
    assert len(local_created) == len(s3_created) == 20
    assert {project.project_id for project in persisted} == local_created
    assert {project.project_id for project in remote} == s3_created


def test_independent_approval_store_instances_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    backend = _SlowLocalBackend(tmp_path)
    local_stores = [
        ApprovalStore(base_dir=str(tmp_path), backend=backend)
        for _ in range(20)
    ]
    client = _MemoryS3Client(read_delay=0.005)
    s3_stores = [
        ApprovalStore(
            base_dir=f"/virtual/approval-state-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]

    def create(store: ApprovalStore, index: int) -> str:
        return _create_approval(store, "alpha", index).approval_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        local_created = set(executor.map(create, local_stores, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        s3_created = set(executor.map(create, s3_stores, range(20)))

    persisted = ApprovalStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    remote = ApprovalStore(
        base_dir="/another/virtual/root",
        backend=_s3_backend(client)[0],
    ).list_by_tenant("alpha")
    assert len(local_created) == len(s3_created) == 20
    assert {record.approval_id for record in persisted} == local_created
    assert {record.approval_id for record in remote} == s3_created


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


def test_project_and_approval_apis_report_corrupt_state_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    headers = {"X-DecisionDoc-Api-Key": "test-key"}
    approval = client.post(
        "/approvals",
        json={
            "title": "Integrity approval",
            "drafter": "drafter",
            "docs": [{"doc_type": "adr", "markdown": "# Decision"}],
        },
        headers=headers,
    )
    assert approval.status_code == 200
    approval_id = approval.json()["approval_id"]

    project_path = _state_path(tmp_path, "project", tenant_id="system")
    approval_path = _state_path(tmp_path, "approval", tenant_id="system")
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_bytes(b"{not-json")
    approval_path.write_bytes(b"{not-json")

    responses = (
        client.get("/projects", headers=headers),
        client.post("/projects", json={"name": "Blocked"}, headers=headers),
        client.get("/approvals", headers=headers),
        client.post(
            f"/approvals/{approval_id}/submit",
            json={"username": "reviewer", "reviewer": "reviewer"},
            headers=headers,
        ),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert project_path.read_bytes() == b"{not-json"
    assert approval_path.read_bytes() == b"{not-json"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.schemas import ProcurementDecisionUpsert, ProcurementSourceSnapshotMetadata
from app.storage.procurement_store import (
    ProcurementDecisionStore,
    ProcurementDecisionStoreError,
)
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
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client()
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


def _upsert(
    store: ProcurementDecisionStore,
    *,
    tenant_id: str = "alpha",
    project_id: str = "project-1",
    notes: str = "",
):
    return store.upsert(
        ProcurementDecisionUpsert(
            tenant_id=tenant_id,
            project_id=project_id,
            notes=notes,
        )
    )


def _decision_path(root: Path, tenant_id: str = "alpha") -> Path:
    return root / f"tenants/{tenant_id}/procurement_decisions.json"


def _decision_s3_key(tenant_id: str = "alpha") -> tuple[str, str]:
    return (
        "unit-bucket",
        f"decisiondoc-ai/state/tenants/{tenant_id}/procurement_decisions.json",
    )


def test_missing_procurement_reads_do_not_create_local_or_s3_state(
    tmp_path: Path,
) -> None:
    local = ProcurementDecisionStore(base_dir=str(tmp_path))
    backend, client = _s3_backend()
    remote = ProcurementDecisionStore(base_dir="/virtual/data", backend=backend)

    assert local.get("project-missing", tenant_id="alpha") is None
    assert remote.get("project-missing", tenant_id="alpha") is None
    assert not (tmp_path / "tenants").exists()
    assert client.objects == {}


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        _upsert(store, tenant_id=tenant_id)
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store.save_source_snapshot(
            tenant_id=tenant_id,
            project_id="project-1",
            source_kind="fixture",
            payload={"source": "test"},
        )

    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "project_id",
    [" project", "project ", ".", "..", "project/a", "project\\a", "project\na"],
)
def test_store_rejects_unsafe_project_before_state_access(
    tmp_path: Path,
    project_id: str,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid project_id"):
        _upsert(store, project_id=project_id)
    with pytest.raises(ValueError, match="Invalid project_id"):
        store.save_source_snapshot(
            tenant_id="alpha",
            project_id=project_id,
            source_kind="fixture",
            payload={"source": "test"},
        )

    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "snapshot_id",
    [" snapshot", "snapshot ", ".", "..", "snapshot/a", "snapshot\\a", "snapshot\na"],
)
def test_store_rejects_unsafe_snapshot_before_state_access(
    tmp_path: Path,
    snapshot_id: str,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid snapshot_id"):
        store.load_source_snapshot(
            tenant_id="alpha",
            project_id="project-1",
            snapshot_id=snapshot_id,
        )

    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{not-json",
        b'{"unexpected":"object"}',
        b'[{"tenant_id":"alpha","project_id":"first","project_id":"second"}]',
        b"\xff\xfe",
    ],
)
def test_invalid_decision_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: bytes,
) -> None:
    tenant_dir = tmp_path / "tenants/alpha"
    tenant_dir.mkdir(parents=True)
    path = tenant_dir / "procurement_decisions.json"
    path.write_bytes(raw)
    original_bytes = path.read_bytes()
    store = ProcurementDecisionStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid procurement decision state document"):
        store.list_by_tenant("alpha")
    with pytest.raises(ValueError, match="Invalid procurement decision state document"):
        _upsert(store)

    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("raw", [b"{not-json", b"\xff\xfe"])
def test_invalid_s3_decision_state_is_preserved(raw: bytes) -> None:
    backend, client = _s3_backend()
    client.objects[_decision_s3_key()] = raw
    store = ProcurementDecisionStore(base_dir="/virtual/data", backend=backend)

    with pytest.raises(
        ProcurementDecisionStoreError,
        match="Invalid procurement decision state document",
    ):
        store.list_by_tenant("alpha")
    with pytest.raises(
        ProcurementDecisionStoreError,
        match="Invalid procurement decision state document",
    ):
        _upsert(store)

    assert client.objects[_decision_s3_key()] == raw


def test_foreign_record_does_not_hide_owned_record_and_is_preserved(
    tmp_path: Path,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    owned = _upsert(store)
    path = tmp_path / "tenants/alpha/procurement_decisions.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    foreign = {
        **records[0],
        "tenant_id": "beta",
        "decision_id": "foreign-decision",
    }
    path.write_text(json.dumps([foreign, records[0]]), encoding="utf-8")

    assert store.get("project-1", tenant_id="alpha") == owned
    created = _upsert(store, project_id="project-2")

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted[0] == foreign
    assert {record["decision_id"] for record in persisted[1:]} == {
        owned.decision_id,
        created.decision_id,
    }


def test_malformed_owned_record_stops_mutation_without_replacement(
    tmp_path: Path,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    _upsert(store)
    path = tmp_path / "tenants/alpha/procurement_decisions.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    del records[0]["decision_id"]
    path.write_text(json.dumps(records), encoding="utf-8")
    malformed_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid owned procurement decision record"):
        store.list_by_tenant("alpha")
    with pytest.raises(ValueError, match="Invalid owned procurement decision record"):
        _upsert(store, project_id="project-2")

    assert path.read_bytes() == malformed_bytes


@pytest.mark.parametrize(
    ("duplicate_field", "error"),
    [
        ("project_id", "Duplicate procurement project records"),
        ("decision_id", "Duplicate procurement decision records"),
    ],
)
def test_duplicate_owned_identity_stops_mutation_without_replacement(
    tmp_path: Path,
    duplicate_field: str,
    error: str,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    _upsert(store, project_id="project-1")
    _upsert(store, project_id="project-2")
    path = tmp_path / "tenants/alpha/procurement_decisions.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    records[1][duplicate_field] = records[0][duplicate_field]
    path.write_text(json.dumps(records), encoding="utf-8")
    duplicate_bytes = path.read_bytes()

    with pytest.raises(ValueError, match=error):
        _upsert(store, project_id="project-3")

    assert path.read_bytes() == duplicate_bytes


def test_independent_store_instances_preserve_concurrent_project_upserts(
    tmp_path: Path,
) -> None:
    stores = [
        ProcurementDecisionStore(
            base_dir=str(tmp_path),
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def upsert(index: int) -> str:
        return _upsert(stores[index], project_id=f"project-{index}").decision_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(upsert, range(20)))

    persisted = ProcurementDecisionStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    assert len(created) == 20
    assert {record.decision_id for record in persisted} == created


def test_independent_store_instances_keep_one_identity_for_concurrent_same_project_upserts(
    tmp_path: Path,
) -> None:
    stores = [
        ProcurementDecisionStore(
            base_dir=str(tmp_path),
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def upsert(index: int) -> str:
        return _upsert(stores[index], notes=f"update-{index}").decision_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        decision_ids = set(executor.map(upsert, range(20)))

    persisted = ProcurementDecisionStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    assert len(decision_ids) == 1
    assert len(persisted) == 1
    assert persisted[0].decision_id in decision_ids


def test_independent_s3_stores_preserve_concurrent_project_upserts() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    stores = [
        ProcurementDecisionStore(
            base_dir=f"/virtual/data-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]

    def upsert(index: int) -> str:
        return _upsert(stores[index], project_id=f"project-{index}").decision_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(upsert, range(20)))

    records = json.loads(client.objects[_decision_s3_key()])
    assert len(created) == 20
    assert {record["decision_id"] for record in records} == created


def test_forged_s3_decision_identity_is_hidden_and_unmodifiable() -> None:
    backend, client = _s3_backend()
    store = ProcurementDecisionStore(base_dir="/virtual/data", backend=backend)
    decision = _upsert(store)
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/procurement_decisions.json",
    )
    records = json.loads(client.objects[key])
    records[0]["tenant_id"] = "beta"
    client.objects[key] = json.dumps(records).encode()
    forged_bytes = client.objects[key]

    assert store.get(decision.project_id, tenant_id="alpha") is None
    assert store.list_by_tenant("alpha") == []
    with pytest.raises(KeyError):
        store.update_notes(
            project_id=decision.project_id,
            tenant_id="alpha",
            notes="Overwritten",
        )
    assert client.objects[key] == forged_bytes


def test_snapshot_is_bound_to_tenant_and_project() -> None:
    backend, _client = _s3_backend()
    store = ProcurementDecisionStore(base_dir="/virtual/data", backend=backend)
    snapshot = store.save_source_snapshot(
        tenant_id="alpha",
        project_id="project-1",
        source_kind="fixture",
        payload={"source": "owned"},
    )

    assert store.load_source_snapshot(
        tenant_id="alpha",
        project_id="project-1",
        snapshot_id=snapshot.snapshot_id,
    ) == {"source": "owned"}
    assert store.load_source_snapshot(
        tenant_id="alpha",
        project_id="project-2",
        snapshot_id=snapshot.snapshot_id,
    ) is None
    assert store.load_source_snapshot(
        tenant_id="beta",
        project_id="project-1",
        snapshot_id=snapshot.snapshot_id,
    ) is None


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{not-json",
        b'{"source":"first","source":"second"}',
        b"\xff\xfe",
    ],
)
def test_invalid_s3_snapshot_is_not_treated_as_missing(raw: bytes) -> None:
    backend, client = _s3_backend()
    store = ProcurementDecisionStore(base_dir="/virtual/data", backend=backend)
    snapshot = store.save_source_snapshot(
        tenant_id="alpha",
        project_id="project-1",
        source_kind="fixture",
        payload={"source": "owned"},
    )
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/procurement_snapshots/"
        f"project-1/{snapshot.snapshot_id}.json",
    )
    client.objects[key] = raw
    invalid_bytes = client.objects[key]

    with pytest.raises(ValueError, match="Invalid procurement source snapshot"):
        store.load_source_snapshot(
            tenant_id="alpha",
            project_id="project-1",
            snapshot_id=snapshot.snapshot_id,
        )

    assert client.objects[key] == invalid_bytes


def test_duplicate_snapshot_metadata_and_invalid_notes_do_not_mutate_state(
    tmp_path: Path,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    existing = _upsert(store)
    path = _decision_path(tmp_path)
    original = path.read_bytes()
    snapshot = ProcurementSourceSnapshotMetadata.model_validate(
        {
            "snapshot_id": "snapshot-1",
            "source_kind": "fixture",
            "captured_at": "2026-07-17T00:00:00+00:00",
            "storage_path": "tenants/alpha/procurement_snapshots/project-2/snapshot-1.json",
        }
    )

    with pytest.raises(
        ProcurementDecisionStoreError,
        match="Duplicate procurement source snapshot metadata",
    ):
        store.upsert(
            ProcurementDecisionUpsert(
                tenant_id="alpha",
                project_id="project-2",
                source_snapshots=[snapshot, snapshot],
            )
        )
    with pytest.raises(ValueError):
        store.update_notes(
            project_id=existing.project_id,
            tenant_id="alpha",
            notes=123,
        )

    assert path.read_bytes() == original


@pytest.mark.parametrize("payload", [{"invalid": object()}, {"invalid": float("nan")}])
def test_invalid_snapshot_payload_is_rejected_before_state_write(
    tmp_path: Path,
    payload: object,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))

    with pytest.raises(
        ProcurementDecisionStoreError,
        match="Invalid procurement source snapshot payload",
    ):
        store.save_source_snapshot(
            tenant_id="alpha",
            project_id="project-1",
            source_kind="fixture",
            payload=payload,
        )

    assert not (tmp_path / "tenants").exists()


def test_forged_snapshot_storage_path_stops_owned_decision_mutation(
    tmp_path: Path,
) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    snapshot = store.save_source_snapshot(
        tenant_id="alpha",
        project_id="project-1",
        source_kind="fixture",
        payload={"source": "owned"},
    )
    store.upsert(
        ProcurementDecisionUpsert(
            tenant_id="alpha",
            project_id="project-1",
            source_snapshots=[snapshot],
        )
    )
    path = tmp_path / "tenants/alpha/procurement_decisions.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    records[0]["source_snapshots"][0]["storage_path"] = (
        "tenants/beta/procurement_snapshots/project-1/foreign.json"
    )
    path.write_text(json.dumps(records), encoding="utf-8")
    forged_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid owned procurement decision record"):
        store.get("project-1", tenant_id="alpha")
    with pytest.raises(ValueError, match="Invalid owned procurement decision record"):
        _upsert(store, project_id="project-2")

    assert path.read_bytes() == forged_bytes


def test_procurement_api_reports_corrupt_state_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    project = client.post(
        "/projects",
        json={"name": "Procurement integrity project", "fiscal_year": 2026},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert project.status_code == 200
    project_id = project.json()["project_id"]
    path = _decision_path(tmp_path, "system")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{not-json")
    headers = {"X-DecisionDoc-Api-Key": "test-key"}

    responses = (
        client.get(f"/projects/{project_id}/procurement", headers=headers),
        client.post(f"/projects/{project_id}/procurement/evaluate", headers=headers),
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
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)

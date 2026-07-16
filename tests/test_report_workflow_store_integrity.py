from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage.report_workflow_store import PlanningVersion, ReportWorkflowStore
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


def _create(
    store: ReportWorkflowStore,
    *,
    tenant_id: str = "alpha",
    title: str = "Report workflow",
):
    return store.create(tenant_id=tenant_id, title=title)


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        _create(store, tenant_id=tenant_id)

    assert not (tmp_path / "tenants").exists()


def test_store_rejects_empty_workflow_identity_before_state_access(
    tmp_path: Path,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid report_workflow_id"):
        store.get("", tenant_id="alpha")

    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "raw",
    [
        "{not-json",
        '{"unexpected":"object"}',
        '[{"tenant_id":"alpha","report_workflow_id":"first",'
        '"report_workflow_id":"second"}]',
    ],
)
def test_invalid_workflow_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: str,
) -> None:
    tenant_dir = tmp_path / "tenants/alpha"
    tenant_dir.mkdir(parents=True)
    path = tenant_dir / "report_workflows.json"
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = ReportWorkflowStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid report workflow state document"):
        store.list_by_tenant("alpha")
    with pytest.raises(ValueError, match="Invalid report workflow state document"):
        _create(store)

    assert path.read_bytes() == original_bytes


def test_foreign_record_does_not_hide_owned_record_and_is_preserved(
    tmp_path: Path,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))
    owned = _create(store)
    path = tmp_path / "tenants/alpha/report_workflows.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    foreign = {
        **records[0],
        "tenant_id": "beta",
        "report_workflow_id": "foreign-workflow",
    }
    path.write_text(json.dumps([foreign, records[0]]), encoding="utf-8")

    assert store.get(owned.report_workflow_id, tenant_id="alpha") == owned
    created = _create(store, title="Second workflow")

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted[0] == foreign
    assert {record["report_workflow_id"] for record in persisted[1:]} == {
        owned.report_workflow_id,
        created.report_workflow_id,
    }


def test_malformed_owned_record_stops_mutation_without_replacement(
    tmp_path: Path,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))
    _create(store)
    path = tmp_path / "tenants/alpha/report_workflows.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    del records[0]["created_at"]
    path.write_text(json.dumps(records), encoding="utf-8")
    malformed_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid owned report workflow record"):
        store.list_by_tenant("alpha")
    with pytest.raises(ValueError, match="Invalid owned report workflow record"):
        _create(store, title="Blocked")

    assert path.read_bytes() == malformed_bytes


def test_duplicate_workflow_identity_stops_mutation_without_replacement(
    tmp_path: Path,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))
    _create(store, title="First")
    _create(store, title="Second")
    path = tmp_path / "tenants/alpha/report_workflows.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    records[1]["report_workflow_id"] = records[0]["report_workflow_id"]
    path.write_text(json.dumps(records), encoding="utf-8")
    duplicate_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Duplicate report workflow records"):
        _create(store, title="Blocked")

    assert path.read_bytes() == duplicate_bytes


@pytest.mark.parametrize("nested_identity", ["slide", "approval_stage"])
def test_duplicate_nested_review_identity_stops_mutation(
    tmp_path: Path,
    nested_identity: str,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))
    workflow = _create(store)
    path = tmp_path / "tenants/alpha/report_workflows.json"
    records = json.loads(path.read_text(encoding="utf-8"))

    if nested_identity == "slide":
        slide = {
            "slide_id": "slide-1",
            "page": 1,
            "title": "Slide",
            "body": "Body",
            "visual_spec": "",
            "speaker_note": "",
            "source_refs": [],
        }
        records[0]["slides"] = [slide, dict(slide)]
    else:
        records[0]["approval_steps"] = [
            {
                "step_id": "step-1",
                "stage": "pm_review",
                "label": "PM review",
            },
            {
                "step_id": "step-2",
                "stage": "pm_review",
                "label": "Duplicate PM review",
            },
        ]

    path.write_text(json.dumps(records), encoding="utf-8")
    duplicate_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid owned report workflow record"):
        store.add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": "blocked"}],
            tenant_id="alpha",
        )

    assert path.read_bytes() == duplicate_bytes


def test_invalid_in_memory_planning_identity_stops_mutation(
    tmp_path: Path,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))
    workflow = _create(store)
    path = tmp_path / "tenants/alpha/report_workflows.json"
    original_bytes = path.read_bytes()
    planning = PlanningVersion(
        plan_id="",
        version=0,
        status="draft",
        objective="Objective",
        audience="Audience",
        executive_message="Message",
        table_of_contents=[],
        slide_plans=[],
        open_questions=[],
        risk_notes=[],
        created_by="tester",
        created_at="2026-07-16T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="Invalid report workflow planning identity"):
        store.save_planning(
            workflow.report_workflow_id,
            planning,
            tenant_id="alpha",
        )

    assert path.read_bytes() == original_bytes

    records = json.loads(original_bytes)
    records[0]["planning"] = {}
    path.write_text(json.dumps(records), encoding="utf-8")
    malformed_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid owned report workflow record"):
        store.get(workflow.report_workflow_id, tenant_id="alpha")

    assert path.read_bytes() == malformed_bytes


def test_independent_store_instances_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    stores = [
        ReportWorkflowStore(
            base_dir=str(tmp_path),
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def create(index: int) -> str:
        return _create(stores[index], title=f"Workflow {index}").report_workflow_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(create, range(20)))

    persisted = ReportWorkflowStore(base_dir=str(tmp_path)).list_by_tenant("alpha")
    assert len(created) == 20
    assert {record.report_workflow_id for record in persisted} == created


def test_independent_store_instances_preserve_concurrent_visual_asset_updates(
    tmp_path: Path,
) -> None:
    workflow = ReportWorkflowStore(base_dir=str(tmp_path)).create(
        tenant_id="alpha",
        title="Shared workflow",
    )
    stores = [
        ReportWorkflowStore(
            base_dir=str(tmp_path),
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def add_asset(index: int) -> None:
        stores[index].add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": f"asset-{index}"}],
            tenant_id="alpha",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add_asset, range(20)))

    persisted = ReportWorkflowStore(base_dir=str(tmp_path)).get(
        workflow.report_workflow_id,
        tenant_id="alpha",
    )
    assert persisted is not None
    assert {asset["asset_id"] for asset in persisted.visual_assets} == {
        f"asset-{index}" for index in range(20)
    }


def test_s3_workflow_round_trip_preserves_owned_state() -> None:
    backend, client = _s3_backend()
    store = ReportWorkflowStore(base_dir="/virtual/data", backend=backend)
    workflow = _create(store)
    store.add_visual_assets(
        workflow.report_workflow_id,
        [{"asset_id": "asset-1"}],
        tenant_id="alpha",
    )
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/report_workflows.json",
    )

    assert key in client.objects
    reloaded = ReportWorkflowStore(
        base_dir="/virtual/data",
        backend=backend,
    ).get(workflow.report_workflow_id, tenant_id="alpha")
    assert reloaded is not None
    assert reloaded.visual_assets == [{"asset_id": "asset-1"}]


def test_forged_s3_workflow_identity_is_hidden_and_unmodifiable() -> None:
    backend, client = _s3_backend()
    store = ReportWorkflowStore(base_dir="/virtual/data", backend=backend)
    workflow = _create(store)
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/report_workflows.json",
    )
    records = json.loads(client.objects[key])
    records[0]["tenant_id"] = "beta"
    client.objects[key] = json.dumps(records).encode()
    forged_bytes = client.objects[key]

    assert store.get(workflow.report_workflow_id, tenant_id="alpha") is None
    assert store.list_by_tenant("alpha") == []
    with pytest.raises(KeyError):
        store.add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": "overwritten"}],
            tenant_id="alpha",
        )
    assert client.objects[key] == forged_bytes

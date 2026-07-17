from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.storage.report_workflow_store import (
    PlanningVersion,
    ReportWorkflowStore,
    ReportWorkflowStoreError,
    SlideDraft,
    SlidePlan,
)
from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)


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

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if self._operation == "write":
            raise StateBackendError("simulated write failure")
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if self._operation == "write":
            raise StateBackendError("simulated write failure")
        return super().replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._read_delay = read_delay
        self._lock = threading.Lock()
        self._read_barrier: threading.Barrier | None = None
        self._coordinated_reads = 0
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

    def coordinate_next_reads(self, count: int) -> None:
        self._read_barrier = threading.Barrier(count)
        self._coordinated_reads = count

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
            wait_at_barrier = self._coordinated_reads > 0
            if wait_at_barrier:
                self._coordinated_reads -= 1
                barrier = self._read_barrier
            else:
                barrier = None
        if barrier is not None:
            barrier.wait(timeout=2)
        time.sleep(self._read_delay)
        return {"Body": _Body(data), "ETag": self._etag(data)}


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


def _create(
    store: ReportWorkflowStore,
    *,
    tenant_id: str = "alpha",
    title: str = "Report workflow",
):
    return store.create(tenant_id=tenant_id, title=title)


def _planning() -> PlanningVersion:
    return PlanningVersion(
        plan_id="plan-1",
        version=0,
        status="draft",
        objective="Objective",
        audience="Audience",
        executive_message="Decision",
        table_of_contents=["First", "Second"],
        slide_plans=[
            SlidePlan(slide_id="slide-1", page=1, title="First"),
            SlidePlan(slide_id="slide-2", page=2, title="Second"),
        ],
        open_questions=[],
        risk_notes=[],
        created_by="planner",
        created_at="2026-07-17T00:00:00+00:00",
    )


def _slides() -> list[SlideDraft]:
    return [
        SlideDraft(
            slide_id=f"slide-{index}",
            page=index,
            title=f"Slide {index}",
            body=f"Body {index}",
            visual_spec="",
            speaker_note="",
            source_refs=[],
        )
        for index in (1, 2)
    ]


def _create_slides_draft(store: ReportWorkflowStore):
    workflow = _create(store)
    store.save_planning(
        workflow.report_workflow_id,
        _planning(),
        tenant_id="alpha",
    )
    store.approve_planning(
        workflow.report_workflow_id,
        author="planner",
        tenant_id="alpha",
    )
    return store.save_slides(
        workflow.report_workflow_id,
        _slides(),
        tenant_id="alpha",
    )


def _create_final_review(store: ReportWorkflowStore):
    workflow = _create_slides_draft(store)
    for slide in workflow.slides:
        store.approve_slide(
            workflow.report_workflow_id,
            slide.slide_id,
            author="planner",
            tenant_id="alpha",
        )
    return store.submit_final(
        workflow.report_workflow_id,
        author="owner",
        tenant_id="alpha",
    )


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
        b"",
        b"{not-json",
        b'{"unexpected":"object"}',
        b'[{"tenant_id":"alpha","report_workflow_id":"first",'
        b'"report_workflow_id":"second"}]',
        b"\xff\xfe",
    ],
)
def test_invalid_workflow_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: bytes,
) -> None:
    tenant_dir = tmp_path / "tenants/alpha"
    tenant_dir.mkdir(parents=True)
    path = tenant_dir / "report_workflows.json"
    path.write_bytes(raw)
    original_bytes = path.read_bytes()
    store = ReportWorkflowStore(base_dir=str(tmp_path))

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid report workflow state document",
    ):
        store.list_by_tenant("alpha")
    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid report workflow state document",
    ):
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

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid owned report workflow record",
    ):
        store.list_by_tenant("alpha")
    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid owned report workflow record",
    ):
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

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Duplicate report workflow records",
    ):
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

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid owned report workflow record",
    ):
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

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid owned report workflow record",
    ):
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


def test_backend_failures_stop_report_workflow_reads_and_writes(
    tmp_path: Path,
) -> None:
    read_store = ReportWorkflowStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="read"),
    )
    write_store = ReportWorkflowStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="write"),
    )

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid report workflow state document",
    ):
        read_store.list_by_tenant("alpha")
    with pytest.raises(
        ReportWorkflowStoreError,
        match="Failed to persist report workflow state",
    ):
        _create(write_store)

    assert not (tmp_path / "tenants/alpha/report_workflows.json").exists()


def test_independent_s3_stores_share_logical_object_lock_across_virtual_bases() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    stores = [
        ReportWorkflowStore(
            base_dir=f"/virtual/report-workflow-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]

    def create(index: int) -> str:
        return _create(stores[index], title=f"Workflow {index}").report_workflow_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(create, range(20)))

    reloaded = ReportWorkflowStore(
        base_dir="/another/virtual/root",
        backend=_s3_backend(client)[0],
    ).list_by_tenant("alpha")
    assert len(created) == 20
    assert {record.report_workflow_id for record in reloaded} == created


def test_independent_s3_stores_preserve_concurrent_visual_asset_updates() -> None:
    client = _MemoryS3Client(read_delay=0.005)
    backend = _s3_backend(client)[0]
    workflow = _create(
        ReportWorkflowStore(base_dir="/virtual/bootstrap", backend=backend)
    )
    stores = [
        ReportWorkflowStore(
            base_dir=f"/virtual/report-workflow-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]

    def add_asset(index: int) -> None:
        stores[index].add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": f"asset-{index}"}],
            tenant_id="alpha",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add_asset, range(20)))

    reloaded = ReportWorkflowStore(
        base_dir="/another/virtual/root",
        backend=_s3_backend(client)[0],
    ).get(workflow.report_workflow_id, tenant_id="alpha")
    assert reloaded is not None
    assert {asset["asset_id"] for asset in reloaded.visual_assets} == {
        f"asset-{index}" for index in range(20)
    }


def test_s3_workflow_cas_preserves_cross_worker_creates_and_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _MemoryS3Client(read_delay=0.002)
    backend, _ = _s3_backend(client)
    bootstrap = ReportWorkflowStore(
        base_dir="/virtual/bootstrap",
        backend=backend,
    )
    workflow = _create(bootstrap, title="Shared workflow")
    monkeypatch.setattr(
        "app.storage.report_workflow.core_mixin.state_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    stores = [
        ReportWorkflowStore(
            base_dir=f"/virtual/worker-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]

    def create(store: ReportWorkflowStore, index: int) -> str:
        return _create(
            store,
            title=f"Workflow {index}",
        ).report_workflow_id

    def add_asset(store: ReportWorkflowStore, index: int) -> str:
        asset_id = f"asset-{index}"
        store.add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": asset_id}],
            tenant_id="alpha",
        )
        return asset_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created_ids = set(executor.map(create, stores, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        asset_ids = set(executor.map(add_asset, stores, range(20)))

    reloaded = ReportWorkflowStore(
        base_dir="/virtual/reload",
        backend=_s3_backend(client)[0],
    )
    records = reloaded.list_by_tenant("alpha")
    persisted = reloaded.get(workflow.report_workflow_id, tenant_id="alpha")

    assert {record.report_workflow_id for record in records} == {
        workflow.report_workflow_id,
        *created_ids,
    }
    assert persisted is not None
    assert {asset["asset_id"] for asset in persisted.visual_assets} == asset_ids


def test_s3_workflow_cas_preserves_disjoint_slide_approvals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _MemoryS3Client(read_delay=0.002)
    backend, _ = _s3_backend(client)
    bootstrap = ReportWorkflowStore(
        base_dir="/virtual/bootstrap",
        backend=backend,
    )
    workflow = _create_slides_draft(bootstrap)
    monkeypatch.setattr(
        "app.storage.report_workflow.core_mixin.state_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    first_worker = ReportWorkflowStore(
        base_dir="/virtual/first-worker",
        backend=_s3_backend(client)[0],
    )
    second_worker = ReportWorkflowStore(
        base_dir="/virtual/second-worker",
        backend=_s3_backend(client)[0],
    )
    client.coordinate_next_reads(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        updates = list(
            executor.map(
                lambda action: action(),
                (
                    lambda: first_worker.approve_slide(
                        workflow.report_workflow_id,
                        "slide-1",
                        author="first-reviewer",
                        tenant_id="alpha",
                    ),
                    lambda: second_worker.approve_slide(
                        workflow.report_workflow_id,
                        "slide-2",
                        author="second-reviewer",
                        tenant_id="alpha",
                    ),
                ),
            )
        )

    persisted = bootstrap.get(
        workflow.report_workflow_id,
        tenant_id="alpha",
    )

    assert persisted is not None
    assert persisted.status == "slides_approved"
    assert {slide.status for slide in persisted.slides} == {"approved"}
    assert {slide.approved_by for slide in persisted.slides} == {
        "first-reviewer",
        "second-reviewer",
    }
    assert persisted.updated_at == max(update.updated_at for update in updates)


def test_s3_workflow_cas_commits_one_competing_final_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _MemoryS3Client(read_delay=0.002)
    backend, _ = _s3_backend(client)
    bootstrap = ReportWorkflowStore(
        base_dir="/virtual/bootstrap",
        backend=backend,
    )
    workflow = _create_final_review(bootstrap)
    bootstrap.approve_final_step(
        workflow.report_workflow_id,
        stage="pm_review",
        author="pm",
        comment="PM approved",
        tenant_id="alpha",
    )
    monkeypatch.setattr(
        "app.storage.report_workflow.core_mixin.state_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    approve_store = ReportWorkflowStore(
        base_dir="/virtual/approve-worker",
        backend=_s3_backend(client)[0],
    )
    change_store = ReportWorkflowStore(
        base_dir="/virtual/change-worker",
        backend=_s3_backend(client)[0],
    )
    client.coordinate_next_reads(2)

    def approve() -> str | None:
        try:
            return approve_store.approve_final_step(
                workflow.report_workflow_id,
                stage="executive_review",
                author="executive",
                comment="Executive approved",
                tenant_id="alpha",
            ).status
        except ValueError:
            return None

    def request_changes() -> str | None:
        try:
            return change_store.request_final_changes(
                workflow.report_workflow_id,
                author="executive",
                comment="Changes required",
                tenant_id="alpha",
            ).status
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(
            executor.map(
                lambda action: action(),
                (approve, request_changes),
            )
        )

    committed = [decision for decision in decisions if decision is not None]
    persisted = bootstrap.get(
        workflow.report_workflow_id,
        tenant_id="alpha",
    )

    assert len(committed) == 1
    assert persisted is not None
    assert persisted.status == committed[0]
    terminal_comments = [
        comment.content
        for comment in persisted.comments
        if comment.content in {"Executive approved", "Changes required"}
    ]
    assert terminal_comments == [
        "Executive approved"
        if persisted.status == "final_approved"
        else "Changes required"
    ]


def test_s3_workflow_store_reconciles_commit_then_successor_cas() -> None:
    backend, client = _s3_backend()
    store = ReportWorkflowStore(base_dir="/virtual/data", backend=backend)
    successor = ReportWorkflowStore(
        base_dir="/virtual/successor",
        backend=_s3_backend(client)[0],
    )
    workflow = _create(store)

    client.fail_after_next_conditional_write(
        after_write=lambda: successor.add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": "successor-asset"}],
            tenant_id="alpha",
        )
    )
    committed = store.add_visual_assets(
        workflow.report_workflow_id,
        [{"asset_id": "committed-asset"}],
        tenant_id="alpha",
    )

    persisted = store.get(
        workflow.report_workflow_id,
        tenant_id="alpha",
    )

    assert {asset["asset_id"] for asset in committed.visual_assets} == {
        "committed-asset"
    }
    assert persisted is not None
    assert {asset["asset_id"] for asset in persisted.visual_assets} == {
        "committed-asset",
        "successor-asset",
    }


def test_workflow_mutation_receipts_are_bounded_private_and_fail_closed(
    tmp_path: Path,
) -> None:
    store = ReportWorkflowStore(base_dir=str(tmp_path))
    workflow = _create(store)
    path = tmp_path / "tenants/alpha/report_workflows.json"

    for index in range(70):
        store.add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": f"asset-{index}"}],
            tenant_id="alpha",
        )

    records = json.loads(path.read_text(encoding="utf-8"))
    public_record = store.get(
        workflow.report_workflow_id,
        tenant_id="alpha",
    )
    assert public_record is not None
    assert len(records[0]["_mutation_ids"]) == 64
    assert "_mutation_ids" not in asdict(public_record)

    records[0]["_mutation_ids"][0] = records[0]["_mutation_ids"][1]
    path.write_text(json.dumps(records), encoding="utf-8")
    corrupted = path.read_bytes()

    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid owned report workflow record",
    ):
        store.get(workflow.report_workflow_id, tenant_id="alpha")
    with pytest.raises(
        ReportWorkflowStoreError,
        match="Invalid owned report workflow record",
    ):
        store.add_visual_assets(
            workflow.report_workflow_id,
            [{"asset_id": "blocked"}],
            tenant_id="alpha",
        )

    assert path.read_bytes() == corrupted


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


def test_report_workflow_api_preserves_corrupt_state_as_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    path = tmp_path / "tenants/system/report_workflows.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{not-json")

    responses = (
        client.get("/report-workflows"),
        client.post("/report-workflows", json={"title": "Blocked"}),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert path.read_bytes() == b"{not-json"

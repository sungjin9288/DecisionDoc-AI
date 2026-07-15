from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from app.storage.procurement_review_store import (
    ProcurementReviewRecord,
    ProcurementReviewStore,
)


TENANT_ID = "alpha"
PROJECT_ID = "proj-review"
PACKET_CONTENT = b"verified procurement review packet"
PACKET_SHA256 = hashlib.sha256(PACKET_CONTENT).hexdigest()


def _pending_receipt() -> dict:
    return {
        "status": "pending",
        "packet_sha256": PACKET_SHA256,
        "packet_size_bytes": len(PACKET_CONTENT),
        "package_id": "pkg-review",
        "recommendation": "CONDITIONAL_GO",
        "reviewer": "review-owner",
        "decision": None,
        "reviewed_at": None,
        "operational_approval": False,
    }


def _prepare(store: ProcurementReviewStore) -> ProcurementReviewRecord:
    record, created = store.prepare(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_content=PACKET_CONTENT,
        receipt=_pending_receipt(),
        prepared_at="2026-07-16T00:00:00Z",
    )
    assert created is True
    return record


def _completed_receipt(record: ProcurementReviewRecord) -> dict:
    return {
        **record.receipt,
        "status": "completed",
        "decision": "accepted",
        "reviewed_at": "2026-07-16T00:01:00Z",
    }


@pytest.mark.parametrize(
    "tenant_id",
    ("", " alpha", "alpha ", ".", "..", "a/b", "a\\b", "a\x00b"),
)
def test_procurement_review_store_rejects_unsafe_tenant_before_path_use(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store.get(
            tenant_id=tenant_id,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "project_id",
    ("", " project", "project ", ".", "..", "a/b", "a\\b", "a\x00b"),
)
def test_procurement_review_store_rejects_unsafe_project_before_path_use(
    tmp_path: Path,
    project_id: str,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="project_id is invalid"):
        store.get(
            tenant_id=TENANT_ID,
            project_id=project_id,
            packet_sha256=PACKET_SHA256,
        )

    assert not (tmp_path / "tenants").exists()


def test_procurement_review_store_rejects_forged_record_artifact_access(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    pending = _prepare(store)
    forged = replace(pending, tenant_id="foreign")

    with pytest.raises(ValueError, match="does not match caller scope"):
        store.read_packet(
            forged,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(ValueError, match="does not match caller scope"):
        store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=forged,
            completed_receipt=_completed_receipt(pending),
            reviewed_package_content=b"forged reviewed package",
        )

    completed = store.complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=pending,
        completed_receipt=_completed_receipt(pending),
        reviewed_package_content=b"owned reviewed package",
    )
    with pytest.raises(ValueError, match="does not match caller scope"):
        store.read_reviewed_package(
            replace(completed, project_id="foreign-project"),
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    assert not (tmp_path / "tenants" / "foreign").exists()


@pytest.mark.parametrize("drift_field", ("tenant_id", "project_id", "packet_sha256"))
def test_procurement_review_store_preserves_and_excludes_identity_drift(
    tmp_path: Path,
    drift_field: str,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    _prepare(store)
    record_path = (
        tmp_path
        / "tenants"
        / TENANT_ID
        / "procurement_reviews"
        / PROJECT_ID
        / PACKET_SHA256
        / "record.json"
    )
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    if drift_field == "tenant_id":
        payload[drift_field] = "foreign"
    elif drift_field == "project_id":
        payload[drift_field] = "foreign-project"
    else:
        drifted_sha256 = hashlib.sha256(b"foreign packet").hexdigest()
        payload[drift_field] = drifted_sha256
        payload["receipt"]["packet_sha256"] = drifted_sha256
    record_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    original = record_path.read_bytes()

    with pytest.raises(ValueError, match="identity is inconsistent"):
        store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    assert store.list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID) == []
    assert store.list_by_tenant(tenant_id=TENANT_ID) == []
    assert record_path.read_bytes() == original


def test_procurement_review_store_preserves_and_excludes_malformed_record(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    _prepare(store)
    record_path = (
        tmp_path
        / "tenants"
        / TENANT_ID
        / "procurement_reviews"
        / PROJECT_ID
        / PACKET_SHA256
        / "record.json"
    )
    record_path.write_text('{"schema_version":', encoding="utf-8")
    original = record_path.read_bytes()

    with pytest.raises(ValueError, match="stored procurement review record is invalid"):
        store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    assert store.list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID) == []
    assert store.list_by_tenant(tenant_id=TENANT_ID) == []
    assert record_path.read_bytes() == original


def test_procurement_review_store_ignores_nested_project_path_alias(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    record = _prepare(store)
    canonical_path = (
        tmp_path
        / "tenants"
        / TENANT_ID
        / "procurement_reviews"
        / PROJECT_ID
        / PACKET_SHA256
        / "record.json"
    )
    nested_path = canonical_path.parent.parent / "nested" / PACKET_SHA256 / "record.json"
    nested_path.parent.mkdir(parents=True)
    nested_path.write_bytes(canonical_path.read_bytes())

    assert store.list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID) == [record]
    assert nested_path.exists()


def test_procurement_review_store_concurrent_prepare_creates_one_record(
    tmp_path: Path,
) -> None:
    stores = [ProcurementReviewStore(base_dir=str(tmp_path)) for _ in range(20)]
    ready = threading.Barrier(len(stores))

    def prepare(index: int) -> tuple[ProcurementReviewRecord, bool]:
        ready.wait()
        return stores[index].prepare(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_content=PACKET_CONTENT,
            receipt=_pending_receipt(),
            prepared_at="2026-07-16T00:00:00Z",
        )

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        results = list(executor.map(prepare, range(len(stores))))

    records = [record for record, _created in results]
    assert sum(created for _record, created in results) == 1
    assert all(record == records[0] for record in records)
    assert stores[0].list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID) == [
        records[0]
    ]


def test_procurement_review_store_concurrent_completion_succeeds_once(
    tmp_path: Path,
) -> None:
    owner = ProcurementReviewStore(base_dir=str(tmp_path))
    pending = _prepare(owner)
    stores = [ProcurementReviewStore(base_dir=str(tmp_path)) for _ in range(20)]
    ready = threading.Barrier(len(stores))

    def complete(index: int) -> tuple[str, int, bytes]:
        reviewed_package = f"reviewed package {index}".encode()
        ready.wait()
        try:
            stores[index].complete(
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                packet_sha256=PACKET_SHA256,
                current=pending,
                completed_receipt=_completed_receipt(pending),
                reviewed_package_content=reviewed_package,
            )
        except ValueError:
            return "rejected", index, reviewed_package
        return "completed", index, reviewed_package

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        results = list(executor.map(complete, range(len(stores))))

    completed_results = [result for result in results if result[0] == "completed"]
    assert len(completed_results) == 1
    completed = owner.get(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    )
    assert completed is not None
    assert completed.review_status == "completed"
    assert owner.read_reviewed_package(
        completed,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    ) == completed_results[0][2]

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.procurement_review_store import (
    ProcurementReviewRecord,
    ProcurementReviewStore,
    ProcurementReviewStoreError,
)
from app.storage.state_backend import (
    LocalStateBackend,
    S3StateBackend,
    StateBackendError,
)
from app.services.procurement_decision_package.reviewer_attestation import (
    build_procurement_reviewer_attestation,
)


TENANT_ID = "alpha"
PROJECT_ID = "proj-review"
PACKET_CONTENT = b"verified procurement review packet"
PACKET_SHA256 = hashlib.sha256(PACKET_CONTENT).hexdigest()


class _FailingLocalBackend(LocalStateBackend):
    def __init__(self, root: Path, *, operation: str) -> None:
        super().__init__(root)
        self._operation = operation

    def read_text(self, relative_path: str) -> str | None:
        if self._operation == "read_record":
            raise StateBackendError("simulated record read failure")
        return super().read_text(relative_path)

    def read_bytes(self, relative_path: str) -> bytes | None:
        if self._operation == "read_artifact":
            raise StateBackendError("simulated artifact read failure")
        return super().read_bytes(relative_path)

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        if self._operation == "write_record":
            raise StateBackendError("simulated record write failure")
        if self._operation == "write_record_oserror":
            raise OSError("simulated raw record write failure")
        super().write_text(relative_path, text, content_type=content_type)

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if self._operation == "write_record":
            raise StateBackendError("simulated record write failure")
        if self._operation == "write_record_oserror":
            raise OSError("simulated raw record write failure")
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
        if self._operation == "write_record":
            raise StateBackendError("simulated record write failure")
        if self._operation == "write_record_oserror":
            raise OSError("simulated raw record write failure")
        return super().replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )

    def list_prefix(self, relative_prefix: str) -> list[str]:
        if self._operation == "list":
            raise StateBackendError("simulated list failure")
        return super().list_prefix(relative_prefix)


class _CasLosingLocalBackend(LocalStateBackend):
    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        return False


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
        self._fail_after_put_fragments: list[str] = []

    def fail_after_next_put_containing(self, fragment: str) -> None:
        self._fail_after_put_fragments.append(fragment)

    @staticmethod
    def _etag(data: bytes) -> str:
        return f'"{hashlib.sha256(data).hexdigest()}"'

    @staticmethod
    def _error(code: str) -> Exception:
        error = Exception(code)
        error.response = {"Error": {"Code": code}}
        return error

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
            matching_failure = next(
                (
                    fragment
                    for fragment in self._fail_after_put_fragments
                    if fragment in Key
                ),
                None,
            )
            if matching_failure is not None:
                self._fail_after_put_fragments.remove(matching_failure)
                raise self._error("InternalError")

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        time.sleep(self._read_delay)
        return {"Body": _Body(data), "ETag": self._etag(data)}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        with self._lock:
            self.objects.pop((Bucket, Key), None)

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict:
        with self._lock:
            keys = sorted(
                key
                for bucket, key in self.objects
                if bucket == Bucket and key.startswith(Prefix)
            )
        return {"Contents": [{"Key": key} for key in keys]}


def _s3_backend(client: _MemoryS3Client) -> S3StateBackend:
    return S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )


def _review_dir(root: Path) -> Path:
    return (
        root
        / "tenants"
        / TENANT_ID
        / "procurement_reviews"
        / PROJECT_ID
        / PACKET_SHA256
    )


def _reviewed_package_path(root: Path, content: bytes) -> Path:
    return (
        _review_dir(root)
        / "reviewed_packages"
        / f"{hashlib.sha256(content).hexdigest()}.zip"
    )


def _pending_receipt() -> dict:
    return {
        "schema_version": "decisiondoc.procurement_review_receipt.v1",
        "status": "pending",
        "packet_sha256": PACKET_SHA256,
        "packet_size_bytes": len(PACKET_CONTENT),
        "packet_schema_version": "decisiondoc.procurement_review_packet.v1",
        "package_id": "pkg-review",
        "recommendation": "CONDITIONAL_GO",
        "reviewer": "review-owner",
        "decision": None,
        "rationale": None,
        "reviewed_at": None,
        "authorization_boundary": "explicit",
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
        "rationale": "Verified against the packet evidence.",
        "reviewed_at": "2026-07-16T00:01:00Z",
    }


def _identity_bound_prepare(
    store: ProcurementReviewStore,
) -> ProcurementReviewRecord:
    record, created = store.prepare(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_content=PACKET_CONTENT,
        receipt=_pending_receipt(),
        prepared_at="2026-07-16T00:00:00Z",
        reviewer_assignment={
            "user_id": "reviewer-stable-id",
            "username": "review-owner",
        },
    )
    assert created is True
    return record


def _attestation_for(record: ProcurementReviewRecord) -> dict:
    receipt = _completed_receipt(record)
    receipt_content = (
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return build_procurement_reviewer_attestation(
        tenant_id=record.tenant_id,
        project_id=record.project_id,
        packet_sha256=record.packet_sha256,
        completed_receipt_sha256=hashlib.sha256(
            receipt_content
        ).hexdigest(),
        decision="accepted",
        reviewed_at=receipt["reviewed_at"],
        reviewer_user_id="reviewer-stable-id",
        reviewer_username="review-owner",
        reviewer_role="member",
    )


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
def test_procurement_review_store_rejects_identity_drift_without_replacement(
    tmp_path: Path,
    drift_field: str,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    _prepare(store)
    record_path = _review_dir(tmp_path) / "record.json"
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

    with pytest.raises(
        ProcurementReviewStoreError,
        match="identity is inconsistent",
    ):
        store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(ProcurementReviewStoreError, match="identity is inconsistent"):
        store.list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID)
    with pytest.raises(ProcurementReviewStoreError, match="identity is inconsistent"):
        store.list_by_tenant(tenant_id=TENANT_ID)
    assert record_path.read_bytes() == original


@pytest.mark.parametrize(
    "raw",
    (
        b"",
        b'{"schema_version":',
        b'{"duplicate":1,"duplicate":2}',
        b"\xff\xfe",
    ),
)
def test_invalid_procurement_review_record_stops_reads_without_replacement(
    tmp_path: Path,
    raw: bytes,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    _prepare(store)
    record_path = _review_dir(tmp_path) / "record.json"
    record_path.write_bytes(raw)
    original = record_path.read_bytes()

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Invalid procurement review record",
    ):
        store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Invalid procurement review record",
    ):
        store.list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID)
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Invalid procurement review record",
    ):
        store.list_by_tenant(tenant_id=TENANT_ID)
    assert record_path.read_bytes() == original


def test_procurement_review_record_requires_receipt_object(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    _prepare(store)
    record_path = _review_dir(tmp_path) / "record.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["receipt"] = list(payload["receipt"].items())
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    original = record_path.read_bytes()

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Invalid procurement review record",
    ):
        store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    assert record_path.read_bytes() == original


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", "unexpected"),
        ("authorization_boundary", "operational"),
        ("rationale", "forged pending rationale"),
    ),
)
def test_procurement_review_record_rejects_receipt_authority_drift(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    _prepare(store)
    record_path = _review_dir(tmp_path) / "record.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["receipt"][field] = value
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    original = record_path.read_bytes()

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Invalid procurement review record",
    ):
        store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

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
    pending = _identity_bound_prepare(owner)
    stores = [ProcurementReviewStore(base_dir=str(tmp_path)) for _ in range(20)]
    ready = threading.Barrier(len(stores))
    reviewer_attestation = _attestation_for(pending)

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
                reviewer_attestation=reviewer_attestation,
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
    assert completed.reviewer_session_bound is True
    assert completed.reviewer_attestation == reviewer_attestation
    assert owner.read_reviewed_package(
        completed,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    ) == completed_results[0][2]


def test_packet_tamper_blocks_read_and_completion_without_record_change(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    pending = _prepare(store)
    record_path = _review_dir(tmp_path) / "record.json"
    packet_path = _review_dir(tmp_path) / "packet.zip"
    record_bytes = record_path.read_bytes()
    packet_path.write_bytes(b"tampered packet")

    with pytest.raises(
        ProcurementReviewStoreError,
        match="packet evidence is inconsistent",
    ):
        store.read_packet(
            pending,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(
        ProcurementReviewStoreError,
        match="packet evidence is inconsistent",
    ):
        store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=pending,
            completed_receipt=_completed_receipt(pending),
            reviewed_package_content=b"blocked reviewed package",
        )

    assert record_path.read_bytes() == record_bytes
    assert not (_review_dir(tmp_path) / "reviewed_package.zip").exists()


def test_missing_packet_blocks_read_and_completion_without_record_change(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    pending = _prepare(store)
    record_path = _review_dir(tmp_path) / "record.json"
    record_bytes = record_path.read_bytes()
    (_review_dir(tmp_path) / "packet.zip").unlink()

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Procurement review packet is missing",
    ):
        store.read_packet(
            pending,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Procurement review packet is missing",
    ):
        store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=pending,
            completed_receipt=_completed_receipt(pending),
            reviewed_package_content=b"blocked reviewed package",
        )
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Procurement review packet is missing",
    ):
        store.list_by_project(tenant_id=TENANT_ID, project_id=PROJECT_ID)

    assert record_path.read_bytes() == record_bytes
    assert not (_review_dir(tmp_path) / "reviewed_package.zip").exists()


def test_record_disappearance_after_lookup_is_persisted_state_error(
    tmp_path: Path,
) -> None:
    read_root = tmp_path / "read"
    read_store = ProcurementReviewStore(base_dir=str(read_root))
    pending_for_read = _prepare(read_store)
    (_review_dir(read_root) / "record.json").unlink()
    with pytest.raises(
        ProcurementReviewStoreError,
        match="record is missing before packet read",
    ):
        read_store.read_packet(
            pending_for_read,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    complete_root = tmp_path / "complete"
    complete_store = ProcurementReviewStore(base_dir=str(complete_root))
    pending_for_completion = _prepare(complete_store)
    (_review_dir(complete_root) / "record.json").unlink()
    with pytest.raises(
        ProcurementReviewStoreError,
        match="record is missing before completion",
    ):
        complete_store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=pending_for_completion,
            completed_receipt=_completed_receipt(pending_for_completion),
            reviewed_package_content=b"reviewed package",
        )

    package_root = tmp_path / "package"
    package_store = ProcurementReviewStore(base_dir=str(package_root))
    pending_for_package = _prepare(package_store)
    completed = package_store.complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=pending_for_package,
        completed_receipt=_completed_receipt(pending_for_package),
        reviewed_package_content=b"reviewed package",
    )
    (_review_dir(package_root) / "record.json").unlink()
    with pytest.raises(
        ProcurementReviewStoreError,
        match="record is missing before package read",
    ):
        package_store.read_reviewed_package(
            completed,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )


def test_reviewed_package_tamper_is_rejected_without_record_change(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    pending = _prepare(store)
    reviewed_package = b"verified reviewed package"
    completed = store.complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=pending,
        completed_receipt=_completed_receipt(pending),
        reviewed_package_content=reviewed_package,
    )
    record_path = _review_dir(tmp_path) / "record.json"
    record_bytes = record_path.read_bytes()
    _reviewed_package_path(tmp_path, reviewed_package).write_bytes(b"tampered")

    with pytest.raises(
        ProcurementReviewStoreError,
        match="reviewed package evidence is inconsistent",
    ):
        store.read_reviewed_package(
            completed,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )

    assert record_path.read_bytes() == record_bytes


def test_missing_reviewed_package_is_rejected_without_record_change(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(base_dir=str(tmp_path))
    pending = _prepare(store)
    reviewed_package = b"verified reviewed package"
    completed = store.complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=pending,
        completed_receipt=_completed_receipt(pending),
        reviewed_package_content=reviewed_package,
    )
    record_path = _review_dir(tmp_path) / "record.json"
    record_bytes = record_path.read_bytes()
    _reviewed_package_path(tmp_path, reviewed_package).unlink()

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Procurement reviewed package is missing",
    ):
        store.read_reviewed_package(
            completed,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Procurement reviewed package is missing",
    ):
        store.list_by_tenant(tenant_id=TENANT_ID)

    assert record_path.read_bytes() == record_bytes


def test_backend_failures_are_separate_from_review_input_errors(
    tmp_path: Path,
) -> None:
    read_store = ProcurementReviewStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="read_record"),
    )
    list_store = ProcurementReviewStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="list"),
    )

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Invalid procurement review record",
    ):
        read_store.get(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Failed to list procurement review records",
    ):
        list_store.list_by_tenant(tenant_id=TENANT_ID)


def test_artifact_read_failure_does_not_look_like_missing_evidence(
    tmp_path: Path,
) -> None:
    pending = _prepare(ProcurementReviewStore(base_dir=str(tmp_path)))
    store = ProcurementReviewStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="read_artifact"),
    )

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Failed to read procurement review packet",
    ):
        store.read_packet(
            pending,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
        )


def test_prepare_recovers_exact_packet_after_record_write_fails(
    tmp_path: Path,
) -> None:
    store = ProcurementReviewStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="write_record"),
    )

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Failed to persist procurement review record",
    ):
        store.prepare(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_content=PACKET_CONTENT,
            receipt=_pending_receipt(),
            prepared_at="2026-07-16T00:00:00Z",
        )

    assert (_review_dir(tmp_path) / "packet.zip").read_bytes() == PACKET_CONTENT
    assert not (_review_dir(tmp_path) / "record.json").exists()

    recovered, created = ProcurementReviewStore(base_dir=str(tmp_path)).prepare(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_content=PACKET_CONTENT,
        receipt=_pending_receipt(),
        prepared_at="2026-07-16T00:00:01Z",
    )
    assert created is True
    assert recovered.review_status == "pending"


def test_completion_recovers_immutable_package_after_record_write_fails(
    tmp_path: Path,
) -> None:
    pending = _prepare(ProcurementReviewStore(base_dir=str(tmp_path)))
    record_path = _review_dir(tmp_path) / "record.json"
    pending_bytes = record_path.read_bytes()
    store = ProcurementReviewStore(
        base_dir=str(tmp_path),
        backend=_FailingLocalBackend(tmp_path, operation="write_record"),
    )

    reviewed_package = b"recoverable reviewed package"
    with pytest.raises(
        ProcurementReviewStoreError,
        match="Failed to persist procurement review record",
    ):
        store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=pending,
            completed_receipt=_completed_receipt(pending),
            reviewed_package_content=reviewed_package,
        )

    assert record_path.read_bytes() == pending_bytes
    assert _reviewed_package_path(tmp_path, reviewed_package).read_bytes() == reviewed_package

    recovered = ProcurementReviewStore(base_dir=str(tmp_path)).complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=pending,
        completed_receipt=_completed_receipt(pending),
        reviewed_package_content=reviewed_package,
    )
    assert recovered.review_status == "completed"


def test_completion_removes_unreferenced_package_after_confirmed_cas_loss(
    tmp_path: Path,
) -> None:
    pending = _prepare(ProcurementReviewStore(base_dir=str(tmp_path)))
    reviewed_package = b"cas-loser reviewed package"
    store = ProcurementReviewStore(
        base_dir=str(tmp_path),
        backend=_CasLosingLocalBackend(tmp_path),
    )

    with pytest.raises(
        ValueError,
        match="record changed before completion",
    ):
        store.complete(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_sha256=PACKET_SHA256,
            current=pending,
            completed_receipt=_completed_receipt(pending),
            reviewed_package_content=reviewed_package,
        )

    assert not _reviewed_package_path(tmp_path, reviewed_package).exists()
    assert store.get(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    ) == pending


def test_prepare_adopts_exact_packet_artifact_without_overwriting_it(
    tmp_path: Path,
) -> None:
    artifact_path = _review_dir(tmp_path) / "packet.zip"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(PACKET_CONTENT)
    store = ProcurementReviewStore(base_dir=str(tmp_path))

    record, created = store.prepare(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_content=PACKET_CONTENT,
        receipt=_pending_receipt(),
        prepared_at="2026-07-16T00:00:00Z",
    )

    assert created is True
    assert record.review_status == "pending"
    assert artifact_path.read_bytes() == PACKET_CONTENT


def test_prepare_rejects_unbound_reviewed_package_without_overwriting_it(
    tmp_path: Path,
) -> None:
    artifact_path = _review_dir(tmp_path) / "reviewed_package.zip"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"orphan reviewed package")
    store = ProcurementReviewStore(base_dir=str(tmp_path))

    with pytest.raises(
        ProcurementReviewStoreError,
        match="Unexpected procurement review artifacts",
    ):
        store.prepare(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_content=PACKET_CONTENT,
            receipt=_pending_receipt(),
            prepared_at="2026-07-16T00:00:00Z",
        )

    assert artifact_path.read_bytes() == b"orphan reviewed package"
    assert not (_review_dir(tmp_path) / "record.json").exists()


@pytest.mark.parametrize(
    "failure_fragment",
    ("packet.zip", "record.json"),
)
def test_s3_prepare_reconciles_commit_then_error(
    failure_fragment: str,
) -> None:
    client = _MemoryS3Client()
    client.fail_after_next_put_containing(failure_fragment)
    store = ProcurementReviewStore(
        base_dir="/virtual/review",
        backend=_s3_backend(client),
    )

    record, created = store.prepare(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_content=PACKET_CONTENT,
        receipt=_pending_receipt(),
        prepared_at="2026-07-16T00:00:00Z",
    )

    assert created is True
    assert record.review_status == "pending"
    assert store.read_packet(
        record,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    ) == PACKET_CONTENT


@pytest.mark.parametrize(
    "failure_fragment",
    ("reviewed_packages/", "record.json"),
)
def test_s3_completion_reconciles_commit_then_error(
    failure_fragment: str,
) -> None:
    client = _MemoryS3Client()
    store = ProcurementReviewStore(
        base_dir="/virtual/review",
        backend=_s3_backend(client),
    )
    pending = _prepare(store)
    client.fail_after_next_put_containing(failure_fragment)
    reviewed_package = b"verified reviewed package after uncertain commit"

    completed = store.complete(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
        current=pending,
        completed_receipt=_completed_receipt(pending),
        reviewed_package_content=reviewed_package,
    )

    assert completed.review_status == "completed"
    assert store.read_reviewed_package(
        completed,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    ) == reviewed_package


def test_s3_conditional_prepare_succeeds_once_without_process_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.storage.procurement_review_store.state_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    client = _MemoryS3Client(read_delay=0.005)
    stores = [
        ProcurementReviewStore(
            base_dir=f"/virtual/review-{index}",
            backend=_s3_backend(client),
        )
        for index in range(20)
    ]
    ready = threading.Barrier(len(stores))

    def prepare(index: int) -> tuple[ProcurementReviewRecord, bool]:
        ready.wait()
        return stores[index].prepare(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            packet_content=PACKET_CONTENT,
            receipt=_pending_receipt(),
            prepared_at=f"2026-07-16T00:00:{index:02d}Z",
        )

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        results = list(executor.map(prepare, range(len(stores))))

    assert sum(created for _record, created in results) == 1
    first_record = results[0][0]
    assert all(record == first_record for record, _created in results)


def test_s3_conditional_completion_succeeds_once_without_process_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.storage.procurement_review_store.state_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    client = _MemoryS3Client(read_delay=0.005)
    pending = _identity_bound_prepare(
        ProcurementReviewStore(
            base_dir="/virtual/bootstrap",
            backend=_s3_backend(client),
        )
    )
    stores = [
        ProcurementReviewStore(
            base_dir=f"/virtual/review-{index}",
            backend=_s3_backend(client),
        )
        for index in range(20)
    ]
    ready = threading.Barrier(len(stores))
    reviewer_attestation = _attestation_for(pending)

    def complete(index: int) -> tuple[str, bytes]:
        package = f"reviewed package {index}".encode()
        ready.wait()
        try:
            stores[index].complete(
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                packet_sha256=PACKET_SHA256,
                current=pending,
                completed_receipt=_completed_receipt(pending),
                reviewed_package_content=package,
                reviewer_attestation=reviewer_attestation,
            )
        except ValueError:
            return "rejected", package
        return "completed", package

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        results = list(executor.map(complete, range(len(stores))))

    completed_packages = [
        package
        for status, package in results
        if status == "completed"
    ]
    assert len(completed_packages) == 1
    reloaded_store = ProcurementReviewStore(
        base_dir="/another/virtual/root",
        backend=_s3_backend(client),
    )
    completed = reloaded_store.get(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    )
    assert completed is not None
    assert completed.reviewer_identity_bound is True
    assert completed.reviewer_session_bound is True
    assert completed.reviewer_attestation == reviewer_attestation
    assert reloaded_store.read_reviewed_package(
        completed,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        packet_sha256=PACKET_SHA256,
    ) == completed_packages[0]
    package_keys = [
        key
        for bucket, key in client.objects
        if bucket == "unit-bucket" and "/reviewed_packages/" in key
    ]
    assert len(package_keys) == 1


def test_procurement_review_api_preserves_corrupt_state_as_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    from app.services.auth_service import issue_auth_token_pair
    from app.storage.user_store import get_user_store

    client = TestClient(create_app(), raise_server_exceptions=False)
    user_store = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    admin = user_store.create_first_admin(
        username="corrupt-review-admin",
        display_name="Corrupt Review Admin",
        email="corrupt-review-admin@example.com",
        password="StrongPassword123!",
    )
    tokens = issue_auth_token_pair(
        admin,
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    project = client.app.state.project_store.create(
        "system",
        name="Corrupt review project",
    )
    record_path = (
        tmp_path
        / "tenants"
        / "system"
        / "procurement_reviews"
        / project.project_id
        / PACKET_SHA256
        / "record.json"
    )
    record_path.parent.mkdir(parents=True)
    record_path.write_bytes(b"{not-json")

    responses = (
        client.get("/procurement/reviews", headers=headers),
        client.get(
            f"/projects/{project.project_id}/procurement/reviews",
            headers=headers,
        ),
        client.get(
            f"/projects/{project.project_id}/procurement/reviews/"
            f"{PACKET_SHA256}/reviewed-package",
            headers=headers,
        ),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert record_path.read_bytes() == b"{not-json"

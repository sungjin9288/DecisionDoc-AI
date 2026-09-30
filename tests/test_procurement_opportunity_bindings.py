"""Opportunity-bound Council and review evidence with local/fake-S3 storage."""

import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
    ProcurementRecommendation,
)
from app.services.decision_council.service import DecisionCouncilService
from app.services.procurement_decision_package.review_packet import (
    build_project_procurement_review_packet,
    verify_procurement_review_packet,
)
from app.services.procurement_decision_package.package_builder import (
    _demo_decision_hard_filters,
    _demo_decision_score_breakdown,
    _demo_decision_checklist_items,
)
from app.storage.decision_council_store import DecisionCouncilStore
from app.storage.procurement_project_state import ProcurementDecisionEntry
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.state_backend import LocalStateBackend
from tests.test_procurement_review_store import _MemoryS3Client, _s3_backend


@pytest.fixture(params=["local", "fake-s3"])
def backend(request, tmp_path):
    return (
        LocalStateBackend(tmp_path)
        if request.param == "local"
        else _s3_backend(_MemoryS3Client())
    )


def _entry(backend, source="A"):
    legacy = ProcurementDecisionStore(backend=backend)
    snapshot = legacy.save_source_snapshot(
        tenant_id="alpha",
        project_id="project-a",
        source_kind="g2b_import",
        payload={"source": source},
    )
    record = legacy.upsert(
        ProcurementDecisionUpsert(
            tenant_id="alpha",
            project_id="project-a",
            source_snapshots=[snapshot],
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b", source_id=source, title=source
            ),
            hard_filters=_demo_decision_hard_filters(),
            score_breakdown=_demo_decision_score_breakdown(),
            checklist_items=_demo_decision_checklist_items(),
            missing_data=["Local missing evidence"],
            soft_fit_score=68.0,
            soft_fit_status="scored",
            recommendation=ProcurementRecommendation(
                value="CONDITIONAL_GO",
                summary="Local fixture",
                evidence=["Local source fact"],
            ),
        )
    )
    record.decision_id = str(uuid4())
    return ProcurementDecisionEntry(record=record, decision_revision=2)


def _capture(entry, backend):
    from app.services.procurement_source_binding import (
        capture_procurement_source_binding,
    )

    return capture_procurement_source_binding(entry, backend=backend)


def _run(service, entry, binding=None):
    options = {} if binding is None else {"source_binding": binding}
    return service.run_procurement_council(
        tenant_id="alpha",
        project_id="project-a",
        goal="Review this opportunity",
        procurement_record=entry.record,
        **options,
    )


def test_capture_hashes_exact_bytes_and_requires_snapshot_presence(backend):
    entry = _entry(backend)
    binding = _capture(entry, backend)
    path = entry.record.source_snapshots[0].storage_path
    raw = backend.read_bytes(path)
    assert binding.snapshots[0].sha256 == hashlib.sha256(raw).hexdigest()
    assert binding.snapshots[0].size_bytes == len(raw)
    assert binding.decision_revision == 2
    assert binding.decision_id == entry.record.decision_id
    entry.record.source_snapshots[0].snapshot_id = "missing"
    entry.record.source_snapshots[
        0
    ].storage_path = "tenants/alpha/procurement_snapshots/project-a/missing.json"
    with pytest.raises(ValueError):
        _capture(entry, backend)


def test_capture_rejects_records_without_source_snapshots(backend):
    entry = _entry(backend)
    entry.record.source_snapshots = []
    with pytest.raises(ValueError):
        _capture(entry, backend)


def test_council_a_b_are_independent_and_legacy_fallback_does_not_write(backend):
    store = DecisionCouncilStore(backend=backend)
    service = DecisionCouncilService(decision_council_store=store)
    a, b = _entry(backend), _entry(backend, "B")
    legacy = _run(service, a)
    path = "tenants/alpha/decision_council_sessions.json"
    before = backend.read_text(path)
    assert service.get_latest_procurement_council(
        tenant_id="alpha", project_id="project-a", decision_id=a.record.decision_id
    ) == legacy.model_copy(update={"operation": None})
    assert (
        service.get_latest_procurement_council(
            tenant_id="alpha", project_id="project-a", decision_id=b.record.decision_id
        )
        is None
    )
    assert backend.read_text(path) == before
    first_a, first_b = (
        _run(service, a, _capture(a, backend)),
        _run(service, b, _capture(b, backend)),
    )
    assert len({legacy.session_id, first_a.session_id, first_b.session_id}) == 3
    assert first_a.session_key != first_b.session_key
    second_a = _run(service, a, _capture(a, backend))
    assert second_a.session_revision == 2
    assert second_a.session_id == first_a.session_id
    assert service.get_latest_procurement_council(
        tenant_id="alpha", project_id="project-a", decision_id=b.record.decision_id
    ) == first_b.model_copy(update={"operation": None})
    assert json.loads(backend.read_text(path))[0] == json.loads(before)[0]


def test_same_timestamp_revision_and_raw_byte_changes_invalidate_only_a(backend):
    service = DecisionCouncilService(
        decision_council_store=DecisionCouncilStore(backend=backend)
    )
    a, b = _entry(backend), _entry(backend, "B")
    a_binding, b_binding = _capture(a, backend), _capture(b, backend)
    a_session, b_session = _run(service, a, a_binding), _run(service, b, b_binding)
    for changed in (
        a.model_copy(update={"decision_revision": 3}, deep=True),
        a.model_copy(deep=True),
    ):
        if changed.decision_revision == 2:
            backend.write_text(
                a.record.source_snapshots[0].storage_path, '{"source": "changed"}'
            )
        attached = service.attach_procurement_binding(
            session=a_session,
            procurement_record=changed.record,
            source_binding=_capture(changed, backend),
        )
        assert attached.current_procurement_binding_status == "stale"
    assert (
        service.attach_procurement_binding(
            session=b_session,
            procurement_record=b.record,
            source_binding=_capture(b, backend),
        ).current_procurement_binding_status
        == "current"
    )
    assert (
        service.attach_procurement_binding(
            session=a_session, procurement_record=a.record
        ).current_procurement_binding_status
        == "stale"
    )


def test_binding_rejects_foreign_scope_before_council_write(backend):
    service = DecisionCouncilService(
        decision_council_store=DecisionCouncilStore(backend=backend)
    )
    a, b = _entry(backend), _entry(backend, "B")
    with pytest.raises(ValueError):
        _run(service, a, _capture(b, backend))
    assert backend.read_text("tenants/alpha/decision_council_sessions.json") is None


def test_packet_v2_roundtrip_keeps_v1_bytes_and_does_not_claim_raw_proof(backend):
    entry = _entry(backend)
    original = build_project_procurement_review_packet(
        entry.record, reviewer_owner="reviewer"
    )
    packet = build_project_procurement_review_packet(
        entry.record, reviewer_owner="reviewer", source_binding=_capture(entry, backend)
    )
    verified = verify_procurement_review_packet(
        packet.content, expected_tenant_id="alpha", expected_project_id="project-a"
    )
    assert verified["schema_version"] == "decisiondoc.procurement_review_packet.v2"
    assert verified["source_binding"]["decision_id"] == entry.record.decision_id
    assert verified["source_bytes_verified"] is False
    assert verified["operational_approval"] is False
    assert verify_procurement_review_packet(original.content)[
        "schema_version"
    ].endswith(".v1")
    assert (
        build_project_procurement_review_packet(
            entry.record, reviewer_owner="reviewer"
        ).content
        == original.content
    )
    with pytest.raises(ValueError):
        verify_procurement_review_packet(
            packet.content,
            expected_tenant_id="foreign",
            expected_project_id="project-a",
        )


@pytest.mark.parametrize(
    "field,value",
    [("decision_id", "wrong"), ("decision_revision", True), ("unexpected", "field")],
)
def test_packet_binding_tamper_is_rejected(backend, field, value):
    entry = _entry(backend)
    packet = build_project_procurement_review_packet(
        entry.record, reviewer_owner="reviewer", source_binding=_capture(entry, backend)
    )
    with zipfile.ZipFile(io.BytesIO(packet.content)) as archive:
        entries = [
            (item.filename, archive.read(item.filename)) for item in archive.infolist()
        ]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries:
            if name == "packet_manifest.json":
                manifest = json.loads(content)
                manifest["source_binding"][field] = value
                content = json.dumps(manifest).encode()
            archive.writestr(name, content)
    with pytest.raises(ValueError):
        verify_procurement_review_packet(output.getvalue())


def _packet(entry, backend):
    return build_project_procurement_review_packet(
        entry.record, reviewer_owner="reviewer", source_binding=_capture(entry, backend)
    )


def _prepare(store, packet, *, reviewer_id=None, project_id="project-a"):
    from app.services.procurement_decision_package.review_receipt import (
        build_pending_procurement_review_receipt,
    )

    assignment = (
        None
        if reviewer_id is None
        else {"user_id": reviewer_id, "username": "reviewer"}
    )
    return store.prepare(
        tenant_id="alpha",
        project_id=project_id,
        packet_content=packet.content,
        receipt=build_pending_procurement_review_receipt(packet.content),
        prepared_at="2026-09-21T00:00:00Z",
        reviewer_assignment=assignment,
    )[0]


def test_foreign_packet_prepare_fails_before_any_artifact_write(backend):
    from app.storage.procurement_review_store import ProcurementReviewStore

    packet = _packet(_entry(backend), backend)
    store = ProcurementReviewStore(backend=backend)
    before = backend.list_prefix("tenants/alpha/procurement_reviews")
    with pytest.raises(ValueError):
        _prepare(store, packet, project_id="foreign-project")
    assert backend.list_prefix("tenants/alpha/procurement_reviews") == before


@pytest.mark.parametrize("identity_bound", [False, True])
def test_bound_receipt_and_completed_package_roundtrip_is_immutable(
    backend, identity_bound
):
    from app.services.procurement_decision_package.review_receipt import (
        record_procurement_review_decision,
    )
    from app.services.procurement_decision_package.reviewed_package import (
        build_procurement_reviewed_package,
        verify_procurement_reviewed_package,
    )
    from app.storage.procurement_review_store import ProcurementReviewStore
    from app.services.procurement_decision_package.reviewer_attestation import (
        build_procurement_reviewer_attestation,
    )

    a, b = _entry(backend), _entry(backend, "B")
    packet = _packet(a, backend)
    store = ProcurementReviewStore(backend=backend)
    pending = _prepare(
        store, packet, reviewer_id="reviewer-a" if identity_bound else None
    )
    receipt = record_procurement_review_decision(
        pending.receipt,
        packet.content,
        reviewer="reviewer",
        decision="accepted",
        rationale="Local review only",
        reviewed_at="2026-09-21T00:01:00Z",
    )
    receipt_content = (
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    attestation = (
        build_procurement_reviewer_attestation(
            tenant_id="alpha",
            project_id="project-a",
            packet_sha256=packet.sha256,
            completed_receipt_sha256=hashlib.sha256(receipt_content).hexdigest(),
            decision="accepted",
            reviewed_at=receipt["reviewed_at"],
            reviewer_user_id="reviewer-a",
            reviewer_username="reviewer",
            reviewer_role="member",
        )
        if identity_bound
        else None
    )
    scope = {
        "expected_tenant_id": "alpha",
        "expected_project_id": "project-a",
        "expected_reviewer_user_id": "reviewer-a" if identity_bound else None,
    }
    content, _ = build_procurement_reviewed_package(
        packet.content,
        receipt,
        receipt_content=receipt_content,
        reviewer_attestation=attestation,
        **scope,
    )
    verified = verify_procurement_reviewed_package(content, **scope)
    assert verified["source_binding"]["decision_id"] == a.record.decision_id
    assert verified["operational_approval"] is False
    with pytest.raises(ValueError):
        verify_procurement_reviewed_package(content, expected_tenant_id="other")
    completed = store.complete(
        tenant_id="alpha",
        project_id="project-a",
        packet_sha256=packet.sha256,
        current=pending,
        completed_receipt=receipt,
        reviewed_package_content=content,
        reviewer_attestation=attestation,
    )
    _prepare(store, _packet(b, backend))
    backend.write_text(a.record.source_snapshots[0].storage_path, '{"updated":true}')
    assert (
        store.read_packet(
            completed,
            tenant_id="alpha",
            project_id="project-a",
            packet_sha256=packet.sha256,
        )
        == packet.content
    )
    assert (
        store.read_reviewed_package(
            completed,
            tenant_id="alpha",
            project_id="project-a",
            packet_sha256=packet.sha256,
        )
        == content
    )
    assert completed.receipt == receipt


@pytest.mark.parametrize("change", ["invalid_zip", "receipt_downgrade"])
def test_bound_completion_rejects_invalid_evidence_without_writes(backend, change):
    from app.services.procurement_decision_package.review_receipt import (
        record_procurement_review_decision,
    )
    from app.storage.procurement_review_store import (
        ProcurementReviewStore,
        ProcurementReviewStoreError,
    )

    packet = _packet(_entry(backend), backend)
    store = ProcurementReviewStore(backend=backend)
    pending = _prepare(store, packet)
    receipt = record_procurement_review_decision(
        pending.receipt,
        packet.content,
        reviewer="reviewer",
        decision="accepted",
        rationale="Local review",
        reviewed_at="2026-09-21T00:01:00Z",
    )
    if change == "receipt_downgrade":
        receipt["packet_schema_version"] = "decisiondoc.procurement_review_packet.v1"
    scope = {
        "tenant_id": "alpha",
        "project_id": "project-a",
        "packet_sha256": packet.sha256,
    }
    prefix = f"tenants/alpha/procurement_reviews/project-a/{packet.sha256}"
    before = {path: backend.read_bytes(path) for path in backend.list_prefix(prefix)}
    with pytest.raises((ValueError, ProcurementReviewStoreError)):
        store.complete(
            **scope,
            current=pending,
            completed_receipt=receipt,
            reviewed_package_content=b"Opaque package bytes are not valid evidence",
        )
    assert store.get(**scope) == pending
    assert {
        path: backend.read_bytes(path) for path in backend.list_prefix(prefix)
    } == before


def test_bound_packet_read_rejects_receipt_downgrade_without_optional_validator(
    backend,
):
    from app.storage.procurement_review_store import (
        ProcurementReviewStore,
        ProcurementReviewStoreError,
    )

    packet = _packet(_entry(backend), backend)
    store = ProcurementReviewStore(backend=backend)
    _prepare(store, packet)
    path = f"tenants/alpha/procurement_reviews/project-a/{packet.sha256}/record.json"
    payload = json.loads(backend.read_text(path))
    payload["receipt"]["packet_schema_version"] = (
        "decisiondoc.procurement_review_packet.v1"
    )
    backend.write_text(path, json.dumps(payload))
    scope = {
        "tenant_id": "alpha",
        "project_id": "project-a",
        "packet_sha256": packet.sha256,
    }
    before = backend.read_bytes(path)
    with pytest.raises(ProcurementReviewStoreError, match="semantics"):
        store.read_packet(store.get(**scope), **scope)
    assert backend.read_bytes(path) == before


@pytest.mark.parametrize(
    "change", ["missing", "downgrade", "duplicate", "boolean_size", "empty_snapshots"]
)
def test_packet_schema_and_snapshot_shape_cannot_bypass_binding(backend, change):
    packet = _packet(_entry(backend), backend)
    with zipfile.ZipFile(io.BytesIO(packet.content)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries["packet_manifest.json"])
    if change == "missing":
        del manifest["source_binding"]
    elif change == "downgrade":
        manifest["schema_version"] = "decisiondoc.procurement_review_packet.v1"
    elif change == "duplicate":
        manifest["source_binding"]["snapshots"] *= 2
    elif change == "empty_snapshots":
        manifest["source_binding"]["snapshots"] = []
    else:
        manifest["source_binding"]["snapshots"][0]["size_bytes"] = True
    entries["packet_manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    from app.services.procurement_decision_package.review_packet import (
        verify_bound_procurement_packet,
    )

    with pytest.raises(ValueError):
        verify_bound_procurement_packet(
            output.getvalue(),
            expected_tenant_id="alpha",
            expected_project_id="project-a",
        )


def test_bound_prepare_requires_matching_receipt_without_optional_validator(backend):
    from app.services.procurement_decision_package.review_receipt import (
        build_pending_procurement_review_receipt,
    )
    from app.storage.procurement_review_store import ProcurementReviewStore

    packet = _packet(_entry(backend), backend)
    receipt = build_pending_procurement_review_receipt(packet.content)
    receipt["packet_schema_version"] = "decisiondoc.procurement_review_packet.v1"
    with pytest.raises(ValueError):
        ProcurementReviewStore(backend=backend).prepare(
            tenant_id="alpha",
            project_id="project-a",
            packet_content=packet.content,
            receipt=receipt,
            prepared_at="2026-09-21T00:00:00Z",
        )
    assert backend.list_prefix("tenants/alpha/procurement_reviews") == []


def test_decision_filter_does_not_read_unassigned_packet_or_adopt_legacy(
    backend, monkeypatch
):
    from app.storage.procurement_review_store import ProcurementReviewStore

    a, b = _entry(backend), _entry(backend, "B")
    store = ProcurementReviewStore(backend=backend)
    a_review = _prepare(store, _packet(a, backend), reviewer_id="reviewer-a")
    b_review = _prepare(store, _packet(b, backend), reviewer_id="reviewer-b")
    old_packet = build_project_procurement_review_packet(
        a.record, reviewer_owner="reviewer"
    )
    _prepare(store, old_packet, reviewer_id="reviewer-a")
    original = backend.read_bytes
    reads = []

    def inspect(path):
        reads.append(path)
        assert not (b_review.packet_sha256 in path and path.endswith(".zip"))
        return original(path)

    monkeypatch.setattr(backend, "read_bytes", inspect)
    records = store.list_by_project(
        tenant_id="alpha", project_id="project-a", reviewer_user_id="reviewer-a"
    )
    filtered = store.filter_by_decision(
        records,
        tenant_id="alpha",
        project_id="project-a",
        decision_id=a.record.decision_id,
    )
    assert filtered == [a_review]
    assert (
        store.filter_by_decision(
            records,
            tenant_id="alpha",
            project_id="project-a",
            decision_id=b.record.decision_id,
        )
        == []
    )
    assert reads

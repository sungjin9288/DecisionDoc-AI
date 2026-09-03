from __future__ import annotations

import json

import pytest

from app.services.generation_export_packet import (
    AUTHORITY_FALSE,
    build_generated_document_review_packet,
    verify_generation_export_packet,
)
from app.storage.generated_document_review_store import (
    GeneratedDocumentReviewStore,
    GeneratedDocumentReviewStoreError,
)
from app.storage.state_backend import StateBackendError
from tests.async_helper import run_async


DOCS = [{"doc_type": "adr", "markdown": "# 검토 대상\n\n본문"}]
CREATOR = {"user_id": "user-admin", "username": "admin", "role": "admin"}
REVIEWER = {"user_id": "user-reviewer", "username": "reviewer", "role": "member"}


def _packet() -> tuple[dict, dict]:
    packet = run_async(
        build_generated_document_review_packet(
            docs=DOCS,
            title="검토 문서",
            tenant_id="tenant-a",
            project_id="project-a",
            project_document_id="document-a",
            request_id="request-a",
            bundle_id="bundle-a",
            document_source_sha256="a" * 64,
            formats=("docx",),
        )
    )
    return packet, verify_generation_export_packet(packet["content"])


def _prepare(
    store: GeneratedDocumentReviewStore,
    *,
    reviewer_assignment: dict[str, str] = REVIEWER,
    prepared_at: str = "2026-09-03T00:00:00+00:00",
):
    packet, verification = _packet()
    record, created = store.prepare(
        tenant_id="tenant-a",
        project_id="project-a",
        project_document_id="document-a",
        packet_content=packet["content"],
        packet_verification=verification,
        prepared_at=prepared_at,
        creator_assignment=CREATOR,
        reviewer_assignment=reviewer_assignment,
    )
    return packet, verification, record, created


def test_store_persists_exact_packet_and_closed_pending_record(tmp_path):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))

    packet, verification, record, created = _prepare(store)

    assert created is True
    assert record.schema_version == "decisiondoc.generated_document_review_handoff.v1"
    assert record.review_status == "pending"
    assert record.authority == AUTHORITY_FALSE
    assert record.review_only is True
    assert record.packet_persisted is True
    assert record.human_review_completed is False
    assert record.operational_approval is False
    assert store.read_packet(record, tenant_id="tenant-a") == packet["content"]
    assert store.packet_path(
        tenant_id="tenant-a", packet_sha256=verification["packet_sha256"]
    ) == (
        "tenants/tenant-a/generated_document_reviews/packets/"
        f"{verification['packet_sha256']}.zip"
    )
    assert store.record_path(
        tenant_id="tenant-a",
        project_id="project-a",
        project_document_id="document-a",
        packet_sha256=verification["packet_sha256"],
    ).endswith(
        f"projects/project-a/document-a/{verification['packet_sha256']}/record.json"
    )


def test_store_exact_replay_returns_original_record_and_bytes(tmp_path):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))
    packet, _verification, first, first_created = _prepare(store)

    replay_packet, _verification, replay, replay_created = _prepare(
        store,
        prepared_at="2026-09-03T00:01:00+00:00",
    )

    assert first_created is True
    assert replay_created is False
    assert replay == first
    assert replay.prepared_at == "2026-09-03T00:00:00+00:00"
    assert replay_packet["content"] == packet["content"]


def test_store_rejects_reviewer_drift_without_rewriting_record(tmp_path):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))
    _packet_value, verification, first, _created = _prepare(store)
    original = store._backend.read_text(
        store.record_path(
            tenant_id="tenant-a",
            project_id="project-a",
            project_document_id="document-a",
            packet_sha256=verification["packet_sha256"],
        )
    )

    with pytest.raises(ValueError, match="identity drift"):
        _prepare(
            store,
            reviewer_assignment={
                "user_id": "user-other",
                "username": "other",
                "role": "member",
            },
        )

    assert store.get(
        tenant_id="tenant-a",
        project_id="project-a",
        project_document_id="document-a",
        packet_sha256=verification["packet_sha256"],
    ) == first
    assert store._backend.read_text(
        store.record_path(
            tenant_id="tenant-a",
            project_id="project-a",
            project_document_id="document-a",
            packet_sha256=verification["packet_sha256"],
        )
    ) == original


def test_store_rejects_corrupt_packet_and_duplicate_record_key(tmp_path):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))
    _packet_value, verification, record, _created = _prepare(store)
    packet_path = store.packet_path(
        tenant_id="tenant-a", packet_sha256=verification["packet_sha256"]
    )
    store._backend.write_bytes(packet_path, b"corrupt")
    with pytest.raises(GeneratedDocumentReviewStoreError):
        store.read_packet(record, tenant_id="tenant-a")

    record_path = store.record_path(
        tenant_id="tenant-a",
        project_id="project-a",
        project_document_id="document-a",
        packet_sha256=verification["packet_sha256"],
    )
    raw = store._backend.read_text(record_path)
    assert raw is not None
    duplicate = raw.replace(
        '"schema_version":',
        '"schema_version": "decisiondoc.generated_document_review_handoff.v1", "schema_version":',
        1,
    )
    store._backend.write_text(record_path, duplicate)
    with pytest.raises(GeneratedDocumentReviewStoreError):
        store.get(
            tenant_id="tenant-a",
            project_id="project-a",
            project_document_id="document-a",
            packet_sha256=verification["packet_sha256"],
        )


def test_store_preserves_orphan_packet_when_record_write_fails(tmp_path, monkeypatch):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))
    packet, verification = _packet()
    original_write_text_if_absent = store._backend.write_text_if_absent

    def fail_record(relative_path: str, text: str, **kwargs):
        if relative_path.endswith("record.json"):
            raise StateBackendError("record unavailable")
        return original_write_text_if_absent(relative_path, text, **kwargs)

    monkeypatch.setattr(store._backend, "write_text_if_absent", fail_record)

    with pytest.raises(GeneratedDocumentReviewStoreError):
        store.prepare(
            tenant_id="tenant-a",
            project_id="project-a",
            project_document_id="document-a",
            packet_content=packet["content"],
            packet_verification=verification,
            prepared_at="2026-09-03T00:00:00+00:00",
            creator_assignment=CREATOR,
            reviewer_assignment=REVIEWER,
        )

    packet_path = store.packet_path(
        tenant_id="tenant-a", packet_sha256=verification["packet_sha256"]
    )
    assert store._backend.read_bytes(packet_path) == packet["content"]
    assert store.list_by_tenant(tenant_id="tenant-a") == []

    monkeypatch.setattr(
        store._backend, "write_text_if_absent", original_write_text_if_absent
    )
    record, created = store.prepare(
        tenant_id="tenant-a",
        project_id="project-a",
        project_document_id="document-a",
        packet_content=packet["content"],
        packet_verification=verification,
        prepared_at="2026-09-03T00:02:00+00:00",
        creator_assignment=CREATOR,
        reviewer_assignment=REVIEWER,
    )
    assert created is True
    assert record.prepared_at == "2026-09-03T00:02:00+00:00"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("tenant_id", "../tenant"),
        ("project_id", "project/other"),
        ("project_document_id", ".."),
        ("packet_sha256", "A" * 64),
    ),
)
def test_store_rejects_unsafe_path_segments_before_backend_access(
    tmp_path, monkeypatch, field, value
):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))
    called = False

    def observe_read(_relative_path):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(store._backend, "read_text", observe_read)
    arguments = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "project_document_id": "document-a",
        "packet_sha256": "a" * 64,
    }
    arguments[field] = value

    with pytest.raises(ValueError):
        store.get(**arguments)

    assert called is False


def test_store_lists_only_canonical_owned_records_newest_first(tmp_path):
    store = GeneratedDocumentReviewStore(base_dir=str(tmp_path))
    _packet_value, verification, record, _created = _prepare(store)
    prefix = "tenants/tenant-a/generated_document_reviews/projects"
    store._backend.write_text(
        f"{prefix}/project-a/document-a/nested/{verification['packet_sha256']}/record.json",
        json.dumps({"forged": True}),
    )

    assert store.list_by_tenant(tenant_id="tenant-a") == [record]
    assert store.list_by_project(
        tenant_id="tenant-a", project_id="project-a"
    ) == [record]
    assert store.list_by_project(
        tenant_id="tenant-b", project_id="project-a"
    ) == []

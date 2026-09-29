from __future__ import annotations

import asyncio
import hashlib
import io
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest

from app.schemas.edited_project_copies import SaveEditedCopyRequest
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    procurement_requirement_node_ids,
)
from app.services.edited_project_copy_service import save_edited_copy
from app.services.generated_document_review_service import document_source_sha256
from app.services.generation_export_packet import (
    MANIFEST_PATH,
    PACKET_SCHEMA,
    PACKET_SCHEMA_V2,
    PERSISTED_PACKET_SCHEMA_V2,
    GenerationExportPacketError,
    build_generated_document_review_packet,
    build_generation_export_packet,
    verify_generation_export_packet,
)
from app.services.procurement_document_binding import (
    binding_sha256,
    describe_procurement_document_binding,
    source_binding_from_documents,
)
from app.storage.edited_project_copy_records import source_hash
from app.storage.generation_export_source_store import (
    GenerationExportSourceStore,
    GenerationExportSourceUnavailableError,
)
from app.storage.generated_document_review_models import (
    verify_generated_document_reviewed_package,
)
from app.storage.generated_document_review_store import GeneratedDocumentReviewStore
from app.storage.project_store import (
    Project,
    ProjectDocument,
    ProjectStore,
    ProjectStoreError,
)
from app.storage.state_backend import LocalStateBackend
from tests.test_project_approval_store_integrity import _s3_backend


def _binding(
    *,
    tenant_id: str = "alpha",
    project_id: str = "project-a",
    decision_id: str = "decision-a",
    revision: int = 3,
) -> dict:
    return {
        "schema_version": "procurement.source_binding.v1",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "decision_id": decision_id,
        "decision_revision": revision,
        "source_kind": "g2b",
        "source_id": "notice-a",
        "source_updated_at": "2026-09-21T00:00:00+00:00",
        "record_sha256": "a" * 64,
        "snapshots": [
            {"snapshot_id": "snapshot-a", "sha256": "b" * 64, "size_bytes": 17}
        ],
    }


def _docs(binding: dict | None = None, *, markdown: str = "# Bound") -> list[dict]:
    doc = {"doc_type": "adr", "markdown": markdown}
    if binding is not None:
        doc["source_procurement_binding"] = binding
    return [doc]


class _Resolver:
    def __init__(self, status: str = "current", reason_code: str = "") -> None:
        self.status = status
        self.reason_code = reason_code
        self.binding = None

    def describe_binding(self, binding):
        self.binding = binding.model_dump(mode="json")
        return {"status": self.status, "reason_code": self.reason_code}

    def capture(
        self,
        project_id,
        *,
        tenant_id,
        decision_id,
        expected_revision,
    ):
        assert expected_revision is None
        assert self.binding is not None
        return SimpleNamespace(
            binding=self.binding,
            record=SimpleNamespace(
                tenant_id=tenant_id,
                project_id=project_id,
                decision_id=decision_id,
                updated_at=self.binding["source_updated_at"],
            ),
        )


def _project_document(*, binding: dict | None = None) -> ProjectDocument:
    return ProjectDocument(
        doc_id="document-a",
        request_id="request-a",
        bundle_id="proposal_kr",
        title="Proposal",
        generated_at="2026-09-21T00:00:00+00:00",
        approval_id=None,
        approval_status=None,
        tags=[],
        doc_snapshot=json.dumps(_docs(binding), ensure_ascii=False),
        gov_options=None,
        file_size_chars=7,
        source_procurement_binding=binding,
    )


def test_strict_binding_helpers_reject_partial_docs_and_fail_closed_freshness():
    binding = _binding()
    assert source_binding_from_documents(
        _docs(binding), tenant_id="alpha", project_id="project-a"
    ) == binding
    assert source_binding_from_documents(
        [{"doc_type": "adr", "markdown": "legacy", "source_procurement_binding": None}],
        tenant_id="alpha",
    ) is None
    assert describe_procurement_document_binding(binding, resolver=None) == {
        "status": "unknown",
        "reason_code": "resolver_unavailable",
    }
    assert describe_procurement_document_binding(
        binding, resolver=_Resolver("stale", "source_changed")
    ) == {"status": "stale", "reason_code": "source_changed"}
    assert binding_sha256(binding) == hashlib.sha256(
        json.dumps(binding, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()

    with pytest.raises(ValueError):
        source_binding_from_documents(
            [*_docs(binding), {"doc_type": "onepager", "markdown": "# Missing"}],
            tenant_id="alpha",
            project_id="project-a",
        )
    with pytest.raises(ValueError):
        source_binding_from_documents(
            _docs(_binding(tenant_id="foreign")), tenant_id="alpha"
        )

    class _RacingResolver:
        def describe_binding(self, binding):
            return {"status": "current", "reason_code": "matches"}

        def capture(self, *args, **kwargs):
            raise RuntimeError("source changed after describe")

    from app.services.procurement_document_binding import (
        resolve_procurement_document_binding,
    )

    raced = resolve_procurement_document_binding(
        binding,
        resolver=_RacingResolver(),
    )
    assert raced.status == "unknown"
    assert raced.reason_code == "resolver_capture_failed"
    assert raced.record is None


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_project_and_export_source_round_trip_binding_without_client_inference(
    tmp_path: Path, backend_kind: str
):
    backend = (
        LocalStateBackend(tmp_path / "state")
        if backend_kind == "local"
        else _s3_backend()[0]
    )
    store = ProjectStore(str(tmp_path), backend=backend)
    project = store.create(tenant_id="alpha", name="Bound")
    binding = _binding(project_id=project.project_id)

    with pytest.raises(ValueError):
        store.add_document(
            project.project_id,
            "forged",
            "proposal_kr",
            "Forged",
            _docs(binding),
            tenant_id="alpha",
        )

    document = store.add_document(
        project.project_id,
        "request-a",
        "proposal_kr",
        "Bound",
        _docs(binding),
        tenant_id="alpha",
        source_procurement_binding=binding,
    )
    restored = ProjectStore(str(tmp_path), backend=backend).get(
        project.project_id, tenant_id="alpha"
    )
    assert restored is not None
    assert restored.documents[0].source_procurement_binding == binding
    assert asdict(restored.documents[0]) == asdict(document)

    export_store = GenerationExportSourceStore(backend=backend)
    export_store.store(
        tenant_id="alpha",
        request_id=f"export-{backend_kind}",
        docs=_docs(binding),
        title="Bound export",
    )
    assert export_store.get(
        tenant_id="alpha", request_id=f"export-{backend_kind}"
    ) == (_docs(binding), "Bound export")
    with pytest.raises(GenerationExportSourceUnavailableError):
        export_store.store(
            tenant_id="foreign",
            request_id="foreign-binding",
            docs=_docs(binding),
            title="Foreign",
        )


def test_edited_copy_inherits_only_binding_and_hashes_it(tmp_path: Path):
    store = ProjectStore(str(tmp_path))
    project = store.create(tenant_id="alpha", name="Edited")
    binding = _binding(project_id=project.project_id)
    parent = store.add_document(
        project.project_id,
        "request-a",
        "proposal_kr",
        "Original",
        _docs(binding),
        tenant_id="alpha",
        approval_id="approval-a",
        source_decision_council_session_id="council-a",
        source_procurement_review_packet_sha256="c" * 64,
        source_procurement_binding=binding,
    )
    payload = SaveEditedCopyRequest(
        operation_id=str(uuid4()),
        parent_sha256=source_hash(parent),
        title="Edited",
        docs=[{"doc_type": "adr", "markdown": "# Edited exact snapshot"}],
    )
    edited = save_edited_copy(
        store,
        tenant_id="alpha",
        actor_id="actor-a",
        project_id=project.project_id,
        parent_id=parent.doc_id,
        payload=payload,
    )
    assert edited.source_procurement_binding == binding
    assert edited.approval_id is None and edited.approval_status is None
    assert edited.source_decision_council_session_id is None
    assert edited.source_procurement_review_packet_sha256 is None
    assert edited.request_id == ""

    legacy = _project_document(binding=None)
    assert source_hash(legacy) == "d139fdba29ed413824298b3eb0d4fb94d4e5980c98e75b04768a20764bc177f5"
    assert source_hash(_project_document(binding=binding)) != source_hash(legacy)


def test_generation_packet_v1_bytes_stay_fixed_and_bound_v2_is_portable(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_export_packet.build_docx",
        lambda docs, title: b"docx-fixed",
    )
    legacy = asyncio.run(
        build_generation_export_packet(
            docs=_docs(None, markdown="# x"),
            title="Title",
            tenant_id="tenant-a",
            request_id="request-a",
            formats="docx",
        )
    )
    assert legacy["manifest"]["schema"] == PACKET_SCHEMA
    assert hashlib.sha256(legacy["content"]).hexdigest() == (
        "46032f5914691a9f0d77755373b51542b98acf22c8ba28ec823ca8074e2ff8cb"
    )

    binding = _binding()
    bound = asyncio.run(
        build_generation_export_packet(
            docs=_docs(binding),
            title="Bound",
            tenant_id="alpha",
            request_id="bound-request",
            formats="docx",
        )
    )
    verified = verify_generation_export_packet(bound["content"])
    assert verified["schema"] == PACKET_SCHEMA_V2
    assert verified["source_procurement_binding"] == binding

    entries = {}
    with zipfile.ZipFile(io.BytesIO(bound["content"])) as archive:
        names = archive.namelist()
        entries = {name: archive.read(name) for name in names}
    manifest = json.loads(entries[MANIFEST_PATH])
    manifest["source_procurement_binding"]["tenant_id"] = "foreign"
    entries[MANIFEST_PATH] = (
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            from app.services.generation_export_packet import _write_zip_entry

            _write_zip_entry(archive, name, entries[name])
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(output.getvalue())


def test_bound_packet_schemas_reject_explicit_null_binding(monkeypatch):
    from app.services.generation_export_packet import _write_zip_entry

    monkeypatch.setattr(
        "app.services.generation_export_packet.build_docx",
        lambda docs, title: b"bound-docx",
    )
    binding = _binding()
    document = _project_document(binding=binding)
    docs = json.loads(document.doc_snapshot)
    packets = [
        asyncio.run(
            build_generation_export_packet(
                docs=docs,
                title="Bound",
                tenant_id="alpha",
                request_id="request-a",
                formats="docx",
            )
        ),
        asyncio.run(
            build_generated_document_review_packet(
                docs=docs,
                title=document.title,
                tenant_id="alpha",
                project_id="project-a",
                project_document_id=document.doc_id,
                request_id=document.request_id,
                bundle_id=document.bundle_id,
                document_source_sha256=document_source_sha256(
                    tenant_id="alpha",
                    project_id="project-a",
                    document=document,
                    docs=docs,
                ),
                formats="docx",
                source_procurement_binding=binding,
            )
        ),
    ]
    assert [packet["manifest"]["schema"] for packet in packets] == [
        PACKET_SCHEMA_V2,
        PERSISTED_PACKET_SCHEMA_V2,
    ]

    for packet in packets:
        with zipfile.ZipFile(io.BytesIO(packet["content"])) as archive:
            names = archive.namelist()
            entries = {name: archive.read(name) for name in names}
        manifest = json.loads(entries[MANIFEST_PATH])
        manifest["source_procurement_binding"] = None
        entries[MANIFEST_PATH] = (
            json.dumps(
                manifest,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode()
        output = io.BytesIO()
        with zipfile.ZipFile(
            output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for name in names:
                _write_zip_entry(archive, name, entries[name])
        with pytest.raises(GenerationExportPacketError):
            verify_generation_export_packet(output.getvalue())


def test_persisted_review_packet_and_document_hash_include_optional_binding(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_export_packet.build_docx",
        lambda docs, title: b"review-docx",
    )
    binding = _binding()
    document = _project_document(binding=binding)
    docs = json.loads(document.doc_snapshot)
    bound_hash = document_source_sha256(
        tenant_id="alpha", project_id="project-a", document=document, docs=docs
    )
    legacy = _project_document(binding=None)
    legacy_docs = json.loads(legacy.doc_snapshot)
    assert document_source_sha256(
        tenant_id="alpha", project_id="project-a", document=legacy, docs=legacy_docs
    ) == "e16e0d4e9eb0416639d376abf527586c67f994e5f5395b04fd3f36fc74fe3b67"
    assert bound_hash != document_source_sha256(
        tenant_id="alpha", project_id="project-a", document=legacy, docs=legacy_docs
    )

    packet = asyncio.run(
        build_generated_document_review_packet(
            docs=docs,
            title=document.title,
            tenant_id="alpha",
            project_id="project-a",
            project_document_id=document.doc_id,
            request_id=document.request_id,
            bundle_id=document.bundle_id,
            document_source_sha256=bound_hash,
            formats="docx",
            source_procurement_binding=binding,
        )
    )
    verified = verify_generation_export_packet(packet["content"])
    assert verified["schema"] == PERSISTED_PACKET_SCHEMA_V2
    assert verified["source_procurement_binding"] == binding


def test_bound_review_store_and_completed_package_preserve_portable_binding(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        "app.services.generation_export_packet.build_docx",
        lambda docs, title: b"review-docx",
    )
    binding = _binding()
    document = _project_document(binding=binding)
    docs = json.loads(document.doc_snapshot)
    packet = asyncio.run(
        build_generated_document_review_packet(
            docs=docs,
            title=document.title,
            tenant_id="alpha",
            project_id="project-a",
            project_document_id=document.doc_id,
            request_id=document.request_id,
            bundle_id=document.bundle_id,
            document_source_sha256=document_source_sha256(
                tenant_id="alpha",
                project_id="project-a",
                document=document,
                docs=docs,
            ),
            formats="docx",
            source_procurement_binding=binding,
        )
    )
    backend = LocalStateBackend(tmp_path / "state")
    store = GeneratedDocumentReviewStore(str(tmp_path), backend=backend)
    assignment = {"user_id": "reviewer-a", "username": "reviewer", "role": "member"}
    record, created = store.prepare(
        tenant_id="alpha",
        project_id="project-a",
        project_document_id=document.doc_id,
        packet_content=packet["content"],
        packet_verification=verify_generation_export_packet(packet["content"]),
        prepared_at="2026-09-21T01:00:00+00:00",
        creator_assignment=assignment,
        reviewer_assignment=assignment,
    )
    assert created is True
    completed, package, completed_now = store.complete(
        record,
        tenant_id="alpha",
        completion_assignment=assignment,
        operation_id=str(uuid4()),
        decision="accepted",
        rationale="Reviewed as a historical document only.",
        reviewed_at="2026-09-21T02:00:00+00:00",
    )
    assert completed_now is True
    evidence = verify_generated_document_reviewed_package(
        package,
        expected_record=completed,
        expected_packet_content=packet["content"],
    )
    assert evidence["packet"]["source_procurement_binding"] == binding
    assert evidence["receipt"]["document"]["source_procurement_binding"] == binding
    assert evidence["receipt"]["operational_approval"] is False


def test_project_serialization_and_fingerprint_use_document_binding_not_project_selection():
    from app.routers.projects._provenance import project_document_source_fingerprint
    from app.routers.projects._shared import _serialize_project_documents

    binding = _binding()
    document = _project_document(binding=binding)
    project = Project(
        project_id="project-a",
        tenant_id="alpha",
        name="Project",
        description="",
        client="",
        contract_number="",
        fiscal_year=2026,
        status="active",
        created_at="2026-09-21T00:00:00+00:00",
        updated_at="2026-09-21T00:00:00+00:00",
        documents=[document],
        tags=[],
    )
    resolver = _Resolver("current", "")
    service = SimpleNamespace(procurement_generation_resolver=resolver)
    state = SimpleNamespace(
        procurement_copilot_enabled=False,
        service=service,
        procurement_store=SimpleNamespace(get=lambda *args, **kwargs: {"decision_id": "decision-b"}),
        decision_council_service=None,
        procurement_review_store=None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    serialized = _serialize_project_documents(
        request, tenant_id="alpha", project=project
    )
    assert serialized[0]["source_procurement_binding_status"] == "current"
    assert serialized[0]["source_procurement_binding_reason_code"] == ""

    first = project_document_source_fingerprint(
        request,
        tenant_id="alpha",
        project_id="project-a",
        binding_status="current",
        document=serialized[0],
    )
    state.procurement_store = SimpleNamespace(
        get=lambda *args, **kwargs: {"decision_id": "decision-c", "updated_at": "later"}
    )
    second = project_document_source_fingerprint(
        request,
        tenant_id="alpha",
        project_id="project-a",
        binding_status="current",
        document=serialized[0],
    )
    assert first == second

    legacy = _project_document(binding=None)
    legacy_project = Project(
        **{
            **asdict(project),
            "documents": [legacy],
        }
    )
    state.procurement_store = SimpleNamespace(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unbound document must not use selected procurement")
        )
    )
    legacy_serialized = _serialize_project_documents(
        request, tenant_id="alpha", project=legacy_project
    )
    assert legacy_serialized[0]["source_procurement_binding_status"] == "unknown"
    project_document_source_fingerprint(
        request,
        tenant_id="alpha",
        project_id="project-a",
        binding_status="current",
        document=legacy_serialized[0],
    )


def test_bound_council_and_review_cannot_be_current_after_binding_change():
    from app.routers.projects._shared import _serialize_project_documents
    from app.schemas.procurement_binding import ProcurementSourceBinding

    stored_binding = _binding()
    current_binding = {
        **stored_binding,
        "record_sha256": "c" * 64,
        "snapshots": [
            {
                **stored_binding["snapshots"][0],
                "sha256": "d" * 64,
            }
        ],
    }

    class _ChangedResolver:
        def describe_binding(self, binding):
            return {"status": "stale", "reason_code": "source_changed"}

        def capture(self, project_id, *, tenant_id, decision_id, expected_revision):
            assert expected_revision is None
            return SimpleNamespace(
                binding=ProcurementSourceBinding.model_validate(current_binding),
                record=SimpleNamespace(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    decision_id=decision_id,
                    updated_at=stored_binding["source_updated_at"],
                ),
            )

    class _Session(SimpleNamespace):
        def model_copy(self, *, update):
            return _Session(**{**self.__dict__, **update})

    attached_bindings = []
    session = _Session(
        session_id="council-a",
        session_revision=1,
        source_binding=ProcurementSourceBinding.model_validate(current_binding),
        current_procurement_binding_status="current",
    )

    class _CouncilService:
        def get_latest_procurement_council(self, **kwargs):
            assert kwargs["decision_id"] == stored_binding["decision_id"]
            return session

        def attach_procurement_binding(
            self,
            *,
            session,
            procurement_record,
            source_binding,
        ):
            attached_bindings.append(source_binding.model_dump(mode="json"))
            return session

    packet_sha256 = "e" * 64
    review_record = SimpleNamespace(
        packet_sha256=packet_sha256,
        review_status="completed",
        decision="accepted",
        operational_approval=False,
    )

    class _ReviewStore:
        def get(self, **kwargs):
            return review_record

        def read_packet(self, *args, **kwargs):
            return b"packet"

        def read_reviewed_package(self, *args, **kwargs):
            return b"reviewed"

    base_document = _project_document(binding=stored_binding)
    document = ProjectDocument(
        **{
            **asdict(base_document),
            "source_decision_council_session_id": "council-a",
            "source_decision_council_session_revision": 1,
            "source_procurement_review_packet_sha256": packet_sha256,
            "source_procurement_review_source_updated_at": stored_binding[
                "source_updated_at"
            ],
            "source_procurement_review_decision": "accepted",
        }
    )
    project = Project(
        project_id="project-a",
        tenant_id="alpha",
        name="Project",
        description="",
        client="",
        contract_number="",
        fiscal_year=2026,
        status="active",
        created_at="2026-09-21T00:00:00+00:00",
        updated_at="2026-09-21T00:00:00+00:00",
        documents=[document],
        tags=[],
    )
    state = SimpleNamespace(
        procurement_copilot_enabled=True,
        service=SimpleNamespace(procurement_generation_resolver=_ChangedResolver()),
        procurement_store=SimpleNamespace(
            get=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("bound document must not use selected procurement")
            )
        ),
        decision_council_service=_CouncilService(),
        procurement_review_store=_ReviewStore(),
    )
    serialized = _serialize_project_documents(
        SimpleNamespace(app=SimpleNamespace(state=state)),
        tenant_id="alpha",
        project=project,
    )[0]
    assert attached_bindings == [current_binding]
    assert serialized["source_procurement_binding_status"] == "stale"
    assert serialized["decision_council_document_status"] == "stale_procurement"
    assert serialized["procurement_review_document_status"] == (
        "stale_procurement_review"
    )


@pytest.mark.parametrize("backend_kind", ["local", "fake-s3"])
def test_v2_backend_bound_project_share_and_evidence_reads_are_decision_exact(
    tmp_path: Path,
    monkeypatch,
    backend_kind: str,
):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
    )
    from app.services.generation.procurement_source import (
        ProcurementGenerationResolver,
    )
    from app.storage.procurement_project_store import ProcurementProjectStore
    from app.storage.procurement_store import ProcurementDecisionStore

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    app = create_app()
    backend = (
        app.state.state_backend
        if backend_kind == "local"
        else _s3_backend()[0]
    )
    legacy_store = ProcurementDecisionStore(backend=backend)
    v2_store = ProcurementProjectStore(backend=backend)
    resolver = ProcurementGenerationResolver(store=v2_store, backend=backend)
    app.state.state_backend = backend
    app.state.procurement_store = legacy_store
    app.state.service.procurement_generation_resolver = resolver

    project = app.state.project_store.create(
        tenant_id="system",
        name="Decision exact downstream",
    )

    def import_opportunity(label: str, selection_revision: int):
        snapshot = legacy_store.save_source_snapshot(
            tenant_id="system",
            project_id=project.project_id,
            source_kind="local_fixture",
            payload={"structured_context": f"Source {label}"},
        )
        return v2_store.import_opportunity(
            ProcurementDecisionUpsert(
                tenant_id="system",
                project_id=project.project_id,
                source_snapshots=[snapshot],
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=label,
                    title=f"Opportunity {label}",
                ),
            ),
            expected_selection_revision=selection_revision,
            expected_decision_revision=0,
            operation_id=str(uuid4()),
        )

    source_a = import_opportunity("A", 0)
    source_b = import_opportunity("B", 1)
    captured_a = resolver.capture(
        project.project_id,
        tenant_id="system",
        decision_id=source_a.decision_id,
        expected_revision=source_a.decision_revision,
    )
    binding_a = captured_a.binding.model_dump(mode="json")
    document = app.state.project_store.add_document(
        project.project_id,
        "request-a",
        "proposal_kr",
        "Bound A",
        _docs(binding_a, markdown="# Exact A snapshot"),
        tenant_id="system",
        source_procurement_binding=binding_a,
    )
    assert (
        v2_store.get(project.project_id, tenant_id="system").active_decision_id
        == source_b.decision_id
    )
    approval = app.state.approval_store.create(
        tenant_id="system", request_id="request-a", bundle_id="proposal_kr",
        title="A approval", drafter="admin", docs=[],
        project_id=project.project_id, project_document_id=document.doc_id,
    )
    workflow = app.state.report_workflow_store.create(
        tenant_id="system", title="A workflow", source_bundle_id="proposal_kr",
    )
    workflow.project_id = project.project_id
    workflow.project_document_id = document.doc_id
    monkeypatch.setattr(app.state.report_workflow_store, "list_by_tenant", lambda tenant_id: [workflow])

    with TestClient(app, raise_server_exceptions=False) as client:
        registered = client.post(
            "/auth/register",
            json={
                "username": f"binding-admin-{backend_kind}",
                "display_name": "Binding Admin",
                "email": f"binding-{backend_kind}@example.com",
                "password": "Password123!",
                "role": "admin",
            },
        )
        assert registered.status_code == 200, registered.text
        logged_in = client.post(
            "/auth/login",
            json={
                "username": f"binding-admin-{backend_kind}",
                "password": "Password123!",
            },
        )
        assert logged_in.status_code == 200, logged_in.text
        auth = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

        project_response = client.get(
            f"/projects/{project.project_id}",
            headers={"X-DecisionDoc-Api-Key": "test-key"},
        )
        assert project_response.status_code == 200, project_response.text
        serialized_document = project_response.json()["documents"][0]
        assert serialized_document["source_procurement_binding"] == binding_a
        assert serialized_document["source_procurement_binding_status"] == "current"

        shared = client.post(
            "/share",
            json={
                "request_id": document.request_id,
                "title": document.title,
                "bundle_id": document.bundle_id,
                "project_id": project.project_id,
                "project_document_id": document.doc_id,
            },
            headers=auth,
        )
        assert shared.status_code == 200, shared.text
        assert shared.json()["source_procurement_binding_status"] == "current"
        public = client.get(f"/shared/{shared.json()['share_id']}")
        assert public.status_code == 200, public.text
        assert "Exact A snapshot" in public.text
        assert binding_a["decision_id"] not in public.text
        assert binding_a["record_sha256"] not in public.text

        evidence = client.get(
            f"/projects/{project.project_id}/decision-evidence-map",
            headers=auth,
        )
        assert evidence.status_code == 200, evidence.text
        assert all(node["node_type"] not in {"approval", "export"} for node in evidence.json()["nodes"])
        assert any(
            item["code"] == "document_procurement_binding_unknown"
            for item in evidence.json()["diagnostics"]
        ) is False
        assert any(
            item["code"] == "document_procurement_binding_stale"
            for item in evidence.json()["diagnostics"]
        ) is False

        handoff = client.get(
            f"/projects/{project.project_id}/guided-decision-review-handoff?bundle_type=proposal_kr",
            headers=auth,
        )
        assert handoff.status_code == 200, handoff.text
        document_stage = next(stage for stage in handoff.json()["stages"] if stage["name"] == "Documents")
        assert document_stage["status"] == "not_observed"

        v2_store.select(
            project.project_id, tenant_id="system", decision_id=source_a.decision_id,
            expected_selection_revision=2, operation_id=str(uuid4()),
        )
        a_evidence = client.get(f"/projects/{project.project_id}/decision-evidence-map", headers=auth)
        assert a_evidence.status_code == 200, a_evidence.text
        assert any(node["node_id"] == f"approval:{approval.approval_id}" for node in a_evidence.json()["nodes"])
        assert any(node["node_type"] == "export" for node in a_evidence.json()["nodes"])

        source_path = captured_a.record.source_snapshots[-1].storage_path
        backend.write_text(source_path, '{"changed":true}')
        stale = client.get(
            f"/projects/{project.project_id}",
            headers={"X-DecisionDoc-Api-Key": "test-key"},
        )
        assert stale.status_code == 200, stale.text
        stale_document = stale.json()["documents"][0]
        assert stale_document["source_procurement_binding"] == binding_a
        assert stale_document["source_procurement_binding_status"] == "stale"
        stale_public = client.get(f"/shared/{shared.json()['share_id']}")
        assert stale_public.status_code == 200, stale_public.text
        assert "공고 출처 변경 확인 필요" in stale_public.text
        assert binding_a["decision_id"] not in stale_public.text


def test_stale_or_different_procurement_binding_does_not_mark_evidence_current():
    binding = _binding(decision_id="decision-a")
    procurement = {
        "decision_id": "decision-b",
        "project_id": "project-a",
        "updated_at": "2026-09-21T00:00:00+00:00",
        "opportunity": {"title": "B", "issuer": "Agency"},
        "hard_filters": [],
        "checklist_items": [
            {
                "category": "security",
                "title": "Security",
                "status": "action_needed",
                "evidence": "",
                "remediation_note": "",
            }
        ],
        "missing_data": [],
        "recommendation": {"value": "GO", "summary": "Proceed"},
        "source_snapshots": [],
    }
    requirement_id = procurement_requirement_node_ids(procurement)[0]
    document = {
        **asdict(_project_document(binding=binding)),
        "source_procurement_binding_status": "stale",
        "source_procurement_binding_reason_code": "source_changed",
        "source_evidence_refs": [requirement_id],
    }
    result = DecisionEvidenceService().build(
        project_id="project-a",
        bundle_type="proposal_kr",
        procurement_record=procurement,
        project_documents=[document],
        generated_at="2026-09-21T12:00:00+00:00",
    )
    assert result.coverage.explicit == 0
    assert any(item.code == "document_procurement_binding_stale" for item in result.diagnostics)
    assert any(
        revision.source_kind == "procurement_source_binding"
        and revision.source_id == "decision-a"
        and revision.content_sha256 == binding_sha256(binding)
        for revision in result.source_revisions
    )


def test_share_store_accepts_empty_request_only_for_explicit_document_binding(tmp_path: Path):
    from app.storage.share_store import ShareStore

    store = ShareStore("alpha", data_dir=tmp_path)
    with pytest.raises(ValueError):
        store.create(request_id="", title="No source", created_by="actor")
    link = store.create(
        request_id="",
        title="Edited",
        created_by="actor",
        bundle_id="proposal_kr",
        project_id="project-a",
        project_document_id="document-a",
        source_procurement_binding=_binding(),
        source_procurement_binding_status="current",
        source_procurement_binding_reason_code="",
    )
    restored = store.get(link.share_id)
    assert restored is not None
    assert restored["source_procurement_binding"] == _binding()
    assert restored["source_procurement_binding_status"] == "current"


def test_public_share_renders_edited_document_snapshot_without_binding_details(tmp_path: Path):
    from app.routers.history import view_shared_document
    from app.storage.share_store import ShareStore

    backend = LocalStateBackend(tmp_path / "state")
    project_store = ProjectStore(str(tmp_path), backend=backend)
    project = project_store.create(tenant_id="alpha", name="Share")
    binding = _binding(project_id=project.project_id)
    parent = project_store.add_document(
        project.project_id,
        "request-a",
        "proposal_kr",
        "Original",
        _docs(binding, markdown="# Original marker"),
        tenant_id="alpha",
        source_procurement_binding=binding,
    )
    edited = save_edited_copy(
        project_store,
        tenant_id="alpha",
        actor_id="actor-a",
        project_id=project.project_id,
        parent_id=parent.doc_id,
        payload=SaveEditedCopyRequest(
            operation_id=str(uuid4()),
            parent_sha256=source_hash(parent),
            title="Edited",
            docs=[{"doc_type": "adr", "markdown": "# Exact edited marker"}],
        ),
    )
    share_store = ShareStore("alpha", data_dir=tmp_path, backend=backend)
    share = share_store.create(
        request_id="",
        title=edited.title,
        created_by="actor-a",
        bundle_id=edited.bundle_id,
        project_id=project.project_id,
        project_document_id=edited.doc_id,
        source_procurement_binding=binding,
        source_procurement_binding_status="current",
        source_procurement_binding_reason_code="procurement_source_matches",
    )
    state = SimpleNamespace(
        data_dir=tmp_path,
        state_backend=backend,
        project_store=project_store,
        procurement_copilot_enabled=False,
        service=SimpleNamespace(procurement_generation_resolver=_Resolver()),
        tenant_store=SimpleNamespace(
            list_tenants=lambda: [SimpleNamespace(tenant_id="alpha")]
        ),
        storage=SimpleNamespace(
            load_bundle=lambda _request_id: (_ for _ in ()).throw(
                AssertionError("document-bound share must not use request fallback")
            )
        ),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=state),
        state=SimpleNamespace(),
    )
    response = view_shared_document(share.share_id, request)
    html = response.body.decode("utf-8")
    assert "Exact edited marker" in html
    assert "Original marker" not in html
    assert binding["decision_id"] not in html
    assert binding["tenant_id"] not in html
    assert binding["record_sha256"] not in html


def test_public_procurement_binding_warning_distinguishes_absent_source():
    from app.routers.history import _render_shared_procurement_binding_warning

    assert (
        _render_shared_procurement_binding_warning(
            {
                "bundle_id": "adr",
                "source_procurement_binding_status": "unknown",
            }
        )
        == ""
    )
    unbound = _render_shared_procurement_binding_warning(
        {
            "bundle_id": "proposal_kr",
            "source_procurement_binding_status": "unknown",
        }
    )
    assert "공고 출처 기록 없음" in unbound
    assert "저장 당시의 공고 출처에 결속" not in unbound

    binding = _binding()
    stale = _render_shared_procurement_binding_warning(
        {
            "bundle_id": "proposal_kr",
            "source_procurement_binding": binding,
            "source_procurement_binding_status": "stale",
        }
    )
    assert "공고 출처 변경 확인 필요" in stale
    assert "저장 당시의 공고 출처에 결속" in stale
    assert binding["decision_id"] not in stale
    assert binding["record_sha256"] not in stale


def test_project_binary_download_uses_headers_not_embedded_binding_claims(
    tmp_path: Path, monkeypatch
):
    from app.routers.projects.core import download_project_doc_endpoint

    monkeypatch.setattr(
        "app.routers.projects.core.build_docx",
        lambda docs, title, gov_options: b"raw-docx",
    )
    store = ProjectStore(str(tmp_path))
    project = store.create(tenant_id="alpha", name="Download")
    binding = _binding(project_id=project.project_id)
    document = store.add_document(
        project.project_id,
        "request-a",
        "proposal_kr",
        "Bound",
        _docs(binding),
        tenant_id="alpha",
        source_procurement_binding=binding,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                project_store=store,
                service=SimpleNamespace(
                    procurement_generation_resolver=_Resolver("current", "matches")
                ),
            )
        ),
        state=SimpleNamespace(tenant_id="alpha"),
    )
    response = asyncio.run(
        download_project_doc_endpoint(
            project.project_id, document.doc_id, "docx", request
        )
    )
    assert response.body == b"raw-docx"
    assert response.headers["x-decisiondoc-procurement-source-status"] == "current"
    assert response.headers[
        "x-decisiondoc-procurement-source-binding-sha256"
    ] == binding_sha256(binding)
    assert binding["decision_id"] not in response.headers.values()


def test_corrupt_persisted_project_binding_fails_closed(tmp_path: Path):
    store = ProjectStore(str(tmp_path))
    project = store.create(tenant_id="alpha", name="Corrupt")
    binding = _binding(project_id=project.project_id)
    store.add_document(
        project.project_id,
        "request-a",
        "proposal_kr",
        "Bound",
        _docs(binding),
        tenant_id="alpha",
        source_procurement_binding=binding,
    )
    path = "tenants/alpha/projects.json"
    records = json.loads(store._backend.read_text(path))
    records[0]["documents"][0]["source_procurement_binding"]["tenant_id"] = "foreign"
    store._backend.write_text(path, json.dumps(records))
    with pytest.raises(ProjectStoreError):
        store.get(project.project_id, tenant_id="alpha")

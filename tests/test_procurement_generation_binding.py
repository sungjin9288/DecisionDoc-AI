"""Pinned generation context with no provider/network side effects."""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.mock_provider import MockProvider
from app.schemas import (
    GenerateRequest,
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
)
from app.storage.procurement_project_store import ProcurementProjectStore
from app.storage.procurement_store import ProcurementDecisionStore
from tests.test_procurement_review_store import _MemoryS3Client, _s3_backend

HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


@pytest.fixture(params=["local", "fake-s3"])
def scope(tmp_path, monkeypatch, request):
    from app.services.generation.procurement_source import ProcurementGenerationResolver

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    app = create_app()
    backend = (
        app.state.state_backend
        if request.param == "local"
        else _s3_backend(_MemoryS3Client())
    )
    legacy = ProcurementDecisionStore(backend=backend)
    store = ProcurementProjectStore(backend=backend)
    project = app.state.project_store.create(
        tenant_id="system", name="Pinned generation"
    )
    resolver = ProcurementGenerationResolver(store=store, backend=backend)
    app.state.service.procurement_generation_resolver = resolver
    app.state.service._procurement_store = legacy
    calls = []
    hook = SimpleNamespace(run=lambda: None)

    class ProbeProvider(MockProvider):
        def generate_bundle(
            self, requirements, *, schema_version, request_id, **kwargs
        ):
            calls.append(deepcopy(requirements))
            hook.run()
            return super().generate_bundle(
                requirements,
                schema_version=schema_version,
                request_id=request_id,
                **kwargs,
            )

    app.state.service.provider_factory = lambda: ProbeProvider()
    app.state.service._eval_store = None
    app.state.service._search_service = None
    with TestClient(app) as client:
        yield SimpleNamespace(
            app=app,
            backend=backend,
            legacy=legacy,
            store=store,
            resolver=resolver,
            project=project.project_id,
            client=client,
            calls=calls,
            hook=hook,
        )


def _import(scope, source="A", selection=0, *, notes=""):
    snapshot = scope.legacy.save_source_snapshot(
        tenant_id="system",
        project_id=scope.project,
        source_kind="local_fixture",
        payload={
            "structured_context": f"Only source {source}",
            "announcement": {"raw_text": source},
        },
    )
    return scope.store.import_opportunity(
        ProcurementDecisionUpsert(
            tenant_id="system",
            project_id=scope.project,
            source_snapshots=[snapshot],
            notes=notes,
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b", source_id=source, title=f"Opportunity {source}"
            ),
        ),
        expected_selection_revision=selection,
        expected_decision_revision=0,
        operation_id=str(uuid4()),
    )


def _request(scope, receipt=None):
    data = {
        "title": "Decision",
        "goal": "Evaluate the attached opportunity",
        "project_id": scope.project,
        "bundle_type": "bid_decision_kr",
    }
    if receipt is not None:
        data.update(
            procurement_decision_id=receipt.decision_id,
            expected_procurement_decision_revision=receipt.decision_revision,
        )
    return data


def test_explicit_b_context_survives_selection_of_a(scope):
    a = _import(scope)
    b = _import(scope, "B", 1)
    scope.hook.run = lambda: scope.store.select(
        scope.project,
        tenant_id="system",
        decision_id=a.decision_id,
        expected_selection_revision=2,
        operation_id=str(uuid4()),
    )
    response = scope.client.post("/generate", json=_request(scope, b), headers=HEADERS)
    assert response.status_code == 200, response.text
    binding = response.json()["source_procurement_binding"]
    assert binding["decision_id"] == b.decision_id
    assert "Opportunity B" in scope.calls[0]["_procurement_context"]
    assert "Only source B" in scope.calls[0]["_procurement_context"]
    assert "Opportunity A" not in scope.calls[0]["_procurement_context"]
    assert all(
        doc["source_procurement_binding"] == binding for doc in response.json()["docs"]
    )
    assert (
        scope.store.get(scope.project, tenant_id="system").active_decision_id
        == a.decision_id
    )


def test_multi_without_id_and_foreign_id_fail_before_provider(scope):
    a = _import(scope)
    _import(scope, "B", 1)
    assert (
        scope.client.post(
            "/generate", json=_request(scope), headers=HEADERS
        ).status_code
        == 409
    )
    data = _request(scope, a)
    data["procurement_decision_id"] = str(uuid4())
    assert scope.client.post("/generate", json=data, headers=HEADERS).status_code == 404
    data = _request(scope, a)
    data["expected_procurement_decision_revision"] += 1
    assert scope.client.post("/generate", json=data, headers=HEADERS).status_code == 409
    assert scope.calls == []


def test_source_change_during_provider_rejects_without_export_or_bundle_write(scope):
    a = _import(scope)
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    scope.hook.run = lambda: scope.backend.write_text(
        entry.record.source_snapshots[0].storage_path, '{"changed":true}'
    )
    saved = []
    scope.app.state.service.storage.save_bundle = lambda *args: saved.append(args)
    response = scope.client.post("/generate", json=_request(scope, a), headers=HEADERS)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "procurement_context_changed"
    assert len(scope.calls) == 1
    assert saved == []
    assert (
        scope.app.state.project_store.get(scope.project, tenant_id="system").documents
        == []
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"procurement_decision_id": str(uuid4())},
        {"expected_procurement_decision_revision": 1},
        {
            "procurement_decision_id": "../other",
            "expected_procurement_decision_revision": 1,
        },
        {
            "procurement_decision_id": str(uuid4()),
            "expected_procurement_decision_revision": True,
        },
    ],
)
def test_generation_request_rejects_partial_or_invalid_selection(extra):
    with pytest.raises(ValueError):
        GenerateRequest(title="Test", goal="Test", project_id="project", **extra)


def test_cache_binding_separates_decisions_and_exact_snapshot_changes(
    scope, monkeypatch
):
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    a = _import(scope)
    b = _import(scope, "B", 1)
    results = [
        scope.client.post("/generate", json=_request(scope, item), headers=HEADERS)
        for item in [a, b, a]
    ]
    assert [r.status_code for r in results] == [200, 200, 200]
    assert [r.json()["cache_hit"] for r in results] == [False, False, True]
    assert len(scope.calls) == 2
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    scope.backend.write_text(
        entry.record.source_snapshots[0].storage_path,
        '{"structured_context":"Changed A bytes"}',
    )
    changed = scope.client.post("/generate", json=_request(scope, a), headers=HEADERS)
    assert changed.status_code == 200
    assert changed.json()["cache_hit"] is False
    assert (
        changed.json()["source_procurement_binding"]
        != results[0].json()["source_procurement_binding"]
    )
    assert len(scope.calls) == 3


def test_no_go_override_from_b_does_not_authorize_a(scope):
    from app.schemas import ProcurementRecommendation

    a = _import(scope)
    b = _import(
        scope,
        "B",
        1,
        notes="[override_reason ts=2026-09-21 actor=operator]\nLocal B exception\n[/override_reason]",
    )
    project = scope.store.get(scope.project, tenant_id="system")
    for entry in project.entries:
        entry.record.recommendation = ProcurementRecommendation(
            value="NO_GO", summary="Missing evidence"
        )
        receipt = scope.store.save_evaluation(
            entry.record,
            expected_decision_revision=entry.decision_revision,
            operation_id=str(uuid4()),
        )
        if entry.record.decision_id == a.decision_id:
            a = receipt
        else:
            b = receipt
    request_a, request_b = _request(scope, a), _request(scope, b)
    request_a["bundle_type"] = request_b["bundle_type"] = "proposal_kr"
    denied = scope.client.post("/generate", json=request_a, headers=HEADERS)
    assert denied.status_code == 409
    assert denied.json()["code"] == "procurement_override_reason_required"
    assert scope.calls == []
    allowed = scope.client.post("/generate", json=request_b, headers=HEADERS)
    assert allowed.status_code == 200, allowed.text
    assert len(scope.calls) == 1


def test_single_implicit_source_and_unknown_legacy_freshness(scope):
    a = _import(scope)
    response = scope.client.post("/generate", json=_request(scope), headers=HEADERS)
    assert response.status_code == 200
    binding = response.json()["source_procurement_binding"]
    assert binding["decision_id"] == a.decision_id
    assert scope.resolver.describe_binding(binding)["status"] == "current"
    _import(scope, "B", 1)
    assert scope.resolver.describe_binding(binding)["status"] == "current"
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    entry.record.notes = "Changed decision, same timestamp"
    scope.store.save_evaluation(
        entry.record,
        expected_decision_revision=entry.decision_revision,
        operation_id=str(uuid4()),
    )
    assert scope.resolver.describe_binding(binding)["status"] == "stale"
    assert scope.resolver.describe_binding(None)["status"] == "unknown"


def test_default_factory_does_not_accept_explicit_bound_generation(scope):
    a = _import(scope)
    scope.app.state.service.procurement_generation_resolver = None
    result = scope.client.post("/generate", json=_request(scope, a), headers=HEADERS)
    assert result.status_code == 409
    assert result.json()["code"] == "procurement_generation_binding_unavailable"
    assert scope.calls == []


def test_stream_source_change_reports_specific_error_without_completion(scope):
    a = _import(scope)
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    scope.hook.run = lambda: scope.backend.write_text(
        entry.record.source_snapshots[0].storage_path, '{"changed":true}'
    )
    response = scope.client.post(
        "/generate/stream", json=_request(scope, a), headers=HEADERS
    )
    assert response.status_code == 200  # The SSE response has already started.
    assert "event: complete" not in response.text
    assert "event: error" in response.text
    event = json.loads(response.text.split("data: ")[-1])
    assert event["code"] == "procurement_context_changed"
    assert len(scope.calls) == 1
    assert (
        scope.app.state.project_store.get(scope.project, tenant_id="system").documents
        == []
    )


def test_generation_audit_state_uses_pinned_source_not_current_selection(scope):
    from app.routers.generate._shared import (
        _apply_generate_state,
        _build_generate_log_event,
    )

    a = _import(scope)
    _import(scope, "B", 1)
    result = scope.app.state.service.generate_documents(
        GenerateRequest(**_request(scope, a)), request_id="audit", tenant_id="system"
    )
    request = SimpleNamespace(
        state=SimpleNamespace(), method="POST", url=SimpleNamespace(path="/generate")
    )
    _apply_generate_state(request, result, "v1")
    event = _build_generate_log_event(request, result, "audit", "v1")
    assert request.state.procurement_decision_id == a.decision_id
    assert event["procurement_decision_revision"] == a.decision_revision
    assert "source_procurement_binding" not in event


def test_binding_cannot_cross_tenant_or_project(scope):
    from app.services.generation.procurement_source import ProcurementGenerationError

    a = _import(scope)
    for tenant, project in [
        ("another-tenant", scope.project),
        ("system", "other-project"),
    ]:
        with pytest.raises(ProcurementGenerationError) as error:
            scope.resolver.capture(
                project,
                tenant_id=tenant,
                decision_id=a.decision_id,
                expected_revision=a.decision_revision,
            )
        assert error.value.status_code == 404
    assert scope.calls == []


def test_stream_persists_the_same_binding_in_project_and_export_source(scope):
    a = _import(scope)
    _import(scope, "B", 1)
    response = scope.client.post(
        "/generate/stream", json=_request(scope, a), headers=HEADERS
    )
    assert "event: error" not in response.text, response.text
    event = json.loads(response.text.split("event: complete\ndata: ")[1])
    document = scope.app.state.project_store.get(
        scope.project, tenant_id="system"
    ).documents[0]
    assert document.source_procurement_binding == event["source_procurement_binding"]
    stored, _ = scope.app.state.generation_export_source_store.get(
        tenant_id="system", request_id=event["request_id"]
    )
    assert all(
        doc["source_procurement_binding"] == document.source_procurement_binding
        for doc in stored
    )
    scope.app.state.procurement_store = scope.legacy
    detail = scope.client.get(f"/projects/{scope.project}", headers=HEADERS)
    assert detail.status_code == 200, detail.text
    assert (
        detail.json()["documents"][0]["source_procurement_binding_status"] == "current"
    )
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    scope.backend.write_text(
        entry.record.source_snapshots[0].storage_path, '{"changed_after_save":true}'
    )
    detail = scope.client.get(f"/projects/{scope.project}", headers=HEADERS)
    assert detail.status_code == 200, detail.text
    assert detail.json()["documents"][0]["source_procurement_binding_status"] == "stale"
    assert (
        detail.json()["documents"][0]["source_procurement_binding"]
        == document.source_procurement_binding
    )


def test_bound_binary_download_keeps_fetchable_manifest_source(scope, monkeypatch):
    from app.routers.generate import export
    from app.services.procurement_document_binding import binding_sha256

    monkeypatch.setattr(
        export._facade(), "build_docx", lambda *args, **kwargs: b"fixture-docx"
    )
    monkeypatch.setattr(
        export, "_generate_visual_assets_for_docs", lambda *args, **kwargs: []
    )
    a = _import(scope)
    response = scope.client.post(
        "/generate/docx", json=_request(scope, a), headers=HEADERS
    )
    assert response.status_code == 200
    assert response.headers["X-DecisionDoc-Procurement-Decision-Id"] == a.decision_id
    docs, _ = scope.app.state.generation_export_source_store.get(
        tenant_id="system", request_id=response.headers["X-Request-Id"]
    )
    assert response.headers[
        "X-DecisionDoc-Procurement-Binding-Sha256"
    ] == binding_sha256(docs[0]["source_procurement_binding"])


def test_bound_stream_does_not_claim_completion_when_project_link_fails(
    scope, monkeypatch
):
    a = _import(scope)

    def fail_link(*args, **kwargs):
        raise ValueError("Fixture project unavailable")

    monkeypatch.setattr(scope.app.state.project_store, "add_document", fail_link)
    response = scope.client.post(
        "/generate/stream", json=_request(scope, a), headers=HEADERS
    )
    assert "event: complete" not in response.text
    assert (
        json.loads(response.text.split("data: ")[-1])["code"]
        == "PROJECT_DOCUMENT_UNAVAILABLE"
    )


def test_approval_fingerprint_changes_when_already_stale_source_changes_again(scope):
    from dataclasses import replace
    from app.routers.approvals import _serialize_approval_record

    a = _import(scope)
    response = scope.client.post(
        "/generate/stream", json=_request(scope, a), headers=HEADERS
    )
    assert "event: complete" in response.text
    document = scope.app.state.project_store.get(
        scope.project, tenant_id="system"
    ).documents[0]
    scope.app.state.procurement_store = scope.legacy
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    path = entry.record.source_snapshots[0].storage_path
    scope.backend.write_text(path, '{"structured_context":"Revision Y"}')
    record = scope.app.state.approval_store.create(
        tenant_id="system",
        request_id=document.request_id,
        bundle_id=document.bundle_id,
        title=document.title,
        drafter="Fixture operator",
        docs=json.loads(document.doc_snapshot),
        project_id=scope.project,
        project_document_id=document.doc_id,
    )
    request = SimpleNamespace(app=scope.app, state=SimpleNamespace())
    first = _serialize_approval_record(record, request, tenant_id="system")
    approved = replace(
        record,
        status="approved",
        freshness_acknowledged=True,
        approved_source_fingerprint=first["current_source_fingerprint"],
    )
    assert (
        _serialize_approval_record(approved, request, tenant_id="system")[
            "post_approval_source_changed"
        ]
        is False
    )
    scope.backend.write_text(path, '{"structured_context":"Revision Z"}')
    after = _serialize_approval_record(approved, request, tenant_id="system")
    assert (
        scope.store.get(scope.project, tenant_id="system").entries[0].record.updated_at
        == entry.record.updated_at
    )
    assert after["current_source_fingerprint"] != first["current_source_fingerprint"]
    assert after["post_approval_source_changed"] is True
    assert after["source_change_acknowledgement_required"] is True


def _evaluate(scope, receipt):
    from app.schemas import ProcurementRecommendation
    from app.schemas.procurement import ProcurementScoreStatus
    from app.services.procurement_decision_package.package_builder import (
        _demo_decision_hard_filters,
        _demo_decision_score_breakdown,
        _demo_decision_checklist_items,
    )

    entry = next(
        item
        for item in scope.store.get(scope.project, tenant_id="system").entries
        if item.record.decision_id == receipt.decision_id
    )
    entry.record.recommendation = ProcurementRecommendation(
        value="CONDITIONAL_GO", summary="Fixture only", evidence=["Fixture source fact"]
    )
    entry.record.hard_filters = _demo_decision_hard_filters()
    entry.record.score_breakdown = _demo_decision_score_breakdown()
    entry.record.checklist_items = _demo_decision_checklist_items()
    entry.record.soft_fit_score = 68.0
    entry.record.soft_fit_status = ProcurementScoreStatus.SCORED
    entry.record.missing_data = ["Fixture evidence not supplied"]
    return scope.store.save_evaluation(
        entry.record,
        expected_decision_revision=entry.decision_revision,
        operation_id=str(uuid4()),
    )


def _review(scope, source, *, bound):
    from app.services.procurement_decision_package.review_packet import (
        build_project_procurement_review_packet,
    )
    from app.services.procurement_decision_package.review_receipt import (
        build_pending_procurement_review_receipt,
        record_procurement_review_decision,
    )
    from app.services.procurement_decision_package.reviewed_package import (
        build_procurement_reviewed_package,
    )

    store = scope.app.state.service._procurement_review_store
    packet = build_project_procurement_review_packet(
        source.record,
        reviewer_owner="reviewer",
        source_binding=source.binding if bound else None,
    )
    pending, _ = store.prepare(
        tenant_id="system",
        project_id=scope.project,
        packet_content=packet.content,
        receipt=build_pending_procurement_review_receipt(packet.content),
        prepared_at="2026-09-21T00:00:00Z",
    )
    receipt = record_procurement_review_decision(
        pending.receipt,
        packet.content,
        reviewer="reviewer",
        decision="accepted",
        rationale=f"Only review {source.record.opportunity.source_id}",
        reviewed_at="2026-09-21T00:01:00Z",
    )
    receipt_content = (
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    content, _ = build_procurement_reviewed_package(
        packet.content, receipt, receipt_content=receipt_content
    )
    store.complete(
        tenant_id="system",
        project_id=scope.project,
        packet_sha256=packet.sha256,
        current=pending,
        completed_receipt=receipt,
        reviewed_package_content=content,
    )
    return packet.sha256


@pytest.mark.parametrize("bound", [True, False])
def test_generation_never_injects_another_decision_or_unbound_review_and_council(
    scope, bound
):
    from app.services.decision_council.service import DecisionCouncilService
    from app.storage.decision_council_store import DecisionCouncilStore
    from app.storage.procurement_review_store import ProcurementReviewStore

    a = _evaluate(scope, _import(scope))
    b = _evaluate(scope, _import(scope, "B", 1))
    service = scope.app.state.service
    service._procurement_review_store = ProcurementReviewStore(backend=scope.backend)
    service._decision_council_store = DecisionCouncilStore(backend=scope.backend)
    council = DecisionCouncilService(
        decision_council_store=service._decision_council_store
    )
    evidence = {}
    for item in [a, b]:
        source = scope.resolver.capture(
            scope.project,
            tenant_id="system",
            decision_id=item.decision_id,
            expected_revision=item.decision_revision,
        )
        session = council.run_procurement_council(
            tenant_id="system",
            project_id=scope.project,
            goal="Fixture council",
            procurement_record=source.record,
            source_binding=source.binding if bound else None,
        )
        evidence[item.decision_id] = (
            session.session_id,
            _review(scope, source, bound=bound),
        )
    result = scope.client.post(
        "/generate",
        json={**_request(scope, a), "bundle_type": "proposal_kr"},
        headers=HEADERS,
    )
    assert result.status_code == 200, result.text
    payload = scope.calls[-1]
    if bound:
        assert payload["_decision_council_session_id"] == evidence[a.decision_id][0]
        assert (
            result.json()["procurement_review_packet_sha256"]
            == evidence[a.decision_id][1]
        )
        assert "Only review A" in payload["_procurement_review_context"]
        assert "Only review B" not in payload["_procurement_review_context"]
    else:
        assert "_decision_council_context" not in payload
        assert "_procurement_review_context" not in payload
        assert result.json()["procurement_review_handoff_used"] is False
    entry = scope.store.get(scope.project, tenant_id="system").entries[0]
    scope.backend.write_text(
        entry.record.source_snapshots[0].storage_path, '{"structured_context":"New A"}'
    )
    changed = scope.client.post(
        "/generate",
        json={**_request(scope, a), "bundle_type": "proposal_kr"},
        headers=HEADERS,
    )
    assert changed.status_code == 200
    assert "_decision_council_context" not in scope.calls[-1]
    assert "_procurement_review_context" not in scope.calls[-1]

from __future__ import annotations

from app.services.decision_evidence_service import (
    NODE_TYPE_ORDER,
    DecisionEvidenceService,
    _ProjectionBuilder,
    procurement_requirement_node_ids,
)


def _procurement_record(*, missing_data: list[str] | None = None) -> dict:
    return {
        "decision_id": "decision-1",
        "project_id": "project-1",
        "updated_at": "2026-07-24T00:00:00+00:00",
        "opportunity": {"title": "Public AI project", "issuer": "Agency"},
        "hard_filters": [
            {
                "code": "registration",
                "label": "Registration",
                "status": "pass",
                "blocking": True,
                "reason": "Registered",
                "evidence": ["certificate"],
            }
        ],
        "checklist_items": [
            {
                "category": "security",
                "title": "Security certificate",
                "status": "action_needed",
                "evidence": "renewal pending",
                "remediation_note": "Attach renewal certificate",
            }
        ],
        "missing_data": missing_data or ["Reference availability"],
        "recommendation": {"value": "GO", "summary": "Proceed with evidence work"},
        "source_snapshots": [
            {
                "snapshot_id": "snapshot-1",
                "source_kind": "g2b",
                "source_label": "RFP snapshot",
                "captured_at": "2026-07-23T00:00:00+00:00",
            }
        ],
    }


def _council(*, stale: bool = False, direction: str = "proceed") -> dict:
    return {
        "session_id": "council-1",
        "project_id": "project-1",
        "session_revision": 2,
        "updated_at": "2026-07-24T00:00:00+00:00",
        "current_procurement_binding_status": "stale" if stale else "current",
        "consensus": {
            "recommended_direction": direction,
            "summary": "Council summary",
            "strategy_options": ["Conservative proposal"],
            "top_risks": ["Schedule risk"],
        },
    }


def _workflow() -> dict:
    return {
        "report_workflow_id": "workflow-1",
        "project_id": "project-1",
        "project_document_id": "document-1",
        "source_bundle_id": "proposal_kr",
        "status": "slides_approved",
        "updated_at": "2026-07-24T00:00:00+00:00",
        "current_slide_version": 3,
        "source_refs": ["procurement:decision-1"],
        "planning": {
            "narrative_arc": ["Problem", "Recommendation"],
            "slide_plans": [
                {
                    "slide_id": "slide-1",
                    "title": "Problem",
                    "required_evidence": ["RFP requirement"],
                    "data_needs": ["Budget confirmation"],
                }
            ],
        },
        "slides": [
            {
                "slide_id": "slide-1",
                "title": "Problem",
                "status": "approved",
                "source_refs": ["procurement:decision-1"],
                "reference_refs": ["knowledge:reference-1"],
            }
        ],
    }


def _document() -> dict:
    return {
        "doc_id": "document-1",
        "request_id": "request-1",
        "bundle_id": "proposal_kr",
        "title": "Proposal",
        "generated_at": "2026-07-24T00:00:00+00:00",
        "approval_status": "in_review",
    }


def test_projection_fingerprint_and_order_are_deterministic():
    service = DecisionEvidenceService()
    kwargs = {
        "project_id": "project-1",
        "bundle_type": "proposal_kr",
        "procurement_record": _procurement_record(),
        "council_session": _council(),
        "project_documents": [_document()],
        "report_workflows": [_workflow()],
        "generated_at": "2026-07-24T12:00:00+00:00",
    }

    first = service.build(**kwargs)
    second = service.build(**{**kwargs, "generated_at": "2026-07-25T12:00:00+00:00"})

    assert first.projection_fingerprint == second.projection_fingerprint
    assert [(node.node_type, node.node_id) for node in first.nodes] == sorted(
        ((node.node_type, node.node_id) for node in first.nodes),
        key=lambda item: (NODE_TYPE_ORDER[item[0]], item[1]),
    )
    assert [edge.edge_id for edge in first.edges] == sorted(edge.edge_id for edge in first.edges)


def test_projection_does_not_leak_review_identity_or_receipt_fields():
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        review_summaries=[
            {
                "project_id": "project-1",
                "packet_sha256": "a" * 64,
                "review_status": "completed",
                "decision": "accepted",
                "rationale": "secret rationale",
                "receipt": {"secret": "receipt"},
                "reviewer_assignment": {"user_id": "stable-user"},
                "completed_by": "private reviewer",
                "tenant_id": "private-tenant",
            }
        ],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    payload = result.model_dump_json()
    for forbidden in ("secret rationale", "receipt", "stable-user", "private reviewer", "private-tenant"):
        assert forbidden not in payload
    assert result.nodes[0].node_id == f"review:{'a' * 64}"


def test_review_edge_requires_exact_document_packet_binding():
    packet_sha256 = "a" * 64
    document = {
        **_document(),
        "source_procurement_review_packet_sha256": packet_sha256,
    }
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        project_documents=[document],
        review_summaries=[
            {
                "project_id": "project-1",
                "packet_sha256": packet_sha256,
                "review_status": "completed",
                "decision": "accepted",
            },
            {
                "project_id": "project-1",
                "packet_sha256": "b" * 64,
                "review_status": "completed",
                "decision": "accepted",
            },
        ],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    review_edges = [
        edge for edge in result.edges if edge.relation_type == "reviewed_document"
    ]
    assert len(review_edges) == 1
    assert review_edges[0].source_node_id == f"review:{packet_sha256}"
    assert review_edges[0].target_node_id == "document:document-1"


def test_edges_keep_source_revision_and_provenance_contract():
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        procurement_record=_procurement_record(),
        generated_at="2026-07-24T12:00:00+00:00",
    )

    edge = next(
        edge
        for edge in result.edges
        if edge.relation_type == "defines_requirement"
        and edge.provenance.field_path == "hard_filters.registration"
    )
    assert edge.provenance.source_kind == "procurement_decision"
    assert edge.provenance.source_id == "decision-1"
    assert edge.provenance.source_revision == "2026-07-24T00:00:00+00:00"
    assert edge.provenance.content_sha256 == (
        "c061dbf7d6f0290a327c5b84ed17787ad937510458ed6fd1bd5a07dfc3de9b64"
    )
    assert edge.provenance.evidence_level == "authoritative"
    assert any(
        revision.source_kind == edge.provenance.source_kind
        and revision.source_id == edge.provenance.source_id
        and revision.revision == edge.provenance.source_revision
        for revision in result.source_revisions
    )


def test_projection_never_promotes_existing_text_to_explicit_coverage():
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        procurement_record=_procurement_record(),
        project_documents=[_document()],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    assert result.coverage.explicit == 0
    assert {item.status for item in result.coverage.items} <= {"missing", "unverifiable"}


def test_canonical_document_reference_creates_explicit_reference_coverage():
    procurement = _procurement_record()
    requirement_ref = next(
        ref
        for ref in procurement_requirement_node_ids(procurement)
        if ":hard_filter:" in ref
    )
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        procurement_record=procurement,
        project_documents=[
            {
                **_document(),
                "source_evidence_refs": [requirement_ref],
            }
        ],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    coverage = next(
        item
        for item in result.coverage.items
        if item.requirement_node_id == requirement_ref
    )
    requirement = next(
        node for node in result.nodes if node.node_id == requirement_ref
    )
    assert coverage.status == "explicit"
    assert coverage.evidence_refs == ["certificate", "document:document-1"]
    assert "does not assert requirement satisfaction" in coverage.summary
    assert requirement.coverage_status == "explicit"
    assert any(
        edge.relation_type == "explicitly_referenced_by"
        and edge.source_node_id == requirement_ref
        and edge.target_node_id == "document:document-1"
        for edge in result.edges
    )


def test_only_genuine_approved_approval_record_is_marked_approved():
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        project_documents=[_document()],
        approval_records=[
            {
                "approval_id": "approval-approved",
                "project_id": "project-1",
                "project_document_id": "document-1",
                "status": "approved",
                "approved_at": "2026-07-24T12:00:00+00:00",
            },
            {
                "approval_id": "approval-review",
                "project_id": "project-1",
                "project_document_id": "document-1",
                "status": "in_review",
            },
        ],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    statuses = {node.node_id: node.status for node in result.nodes if node.node_type == "approval"}
    assert statuses == {"approval:approval-approved": "approved", "approval:approval-review": "in_review"}


def test_export_node_is_readiness_not_observed_export():
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        project_documents=[_document()],
        report_workflows=[_workflow()],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    export = next(node for node in result.nodes if node.node_type == "export")
    assert export.status == "available"
    assert export.actual_export_observed is False
    assert result.proposal_blueprint.actual_export_observed is False
    assert "export_evidence_not_observed" in {item.code for item in result.diagnostics}


def test_stale_conflict_and_rejection_diagnostics_are_reported():
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        procurement_record=_procurement_record(),
        council_session=_council(stale=True, direction="do_not_proceed"),
        review_summaries=[
            {
                "project_id": "project-1",
                "packet_sha256": "b" * 64,
                "review_status": "completed",
                "decision": "rejected",
            }
        ],
        approval_records=[
            {
                "approval_id": "approval-stale",
                "project_id": "project-1",
                "status": "approved",
                "source_decision_council_document_status": "stale_procurement",
            }
        ],
        generated_at="2026-07-24T12:00:00+00:00",
    )

    codes = {item.code for item in result.diagnostics}
    assert {
        "council_binding_stale",
        "recommendation_council_conflict",
        "procurement_review_rejected",
        "approval_source_stale",
        "requirement_evidence_missing",
    } <= codes


def test_projection_caps_nodes_and_edges_with_transparent_diagnostic():
    record = _procurement_record(missing_data=[f"Missing evidence {index}" for index in range(250)])
    result = DecisionEvidenceService().build(
        project_id="project-1",
        bundle_type="proposal_kr",
        procurement_record=record,
        generated_at="2026-07-24T12:00:00+00:00",
    )

    assert len(result.nodes) == 200
    assert len(result.edges) <= 400
    assert result.truncated is True
    assert "projection_truncated" in {item.code for item in result.diagnostics}


def test_projection_edge_limit_is_exact_at_400():
    def build_projection(edge_count: int):
        builder = _ProjectionBuilder(
            project_id="project-edge-limit",
            bundle_type="proposal_kr",
        )
        for node_id, node_type in (
            ("source:edge-limit", "source"),
            ("claim:edge-limit", "claim"),
        ):
            builder._add_node(
                node_id=node_id,
                node_type=node_type,
                label=node_id,
                status="current",
                summary="",
                updated_at="2026-07-27T00:00:00+00:00",
                evidence_level="derived",
            )
        for index in range(edge_count):
            builder._add_edge(
                relation_type=f"edge_{index}",
                source_node_id="source:edge-limit",
                target_node_id="claim:edge-limit",
                status="current",
                source_kind="edge_limit_fixture",
                source_id="edge-limit",
                source_revision="1",
                field_path=f"edges.{index}",
                content={"index": index},
                evidence_level="derived",
            )
        return builder.finish(generated_at="2026-07-27T00:00:00+00:00")

    exact = build_projection(400)
    overflow = build_projection(401)

    assert len(exact.nodes) == 2
    assert len(exact.edges) == 400
    assert exact.truncated is False
    assert "projection_truncated" not in {item.code for item in exact.diagnostics}

    assert len(overflow.nodes) == 2
    assert len(overflow.edges) == 400
    assert overflow.truncated is True
    assert "projection_truncated" in {item.code for item in overflow.diagnostics}

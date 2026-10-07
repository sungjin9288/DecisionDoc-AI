"""Attach a finished generation to its project with source provenance."""
from __future__ import annotations

from typing import Any

from app.schemas import GenerateRequest


def link_generated_document(
    project_store: Any,
    payload: GenerateRequest,
    *,
    tenant_id: str,
    request_id: str,
    docs: list[dict[str, Any]],
    metadata: dict[str, Any],
):
    return project_store.add_document(
        project_id=payload.project_id,
        tenant_id=tenant_id,
        request_id=request_id,
        bundle_id=payload.bundle_type,
        title=payload.title,
        docs=docs,
        approval_id=None,
        tags=[],
        source_decision_council_session_id=metadata.get("decision_council_session_id"),
        source_decision_council_session_revision=metadata.get("decision_council_session_revision"),
        source_decision_council_direction=metadata.get("decision_council_direction"),
        source_procurement_review_packet_sha256=metadata.get("procurement_review_packet_sha256"),
        source_procurement_review_decision=metadata.get("procurement_review_decision"),
        source_procurement_reviewed_at=metadata.get("procurement_reviewed_at"),
        source_procurement_review_source_updated_at=metadata.get("procurement_review_source_updated_at"),
        source_procurement_review_operational_approval=metadata.get(
            "procurement_review_operational_approval"
        ),
        source_evidence_refs=metadata.get("decision_evidence_refs", []),
        source_procurement_binding=metadata.get("source_procurement_binding"),
    )

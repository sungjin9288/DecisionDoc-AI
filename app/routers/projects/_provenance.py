"""Tenant-scoped project document provenance shared by route modules."""
from __future__ import annotations

import hashlib
import json

from fastapi import Request

from app.routers.projects._shared import _serialize_project_detail
from app.services.procurement_review_handoff import (
    load_validated_procurement_review_evidence,
)


PROJECT_DOCUMENT_FRESHNESS_FIELDS = (
    "decision_council_document_status",
    "decision_council_document_status_tone",
    "decision_council_document_status_copy",
    "decision_council_document_status_summary",
    "procurement_review_document_status",
    "procurement_review_document_status_tone",
    "procurement_review_document_status_copy",
    "procurement_review_document_status_summary",
)


def lookup_project_document(
    request: Request,
    *,
    tenant_id: str,
    project_id: str,
    project_document_id: str,
    request_id: str,
    bundle_id: str,
) -> tuple[str, dict | None]:
    if not project_id and not project_document_id:
        return "not_linked", None
    if not project_id or not project_document_id:
        return "mismatch", None

    project = request.app.state.project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        return "missing", None

    detail = _serialize_project_detail(request, tenant_id=tenant_id, project=project)
    document = next(
        (
            item
            for item in detail.get("documents", [])
            if item.get("doc_id") == project_document_id
        ),
        None,
    )
    if document is None:
        return "missing", None
    if request_id and document.get("request_id") != request_id:
        return "mismatch", None
    if bundle_id and document.get("bundle_id") != bundle_id:
        return "mismatch", None
    return "current", document


def project_document_freshness_values(document: dict | None) -> dict[str, str]:
    if document is None:
        return {field: "" for field in PROJECT_DOCUMENT_FRESHNESS_FIELDS}
    return {
        field: str(document.get(field) or "").strip()
        for field in PROJECT_DOCUMENT_FRESHNESS_FIELDS
    }


def project_document_source_fingerprint(
    request: Request,
    *,
    tenant_id: str,
    project_id: str,
    binding_status: str,
    document: dict | None,
) -> str:
    if not project_id or document is None:
        return ""

    procurement_record = None
    procurement_store = getattr(request.app.state, "procurement_store", None)
    if procurement_store is not None:
        procurement_record = procurement_store.get(project_id, tenant_id=tenant_id)

    latest_council = None
    council_service = getattr(request.app.state, "decision_council_service", None)
    if council_service is not None:
        latest_council = council_service.get_latest_procurement_council(
            tenant_id=tenant_id,
            project_id=project_id,
        )

    review_record = None
    packet_sha256 = str(
        document.get("source_procurement_review_packet_sha256") or ""
    ).strip()
    review_store = getattr(request.app.state, "procurement_review_store", None)
    if review_store is not None and packet_sha256:
        try:
            review_record = load_validated_procurement_review_evidence(
                review_store,
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
        except ValueError:
            review_record = None

    source_state = {
        "binding_status": binding_status,
        "document": {
            "doc_id": document.get("doc_id"),
            "request_id": document.get("request_id"),
            "bundle_id": document.get("bundle_id"),
            "source_decision_council_session_id": document.get(
                "source_decision_council_session_id"
            ),
            "source_decision_council_session_revision": document.get(
                "source_decision_council_session_revision"
            ),
            "source_procurement_review_packet_sha256": packet_sha256,
            "source_procurement_review_source_updated_at": document.get(
                "source_procurement_review_source_updated_at"
            ),
            "decision_council_document_status": document.get(
                "decision_council_document_status"
            ),
            "procurement_review_document_status": document.get(
                "procurement_review_document_status"
            ),
        },
        "current_procurement_updated_at": getattr(procurement_record, "updated_at", ""),
        "latest_council_session_id": getattr(latest_council, "session_id", ""),
        "latest_council_session_revision": getattr(latest_council, "session_revision", None),
        "review_status": getattr(review_record, "review_status", ""),
        "review_decision": getattr(review_record, "decision", ""),
        "review_operational_approval": getattr(review_record, "operational_approval", None),
    }
    canonical = json.dumps(
        source_state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

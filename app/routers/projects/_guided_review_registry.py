"""Guided Decision Review disposition registry helpers for decision evidence routes."""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from fastapi import HTTPException, Request, Response

from app.dependencies import get_tenant_id
from app.schemas.decision_evidence import DecisionEvidenceBundleType
from app.services.procurement_review_access import get_procurement_review_access
from app.storage.guided_decision_review_disposition_registry import (
    GuidedDecisionReviewDispositionRegistryError,
    canonical_guided_review_registry_json_bytes,
    get_guided_decision_review_disposition_registry,
)


logger = logging.getLogger("decisiondoc.procurement.guided_review")


def _guided_review_disposition_registry(
    request: Request,
    *,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType,
):
    return get_guided_decision_review_disposition_registry(
        tenant_id=get_tenant_id(request),
        project_id=project_id,
        bundle_type=bundle_type,
        backend=request.app.state.state_backend,
    )


def _require_guided_review_registry_operation_id(operation_id: str) -> str:
    try:
        parsed = UUID(operation_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="operation ID 형식이 올바르지 않습니다.",
        ) from exc
    if parsed.version != 4 or str(parsed) != operation_id:
        raise HTTPException(
            status_code=422,
            detail="operation ID 형식이 올바르지 않습니다.",
        )
    return operation_id


def _guided_review_registry_owner(request: Request) -> str | None:
    access = get_procurement_review_access(request)
    return None if access.is_admin else access.user_id


def _guided_review_registry_record_response(
    record: dict,
    *,
    status_code: int,
    attachment: bool = False,
) -> Response:
    body = canonical_guided_review_registry_json_bytes(record)
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-DecisionDoc-Guided-Review-Disposition-Record-SHA256": (
            hashlib.sha256(body).hexdigest()
        ),
        "X-DecisionDoc-Operational-Approval": "false",
    }
    if record["contract_version"] == "guided-decision-review-disposition-record.v1":
        headers["X-DecisionDoc-Guided-Review-Disposition-Issuance-Provenance"] = (
            "legacy-unrecorded"
        )
    else:
        headers["X-DecisionDoc-Guided-Review-Disposition-Issuance-Provenance"] = (
            "server-issued"
        )
        headers[
            "X-DecisionDoc-Guided-Review-Disposition-Issuance-Record-SHA256"
        ] = record["source_issuance_metadata_sha256"]
    if attachment:
        headers["Content-Disposition"] = (
            'attachment; filename="guided-decision-review-disposition-record-'
            f'{record["operation_id"]}.json"'
        )
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/json; charset=utf-8",
        headers=headers,
    )


def _set_guided_review_registry_audit(
    request: Request,
    record: dict,
    *,
    replay: bool,
) -> None:
    detail = {
        "operation_id": record["operation_id"],
        "record_sha256": hashlib.sha256(
            canonical_guided_review_registry_json_bytes(record)
        ).hexdigest(),
        "source_disposition_receipt_sha256": record[
            "source_disposition_receipt_sha256"
        ],
        "source_recheck_receipt_sha256": record[
            "source_recheck_receipt_sha256"
        ],
        "current_handoff_sha256": record["current_handoff_sha256"],
        "current_review_state_fingerprint_sha256": record[
            "current_review_state_fingerprint_sha256"
        ],
        "review_state_status": record["review_state_status"],
        "review_disposition": record["review_disposition"],
        "disposition_binding_sha256": record["disposition_binding_sha256"],
        "replay": replay,
        "review_state_only": True,
        "review_only": True,
        "read_only": True,
        "reviewer_identity_bound": True,
        "registry_record_persisted": True,
        "snapshot_atomic": False,
        "requires_recheck_before_reliance": True,
        **record["authority"],
    }
    if record["contract_version"] == "guided-decision-review-disposition-record.v1":
        detail["issuance_provenance"] = "legacy_issuance_unrecorded"
    else:
        detail["issuance_provenance"] = "server_issued"
        detail["source_issuance_metadata_sha256"] = record[
            "source_issuance_metadata_sha256"
        ]
    request.state.guided_review_registry_detail = detail


def _read_guided_review_registry_record(
    request: Request,
    *,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType,
    operation_id: str,
) -> tuple[dict, bytes]:
    operation_id = _require_guided_review_registry_operation_id(operation_id)
    try:
        return _guided_review_disposition_registry(
            request,
            project_id=project_id,
            bundle_type=bundle_type,
        ).read_canonical(
            operation_id,
            reviewer_user_id=_guided_review_registry_owner(request),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Guided Decision Review 처리 이력이 없습니다.",
        ) from exc
    except GuidedDecisionReviewDispositionRegistryError as exc:
        logger.error("Guided review registry read failed closed.", exc_info=exc)
        raise HTTPException(
            status_code=503,
            detail="Guided Decision Review 처리 이력을 조회할 수 없습니다.",
        ) from exc

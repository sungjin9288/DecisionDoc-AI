"""Pure scope, parsing, and binding helpers for procurement review storage."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.storage.procurement_review_models import (
    ProcurementReviewRecord,
    ProcurementReviewStoreError,
    record_from_dict,
    require_sha256,
    safe_segment,
    unique_object,
)
from app.tenant import require_tenant_id


def tenant_review_prefix(*, tenant_id: str) -> Path:
    """Return the tenant-owned root for procurement review artifacts."""
    tenant = require_tenant_id(tenant_id)
    return Path("tenants") / tenant / "procurement_reviews"


def review_prefix(
    *,
    tenant_id: str,
    project_id: str,
    packet_sha256: str | None = None,
) -> Path:
    """Return the project (and optional packet) scoped review prefix."""
    project = safe_segment(project_id, field="project_id")
    prefix = tenant_review_prefix(tenant_id=tenant_id) / project
    if packet_sha256 is not None:
        prefix /= require_sha256(packet_sha256)
    return prefix


def require_record_scope(
    record: ProcurementReviewRecord,
    *,
    tenant_id: str,
    project_id: str,
    packet_sha256: str,
) -> tuple[str, str, str]:
    """Normalize caller scope and require the record to belong to it."""
    tenant_id = require_tenant_id(tenant_id)
    project_id = safe_segment(project_id, field="project_id")
    packet_sha256 = require_sha256(packet_sha256)
    if not isinstance(record, ProcurementReviewRecord) or (
        record.tenant_id != tenant_id
        or record.project_id != project_id
        or record.packet_sha256 != packet_sha256
    ):
        raise ValueError("procurement review record does not match caller scope")
    return tenant_id, project_id, packet_sha256


def record_from_raw(
    raw: str | None,
    *,
    tenant_id: str,
    project_id: str,
    packet_sha256: str,
) -> ProcurementReviewRecord | None:
    """Parse one persisted review record and require its stored identity."""
    if raw is None:
        return None
    if not raw.strip():
        raise ProcurementReviewStoreError(
            "Invalid procurement review record"
        )
    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(payload, dict):
            raise TypeError("procurement review record must be an object")
        record = record_from_dict(payload)
    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        ProcurementReviewStoreError,
    ) as exc:
        raise ProcurementReviewStoreError(
            "Invalid procurement review record"
        ) from exc
    if (
        record.tenant_id != tenant_id
        or record.project_id != project_id
        or record.packet_sha256 != packet_sha256
    ):
        raise ProcurementReviewStoreError(
            "Procurement review record identity is inconsistent"
        )
    return record


def validate_bound_packet(
    record: ProcurementReviewRecord, content: bytes,
) -> dict[str, Any] | None:
    """Verify packet bytes against the record's tenant/project binding."""
    from app.services.procurement_decision_package.review_packet import (
        PACKET_SCHEMA_VERSION_V2,
        PACKET_SCHEMA_VERSION_V3,
        verify_bound_procurement_packet,
    )
    from app.services.procurement_review_evidence import (
        validate_persisted_procurement_review_packet,
    )

    verified = verify_bound_procurement_packet(
        content,
        expected_tenant_id=record.tenant_id,
        expected_project_id=record.project_id,
    )
    if (
        verified is not None
        or record.receipt["packet_schema_version"] in {PACKET_SCHEMA_VERSION_V2, PACKET_SCHEMA_VERSION_V3}
    ):
        validate_persisted_procurement_review_packet(record, content)
    return verified


def validate_bound_reviewed_package(
    record: ProcurementReviewRecord, content: bytes,
) -> None:
    """Verify reviewed package bytes for bound (v2/v3) packet schemas."""
    from app.services.procurement_decision_package.review_packet import (
        PACKET_SCHEMA_VERSION_V2,
        PACKET_SCHEMA_VERSION_V3,
    )
    from app.services.procurement_review_evidence import (
        validate_persisted_procurement_reviewed_package,
    )

    if record.receipt["packet_schema_version"] in {PACKET_SCHEMA_VERSION_V2, PACKET_SCHEMA_VERSION_V3}:
        validate_persisted_procurement_reviewed_package(record, content)

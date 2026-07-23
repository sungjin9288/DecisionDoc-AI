"""Persisted procurement review contracts and backend artifact helpers."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping

from app.tenant import require_tenant_id
from app.storage.state_backend import StateBackend, StateBackendError


REVIEW_RECORD_SCHEMA_VERSION_V1 = "decisiondoc.procurement_project_review_record.v1"
REVIEW_RECORD_SCHEMA_VERSION = "decisiondoc.procurement_project_review_record.v2"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REVIEW_RECEIPT_SCHEMA_VERSION = "decisiondoc.procurement_review_receipt.v1"
REVIEW_RECEIPT_FIELD_ORDER = (
    "schema_version",
    "status",
    "packet_sha256",
    "packet_size_bytes",
    "packet_schema_version",
    "package_id",
    "recommendation",
    "reviewer",
    "decision",
    "rationale",
    "reviewed_at",
    "authorization_boundary",
    "operational_approval",
)


class ProcurementReviewStoreError(RuntimeError):
    """Raised when persisted procurement review evidence cannot be trusted."""


def sha256_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_review_artifact(
    backend: StateBackend,
    relative_path: str,
    *,
    label: str,
) -> bytes | None:
    try:
        return backend.read_bytes(relative_path)
    except StateBackendError as exc:
        raise ProcurementReviewStoreError(
            f"Failed to read {label}"
        ) from exc


def ensure_review_artifact(
    backend: StateBackend,
    relative_path: str,
    content: bytes,
    *,
    label: str,
) -> bool:
    try:
        created = backend.write_bytes_if_absent(
            relative_path,
            content,
            content_type="application/zip",
        )
    except StateBackendError as exc:
        try:
            observed = backend.read_bytes(relative_path)
        except StateBackendError:
            observed = None
        if observed == content:
            return False
        raise ProcurementReviewStoreError(
            f"Failed to persist {label}"
        ) from exc
    if created:
        return True
    observed = read_review_artifact(backend, relative_path, label=label)
    if observed != content:
        raise ProcurementReviewStoreError(
            f"Existing {label} is inconsistent"
        )
    return False


def delete_unreferenced_review_artifact(
    backend: StateBackend,
    relative_path: str,
    *,
    label: str,
) -> None:
    try:
        backend.delete(relative_path)
    except StateBackendError as exc:
        try:
            observed = backend.read_bytes(relative_path)
        except StateBackendError:
            observed = b"unverified"
        if observed is None:
            return
        raise ProcurementReviewStoreError(
            f"Failed to remove unreferenced {label}"
        ) from exc


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProcurementReviewStoreError(
                f"Duplicate key in procurement review state: {key!r}"
            )
        result[key] = value
    return result


@dataclass(frozen=True)
class ProcurementReviewRecord:
    schema_version: str
    tenant_id: str
    project_id: str
    packet_sha256: str
    packet_size_bytes: int
    package_id: str
    recommendation: str
    reviewer: str
    review_status: Literal["pending", "completed"]
    decision: Literal["accepted", "changes_requested", "rejected"] | None
    prepared_at: str
    reviewed_at: str | None
    reviewed_package_sha256: str | None
    reviewed_package_size_bytes: int | None
    operational_approval: bool
    receipt: dict[str, Any]
    reviewer_assignment: dict[str, str] | None = None
    reviewer_attestation: dict[str, Any] | None = None
    reviewer_identity_bound: bool = False
    reviewer_session_bound: bool = False
    reviewer_attestation_sha256: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """Return reviewer-facing state without storage paths or rationale."""
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in {"tenant_id", "receipt"}
        }


_V2_RECORD_FIELDS = set(ProcurementReviewRecord.__dataclass_fields__)
_V1_RECORD_FIELDS = _V2_RECORD_FIELDS - {
    "reviewer_assignment",
    "reviewer_attestation",
    "reviewer_identity_bound",
    "reviewer_session_bound",
    "reviewer_attestation_sha256",
}


def safe_segment(value: str, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise ValueError(f"{field} is invalid")
    return value


def require_sha256(value: str, *, field: str = "packet_sha256") -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field} is invalid")
    return value


def _require_reviewer_assignment(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or tuple(value) != ("user_id", "username"):
        raise ValueError("procurement review reviewer_assignment is invalid")
    assignment: dict[str, str] = {}
    for field in ("user_id", "username"):
        field_value = value[field]
        if (
            not isinstance(field_value, str)
            or not field_value
            or field_value != field_value.strip()
        ):
            raise ValueError(
                f"procurement review reviewer_assignment.{field} is invalid"
            )
        assignment[field] = field_value
    return assignment


def record_from_dict(payload: Mapping[str, Any]) -> ProcurementReviewRecord:
    schema_version = payload.get("schema_version")
    expected_fields = (
        _V1_RECORD_FIELDS
        if schema_version == REVIEW_RECORD_SCHEMA_VERSION_V1
        else _V2_RECORD_FIELDS
    )
    if set(payload) != expected_fields:
        raise ValueError("procurement review record fields are invalid")
    if not isinstance(payload["receipt"], dict):
        raise ValueError("procurement review record receipt is invalid")
    record = ProcurementReviewRecord(**payload)
    validate_record(record)
    return record


def serialize_review_record(record: ProcurementReviewRecord) -> str:
    """Serialize v1 records without adding v2 compatibility defaults."""
    validate_record(record)
    payload = asdict(record)
    if record.schema_version == REVIEW_RECORD_SCHEMA_VERSION_V1:
        for field in _V2_RECORD_FIELDS - _V1_RECORD_FIELDS:
            payload.pop(field)
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:
        raise ProcurementReviewStoreError(
            "Failed to serialize procurement review record"
        ) from exc


def validate_record(record: ProcurementReviewRecord) -> None:
    if record.schema_version not in {
        REVIEW_RECORD_SCHEMA_VERSION_V1,
        REVIEW_RECORD_SCHEMA_VERSION,
    }:
        raise ValueError("procurement review record schema_version is invalid")
    require_tenant_id(record.tenant_id)
    safe_segment(record.project_id, field="project_id")
    require_sha256(record.packet_sha256)
    if (
        isinstance(record.packet_size_bytes, bool)
        or not isinstance(record.packet_size_bytes, int)
        or record.packet_size_bytes <= 0
    ):
        raise ValueError("procurement review record packet_size_bytes is invalid")
    if not isinstance(record.prepared_at, str) or not record.prepared_at:
        raise ValueError("procurement review record identity is invalid")
    if any(
        not isinstance(value, str) or not value
        for value in (
            record.package_id,
            record.recommendation,
            record.reviewer,
        )
    ):
        raise ValueError("procurement review record review context is invalid")
    if record.operational_approval is not False:
        raise ValueError("procurement review record must not grant operational approval")
    if not isinstance(record.receipt, dict):
        raise ValueError("procurement review record receipt is invalid")

    receipt = record.receipt
    if tuple(receipt) != REVIEW_RECEIPT_FIELD_ORDER:
        raise ValueError("procurement review record receipt fields are invalid")
    if receipt["schema_version"] != REVIEW_RECEIPT_SCHEMA_VERSION:
        raise ValueError(
            "procurement review record receipt schema_version is invalid"
        )
    if (
        not isinstance(receipt["packet_schema_version"], str)
        or not receipt["packet_schema_version"]
        or receipt["authorization_boundary"] != "explicit"
    ):
        raise ValueError("procurement review record receipt authority is invalid")

    expected_receipt_values = {
        "packet_sha256": record.packet_sha256,
        "packet_size_bytes": record.packet_size_bytes,
        "package_id": record.package_id,
        "recommendation": record.recommendation,
        "reviewer": record.reviewer,
        "status": record.review_status,
        "decision": record.decision,
        "reviewed_at": record.reviewed_at,
        "operational_approval": False,
    }
    if any(
        receipt.get(field) != expected
        for field, expected in expected_receipt_values.items()
    ):
        raise ValueError("procurement review record receipt is inconsistent")

    if record.review_status == "pending":
        if any(
            value is not None
            for value in (
                record.decision,
                record.reviewed_at,
                record.reviewed_package_sha256,
                record.reviewed_package_size_bytes,
            )
        ):
            raise ValueError(
                "pending procurement review record contains completion evidence"
            )
        if record.receipt["rationale"] is not None:
            raise ValueError(
                "pending procurement review record contains review rationale"
            )
        if record.schema_version == REVIEW_RECORD_SCHEMA_VERSION_V1:
            if any(
                (
                    record.reviewer_assignment,
                    record.reviewer_attestation,
                    record.reviewer_identity_bound,
                    record.reviewer_session_bound,
                    record.reviewer_attestation_sha256,
                )
            ):
                raise ValueError(
                    "v1 procurement review record contains v2 reviewer evidence"
                )
            return

        assignment = _require_reviewer_assignment(
            record.reviewer_assignment
        )
        if assignment["username"] != record.reviewer:
            raise ValueError("procurement review assignment is inconsistent")
        if record.reviewer_identity_bound is not True:
            raise ValueError(
                "procurement review record must remain identity bound"
            )
        if record.reviewer_session_bound is not False:
            raise ValueError(
                "pending procurement review must not claim a reviewer session"
            )
        if (
            record.reviewer_attestation is not None
            or record.reviewer_attestation_sha256 is not None
        ):
            raise ValueError(
                "pending procurement review contains reviewer attestation"
            )
        return

    if record.review_status != "completed":
        raise ValueError("procurement review record status is invalid")
    if record.decision not in {"accepted", "changes_requested", "rejected"}:
        raise ValueError("procurement review record decision is invalid")
    if not isinstance(record.reviewed_at, str) or not record.reviewed_at:
        raise ValueError("completed procurement review record is incomplete")
    if (
        isinstance(record.reviewed_package_size_bytes, bool)
        or not isinstance(record.reviewed_package_size_bytes, int)
        or record.reviewed_package_size_bytes <= 0
    ):
        raise ValueError("procurement review record package size is invalid")
    require_sha256(
        record.reviewed_package_sha256 or "",
        field="reviewed_package_sha256",
    )
    if (
        not isinstance(record.receipt["rationale"], str)
        or not record.receipt["rationale"].strip()
    ):
        raise ValueError(
            "completed procurement review record rationale is invalid"
        )

    if record.schema_version == REVIEW_RECORD_SCHEMA_VERSION_V1:
        if any(
            (
                record.reviewer_assignment,
                record.reviewer_attestation,
                record.reviewer_identity_bound,
                record.reviewer_session_bound,
                record.reviewer_attestation_sha256,
            )
        ):
            raise ValueError(
                "v1 procurement review record contains v2 reviewer evidence"
            )
        return

    assignment = _require_reviewer_assignment(record.reviewer_assignment)
    if assignment["username"] != record.reviewer:
        raise ValueError("procurement review assignment is inconsistent")
    if record.reviewer_identity_bound is not True:
        raise ValueError("procurement review record must remain identity bound")

    if record.reviewer_session_bound is not True:
        raise ValueError(
            "completed procurement review must remain session bound"
        )
    if not isinstance(record.reviewer_attestation, dict):
        raise ValueError(
            "completed procurement review requires reviewer attestation"
        )

    from app.services.procurement_decision_package.reviewer_attestation import (
        attestation_sha256,
        validate_procurement_reviewer_attestation,
    )

    attestation = validate_procurement_reviewer_attestation(
        record.reviewer_attestation,
        expected_tenant_id=record.tenant_id,
        expected_project_id=record.project_id,
        expected_packet_sha256=record.packet_sha256,
        expected_receipt_sha256=hashlib.sha256(
            (
                json.dumps(record.receipt, ensure_ascii=False, indent=2)
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
        expected_decision=record.decision,
        expected_reviewed_at=record.reviewed_at,
    )
    if attestation["reviewer"]["user_id"] != assignment["user_id"]:
        raise ValueError(
            "procurement review reviewer attestation identity is inconsistent"
        )
    require_sha256(
        record.reviewer_attestation_sha256 or "",
        field="reviewer_attestation_sha256",
    )
    if (
        record.reviewer_attestation_sha256
        != attestation_sha256(record.reviewer_attestation)
    ):
        raise ValueError(
            "procurement review reviewer attestation hash is invalid"
        )


def build_pending_review_record(
    *,
    tenant_id: str,
    project_id: str,
    packet_sha256: str,
    packet_size_bytes: int,
    receipt: Mapping[str, Any],
    prepared_at: str,
    reviewer_assignment: Mapping[str, str] | None = None,
) -> ProcurementReviewRecord:
    """Build a validated v1 or identity-assigned v2 pending record."""
    pending_receipt = dict(receipt)
    assignment = (
        dict(reviewer_assignment)
        if reviewer_assignment is not None
        else None
    )
    record = ProcurementReviewRecord(
        schema_version=(
            REVIEW_RECORD_SCHEMA_VERSION
            if assignment is not None
            else REVIEW_RECORD_SCHEMA_VERSION_V1
        ),
        tenant_id=tenant_id,
        project_id=project_id,
        packet_sha256=packet_sha256,
        packet_size_bytes=packet_size_bytes,
        package_id=pending_receipt.get("package_id", ""),
        recommendation=pending_receipt.get("recommendation", ""),
        reviewer=pending_receipt.get("reviewer", ""),
        review_status=pending_receipt.get("status", ""),
        decision=pending_receipt.get("decision"),
        prepared_at=prepared_at,
        reviewed_at=pending_receipt.get("reviewed_at"),
        reviewed_package_sha256=None,
        reviewed_package_size_bytes=None,
        operational_approval=False,
        receipt=pending_receipt,
        reviewer_assignment=assignment,
        reviewer_identity_bound=assignment is not None,
    )
    validate_record(record)
    return record


def upgrade_pending_reviewer_assignment(
    record: ProcurementReviewRecord,
    reviewer_assignment: Mapping[str, str],
) -> ProcurementReviewRecord:
    """Upgrade one exact legacy pending record without rewriting evidence."""
    if (
        record.schema_version != REVIEW_RECORD_SCHEMA_VERSION_V1
        or record.review_status != "pending"
    ):
        raise ValueError(
            "only a legacy pending procurement review can be upgraded"
        )
    upgraded = replace(
        record,
        schema_version=REVIEW_RECORD_SCHEMA_VERSION,
        reviewer_assignment=dict(reviewer_assignment),
        reviewer_identity_bound=True,
    )
    validate_record(upgraded)
    return upgraded


def build_completed_review_record(
    current: ProcurementReviewRecord,
    *,
    completed_receipt: Mapping[str, Any],
    reviewed_package_content: bytes,
    reviewer_attestation: Mapping[str, Any] | None,
) -> ProcurementReviewRecord:
    """Bind completion evidence to the current immutable review record."""
    if current.reviewer_identity_bound and reviewer_attestation is None:
        raise ValueError(
            "identity-bound procurement review requires reviewer attestation"
        )
    if not current.reviewer_identity_bound and reviewer_attestation is not None:
        raise ValueError(
            "legacy procurement review cannot add reviewer attestation"
        )

    attestation = (
        dict(reviewer_attestation)
        if reviewer_attestation is not None
        else None
    )
    attestation_hash = None
    if attestation is not None:
        from app.services.procurement_decision_package.reviewer_attestation import (
            attestation_sha256,
        )

        attestation_hash = attestation_sha256(attestation)

    completed = ProcurementReviewRecord(
        **{
            **asdict(current),
            "review_status": completed_receipt.get("status"),
            "decision": completed_receipt.get("decision"),
            "reviewed_at": completed_receipt.get("reviewed_at"),
            "reviewed_package_sha256": sha256_content(
                reviewed_package_content
            ),
            "reviewed_package_size_bytes": len(
                reviewed_package_content
            ),
            "receipt": dict(completed_receipt),
            "reviewer_attestation": attestation,
            "reviewer_session_bound": attestation is not None,
            "reviewer_attestation_sha256": attestation_hash,
        }
    )
    validate_record(completed)
    return completed

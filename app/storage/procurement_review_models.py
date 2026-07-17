"""Persisted procurement review contracts and backend artifact helpers."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

from app.tenant import require_tenant_id
from app.storage.state_backend import StateBackend, StateBackendError


REVIEW_RECORD_SCHEMA_VERSION = "decisiondoc.procurement_project_review_record.v1"
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

    def to_public_dict(self) -> dict[str, Any]:
        """Return reviewer-facing state without exposing storage paths."""
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in {"tenant_id", "receipt"}
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


def record_from_dict(payload: Mapping[str, Any]) -> ProcurementReviewRecord:
    expected_fields = set(ProcurementReviewRecord.__dataclass_fields__)
    if set(payload) != expected_fields:
        raise ValueError("procurement review record fields are invalid")
    if not isinstance(payload["receipt"], dict):
        raise ValueError("procurement review record receipt is invalid")
    record = ProcurementReviewRecord(
        schema_version=payload["schema_version"],
        tenant_id=payload["tenant_id"],
        project_id=payload["project_id"],
        packet_sha256=payload["packet_sha256"],
        packet_size_bytes=payload["packet_size_bytes"],
        package_id=payload["package_id"],
        recommendation=payload["recommendation"],
        reviewer=payload["reviewer"],
        review_status=payload["review_status"],
        decision=payload["decision"],
        prepared_at=payload["prepared_at"],
        reviewed_at=payload["reviewed_at"],
        reviewed_package_sha256=payload["reviewed_package_sha256"],
        reviewed_package_size_bytes=payload["reviewed_package_size_bytes"],
        operational_approval=payload["operational_approval"],
        receipt=dict(payload["receipt"]),
    )
    validate_record(record)
    return record


def validate_record(record: ProcurementReviewRecord) -> None:
    if record.schema_version != REVIEW_RECORD_SCHEMA_VERSION:
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

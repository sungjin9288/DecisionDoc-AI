"""Create and validate review receipts bound to procurement packets."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.services.procurement_decision_package.constants import (
    DECISION_PACKAGE_NAME,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
)
from app.services.procurement_decision_package.review_packet import (
    _load_package_document,
    verify_procurement_review_packet,
)


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
REVIEW_RECEIPT_PENDING = "pending"
REVIEW_RECEIPT_COMPLETED = "completed"
REVIEW_DECISIONS = ("accepted", "changes_requested", "rejected")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _packet_context(content: bytes) -> dict[str, Any]:
    verification = verify_procurement_review_packet(content)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        package_doc = _load_package_document(archive.read(DECISION_PACKAGE_NAME))
    package = package_doc["package"]
    return {
        **verification,
        "reviewer": package["pending_signoff"]["reviewer"],
    }


def _require_non_empty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"procurement review receipt {field} must be non-empty")
    return value.strip()


def _normalize_reviewed_at(value: Any) -> str:
    reviewed_at = _require_non_empty_text(value, "reviewed_at")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "procurement review receipt reviewed_at must be an ISO 8601 timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("procurement review receipt reviewed_at must use UTC")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_pending_procurement_review_receipt(
    packet_content: bytes,
) -> dict[str, Any]:
    """Build a deterministic pending receipt for a verified packet."""
    packet = _packet_context(packet_content)
    return {
        "schema_version": REVIEW_RECEIPT_SCHEMA_VERSION,
        "status": REVIEW_RECEIPT_PENDING,
        "packet_sha256": _sha256(packet_content),
        "packet_size_bytes": len(packet_content),
        "packet_schema_version": packet["schema_version"],
        "package_id": packet["package_id"],
        "recommendation": packet["recommendation"],
        "reviewer": packet["reviewer"],
        "decision": None,
        "rationale": None,
        "reviewed_at": None,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
    }


def validate_procurement_review_receipt(
    receipt: Any,
    packet_content: bytes,
) -> dict[str, Any]:
    """Validate receipt structure, packet binding, review state, and authority."""
    if not isinstance(receipt, dict):
        raise ValueError("procurement review receipt must be an object")
    if tuple(receipt) != REVIEW_RECEIPT_FIELD_ORDER:
        raise ValueError("procurement review receipt fields are invalid")
    if receipt["schema_version"] != REVIEW_RECEIPT_SCHEMA_VERSION:
        raise ValueError("procurement review receipt schema_version is invalid")

    packet = _packet_context(packet_content)
    expected_values = {
        "packet_sha256": _sha256(packet_content),
        "packet_size_bytes": len(packet_content),
        "packet_schema_version": packet["schema_version"],
        "package_id": packet["package_id"],
        "recommendation": packet["recommendation"],
        "reviewer": packet["reviewer"],
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }
    for field, expected in expected_values.items():
        if receipt[field] != expected:
            raise ValueError(f"procurement review receipt {field} is inconsistent")
    if receipt["operational_approval"] is not False:
        raise ValueError(
            "procurement review receipt operational_approval is inconsistent"
        )

    status = receipt["status"]
    if status == REVIEW_RECEIPT_PENDING:
        if any(
            receipt[field] is not None
            for field in ("decision", "rationale", "reviewed_at")
        ):
            raise ValueError("pending procurement review receipt must not record a decision")
    elif status == REVIEW_RECEIPT_COMPLETED:
        if receipt["decision"] not in REVIEW_DECISIONS:
            raise ValueError("procurement review receipt decision is invalid")
        _require_non_empty_text(receipt["rationale"], "rationale")
        if receipt["reviewed_at"] != _normalize_reviewed_at(receipt["reviewed_at"]):
            raise ValueError("procurement review receipt reviewed_at must be canonical UTC")
    else:
        raise ValueError("procurement review receipt status is invalid")

    return {
        "receipt_schema_version": receipt["schema_version"],
        "review_status": status,
        "packet_sha256": receipt["packet_sha256"],
        "package_id": receipt["package_id"],
        "recommendation": receipt["recommendation"],
        "reviewer": receipt["reviewer"],
        "decision": receipt["decision"],
        "reviewed_at": receipt["reviewed_at"],
        "authorization_boundary": receipt["authorization_boundary"],
        "operational_approval": receipt["operational_approval"],
        "receipt_valid": True,
    }


def record_procurement_review_decision(
    receipt: Mapping[str, Any],
    packet_content: bytes,
    *,
    reviewer: str,
    decision: str,
    rationale: str,
    reviewed_at: str,
) -> dict[str, Any]:
    """Return a completed receipt after validating the pending source receipt."""
    current = dict(receipt)
    validate_procurement_review_receipt(current, packet_content)
    if current["status"] != REVIEW_RECEIPT_PENDING:
        raise ValueError("procurement review receipt is already completed")
    reviewer = _require_non_empty_text(reviewer, "reviewer")
    if reviewer != current["reviewer"]:
        raise ValueError("procurement review receipt reviewer does not match the request")
    if decision not in REVIEW_DECISIONS:
        raise ValueError("procurement review receipt decision is invalid")

    completed = {
        **current,
        "status": REVIEW_RECEIPT_COMPLETED,
        "decision": decision,
        "rationale": _require_non_empty_text(rationale, "rationale"),
        "reviewed_at": _normalize_reviewed_at(reviewed_at),
    }
    validate_procurement_review_receipt(completed, packet_content)
    return completed

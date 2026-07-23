"""Canonical, non-authorizing reviewer identity attestations for project reviews."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


REVIEWER_ATTESTATION_SCHEMA_VERSION = "decisiondoc.procurement_reviewer_attestation.v1"
REVIEWER_ATTESTATION_FIELD_ORDER = (
    "schema_version",
    "tenant_id",
    "project_id",
    "packet_sha256",
    "completed_receipt_sha256",
    "decision",
    "reviewed_at",
    "reviewer",
    "authorization_boundary",
    "approval_granted",
    "operational_approval",
    "bid_submission_authorized",
    "legal_commitment_authorized",
    "contractual_commitment_authorized",
)
REVIEWER_PRINCIPAL_FIELD_ORDER = ("user_id", "username", "role")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_attestation_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )


def attestation_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_attestation_bytes(value)).hexdigest()


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"procurement reviewer attestation {field} is invalid")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"procurement reviewer attestation {field} is invalid")
    return value


def _require_reviewed_at(value: object) -> str:
    reviewed_at = _require_text(value, "reviewed_at")
    try:
        parsed = datetime.fromisoformat(
            reviewed_at.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "procurement reviewer attestation reviewed_at is invalid"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(
            "procurement reviewer attestation reviewed_at must use UTC"
        )
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    if reviewed_at != canonical:
        raise ValueError(
            "procurement reviewer attestation reviewed_at must be canonical UTC"
        )
    return reviewed_at


def build_procurement_reviewer_attestation(
    *,
    tenant_id: str,
    project_id: str,
    packet_sha256: str,
    completed_receipt_sha256: str,
    decision: str,
    reviewed_at: str,
    reviewer_user_id: str,
    reviewer_username: str,
    reviewer_role: str,
) -> dict[str, Any]:
    """Bind a completed receipt to the authenticated reviewer principal only."""
    attestation = {
        "schema_version": REVIEWER_ATTESTATION_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "packet_sha256": packet_sha256,
        "completed_receipt_sha256": completed_receipt_sha256,
        "decision": decision,
        "reviewed_at": reviewed_at,
        "reviewer": {
            "user_id": reviewer_user_id,
            "username": reviewer_username,
            "role": reviewer_role,
        },
        "authorization_boundary": "explicit",
        "approval_granted": False,
        "operational_approval": False,
        "bid_submission_authorized": False,
        "legal_commitment_authorized": False,
        "contractual_commitment_authorized": False,
    }
    validate_procurement_reviewer_attestation(attestation)
    return attestation


def validate_procurement_reviewer_attestation(
    value: object,
    *,
    expected_tenant_id: str | None = None,
    expected_project_id: str | None = None,
    expected_packet_sha256: str | None = None,
    expected_receipt_sha256: str | None = None,
    expected_decision: str | None = None,
    expected_reviewed_at: str | None = None,
    expected_reviewer_user_id: str | None = None,
) -> dict[str, Any]:
    """Fail closed on unexpected fields, authority claims, or identity drift."""
    if not isinstance(value, dict) or tuple(value) != REVIEWER_ATTESTATION_FIELD_ORDER:
        raise ValueError("procurement reviewer attestation fields are invalid")
    if value["schema_version"] != REVIEWER_ATTESTATION_SCHEMA_VERSION:
        raise ValueError("procurement reviewer attestation schema_version is invalid")
    for field in ("tenant_id", "project_id"):
        _require_text(value[field], field)
    if value["decision"] not in {
        "accepted",
        "changes_requested",
        "rejected",
    }:
        raise ValueError(
            "procurement reviewer attestation decision is invalid"
        )
    _require_reviewed_at(value["reviewed_at"])
    _require_sha256(value["packet_sha256"], "packet_sha256")
    _require_sha256(value["completed_receipt_sha256"], "completed_receipt_sha256")
    reviewer = value["reviewer"]
    if (
        not isinstance(reviewer, dict)
        or tuple(reviewer) != REVIEWER_PRINCIPAL_FIELD_ORDER
    ):
        raise ValueError("procurement reviewer attestation reviewer is invalid")
    if reviewer["role"] not in {"admin", "member"}:
        raise ValueError("procurement reviewer attestation reviewer role is invalid")
    _require_text(reviewer["user_id"], "reviewer.user_id")
    _require_text(reviewer["username"], "reviewer.username")
    if value["authorization_boundary"] != "explicit" or any(
        value[field] is not False
        for field in (
            "approval_granted",
            "operational_approval",
            "bid_submission_authorized",
            "legal_commitment_authorized",
            "contractual_commitment_authorized",
        )
    ):
        raise ValueError("procurement reviewer attestation authority is invalid")
    expected = {
        "tenant_id": expected_tenant_id,
        "project_id": expected_project_id,
        "packet_sha256": expected_packet_sha256,
        "completed_receipt_sha256": expected_receipt_sha256,
        "decision": expected_decision,
        "reviewed_at": expected_reviewed_at,
    }
    if any(
        expected_value is not None and value[field] != expected_value
        for field, expected_value in expected.items()
    ) or (
        expected_reviewer_user_id is not None
        and reviewer["user_id"] != expected_reviewer_user_id
    ):
        raise ValueError("procurement reviewer attestation binding is inconsistent")
    return dict(value)

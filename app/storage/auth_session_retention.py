"""Read-only contracts for authentication-session retention review evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any


AUTH_SESSION_RETENTION_DEFAULT_DAYS = 30
AUTH_SESSION_RETENTION_MIN_DAYS = 1
AUTH_SESSION_RETENTION_MAX_DAYS = 3650
AUTH_SESSION_RETENTION_POLICY_DAYS = (30, 90, 180, 365)
RETENTION_COMPARISON_CONTRACT_VERSION = "auth-session-retention-comparison.v1"
RETENTION_REVIEW_HANDOFF_CONTRACT_VERSION = "auth-session-retention-review-handoff.v2"
RETENTION_RECHECK_RECEIPT_CONTRACT_VERSION = "auth-session-retention-recheck-receipt.v1"
RETENTION_RECHECK_VOLATILE_FIELDS = [
    "comparison.generated_at",
    "comparison.policies[*].eligible_before",
]
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class AuthSessionRetentionContractError(ValueError):
    """Raised when review evidence is malformed or outside its tenant boundary."""


def canonical_retention_json_bytes(value: object) -> bytes:
    """Encode a retention contract in the one stable JSON representation."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def retention_sha256(value: object) -> str:
    """Return the canonical JSON SHA-256 used by retention contracts."""
    return hashlib.sha256(canonical_retention_json_bytes(value)).hexdigest()


def build_retention_review_handoff(
    *,
    tenant_id: str,
    retention_days: int,
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """Bind one read-only comparison to its tenant and selected policy."""
    if retention_days not in AUTH_SESSION_RETENTION_POLICY_DAYS:
        raise ValueError(
            "retention_days must be one of "
            f"{', '.join(map(str, AUTH_SESSION_RETENTION_POLICY_DAYS))}"
        )
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("tenant_id must be a non-empty string")

    validate_retention_comparison(comparison)
    return {
        "contract_version": RETENTION_REVIEW_HANDOFF_CONTRACT_VERSION,
        "tenant_id": tenant_id,
        "selected_policy_days": retention_days,
        "comparison": comparison,
        "comparison_sha256": retention_sha256(comparison),
        "review_only": True,
        "policy_change_authorized": False,
        "deletion_authorized": False,
        "scheduler_authorized": False,
        "snapshot_atomic": False,
        "requires_recheck_before_mutation": True,
        "handoff_persisted": False,
    }


def validate_retention_review_handoff(
    handoff: object,
    *,
    expected_tenant_id: str,
    expected_sha256: object,
) -> dict[str, Any]:
    """Validate a v2 review handoff before it can be rechecked."""
    source_handoff_sha256 = _require_sha256(
        expected_sha256,
        field="source_handoff_sha256",
    )
    handoff = _require_exact_object(
        handoff,
        {
            "contract_version",
            "tenant_id",
            "selected_policy_days",
            "comparison",
            "comparison_sha256",
            "review_only",
            "policy_change_authorized",
            "deletion_authorized",
            "scheduler_authorized",
            "snapshot_atomic",
            "requires_recheck_before_mutation",
            "handoff_persisted",
        },
        message="Invalid authentication-session retention review handoff",
    )
    if retention_sha256(handoff) != source_handoff_sha256:
        raise AuthSessionRetentionContractError("source_handoff_sha256 does not match")
    if handoff["contract_version"] != RETENTION_REVIEW_HANDOFF_CONTRACT_VERSION:
        raise AuthSessionRetentionContractError("Unsupported retention review handoff")
    if handoff["tenant_id"] != expected_tenant_id:
        raise AuthSessionRetentionContractError("Retention review handoff tenant mismatch")
    if handoff["selected_policy_days"] not in AUTH_SESSION_RETENTION_POLICY_DAYS:
        raise AuthSessionRetentionContractError("Invalid selected retention policy")
    if (
        handoff["review_only"] is not True
        or handoff["policy_change_authorized"] is not False
        or handoff["deletion_authorized"] is not False
        or handoff["scheduler_authorized"] is not False
        or handoff["snapshot_atomic"] is not False
        or handoff["requires_recheck_before_mutation"] is not True
        or handoff["handoff_persisted"] is not False
    ):
        raise AuthSessionRetentionContractError("Invalid retention review authority")

    comparison = validate_retention_comparison(handoff["comparison"])
    if handoff["comparison_sha256"] != retention_sha256(comparison):
        raise AuthSessionRetentionContractError("Invalid retention comparison SHA-256")
    return handoff


def build_retention_recheck_receipt(
    *,
    source_handoff: dict[str, Any],
    source_handoff_sha256: str,
    current_handoff: dict[str, Any],
) -> dict[str, Any]:
    """Build a read-only receipt comparing two tenant-bound aggregates."""
    source_comparison = validate_retention_comparison(source_handoff["comparison"])
    current_comparison = validate_retention_comparison(current_handoff["comparison"])
    source_fingerprint = retention_aggregate_fingerprint(source_comparison)
    current_fingerprint = retention_aggregate_fingerprint(current_comparison)
    source_fingerprint_sha256 = retention_sha256(source_fingerprint)
    current_fingerprint_sha256 = retention_sha256(current_fingerprint)

    return {
        "contract_version": RETENTION_RECHECK_RECEIPT_CONTRACT_VERSION,
        "source_handoff": source_handoff,
        "source_handoff_sha256": source_handoff_sha256,
        "current_handoff": current_handoff,
        "current_handoff_sha256": retention_sha256(current_handoff),
        "source_aggregate_fingerprint_sha256": source_fingerprint_sha256,
        "current_aggregate_fingerprint_sha256": current_fingerprint_sha256,
        "aggregate_status": (
            "unchanged"
            if source_fingerprint_sha256 == current_fingerprint_sha256
            else "changed"
        ),
        "fingerprint_algorithm": "sha256",
        "volatile_fields_excluded": list(RETENTION_RECHECK_VOLATILE_FIELDS),
        "aggregate_only": True,
        "review_only": True,
        "policy_change_authorized": False,
        "deletion_authorized": False,
        "scheduler_authorized": False,
        "snapshot_atomic": False,
        "requires_recheck_before_mutation": True,
        "recheck_persisted": False,
    }


def retention_aggregate_fingerprint(comparison: object) -> dict[str, Any]:
    """Project every stable aggregate field and omit only inspection timestamps."""
    validated = validate_retention_comparison(comparison)
    return {
        "contract_version": validated["contract_version"],
        "policy_days": list(validated["policy_days"]),
        "inspected_sessions": validated["inspected_sessions"],
        "active_sessions": validated["active_sessions"],
        "policies": [
            {
                "retention_days": policy["retention_days"],
                "eligible_sessions": policy["eligible_sessions"],
                "eligible_by_reason": dict(policy["eligible_by_reason"]),
                "retained_inactive_sessions": policy["retained_inactive_sessions"],
                "oldest_eligible_inactive_at": policy[
                    "oldest_eligible_inactive_at"
                ],
            }
            for policy in validated["policies"]
        ],
        "read_only": validated["read_only"],
        "deletion_authorized": validated["deletion_authorized"],
        "snapshot_atomic": validated["snapshot_atomic"],
        "requires_recheck_before_mutation": validated[
            "requires_recheck_before_mutation"
        ],
    }


def validate_retention_comparison(comparison: object) -> dict[str, Any]:
    """Require the exact aggregate-only comparison schema used by H116."""
    comparison = _require_exact_object(
        comparison,
        {
            "contract_version",
            "generated_at",
            "policy_days",
            "inspected_sessions",
            "active_sessions",
            "policies",
            "read_only",
            "deletion_authorized",
            "snapshot_atomic",
            "requires_recheck_before_mutation",
        },
        message="Invalid authentication-session retention comparison",
    )
    generated_at = _parse_timestamp(comparison["generated_at"], field="generated_at")
    if (
        comparison["contract_version"] != RETENTION_COMPARISON_CONTRACT_VERSION
        or comparison["policy_days"] != list(AUTH_SESSION_RETENTION_POLICY_DAYS)
        or comparison["read_only"] is not True
        or comparison["deletion_authorized"] is not False
        or comparison["snapshot_atomic"] is not False
        or comparison["requires_recheck_before_mutation"] is not True
    ):
        raise AuthSessionRetentionContractError("Invalid retention comparison authority")

    inspected_sessions = _require_non_negative_integer(
        comparison["inspected_sessions"], field="inspected_sessions"
    )
    active_sessions = _require_non_negative_integer(
        comparison["active_sessions"], field="active_sessions"
    )
    if active_sessions > inspected_sessions:
        raise AuthSessionRetentionContractError("Invalid retention comparison counts")

    policies = comparison["policies"]
    if not isinstance(policies, list) or len(policies) != len(
        AUTH_SESSION_RETENTION_POLICY_DAYS
    ):
        raise AuthSessionRetentionContractError("Invalid retention comparison policies")

    previous_eligible = inspected_sessions
    previous_retained = 0
    for retention_days, policy in zip(
        AUTH_SESSION_RETENTION_POLICY_DAYS,
        policies,
        strict=True,
    ):
        policy = _require_exact_object(
            policy,
            {
                "retention_days",
                "eligible_before",
                "eligible_sessions",
                "eligible_by_reason",
                "retained_inactive_sessions",
                "oldest_eligible_inactive_at",
            },
            message="Invalid retention comparison policy",
        )
        eligible_by_reason = _require_exact_object(
            policy["eligible_by_reason"],
            {"expired", "revoked"},
            message="Invalid retention comparison reason counts",
        )
        eligible_before = _parse_timestamp(
            policy["eligible_before"], field="eligible_before"
        )
        eligible_sessions = _require_non_negative_integer(
            policy["eligible_sessions"], field="eligible_sessions"
        )
        expired_sessions = _require_non_negative_integer(
            eligible_by_reason["expired"], field="expired"
        )
        revoked_sessions = _require_non_negative_integer(
            eligible_by_reason["revoked"], field="revoked"
        )
        retained_sessions = _require_non_negative_integer(
            policy["retained_inactive_sessions"], field="retained_inactive_sessions"
        )
        if (
            policy["retention_days"] != retention_days
            or eligible_before != generated_at - timedelta(days=retention_days)
            or eligible_sessions != expired_sessions + revoked_sessions
            or inspected_sessions != active_sessions + eligible_sessions + retained_sessions
            or eligible_sessions > previous_eligible
            or retained_sessions < previous_retained
        ):
            raise AuthSessionRetentionContractError("Invalid retention comparison policy")

        oldest_eligible = policy["oldest_eligible_inactive_at"]
        if eligible_sessions == 0:
            if oldest_eligible is not None:
                raise AuthSessionRetentionContractError("Invalid eligible session timestamp")
        else:
            oldest_at = _parse_timestamp(
                oldest_eligible, field="oldest_eligible_inactive_at"
            )
            if oldest_at > eligible_before:
                raise AuthSessionRetentionContractError("Invalid eligible session timestamp")
        previous_eligible = eligible_sessions
        previous_retained = retained_sessions
    return comparison


def _require_exact_object(
    value: object,
    expected_keys: set[str],
    *,
    message: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected_keys:
        raise AuthSessionRetentionContractError(message)
    return value


def _require_non_negative_integer(value: object, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise AuthSessionRetentionContractError(f"Invalid {field}")
    return value


def _require_sha256(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256_PATTERN.fullmatch(value):
        raise AuthSessionRetentionContractError(f"Invalid {field}")
    return value


def _parse_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AuthSessionRetentionContractError(f"Invalid {field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthSessionRetentionContractError(f"Invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthSessionRetentionContractError(f"Invalid {field}")
    return parsed.astimezone(timezone.utc)

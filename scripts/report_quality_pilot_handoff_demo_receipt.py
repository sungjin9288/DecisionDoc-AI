"""Define and validate the mock-only Report Quality pilot demo receipt."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Mapping


SCHEMA_VERSION = "decisiondoc.report_quality_pilot_handoff_demo.v1"
ARTIFACT_COUNT = 3
COMPLETED_STAGES = (
    "three_ready_artifacts_created",
    "pilot_preview_confirmed",
    "pilot_package_verified",
    "source_package_imported",
    "simulated_local_review_applied",
    "ready_sync_completed",
    "handoff_finalized",
    "browser_summary_verified",
)
EXCLUDED_EXTERNAL_ACTIONS = (
    "provider_api_execution",
    "aws_runtime_execution",
    "dataset_upload",
    "provider_job_creation",
    "training_execution",
    "model_promotion",
    "production_service_resume",
)
EXPECTED_EXECUTION_MODE = {
    "provider": "mock",
    "storage": "temporary_local",
    "runtime_data_persisted": False,
    "review_evidence": "simulated_demo_input",
    "human_review_claimed": False,
}
EXPECTED_EXTERNAL_ACTIONS = {
    action: False for action in EXCLUDED_EXTERNAL_ACTIONS
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[0-9A-Za-z_]{20,}"),
    re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
TOP_LEVEL_FIELDS = {
    "schema_version",
    "status",
    "generated_at",
    "execution_mode",
    "api_pilot_package",
    "local_review",
    "handoff",
    "completed_stages",
    "external_actions",
}


def _require_object(
    value: Any,
    *,
    field: str,
    expected_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    if set(value) != expected_fields:
        raise ValueError(f"{field} fields drifted: {sorted(value)}")
    return value


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 value")
    return value


def _require_utc_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("generated_at must be a non-empty timestamp")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("generated_at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError("generated_at must use UTC")
    return value


def _require_artifact_ids(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) != ARTIFACT_COUNT:
        raise ValueError(f"{field} must contain exactly three artifact IDs")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field} must contain non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must contain unique artifact IDs")
    return value


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def validate_demo_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a persisted full-chain demo receipt without external actions."""
    if set(payload) != TOP_LEVEL_FIELDS:
        raise ValueError(f"demo receipt fields drifted: {sorted(payload)}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("demo receipt schema_version is unsupported")
    if payload["status"] != "passed":
        raise ValueError("demo receipt status must be passed")
    _require_utc_timestamp(payload["generated_at"])

    execution_mode = _require_object(
        payload["execution_mode"],
        field="execution_mode",
        expected_fields=set(EXPECTED_EXECUTION_MODE),
    )
    if execution_mode != EXPECTED_EXECUTION_MODE:
        raise ValueError("execution_mode must record mock, temporary, simulated execution")

    api_package = _require_object(
        payload["api_pilot_package"],
        field="api_pilot_package",
        expected_fields={
            "artifact_count",
            "ready_artifact_count",
            "ordered_artifact_ids",
            "export_sha256",
            "package_sha256",
            "package_validation_passed",
        },
    )
    if (
        api_package["artifact_count"] != ARTIFACT_COUNT
        or api_package["ready_artifact_count"] != ARTIFACT_COUNT
    ):
        raise ValueError("api_pilot_package must record three ready artifacts")
    artifact_ids = _require_artifact_ids(
        api_package["ordered_artifact_ids"],
        field="api_pilot_package.ordered_artifact_ids",
    )
    _require_sha256(api_package["export_sha256"], field="api_pilot_package.export_sha256")
    _require_sha256(api_package["package_sha256"], field="api_pilot_package.package_sha256")
    if api_package["package_validation_passed"] is not True:
        raise ValueError("api_pilot_package.package_validation_passed must be true")

    local_review = _require_object(
        payload["local_review"],
        field="local_review",
        expected_fields={
            "source_bound",
            "decision_count",
            "ready_decisions",
            "receipt_sha256",
            "simulated",
        },
    )
    if local_review["source_bound"] is not True:
        raise ValueError("local_review must remain source-bound")
    if (
        local_review["decision_count"] != ARTIFACT_COUNT
        or local_review["ready_decisions"] != ARTIFACT_COUNT
    ):
        raise ValueError("local_review must record three ready decisions")
    if local_review["simulated"] is not True:
        raise ValueError("local_review.simulated must be true")
    _require_sha256(local_review["receipt_sha256"], field="local_review.receipt_sha256")

    handoff = _require_object(
        payload["handoff"],
        field="handoff",
        expected_fields={
            "artifact_count",
            "ordered_artifact_ids",
            "package_sha256",
            "browser_summary_sha256",
            "exact_browser_summary_verified",
            "source_bound",
            "training_authorized",
            "temporary_artifacts_retained",
        },
    )
    if handoff["artifact_count"] != ARTIFACT_COUNT:
        raise ValueError("handoff.artifact_count must be three")
    if _require_artifact_ids(
        handoff["ordered_artifact_ids"],
        field="handoff.ordered_artifact_ids",
    ) != artifact_ids:
        raise ValueError("handoff artifact order must match the API pilot package")
    _require_sha256(handoff["package_sha256"], field="handoff.package_sha256")
    _require_sha256(
        handoff["browser_summary_sha256"],
        field="handoff.browser_summary_sha256",
    )
    if handoff["exact_browser_summary_verified"] is not True:
        raise ValueError("handoff exact browser summary must be verified")
    if handoff["source_bound"] is not True:
        raise ValueError("handoff must remain source-bound")
    if handoff["training_authorized"] is not False:
        raise ValueError("handoff must keep training_authorized=false")
    if handoff["temporary_artifacts_retained"] is not False:
        raise ValueError("handoff must not claim retained temporary artifacts")

    if payload["completed_stages"] != list(COMPLETED_STAGES):
        raise ValueError("completed_stages order or membership drifted")
    if payload["external_actions"] != EXPECTED_EXTERNAL_ACTIONS:
        raise ValueError("external_actions must remain false for every excluded action")
    for text in _iter_strings(dict(payload)):
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise ValueError("demo receipt appears to contain a secret value")

    return {
        "artifact_count": ARTIFACT_COUNT,
        "source_bound": True,
        "simulated_review": True,
        "human_review_claimed": False,
        "training_authorized": False,
        "completed_stage_count": len(COMPLETED_STAGES),
    }

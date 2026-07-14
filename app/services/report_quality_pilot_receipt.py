"""Build and validate portable receipts for Report Quality pilot exports."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


RECEIPT_REPORT_TYPE = "report_quality_pilot_export_receipt"
RECEIPT_SCHEMA_VERSION = "decisiondoc_report_quality_pilot_export_receipt.v1"
RECEIPT_HEADER = "X-DecisionDoc-Pilot-Receipt"
RECEIPT_SHA256_HEADER = "X-DecisionDoc-Pilot-Receipt-SHA256"
NO_EXTERNAL_ACTION_KEYS = (
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)
SAFE_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def build_pilot_export_receipt(
    *,
    preview: dict[str, Any],
    tenant_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Describe the exact server-verified JSONL returned by one export request."""
    ordered_artifact_ids = [str(value) for value in preview["ordered_artifact_ids"]]
    export_sha256 = str(preview["export_sha256"])
    return {
        "report_type": RECEIPT_REPORT_TYPE,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "tenant_id": tenant_id,
        "audit_action": "report_quality.pilot_export",
        "export": {
            "filename": str(preview["filename"]),
            "content_type": "application/x-ndjson",
            "sha256": export_sha256,
            "artifact_count": len(ordered_artifact_ids),
            "ordered_artifact_ids": ordered_artifact_ids,
        },
        "preview": {
            "sha256": export_sha256,
            "verified": True,
        },
        "validation": {
            "all_ready_for_learning": True,
            "unique_artifact_ids": True,
            "single_tenant": True,
        },
        "external_action_boundary": {
            key: False for key in NO_EXTERNAL_ACTION_KEYS
        },
    }


def serialize_pilot_export_receipt(receipt: dict[str, Any]) -> bytes:
    """Return stable UTF-8 bytes suitable for a response header and sidecar file."""
    text = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{text}\n".encode("utf-8")


def encode_pilot_export_receipt(receipt_bytes: bytes) -> str:
    """Encode receipt bytes as an ASCII-safe HTTP header value."""
    return base64.urlsafe_b64encode(receipt_bytes).decode("ascii").rstrip("=")


def pilot_export_receipt_sha256(receipt_bytes: bytes) -> str:
    return hashlib.sha256(receipt_bytes).hexdigest()


def parse_pilot_export_receipt(receipt_bytes: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("pilot export receipt must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"pilot export receipt is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("pilot export receipt root must be an object")
    return payload


def validate_pilot_export_receipt(
    receipt: dict[str, Any],
    *,
    export_sha256: str,
    artifact_ids: list[str],
    tenant_id: str,
) -> None:
    """Fail when a receipt does not describe the supplied JSONL export exactly."""
    if receipt.get("report_type") != RECEIPT_REPORT_TYPE:
        raise ValueError("pilot export receipt report_type is unsupported")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ValueError("pilot export receipt schema_version is unsupported")
    request_id = str(receipt.get("request_id") or "").strip()
    if not SAFE_REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("pilot export receipt request_id is invalid")
    try:
        issued_at = datetime.fromisoformat(str(receipt.get("issued_at") or ""))
    except ValueError as exc:
        raise ValueError("pilot export receipt issued_at is invalid") from exc
    if issued_at.tzinfo is None:
        raise ValueError("pilot export receipt issued_at must include a timezone")
    if receipt.get("tenant_id") != tenant_id:
        raise ValueError("pilot export receipt tenant_id does not match the JSONL")
    if receipt.get("audit_action") != "report_quality.pilot_export":
        raise ValueError("pilot export receipt audit_action is invalid")

    export = receipt.get("export")
    if not isinstance(export, dict):
        raise ValueError("pilot export receipt export must be an object")
    if export.get("sha256") != export_sha256:
        raise ValueError("pilot export receipt SHA-256 does not match the JSONL")
    if export.get("ordered_artifact_ids") != artifact_ids:
        raise ValueError("pilot export receipt artifact order does not match the JSONL")
    if export.get("artifact_count") != len(artifact_ids):
        raise ValueError("pilot export receipt artifact_count does not match the JSONL")
    if export.get("content_type") != "application/x-ndjson":
        raise ValueError("pilot export receipt content_type is invalid")
    expected_filename = f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl"
    if export.get("filename") != expected_filename:
        raise ValueError("pilot export receipt filename does not match the JSONL SHA-256")

    preview = receipt.get("preview")
    if not isinstance(preview, dict):
        raise ValueError("pilot export receipt preview must be an object")
    if preview.get("verified") is not True or preview.get("sha256") != export_sha256:
        raise ValueError("pilot export receipt does not prove the reviewed preview")

    validation = receipt.get("validation")
    required_checks = (
        "all_ready_for_learning",
        "unique_artifact_ids",
        "single_tenant",
    )
    if not isinstance(validation, dict) or any(
        validation.get(key) is not True for key in required_checks
    ):
        raise ValueError("pilot export receipt validation contract is incomplete")

    boundary = receipt.get("external_action_boundary")
    expected_boundary = {key: False for key in NO_EXTERNAL_ACTION_KEYS}
    if boundary != expected_boundary:
        raise ValueError("pilot export receipt external action boundary is invalid")

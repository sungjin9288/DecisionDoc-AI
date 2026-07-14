"""Build and verify portable Report Quality pilot review packages."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

from app.services.report_quality_pilot_receipt import (
    RECEIPT_SHA256_HEADER,
    build_pilot_export_receipt,
    parse_pilot_export_receipt,
    pilot_export_receipt_sha256,
    serialize_pilot_export_receipt,
    validate_pilot_export_receipt,
)


PACKAGE_REPORT_TYPE = "report_quality_pilot_review_package"
PACKAGE_SCHEMA_VERSION = "decisiondoc_report_quality_pilot_review_package.v1"
PACKAGE_SHA256_HEADER = "X-DecisionDoc-Pilot-Package-SHA256"
PACKAGE_ENTRY_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
PACKAGE_MANIFEST_NAME = "pilot_package_manifest.json"
MAX_PACKAGE_SIZE_BYTES = 5 * 1024 * 1024
NO_EXTERNAL_ACTION_KEYS = (
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_entry(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=PACKAGE_ENTRY_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        content,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def build_pilot_review_package(
    *,
    jsonl: str,
    receipt_bytes: bytes,
    preview: dict[str, Any],
    tenant_id: str,
) -> tuple[bytes, dict[str, Any]]:
    """Package one server-confirmed pilot export and its receipt in one ZIP."""
    jsonl_bytes = jsonl.encode("utf-8")
    export_sha256 = _sha256(jsonl_bytes)
    if preview.get("export_sha256") != export_sha256:
        raise ValueError("pilot package JSONL does not match the confirmed preview")

    artifact_ids = [str(value) for value in preview.get("ordered_artifact_ids") or []]
    receipt = parse_pilot_export_receipt(receipt_bytes)
    validate_pilot_export_receipt(
        receipt,
        export_sha256=export_sha256,
        artifact_ids=artifact_ids,
        tenant_id=tenant_id,
    )

    jsonl_name = str(preview.get("filename") or "")
    expected_jsonl_name = f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl"
    if jsonl_name != expected_jsonl_name:
        raise ValueError("pilot package JSONL filename does not match its SHA-256")
    receipt_name = f"report_quality_pilot_receipt_{export_sha256[:12]}.json"
    manifest = {
        "report_type": PACKAGE_REPORT_TYPE,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "request_id": receipt["request_id"],
        "artifact_count": len(artifact_ids),
        "ordered_artifact_ids": artifact_ids,
        "export_sha256": export_sha256,
        "entries": [
            {
                "path": jsonl_name,
                "sha256": export_sha256,
                "size_bytes": len(jsonl_bytes),
                "media_type": "application/x-ndjson",
            },
            {
                "path": receipt_name,
                "sha256": _sha256(receipt_bytes),
                "size_bytes": len(receipt_bytes),
                "media_type": "application/json",
            },
        ],
        "external_action_boundary": {
            key: False for key in NO_EXTERNAL_ACTION_KEYS
        },
    }
    entries = {
        jsonl_name: jsonl_bytes,
        receipt_name: receipt_bytes,
        PACKAGE_MANIFEST_NAME: _json_bytes(manifest),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(entries):
            _write_entry(archive, path, entries[path])
    return output.getvalue(), manifest


def prepare_pilot_review_package_delivery(
    *,
    jsonl: str,
    preview: dict[str, Any],
    tenant_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Return a self-verified package and its HTTP delivery metadata."""
    receipt = build_pilot_export_receipt(
        preview=preview,
        tenant_id=tenant_id,
        request_id=request_id,
    )
    receipt_bytes = serialize_pilot_export_receipt(receipt)
    package, manifest = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=receipt_bytes,
        preview=preview,
        tenant_id=tenant_id,
    )
    verify_pilot_review_package(package)
    export_sha256 = str(preview["export_sha256"])
    filename = f"report_quality_pilot_review_package_{export_sha256[:12]}.zip"
    return {
        "content": package,
        "manifest": manifest,
        "filename": filename,
        "headers": {
            "X-DecisionDoc-Pilot-Artifact-Count": str(preview["artifact_count"]),
            "X-DecisionDoc-Pilot-SHA256": export_sha256,
            "X-DecisionDoc-Pilot-Preview-Verified": "true",
            "X-DecisionDoc-Training-Authorized": "false",
            RECEIPT_SHA256_HEADER: pilot_export_receipt_sha256(receipt_bytes),
            PACKAGE_SHA256_HEADER: _sha256(package),
        },
    }


def verify_pilot_review_package(content: bytes) -> dict[str, Any]:
    """Validate package membership, hashes, receipt binding, and boundaries."""
    if len(content) > MAX_PACKAGE_SIZE_BYTES:
        raise ValueError("pilot review package is too large")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise ValueError("pilot review package contains duplicate entries")
            if PACKAGE_MANIFEST_NAME not in names:
                raise ValueError("pilot review package manifest is missing")
            if sum(member.file_size for member in members) > MAX_PACKAGE_SIZE_BYTES:
                raise ValueError("pilot review package uncompressed content is too large")
            entries = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid pilot review package: {exc}") from exc

    try:
        manifest = json.loads(entries[PACKAGE_MANIFEST_NAME])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("pilot review package manifest must be valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("pilot review package manifest must be an object")
    if manifest.get("report_type") != PACKAGE_REPORT_TYPE:
        raise ValueError("pilot review package report_type is unsupported")
    if manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise ValueError("pilot review package schema_version is unsupported")

    declared_entries = manifest.get("entries")
    if not isinstance(declared_entries, list) or len(declared_entries) != 2:
        raise ValueError("pilot review package entries contract is invalid")
    declared_paths = [item.get("path") for item in declared_entries if isinstance(item, dict)]
    if any(not isinstance(path, str) or not path for path in declared_paths):
        raise ValueError("pilot review package entry path is invalid")
    expected_names = sorted([PACKAGE_MANIFEST_NAME, *declared_paths])
    if len(declared_paths) != 2 or sorted(names) != expected_names:
        raise ValueError("pilot review package membership does not match the manifest")

    for item in declared_entries:
        path = str(item["path"])
        entry = entries[path]
        if item.get("sha256") != _sha256(entry):
            raise ValueError(f"pilot review package entry SHA-256 mismatch: {path}")
        if item.get("size_bytes") != len(entry):
            raise ValueError(f"pilot review package entry size mismatch: {path}")

    export_sha256 = str(manifest.get("export_sha256") or "")
    jsonl_name = f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl"
    receipt_name = f"report_quality_pilot_receipt_{export_sha256[:12]}.json"
    if jsonl_name not in entries or receipt_name not in entries:
        raise ValueError("pilot review package filenames do not match the export SHA-256")
    media_types = {item["path"]: item.get("media_type") for item in declared_entries}
    if media_types.get(jsonl_name) != "application/x-ndjson":
        raise ValueError("pilot review package JSONL media_type is invalid")
    if media_types.get(receipt_name) != "application/json":
        raise ValueError("pilot review package receipt media_type is invalid")
    if _sha256(entries[jsonl_name]) != export_sha256:
        raise ValueError("pilot review package JSONL does not match export_sha256")

    try:
        artifacts = [
            json.loads(line)
            for line in entries[jsonl_name].decode("utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("pilot review package JSONL is invalid") from exc
    if any(not isinstance(item, dict) for item in artifacts):
        raise ValueError("pilot review package JSONL entries must be objects")
    artifact_ids = [str(item.get("artifact_id") or "") for item in artifacts]
    if not 3 <= len(artifact_ids) <= 5:
        raise ValueError("pilot review package must contain three to five artifacts")
    if any(not artifact_id for artifact_id in artifact_ids) or len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("pilot review package artifact IDs must be non-empty and unique")
    if artifact_ids != manifest.get("ordered_artifact_ids"):
        raise ValueError("pilot review package artifact order does not match the manifest")
    if len(artifact_ids) != manifest.get("artifact_count"):
        raise ValueError("pilot review package artifact_count does not match the JSONL")

    tenant_id = str(manifest.get("tenant_id") or "")
    if not tenant_id:
        raise ValueError("pilot review package tenant_id is missing")
    for artifact in artifacts:
        workflow_reference = artifact.get("workflow_reference")
        if not isinstance(workflow_reference, dict) or workflow_reference.get("tenant_id") != tenant_id:
            raise ValueError("pilot review package contains an artifact from another tenant")
        boundary = artifact.get("training_boundary")
        if not isinstance(boundary, dict) or any(
            boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS
        ):
            raise ValueError("pilot review package artifact external action boundary is invalid")
    receipt = parse_pilot_export_receipt(entries[receipt_name])
    validate_pilot_export_receipt(
        receipt,
        export_sha256=export_sha256,
        artifact_ids=artifact_ids,
        tenant_id=tenant_id,
    )
    if receipt.get("request_id") != manifest.get("request_id"):
        raise ValueError("pilot review package request_id does not match the receipt")
    expected_boundary = {key: False for key in NO_EXTERNAL_ACTION_KEYS}
    if manifest.get("external_action_boundary") != expected_boundary:
        raise ValueError("pilot review package external action boundary is invalid")

    return manifest


def read_pilot_review_package(content: bytes) -> dict[str, Any]:
    """Return verified package entries without writing them to disk."""
    manifest = verify_pilot_review_package(content)
    export_sha256 = str(manifest["export_sha256"])
    jsonl_name = f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl"
    receipt_name = f"report_quality_pilot_receipt_{export_sha256[:12]}.json"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        manifest_bytes = archive.read(PACKAGE_MANIFEST_NAME)
        jsonl_bytes = archive.read(jsonl_name)
        receipt_bytes = archive.read(receipt_name)
    return {
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "jsonl_name": jsonl_name,
        "jsonl_bytes": jsonl_bytes,
        "receipt_name": receipt_name,
        "receipt_bytes": receipt_bytes,
    }

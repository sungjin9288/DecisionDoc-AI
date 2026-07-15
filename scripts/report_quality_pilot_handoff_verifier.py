"""Verify reviewed Report Quality pilot handoff packages and extract summaries."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.report_quality_learning import validate_correction_artifact
from app.services.report_quality_pilot_receipt import (
    parse_pilot_export_receipt,
    validate_pilot_export_receipt,
)
from scripts.create_report_quality_review_sheet import (
    REVIEW_MANIFEST_REPORT_TYPE,
    REVIEW_MANIFEST_SCHEMA,
)
from scripts.local_write_once import write_bytes_once
from scripts.report_quality_pilot_handoff_summary import (
    HTML_SUMMARY_NAME,
    SUMMARY_NAME,
    verify_report_quality_pilot_handoff_summary,
)
from scripts.report_quality_pilot_pack_provenance import (
    LEGACY_SOURCE_MANIFEST_SCHEMA,
    PREVIOUS_SOURCE_MANIFEST_SCHEMA,
    SOURCE_MANIFEST_NAME,
    SOURCE_MANIFEST_REPORT_TYPE,
    SOURCE_MANIFEST_SCHEMA,
    SOURCE_PACKAGE_MANIFEST_NAME,
    SOURCE_RECEIPT_NAME,
)
from scripts.validate_report_quality_review_decision_receipt import (
    NO_EXTERNAL_ACTION_KEYS,
    RECEIPT_SCHEMA,
)


REPORT_TYPE = "report_quality_pilot_review_handoff"
SCHEMA_VERSION = "decisiondoc_report_quality_pilot_review_handoff.v2"
PREVIOUS_SCHEMA_VERSION = "decisiondoc_report_quality_pilot_review_handoff.v1"
MANIFEST_NAME = "handoff_manifest.json"
MAX_PACKAGE_SIZE_BYTES = 10 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_EVIDENCE_NAMES = (
    SOURCE_MANIFEST_NAME,
    SOURCE_RECEIPT_NAME,
    SOURCE_PACKAGE_MANIFEST_NAME,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be an object")
    return payload


def _read_jsonl(content: bytes) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in content.decode("utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "reviewed pilot JSONL must contain valid UTF-8 JSON objects"
        ) from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("reviewed pilot JSONL must contain at least one JSON object")
    return rows


def _ordered_object_ids(
    value: Any,
    *,
    label: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, dict) for item in value)
    ):
        raise ValueError(f"{label} must be a non-empty list of objects")
    items = value
    artifact_ids = [str(item.get("artifact_id") or "") for item in items]
    if any(not artifact_id for artifact_id in artifact_ids):
        raise ValueError(f"{label} artifact_id values must be non-empty")
    return items, artifact_ids


def _media_type(path: str) -> str:
    if path.endswith(".jsonl"):
        return "application/x-ndjson"
    if path.endswith(".html"):
        return "text/html; charset=utf-8"
    if path.endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "application/json"


def _safe_entry_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("handoff manifest entry path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"handoff manifest entry path is unsafe: {value}")
    return value


def _read_archive(content: bytes) -> dict[str, bytes]:
    if len(content) > MAX_PACKAGE_SIZE_BYTES:
        raise ValueError("reviewed pilot handoff package is too large")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise ValueError("reviewed pilot handoff contains duplicate entries")
            if any(member.is_dir() or member.flag_bits & 0x1 for member in members):
                raise ValueError("reviewed pilot handoff contains an unsupported entry")
            if sum(member.file_size for member in members) > MAX_PACKAGE_SIZE_BYTES:
                raise ValueError("reviewed pilot handoff content is too large")
            for name in names:
                _safe_entry_path(name)
            return {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid reviewed pilot handoff package: {exc}") from exc


def _verify_entry_inventory(
    entries: dict[str, bytes],
    manifest: dict[str, Any],
) -> None:
    declared = manifest.get("entries")
    if not isinstance(declared, list) or not declared:
        raise ValueError("handoff manifest entries must be a non-empty list")
    if any(not isinstance(item, dict) for item in declared):
        raise ValueError("handoff manifest entries must contain objects")
    declared_paths = [_safe_entry_path(item.get("path")) for item in declared]
    if len(declared_paths) != len(set(declared_paths)):
        raise ValueError("handoff manifest entry paths must be unique")
    if sorted(entries) != sorted([MANIFEST_NAME, *declared_paths]):
        raise ValueError(
            "reviewed pilot handoff membership does not match the manifest"
        )
    for item in declared:
        path = str(item["path"])
        content = entries[path]
        if item.get("sha256") != _sha256(content):
            raise ValueError(f"reviewed pilot handoff entry SHA-256 mismatch: {path}")
        if item.get("size_bytes") != len(content):
            raise ValueError(f"reviewed pilot handoff entry size mismatch: {path}")
        if item.get("media_type") != _media_type(path):
            raise ValueError(
                f"reviewed pilot handoff entry media type mismatch: {path}"
            )


def _verify_artifacts(
    entries: dict[str, bytes],
    manifest: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    records = manifest.get("artifacts")
    if not isinstance(records, list) or not 3 <= len(records) <= 5:
        raise ValueError("handoff manifest must describe between 3 and 5 artifacts")
    artifact_ids: list[str] = []
    draft_hashes: dict[str, str] = {}
    draft_payloads: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("handoff manifest artifact records must be objects")
        artifact_id = str(record.get("artifact_id") or "")
        draft_path = _safe_entry_path(record.get("draft_path"))
        draft_sha256 = str(record.get("draft_sha256") or "")
        if not artifact_id or not SHA256_PATTERN.fullmatch(draft_sha256):
            raise ValueError("handoff manifest artifact identity is invalid")
        if draft_path != f"drafts/{artifact_id}.json" or draft_path not in entries:
            raise ValueError(f"handoff draft path is invalid: {artifact_id}")
        if _sha256(entries[draft_path]) != draft_sha256:
            raise ValueError(f"handoff draft SHA-256 mismatch: {artifact_id}")
        payload = _read_json_object(entries[draft_path], label=f"draft {artifact_id}")
        if payload.get("artifact_id") != artifact_id:
            raise ValueError(f"handoff draft artifact_id mismatch: {artifact_id}")
        validation = validate_correction_artifact(payload)
        if (
            validation.get("ok") is not True
            or validation.get("ready_for_learning") is not True
        ):
            raise ValueError(f"handoff draft is not ready_for_learning: {artifact_id}")
        artifact_ids.append(artifact_id)
        draft_hashes[artifact_id] = draft_sha256
        draft_payloads.append(payload)
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("handoff artifact IDs must be unique")
    if artifact_ids != manifest.get("ordered_artifact_ids"):
        raise ValueError("handoff artifact order does not match the manifest")
    if manifest.get("artifact_count") != len(artifact_ids):
        raise ValueError("handoff artifact_count does not match the manifest")

    jsonl = manifest.get("jsonl")
    if not isinstance(jsonl, dict):
        raise ValueError("handoff manifest jsonl must be an object")
    jsonl_path = _safe_entry_path(jsonl.get("path"))
    if jsonl_path != "artifacts/ready_artifacts.jsonl" or jsonl_path not in entries:
        raise ValueError("handoff JSONL path is invalid")
    if jsonl.get("sha256") != _sha256(entries[jsonl_path]):
        raise ValueError("handoff JSONL SHA-256 mismatch")
    if _read_jsonl(entries[jsonl_path]) != draft_payloads:
        raise ValueError("handoff JSONL does not match the packaged drafts")
    return artifact_ids, draft_hashes


def _verify_review_evidence(
    entries: dict[str, bytes],
    manifest: dict[str, Any],
    artifact_ids: list[str],
    draft_hashes: dict[str, str],
) -> dict[str, Any]:
    review = manifest.get("review")
    if not isinstance(review, dict):
        raise ValueError("handoff manifest review must be an object")
    paths = {
        "manifest": _safe_entry_path(review.get("manifest_path")),
        "decision_receipt": _safe_entry_path(review.get("decision_receipt_path")),
        "decision_file": _safe_entry_path(review.get("decision_file_path")),
    }
    for label, path in paths.items():
        if path not in entries:
            raise ValueError(f"handoff {label} entry is missing")
        if review.get(f"{label}_sha256") != _sha256(entries[path]):
            raise ValueError(f"handoff {label} SHA-256 mismatch")

    review_manifest = _read_json_object(
        entries[paths["manifest"]],
        label="human review manifest",
    )
    if review_manifest.get("report_type") != REVIEW_MANIFEST_REPORT_TYPE:
        raise ValueError("human review manifest report_type is invalid")
    if review_manifest.get("schema_version") != REVIEW_MANIFEST_SCHEMA:
        raise ValueError("human review manifest schema_version is invalid")
    pack_binding = manifest.get("pack_binding")
    if review_manifest.get("pack_binding") != pack_binding:
        raise ValueError(
            "human review manifest pack binding does not match the handoff"
        )
    binding_artifacts = (
        pack_binding.get("artifacts") if isinstance(pack_binding, dict) else None
    )
    expected_binding = [
        {"artifact_id": artifact_id, "draft_sha256": draft_hashes[artifact_id]}
        for artifact_id in artifact_ids
    ]
    if binding_artifacts != expected_binding:
        raise ValueError("handoff pack binding does not match the packaged drafts")

    rows, row_ids = _ordered_object_ids(
        review_manifest.get("artifacts"),
        label="human review manifest artifacts",
    )
    if row_ids != artifact_ids:
        raise ValueError("human review manifest artifact order is invalid")
    for row in rows:
        artifact_id = str(row["artifact_id"])
        if (
            row.get("draft_sha256") != draft_hashes[artifact_id]
            or row.get("validation_ok") is not True
            or row.get("ready_for_learning") is not True
            or row.get("accepted_for_learning") is not True
            or row.get("human_review_status") != "accepted"
            or row.get("required_actions") != []
        ):
            raise ValueError(f"human review manifest is not ready: {artifact_id}")
    expected_count = len(artifact_ids)
    counts = review_manifest.get("counts")
    expected_counts = {
        "artifact_count": expected_count,
        "validation_ok_artifacts": expected_count,
        "invalid_artifacts": 0,
        "accepted_artifacts": expected_count,
        "ready_artifacts": expected_count,
        "not_ready_artifacts": 0,
        "pending_artifacts": 0,
        "changes_requested_artifacts": 0,
    }
    if not isinstance(counts, dict) or any(
        counts.get(key) != value for key, value in expected_counts.items()
    ):
        raise ValueError("human review manifest counts are not ready")
    manifest_boundary = review_manifest.get("side_effect_boundary")
    if not isinstance(manifest_boundary, dict) or any(
        manifest_boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS
    ):
        raise ValueError("human review manifest external action boundary is invalid")

    receipt = _read_json_object(
        entries[paths["decision_receipt"]],
        label="review decision receipt",
    )
    if (
        receipt.get("report_type")
        != "report_quality_review_decision_application_receipt"
    ):
        raise ValueError("review decision receipt report_type is invalid")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("review decision receipt schema_version is invalid")
    operation = receipt.get("operation")
    if not isinstance(operation, dict) or any(
        operation.get(key) is not expected
        for key, expected in (
            ("ok", True),
            ("dry_run", False),
            ("require_ready", True),
        )
    ):
        raise ValueError("review decision receipt operation is not ready")
    if operation.get("decision_count") != len(artifact_ids) or operation.get(
        "applied_count"
    ) != len(artifact_ids):
        raise ValueError("review decision receipt counts do not match the handoff")
    if receipt.get("pack_binding_after") != pack_binding:
        raise ValueError(
            "review decision receipt does not match the current pack binding"
        )
    transitions, transition_ids = _ordered_object_ids(
        receipt.get("artifacts"),
        label="review decision receipt artifacts",
    )
    if transition_ids != artifact_ids:
        raise ValueError("review decision receipt artifact order is invalid")
    for transition in transitions:
        artifact_id = str(transition["artifact_id"])
        if (
            transition.get("decision") != "accepted"
            or transition.get("ready_for_learning") is not True
            or transition.get("after_draft_sha256") != draft_hashes[artifact_id]
        ):
            raise ValueError(f"review decision receipt is not accepted: {artifact_id}")
    boundary = receipt.get("side_effect_boundary")
    if not isinstance(boundary, dict) or any(
        boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS
    ):
        raise ValueError("review decision receipt external action boundary is invalid")

    decision_file = _read_json_object(
        entries[paths["decision_file"]],
        label="review decision file",
    )
    decision_record = receipt.get("decision_file")
    if not isinstance(decision_record, dict):
        raise ValueError("review decision receipt decision_file is invalid")
    if decision_record.get("path") != PurePosixPath(paths["decision_file"]).name:
        raise ValueError("review decision file path does not match the receipt")
    if decision_record.get("sha256") != _sha256(entries[paths["decision_file"]]):
        raise ValueError("review decision file SHA-256 does not match the receipt")
    decisions, decision_ids = _ordered_object_ids(
        decision_file.get("decisions"),
        label="review decision file decisions",
    )
    if decision_ids != artifact_ids:
        raise ValueError("review decision file artifact order is invalid")
    if any(item.get("decision") != "accepted" for item in decisions):
        raise ValueError("review decision file contains a non-accepted decision")
    if decision_file.get("training_authorized") is not False:
        raise ValueError("review decision file must keep training_authorized=false")
    if decision_file.get("pack_binding") != receipt.get("pack_binding_before"):
        raise ValueError(
            "review decision file does not match the receipt before binding"
        )
    return review_manifest


def _verify_source_evidence(
    entries: dict[str, bytes],
    manifest: dict[str, Any],
    artifact_ids: list[str],
) -> None:
    source_paths = manifest.get("source_evidence")
    if not isinstance(source_paths, list) or any(
        not isinstance(path, str) for path in source_paths
    ):
        raise ValueError("handoff source_evidence must be a list of paths")
    actual_paths = sorted(path for path in entries if path.startswith("source/"))
    if source_paths != actual_paths:
        raise ValueError("handoff source evidence membership is invalid")
    allowed_paths = {f"source/{name}" for name in SOURCE_EVIDENCE_NAMES}
    if any(path not in allowed_paths for path in actual_paths):
        raise ValueError("handoff contains unsupported source evidence")

    pack_binding = manifest.get("pack_binding")
    source_binding = (
        pack_binding.get("source_manifest") if isinstance(pack_binding, dict) else None
    )
    source_manifest_path = f"source/{SOURCE_MANIFEST_NAME}"
    if source_binding is None:
        if source_manifest_path in entries:
            raise ValueError("unbound handoff must not include a source manifest")
        return
    if not isinstance(source_binding, dict) or source_manifest_path not in entries:
        raise ValueError("source-bound handoff is missing its source manifest")
    if source_binding.get("sha256") != _sha256(entries[source_manifest_path]):
        raise ValueError("source manifest SHA-256 does not match the pack binding")
    source_manifest = _read_json_object(
        entries[source_manifest_path],
        label="source manifest",
    )
    if source_manifest.get("report_type") != SOURCE_MANIFEST_REPORT_TYPE:
        raise ValueError("source manifest report_type is invalid")
    if source_manifest.get("schema_version") not in {
        SOURCE_MANIFEST_SCHEMA,
        PREVIOUS_SOURCE_MANIFEST_SCHEMA,
        LEGACY_SOURCE_MANIFEST_SCHEMA,
    }:
        raise ValueError("source manifest schema_version is invalid")
    source = source_manifest.get("source")
    if not isinstance(source, dict) or source.get("artifact_ids") != artifact_ids:
        raise ValueError("source manifest artifact order does not match the handoff")
    if source.get("tenant_id") != source_binding.get("tenant_id"):
        raise ValueError("source manifest tenant does not match the pack binding")
    if source.get("sha256") != source_binding.get("source_jsonl_sha256"):
        raise ValueError(
            "source manifest JSONL SHA-256 does not match the pack binding"
        )
    source_boundary = source_manifest.get("side_effect_boundary")
    if not isinstance(source_boundary, dict) or any(
        source_boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS
    ):
        raise ValueError("source manifest external action boundary is invalid")

    receipt = source_manifest.get("receipt")
    if receipt is not None:
        receipt_path = f"source/{SOURCE_RECEIPT_NAME}"
        if not isinstance(receipt, dict) or receipt_path not in entries:
            raise ValueError(
                "source-bound handoff is missing its source export receipt"
            )
        if receipt.get("sha256") != _sha256(entries[receipt_path]):
            raise ValueError(
                "source export receipt SHA-256 does not match the source manifest"
            )
        export_receipt = parse_pilot_export_receipt(entries[receipt_path])
        validate_pilot_export_receipt(
            export_receipt,
            export_sha256=str(source["sha256"]),
            artifact_ids=artifact_ids,
            tenant_id=str(source["tenant_id"]),
        )
        if export_receipt.get("request_id") != receipt.get("request_id"):
            raise ValueError(
                "source export receipt request_id does not match the source manifest"
            )
        if export_receipt.get("issued_at") != receipt.get("issued_at"):
            raise ValueError(
                "source export receipt issued_at does not match the source manifest"
            )

    package = source.get("package")
    if isinstance(package, dict) and package.get("manifest_path") is not None:
        package_manifest_path = f"source/{SOURCE_PACKAGE_MANIFEST_NAME}"
        if package_manifest_path not in entries:
            raise ValueError(
                "source-bound handoff is missing its source package manifest"
            )
        if package.get("manifest_sha256") != _sha256(entries[package_manifest_path]):
            raise ValueError(
                "source package manifest SHA-256 does not match the source manifest"
            )


def _validate_report_quality_pilot_handoff(
    content: bytes,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    entries = _read_archive(content)
    if MANIFEST_NAME not in entries:
        raise ValueError("reviewed pilot handoff manifest is missing")
    manifest = _read_json_object(entries[MANIFEST_NAME], label="handoff manifest")
    if manifest.get("report_type") != REPORT_TYPE:
        raise ValueError("handoff manifest report_type is unsupported")
    schema_version = manifest.get("schema_version")
    if schema_version not in {SCHEMA_VERSION, PREVIOUS_SCHEMA_VERSION}:
        raise ValueError("handoff manifest schema_version is unsupported")
    _verify_entry_inventory(entries, manifest)
    artifact_ids, draft_hashes = _verify_artifacts(entries, manifest)
    review_manifest = _verify_review_evidence(
        entries,
        manifest,
        artifact_ids,
        draft_hashes,
    )
    verify_report_quality_pilot_handoff_summary(
        entries,
        manifest,
        review_manifest,
        require_html=schema_version == SCHEMA_VERSION,
    )
    _verify_source_evidence(entries, manifest, artifact_ids)
    expected_boundary = {key: False for key in NO_EXTERNAL_ACTION_KEYS}
    if manifest.get("external_action_boundary") != expected_boundary:
        raise ValueError("handoff external action boundary is invalid")
    result = {
        "report_type": "report_quality_pilot_review_handoff_validation",
        "ok": True,
        "batch_id": manifest.get("batch_id"),
        "artifact_count": len(artifact_ids),
        "ordered_artifact_ids": artifact_ids,
        "jsonl_sha256": manifest["jsonl"]["sha256"],
        "review_manifest_sha256": manifest["review"]["manifest_sha256"],
        "decision_receipt_sha256": manifest["review"]["decision_receipt_sha256"],
        "summary_path": manifest["summary"]["path"],
        "summary_sha256": manifest["summary"]["sha256"],
        "browser_summary_path": (
            manifest["browser_summary"]["path"]
            if isinstance(manifest.get("browser_summary"), dict)
            else None
        ),
        "browser_summary_sha256": (
            manifest["browser_summary"]["sha256"]
            if isinstance(manifest.get("browser_summary"), dict)
            else None
        ),
        "source_bound": (
            manifest.get("pack_binding", {}).get("source_manifest") is not None
        ),
        "training_authorized": False,
    }
    return result, entries


def verify_report_quality_pilot_handoff(content: bytes) -> dict[str, Any]:
    result, _ = _validate_report_quality_pilot_handoff(content)
    return result


def _resolve_summary_output_path(
    output_path: Path,
    *,
    extension: str,
    label: str,
) -> Path:
    expanded = output_path.expanduser()
    if expanded.is_symlink():
        raise ValueError(f"symlink {label} outputs are not allowed")
    resolved = expanded.resolve()
    if resolved.suffix.lower() != extension:
        raise ValueError(f"{label} output must use the {extension} extension")
    if resolved.exists():
        raise ValueError(f"refusing to overwrite existing {label}: {resolved}")
    return resolved


def write_verified_handoff_summary(
    content: bytes,
    *,
    output_path: Path,
) -> dict[str, Any]:
    result, entries = _validate_report_quality_pilot_handoff(content)
    resolved = _resolve_summary_output_path(
        output_path,
        extension=".md",
        label="handoff summary",
    )
    summary_bytes = entries[SUMMARY_NAME]
    write_bytes_once(resolved, summary_bytes, label="handoff summary")
    return {**result, "summary_output_path": str(resolved)}


def write_verified_handoff_browser_summary(
    content: bytes,
    *,
    output_path: Path,
) -> dict[str, Any]:
    result, entries = _validate_report_quality_pilot_handoff(content)
    if result["browser_summary_path"] is None:
        raise ValueError("handoff package does not contain a browser summary")
    resolved = _resolve_summary_output_path(
        output_path,
        extension=".html",
        label="handoff browser summary",
    )
    summary_bytes = entries[HTML_SUMMARY_NAME]
    write_bytes_once(resolved, summary_bytes, label="handoff browser summary")
    return {**result, "browser_summary_output_path": str(resolved)}

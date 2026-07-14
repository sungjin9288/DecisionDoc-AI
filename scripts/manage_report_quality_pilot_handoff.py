#!/usr/bin/env python3
"""Create or verify a portable handoff for one reviewed Report Quality pilot."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402
from app.services.report_quality_pilot_receipt import (  # noqa: E402
    parse_pilot_export_receipt,
    validate_pilot_export_receipt,
)
from scripts.local_write_once import write_bytes_once  # noqa: E402
from scripts.create_report_quality_review_sheet import (  # noqa: E402
    REVIEW_MANIFEST_REPORT_TYPE,
    REVIEW_MANIFEST_SCHEMA,
)
from scripts.report_quality_pilot_pack_provenance import (  # noqa: E402
    LEGACY_SOURCE_MANIFEST_SCHEMA,
    PREVIOUS_SOURCE_MANIFEST_SCHEMA,
    SOURCE_MANIFEST_NAME,
    SOURCE_MANIFEST_REPORT_TYPE,
    SOURCE_MANIFEST_SCHEMA,
    SOURCE_PACKAGE_MANIFEST_NAME,
    SOURCE_RECEIPT_NAME,
    load_pilot_pack,
)
from scripts.report_quality_pilot_review_evidence import (  # noqa: E402
    load_current_decision_receipt,
    load_current_review_manifest,
)
from scripts.report_quality_pilot_handoff_summary import (  # noqa: E402
    SUMMARY_NAME,
    render_report_quality_pilot_handoff_summary,
    verify_report_quality_pilot_handoff_summary,
)
from scripts.sync_report_quality_pilot_pack import (  # noqa: E402
    sync_report_quality_pilot_pack,
)
from scripts.validate_report_quality_review_decision_receipt import (  # noqa: E402
    NO_EXTERNAL_ACTION_KEYS,
    RECEIPT_SCHEMA,
)


REPORT_TYPE = "report_quality_pilot_review_handoff"
SCHEMA_VERSION = "decisiondoc_report_quality_pilot_review_handoff.v1"
MANIFEST_NAME = "handoff_manifest.json"
ENTRY_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
MAX_PACKAGE_SIZE_BYTES = 10 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_EVIDENCE_NAMES = (
    SOURCE_MANIFEST_NAME,
    SOURCE_RECEIPT_NAME,
    SOURCE_PACKAGE_MANIFEST_NAME,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


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
        raise ValueError("reviewed pilot JSONL must contain valid UTF-8 JSON objects") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("reviewed pilot JSONL must contain at least one JSON object")
    return rows


def _ordered_object_ids(value: Any, *, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, dict) for item in value
    ):
        raise ValueError(f"{label} must be a non-empty list of objects")
    items = value
    artifact_ids = [str(item.get("artifact_id") or "") for item in items]
    if any(not artifact_id for artifact_id in artifact_ids):
        raise ValueError(f"{label} artifact_id values must be non-empty")
    return items, artifact_ids


def _write_zip_entry(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=ENTRY_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        content,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def _media_type(path: str) -> str:
    if path.endswith(".jsonl"):
        return "application/x-ndjson"
    if path.endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "application/json"


def _entry_record(path: str, content: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": _sha256(content),
        "size_bytes": len(content),
        "media_type": _media_type(path),
    }


def _safe_entry_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("handoff manifest entry path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"handoff manifest entry path is unsafe: {value}")
    return value


def _regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"symlink {label} files are not allowed")
    if not path.is_file():
        raise ValueError(f"{label} file does not exist: {path}")
    return path.read_bytes()


def _resolve_output_path(output_path: Path | None, *, pack_dir: Path, jsonl_sha256: str) -> Path:
    candidate = output_path or (
        pack_dir / f"report_quality_pilot_review_handoff_{jsonl_sha256[:12]}.zip"
    )
    expanded = candidate.expanduser()
    if expanded.is_symlink():
        raise ValueError("symlink handoff package outputs are not allowed")
    resolved = expanded.resolve()
    if resolved.suffix.lower() != ".zip":
        raise ValueError("handoff package output must use the .zip extension")
    if resolved.exists():
        raise ValueError(f"refusing to overwrite existing handoff package: {resolved}")
    return resolved


def _source_entries(pack_dir: Path, *, source_bound: bool) -> dict[str, bytes]:
    if not source_bound:
        return {}

    manifest_path = pack_dir / SOURCE_MANIFEST_NAME
    manifest_bytes = _regular_file(manifest_path, label="source manifest")
    manifest = _read_json_object(manifest_bytes, label="source manifest")
    required_names = [SOURCE_MANIFEST_NAME]
    if isinstance(manifest.get("receipt"), dict):
        required_names.append(SOURCE_RECEIPT_NAME)
    source = manifest.get("source")
    package = source.get("package") if isinstance(source, dict) else None
    if isinstance(package, dict) and package.get("manifest_path") is not None:
        required_names.append(SOURCE_PACKAGE_MANIFEST_NAME)
    return {
        f"source/{name}": _regular_file(
            pack_dir / name,
            label=f"source evidence {name}",
        )
        for name in required_names
    }


def _build_archive(entries: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    archive_entries = {**entries, MANIFEST_NAME: _json_bytes(manifest)}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(archive_entries):
            _write_zip_entry(archive, path, archive_entries[path])
    return output.getvalue()


def create_report_quality_pilot_handoff(
    *,
    pack_dir: Path,
    jsonl_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    snapshot = load_pilot_pack(resolved_pack_dir)
    review_manifest = load_current_review_manifest(snapshot)
    decision_receipt = load_current_decision_receipt(snapshot)

    expanded_jsonl_path = jsonl_path.expanduser()
    if expanded_jsonl_path.is_symlink():
        raise ValueError("symlink reviewed pilot JSONL files are not allowed")
    resolved_jsonl_path = expanded_jsonl_path.resolve()
    if resolved_jsonl_path.suffix.lower() != ".jsonl":
        raise ValueError("reviewed pilot input must use the .jsonl extension")
    jsonl_bytes = _regular_file(resolved_jsonl_path, label="reviewed pilot JSONL")
    artifacts = _read_jsonl(jsonl_bytes)
    expected_artifacts = [draft.payload for draft in snapshot.drafts]
    if artifacts != expected_artifacts:
        raise ValueError("reviewed pilot JSONL does not match the current draft order and content")
    if not 3 <= len(artifacts) <= 5:
        raise ValueError("reviewed pilot handoff must contain between 3 and 5 artifacts")

    validations = [validate_correction_artifact(artifact) for artifact in artifacts]
    if any(
        validation.get("ok") is not True
        or validation.get("ready_for_learning") is not True
        for validation in validations
    ):
        raise ValueError("reviewed pilot handoff requires valid ready_for_learning artifacts")

    decision_path = Path(str(decision_receipt.validation["decision_path"]))
    decision_bytes = _regular_file(decision_path, label="review decision")
    entries = {
        "artifacts/ready_artifacts.jsonl": jsonl_bytes,
        "review/human_review_manifest.json": review_manifest.content,
        f"review/{decision_receipt.path.name}": decision_receipt.content,
        f"review/{decision_path.name}": decision_bytes,
        **{
            f"drafts/{draft.path.name}": draft.path.read_bytes()
            for draft in snapshot.drafts
        },
        **_source_entries(
            resolved_pack_dir,
            source_bound=snapshot.source_order_applied,
        ),
    }
    artifact_records = [
        {
            "artifact_id": draft.artifact_id,
            "draft_path": f"drafts/{draft.path.name}",
            "draft_sha256": draft.sha256,
        }
        for draft in snapshot.drafts
    ]
    manifest: dict[str, Any] = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "batch_id": resolved_pack_dir.name,
        "artifact_count": len(artifact_records),
        "ordered_artifact_ids": [item["artifact_id"] for item in artifact_records],
        "jsonl": {
            "path": "artifacts/ready_artifacts.jsonl",
            "sha256": _sha256(jsonl_bytes),
        },
        "review": {
            "manifest_path": "review/human_review_manifest.json",
            "manifest_sha256": review_manifest.sha256,
            "decision_receipt_path": f"review/{decision_receipt.path.name}",
            "decision_receipt_sha256": decision_receipt.sha256,
            "decision_file_path": f"review/{decision_path.name}",
            "decision_file_sha256": _sha256(decision_bytes),
        },
        "pack_binding": review_manifest.payload["pack_binding"],
        "artifacts": artifact_records,
        "source_evidence": sorted(
            path for path in entries if path.startswith("source/")
        ),
        "external_action_boundary": {
            key: False for key in NO_EXTERNAL_ACTION_KEYS
        },
    }
    summary_bytes = render_report_quality_pilot_handoff_summary(
        manifest,
        review_manifest.payload,
    ).encode("utf-8")
    entries[SUMMARY_NAME] = summary_bytes
    manifest["summary"] = {
        "path": SUMMARY_NAME,
        "sha256": _sha256(summary_bytes),
    }
    manifest["entries"] = [
        _entry_record(path, content)
        for path, content in sorted(entries.items())
    ]
    package_bytes = _build_archive(entries, manifest)
    verification = verify_report_quality_pilot_handoff(package_bytes)
    resolved_output_path = _resolve_output_path(
        output_path,
        pack_dir=resolved_pack_dir,
        jsonl_sha256=manifest["jsonl"]["sha256"],
    )
    protected_paths = {
        resolved_jsonl_path,
        review_manifest.path.resolve(),
        decision_receipt.path.resolve(),
        decision_path.resolve(),
        *(draft.path.resolve() for draft in snapshot.drafts),
    }
    if resolved_output_path in protected_paths:
        raise ValueError("handoff package must not overwrite source evidence")
    write_bytes_once(
        resolved_output_path,
        package_bytes,
        label="handoff package",
    )
    return {
        "report_type": "report_quality_pilot_review_handoff_created",
        "ok": True,
        "pack_dir": str(resolved_pack_dir),
        "jsonl_path": str(resolved_jsonl_path),
        "output_path": str(resolved_output_path),
        "package_sha256": _sha256(package_bytes),
        "package_size_bytes": len(package_bytes),
        **verification,
        "side_effect_boundary": {
            "reads_local_review_evidence": True,
            "writes_local_handoff_package": True,
            **{key: False for key in NO_EXTERNAL_ACTION_KEYS},
        },
    }


def finalize_report_quality_pilot_handoff(
    *,
    pack_dir: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    with TemporaryDirectory(prefix="decisiondoc-report-quality-handoff-") as temp_dir:
        jsonl_path = Path(temp_dir) / "ready-artifacts.jsonl"
        sync_result = sync_report_quality_pilot_pack(
            pack_dir=resolved_pack_dir,
            output_path=jsonl_path,
            min_records=3,
            require_ready=True,
        )
        if not sync_result["ok"]:
            errors = "; ".join(sync_result["errors"]) or "ready sync did not pass"
            raise ValueError(f"reviewed pilot finalization blocked: {errors}")

        handoff = create_report_quality_pilot_handoff(
            pack_dir=resolved_pack_dir,
            jsonl_path=jsonl_path,
            output_path=output_path,
        )

    result = dict(handoff)
    result.pop("jsonl_path", None)
    return {
        **result,
        "report_type": "report_quality_pilot_review_handoff_finalized",
        "ready_sync": {
            "artifact_count": sync_result["artifact_count"],
            "jsonl_sha256": sync_result["output_sha256"],
            "review_manifest": sync_result["review_manifest"],
            "decision_receipt": sync_result["decision_receipt"],
        },
        "side_effect_boundary": {
            "reads_local_review_evidence": True,
            "writes_temporary_jsonl": True,
            "retains_standalone_jsonl": False,
            "writes_local_handoff_package": True,
            **{key: False for key in NO_EXTERNAL_ACTION_KEYS},
        },
    }


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
        raise ValueError("reviewed pilot handoff membership does not match the manifest")
    for item in declared:
        path = str(item["path"])
        content = entries[path]
        if item.get("sha256") != _sha256(content):
            raise ValueError(f"reviewed pilot handoff entry SHA-256 mismatch: {path}")
        if item.get("size_bytes") != len(content):
            raise ValueError(f"reviewed pilot handoff entry size mismatch: {path}")
        if item.get("media_type") != _media_type(path):
            raise ValueError(f"reviewed pilot handoff entry media type mismatch: {path}")


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
        if validation.get("ok") is not True or validation.get("ready_for_learning") is not True:
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
        raise ValueError("human review manifest pack binding does not match the handoff")
    binding_artifacts = pack_binding.get("artifacts") if isinstance(pack_binding, dict) else None
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
    if not isinstance(counts, dict) or any(counts.get(key) != value for key, value in expected_counts.items()):
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
    if receipt.get("report_type") != "report_quality_review_decision_application_receipt":
        raise ValueError("review decision receipt report_type is invalid")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("review decision receipt schema_version is invalid")
    operation = receipt.get("operation")
    if not isinstance(operation, dict) or any(
        operation.get(key) is not expected
        for key, expected in (("ok", True), ("dry_run", False), ("require_ready", True))
    ):
        raise ValueError("review decision receipt operation is not ready")
    if operation.get("decision_count") != len(artifact_ids) or operation.get("applied_count") != len(artifact_ids):
        raise ValueError("review decision receipt counts do not match the handoff")
    if receipt.get("pack_binding_after") != pack_binding:
        raise ValueError("review decision receipt does not match the current pack binding")
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
    if not isinstance(boundary, dict) or any(boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS):
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
        raise ValueError("review decision file does not match the receipt before binding")
    return review_manifest


def _verify_source_evidence(
    entries: dict[str, bytes],
    manifest: dict[str, Any],
    artifact_ids: list[str],
) -> None:
    source_paths = manifest.get("source_evidence")
    if not isinstance(source_paths, list) or any(not isinstance(path, str) for path in source_paths):
        raise ValueError("handoff source_evidence must be a list of paths")
    actual_paths = sorted(path for path in entries if path.startswith("source/"))
    if source_paths != actual_paths:
        raise ValueError("handoff source evidence membership is invalid")
    allowed_paths = {f"source/{name}" for name in SOURCE_EVIDENCE_NAMES}
    if any(path not in allowed_paths for path in actual_paths):
        raise ValueError("handoff contains unsupported source evidence")

    pack_binding = manifest.get("pack_binding")
    source_binding = pack_binding.get("source_manifest") if isinstance(pack_binding, dict) else None
    source_manifest_path = f"source/{SOURCE_MANIFEST_NAME}"
    if source_binding is None:
        if source_manifest_path in entries:
            raise ValueError("unbound handoff must not include a source manifest")
        return
    if not isinstance(source_binding, dict) or source_manifest_path not in entries:
        raise ValueError("source-bound handoff is missing its source manifest")
    if source_binding.get("sha256") != _sha256(entries[source_manifest_path]):
        raise ValueError("source manifest SHA-256 does not match the pack binding")
    source_manifest = _read_json_object(entries[source_manifest_path], label="source manifest")
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
        raise ValueError("source manifest JSONL SHA-256 does not match the pack binding")
    source_boundary = source_manifest.get("side_effect_boundary")
    if not isinstance(source_boundary, dict) or any(
        source_boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS
    ):
        raise ValueError("source manifest external action boundary is invalid")

    receipt = source_manifest.get("receipt")
    if receipt is not None:
        receipt_path = f"source/{SOURCE_RECEIPT_NAME}"
        if not isinstance(receipt, dict) or receipt_path not in entries:
            raise ValueError("source-bound handoff is missing its source export receipt")
        if receipt.get("sha256") != _sha256(entries[receipt_path]):
            raise ValueError("source export receipt SHA-256 does not match the source manifest")
        export_receipt = parse_pilot_export_receipt(entries[receipt_path])
        validate_pilot_export_receipt(
            export_receipt,
            export_sha256=str(source["sha256"]),
            artifact_ids=artifact_ids,
            tenant_id=str(source["tenant_id"]),
        )
        if export_receipt.get("request_id") != receipt.get("request_id"):
            raise ValueError("source export receipt request_id does not match the source manifest")
        if export_receipt.get("issued_at") != receipt.get("issued_at"):
            raise ValueError("source export receipt issued_at does not match the source manifest")

    package = source.get("package")
    if isinstance(package, dict) and package.get("manifest_path") is not None:
        package_manifest_path = f"source/{SOURCE_PACKAGE_MANIFEST_NAME}"
        if package_manifest_path not in entries:
            raise ValueError("source-bound handoff is missing its source package manifest")
        if package.get("manifest_sha256") != _sha256(entries[package_manifest_path]):
            raise ValueError("source package manifest SHA-256 does not match the source manifest")


def _validate_report_quality_pilot_handoff(content: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    entries = _read_archive(content)
    if MANIFEST_NAME not in entries:
        raise ValueError("reviewed pilot handoff manifest is missing")
    manifest = _read_json_object(entries[MANIFEST_NAME], label="handoff manifest")
    if manifest.get("report_type") != REPORT_TYPE:
        raise ValueError("handoff manifest report_type is unsupported")
    if manifest.get("schema_version") != SCHEMA_VERSION:
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
        "source_bound": manifest.get("pack_binding", {}).get("source_manifest") is not None,
        "training_authorized": False,
    }
    return result, entries


def verify_report_quality_pilot_handoff(content: bytes) -> dict[str, Any]:
    result, _ = _validate_report_quality_pilot_handoff(content)
    return result


def write_verified_handoff_summary(content: bytes, *, output_path: Path) -> dict[str, Any]:
    result, entries = _validate_report_quality_pilot_handoff(content)
    expanded = output_path.expanduser()
    if expanded.is_symlink():
        raise ValueError("symlink handoff summary outputs are not allowed")
    resolved = expanded.resolve()
    if resolved.suffix.lower() != ".md":
        raise ValueError("handoff summary output must use the .md extension")
    if resolved.exists():
        raise ValueError(f"refusing to overwrite existing handoff summary: {resolved}")
    summary_bytes = entries[SUMMARY_NAME]
    write_bytes_once(resolved, summary_bytes, label="handoff summary")
    return {**result, "summary_output_path": str(resolved)}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create_parser = subparsers.add_parser("create", help="Create one reviewed pilot handoff ZIP.")
    create_parser.add_argument("pack_dir", type=Path)
    create_parser.add_argument("--jsonl", type=Path, required=True)
    create_parser.add_argument("--output", type=Path, default=None)
    create_parser.add_argument("--json", action="store_true")

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Validate a reviewed pack and create its handoff ZIP in one step.",
    )
    finalize_parser.add_argument("pack_dir", type=Path)
    finalize_parser.add_argument("--output", type=Path, default=None)
    finalize_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="Verify one reviewed pilot handoff ZIP.")
    verify_parser.add_argument("package", type=Path)
    verify_parser.add_argument("--summary-output", type=Path, default=None)
    verify_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.operation == "create":
            result = create_report_quality_pilot_handoff(
                pack_dir=args.pack_dir,
                jsonl_path=args.jsonl,
                output_path=args.output,
            )
        elif args.operation == "finalize":
            result = finalize_report_quality_pilot_handoff(
                pack_dir=args.pack_dir,
                output_path=args.output,
            )
        else:
            package_path = args.package.expanduser()
            package_bytes = _regular_file(package_path, label="reviewed pilot handoff")
            verification = (
                write_verified_handoff_summary(
                    package_bytes,
                    output_path=args.summary_output,
                )
                if args.summary_output is not None
                else verify_report_quality_pilot_handoff(package_bytes)
            )
            result = {
                "package_path": str(package_path.resolve()),
                "package_sha256": _sha256(package_bytes),
                "package_size_bytes": len(package_bytes),
                **verification,
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({
                "ok": False,
                "operation": args.operation,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PASS reviewed Report Quality pilot handoff verified")
        print(f"artifact_count={result['artifact_count']}")
        print(f"summary_path={result['summary_path']}")
        print(f"summary_sha256={result['summary_sha256']}")
        print(f"jsonl_sha256={result['jsonl_sha256']}")
        print(f"package_sha256={result['package_sha256']}")
        if result.get("output_path"):
            print(f"output_path={result['output_path']}")
        if result.get("summary_output_path"):
            print(f"summary_output_path={result['summary_output_path']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Import DocumentOps reviewer sign-off records into the tenant-local data tree.

This helper copies an existing pending or locally validated completed sign-off
record into DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/.

It never creates reviewer approval, changes sign-off content, starts training,
uploads datasets, calls provider APIs, creates provider jobs, or promotes
models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PHASE21_DIR = Path(__file__).resolve().parents[1] / "phase21_reviewer_signoff"
if str(PHASE21_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE21_DIR))

from validate_signoff_record import PROTECTED_FALSE_BOUNDARY_KEYS, validate_signoff_record  # noqa: E402


TENANT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
FILENAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json")
SAFE_RECORD_ID_PATTERN = re.compile(r"dsr_[A-Za-z0-9_-]{8,80}")
ALLOWED_PENDING_STATUSES = {"pending_manual_signoff"}
ALLOWED_COMPLETED_STATUSES = {"manual_signoff_complete"}
PROTECTED_FALSE_GENERATION_KEYS = {
    "training_execution_started",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "model_promoted",
}


def _fail(message: str, *, code: str = "invalid_import") -> int:
    print(json.dumps({"ok": False, "code": code, "error": message}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 1


def _safe_tenant_id(value: str) -> str:
    tenant_id = value.strip()
    if not TENANT_ID_PATTERN.fullmatch(tenant_id):
        raise ValueError("tenant id must match [A-Za-z0-9_-]{1,64}")
    if tenant_id in {".", ".."}:
        raise ValueError("tenant id must not be a path segment")
    return tenant_id


def _safe_filename(value: str) -> str:
    filename = value.strip()
    if Path(filename).name != filename:
        raise ValueError("output filename must not contain path separators")
    if not FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("output filename must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}.json")
    return filename


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sign-off record must be a JSON object")
    return data


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_id(record: dict[str, Any]) -> str:
    value = record.get("signoff_record_id")
    if not isinstance(value, str) or not SAFE_RECORD_ID_PATTERN.fullmatch(value):
        raise ValueError("signoff_record_id must match dsr_[A-Za-z0-9_-]{8,80}")
    return value


def _default_filename(record: dict[str, Any], *, validation_valid: bool) -> str:
    suffix = "completed_signoff" if validation_valid else "pending_signoff"
    return f"{_record_id(record)}_{suffix}.json"


def _protected_boundary_false(record: dict[str, Any]) -> bool:
    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        return False
    return all(boundary.get(key) is False for key in PROTECTED_FALSE_BOUNDARY_KEYS)


def _generation_side_effects_false(record: dict[str, Any]) -> bool:
    boundary = record.get("generation_boundary")
    if not isinstance(boundary, dict):
        return True
    return all(boundary.get(key, False) is False for key in PROTECTED_FALSE_GENERATION_KEYS)


def _pending_record_valid(record: dict[str, Any]) -> bool:
    if record.get("status") not in ALLOWED_PENDING_STATUSES:
        return False
    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        return False
    if boundary.get("actual_reviewer_approval_recorded") is not False:
        return False
    reviewers = record.get("required_reviewers")
    if not isinstance(reviewers, list):
        return False
    decisions = [item.get("decision") for item in reviewers if isinstance(item, dict)]
    return bool(decisions) and all(value == "pending" for value in decisions)


def _validate_import_record(record: dict[str, Any]) -> dict[str, Any]:
    if not _protected_boundary_false(record):
        raise ValueError("protected signoff_boundary training/provider authorization flags must remain false")
    if not _generation_side_effects_false(record):
        raise ValueError("generation side-effect flags must remain false")

    validation = validate_signoff_record(record)
    status = str(record.get("status") or "")
    if validation["valid"]:
        if status not in ALLOWED_COMPLETED_STATUSES:
            raise ValueError("validated completed records must use status=manual_signoff_complete")
        record_state = "manual_signoff_complete_no_training_authorization"
    elif _pending_record_valid(record):
        record_state = "pending_manual_signoff_no_training_authorization"
    else:
        errors = "; ".join(validation.get("errors") or ["record is neither a valid completed sign-off nor a pending sign-off"])
        raise ValueError(f"record is not importable: {errors}")

    return {
        "validation_valid": bool(validation["valid"]),
        "validation_error_count": int(validation["error_count"]),
        "record_state": record_state,
        "validation_errors": validation.get("errors", []),
    }


def _destination_dir(data_dir: Path, tenant_id: str) -> Path:
    base = data_dir.resolve()
    destination = (base / "tenants" / tenant_id / "trajectory_reviewer_signoffs").resolve()
    if not str(destination).startswith(str(base) + os.sep):
        raise ValueError("destination must stay inside DATA_DIR")
    return destination


def _atomic_copy_bytes(content: bytes, destination: Path, *, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    try:
        with tmp.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, destination)
    finally:
        if tmp.exists():
            tmp.unlink()


def import_record(
    source: Path,
    *,
    data_dir: Path,
    tenant_id: str,
    output_filename: str | None,
    dry_run: bool,
    overwrite: bool,
) -> dict[str, Any]:
    tenant = _safe_tenant_id(tenant_id)
    source_path = source.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"source file not found: {source}")
    if source_path.suffix.lower() != ".json":
        raise ValueError("source file must be .json")

    content = source_path.read_bytes()
    record = _load_json(source_path)
    import_validation = _validate_import_record(record)
    filename = _safe_filename(output_filename) if output_filename else _default_filename(
        record,
        validation_valid=import_validation["validation_valid"],
    )
    destination_directory = _destination_dir(data_dir, tenant)
    destination = (destination_directory / filename).resolve()
    if destination.parent != destination_directory:
        raise ValueError("destination filename escaped the tenant sign-off directory")

    if not dry_run:
        _atomic_copy_bytes(content, destination, overwrite=overwrite)

    return {
        "ok": True,
        "report_type": "document_ops_phase31_reviewer_signoff_import_result",
        "dry_run": dry_run,
        "tenant_id": tenant,
        "source_path": str(source_path),
        "destination_path": str(destination),
        "destination_filename": filename,
        "record_state": import_validation["record_state"],
        "signoff_record_id": _record_id(record),
        "source_sha256": _sha256_bytes(content),
        "copied_sha256": _sha256_bytes(destination.read_bytes()) if destination.exists() and not dry_run else None,
        "validation_valid": import_validation["validation_valid"],
        "validation_error_count": import_validation["validation_error_count"],
        "validation_errors": import_validation["validation_errors"],
        "import_boundary": {
            "actual_reviewer_approval_recorded_by_import": False,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "server_side_generated_approval_record": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "provider_job_polling_authorized": False,
            "model_candidate_emission_authorized": False,
            "model_promotion_authorized": False,
        },
        "side_effect_boundary": {
            "tenant_local_record_copied": not dry_run,
            "model_training_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "provider_job_polled": False,
            "model_candidate_emitted": False,
            "model_promoted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a reviewer sign-off JSON record into tenant-local DATA_DIR.")
    parser.add_argument("source", type=Path, help="Pending or validated completed sign-off JSON record.")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", "data")), help="DecisionDoc DATA_DIR.")
    parser.add_argument("--tenant-id", default="system", help="Tenant id. Must match [A-Za-z0-9_-]{1,64}.")
    parser.add_argument("--output-filename", help="Optional safe destination filename ending in .json.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without copying.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing destination file.")
    args = parser.parse_args(argv)

    try:
        result = import_record(
            args.source,
            data_dir=args.data_dir,
            tenant_id=args.tenant_id,
            output_filename=args.output_filename,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI error path
        return _fail(str(exc))

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

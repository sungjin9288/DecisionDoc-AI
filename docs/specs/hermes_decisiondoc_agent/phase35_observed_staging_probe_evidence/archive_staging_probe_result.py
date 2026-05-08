#!/usr/bin/env python3
"""Archive an observed Phase 34 staging readiness probe result.

This helper validates a probe result JSON and writes a local evidence archive.
It never calls providers, uploads datasets, creates reviewer approvals, starts
training jobs, or writes server-side export artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_REPORT_TYPE = "document_ops_phase34_staging_readiness_probe_result"
ARCHIVE_REPORT_TYPE = "document_ops_phase35_observed_staging_probe_evidence_archive"
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("probe result must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_filename(name: str) -> str:
    if not SAFE_FILENAME_RE.fullmatch(name):
        raise ValueError("output filename must use only letters, numbers, dot, underscore, or dash")
    if name in {".", ".."}:
        raise ValueError("output filename must not be a special path component")
    return name


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _require_false_map(payload: dict[str, Any], field: str, errors: list[str]) -> None:
    value = payload.get(field)
    if not isinstance(value, dict):
        errors.append(f"{field} must be a JSON object")
        return
    for key, flag in value.items():
        if flag is not False:
            errors.append(f"{field}.{key} must remain false")


def _validate_probe_result(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if payload.get("phase") != 34:
        errors.append("phase must be 34")
    if payload.get("status") != "pass":
        errors.append("status must be pass")
    target = payload.get("target")
    if not isinstance(target, dict):
        errors.append("target must be a JSON object")
    else:
        base_url = target.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            errors.append("target.base_url is required")
        if isinstance(base_url, str) and base_url.startswith("fixture://"):
            errors.append("fixture probe results cannot be archived as observed staging evidence")
    checkpoints = payload.get("checkpoints")
    if not isinstance(checkpoints, dict):
        errors.append("checkpoints must be a JSON object")
    else:
        health = checkpoints.get("health")
        summary_auth = checkpoints.get("summary_auth_required")
        summary = checkpoints.get("summary")
        download = checkpoints.get("download")
        if isinstance(health, dict) and health.get("status_code") != 200:
            errors.append("health status_code must be 200")
        if isinstance(summary_auth, dict) and summary_auth.get("passed") is not True:
            errors.append("summary_auth_required.passed must be true")
        if isinstance(summary, dict):
            if summary.get("passed") is not True:
                errors.append("summary.passed must be true")
            if summary.get("record_count", 0) <= 0:
                errors.append("summary.record_count must be greater than zero")
        else:
            errors.append("checkpoints.summary must be a JSON object")
        if isinstance(download, dict):
            if download.get("passed") is not True:
                errors.append("download.passed must be true")
            if download.get("server_file_written") is not False:
                errors.append("download.server_file_written must be false")
        else:
            errors.append("checkpoints.download must be a JSON object")
    readiness = payload.get("readiness")
    if not isinstance(readiness, dict):
        errors.append("readiness must be a JSON object")
    else:
        required_true = [
            "ops_key_required",
            "imported_signoff_visible",
            "json_download_contains_records",
            "download_json_in_memory_or_browser_blob_only",
            "guard_flags_clear",
            "staging_probe_completed",
        ]
        for key in required_true:
            if readiness.get(key) is not True:
                errors.append(f"readiness.{key} must be true")
        required_false = [
            "production_smoke_completed",
            "training_authorized",
            "external_dataset_upload_authorized",
            "provider_fine_tune_api_call_authorized",
            "provider_job_creation_authorized",
            "model_promotion_authorized",
        ]
        for key in required_false:
            if readiness.get(key) is not False:
                errors.append(f"readiness.{key} must be false")
    if payload.get("failures") != []:
        errors.append("failures must be an empty list")
    _require_false_map(payload, "guard_flags", errors)
    _require_false_map(payload, "side_effect_boundary", errors)
    return errors


def _build_archive(
    *,
    source_path: Path,
    source_sha256: str,
    result: dict[str, Any],
    evidence_owner: str,
    notes: str,
) -> dict[str, Any]:
    target = result.get("target") if isinstance(result.get("target"), dict) else {}
    checkpoints = result.get("checkpoints") if isinstance(result.get("checkpoints"), dict) else {}
    readiness = result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
    return {
        "report_type": ARCHIVE_REPORT_TYPE,
        "phase": 35,
        "status": "observed_staging_probe_archived_no_training_authorization",
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "source_probe": {
            "path": str(source_path),
            "sha256": source_sha256,
            "report_type": result.get("report_type"),
            "status": result.get("status"),
            "observed_at": result.get("observed_at"),
        },
        "target": {
            "base_url": target.get("base_url"),
            "tenant_id": target.get("tenant_id"),
            "expected_record_ids": target.get("expected_record_ids", []),
        },
        "checkpoint_summary": {
            "health_status_code": (checkpoints.get("health") or {}).get("status_code")
            if isinstance(checkpoints.get("health"), dict)
            else None,
            "ops_key_required": readiness.get("ops_key_required"),
            "summary_record_count": (checkpoints.get("summary") or {}).get("record_count")
            if isinstance(checkpoints.get("summary"), dict)
            else None,
            "download_record_count": (checkpoints.get("download") or {}).get("record_count")
            if isinstance(checkpoints.get("download"), dict)
            else None,
            "download_server_file_written": (checkpoints.get("download") or {}).get("server_file_written")
            if isinstance(checkpoints.get("download"), dict)
            else None,
            "guard_flags_clear": readiness.get("guard_flags_clear"),
        },
        "readiness": {
            "observed_staging_probe_completed": True,
            "production_smoke_completed": False,
            "training_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "archive_boundary": {
            "actual_reviewer_approval_recorded_by_archive": False,
            "training_execution_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "provider_job_polled": False,
            "model_candidate_emitted": False,
            "model_promoted": False,
            "server_side_generated_approval_record": False,
            "server_side_export_artifact_written": False,
        },
        "evidence_owner": evidence_owner,
        "notes": notes,
        "next_step": "Review observed staging evidence and decide whether to run a separate production smoke; this archive does not authorize model training or promotion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive a passing Phase 34 staging readiness probe result.")
    parser.add_argument("probe_result", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-filename", default="phase35_observed_staging_probe_evidence.json")
    parser.add_argument("--evidence-owner", default="release_owner")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    try:
        output_filename = _safe_filename(args.output_filename)
        result = _load_json(args.probe_result)
        errors = _validate_probe_result(result)
        if errors:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "report_type": "document_ops_phase35_observed_staging_probe_archive_rejected",
                        "errors": errors,
                        "side_effect_boundary": {
                            "archive_written": False,
                            "training_execution_started": False,
                            "external_dataset_uploaded": False,
                            "provider_fine_tune_api_called": False,
                            "provider_job_created": False,
                            "model_promoted": False,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
        archive = _build_archive(
            source_path=args.probe_result,
            source_sha256=_sha256(args.probe_result),
            result=result,
            evidence_owner=args.evidence_owner,
            notes=args.notes,
        )
        destination = args.output_dir / output_filename
        _atomic_write_json(destination, archive)
        print(
            json.dumps(
                {
                    "ok": True,
                    "report_type": "document_ops_phase35_observed_staging_probe_archive_result",
                    "destination_path": str(destination),
                    "source_sha256": archive["source_probe"]["sha256"],
                    "status": archive["status"],
                    "readiness": archive["readiness"],
                    "archive_boundary": archive["archive_boundary"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "report_type": "document_ops_phase35_observed_staging_probe_archive_error",
                    "error": str(exc),
                    "side_effect_boundary": {
                        "archive_written": False,
                        "training_execution_started": False,
                        "external_dataset_uploaded": False,
                        "provider_fine_tune_api_called": False,
                        "provider_job_created": False,
                        "model_promoted": False,
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

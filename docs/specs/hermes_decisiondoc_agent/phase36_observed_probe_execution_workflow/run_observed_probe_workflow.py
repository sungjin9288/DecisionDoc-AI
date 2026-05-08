#!/usr/bin/env python3
"""Phase 36 one-shot wrapper for observed staging probe execution.

This wrapper validates runtime inputs, runs the Phase 34 read-only probe, and
archives a passing result with the Phase 35 helper. It never prints ops keys,
imports sign-off records, uploads datasets, calls provider fine-tune APIs, starts
provider jobs, or promotes models.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_TYPE = "document_ops_phase36_observed_probe_execution_workflow"
PRELIGHT_REPORT_TYPE = "document_ops_phase36_observed_probe_execution_preflight_result"
ROOT = Path(__file__).resolve().parents[4]
PHASE34_PROBE = ROOT / "docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/run_staging_readiness_probe.py"
PHASE35_ARCHIVE = (
    ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/archive_staging_probe_result.py"
)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key] = value
    return values


def _first_value(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _split_record_ids(*values: str | None) -> list[str]:
    ids: list[str] = []
    for value in values:
        if not value:
            continue
        for item in value.replace("\n", ",").split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in ids:
                ids.append(cleaned)
    return ids


def _collect_runtime(args: argparse.Namespace) -> dict[str, Any]:
    file_values: dict[str, str] = {}
    for env_file in args.env_file:
        file_values.update(_parse_env_file(Path(env_file)))
    environ = os.environ
    base_url = _first_value(
        args.base_url,
        environ.get("PHASE36_BASE_URL"),
        environ.get("PHASE35_BASE_URL"),
        environ.get("SMOKE_BASE_URL"),
        file_values.get("PHASE36_BASE_URL"),
        file_values.get("PHASE35_BASE_URL"),
        file_values.get("SMOKE_BASE_URL"),
    )
    ops_key = _first_value(args.ops_key, environ.get("DECISIONDOC_OPS_KEY"), file_values.get("DECISIONDOC_OPS_KEY"))
    tenant_id = _first_value(args.tenant_id, environ.get("PHASE36_TENANT_ID"), file_values.get("PHASE36_TENANT_ID"), "system")
    record_ids = _split_record_ids(
        ",".join(args.expect_record_id),
        environ.get("PHASE36_EXPECT_RECORD_IDS"),
        environ.get("PHASE34_EXPECT_RECORD_IDS"),
        file_values.get("PHASE36_EXPECT_RECORD_IDS"),
        file_values.get("PHASE34_EXPECT_RECORD_IDS"),
    )
    return {
        "base_url": base_url,
        "ops_key": ops_key,
        "ops_key_available": bool(ops_key),
        "tenant_id": tenant_id,
        "expected_record_ids": record_ids,
        "env_files_read": [str(path) for path in args.env_file if Path(path).exists()],
        "env_files_missing": [str(path) for path in args.env_file if not Path(path).exists()],
    }


def _preflight(runtime: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    if not runtime["base_url"]:
        missing.append("base_url")
    if not runtime["ops_key_available"]:
        missing.append("DECISIONDOC_OPS_KEY")
    if not runtime["expected_record_ids"]:
        missing.append("expected_signoff_record_ids")
    return {
        "report_type": PRELIGHT_REPORT_TYPE,
        "phase": 36,
        "status": "ready_for_observed_probe_execution" if not missing else "blocked_missing_runtime_inputs",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "base_url": runtime["base_url"] or None,
            "tenant_id": runtime["tenant_id"],
            "expected_record_ids": runtime["expected_record_ids"],
            "ops_key_available": runtime["ops_key_available"],
            "env_files_read": runtime["env_files_read"],
            "env_files_missing": runtime["env_files_missing"],
        },
        "missing_inputs": missing,
        "readiness": {
            "observed_probe_can_run": not missing,
            "observed_staging_probe_completed": False,
            "observed_staging_evidence_archived": False,
            "production_smoke_completed": False,
            "training_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "guard_flags": {
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "server_side_generated_approval_record": False,
        },
        "side_effect_boundary": {
            "actual_reviewer_approval_recorded_by_workflow": False,
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
    }


def _run_command(command: list[str]) -> tuple[int, dict[str, Any] | None, str, str]:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    parsed: dict[str, Any] | None = None
    try:
        loaded = json.loads(completed.stdout)
        if isinstance(loaded, dict):
            parsed = loaded
    except json.JSONDecodeError:
        parsed = None
    return completed.returncode, parsed, completed.stdout, completed.stderr


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 34 probe and Phase 35 archive as one guarded workflow.")
    parser.add_argument("--env-file", action="append", default=[])
    parser.add_argument("--base-url")
    parser.add_argument("--ops-key")
    parser.add_argument("--tenant-id")
    parser.add_argument("--expect-record-id", action="append", default=[])
    parser.add_argument("--output-dir", default="reports/phase36-observed-probe")
    parser.add_argument("--probe-output-filename", default="phase34-staging-readiness.json")
    parser.add_argument("--archive-output-filename", default="phase35-observed-staging-probe-evidence.json")
    parser.add_argument("--evidence-owner", default="release_owner")
    parser.add_argument("--timeout", default="20")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    runtime = _collect_runtime(args)
    preflight = _preflight(runtime)
    if args.dry_run or preflight["status"] != "ready_for_observed_probe_execution":
        print(json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if preflight["status"] == "ready_for_observed_probe_execution" else 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_output = output_dir / args.probe_output_filename
    archive_output = args.archive_output_filename
    phase34_command = [
        sys.executable,
        str(PHASE34_PROBE),
        "--base-url",
        runtime["base_url"],
        "--ops-key",
        runtime["ops_key"],
        "--tenant-id",
        runtime["tenant_id"],
        "--timeout",
        str(args.timeout),
        "--output",
        str(probe_output),
    ]
    for record_id in runtime["expected_record_ids"]:
        phase34_command.extend(["--expect-record-id", record_id])
    probe_returncode, probe_json, _, probe_stderr = _run_command(phase34_command)
    if probe_returncode != 0:
        result = {
            "report_type": REPORT_TYPE,
            "phase": 36,
            "status": "phase34_probe_failed",
            "preflight": preflight,
            "probe_output_path": str(probe_output),
            "probe_result": probe_json,
            "probe_error": probe_stderr,
            "readiness": {
                "observed_staging_probe_completed": False,
                "observed_staging_evidence_archived": False,
                "production_smoke_completed": False,
                "training_authorized": False,
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "provider_job_creation_authorized": False,
                "model_promotion_authorized": False,
            },
        }
        _write_json(output_dir / "phase36-observed-probe-workflow-result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    phase35_command = [
        sys.executable,
        str(PHASE35_ARCHIVE),
        str(probe_output),
        "--output-dir",
        str(output_dir),
        "--output-filename",
        archive_output,
        "--evidence-owner",
        args.evidence_owner,
    ]
    archive_returncode, archive_json, _, archive_stderr = _run_command(phase35_command)
    result = {
        "report_type": REPORT_TYPE,
        "phase": 36,
        "status": "observed_probe_archived_no_training_authorization" if archive_returncode == 0 else "phase35_archive_failed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "probe_output_path": str(probe_output),
        "archive_output_path": str(output_dir / archive_output),
        "probe_result": probe_json,
        "archive_result": archive_json,
        "archive_error": archive_stderr if archive_returncode else "",
        "readiness": {
            "observed_staging_probe_completed": probe_returncode == 0,
            "observed_staging_evidence_archived": archive_returncode == 0,
            "production_smoke_completed": False,
            "training_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "side_effect_boundary": {
            "local_probe_result_written": probe_returncode == 0,
            "local_archive_written": archive_returncode == 0,
            "actual_reviewer_approval_recorded_by_workflow": False,
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
    }
    _write_json(output_dir / "phase36-observed-probe-workflow-result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if archive_returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

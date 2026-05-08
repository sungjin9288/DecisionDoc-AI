#!/usr/bin/env python3
"""Phase 34 read-only staging readiness probe for DocumentOps reviewer sign-off.

The probe only performs safe GET requests, or evaluates supplied fixture JSON.
It does not import records, write server artifacts, upload datasets, call
provider fine-tune APIs, create provider jobs, or promote models.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


SUMMARY_PATH = "/api/agent/document-ops/trajectories/reviewer-signoff/summary"
DOWNLOAD_PATH = "/api/agent/document-ops/trajectories/reviewer-signoff/summary/download"
OPS_KEY_HEADER = "X-DecisionDoc-Ops-Key"

PROTECTED_FALSE_KEYS = {
    "training_execution_allowed",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "provider_job_started",
    "model_promotion_allowed",
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "model_promotion_authorized",
    "server_file_written",
}


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _build_url(base_url: str, path: str, *, limit: int) -> str:
    base = base_url.rstrip("/")
    query = parse.urlencode({"limit": str(limit)})
    return f"{base}{path}?{query}"


def _http_get_json(url: str, *, ops_key: str | None, timeout: float) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if ops_key:
        headers[OPS_KEY_HEADER] = ops_key
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            parsed = json.loads(body.decode("utf-8")) if body else None
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "content_type": response.headers.get("content-type", ""),
                "content_disposition": response.headers.get("content-disposition", ""),
                "payload": parsed if isinstance(parsed, dict) else None,
            }
    except error.HTTPError as exc:
        body = exc.read()
        parsed: dict[str, Any] | None = None
        try:
            loaded = json.loads(body.decode("utf-8")) if body else None
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = None
        return {
            "ok": False,
            "status_code": exc.code,
            "content_type": exc.headers.get("content-type", ""),
            "content_disposition": exc.headers.get("content-disposition", ""),
            "payload": parsed,
        }
    except Exception as exc:  # pragma: no cover - exercised through CLI result shape.
        return {
            "ok": False,
            "status_code": None,
            "content_type": "",
            "content_disposition": "",
            "payload": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _record_ids(payload: dict[str, Any] | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    records = payload.get("records")
    if records is None and isinstance(payload.get("summary"), dict):
        records = payload["summary"].get("records")
    if not isinstance(records, list):
        return set()
    ids: set[str] = set()
    for item in records:
        if isinstance(item, dict) and isinstance(item.get("signoff_record_id"), str):
            ids.add(item["signoff_record_id"])
    return ids


def _record_count(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0
    if isinstance(payload.get("record_count"), int):
        return int(payload["record_count"])
    summary = payload.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("record_count"), int):
        return int(summary["record_count"])
    return len(_record_ids(payload))


def _guard_violations(payload: dict[str, Any] | None, *, prefix: str = "payload") -> list[str]:
    if not isinstance(payload, dict):
        return [f"{prefix}: missing JSON object"]
    violations: list[str] = []
    guard_flags = payload.get("guard_flags")
    if isinstance(guard_flags, dict):
        for key, value in guard_flags.items():
            if value is not False:
                violations.append(f"{prefix}.guard_flags.{key} must remain false")
    side_effect_boundary = payload.get("side_effect_boundary")
    if isinstance(side_effect_boundary, dict):
        for key, value in side_effect_boundary.items():
            if value is not False:
                violations.append(f"{prefix}.side_effect_boundary.{key} must remain false")
    aggregate = payload.get("aggregate")
    if isinstance(aggregate, dict):
        for key in PROTECTED_FALSE_KEYS:
            if key in aggregate and aggregate[key] is not False:
                violations.append(f"{prefix}.aggregate.{key} must remain false")
    for key in PROTECTED_FALSE_KEYS:
        if key in payload and payload[key] is not False:
            violations.append(f"{prefix}.{key} must remain false")
    summary = payload.get("summary")
    if isinstance(summary, dict):
        violations.extend(_guard_violations(summary, prefix=f"{prefix}.summary"))
    return violations


def _evaluate_probe(
    *,
    base_url: str,
    tenant_id: str,
    expected_record_ids: list[str],
    health_check: dict[str, Any] | None,
    auth_required_check: dict[str, Any],
    summary_check: dict[str, Any],
    download_check: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    expected_ids = set(expected_record_ids)
    summary_payload = summary_check.get("payload")
    download_payload = download_check.get("payload")
    summary_record_ids = _record_ids(summary_payload)
    download_record_ids = _record_ids(download_payload)

    if health_check is not None and health_check.get("status_code") != 200:
        failures.append("health endpoint did not return 200")
    if auth_required_check.get("status_code") not in {401, 403}:
        failures.append("reviewer sign-off summary did not require ops key")
    if summary_check.get("status_code") != 200:
        failures.append("ops-key reviewer sign-off summary did not return 200")
    if download_check.get("status_code") != 200:
        failures.append("ops-key reviewer sign-off JSON download did not return 200")
    if isinstance(summary_payload, dict) and summary_payload.get("report_type") != "document_ops_phase25_signoff_summary_endpoint":
        failures.append("summary report_type is unexpected")
    if isinstance(download_payload, dict) and download_payload.get("report_type") != "document_ops_phase27_reviewer_signoff_summary_export":
        failures.append("download report_type is unexpected")
    if _record_count(summary_payload) <= 0:
        failures.append("summary contains no reviewer sign-off records")
    if expected_ids:
        missing_summary = sorted(expected_ids - summary_record_ids)
        missing_download = sorted(expected_ids - download_record_ids)
        if missing_summary:
            failures.append(f"summary missing expected sign-off record ids: {', '.join(missing_summary)}")
        if missing_download:
            failures.append(f"download JSON missing expected sign-off record ids: {', '.join(missing_download)}")
    if isinstance(download_payload, dict):
        if download_payload.get("server_file_written") is not False:
            failures.append("download payload must keep server_file_written=false")
        if not str(download_check.get("content_type", "application/json")).startswith("application/json"):
            failures.append("download response content-type is not application/json")
    failures.extend(_guard_violations(summary_payload, prefix="summary"))
    failures.extend(_guard_violations(download_payload, prefix="download"))

    return {
        "report_type": "document_ops_phase34_staging_readiness_probe_result",
        "phase": 34,
        "status": "pass" if not failures else "fail",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "target": {
            "base_url": base_url,
            "tenant_id": tenant_id,
            "expected_record_ids": expected_record_ids,
        },
        "checkpoints": {
            "health": health_check,
            "summary_auth_required": {
                "status_code": auth_required_check.get("status_code"),
                "passed": auth_required_check.get("status_code") in {401, 403},
            },
            "summary": {
                "status_code": summary_check.get("status_code"),
                "report_type": summary_payload.get("report_type") if isinstance(summary_payload, dict) else None,
                "record_count": _record_count(summary_payload),
                "observed_record_ids": sorted(summary_record_ids),
                "passed": summary_check.get("status_code") == 200,
            },
            "download": {
                "status_code": download_check.get("status_code"),
                "content_type": download_check.get("content_type", ""),
                "content_disposition": download_check.get("content_disposition", ""),
                "report_type": download_payload.get("report_type") if isinstance(download_payload, dict) else None,
                "record_count": _record_count(download_payload),
                "observed_record_ids": sorted(download_record_ids),
                "server_file_written": download_payload.get("server_file_written") if isinstance(download_payload, dict) else None,
                "passed": download_check.get("status_code") == 200,
            },
        },
        "readiness": {
            "ops_key_required": auth_required_check.get("status_code") in {401, 403},
            "imported_signoff_visible": bool(summary_record_ids) and expected_ids <= summary_record_ids,
            "json_download_contains_records": bool(download_record_ids) and expected_ids <= download_record_ids,
            "download_json_in_memory_or_browser_blob_only": (
                isinstance(download_payload, dict) and download_payload.get("server_file_written") is False
            ),
            "guard_flags_clear": not _guard_violations(summary_payload, prefix="summary")
            and not _guard_violations(download_payload, prefix="download"),
            "staging_probe_completed": not failures,
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
            "actual_reviewer_approval_recorded_by_probe": False,
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
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only Phase 34 DocumentOps staging readiness probe.")
    parser.add_argument("--base-url", help="Base URL such as https://admin.decisiondoc.kr")
    parser.add_argument("--ops-key", help="Value for X-DecisionDoc-Ops-Key")
    parser.add_argument("--tenant-id", default="system")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--expect-record-id", action="append", default=[])
    parser.add_argument("--summary-fixture", help="Evaluate an existing summary JSON object instead of calling HTTP.")
    parser.add_argument("--download-fixture", help="Evaluate an existing download JSON object instead of calling HTTP.")
    parser.add_argument("--auth-required-status", type=int, default=401)
    parser.add_argument("--output", help="Optional local file path for the probe result JSON.")
    args = parser.parse_args()

    summary_fixture = _load_json(args.summary_fixture)
    download_fixture = _load_json(args.download_fixture)
    fixture_mode = summary_fixture is not None or download_fixture is not None
    if fixture_mode and not (summary_fixture and download_fixture):
        parser.error("--summary-fixture and --download-fixture must be provided together")
    if not fixture_mode and (not args.base_url or not args.ops_key):
        parser.error("--base-url and --ops-key are required unless fixture JSON files are supplied")

    base_url = args.base_url or "fixture://phase34"
    if fixture_mode:
        health_check = {"status_code": 200, "fixture": True}
        auth_required_check = {"status_code": args.auth_required_status, "fixture": True}
        summary_check = {
            "status_code": 200,
            "content_type": "application/json",
            "content_disposition": "",
            "payload": summary_fixture,
            "fixture": True,
        }
        download_check = {
            "status_code": 200,
            "content_type": "application/json",
            "content_disposition": 'attachment; filename="reviewer_signoff_summary_fixture.json"',
            "payload": download_fixture,
            "fixture": True,
        }
    else:
        health_check = _http_get_json(f"{base_url.rstrip('/')}/health", ops_key=None, timeout=args.timeout)
        auth_required_check = _http_get_json(
            _build_url(base_url, SUMMARY_PATH, limit=args.limit),
            ops_key=None,
            timeout=args.timeout,
        )
        summary_check = _http_get_json(
            _build_url(base_url, SUMMARY_PATH, limit=args.limit),
            ops_key=args.ops_key,
            timeout=args.timeout,
        )
        download_check = _http_get_json(
            _build_url(base_url, DOWNLOAD_PATH, limit=args.limit),
            ops_key=args.ops_key,
            timeout=args.timeout,
        )

    result = _evaluate_probe(
        base_url=base_url,
        tenant_id=args.tenant_id,
        expected_record_ids=args.expect_record_id,
        health_check=health_check,
        auth_required_check=auth_required_check,
        summary_check=summary_check,
        download_check=download_check,
    )
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

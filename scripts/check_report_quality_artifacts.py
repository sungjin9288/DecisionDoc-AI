#!/usr/bin/env python3
"""Check Report Workflow quality correction artifacts before any training step."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402


DEFAULT_TIMEOUT_SEC = 60.0
DEFAULT_OUTPUT_PATH = Path("tmp/report_quality_correction_artifacts.jsonl")
TRAINING_BOUNDARY_KEYS = (
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)


def _required_value(value: str, *, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise SystemExit(f"Missing required value: {name}")
    return stripped


def _headers(api_key: str, tenant_id: str = "") -> dict[str, str]:
    headers = {"X-DecisionDoc-Api-Key": api_key}
    if tenant_id.strip():
        headers["X-Tenant-ID"] = tenant_id.strip()
    return headers


def _json_object(response: httpx.Response, *, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit(f"{label} returned non-JSON body") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} returned non-object JSON")
    return payload


def _assert_http_status(label: str, response: httpx.Response, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        try:
            body: dict[str, Any] | str = response.json()
        except ValueError:
            body = response.text[:500]
        raise SystemExit(f"{label} expected {expected}, got {response.status_code}: {body}")
    return _json_object(response, label=label) if response.content else {}


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _validate_training_boundary(summary: dict[str, Any]) -> list[str]:
    boundary = summary.get("training_boundary")
    if not isinstance(boundary, dict):
        return ["summary.training_boundary must be an object"]
    issues: list[str] = []
    for key in TRAINING_BOUNDARY_KEYS:
        if boundary.get(key) is not False:
            issues.append(f"summary.training_boundary.{key} must be false")
    return issues


def _validate_jsonl(text: str, *, min_records: int, require_ready: bool) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    results: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(payload, dict):
            errors.append(f"line {line_no}: artifact root must be an object")
            continue
        validation = validate_correction_artifact(payload)
        row = {
            "line": line_no,
            "artifact_id": validation.get("artifact_id"),
            "ok": bool(validation.get("ok")),
            "ready_for_learning": bool(validation.get("ready_for_learning")),
            "errors": list(validation.get("errors") or []),
            "warnings": list(validation.get("warnings") or []),
        }
        results.append(row)
        for warning in row["warnings"]:
            warnings.append(f"line {line_no}: {warning}")

    artifact_count = len(results)
    valid_artifacts = sum(1 for row in results if row["ok"])
    ready_artifacts = sum(1 for row in results if row["ready_for_learning"])
    if artifact_count < min_records:
        errors.append(f"artifact_count {artifact_count} is below min_records {min_records}")
    if require_ready and ready_artifacts != artifact_count:
        errors.append("not all artifacts are ready_for_learning")
    for row in results:
        for error in row["errors"]:
            errors.append(f"line {row['line']}: {error}")

    return {
        "report_type": "report_quality_correction_artifact_remote_check",
        "ok": not errors and valid_artifacts == artifact_count,
        "ready_for_learning": not errors and artifact_count > 0 and ready_artifacts == artifact_count,
        "min_records": min_records,
        "artifact_count": artifact_count,
        "valid_artifacts": valid_artifacts,
        "ready_artifacts": ready_artifacts,
        "not_ready_artifacts": artifact_count - ready_artifacts,
        "errors": errors,
        "warnings": warnings,
        "results": results,
    }


def run_report_quality_artifact_check(
    *,
    base_url: str,
    api_key: str,
    tenant_id: str = "",
    min_records: int = 3,
    limit: int = 200,
    output_path: Path | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    base_url = _required_value(base_url, name="base_url").rstrip("/")
    api_key = _required_value(api_key, name="api_key")
    min_records = max(1, int(min_records or 1))
    limit = max(min_records, min(int(limit or 200), 500))
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_sec)
    headers = _headers(api_key, tenant_id)

    try:
        summary_response = http.get(
            f"{base_url}/report-workflows/learning/correction-artifacts",
            params={"ready_only": "false", "limit": str(limit)},
            headers=headers,
        )
        summary = _assert_http_status("GET /report-workflows/learning/correction-artifacts", summary_response, 200)
        boundary_issues = _validate_training_boundary(summary)
        if boundary_issues:
            raise SystemExit("; ".join(boundary_issues))

        ready_artifacts = int(summary.get("ready_artifacts") or 0)
        total_artifacts = int(summary.get("total_artifacts") or 0)
        if ready_artifacts < min_records:
            raise SystemExit(
                f"ready_artifacts {ready_artifacts} is below min_records {min_records} "
                f"(total_artifacts={total_artifacts})"
            )

        export_response = http.get(
            f"{base_url}/report-workflows/learning/correction-artifacts/export",
            params={"ready_only": "true", "limit": str(limit)},
            headers=headers,
        )
        if export_response.status_code != 200:
            raise SystemExit(
                "GET /report-workflows/learning/correction-artifacts/export "
                f"expected 200, got {export_response.status_code}: {export_response.text[:500]}"
            )
        jsonl_text = export_response.text
        validation = _validate_jsonl(jsonl_text, min_records=min_records, require_ready=True)
        if output_path is not None:
            _write_text_atomic(output_path, jsonl_text)

        if not validation["ok"]:
            raise SystemExit("; ".join(str(item) for item in validation["errors"]))

        return {
            "status": "passed",
            "tenant_id": tenant_id or "system",
            "summary": {
                "total_artifacts": total_artifacts,
                "ready_artifacts": ready_artifacts,
                "not_ready_artifacts": int(summary.get("not_ready_artifacts") or 0),
                "returned": int(summary.get("returned") or 0),
            },
            "validation": validation,
            "output_path": str(output_path) if output_path is not None else "",
            "side_effect_boundary": {
                "downloads_jsonl_for_local_review": True,
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "training_execution_authorized": False,
                "model_promotion_authorized": False,
            },
        }
    finally:
        if owns_client:
            http.close()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and validate ready Report Workflow correction artifact JSONL.",
    )
    parser.add_argument("--base-url", default=_env("SMOKE_BASE_URL") or _env("BASE_URL"))
    parser.add_argument("--api-key", default=_env("SMOKE_API_KEY") or _env("DECISIONDOC_API_KEY"))
    parser.add_argument("--tenant-id", default=_env("SMOKE_TENANT_ID"))
    parser.add_argument("--min-records", type=int, default=3)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--no-write", action="store_true", help="Validate remote export without writing JSONL locally.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = run_report_quality_artifact_check(
        base_url=args.base_url,
        api_key=args.api_key,
        tenant_id=args.tenant_id,
        min_records=args.min_records,
        limit=args.limit,
        output_path=None if args.no_write else args.output,
        timeout_sec=args.timeout_sec,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        validation = result["validation"]
        summary = result["summary"]
        print("PASS report quality correction artifact export check")
        print(f"tenant_id={result['tenant_id']}")
        print(f"total_artifacts={summary['total_artifacts']}")
        print(f"ready_artifacts={summary['ready_artifacts']}")
        print(f"artifact_count={validation['artifact_count']}")
        print(f"min_records={validation['min_records']}")
        print(f"output_path={result['output_path'] or '-'}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

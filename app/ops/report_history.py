from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def get_default_post_deploy_report_dir() -> Path:
    configured = os.getenv("DECISIONDOC_POST_DEPLOY_REPORT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "reports" / "post-deploy"


def load_report_json(path: Path) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Report file not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON report: {resolved}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected JSON payload: {resolved}")
    return payload


def resolve_report_index(report_dir: Path) -> tuple[dict[str, Any], Path]:
    resolved_dir = Path(report_dir).expanduser()
    index_path = resolved_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Report index not found: {index_path}")
    payload = load_report_json(index_path)
    return payload, index_path


def resolve_named_report(report_dir: Path, report_file: str) -> tuple[dict[str, Any], Path]:
    requested = str(report_file or "").strip()
    if not requested:
        raise ValueError("Report file name is required.")
    report_name = Path(requested).name
    if report_name != requested or not report_name.endswith(".json"):
        raise ValueError(f"Invalid report file name: {report_file}")

    index_payload, index_path = resolve_report_index(report_dir)
    allowed_files = {
        str(index_payload.get("latest", "")).strip(),
        str(index_payload.get("latest_report", "")).strip(),
    }
    reports = index_payload.get("reports", [])
    if isinstance(reports, list):
        for entry in reports:
            if isinstance(entry, dict):
                allowed_files.add(str(entry.get("file", "")).strip())
    allowed_files = {item for item in allowed_files if item}
    if report_name not in allowed_files:
        raise FileNotFoundError(f"Report file not listed in index: {report_name}")

    resolved_path = Path(report_dir).expanduser() / report_name
    if not resolved_path.exists():
        raise FileNotFoundError(f"Report file not found: {resolved_path}")
    payload = load_report_json(resolved_path)
    payload.setdefault("report_file", report_name)
    payload.setdefault("report_index_file", str(index_path))
    return payload, resolved_path


def _extract_provider_route_summary(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name", "")).strip() != "health provider routing":
            continue
        summary: dict[str, Any] = {}
        provider_routes = check.get("provider_routes")
        provider_route_checks = check.get("provider_route_checks")
        provider_policy_checks = check.get("provider_policy_checks")
        provider_policy_issues = check.get("provider_policy_issues")
        if isinstance(provider_routes, dict):
            summary["provider_routes"] = {
                key: str(value)
                for key, value in provider_routes.items()
                if str(key).strip() and str(value).strip()
            }
        if isinstance(provider_route_checks, dict):
            summary["provider_route_checks"] = {
                key: str(value)
                for key, value in provider_route_checks.items()
                if str(key).strip() and str(value).strip()
            }
        if isinstance(provider_policy_checks, dict):
            summary["provider_policy_checks"] = {
                key: str(value)
                for key, value in provider_policy_checks.items()
                if str(key).strip() and str(value).strip()
            }
        if isinstance(provider_policy_issues, dict):
            summary["provider_policy_issues"] = {
                key: [str(item) for item in value if str(item).strip()]
                for key, value in provider_policy_issues.items()
                if str(key).strip() and isinstance(value, list)
            }
        return summary
    return {}


def _extract_smoke_failure_summary(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name", "")).strip() != "deployed smoke":
            continue
        summary: dict[str, Any] = {}
        smoke_response_code = str(check.get("smoke_response_code", "")).strip()
        if smoke_response_code:
            summary["smoke_response_code"] = smoke_response_code
        provider_error_code = str(check.get("provider_error_code", "")).strip()
        if provider_error_code:
            summary["provider_error_code"] = provider_error_code
        smoke_message = str(check.get("smoke_message", "")).strip()
        if smoke_message:
            summary["smoke_message"] = smoke_message
        retry_after_seconds = check.get("retry_after_seconds")
        if isinstance(retry_after_seconds, int):
            summary["retry_after_seconds"] = retry_after_seconds
        smoke_exception_type = str(check.get("smoke_exception_type", "")).strip()
        if smoke_exception_type:
            summary["smoke_exception_type"] = smoke_exception_type
        smoke_results = check.get("smoke_results")
        summary["smoke_results_available"] = isinstance(smoke_results, list)
        if isinstance(smoke_results, list):
            normalized_results = [str(item).strip() for item in smoke_results if str(item).strip()]
            if normalized_results:
                summary["smoke_results"] = normalized_results
        return summary
    return {}


def _extract_report_workflow_smoke_summary(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name", "")).strip() != "report workflow smoke":
            continue
        summary: dict[str, Any] = {}
        report_workflow_smoke_results = check.get("report_workflow_smoke_results")
        summary["report_workflow_smoke_results_available"] = isinstance(report_workflow_smoke_results, list)
        if isinstance(report_workflow_smoke_results, list):
            normalized_results = [
                str(item).strip()
                for item in report_workflow_smoke_results
                if str(item).strip()
            ]
            if normalized_results:
                summary["report_workflow_smoke_results"] = normalized_results
        return summary
    return {}


def _apply_extracted_summary_fields(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks")
    has_available_results = False
    has_available_report_workflow_results = False
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_name = str(check.get("name", "")).strip()
            if check_name == "deployed smoke":
                available = isinstance(check.get("smoke_results"), list)
                check.setdefault("smoke_results_available", available)
                has_available_results = has_available_results or available
                continue
            if check_name != "report workflow smoke":
                continue
            available = isinstance(check.get("report_workflow_smoke_results"), list)
            check.setdefault("report_workflow_smoke_results_available", available)
            has_available_report_workflow_results = has_available_report_workflow_results or available
    payload.setdefault("smoke_results_available", has_available_results)
    payload.setdefault("report_workflow_smoke_results_available", has_available_report_workflow_results)
    extracted_summary: dict[str, Any] = {}
    extracted_summary.update(_extract_provider_route_summary(payload))
    extracted_summary.update(_extract_smoke_failure_summary(payload))
    extracted_summary.update(_extract_report_workflow_smoke_summary(payload))
    for key, value in extracted_summary.items():
        payload.setdefault(key, value)
    return payload


def build_post_deploy_reports_payload(*, report_dir: Path, limit: int, latest: bool) -> dict[str, Any]:
    index_payload, index_path = resolve_report_index(report_dir)
    reports = list(index_payload.get("reports", []))
    if not reports:
        raise ValueError(f"No reports listed in index: {index_path}")

    normalized_limit = max(1, int(limit))
    normalized_reports: list[dict[str, Any]] = []
    for entry in reports[:normalized_limit]:
        if not isinstance(entry, dict):
            continue
        normalized_entry = dict(entry)
        normalized_entry.setdefault(
            "smoke_results_available",
            isinstance(normalized_entry.get("smoke_results"), list),
        )
        normalized_entry.setdefault(
            "report_workflow_smoke_results_available",
            isinstance(normalized_entry.get("report_workflow_smoke_results"), list),
        )
        normalized_reports.append(normalized_entry)
    payload: dict[str, Any] = {
        "report_dir": str(Path(report_dir).expanduser()),
        "index_file": str(index_path),
        "latest_report": index_payload.get("latest_report", "-"),
        "updated_at": index_payload.get("updated_at", "-"),
        "reports": normalized_reports,
    }
    if latest:
        latest_path = Path(report_dir).expanduser() / "latest.json"
        latest_payload = _apply_extracted_summary_fields(load_report_json(latest_path))
        payload["latest_details"] = latest_payload
    return payload


def build_post_deploy_report_detail_payload(*, report_dir: Path, report_file: str) -> dict[str, Any]:
    payload, resolved_path = resolve_named_report(report_dir, report_file)
    payload = _apply_extracted_summary_fields(payload)
    return {
        "report_dir": str(Path(report_dir).expanduser()),
        "report_file": payload.get("report_file") or resolved_path.name,
        "report_path": str(resolved_path),
        "details": payload,
    }

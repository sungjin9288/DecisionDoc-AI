#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_report_history_module():
    module_path = REPO_ROOT / "app" / "ops" / "report_history.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_report_history", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_report_history = _load_report_history_module()
_extract_provider_route_summary = _report_history._extract_provider_route_summary
_extract_smoke_failure_summary = _report_history._extract_smoke_failure_summary
build_post_deploy_reports_payload = _report_history.build_post_deploy_reports_payload
get_default_post_deploy_report_dir = _report_history.get_default_post_deploy_report_dir
load_report_json = _report_history.load_report_json


DEFAULT_REPORT_DIR = get_default_post_deploy_report_dir()
DEFAULT_LIMIT = 5


def _format_smoke_failure_summary(entry: dict[str, Any]) -> str | None:
    smoke_response_code = str(entry.get("smoke_response_code", "")).strip()
    provider_error_code = str(entry.get("provider_error_code", "")).strip()
    smoke_message = str(entry.get("smoke_message", "")).strip()
    smoke_exception_type = str(entry.get("smoke_exception_type", "")).strip()
    retry_after_seconds = entry.get("retry_after_seconds")
    parts: list[str] = []
    if smoke_response_code:
        parts.append(f"code={smoke_response_code}")
    if provider_error_code:
        parts.append(f"provider_error_code={provider_error_code}")
    if isinstance(retry_after_seconds, int):
        parts.append(f"retry_after_seconds={retry_after_seconds}")
    if smoke_exception_type:
        parts.append(f"exception={smoke_exception_type}")
    if smoke_message:
        parts.append(f"message={smoke_message}")
    if not parts:
        return None
    return "  smoke_failure: " + " | ".join(parts)


def _print_entry(entry: dict[str, Any]) -> None:
    status = str(entry.get("status", "unknown")).upper()
    finished_at = str(entry.get("finished_at", "-"))
    file_name = str(entry.get("file", "-"))
    base_url = str(entry.get("base_url", "-"))
    skip_smoke = "yes" if entry.get("skip_smoke") else "no"
    print(f"- [{status}] {finished_at}  file={file_name}  base_url={base_url}  skip_smoke={skip_smoke}", flush=True)
    provider_routes = entry.get("provider_routes")
    provider_policy_checks = entry.get("provider_policy_checks")
    if isinstance(provider_routes, dict) and provider_routes:
        print(
            "  provider_routes: "
            f"generation={provider_routes.get('generation', '-')} "
            f"attachment={provider_routes.get('attachment', '-')} "
            f"visual={provider_routes.get('visual', '-')}",
            flush=True,
        )
    if isinstance(provider_policy_checks, dict) and provider_policy_checks:
        print(
            "  provider_policy: "
            f"quality_first={provider_policy_checks.get('quality_first', '-')}",
            flush=True,
        )
    smoke_failure = _format_smoke_failure_summary(entry)
    if smoke_failure:
        print(smoke_failure, flush=True)


def _print_latest_details(report_dir: Path) -> None:
    latest_path = Path(report_dir).expanduser() / "latest.json"
    payload = load_report_json(latest_path)
    extracted_summary: dict[str, Any] = {}
    extracted_summary.update(_extract_provider_route_summary(payload))
    extracted_summary.update(_extract_smoke_failure_summary(payload))
    for key, value in extracted_summary.items():
        payload.setdefault(key, value)
    print("", flush=True)
    print("Latest report details", flush=True)
    print(f"- status={payload.get('status', 'unknown')}", flush=True)
    print(f"- base_url={payload.get('base_url', '-')}", flush=True)
    print(f"- started_at={payload.get('started_at', '-')}", flush=True)
    print(f"- finished_at={payload.get('finished_at', '-')}", flush=True)
    print(f"- skip_smoke={'yes' if payload.get('skip_smoke') else 'no'}", flush=True)
    if payload.get("error"):
        print(f"- error={payload['error']}", flush=True)
    provider_routes = payload.get("provider_routes")
    provider_route_checks = payload.get("provider_route_checks")
    provider_policy_checks = payload.get("provider_policy_checks")
    provider_policy_issues = payload.get("provider_policy_issues")
    if isinstance(provider_routes, dict) and provider_routes:
        print(
            "- provider_routes="
            f"default:{provider_routes.get('default', '-')} "
            f"generation:{provider_routes.get('generation', '-')} "
            f"attachment:{provider_routes.get('attachment', '-')} "
            f"visual:{provider_routes.get('visual', '-')}",
            flush=True,
        )
    if isinstance(provider_route_checks, dict) and provider_route_checks:
        print(
            "- provider_route_checks="
            f"default:{provider_route_checks.get('default', '-')} "
            f"generation:{provider_route_checks.get('generation', '-')} "
            f"attachment:{provider_route_checks.get('attachment', '-')} "
            f"visual:{provider_route_checks.get('visual', '-')}",
            flush=True,
        )
    if isinstance(provider_policy_checks, dict) and provider_policy_checks:
        print(
            "- provider_policy_checks="
            f"quality_first:{provider_policy_checks.get('quality_first', '-')}",
            flush=True,
        )
    if isinstance(provider_policy_issues, dict) and provider_policy_issues.get("quality_first"):
        issues = provider_policy_issues.get("quality_first") or []
        issue_text = " | ".join(str(item) for item in issues if str(item).strip())
        if issue_text:
            print(f"- provider_policy_issues=quality_first:{issue_text}", flush=True)
    smoke_failure = _format_smoke_failure_summary(payload)
    if smoke_failure:
        print(smoke_failure.replace("  ", "- ", 1), flush=True)
    checks = payload.get("checks", [])
    print("Checks", flush=True)
    for check in checks:
        name = check.get("name", "unknown")
        status = check.get("status", "unknown")
        exit_code = check.get("exit_code")
        suffix = f" exit_code={exit_code}" if exit_code is not None else ""
        print(f"- [{status}] {name}{suffix}", flush=True)


def _build_json_payload(*, report_dir: Path, limit: int, latest: bool) -> dict[str, Any]:
    try:
        return build_post_deploy_reports_payload(report_dir=report_dir, limit=limit, latest=latest)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def show_post_deploy_reports(*, report_dir: Path, limit: int, latest: bool, json_output: bool) -> int:
    payload = _build_json_payload(report_dir=report_dir, limit=limit, latest=latest)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        return 0

    latest_report = payload["latest_report"]
    updated_at = payload["updated_at"]

    print(f"Report directory: {Path(report_dir).expanduser()}", flush=True)
    print(f"Index file: {payload['index_file']}", flush=True)
    print(f"Latest report: {latest_report}", flush=True)
    print(f"Updated at: {updated_at}", flush=True)
    print("", flush=True)
    print(f"Recent reports (limit={max(1, int(limit))})", flush=True)
    for entry in payload["reports"]:
        _print_entry(entry)

    if latest:
        _print_latest_details(report_dir)

    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show recent DecisionDoc post-deploy verification reports from the local report history.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory that contains post-deploy report history. Default: reports/post-deploy",
    )
    parser.add_argument(
        "--limit",
        default=DEFAULT_LIMIT,
        type=int,
        help="Number of recent reports to display from index.json. Default: 5",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Also print detailed checks from latest.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON payload instead of human-readable text.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    return show_post_deploy_reports(
        report_dir=Path(args.report_dir),
        limit=int(args.limit),
        latest=bool(args.latest),
        json_output=bool(args.json),
    )


if __name__ == "__main__":
    raise SystemExit(main())

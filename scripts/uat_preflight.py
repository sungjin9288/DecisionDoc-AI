#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib import error, request


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


def _load_post_deploy_check_module():
    module_path = REPO_ROOT / "scripts" / "post_deploy_check.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_post_deploy_check", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_report_history = _load_report_history_module()
_post_deploy_check = _load_post_deploy_check_module()

build_post_deploy_reports_payload = _report_history.build_post_deploy_reports_payload
get_default_post_deploy_report_dir = _report_history.get_default_post_deploy_report_dir
_load_env_file = _post_deploy_check._load_env_file
_resolve_base_url = _post_deploy_check._resolve_base_url

DEFAULT_ENV_FILE = REPO_ROOT / ".env.prod"
DEFAULT_REPORT_DIR = get_default_post_deploy_report_dir()


def _fetch_health_json(base_url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    health_url = f"{base_url.rstrip('/')}/health"
    try:
        with request.urlopen(health_url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(f"Health check failed for {health_url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Health check returned invalid JSON for {health_url}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Health check returned unexpected payload for {health_url}")
    return payload


def _evaluate_check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def build_uat_preflight_payload(*, base_url: str, report_dir: Path) -> dict[str, Any]:
    health_payload = _fetch_health_json(base_url)
    reports_payload = build_post_deploy_reports_payload(report_dir=report_dir, limit=5, latest=True)
    latest_details = reports_payload.get("latest_details") or {}

    health_ok = str(health_payload.get("status", "")).strip().lower() == "ok"
    quality_first = str(
        (health_payload.get("provider_policy_checks") or {}).get("quality_first", "")
    ).strip()
    latest_report = str(reports_payload.get("latest_report", "")).strip()
    latest_status = str(latest_details.get("status", "")).strip().lower()
    latest_smoke_skip = bool(latest_details.get("skip_smoke"))

    checks = [
        _evaluate_check(
            "health",
            health_ok,
            f"status={health_payload.get('status', 'unknown')}",
        ),
        _evaluate_check(
            "quality_first",
            quality_first == "ok",
            f"quality_first={quality_first or 'unknown'}",
        ),
        _evaluate_check(
            "latest_report",
            bool(latest_report),
            f"latest_report={latest_report or 'missing'}",
        ),
        _evaluate_check(
            "latest_report_status",
            latest_status == "passed",
            f"status={latest_status or 'unknown'}",
        ),
        _evaluate_check(
            "latest_report_smoke_mode",
            not latest_smoke_skip,
            f"skip_smoke={'yes' if latest_smoke_skip else 'no'}",
        ),
    ]

    overall_ready = all(check["status"] == "pass" for check in checks)
    return {
        "ready": overall_ready,
        "base_url": base_url.rstrip("/"),
        "health": {
            "status": health_payload.get("status"),
            "provider": health_payload.get("provider"),
            "provider_routes": health_payload.get("provider_routes") or {},
            "provider_policy_checks": health_payload.get("provider_policy_checks") or {},
            "provider_policy_issues": health_payload.get("provider_policy_issues") or {},
        },
        "latest_report": {
            "file": latest_report,
            "status": latest_details.get("status"),
            "skip_smoke": latest_smoke_skip,
            "error": latest_details.get("error", ""),
            "finished_at": latest_details.get("finished_at", ""),
        },
        "checks": checks,
    }


def show_uat_preflight(*, base_url: str, report_dir: Path, json_output: bool) -> int:
    payload = build_uat_preflight_payload(base_url=base_url, report_dir=report_dir)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        return 0 if payload["ready"] else 1

    print(f"UAT preflight target: {payload['base_url']}", flush=True)
    print(f"Overall readiness: {'READY' if payload['ready'] else 'BLOCKED'}", flush=True)
    print("", flush=True)
    print("Checks", flush=True)
    for check in payload["checks"]:
        marker = "PASS" if check["status"] == "pass" else "FAIL"
        print(f"- {marker} {check['name']} ({check['detail']})", flush=True)

    print("", flush=True)
    print("Health summary", flush=True)
    print(f"- provider={payload['health'].get('provider', '-')}", flush=True)
    provider_routes = payload["health"].get("provider_routes") or {}
    if provider_routes:
        print(
            "- provider_routes="
            f"default:{provider_routes.get('default', '-')} "
            f"generation:{provider_routes.get('generation', '-')} "
            f"attachment:{provider_routes.get('attachment', '-')} "
            f"visual:{provider_routes.get('visual', '-')}",
            flush=True,
        )
    provider_policy_checks = payload["health"].get("provider_policy_checks") or {}
    if provider_policy_checks:
        print(
            f"- quality_first={provider_policy_checks.get('quality_first', '-')}",
            flush=True,
        )
    provider_policy_issues = payload["health"].get("provider_policy_issues") or {}
    issues = provider_policy_issues.get("quality_first") or []
    if issues:
        print("- quality_first_issues=" + " | ".join(str(item) for item in issues), flush=True)

    print("", flush=True)
    print("Latest post-deploy", flush=True)
    print(f"- file={payload['latest_report'].get('file', '-')}", flush=True)
    print(f"- status={payload['latest_report'].get('status', '-')}", flush=True)
    print(f"- finished_at={payload['latest_report'].get('finished_at', '-')}", flush=True)
    print(f"- skip_smoke={'yes' if payload['latest_report'].get('skip_smoke') else 'no'}", flush=True)
    if payload["latest_report"].get("error"):
        print(f"- error={payload['latest_report']['error']}", flush=True)

    return 0 if payload["ready"] else 1


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate whether DecisionDoc is ready for business UAT based on /health and latest post-deploy evidence.",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Environment file used to resolve the default base URL. Default: .env.prod",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional explicit base URL. When omitted, ALLOWED_ORIGINS in the env file is used.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory that contains post-deploy reports. Default: reports/post-deploy",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON payload.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    env_values = _load_env_file(Path(args.env_file))
    base_url = _resolve_base_url(str(args.base_url or ""), env_values)
    return show_uat_preflight(
        base_url=base_url,
        report_dir=Path(args.report_dir),
        json_output=bool(args.json),
    )


if __name__ == "__main__":
    raise SystemExit(main())

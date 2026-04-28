#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib import error, request


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.prod"
DEFAULT_COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
DEFAULT_APP_SERVICE = "app"
DEFAULT_NGINX_SERVICE = "nginx"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "post-deploy"
DEFAULT_REPORT_INDEX_LIMIT = 20
REQUIRED_PROVIDER_ROUTE_KEYS = ("default", "generation", "attachment", "visual")
REQUIRED_PROVIDER_CHECK_KEYS = ("provider", "provider_generation", "provider_attachment", "provider_visual")
REQUIRED_PROVIDER_POLICY_KEYS = ("quality_first",)
ALLOWED_PROVIDER_ROUTE_STATUSES = {"ok", "degraded"}
ALLOWED_PROVIDER_POLICY_STATUSES = {"ok", "degraded"}
MAX_CAPTURED_OUTPUT_CHARS = 4000


def _load_env_file(env_file: Path) -> dict[str, str]:
    resolved = Path(env_file).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Env file not found: {resolved}")
    loaded: dict[str, str] = {}
    for lineno, raw_line in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise SystemExit(f"Invalid env file line {lineno}: {resolved}")
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise SystemExit(f"Invalid env file line {lineno}: {resolved}")
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        loaded[normalized_key] = normalized_value
    return loaded


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _resolve_api_key(env_values: dict[str, str]) -> str:
    keys = _split_csv(env_values.get("DECISIONDOC_API_KEYS", ""))
    if keys:
        return keys[0]
    legacy_key = env_values.get("DECISIONDOC_API_KEY", "").strip()
    if legacy_key:
        return legacy_key
    raise SystemExit("Missing runtime API key. Set DECISIONDOC_API_KEYS or DECISIONDOC_API_KEY in the env file.")


def _resolve_smoke_timeout_sec(env_values: dict[str, str]) -> str:
    env_timeout = str(env_values.get("SMOKE_TIMEOUT_SEC", "")).strip()
    if env_timeout:
        return env_timeout
    inherited_timeout = os.getenv("SMOKE_TIMEOUT_SEC", "").strip()
    if inherited_timeout:
        return inherited_timeout
    return "180"


def _resolve_base_url(base_url: str, env_values: dict[str, str]) -> str:
    normalized = str(base_url or "").strip()
    if normalized:
        return normalized.rstrip("/")
    origins = _split_csv(env_values.get("ALLOWED_ORIGINS", ""))
    if origins:
        return origins[0].rstrip("/")
    raise SystemExit("Missing base URL. Pass --base-url or set ALLOWED_ORIGINS in the env file.")


def _append_step(report: dict[str, Any], *, name: str, status: str, **details: Any) -> None:
    report.setdefault("checks", []).append({"name": name, "status": status, **details})


def _tail_output(value: str, *, max_len: int = MAX_CAPTURED_OUTPUT_CHARS) -> str | None:
    text = str(value or "")
    if not text.strip():
        return None
    if len(text) <= max_len:
        return text
    return f"...\n{text[-max_len:]}"


def _replay_captured_output(*, stdout: str, stderr: str) -> None:
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n", flush=True)
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)


def _redact_command_for_report(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    for item in command:
        text = str(item)
        if text.startswith("SMOKE_API_KEY="):
            redacted.append("SMOKE_API_KEY=<redacted>")
        else:
            redacted.append(text)
    return redacted


def _extract_smoke_failure_details(*, stdout: str, stderr: str) -> dict[str, Any]:
    combined = "\n".join(part for part in (stdout, stderr) if str(part or "").strip())
    if not combined.strip():
        return {}

    details: dict[str, Any] = {}
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    failure_line = next((line for line in reversed(lines) if " expected " in line and " got " in line), "")
    target_text = failure_line or combined

    smoke_response_code = re.search(r"\(code=([A-Z_]+)", target_text)
    if smoke_response_code:
        details["smoke_response_code"] = smoke_response_code.group(1)

    smoke_message = re.search(r"message=([^;\n)]+)", target_text)
    if smoke_message:
        details["smoke_message"] = smoke_message.group(1).strip()

    provider_error_code = re.search(r"provider_error_code=([A-Za-z0-9_.-]+)", combined)
    if provider_error_code:
        details["provider_error_code"] = provider_error_code.group(1)

    retry_after_seconds = re.search(r"retry_after_seconds=(\d+)", combined)
    if retry_after_seconds:
        details["retry_after_seconds"] = int(retry_after_seconds.group(1))

    smoke_exception_type = re.search(r"\b((?:httpx|httpcore)\.[A-Za-z]+)\b", combined)
    if smoke_exception_type:
        details["smoke_exception_type"] = smoke_exception_type.group(1)

    if failure_line:
        details["failure_line"] = failure_line

    return details


def _extract_smoke_result_details(*, stdout: str, stderr: str) -> dict[str, Any]:
    results: list[str] = []
    seen: set[str] = set()
    for raw_line in "\n".join(part for part in (stdout, stderr) if str(part or "").strip()).splitlines():
        line = str(raw_line).strip()
        if not line.startswith(("GET /", "POST /")) or "->" not in line:
            continue
        if line in seen:
            continue
        seen.add(line)
        results.append(line)
    if not results:
        return {}
    return {"smoke_results": results, "smoke_results_available": True}


def _extract_report_workflow_smoke_result_details(*, stdout: str, stderr: str) -> dict[str, Any]:
    results: list[str] = []
    seen: set[str] = set()
    for raw_line in "\n".join(part for part in (stdout, stderr) if str(part or "").strip()).splitlines():
        line = str(raw_line).strip()
        if not line.startswith("PASS ") and not line.startswith("Report workflow smoke completed"):
            continue
        if line in seen:
            continue
        seen.add(line)
        results.append(line)
    if not results:
        return {}
    return {
        "report_workflow_smoke_results": results,
        "report_workflow_smoke_results_available": True,
    }


def _build_failure_suffix(details: dict[str, Any]) -> str:
    parts: list[str] = []
    smoke_response_code = str(details.get("smoke_response_code", "")).strip()
    if smoke_response_code:
        parts.append(f"smoke_response_code={smoke_response_code}")
    provider_error_code = str(details.get("provider_error_code", "")).strip()
    if provider_error_code:
        parts.append(f"provider_error_code={provider_error_code}")
    retry_after_seconds = details.get("retry_after_seconds")
    if isinstance(retry_after_seconds, int):
        parts.append(f"retry_after_seconds={retry_after_seconds}")
    smoke_exception_type = str(details.get("smoke_exception_type", "")).strip()
    if smoke_exception_type:
        parts.append(f"smoke_exception_type={smoke_exception_type}")
    return f" ({'; '.join(parts)})" if parts else ""


def _run_command_with_report(
    report: dict[str, Any],
    command: list[str],
    *,
    label: str,
    capture_output: bool = False,
    output_parser: Callable[..., dict[str, Any]] | None = None,
    failure_parser: Callable[..., dict[str, Any]] | None = None,
) -> None:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=capture_output,
        text=capture_output,
    )
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    if capture_output:
        _replay_captured_output(stdout=stdout, stderr=stderr)
    parsed_output = output_parser(stdout=stdout, stderr=stderr) if output_parser is not None else {}

    if completed.returncode != 0:
        step_details: dict[str, Any] = {
            "command": _redact_command_for_report(command),
            "exit_code": completed.returncode,
        }
        stdout_tail = _tail_output(stdout)
        stderr_tail = _tail_output(stderr)
        if stdout_tail is not None:
            step_details["stdout"] = stdout_tail
        if stderr_tail is not None:
            step_details["stderr"] = stderr_tail
        step_details.update(parsed_output)
        parsed_details = failure_parser(stdout=stdout, stderr=stderr) if failure_parser is not None else {}
        step_details.update(parsed_details)
        _append_step(report, name=label, status="failed", **step_details)
        raise SystemExit(f"{label} failed with exit code {completed.returncode}{_build_failure_suffix(parsed_details)}")
    _append_step(
        report,
        name=label,
        status="passed",
        command=_redact_command_for_report(command),
        exit_code=completed.returncode,
        **parsed_output,
    )


def _write_json_report(report_file: Path, payload: dict[str, Any]) -> None:
    resolved = Path(report_file).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temp_path = resolved.with_name(f"{resolved.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, resolved)


def _resolve_report_targets(
    *,
    report_file: Path | None,
    report_dir: Path | None,
    started_at: datetime,
) -> tuple[Path | None, Path | None]:
    if report_file is not None and report_dir is not None:
        raise SystemExit("Use either --report-file or --report-dir, not both.")
    if report_dir is not None:
        resolved_dir = Path(report_dir).expanduser()
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        return resolved_dir / f"post-deploy-{timestamp}.json", resolved_dir / "latest.json"
    if report_file is not None:
        return Path(report_file).expanduser(), None
    return None, None


def _normalize_index_error(value: Any, *, max_len: int = 160) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3].rstrip()}..."


def _extract_provider_route_summary(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name", "")).strip() != "health provider routing":
            continue
        provider_routes = check.get("provider_routes")
        provider_route_checks = check.get("provider_route_checks")
        summary: dict[str, Any] = {}
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
        provider_policy_checks = check.get("provider_policy_checks")
        provider_policy_issues = check.get("provider_policy_issues")
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


def _annotate_smoke_results_availability(payload: dict[str, Any]) -> dict[str, Any]:
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
    return payload


def _build_index_entry(*, report_file: Path, payload: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "file": report_file.name,
        "status": payload.get("status"),
        "base_url": payload.get("base_url"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "skip_smoke": bool(payload.get("skip_smoke")),
    }
    error = _normalize_index_error(payload.get("error"))
    if error:
        entry["error"] = error
    entry["smoke_results_available"] = bool(payload.get("smoke_results_available"))
    entry["report_workflow_smoke_results_available"] = bool(
        payload.get("report_workflow_smoke_results_available")
    )
    entry.update(_extract_provider_route_summary(payload))
    entry.update(_extract_smoke_failure_summary(payload))
    entry.update(_extract_report_workflow_smoke_summary(payload))
    return entry


def _update_report_index(
    *,
    report_file: Path,
    latest_file: Path | None,
    payload: dict[str, Any],
    history_limit: int = DEFAULT_REPORT_INDEX_LIMIT,
) -> None:
    report_dir = report_file.parent
    index_file = report_dir / "index.json"
    index_payload: dict[str, Any] = {
        "updated_at": payload.get("finished_at") or payload.get("started_at"),
        "latest": latest_file.name if latest_file is not None else report_file.name,
        "latest_report": report_file.name,
        "reports": [],
    }
    if index_file.exists():
        try:
            loaded = json.loads(index_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index_payload.update(
                    {
                        "updated_at": loaded.get("updated_at", index_payload["updated_at"]),
                        "latest": loaded.get("latest", index_payload["latest"]),
                        "latest_report": loaded.get("latest_report", index_payload["latest_report"]),
                        "reports": list(loaded.get("reports", [])),
                    }
                )
        except json.JSONDecodeError:
            pass

    reports = [entry for entry in index_payload.get("reports", []) if entry.get("file") != report_file.name]
    reports.insert(0, _build_index_entry(report_file=report_file, payload=payload))
    index_payload["updated_at"] = payload.get("finished_at") or payload.get("started_at")
    index_payload["latest"] = latest_file.name if latest_file is not None else report_file.name
    index_payload["latest_report"] = report_file.name
    index_payload["reports"] = reports[:history_limit]
    _write_json_report(index_file, index_payload)


def _persist_reports(
    *,
    payload: dict[str, Any],
    report_file: Path | None,
    latest_file: Path | None,
) -> None:
    _annotate_smoke_results_availability(payload)
    payload.update(_extract_provider_route_summary(payload))
    payload.update(_extract_smoke_failure_summary(payload))
    payload.update(_extract_report_workflow_smoke_summary(payload))
    if report_file is not None:
        _write_json_report(report_file, payload)
    if latest_file is not None:
        _write_json_report(latest_file, payload)
    if report_file is not None and latest_file is not None:
        _update_report_index(report_file=report_file, latest_file=latest_file, payload=payload)


def _fetch_health_json(base_url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    health_url = f"{base_url.rstrip('/')}/health"
    try:
        with request.urlopen(health_url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(f"Health check failed for {health_url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Health check returned invalid JSON for {health_url}") from exc
    if payload.get("status") != "ok":
        raise SystemExit(f"Health check returned non-ok status for {health_url}: {payload}")
    return payload


def _validate_health_provider_routing(payload: dict[str, Any]) -> dict[str, Any]:
    provider_routes = payload.get("provider_routes")
    if not isinstance(provider_routes, dict):
        raise SystemExit("Health check missing provider_routes metadata.")
    missing_routes = [key for key in REQUIRED_PROVIDER_ROUTE_KEYS if not str(provider_routes.get(key, "")).strip()]
    if missing_routes:
        raise SystemExit(f"Health check missing provider_routes keys: {', '.join(missing_routes)}")

    provider_route_checks = payload.get("provider_route_checks")
    if not isinstance(provider_route_checks, dict):
        raise SystemExit("Health check missing provider_route_checks metadata.")
    missing_route_checks = [key for key in REQUIRED_PROVIDER_ROUTE_KEYS if key not in provider_route_checks]
    if missing_route_checks:
        raise SystemExit(
            f"Health check missing provider_route_checks keys: {', '.join(missing_route_checks)}"
        )
    invalid_route_checks = {
        key: provider_route_checks.get(key)
        for key in REQUIRED_PROVIDER_ROUTE_KEYS
        if provider_route_checks.get(key) not in ALLOWED_PROVIDER_ROUTE_STATUSES
    }
    if invalid_route_checks:
        raise SystemExit(f"Health check has invalid provider_route_checks values: {invalid_route_checks}")

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        raise SystemExit("Health check missing checks metadata.")
    missing_checks = [key for key in REQUIRED_PROVIDER_CHECK_KEYS if key not in checks]
    if missing_checks:
        raise SystemExit(f"Health check missing provider check keys: {', '.join(missing_checks)}")
    invalid_checks = {
        key: checks.get(key)
        for key in REQUIRED_PROVIDER_CHECK_KEYS
        if checks.get(key) not in ALLOWED_PROVIDER_ROUTE_STATUSES
    }
    if invalid_checks:
        raise SystemExit(f"Health check has invalid provider check values: {invalid_checks}")

    provider_policy_checks = payload.get("provider_policy_checks")
    if not isinstance(provider_policy_checks, dict):
        raise SystemExit("Health check missing provider_policy_checks metadata.")
    missing_policy_checks = [key for key in REQUIRED_PROVIDER_POLICY_KEYS if key not in provider_policy_checks]
    if missing_policy_checks:
        raise SystemExit(
            f"Health check missing provider_policy_checks keys: {', '.join(missing_policy_checks)}"
        )
    invalid_policy_checks = {
        key: provider_policy_checks.get(key)
        for key in REQUIRED_PROVIDER_POLICY_KEYS
        if provider_policy_checks.get(key) not in ALLOWED_PROVIDER_POLICY_STATUSES
    }
    if invalid_policy_checks:
        raise SystemExit(f"Health check has invalid provider_policy_checks values: {invalid_policy_checks}")

    provider_policy_issues = payload.get("provider_policy_issues")
    if not isinstance(provider_policy_issues, dict):
        raise SystemExit("Health check missing provider_policy_issues metadata.")
    missing_policy_issue_keys = [key for key in REQUIRED_PROVIDER_POLICY_KEYS if key not in provider_policy_issues]
    if missing_policy_issue_keys:
        raise SystemExit(
            f"Health check missing provider_policy_issues keys: {', '.join(missing_policy_issue_keys)}"
        )
    invalid_policy_issues = {
        key: value
        for key, value in provider_policy_issues.items()
        if key in REQUIRED_PROVIDER_POLICY_KEYS
        and not (
            isinstance(value, list)
            and all(isinstance(item, str) for item in value)
        )
    }
    if invalid_policy_issues:
        raise SystemExit(f"Health check has invalid provider_policy_issues values: {invalid_policy_issues}")

    return {
        "provider_routes": {key: str(provider_routes[key]) for key in REQUIRED_PROVIDER_ROUTE_KEYS},
        "provider_route_checks": {key: str(provider_route_checks[key]) for key in REQUIRED_PROVIDER_ROUTE_KEYS},
        "checks": {key: str(checks[key]) for key in REQUIRED_PROVIDER_CHECK_KEYS},
        "provider_policy_checks": {
            key: str(provider_policy_checks[key]) for key in REQUIRED_PROVIDER_POLICY_KEYS
        },
        "provider_policy_issues": {
            key: [str(item) for item in provider_policy_issues[key]]
            for key in REQUIRED_PROVIDER_POLICY_KEYS
        },
    }


def run_post_deploy_check(
    *,
    env_file: Path,
    compose_file: Path,
    app_service: str,
    nginx_service: str,
    base_url: str = "",
    skip_smoke: bool = False,
    report_file: Path | None = None,
    report_dir: Path | None = None,
) -> int:
    resolved_env_file = Path(env_file).expanduser()
    resolved_compose_file = Path(compose_file).expanduser()
    if not resolved_compose_file.exists():
        raise SystemExit(f"Compose file not found: {resolved_compose_file}")

    env_values = _load_env_file(resolved_env_file)
    resolved_base_url = _resolve_base_url(base_url, env_values)
    started_at = datetime.now(timezone.utc)
    resolved_report_file, latest_report_file = _resolve_report_targets(
        report_file=report_file,
        report_dir=report_dir,
        started_at=started_at,
    )
    report: dict[str, Any] = {
        "status": "passed",
        "base_url": resolved_base_url,
        "env_file": str(resolved_env_file),
        "compose_file": str(resolved_compose_file),
        "app_service": app_service,
        "nginx_service": nginx_service,
        "skip_smoke": bool(skip_smoke),
        "started_at": started_at.isoformat(),
        "checks": [],
    }

    try:
        health_payload = _fetch_health_json(resolved_base_url)
        _append_step(
            report,
            name="health",
            status="passed",
            url=f"{resolved_base_url}/health",
            response=health_payload,
        )
        print(f"PASS health {resolved_base_url}/health -> {health_payload}", flush=True)

        try:
            provider_routing = _validate_health_provider_routing(health_payload)
        except SystemExit as exc:
            _append_step(
                report,
                name="health provider routing",
                status="failed",
                url=f"{resolved_base_url}/health",
                error=str(exc),
                response=health_payload,
            )
            raise
        _append_step(
            report,
            name="health provider routing",
            status="passed",
            url=f"{resolved_base_url}/health",
            **provider_routing,
        )
        print(
            "PASS health provider routing -> "
            f"generation={provider_routing['provider_routes']['generation']} "
            f"attachment={provider_routing['provider_routes']['attachment']} "
            f"visual={provider_routing['provider_routes']['visual']} "
            f"quality_first={provider_routing['provider_policy_checks']['quality_first']}",
            flush=True,
        )

        compose_prefix = [
            "docker",
            "compose",
            "--env-file",
            str(resolved_env_file),
            "-f",
            str(resolved_compose_file),
        ]
        _run_command_with_report(report, [*compose_prefix, "ps"], label="docker compose ps")
        print("PASS docker compose ps", flush=True)

        _run_command_with_report(
            report,
            [*compose_prefix, "exec", "-T", nginx_service, "nginx", "-t"],
            label="nginx config test",
        )
        print("PASS nginx -t", flush=True)

        if not skip_smoke:
            _run_command_with_report(
                report,
                [
                    sys.executable,
                    "scripts/run_deployed_smoke.py",
                    "--env-file",
                    str(resolved_env_file),
                    "--base-url",
                    resolved_base_url,
                    "--preflight",
                ],
                label="deployed smoke preflight",
            )
            print("PASS deployed smoke preflight", flush=True)

            _run_command_with_report(
                report,
                [
                    sys.executable,
                    "scripts/run_deployed_smoke.py",
                    "--env-file",
                    str(resolved_env_file),
                    "--compose-file",
                    str(resolved_compose_file),
                    "--service",
                    app_service,
                    "--base-url",
                    resolved_base_url,
                ],
                label="deployed smoke",
                capture_output=True,
                output_parser=_extract_smoke_result_details,
                failure_parser=_extract_smoke_failure_details,
            )
            print("PASS deployed smoke", flush=True)

            resolved_api_key = _resolve_api_key(env_values)
            resolved_smoke_timeout_sec = _resolve_smoke_timeout_sec(env_values)

            _run_command_with_report(
                report,
                [
                    *compose_prefix,
                    "exec",
                    "-T",
                    "-e",
                    f"SMOKE_BASE_URL={resolved_base_url}",
                    "-e",
                    f"SMOKE_API_KEY={resolved_api_key}",
                    "-e",
                    f"SMOKE_TIMEOUT_SEC={resolved_smoke_timeout_sec}",
                    app_service,
                    "python",
                    "scripts/report_workflow_smoke.py",
                ],
                label="report workflow smoke",
                capture_output=True,
                output_parser=_extract_report_workflow_smoke_result_details,
            )
            print("PASS report workflow smoke", flush=True)

        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _persist_reports(
            payload=report,
            report_file=resolved_report_file,
            latest_file=latest_report_file,
        )
        if resolved_report_file is not None:
            print(f"PASS report written -> {resolved_report_file}", flush=True)
        if latest_report_file is not None:
            print(f"PASS latest report updated -> {latest_report_file}", flush=True)

        print("PASS post-deploy check completed.", flush=True)
        return 0
    except SystemExit as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _persist_reports(
            payload=report,
            report_file=resolved_report_file,
            latest_file=latest_report_file,
        )
        raise


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run post-deploy verification for a DecisionDoc docker-compose environment.",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the deployment env file. Default: .env.prod in repo root",
    )
    parser.add_argument(
        "--compose-file",
        default=str(DEFAULT_COMPOSE_FILE),
        help="Path to the docker compose file. Default: docker-compose.prod.yml",
    )
    parser.add_argument(
        "--app-service",
        default=DEFAULT_APP_SERVICE,
        help="Compose service name that contains the app runtime. Default: app",
    )
    parser.add_argument(
        "--nginx-service",
        default=DEFAULT_NGINX_SERVICE,
        help="Compose service name for nginx. Default: nginx",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Override deployed base URL. Defaults to the first ALLOWED_ORIGINS value in the env file.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the deployed smoke runner and only check health, compose status, and nginx config.",
    )
    parser.add_argument(
        "--report-file",
        default="",
        help="Optional path to write a JSON summary report for the post-deploy check.",
    )
    parser.add_argument(
        "--report-dir",
        default="",
        help="Optional directory to store a timestamped report plus latest.json for the post-deploy check.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    return run_post_deploy_check(
        env_file=Path(args.env_file),
        compose_file=Path(args.compose_file),
        app_service=args.app_service,
        nginx_service=args.nginx_service,
        base_url=args.base_url,
        skip_smoke=bool(args.skip_smoke),
        report_file=Path(args.report_file).expanduser() if args.report_file else None,
        report_dir=Path(args.report_dir).expanduser() if args.report_dir else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())

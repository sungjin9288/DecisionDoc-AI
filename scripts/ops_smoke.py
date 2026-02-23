#!/usr/bin/env python3
import os
import sys
from typing import Any

import boto3
import httpx


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _assert_status(endpoint: str, response: httpx.Response, expected: int) -> dict[str, Any]:
    body = _json_body(response)
    if response.status_code != expected:
        code = body.get("code", "unknown")
        raise SystemExit(f"{endpoint} expected {expected}, got {response.status_code} (code={code})")
    return body


def _print_result(endpoint: str, status_code: int, incident_key: str, deduped: bool, report_key: str) -> None:
    print(
        f"{endpoint} -> {status_code} incident_key={incident_key} "
        f"deduped={str(deduped).lower()} report_key={report_key}"
    )


def _resolve_report_key(payload: dict[str, Any]) -> str:
    report_key = payload.get("report_json_key") or payload.get("report_s3_key")
    if not isinstance(report_key, str) or not report_key:
        raise SystemExit("ops investigate response missing report key")
    return report_key


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL").rstrip("/")
    ops_key = _required_env("SMOKE_OPS_KEY")
    bucket = _required_env("SMOKE_S3_BUCKET")
    prefix = os.getenv("SMOKE_S3_PREFIX", "").strip()
    region = _required_env("AWS_REGION")
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", "30"))

    payload = {
        "window_minutes": 30,
        "reason": "smoke",
        "notify": False,
        "force": False,
    }
    headers = {"X-DecisionDoc-Ops-Key": ops_key}
    s3 = boto3.client("s3", region_name=region)

    with httpx.Client(timeout=timeout_sec) as client:
        first = client.post(f"{base_url}/ops/investigate", headers=headers, json=payload)
        first_body = _assert_status("POST /ops/investigate (first)", first, 200)
        first_incident_key = str(first_body.get("incident_key", ""))
        first_deduped = bool(first_body.get("deduped", False))
        first_report_key = _resolve_report_key(first_body)
        if prefix and not first_report_key.startswith(prefix):
            first_report_key = f"{prefix.rstrip('/')}/{first_report_key.lstrip('/')}"
        if not first_incident_key:
            raise SystemExit("ops investigate response missing incident_key")
        s3.head_object(Bucket=bucket, Key=first_report_key)
        _print_result(
            "POST /ops/investigate (first)",
            first.status_code,
            first_incident_key,
            first_deduped,
            first_report_key,
        )

        second = client.post(f"{base_url}/ops/investigate", headers=headers, json=payload)
        second_body = _assert_status("POST /ops/investigate (second)", second, 200)
        second_incident_key = str(second_body.get("incident_key", ""))
        second_deduped = bool(second_body.get("deduped", False))
        second_report_key = _resolve_report_key(second_body)
        if prefix and not second_report_key.startswith(prefix):
            second_report_key = f"{prefix.rstrip('/')}/{second_report_key.lstrip('/')}"
        if not second_deduped:
            raise SystemExit("second ops investigate call was not deduped=true")
        _print_result(
            "POST /ops/investigate (second)",
            second.status_code,
            second_incident_key,
            second_deduped,
            second_report_key,
        )

    print("Ops smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

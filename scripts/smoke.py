#!/usr/bin/env python3
import os
import sys
from typing import Any

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


def _print_result(endpoint: str, status_code: int, request_id: str = "", bundle_id: str = "", extra: str = "") -> None:
    parts = [f"{endpoint} -> {status_code}"]
    if request_id:
        parts.append(f"request_id={request_id}")
    if bundle_id:
        parts.append(f"bundle_id={bundle_id}")
    if extra:
        parts.append(extra)
    print(" ".join(parts))


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL").rstrip("/")
    api_key = _required_env("SMOKE_API_KEY")
    provider = os.getenv("SMOKE_PROVIDER", "mock").strip() or "mock"
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", "30"))

    payload = {
        "title": "Smoke Check",
        "goal": "Verify deployed generate endpoints",
        "context": f"provider={provider}",
    }

    with httpx.Client(timeout=timeout_sec) as client:
        health = client.get(f"{base_url}/health")
        _assert_status("GET /health", health, 200)
        _print_result("GET /health", health.status_code, request_id=health.headers.get("X-Request-Id", ""))

        no_auth = client.post(f"{base_url}/generate", json=payload)
        no_auth_body = _assert_status("POST /generate (no key)", no_auth, 401)
        if no_auth_body.get("code") != "UNAUTHORIZED":
            raise SystemExit("POST /generate (no key) did not return UNAUTHORIZED")
        _print_result(
            "POST /generate (no key)",
            no_auth.status_code,
            request_id=str(no_auth_body.get("request_id", "")),
        )

        auth_headers = {"X-DecisionDoc-Api-Key": api_key}
        generate = client.post(f"{base_url}/generate", headers=auth_headers, json=payload)
        generate_body = _assert_status("POST /generate (auth)", generate, 200)
        generate_bundle_id = str(generate_body.get("bundle_id", ""))
        generate_request_id = str(generate_body.get("request_id", ""))
        if not generate_bundle_id:
            raise SystemExit("POST /generate (auth) missing bundle_id")
        _print_result(
            "POST /generate (auth)",
            generate.status_code,
            request_id=generate_request_id,
            bundle_id=generate_bundle_id,
        )

        export = client.post(f"{base_url}/generate/export", headers=auth_headers, json=payload)
        export_body = _assert_status("POST /generate/export (auth)", export, 200)
        export_bundle_id = str(export_body.get("bundle_id", ""))
        export_request_id = str(export_body.get("request_id", ""))
        files = export_body.get("files")
        if not export_bundle_id:
            raise SystemExit("POST /generate/export (auth) missing bundle_id")
        if not isinstance(files, list) or not files:
            raise SystemExit("POST /generate/export (auth) missing export files")
        _print_result(
            "POST /generate/export (auth)",
            export.status_code,
            request_id=export_request_id,
            bundle_id=export_bundle_id,
            extra=f"files={len(files)}",
        )

    print("Smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared HTTP assertions and output helpers for deployment smoke checks."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _error_items(body: dict[str, Any]) -> list[str]:
    raw_errors = body.get("errors")
    if not isinstance(raw_errors, list):
        return []
    items: list[str] = []
    for raw_item in raw_errors:
        item = str(raw_item or "").strip()
        if item:
            items.append(item)
    return items


def _assert_status(
    endpoint: str, response: httpx.Response, expected: int
) -> dict[str, Any]:
    body = _json_body(response)
    if response.status_code != expected:
        code = body.get("code", "unknown")
        details: list[str] = []
        message = str(body.get("message", "")).strip()
        if message:
            details.append(f"message={message}")
        details.extend(_error_items(body))
        detail_suffix = f"; {'; '.join(details)}" if details else ""
        raise SystemExit(
            f"{endpoint} expected {expected}, got {response.status_code} (code={code}{detail_suffix})"
        )
    return body


def _print_result(
    endpoint: str,
    status_code: int,
    request_id: str = "",
    bundle_id: str = "",
    extra: str = "",
) -> None:
    parts = [f"{endpoint} -> {status_code}"]
    if request_id:
        parts.append(f"request_id={request_id}")
    if bundle_id:
        parts.append(f"bundle_id={bundle_id}")
    if extra:
        parts.append(extra)
    print(" ".join(parts))


def _print_skip(reason: str) -> None:
    print(f"SKIP {reason}")


def _tenant_headers() -> dict[str, str]:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    if not tenant_id or tenant_id == "system":
        return {}
    return {"X-Tenant-ID": tenant_id}


def _read_stream_complete(response: httpx.Response) -> dict[str, Any]:
    buffer = ""
    for chunk in response.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            part, buffer = buffer.split("\n\n", 1)
            event_type = ""
            payload_raw = ""
            for line in part.splitlines():
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: "):
                    payload_raw += line[6:]
            if not payload_raw:
                continue
            try:
                payload = json.loads(payload_raw)
            except ValueError:
                continue
            if event_type == "complete":
                return payload if isinstance(payload, dict) else {}
            if event_type == "error":
                message = (
                    payload.get("message", "stream generation failed")
                    if isinstance(payload, dict)
                    else "stream generation failed"
                )
                raise SystemExit(
                    f"POST /generate/stream procurement smoke failed: {message}"
                )
    raise SystemExit(
        "POST /generate/stream procurement smoke ended without a complete event"
    )

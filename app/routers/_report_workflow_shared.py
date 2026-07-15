"""Shared request and response helpers for report workflow routes."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import HTTPException, Request

from app.dependencies import get_username


def actor(request: Request, payload_username: str = "") -> str:
    return payload_username.strip() or get_username(request) or "anonymous"


def get_store(request: Request):
    return request.app.state.report_workflow_store


def get_service(request: Request):
    return request.app.state.report_workflow_service


def get_document_ops_service(request: Request):
    return request.app.state.document_ops_service


def record_quality_pilot_state(
    request: Request,
    preview: dict[str, Any],
    *,
    preview_verified: bool,
    action: str | None = None,
) -> None:
    request.state.report_quality_action = action or (
        "pilot_export" if preview_verified else "pilot_preview"
    )
    request.state.report_quality_pilot_sha256 = str(preview.get("export_sha256") or "")
    request.state.report_quality_pilot_artifact_count = int(
        preview.get("artifact_count") or 0
    )
    request.state.report_quality_pilot_preview_verified = preview_verified


def record_quality_pilot_package_verification_state(
    request: Request,
    result: dict[str, Any] | None = None,
) -> None:
    request.state.audit_action = "report_quality.pilot_package_verify"
    if result is None:
        return
    request.state.report_quality_pilot_sha256 = str(result.get("export_sha256") or "")
    request.state.report_quality_pilot_package_sha256 = str(
        result.get("package_sha256") or ""
    )
    request.state.report_quality_pilot_artifact_count = int(
        result.get("artifact_count") or 0
    )
    request.state.report_quality_pilot_preview_verified = True


def handle_store_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def redact_visual_asset_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [redact_visual_asset_payload(item) for item in value]
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key == "content_base64":
                redacted["has_content_base64"] = bool(item)
                redacted["content_base64_len"] = len(str(item or ""))
                continue
            redacted[key] = redact_visual_asset_payload(item)
        return redacted
    return value


def workflow_list_item(record: Any) -> dict[str, Any]:
    raw = asdict(record)
    visual_assets = raw.get("visual_assets")
    asset_count = len(visual_assets) if isinstance(visual_assets, list) else 0
    item = redact_visual_asset_payload(raw)
    item["visual_asset_count"] = asset_count
    return item

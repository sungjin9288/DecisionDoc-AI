"""Shared request validation for project procurement review routes."""
from __future__ import annotations

import re

from fastapi import HTTPException, Request


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def require_packet_sha256(packet_sha256: str) -> str:
    """Return a canonical packet SHA-256 or reject the request."""
    if not _SHA256_PATTERN.fullmatch(packet_sha256):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_procurement_review_packet_sha256",
                "message": "검토 패킷 SHA256 형식이 올바르지 않습니다.",
            },
        )
    return packet_sha256


def ensure_project_exists(
    request: Request,
    *,
    project_id: str,
    tenant_id: str,
) -> None:
    """Keep review artifact lookup inside an existing tenant project."""
    project = request.app.state.project_store.get(
        project_id,
        tenant_id=tenant_id,
    )
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"프로젝트를 찾을 수 없습니다: {project_id}",
        )

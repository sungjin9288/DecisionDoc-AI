"""Verified, non-persisted ZIP review-packet download route."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.auth.api_key import require_api_key
from app.dependencies import require_auth as _require_auth
from app.maintenance.mode import require_not_maintenance
from app.routers.generate._shared import _get_zip_docs
from app.services.generation_export_packet import (
    ExportFormatInvalidError,
    GenerationExportPacketError,
    canonicalize_export_formats,
    prepare_generation_export_packet_delivery,
)


logger = logging.getLogger("decisiondoc.generate")
router = APIRouter(tags=["generate"])


@router.get(
    "/generate/export-zip",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def export_zip(request: Request, request_id: str, formats: str = "docx") -> Response:
    """Deliver a tenant-bound packet only after byte-only verification succeeds."""
    _require_auth(request)
    response_request_id = getattr(request.state, "request_id", "unknown-request-id")
    try:
        canonical_formats = canonicalize_export_formats(formats)
    except ExportFormatInvalidError:
        return _export_packet_error(
            request_id=response_request_id,
            status_code=400,
            code="EXPORT_FORMAT_INVALID",
            message="Invalid export formats.",
        )

    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    cached = _get_zip_docs(request_id, tenant_id=tenant_id)
    if cached is None:
        return _export_packet_error(
            request_id=response_request_id,
            status_code=404,
            code="EXPORT_SOURCE_NOT_FOUND",
            message="Export source not found.",
        )
    docs, title = cached
    try:
        delivery = await prepare_generation_export_packet_delivery(
            docs=docs,
            title=title,
            tenant_id=tenant_id,
            request_id=request_id,
            formats=canonical_formats,
        )
    except GenerationExportPacketError:
        logger.warning("Generation export packet failed request_id=%s", response_request_id)
        return _export_packet_error(
            request_id=response_request_id,
            status_code=500,
            code="EXPORT_PACKET_FAILED",
            message="Export packet could not be produced.",
        )

    request.state.audit_action = "doc.download"
    return Response(
        content=delivery["content"],
        media_type="application/zip",
        headers=delivery["headers"],
    )


def _export_packet_error(
    *,
    request_id: str,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "request_id": request_id},
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )

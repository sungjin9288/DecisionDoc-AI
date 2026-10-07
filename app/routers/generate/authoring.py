"""app/routers/generate/authoring.py — Local agent-authored generation.

A Claude Code or Codex session opened on this repository writes the bundle
itself. These routes give it the same prompt the provider path would use and
then run its JSON through the normal pipeline without any provider call:

  POST /generate/authoring-brief
  POST /generate/authored
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.ai_profiles.catalog import ensure_bundle_access
from app.auth.api_key import require_api_key
from app.maintenance.mode import require_not_maintenance
from app.schemas import (
    AuthoredGenerateRequest,
    AuthoredGenerateResponse,
    AuthoringBriefResponse,
    GenerateRequest,
)
from app.services.generation.errors import EvalLintFailedError, ProviderFailedError
from app.services.validator import DocumentValidationError
from app.routers.generate._project_link import link_generated_document
from app.routers.generate._shared import (
    _ensure_procurement_bundle_enabled,
    _run_generate_with_result,
)

logger = logging.getLogger("decisiondoc.generate.authoring")

router = APIRouter(tags=["generate"])


def _tenant_id(request: Request) -> str:
    return getattr(request.state, "tenant_id", "system") or "system"


@router.post(
    "/generate/authoring-brief",
    response_model=AuthoringBriefResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def authoring_brief(payload: GenerateRequest, request: Request) -> AuthoringBriefResponse:
    """Return the provider prompt for this request without resolving a provider."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    ensure_bundle_access(request, payload.bundle_type)
    brief = request.app.state.service.build_authoring_brief(
        payload,
        request_id=request.state.request_id,
        tenant_id=_tenant_id(request),
    )
    return AuthoringBriefResponse(**brief)


@router.post(
    "/generate/authored",
    response_model=AuthoredGenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def authored_generate(body: AuthoredGenerateRequest, request: Request) -> AuthoredGenerateResponse:
    """Validate, render and store a bundle written by a local agent session."""
    payload = body.request
    try:
        response, result = _run_generate_with_result(payload, request, authored_bundle=body.bundle)
    except (ProviderFailedError, EvalLintFailedError, DocumentValidationError) as exc:
        # The session wrote this JSON; return the reasons so it can fix its draft.
        request.state.error_code = "AUTHORED_BUNDLE_INVALID"
        errors = [str(item) for item in getattr(exc, "errors", None) or []][:20]
        raise HTTPException(
            status_code=422,
            detail={"code": "AUTHORED_BUNDLE_INVALID", "message": str(exc), "errors": errors},
        ) from exc

    project_document_id = None
    if payload.project_id:
        metadata = result["metadata"]
        bound = bool(metadata.get("source_procurement_binding"))
        try:
            linked = link_generated_document(
                request.app.state.project_store,
                payload,
                tenant_id=_tenant_id(request),
                request_id=request.state.request_id,
                docs=result["docs"],
                metadata=metadata,
            )
        except Exception:
            logger.warning("Authored document could not be linked request_id=%s", request.state.request_id)
            linked = None
        if linked is None and bound:
            request.state.error_code = "PROJECT_DOCUMENT_UNAVAILABLE"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PROJECT_DOCUMENT_UNAVAILABLE",
                    "message": "Generated document could not be linked to its project.",
                },
            )
        project_document_id = getattr(linked, "doc_id", None)

    return AuthoredGenerateResponse(**response.model_dump(), project_document_id=project_document_id)

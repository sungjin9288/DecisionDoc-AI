"""app/routers/local_llm.py — Local LLM endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import (
    get_local_llm_api_key,
    get_local_llm_base_url,
    get_local_llm_model,
    get_local_llm_timeout,
)
from app.providers.base import ProviderError
from app.providers.factory import configured_provider_routes
from app.providers.local_provider import LocalProvider

router = APIRouter(prefix="/local-llm", tags=["local-llm"])


def _is_local_provider_configured() -> bool:
    configured = configured_provider_routes()["generation"]
    names = [n.strip() for n in configured.split(",") if n.strip()]
    return "local" in names


def _not_configured_response() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "status": "not_configured",
            "message": (
                "Set DECISIONDOC_PROVIDER_GENERATION=local or "
                "DECISIONDOC_PROVIDER=local to enable local LLM."
            ),
        },
    )


def _configuration_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "status": "configuration_error",
            "message": "Local LLM configuration is invalid.",
        },
    )


async def _local_health_result() -> dict:
    provider = LocalProvider(
        base_url=get_local_llm_base_url(),
        model=get_local_llm_model(),
        api_key=get_local_llm_api_key(),
        timeout=get_local_llm_timeout(),
    )
    return await provider.health_check()


@router.get("/health")
async def local_llm_health() -> JSONResponse:
    """Check if the configured local LLM server is reachable.

    Returns 200 when not configured (status=not_configured), 200 when the
    server responds OK, or 503 when the server cannot be reached.
    """
    try:
        if not _is_local_provider_configured():
            return _not_configured_response()
        result = await _local_health_result()
    except ProviderError:
        return _configuration_error_response()
    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=result)


@router.get("/models")
async def list_local_models() -> JSONResponse:
    """List models available on the local LLM server.

    Tries the standard OpenAI ``/models`` endpoint first, then falls back
    to the Ollama ``/api/tags`` endpoint.
    """
    try:
        if not _is_local_provider_configured():
            return _not_configured_response()
        result = await _local_health_result()
    except ProviderError:
        return _configuration_error_response()
    if result["status"] != "ok":
        return JSONResponse(status_code=503, content=result)
    return JSONResponse(
        status_code=200,
        content={
            "models": result.get("available_models", []),
            "current": result.get("model", get_local_llm_model()),
        },
    )

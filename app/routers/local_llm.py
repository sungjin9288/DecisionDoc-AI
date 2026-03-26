"""app/routers/local_llm.py — Local LLM endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import (
    get_local_llm_api_key,
    get_local_llm_base_url,
    get_local_llm_model,
)

router = APIRouter(prefix="/local-llm", tags=["local-llm"])


def _is_local_provider_configured() -> bool:
    configured = os.getenv("DECISIONDOC_PROVIDER", "mock")
    names = [n.strip() for n in configured.split(",") if n.strip()]
    return "local" in names


@router.get("/health")
async def local_llm_health() -> JSONResponse:
    """Check if the configured local LLM server is reachable.

    Returns 200 when not configured (status=not_configured), 200 when the
    server responds OK, or 503 when the server cannot be reached.
    """
    if not _is_local_provider_configured():
        return JSONResponse(
            status_code=200,
            content={
                "status": "not_configured",
                "message": "Set DECISIONDOC_PROVIDER=local to enable local LLM.",
            },
        )
    from app.providers.local_provider import LocalProvider

    provider = LocalProvider(
        base_url=get_local_llm_base_url(),
        model=get_local_llm_model(),
        api_key=get_local_llm_api_key(),
    )
    result = await provider.health_check()
    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=result)


@router.get("/models")
async def list_local_models() -> dict:
    """List models available on the local LLM server.

    Tries the standard OpenAI ``/models`` endpoint first, then falls back
    to the Ollama ``/api/tags`` endpoint.
    """
    base_url = get_local_llm_base_url()
    api_key = get_local_llm_api_key()
    models: list[str] = []

    # 1. OpenAI-compatible /models
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if res.status_code == 200:
                models = [m.get("id", "") for m in res.json().get("data", [])]
    except Exception:
        pass

    # 2. Ollama /api/tags fallback
    if not models:
        try:
            ollama_base = base_url.replace("/v1", "").rstrip("/")
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(f"{ollama_base}/api/tags")
                if res.status_code == 200:
                    models = [
                        m.get("name", "")
                        for m in res.json().get("models", [])
                    ]
        except Exception:
            pass

    return {"models": models, "current": get_local_llm_model()}

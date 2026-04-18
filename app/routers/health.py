"""app/routers/health.py — Health, metrics, and version endpoints.

Extracted from app/main.py. Closure variables resolved via app.state and os.getenv().
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.config import (
    APP_VERSION,
    get_local_llm_api_key,
    get_local_llm_base_url,
    is_enabled,
    is_procurement_copilot_enabled,
    is_realtime_events_enabled,
)
from app.maintenance.mode import is_maintenance_mode
from app.providers.factory import configured_provider_names, configured_provider_routes
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


def _provider_chain_ready(provider_names: list[str]) -> str:
    if "openai" in provider_names and not os.getenv("OPENAI_API_KEY", "").strip():
        return "degraded"
    if "gemini" in provider_names and not os.getenv("GEMINI_API_KEY", "").strip():
        return "degraded"
    if "claude" in provider_names and not os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "degraded"
    return "ok"


def _split_provider_route(route: str) -> list[str]:
    return [name.strip() for name in str(route or "").split(",") if name.strip()]


def _quality_first_policy_issues(provider_routes: dict[str, str]) -> list[str]:
    issues: list[str] = []

    default_route = _split_provider_route(provider_routes.get("default", ""))
    generation_route = _split_provider_route(provider_routes.get("generation", ""))
    attachment_route = _split_provider_route(provider_routes.get("attachment", ""))
    visual_route = _split_provider_route(provider_routes.get("visual", ""))

    if {"claude", "gemini", "openai"} - set(default_route):
        issues.append("default route must include claude, gemini, openai for quality-first readiness")
    if default_route and default_route[0] not in {"claude", "gemini"}:
        issues.append("default route must prioritize claude or gemini ahead of openai for quality-first readiness")
    if any(name in {"mock", "local"} for name in default_route):
        issues.append("default route cannot include mock/local for quality-first readiness")

    generation_override = os.getenv("DECISIONDOC_PROVIDER_GENERATION", "").strip()
    if not generation_override:
        issues.append("DECISIONDOC_PROVIDER_GENERATION is not explicitly configured")
    if {"claude", "gemini"} - set(generation_route):
        issues.append("generation route must include both claude and gemini for quality-first readiness")
    if generation_route and generation_route[0] not in {"claude", "gemini"}:
        issues.append("generation route must prioritize claude or gemini first for quality-first readiness")
    if any(name in {"mock", "local"} for name in generation_route):
        issues.append("generation route cannot include mock/local for quality-first readiness")

    attachment_override = os.getenv("DECISIONDOC_PROVIDER_ATTACHMENT", "").strip()
    if not attachment_override:
        issues.append("DECISIONDOC_PROVIDER_ATTACHMENT is not explicitly configured")
    if {"claude", "gemini"} - set(attachment_route):
        issues.append("attachment route must include both claude and gemini for quality-first readiness")
    if attachment_route and attachment_route[0] not in {"gemini", "claude"}:
        issues.append("attachment route must prioritize gemini or claude first for quality-first readiness")
    if any(name in {"mock", "local"} for name in attachment_route):
        issues.append("attachment route cannot include mock/local for quality-first readiness")

    visual_override = os.getenv("DECISIONDOC_PROVIDER_VISUAL", "").strip()
    if not visual_override:
        issues.append("DECISIONDOC_PROVIDER_VISUAL is not explicitly configured")
    if visual_route != ["openai"]:
        issues.append("visual route must be exactly openai because direct visual asset generation is only implemented for OpenAI in this deployment")

    return issues


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    maintenance = is_maintenance_mode()
    checks: dict[str, str] = {}

    configured_provider = os.getenv("DECISIONDOC_PROVIDER", "mock")
    provider_names = configured_provider_names()
    provider_routes = configured_provider_routes()
    provider_route_checks = {
        capability: _provider_chain_ready([n.strip() for n in route.split(",") if n.strip()])
        for capability, route in provider_routes.items()
    }
    provider_policy_issues = {
        "quality_first": _quality_first_policy_issues(provider_routes),
    }
    provider_policy_checks = {
        name: ("ok" if not issues else "degraded")
        for name, issues in provider_policy_issues.items()
    }
    data_dir = request.app.state.data_dir
    storage_kind = os.getenv("DECISIONDOC_STORAGE", "local").lower()
    storage = request.app.state.storage
    _eval_store = request.app.state.eval_store
    template_version = request.app.state.template_version

    # 1. Provider API key presence
    checks["provider"] = "degraded" if any(status == "degraded" for status in provider_route_checks.values()) else "ok"
    checks["provider_generation"] = provider_route_checks["generation"]
    checks["provider_attachment"] = provider_route_checks["attachment"]
    checks["provider_visual"] = provider_route_checks["visual"]

    # 2. Local storage read/write roundtrip
    try:
        _health_path = data_dir / ".health_probe"
        _health_path.write_text("ok", encoding="utf-8")
        _health_path.unlink()
        checks["storage"] = "ok"
    except Exception:
        checks["storage"] = "degraded"

    # 3. S3 connectivity (only when S3 is configured)
    if storage_kind == "s3":
        try:
            storage.health_check()  # type: ignore[union-attr]
            checks["s3"] = "ok"
        except Exception:
            checks["s3"] = "degraded"

    # 4. EvalStore readability
    try:
        _eval_store.load_all()
        checks["eval_store"] = "ok"
    except Exception:
        checks["eval_store"] = "degraded"

    # 5. Local LLM reachability (only when provider=local)
    if "local" in provider_names:
        try:
            _local_url = get_local_llm_base_url()
            _local_key = get_local_llm_api_key()
            with httpx.Client(timeout=5) as _hc:
                _r = _hc.get(
                    f"{_local_url}/models",
                    headers={"Authorization": f"Bearer {_local_key}"},
                )
            checks["local_llm"] = "ok" if _r.status_code == 200 else "degraded"
        except Exception:
            checks["local_llm"] = "degraded"

    overall = "degraded" if any(v == "degraded" for v in checks.values()) else "ok"
    request.state.provider = configured_provider
    request.state.template_version = template_version
    request.state.maintenance = maintenance
    return HealthResponse(
        status=overall,
        provider=configured_provider,
        maintenance=maintenance,
        checks=checks,
        provider_routes=provider_routes,
        provider_route_checks=provider_route_checks,
        provider_policy_checks=provider_policy_checks,
        provider_policy_issues=provider_policy_issues,
    )


@router.get("/health/live")
def health_live():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/health/ready")
def health_ready():
    """Kubernetes readiness probe."""
    maintenance = is_maintenance_mode()
    overall = "degraded" if maintenance else "ok"
    return {"status": overall, "maintenance": maintenance}


@router.get("/metrics")
def metrics():
    """Prometheus metrics scrape endpoint."""
    from app.middleware.metrics import get_metrics_response
    resp = get_metrics_response()
    if resp is not None:
        return resp
    return Response(content="# metrics disabled\n", media_type="text/plain; charset=utf-8")


@router.get("/version")
def version_endpoint(request: Request) -> dict:
    """앱 버전 및 환경 정보를 반환합니다."""
    import importlib.metadata
    try:
        ver = importlib.metadata.version("decisiondoc-ai")
    except importlib.metadata.PackageNotFoundError:
        ver = APP_VERSION
    environment = request.app.state.environment
    return {
        "version": ver,
        "api_version": "v1",
        "environment": environment,
        "provider": os.getenv("DECISIONDOC_PROVIDER", "mock"),
        "storage": os.getenv("DECISIONDOC_STORAGE", "local"),
        "maintenance": is_maintenance_mode(),
        "features": {
            "search": is_enabled(os.getenv("DECISIONDOC_SEARCH_ENABLED", "0")),
            "cache": is_enabled(os.getenv("DECISIONDOC_CACHE_ENABLED", "0")),
            "cors": is_enabled(os.getenv("DECISIONDOC_CORS_ENABLED", "0")),
            "procurement_copilot": getattr(
                request.app.state,
                "procurement_copilot_enabled",
                is_procurement_copilot_enabled(),
            ),
            "realtime_events": is_realtime_events_enabled(),
        },
    }

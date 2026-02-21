import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import install_exception_handlers
from app.auth.api_key import API_KEY_HEADER, get_allowed_api_keys, require_api_key
from app.auth.ops_key import require_ops_key
from app.maintenance.mode import is_maintenance_mode, require_not_maintenance
from app.middleware.observability import install_observability_middleware
from app.middleware.request_id import install_request_id_middleware
from app.observability.logging import log_event, setup_logging
from app.observability.timing import Timer
from app.ops.factory import get_ops_service
from app.schemas import (
    GenerateExportResponse,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    OpsInvestigateRequest,
    OpsInvestigateResponse,
)
from app.providers.factory import get_provider
from app.services.generation_service import GenerationService
from app.storage.factory import get_storage

logger = logging.getLogger("decisiondoc.generate")


def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_cors_allow_origins(environment: str) -> list[str]:
    raw = os.getenv("DECISIONDOC_CORS_ALLOW_ORIGINS")
    if raw is None:
        return ["*"] if environment == "dev" else []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _apply_generate_state(request: Request, result: dict, template_version: str) -> None:
    """Set all generate-related fields on request.state for observability middleware."""
    metadata = result["metadata"]
    timings = metadata.get("timings_ms", {})
    request.state.provider = metadata["provider"]
    request.state.template_version = template_version
    request.state.schema_version = metadata["schema_version"]
    request.state.cache_hit = metadata["cache_hit"]
    request.state.llm_prompt_tokens = metadata.get("llm_prompt_tokens")
    request.state.llm_output_tokens = metadata.get("llm_output_tokens")
    request.state.llm_total_tokens = metadata.get("llm_total_tokens")
    request.state.provider_ms = timings.get("provider_ms")
    request.state.render_ms = timings.get("render_ms")
    request.state.lints_ms = timings.get("lints_ms")
    request.state.validator_ms = timings.get("validator_ms")


def _build_generate_log_event(request: Request, result: dict, request_id: str, template_version: str) -> dict:
    """Build the structured log event dict for a completed generate call."""
    metadata = result["metadata"]
    return {
        "event": "generate.completed",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": 200,
        "provider": metadata["provider"],
        "template_version": template_version,
        "schema_version": metadata["schema_version"],
        "cache_hit": metadata["cache_hit"],
        "llm_prompt_tokens": request.state.llm_prompt_tokens,
        "llm_output_tokens": request.state.llm_output_tokens,
        "llm_total_tokens": request.state.llm_total_tokens,
        "provider_ms": request.state.provider_ms,
        "render_ms": request.state.render_ms,
        "lints_ms": request.state.lints_ms,
        "validator_ms": request.state.validator_ms,
    }


def create_app() -> FastAPI:
    load_dotenv()
    setup_logging()
    environment = os.getenv("DECISIONDOC_ENV", "dev").lower()
    if environment == "prod" and not get_allowed_api_keys():
        raise RuntimeError("An API key is required when DECISIONDOC_ENV=prod.")

    configured_provider = os.getenv("DECISIONDOC_PROVIDER", "mock").lower()
    configured_stage = os.getenv("DECISIONDOC_ENV", "dev").lower()
    template_version = os.getenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    template_dir = Path(__file__).resolve().parent / "templates" / template_version
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    storage = get_storage()
    service = GenerationService(provider_factory=get_provider, template_dir=template_dir, data_dir=data_dir, storage=storage)
    ops_service = get_ops_service()

    app = FastAPI(
        title="DecisionDoc AI",
        version="0.1.0",
        docs_url=None if environment == "prod" else "/docs",
        redoc_url=None if environment == "prod" else "/redoc",
        openapi_url=None if environment == "prod" else "/openapi.json",
    )
    cors_enabled = _is_enabled(os.getenv("DECISIONDOC_CORS_ENABLED", "0"))
    if cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_resolve_cors_allow_origins(environment),
            allow_methods=["*"],
            allow_headers=[API_KEY_HEADER, "Content-Type", "Authorization"],
        )
    install_observability_middleware(app)
    install_request_id_middleware(app)
    install_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        maintenance = is_maintenance_mode()
        request.state.provider = configured_provider
        request.state.template_version = template_version
        request.state.maintenance = maintenance
        return HealthResponse(status="ok", provider=configured_provider, maintenance=maintenance)

    @app.post(
        "/generate",
        response_model=GenerateResponse,
        dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
    )
    def generate(
        payload: GenerateRequest,
        request: Request,
    ) -> GenerateResponse:
        # Keep sync endpoints to avoid nested event-loop issues because providers use anyio.run internally.
        request_id = request.state.request_id
        result = service.generate_documents(payload, request_id=request_id)

        _apply_generate_state(request, result, template_version)
        log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

        metadata = result["metadata"]
        return GenerateResponse(
            request_id=request_id,
            bundle_id=metadata["bundle_id"],
            title=payload.title,
            provider=metadata["provider"],
            schema_version=metadata["schema_version"],
            cache_hit=metadata["cache_hit"],
            docs=result["docs"],
        )

    @app.post(
        "/generate/export",
        response_model=GenerateExportResponse,
        dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
    )
    def generate_export(
        payload: GenerateRequest,
        request: Request,
    ) -> GenerateExportResponse:
        # Keep sync endpoints to avoid nested event-loop issues because providers use anyio.run internally.
        request_id = request.state.request_id
        result = service.generate_documents(payload, request_id=request_id)
        docs = result["docs"]
        bundle_id = result["metadata"]["bundle_id"]
        export_timer = Timer()
        with export_timer.measure("export_ms"):
            files = []
            for doc in docs:
                storage.save_export(bundle_id, doc["doc_type"], doc["markdown"])
                files.append({"doc_type": doc["doc_type"], "path": storage.get_export_path(bundle_id, doc["doc_type"])})
            export_dir = storage.get_export_dir(bundle_id)

        _apply_generate_state(request, result, template_version)
        request.state.export_ms = export_timer.durations_ms.get("export_ms")

        log_event_data = _build_generate_log_event(request, result, request_id, template_version)
        log_event_data["export_ms"] = request.state.export_ms
        log_event(logger, log_event_data)

        metadata = result["metadata"]
        return GenerateExportResponse(
            request_id=request_id,
            bundle_id=bundle_id,
            title=payload.title,
            provider=metadata["provider"],
            schema_version=metadata["schema_version"],
            cache_hit=metadata["cache_hit"],
            export_dir=str(export_dir),
            files=files,
        )

    @app.post(
        "/ops/investigate",
        response_model=OpsInvestigateResponse,
        dependencies=[Depends(require_ops_key)],
    )
    def investigate_ops(payload: OpsInvestigateRequest, request: Request) -> OpsInvestigateResponse:
        request_id = request.state.request_id
        stage = payload.stage or configured_stage
        result = ops_service.investigate(
            window_minutes=payload.window_minutes,
            reason=payload.reason,
            stage=stage,
            request_id=request_id,
            force=payload.force,
        )
        request.state.maintenance = is_maintenance_mode()
        log_event(
            logger,
            {
                "event": "ops.investigate.completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 200,
                "stage": stage,
                "incident_id": result["incident_id"],
                "window_minutes": payload.window_minutes,
            },
        )
        return OpsInvestigateResponse(**result)

    return app


app = create_app()

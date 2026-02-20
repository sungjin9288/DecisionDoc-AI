import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import install_exception_handlers
from app.auth.api_key import API_KEY_HEADER, get_allowed_api_keys, require_api_key
from app.maintenance.mode import is_maintenance_mode, require_not_maintenance
from app.middleware.observability import install_observability_middleware
from app.middleware.request_id import install_request_id_middleware
from app.observability.logging import log_event, setup_logging
from app.observability.timing import Timer
from app.schemas import GenerateExportResponse, GenerateRequest, GenerateResponse, HealthResponse
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


def create_app() -> FastAPI:
    load_dotenv()
    setup_logging()
    environment = os.getenv("DECISIONDOC_ENV", "dev").lower()
    if environment == "prod" and not get_allowed_api_keys():
        raise RuntimeError("An API key is required when DECISIONDOC_ENV=prod.")

    configured_provider = os.getenv("DECISIONDOC_PROVIDER", "mock").lower()
    template_version = os.getenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    template_dir = Path(__file__).resolve().parent / "templates" / template_version
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    storage = get_storage()
    service = GenerationService(provider_factory=get_provider, template_dir=template_dir, data_dir=data_dir, storage=storage)

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
        docs = result["docs"]

        request.state.provider = result["metadata"]["provider"]
        request.state.template_version = template_version
        request.state.schema_version = result["metadata"]["schema_version"]
        request.state.cache_hit = result["metadata"]["cache_hit"]
        timings = result["metadata"].get("timings_ms", {})
        request.state.provider_ms = timings.get("provider_ms")
        request.state.render_ms = timings.get("render_ms")
        request.state.lints_ms = timings.get("lints_ms")
        request.state.validator_ms = timings.get("validator_ms")

        log_event(
            logger,
            {
                "event": "generate.completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 200,
                "provider": result["metadata"]["provider"],
                "template_version": template_version,
                "schema_version": result["metadata"]["schema_version"],
                "cache_hit": result["metadata"]["cache_hit"],
                "provider_ms": request.state.provider_ms,
                "render_ms": request.state.render_ms,
                "lints_ms": request.state.lints_ms,
                "validator_ms": request.state.validator_ms,
            },
        )
        return GenerateResponse(
            request_id=request_id,
            bundle_id=result["metadata"]["bundle_id"],
            title=payload.title,
            provider=result["metadata"]["provider"],
            schema_version=result["metadata"]["schema_version"],
            cache_hit=result["metadata"]["cache_hit"],
            docs=docs,
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

        request.state.provider = result["metadata"]["provider"]
        request.state.template_version = template_version
        request.state.schema_version = result["metadata"]["schema_version"]
        request.state.cache_hit = result["metadata"]["cache_hit"]
        timings = result["metadata"].get("timings_ms", {})
        request.state.provider_ms = timings.get("provider_ms")
        request.state.render_ms = timings.get("render_ms")
        request.state.lints_ms = timings.get("lints_ms")
        request.state.validator_ms = timings.get("validator_ms")
        request.state.export_ms = export_timer.durations_ms.get("export_ms")

        log_event(
            logger,
            {
                "event": "generate.completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 200,
                "provider": result["metadata"]["provider"],
                "template_version": template_version,
                "schema_version": result["metadata"]["schema_version"],
                "cache_hit": result["metadata"]["cache_hit"],
                "provider_ms": request.state.provider_ms,
                "render_ms": request.state.render_ms,
                "lints_ms": request.state.lints_ms,
                "validator_ms": request.state.validator_ms,
                "export_ms": request.state.export_ms,
            },
        )
        return GenerateExportResponse(
            request_id=request_id,
            bundle_id=bundle_id,
            title=payload.title,
            provider=result["metadata"]["provider"],
            schema_version=result["metadata"]["schema_version"],
            cache_hit=result["metadata"]["cache_hit"],
            export_dir=str(export_dir),
            files=files,
        )

    return app


app = create_app()

import os
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.exception_handlers import install_exception_handlers
from app.auth.api_key import API_KEY_HEADER, get_allowed_api_keys
from app.config import (
    APP_VERSION,
    is_procurement_copilot_enabled,
    get_voice_brief_api_base_url,
    get_voice_brief_api_bearer_token,
    get_voice_brief_timeout_seconds,
    is_enabled,
)
from app.middleware.observability import install_observability_middleware
from app.middleware.request_id import install_request_id_middleware
from app.observability.logging import setup_logging
from app.ops.factory import get_ops_service
from app.services.search_service import SearchService
from app.services.decision_council_service import DecisionCouncilService
from app.services.meeting_recording_service import MeetingRecordingService
from app.services.voice_brief_import_service import VoiceBriefImportService
from app.providers.factory import configured_provider_names, get_provider, get_provider_for_capability
from app.services.generation_service import GenerationService
from app.storage.factory import get_storage
from app.storage.approval_store import ApprovalStore
from app.storage.decision_council_store import DecisionCouncilStore
from app.storage.meeting_recording_store import MeetingRecordingStore
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.project_store import ProjectStore
from app.storage.report_workflow_store import ReportWorkflowStore
from app.storage.feedback_store import FeedbackStore
from app.storage.prompt_override_store import PromptOverrideStore
from app.storage.state_backend import get_state_backend


def _resolve_cors_allow_origins(environment: str) -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS") or os.getenv("DECISIONDOC_CORS_ALLOW_ORIGINS")
    if raw is None:
        return ["http://localhost:3000", "http://localhost:8000"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _resolve_data_dir(*, explicit_data_dir: str = "") -> Path:
    configured = explicit_data_dir.strip()
    if configured:
        return Path(configured)
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("LAMBDA_TASK_ROOT"):
        return Path(tempfile.gettempdir()) / "decisiondoc"
    configured = (os.getenv("DATA_DIR") or "").strip()
    if configured:
        return Path(configured)
    return Path("./data")



def create_app() -> FastAPI:
    explicit_data_dir = os.environ.get("DATA_DIR", "")
    load_dotenv()
    setup_logging()
    environment = os.getenv("DECISIONDOC_ENV", "dev").lower()
    # Also honour the standardized ENVIRONMENT variable (production → treat as prod)
    _std_env = os.getenv("ENVIRONMENT", "development").lower()
    if _std_env == "production":
        environment = "prod"
    if environment == "prod" and not get_allowed_api_keys():
        raise RuntimeError("An API key is required when DECISIONDOC_ENV=prod.")

    provider_names = configured_provider_names()
    template_version = os.getenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    template_dir = Path(__file__).resolve().parent / "templates" / template_version

    # Fail fast on misconfigured environment before accepting traffic.
    # provider_names supports comma-separated fallback chains (e.g. "openai,gemini,claude").
    if not template_dir.is_dir():
        raise RuntimeError(f"Template directory does not exist: {template_dir}")
    if "openai" in provider_names and not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is required when DECISIONDOC_PROVIDER=openai.")
    if "gemini" in provider_names and not os.getenv("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY is required when DECISIONDOC_PROVIDER=gemini.")
    if "claude" in provider_names and not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise RuntimeError("ANTHROPIC_API_KEY is required when DECISIONDOC_PROVIDER=claude.")
    storage_kind = os.getenv("DECISIONDOC_STORAGE", "local").lower()
    if storage_kind == "s3" and not os.getenv("DECISIONDOC_S3_BUCKET", "").strip():
        raise RuntimeError("DECISIONDOC_S3_BUCKET is required when DECISIONDOC_STORAGE=s3.")

    data_dir = _resolve_data_dir(explicit_data_dir=explicit_data_dir)
    os.environ["DATA_DIR"] = str(data_dir)
    storage = get_storage()
    state_backend = get_state_backend(data_dir=data_dir)

    # ── Multi-tenant setup ──────────────────────────────────────────────────
    from app.storage.tenant_store import TenantStore, migrate_legacy_data
    from app.middleware.tenant import install_tenant_middleware
    _tenant_store = TenantStore(data_dir, backend=state_backend)
    _tenant_store.ensure_system_tenant()
    migrate_legacy_data(data_dir)

    feedback_store = FeedbackStore(data_dir=data_dir)
    _prompt_override_store = PromptOverrideStore(data_dir=data_dir)
    from app.eval.eval_store import EvalStore as _EvalStore
    _eval_store = _EvalStore(data_dir)
    _search_service = SearchService()
    from app.storage.finetune_store import FineTuneStore as _FineTuneStore
    _finetune_store = _FineTuneStore(data_dir)
    procurement_store = ProcurementDecisionStore(base_dir=str(data_dir), backend=state_backend)
    decision_council_store = DecisionCouncilStore(base_dir=str(data_dir), backend=state_backend)
    procurement_copilot_enabled = is_procurement_copilot_enabled()

    def _generation_provider_factory():
        if os.getenv("DECISIONDOC_PROVIDER_GENERATION", "").strip():
            return get_provider_for_capability("generation")
        return get_provider()

    service = GenerationService(
        provider_factory=_generation_provider_factory,
        template_dir=template_dir,
        data_dir=data_dir,
        storage=storage,
        procurement_store=procurement_store,
        decision_council_store=decision_council_store,
        procurement_copilot_enabled=procurement_copilot_enabled,
        feedback_store=feedback_store,
        eval_store=_eval_store,
        search_service=_search_service,
        finetune_store=_finetune_store,
    )
    decision_council_service = DecisionCouncilService(
        decision_council_store=decision_council_store,
    )
    ops_service = get_ops_service()
    approval_store = ApprovalStore(base_dir=str(data_dir), backend=state_backend)
    project_store = ProjectStore(base_dir=str(data_dir), backend=state_backend)
    report_workflow_store = ReportWorkflowStore(base_dir=str(data_dir), backend=state_backend)
    meeting_recording_store = MeetingRecordingStore(base_dir=str(data_dir), backend=state_backend)
    voice_brief_base_url = get_voice_brief_api_base_url()
    voice_brief_import_service = (
        VoiceBriefImportService(
            base_url=voice_brief_base_url,
            bearer_token=get_voice_brief_api_bearer_token(),
            timeout_seconds=get_voice_brief_timeout_seconds(),
        )
        if voice_brief_base_url
        else None
    )
    meeting_recording_service = MeetingRecordingService(
        recording_store=meeting_recording_store,
        project_store=project_store,
        generation_service=service,
    )
    from app.services.report_workflow_service import ReportWorkflowService
    report_workflow_service = ReportWorkflowService(
        store=report_workflow_store,
        provider_factory=lambda: get_provider_for_capability("generation"),
    )

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        """FastAPI lifespan: drain background eval executor on shutdown."""
        yield
        if os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("LAMBDA_TASK_ROOT"):
            return
        from app.services.generation_service import _eval_executor
        _shutdown_thread = threading.Thread(
            target=lambda: _eval_executor.shutdown(wait=True, cancel_futures=False),
            daemon=True,
            name="eval-executor-drain",
        )
        _shutdown_thread.start()
        _shutdown_thread.join(timeout=10)

    app = FastAPI(
        title="DecisionDoc AI",
        version=APP_VERSION,
        lifespan=_lifespan,
        docs_url=None if environment == "prod" else "/docs",
        redoc_url=None if environment == "prod" else "/redoc",
        openapi_url=None if environment == "prod" else "/openapi.json",
    )
    cors_enabled = is_enabled(os.getenv("DECISIONDOC_CORS_ENABLED", "0"))
    if cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_resolve_cors_allow_origins(environment),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Session-ID", API_KEY_HEADER],
        )
    install_observability_middleware(app)
    install_request_id_middleware(app)
    install_exception_handlers(app)
    install_tenant_middleware(app, _tenant_store)
    from app.middleware.auth import install_auth_middleware
    install_auth_middleware(app)
    from app.middleware.audit import install_audit_middleware
    install_audit_middleware(app)
    from app.middleware.billing import install_billing_middleware
    install_billing_middleware(app)
    from app.middleware.rate_limit import install_rate_limit_middleware
    install_rate_limit_middleware(app)
    from app.middleware.security_headers import install_security_headers_middleware
    install_security_headers_middleware(app)

    # ── Store shared dependencies on app.state for router access ─────────
    app.state.service = service
    app.state.template_version = template_version
    app.state.approval_store = approval_store
    app.state.report_workflow_store = report_workflow_store
    app.state.report_workflow_service = report_workflow_service
    app.state.procurement_store = procurement_store
    app.state.decision_council_store = decision_council_store
    app.state.decision_council_service = decision_council_service
    app.state.procurement_copilot_enabled = procurement_copilot_enabled
    app.state.project_store = project_store
    app.state.meeting_recording_store = meeting_recording_store
    app.state.meeting_recording_service = meeting_recording_service
    app.state.voice_brief_import_service = voice_brief_import_service
    app.state.feedback_store = feedback_store
    app.state.prompt_override_store = _prompt_override_store
    app.state.eval_store = _eval_store
    app.state.search_service = _search_service
    app.state.finetune_store = _finetune_store
    app.state.ops_service = ops_service
    app.state.tenant_store = _tenant_store
    app.state.data_dir = data_dir
    app.state.storage = storage
    app.state.state_backend = state_backend
    app.state.environment = environment
    from app.services.event_bus import get_event_bus
    app.state.event_bus = get_event_bus()

    # ── Register APIRouters ───────────────────────────────────────────────
    from app.routers.auth import router as auth_router
    from app.routers.approvals import router as approvals_router
    from app.routers.projects import router as projects_router
    from app.routers.billing import router as billing_router
    from app.routers.sso import router as sso_router
    from app.routers.notifications import router as notifications_router
    from app.routers.messages import router as messages_router
    from app.routers.styles import router as styles_router
    from app.routers.dashboard import router as dashboard_router
    from app.routers.history import router as history_router
    from app.routers.finetune import router as finetune_router
    from app.routers.admin import router as admin_router
    from app.routers.eval import router as eval_router
    from app.routers.audit import router as audit_router
    from app.routers.local_llm import router as local_llm_router
    from app.routers.g2b import router as g2b_router
    from app.routers.report_workflows import router as report_workflows_router

    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(projects_router)
    app.include_router(billing_router)
    app.include_router(sso_router)
    app.include_router(notifications_router)
    app.include_router(messages_router)
    app.include_router(styles_router)
    app.include_router(dashboard_router)
    app.include_router(history_router)
    app.include_router(finetune_router)
    app.include_router(admin_router)
    app.include_router(eval_router)
    app.include_router(audit_router)
    app.include_router(local_llm_router)
    app.include_router(g2b_router)
    app.include_router(report_workflows_router)
    from app.routers.generate import router as generate_router
    from app.routers.health import router as health_router
    from app.routers.templates import router as templates_router
    from app.routers.knowledge import router as knowledge_router
    from app.routers.events import router as events_router
    app.include_router(generate_router)
    app.include_router(health_router)
    app.include_router(templates_router)
    app.include_router(knowledge_router)
    app.include_router(events_router)

    # Mount static files (Web UI).
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

    @app.api_route("/", methods=["GET", "HEAD"])
    async def root():
        """Serve the Web UI index.html (PWA entry point)."""
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return {"status": "DecisionDoc AI API", "docs": "/docs"}
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.api_route("/favicon.ico", methods=["GET", "HEAD"])
    async def serve_favicon():
        """Serve the favicon without authentication to avoid browser console noise."""
        from fastapi.responses import FileResponse as _FR

        svg_icon = static_dir / "icons" / "icon.svg"
        png_icon = static_dir / "icons" / "icon-192.png"
        if svg_icon.exists():
            return _FR(str(svg_icon), media_type="image/svg+xml")
        if png_icon.exists():
            return _FR(str(png_icon), media_type="image/png")
        raise HTTPException(404, "favicon not found")

    @app.api_route("/manifest.json", methods=["GET", "HEAD"])
    async def serve_manifest():
        """Serve the PWA Web App Manifest."""
        from fastapi.responses import FileResponse as _FR
        path = static_dir / "manifest.json"
        if path.exists():
            return _FR(str(path), media_type="application/manifest+json")
        raise HTTPException(404, "manifest.json not found")

    @app.api_route("/sw.js", methods=["GET", "HEAD"])
    async def serve_sw():
        """Serve the Service Worker (must be at root scope)."""
        from fastapi.responses import FileResponse as _FR
        path = static_dir / "sw.js"
        if path.exists():
            return _FR(
                str(path),
                media_type="application/javascript",
                headers={"Service-Worker-Allowed": "/"},
            )
        raise HTTPException(404, "sw.js not found")

    @app.api_route("/offline.html", methods=["GET", "HEAD"])
    async def serve_offline():
        """Serve the PWA offline fallback page."""
        from fastapi.responses import FileResponse as _FR
        path = static_dir / "offline.html"
        if path.exists():
            return _FR(str(path), media_type="text/html")
        raise HTTPException(404, "offline.html not found")

    @app.get("/bundles")
    def list_bundle_types(
        request: Request,
        q: str | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """Return all available document bundle types for the UI selection screen.

        Query parameters:
          - q: keyword search (filters by id, name_ko, name_en, description_ko)
          - category: filter by category (e.g. 'tech', 'business', 'public')
        """
        from app.bundle_catalog.registry import list_bundles
        from app.ai_profiles.catalog import effective_bundle_ids_for_request
        all_bundles = list_bundles()
        effective_bundle_ids = effective_bundle_ids_for_request(request)
        all_bundles = [b for b in all_bundles if b["id"] in effective_bundle_ids]

        # Keyword search filter
        if q:
            q_lower = q.lower()
            all_bundles = [
                b for b in all_bundles
                if q_lower in (b.get("id") or "").lower()
                or q_lower in (b.get("name_ko") or "").lower()
                or q_lower in (b.get("name_en") or "").lower()
                or q_lower in (b.get("description_ko") or "").lower()
            ]

        # Category filter
        if category:
            all_bundles = [
                b for b in all_bundles
                if (b.get("category") or "").lower() == category.lower()
            ]

        return all_bundles

    @app.get("/bundles/{bundle_id}")
    def get_bundle_detail(bundle_id: str, request: Request) -> dict:
        """Return detailed information for a specific bundle type."""
        from app.bundle_catalog.registry import BUNDLE_REGISTRY
        from app.ai_profiles.catalog import effective_bundle_ids_for_request
        if bundle_id not in BUNDLE_REGISTRY:
            raise HTTPException(status_code=404, detail=f"번들을 찾을 수 없습니다: {bundle_id}")
        if bundle_id not in effective_bundle_ids_for_request(request):
            raise HTTPException(status_code=404, detail=f"번들을 찾을 수 없습니다: {bundle_id}")
        spec = BUNDLE_REGISTRY[bundle_id]
        metadata = spec.ui_metadata()

        # Add extra detail fields
        metadata["doc_schema_keys"] = [
            {"doc_key": doc.key, "json_schema_keys": list(doc.json_schema.keys())}
            for doc in spec.docs
        ]
        return metadata

    return app


# ── SSO helper functions ───────────────────────────────────────────────────────

def _provision_sso_user(tenant_id: str, username: str, display_name: str, email: str, role: str):
    """Create or update SSO user on first login."""
    from app.storage.user_store import get_user_store, UserRole
    usr_store = get_user_store(tenant_id)
    user = usr_store.get_by_username(tenant_id, username)
    if user is None:
        import secrets as _secrets
        random_pw = _secrets.token_urlsafe(32)
        try:
            user_role = UserRole(role) if role in ("admin", "member", "viewer") else UserRole.MEMBER
        except ValueError:
            user_role = UserRole.MEMBER
        user = usr_store.create(
            tenant_id=tenant_id,
            username=username,
            display_name=display_name or username,
            email=email,
            password=random_pw,
            role=user_role,
        )
    return user


def _create_jwt_for_user(user) -> str:
    """Create JWT token for a provisioned user."""
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta
    from app.config import get_jwt_secret_key
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "tenant_id": user.tenant_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return pyjwt.encode(payload, get_jwt_secret_key(), algorithm="HS256")


def _mask_sso_secrets(d: dict) -> None:
    """Replace secret fields with '***' for safe client response."""
    SECRET_FIELDS = {"bind_password", "client_secret", "sp_private_key"}
    for k, v in list(d.items()):
        if k in SECRET_FIELDS and v:
            d[k] = "***"
        elif isinstance(v, dict):
            _mask_sso_secrets(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _mask_sso_secrets(item)


def _update_ldap_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "bind_password" and v and v != "***":
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_saml_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "sp_private_key" and v and v != "***":
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_gcloud_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "client_secret" and v and v != "***":
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


app = create_app()

"""app/middleware/billing.py — Usage limit enforcement middleware."""

from __future__ import annotations

import asyncio
import logging
import re
import threading

from fastapi import Request
from fastapi.responses import JSONResponse

_log = logging.getLogger("decisiondoc.billing")

METERED_ENDPOINTS = {
    "POST /api/agent/document-ops/run",
    "POST /admin/expand-bundles",
    "POST /attachments/parse-rfp",
    "POST /generate",
    "POST /generate/docx",
    "POST /generate/excel",
    "POST /generate/export",
    "POST /generate/from-pdf",
    "POST /generate/hwp",
    "POST /generate/pdf",
    "POST /generate/pptx",
    "POST /generate/refine",
    "POST /generate/review",
    "POST /generate/rewrite-section",
    "POST /generate/summary",
    "POST /generate/stream",
    "POST /generate/sketch",
    "POST /generate/translate",
    "POST /generate/visual-assets",
    "POST /generate/with-attachments",
    "POST /generate/from-documents",
}
_METERED_PATH_PATTERNS = (
    re.compile(r"^POST /styles/[^/]+/analyze$"),
    re.compile(
        r"^POST /projects/[^/]+/recordings/[^/]+/"
        r"(?:generate-documents|transcribe)$"
    ),
    re.compile(
        r"^POST /report-workflows/[^/]+/"
        r"(?:develop-quality/preview|planning/generate|slides/generate|visual-assets/generate)$"
    ),
)
_lock_registry_guard = threading.Lock()
_admission_locks: dict[str, threading.Lock] = {}


def is_metered_endpoint(method: str, path: str) -> bool:
    endpoint_key = f"{method.upper()} {path}"
    return endpoint_key in METERED_ENDPOINTS or any(
        pattern.fullmatch(endpoint_key) for pattern in _METERED_PATH_PATTERNS
    )


def _admission_lock(tenant_id: str) -> threading.Lock:
    with _lock_registry_guard:
        return _admission_locks.setdefault(tenant_id, threading.Lock())


def _release_lock_after_worker(
    lock: threading.Lock,
    worker_done: threading.Event,
) -> None:
    if worker_done.is_set():
        lock.release()
        return

    def _wait_and_release() -> None:
        worker_done.wait()
        lock.release()

    threading.Thread(
        target=_wait_and_release,
        daemon=True,
        name="billing-admission-release",
    ).start()


async def _acquire_thread_lock(lock: threading.Lock) -> None:
    """Acquire a thread lock without orphaning it when the task is cancelled."""
    loop = asyncio.get_running_loop()
    acquired = loop.create_future()
    cancelled = threading.Event()
    ownership_transferred = threading.Event()

    def _finish_acquire() -> None:
        if cancelled.is_set() or acquired.cancelled():
            lock.release()
        elif not acquired.done():
            ownership_transferred.set()
            acquired.set_result(None)

    def _wait_for_lock() -> None:
        lock.acquire()
        if cancelled.is_set():
            lock.release()
            return
        try:
            loop.call_soon_threadsafe(_finish_acquire)
        except RuntimeError:
            lock.release()

    threading.Thread(
        target=_wait_for_lock,
        daemon=True,
        name="billing-admission-acquire",
    ).start()
    try:
        await acquired
    except asyncio.CancelledError:
        cancelled.set()
        if ownership_transferred.is_set():
            lock.release()
        raise


async def acquire_billing_admission(
    request: Request,
) -> tuple[threading.Lock | None, JSONResponse | None]:
    """Validate one tenant's limit and retain its finite-plan admission lock."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return None, None

    lock = _admission_lock(tenant_id)
    await _acquire_thread_lock(lock)
    try:
        from app.storage.billing_store import get_billing_store
        from app.storage.usage_store import UsageStore

        data_dir = getattr(request.app.state, "data_dir", None)
        state_backend = getattr(request.app.state, "state_backend", None)
        billing = get_billing_store(
            tenant_id,
            data_dir=data_dir,
            backend=state_backend,
        )
        usage = UsageStore(
            data_dir,
            tenant_id=tenant_id,
            backend=state_backend,
        )

        account, plan = billing.get_account_and_plan()
        limit_check = usage.check_limit(plan)

        if (
            plan.plan_id != "enterprise"
            and account.status != "trialing"
            and not limit_check["within_limit"]
        ):
            lock.release()
            return None, JSONResponse(
                status_code=402,
                content={
                    "error": "사용량 한도를 초과했습니다.",
                    "code": "LIMIT_EXCEEDED",
                    "plan": plan.plan_id,
                    "limit": limit_check["generations_limit"],
                    "used": limit_check["generations_used"],
                    "upgrade_url": "/billing/upgrade",
                },
            )

        if (
            plan.plan_id != "enterprise"
            and account.status != "trialing"
            and limit_check["percent_used"] >= 80
        ):
            request.state.usage_warning = {
                "percent_used": limit_check["percent_used"],
                "generations_remaining": max(
                    0,
                    limit_check["generations_limit"]
                    - limit_check["generations_used"],
                ),
            }
        if plan.plan_id == "enterprise" or account.status == "trialing":
            lock.release()
            return None, None
        return lock, None
    except Exception as exc:
        lock.release()
        _log.error("[BillingMiddleware] Unable to verify billing state: %s", exc)
        return None, JSONResponse(
            status_code=503,
            content={
                "error": "결제 상태를 확인할 수 없습니다.",
                "code": "BILLING_STATE_UNAVAILABLE",
            },
        )


async def billing_middleware(request: Request, call_next):
    """Check usage limits before allowing generation requests."""
    path = request.url.path
    if not is_metered_endpoint(request.method, path):
        return await call_next(request)

    lock, rejection = await acquire_billing_admission(request)
    if rejection is not None:
        return rejection
    if lock is None:
        return await call_next(request)

    release_lock = True
    try:
        response = await call_next(request)
        if path == "/generate/stream" and response.status_code < 400:
            body_iterator = response.body_iterator

            async def _locked_stream():
                try:
                    async for chunk in body_iterator:
                        yield chunk
                finally:
                    worker_done = getattr(
                        request.state,
                        "billing_stream_worker_done",
                        None,
                    )
                    if isinstance(worker_done, threading.Event):
                        _release_lock_after_worker(lock, worker_done)
                    else:
                        lock.release()

            response.body_iterator = _locked_stream()
            release_lock = False
        return response
    finally:
        if release_lock:
            worker_done = getattr(
                request.state,
                "billing_provider_worker_done",
                None,
            )
            if isinstance(worker_done, threading.Event):
                _release_lock_after_worker(lock, worker_done)
            else:
                lock.release()


def install_billing_middleware(app) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=billing_middleware)

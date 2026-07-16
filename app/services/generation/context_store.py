"""Generation request context tracking and background eval executor.

Thread-local generation context capture, a cross-request context cache used
by the /feedback endpoint for fine-tune collection, usage-event recording,
and the bounded background thread pool for quality eval tasks.
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from app.tenant import require_tenant_id

if TYPE_CHECKING:
    from fastapi import Request

    from app.providers.base import Provider
    from app.storage.state_backend import StateBackend

_log = logging.getLogger("decisiondoc.generate")
_DECISION_COUNCIL_APPLIED_BUNDLE_IDS = {
    "bid_decision_kr",
    "proposal_kr",
}
def _record_usage_sync(
    tenant_id: str,
    user_id: str,
    bundle_id: str,
    request_id: str,
    model: str,
    tokens_input: int,
    tokens_output: int,
    data_dir: Path,
    state_backend: "StateBackend | None" = None,
    event_type: str = "doc.generate",
) -> None:
    """Record a usage event against the same state authority as the request."""
    from app.storage.usage_store import UsageStore, UsageEvent
    from app.storage.billing_store import get_billing_store
    import uuid as _uuid
    from datetime import datetime as _datetime, timezone as _timezone

    plan = get_billing_store(
        tenant_id,
        data_dir=data_dir,
        backend=state_backend,
    ).get_plan()
    tokens_total = tokens_input + tokens_output
    cost = (tokens_total / 1000) * plan.price_per_1k_tokens if tokens_total > 0 else 0.0

    event = UsageEvent(
        event_id=str(_uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        timestamp=_datetime.now(_timezone.utc).isoformat(),
        event_type=event_type,
        bundle_id=bundle_id,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_total=tokens_total,
        cost_usd=cost,
        model=model,
        request_id=request_id,
    )
    UsageStore(
        data_dir,
        tenant_id=tenant_id,
        backend=state_backend,
    ).record(event)


def record_direct_provider_usage(
    request: "Request",
    provider: "Provider",
    *,
    bundle_id: str,
    event_type: str = "doc.generate",
    extra_tokens: dict[str, int] | None = None,
) -> None:
    """Persist usage for a route that calls a provider outside GenerationService."""
    consume_usage = getattr(provider, "consume_usage_tokens", None)
    tokens = consume_usage() if callable(consume_usage) else {}
    tokens = tokens or {}
    extra_tokens = extra_tokens or {}
    _record_usage_sync(
        tenant_id=getattr(request.state, "tenant_id", "system") or "system",
        user_id=getattr(request.state, "user_id", "") or "",
        bundle_id=bundle_id,
        request_id=request.state.request_id,
        model=provider.name,
        tokens_input=(tokens.get("prompt_tokens", 0) or 0)
        + (extra_tokens.get("prompt_tokens", 0) or 0),
        tokens_output=(tokens.get("output_tokens", 0) or 0)
        + (extra_tokens.get("output_tokens", 0) or 0),
        data_dir=request.app.state.data_dir,
        state_backend=request.app.state.state_backend,
        event_type=event_type,
    )


def record_named_provider_usage(
    request: "Request",
    *,
    model: str,
    bundle_id: str,
    event_type: str = "doc.generate",
) -> None:
    """Persist a zero-token event when a service owns the provider instance."""
    _record_usage_sync(
        tenant_id=getattr(request.state, "tenant_id", "system") or "system",
        user_id=getattr(request.state, "user_id", "") or "",
        bundle_id=bundle_id,
        request_id=request.state.request_id,
        model=model,
        tokens_input=0,
        tokens_output=0,
        data_dir=request.app.state.data_dir,
        state_backend=request.app.state.state_backend,
        event_type=event_type,
    )


# ── Fine-tune context capture ─────────────────────────────────────────────────
# Thread-local for capturing generation context within a single request.
_generation_context: threading.local = threading.local()

# In-memory cross-request context cache: request_id → (context dict, timestamp).
# Used by the /feedback endpoint (a separate request) to find the original
# system_prompt + output for Trigger A fine-tune collection.
_ctx_lock: threading.Lock = threading.Lock()
_recent_generation_contexts: dict[tuple[str, str], tuple[dict, float]] = {}
_CTX_MAX_SIZE = 500   # evict oldest entries beyond this limit
_CTX_TTL_SECONDS = 3600  # 1 hour — stale entries expire regardless of size


def _store_generation_context(
    request_id: str,
    ctx: dict,
    *,
    tenant_id: str,
) -> None:
    """Store ctx with timestamp; evict expired + oldest-over-limit entries."""
    tenant_id = require_tenant_id(tenant_id)
    with _ctx_lock:
        now = time.time()
        # Purge expired entries first
        expired = [k for k, (_, ts) in _recent_generation_contexts.items()
                   if now - ts > _CTX_TTL_SECONDS]
        for k in expired:
            del _recent_generation_contexts[k]
        # Evict oldest if still at capacity
        if len(_recent_generation_contexts) >= _CTX_MAX_SIZE:
            oldest = min(_recent_generation_contexts.items(), key=lambda x: x[1][1])
            del _recent_generation_contexts[oldest[0]]
        _recent_generation_contexts[(tenant_id, request_id)] = (ctx, now)


def get_generation_context(
    request_id: str,
    *,
    tenant_id: str,
) -> dict | None:
    """Return stored generation context for a request_id, or None if missing/expired."""
    tenant_id = require_tenant_id(tenant_id)
    key = (tenant_id, request_id)
    with _ctx_lock:
        entry = _recent_generation_contexts.get(key)
        if entry is None:
            return None
        ctx, ts = entry
        if time.time() - ts > _CTX_TTL_SECONDS:
            del _recent_generation_contexts[key]
            return None
        return ctx


# ── Background eval executor ──────────────────────────────────────────────────
# Bounded thread pool for background quality eval tasks.
# Use shutdown(wait=True) during FastAPI lifespan to drain in-flight tasks.
_eval_executor: concurrent.futures.ThreadPoolExecutor = (
    concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="eval")
)


def _eval_done_callback(future: concurrent.futures.Future) -> None:  # type: ignore[type-arg]
    """Log any unhandled exception from a background eval task."""
    exc = future.exception()
    if exc is not None:
        _log.error("[Eval] Background eval task raised an exception: %s", exc, exc_info=exc)

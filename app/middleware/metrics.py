"""
Prometheus metrics collection middleware.
Gracefully degrades if prometheus-client is not installed.
"""
from __future__ import annotations

import re
import time
import logging

_log = logging.getLogger("decisiondoc.metrics")

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        CONTENT_TYPE_LATEST,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True

    REQUEST_COUNT = Counter(
        "decisiondoc_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code", "tenant_id"],
    )
    REQUEST_LATENCY = Histogram(
        "decisiondoc_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    )
    ACTIVE_REQUESTS = Gauge(
        "decisiondoc_active_requests",
        "Number of in-flight HTTP requests",
    )
    GENERATION_COUNT = Counter(
        "decisiondoc_generations_total",
        "Total document generation attempts",
        ["bundle_id", "tenant_id", "status"],
    )
    AUTH_FAILURES = Counter(
        "decisiondoc_auth_failures_total",
        "Authentication / authorisation failures",
        ["reason"],
    )

except ImportError:
    PROMETHEUS_AVAILABLE = False
    _log.info("[Metrics] prometheus-client not installed — metrics disabled")


# ── Path normalisation ────────────────────────────────────────────────────────

_UUID_RE = re.compile(r"/[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}", re.I)
_SHORT_ID_RE = re.compile(r"/[0-9a-f\-]{8,36}")


def _normalize_path(path: str) -> str:
    """Replace UUIDs and long hex IDs with ``/{id}`` to limit cardinality."""
    path = _UUID_RE.sub("/{id}", path)
    path = _SHORT_ID_RE.sub("/{id}", path)
    return path


# ── Middleware ────────────────────────────────────────────────────────────────

# Paths excluded from instrumentation (probes + metrics itself)
_SKIP_PATHS = frozenset({"/metrics", "/health/live", "/health/ready", "/health"})


async def metrics_middleware(request, call_next):  # type: ignore[override]
    """ASGI middleware that records Prometheus metrics for every HTTP request."""
    if not PROMETHEUS_AVAILABLE or request.url.path in _SKIP_PATHS:
        return await call_next(request)

    start = time.perf_counter()
    ACTIVE_REQUESTS.inc()
    try:
        response = await call_next(request)
    finally:
        ACTIVE_REQUESTS.dec()

    duration = time.perf_counter() - start
    tenant_id = getattr(request.state, "tenant_id", "unknown") or "unknown"
    path = _normalize_path(request.url.path)

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=path,
        status_code=str(response.status_code),
        tenant_id=tenant_id,
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=path,
    ).observe(duration)

    # Track auth / rate-limit failures for alerting
    if response.status_code == 401:
        AUTH_FAILURES.labels(reason="unauthorized").inc()
    elif response.status_code == 403:
        AUTH_FAILURES.labels(reason="forbidden").inc()
    elif response.status_code == 429:
        AUTH_FAILURES.labels(reason="rate_limited").inc()

    return response


def install_metrics_middleware(app) -> None:  # type: ignore[type-arg]
    """Register the metrics middleware on a FastAPI app."""
    app.middleware("http")(metrics_middleware)


# ── Scrape endpoint helper ────────────────────────────────────────────────────

def get_metrics_response():  # type: ignore[return]
    """Return a ``Response`` with Prometheus text format, or ``None`` if unavailable."""
    if not PROMETHEUS_AVAILABLE:
        return None
    from fastapi.responses import Response  # local import to avoid circular
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── Instrumentation helpers for other services ───────────────────────────────

def record_generation(
    bundle_id: str,
    tenant_id: str,
    status: str,
    duration: float = 0.0,
) -> None:
    """Increment the generation counter.  Call from GenerationService."""
    if not PROMETHEUS_AVAILABLE:
        return
    GENERATION_COUNT.labels(
        bundle_id=bundle_id,
        tenant_id=tenant_id,
        status=status,
    ).inc()

import logging
import time

from fastapi import FastAPI, Request

from app.observability.logging import log_event

logger = logging.getLogger("decisiondoc.observability")


def install_observability_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):  # type: ignore[override]
        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", "unknown-request-id")

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = int(round((time.perf_counter() - start) * 1000))
            failed_event = {
                "event": "request.failed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "latency_ms": latency_ms,
                "error_code": getattr(request.state, "error_code", "INTERNAL_ERROR"),
            }
            log_event(logger, failed_event)
            raise

        latency_ms = int(round((time.perf_counter() - start) * 1000))
        completed_event = {
            "event": "request.completed",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        }

        optional_keys = [
            "provider",
            "template_version",
            "maintenance",
            "schema_version",
            "cache_hit",
            "llm_prompt_tokens",
            "llm_output_tokens",
            "llm_total_tokens",
            "error_code",
            "provider_ms",
            "render_ms",
            "lints_ms",
            "validator_ms",
            "export_ms",
        ]
        for key in optional_keys:
            value = getattr(request.state, key, None)
            if value is not None:
                completed_event[key] = value

        log_event(logger, completed_event)
        return response

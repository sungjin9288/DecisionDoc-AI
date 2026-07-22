"""app/routers/events.py — Server-Sent Events (SSE) endpoint for real-time collaboration."""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.observability.logging import log_event
from app.services.auth_service import resolve_persisted_user, verify_token
from app.tenant import require_tenant_id

if TYPE_CHECKING:
    from app.storage.state_backend import StateBackend

router = APIRouter(tags=["events"])

_HEARTBEAT_INTERVAL = 15.0
_AUTH_RECHECK_INTERVAL = 15.0
_POLL_INTERVAL = 0.4


@router.get("/events")
async def sse_stream(request: Request, token: str = Query(default="")):
    """SSE endpoint. Clients connect with ?token=<jwt>.

    Streams events:
      event: notification
      event: approval_updated
      event: message_posted
      : heartbeat   (every 15s to keep connection alive)
    """
    tenant_id = _resolve_event_tenant_id(
        token,
        data_dir=getattr(request.app.state, "data_dir", None),
        backend=getattr(request.app.state, "state_backend", None),
    )

    bus = getattr(request.app.state, "event_bus", None) or _get_event_bus()
    subscription = bus.subscribe(tenant_id)

    return StreamingResponse(
        _stream_events(
            request,
            token=token,
            tenant_id=tenant_id,
            bus=bus,
            subscription=subscription,
            data_dir=getattr(request.app.state, "data_dir", None),
            backend=getattr(request.app.state, "state_backend", None),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _stream_events(
    request: Request,
    *,
    token: str,
    tenant_id: str,
    bus,
    subscription: queue.SimpleQueue,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> AsyncIterator[str]:
    last_heartbeat = time.monotonic()
    last_auth_check = last_heartbeat
    try:
        while True:
            if await request.is_disconnected():
                break

            now = time.monotonic()
            if now - last_auth_check >= _AUTH_RECHECK_INTERVAL:
                auth_state = _revalidate_event_access(
                    token,
                    tenant_id=tenant_id,
                    data_dir=data_dir,
                    backend=backend,
                )
                if auth_state != "current":
                    _log_stream_auth_close(request, tenant_id=tenant_id, reason=auth_state)
                    if auth_state == "unavailable":
                        yield (
                            'event: auth_unavailable\n'
                            'data: {"reason":"authority_unavailable","retryable":true}\n\n'
                        )
                    else:
                        yield (
                            'event: auth_revoked\n'
                            'data: {"reason":"access_invalidated","refresh_allowed":true}\n\n'
                        )
                    break
                last_auth_check = now

            try:
                item = subscription.get_nowait()
                event_type = item["event_type"]
                data = json.dumps(item["data"], ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
                last_heartbeat = time.monotonic()
            except queue.Empty:
                now = time.monotonic()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                await asyncio.sleep(_POLL_INTERVAL)
    finally:
        bus.unsubscribe(tenant_id, subscription)


def _revalidate_event_access(
    token: str,
    *,
    tenant_id: str,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> str:
    try:
        current_tenant_id = _resolve_event_tenant_id(
            token,
            data_dir=data_dir,
            backend=backend,
        )
    except HTTPException as exc:
        return "unavailable" if exc.status_code == 503 else "revoked"
    except Exception:
        logging.getLogger("decisiondoc.auth").exception(
            "[Auth] Unexpected realtime event authorization failure — failing CLOSED."
        )
        return "unavailable"
    return "current" if current_tenant_id == tenant_id else "revoked"


def _log_stream_auth_close(request: Request, *, tenant_id: str, reason: str) -> None:
    request_state = getattr(request, "state", None)
    log_event(
        logging.getLogger("decisiondoc.auth"),
        {
            "event": "auth.sse_stream_closed",
            "request_id": getattr(request_state, "request_id", None),
            "tenant_id": tenant_id,
            "reason": reason,
        },
    )


def _resolve_event_tenant_id(
    token: str,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> str:
    """Resolve an SSE subscription tenant from a valid access token."""
    if not token:
        raise _event_auth_error()

    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        raise _event_auth_error()

    try:
        tenant_id = require_tenant_id(payload.get("tenant_id"))
    except ValueError as exc:
        raise _event_auth_error() from exc

    try:
        user, _ = resolve_persisted_user(
            payload,
            data_dir=data_dir,
            backend=backend,
        )
    except Exception as exc:
        logging.getLogger("decisiondoc.auth").error(
            "[Auth] UserStore read failed for realtime events — failing CLOSED: %s",
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from exc

    if not user:
        raise _event_auth_error()
    return tenant_id


def _event_auth_error() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="A valid access token is required for realtime events.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _get_event_bus():
    from app.services.event_bus import get_event_bus
    return get_event_bus()

"""app/routers/events.py — Server-Sent Events (SSE) endpoint for real-time collaboration."""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.services.auth_service import resolve_persisted_user, verify_token
from app.tenant import require_tenant_id

if TYPE_CHECKING:
    from app.storage.state_backend import StateBackend

router = APIRouter(tags=["events"])

_HEARTBEAT_INTERVAL = 15.0   # seconds
_POLL_INTERVAL     = 0.4     # seconds


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
    q = bus.subscribe(tenant_id)

    async def generator():
        last_hb = time.monotonic()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = q.get_nowait()
                    etype = item["event_type"]
                    data = json.dumps(item["data"], ensure_ascii=False)
                    yield f"event: {etype}\ndata: {data}\n\n"
                    last_hb = time.monotonic()
                except queue.Empty:
                    now = time.monotonic()
                    if now - last_hb >= _HEARTBEAT_INTERVAL:
                        yield ": heartbeat\n\n"
                        last_hb = now
                    await asyncio.sleep(_POLL_INTERVAL)
        finally:
            bus.unsubscribe(tenant_id, q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
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

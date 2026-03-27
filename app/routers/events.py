"""app/routers/events.py — Server-Sent Events (SSE) endpoint for real-time collaboration."""
from __future__ import annotations

import asyncio
import json
import queue
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

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
    tenant_id = "system"
    try:
        if token:
            from app.services.auth_service import verify_token
            payload = verify_token(token)
            if payload:
                tenant_id = payload.get("tenant_id") or payload.get("tid") or "system"
    except Exception:
        pass

    bus = _get_event_bus()
    try:
        bus = request.app.state.event_bus
    except AttributeError:
        pass

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
                    data  = json.dumps(item["data"], ensure_ascii=False)
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


def _get_event_bus():
    from app.services.event_bus import get_event_bus
    return get_event_bus()

"""app/routers/messages.py — Team messaging endpoints.

Extracted from app/main.py.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from app.dependencies import get_tenant_id, get_user_id, get_username
from app.schemas import EditMessageRequest, PostMessageRequest

router = APIRouter(tags=["messages"])


@router.post("/messages")
async def post_message(request: Request, body: PostMessageRequest):
    """Post a team message, optionally with @mention support."""
    from app.storage.message_store import get_message_store

    tenant_id = get_tenant_id(request)
    author_id = get_user_id(request)
    author_name = get_username(request)
    msg_store = get_message_store(tenant_id)
    msg = msg_store.post(
        tenant_id=tenant_id,
        author_id=author_id,
        author_name=author_name,
        content=body.content,
        context_type=body.context_type,
        context_id=body.context_id,
    )
    try:
        from app.services.event_bus import get_event_bus
        get_event_bus().publish(
            tenant_id,
            "message_posted",
            {
                "message_id": msg.message_id,
                "context_type": msg.context_type,
                "context_id": msg.context_id,
                "author_name": author_name,
            },
        )
    except Exception:
        pass
    # Notify mentioned users (fire-and-forget)
    if msg.mentions:
        try:
            from app.services.notification_service import NotificationService

            mentioned_ids = [uid for uid in msg.mentions if uid != author_id]
            if mentioned_ids:
                await NotificationService(tenant_id).notify_mention(
                    msg, mentioned_ids, author_name
                )
        except Exception:
            pass
    return {"message": asdict(msg)}


@router.get("/messages")
async def get_thread(
    request: Request,
    context_type: str = "general",
    context_id: str = "global",
    limit: int = 50,
):
    """Retrieve messages for a given context thread."""
    from app.storage.message_store import get_message_store

    tenant_id = get_tenant_id(request)
    msg_store = get_message_store(tenant_id)
    msgs = msg_store.get_thread(tenant_id, context_type, context_id, limit=limit)
    return {"messages": [asdict(m) for m in msgs]}


@router.get("/messages/mentions")
async def get_my_mentions(request: Request, limit: int = 20):
    """Return messages where the current user is mentioned."""
    from app.storage.message_store import get_message_store

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    msg_store = get_message_store(tenant_id)
    msgs = msg_store.get_mentions(tenant_id, user_id, limit=limit)
    return {"messages": [asdict(m) for m in msgs]}


@router.get("/messages/unread-count")
async def get_messages_unread_count(request: Request, since: str = ""):
    """Return count of unread mention messages since the given ISO timestamp."""
    from app.storage.message_store import get_message_store

    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    msg_store = get_message_store(tenant_id)
    count = msg_store.get_unread_count(tenant_id, user_id, since)
    return {"unread_count": count}


@router.patch("/messages/{message_id}")
async def edit_message(request: Request, message_id: str, body: EditMessageRequest):
    """Edit a message (author only)."""
    from app.storage.message_store import get_message_store

    tenant_id = get_tenant_id(request)
    author_id = get_user_id(request)
    msg_store = get_message_store(tenant_id)
    try:
        msg = msg_store.edit(message_id, author_id, body.content)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"message": asdict(msg)}


@router.delete("/messages/{message_id}")
async def delete_message(request: Request, message_id: str):
    """Soft-delete a message (author only)."""
    from app.storage.message_store import get_message_store

    tenant_id = get_tenant_id(request)
    author_id = get_user_id(request)
    msg_store = get_message_store(tenant_id)
    try:
        msg_store.delete(message_id, author_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"message": "메시지가 삭제되었습니다."}

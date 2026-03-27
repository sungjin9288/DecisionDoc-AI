"""app/routers/notifications.py — Notification endpoints.

Extracted from app/main.py.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.dependencies import get_tenant_id, get_user_id

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def get_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
):
    """Return notifications for the current user."""
    from app.storage.notification_store import get_notification_store

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    store = get_notification_store(tenant_id)
    notifications = store.get_for_user(user_id, unread_only=unread_only, limit=limit)
    return {"notifications": [asdict(n) for n in notifications]}


@router.get("/notifications/unread-count")
async def get_unread_count(request: Request):
    """Return the count of unread notifications for the current user."""
    from app.storage.notification_store import get_notification_store

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    store = get_notification_store(tenant_id)
    count = store.get_unread_count(user_id)
    return {"count": count}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(request: Request, notification_id: str):
    """Mark a single notification as read."""
    from app.storage.notification_store import get_notification_store

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    store = get_notification_store(tenant_id)
    found = store.mark_read(notification_id, user_id)
    if not found:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    return {"message": "읽음 처리되었습니다."}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(request: Request):
    """Mark all notifications for the current user as read."""
    from app.storage.notification_store import get_notification_store

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    store = get_notification_store(tenant_id)
    count = store.mark_all_read(user_id)
    return {"updated": count}

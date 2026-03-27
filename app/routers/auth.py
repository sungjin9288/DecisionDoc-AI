"""app/routers/auth.py — Auth-related endpoints extracted from main.py.

Handles: register, login, refresh, me, change-password,
         my-data, export-my-data, withdraw, admin/users.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.dependencies import get_tenant_id
from app.schemas import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    RefreshRequest,
    UpdateUserRequest,
    WithdrawRequest,
)

logger = logging.getLogger("decisiondoc.generate")

router = APIRouter(tags=["auth"])


# ── Auth endpoints ────────────────────────────────────────────────────────


@router.post("/auth/register")
async def register_first_admin(request: Request, body: CreateUserRequest):
    """Create the first admin user when no users exist in the tenant."""
    from app.storage.user_store import get_user_store, UserRole
    from app.services.auth_service import create_access_token, create_refresh_token

    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    existing = user_store.list_by_tenant(tenant_id)
    if existing:
        raise HTTPException(403, "이미 사용자가 존재합니다. 관리자에게 초대를 요청하세요.")
    try:
        user = user_store.create(
            tenant_id=tenant_id,
            username=body.username,
            display_name=body.display_name,
            email=body.email,
            password=body.password,
            role=UserRole.ADMIN,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    user_store.update_last_login(user.user_id)
    return {
        "access_token": create_access_token(
            user.user_id, tenant_id, user.role.value, user.username
        ),
        "refresh_token": create_refresh_token(user.user_id, tenant_id),
        "message": "관리자 계정이 생성되었습니다.",
    }


@router.post("/auth/login")
async def login(request: Request, body: LoginRequest):
    """Authenticate and return access + refresh tokens."""
    from app.storage.user_store import get_user_store
    from app.services.auth_service import create_access_token, create_refresh_token

    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    user = user_store.get_by_username(tenant_id, body.username)
    if not user or not user.is_active:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    if not user_store.verify_password(user.user_id, body.password):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    user_store.update_last_login(user.user_id)
    return {
        "access_token": create_access_token(
            user.user_id, tenant_id, user.role.value, user.username
        ),
        "refresh_token": create_refresh_token(user.user_id, tenant_id),
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value,
            "avatar_color": user.avatar_color,
        },
    }


@router.post("/auth/refresh")
async def refresh_token(body: RefreshRequest):
    """Exchange a refresh token for a new access token."""
    from app.storage.user_store import get_user_store
    from app.services.auth_service import verify_token, create_access_token

    payload = verify_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "유효하지 않은 리프레시 토큰입니다.")
    user_store = get_user_store(payload["tenant_id"])
    user = user_store.get_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(401, "사용자를 찾을 수 없습니다.")
    return {
        "access_token": create_access_token(
            user.user_id, user.tenant_id, user.role.value, user.username
        )
    }


@router.get("/auth/me")
async def get_me(request: Request):
    """Return the current authenticated user's profile."""
    from app.storage.user_store import get_user_store

    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "인증이 필요합니다.")
    user = user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role.value,
        "created_at": user.created_at,
        "last_login": user.last_login,
        "avatar_color": user.avatar_color,
    }


@router.post("/auth/change-password")
async def change_password(request: Request, body: ChangePasswordRequest):
    """Change the current user's password."""
    from app.storage.user_store import get_user_store

    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "인증이 필요합니다.")
    try:
        success = user_store.change_password(
            user_id, body.old_password, body.new_password
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not success:
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다.")
    return {"message": "비밀번호가 변경되었습니다."}


# ── Personal data rights (개인정보보호법 §35, §35의2, §36) ─────────────────


@router.get("/auth/my-data")
async def get_my_data(request: Request):
    """개인정보 열람권 — 본인의 저장 데이터 반환 (개인정보보호법 §35)."""
    from datetime import datetime as _dt
    from app.storage.user_store import get_user_store

    tenant_id = get_tenant_id(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "인증이 필요합니다.")

    user_store = get_user_store(tenant_id)
    user = user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    from app.storage.audit_store import AuditStore
    audit_store = AuditStore(tenant_id)
    try:
        my_audits = audit_store.query(
            tenant_id, filters={"user_id": user_id}
        )[:100]
    except Exception:
        my_audits = []

    from app.storage.notification_store import NotificationStore
    notif_store = NotificationStore(tenant_id)
    try:
        my_notifs = notif_store.get_for_user(user_id, limit=100)
    except Exception:
        my_notifs = []

    return {
        "collected_at": _dt.now().isoformat(),
        "user_info": {
            "user_id": getattr(user, "user_id", user_id),
            "username": getattr(user, "username", ""),
            "display_name": getattr(user, "display_name", ""),
            "email": getattr(user, "email", ""),
            "role": getattr(user, "role", ""),
            "created_at": getattr(user, "created_at", ""),
            "last_login": getattr(user, "last_login", ""),
        },
        "activity_logs": [
            {
                "timestamp": a.get("timestamp", ""),
                "action": a.get("action", ""),
                "ip_address": a.get("ip_address", ""),
                "result": a.get("result", ""),
            }
            for a in my_audits
        ],
        "notifications": [
            {
                "title": getattr(n, "title", ""),
                "created_at": getattr(n, "created_at", ""),
                "is_read": getattr(n, "is_read", False),
            }
            for n in my_notifs
        ],
        "data_retention_policy": {
            "user_info": "탈퇴 시 즉시 삭제",
            "audit_logs": "1년 보존 후 삭제",
            "notifications": "90일 보존",
        },
    }


@router.post("/auth/export-my-data")
async def export_my_data(request: Request):
    """개인정보 이동권 — JSON 파일로 내보내기 (개인정보보호법 §35의2)."""
    import json as _json
    from datetime import datetime as _dt

    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "인증이 필요합니다.")

    data = await get_my_data(request)
    json_content = _json.dumps(data, ensure_ascii=False, indent=2, default=str)
    filename = f"my_data_{user_id[:8]}_{_dt.now().strftime('%Y%m%d')}.json"
    return Response(
        content=json_content.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.delete("/auth/withdraw")
async def withdraw_account(request: Request, body: WithdrawRequest):
    """회원 탈퇴 — 개인정보 삭제 처리 (개인정보보호법 §36)."""
    import uuid as _uuid
    from datetime import datetime as _dt
    from app.storage.user_store import get_user_store

    tenant_id = get_tenant_id(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "인증이 필요합니다.")

    user_store = get_user_store(tenant_id)
    user = user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # Verify password before deletion
    if not user_store.verify_password(user_id, body.password):
        raise HTTPException(status_code=400, detail="비밀번호가 올바르지 않습니다.")

    # Anonymize personal data (keep audit logs for legal compliance)
    user_store.update(
        user_id,
        display_name="탈퇴한 사용자",
        email="",
        is_active=False,
    )

    # ── Cascade: anonymize approval records that reference this user ───
    try:
        approval_store = request.app.state.approval_store
        all_approvals = approval_store.list_by_tenant(tenant_id)
        username = getattr(user, "username", user_id)
        for approval in all_approvals:
            changed: dict[str, str] = {}
            if approval.drafter == username:
                changed["drafter"] = "탈퇴한 사용자"
            if approval.reviewer == username:
                changed["reviewer"] = "탈퇴한 사용자"
            if approval.approver == username:
                changed["approver"] = "탈퇴한 사용자"
            if changed:
                approval_store.update(approval.approval_id, tenant_id=tenant_id, **changed)
    except Exception as _cascade_exc:
        logger.warning("[Withdraw] 결재 cascade 실패 (무시): %s", _cascade_exc)

    # ── Cascade: delete notifications for the withdrawn user ─────────
    try:
        from app.storage.notification_store import get_notification_store
        get_notification_store(tenant_id).delete_for_user(user_id)
    except Exception as _notif_exc:
        logger.warning("[Withdraw] 알림 삭제 실패 (무시): %s", _notif_exc)

    logger.info("[Withdraw] Cascade cleanup complete for user %s", user_id)

    # Audit log the withdrawal
    from app.storage.audit_store import AuditStore, AuditLog
    try:
        audit_store = AuditStore(tenant_id)
        audit_store.append(AuditLog(
            log_id=str(_uuid.uuid4()),
            tenant_id=tenant_id,
            timestamp=_dt.now().isoformat(),
            user_id=user_id,
            username=getattr(user, "username", user_id),
            user_role=getattr(getattr(user, "role", "member"), "value", str(getattr(user, "role", "member"))),
            ip_address=request.client.host if request.client else "unknown",
            user_agent="",
            action="user.withdraw",
            resource_type="user",
            resource_id=user_id,
            resource_name=getattr(user, "username", user_id),
            result="success",
            detail={"reason": body.reason or "사용자 요청"},
            session_id="",
        ))
    except Exception:
        pass  # Audit failure should not block withdrawal

    return {
        "message": "회원 탈퇴가 완료되었습니다. 개인정보가 삭제되었습니다.",
        "deleted_at": _dt.now().isoformat(),
        "note": "감사 로그는 법령에 따라 1년간 보존됩니다.",
    }


# ── Admin endpoints ───────────────────────────────────────────────────────


@router.get("/admin/users")
async def list_users(request: Request):
    """List all users in the tenant (admin only)."""
    from app.storage.user_store import get_user_store

    if getattr(request.state, "user_role", None) != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    users = user_store.list_by_tenant(tenant_id)
    return {"users": [
        {
            "user_id": u.user_id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "role": u.role.value,
            "is_active": u.is_active,
            "last_login": u.last_login,
            "avatar_color": u.avatar_color,
        } for u in users
    ]}


@router.post("/admin/users")
async def create_user(request: Request, body: CreateUserRequest):
    """Create a new user (admin only)."""
    from app.storage.user_store import get_user_store

    if getattr(request.state, "user_role", None) != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    try:
        user = user_store.create(
            tenant_id=tenant_id,
            username=body.username,
            display_name=body.display_name,
            email=body.email,
            password=body.password,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"user_id": user.user_id, "message": "사용자가 생성되었습니다."}


@router.patch("/admin/users/{user_id}")
async def update_user(request: Request, user_id: str, body: UpdateUserRequest):
    """Update a user's role, active status, or profile (admin only)."""
    from app.storage.user_store import get_user_store

    if getattr(request.state, "user_role", None) != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    tenant_id = get_tenant_id(request)
    user_store = get_user_store(tenant_id)
    try:
        user_store.update(user_id, **body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"message": "사용자 정보가 수정되었습니다."}

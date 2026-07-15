"""app/routers/admin/_locations.py — Location (tenant) overview + user management.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.api_key import require_api_key
from app.dependencies import require_admin

from app.routers.admin._procurement_quality_location import (
    _build_procurement_location_overview,
    _empty_procurement_location_overview,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Location (Tenant) Overview with User Counts
# ---------------------------------------------------------------------------

@router.get("/admin/locations", dependencies=[Depends(require_api_key)])
def admin_list_locations(request: Request, include_procurement: bool = False) -> list[dict]:
    """List all tenants as 'locations' with user count + usage stats. Requires admin."""
    require_admin(request)
    from app.storage.user_store import UserStore
    tenant_store = request.app.state.tenant_store
    data_dir = request.app.state.data_dir

    result = []
    for tenant in tenant_store.list_tenants():
        try:
            user_store = UserStore(
                data_dir / "tenants" / tenant.tenant_id,
                backend=request.app.state.state_backend,
            )
            users = user_store.list_users()
            user_count = len(users)
        except Exception:
            user_count = 0

        try:
            from app.eval.eval_store import get_eval_store
            eval_stats = get_eval_store(tenant.tenant_id).get_all_stats()
            gen_count = eval_stats.get("total_count", 0)
        except Exception:
            gen_count = 0

        location_summary = {
            **dataclasses.asdict(tenant),
            "user_count": user_count,
            "generation_count": gen_count,
        }
        if include_procurement:
            try:
                location_summary["procurement"] = _build_procurement_location_overview(
                    tenant.tenant_id,
                    request,
                )
            except Exception:
                location_summary["procurement"] = _empty_procurement_location_overview()
        result.append(location_summary)
    return result


@router.get("/admin/locations/{tenant_id_path}/users", dependencies=[Depends(require_api_key)])
def admin_location_users(tenant_id_path: str, request: Request) -> list[dict]:
    """List users for a specific location/tenant. Requires admin."""
    require_admin(request)
    from app.storage.user_store import UserStore
    tenant_store = request.app.state.tenant_store
    if tenant_store.get_tenant(tenant_id_path) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    data_dir = request.app.state.data_dir
    user_store = UserStore(
        data_dir / "tenants" / tenant_id_path,
        backend=request.app.state.state_backend,
    )
    users = user_store.list_users()
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "role": u.role.value,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "last_login": u.last_login,
            "avatar_color": u.avatar_color,
            "job_title": getattr(u, "job_title", ""),
            "assigned_ai_profiles": list(getattr(u, "assigned_ai_profiles", []) or []),
        }
        for u in users
    ]


@router.patch("/admin/locations/{tenant_id_path}/users/{user_id}", dependencies=[Depends(require_api_key)])
def admin_update_location_user(tenant_id_path: str, user_id: str, payload: dict, request: Request) -> dict:
    """Update a tenant user's role/profile assignment. Requires admin."""
    require_admin(request)
    from app.storage.user_store import UserStore

    tenant_store = request.app.state.tenant_store
    if tenant_store.get_tenant(tenant_id_path) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    data_dir = request.app.state.data_dir
    user_store = UserStore(
        data_dir / "tenants" / tenant_id_path,
        backend=request.app.state.state_backend,
    )
    updates: dict = {}
    for key in ("display_name", "email", "role", "is_active", "job_title", "assigned_ai_profiles"):
        if key in payload:
            updates[key] = payload[key]
    try:
        user_store.update(user_id, **updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "사용자 업무 AI 배정이 수정되었습니다."}

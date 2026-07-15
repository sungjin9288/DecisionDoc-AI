"""app/routers/admin/_tenants.py — Tenant management + per-tenant API key endpoints.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
Note: the procurement-quality-summary endpoints under /admin/tenants/{id}/...
live in _procurement_quality.py since they share its aggregation helpers.
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.api_key import require_api_key
from app.dependencies import require_admin
from app.storage.tenant_store import TenantRegistryError
from app.tenant import require_tenant_id

router = APIRouter()

# ---------------------------------------------------------------------------
# Tenant Management
# ---------------------------------------------------------------------------

@router.post("/admin/tenants")
def admin_create_tenant(payload: dict, request: Request) -> dict:
    """Create a new tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant_store = request.app.state.tenant_store
    tenant_id_val = payload.get("tenant_id", "")
    display_name_val = payload.get("display_name", "")
    if not isinstance(display_name_val, str) or not display_name_val.strip():
        raise HTTPException(status_code=422, detail="tenant_id and display_name are required.")
    display_name_val = display_name_val.strip()
    try:
        tenant_id_val = require_tenant_id(tenant_id_val)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    allowed = payload.get("allowed_bundles") or []
    try:
        tenant = tenant_store.create_tenant(
            tenant_id=tenant_id_val,
            display_name=display_name_val,
            allowed_bundles=allowed,
        )
    except TenantRegistryError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return dataclasses.asdict(tenant)


@router.get("/admin/tenants")
def admin_list_tenants(request: Request) -> list[dict]:
    """List all tenants. Accepts admin JWT or OPS key."""
    require_admin(request)
    return [dataclasses.asdict(t) for t in request.app.state.tenant_store.list_tenants()]


@router.get("/admin/tenants/{tenant_id_path}")
def admin_get_tenant(tenant_id_path: str, request: Request) -> dict:
    """Get a single tenant by ID. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    return dataclasses.asdict(tenant)


@router.patch("/admin/tenants/{tenant_id_path}")
def admin_update_tenant(tenant_id_path: str, payload: dict, request: Request) -> dict:
    """Update mutable fields of a tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    try:
        tenant = request.app.state.tenant_store.update_tenant(
            tenant_id_path,
            display_name=payload.get("display_name"),
            allowed_bundles=payload.get("allowed_bundles"),
            is_active=payload.get("is_active"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dataclasses.asdict(tenant)


@router.post("/admin/tenants/{tenant_id_path}/custom-hint")
def admin_set_custom_hint(tenant_id_path: str, payload: dict, request: Request) -> dict:
    """Set a bundle-specific custom prompt hint for a tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    bundle_id_val = payload.get("bundle_id", "").strip()
    hint_val = payload.get("hint", "").strip()
    if not bundle_id_val or not hint_val:
        raise HTTPException(status_code=422, detail="bundle_id and hint are required.")
    try:
        request.app.state.tenant_store.set_custom_hint(tenant_id_path, bundle_id_val, hint_val)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"tenant_id": tenant_id_path, "bundle_id": bundle_id_val, "hint": hint_val}


@router.delete("/admin/tenants/{tenant_id_path}/custom-hint/{bundle_id_path}")
def admin_delete_custom_hint(tenant_id_path: str, bundle_id_path: str, request: Request) -> dict:
    """Remove a bundle-specific custom prompt hint for a tenant. Accepts admin JWT or OPS key."""
    require_admin(request)
    try:
        request.app.state.tenant_store.delete_custom_hint(tenant_id_path, bundle_id_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "tenant_id": tenant_id_path, "bundle_id": bundle_id_path}


@router.get("/admin/tenants/{tenant_id_path}/stats")
def admin_tenant_stats(tenant_id_path: str, request: Request) -> dict:
    """Tenant usage statistics. Accepts admin JWT or OPS key."""
    require_admin(request)
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    try:
        from app.eval.eval_store import get_eval_store
        eval_stats = get_eval_store(tenant_id_path).get_all_stats()
    except Exception:
        eval_stats = {}
    try:
        from app.storage.feedback_store import get_feedback_store
        all_fb = get_feedback_store(tenant_id_path).get_all()
        fb_count = len(all_fb)
        avg_rating: float | None = (
            round(sum(f.get("rating", 0) for f in all_fb) / fb_count, 2)
            if all_fb else None
        )
    except Exception:
        fb_count = 0
        avg_rating = None
    return {
        "tenant": dataclasses.asdict(tenant),
        "eval": eval_stats,
        "feedback_count": fb_count,
        "avg_rating": avg_rating,
    }



# ---------------------------------------------------------------------------
# Per-Tenant API Key Management
# ---------------------------------------------------------------------------

@router.post("/admin/tenants/{tenant_id_path}/rotate-key", dependencies=[Depends(require_api_key)])
def admin_rotate_tenant_key(tenant_id_path: str, request: Request) -> dict:
    """Generate a new API key for the tenant. Key is shown ONLY in this response.
    Requires admin role."""
    require_admin(request)
    tenant_store = request.app.state.tenant_store
    if tenant_store.get_tenant(tenant_id_path) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    key = tenant_store.rotate_api_key(tenant_id_path)
    return {
        "tenant_id": tenant_id_path,
        "api_key": key,
        "note": "이 키는 지금만 표시됩니다. 안전한 곳에 저장하세요.",
    }

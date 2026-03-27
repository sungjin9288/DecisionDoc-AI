"""app/routers/templates.py — Document template CRUD endpoints.

Extracted from app/main.py. TemplateStore instances are created internally
per request — no app.state dependency required.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.api_key import require_api_key

router = APIRouter(tags=["templates"])


@router.post("/templates", dependencies=[Depends(require_api_key)])
def create_template_endpoint(payload: dict, request: Request) -> dict:
    """Save form inputs as a reusable template."""
    import uuid
    from app.storage.template_store import TemplateStore, TemplateEntry

    user_id = getattr(request.state, "user_id", "anonymous")
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"

    name = (payload.get("name") or "").strip()
    bundle_id = (payload.get("bundle_id") or "").strip()
    form_data = payload.get("form_data") or {}

    errors = []
    if not name:
        errors.append({"field": "name", "message": "템플릿 이름은 필수입니다."})
    elif len(name) > 100:
        errors.append({"field": "name", "message": "템플릿 이름은 100자 이하여야 합니다."})
    if not bundle_id:
        errors.append({"field": "bundle_id", "message": "번들 ID는 필수입니다."})

    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    from app.bundle_catalog.registry import BUNDLE_REGISTRY
    bundle_name = BUNDLE_REGISTRY[bundle_id].name_ko if bundle_id in BUNDLE_REGISTRY else bundle_id

    store = TemplateStore(tenant_id)
    entry = TemplateEntry(
        template_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        bundle_id=bundle_id,
        bundle_name=bundle_name,
        form_data=form_data,
    )
    store.add(entry)
    return {"template_id": entry.template_id, "name": name, "bundle_id": bundle_id, "created_at": entry.created_at}


@router.get("/templates", dependencies=[Depends(require_api_key)])
def list_templates_endpoint(request: Request) -> list:
    """List saved templates for current user."""
    from app.storage.template_store import TemplateStore

    user_id = getattr(request.state, "user_id", "anonymous")
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    store = TemplateStore(tenant_id)
    templates = store.list_for_user(user_id)
    return sorted(templates, key=lambda x: x.get("created_at", ""), reverse=True)


@router.get("/templates/{template_id}", dependencies=[Depends(require_api_key)])
def get_template_endpoint(template_id: str, request: Request) -> dict:
    """Get a specific template."""
    from app.storage.template_store import TemplateStore

    user_id = getattr(request.state, "user_id", "anonymous")
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    store = TemplateStore(tenant_id)
    tmpl = store.get(template_id, user_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail={"message": "템플릿을 찾을 수 없습니다."})
    store.increment_use_count(template_id, user_id)
    return tmpl


@router.delete("/templates/{template_id}", dependencies=[Depends(require_api_key)])
def delete_template_endpoint(template_id: str, request: Request) -> dict:
    """Delete a template."""
    from app.storage.template_store import TemplateStore

    user_id = getattr(request.state, "user_id", "anonymous")
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    store = TemplateStore(tenant_id)
    deleted = store.delete(template_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"message": "템플릿을 찾을 수 없습니다."})
    return {"deleted": True, "template_id": template_id}

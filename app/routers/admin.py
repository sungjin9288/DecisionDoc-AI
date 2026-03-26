"""app/routers/admin.py — Admin, tenant management, invite, and model registry endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

import dataclasses
import json as _json
import os
import secrets as _secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from app.auth.api_key import require_api_key
from app.auth.ops_key import require_ops_key
from app.dependencies import require_admin
from app.providers.factory import get_provider
from app.schemas import AcceptInviteRequest, InviteUserRequest

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Helper: invite page HTML
# ---------------------------------------------------------------------------

def _render_invite_page(invite: dict, invite_id: str) -> str:
    role_labels = {"admin": "관리자", "member": "팀원", "viewer": "열람자"}
    role = role_labels.get(invite.get("role", "member"), "팀원")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>초대 — DecisionDoc AI</title>
<style>
  body{{font-family:'Malgun Gothic',sans-serif;display:flex;align-items:center;
       justify-content:center;min-height:100vh;margin:0;background:#f9fafb}}
  .box{{background:white;border-radius:16px;padding:40px;max-width:400px;
        width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.1)}}
  h2{{color:#6366f1;margin-top:0}}
  .badge{{display:inline-block;background:#6366f120;color:#6366f1;
          padding:4px 12px;border-radius:99px;font-size:.85rem}}
  input{{width:100%;padding:10px;margin:6px 0 12px;border:1px solid #e5e7eb;
         border-radius:8px;box-sizing:border-box;font-size:1rem}}
  button{{width:100%;padding:12px;background:#6366f1;color:white;border:none;
          border-radius:8px;font-size:1rem;cursor:pointer}}
  label{{font-size:.85rem;color:#374151;font-weight:500}}
  #err{{color:#ef4444;margin-top:8px}}
</style>
</head>
<body>
<div class="box">
  <h2>🎉 팀 초대</h2>
  <p>DecisionDoc AI 팀에 초대되었습니다.</p>
  <p>역할: <span class="badge">{role}</span></p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
  <form onsubmit="accept(event)">
    <label>아이디</label>
    <input id="u" required minlength="3" placeholder="사용할 아이디">
    <label>이름</label>
    <input id="n" required placeholder="실명 또는 닉네임">
    <label>비밀번호</label>
    <input id="p" type="password" required minlength="8" placeholder="8자 이상">
    <button type="submit">계정 만들기 →</button>
  </form>
  <div id="err"></div>
</div>
<script>
async function accept(e){{
  e.preventDefault();
  const r=await fetch('/invite/{invite_id}/accept',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{username:document.getElementById('u').value,
      display_name:document.getElementById('n').value,
      password:document.getElementById('p').value}})
  }});
  if(r.ok){{const d=await r.json();
    localStorage.setItem('dd_access_token',d.access_token);
    localStorage.setItem('dd_refresh_token',d.refresh_token);
    location.href='/';
  }}else{{document.getElementById('err').textContent=(await r.json()).detail||'오류';}}
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Bundle auto-expansion
# ---------------------------------------------------------------------------

@router.post("/admin/expand-bundles", dependencies=[Depends(require_ops_key)])
def expand_bundles(request: Request) -> dict:
    """Manually trigger bundle auto-expansion from unmatched request patterns."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.services.bundle_expander import BundleAutoExpander
    from app.config import get_auto_expand_threshold

    data_dir = request.app.state.data_dir
    prompt_override_store = request.app.state.prompt_override_store
    provider = get_provider()
    pattern_store = RequestPatternStore(data_dir)
    expander = BundleAutoExpander(
        provider=provider,
        override_store=prompt_override_store,
        pattern_store=pattern_store,
    )
    result = expander.analyze_and_expand()
    if result is None:
        unmatched_count = len(pattern_store.get_unmatched(limit=50))
        threshold = get_auto_expand_threshold()
        return {
            "expanded": False,
            "reason": (
                f"unmatched={unmatched_count} < threshold={threshold}"
                if unmatched_count < threshold
                else "패턴 미감지 또는 confidence 부족"
            ),
        }
    return {"expanded": True, "bundle": result}


@router.get("/admin/auto-bundles")
def list_auto_bundles(request: Request) -> list[dict]:
    """List all auto-generated bundles with their metadata."""
    data_dir = request.app.state.data_dir
    registry_path = data_dir / "auto_bundles" / "registry.json"
    if not registry_path.exists():
        return []
    try:
        data = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return list(data.values())


@router.delete("/admin/auto-bundles/{bundle_id}", dependencies=[Depends(require_ops_key)])
def delete_auto_bundle(bundle_id: str, request: Request) -> dict:
    """Remove an auto-generated bundle from the registry and reload."""
    data_dir = request.app.state.data_dir
    registry_path = data_dir / "auto_bundles" / "registry.json"
    if not registry_path.exists():
        raise HTTPException(status_code=404, detail=f"Auto bundle '{bundle_id}' not found")

    try:
        data = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"registry.json 읽기 실패: {exc}") from exc

    if bundle_id not in data:
        raise HTTPException(status_code=404, detail=f"Auto bundle '{bundle_id}' not found")

    del data[bundle_id]
    registry_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    py_path = data_dir / "auto_bundles" / f"{bundle_id}.py"
    if py_path.exists():
        py_path.unlink()

    try:
        from app.bundle_catalog.registry import reload_auto_bundles
        reload_auto_bundles()
    except Exception:
        pass

    return {"deleted": True, "bundle_id": bundle_id}


@router.get("/admin/request-patterns")
def get_request_patterns(request: Request) -> dict:
    """View the request pattern log."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.config import get_auto_expand_threshold

    data_dir = request.app.state.data_dir
    pattern_store = RequestPatternStore(data_dir)
    all_records = pattern_store.get_all(limit=200)
    unmatched = [r for r in all_records if not r.get("matched", True)]
    threshold = get_auto_expand_threshold()
    return {
        "total": len(all_records),
        "unmatched_count": len(unmatched),
        "threshold": threshold,
        "ready_to_expand": len(unmatched) >= threshold,
        "records": all_records,
    }


# ---------------------------------------------------------------------------
# Team Invitations
# ---------------------------------------------------------------------------

@router.post("/admin/invite")
async def admin_invite_user(body: InviteUserRequest, request: Request) -> dict:
    """Generate a 7-day invitation link for a new team member. Admin only."""
    require_admin(request)
    from app.storage.invite_store import InviteStore
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    invite_id = _secrets.token_urlsafe(20)
    store = InviteStore(tenant_id)
    store.create(
        invite_id=invite_id,
        tenant_id=tenant_id,
        email=body.email,
        role=body.role,
        created_by=getattr(request.state, "user_id", "admin"),
        expires_days=7,
    )
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/invite/{invite_id}"
    return {
        "invite_id": invite_id,
        "invite_url": invite_url,
        "email": body.email,
        "role": body.role,
        "expires_days": 7,
    }


@router.get("/invite/{invite_id}")
async def view_invite(invite_id: str, request: Request):
    """Public invite acceptance page."""
    tenant_store = request.app.state.tenant_store
    from app.storage.invite_store import InviteStore
    for tenant in tenant_store.list_tenants():
        store = InviteStore(tenant.tenant_id)
        invite = store.get(invite_id)
        if invite:
            if not invite.get("is_active"):
                return HTMLResponse("<h2>초대 링크가 만료되었습니다.</h2>", status_code=410)
            return HTMLResponse(_render_invite_page(invite, invite_id))
    raise HTTPException(404, "초대 링크를 찾을 수 없습니다.")


@router.post("/invite/{invite_id}/accept")
async def accept_invite(invite_id: str, body: AcceptInviteRequest, request: Request) -> dict:
    """Accept invite and create account."""
    from app.storage.invite_store import InviteStore
    from app.storage.user_store import UserStore
    from app.services.auth_service import create_access_token, create_refresh_token
    tenant_store = request.app.state.tenant_store
    for tenant in tenant_store.list_tenants():
        store = InviteStore(tenant.tenant_id)
        invite = store.get(invite_id)
        if invite and invite.get("is_active"):
            data_dir = Path(os.getenv("DATA_DIR", "./data"))
            user_store = UserStore(
                data_dir / "tenants" / tenant.tenant_id,
                backend=request.app.state.state_backend,
            )
            existing = user_store.get_by_username(tenant.tenant_id, body.username)
            if existing:
                raise HTTPException(400, "이미 사용 중인 아이디입니다.")
            user = user_store.create(
                tenant_id=tenant.tenant_id,
                username=body.username,
                display_name=body.display_name,
                email=invite.get("email", ""),
                password=body.password,
                role=invite.get("role", "member"),
            )
            store.mark_used(invite_id)
            return {
                "message": "계정이 생성되었습니다.",
                "access_token": create_access_token(
                    user.user_id, tenant.tenant_id, user.role.value, user.username
                ),
                "refresh_token": create_refresh_token(user.user_id, tenant.tenant_id),
                "user": {
                    "user_id": user.user_id,
                    "username": user.username,
                    "role": user.role.value,
                },
            }
    raise HTTPException(404, "초대 링크를 찾을 수 없습니다.")


# ---------------------------------------------------------------------------
# Tenant Management
# ---------------------------------------------------------------------------

@router.post("/admin/tenants", dependencies=[Depends(require_ops_key)])
def admin_create_tenant(payload: dict, request: Request) -> dict:
    """Create a new tenant. Requires OPS key."""
    tenant_store = request.app.state.tenant_store
    tenant_id_val = payload.get("tenant_id", "").strip()
    display_name_val = payload.get("display_name", "").strip()
    if not tenant_id_val or not display_name_val:
        raise HTTPException(status_code=422, detail="tenant_id and display_name are required.")
    allowed = payload.get("allowed_bundles") or []
    try:
        tenant = tenant_store.create_tenant(
            tenant_id=tenant_id_val,
            display_name=display_name_val,
            allowed_bundles=allowed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return dataclasses.asdict(tenant)


@router.get("/admin/tenants", dependencies=[Depends(require_ops_key)])
def admin_list_tenants(request: Request) -> list[dict]:
    """List all tenants. Requires OPS key."""
    return [dataclasses.asdict(t) for t in request.app.state.tenant_store.list_tenants()]


@router.get("/admin/tenants/{tenant_id_path}", dependencies=[Depends(require_ops_key)])
def admin_get_tenant(tenant_id_path: str, request: Request) -> dict:
    """Get a single tenant by ID. Requires OPS key."""
    tenant = request.app.state.tenant_store.get_tenant(tenant_id_path)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id_path}' not found.")
    return dataclasses.asdict(tenant)


@router.patch("/admin/tenants/{tenant_id_path}", dependencies=[Depends(require_ops_key)])
def admin_update_tenant(tenant_id_path: str, payload: dict, request: Request) -> dict:
    """Update mutable fields of a tenant. Requires OPS key."""
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


@router.post("/admin/tenants/{tenant_id_path}/custom-hint", dependencies=[Depends(require_ops_key)])
def admin_set_custom_hint(tenant_id_path: str, payload: dict, request: Request) -> dict:
    """Set a bundle-specific custom prompt hint for a tenant. Requires OPS key."""
    bundle_id_val = payload.get("bundle_id", "").strip()
    hint_val = payload.get("hint", "").strip()
    if not bundle_id_val or not hint_val:
        raise HTTPException(status_code=422, detail="bundle_id and hint are required.")
    try:
        request.app.state.tenant_store.set_custom_hint(tenant_id_path, bundle_id_val, hint_val)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"tenant_id": tenant_id_path, "bundle_id": bundle_id_val, "hint": hint_val}


@router.delete("/admin/tenants/{tenant_id_path}/custom-hint/{bundle_id_path}", dependencies=[Depends(require_ops_key)])
def admin_delete_custom_hint(tenant_id_path: str, bundle_id_path: str, request: Request) -> dict:
    """Remove a bundle-specific custom prompt hint for a tenant. Requires OPS key."""
    try:
        request.app.state.tenant_store.delete_custom_hint(tenant_id_path, bundle_id_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "tenant_id": tenant_id_path, "bundle_id": bundle_id_path}


@router.get("/admin/tenants/{tenant_id_path}/stats", dependencies=[Depends(require_ops_key)])
def admin_tenant_stats(tenant_id_path: str, request: Request) -> dict:
    """Tenant usage statistics. Requires OPS key."""
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


# ---------------------------------------------------------------------------
# Location (Tenant) Overview with User Counts
# ---------------------------------------------------------------------------

@router.get("/admin/locations", dependencies=[Depends(require_api_key)])
def admin_list_locations(request: Request) -> list[dict]:
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
            users = user_store.list_by_tenant(tenant.tenant_id)
            user_count = len(users)
        except Exception:
            user_count = 0

        try:
            from app.eval.eval_store import get_eval_store
            eval_stats = get_eval_store(tenant.tenant_id).get_all_stats()
            gen_count = eval_stats.get("total_count", 0)
        except Exception:
            gen_count = 0

        result.append({
            **dataclasses.asdict(tenant),
            "user_count": user_count,
            "generation_count": gen_count,
        })
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
    users = user_store.list_by_tenant(tenant_id_path)
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "last_login": u.last_login,
            "avatar_color": u.avatar_color,
        }
        for u in users
    ]


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

@router.get("/models")
def list_models(
    request: Request,
    bundle_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List fine-tuned models for the current tenant."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    return registry.list_models(tenant_id=tenant_id, bundle_id=bundle_id, status=status)


@router.get("/models/{model_id:path}")
def get_model(model_id: str, request: Request) -> dict:
    """Get details for a specific fine-tuned model."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    model = registry.get_model(model_id, tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return model


@router.post("/admin/models/trigger-training", dependencies=[Depends(require_ops_key)])
async def admin_trigger_training(request: Request, payload: dict) -> dict:
    """Manually trigger fine-tune check for a bundle+tenant. Requires OPS key."""
    from app.services.finetune_orchestrator import FineTuneOrchestrator
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    bundle_id_val: str | None = payload.get("bundle_id") or None
    orch = FineTuneOrchestrator(request.app.state.data_dir)
    result = await orch.check_and_trigger(bundle_id_val, tenant_id)
    if result is None:
        return {"triggered": False, "message": "Not enough data or training already in progress."}
    return {"triggered": True, **result}


@router.post("/admin/models/{model_id:path}/promote", dependencies=[Depends(require_ops_key)])
def admin_promote_model(model_id: str, request: Request) -> dict:
    """Manually promote a model to 'ready' status. Requires OPS key."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    model = registry.get_model(model_id, tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    job_id = model.get("openai_job_id", "")
    if not registry.update_status(job_id, "ready", tenant_id=tenant_id, model_id=model_id):
        raise HTTPException(status_code=500, detail="Failed to update model status.")
    return {"promoted": True, "model_id": model_id, "status": "ready"}


@router.post("/admin/models/{model_id:path}/deprecate", dependencies=[Depends(require_ops_key)])
def admin_deprecate_model(model_id: str, request: Request) -> dict:
    """Deprecate a model. Requires OPS key."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    registry = ModelRegistry(request.app.state.data_dir)
    if not registry.deprecate_model(model_id, tenant_id):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return {"deprecated": True, "model_id": model_id}


@router.get("/admin/models/jobs", dependencies=[Depends(require_ops_key)])
async def admin_list_jobs(request: Request) -> list[dict]:
    """List active OpenAI fine-tuning jobs with fresh status. Requires OPS key."""
    from app.services.finetune_orchestrator import FineTuneOrchestrator
    orch = FineTuneOrchestrator(request.app.state.data_dir)
    jobs = await orch.list_active_jobs()
    return [
        {
            "id": j.get("id"),
            "status": j.get("status"),
            "model": j.get("model"),
            "fine_tuned_model": j.get("fine_tuned_model"),
            "created_at": j.get("created_at"),
            "finished_at": j.get("finished_at"),
            "training_file": j.get("training_file"),
            "error": j.get("error"),
        }
        for j in jobs
    ]

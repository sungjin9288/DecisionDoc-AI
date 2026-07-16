"""app/routers/admin/_invite.py — Team invitation endpoints.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

import secrets as _secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.ai_profiles.catalog import (
    default_ai_profiles_for_role,
    list_ai_profiles,
    normalize_ai_profile_keys,
)
from app.dependencies import require_admin
from app.schemas import AcceptInviteRequest, InviteUserRequest

router = APIRouter()

def _render_invite_page(invite: dict, invite_id: str) -> str:
    role_labels = {"admin": "관리자", "member": "팀원", "viewer": "열람자"}
    role = role_labels.get(invite.get("role", "member"), "팀원")
    job_title = str(invite.get("job_title", "") or "").strip()
    assigned_profiles = list_ai_profiles(invite.get("assigned_ai_profiles") or [])
    profile_html = (
        "".join(
            f'<span class="badge" style="margin-right:6px;margin-bottom:6px;">{profile["label"]}</span>'
            for profile in assigned_profiles
        )
        if assigned_profiles
        else '<span style="color:#6b7280;font-size:.9rem;">관리자가 로그인 후 업무 AI를 배정할 예정입니다.</span>'
    )
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
  <p>직위: <strong>{job_title or '미지정'}</strong></p>
  <div style="margin:12px 0 4px;">
    <div style="font-size:.85rem;color:#374151;font-weight:600;margin-bottom:6px;">배정된 업무 AI</div>
    <div style="display:flex;flex-wrap:wrap;">{profile_html}</div>
  </div>
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
# Team Invitations
# ---------------------------------------------------------------------------

@router.post("/admin/invite")
async def admin_invite_user(body: InviteUserRequest, request: Request) -> dict:
    """Generate a 7-day invitation link for a new team member. Admin only."""
    require_admin(request)
    from app.storage.invite_store import InviteStore
    tenant_store = request.app.state.tenant_store
    tenant_id = (body.tenant_id or getattr(request.state, "tenant_id", "system") or "system").strip()
    if tenant_store.get_tenant(tenant_id) is None:
        raise HTTPException(404, f"Tenant '{tenant_id}' not found.")
    assigned_profiles = (
        normalize_ai_profile_keys(body.assigned_ai_profiles)
        if body.assigned_ai_profiles
        else default_ai_profiles_for_role(body.role)
    )
    invite_id = _secrets.token_urlsafe(20)
    store = InviteStore(
        tenant_id,
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )
    store.create(
        invite_id=invite_id,
        email=body.email,
        role=body.role,
        created_by=getattr(request.state, "user_id", "admin"),
        expires_days=7,
        job_title=body.job_title.strip(),
        assigned_ai_profiles=assigned_profiles,
    )
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/invite/{invite_id}"
    return {
        "invite_id": invite_id,
        "invite_url": invite_url,
        "email": body.email,
        "role": body.role,
        "job_title": body.job_title.strip(),
        "assigned_ai_profiles": assigned_profiles,
        "expires_days": 7,
    }


@router.get("/invite/{invite_id}")
async def view_invite(invite_id: str, request: Request):
    """Public invite acceptance page."""
    tenant_store = request.app.state.tenant_store
    from app.storage.invite_store import InviteStore
    for tenant in tenant_store.list_tenants():
        store = InviteStore(
            tenant.tenant_id,
            data_dir=request.app.state.data_dir,
            backend=request.app.state.state_backend,
        )
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
        store = InviteStore(
            tenant.tenant_id,
            data_dir=request.app.state.data_dir,
            backend=request.app.state.state_backend,
        )

        def create_account(invite: dict):
            data_dir = request.app.state.data_dir
            user_store = UserStore(
                data_dir / "tenants" / tenant.tenant_id,
                backend=request.app.state.state_backend,
            )
            existing = user_store.get_by_username(body.username)
            if existing:
                raise HTTPException(400, "이미 사용 중인 아이디입니다.")
            user = user_store.create(
                username=body.username,
                display_name=body.display_name,
                email=invite.get("email", ""),
                password=body.password,
                role=invite.get("role", "member"),
                job_title=invite.get("job_title", ""),
                assigned_ai_profiles=invite.get("assigned_ai_profiles") or [],
            )
            return user

        user = store.accept(invite_id, create_account)
        if user is not None:
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
                    "job_title": user.job_title,
                    "assigned_ai_profiles": list(user.assigned_ai_profiles),
                },
            }
    raise HTTPException(404, "초대 링크를 찾을 수 없습니다.")

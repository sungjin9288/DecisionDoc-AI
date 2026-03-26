"""app/routers/audit.py — Audit log endpoints and privacy policy.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

import html as _html
import os as _os
from collections import Counter

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["audit"])


def _require_admin(request: Request) -> None:
    if getattr(request.state, "user_role", None) != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다.")


@router.get("/admin/audit-logs")
async def query_audit_logs(
    request: Request,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    result: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
):
    """Query audit logs (admin only)."""
    from app.storage.audit_store import AuditStore

    _require_admin(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    store = AuditStore(tenant_id)
    logs = store.query(
        tenant_id,
        filters={
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "result": result,
            "date_from": date_from,
            "date_to": date_to,
        },
    )
    capped = logs[: min(limit, 1000)]
    return {"logs": capped, "total": len(logs)}


@router.get("/admin/audit-logs/stats")
async def audit_stats(request: Request, days: int = 30):
    """Return audit log summary statistics (admin only)."""
    from app.storage.audit_store import AuditStore

    _require_admin(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    return AuditStore(tenant_id).get_stats(tenant_id, days=days)


@router.get("/admin/audit-logs/export")
async def export_audit_logs(request: Request, date_from: str, date_to: str):
    """Export audit logs as CSV (admin only)."""
    from app.storage.audit_store import AuditStore

    _require_admin(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    csv_content = AuditStore(tenant_id).export_csv(tenant_id, date_from, date_to)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_{date_from}_{date_to}.csv"
        },
    )


@router.get("/admin/audit-logs/failed-logins")
async def failed_logins(request: Request, hours: int = 24):
    """Security monitoring: failed login attempts with brute-force detection."""
    from app.storage.audit_store import AuditStore

    _require_admin(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    logs = AuditStore(tenant_id).get_failed_logins(tenant_id, hours=hours)

    ip_counts = Counter(log.get("ip_address", "") for log in logs)
    suspicious_ips = [
        {"ip": ip, "attempts": count}
        for ip, count in ip_counts.most_common()
        if count >= 5
    ]
    return {
        "total_failures": len(logs),
        "unique_ips": len(ip_counts),
        "suspicious_ips": suspicious_ips,
        "logs": logs[:100],
    }


@router.get("/privacy")
async def privacy_policy():
    """Serve privacy policy page."""
    policy_path = _os.path.join(
        _os.path.dirname(__file__), "..", "..", "docs", "privacy_policy.md"
    )
    if _os.path.exists(policy_path):
        with open(policy_path, encoding="utf-8") as f:
            content = f.read()
        try:
            import markdown as _md
            html_content = _md.markdown(content, extensions=["tables", "toc"])
        except ImportError:
            html_content = f"<pre>{_html.escape(content)}</pre>"
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>개인정보처리방침 — DecisionDoc AI</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px;
         margin: 2rem auto; padding: 0 1rem; color: #111; line-height: 1.6; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; }}
  th {{ background: #f9fafb; font-weight: 600; }}
  h1 {{ color: #6366f1; }} h2, h3 {{ color: #374151; }}
  a {{ color: #6366f1; }} code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }}
</style>
</head><body>{html_content}
<p style="margin-top:3rem;color:#9ca3af">
  <a href="/">← 서비스로 돌아가기</a>
</p>
</body></html>""")
    raise HTTPException(status_code=404, detail="Privacy policy not found")

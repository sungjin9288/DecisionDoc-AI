"""app/routers/history.py — History, G2B bookmarks, and share link endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.auth.api_key import require_api_key
from app.dependencies import require_auth
from app.schemas import CreateShareRequest

router = APIRouter(tags=["history"])


# ── History ────────────────────────────────────────────────────────────────────

@router.get("/history/favorites", dependencies=[Depends(require_api_key)])
def get_history_favorites(request: Request):
    """즐겨찾기된 히스토리 항목 반환."""
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.history_store import HistoryStore
    store = HistoryStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    entries = store.get_favorites(user_id)
    return {"favorites": entries, "count": len(entries)}


@router.get("/history", dependencies=[Depends(require_api_key)])
def get_history(
    request: Request,
    q: str = Query(default="", description="제목·번들·태그 검색어"),
    limit: int = Query(default=20, ge=1, le=100),
    starred: bool = Query(default=False, description="즐겨찾기만 보기"),
):
    """이력 조회. q 파라미터로 검색, starred=true 로 즐겨찾기 필터."""
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.history_store import HistoryStore
    store = HistoryStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    if starred:
        entries = store.get_favorites(user_id)[:limit]
    elif q:
        entries = store.search(user_id, q, limit)
    else:
        entries = store.get_for_user(user_id, limit)
    return {"history": entries, "count": len(entries), "q": q}


@router.delete("/history/{entry_id}", dependencies=[Depends(require_api_key)])
def delete_history_entry(entry_id: str, request: Request):
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.history_store import HistoryStore
    store = HistoryStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    store.delete(entry_id, user_id)
    return {"status": "deleted"}


@router.post("/history/{entry_id}/star", dependencies=[Depends(require_api_key)])
def toggle_history_star(entry_id: str, request: Request):
    """히스토리 항목 즐겨찾기 토글."""
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.history_store import HistoryStore
    store = HistoryStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    starred = store.toggle_favorite(entry_id, user_id)
    return {"entry_id": entry_id, "starred": starred}


# ── G2B Bookmarks ──────────────────────────────────────────────────────────────

@router.get("/g2b/bookmarks", dependencies=[Depends(require_api_key)])
def get_g2b_bookmarks(request: Request):
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.bookmark_store import BookmarkStore
    store = BookmarkStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    bookmarks = store.get_for_user(user_id)
    return {"bookmarks": bookmarks}


@router.post("/g2b/bookmarks", dependencies=[Depends(require_api_key)])
def add_g2b_bookmark(request: Request, payload: dict):
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.bookmark_store import BookmarkStore
    store = BookmarkStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    result = store.add(user_id, payload)
    return {"bookmark": result}


@router.delete("/g2b/bookmarks/{bid_number}", dependencies=[Depends(require_api_key)])
def remove_g2b_bookmark(bid_number: str, request: Request):
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.bookmark_store import BookmarkStore
    store = BookmarkStore(
        tenant_id,
        base_dir=str(request.app.state.data_dir),
        backend=request.app.state.state_backend,
    )
    store.remove(user_id, bid_number)
    return {"status": "removed"}


# ── Share Links ────────────────────────────────────────────────────────────────

@router.post("/share", dependencies=[Depends(require_api_key)])
def create_share_link(payload: CreateShareRequest, request: Request):
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.share_store import ShareStore
    store = ShareStore(tenant_id, data_dir=request.app.state.data_dir)
    link = store.create(
        tenant_id=tenant_id,
        request_id=payload.request_id,
        title=payload.title,
        created_by=user_id,
        bundle_id=payload.bundle_id,
        expires_days=payload.expires_days,
    )
    return {
        "share_id": link.share_id,
        "share_url": f"/shared/{link.share_id}",
        "expires_at": link.expires_at,
    }


@router.get("/shared/{share_id}")
def view_shared_document(share_id: str, request: Request):
    """Public endpoint — no auth required."""
    from app.storage.share_store import ShareStore
    tenant_store = request.app.state.tenant_store
    for tenant in tenant_store.list_tenants():
        store = ShareStore(
            tenant.tenant_id,
            data_dir=request.app.state.data_dir,
            backend=request.app.state.state_backend,
        )
        link = store.get(share_id)
        if link and link.get("is_active"):
            store.increment_access(share_id)
            title = link.get("title", "공유 문서")
            request_id = link.get("request_id", "")
            doc_html = ""
            if request_id:
                try:
                    storage = request.app.state.storage
                    bundle = storage.load_bundle(request_id)
                    if bundle:
                        docs = bundle.get("documents", {})
                        parts = []
                        for doc_key, content in docs.items():
                            if isinstance(content, str) and content.strip():
                                html = _md_to_html(content)
                                parts.append(f'<section class="doc-section">{html}</section>')
                        doc_html = "\n".join(parts)
                except Exception:
                    pass
            if not doc_html:
                doc_html = '<p style="color:#6b7280">문서 내용을 불러올 수 없습니다.</p>'
            return HTMLResponse(_render_shared_page(title, doc_html))
    raise HTTPException(status_code=404, detail="공유 링크를 찾을 수 없습니다.")


def _md_to_html(md: str) -> str:
    import html as _html
    import re
    lines = md.split("\n")
    out = []
    for line in lines:
        line = _html.escape(line)
        if line.startswith("### "):
            out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            out.append(f"<li>{line[2:]}</li>")
        elif line.startswith("| ") and "|" in line[2:]:
            cells = [c.strip() for c in line.strip("| ").split("|")]
            cells_html = "".join(f"<td>{c}</td>" for c in cells if c and not re.match(r"^[-:]+$", c))
            if cells_html:
                out.append(f"<tr>{cells_html}</tr>")
        elif not line.strip():
            out.append("<br>")
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            out.append(f"<p>{line}</p>")
    return "\n".join(out)


def _render_shared_page(title: str, doc_html: str) -> str:
    import html as _html
    safe_title = _html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} — DecisionDoc AI</title>
<style>
  body{{font-family:'Malgun Gothic',Apple SD Gothic Neo,sans-serif;
       max-width:860px;margin:2rem auto;padding:0 1.5rem;color:#1f2937;line-height:1.7}}
  .share-header{{border-bottom:2px solid #6366f1;padding-bottom:.75rem;margin-bottom:2rem}}
  .share-header h1{{color:#6366f1;margin:0 0 .25rem;font-size:1.5rem}}
  .share-meta{{font-size:.8rem;color:#6b7280}}
  .doc-section{{margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:1px solid #e5e7eb}}
  .doc-section:last-child{{border-bottom:none}}
  h1,h2,h3{{color:#1f2937;margin-top:1.5rem}}
  h2{{font-size:1.15rem;border-bottom:1px solid #e5e7eb;padding-bottom:.25rem}}
  h3{{font-size:1rem}}
  li{{margin:.25rem 0}}
  table{{border-collapse:collapse;width:100%;font-size:.9rem}}
  td{{border:1px solid #e5e7eb;padding:.4rem .6rem}}
  strong{{color:#111}}
  .dd-badge{{display:inline-block;background:#6366f1;color:#fff;
             font-size:.72rem;padding:2px 10px;border-radius:99px;margin-left:.5rem}}
</style>
</head>
<body>
<div class="share-header">
  <h1>📄 {safe_title} <span class="dd-badge">공유 문서</span></h1>
  <div class="share-meta">DecisionDoc AI로 생성된 문서입니다.</div>
</div>
{doc_html}
</body>
</html>"""


@router.delete("/share/{share_id}", dependencies=[Depends(require_api_key)])
def revoke_share_link(share_id: str, request: Request):
    require_auth(request)
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    user_id = getattr(request.state, "user_id", "anonymous")
    from app.storage.share_store import ShareStore
    store = ShareStore(tenant_id, data_dir=request.app.state.data_dir)
    success = store.revoke(share_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="공유 링크를 찾을 수 없습니다.")
    return {"message": "공유 링크가 비활성화되었습니다.", "share_id": share_id}

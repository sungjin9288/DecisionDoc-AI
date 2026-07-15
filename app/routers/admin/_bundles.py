"""app/routers/admin/_bundles.py — Bundle auto-expansion admin endpoints.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.ops_key import require_ops_key
from app.dependencies import get_tenant_id, require_admin
from app.providers.factory import get_provider
from app.storage.base import atomic_write_text

router = APIRouter()

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
    from app.storage.prompt_override_store import get_override_store

    tenant_id = get_tenant_id(request)
    prompt_override_store = get_override_store(tenant_id)
    provider = get_provider()
    pattern_store = RequestPatternStore(data_dir, tenant_id=tenant_id)
    expander = BundleAutoExpander(
        provider=provider,
        override_store=prompt_override_store,
        pattern_store=pattern_store,
        data_dir=data_dir,
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
    if not isinstance(data, dict):
        return []
    return [record for record in data.values() if isinstance(record, dict)]


@router.delete("/admin/auto-bundles/{bundle_id}", dependencies=[Depends(require_ops_key)])
def delete_auto_bundle(bundle_id: str, request: Request) -> dict:
    """Remove an auto-generated bundle from the registry and reload."""
    from app.services.bundle_expander import is_safe_bundle_id

    if not is_safe_bundle_id(bundle_id):
        raise HTTPException(status_code=400, detail="Invalid auto bundle ID")

    data_dir = request.app.state.data_dir
    registry_path = data_dir / "auto_bundles" / "registry.json"
    if not registry_path.exists():
        raise HTTPException(status_code=404, detail=f"Auto bundle '{bundle_id}' not found")

    try:
        data = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"registry.json 읽기 실패: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="registry.json must contain an object")

    if bundle_id not in data:
        raise HTTPException(status_code=404, detail=f"Auto bundle '{bundle_id}' not found")

    del data[bundle_id]
    atomic_write_text(
        registry_path,
        _json.dumps(data, ensure_ascii=False, indent=2),
    )

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
    require_admin(request)
    from app.storage.request_pattern_store import RequestPatternStore
    from app.config import get_auto_expand_threshold

    data_dir = request.app.state.data_dir
    pattern_store = RequestPatternStore(
        data_dir,
        tenant_id=get_tenant_id(request),
    )
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

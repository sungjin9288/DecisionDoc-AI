"""app/routers/finetune.py — Fine-tune dataset management endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

import os
import re as _re

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.ops_key import require_ops_key

router = APIRouter(prefix="/finetune", tags=["finetune"])


@router.get("/stats")
def finetune_stats(request: Request) -> dict:
    """Fine-tune 데이터셋 통계 반환."""
    return request.app.state.finetune_store.get_stats()


@router.get("/records")
def finetune_records(
    request: Request,
    bundle_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fine-tune 레코드 목록 반환 (최대 limit 건)."""
    return request.app.state.finetune_store.get_records(bundle_id=bundle_id, limit=limit)


@router.post("/export", dependencies=[Depends(require_ops_key)])
def finetune_export(request: Request, payload: dict | None = None) -> dict:
    """Fine-tune 데이터셋 JSONL 내보내기."""
    body = payload or {}
    bundle_id_filter = body.get("bundle_id")
    min_records = int(body.get("min_records", 10))
    finetune_store = request.app.state.finetune_store
    export_path = finetune_store.export_for_training(
        bundle_id=bundle_id_filter,
        min_records=min_records,
    )
    filename = os.path.basename(export_path) if export_path else None
    return {
        "exported": export_path is not None,
        "filename": filename,
        "bundle_id": bundle_id_filter,
    }


@router.get("/export/{filename}", dependencies=[Depends(require_ops_key)])
def finetune_download_export(filename: str, request: Request) -> Response:
    """내보낸 JSONL 파일 다운로드."""
    if not _re.match(r"^[\w.\-]+\.jsonl$", filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    data_dir = request.app.state.data_dir
    export_path = data_dir / "finetune" / filename
    if not export_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found.")
    content = export_path.read_bytes()
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/dataset", dependencies=[Depends(require_ops_key)])
def finetune_clear_dataset(request: Request) -> dict:
    """Fine-tune 데이터셋 전체 삭제 (복구 불가)."""
    removed = request.app.state.finetune_store.clear_dataset()
    return {"cleared": True, "records_removed": removed}

"""app/routers/finetune.py — Fine-tune dataset management endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.auth.ops_key import require_ops_key
from app.dependencies import get_tenant_id
from app.schemas import FineTuneExportRequest
from app.storage.finetune_store import FineTuneStore, get_finetune_store

router = APIRouter(prefix="/finetune", tags=["finetune"])


def _store(request: Request) -> FineTuneStore:
    return get_finetune_store(
        get_tenant_id(request),
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )


@router.get("/stats")
def finetune_stats(request: Request) -> dict:
    """Fine-tune 데이터셋 통계 반환."""
    return _store(request).get_stats()


@router.get("/records")
def finetune_records(
    request: Request,
    bundle_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict]:
    """Fine-tune 레코드 목록 반환 (최대 limit 건)."""
    return _store(request).get_records(bundle_id=bundle_id, limit=limit)


@router.post("/export", dependencies=[Depends(require_ops_key)])
def finetune_export(
    request: Request,
    payload: FineTuneExportRequest | None = None,
) -> dict:
    """Fine-tune 데이터셋 JSONL 내보내기."""
    body = payload or FineTuneExportRequest()
    finetune_store = _store(request)
    export = finetune_store.export_for_training(
        bundle_id=body.bundle_id,
        min_records=body.min_records,
    )
    return {
        "exported": export is not None,
        "filename": export.filename if export else None,
        "bundle_id": body.bundle_id,
        "record_count": export.record_count if export else 0,
        "sha256": export.sha256 if export else None,
        "size_bytes": export.size_bytes if export else 0,
    }


@router.get("/export/{filename}", dependencies=[Depends(require_ops_key)])
def finetune_download_export(filename: str, request: Request) -> Response:
    """내보낸 JSONL 파일 다운로드."""
    content = _store(request).get_export_bytes(filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Export file not found.")
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/dataset", dependencies=[Depends(require_ops_key)])
def finetune_clear_dataset(request: Request) -> dict:
    """Fine-tune 데이터셋 전체 삭제 (복구 불가)."""
    removed = _store(request).clear_dataset()
    return {"cleared": True, "records_removed": removed}

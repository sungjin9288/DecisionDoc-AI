"""History persistence shared by synchronous and streaming generation routes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from app.schemas import GenerateRequest
from app.storage.history_store import HistoryEntry, HistoryStore

logger = logging.getLogger("decisiondoc.generate")


def store_generation_history(
    req: GenerateRequest,
    request: Request,
    *,
    tenant_id: str,
    request_id: str,
    docs: list[dict[str, Any]],
    applied_references: list[dict[str, Any]],
) -> None:
    """Persist a completed generation for the authenticated user's reuse flow."""
    try:
        user_id = getattr(request.state, "user_id", None) or "anonymous"
        HistoryStore(
            tenant_id,
            base_dir=str(request.app.state.data_dir),
            backend=request.app.state.state_backend,
        ).add(
            HistoryEntry(
                entry_id=request_id,
                tenant_id=tenant_id,
                user_id=user_id,
                bundle_id=req.bundle_type,
                bundle_type=req.bundle_type,
                bundle_name=req.bundle_type,
                title=req.title,
                request_id=request_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                project_id=req.project_id or "",
                score=0.0,
                tags=[],
                applied_references=applied_references,
                docs=docs,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[History] 이력 저장 실패 (무시): %s", exc)

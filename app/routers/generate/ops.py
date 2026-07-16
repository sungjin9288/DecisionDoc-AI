"""app/routers/generate/ops.py — Feedback, ops, and attachment-parsing endpoints.

Split out of the former app/routers/generate.py (2,170 lines) to keep each
sub-module under the file-size limit. Covers:
  POST /feedback
  POST /ops/cache/clear
  POST /ops/investigate
  GET  /ops/post-deploy/reports
  GET  /ops/post-deploy/reports/{report_file}
  POST /ops/post-deploy/run
  POST /attachments/parse-rfp
  POST /generate/recommend-bundle

Pure code relocation — no behavior changes.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File

from app.auth.api_key import require_api_key
from app.auth.ops_key import require_ops_key
from app.dependencies import get_tenant_id, require_admin as _require_admin
from app.maintenance.mode import is_maintenance_mode, require_not_maintenance
from app.observability.logging import log_event
from app.providers.factory import get_provider_for_bundle
from app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    OpsInvestigateRequest,
    OpsInvestigateResponse,
    OpsPostDeployReportDetailResponse,
    OpsPostDeployReportsResponse,
    OpsPostDeployRunRequest,
    OpsPostDeployRunResponse,
)
from app.routers.generate._shared import (
    _auto_improve_if_needed,
    _build_procurement_attachment_context,
    _raise_if_legacy_binary_hwp_uploads,
)

logger = logging.getLogger("decisiondoc.generate")

router = APIRouter(tags=["generate"])


def _facade():
    """Return the `app.routers.generate` package module.

    Some existing tests patch library functions (``extract_multiple``,
    ``extract_pdf_structured``) via
    ``unittest.mock.patch("app.routers.generate.<name>", ...)`` — a pattern
    written against the pre-split single-file module. Looking these up on the
    facade module at call time keeps those patches effective after the split.
    """
    import app.routers.generate as _generate_pkg

    return _generate_pkg


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest, request: Request) -> FeedbackResponse:
    tenant_id = get_tenant_id(request)
    from app.eval.eval_store import get_eval_store
    from app.storage.feedback_store import get_feedback_store
    from app.storage.finetune_store import get_finetune_store
    from app.storage.prompt_override_store import get_override_store

    store_context = {
        "data_dir": request.app.state.data_dir,
        "backend": request.app.state.state_backend,
    }
    feedback_store = get_feedback_store(tenant_id, **store_context)
    prompt_override_store = get_override_store(tenant_id, **store_context)
    eval_store = get_eval_store(tenant_id, **store_context)
    finetune_store = get_finetune_store(tenant_id, **store_context)

    feedback_id = feedback_store.save(payload.model_dump())
    log_event(logger, {
        "event": "feedback.submitted",
        "request_id": request.state.request_id,
        "feedback_id": feedback_id,
        "bundle_type": payload.bundle_type,
        "rating": payload.rating,
    })

    # Auto-improve: 저평점 누적 시 패턴 분석 → PromptOverrideStore 저장
    _auto_improve_if_needed(
        bundle_type=payload.bundle_type,
        feedback_store=feedback_store,
        override_store=prompt_override_store,
        eval_store=eval_store,
        tenant_id=tenant_id,
        data_dir=request.app.state.data_dir,
    )

    # ── Trigger A: high user rating → collect fine-tune record ───────────
    try:
        from app.config import get_finetune_min_rating
        gen_request_id = payload.request_id or ""
        if payload.rating >= get_finetune_min_rating() and gen_request_id:
            from app.services.generation_service import get_generation_context
            ctx = get_generation_context(gen_request_id, tenant_id=tenant_id)
            if ctx and ctx.get("system_prompt") and ctx.get("output"):
                user_content = (
                    f"{ctx.get('title', '')}\n"
                    f"목표: {ctx.get('goal', '')}\n"
                    f"컨텍스트: {ctx.get('context_text', '')}"
                ).strip()
                messages = [
                    {"role": "system", "content": ctx["system_prompt"]},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": ctx["output"]},
                ]
                finetune_store.save_record(
                    messages=messages,
                    metadata={
                        "bundle_id": ctx.get("bundle_type", payload.bundle_type),
                        "request_id": gen_request_id,
                        "heuristic_score": 0.0,
                        "llm_score": None,
                        "user_rating": payload.rating,
                        "source": "high_rating",
                    },
                )
    except Exception as _ft_exc:
        logger.warning("[FineTune] Trigger A 수집 실패 (무시): %s", _ft_exc)

    return FeedbackResponse(feedback_id=feedback_id, saved=True)


@router.post("/ops/cache/clear", dependencies=[Depends(require_ops_key)])
def clear_cache(request: Request) -> dict:
    """Clear all cached bundles. Requires OPS key."""
    service = request.app.state.service
    removed = service.clear_cache()
    log_event(logger, {
        "event": "cache.cleared",
        "request_id": request.state.request_id,
        "files_removed": removed,
    })
    return {"cleared": True, "files_removed": removed}


@router.post(
    "/ops/investigate",
    response_model=OpsInvestigateResponse,
    dependencies=[Depends(require_ops_key)],
)
def investigate_ops(payload: OpsInvestigateRequest, request: Request) -> OpsInvestigateResponse:
    ops_service = request.app.state.ops_service
    configured_stage = os.getenv("DECISIONDOC_ENV", "dev").lower()
    request_id = request.state.request_id
    stage = payload.stage or configured_stage
    result = ops_service.investigate(
        window_minutes=payload.window_minutes,
        reason=payload.reason,
        stage=stage,
        request_id=request_id,
        force=payload.force,
        notify=payload.notify,
    )
    request.state.maintenance = is_maintenance_mode()
    return OpsInvestigateResponse(**result)


@router.get(
    "/ops/post-deploy/reports",
    response_model=OpsPostDeployReportsResponse,
)
def get_ops_post_deploy_reports(
    request: Request,
    limit: int = Query(default=5, ge=1, le=20),
    latest: bool = Query(default=False),
) -> OpsPostDeployReportsResponse:
    _require_admin(request)
    ops_service = request.app.state.ops_service
    try:
        result = ops_service.read_post_deploy_reports(limit=limit, latest=latest)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Post-deploy report history not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Post-deploy report history is invalid.") from exc
    return OpsPostDeployReportsResponse(**result)


@router.get(
    "/ops/post-deploy/reports/{report_file}",
    response_model=OpsPostDeployReportDetailResponse,
)
def get_ops_post_deploy_report_detail(
    report_file: str,
    request: Request,
) -> OpsPostDeployReportDetailResponse:
    _require_admin(request)
    ops_service = request.app.state.ops_service
    try:
        result = ops_service.read_post_deploy_report(report_file=report_file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Requested post-deploy report not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid post-deploy report file name.") from exc
    return OpsPostDeployReportDetailResponse(**result)


@router.post(
    "/ops/post-deploy/run",
    response_model=OpsPostDeployRunResponse,
    dependencies=[Depends(require_ops_key)],
)
def run_ops_post_deploy_check(
    payload: OpsPostDeployRunRequest,
    request: Request,
) -> OpsPostDeployRunResponse:
    ops_service = request.app.state.ops_service
    try:
        result = ops_service.run_post_deploy_check(skip_smoke=payload.skip_smoke)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Post-deploy runner is disabled.") from exc
    except Exception as exc:
        logger.warning("Post-deploy run failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Post-deploy run failed.") from exc
    return OpsPostDeployRunResponse(**result)


@router.post(
    "/attachments/parse-rfp",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def parse_rfp_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict:
    """Upload RFP document(s) -> extract structured fields for form auto-fill.

    Returns extracted fields (project title, issuer, budget, etc.) plus a
    raw text preview so the frontend can populate the generation form.
    """
    from app.services.rfp_parser import build_rfp_context, parse_rfp_fields

    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    request_id = request.state.request_id

    _raise_if_legacy_binary_hwp_uploads(files)
    file_data: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        if raw and f.filename:
            file_data.append((f.filename, raw))

    if not file_data:
        raise HTTPException(status_code=422, detail="파일이 없거나 비어 있습니다.")

    provider = get_provider_for_bundle("rfp_analysis_kr", tenant_id)
    combined = _facade().extract_multiple(
        file_data,
        provider=provider,
        request_id=request_id,
    )
    procurement_context = _build_procurement_attachment_context(file_data)
    parse_input = procurement_context + "\n\n" + combined if procurement_context else combined
    fields = parse_rfp_fields(parse_input, provider=provider, request_id=request_id)
    structured_context = build_rfp_context(combined[:6_000], normalized_context=procurement_context)

    return {
        "extracted_fields": fields,
        "raw_text_preview": combined[:2_000],
        "total_chars": len(combined),
        "structured_context": structured_context,
        "procurement_context_preview": procurement_context[:1_000],
        "files_processed": [f[0] for f in file_data],
    }


@router.post(
    "/generate/recommend-bundle",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def recommend_bundle_endpoint(payload: dict, request: Request) -> dict:
    """키워드 기반으로 적합한 번들 타입을 추천합니다."""
    from app.domain.schema import recommend_bundles

    title = payload.get("title", "")
    goal = payload.get("goal", "")
    industry = payload.get("industry", "")
    text = f"{title} {goal} {industry}".lower()
    recommendations = recommend_bundles(text)
    return {"recommended": recommendations}

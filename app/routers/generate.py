"""app/routers/generate.py — Generate endpoints extracted from main.py.

Covers:
  POST /generate
  POST /generate/with-attachments
  POST /generate/export
  POST /generate/pptx
  POST /generate/stream
  POST /generate/docx
  POST /generate/pdf
  POST /generate/excel
  POST /generate/hwp
  POST /generate/export-edited
  POST /generate/rewrite-section
  POST /generate/sketch
  POST /generate/refine
  POST /generate/related
  POST /generate/summary
  POST /generate/validate
  POST /generate/freeform
  POST /generate/review
  POST /generate/translate
  GET  /generate/export-zip
  POST /feedback
  POST /ops/cache/clear
  POST /ops/investigate
  POST /attachments/parse-rfp
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import threading
import urllib.parse
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.auth.api_key import require_api_key
from app.auth.ops_key import require_ops_key
from app.dependencies import require_admin as _require_admin, require_auth as _require_auth
from app.maintenance.mode import is_maintenance_mode, require_not_maintenance
from app.observability.logging import log_event
from app.observability.timing import Timer
from app.providers.factory import get_provider, get_provider_for_bundle
from app.schemas import (
    EditedExportRequest,
    FeedbackRequest,
    FeedbackResponse,
    FreeformRequest,
    GenerateExportResponse,
    GenerateRequest,
    GenerateResponse,
    GovDocOptions,
    OpsInvestigateRequest,
    OpsInvestigateResponse,
    OpsPostDeployReportDetailResponse,
    OpsPostDeployReportsResponse,
    OpsPostDeployRunRequest,
    OpsPostDeployRunResponse,
    SectionRewriteRequest,
)
from app.services.attachment_service import (
    AttachmentError,
    MAX_TOTAL_CHARS,
    extract_multiple,
    extract_pdf_structured,
    extract_text,
)
from app.services.docx_service import build_docx
from app.services.excel_service import build_excel
from app.services.generation_service import BundleNotSupportedError
from app.services.hwp_service import build_hwp
from app.services.pptx_service import build_pptx

logger = logging.getLogger("decisiondoc.generate")

router = APIRouter(tags=["generate"])

_PROCUREMENT_OVERRIDE_REQUIRED_BUNDLE_IDS = {
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
}
_PROCUREMENT_BUNDLE_LABELS = {
    "rfp_analysis_kr": "RFP 분석",
    "proposal_kr": "제안서",
    "performance_plan_kr": "수행계획",
}
_DECISION_COUNCIL_APPLIED_BUNDLE_IDS = {"bid_decision_kr", "proposal_kr"}


# ── Module-level helpers ──────────────────────────────────────────────────────

def _resolve_gov_options(gov_options_dict: dict | None) -> GovDocOptions | None:
    """Convert a raw dict (from JSON payload) into a ``GovDocOptions`` instance.

    Returns ``None`` when ``gov_options_dict`` is ``None`` or empty so that
    downstream build functions can use their own defaults.
    """
    if not gov_options_dict:
        return None
    try:
        return GovDocOptions(**gov_options_dict)
    except (TypeError, ValueError):
        return None


def _extract_uploaded_documents(files: list[UploadFile]) -> tuple[str, list[str]]:
    """Extract uploaded files into one generation-ready context block.

    Returns the merged text and a list of successfully parsed filenames.
    Raises ``HTTPException`` when all files fail so the caller does not generate
    docs from warning-only placeholders.
    """
    parts: list[str] = []
    parsed_filenames: list[str] = []
    total = 0
    errors: list[str] = []

    for upload in files:
        filename = upload.filename or "attachment"
        raw = upload.file.read()
        if not raw:
            continue

        try:
            text = extract_text(filename, raw)
        except AttachmentError as exc:
            errors.append(str(exc))
            continue

        remaining = MAX_TOTAL_CHARS - total
        if remaining <= 0:
            break
        if len(text) > remaining:
            if remaining <= 500:
                break
            text = text[:remaining] + "\n...(이하 생략)"

        parts.append(f"[첨부파일: {filename}]\n{text}")
        parsed_filenames.append(filename)
        total += len(text)

    if not parsed_filenames:
        detail = errors[0] if errors else "텍스트를 추출할 수 있는 파일이 없습니다."
        raise HTTPException(status_code=422, detail=detail)

    return "\n\n---\n\n".join(parts), parsed_filenames


# ── ZIP export in-memory cache ────────────────────────────────────────────────
_zip_docs_cache: dict[str, tuple[list[dict], str]] = {}


def _store_zip_docs(request_id: str, docs: list[dict], title: str) -> None:
    """Store generated docs for later ZIP export."""
    _zip_docs_cache[request_id] = (docs, title)


def _get_zip_docs(request_id: str) -> tuple[list[dict], str] | None:
    """Retrieve cached docs for ZIP export, or None if not found."""
    return _zip_docs_cache.get(request_id)


def _get_low_rating_threshold() -> int:
    """Return the low-rating threshold from env var, with safe fallback."""
    try:
        return int(os.getenv("LOW_RATING_THRESHOLD", "3"))
    except ValueError:
        logging.getLogger("decisiondoc.config").warning(
            "LOW_RATING_THRESHOLD is not a valid integer; using default 3"
        )
        return 3


def _load_pdf_builder():
    try:
        from app.services.pdf_service import build_pdf as _build_pdf
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export is not available in this deployment.",
        ) from exc
    return _build_pdf


def _auto_improve_if_needed(
    bundle_type: str,
    feedback_store: Any,
    override_store: Any,
    eval_store: Any,
) -> None:
    """저평점(≤2) 피드백이 임계값 이상 누적되면 패턴 분석 후 PromptOverrideStore에 저장.

    오버라이드 저장 후 활성 A/B 테스트가 없으면 새 A/B 테스트를 자동 생성합니다.
    백그라운드로 실행하지 않고 인라인으로 처리 (빠른 file I/O 작업만 수행).
    """
    try:
        low_rated = feedback_store.get_low_rated(bundle_type, max_rating=2)
        if len(low_rated) < _get_low_rating_threshold():
            return

        from app.services.prompt_optimizer import (
            analyze_feedback_patterns,
            generate_prompt_improvement,
        )
        from app.bundle_catalog.registry import get_bundle_spec

        report = analyze_feedback_patterns(low_rated, bundle_type)
        if not report.patterns:
            return

        bundle_spec = get_bundle_spec(bundle_type)
        current_hint = getattr(bundle_spec, "prompt_hint", "")
        improvement = generate_prompt_improvement(current_hint, report)

        # 개선 지시만 추출 (current_hint 제외)
        override_hint = improvement[len(current_hint):].strip()
        if not override_hint:
            return

        # 평균 heuristic_score 계산 (EvalStore에서)
        avg_score_before = 0.0
        try:
            records = eval_store.load_all()
            bundle_records = [r for r in records if r.bundle_id == bundle_type]
            if bundle_records:
                avg_score_before = sum(r.heuristic_score for r in bundle_records) / len(bundle_records)
        except Exception:
            pass

        override_store.save_override(
            bundle_id=bundle_type,
            override_hint=override_hint,
            trigger_reason="low_rating_pattern",
            avg_score_before=round(avg_score_before, 3),
        )
        logger.info(
            "[AutoImprove] Override saved for %s: %s",
            bundle_type,
            override_hint[:100],
        )

        # A/B 테스트 자동 생성 (활성 테스트가 없는 경우)
        try:
            import random
            from dataclasses import replace as _dc_replace
            from app.storage.ab_test_store import ABTestStore

            data_dir = Path(os.getenv("DATA_DIR", "./data"))
            ab_store = ABTestStore(data_dir=data_dir)
            if ab_store.get_active_test(bundle_type) is None:
                # Variant A = the override hint we just generated
                variant_a_hint = override_hint
                # Variant B = same patterns but shuffled order → different hint ordering
                shuffled_patterns = report.patterns[:]
                random.shuffle(shuffled_patterns)
                shuffled_report = _dc_replace(report, patterns=shuffled_patterns)
                variant_b_improvement = generate_prompt_improvement(current_hint, shuffled_report)
                variant_b_hint = variant_b_improvement[len(current_hint):].strip()
                if not variant_b_hint:
                    variant_b_hint = variant_a_hint  # fallback to same hint
                ab_store.create_test(bundle_type, variant_a_hint, variant_b_hint)
                logger.info(
                    "[ABTest] Started for %s: A=%s...",
                    bundle_type,
                    variant_a_hint[:60],
                )
        except Exception as exc:
            logger.warning("[ABTest] A/B 테스트 생성 실패 (무시): %s", exc)

    except Exception as exc:
        logger.warning("[AutoImprove] 오버라이드 저장 실패 (무시): %s", exc)


def _apply_generate_state(request: Request, result: dict, template_version: str) -> None:
    """Set all generate-related fields on request.state for observability middleware."""
    metadata = result["metadata"]
    timings = metadata.get("timings_ms", {})
    request.state.provider = metadata["provider"]
    request.state.template_version = template_version
    request.state.schema_version = metadata["schema_version"]
    request.state.cache_hit = metadata["cache_hit"]
    request.state.bundle_type = metadata.get("bundle_type")
    request.state.decision_council_project_id = metadata.get("project_id")
    request.state.doc_count = metadata.get("doc_count")
    request.state.llm_prompt_tokens = metadata.get("llm_prompt_tokens")
    request.state.llm_output_tokens = metadata.get("llm_output_tokens")
    request.state.llm_total_tokens = metadata.get("llm_total_tokens")
    request.state.provider_ms = timings.get("provider_ms")
    request.state.render_ms = timings.get("render_ms")
    request.state.lints_ms = timings.get("lints_ms")
    request.state.validator_ms = timings.get("validator_ms")
    request.state.procurement_handoff_used = metadata.get("procurement_handoff_used")
    request.state.decision_council_handoff_used = metadata.get("decision_council_handoff_used")
    request.state.decision_council_handoff_skipped_reason = metadata.get("decision_council_handoff_skipped_reason")
    request.state.decision_council_session_id = metadata.get("decision_council_session_id")
    request.state.decision_council_session_revision = metadata.get("decision_council_session_revision")
    request.state.decision_council_direction = metadata.get("decision_council_direction")
    request.state.decision_council_use_case = metadata.get("decision_council_use_case")
    request.state.decision_council_target_bundle = metadata.get("decision_council_target_bundle")
    request.state.decision_council_applied_bundle = metadata.get("decision_council_applied_bundle")


def _build_generate_log_event(request: Request, result: dict, request_id: str, template_version: str) -> dict:
    """Build the structured log event dict for a completed generate call."""
    metadata = result["metadata"]
    return {
        "event": "generate.completed",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": 200,
        "provider": metadata["provider"],
        "template_version": template_version,
        "schema_version": metadata["schema_version"],
        "cache_hit": metadata["cache_hit"],
        "bundle_type": metadata.get("bundle_type"),
        "project_id": metadata.get("project_id"),
        "doc_count": metadata.get("doc_count"),
        "llm_prompt_tokens": request.state.llm_prompt_tokens,
        "llm_output_tokens": request.state.llm_output_tokens,
        "llm_total_tokens": request.state.llm_total_tokens,
        "provider_ms": request.state.provider_ms,
        "render_ms": request.state.render_ms,
        "lints_ms": request.state.lints_ms,
        "validator_ms": request.state.validator_ms,
        "procurement_handoff_used": request.state.procurement_handoff_used,
        "decision_council_handoff_used": request.state.decision_council_handoff_used,
        "decision_council_handoff_skipped_reason": request.state.decision_council_handoff_skipped_reason,
        "decision_council_session_id": request.state.decision_council_session_id,
        "decision_council_session_revision": request.state.decision_council_session_revision,
        "decision_council_direction": request.state.decision_council_direction,
        "decision_council_use_case": request.state.decision_council_use_case,
        "decision_council_target_bundle": request.state.decision_council_target_bundle,
        "decision_council_applied_bundle": request.state.decision_council_applied_bundle,
    }


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _heuristic_score(content: str) -> int:
    """Simple heuristic scoring based on content characteristics."""
    score = 50
    if len(content) > 500:
        score += 10
    if len(content) > 1500:
        score += 10
    if "##" in content or "# " in content:
        score += 10  # Has headings
    if any(c in content for c in ["목표", "배경", "결정", "Goal", "Background"]):
        score += 10
    if len(content.split("\n")) > 10:
        score += 10  # Multi-line
    return min(score, 95)


def _ensure_procurement_bundle_enabled(bundle_type: str, request: Request) -> None:
    if bundle_type != "bid_decision_kr":
        return
    if getattr(request.app.state, "procurement_copilot_enabled", False):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "FEATURE_DISABLED",
            "message": "Public Procurement Go/No-Go Copilot is disabled in this environment.",
        },
    )


def _extract_latest_procurement_override_reason(notes: str) -> str | None:
    text = str(notes or "").strip()
    if not text:
        return None
    matches = list(
        re.finditer(
            r"\[override_reason ts=(?P<timestamp>[^\s]+) actor=(?P<actor>[^\]]+)\]\n(?P<reason>.*?)\n\[/override_reason\]",
            text,
            flags=re.DOTALL,
        )
    )
    if not matches:
        return None
    reason = matches[-1].group("reason").strip()
    return reason or None


def _ensure_procurement_override_reason_for_downstream(
    payload: GenerateRequest,
    request: Request,
    *,
    tenant_id: str,
) -> None:
    if payload.bundle_type not in _PROCUREMENT_OVERRIDE_REQUIRED_BUNDLE_IDS:
        return
    project_id = payload.project_id or ""
    if not project_id:
        return
    if not getattr(request.app.state, "procurement_copilot_enabled", False):
        return

    procurement_store = getattr(request.app.state, "procurement_store", None)
    if procurement_store is None:
        return

    record = procurement_store.get(project_id, tenant_id=tenant_id)
    if record is None or record.recommendation is None:
        return
    if record.recommendation.value != "NO_GO":
        return
    if _extract_latest_procurement_override_reason(record.notes):
        return

    request.state.error_code = "procurement_override_reason_required"
    request.state.bundle_type = payload.bundle_type
    request.state.procurement_action = "downstream_blocked"
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = "override_reason_required"
    request.state.procurement_recommendation = "NO_GO"
    raise HTTPException(
        status_code=409,
        detail={
            "code": "procurement_override_reason_required",
            "message": (
                f"현재 recommendation이 NO_GO이므로 "
                f"{_PROCUREMENT_BUNDLE_LABELS.get(payload.bundle_type, payload.bundle_type)} 생성을 진행하려면 "
                "project detail의 procurement panel에서 override 사유를 먼저 저장하세요."
            ),
            "project_id": project_id,
            "bundle_type": payload.bundle_type,
            "recommendation": "NO_GO",
            "required_action": "save_override_reason",
            "focus_field": "project-procurement-override-reason",
        },
    )


def _mark_procurement_downstream_resolved_context(
    payload: GenerateRequest,
    request: Request,
    *,
    tenant_id: str,
) -> None:
    if payload.bundle_type not in _PROCUREMENT_OVERRIDE_REQUIRED_BUNDLE_IDS:
        return
    project_id = payload.project_id or ""
    if not project_id:
        return
    if not getattr(request.app.state, "procurement_copilot_enabled", False):
        return

    procurement_store = getattr(request.app.state, "procurement_store", None)
    if procurement_store is None:
        return

    record = procurement_store.get(project_id, tenant_id=tenant_id)
    if record is None or record.recommendation is None:
        return
    if record.recommendation.value != "NO_GO":
        return
    if not _extract_latest_procurement_override_reason(record.notes):
        return

    request.state.bundle_type = payload.bundle_type
    request.state.procurement_action = "downstream_resolved"
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = "override_reason_present"
    request.state.procurement_recommendation = "NO_GO"


def _mark_decision_council_handoff_context(
    payload: GenerateRequest,
    request: Request,
    *,
    tenant_id: str,
) -> None:
    if payload.bundle_type not in _DECISION_COUNCIL_APPLIED_BUNDLE_IDS:
        return
    project_id = payload.project_id or ""
    if not project_id:
        return
    if not getattr(request.app.state, "procurement_copilot_enabled", False):
        return

    decision_council_store = getattr(request.app.state, "decision_council_store", None)
    if decision_council_store is None:
        return

    session = decision_council_store.get_latest(
        tenant_id=tenant_id,
        project_id=project_id,
        use_case="public_procurement",
        target_bundle_type="bid_decision_kr",
    )
    if session is None:
        return

    request.state.decision_council_handoff_used = True
    request.state.bundle_type = payload.bundle_type
    request.state.decision_council_project_id = project_id
    request.state.decision_council_session_id = session.session_id
    request.state.decision_council_session_revision = session.session_revision
    request.state.decision_council_direction = session.consensus.recommended_direction
    request.state.decision_council_use_case = session.use_case
    request.state.decision_council_target_bundle = session.target_bundle_type
    request.state.decision_council_applied_bundle = payload.bundle_type


# ── Shared generate core ──────────────────────────────────────────────────────

def _run_generate(req: GenerateRequest, request: Request) -> GenerateResponse:
    """Shared generate logic — called by both /generate and /generate/with-attachments."""
    _ensure_procurement_bundle_enabled(req.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and req.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{req.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(req, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(req, request, tenant_id=tenant_id)
    _mark_decision_council_handoff_context(req, request, tenant_id=tenant_id)
    result = service.generate_documents(req, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))
    metadata = result["metadata"]

    # 이력 자동 저장 (fire-and-forget)
    try:
        from datetime import datetime, timezone
        from app.storage.history_store import HistoryStore, HistoryEntry
        user_id = getattr(request.state, "user_id", None) or "anonymous"
        HistoryStore(tenant_id).add(HistoryEntry(
            entry_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            bundle_id=req.bundle_type,
            bundle_name=req.bundle_type,
            title=req.title,
            request_id=request_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            score=0.0,
            tags=[],
        ))
    except Exception as _he:
        logger.warning("[History] 이력 저장 실패 (무시): %s", _he)

    return GenerateResponse(
        request_id=request_id,
        bundle_id=metadata["bundle_id"],
        title=req.title,
        provider=metadata["provider"],
        schema_version=metadata["schema_version"],
        cache_hit=metadata["cache_hit"],
        llm_total_tokens=metadata.get("llm_total_tokens"),
        docs=result["docs"],
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/generate",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate(
    payload: GenerateRequest,
    request: Request,
) -> GenerateResponse:
    # Keep sync — providers use anyio.run() internally and require a thread-pool context.
    return _run_generate(payload, request)


@router.post(
    "/generate/with-attachments",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_with_attachments(
    request: Request,
    payload: str = Form(..., description="GenerateRequest as JSON string"),
    attachments: list[UploadFile] = File(default=[]),
) -> GenerateResponse:
    # Keep sync — file bytes read via upload.file.read() to stay in sync context.
    try:
        req = GenerateRequest.model_validate_json(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid payload JSON: {exc}") from exc

    if attachments:
        file_data: list[tuple[str, bytes]] = []
        for upload in attachments:
            if not upload.filename:
                continue
            raw = upload.file.read()
            if not raw:
                continue
            file_data.append((upload.filename, raw))
        if file_data:
            from app.services.rfp_parser import build_rfp_context
            combined = extract_multiple(file_data)
            rfp_context = build_rfp_context(combined)
            existing = req.context or ""
            merged = rfp_context + ("\n\n" + existing if existing else "")
            req = req.model_copy(update={"context": merged})

    return _run_generate(req, request)


@router.post(
    "/generate/from-documents",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_from_documents(
    request: Request,
    files: list[UploadFile] = File(..., description="지원 문서 파일 목록"),
    title: str = Form(default="", description="생성 문서 제목"),
    goal: str = Form(
        default="업로드 문서를 근거로 의사결정 문서를 작성합니다.",
        description="생성 목표",
    ),
    context: str = Form(default="", description="추가 컨텍스트"),
    doc_types: str = Form(
        default="adr,onepager,eval_plan,ops_checklist",
        description="생성할 문서 유형 (콤마 구분)",
    ),
    bundle_type: str = Form(default="tech_decision", description="번들 유형"),
    tenant_id: str = Form(default="default", description="테넌트 ID"),
) -> GenerateResponse:
    """Upload one or more documents and generate a bundle directly from them."""
    from app.schemas import GenerateRequest as _GenerateRequest

    combined_text, parsed_filenames = _extract_uploaded_documents(files)
    doc_types_list = [dt.strip() for dt in doc_types.split(",") if dt.strip()]
    merged_context = combined_text + ("\n\n" + context if context else "")
    first_name = parsed_filenames[0]
    default_title = Path(first_name).stem

    try:
        req = _GenerateRequest(
            title=title.strip() or default_title,
            goal=goal,
            context=merged_context,
            doc_types=doc_types_list,
            bundle_type=bundle_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"요청 생성 실패: {exc}") from exc

    request.state.document_ingestion_files = parsed_filenames
    log_event(
        logger,
        {
            "event": "generate.from_documents.started",
            "request_id": request.state.request_id,
            "bundle_type": bundle_type,
            "files_count": len(parsed_filenames),
            "files": parsed_filenames,
            "tenant_id": tenant_id,
        },
    )

    return _run_generate(req, request)


@router.post(
    "/generate/from-pdf",
    response_model=GenerateResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_from_pdf(
    request: Request,
    file: UploadFile = File(..., description="PDF 파일 (최대 20MB)"),
    doc_types: str = Form(default="adr,onepager", description="생성할 문서 유형 (콤마 구분)"),
    tenant_id: str = Form(default="default", description="테넌트 ID"),
) -> GenerateResponse:
    """PDF 파일을 업로드하여 구조화된 의사결정 문서를 생성합니다.

    PDF에서 텍스트를 구조화 추출한 뒤 GenerationService를 통해 문서 번들을 생성합니다.
    """
    from app.schemas import GenerateRequest as _GenerateRequest

    # ── Validate file ──────────────────────────────────────────────────────────
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="PDF 파일만 허용됩니다.")

    raw = file.file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="파일 크기가 20MB를 초과합니다.")

    # ── Structured extraction ──────────────────────────────────────────────────
    try:
        structured = extract_pdf_structured(raw, filename)
    except AttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Build requirements ─────────────────────────────────────────────────────
    filename_stem = Path(filename).stem
    doc_types_list = [dt.strip() for dt in doc_types.split(",") if dt.strip()]

    requirements: dict = {
        "title": structured["title"] or filename_stem,
        "background": f"PDF 문서 '{filename}'에서 추출된 내용을 기반으로 문서를 재구성합니다.",
        "pdf_source": structured["raw_text"],
        "pdf_sections": json.dumps(
            [s["heading"] for s in structured["sections"]], ensure_ascii=False
        ),
        "doc_types": doc_types_list,
    }

    # ── Build GenerateRequest ──────────────────────────────────────────────────
    try:
        req = _GenerateRequest(
            title=requirements["title"],
            goal=f"PDF 문서 '{filename}'의 내용을 기반으로 의사결정 문서를 작성합니다.",
            context=structured["raw_text"][:3000],
            doc_types=doc_types_list,
            bundle_type="tech_decision",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"요청 생성 실패: {exc}") from exc

    # Inject PDF-specific fields into the requirements dict that will reach the
    # prompt builder via GenerationService (stored as req attributes are not
    # directly accessible; we piggyback on context which is already set).
    # We also attach them as extra state so the prompt builder can detect them.
    request.state.pdf_source = structured["raw_text"]
    request.state.pdf_structured = structured

    log_event(
        logger,
        {
            "event": "generate.from_pdf.started",
            "request_id": request.state.request_id,
            "filename": filename,
            "page_count": structured["page_count"],
            "has_tables": structured["has_tables"],
            "sections_count": len(structured["sections"]),
        },
    )

    return _run_generate(req, request)


@router.post(
    "/generate/export",
    response_model=GenerateExportResponse,
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_export(
    payload: GenerateRequest,
    request: Request,
) -> GenerateExportResponse:
    # Keep sync endpoints to avoid nested event-loop issues because providers use anyio.run internally.
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    storage = request.app.state.storage
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    docs = result["docs"]
    bundle_id = result["metadata"]["bundle_id"]
    export_timer = Timer()
    with export_timer.measure("export_ms"):
        # Pre-compute all file metadata before any writes to keep files/paths consistent
        planned = [
            {
                "doc_type": doc["doc_type"],
                "markdown": doc["markdown"],
                "path": storage.get_export_path(bundle_id, doc["doc_type"]),
            }
            for doc in docs
        ]
        for item in planned:
            storage.save_export(bundle_id, item["doc_type"], item["markdown"])
        files = [{"doc_type": item["doc_type"], "path": item["path"]} for item in planned]
        export_dir = storage.get_export_dir(bundle_id)

    _apply_generate_state(request, result, template_version)
    request.state.export_ms = export_timer.durations_ms.get("export_ms")

    log_event_data = _build_generate_log_event(request, result, request_id, template_version)
    log_event_data["export_ms"] = request.state.export_ms
    log_event(logger, log_event_data)

    metadata = result["metadata"]
    return GenerateExportResponse(
        request_id=request_id,
        bundle_id=bundle_id,
        title=payload.title,
        provider=metadata["provider"],
        schema_version=metadata["schema_version"],
        cache_hit=metadata["cache_hit"],
        export_dir=str(export_dir),
        files=files,
    )


@router.post(
    "/generate/pptx",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_pptx_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate a PPTX skeleton from a presentation_kr bundle and return it as a download."""
    if payload.bundle_type != "presentation_kr":
        raise BundleNotSupportedError(payload.bundle_type, "generate/pptx")

    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    slide_data = result["raw_bundle"].get("slide_structure", {})
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    pptx_bytes = build_pptx(slide_data, title=payload.title)

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"presentation.pptx\"; "
                f"filename*=UTF-8''{encoded_title}.pptx"
            )
        },
    )


@router.post(
    "/generate/stream",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def generate_stream(
    payload: GenerateRequest,
    request: Request,
) -> StreamingResponse:
    """SSE streaming endpoint — yields progress events every 2 s, then the final result."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    project_store = request.app.state.project_store
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(status_code=403, detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.")
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    _mark_decision_council_handoff_context(payload, request, tenant_id=tenant_id)
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _worker() -> None:
        try:
            result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
            loop.call_soon_threadsafe(q.put_nowait, ("done", result))
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(q.put_nowait, ("error", exc))

    async def _event_stream():
        threading.Thread(target=_worker, daemon=True).start()
        _STEPS = [
            "AI가 문서를 생성하는 중...",
            "번들 스키마를 검증하는 중...",
            "문서를 렌더링하는 중...",
            "품질 검사를 수행하는 중...",
        ]
        step = 0
        while True:
            try:
                event_type, data = await asyncio.wait_for(q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                msg = _STEPS[step % len(_STEPS)]
                step += 1
                yield f"event: progress\ndata: {json.dumps({'step': step, 'msg': msg})}\n\n"
                if step > 80:  # 160 s hard limit
                    yield (
                        f"event: error\ndata: "
                        f"{json.dumps({'code': 'STREAM_TIMEOUT', 'message': '응답 시간 초과'})}\n\n"
                    )
                    return
                continue

            if event_type == "done":
                result = data
                _apply_generate_state(request, result, template_version)
                log_event(
                    logger,
                    _build_generate_log_event(request, result, request_id, template_version),
                )
                metadata = result["metadata"]
                resp = GenerateResponse(
                    request_id=request_id,
                    bundle_id=metadata["bundle_id"],
                    title=payload.title,
                    provider=metadata["provider"],
                    schema_version=metadata["schema_version"],
                    cache_hit=metadata["cache_hit"],
                    llm_total_tokens=metadata.get("llm_total_tokens"),
                    docs=result["docs"],
                )
                yield f"event: complete\ndata: {resp.model_dump_json()}\n\n"
                # Auto-link to project if project_id provided
                if getattr(payload, "project_id", None):
                    try:
                        project_store.add_document(
                            project_id=payload.project_id,
                            request_id=request_id,
                            bundle_id=payload.bundle_type,
                            title=payload.title,
                            docs=result["docs"],
                            approval_id=None,
                            tags=[],
                            source_decision_council_session_id=metadata.get("decision_council_session_id"),
                            source_decision_council_session_revision=metadata.get("decision_council_session_revision"),
                            source_decision_council_direction=metadata.get("decision_council_direction"),
                        )
                    except Exception:
                        pass  # project link is non-critical
                return
            else:  # error
                err = json.dumps({"code": type(data).__name__, "message": str(data)})
                yield f"event: error\ndata: {err}\n\n"
                return

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/generate/docx",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_docx_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate a .docx from any bundle and return it as a download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    docx_bytes = build_docx(result["docs"], title=payload.title, gov_options=None)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.docx\"; "
                f"filename*=UTF-8''{encoded_title}.docx"
            )
        },
    )


@router.post(
    "/generate/pdf",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def generate_pdf_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate a PDF from any bundle via Playwright and return as download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    build_pdf = _load_pdf_builder()
    pdf_bytes = await build_pdf(result["docs"], title=payload.title, gov_options=None)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.pdf\"; "
                f"filename*=UTF-8''{encoded_title}.pdf"
            )
        },
    )


@router.post(
    "/generate/excel",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_excel_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate an Excel (.xlsx) from any bundle and return as download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    excel_bytes = build_excel(result["docs"], title=payload.title)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.xlsx\"; "
                f"filename*=UTF-8''{encoded_title}.xlsx"
            )
        },
    )


@router.post(
    "/generate/hwp",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_hwp_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> Response:
    """Generate an hwpx (HancomOffice) file from any bundle and return as download."""
    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    service = request.app.state.service
    template_version = request.app.state.template_version
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    _ensure_procurement_override_reason_for_downstream(payload, request, tenant_id=tenant_id)
    _mark_procurement_downstream_resolved_context(payload, request, tenant_id=tenant_id)
    result = service.generate_documents(payload, request_id=request_id, tenant_id=tenant_id)
    _apply_generate_state(request, result, template_version)
    log_event(logger, _build_generate_log_event(request, result, request_id, template_version))

    safe_title = re.sub(r'[\\/*?:"<>|]', "_", payload.title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    hwp_bytes = build_hwp(result["docs"], title=payload.title, gov_options=None)

    return Response(
        content=hwp_bytes,
        media_type="application/hwp+zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.hwpx\"; "
                f"filename*=UTF-8''{encoded_title}.hwpx"
            )
        },
    )


@router.post(
    "/generate/export-edited",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def generate_export_edited_endpoint(
    payload: EditedExportRequest,
    request: Request,
) -> Response:
    """Export pre-rendered (possibly user-edited) docs to the requested format.

    Does **not** call the LLM — uses the docs list directly.
    Supported formats: docx, pdf, excel, hwp.
    """
    docs = [{"doc_type": d.doc_type, "markdown": d.markdown} for d in payload.docs]
    title = payload.title or "문서"
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    fmt = payload.format.lower().lstrip(".")
    gov_opts = _resolve_gov_options(payload.gov_options)

    if fmt == "docx":
        content = build_docx(docs, title=title, gov_options=gov_opts)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif fmt == "pdf":
        build_pdf = _load_pdf_builder()
        content = await build_pdf(docs, title=title, gov_options=gov_opts)
        media_type = "application/pdf"
        ext = "pdf"
    elif fmt in ("excel", "xlsx"):
        content = build_excel(docs, title=title)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif fmt in ("hwp", "hwpx"):
        content = build_hwp(docs, title=title, gov_options=gov_opts)
        media_type = "application/hwp+zip"
        ext = "hwpx"
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다: {payload.format}")

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document.{ext}\"; "
                f"filename*=UTF-8''{encoded_title}.{ext}"
            )
        },
    )


@router.post(
    "/generate/rewrite-section",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def rewrite_section_endpoint(
    body: SectionRewriteRequest,
    request: Request,
) -> dict:
    """Rewrite a single document section with AI guidance.

    Calls the LLM with the current section content + user instruction and
    returns only the rewritten markdown body (no section title).
    """
    request_id = request.state.request_id
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    provider = get_provider_for_bundle(body.bundle_id, tenant_id)

    prompt = (
        f"You are rewriting one section of a {body.bundle_id} document.\n"
        f"Current section title: {body.section_title}\n"
        f"Current content:\n{body.current_content}\n\n"
        f"User's rewrite instruction: {body.instruction}\n\n"
        "Rewrite this section following the instruction.\n"
        "Return only the rewritten section content in markdown format.\n"
        "Do not include the section title in your response.\n"
        "Keep the same language (Korean) as the original."
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: provider.generate_raw(
            prompt,
            request_id=request_id,
            max_output_tokens=1500,
        ),
    )
    return {"rewritten": result}


@router.post(
    "/generate/sketch",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_sketch_endpoint(
    payload: GenerateRequest,
    request: Request,
) -> dict:
    """Generate a quick document sketch/outline before full generation."""
    import dataclasses
    from app.bundle_catalog.registry import get_bundle_spec
    from app.services.sketch_service import generate_sketch

    _ensure_procurement_bundle_enabled(payload.bundle_type, request)
    data_dir = request.app.state.data_dir
    search_service = request.app.state.search_service
    request_id = request.state.request_id
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.allowed_bundles and payload.bundle_type not in tenant.allowed_bundles:
        raise HTTPException(
            status_code=403,
            detail=f"Bundle '{payload.bundle_type}' is not allowed for this tenant.",
        )
    bundle_spec = get_bundle_spec(payload.bundle_type)
    provider = get_provider()
    result = generate_sketch(
        payload.model_dump(),
        provider,
        bundle_spec,
        search_service=search_service,
        request_id=request_id,
    )

    # Record request for pattern analysis
    try:
        from app.storage.request_pattern_store import RequestPatternStore
        pattern_store = RequestPatternStore(data_dir)
        raw_input = f"{payload.title} {payload.goal}".strip()[:200]
        pattern_store.record_request(raw_input, bundle_id=payload.bundle_type, matched=True)
    except Exception:
        pass

    return dataclasses.asdict(result)


@router.post(
    "/generate/refine",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_refine_endpoint(payload: dict, request: Request) -> dict:
    """생성된 문서의 특정 섹션을 재작성하거나 보완합니다.

    payload:
      - section_content: 원본 섹션 텍스트 (마크다운)
      - instruction: 개선 지시 (예: "더 간결하게", "영어 용어를 한국어로", "수치 예시 추가")
      - context: 전체 문서 맥락 (optional)
      - bundle_type: 번들 타입 (optional, 스타일 힌트용)
    """
    section_content = (payload.get("section_content") or "").strip()
    instruction = (payload.get("instruction") or "").strip()
    context = (payload.get("context") or "").strip()
    if not section_content:
        raise HTTPException(status_code=422, detail="section_content는 필수입니다.")
    if not instruction:
        raise HTTPException(status_code=422, detail="instruction(개선 지시)은 필수입니다.")
    if len(section_content) > 8000:
        raise HTTPException(status_code=422, detail="section_content는 8000자 이내여야 합니다.")

    prompt = (
        "당신은 전문 문서 편집자입니다. "
        "아래 섹션을 주어진 지시에 따라 개선해주세요.\n"
        "원본 내용의 핵심 정보는 유지하되, 지시 사항을 충실히 반영하세요.\n"
        "마크다운 형식을 그대로 유지하고, 결과만 출력하세요.\n\n"
        f"[개선 지시]\n{instruction}\n\n"
        f"[원본 섹션]\n{section_content}\n"
    )
    if context:
        prompt += f"\n[문서 맥락 참고]\n{context[:1000]}\n"
    prompt += "\n[개선된 섹션]"

    provider = get_provider()
    request_id = request.state.request_id
    try:
        refined = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=2000)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI 처리 오류: {str(e)}")

    return {
        "refined_content": refined.strip(),
        "original_length": len(section_content),
        "refined_length": len(refined.strip()),
        "request_id": request_id,
    }


@router.post(
    "/generate/related",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_related_endpoint(payload: dict, request: Request) -> dict:
    """현재 생성된 번들과 관련된 추가 문서/번들을 추천합니다.

    payload:
      - bundle_id: 현재 번들 ID (필수)
      - title: 문서 제목
      - goal: 문서 목표
    """
    from app.bundle_catalog.registry import BUNDLE_REGISTRY

    bundle_id = (payload.get("bundle_id") or "").strip()
    title = (payload.get("title") or "").strip()
    goal = (payload.get("goal") or "").strip()

    if not bundle_id:
        raise HTTPException(status_code=422, detail="bundle_id는 필수입니다.")

    current_spec = BUNDLE_REGISTRY.get(bundle_id)

    # 현재 번들의 카테고리/태그 기반 관련 번들 찾기
    related: list[dict] = []
    text = f"{title} {goal} {bundle_id}".lower()

    for bid, spec in BUNDLE_REGISTRY.items():
        if bid == bundle_id:
            continue
        meta = spec.ui_metadata()
        score = 0
        # 카테고리 일치
        if current_spec and meta.get("category") == current_spec.ui_metadata().get("category"):
            score += 2
        # 태그 겹침
        if current_spec:
            cur_tags = set(current_spec.ui_metadata().get("tags", []))
            rel_tags = set(meta.get("tags", []))
            score += len(cur_tags & rel_tags)
        # 키워드 매칭
        for kw in (meta.get("name_ko", "") + " " + meta.get("description_ko", "")).lower().split():
            if len(kw) > 1 and kw in text:
                score += 1

        if score > 0:
            related.append({
                "bundle_id": bid,
                "name_ko": meta.get("name_ko", bid),
                "name_en": meta.get("name_en", bid),
                "description_ko": meta.get("description_ko", ""),
                "category": meta.get("category", ""),
                "relevance_score": score,
            })

    # 점수 내림차순, 최대 5개
    related.sort(key=lambda x: x["relevance_score"], reverse=True)

    return {
        "current_bundle_id": bundle_id,
        "related": related[:5],
        "request_id": request.state.request_id,
    }


@router.post(
    "/generate/summary",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_summary_endpoint(payload: dict, request: Request) -> dict:
    """생성된 문서 전체를 3줄 한국어 요약으로 압축합니다.

    payload:
      - content: 요약할 마크다운 텍스트 (필수)
      - max_sentences: 최대 문장 수 (기본 3, 최대 10)
      - audience: 대상 독자 힌트 (예: '임원', '개발자', '일반')
    """
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="content는 필수입니다.")
    if len(content) > 20000:
        raise HTTPException(status_code=422, detail="content는 20,000자 이내여야 합니다.")

    max_sentences = min(int(payload.get("max_sentences") or 3), 10)
    audience = (payload.get("audience") or "일반").strip()

    prompt = (
        f"다음 문서를 {audience} 독자를 위해 핵심 내용 {max_sentences}문장으로 요약해주세요.\n"
        "각 문장은 구체적이고 명확해야 합니다.\n"
        "불릿 포인트나 헤더 없이 자연스러운 문장으로 작성하세요.\n\n"
        f"[원본 문서]\n{content[:10000]}\n\n"
        "[요약]"
    )

    provider = get_provider()
    request_id = request.state.request_id
    try:
        summary = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=500)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI 처리 오류: {str(e)}")

    return {
        "summary": summary.strip(),
        "original_length": len(content),
        "summary_length": len(summary.strip()),
        "audience": audience,
        "request_id": request_id,
    }


@router.post(
    "/generate/validate",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def validate_generate_endpoint(payload: dict, request: Request) -> dict:
    """생성 요청 사전 검증. 오류/경고 목록을 반환하며 실제 생성은 수행하지 않습니다."""
    from app.bundle_catalog.registry import BUNDLE_REGISTRY

    errors: list[dict] = []
    warnings: list[dict] = []

    title = (payload.get("title") or "").strip()
    goal = (payload.get("goal") or "").strip()
    bundle_type = (payload.get("bundle_type") or "tech_decision").strip()

    # 필수 필드 검사
    if not title:
        errors.append({"field": "title", "code": "required", "message": "제목은 필수 입력 항목입니다."})
    elif len(title) < 4:
        errors.append({"field": "title", "code": "too_short", "message": "제목은 4자 이상 입력해주세요."})
    elif len(title) > 300:
        warnings.append({"field": "title", "code": "too_long", "message": "제목이 너무 깁니다. 300자 이내를 권장합니다."})

    if not goal:
        errors.append({"field": "goal", "code": "required", "message": "목표는 필수 입력 항목입니다."})
    elif len(goal) < 4:
        errors.append({"field": "goal", "code": "too_short", "message": "목표는 4자 이상 입력해주세요."})
    elif len(goal) > 1000:
        warnings.append({"field": "goal", "code": "too_long", "message": "목표가 너무 깁니다. 1000자 이내를 권장합니다."})

    # 번들 타입 검사
    if bundle_type not in BUNDLE_REGISTRY:
        errors.append({"field": "bundle_type", "code": "invalid", "message": f"유효하지 않은 번들 타입입니다: {bundle_type}"})

    # 배경/맥락 권장
    context = (payload.get("context") or payload.get("background") or "").strip()
    if not context and not errors:
        warnings.append({"field": "context", "code": "recommended", "message": "배경/맥락을 추가하면 더 정확한 문서가 생성됩니다."})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "request_id": request.state.request_id,
    }


@router.post(
    "/generate/freeform",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_freeform_endpoint(
    payload: FreeformRequest,
    request: Request,
) -> dict:
    """Record an unmatched document request for future pattern analysis.

    Use this endpoint when no existing bundle fits the user's needs.
    Accumulated unmatched requests trigger auto bundle expansion via
    POST /admin/expand-bundles.
    """
    from app.storage.request_pattern_store import RequestPatternStore

    data_dir = request.app.state.data_dir
    pattern_store = RequestPatternStore(data_dir)
    raw_input = f"{payload.title} {payload.goal}".strip()[:200]
    pattern_store.record_request(raw_input, bundle_id=None, matched=False)
    return {
        "message": "요청이 기록되었습니다. 패턴 분석 후 새 번들이 생성될 수 있습니다.",
        "request_id": request.state.request_id,
    }


@router.post(
    "/generate/review",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_review_endpoint(payload: dict, request: Request) -> dict:
    """AI-powered quality review of a generated document."""
    request_id = str(uuid.uuid4())

    content = (payload.get("content") or "").strip()
    bundle_type = (payload.get("bundle_type") or "").strip()

    # Validation
    errors = []
    if not content:
        errors.append({"field": "content", "message": "content는 필수 항목입니다."})
    elif len(content) > 30000:
        errors.append({"field": "content", "message": f"content는 30,000자를 초과할 수 없습니다. (현재: {len(content)}자)"})

    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors, "request_id": request_id})

    provider = get_provider()

    bundle_hint = f"\n번들 유형: {bundle_type}" if bundle_type else ""
    prompt = (
        "당신은 전문 문서 품질 검토자입니다.\n"
        "아래 문서를 검토하고 JSON 형식으로 평가 결과를 반환하세요.\n"
        f"{bundle_hint}\n\n"
        "평가 기준: 명확성, 완결성, 논리적 흐름, 전문성, 실행 가능성\n\n"
        "Return ONLY valid JSON:\n"
        '{"score": <0-100 integer>, '
        '"grade": "<S|A|B|C|D>", '
        '"strengths": ["<강점1>", "<강점2>", "<강점3>"], '
        '"improvements": ["<개선사항1>", "<개선사항2>", "<개선사항3>"], '
        '"summary": "<2-3문장 종합 의견>"}\n\n'
        f"문서 내용:\n{content[:8000]}"
    )

    try:
        raw = provider.generate_raw(prompt, request_id=request_id)
        # Extract JSON from response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError("No JSON found")
        data = json.loads(match.group())
        score = int(data.get("score", 75))
        score = max(0, min(100, score))
        return {
            "score": score,
            "grade": data.get("grade", _score_to_grade(score)),
            "strengths": data.get("strengths", [])[:5],
            "improvements": data.get("improvements", [])[:5],
            "summary": data.get("summary", ""),
            "content_length": len(content),
            "request_id": request_id,
        }
    except Exception as e:
        logger.warning(f"Review generation failed: {e}")
        # Fallback: return heuristic review
        score = _heuristic_score(content)
        return {
            "score": score,
            "grade": _score_to_grade(score),
            "strengths": ["구조화된 내용", "명확한 목적"],
            "improvements": ["더 구체적인 수치나 지표 추가", "결론 및 다음 단계 명확화"],
            "summary": "문서가 생성되었습니다. 세부 내용을 보강하면 품질이 향상됩니다.",
            "content_length": len(content),
            "request_id": request_id,
        }


@router.post(
    "/generate/translate",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def generate_translate_endpoint(payload: dict, request: Request) -> dict:
    """AI-powered document translation (Korean <-> English).

    payload:
      - content: 번역할 마크다운 텍스트 (필수, 최대 20,000자)
      - target_lang: 대상 언어 'ko' 또는 'en' (기본 'en')
      - preserve_structure: 마크다운 구조 유지 여부 (기본 true)
    """
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="content는 필수입니다.")
    if len(content) > 20000:
        raise HTTPException(status_code=422, detail="content는 20,000자 이내여야 합니다.")

    target_lang = (payload.get("target_lang") or "en").strip().lower()
    if target_lang not in ("ko", "en"):
        raise HTTPException(status_code=422, detail="target_lang은 'ko' 또는 'en'이어야 합니다.")

    preserve = payload.get("preserve_structure", True)

    lang_name = "영어" if target_lang == "en" else "한국어"
    structure_hint = "마크다운 헤더(#), 리스트(-), 강조(**) 등 원본 구조를 그대로 유지하세요." if preserve else ""

    prompt = (
        f"다음 문서를 {lang_name}로 번역하세요.\n"
        f"{structure_hint}\n"
        "전문 용어는 적절히 번역하되 원어를 괄호 안에 병기하세요 (예: 의사결정기록문서(ADR)).\n"
        "번역문만 출력하고 설명은 포함하지 마세요.\n\n"
        f"{content[:15000]}"
    )

    provider = get_provider()
    request_id = request.state.request_id
    try:
        translated = provider.generate_raw(
            prompt, request_id=request_id, max_output_tokens=4000
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI 처리 오류: {str(e)}")

    return {
        "translated_content": translated.strip(),
        "target_lang": target_lang,
        "original_length": len(content),
        "translated_length": len(translated.strip()),
        "request_id": request_id,
    }


@router.get(
    "/generate/export-zip",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
def export_zip(request: Request, request_id: str, formats: str = "docx"):
    """Export cached generation results as a ZIP of converted files."""
    _require_auth(request)
    cached = _get_zip_docs(request_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="No cached documents found for this request_id.")
    docs, title = cached

    valid_formats = {"docx", "pdf", "xlsx", "hwp", "pptx"}
    requested = [f.strip().lower() for f in formats.split(",") if f.strip()]
    actual_formats = [f for f in requested if f in valid_formats]
    if not actual_formats:
        raise HTTPException(status_code=400, detail=f"No valid formats requested. Valid: {', '.join(sorted(valid_formats))}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fmt in actual_formats:
            try:
                if fmt == "docx":
                    content = build_docx(docs, title=title)
                    zf.writestr(f"{title or 'document'}.docx", content)
                elif fmt == "pdf":
                    from app.services.pdf_service import build_pdf
                    content = asyncio.get_event_loop().run_until_complete(build_pdf(docs, title=title))
                    zf.writestr(f"{title or 'document'}.pdf", content)
                elif fmt == "xlsx":
                    content = build_excel(docs, title=title)
                    zf.writestr(f"{title or 'document'}.xlsx", content)
                elif fmt == "hwp":
                    content = build_hwp(docs, title=title)
                    zf.writestr(f"{title or 'document'}.hwp", content)
                elif fmt == "pptx":
                    content = build_pptx(docs[0] if docs else {}, title=title)
                    zf.writestr(f"{title or 'document'}.pptx", content)
            except Exception:
                logger.warning("Failed to convert to %s", fmt, exc_info=True)
    buf.seek(0)
    safe_title = urllib.parse.quote(title[:50], safe="") if title else "export"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.zip"'},
    )


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest, request: Request) -> FeedbackResponse:
    feedback_store = request.app.state.feedback_store
    prompt_override_store = request.app.state.prompt_override_store
    eval_store = request.app.state.eval_store
    finetune_store = request.app.state.finetune_store

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
    )

    # ── Trigger A: high user rating → collect fine-tune record ───────────
    try:
        from app.config import get_finetune_min_rating
        gen_request_id = payload.request_id or ""
        if payload.rating >= get_finetune_min_rating() and gen_request_id:
            from app.services.generation_service import get_generation_context
            ctx = get_generation_context(gen_request_id)
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

    file_data: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        if raw and f.filename:
            file_data.append((f.filename, raw))

    if not file_data:
        raise HTTPException(status_code=422, detail="파일이 없거나 비어 있습니다.")

    combined = extract_multiple(file_data)
    provider = get_provider_for_bundle("rfp_analysis_kr", tenant_id)
    fields = parse_rfp_fields(combined, provider=provider, request_id=request_id)
    structured_context = build_rfp_context(combined[:6_000])

    return {
        "extracted_fields": fields,
        "raw_text_preview": combined[:2_000],
        "total_chars": len(combined),
        "structured_context": structured_context,
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

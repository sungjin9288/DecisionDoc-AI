"""app/routers/generate/_shared.py — Shared constants and helpers for the generate router package.

Split out of the former app/routers/generate.py (2,170 lines) to keep each
sub-module under the file-size limit. Contains:
  - module-level constants used across generate sub-routers
  - attachment / upload helpers shared by core.py and ops.py
  - visual-asset / structured-slide helpers shared by export.py
  - request.state / log-event helpers shared by core.py and export.py
  - procurement + decision-council context helpers shared by core.py, export.py
  - the `_run_generate` core pipeline used by core.py

Pure code relocation — no behavior changes.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, UploadFile

from app.ai_profiles.catalog import ensure_bundle_access
from app.observability.logging import log_event
from app.providers.factory import get_provider_for_capability
from app.schemas import GenerateRequest, GenerateResponse, GovDocOptions
from app.services.attachment_service import (
    AttachmentError,
    MAX_TOTAL_CHARS,
)

logger = logging.getLogger("decisiondoc.generate")


def _facade():
    """Return the `app.routers.generate` package module.

    Several existing tests patch library functions (e.g. ``extract_pdf_structured``,
    ``generate_visual_assets_from_docs``) via
    ``unittest.mock.patch("app.routers.generate.<name>", ...)`` — a pattern
    written against the pre-split single-file module. Looking the callables up
    on the facade module at call time (instead of using the module-level
    imports directly) keeps those patches effective after the split into this
    package. Imported lazily to avoid a circular import at module load time.
    """
    import app.routers.generate as _generate_pkg

    return _generate_pkg

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
_LEGACY_BINARY_HWP_GUIDANCE = "구형 바이너리 .hwp 파일은 직접 분석하지 못합니다. HWPX, PDF 또는 DOCX로 변환해 다시 업로드하세요."


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


def _legacy_binary_hwp_upload_names(files: list[UploadFile]) -> list[str]:
    blocked: list[str] = []
    for upload in files:
        filename = str(getattr(upload, "filename", "") or "").strip()
        lower = filename.lower()
        if lower.endswith(".hwp") and not lower.endswith(".hwpx"):
            blocked.append(filename or "attachment.hwp")
    return blocked


def _raise_if_legacy_binary_hwp_uploads(files: list[UploadFile]) -> None:
    blocked = _legacy_binary_hwp_upload_names(files)
    if not blocked:
        return
    preview = ", ".join(blocked[:3])
    extra = f" 외 {len(blocked) - 3}건" if len(blocked) > 3 else ""
    raise AttachmentError(f"{preview}{extra}: {_LEGACY_BINARY_HWP_GUIDANCE}")


def _extract_uploaded_documents(
    files: list[UploadFile],
    *,
    provider: Any | None = None,
    request_id: str = "",
) -> tuple[str, list[str], str]:
    """Extract uploaded files into one generation-ready context block.

    Returns the merged text and a list of successfully parsed filenames.
    Raises ``HTTPException`` when all files fail so the caller does not generate
    docs from warning-only placeholders.
    """
    parts: list[str] = []
    parsed_filenames: list[str] = []
    file_data: list[tuple[str, bytes]] = []
    total = 0
    errors: list[str] = []

    for upload in files:
        filename = upload.filename or "attachment"
        raw = upload.file.read()
        if not raw:
            continue
        file_data.append((filename, raw))

        try:
            text = _facade().extract_text_with_ai_fallback(
                filename,
                raw,
                provider=provider,
                request_id=request_id,
            )
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

    return "\n\n---\n\n".join(parts), parsed_filenames, _build_procurement_attachment_context(file_data)


def _build_procurement_attachment_context(file_data: list[tuple[str, bytes]]) -> str:
    """Best-effort procurement-oriented summary for uploaded PDF attachments."""
    from app.services.procurement_pdf_normalizer import build_procurement_pdf_context

    blocks: list[str] = []
    for filename, raw in file_data:
        if Path(filename).suffix.lower() != ".pdf":
            continue
        try:
            structured = _facade().extract_pdf_structured(raw, filename)
        except Exception:
            continue
        block = build_procurement_pdf_context(structured, filename)
        if block:
            blocks.append(block)

    if not blocks:
        return ""
    return "\n\n".join(blocks)[:4_000]


def _generate_visual_assets_for_docs(
    docs: list[dict[str, Any]],
    *,
    title: str,
    goal: str,
    bundle_type: str,
    tenant_id: str,
    request_id: str,
) -> list[dict[str, Any]]:
    if not any(isinstance(doc, dict) and isinstance(doc.get("slide_outline"), list) and doc.get("slide_outline") for doc in docs):
        return []
    try:
        return _facade().generate_visual_assets_from_docs(
            docs,
            title=title,
            goal=goal,
            provider=get_provider_for_capability("visual"),
            request_id=request_id,
            max_assets=6,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[VisualAssets] Export visual asset generation failed: %s", exc)
        return []


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


def _build_structured_slide_data(bundle: dict[str, Any], goal: str) -> dict[str, Any] | None:
    """Collect slide outline metadata embedded in bundle docs."""
    slide_outline: list[dict[str, Any]] = []
    page = 1

    for value in bundle.values():
        if not isinstance(value, dict):
            continue
        outline = value.get("slide_outline")
        if not isinstance(outline, list) or not outline:
            continue
        for item in outline:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title or "PPT 구성 가이드" in title:
                continue
            slide_outline.append({
                "page": page,
                "title": title,
                "key_content": str(item.get("key_content", "")).strip(),
                "core_message": str(item.get("core_message", "")).strip(),
                "evidence_points": [
                    str(point).strip()
                    for point in item.get("evidence_points", [])
                    if str(point).strip()
                ],
                "visual_type": str(item.get("visual_type", "")).strip(),
                "visual_brief": str(item.get("visual_brief", "")).strip(),
                "layout_hint": str(item.get("layout_hint", "")).strip(),
                "design_tip": str(item.get("design_tip", "")).strip(),
            })
            page += 1

    if not slide_outline:
        return None

    return {
        "presentation_goal": str(goal).strip(),
        "slide_outline": slide_outline,
    }


def _build_generated_docs_response(
    docs: list[dict[str, Any]],
    raw_bundle: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Attach structured slide metadata to rendered docs when present."""
    raw_bundle = raw_bundle if isinstance(raw_bundle, dict) else {}
    response_docs: list[dict[str, Any]] = []
    for doc in docs:
        doc_type = str(doc.get("doc_type", "") or "").strip()
        markdown = str(doc.get("markdown", "") or "")
        item: dict[str, Any] = {
            "doc_type": doc_type,
            "markdown": markdown,
        }
        structured = raw_bundle.get(doc_type)
        if isinstance(structured, dict):
            total_slides = structured.get("total_slides")
            slide_outline = structured.get("slide_outline")
            if isinstance(total_slides, int) and total_slides > 0:
                item["total_slides"] = total_slides
            if isinstance(slide_outline, list) and slide_outline:
                item["slide_outline"] = slide_outline
        response_docs.append(item)
    return response_docs


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
    request.state.procurement_project_id = metadata.get("project_id")
    request.state.doc_count = metadata.get("doc_count")
    request.state.llm_prompt_tokens = metadata.get("llm_prompt_tokens")
    request.state.llm_output_tokens = metadata.get("llm_output_tokens")
    request.state.llm_total_tokens = metadata.get("llm_total_tokens")
    request.state.provider_ms = timings.get("provider_ms")
    request.state.render_ms = timings.get("render_ms")
    request.state.lints_ms = timings.get("lints_ms")
    request.state.validator_ms = timings.get("validator_ms")
    request.state.procurement_handoff_used = metadata.get("procurement_handoff_used")
    request.state.procurement_review_handoff_used = metadata.get("procurement_review_handoff_used")
    request.state.procurement_review_handoff_skipped_reason = metadata.get(
        "procurement_review_handoff_skipped_reason"
    )
    request.state.procurement_review_packet_sha256 = metadata.get("procurement_review_packet_sha256")
    request.state.procurement_review_decision = metadata.get("procurement_review_decision")
    request.state.procurement_reviewed_at = metadata.get("procurement_reviewed_at")
    request.state.procurement_review_source_updated_at = metadata.get(
        "procurement_review_source_updated_at"
    )
    request.state.procurement_review_operational_approval = metadata.get(
        "procurement_review_operational_approval"
    )
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
        "procurement_review_handoff_used": request.state.procurement_review_handoff_used,
        "procurement_review_handoff_skipped_reason": request.state.procurement_review_handoff_skipped_reason,
        "procurement_review_packet_sha256": request.state.procurement_review_packet_sha256,
        "procurement_review_decision": request.state.procurement_review_decision,
        "procurement_review_operational_approval": request.state.procurement_review_operational_approval,
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
    ensure_bundle_access(request, req.bundle_type)
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
        HistoryStore(
            tenant_id,
            base_dir=str(request.app.state.data_dir),
            backend=request.app.state.state_backend,
        ).add(HistoryEntry(
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
            applied_references=metadata.get("applied_references", []),
            docs=_build_generated_docs_response(result["docs"], result.get("raw_bundle")),
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
        applied_references=metadata.get("applied_references", []),
        procurement_review_handoff_used=metadata.get("procurement_review_handoff_used", False),
        procurement_review_handoff_skipped_reason=metadata.get(
            "procurement_review_handoff_skipped_reason"
        ),
        procurement_review_packet_sha256=metadata.get("procurement_review_packet_sha256"),
        procurement_review_decision=metadata.get("procurement_review_decision"),
        procurement_reviewed_at=metadata.get("procurement_reviewed_at"),
        procurement_review_source_updated_at=metadata.get(
            "procurement_review_source_updated_at"
        ),
        procurement_review_operational_approval=metadata.get(
            "procurement_review_operational_approval", False
        ),
        docs=_build_generated_docs_response(result["docs"], result.get("raw_bundle")),
    )

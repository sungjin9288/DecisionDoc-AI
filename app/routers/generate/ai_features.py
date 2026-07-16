"""app/routers/generate/ai_features.py — Auxiliary AI-powered text endpoints.

Split out of the former app/routers/generate.py (2,170 lines) to keep each
sub-module under the file-size limit. Covers:
  POST /generate/rewrite-section
  POST /generate/sketch
  POST /generate/refine
  POST /generate/related
  POST /generate/summary
  POST /generate/validate
  POST /generate/freeform
  POST /generate/review
  POST /generate/translate

Pure code relocation — no behavior changes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.ai_profiles.catalog import ensure_bundle_access
from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id
from app.maintenance.mode import require_not_maintenance
from app.providers.factory import get_provider_for_bundle, get_provider_for_capability
from app.schemas import FreeformRequest, GenerateRequest, SectionRewriteRequest
from app.services.generation.context_store import record_direct_provider_usage
from app.storage.usage_store import UsageStoreError

from app.routers.generate._shared import (
    _ensure_procurement_bundle_enabled,
    _heuristic_score,
    _score_to_grade,
)

logger = logging.getLogger("decisiondoc.generate")

router = APIRouter(tags=["generate"])


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

    worker_done = threading.Event()
    request.state.billing_provider_worker_done = worker_done

    def _rewrite_and_record() -> str:
        try:
            return provider.generate_raw(
                prompt,
                request_id=request_id,
                max_output_tokens=1500,
            )
        finally:
            try:
                record_direct_provider_usage(
                    request,
                    provider,
                    bundle_id=f"ai.rewrite-section.{body.bundle_id}",
                )
            finally:
                worker_done.set()

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, _rewrite_and_record)
    except UsageStoreError:
        raise
    except Exception as exc:
        logger.warning(
            "Section rewrite provider request failed request_id=%s provider=%s",
            request_id,
            provider.name,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider 요청에 실패했습니다.",
        ) from exc
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
    tenant_id = getattr(request.state, "tenant_id", "system") or "system"
    ensure_bundle_access(request, payload.bundle_type)
    bundle_spec = get_bundle_spec(payload.bundle_type)
    provider = get_provider_for_bundle(payload.bundle_type, tenant_id)
    try:
        result = generate_sketch(
            payload.model_dump(),
            provider,
            bundle_spec,
            search_service=search_service,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning(
            "Sketch provider request failed request_id=%s provider=%s",
            request_id,
            provider.name,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider 요청에 실패했습니다.",
        ) from exc
    finally:
        record_direct_provider_usage(
            request,
            provider,
            bundle_id=f"ai.sketch.{payload.bundle_type}",
        )

    from app.storage.request_pattern_store import RequestPatternStore

    pattern_store = RequestPatternStore(
        data_dir,
        tenant_id=tenant_id,
        backend=request.app.state.state_backend,
    )
    raw_input = f"{payload.title} {payload.goal}".strip()[:200]
    pattern_store.record_request(
        raw_input,
        bundle_id=payload.bundle_type,
        matched=True,
    )

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

    provider = get_provider_for_capability("generation")
    request_id = request.state.request_id
    try:
        refined = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=2000)
    except Exception as exc:
        logger.warning(
            "Refine provider request failed request_id=%s provider=%s",
            request_id,
            provider.name,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider 요청에 실패했습니다.",
        ) from exc
    finally:
        record_direct_provider_usage(request, provider, bundle_id="ai.refine")

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

    provider = get_provider_for_capability("generation")
    request_id = request.state.request_id
    try:
        summary = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=500)
    except Exception as exc:
        logger.warning(
            "Summary provider request failed request_id=%s provider=%s",
            request_id,
            provider.name,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider 요청에 실패했습니다.",
        ) from exc
    finally:
        record_direct_provider_usage(request, provider, bundle_id="ai.summary")

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
    pattern_store = RequestPatternStore(
        data_dir,
        tenant_id=get_tenant_id(request),
        backend=request.app.state.state_backend,
    )
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

    provider = get_provider_for_capability("generation")

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
        result = {
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
        score = _heuristic_score(content)
        result = {
            "score": score,
            "grade": _score_to_grade(score),
            "strengths": ["구조화된 내용", "명확한 목적"],
            "improvements": ["더 구체적인 수치나 지표 추가", "결론 및 다음 단계 명확화"],
            "summary": "문서가 생성되었습니다. 세부 내용을 보강하면 품질이 향상됩니다.",
            "content_length": len(content),
            "request_id": request_id,
        }
    record_direct_provider_usage(request, provider, bundle_id="ai.review")
    return result


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

    provider = get_provider_for_capability("generation")
    request_id = request.state.request_id
    try:
        translated = provider.generate_raw(
            prompt, request_id=request_id, max_output_tokens=4000
        )
    except Exception as exc:
        logger.warning(
            "Translation provider request failed request_id=%s provider=%s",
            request_id,
            provider.name,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider 요청에 실패했습니다.",
        ) from exc
    finally:
        record_direct_provider_usage(request, provider, bundle_id="ai.translate")

    return {
        "translated_content": translated.strip(),
        "target_lang": target_lang,
        "original_length": len(content),
        "translated_length": len(translated.strip()),
        "request_id": request_id,
    }

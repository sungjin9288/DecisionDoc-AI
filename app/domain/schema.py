from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Per-thread tracking of the A/B variant selected during the current generation.
# Set by _inject_prompt_override() when an active A/B test is found.
# Read by generation_service.py to record the result after eval.
_ab_selected: threading.local = threading.local()

# Per-thread capture of the last built bundle prompt.
# Set by build_bundle_prompt() so generation_service.py can retrieve it for
# fine-tune data collection without changing provider interfaces.
_ft_last_prompt: threading.local = threading.local()

# Per-thread current tenant ID for multi-tenant store isolation.
# Set by GenerationService.generate_documents() at request start.
_current_tenant_id: threading.local = threading.local()

if TYPE_CHECKING:
    from app.bundle_catalog.spec import BundleSpec

SCHEMA_VERSION = "v1"

BUNDLE_JSON_SCHEMA_V1: dict = {
    "type": "object",
    "required": ["adr", "onepager", "eval_plan", "ops_checklist"],
    "properties": {
        "adr": {
            "type": "object",
            "required": ["decision", "options", "risks", "assumptions", "checks", "next_actions"],
            "properties": {
                "decision": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "checks": {"type": "array", "items": {"type": "string"}},
                "next_actions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "onepager": {
            "type": "object",
            "required": ["problem", "recommendation", "impact", "checks"],
            "properties": {
                "problem": {"type": "string"},
                "recommendation": {"type": "string"},
                "impact": {"type": "array", "items": {"type": "string"}},
                "checks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "eval_plan": {
            "type": "object",
            "required": ["metrics", "test_cases", "failure_criteria", "monitoring"],
            "properties": {
                "metrics": {"type": "array", "items": {"type": "string"}},
                "test_cases": {"type": "array", "items": {"type": "string"}},
                "failure_criteria": {"type": "array", "items": {"type": "string"}},
                "monitoring": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ops_checklist": {
            "type": "object",
            "required": ["security", "reliability", "cost", "operations"],
            "properties": {
                "security": {"type": "array", "items": {"type": "string"}},
                "reliability": {"type": "array", "items": {"type": "string"}},
                "cost": {"type": "array", "items": {"type": "string"}},
                "operations": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

_STABILITY_CHECKLIST = (
    "Stability checklist:\n"
    "- Return one JSON bundle object only.\n"
    "- Include top-level keys: adr, onepager, eval_plan, ops_checklist.\n"
    "- Include required fields for each doc section per schema.\n"
    "- Do not include TODO/TBD/FIXME.\n"
    "- Keep each doc section sufficiently detailed (target >= 600 chars per doc after rendering).\n"
    "- Output JSON only, no markdown."
)


def _clean_requirements_for_prompt(requirements: dict[str, Any]) -> dict[str, Any]:
    """Remove noisy fields from the requirements dict before sending to the LLM.

    Strips:
    - Fields only relevant to tech_decision (bundle_type, doc_types, priority)
    - Empty strings and empty lists (no informational value, waste tokens)
    """
    SKIP_KEYS = {"bundle_type", "doc_types", "priority", "doc_tone", "_search_context",
                 "_knowledge_context", "_style_context", "_procurement_context", "_decision_council_context", "project_id",
                 "pdf_source", "pdf_sections"}
    return {
        k: v
        for k, v in requirements.items()
        if k not in SKIP_KEYS and v != "" and v != []
    }


def build_bundle_prompt(
    requirements: dict[str, Any],
    schema_version: str,
    bundle_spec: BundleSpec | None = None,
    *,
    feedback_hints: str = "",
) -> str:
    """Build the LLM prompt for bundle generation.

    Args:
        requirements: The serialised ``GenerateRequest`` payload.
        schema_version: Version string embedded in the prompt (e.g. ``"v1"``).
        bundle_spec: When provided, uses the bundle's own schema and stability
                     checklist instead of the legacy tech_decision constants.
                     Pass ``None`` (default) for backward-compatible behaviour.
        feedback_hints: Optional few-shot hints from high-rated user feedback.
    """
    if bundle_spec is not None:
        stability_checklist = bundle_spec.stability_checklist
        schema_json = bundle_spec.build_json_schema_str()
        lang = getattr(bundle_spec, "prompt_language", "en")
        lang_hint = getattr(bundle_spec, "prompt_hint", "")
    else:
        stability_checklist = _STABILITY_CHECKLIST
        schema_json = json.dumps(BUNDLE_JSON_SCHEMA_V1, ensure_ascii=False)
        lang = "en"
        lang_hint = ""

    if lang == "ko":
        system_instruction = (
            "당신은 전문 문서 작성 AI입니다.\n"
            "아래 JSON 스키마를 엄격히 따라 문서 번들을 생성하세요.\n"
            "모든 텍스트 필드는 반드시 한국어로 작성하세요.\n"
            "slide_outline 배열의 각 슬라이드(page, title, key_content, design_tip)는\n"
            "실제 발표에서 사용할 수 있도록 구체적이고 실무적인 내용으로 작성하세요.\n"
        )
    else:
        system_instruction = (
            "You are a professional document writing AI.\n"
            "Generate a document bundle strictly following the JSON schema below.\n"
        )

    if lang_hint:
        system_instruction += f"{lang_hint}\n"

    # 스타일 가이드 주입 (bundle_spec이 있을 때)
    from app.bundle_catalog.style_loader import get_style_prompt
    style_text = ""
    if bundle_spec is not None:
        style_text = get_style_prompt(bundle_id=bundle_spec.id, language=lang)

    # Few-shot 골든 예시 추출
    few_shot = getattr(bundle_spec, "few_shot_example", "") if bundle_spec is not None else ""

    # Extract search context (injected by GenerationService, not a user field)
    search_context = requirements.get("_search_context", "") if isinstance(requirements, dict) else ""

    # Extract knowledge context (injected by GenerationService from KnowledgeStore)
    knowledge_context = requirements.get("_knowledge_context", "") if isinstance(requirements, dict) else ""
    style_context = requirements.get("_style_context", "") if isinstance(requirements, dict) else ""
    procurement_context = requirements.get("_procurement_context", "") if isinstance(requirements, dict) else ""
    decision_council_context = requirements.get("_decision_council_context", "") if isinstance(requirements, dict) else ""

    # doc_tone 지시
    _TONE_MAP = {
        "formal":    "공식적이고 격식 있는 문체를 사용하세요. 합니다/입니다체를 유지하세요.",
        "concise":   "핵심만 간결하게 작성하세요. 각 항목은 3줄 이내로 유지하세요.",
        "detailed":  "배경·근거·예시를 충분히 서술하고 상세하게 작성하세요.",
        "executive": "경영진 요약 스타일로 작성하세요. 첫 문단에 결론을 제시하고 이후 근거를 서술하세요.",
    }
    doc_tone = requirements.get("doc_tone", "formal") if isinstance(requirements, dict) else getattr(requirements, "doc_tone", "formal")
    tone_instruction = _TONE_MAP.get(doc_tone, "")

    # 프롬프트 조립: 스타일 가이드 → Few-shot → 스키마 → 요구사항
    prompt = (
        f"{system_instruction}"
        "Return ONLY JSON matching this schema. No markdown.\n"
        f"{stability_checklist}\n"
    )
    if style_text:
        prompt += f"{style_text}\n"
    if few_shot:
        prompt += (
            f"\n=== 고품질 출력 예시 (이 스타일과 톤으로 작성) ===\n"
            f"{few_shot}\n"
            f"=== 예시 끝 ===\n\n"
        )
    if tone_instruction:
        prompt += f"\n[문서 톤 지시] {tone_instruction}\n"
    prompt += (
        f"schema_version={schema_version}\n"
        f"schema={schema_json}\n"
        f"requirements={json.dumps(_clean_requirements_for_prompt(requirements), ensure_ascii=False)}"
    )
    # PDF source injection — appears before feedback to give the LLM full context
    pdf_source = requirements.get("pdf_source", "") if isinstance(requirements, dict) else ""
    if pdf_source:
        prompt += (
            f"\n\n[참고 PDF 원문 — 아래 내용을 분석하여 문서를 재구성하세요]\n"
            f"{pdf_source[:6000]}"
        )

    if feedback_hints:
        prompt += f"\n\n--- 사용자 피드백 (품질 참고용) ---\n{feedback_hints}"
    if search_context:
        prompt += f"\n\n[웹 검색 참고 자료 — 내용 작성 시 참고]\n{search_context}"
    if knowledge_context:
        prompt += f"\n\n[프로젝트 참고 문서 — 아래 내용을 충분히 반영하여 문서를 작성하세요]\n{knowledge_context}"
    if style_context:
        prompt += f"\n\n{style_context}"
    if procurement_context:
        prompt += (
            "\n\n[프로젝트 공공조달 의사결정 상태 — 아래 structured state를 source of truth로 사용하세요]\n"
            f"{procurement_context}"
        )
    if decision_council_context:
        prompt += (
            "\n\n[Decision Council v1 handoff — 아래 council 합의 방향을 추가 source of truth로 사용하세요]\n"
            f"{decision_council_context}"
        )

    # Task 4: PromptOverrideStore에서 저평점 패턴 기반 개선 지시 주입
    if bundle_spec is not None:
        _inject_prompt_override(prompt_parts := [], bundle_spec.id)
        if prompt_parts:
            prompt += prompt_parts[0]

    # Task 5: EvalStore LLM judge 피드백 주입 (최근 3건)
    if bundle_spec is not None:
        _inject_llm_feedbacks(feedback_parts := [], bundle_spec.id)
        if feedback_parts:
            prompt += feedback_parts[0]

    # User style profile injection — default tenant profile overrides global style
    try:
        from app.storage.style_store import StyleStore
        from app.services.style_analyzer import build_style_prompt as _build_style_prompt

        _tid = getattr(_current_tenant_id, "value", None)
        if _tid:
            _sp = StyleStore(_tid).get_default(_tid)
            if _sp:
                _style_block = _build_style_prompt(
                    _sp, bundle_id=bundle_spec.id if bundle_spec is not None else None
                )
                if _style_block:
                    prompt += f"\n\n{_style_block}"
    except Exception as _style_exc:
        import logging as _logging
        _logging.getLogger("decisiondoc.schema").warning(
            "[Schema] Style injection failed: %s", _style_exc
        )

    # Tenant custom prompt hint injection
    if bundle_spec is not None:
        try:
            from app.storage.tenant_store import TenantStore
            tid = getattr(_current_tenant_id, "value", None)
            if tid and tid != "system":
                ts = TenantStore(Path(os.getenv("DATA_DIR", "./data")))
                hint = ts.get_custom_hint(tid, bundle_spec.id)
                if hint:
                    prompt += f"\n\n[테넌트 맞춤 지시]\n{hint}"
        except Exception:
            pass

    # Inject quality guidelines
    from app.bundle_catalog.system_prompt import enhance_bundle_prompt
    prompt = enhance_bundle_prompt(prompt)

    # Capture prompt in thread-local for fine-tune data collection
    _ft_last_prompt.prompt = prompt

    return prompt


def _inject_prompt_override(out: list[str], bundle_id: str) -> None:
    """A/B 활성 테스트 variant 힌트 또는 PromptOverrideStore 힌트를 주입. 실패 시 무시.

    Priority:
    1. Active A/B test → inject the next round-robin variant's hint,
       set _ab_selected.{bundle_id, variant} for the current thread.
    2. PromptOverrideStore → inject saved override hint (increment applied_count).
    """
    # Always reset thread-local A/B selection at the start of each call
    _ab_selected.bundle_id = None
    _ab_selected.variant = None

    # 1. Check for active A/B test first
    try:
        from app.storage.ab_test_store import get_ab_test_store
        tid = getattr(_current_tenant_id, "value", "system") or "system"
        ab_store = get_ab_test_store(tid)
        test = ab_store.get_active_test(bundle_id)
        if test:
            variant = ab_store.get_next_variant(bundle_id)
            if variant:
                hint = test.get(f"{variant}_hint", "")
                if hint:
                    _ab_selected.bundle_id = bundle_id
                    _ab_selected.variant = variant
                    out.append(f"\n\n[품질 개선 지시]\n{hint}")
                    return
    except Exception:
        pass

    # 2. Fall back to PromptOverrideStore
    try:
        from app.storage.prompt_override_store import get_override_store
        tid = getattr(_current_tenant_id, "value", "system") or "system"
        store = get_override_store(tid)
        record = store.get_override(bundle_id)
        if record and record.get("override_hint"):
            out.append(f"\n\n[품질 개선 지시]\n{record['override_hint']}")
            store.increment_applied(bundle_id)
    except Exception:
        pass


def _inject_llm_feedbacks(out: list[str], bundle_id: str) -> None:
    """EvalStore에서 최근 LLM judge 피드백을 읽어 out에 추가. 실패 시 무시."""
    try:
        from app.eval.eval_store import get_eval_store
        tid = getattr(_current_tenant_id, "value", "system") or "system"
        store = get_eval_store(tid)
        records = store.load_all()
        feedbacks = [
            fb
            for r in sorted(records, key=lambda x: x.timestamp, reverse=True)
            if r.bundle_id == bundle_id and r.llm_score is not None
            for fb in r.llm_feedbacks
        ][:3]
        if feedbacks:
            lines = "\n".join(f"- {fb}" for fb in feedbacks)
            out.append(f"\n\n[이전 LLM 평가 피드백 — 개선 참고용]\n{lines}")
    except Exception:
        pass


def build_sketch_prompt(
    requirements: dict[str, Any],
    bundle_spec: "BundleSpec",
    *,
    search_context: str = "",
) -> str:
    """Build a lightweight sketch prompt — returns section outline + PPT slides only.

    Used by POST /generate/sketch for fast 2-3 second preview before full generation.
    """

    doc_keys = bundle_spec.doc_keys
    lang = getattr(bundle_spec, "prompt_language", "ko")
    is_ppt = any(
        "slide_outline" in str(doc.json_schema)
        for doc in bundle_spec.docs
    )

    ppt_note = (
        '  "ppt_slides": [{"page": 1, "title": "string", "key_content": "string"}]'
        if is_ppt
        else '  "ppt_slides": null'
    )

    if lang == "ko":
        instruction = (
            "당신은 문서 구성 전문가입니다.\n"
            "아래 요구사항을 분석해 문서 구성 스케치를 작성하세요.\n"
            "전체 문서가 아닌, 각 섹션 제목과 핵심 포인트 2-3개만 간략히 작성합니다.\n"
        )
    else:
        instruction = (
            "You are a document structure expert.\n"
            "Produce a brief document sketch: section headings and 2-3 key bullets each.\n"
        )

    schema_str = (
        "{\n"
        '  "sections": [{"heading": "string", "bullets": ["string"]}],\n'
        f"{ppt_note}\n"
        "}"
    )

    # Clean requirements: strip internal/noisy keys
    SKETCH_SKIP = {"bundle_type", "doc_types", "priority", "doc_tone", "_search_context",
                   "_knowledge_context", "_style_context", "_procurement_context", "_decision_council_context", "project_id",
                   "pdf_source", "pdf_sections"}
    clean_req = {k: v for k, v in requirements.items() if k not in SKETCH_SKIP and v not in ("", [], None)}

    prompt = (
        f"{instruction}"
        "Return ONLY JSON matching this schema. No markdown, no explanation.\n"
        f"{schema_str}\n\n"
        f"bundle={bundle_spec.id}\n"
        f"doc_structure={json.dumps(doc_keys)}\n"
        f"requirements={json.dumps(clean_req, ensure_ascii=False)}"
    )
    if search_context:
        prompt += f"\n\n[웹 검색 참고 자료]\n{search_context}"
    return prompt


def recommend_bundles(text: str) -> list[str]:
    """Keyword-based bundle recommendation. Returns up to 3 bundle IDs.

    Args:
        text: Combined title+goal+industry text (lowercased).

    Returns:
        List of recommended bundle IDs (max 3), ordered by relevance.
    """
    _BUNDLE_KEYWORDS: dict[str, list[str]] = {
        "proposal_kr": ["제안서", "제안", "입찰", "수주", "영업", "proposal", "rfp"],
        "management_report": ["경영", "보고서", "임원", "이사회", "실적", "현황", "management", "report"],
        "g2b_bid": ["나라장터", "공공", "입찰", "g2b", "정부", "관공서", "조달", "공고"],
        "meeting_minutes": ["회의", "미팅", "회의록", "minutes", "agenda", "회의 내용"],
        "analysis_report": ["분석", "데이터", "리포트", "analysis", "research", "조사"],
        "contract_kr": ["계약", "계약서", "agreement", "contract", "법적", "협약"],
        "tech_decision": ["adr", "기술", "architecture", "개발", "시스템", "인프라", "마이크레이션"],
        "presentation_kr": ["발표", "ppt", "프레젠테이션", "슬라이드", "presentation"],
        "one_pager": ["원페이저", "one-pager", "요약", "개요", "overview", "summary"],
        "eval_plan": ["평가", "계획", "plan", "evaluation", "검토", "기획"],
        "ops_checklist": ["운영", "체크리스트", "checklist", "ops", "운영 절차"],
    }

    scores: dict[str, int] = {}
    for bundle_id, keywords in _BUNDLE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[bundle_id] = score

    # Sort by score desc, return top 3
    sorted_bundles = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [bid for bid, _ in sorted_bundles[:3]]

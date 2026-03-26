"""app/services/style_analyzer.py — Document style analysis + prompt injection.

Two responsibilities:
1. analyze_document_style()  — LLM-powered style extraction from uploaded docs
2. build_style_prompt()      — Convert a StyleProfile into a prompt instruction block
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.storage.style_store import StyleProfile

_log = logging.getLogger("decisiondoc.style")


async def analyze_document_style(
    filename: str,
    raw: bytes,
    bundle_id: str | None,
    provider,
) -> dict:
    """Extract style patterns from an uploaded document using an LLM.

    Returns a structured dict with keys:
        formality, density, perspective, patterns, sample_sentences,
        preferred_expressions, avoid_expressions, summary
    """
    from app.services.attachment_service import extract_text

    try:
        text = extract_text(filename, raw)
    except Exception as exc:
        raise ValueError(f"{filename}: 텍스트를 추출할 수 없습니다. ({exc})")

    if not text.strip():
        raise ValueError(f"{filename}: 텍스트를 추출할 수 없습니다.")

    bundle_hint = f"문서 유형: {bundle_id}" if bundle_id else ""

    prompt = f"""다음 문서의 문체와 작성 스타일을 분석하세요.
{bundle_hint}

분석할 문서 (처음 3,000자):
{text[:3000]}

다음 JSON 형식으로 분석 결과를 반환하세요:
{{
  "formality": "경어체 | 해요체 | 합쇼체 | 혼용",
  "density": "간결 | 보통 | 상세",
  "perspective": "1인칭 | 3인칭 | 기관명칭 | 혼용",
  "patterns": [
    "문장 끝 표현 패턴 (예: ~합니다, ~추진합니다)",
    "자주 쓰는 접속어 (예: 이를 위해, 따라서)",
    "강조 방식 (예: 반드시, 필히, 특히)"
  ],
  "sample_sentences": [
    "대표적인 문장 1 (원문에서 그대로)",
    "대표적인 문장 2",
    "대표적인 문장 3"
  ],
  "preferred_expressions": ["선호 표현1", "선호 표현2"],
  "avoid_expressions": ["피해야 할 표현1"],
  "summary": "이 문서의 전체적인 문체 특징을 2문장으로 요약"
}}
반드시 유효한 JSON만 반환하세요."""

    try:
        result = await provider.generate_raw(prompt, max_tokens=800)
        # Strip markdown code fences if present
        result = re.sub(r"```(?:json)?\s*", "", result).strip()
        result = re.sub(r"```\s*$", "", result).strip()
        return json.loads(result)
    except Exception as exc:
        _log.warning("[StyleAnalyzer] Analysis failed for %s: %s", filename, exc)
        return {
            "formality": "혼용",
            "density": "보통",
            "perspective": "혼용",
            "patterns": [],
            "sample_sentences": [],
            "preferred_expressions": [],
            "avoid_expressions": [],
            "summary": "분석 실패",
        }


def build_style_prompt(
    style_profile: StyleProfile,
    bundle_id: str | None = None,
) -> str:
    """Convert a StyleProfile into a prompt instruction block.

    Uses the bundle-specific ToneGuide override when available, otherwise
    falls back to the profile's global ToneGuide.
    Returns an empty string when there is nothing meaningful to inject.
    """
    if not style_profile:
        return ""

    # Prefer bundle-specific override
    tone = None
    overrides = style_profile.bundle_overrides or {}
    if bundle_id and bundle_id in overrides:
        tone = overrides[bundle_id]
    else:
        tone = style_profile.tone_guide

    if not tone:
        return ""

    # Check if there's anything meaningful to inject
    has_content = any([
        tone.formality, tone.density, tone.perspective,
        tone.custom_rules, tone.preferred_words, tone.forbidden_words,
    ])
    if not has_content and not style_profile.examples:
        return ""

    lines = ["=== 문체 및 스타일 지침 ==="]

    if tone.formality:
        lines.append(f"문체: {tone.formality}를 일관되게 사용하세요.")
    if tone.density:
        lines.append(f"서술 밀도: {tone.density} 수준으로 작성하세요.")
    if tone.perspective:
        lines.append(f"서술 관점: {tone.perspective}을 사용하세요.")

    if tone.custom_rules:
        lines.append("추가 규칙:")
        for rule in tone.custom_rules:
            lines.append(f"  - {rule}")

    if tone.preferred_words:
        lines.append(f"선호 표현: {', '.join(tone.preferred_words)}")
    if tone.forbidden_words:
        lines.append(f"사용 금지: {', '.join(tone.forbidden_words)}")

    # Inject up to 2 relevant style examples
    examples = style_profile.examples or []
    relevant = [
        e for e in examples
        if not e.bundle_id or e.bundle_id == bundle_id
    ][:2]

    if relevant:
        lines.append("\n참고 문체 예시 (이 스타일을 따르세요):")
        for ex in relevant:
            for sent in (ex.sample_sentences or [])[:2]:
                lines.append(f"  예: {sent}")

    lines.append("=== 문체 지침 끝 ===")
    return "\n".join(lines)

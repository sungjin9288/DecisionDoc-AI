"""app/services/rfp_parser.py — RFP (제안요청서) document parser.

Extracts structured fields from RFP text using a lightweight LLM call,
and builds a structured context block for downstream prompt injection.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

_log = logging.getLogger("decisiondoc.rfp_parser")

# Default result returned on parse failure
_EMPTY_RESULT: dict[str, Any] = {
    "project_title": "",
    "issuer": "",
    "budget": "",
    "deadline": "",
    "duration": "",
    "objective": "",
    "key_requirements": [],
    "evaluation_criteria": [],
    "suggested_bundle": "rfp_analysis_kr",
    "confidence": 0.0,
}

_RFP_PROMPT_TEMPLATE = """\
다음은 RFP(제안요청서) 또는 공고문 텍스트입니다.
이 텍스트에서 아래 정보를 JSON으로 추출하세요.
정보가 없는 항목은 빈 문자열("") 또는 빈 배열([])로 반환하세요.

텍스트:
{text}

추출할 필드:
{{
  "project_title": "사업명 또는 과제명",
  "issuer": "발주기관명",
  "budget": "예산 (예: 5억원, 500,000,000원)",
  "deadline": "제안서 제출 기한 또는 사업 완료 기한",
  "duration": "사업 기간 (예: 2025.04~2025.12)",
  "objective": "사업 목적 또는 목표 (2-3문장)",
  "key_requirements": ["핵심 요구사항 1", "핵심 요구사항 2"],
  "evaluation_criteria": ["평가항목 1 (배점)", "평가항목 2 (배점)"],
  "confidence": 0.9
}}

반드시 유효한 JSON만 반환하세요. 설명 없이.\
"""


def parse_rfp_fields(
    attachment_text: str,
    provider: Any | None = None,
    request_id: str = "rfp-parse",
) -> dict[str, Any]:
    """Extract structured fields from RFP/공고문 text via LLM.

    This function is **synchronous** — the provider's ``generate_raw`` method
    is sync (uses anyio internally).

    Args:
        attachment_text: Combined text extracted from attached RFP files.
        provider:        LLM provider; resolved from env when ``None``.
        request_id:      Passed to provider for observability.

    Returns:
        Dict with extracted fields.  ``confidence`` is 0.0 on failure.
        ``suggested_bundle`` is always set (defaults to
        ``"rfp_analysis_kr"``).
    """
    if provider is None:
        from app.providers.factory import get_provider
        provider = get_provider()

    prompt = _RFP_PROMPT_TEMPLATE.format(text=attachment_text[:8_000])

    try:
        raw = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=1_000)

        # Strip markdown code fences
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
        raw = re.sub(r"```\s*$", "", raw).strip()

        data: dict[str, Any] = json.loads(raw)

        # Ensure all expected keys exist with correct types
        result = dict(_EMPTY_RESULT)
        result.update(
            {k: v for k, v in data.items() if k in _EMPTY_RESULT}
        )
        result["suggested_bundle"] = _suggest_bundle(attachment_text, result)
        return result

    except Exception as exc:
        _log.warning("[RFPParser] Field extraction failed: %s", exc)
        return dict(_EMPTY_RESULT)


def _suggest_bundle(text: str, fields: dict[str, Any]) -> str:
    """Heuristically pick the most appropriate bundle for the RFP content."""
    text_lower = text.lower()

    if any(k in text_lower for k in ["제안요청", "rfp", "입찰공고", "나라장터"]):
        return "rfp_analysis_kr"
    if any(k in text_lower for k in ["수행계획", "착수", "과업지시"]):
        return "performance_plan_kr"
    if any(k in text_lower for k in ["완료", "준공", "결과보고"]):
        return "completion_report_kr"
    if any(k in text_lower for k in ["중간", "진행", "진척"]):
        return "interim_report_kr"
    if any(k in text_lower for k in ["제안서", "사업계획"]):
        return "proposal_kr"
    return "rfp_analysis_kr"


def build_rfp_context(attachment_text: str) -> str:
    """Wrap raw attachment text in a structured RFP context block.

    This produces better LLM results than injecting flat text into the
    ``context`` field, because the model is explicitly told what the
    block is and how to use it.

    Args:
        attachment_text: Raw text extracted from one or more attachment files.

    Returns:
        A labelled context string ready to be prepended to ``req.context``.
    """
    return (
        "=== RFP 원문 (참고용) ===\n"
        f"{attachment_text}\n"
        "=== RFP 원문 끝 ===\n"
        "위 RFP 원문을 바탕으로 문서를 작성하세요. "
        "발주처의 요구사항, 평가기준, 사업 목적을 최대한 반영하세요."
    )

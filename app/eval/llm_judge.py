"""llm_judge.py — LLM-as-Judge 문서 품질 평가.

OpenAI 호환 API를 사용하여 생성된 문서를 4개 차원으로 평가합니다:
- context_alignment: 입력 컨텍스트와의 일치도
- specificity: 구체성 (수치, 예시, 고유 내용)
- coherence: 내용의 논리적 흐름
- actionability: 실행 가능성

환경변수:
  OPENAI_API_KEY 또는 DECISIONDOC_PROVIDER=openai 필요
  DECISIONDOC_LLM_JUDGE_MODEL (기본값: gpt-4o-mini)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_JUDGE_PROMPT = """당신은 문서 품질 평가 전문가입니다. 아래 문서를 4개 차원에서 1~5점으로 평가하세요.

## 평가 기준
- context_alignment (1-5): 제공된 제목/목표/컨텍스트와 문서 내용의 일치도
- specificity (1-5): 구체적인 수치, 예시, 고유한 세부사항 포함 여부 (1=매우 추상적, 5=매우 구체적)
- coherence (1-5): 섹션 간 논리적 흐름과 일관성 (1=산만함, 5=매우 일관됨)
- actionability (1-5): 독자가 즉시 실행할 수 있는 내용 여부 (1=이론적, 5=즉시 실행 가능)

## 입력 컨텍스트
제목: {title}
목표: {goal}
컨텍스트: {context}

## 평가할 문서 (doc_type: {doc_type})
{markdown}

## 응답 형식 (JSON만 반환, 다른 텍스트 없음)
{{
  "context_alignment": <1-5>,
  "specificity": <1-5>,
  "coherence": <1-5>,
  "actionability": <1-5>,
  "brief_feedback": "<한국어로 2문장 피드백>"
}}"""


@dataclass
class LLMJudgeResult:
    doc_type: str
    context_alignment: float
    specificity: float
    coherence: float
    actionability: float
    average_score: float  # 1.0 ~ 5.0
    brief_feedback: str
    error: str | None = None


def _call_openai_judge(prompt: str, model: str, api_key: str) -> dict[str, Any]:
    """Call OpenAI-compatible API. Returns parsed JSON dict."""
    import urllib.request

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    content = result["choices"][0]["message"]["content"]
    return json.loads(content)


def judge_document(
    doc_type: str,
    markdown: str,
    title: str = "",
    goal: str = "",
    context: str = "",
    model: str | None = None,
    api_key: str | None = None,
) -> LLMJudgeResult:
    """Judge a single document using LLM.

    Returns LLMJudgeResult. If API key is unavailable, returns error result.
    """
    _api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    _model = model or os.getenv("DECISIONDOC_LLM_JUDGE_MODEL", "gpt-4o-mini")

    if not _api_key:
        return LLMJudgeResult(
            doc_type=doc_type,
            context_alignment=0.0,
            specificity=0.0,
            coherence=0.0,
            actionability=0.0,
            average_score=0.0,
            brief_feedback="",
            error="OPENAI_API_KEY 미설정 — LLM judge 불가",
        )

    prompt = _JUDGE_PROMPT.format(
        title=title or "(없음)",
        goal=goal or "(없음)",
        context=context or "(없음)",
        doc_type=doc_type,
        markdown=markdown[:3000],  # truncate to avoid token limits
    )

    try:
        parsed = _call_openai_judge(prompt, _model, _api_key)
        scores = {
            "context_alignment": float(parsed.get("context_alignment", 3)),
            "specificity": float(parsed.get("specificity", 3)),
            "coherence": float(parsed.get("coherence", 3)),
            "actionability": float(parsed.get("actionability", 3)),
        }
        avg = sum(scores.values()) / 4
        return LLMJudgeResult(
            doc_type=doc_type,
            context_alignment=scores["context_alignment"],
            specificity=scores["specificity"],
            coherence=scores["coherence"],
            actionability=scores["actionability"],
            average_score=round(avg, 2),
            brief_feedback=str(parsed.get("brief_feedback", "")),
        )
    except Exception as exc:
        logger.warning("LLM judge failed for %s: %s", doc_type, exc)
        return LLMJudgeResult(
            doc_type=doc_type,
            context_alignment=0.0,
            specificity=0.0,
            coherence=0.0,
            actionability=0.0,
            average_score=0.0,
            brief_feedback="",
            error=str(exc),
        )


def judge_bundle_docs(
    docs: list[dict[str, Any]],
    title: str = "",
    goal: str = "",
    context: str = "",
    model: str | None = None,
    api_key: str | None = None,
) -> list[LLMJudgeResult]:
    """Judge all documents in a bundle. Returns list of LLMJudgeResult."""
    results = []
    for doc in docs:
        result = judge_document(
            doc_type=doc.get("doc_type", ""),
            markdown=doc.get("markdown", ""),
            title=title,
            goal=goal,
            context=context,
            model=model,
            api_key=api_key,
        )
        results.append(result)
    return results

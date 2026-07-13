"""Hard gates and rubric scoring for DocumentOps outputs."""
from __future__ import annotations

import re
from typing import Any

from app.evals.document_ops.rubric import (
    DEFAULT_FORBIDDEN_TERMS,
    DOCUMENT_OPS_RUBRIC,
    GOVERNANCE_TASK_TYPES,
    OVERCONFIDENT_PATTERNS,
    DocumentOpsGateIssue,
    DocumentOpsGateResult,
)


def evaluate_document_ops_output(
    *,
    task_type: str,
    draft: str,
    plan: list[str] | None = None,
    evidence_status: dict[str, Any] | None = None,
    qa: dict[str, Any] | None = None,
    forbidden_terms: tuple[str, ...] = DEFAULT_FORBIDDEN_TERMS,
) -> DocumentOpsGateResult:
    """Evaluate a DocumentOps draft with deterministic hard gates.

    The gate is intentionally conservative. It does not prove factual truth;
    it blocks obvious unsafe states and creates labels for later reviewed-data
    export.
    """
    draft_text = str(draft or "")
    plan_items = [str(item).strip() for item in (plan or []) if str(item).strip()]
    evidence = evidence_status if isinstance(evidence_status, dict) else {}
    provider_qa = qa if isinstance(qa, dict) else {}
    confirmed = _string_list(evidence.get("confirmed"))
    assumptions = _string_list(evidence.get("assumptions") or evidence.get("assumed"))
    gaps = _string_list(evidence.get("gaps") or evidence.get("todo") or evidence.get("open_questions"))
    sources = _string_list(evidence.get("source_references") or evidence.get("sources"))

    issues: list[DocumentOpsGateIssue] = []
    forbidden_hits = [term for term in forbidden_terms if term and term in draft_text]
    if forbidden_hits:
        issues.append(
            DocumentOpsGateIssue(
                code="forbidden_terms",
                severity="blocker",
                affected_field="draft",
                message="금지 또는 제출 민감 표현이 draft에 남아 있습니다.",
                remediation_hint="표시된 표현을 삭제하고 검증 가능한 중립 표현으로 다시 작성하세요.",
                evidence=forbidden_hits,
            )
        )

    if not confirmed and not sources:
        issues.append(
            DocumentOpsGateIssue(
                code="evidence_gap:no_confirmed_sources",
                severity="warning",
                affected_field="evidence_status.source_references",
                message="확인된 근거 또는 source reference가 없어 confirmed claim로 사용할 수 없습니다.",
                remediation_hint="공식 출처를 연결하거나 해당 내용을 assumption 또는 gap으로 분류하세요.",
            )
        )

    if confirmed and not sources:
        issues.append(
            DocumentOpsGateIssue(
                code="unsupported_confirmed_claims",
                severity="blocker",
                affected_field="evidence_status.source_references",
                message="confirmed 항목이 있지만 연결된 source reference가 없습니다.",
                remediation_hint="각 confirmed 항목의 출처를 연결하거나 근거가 없는 항목을 assumption으로 이동하세요.",
                evidence=confirmed[:5],
            )
        )

    overconfident_hits = [pattern for pattern in OVERCONFIDENT_PATTERNS if pattern in draft_text]
    if overconfident_hits and gaps:
        issues.append(
            DocumentOpsGateIssue(
                code="certainty_with_open_gaps",
                severity="blocker",
                affected_field="draft",
                message="미확인 gap이 있는데 성과/비용/KPI를 확정적으로 표현했습니다.",
                remediation_hint="미확인 수치를 조건부 표현으로 바꾸고 확정에 필요한 근거를 gap에 명시하세요.",
                evidence=overconfident_hits,
            )
        )

    if task_type in GOVERNANCE_TASK_TYPES and not _contains_any(
        draft_text,
        ("개인정보", "보안", "거버넌스", "운영책임", "로그", "감사", "권한", "리스크"),
    ):
        issues.append(
            DocumentOpsGateIssue(
                code="missing_governance_privacy_security",
                severity="blocker",
                affected_field="draft",
                message="정책/공공 기획안에 필요한 개인정보, 보안, 운영책임, 리스크 검토가 없습니다.",
                remediation_hint="개인정보, 보안, 권한, 운영책임, 로그/감사, 리스크 중 적용 항목을 본문에 추가하세요.",
            )
        )

    if not draft_text.strip() or len(draft_text.strip()) < 80:
        issues.append(
            DocumentOpsGateIssue(
                code="missing_output_sections",
                severity="blocker",
                affected_field="draft",
                message="검토 가능한 draft 본문이 부족합니다.",
                remediation_hint="문제, 근거, 실행, 운영 또는 승인 판단을 구분한 검토 가능한 본문을 작성하세요.",
            )
        )

    if not plan_items:
        issues.append(
            DocumentOpsGateIssue(
                code="missing_plan",
                severity="warning",
                affected_field="plan",
                message="작업 plan이 없어 검토/수정 흐름을 추적하기 어렵습니다.",
                remediation_hint="요구사항 확인, 근거 검토, 수정 또는 승인 순서를 plan에 추가하세요.",
            )
        )

    provider_warnings = _string_list(provider_qa.get("warnings"))
    warnings = [issue.code for issue in issues if issue.severity == "warning"]
    warnings.extend(provider_warnings)
    scores = _score_dimensions(
        draft=draft_text,
        plan=plan_items,
        confirmed=confirmed,
        assumptions=assumptions,
        gaps=gaps,
        sources=sources,
        forbidden_hits=forbidden_hits,
        issues=issues,
    )
    overall = _weighted_score(scores)
    hard_gate_pass = not any(issue.severity == "blocker" for issue in issues)
    action = _recommended_action(hard_gate_pass=hard_gate_pass, gaps=gaps, overall_score=overall)
    return DocumentOpsGateResult(
        hard_gate_pass=hard_gate_pass,
        issues=issues,
        warnings=_dedupe(warnings),
        forbidden_terms=forbidden_hits,
        scores=scores,
        overall_score=overall,
        recommended_next_action=action,
    )


def _score_dimensions(
    *,
    draft: str,
    plan: list[str],
    confirmed: list[str],
    assumptions: list[str],
    gaps: list[str],
    sources: list[str],
    forbidden_hits: list[str],
    issues: list[DocumentOpsGateIssue],
) -> dict[str, float]:
    text = draft.strip()
    policy_markers = ("문제", "원인", "근거", "실행", "운영", "효과", "승인", "결정")
    implementation_markers = ("역할", "일정", "책임", "운영", "데이터", "보안", "리스크", "변경")
    scores = {
        "policy_logic": _ratio_score(text, policy_markers, min_hits=3),
        "evidence_grounding": _evidence_score(confirmed, assumptions, gaps, sources),
        "public_sector_tone": 0.25 if forbidden_hits else 1.0,
        "implementation_detail": _ratio_score(text, implementation_markers, min_hits=3),
        "artifact_readiness": _artifact_score(text, plan),
    }
    if any(issue.code == "missing_output_sections" for issue in issues):
        scores["artifact_readiness"] = min(scores["artifact_readiness"], 0.2)
    return {key: round(max(0.0, min(1.0, value)), 3) for key, value in scores.items()}


def _evidence_score(confirmed: list[str], assumptions: list[str], gaps: list[str], sources: list[str]) -> float:
    if confirmed and sources:
        base = 0.85
    elif sources:
        base = 0.65
    elif confirmed:
        base = 0.35
    else:
        base = 0.3
    if assumptions:
        base += 0.05
    if gaps:
        base += 0.05 if sources else -0.05
    return base


def _artifact_score(text: str, plan: list[str]) -> float:
    score = 0.2
    if len(text) >= 300:
        score += 0.25
    if len(plan) >= 3:
        score += 0.25
    if _heading_count(text) >= 2:
        score += 0.2
    if _contains_any(text, ("TODO", "승인", "권고", "다음", "수정")):
        score += 0.1
    return score


def _weighted_score(scores: dict[str, float]) -> float:
    total = 0.0
    for dim in DOCUMENT_OPS_RUBRIC:
        total += scores.get(dim.key, 0.0) * dim.weight
    return round(max(0.0, min(1.0, total)), 3)


def _recommended_action(*, hard_gate_pass: bool, gaps: list[str], overall_score: float) -> str:
    if not hard_gate_pass:
        return "request_changes"
    if gaps or overall_score < 0.72:
        return "collect_more_evidence"
    return "approve"


def _ratio_score(text: str, markers: tuple[str, ...], *, min_hits: int) -> float:
    if not text:
        return 0.0
    hits = sum(1 for marker in markers if marker in text)
    return min(1.0, hits / min_hits)


def _heading_count(text: str) -> int:
    return len(re.findall(r"(?m)^#{1,4}\s+", text))


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

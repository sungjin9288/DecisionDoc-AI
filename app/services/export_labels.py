"""Shared helpers for human-friendly export labels."""
from __future__ import annotations


_DOC_TYPE_LABELS = {
    "business_understanding": "사업 이해",
    "tech_proposal": "기술 제안",
    "execution_plan": "수행 계획",
    "expected_impact": "기대 효과",
    "performance_overview": "수행 개요",
    "quality_risk_plan": "품질·리스크 계획",
    "rfp_summary": "RFP 핵심 요약",
    "win_strategy": "수주 전략",
    "opportunity_brief": "기회 분석",
    "go_no_go_memo": "Go / No-Go 메모",
    "bid_readiness_checklist": "입찰 준비 체크리스트",
    "proposal_kickoff_summary": "제안 킥오프 요약",
    "completion_summary": "완료 보고 요약",
    "progress_report": "중간 진척 보고",
    "task_definition": "과업 정의",
}


def humanize_doc_type(doc_type: str) -> str:
    normalized = str(doc_type or "").strip()
    if not normalized:
        return "문서"
    if normalized in _DOC_TYPE_LABELS:
        return _DOC_TYPE_LABELS[normalized]
    return normalized.replace("_", " ").title()

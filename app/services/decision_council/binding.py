"""Procurement/council binding staleness and generation-context helpers.

These are standalone, deterministic functions (no service state) that describe
whether a stored Decision Council session — or a council-backed procurement
document generated from it — still matches the current procurement state, and
that render a council session into the prompt context consumed when
generating ``bid_decision_kr`` / ``proposal_kr`` documents.
"""
from __future__ import annotations

from app.schemas import (
    DecisionCouncilSessionResponse,
    ProcurementDecisionRecord,
)

_DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES = ("bid_decision_kr", "proposal_kr")


def _build_procurement_binding_metrics(
    procurement_record: ProcurementDecisionRecord | None,
) -> dict[str, int | str]:
    if procurement_record is None:
        return {
            "recommendation_value": "",
            "updated_at": "",
            "missing_data_count": 0,
            "action_needed_count": 0,
            "blocking_hard_filter_count": 0,
        }
    recommendation_value = ""
    if procurement_record.recommendation is not None:
        raw_value = procurement_record.recommendation.value
        recommendation_value = getattr(raw_value, "value", raw_value) or ""
    return {
        "recommendation_value": recommendation_value,
        "updated_at": procurement_record.updated_at,
        "missing_data_count": len([item for item in procurement_record.missing_data if str(item).strip()]),
        "action_needed_count": len(
            [
                item for item in procurement_record.checklist_items
                if item.status in {"action_needed", "blocked"}
            ]
        ),
        "blocking_hard_filter_count": len(
            [
                item for item in procurement_record.hard_filters
                if item.blocking and item.status == "fail"
            ]
        ),
    }


def describe_procurement_council_binding(
    *,
    session: DecisionCouncilSessionResponse,
    procurement_record: ProcurementDecisionRecord | None,
) -> dict[str, str]:
    """Describe whether a stored council session still matches current procurement state."""

    if (
        procurement_record is None
        or procurement_record.opportunity is None
        or procurement_record.recommendation is None
    ):
        return {
            "status": "stale",
            "reason_code": "procurement_context_missing",
            "summary": (
                "현재 procurement opportunity 또는 recommendation이 없어 "
                "이전 council handoff를 최신 의사결정 기준으로 사용할 수 없습니다."
            ),
        }

    if session.source_procurement_decision_id != procurement_record.decision_id:
        return {
            "status": "stale",
            "reason_code": "decision_replaced",
            "summary": (
                "현재 procurement decision 식별자가 council 실행 시점과 달라 "
                "이전 handoff를 그대로 재사용할 수 없습니다."
            ),
        }

    bound_updated_at = str(session.source_procurement_updated_at or "").strip()
    if not bound_updated_at or bound_updated_at != procurement_record.updated_at:
        current_metrics = _build_procurement_binding_metrics(procurement_record)
        source_recommendation = str(session.source_procurement_recommendation_value or "").strip()
        current_recommendation = str(current_metrics["recommendation_value"] or "").strip()
        change_summary = []
        if source_recommendation and current_recommendation and source_recommendation != current_recommendation:
            change_summary.append(f"권고안 {source_recommendation} → {current_recommendation}")
        if int(current_metrics["action_needed_count"]) > 0:
            change_summary.append(f"현재 action needed {current_metrics['action_needed_count']}건")
        if int(current_metrics["missing_data_count"]) > 0:
            change_summary.append(f"현재 missing data {current_metrics['missing_data_count']}건")
        if int(current_metrics["blocking_hard_filter_count"]) > 0:
            change_summary.append(
                f"현재 blocking hard filter {current_metrics['blocking_hard_filter_count']}건"
            )
        suffix = f" ({', '.join(change_summary)})" if change_summary else ""
        return {
            "status": "stale",
            "reason_code": "procurement_updated",
            "summary": (
                "현재 procurement recommendation, checklist, 또는 missing data가 council 실행 이후 갱신되었습니다. "
                f"Decision Council을 다시 실행해야 최신 handoff가 bid_decision_kr / proposal_kr 생성에 반영됩니다.{suffix}"
            ),
        }

    return {
        "status": "current",
        "reason_code": "",
        "summary": "현재 procurement recommendation과 같은 기준의 council handoff입니다.",
    }


def describe_procurement_council_document_status(
    *,
    bundle_id: str,
    source_session_id: str | None,
    source_session_revision: int | None,
    latest_session: DecisionCouncilSessionResponse | None,
) -> dict[str, str] | None:
    """Describe whether a council-backed procurement document is current or outdated."""

    if bundle_id not in _DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES:
        return None
    normalized_source_session_id = str(source_session_id or "").strip()
    if not normalized_source_session_id:
        return None

    latest_session_id = str(latest_session.session_id if latest_session else "").strip()
    latest_revision = int(latest_session.session_revision if latest_session else 0)
    document_revision = int(source_session_revision or 1)

    if not latest_session_id or normalized_source_session_id != latest_session_id:
        return {
            "status": "previous_council",
            "tone": "warning",
            "copy": "이전 council 기준",
            "summary": "현재 프로젝트의 latest Decision Council session과 다른 기준으로 생성된 문서입니다.",
        }

    if latest_session.current_procurement_binding_status == "stale":
        return {
            "status": "stale_procurement",
            "tone": "danger",
            "copy": "현재 procurement 대비 이전 council 기준",
            "summary": (
                "현재 procurement recommendation 또는 checklist가 갱신되어, "
                "이 문서는 최신 council/procurement 기준과 일치하지 않습니다."
            ),
        }

    if latest_revision > 0 and document_revision > 0 and document_revision < latest_revision:
        return {
            "status": "stale_revision",
            "tone": "warning",
            "copy": f"이전 council revision (r{document_revision})",
            "summary": (
                f"현재 latest council revision은 r{latest_revision}이며, "
                "이 문서는 그 이전 revision 기준입니다."
            ),
        }

    return {
        "status": "current",
        "tone": "success",
        "copy": "현재 council 기준",
        "summary": "현재 latest Decision Council handoff와 같은 revision 기준의 문서입니다.",
    }


def build_procurement_council_generation_context(
    session: DecisionCouncilSessionResponse,
    *,
    bundle_type: str = "bid_decision_kr",
) -> str:
    target_bundle = bundle_type if bundle_type in _DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES else "bid_decision_kr"
    if target_bundle == "proposal_kr":
        intro = (
            "Decision Council v1 결과입니다. proposal_kr 작성 시 아래 합의 방향을 "
            "procurement state와 함께 반영해 제안 전략, 차별화 포인트, 금지 주장 범위를 정리하세요."
        )
        strategy_label = "Proposal 전략 옵션:"
        risk_label = "Proposal drafting 리스크:"
        disagreement_label = "Proposal drafting 이견:"
        handoff_title = "Proposal drafting handoff:"
    else:
        intro = (
            "Decision Council v1 결과입니다. bid_decision_kr 작성 시 아래 합의 방향을 "
            "procurement state와 함께 반영하세요."
        )
        strategy_label = "전략 옵션:"
        risk_label = "상위 리스크:"
        disagreement_label = "주요 이견:"
        handoff_title = "Drafting handoff:"

    lines = [
        intro,
        f"- council_session_id: {session.session_id}",
        f"- council_revision: {session.session_revision}",
        f"- stored_target_bundle_type: {session.target_bundle_type}",
        f"- applied_bundle_type: {target_bundle}",
        f"- 추천 방향: {session.consensus.recommended_direction}",
        f"- 합의 상태: {session.consensus.alignment}",
        f"- 목표: {session.goal}",
    ]
    if session.constraints:
        lines.append(f"- 제약: {session.constraints}")
    lines.append(f"- 합의 요약: {session.consensus.summary}")
    if session.consensus.strategy_options:
        lines.append(strategy_label)
        for item in session.consensus.strategy_options[:4]:
            lines.append(f"- {item}")
    if session.risks:
        lines.append(risk_label)
        for item in session.risks[:5]:
            lines.append(f"- {item}")
    if session.disagreements:
        lines.append(disagreement_label)
        for item in session.disagreements[:3]:
            lines.append(f"- {item}")
    lines.append(handoff_title)
    lines.append(f"- drafting_brief: {session.handoff.drafting_brief}")
    for label, values in (
        ("must_include", session.handoff.must_include),
        ("must_address", session.handoff.must_address),
        ("must_not_claim", session.handoff.must_not_claim),
        ("open_questions", session.handoff.open_questions),
    ):
        if not values:
            continue
        lines.append(f"- {label}:")
        for item in values[:6]:
            lines.append(f"  - {item}")
    return "\n".join(lines).strip()

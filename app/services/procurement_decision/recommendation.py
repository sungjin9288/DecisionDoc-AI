"""Recommendation-building mixin.

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

from app.schemas import (
    ProcurementDecisionRecord,
    ProcurementHardFilterStatus,
    ProcurementRecommendation,
    ProcurementRecommendationValue,
    ProcurementScoreStatus,
)
from app.services.procurement_decision.text_utils import _unique


class RecommendationMixin:
    """Builds the Go / No-Go / Conditional-Go recommendation for a record."""

    def _build_recommendation(self, record: ProcurementDecisionRecord) -> ProcurementRecommendation:
        hard_failures = [item for item in record.hard_filters if item.blocking and item.status == ProcurementHardFilterStatus.FAIL]
        strong_scores = [
            item for item in sorted(record.score_breakdown, key=lambda value: value.score, reverse=True)
            if item.status == ProcurementScoreStatus.SCORED and item.score >= 70.0
        ]
        weak_scores = [
            item for item in record.score_breakdown
            if item.status == ProcurementScoreStatus.INSUFFICIENT_DATA or item.score < 60.0
        ]

        if hard_failures:
            value = ProcurementRecommendationValue.NO_GO
            summary = (
                f"Blocking hard-filter {len(hard_failures)}건으로 현재 상태에서는 입찰 진행을 권고하지 않습니다."
            )
        elif record.soft_fit_status == ProcurementScoreStatus.INSUFFICIENT_DATA:
            value = ProcurementRecommendationValue.CONDITIONAL_GO
            score_text = f"{record.soft_fit_score:.2f}점" if record.soft_fit_score is not None else "미산정"
            summary = (
                f"Weighted fit score {score_text} 기준으로 추가 확인이 필요한 입력이 남아 있어 조건부 진행이 적절합니다."
            )
        elif record.soft_fit_score is not None and record.soft_fit_score >= 75.0 and record.soft_fit_status == ProcurementScoreStatus.SCORED and not record.missing_data:
            value = ProcurementRecommendationValue.GO
            summary = (
                f"Weighted fit score {record.soft_fit_score:.2f}점이며 blocking hard-fail이 없어 진행 권고가 가능합니다."
            )
        elif record.soft_fit_score is not None and record.soft_fit_score < 55.0:
            value = ProcurementRecommendationValue.NO_GO
            summary = (
                f"Weighted fit score {record.soft_fit_score:.2f}점으로 초기 기준선 55점을 밑돌아 현재 상태에서는 보류가 적절합니다."
            )
        else:
            value = ProcurementRecommendationValue.CONDITIONAL_GO
            score_text = f"{record.soft_fit_score:.2f}점" if record.soft_fit_score is not None else "미산정"
            summary = (
                f"Weighted fit score {score_text} 기준으로 보완 가능한 갭이 남아 있어 조건부 진행이 적절합니다."
            )

        evidence = [
            f"{item.label}: {item.score:.0f}점"
            for item in strong_scores[:3]
        ]
        evidence.extend(
            f"{item.label}: {item.reason}"
            for item in hard_failures[:3]
        )
        if record.soft_fit_score is not None:
            evidence.append(f"Weighted fit score: {record.soft_fit_score:.2f}")

        remediation_notes = [
            f"{item.label}: {item.reason}"
            for item in hard_failures
        ]
        remediation_notes.extend(
            f"{item.label}: {item.summary}"
            for item in weak_scores[:4]
        )
        remediation_notes.extend(
            f"추가 확인 필요: {item}"
            for item in record.missing_data[:4]
        )
        if value == ProcurementRecommendationValue.CONDITIONAL_GO and not remediation_notes:
            lowest_score = min(
                (
                    item
                    for item in record.score_breakdown
                    if item.status == ProcurementScoreStatus.SCORED
                ),
                key=lambda item: item.score,
                default=None,
            )
            if lowest_score is not None:
                remediation_notes.append(
                    f"{lowest_score.label}: {lowest_score.summary}"
                )

        return ProcurementRecommendation(
            value=value,
            summary=summary,
            evidence=_unique(evidence),
            missing_data=list(record.missing_data),
            remediation_notes=_unique(remediation_notes),
            decided_at=self._now_provider().isoformat(),
        )

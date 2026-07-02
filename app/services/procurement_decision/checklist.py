"""Checklist-building mixin.

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

from app.schemas import (
    ProcurementChecklistItem,
    ProcurementChecklistSeverity,
    ProcurementChecklistStatus,
    ProcurementDecisionRecord,
    ProcurementHardFilterStatus,
    ProcurementScoreStatus,
)


class ChecklistMixin:
    """Builds the bid-readiness checklist items for a decision record."""

    def _build_checklist(self, record: ProcurementDecisionRecord) -> list[ProcurementChecklistItem]:
        return [
            self._build_checklist_item(
                record,
                category="eligibility_and_compliance",
                title="입찰참가자격 및 참여제한 확인",
                hard_filter_codes=["mandatory_eligibility_mismatch", "regional_or_participation_restriction"],
                score_keys=["compliance_readiness"],
                remediation="참여자격 증빙과 지역 제한 충족 여부를 입찰 전 다시 확인합니다.",
            ),
            self._build_checklist_item(
                record,
                category="certifications_and_licenses",
                title="필수 인증 및 라이선스 증빙 확보",
                hard_filter_codes=["mandatory_certification_or_license"],
                score_keys=["compliance_readiness"],
                remediation="필수 인증서 또는 등록증 사본을 최신본으로 정리합니다.",
            ),
            self._build_checklist_item(
                record,
                category="domain_capability_fit",
                title="도메인 수행역량 정합성 검토",
                hard_filter_codes=["required_deliverable_capability"],
                score_keys=["domain_fit", "delivery_capability_fit"],
                remediation="필수 도메인과 산출물에 맞는 역량 및 수행방식을 보강합니다.",
            ),
            self._build_checklist_item(
                record,
                category="reference_cases_and_proof_points",
                title="유사사업 레퍼런스와 증빙 포인트 확보",
                hard_filter_codes=["mandatory_domain_experience"],
                score_keys=["reference_project_fit"],
                remediation="유사사업 실적, 발주기관 사례, 정량 성과를 정리합니다.",
            ),
            self._build_checklist_item(
                record,
                category="staffing_and_partner_readiness",
                title="투입인력 및 파트너 대응 준비",
                hard_filter_codes=["mandatory_consortium_requirement"],
                score_keys=["staffing_readiness", "partner_readiness"],
                remediation="핵심 인력, 협력사, 역할 분담안을 명확히 정리합니다.",
            ),
            self._build_checklist_item(
                record,
                category="schedule_and_deadline_readiness",
                title="마감 일정과 준비 리드타임 점검",
                hard_filter_codes=["impossible_deadline"],
                score_keys=["schedule_readiness"],
                remediation="제안 일정 역산 계획과 필수 산출물 준비 리드타임을 재확인합니다.",
            ),
            self._build_checklist_item(
                record,
                category="deliverables_and_scope_clarity",
                title="요구 산출물과 범위 명확화",
                hard_filter_codes=["required_deliverable_capability"],
                score_keys=["document_readiness", "delivery_capability_fit"],
                remediation="핵심 요구사항과 평가기준, 범위 경계를 다시 구조화합니다.",
            ),
            self._build_checklist_item(
                record,
                category="security_data_infrastructure_obligations",
                title="보안·데이터·인프라 의무 검토",
                hard_filter_codes=["prohibited_risk_condition", "mandatory_certification_or_license"],
                score_keys=["compliance_readiness", "delivery_capability_fit"],
                remediation="보안 인증, 데이터 처리 책임, 인프라 의무를 명시적으로 검토합니다.",
            ),
            self._build_checklist_item(
                record,
                category="pricing_budget_contract_risk",
                title="예산 적합도와 계약 리스크 검토",
                hard_filter_codes=["prohibited_risk_condition"],
                score_keys=["profitability_budget_fit"],
                remediation="예산 규모, 수익성 가정, 계약 리스크를 내부 기준과 비교합니다.",
            ),
            self._build_checklist_item(
                record,
                category="executive_approval_internal_readiness",
                title="내부 승인과 추진 가능성 확인",
                hard_filter_codes=[],
                score_keys=["strategic_fit", "document_readiness", "schedule_readiness"],
                remediation="핵심 리스크, 남은 갭, 승인 포인트를 요약해 내부 의사결정을 준비합니다.",
            ),
        ]

    def _build_checklist_item(
        self,
        record: ProcurementDecisionRecord,
        *,
        category: str,
        title: str,
        hard_filter_codes: list[str],
        score_keys: list[str],
        remediation: str,
    ) -> ProcurementChecklistItem:
        relevant_filters = [item for item in record.hard_filters if item.code in hard_filter_codes]
        relevant_scores = [item for item in record.score_breakdown if item.key in score_keys]
        filter_failures = [item for item in relevant_filters if item.status == ProcurementHardFilterStatus.FAIL]
        filter_unknown = [item for item in relevant_filters if item.status == ProcurementHardFilterStatus.UNKNOWN]
        low_scores = [item for item in relevant_scores if item.status == ProcurementScoreStatus.SCORED and item.score < 60.0]
        medium_scores = [item for item in relevant_scores if item.status == ProcurementScoreStatus.SCORED and 60.0 <= item.score < 75.0]
        insufficient_scores = [item for item in relevant_scores if item.status == ProcurementScoreStatus.INSUFFICIENT_DATA]

        if filter_failures:
            status = ProcurementChecklistStatus.BLOCKED
            severity = ProcurementChecklistSeverity.CRITICAL
        elif filter_unknown or low_scores or medium_scores or insufficient_scores or record.soft_fit_status == ProcurementScoreStatus.INSUFFICIENT_DATA:
            status = ProcurementChecklistStatus.ACTION_NEEDED
            severity = ProcurementChecklistSeverity.HIGH if filter_unknown or low_scores else ProcurementChecklistSeverity.MEDIUM
        else:
            status = ProcurementChecklistStatus.READY
            severity = ProcurementChecklistSeverity.LOW

        evidence_parts = [f"{item.label}: {item.reason}" for item in relevant_filters]
        evidence_parts.extend(
            f"{item.label}: {item.score:.0f}점"
            for item in relevant_scores
            if item.status == ProcurementScoreStatus.SCORED
        )
        if not evidence_parts and record.recommendation is not None:
            evidence_parts.append(record.recommendation.summary)

        if status == ProcurementChecklistStatus.READY:
            remediation_note = "현재 구조화된 평가 기준에서는 즉시 조치가 필요한 항목이 없습니다."
        elif status == ProcurementChecklistStatus.BLOCKED:
            remediation_note = remediation
        else:
            missing = ", ".join(record.missing_data[:2])
            remediation_note = remediation if not missing else f"{remediation} 부족한 입력: {missing}"

        return ProcurementChecklistItem(
            category=category,
            title=title,
            status=status,
            severity=severity,
            evidence=" | ".join(evidence_parts[:3]),
            remediation_note=remediation_note,
        )

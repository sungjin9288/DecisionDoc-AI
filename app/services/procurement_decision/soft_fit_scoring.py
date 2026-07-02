"""Soft-fit weighted scoring mixin.

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

from app.schemas import (
    ProcurementHardFilterResult,
    ProcurementHardFilterStatus,
    ProcurementScoreBreakdownItem,
    ProcurementScoreStatus,
)
from app.services.procurement_decision.constants import (
    CONSORTIUM_REQUIRED_TERMS,
    DEFAULT_MIN_SCORABLE_WEIGHT,
    DOMAIN_GROUPS,
    EXPERIENCE_REQUIREMENT_TERMS,
    PARTNER_TERMS,
    REFERENCE_TERMS,
    SCORE_WEIGHTS,
    STAFFING_TERMS,
    _EvaluationInputs,
)
from app.services.procurement_decision.text_utils import (
    _contains_any,
    _extract_budget_amount,
    _has_negative_signal,
    _matched_groups,
    _normalize_text,
    _parse_deadline,
    _score_from_overlap,
    _unique,
)


class SoftFitScoringMixin:
    """Computes the weighted soft-fit score breakdown for a decision record."""

    def _evaluate_soft_fit(
        self,
        hard_filters: list[ProcurementHardFilterResult],
        inputs: _EvaluationInputs,
    ) -> tuple[list[ProcurementScoreBreakdownItem], float | None, str, list[str]]:
        missing_data: list[str] = []
        items = [
            self._score_domain_fit(inputs, missing_data),
            self._score_reference_fit(inputs, missing_data),
            self._score_staffing_readiness(inputs, missing_data),
            self._score_delivery_capability(inputs, missing_data),
            self._score_strategic_fit(inputs, missing_data),
            self._score_profitability(inputs, missing_data),
            self._score_partner_readiness(inputs, missing_data),
            self._score_document_readiness(inputs, missing_data),
            self._score_schedule_readiness(inputs, missing_data),
            self._score_compliance_readiness(hard_filters, missing_data),
        ]
        available_weight = sum(item.weight for item in items if item.status == ProcurementScoreStatus.SCORED)
        total_weighted = sum(item.weighted_score for item in items if item.status == ProcurementScoreStatus.SCORED)
        final_score = round(total_weighted / available_weight, 2) if available_weight > 0 else None
        if final_score is not None and any(item.blocking and item.status == ProcurementHardFilterStatus.FAIL for item in hard_filters):
            final_score = min(final_score, 54.0)
        status = (
            ProcurementScoreStatus.SCORED
            if available_weight >= DEFAULT_MIN_SCORABLE_WEIGHT
            else ProcurementScoreStatus.INSUFFICIENT_DATA
        )
        return items, final_score, status, _unique(missing_data)

    def _score_item(
        self,
        *,
        key: str,
        label: str,
        raw_score: float | None,
        summary: str,
        evidence: list[str] | None = None,
    ) -> ProcurementScoreBreakdownItem:
        weight = SCORE_WEIGHTS[key]
        if raw_score is None:
            return ProcurementScoreBreakdownItem(
                key=key,
                label=label,
                score=0.0,
                weight=weight,
                weighted_score=0.0,
                status=ProcurementScoreStatus.INSUFFICIENT_DATA,
                summary=summary,
                evidence=evidence or [],
            )
        score = round(max(0.0, min(100.0, raw_score)), 2)
        return ProcurementScoreBreakdownItem(
            key=key,
            label=label,
            score=score,
            weight=weight,
            weighted_score=round(score * weight, 2),
            status=ProcurementScoreStatus.SCORED,
            summary=summary,
            evidence=evidence or [],
        )

    def _score_domain_fit(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        required = _matched_groups(inputs.opportunity_text, DOMAIN_GROUPS)
        available = _matched_groups(inputs.capability_text, DOMAIN_GROUPS)
        if not required:
            missing_data.append("domain mapping cues")
            return self._score_item(
                key="domain_fit",
                label="도메인 적합도",
                raw_score=None,
                summary="도메인 적합도를 산정할 opportunity 단서가 부족합니다.",
            )
        if not inputs.capability_text:
            missing_data.append("capability profile knowledge context")
            return self._score_item(
                key="domain_fit",
                label="도메인 적합도",
                raw_score=None,
                summary="Capability profile 정보가 없어 도메인 적합도를 계산하지 못했습니다.",
                evidence=sorted(required),
            )
        overlap = sorted(required & available)
        score = _score_from_overlap(len(overlap))
        if _has_negative_signal(inputs.capability_text) and len(overlap) < 3:
            score -= 10.0
        return self._score_item(
            key="domain_fit",
            label="도메인 적합도",
            raw_score=score,
            summary="Opportunity 도메인과 capability profile의 겹침 정도를 기반으로 계산했습니다.",
            evidence=overlap or sorted(required),
        )

    def _score_reference_fit(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        if not inputs.capability_text:
            missing_data.append("reference project evidence")
            return self._score_item(
                key="reference_project_fit",
                label="유사 레퍼런스 적합도",
                raw_score=None,
                summary="Capability profile 정보가 없어 레퍼런스 적합도를 계산하지 못했습니다.",
            )
        has_refs = _contains_any(inputs.capability_text, REFERENCE_TERMS)
        overlap = _matched_groups(inputs.opportunity_text, DOMAIN_GROUPS) & _matched_groups(inputs.capability_text, DOMAIN_GROUPS)
        if has_refs and overlap:
            score = 86.0
        elif has_refs:
            score = 68.0
        elif _contains_any(inputs.opportunity_text, EXPERIENCE_REQUIREMENT_TERMS):
            score = 25.0
        else:
            score = 50.0
        if _has_negative_signal(inputs.capability_text):
            score -= 18.0
        evidence = sorted(overlap) if overlap else (["reference signals found"] if has_refs else [])
        return self._score_item(
            key="reference_project_fit",
            label="유사 레퍼런스 적합도",
            raw_score=score,
            summary="레퍼런스 표현과 도메인 겹침을 기반으로 계산했습니다.",
            evidence=evidence,
        )

    def _score_staffing_readiness(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        if not inputs.capability_text:
            missing_data.append("staffing readiness evidence")
            return self._score_item(
                key="staffing_readiness",
                label="인력 준비도",
                raw_score=None,
                summary="Capability profile 정보가 없어 인력 준비도를 계산하지 못했습니다.",
            )
        count = sum(1 for term in STAFFING_TERMS if term.lower() in _normalize_text(inputs.capability_text))
        if count >= 4:
            score = 85.0
        elif count >= 2:
            score = 72.0
        elif count == 1:
            score = 58.0
        else:
            score = 32.0
        return self._score_item(
            key="staffing_readiness",
            label="인력 준비도",
            raw_score=score,
            summary="Capability profile 내 인력 및 역할 단서 빈도를 기반으로 계산했습니다.",
            evidence=[term for term in STAFFING_TERMS if term.lower() in _normalize_text(inputs.capability_text)],
        )

    def _score_delivery_capability(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        required = _matched_groups(inputs.opportunity_text, DOMAIN_GROUPS)
        available = _matched_groups(inputs.capability_text, DOMAIN_GROUPS)
        if not required:
            missing_data.append("deliverable capability cues")
            return self._score_item(
                key="delivery_capability_fit",
                label="수행역량 적합도",
                raw_score=None,
                summary="수행역량 적합도를 산정할 요구사항 단서가 부족합니다.",
            )
        if not inputs.capability_text:
            missing_data.append("deliverable capability evidence")
            return self._score_item(
                key="delivery_capability_fit",
                label="수행역량 적합도",
                raw_score=None,
                summary="Capability profile 정보가 없어 수행역량 적합도를 계산하지 못했습니다.",
            )
        overlap = sorted(required & available)
        score = _score_from_overlap(len(overlap))
        if _has_negative_signal(inputs.capability_text) and len(overlap) < 2:
            score -= 12.0
        return self._score_item(
            key="delivery_capability_fit",
            label="수행역량 적합도",
            raw_score=score,
            summary="필수 산출물 및 요구사항과 capability profile의 겹침을 기반으로 계산했습니다.",
            evidence=overlap or sorted(required),
        )

    def _score_strategic_fit(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        if not inputs.capability_text:
            missing_data.append("strategic fit evidence")
            return self._score_item(
                key="strategic_fit",
                label="전략 적합도",
                raw_score=None,
                summary="Capability profile 정보가 없어 전략 적합도를 계산하지 못했습니다.",
            )
        public_overlap = _matched_groups(inputs.opportunity_text, {"public": DOMAIN_GROUPS["public_sector"]}) & _matched_groups(
            inputs.capability_text,
            {"public": DOMAIN_GROUPS["public_sector"]},
        )
        score = 82.0 if public_overlap else 60.0
        return self._score_item(
            key="strategic_fit",
            label="전략 적합도",
            raw_score=score,
            summary="공공 부문 및 전략적 주력 분야 단서를 기준으로 계산했습니다.",
            evidence=sorted(public_overlap),
        )

    def _score_profitability(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        budget_amount = _extract_budget_amount(inputs.budget_text)
        if budget_amount is None:
            missing_data.append("budget")
            return self._score_item(
                key="profitability_budget_fit",
                label="예산 적합도",
                raw_score=None,
                summary="예산 정보를 해석하지 못해 예산 적합도를 계산하지 못했습니다.",
            )
        if budget_amount <= 7_000_000_000:
            score = 78.0
        elif budget_amount <= 20_000_000_000:
            score = 65.0
        else:
            score = 50.0
        return self._score_item(
            key="profitability_budget_fit",
            label="예산 적합도",
            raw_score=score,
            summary="예산 규모의 초기 적정 범위만 반영한 보수적 점수입니다.",
            evidence=[inputs.budget_text],
        )

    def _score_partner_readiness(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        consortium_required = _contains_any(inputs.opportunity_text, CONSORTIUM_REQUIRED_TERMS)
        if consortium_required and not inputs.capability_text:
            missing_data.append("partner readiness evidence")
            return self._score_item(
                key="partner_readiness",
                label="파트너 준비도",
                raw_score=None,
                summary="파트너 대응 여부를 확인할 capability profile 정보가 없습니다.",
            )
        if consortium_required:
            score = 82.0 if _contains_any(inputs.capability_text, PARTNER_TERMS) else 30.0
            evidence = ["consortium requirement"] + (
                ["partner readiness signal"] if _contains_any(inputs.capability_text, PARTNER_TERMS) else []
            )
            return self._score_item(
                key="partner_readiness",
                label="파트너 준비도",
                raw_score=score,
                summary="컨소시엄 요구 여부와 파트너 단서를 기준으로 계산했습니다.",
                evidence=evidence,
            )
        return self._score_item(
            key="partner_readiness",
            label="파트너 준비도",
            raw_score=60.0,
            summary="명시적 컨소시엄 요구가 없어 중립적인 기본 파트너 준비 점수를 부여했습니다.",
        )

    def _score_document_readiness(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        fields = [
            bool(inputs.parsed_rfp_fields.get("project_title")),
            bool(inputs.parsed_rfp_fields.get("issuer")),
            bool(inputs.parsed_rfp_fields.get("budget")),
            bool(inputs.parsed_rfp_fields.get("deadline")),
            bool(inputs.parsed_rfp_fields.get("objective")),
            bool(inputs.parsed_rfp_fields.get("key_requirements")),
            bool(inputs.parsed_rfp_fields.get("evaluation_criteria")),
        ]
        completeness = sum(fields)
        if completeness == 0:
            missing_data.append("structured RFP requirement signals")
            return self._score_item(
                key="document_readiness",
                label="문서 준비도",
                raw_score=None,
                summary="구조화된 RFP 필드가 없어 문서 준비도를 계산하지 못했습니다.",
            )
        if completeness >= 6:
            score = 90.0
        elif completeness >= 4:
            score = 72.0
        elif completeness >= 2:
            score = 48.0
        else:
            score = 30.0
        return self._score_item(
            key="document_readiness",
            label="문서 준비도",
            raw_score=score,
            summary="구조화된 RFP 필드 완성도를 기준으로 계산했습니다.",
            evidence=[f"structured_fields={completeness}/7"],
        )

    def _score_schedule_readiness(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementScoreBreakdownItem:
        deadline = _parse_deadline(inputs.deadline_text)
        if deadline is None:
            missing_data.append("deadline")
            return self._score_item(
                key="schedule_readiness",
                label="일정 준비도",
                raw_score=None,
                summary="마감일을 해석하지 못해 일정 준비도를 계산하지 못했습니다.",
            )
        days_left = (deadline - self._now_provider()).total_seconds() / 86400
        if days_left >= 45:
            score = 90.0
        elif days_left >= 30:
            score = 80.0
        elif days_left >= 21:
            score = 70.0
        elif days_left >= 14:
            score = 60.0
        elif days_left >= 7:
            score = 35.0
        else:
            score = 15.0
        return self._score_item(
            key="schedule_readiness",
            label="일정 준비도",
            raw_score=score,
            summary="제안 마감일까지 남은 일수를 기준으로 계산했습니다.",
            evidence=[inputs.deadline_text],
        )

    def _score_compliance_readiness(
        self,
        hard_filters: list[ProcurementHardFilterResult],
        missing_data: list[str],
    ) -> ProcurementScoreBreakdownItem:
        relevant = [
            item
            for item in hard_filters
            if item.code in {
                "mandatory_eligibility_mismatch",
                "mandatory_certification_or_license",
                "regional_or_participation_restriction",
                "mandatory_consortium_requirement",
            }
        ]
        if not relevant:
            missing_data.append("compliance evaluation inputs")
            return self._score_item(
                key="compliance_readiness",
                label="컴플라이언스 준비도",
                raw_score=None,
                summary="컴플라이언스 평가 입력이 부족합니다.",
            )
        if any(item.status == ProcurementHardFilterStatus.FAIL for item in relevant):
            score = 15.0
        else:
            unknown_count = sum(1 for item in relevant if item.status == ProcurementHardFilterStatus.UNKNOWN)
            if unknown_count >= 2:
                score = 45.0
            elif unknown_count == 1:
                score = 62.0
            else:
                score = 85.0
        return self._score_item(
            key="compliance_readiness",
            label="컴플라이언스 준비도",
            raw_score=score,
            summary="필수 자격, 인증, 지역 제한, 파트너 대응 필터 결과를 기준으로 계산했습니다.",
            evidence=[f"{item.code}:{item.status}" for item in relevant],
        )

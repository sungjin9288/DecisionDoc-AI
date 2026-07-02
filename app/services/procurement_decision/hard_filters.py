"""Hard-filter evaluation mixin (blocking eligibility/compliance gates).

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

from app.schemas import (
    ProcurementDecisionRecord,
    ProcurementHardFilterResult,
    ProcurementHardFilterStatus,
)
from app.services.procurement_decision.constants import (
    CERTIFICATION_GROUPS,
    CONSORTIUM_REQUIRED_TERMS,
    DEFAULT_MIN_READY_DAYS,
    DOMAIN_GROUPS,
    ELIGIBILITY_GROUPS,
    EXPERIENCE_REQUIREMENT_TERMS,
    PARTNER_TERMS,
    REFERENCE_TERMS,
    RISK_TERMS,
    _EvaluationInputs,
)
from app.services.procurement_decision.text_utils import (
    _contains_any,
    _detect_region,
    _matched_groups,
    _normalize_text,
    _parse_deadline,
    _unique,
)


class HardFiltersMixin:
    """Evaluates blocking hard filters (eligibility, certification, region, etc.)."""

    def _evaluate_hard_filters(
        self,
        record: ProcurementDecisionRecord,
        inputs: _EvaluationInputs,
    ) -> tuple[list[ProcurementHardFilterResult], list[str]]:
        missing_data: list[str] = []
        if not inputs.latest_snapshot_payload:
            missing_data.append("latest procurement source snapshot")
        if not inputs.capability_text:
            missing_data.append("capability profile knowledge context")
        if not inputs.parsed_rfp_fields.get("key_requirements") and not inputs.parsed_rfp_fields.get("evaluation_criteria"):
            missing_data.append("structured RFP requirement signals")

        filters = [
            self._eligibility_filter(inputs, missing_data),
            self._certification_filter(inputs, missing_data),
            self._regional_filter(inputs, missing_data),
            self._consortium_filter(inputs, missing_data),
            self._deadline_filter(inputs, missing_data),
            self._risk_filter(inputs, missing_data),
            self._deliverable_capability_filter(inputs, missing_data),
            self._domain_experience_filter(inputs, missing_data),
        ]
        return filters, _unique(missing_data)

    def _eligibility_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        required = _matched_groups(inputs.opportunity_text, ELIGIBILITY_GROUPS)
        if not required:
            return ProcurementHardFilterResult(
                code="mandatory_eligibility_mismatch",
                label="필수 참여자격 충족 여부",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="명시적인 참여자격 제한이 탐지되지 않았습니다.",
            )
        if not inputs.capability_text:
            missing_data.append("participation eligibility evidence")
            return ProcurementHardFilterResult(
                code="mandatory_eligibility_mismatch",
                label="필수 참여자격 충족 여부",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="참여자격 충족 여부를 확인할 capability profile 정보가 없습니다.",
                evidence=sorted(required),
            )
        available = _matched_groups(inputs.capability_text, ELIGIBILITY_GROUPS)
        missing = sorted(required - available)
        if missing:
            return ProcurementHardFilterResult(
                code="mandatory_eligibility_mismatch",
                label="필수 참여자격 충족 여부",
                status=ProcurementHardFilterStatus.FAIL,
                blocking=True,
                reason="필수 참여자격을 뒷받침하는 내부 증빙이 확인되지 않았습니다.",
                evidence=missing,
            )
        return ProcurementHardFilterResult(
            code="mandatory_eligibility_mismatch",
            label="필수 참여자격 충족 여부",
            status=ProcurementHardFilterStatus.PASS,
            blocking=True,
            reason="탐지된 참여자격 제한과 일치하는 내부 자격 단서가 있습니다.",
            evidence=sorted(required),
        )

    def _certification_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        required = _matched_groups(inputs.opportunity_text, CERTIFICATION_GROUPS)
        if not required:
            return ProcurementHardFilterResult(
                code="mandatory_certification_or_license",
                label="필수 인증 및 라이선스 충족 여부",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="명시적인 필수 인증 또는 라이선스 조건이 탐지되지 않았습니다.",
            )
        if not inputs.capability_text:
            missing_data.append("certification or license evidence")
            return ProcurementHardFilterResult(
                code="mandatory_certification_or_license",
                label="필수 인증 및 라이선스 충족 여부",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="필수 인증 충족 여부를 확인할 capability profile 정보가 없습니다.",
                evidence=sorted(required),
            )
        available = _matched_groups(inputs.capability_text, CERTIFICATION_GROUPS)
        missing = sorted(required - available)
        if missing:
            return ProcurementHardFilterResult(
                code="mandatory_certification_or_license",
                label="필수 인증 및 라이선스 충족 여부",
                status=ProcurementHardFilterStatus.FAIL,
                blocking=True,
                reason="필수 인증 또는 라이선스 증빙이 확인되지 않았습니다.",
                evidence=missing,
            )
        return ProcurementHardFilterResult(
            code="mandatory_certification_or_license",
            label="필수 인증 및 라이선스 충족 여부",
            status=ProcurementHardFilterStatus.PASS,
            blocking=True,
            reason="탐지된 인증 요구사항을 뒷받침하는 내부 단서가 있습니다.",
            evidence=sorted(required),
        )

    def _regional_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        if _contains_any(inputs.opportunity_text, ("지역제한 없음", "지역 제한 없음", "제한 없음")):
            return ProcurementHardFilterResult(
                code="regional_or_participation_restriction",
                label="지역 및 참여제한 충돌 여부",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="지역 제한 없음으로 명시돼 있습니다.",
            )
        if not _contains_any(inputs.opportunity_text, ("지역제한", "소재지", "사업장 소재")):
            return ProcurementHardFilterResult(
                code="regional_or_participation_restriction",
                label="지역 및 참여제한 충돌 여부",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="명시적인 지역 제한 조건이 탐지되지 않았습니다.",
            )
        required_region = _detect_region(inputs.opportunity_text)
        if not required_region:
            missing_data.append("regional restriction detail")
            return ProcurementHardFilterResult(
                code="regional_or_participation_restriction",
                label="지역 및 참여제한 충돌 여부",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="지역 제한은 감지됐지만 구체 지역을 해석하지 못했습니다.",
            )
        if not inputs.capability_text:
            missing_data.append("regional capability evidence")
            return ProcurementHardFilterResult(
                code="regional_or_participation_restriction",
                label="지역 및 참여제한 충돌 여부",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="지역 제한 충족 여부를 확인할 capability profile 정보가 없습니다.",
                evidence=[required_region],
            )
        normalized_capability = _normalize_text(inputs.capability_text)
        if "전국" in inputs.capability_text or required_region.lower() in normalized_capability:
            return ProcurementHardFilterResult(
                code="regional_or_participation_restriction",
                label="지역 및 참여제한 충돌 여부",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="지역 제한과 부합하는 수행 범위 단서가 있습니다.",
                evidence=[required_region],
            )
        return ProcurementHardFilterResult(
            code="regional_or_participation_restriction",
            label="지역 및 참여제한 충돌 여부",
            status=ProcurementHardFilterStatus.FAIL,
            blocking=True,
            reason="지역 제한과 맞는 수행 범위 단서가 확인되지 않았습니다.",
            evidence=[required_region],
        )

    def _consortium_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        if not _contains_any(inputs.opportunity_text, CONSORTIUM_REQUIRED_TERMS):
            return ProcurementHardFilterResult(
                code="mandatory_consortium_requirement",
                label="필수 컨소시엄 또는 파트너 경로",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="명시적인 컨소시엄 요구사항이 탐지되지 않았습니다.",
            )
        if not inputs.capability_text:
            missing_data.append("partner readiness evidence")
            return ProcurementHardFilterResult(
                code="mandatory_consortium_requirement",
                label="필수 컨소시엄 또는 파트너 경로",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="컨소시엄 대응 여부를 확인할 capability profile 정보가 없습니다.",
            )
        if _contains_any(inputs.capability_text, PARTNER_TERMS):
            return ProcurementHardFilterResult(
                code="mandatory_consortium_requirement",
                label="필수 컨소시엄 또는 파트너 경로",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="협력사 또는 컨소시엄 대응 단서가 확인됐습니다.",
                evidence=["partner readiness signal"],
            )
        return ProcurementHardFilterResult(
            code="mandatory_consortium_requirement",
            label="필수 컨소시엄 또는 파트너 경로",
            status=ProcurementHardFilterStatus.FAIL,
            blocking=True,
            reason="컨소시엄 또는 파트너 대응 경로가 확인되지 않았습니다.",
        )

    def _deadline_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        deadline = _parse_deadline(inputs.deadline_text)
        if deadline is None:
            missing_data.append("deadline")
            return ProcurementHardFilterResult(
                code="impossible_deadline",
                label="내부 준비 기준 대비 마감 가능성",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="마감일을 파싱할 수 없어 준비 가능성을 판단하지 못했습니다.",
            )
        days_left = (deadline - self._now_provider()).total_seconds() / 86400
        if days_left < DEFAULT_MIN_READY_DAYS:
            return ProcurementHardFilterResult(
                code="impossible_deadline",
                label="내부 준비 기준 대비 마감 가능성",
                status=ProcurementHardFilterStatus.FAIL,
                blocking=True,
                reason=f"제안 마감까지 약 {max(int(days_left), 0)}일 남아 내부 준비 최소 기준 {DEFAULT_MIN_READY_DAYS}일을 충족하지 못합니다.",
                evidence=[inputs.deadline_text],
            )
        return ProcurementHardFilterResult(
            code="impossible_deadline",
            label="내부 준비 기준 대비 마감 가능성",
            status=ProcurementHardFilterStatus.PASS,
            blocking=True,
            reason=f"제안 마감까지 약 {int(days_left)}일 남아 내부 준비 기준을 충족합니다.",
            evidence=[inputs.deadline_text],
        )

    def _risk_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        if not inputs.capability_text:
            missing_data.append("excluded risk conditions")
            return ProcurementHardFilterResult(
                code="prohibited_risk_condition",
                label="금지 리스크 조건 충돌 여부",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="내부 금지 리스크 기준을 확인할 capability profile 정보가 없습니다.",
            )
        normalized_capability = _normalize_text(inputs.capability_text)
        denied_terms = [
            term
            for term in RISK_TERMS
            if term.lower() in normalized_capability and _contains_any(normalized_capability, ("불가", "제외", "금지"))
        ]
        matched = [term for term in denied_terms if term.lower() in _normalize_text(inputs.opportunity_text)]
        if matched:
            return ProcurementHardFilterResult(
                code="prohibited_risk_condition",
                label="금지 리스크 조건 충돌 여부",
                status=ProcurementHardFilterStatus.FAIL,
                blocking=True,
                reason="내부 금지 리스크 조건과 충돌하는 조항이 탐지됐습니다.",
                evidence=matched,
            )
        if denied_terms:
            return ProcurementHardFilterResult(
                code="prohibited_risk_condition",
                label="금지 리스크 조건 충돌 여부",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="정의된 금지 리스크 조건과 직접 충돌하는 항목은 탐지되지 않았습니다.",
                evidence=denied_terms,
            )
        return ProcurementHardFilterResult(
            code="prohibited_risk_condition",
            label="금지 리스크 조건 충돌 여부",
            status=ProcurementHardFilterStatus.PASS,
            blocking=True,
            reason="Capability profile에 금지 리스크 조건이 명시되지 않았습니다.",
        )

    def _deliverable_capability_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        required_groups = _matched_groups(inputs.opportunity_text, DOMAIN_GROUPS)
        if not required_groups:
            missing_data.append("deliverable capability cues")
            return ProcurementHardFilterResult(
                code="required_deliverable_capability",
                label="필수 산출물 수행역량",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="필수 산출물 역량을 매핑할 요구사항 단서가 부족합니다.",
            )
        if not inputs.capability_text:
            missing_data.append("deliverable capability evidence")
            return ProcurementHardFilterResult(
                code="required_deliverable_capability",
                label="필수 산출물 수행역량",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="수행역량을 확인할 capability profile 정보가 없습니다.",
                evidence=sorted(required_groups),
            )
        available_groups = _matched_groups(inputs.capability_text, DOMAIN_GROUPS)
        overlap = sorted(required_groups & available_groups)
        if overlap:
            return ProcurementHardFilterResult(
                code="required_deliverable_capability",
                label="필수 산출물 수행역량",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="필수 산출물과 겹치는 수행역량 단서가 있습니다.",
                evidence=overlap,
            )
        return ProcurementHardFilterResult(
            code="required_deliverable_capability",
            label="필수 산출물 수행역량",
            status=ProcurementHardFilterStatus.FAIL,
            blocking=True,
            reason="필수 산출물과 맞는 수행역량 단서가 capability profile에서 확인되지 않았습니다.",
            evidence=sorted(required_groups),
        )

    def _domain_experience_filter(self, inputs: _EvaluationInputs, missing_data: list[str]) -> ProcurementHardFilterResult:
        if not _contains_any(inputs.opportunity_text, EXPERIENCE_REQUIREMENT_TERMS):
            return ProcurementHardFilterResult(
                code="mandatory_domain_experience",
                label="필수 도메인 경험",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="명시적인 유사사업 또는 도메인 실적 요구가 탐지되지 않았습니다.",
            )
        if not inputs.capability_text:
            missing_data.append("reference project evidence")
            return ProcurementHardFilterResult(
                code="mandatory_domain_experience",
                label="필수 도메인 경험",
                status=ProcurementHardFilterStatus.UNKNOWN,
                blocking=True,
                reason="도메인 실적을 확인할 capability profile 정보가 없습니다.",
            )
        has_reference_signal = _contains_any(inputs.capability_text, REFERENCE_TERMS)
        domain_overlap = _matched_groups(inputs.opportunity_text, DOMAIN_GROUPS) & _matched_groups(
            inputs.capability_text,
            DOMAIN_GROUPS,
        )
        if has_reference_signal and domain_overlap:
            return ProcurementHardFilterResult(
                code="mandatory_domain_experience",
                label="필수 도메인 경험",
                status=ProcurementHardFilterStatus.PASS,
                blocking=True,
                reason="유사사업 또는 도메인 실적 단서가 확인됐습니다.",
                evidence=sorted(domain_overlap),
            )
        return ProcurementHardFilterResult(
            code="mandatory_domain_experience",
            label="필수 도메인 경험",
            status=ProcurementHardFilterStatus.FAIL,
            blocking=True,
            reason="명시된 도메인 실적 요구를 뒷받침하는 내부 실적 단서가 부족합니다.",
            evidence=sorted(domain_overlap) if domain_overlap else ["reference evidence missing"],
        )

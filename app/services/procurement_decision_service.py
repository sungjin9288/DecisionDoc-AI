"""Deterministic public procurement decision evaluation for project-scoped state."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.schemas import (
    CapabilityProfileReference,
    ProcurementChecklistItem,
    ProcurementChecklistSeverity,
    ProcurementChecklistStatus,
    ProcurementDecisionRecord,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementHardFilterStatus,
    ProcurementRecommendation,
    ProcurementRecommendationValue,
    ProcurementScoreBreakdownItem,
    ProcurementScoreStatus,
)
from app.storage.knowledge_store import KnowledgeStore
from app.storage.procurement_store import ProcurementDecisionStore

DEFAULT_MIN_READY_DAYS = 14
DEFAULT_MIN_SCORABLE_WEIGHT = 0.65

SCORE_WEIGHTS: dict[str, float] = {
    "domain_fit": 0.16,
    "reference_project_fit": 0.12,
    "staffing_readiness": 0.10,
    "delivery_capability_fit": 0.12,
    "strategic_fit": 0.10,
    "profitability_budget_fit": 0.08,
    "partner_readiness": 0.08,
    "document_readiness": 0.08,
    "schedule_readiness": 0.08,
    "compliance_readiness": 0.08,
}

DOMAIN_GROUPS: dict[str, tuple[str, ...]] = {
    "ai": ("ai", "인공지능", "머신러닝", "ml", "llm"),
    "cloud": ("cloud", "클라우드", "saas", "iaas", "paas"),
    "security": ("보안", "정보보호", "isms", "pims", "개인정보"),
    "data": ("data", "데이터", "분석", "dw", "bi", "빅데이터"),
    "public_sector": ("공공", "행정", "조달", "지자체", "공공기관"),
    "citizen_service": ("민원", "대민", "서비스 고도화", "행정서비스"),
    "platform": ("플랫폼", "포털", "시스템", "구축", "고도화"),
    "consulting": ("컨설팅", "pm", "pmo", "isp", "bpr"),
}

CERTIFICATION_GROUPS: dict[str, tuple[str, ...]] = {
    "isms": ("isms", "정보보호 관리체계"),
    "pims": ("pims", "개인정보보호 관리체계"),
    "iso9001": ("iso 9001", "iso9001", "품질경영"),
    "software_business": ("소프트웨어사업자", "software business"),
    "direct_producer": ("직접생산", "직접생산확인"),
}

ELIGIBILITY_GROUPS: dict[str, tuple[str, ...]] = {
    "small_business": ("중소기업", "소기업", "소상공인"),
    "venture": ("벤처기업",),
    "female_business": ("여성기업",),
    "social_enterprise": ("사회적기업",),
    "startup": ("창업기업", "startup"),
}

REGION_TERMS: tuple[str, ...] = (
    "전국", "서울", "경기", "인천", "강원", "충북", "충남", "세종", "대전",
    "전북", "전남", "광주", "경북", "경남", "대구", "부산", "울산", "제주",
)
PARTNER_TERMS: tuple[str, ...] = ("공동수급", "컨소시엄", "분담이행", "협력사", "partner", "파트너")
REFERENCE_TERMS: tuple[str, ...] = ("레퍼런스", "실적", "사례", "구축 경험", "수행 경험", "프로젝트")
STAFFING_TERMS: tuple[str, ...] = ("전문가", "컨설턴트", "아키텍트", "개발자", "pm", "pmo", "인력", "투입")
RISK_TERMS: tuple[str, ...] = ("무한책임", "과도한 지체상금", "손해배상", "위약벌", "과업범위 불명확")
EXPERIENCE_REQUIREMENT_TERMS: tuple[str, ...] = ("유사사업", "동종", "레퍼런스", "수행실적", "경험")
CONSORTIUM_REQUIRED_TERMS: tuple[str, ...] = ("공동수급", "컨소시엄", "분담이행", "공동이행")
NEGATIVE_SIGNAL_TERMS: tuple[str, ...] = ("제한적", "부족", "적음", "미흡", "없음", "아직")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(term.lower() in normalized for term in terms)


def _matched_groups(text: str, groups: dict[str, tuple[str, ...]]) -> set[str]:
    normalized = _normalize_text(text)
    matched: set[str] = set()
    for key, terms in groups.items():
        if any(term.lower() in normalized for term in terms):
            matched.add(key)
    return matched


def _detect_region(text: str) -> str | None:
    normalized = _normalize_text(text)
    for region in REGION_TERMS:
        if region.lower() in normalized:
            return region
    return None


def _extract_budget_amount(value: str) -> int | None:
    if not value:
        return None
    normalized = value.replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)억원", normalized)
    if match:
        return int(float(match.group(1)) * 100_000_000)
    match = re.search(r"(\d+)만원", normalized)
    if match:
        return int(match.group(1)) * 10_000
    digits = re.sub(r"\D", "", normalized)
    if digits:
        return int(digits)
    return None


def _parse_deadline(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace(".", "-").replace("/", "-")
    normalized = normalized.replace("년", "-").replace("월", "-").replace("일", "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    hour = 23
    minute = 59
    time_match = re.search(r"(\d{1,2}):(\d{2})", normalized)
    if time_match:
        hour, minute = map(int, time_match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def _score_from_overlap(overlap_count: int) -> float:
    if overlap_count >= 3:
        return 90.0
    if overlap_count == 2:
        return 78.0
    if overlap_count == 1:
        return 64.0
    return 28.0


def _has_negative_signal(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_TERMS)


@dataclass
class _EvaluationInputs:
    capability_profile: CapabilityProfileReference | None
    capability_text: str
    latest_snapshot_payload: dict[str, Any]
    parsed_rfp_fields: dict[str, Any]
    opportunity_text: str
    deadline_text: str
    budget_text: str


class ProcurementDecisionService:
    """Deterministic evaluator for project-scoped procurement decisions."""

    def __init__(
        self,
        *,
        procurement_store: ProcurementDecisionStore,
        data_dir: str = "data",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._procurement_store = procurement_store
        self._data_dir = data_dir
        self._now_provider = now_provider or _now_utc

    def evaluate_project(self, *, project_id: str, tenant_id: str) -> ProcurementDecisionRecord:
        existing = self._procurement_store.get(project_id, tenant_id=tenant_id)
        if existing is None or existing.opportunity is None:
            raise KeyError("procurement_opportunity_not_attached")

        inputs = self._build_inputs(existing)
        hard_filters, missing_data = self._evaluate_hard_filters(existing, inputs)
        score_breakdown, soft_fit_score, soft_fit_status, scoring_missing = self._evaluate_soft_fit(
            hard_filters,
            inputs,
        )
        payload = ProcurementDecisionUpsert(
            project_id=existing.project_id,
            tenant_id=existing.tenant_id,
            schema_version=existing.schema_version,
            opportunity=existing.opportunity,
            capability_profile=inputs.capability_profile,
            hard_filters=hard_filters,
            score_breakdown=score_breakdown,
            soft_fit_score=soft_fit_score,
            soft_fit_status=soft_fit_status,
            missing_data=_unique(missing_data + scoring_missing),
            checklist_items=list(existing.checklist_items),
            recommendation=existing.recommendation,
            source_snapshots=list(existing.source_snapshots),
            notes=existing.notes,
        )
        return self._procurement_store.upsert(payload)

    def recommend_project(self, *, project_id: str, tenant_id: str) -> ProcurementDecisionRecord:
        evaluated = self.evaluate_project(project_id=project_id, tenant_id=tenant_id)
        recommendation = self._build_recommendation(evaluated)
        checklist_items = self._build_checklist(evaluated)
        payload = ProcurementDecisionUpsert(
            project_id=evaluated.project_id,
            tenant_id=evaluated.tenant_id,
            schema_version=evaluated.schema_version,
            opportunity=evaluated.opportunity,
            capability_profile=evaluated.capability_profile,
            hard_filters=list(evaluated.hard_filters),
            score_breakdown=list(evaluated.score_breakdown),
            soft_fit_score=evaluated.soft_fit_score,
            soft_fit_status=evaluated.soft_fit_status,
            missing_data=list(evaluated.missing_data),
            checklist_items=checklist_items,
            recommendation=recommendation,
            source_snapshots=list(evaluated.source_snapshots),
            notes=evaluated.notes,
        )
        return self._procurement_store.upsert(payload)

    def _build_inputs(self, record: ProcurementDecisionRecord) -> _EvaluationInputs:
        capability_profile, capability_text = self._resolve_capability_profile(record.project_id)
        latest_snapshot_payload = self._load_latest_snapshot_payload(record)
        parsed_rfp_fields = latest_snapshot_payload.get("extracted_fields", {}) or {}
        opportunity_text = "\n".join(
            filter(
                None,
                [
                    record.opportunity.title if record.opportunity else "",
                    record.opportunity.issuer if record.opportunity else "",
                    record.opportunity.raw_text_preview if record.opportunity else "",
                    latest_snapshot_payload.get("structured_context", ""),
                    latest_snapshot_payload.get("announcement", {}).get("raw_text", ""),
                    parsed_rfp_fields.get("objective", ""),
                    "\n".join(parsed_rfp_fields.get("key_requirements", []) or []),
                    "\n".join(parsed_rfp_fields.get("evaluation_criteria", []) or []),
                ],
            )
        )
        deadline_text = parsed_rfp_fields.get("deadline") or (record.opportunity.deadline if record.opportunity else "")
        budget_text = parsed_rfp_fields.get("budget") or (record.opportunity.budget if record.opportunity else "")
        return _EvaluationInputs(
            capability_profile=capability_profile,
            capability_text=capability_text,
            latest_snapshot_payload=latest_snapshot_payload,
            parsed_rfp_fields=parsed_rfp_fields,
            opportunity_text=opportunity_text,
            deadline_text=deadline_text,
            budget_text=budget_text,
        )

    def _resolve_capability_profile(
        self,
        project_id: str,
    ) -> tuple[CapabilityProfileReference | None, str]:
        store = KnowledgeStore(project_id, data_dir=self._data_dir)
        docs = store.list_documents()
        if not docs:
            return None, ""
        context = store.build_context()
        filenames = [doc.get("filename", "") for doc in docs[:3] if doc.get("filename")]
        title = ", ".join(filenames) if filenames else "project knowledge"
        summary = context[:300]
        return (
            CapabilityProfileReference(
                source_kind="knowledge_document",
                source_ref=project_id,
                title=title,
                summary=summary,
                document_ids=[doc["doc_id"] for doc in docs if doc.get("doc_id")],
            ),
            context,
        )

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

    def _load_latest_snapshot_payload(self, record: ProcurementDecisionRecord) -> dict[str, Any]:
        if not record.source_snapshots:
            return {}
        latest = record.source_snapshots[-1]
        payload = self._procurement_store.load_source_snapshot(
            tenant_id=record.tenant_id,
            project_id=record.project_id,
            snapshot_id=latest.snapshot_id,
        )
        return payload if isinstance(payload, dict) else {}

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

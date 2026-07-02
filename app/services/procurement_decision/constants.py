"""Shared constants, term dictionaries, and evaluation input dataclass.

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas import CapabilityProfileReference

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


@dataclass
class _EvaluationInputs:
    capability_profile: CapabilityProfileReference | None
    capability_text: str
    latest_snapshot_payload: dict[str, Any]
    parsed_rfp_fields: dict[str, Any]
    opportunity_text: str
    deadline_text: str
    budget_text: str

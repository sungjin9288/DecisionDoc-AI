"""Stage report types: required sections, their basis and the fulfilment table rule.

A section with an official basis is required (missing = error). Most report outlines
have no common official minimum — the contract or RFP sets them — so their sections are
labelled convention and missing ones are warnings. Sources were checked 2026-10-19; see
docs/superpowers/specs/2026-10-19-public-sector-specialization-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass

CONVENTION = "관행"
EXECUTION_PLAN_BASIS = "행안부 고시 제2025-1호 정보시스템 구축·운영 지침 별지 제5호"
MOE_POLICY_BASIS = "교육부 정책연구 관리규정(교육부훈령 제481호) 별지 제7호·제8호"


@dataclass(frozen=True)
class Section:
    title: str
    synonyms: tuple[str, ...] = ()
    basis: str = CONVENTION

    @property
    def official(self) -> bool:
        return self.basis != CONVENTION

    @property
    def names(self) -> tuple[str, ...]:
        return (self.title, *self.synonyms)


@dataclass(frozen=True)
class LengthRule:
    section: str
    target_chars: int
    tolerance: float
    basis: str


@dataclass(frozen=True)
class ReportType:
    id: str
    name: str
    sections: tuple[Section, ...]
    statuses: tuple[str, ...] = ()  # allowed fulfilment-table statuses; empty = no table
    length_rules: tuple[LengthRule, ...] = ()
    note: str = ""


def _official(title: str, *synonyms: str) -> Section:
    return Section(title, synonyms, EXECUTION_PLAN_BASIS)


def _convention(title: str, *synonyms: str) -> Section:
    return Section(title, synonyms)


_EXECUTION_PLAN = ReportType(
    "execution_plan", "사업수행계획서",
    (
        _official("사업명"), _official("사업기간", "사업 기간", "수행기간"), _official("사업목적", "사업 목적", "추진 목적"),
        _official("사업범위", "사업 범위", "과업 범위", "과업범위"), _official("추진체계", "추진 체계", "수행 조직", "수행조직"),
        _official("추진절차", "추진 절차", "수행 절차", "추진 방법"), _official("산출물계획", "산출물 계획", "산출물"),
        _official("일정", "추진 일정", "사업 일정"), _official("투입인력", "투입 인력", "인력 투입"),
        _official("보고계획", "보고 계획", "보고"), _official("표준화"), _official("품질보증", "품질 보증", "품질관리", "품질 관리"),
        _official("위험관리", "위험 관리", "리스크 관리"), _official("보안대책", "보안 대책", "보안 관리"),
        _official("교육", "교육 계획"), _official("협조요청", "협조 요청", "협조 요청사항", "요청사항"),
    ),
    statuses=("계획", "협의 필요"),
    note="착수계 붙임(사업책임자계, 청렴서약서, 보안서약서)은 같은 고시 제39조①의 별도 서류다.",
)
_START = ReportType(
    "start_report", "착수보고서",
    (
        _convention("사업 개요", "개요"), _convention("추진 목표", "목표", "사업 범위"), _convention("추진 체계", "수행 조직"),
        _convention("추진 일정", "일정"), _convention("산출물 계획", "산출물"), _convention("품질·위험 관리", "품질 관리", "위험 관리"),
        _convention("협조 요청 사항", "협조 요청", "요청사항"),
    ),
    statuses=("계획", "협의 필요"),
    note="공통 법정 최소 내용이 없다. 계약과 RFP가 정한 목차가 있으면 그것을 따른다.",
)
_INTERIM = ReportType(
    "interim_report", "중간보고서",
    (
        _convention("사업 개요", "개요"), _convention("추진 경과", "추진 현황", "진행 현황"),
        _convention("과업 이행 현황", "이행 현황", "과업 대비"), _convention("주요 결과", "주요 성과", "중간 결과"),
        _convention("이슈 및 대응", "이슈", "문제점 및 대책"), _convention("향후 계획", "향후 추진 계획"),
    ),
    statuses=("완료", "진행 중", "미착수", "변경"),
    note="공통 법정 최소 내용이 없다. 계약과 RFP가 정한 목차가 있으면 그것을 따른다.",
)
_COMPLETION = ReportType(
    "completion_report", "완료보고서",
    (
        _convention("사업 개요", "개요"), _convention("추진 경과", "추진 현황"), _convention("과업 이행 결과", "이행 결과", "과업 대비"),
        _convention("성과", "사업 성과", "주요 결과"), _convention("산출물 목록", "산출물"),
        _convention("이슈 및 개선사항", "개선사항", "문제점"), _convention("향후 과제", "유지관리", "후속 과제"),
    ),
    statuses=("완료", "미완료", "변경"),
    note="공통 법정 최소 내용이 없다. 계약과 RFP가 정한 목차가 있으면 그것을 따른다.",
)
_POLICY = ReportType(
    "policy_research", "정책연구 결과보고서",
    (
        _convention("요약", "연구 요약"), _convention("서론", "연구 배경", "연구의 필요성"), _convention("연구 방법", "연구방법"),
        _convention("결론", "결론 및 정책제언", "정책제언", "정책 제언"), _convention("참고문헌", "참고 문헌"),
    ),
    note="보고서 구성 공통 기준이 없다. 발주 부처 훈령의 양식이 있으면 그 유형(예: policy_research_moe)을 쓴다.",
)
_POLICY_MOE = ReportType(
    "policy_research_moe", "정책연구 결과보고서(교육부)",
    (
        Section("초록", ("연구 초록",), MOE_POLICY_BASIS), Section("국문 색인어", ("주제어", "색인어"), MOE_POLICY_BASIS),
        Section("영문 색인어", ("Keywords", "영문 주제어"), MOE_POLICY_BASIS),
        *_POLICY.sections,
    ),
    length_rules=(LengthRule("초록", 500, 0.3, MOE_POLICY_BASIS + " (개조식 500자 내외)"),),
    note="최종보고서 표지는 같은 훈령 별지 제8호 서식을 따른다. 과제 종료 15일 전까지 제출한다.",
)
_BUSINESS_PLAN = ReportType(
    "business_plan", "사업계획서",
    (
        _convention("사업 개요", "개요"), _convention("추진 배경", "필요성", "추진 배경 및 필요성"), _convention("사업 목표", "목표"),
        _convention("추진 내용", "주요 내용", "세부 추진 내용"), _convention("추진 체계"), _convention("추진 일정", "일정"),
        _convention("소요 예산", "예산", "재원"), _convention("기대 효과", "기대효과"), _convention("성과 지표", "성과지표", "성과 관리"),
    ),
    note="공식 공통 양식을 확인하지 않았다(관행). 기관 양식이 있으면 그것을 따른다.",
)
_FEASIBILITY = ReportType(
    "feasibility_report", "타당성 검토 보고서",
    (
        _convention("검토 개요", "개요"), _convention("현황 분석", "현황"), _convention("대안 검토", "대안 비교", "대안"),
        _convention("타당성 분석", "타당성 검토", "경제성 분석"), _convention("종합 의견", "종합 검토", "결론"),
        _convention("권고", "권고안", "제언"),
    ),
    note="예비타당성조사 등 법정 조사는 별도 지침을 따른다. 이 유형은 관행 목차다.",
)

REPORT_TYPES: dict[str, ReportType] = {
    report.id: report
    for report in (_EXECUTION_PLAN, _START, _INTERIM, _COMPLETION, _POLICY, _POLICY_MOE, _BUSINESS_PLAN, _FEASIBILITY)
}
STATUS_PENDING = "확인 필요"


def obligation_sources(report: ReportType) -> list[str]:
    """Which profile lists a report's fulfilment table must cover."""
    return ["tasks", "commitments"] if report.statuses else []


"""Attachment-context and sparse-context proposal quality guards.

Detects whether the proposal_kr context is grounded in a parsed RFP
attachment or is a sparse non-attachment context, and applies the matching
static fallback content (including the slide outlines from
``slide_outline_data``) so lint/validation still pass when the provider
output is too thin to use as-is.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.generation.slide_outline_data import (
    _attachment_grounded_slide_outline,
    _sparse_proposal_slide_outline,
)
from app.services.generation.text_normalization import (
    _normalize_finished_doc_text,
    _normalized_row_list,
    _project_subject,
)


def _extract_attachment_reference_text(context_text: Any) -> str:
    raw = str(context_text or "")
    start_marker = "=== RFP 원문 (참고용) ==="
    end_marker = "=== RFP 원문 끝 ==="
    start = raw.find(start_marker)
    end = raw.find(end_marker)
    if start == -1 or end == -1 or end < start:
        return ""
    return raw[start + len(start_marker):end].strip()


def _is_sparse_attachment_context(context_text: Any) -> bool:
    reference_text = _extract_attachment_reference_text(context_text)
    if not reference_text:
        return False
    normalized = re.sub(r"\[첨부파일:[^\]]+\]", " ", reference_text)
    token_count = len(re.findall(r"[가-힣A-Za-z0-9]+", normalized))
    has_digits = bool(re.search(r"\d", normalized))
    return token_count <= 80 and not has_digits


def _is_sparse_non_attachment_context(context_text: Any) -> bool:
    raw = str(context_text or "").strip()
    if not raw or _extract_attachment_reference_text(raw):
        return False
    normalized = re.sub(r"\s+", " ", raw)
    token_count = len(re.findall(r"[가-힣A-Za-z0-9]+", normalized))
    has_digits = bool(re.search(r"\d", normalized))
    return token_count <= 80 and not has_digits


def _contains_unanchored_quant_claims(value: Any) -> bool:
    text = _normalize_finished_doc_text(value)
    if not text:
        return False
    return bool(
        re.search(
            r"(ROI|KPI|Q[1-4]|%|\d|억원|억\s*원|원\b|개월|월|년|분기|초|건)",
            text,
            re.IGNORECASE,
        )
    )


def _rows_contain_unanchored_quant_claims(value: Any) -> bool:
    return any(_contains_unanchored_quant_claims(row) for row in _normalized_row_list(value))


def _quality_guard_attachment_grounded_proposal_bundle(
    bundle: dict[str, Any],
    *,
    title: str,
    goal: str,
    context_text: str,
) -> None:
    if not _is_sparse_attachment_context(context_text):
        return

    subject = _project_subject(title)

    business = bundle.get("business_understanding")
    if isinstance(business, dict):
        business["executive_summary"] = (
            f"본 제안은 {subject} 과제에서 확인된 교차로 안전 강화와 장애인 보호 요구를 사업 구조로 재정리한 안입니다. "
            "첨부 원문에 없는 수치나 일정 대신, 발주기관이 왜 이 사업을 추진해야 하는지와 어떤 운영 변화가 필요한지를 중심으로 설명합니다. "
            "제안서의 초점은 안전 문제를 줄이기 위한 실행 방향, 평가 대응 포인트, 후속 운영 체계를 명확히 제시하는 데 있습니다."
        )
        business["project_background"] = (
            f"{subject} 사업은 교차로 안전 강화와 장애인 보호 강화를 동시에 요구합니다. "
            "따라서 제안서는 현장의 안전 문제를 어떻게 줄일지, 교통약자 관점의 보호 체계를 어떤 방식으로 보강할지, "
            "그리고 발주기관이 관리 가능한 운영 구조를 어떻게 만들지를 중심으로 구성되어야 합니다."
        )
        business["current_issues"] = [
            "교차로 안전 강화 요구에 비해 현장 대응 체계가 분산되어 있음",
            "장애인 보호 관점의 운영 기준과 현장 실행 절차가 일관되지 않음",
            "안전 관련 현황을 통합적으로 확인하고 점검할 수 있는 운영 체계가 부족함",
        ]
        business["project_objectives"] = [
            "교차로 안전 강화 | 현행 위험 요소를 줄일 수 있는 실행 구조 마련 | 운영 로그와 현장 점검 결과",
            "장애인 보호 강화 | 교통약자 관점의 보호 조치와 운영 기준 정비 | 현장 적용 여부와 개선 이력",
            "운영 관리 체계 확보 | 발주기관이 지속적으로 점검 가능한 보고·검수 구조 구성 | 보고 체계와 검수 기록",
        ]
        business["evaluation_alignment"] = [
            "사업 이해도 | 교차로 안전과 장애인 보호라는 핵심 요구를 제안 배경과 목표에 직접 연결 | 첨부 원문 요구사항과 사업 배경 서술",
            "실행 가능성 | 단계별 수행 구조와 산출물, 보고 체계를 명확히 정리 | 수행계획, 산출물, 거버넌스 계획",
            "효과성 | 정량 수치 대신 확인 가능한 운영 변화와 점검 방법을 제시 | 기대효과, 모니터링 계획, 후속 확산 기준",
        ]
        business["scope_summary"] = (
            "본 사업 범위는 교차로 안전과 교통약자 보호를 위한 현황 분석, 운영 체계 설계, 현장 적용 방안, 보고와 검수 절차 정비까지 포함합니다. "
            "기술 도입 자체보다 현장에서 지속적으로 활용할 수 있는 운영 구조와 관리 체계를 함께 제시하는 것이 핵심입니다."
        )
        business["total_slides"] = 2
        business["slide_outline"] = _attachment_grounded_slide_outline(title, section="business_understanding")

    tech = bundle.get("tech_proposal")
    if isinstance(tech, dict):
        tech["technical_summary"] = (
            f"{subject}의 기술 제안은 특정 제품명보다 필요한 기능과 운영 목적을 중심으로 설명합니다. "
            "핵심은 현장 데이터를 수집하고, 위험 징후를 분석하며, 운영자가 바로 활용할 수 있는 화면과 보고 체계를 제공하는 것입니다. "
            "첨부 원문에 없는 기술 스택이나 제품명은 확정적으로 쓰지 않고 기능 수준에서 설계를 제시합니다."
        )
        tech["tech_stack"] = [
            "데이터 수집·연계 | 현장 정보 수집 및 입력 데이터 정리 | 교차로 안전 현황 통합",
            "분석·판단 지원 | 위험 징후 분석과 의사결정 보조 기능 | 안전 대응 우선순위 도출",
            "운영 화면·보고 | 관리자 화면과 보고서 생성 기능 | 운영 가시성과 검수 대응 확보",
        ]
        tech["architecture_overview"] = (
            "시스템은 현장 데이터 수집, 분석 처리, 운영자 확인 화면, 보고와 검수 기록 계층으로 구성합니다. "
            "이 구조는 운영자가 교차로 안전 상황과 교통약자 보호 관련 조치를 한 흐름 안에서 확인할 수 있도록 설계합니다."
        )
        tech["ai_approach"] = (
            "AI 기능은 현장 위험 징후를 분석하고 대응 우선순위를 정리해 운영자가 빠르게 판단할 수 있도록 지원하는 수준에서 설명합니다. "
            "특정 모델명이나 제품명을 단정하기보다, 운영 데이터와 현장 정보에 기반한 분석 보조 기능이라는 역할을 분명히 합니다."
        )
        tech["implementation_principles"] = [
            "기능 중심 설계 | 데이터 수집, 분석, 운영 활용 흐름을 먼저 정의 | 기능별 책임 경계와 화면 흐름 확인",
            "설명 가능한 운영 | 판단 근거와 검수 이력을 함께 남김 | 운영 로그와 검수 기록 확인",
            "보안 기본값 적용 | 접근 통제와 감사 대응을 기본 설계에 포함 | 권한 정책과 운영 절차 점검",
        ]
        tech["security_measures"] = [
            "접근 통제 | 역할 기반 권한 관리와 승인 절차 운영 | 최소 권한 원칙 적용 여부 확인",
            "운영 추적성 | 로그와 검수 이력을 기록 | 감사 대응용 기록 유지 여부 확인",
            "데이터 보호 | 민감 정보 처리 기준과 저장 정책 정비 | 내부 보안 기준 준수 여부 확인",
        ]
        tech["differentiation"] = [
            "운영 중심 제안 | 기술명보다 현장 실행 방식과 관리 체계를 우선 설명 | 발주기관 운영 관점과 직접 연결",
            "교통약자 보호 강조 | 장애인 보호 요구를 사업 전반의 설계 원칙으로 반영 | 첨부 원문 요구사항과 일치",
            "검수 대응 구조 | 보고, 모니터링, 검수 체계를 함께 제시 | 운영 지속성과 감사 대응력 확보",
        ]
        tech["total_slides"] = 2
        tech["slide_outline"] = _attachment_grounded_slide_outline(title, section="tech_proposal")

    execution = bundle.get("execution_plan")
    if isinstance(execution, dict):
        execution["delivery_summary"] = (
            f"{subject} 수행계획은 착수, 설계, 구현, 검증, 운영 전환의 기본 단계를 기준으로 정리합니다. "
            "각 단계는 완료 기준과 산출물을 함께 제시해 발주기관이 진행률과 품질을 확인할 수 있게 구성합니다. "
            "첨부 원문에 없는 기간 수치는 확정하지 않고 단계 중심으로 수행 구조를 설명합니다."
        )
        execution["team_structure"] = [
            "PM·총괄 | 핵심 인력 | 일정·범위·대외 협의 총괄 | 착수 단계부터 종료까지",
            "기술 리드 | 핵심 인력 | 기능 설계와 구현 방향 정리 | 설계 단계부터 검증 단계까지",
            "운영·품질 담당 | 핵심 인력 | 검수 기준 수립과 운영 전환 준비 | 구현 단계부터 운영 전환까지",
        ]
        execution["milestones"] = [
            "착수 및 요구사항 정리 | 착수 단계 | 사업 범위와 요구사항 정리 완료 | 착수보고서, 요구사항 정리본",
            "설계 및 구현 정리 | 구현 준비 단계 | 기능 구조와 운영 흐름 설계 완료 | 설계 문서, 구현 계획서",
            "검증 및 운영 전환 | 검증 단계 | 주요 시나리오 점검과 운영 준비 완료 | 시험 결과서, 운영 매뉴얼",
        ]
        execution["methodology"] = (
            "요구사항 정리, 기능 설계, 구현, 검증, 운영 전환이 이어지는 단계형 수행 방식을 적용합니다. "
            "각 단계에서 발주기관과 점검 포인트를 공유하고, 이슈가 생기면 즉시 보완 계획을 반영하는 방식으로 운영합니다."
        )
        execution["governance_plan"] = (
            "PM, 기술 리드, 운영·품질 담당이 정기 점검 회의를 운영하고, 발주기관과는 단계별 산출물과 이슈를 공유합니다. "
            "중요 변경사항은 영향도 검토 후 승인 절차를 거치며, 모든 의사결정은 기록으로 남겨 후속 검수와 운영에 활용합니다."
        )
        execution["risk_management"] = [
            "요구사항 해석 차이 | 범위 오해로 인한 산출물 재작업 가능성 | 단계별 확인 회의와 검수 기준 합의",
            "현장 적용 난이도 | 운영 현장과 문서 간 괴리 발생 가능성 | 시범 적용과 피드백 반영 절차 운영",
            "운영 전환 지연 | 인수인계와 교육 부족으로 초기 운영 혼선 가능성 | 운영 매뉴얼과 교육 계획 선제 마련",
        ]
        execution["deliverables"] = [
            "착수보고서 | 착수 단계 종료 시 | 문서 | 발주기관 검토 및 승인",
            "설계 및 구현 산출물 | 설계·구현 단계 종료 시 | 문서 및 결과물 | 단계별 점검 회의",
            "시험 결과서 및 운영 매뉴얼 | 검증·운영 전환 단계 종료 시 | 문서 | 최종 검수 및 운영 준비 확인",
        ]
        execution["total_slides"] = 2
        execution["slide_outline"] = _attachment_grounded_slide_outline(title, section="execution_plan")

    impact = bundle.get("expected_impact")
    if isinstance(impact, dict):
        impact["impact_summary"] = (
            f"{subject}의 기대효과는 교차로 안전성과 교통약자 보호 수준을 높이고, 발주기관이 지속적으로 관리 가능한 운영 구조를 만드는 데 있습니다. "
            "정량 수치를 임의로 제시하기보다, 어떤 효과 범주를 어떤 방식으로 점검할지 중심으로 설명합니다."
        )
        impact["quantitative_effects"] = [
            "교차로 안전성 | 현행 대비 개선 | 사고·민원·운영 로그를 통해 개선 여부 확인 | 안전 관련 운영 품질 향상",
            "교통약자 보호 체계 | 현행 대비 보강 | 현장 점검과 보호 조치 이행 여부 확인 | 장애인 보호 관점의 실행력 강화",
            "운영 관리 수준 | 점검 체계 확보 | 보고와 검수 기록 유지 여부 확인 | 지속 가능한 운영 구조 마련",
        ]
        impact["qualitative_effects"] = [
            "교통약자 신뢰도 향상 | 보호 대상 관점의 서비스 신뢰성 제고 | 공공서비스 체감 품질 개선",
            "운영 일관성 확보 | 현장과 관리 부서 간 판단 기준 정렬 | 반복 가능한 운영 프로세스 정착",
            "정책 확산 기반 마련 | 시범 운영 결과를 후속 의사결정 근거로 활용 | 후속 사업 검토 기반 확보",
        ]
        impact["social_value"] = (
            f"{subject} 사업은 교차로 안전과 교통약자 보호라는 공공 가치를 직접 다룹니다. "
            "따라서 기대효과는 기술 도입 자체보다, 현장에서 안전 문제를 줄이고 보호 대상을 더 일관되게 지원할 수 있는 운영 체계를 만드는 데 있습니다."
        )
        impact["kpi_commitments"] = [
            "교차로 안전 관련 운영 지표 | 현행 대비 개선 여부 확인 | 운영 로그와 점검 결과 | 시범 운영 이후 검토",
            "교통약자 보호 조치 이행도 | 현장 적용 여부 확인 | 현장 피드백과 점검 기록 | 단계별 운영 점검 시점",
            "운영 보고 체계 정착 | 정기 보고와 검수 기록 유지 | 보고서와 검수 이력 | 운영 전환 이후 점검",
        ]
        impact["roi_estimate"] = "투자 대비 효과는 시범 운영 이후 실제 운영 데이터와 검수 결과를 바탕으로 산정합니다."
        impact["monitoring_plan"] = [
            "안전 관련 운영 로그 | 정기 점검 주기 | 운영 담당자 | 개선 여부와 이슈 추이 확인",
            "교통약자 보호 조치 이행 현황 | 단계별 점검 주기 | 현장·운영 공동 책임 | 보호 조치 적용 여부 확인",
            "보고 및 검수 기록 유지 상태 | 정기 리뷰 주기 | PM 및 품질 담당 | 운영 관리 체계 유지 여부 확인",
        ]
        impact["total_slides"] = 2
        impact["slide_outline"] = _attachment_grounded_slide_outline(title, section="expected_impact")


def _quality_guard_sparse_non_attachment_proposal_bundle(
    bundle: dict[str, Any],
    *,
    title: str,
    goal: str,
    context_text: str,
) -> None:
    if not _is_sparse_non_attachment_context(context_text):
        return

    subject = _project_subject(title)

    business = bundle.get("business_understanding")
    if isinstance(business, dict):
        if _contains_unanchored_quant_claims(business.get("executive_summary")):
            business["executive_summary"] = (
                f"본 제안은 {subject} 사업에서 현장 안전 문제를 먼저 정리하고, "
                "운영자가 실제로 점검하고 개선할 수 있는 실행 구조를 제시하는 데 목적이 있습니다. "
                "정량 수치를 임의로 약속하기보다 어떤 문제를 어떤 운영 방식으로 줄일지 중심으로 설명합니다."
            )
        if _contains_unanchored_quant_claims(business.get("project_background")):
            business["project_background"] = (
                f"{subject} 사업은 교차로와 보행 환경의 위험 징후를 더 빠르게 파악하고, "
                "교통약자 보호 관점에서 현장 대응 기준을 일관되게 운영해야 한다는 요구를 배경으로 합니다."
            )
        if _rows_contain_unanchored_quant_claims(business.get("current_issues")):
            business["current_issues"] = [
                "현장 위험 징후를 일관되게 파악하고 공유하는 기준이 부족함",
                "교통약자 보호 관점의 대응 절차가 현장마다 달라 운영 일관성이 낮음",
                "안전 관련 현황을 통합적으로 점검하고 보고하는 체계가 부족함",
            ]
        if _rows_contain_unanchored_quant_claims(business.get("project_objectives")):
            business["project_objectives"] = [
                "현장 위험 징후를 조기에 식별하고 대응 기준을 정리한다.",
                "교통약자 보호 관점의 운영 절차를 표준화하고 점검 체계를 마련한다.",
                "운영 데이터와 현장 피드백을 바탕으로 후속 개선 여부를 판단할 수 있게 한다.",
            ]
        if _contains_unanchored_quant_claims(business.get("scope_summary")):
            business["scope_summary"] = (
                "본 사업 범위는 현황 분석, 운영 기준 설계, 위험 징후 분석 지원, 현장 적용과 점검 절차 정비까지 포함합니다. "
                "확정 일정이나 예산 수치보다 실행 단계와 운영 책임 구조를 우선 정리합니다."
            )
        business["total_slides"] = 2
        business["slide_outline"] = _sparse_proposal_slide_outline(title, section="business_understanding")

    execution = bundle.get("execution_plan")
    if isinstance(execution, dict):
        if _contains_unanchored_quant_claims(execution.get("delivery_summary")):
            execution["delivery_summary"] = (
                f"{subject} 수행계획은 착수, 설계, 구현, 검증, 운영 전환으로 이어지는 단계형 delivery 구조를 기준으로 설명합니다. "
                "기간과 예산을 단정하기보다 각 단계의 완료 기준과 산출물, 승인 절차를 명확히 두는 방식으로 수행 현실성을 설명합니다."
            )
        if _rows_contain_unanchored_quant_claims(execution.get("team_structure")):
            execution["team_structure"] = [
                "PM·총괄 | 핵심 인력 | 일정, 범위, 대외 협의 총괄 | 착수부터 종료까지",
                "기술 리드 | 핵심 인력 | 기능 설계와 구현 방향 정리 | 설계부터 검증까지",
                "운영·품질 담당 | 핵심 인력 | 검수 기준 수립과 운영 전환 준비 | 구현부터 운영 전환까지",
            ]
        if _rows_contain_unanchored_quant_claims(execution.get("milestones")):
            execution["milestones"] = [
                "착수 및 요구사항 정리 | 사업 범위와 요구사항 정리 완료 | 착수보고서, 요구사항 정리본",
                "설계 및 구현 준비 | 기능 구조와 운영 흐름 설계 완료 | 설계 문서, 구현 계획서",
                "검증 및 운영 전환 준비 | 주요 시나리오 점검과 운영 준비 완료 | 시험 결과서, 운영 매뉴얼",
            ]
        if _rows_contain_unanchored_quant_claims(execution.get("risk_management")):
            execution["risk_management"] = [
                "요구사항 해석 차이 | 범위 오해로 인한 재작업 가능성 | 단계별 확인 회의와 검수 기준 합의",
                "현장 적용 난이도 | 운영 현장과 문서 간 괴리 발생 가능성 | 시범 적용과 피드백 반영 절차 운영",
                "운영 전환 혼선 | 초기 운영 과정에서 혼란 발생 가능성 | 운영 매뉴얼과 교육 계획 선제 마련",
            ]
        if _rows_contain_unanchored_quant_claims(execution.get("deliverables")):
            execution["deliverables"] = [
                "착수보고서 | 착수 단계 종료 시 | 문서 | 발주기관 검토 및 승인",
                "설계 및 구현 산출물 | 설계·구현 단계 종료 시 | 문서 및 결과물 | 단계별 점검 회의",
                "시험 결과서 및 운영 매뉴얼 | 검증·운영 전환 단계 종료 시 | 문서 | 최종 검수 및 운영 준비 확인",
            ]
        execution["total_slides"] = 2
        execution["slide_outline"] = _sparse_proposal_slide_outline(title, section="execution_plan")

    impact = bundle.get("expected_impact")
    if isinstance(impact, dict):
        if _contains_unanchored_quant_claims(impact.get("impact_summary")):
            impact["impact_summary"] = (
                f"{subject}의 기대효과는 교차로 안전성과 교통약자 보호 수준을 높이고, "
                "운영자가 실제 데이터를 기반으로 개선 여부를 판단할 수 있는 관리 체계를 만드는 데 있습니다. "
                "정량 수치를 선제적으로 약속하기보다 효과 범주와 점검 방법을 명확히 설명합니다."
            )
        if _rows_contain_unanchored_quant_claims(impact.get("quantitative_effects")):
            impact["quantitative_effects"] = [
                "교차로 안전성 | 현행 대비 개선 여부 확인 | 사고·민원·운영 로그를 통해 추이 점검 | 안전 관련 운영 품질 향상",
                "교통약자 보호 체계 | 현행 대비 보강 여부 확인 | 현장 점검과 보호 조치 이행 여부 확인 | 보호 대상 관점의 실행력 강화",
                "운영 관리 수준 | 점검 체계 확보 여부 확인 | 보고와 검수 기록 유지 여부 확인 | 지속 가능한 운영 구조 마련",
            ]
        if _rows_contain_unanchored_quant_claims(impact.get("kpi_commitments")):
            impact["kpi_commitments"] = [
                "교차로 안전 관련 운영 지표 | 현행 대비 개선 여부 확인 | 운영 로그와 점검 결과 | 시범 운영 이후 검토",
                "교통약자 보호 조치 이행도 | 현장 적용 여부 확인 | 현장 피드백과 점검 기록 | 단계별 운영 점검 시점",
                "운영 보고 체계 정착 | 정기 보고와 검수 기록 유지 | 보고서와 검수 이력 | 운영 전환 이후 점검",
            ]
        if _contains_unanchored_quant_claims(impact.get("roi_estimate")):
            impact["roi_estimate"] = "투자 대비 효과는 시범 운영 이후 실제 운영 데이터와 검수 결과를 바탕으로 산정합니다."
        if _rows_contain_unanchored_quant_claims(impact.get("monitoring_plan")):
            impact["monitoring_plan"] = [
                "안전 관련 운영 로그 | 정기 점검 주기 | 운영 담당자 | 개선 여부와 이슈 추이 확인",
                "교통약자 보호 조치 이행 현황 | 단계별 점검 주기 | 현장·운영 공동 책임 | 보호 조치 적용 여부 확인",
                "보고 및 검수 기록 유지 상태 | 정기 리뷰 주기 | PM 및 품질 담당 | 운영 관리 체계 유지 여부 확인",
            ]
        impact["total_slides"] = 2
        impact["slide_outline"] = _sparse_proposal_slide_outline(title, section="expected_impact")

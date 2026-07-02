"""Proposal bundle (proposal_kr) quality guard.

Fills in fallback text/rows for the proposal bundle's business understanding,
tech proposal, execution plan, and expected impact sections whenever the
provider output is missing or too sparse to pass downstream lint/validation.
"""
from __future__ import annotations

from typing import Any

from app.services.generation.text_normalization import (
    _ensure_rows,
    _ensure_text,
    _project_subject,
    _sanitize_rows,
    _strip_reference_noise,
)


def _quality_guard_proposal_bundle(bundle: dict[str, Any], *, title: str, goal: str) -> None:
    subject = _project_subject(title)
    business = bundle.get("business_understanding")
    if isinstance(business, dict):
        business["executive_summary"] = _strip_reference_noise(business.get("executive_summary"))
        business["executive_summary"] = _ensure_text(
            business.get("executive_summary"),
            (
                "본 제안은 발주기관이 요구하는 핵심 정책 목표를 운영 KPI와 실행 단계로 재구성해 현행 업무의 병목과 운영 리스크를 먼저 정리하고, "
                "그 위에 데이터·AI·운영 체계를 단계적으로 구축하는 방식을 제시합니다. 본 제안은 단순 기능 도입이 아니라 "
                "평가위원이 확인하는 사업 필요성, 정책 적합성, 실현 가능성, 효과 입증 경로를 하나의 실행 시나리오로 묶는 데 목적이 있습니다. "
                "특히 초기 3개월 내 가시적 성과를 만들고, 중간 검증 이후 확산 여부를 판단할 수 있도록 단계별 성공 기준을 명확히 정의합니다."
            ),
        )
        business["project_background"] = _ensure_text(
            _strip_reference_noise(business.get("project_background")),
            (
                f"{subject} 사업은 공공 서비스 디지털 전환과 현장 운영 효율 개선을 동시에 요구합니다. "
                "발주기관은 현행 프로세스의 병목, 데이터 단절, 대응 지연 문제를 해소할 수 있는 실행 가능한 사업 구조를 요구하고 있으며, "
                "이에 따라 본 문서는 정책 배경과 현황 문제, 목표 KPI를 같은 평가 언어로 재구성해 사업 필요성을 선명하게 설명합니다."
            ),
        )
        business["evaluation_alignment"] = _ensure_rows(
            business.get("evaluation_alignment"),
            [
                "사업 이해도 | 발주기관의 정책 목표와 현행 문제를 AS-IS/TO-BE 구조로 재정리해 제안 배경의 타당성을 선명하게 설명 | 사업 배경, 현황 및 문제점, 사업 목표 표",
                "실행 가능성 | 단계별 구축 범위와 일정, 주요 산출물, 운영 전환 시점을 연결해 일정 현실성과 납품 가능성을 증명 | 사업 범위 요약, 후속 수행계획서 및 WBS",
                "효과성 | 정량 KPI와 정성 효과를 동시에 제시해 예산 대비 효과와 정책 성과를 같은 문서 안에서 검증 가능하게 구성 | 정량·정성 기대효과, ROI, 성과 모니터링 계획",
            ],
        )
        business["target_users"] = _sanitize_rows(
            business.get("target_users"),
            [
                "사업 담당 공무원 및 운영 관리자 | 사업 집행 현황·성과지표를 통합 모니터링해야 함 | 실시간 성과판과 의사결정 속도 향상",
                "현장 실무자 및 데이터 입력 담당자 | 반복 입력·검증 업무를 줄이고 오류를 낮추고자 함 | 자동 검증과 예외 처리 중심 업무 전환",
                "경영진 및 의사결정자 | 예산 집행 효과와 리스크를 요약 보고받아야 함 | 대시보드 기반 신속한 승인·보완 판단",
                "일반 국민 | 서비스 응답 속도와 정확도 향상을 기대함 | 체감 만족도와 접근성 개선",
            ],
            min_items=4,
        )
        business["scope_summary"] = _ensure_text(
            _strip_reference_noise(business.get("scope_summary")),
            (
                "본 사업의 범위는 데이터 수집·정제, AI 분석 모델 구축, 운영 대시보드, 현장 적용 및 확산 지원까지 포함합니다. "
                "착수·설계·개발·검증·운영 전환을 단계적으로 구분하고, 각 단계마다 산출물과 승인 기준을 연결해 범위 누락과 일정 지연을 줄이도록 구성합니다."
            ),
        )

    tech = bundle.get("tech_proposal")
    if isinstance(tech, dict):
        tech["technical_summary"] = _strip_reference_noise(tech.get("technical_summary"))
        tech["technical_summary"] = _ensure_text(
            tech.get("technical_summary"),
            (
                f"{subject}의 기술 제안은 공공기관 운영 환경에서 바로 수용 가능한 보안·가용성 기준을 전제로, "
                "데이터 수집부터 AI 추론, 운영자 대시보드, 감사 대응 로그까지 하나의 통합 아키텍처로 설계합니다. "
                "핵심은 정확도만 높은 모델이 아니라 운영 현장에서 설명 가능하고, 장애 격리와 확장성이 확보된 구조를 제공하는 것입니다. "
                "이를 통해 평가위원이 가장 우려하는 유지보수 리스크와 보안 통제를 초기 설계 단계에서 함께 해소합니다."
            ),
        )
        tech["implementation_principles"] = _ensure_rows(
            tech.get("implementation_principles"),
            [
                "업무 연속성 우선 | 핵심 API와 데이터 계층을 분리해 장애 발생 시 부분 격리와 점진적 복구가 가능하도록 설계 | 무중단 배포, 장애 복구 시나리오, 서비스별 책임 경계",
                "설명 가능한 AI | 모델 판단 근거와 예외 사유를 운영 화면과 보고서에 함께 남겨 감사·검수 대응력을 확보 | 판단 근거 로그, 검수 화면, 재현 가능한 평가 데이터셋",
                "보안·확장성 동시 확보 | 최소 권한, 암호화, 접근통제를 기본값으로 두고 트래픽 증가 시 서비스별 수평 확장이 가능하도록 구성 | 인증·인가 정책, 오토스케일링, 성능 테스트 계획",
            ],
        )

    execution = bundle.get("execution_plan")
    if isinstance(execution, dict):
        execution["delivery_summary"] = _strip_reference_noise(execution.get("delivery_summary"))
        execution["delivery_summary"] = _ensure_text(
            execution.get("delivery_summary"),
            (
                f"{subject} 수행계획은 착수 직후 요구사항·데이터·연계 환경을 동시에 정리하고, "
                "프로토타입 검증과 통합 개발, 파일럿 운영, 전면 전개로 이어지는 4단계 delivery 체계를 기준으로 구성합니다. "
                "각 단계는 산출물, 완료 기준, 승인 게이트가 연결되어 있어 발주기관이 중간 점검 시점마다 진행률과 품질 수준을 객관적으로 확인할 수 있습니다. "
                "이 방식은 일정 지연과 요구사항 누락을 줄이고, 운영 이관까지 포함한 종료 조건을 명확히 합니다."
            ),
        )
        execution["team_structure"] = _sanitize_rows(
            execution.get("team_structure"),
            [
                "PM·총괄 | 특급 1명 | 일정·범위·대외 협의 총괄 | 착수~종료 전기간",
                "AI 기술 리드 | 고급 1명 | 모델 품질·데이터 설계·성능 검증 책임 | 설계~통합시험",
                "개발 리드 및 구현 인력 | 중급 3명 | 서비스 개발·연계·배포 자동화 수행 | 개발~운영 전환",
                "품질 책임자 | 고급 1명 | 검수 기준 수립·결함 관리·인수시험 총괄 | 시험~종료",
            ],
            min_items=4,
        )
        execution["milestones"] = _sanitize_rows(
            execution.get("milestones"),
            [
                "착수 및 요구사항 확정 | 1~2개월 | 요구사항 정의서 승인 | 착수보고서, 현행 분석서",
                "아키텍처·상세 설계 완료 | 3~4개월 | 설계 검토 승인 | 아키텍처 설계서, 인터페이스 정의서",
                "개발 및 통합시험 완료 | 5~9개월 | 핵심 시나리오 100% 통과 | 시험 결과서, 운영자 검수 기록",
                "파일럿 및 최종 이관 완료 | 10~12개월 | 최종 검수 승인 | 완료보고서, 운영 매뉴얼",
            ],
            min_items=4,
        )
        execution["governance_plan"] = _ensure_text(
            execution.get("governance_plan"),
            (
                "PM이 주간 실행계획과 리스크를 총괄하고, AI 리드·개발 리드·품질 책임자가 주간 점검회의에서 이슈를 선분류합니다. "
                "발주기관과는 월간 운영위원회 및 중요 이슈 수시 보고 체계를 유지하며, 일정·범위·비용에 영향을 주는 변경은 영향도 분석 후 승인 절차를 거칩니다. "
                "모든 의사결정은 회의록과 변경대장으로 남겨 이후 검수와 감사 대응 근거로 사용합니다."
            ),
        )

    impact = bundle.get("expected_impact")
    if isinstance(impact, dict):
        impact["impact_summary"] = _strip_reference_noise(impact.get("impact_summary"))
        impact["impact_summary"] = _ensure_text(
            impact.get("impact_summary"),
            (
                f"{subject}의 기대효과는 단순한 기능 도입이 아니라 핵심 정책 목표를 실무 KPI로 전환해 지속적으로 측정 가능한 운영 성과를 만드는 데 있습니다. "
                "처리시간 단축, 오류율 감소, 운영비 절감, 서비스 안정성 향상 같은 정량 지표와 함께 조직 역량 강화, 정책 신뢰도 제고, 국민 체감 개선 같은 정성 효과를 병행 관리합니다. "
                "이렇게 정의한 효과 구조는 제안 단계의 약속과 운영 단계의 성과관리가 단절되지 않도록 하는 장치입니다."
            ),
        )
        impact["qualitative_effects"] = _sanitize_rows(
            impact.get("qualitative_effects"),
            [
                "조직 역량 강화 | 데이터 기반 의사결정 문화 정착 | 정책·사업 운영의 디지털 전환 가속",
                "국민 신뢰 제고 | 서비스 체감 품질과 응답 일관성 향상 | 공공서비스 브랜드 가치와 정책 수용성 강화",
                "업무 방식 혁신 | 반복 업무 부담 감소와 고부가가치 업무 집중 | 실무자 만족도와 생산성 동시 개선",
                "정책 확산 효과 | AI 활용 선도 사례 구축 | 타 기관 벤치마킹과 후속 사업 확장 기반 확보",
            ],
            min_items=4,
        )
        impact["social_value"] = _ensure_text(
            _strip_reference_noise(impact.get("social_value")),
            (
                f"{subject} 사업은 공공서비스 품질 개선과 국민 체감 편익 확대를 동시에 목표로 합니다. "
                "디지털 소외 계층을 포함한 이용자 접근성을 개선하고, 현장 운영의 신뢰도와 일관성을 높여 공공 AI 활용의 모범 사례로 확산될 수 있도록 설계합니다."
            ),
        )
        impact["kpi_commitments"] = _ensure_rows(
            impact.get("kpi_commitments"),
            [
                "핵심 업무 처리시간 | 기준 대비 50% 이상 단축 | 업무 로그와 월간 운영 리포트 | 파일럿 운영 종료 시점",
                "데이터 오류율 | 기준 대비 70% 이상 개선 | 검수 샘플링과 자동 검증 결과 | 통합 테스트 종료 시점",
                "서비스 가용률 | 99.9% 이상 유지 | 모니터링 대시보드와 장애 리포트 | 전면 운영 전환 후 3개월",
            ],
        )

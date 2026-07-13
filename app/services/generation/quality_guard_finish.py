"""Performance-plan quality guard and the top-level quality-guard dispatcher.

``_apply_finished_doc_quality_guard`` is the single entry point called from
``GenerationService._call_and_prepare_bundle``: it dispatches to the
proposal_kr and performance_plan_kr guards, then runs a final text
normalization pass over the whole bundle.
"""
from __future__ import annotations

from typing import Any

from app.services.generation.quality_guard_attachment import (
    _quality_guard_attachment_grounded_proposal_bundle,
    _quality_guard_sparse_non_attachment_proposal_bundle,
)
from app.services.generation.quality_guard_proposal import _quality_guard_proposal_bundle
from app.services.generation.text_normalization import (
    _ensure_rows,
    _ensure_text,
    _normalize_finished_doc_value,
    _project_subject,
    _sanitize_rows,
    _strip_reference_noise,
)


def _quality_guard_performance_bundle(bundle: dict[str, Any], *, title: str, goal: str) -> None:
    subject = _project_subject(title)
    overview = bundle.get("performance_overview")
    if isinstance(overview, dict):
        overview["executive_summary"] = _strip_reference_noise(overview.get("executive_summary"))
        overview["executive_summary"] = _ensure_text(
            overview.get("executive_summary"),
            (
                f"{subject} 수행계획서는 계약 기간 내 필요한 범위, 일정, 산출물, 투입 인력, 승인 게이트를 발주처 기준으로 재정렬한 실행 문서입니다. "
                "착수 이후 요구사항 정의와 설계, 개발·시험, 배포·운영 교육까지 단계별 책임과 완료 기준을 명확히 두어, 중간점검과 최종 납품 시점 모두에서 진행 상태를 객관적으로 설명할 수 있게 합니다. "
                "특히 산출물과 인력, WBS를 서로 연결해 일정과 품질, 자원 배분이 분리되지 않도록 구성합니다."
            ),
        )
        overview["project_info"] = _ensure_text(
            _strip_reference_noise(overview.get("project_info")),
            (
                f"**사업명**: {title}\n"
                "**계약 기간**: 입력 요구사항 및 계약서 확인 필요\n"
                "**계약 금액**: 입력 요구사항 및 계약서 확인 필요\n"
                "**발주처**: 입력 요구사항 확인 필요\n"
                f"**추진 목표**: {goal}\n"
                "**수행 원칙**: 단계별 산출물과 승인 게이트를 연결해 일정·품질·운영 이관을 동시에 관리"
            ),
        )
        overview["scope_of_work"] = _sanitize_rows(
            overview.get("scope_of_work"),
            [
                "교차로 및 스쿨존 대상 AI 기반 안전 모니터링 시스템을 구축합니다.",
                "위험 요소 분석과 개선 방안을 포함한 데이터 기반 운영 체계를 수립합니다.",
                "교통약자 보호를 위한 실시간 대응 대시보드와 보고 체계를 구축합니다.",
                "운영 매뉴얼과 교육 체계를 포함해 현장 적용과 이관까지 사업 범위에 포함합니다.",
            ],
            min_items=4,
        )
        overview["team_structure"] = _sanitize_rows(
            overview.get("team_structure"),
            [
                "PM·총괄 | 등급 확인 필요 | 담당자 지정 필요 | 투입량 산정 필요 | 프로젝트 총괄 및 대외 협의",
                "AI 기술 리드 | 등급 확인 필요 | 담당자 지정 필요 | 투입량 산정 필요 | 안전 분석 모델 설계 및 성능 검증",
                "소프트웨어 개발 | 등급 확인 필요 | 담당자 지정 필요 | 투입량 산정 필요 | 공공 솔루션 개발 및 연계 구현",
                "품질 관리 | 등급 확인 필요 | 담당자 지정 필요 | 투입량 산정 필요 | 품질 기준 수립, 시험·검수 운영",
            ],
            min_items=4,
        )
        overview["success_metrics"] = _ensure_rows(
            overview.get("success_metrics"),
            [
                "핵심 산출물 납기 준수 | 계약 일정에 정의된 납기 충족 | 산출물 제출대장과 승인 기록",
                "통합 테스트 완료율 | 합의된 핵심 시나리오 통과 | 시험 결과서와 결함 조치 이력",
                "사업 목표 달성도 | 계약서에 정의된 완료 KPI 충족 | 월간 보고서와 최종 검수 확인서",
            ],
        )

    quality = bundle.get("quality_risk_plan")
    if isinstance(quality, dict):
        quality["quality_operating_principles"] = _strip_reference_noise(quality.get("quality_operating_principles"))
        quality["quality_operating_principles"] = _ensure_text(
            quality.get("quality_operating_principles"),
            (
                "품질관리는 산출물 검수만이 아니라 일정·범위·운영 안정성을 함께 관리하는 방식으로 운영합니다. "
                "각 단계마다 사전 점검, 중간 검토, 최종 승인 조건을 분리하고, 결함·리스크·변경 요청은 동일한 이슈 관리 체계 안에서 추적합니다. "
                "이를 통해 품질 기준이 문서상 선언에 그치지 않고 실제 운영 회의와 승인 절차에서 반복 확인되도록 합니다."
            ),
        )
        quality["governance_checkpoints"] = _ensure_rows(
            quality.get("governance_checkpoints"),
            [
                "주간 PMO 회의 | 매주 | PM, 기술 리드, 품질 책임자 | 일정 진척률, 결함 조치, 선행 과제 상태",
                "월간 운영위원회 | 매월 | PM, 발주처 담당관, 주요 수행 리더 | 산출물 승인 여부, 리스크 등급, 변경 요청 검토",
                "분기 경영진 보고 | 분기 | Executive Approver, PM | 예산·성과·운영 리스크 종합 점검과 의사결정",
            ],
        )


def _apply_finished_doc_quality_guard(
    bundle: dict[str, Any],
    *,
    bundle_type: str,
    title: str,
    goal: str,
    context_text: str = "",
) -> dict[str, Any]:
    if bundle_type == "proposal_kr":
        _quality_guard_proposal_bundle(bundle, title=title, goal=goal)
        _quality_guard_sparse_non_attachment_proposal_bundle(
            bundle,
            title=title,
            goal=goal,
            context_text=context_text,
        )
        _quality_guard_attachment_grounded_proposal_bundle(
            bundle,
            title=title,
            goal=goal,
            context_text=context_text,
        )
    elif bundle_type == "performance_plan_kr":
        _quality_guard_performance_bundle(bundle, title=title, goal=goal)
    normalized = _normalize_finished_doc_value(bundle)
    return normalized if isinstance(normalized, dict) else bundle

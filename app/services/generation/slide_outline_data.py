"""Static slide outline fallback data for the proposal_kr bundle.

Provides deterministic ``slide_outline`` fallback content for two quality
scenarios: an attachment-grounded context (RFP text was parsed) and a sparse
non-attachment context (little/no usable input). Both keep responses free of
unanchored quantitative claims so downstream quality guards can safely use
them as a floor.
"""
from __future__ import annotations

from typing import Any


def _attachment_grounded_slide_outline(title: str, *, section: str) -> list[dict[str, Any]]:
    if section == "business_understanding":
        return [
            {
                "page": 1,
                "title": "사업 배경과 문제 정의",
                "key_content": (
                    f"{title} 제안은 교차로 안전 강화와 장애인 보호라는 핵심 요구를 먼저 정리하고, "
                    "현행 운영에서 어떤 문제가 반복되는지 평가위원이 바로 이해할 수 있게 설명합니다."
                ),
                "core_message": "첨부에서 확인된 요구사항을 기준으로 사업 필요성을 정리합니다.",
                "evidence_points": [
                    "첨부 원문에 교차로 안전 강화 요구가 명시됨",
                    "첨부 원문에 장애인 보호 강화 요구가 명시됨",
                ],
                "visual_type": "비교표",
                "visual_brief": "현행 문제와 개선 방향을 좌우 비교표로 정리",
                "layout_hint": "좌측 현황 문제 / 우측 제안 방향 / 하단 핵심 시사점",
                "design_tip": "원문 요구사항 문구를 강조 박스로 노출",
            },
            {
                "page": 2,
                "title": "평가 대응 포인트",
                "key_content": (
                    "평가위원이 확인할 사업 이해도, 실행 가능성, 기대효과를 "
                    "원문 요구사항과 운영 대응 전략 중심으로 구조화합니다."
                ),
                "core_message": "원문 요구사항을 평가 항목 언어로 변환해 제안 메시지를 정리합니다.",
                "evidence_points": [
                    "요구사항 반영 범위를 평가 포인트별로 재구성",
                    "근거 없는 수치 대신 확인 가능한 운영 방식 중심으로 설명",
                ],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "요구사항에서 제안 방향으로 이어지는 대응 흐름도",
                "layout_hint": "상단 요구사항 / 중앙 대응 전략 / 하단 기대 효과",
                "design_tip": "평가위원이 보는 관점 순서대로 읽히게 배치",
            },
        ]
    if section == "tech_proposal":
        return [
            {
                "page": 1,
                "title": "기술 접근 방향",
                "key_content": (
                    "특정 제품명을 앞세우기보다 데이터 수집, 위험 징후 분석, 운영 화면 제공 등 "
                    "실제 구현이 필요한 기능 단위로 기술 구성을 설명합니다."
                ),
                "core_message": "기술명보다 구현 기능과 운영 목적을 먼저 설명합니다.",
                "evidence_points": [
                    "현장 데이터 수집과 분석 지원이 핵심",
                    "운영자가 즉시 활용할 수 있는 화면과 보고 체계 필요",
                ],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "데이터 수집, 분석, 운영 활용 단계를 연결한 기능 흐름도",
                "layout_hint": "좌측 입력 / 중앙 분석 / 우측 운영 활용",
                "design_tip": "제품명 대신 기능 목적을 라벨로 사용",
            },
            {
                "page": 2,
                "title": "보안 및 운영 원칙",
                "key_content": (
                    "공공사업 제안서에 필요한 보안 통제, 접근권한 관리, 운영 추적 가능성을 "
                    "기본 설계 원칙으로 제시합니다."
                ),
                "core_message": "공공 운영 기준에 맞는 보안과 감사 대응 체계를 함께 제시합니다.",
                "evidence_points": [
                    "최소 권한과 접근 통제 원칙 적용",
                    "운영 로그와 검수 이력 확보 필요",
                ],
                "visual_type": "비교표",
                "visual_brief": "보안 원칙, 운영 통제, 검수 포인트를 나란히 보여주는 표",
                "layout_hint": "상단 핵심 원칙 / 하단 통제 항목 표",
                "design_tip": "공공기관 운영 기준 용어를 우선 사용",
            },
        ]
    if section == "execution_plan":
        return [
            {
                "page": 1,
                "title": "수행 단계 개요",
                "key_content": (
                    "착수, 설계, 구현, 검증, 운영 전환으로 이어지는 기본 수행 단계를 정리하고 "
                    "각 단계의 완료 기준을 함께 제시합니다."
                ),
                "core_message": "단계별 완료 기준과 산출물을 명확히 두는 수행계획입니다.",
                "evidence_points": [
                    "착수 단계에서 요구사항과 범위를 정리",
                    "검증 단계에서 품질 점검과 운영 전환 준비 수행",
                ],
                "visual_type": "타임라인",
                "visual_brief": "착수부터 운영 전환까지의 단계형 타임라인",
                "layout_hint": "가로 타임라인 / 단계별 산출물 박스",
                "design_tip": "날짜 대신 단계와 승인 조건을 중심으로 표기",
            },
            {
                "page": 2,
                "title": "거버넌스와 리스크 관리",
                "key_content": (
                    "PM, 기술 리드, 품질 책임자가 어떤 방식으로 이슈를 관리하고 "
                    "발주기관과 보고 체계를 유지하는지 설명합니다."
                ),
                "core_message": "보고 체계와 리스크 관리 책임을 분명히 하는 수행 구조입니다.",
                "evidence_points": [
                    "주기적 점검 회의와 승인 절차 운영",
                    "리스크 식별과 대응 이력을 같은 체계로 관리",
                ],
                "visual_type": "조직도",
                "visual_brief": "PM, 기술 리드, 품질 책임자 중심의 거버넌스 구조도",
                "layout_hint": "상단 의사결정 / 하단 실행 조직",
                "design_tip": "역할 관계와 승인 흐름을 동시에 보이게 구성",
            },
        ]
    return [
        {
            "page": 1,
            "title": "기대 효과 개요",
            "key_content": (
                "정량 수치를 임의로 제시하기보다 교차로 안전성 개선, 교통약자 보호 강화, "
                "운영 신뢰도 향상 같은 효과 범주를 명확히 설명합니다."
            ),
            "core_message": "근거가 확인된 효과 범주 중심으로 기대효과를 설명합니다.",
            "evidence_points": [
                "교차로 안전 강화 요구와 직접 연결된 효과",
                "장애인 보호 강화 요구와 직접 연결된 효과",
            ],
            "visual_type": "비교표",
            "visual_brief": "현행 문제와 기대 효과 범주를 비교하는 표",
            "layout_hint": "좌측 현행 한계 / 우측 기대 변화",
            "design_tip": "숫자 대신 효과 범주와 측정 방법을 강조",
        },
        {
            "page": 2,
            "title": "모니터링 및 확산 계획",
            "key_content": (
                "시범 운영 이후 어떤 항목을 모니터링하고, 후속 확산 여부를 어떻게 판단할지 "
                "운영 관점에서 정리합니다."
            ),
            "core_message": "실제 운영 데이터를 바탕으로 후속 확산 여부를 판단합니다.",
            "evidence_points": [
                "운영 로그, 사고·민원 추이, 현장 피드백을 함께 확인",
                "시범 운영 결과를 기반으로 후속 투자 판단",
            ],
            "visual_type": "타임라인",
            "visual_brief": "시범 운영, 점검, 확산 판단으로 이어지는 운영 타임라인",
            "layout_hint": "상단 단계 / 하단 확인 항목",
            "design_tip": "확산 결정이 실제 운영 데이터에 기반한다는 점을 강조",
        },
    ]


def _sparse_proposal_slide_outline(title: str, *, section: str) -> list[dict[str, Any]]:
    if section == "business_understanding":
        return [
            {
                "page": 1,
                "title": "사업 배경과 현안",
                "key_content": (
                    f"{title} 제안은 교차로 안전과 교통약자 보호가 왜 중요한지, "
                    "현장 운영 기준과 대응 체계가 왜 다시 정리되어야 하는지 설명합니다."
                ),
                "core_message": "문제 정의와 사업 필요성을 운영 관점에서 먼저 정리합니다.",
                "evidence_points": [
                    "현장 위험 징후를 더 빠르게 파악할 필요가 있음",
                    "교통약자 보호 기준을 일관되게 운영해야 함",
                ],
                "visual_type": "비교표",
                "visual_brief": "현행 한계와 개선 방향을 나란히 보여주는 비교표",
                "layout_hint": "좌측 현행 문제 / 우측 제안 방향 / 하단 핵심 메시지",
                "design_tip": "수치보다 운영상 문제와 개선 포인트를 강조",
            },
            {
                "page": 2,
                "title": "사업 목표와 평가 대응",
                "key_content": (
                    "발주기관이 확인할 사업 이해도, 실행 가능성, 기대효과를 "
                    "운영 과제와 점검 항목 중심으로 구조화합니다."
                ),
                "core_message": "근거 없는 정량 약속보다 점검 가능한 목표 체계를 제시합니다.",
                "evidence_points": [
                    "운영 절차와 점검 기준을 먼저 정의",
                    "후속 개선 여부를 실제 데이터로 판단할 수 있게 구성",
                ],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "사업 목표에서 평가 대응 포인트로 이어지는 흐름도",
                "layout_hint": "상단 목표 / 중앙 대응 전략 / 하단 점검 포인트",
                "design_tip": "평가 항목 순서대로 읽히게 배치",
            },
        ]
    if section == "tech_proposal":
        return [
            {
                "page": 1,
                "title": "기술 구성 방향",
                "key_content": (
                    "데이터 수집, 위험 징후 분석, 운영 화면 제공처럼 실제 구현이 필요한 기능을 기준으로 "
                    "기술 구성을 설명합니다."
                ),
                "core_message": "제품명보다 기능 흐름과 운영 목적을 먼저 설명합니다.",
                "evidence_points": [
                    "현장 데이터 수집과 분석 지원이 핵심",
                    "운영자가 즉시 활용할 수 있는 화면과 보고 체계 필요",
                ],
                "visual_type": "프로세스 흐름도",
                "visual_brief": "데이터 수집에서 운영 활용까지 이어지는 기능 흐름도",
                "layout_hint": "좌측 입력 / 중앙 분석 / 우측 운영 활용",
                "design_tip": "기능 단위를 중심으로 라벨링",
            },
            {
                "page": 2,
                "title": "보안과 운영 원칙",
                "key_content": (
                    "공공 운영 환경에 필요한 접근 통제, 감사 대응, 운영 추적성을 "
                    "기본 설계 원칙으로 제시합니다."
                ),
                "core_message": "보안과 운영 통제를 동시에 만족하는 구조를 제안합니다.",
                "evidence_points": [
                    "최소 권한과 로그 기록을 기본값으로 적용",
                    "운영 검수와 감사 대응이 가능한 구조를 유지",
                ],
                "visual_type": "비교표",
                "visual_brief": "보안 원칙, 운영 통제, 검수 포인트 비교표",
                "layout_hint": "상단 원칙 요약 / 하단 통제 항목 표",
                "design_tip": "공공기관 운영 용어를 우선 사용",
            },
        ]
    if section == "execution_plan":
        return [
            {
                "page": 1,
                "title": "수행 단계 개요",
                "key_content": (
                    "착수, 설계, 구현, 검증, 운영 전환의 기본 단계를 정리하고 각 단계의 완료 기준을 함께 제시합니다."
                ),
                "core_message": "단계별 완료 기준과 산출물을 명확히 둔 수행계획입니다.",
                "evidence_points": [
                    "착수 단계에서 요구사항과 범위를 명확히 정리",
                    "검증 단계에서 품질 점검과 운영 전환 준비 수행",
                ],
                "visual_type": "타임라인",
                "visual_brief": "착수부터 운영 전환까지의 단계형 타임라인",
                "layout_hint": "가로 타임라인 / 단계별 산출물 박스",
                "design_tip": "날짜보다 단계와 승인 조건을 강조",
            },
            {
                "page": 2,
                "title": "거버넌스와 리스크 관리",
                "key_content": (
                    "PM, 기술 리드, 운영·품질 담당이 어떤 방식으로 이슈를 관리하고 발주기관과 보고 체계를 유지하는지 설명합니다."
                ),
                "core_message": "보고 체계와 리스크 관리 책임을 분명히 하는 구조입니다.",
                "evidence_points": [
                    "주기적 점검 회의와 승인 절차 운영",
                    "리스크 식별과 대응 이력을 같은 체계로 관리",
                ],
                "visual_type": "조직도",
                "visual_brief": "PM, 기술 리드, 운영·품질 담당 중심의 거버넌스 구조도",
                "layout_hint": "상단 의사결정 / 하단 실행 조직",
                "design_tip": "역할 관계와 승인 흐름을 동시에 표시",
            },
        ]
    return [
        {
            "page": 1,
            "title": "기대 효과 개요",
            "key_content": (
                "정량 수치를 임의로 약속하기보다 교차로 안전성 개선, 교통약자 보호 강화, 운영 신뢰도 향상 같은 효과 범주를 정리합니다."
            ),
            "core_message": "근거가 확인된 효과 범주와 점검 방법 중심으로 기대효과를 설명합니다.",
            "evidence_points": [
                "현장 안전성과 보호 체계 강화를 목표로 함",
                "운영 데이터와 점검 결과로 후속 개선 여부를 판단",
            ],
            "visual_type": "비교표",
            "visual_brief": "현행 한계와 기대 효과 범주를 비교하는 표",
            "layout_hint": "좌측 현행 한계 / 우측 기대 변화",
            "design_tip": "숫자보다 효과 범주와 측정 방법을 강조",
        },
        {
            "page": 2,
            "title": "모니터링과 확산 기준",
            "key_content": (
                "시범 운영 이후 어떤 항목을 점검하고, 후속 확산 여부를 어떤 기준으로 판단할지 운영 관점에서 정리합니다."
            ),
            "core_message": "실제 운영 데이터를 바탕으로 후속 확산 여부를 판단합니다.",
            "evidence_points": [
                "운영 로그, 민원 추이, 현장 피드백을 함께 확인",
                "시범 운영 결과를 후속 투자 판단 근거로 활용",
            ],
            "visual_type": "타임라인",
            "visual_brief": "시범 운영, 점검, 확산 판단으로 이어지는 운영 타임라인",
            "layout_hint": "상단 단계 / 하단 확인 항목",
            "design_tip": "확산 결정이 실제 운영 데이터에 기반한다는 점을 강조",
        },
    ]

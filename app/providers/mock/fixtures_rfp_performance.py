"""Mock fixture builders for rfp_analysis_kr and performance_plan_kr bundles."""
from app.providers.mock.shared import _ctx_excerpt, _project_subject, _slide


def _rfp_analysis_summary(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "project_overview": (
            f"{title} 공고를 기준으로 {goal}에 필요한 평가 포인트를 정리합니다. {excerpt}"
        ),
        "budget_schedule": "예산, 계약 기간, 제안 마감과 질의응답 일정을 procurement state와 함께 검토합니다.",
        "issuer_needs": [
            "발주기관의 문제 정의와 평가 우선순위를 procurement context와 source snapshot에서 추출합니다.",
            f"핵심 맥락: {excerpt}",
        ],
        "evaluation_criteria": [
            "필수 자격·인증·유사 실적 요구를 평가항목 해석의 출발점으로 둡니다.",
            "hard filter에서 확인된 blocking 조건을 평가 리스크로 명시합니다.",
        ],
        "mandatory_requirements": [
            "입찰참가자격, 보안 의무, 일정 제약, 핵심 기술 범위를 필수 요구사항으로 정리합니다.",
            f"현재 procurement context: {excerpt}",
        ],
        "optional_requirements": [
            "가점 요소와 차별화 요소를 별도로 분리해 win strategy에 연결합니다.",
        ],
        "win_probability": (
            f"현재 recommendation과 soft-fit breakdown을 반영해 수주 가능성 판단 근거를 요약합니다. {excerpt}"
        ),
    }

def _rfp_analysis_win_strategy(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "swot_analysis": (
            f"{title} 입찰에 대한 SWOT 분석은 procurement recommendation과 capability profile을 기준으로 작성합니다. {excerpt}"
        ),
        "differentiation_points": [
            "기존 공공 레퍼런스와 domain fit 점수에 근거한 차별화 포인트를 우선 배치합니다.",
            "Conditional Go 보완 항목은 차별화와 동시에 리스크 완화 계획으로 표현합니다.",
        ],
        "risk_factors": [
            "blocking hard filter와 action-needed checklist는 제안 리스크로 직접 연결합니다.",
            f"리스크 근거: {excerpt}",
        ],
        "response_strategy": (
            f"{goal} 달성을 위해 procurement checklist와 recommendation evidence를 대응 전략으로 전환합니다. {excerpt}"
        ),
        "key_messages": [
            "발주기관 핵심 니즈와 당사 적합성을 한 문장으로 연결합니다.",
            "승인 조건이 있다면 제안 전략에 필요한 선결 과제로 명시합니다.",
            f"참고 맥락: {excerpt}",
        ],
    }

def _performance_overview(title: str, goal: str, ctx: str) -> dict:
    subject = _project_subject(title)
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "executive_summary": (
            f"{subject} 수행계획서는 계약 범위, 일정, 산출물, 투입 인력, 승인 게이트를 하나의 실행 문서로 정리한 결과물입니다. "
            "착수 이후 요구사항 정의와 설계, 개발·시험, 배포·운영 교육까지 단계별 책임과 완료 기준을 명확히 두어 발주처가 중간점검과 최종 검수 시점 모두에서 진행 상태를 객관적으로 확인할 수 있게 구성했습니다. "
            "특히 산출물·인력·WBS를 서로 연결해 일정과 품질, 자원 배분이 분리되지 않도록 설계했습니다. "
            f"조달 연계 참고: {excerpt}"
        ),
        "project_info": (
            f"**사업명**: {title}\n"
            f"**계약 기간**: 2026년 1월 1일 ~ 2027년 12월 31일 (24개월)\n"
            f"**계약 금액**: 6,500,000,000원 (부가세 포함)\n"
            f"**발주처**: 국토교통부\n"
            f"**추진 목표**: {goal}\n"
            "**수행 원칙**: 단계별 산출물과 승인 게이트를 연결해 일정·품질·운영 이관을 동시에 관리"
        ),
        "scope_of_work": [
            "교차로 및 스쿨존 대상 AI 기반 안전 모니터링 시스템을 구축합니다.",
            "위험 요소 분석과 개선 방안을 포함한 데이터 기반 운영 체계를 수립합니다.",
            "교통약자 보호를 위한 실시간 대응 대시보드와 보고 체계를 구축합니다.",
            "운영 매뉴얼과 교육 체계를 포함해 현장 적용과 이관까지 사업 범위에 포함합니다.",
        ],
        "deliverables": [
            "착수보고서 | 2026년 1월 15일 | HWP+PDF | 발주처 PM 서면 승인",
            "중간보고서 | 2026년 6월 30일 | HWP+PDF | 월간 점검회의 검토",
            "운영 매뉴얼 | 2027년 12월 15일 | HWP+PDF | 현장 시연 및 교육 결과 확인",
            "최종보고서 | 2027년 12월 31일 | HWP+PDF | 최종 검수위원회 승인",
        ],
        "team_structure": [
            "PM·총괄 | 특급 | 이현수 | 15 | 국토교통 프로젝트 경험 10년",
            "AI 기술 리드 | 고급 | 김석진 | 10 | 안전 분석 알고리즘 구현 경력 5년",
            "소프트웨어 개발 | 중급 | 박민재 외 2명 | 7 | 공공 솔루션 개발 경험",
            "품질 관리 | 고급 | 송지현 | 6 | ISO 품질 인증 및 검수 경험",
        ],
        "success_metrics": [
            "핵심 산출물 납기 준수 | 예정일 대비 지연 0건 | 산출물 제출대장과 승인 기록",
            "통합 테스트 완료율 | 계획된 핵심 시나리오 100% 통과 | 시험 결과서와 결함 조치 이력",
            "사업 목표 달성도 | 계약서에 정의된 완료 KPI 충족 | 월간 보고서와 최종 검수 확인서",
        ],
        "wbs_summary": [
            "1단계 착수 및 요구사항 정의 | 2026년 1월 ~ 2026년 3월 | 착수보고서, 요구사항 정의서 | M1: 착수보고 완료",
            "2단계 시스템 설계 | 2026년 4월 ~ 2026년 6월 | 아키텍처 설계서, 데이터 정의서 | M2: 설계 검토 승인",
            "3단계 개발 및 테스트 | 2026년 7월 ~ 2027년 9월 | 개발 산출물, 시험 결과서 | M3: 통합 테스트 통과",
            "4단계 배포 및 운영 교육 | 2027년 10월 ~ 2027년 12월 | 운영 매뉴얼, 완료보고서 | M4: 최종 납품",
        ],
        "total_slides": 8,
        "slide_outline": [
            _slide(1, "사업 개요",
                   f"{subject} 사업 목적, 계약 기간·예산, 발주처 핵심 요구사항 요약",
                   "표지 이후 첫 슬라이드. 사업명과 목표를 한 문장으로 강조."),
            _slide(2, "사업 배경과 추진 필요성",
                   "교통약자 안전 확보 필요성, 현행 운영 한계, 정책·행정 맥락 정리",
                   "배경 사진 1장 + 문제 정의 3포인트 카드."),
            _slide(3, "수행 범위",
                   "AI 모니터링, 위험 분석, 대시보드, 교육·운영 체계 등 범위 4개 축 설명",
                   "4분할 범위 다이어그램 또는 아이콘 카드."),
            _slide(4, "핵심 산출물",
                   "착수보고서, 중간보고서, 운영 매뉴얼, 최종보고서 제출 시점과 검수 방안",
                   "산출물 표를 중심으로 구성."),
            _slide(5, "투입 인력 및 역할",
                   "PM, AI 리드, 개발, 품질관리의 책임과 전문성, M/M 배분",
                   "조직도 + 인력 표 조합."),
            _slide(6, "WBS 및 마일스톤",
                   "4단계 일정, 단계별 산출물, 주요 승인 게이트 정리",
                   "타임라인 또는 표 형태."),
            _slide(7, "추진 거버넌스",
                   "PMO 운영, 주간 점검, 이슈 escalation, 발주처 보고 구조 정리",
                   "거버넌스 흐름도와 보고 주기 배지."),
            _slide(8, "기대 성과와 다음 단계",
                   "완료 기준, 인수 조건, 사업 종료 후 기대되는 운영 상태",
                   "마무리 슬라이드. 성공 지표 3개 강조."),
        ],
    }

def _performance_quality_risk(title: str, goal: str, ctx: str) -> dict:
    excerpt = _ctx_excerpt(ctx, 520)
    return {
        "quality_operating_principles": (
            "품질관리는 산출물 검수만이 아니라 일정·범위·운영 안정성을 함께 관리하는 방식으로 운영합니다. "
            "각 단계마다 사전 점검, 중간 검토, 최종 승인 조건을 분리하고, 결함·리스크·변경 요청은 동일한 이슈 관리 체계 안에서 추적합니다. "
            "이를 통해 품질 기준이 선언에 그치지 않고 실제 운영 회의와 승인 절차에서 반복 확인되도록 합니다. "
            f"또한 최근 조달 의사결정 상태와 원문 추출 신호를 품질 관리 기준에 반영합니다: {excerpt}"
        ),
        "quality_standards": [
            "기능 적합성 | 교차로/스쿨존 위험 감지 정확도 92% 이상 | 월별 정확도 측정 보고",
            "성능 효율성 | 경보 이벤트 처리 응답시간 3초 이내 | 부하 테스트 결과서",
            "운영 안정성 | 장애 복구 시간 30분 이내 | 모의 장애 복구 리허설",
        ],
        "inspection_criteria": [
            "착수보고서 | 착수 단계 종료 시 | 요구사항 누락 0건 | 착수보고 회의록",
            "중간보고서 | 개발 단계 종료 시 | 핵심 기능 시연 완료 | 중간보고 검토서",
            "최종보고서 | 사업 종료 시 | 계약서에 정의된 완료 지표 충족 | 최종 검수 확인서",
        ],
        "risk_matrix": [
            "데이터 누락 | 중 | 상 | 현장 센서 데이터 품질 진단 및 예비 수집 계획 운영",
            "시스템 오류 | 중 | 중 | 핵심 모듈 이중화와 장애 대응 Runbook 준비",
            "일정 지연 | 상 | 중 | 주간 PMO 점검과 선행 과제 조기 경보 체계 운영",
        ],
        "change_management": (
            "변경 요청은 PM이 접수 후 영향도(범위, 일정, 비용)를 분석하고, 발주처 승인 회의에서 결정합니다. 승인된 변경만 WBS와 산출물 목록에 반영하며 모든 이력은 변경대장으로 관리합니다."
        ),
        "reporting_structure": (
            f"{goal} 달성을 위해 PM 주간보고, 월간 운영위원회, 분기별 경영진 보고 체계를 운영합니다. 주요 이슈는 Delivery Lead와 품질 책임자가 사전 검토하고, 최종 의사결정은 Executive Approver가 수행합니다."
        ),
        "governance_checkpoints": [
            "주간 PMO 회의 | 매주 | PM, 기술 리드, 품질 책임자 | 일정 진척률, 결함 조치, 선행 과제 상태",
            "월간 운영위원회 | 매월 | PM, 발주처 담당관, 주요 수행 리더 | 산출물 승인 여부, 리스크 등급, 변경 요청 검토",
            "분기 경영진 보고 | 분기 | Executive Approver, PM | 예산·성과·운영 리스크 종합 점검과 의사결정",
        ],
        "total_slides": 6,
        "slide_outline": [
            _slide(1, "품질관리 개요",
                   "품질 목표, 품질지표, 검수 운영 원칙 요약",
                   "품질 KPI 배지와 핵심 문장 강조."),
            _slide(2, "품질 기준 상세",
                   "기능 적합성, 성능 효율성, 운영 안정성 기준과 측정 방식 정리",
                   "품질 기준 표 중심 구성."),
            _slide(3, "검수 기준과 승인 체계",
                   "착수·중간·최종 산출물 검수 시점, 승인 기준, 증빙 문서 정리",
                   "검수 절차 플로우 + 표."),
            _slide(4, "리스크 매트릭스",
                   "데이터, 시스템, 일정 리스크의 가능성과 영향도, 대응 계획",
                   "리스크 표 또는 2x2 matrix 시각화."),
            _slide(5, "변경관리 및 이슈 대응",
                   "변경 요청 처리, 영향도 검토, 승인 절차, 이력 관리 원칙",
                   "변경관리 흐름도."),
            _slide(6, "보고 체계와 운영 통제",
                   f"{goal} 달성을 위한 주간·월간·분기 보고 체계와 escalation 규칙",
                   "보고 cadence 타임라인과 책임자 구분."),
        ],
    }

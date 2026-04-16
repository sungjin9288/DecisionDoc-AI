"""performance_plan_kr bundle — 사업수행계획서 (한국어).

2개 문서로 구성:
  1. performance_overview — 수행 개요, WBS, 투입 인력, 산출물
  2. quality_risk_plan    — 품질·리스크 관리 계획
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

_SLIDE_ITEM = {
    "type": "object",
    "properties": {
        "page": {"type": "integer"},
        "title": {"type": "string"},
        "key_content": {"type": "string"},
        "core_message": {"type": "string"},
        "evidence_points": {"type": "array", "items": {"type": "string"}},
        "visual_type": {"type": "string"},
        "visual_brief": {"type": "string"},
        "layout_hint": {"type": "string"},
        "design_tip": {"type": "string"},
    },
}

PERFORMANCE_PLAN_KR = BundleSpec(
    id="performance_plan_kr",
    name_ko="사업수행계획서",
    name_en="Project Performance Plan",
    description_ko="나라장터 과업 수행계획서. WBS, 품질관리, 납품물 계획 포함. 착수보고 즉시 활용 가능.",
    icon="📋",
    prompt_language="ko",
    category="gov",
    prompt_hint=(
        "당신은 공공 IT 프로젝트 PMO 전문가로, 발주처 감독관이 검토하는 수행계획서를 작성합니다.\n"
        "작성 전 내부적으로 검토하세요: (1) 계약서상 납품 기한과 산출물이 WBS에 빠짐없이 반영됐는가, "
        "(2) 투입 인력의 역할과 책임이 명확히 구분됐는가, "
        "(3) 품질 검수 기준이 발주처가 측정 가능한 수준으로 정의됐는가.\n"
        "- executive_summary 와 quality_operating_principles 는 각각 3~5문장 분량으로 작성하고, 첫 문장은 발주처가 바로 이해할 수 있는 결론형 문장으로 시작하세요.\n"
        "- 모든 설명 문단은 '계약 목적 → 운영 방식 → 검수/통제 기준' 흐름을 유지하고, 선언형 슬로건만 남기지 마세요.\n"
        "- project_info는 `**항목명**: 값` 형식의 줄 목록으로 작성하세요. 예: `**사업명**: ...`\n"
        "- WBS는 `단계 | 기간 | 주요 산출물 | 마일스톤` 순서의 table row 목록으로 작성하세요.\n"
        "- 납품물(산출물) 목록은 `산출물 | 제출 기한 | 형식 | 검수 방법` 순서의 table row 목록으로 작성하세요.\n"
        "- 투입 인력은 `역할 | 등급 | 성명 | M/M | 책임 및 전문성` 순서의 table row 목록으로 작성하세요.\n"
        "- success_metrics는 `관리 항목 | 목표 기준 | 확인 방식` 순서의 table row 목록으로 작성하세요.\n"
        "- 품질 기준은 `구분 | 품질 기준 | 측정 방법` 순서의 table row 목록으로 작성하세요.\n"
        "- 검수 기준은 `검수 대상 | 검수 시점 | 승인 기준 | 증빙` 순서의 table row 목록으로 작성하세요.\n"
        "- 리스크는 `리스크 | 발생 가능성 | 영향도 | 대응 방안` 순서의 table row 목록으로 작성하세요.\n"
        "- governance_checkpoints는 `운영 회의체 | 주기 | 책임 | 주요 확인 항목` 순서의 table row 목록으로 작성하세요.\n"
        "- 변경 관리 절차와 보고 체계를 명확히 기술하세요.\n"
        "- slide_outline 은 발표자료 페이지별 설계안입니다. 각 페이지마다 page·title·key_content·core_message·evidence_points·visual_type·visual_brief·layout_hint·design_tip 을 채우세요.\n"
        "- key_content는 발표자가 설명할 핵심 내용을 2~4문장으로 정리하고, core_message는 발주처가 바로 이해할 한 줄 결론으로 적으세요.\n"
        "- evidence_points는 일정·산출물·검수 기준·리스크 등 발주처를 설득할 근거 2~4개를 적고, visual_type은 사진·타임라인·조직도·비교표·간트 차트·프로세스 흐름도·리스크 매트릭스 중 가장 적합한 유형을 고르세요.\n"
        "- visual_brief에는 실제로 넣어야 할 도표/그림 구성을 쓰고, layout_hint에는 좌우 배치, 강조 숫자, 표/도식 위치를 구체적으로 적으세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## 수행 총괄 요약\n"
        "본 수행계획서는 국가재정정보시스템 AI 고도화 사업을 계약 범위, 납품 일정, 품질 검수 기준까지 한 번에 설명할 수 있도록 정리한 실행 문서입니다. "
        "발주처가 중간점검 시점마다 진행률과 산출물 완성도를 객관적으로 확인할 수 있도록 WBS, 투입 인력, 산출물, 품질 기준을 서로 연결해 서술합니다. "
        "또한 리스크와 변경관리 절차를 별도 문단으로 분리하여 사업 종료 시점의 책임 경계와 운영 이관 조건을 명확히 합니다.\n\n"
        "## 사업 개요\n"
        "**사업명**: 기획재정부 국가재정정보시스템(NAFIS) AI 고도화 사업\n"
        "**계약 기간**: 2025.03.01 ~ 2026.08.31 (18개월)\n"
        "**계약 금액**: 3,500,000,000원 (부가세 포함)\n"
        "**발주처**: 기획재정부 재정정보화과\n\n"
        "## 수행 범위\n"
        "- 국가 세출예산 집행 이상 탐지 AI 엔진 개발 (예산 전용·과목 오류 자동 탐지)\n"
        "- 기관별 예산 집행 패턴 분석 대시보드 구축 (246개 중앙행정기관)\n"
        "- 차세대 예산회계 시스템(디브레인) 연계 API 개발\n"
        "- 사용자 교육 및 운영 이관 (50명 교육, 운영 매뉴얼 3종)\n\n"
        "## WBS (단계별 일정)\n"
        "| 단계 | 기간 | 주요 산출물 | 마일스톤 |\n"
        "|------|------|------------|---------|\n"
        "| 1단계 착수·분석 | 25.03~25.05 (3개월) | 착수보고서, 요구사항 정의서 | M1: 착수보고 |\n"
        "| 2단계 AI 설계 | 25.06~25.08 (3개월) | AI 설계서, 학습 데이터 정의서 | M2: 설계 완료 |\n"
        "| 3단계 개발·학습 | 25.09~26.01 (5개월) | 이상 탐지 엔진, 단위 시험 결과서 | M3: 중간보고 |\n"
        "| 4단계 연계·시험 | 26.02~26.06 (5개월) | API 연계 결과서, 통합 테스트 결과서 | M4: 파일럿 완료 |\n"
        "| 5단계 전개·완료 | 26.07~26.08 (2개월) | 교육 결과서, 완료보고서 | M5: 최종 납품 |\n\n"
        "## 산출물 목록\n"
        "| 산출물 | 제출 기한 | 형식 | 검수 방법 |\n"
        "|--------|----------|------|---------|\n"
        "| 착수보고서 | 25.03.15 | HWP+PDF | 계약담당관 서면 승인 |\n"
        "| AI 아키텍처 설계서 | 25.08.31 | HWP+PDF | 기술 검수 위원회 |\n"
        "| 완료보고서 | 26.08.31 | HWP+PDF | 계약담당관 최종 승인 |\n\n"
        "## 투입 인력 (총 62.5M/M)\n"
        "| 역할 | 등급 | 성명 | M/M | 책임 및 전문성 |\n"
        "|------|------|------|-----|----------------|\n"
        "| PM·총괄 | 특급 | 홍길동 | 18 | PMP, 재정정보화 사업 PMO 경력 8년 |\n"
        "| AI 리드 | 특급 | 김철수 | 15 | 이상 탐지 알고리즘 논문 4편 |\n"
        "| 백엔드 개발 | 고급 | 이영희 | 8 | 디브레인 연계 경험 보유 |\n"
        "| 데이터 엔지니어 | 중급 | 박민준 | 7 | 공공 데이터 파이프라인 구축 3건 |\n"
        "| 품질관리 | 고급 | 최지수 | 6.5 | ISO 25010 기반 품질 검수 |\n"
        "\n## 핵심 성공 지표\n"
        "| 관리 항목 | 목표 기준 | 확인 방식 |\n"
        "|----------|-----------|-----------|\n"
        "| 핵심 산출물 납기 준수 | 예정일 대비 지연 0건 | 산출물 제출대장 및 승인 기록 |\n"
        "| 통합 테스트 완료율 | 핵심 시나리오 100% 통과 | 시험 결과서 및 결함 조치 이력 |\n"
        "| 사업 목표 달성도 | 이상 탐지 정확도 92% 이상 | 월간 성능 보고 및 최종 검수 확인 |\n"
    ),
    docs=[
        DocumentSpec(
            key="performance_overview",
            template_file="performance_plan_kr/performance_overview.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "executive_summary", "project_info", "scope_of_work", "deliverables",
                    "success_metrics",
                    "team_structure", "wbs_summary", "total_slides", "slide_outline",
                ],
                "properties": {
                    "executive_summary": {"type": "string"},
                    "project_info":   {"type": "string"},
                    "scope_of_work":  {"type": "array", "items": {"type": "string"}},
                    "deliverables":   {"type": "array", "items": {"type": "string"}},
                    "success_metrics": {"type": "array", "items": {"type": "string"}},
                    "team_structure": {"type": "array", "items": {"type": "string"}},
                    "wbs_summary":    {"type": "array", "items": {"type": "string"}},
                    "total_slides":   {"type": "integer"},
                    "slide_outline":  {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "executive_summary": "",
                "project_info": "",
                "scope_of_work": [],
                "deliverables": [],
                "success_metrics": [],
                "team_structure": [],
                "wbs_summary": [],
                "total_slides": 0,
                "slide_outline": [],
            },
            lint_headings=[
                "# 사업수행계획서:", "## 수행 총괄 요약", "## 사업 개요", "## 수행 범위",
                "## 산출물 목록", "## WBS", "## PPT 구성 가이드",
            ],
            validator_headings=[
                "## 수행 총괄 요약", "## 사업 개요", "## 수행 범위", "## 산출물 목록",
                "## 투입 인력", "## WBS", "## 핵심 성공 지표", "## PPT 구성 가이드",
            ],
            critical_non_empty_headings=["## 수행 총괄 요약", "## 사업 개요", "## WBS"],
        ),
        DocumentSpec(
            key="quality_risk_plan",
            template_file="performance_plan_kr/quality_risk_plan.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "quality_operating_principles", "quality_standards", "inspection_criteria",
                    "risk_matrix", "change_management", "reporting_structure", "total_slides", "slide_outline",
                    "governance_checkpoints",
                ],
                "properties": {
                    "quality_operating_principles": {"type": "string"},
                    "quality_standards":   {"type": "array", "items": {"type": "string"}},
                    "inspection_criteria": {"type": "array", "items": {"type": "string"}},
                    "risk_matrix":         {"type": "array", "items": {"type": "string"}},
                    "change_management":   {"type": "string"},
                    "reporting_structure": {"type": "string"},
                    "governance_checkpoints": {"type": "array", "items": {"type": "string"}},
                    "total_slides":        {"type": "integer"},
                    "slide_outline":       {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "quality_operating_principles": "",
                "quality_standards": [],
                "inspection_criteria": [],
                "risk_matrix": [],
                "change_management": "",
                "reporting_structure": "",
                "governance_checkpoints": [],
                "total_slides": 0,
                "slide_outline": [],
            },
            lint_headings=[
                "# 품질·리스크 관리계획:", "## 품질 운영 원칙", "## 품질 기준",
                "## 검수 기준", "## 리스크 매트릭스", "## 변경 관리", "## PPT 구성 가이드",
            ],
            validator_headings=[
                "## 품질 운영 원칙", "## 품질 기준", "## 검수 기준", "## 리스크 매트릭스",
                "## 변경 관리", "## 보고 체계", "## 운영 회의체 및 통제 포인트", "## PPT 구성 가이드",
            ],
            critical_non_empty_headings=["## 품질 운영 원칙", "## 품질 기준", "## 리스크 매트릭스"],
        ),
    ],
)

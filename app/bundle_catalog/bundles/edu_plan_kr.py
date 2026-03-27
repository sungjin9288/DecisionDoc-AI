"""edu_plan_kr bundle — 사내 교육훈련 계획 (한국어).

4개 문서:
  1. edu_objective  — 교육 목표
  2. curriculum     — 커리큘럼
  3. assessment     — 평가 방법
  4. operation_plan — 운영 계획
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

_SLIDE_ITEM = {
    "type": "object",
    "properties": {
        "page":        {"type": "integer"},
        "title":       {"type": "string"},
        "key_content": {"type": "string"},
        "design_tip":  {"type": "string"},
    },
}

EDU_PLAN_KR = BundleSpec(
    id="edu_plan_kr",
    name_ko="사내 교육훈련 계획",
    name_en="Corporate Training Plan",
    description_ko="사내 교육훈련 계획서·학습 목표·커리큘럼 설계. 기업 직무교육 및 역량 개발 전문.",
    icon="🎯",
    prompt_language="ko",
    prompt_hint=(
        "당신은 대기업 HR 및 조직개발(OD) 전문가로, 사내 직무교육 훈련 계획서 작성 전문가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 직무 역량 갭이 명확히 정의되었는가, "
        "(2) 교육 목표가 비즈니스 성과와 연계되는가, (3) 교육 효과를 어떻게 측정할 것인가.\n"
        "- 학습 성취 기준은 직무 수행 능력 향상 관점에서 구체적으로 서술하세요.\n"
        "- 주차별 계획은 도입→전개→정리 구조로, 실무 적용 중심으로 작성하세요.\n"
        "- 평가는 사전/사후 역량 측정, 현업 적용도 평가를 포함하세요.\n"
        "- 교육 담당자가 실제 운영할 수 있도록 구체적인 지침을 제공하세요.\n"
        "- slide_outline 은 PPT 슬라이드별 구성안입니다. page·title·key_content·design_tip 을 채우세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="internal",
    few_shot_example=(
        "## 학습 목표\n"
        "본 교육 과정 이수 후 수강자는 (1) 신규 ERP 시스템(SAP S/4HANA)을 활용해 발주·정산 업무를 독립 수행하고, "
        "(2) 부서 KPI 대시보드를 주간 리포트 형식으로 작성하며, "
        "(3) 내부 감사 대비 증빙 서류를 규정 절차에 따라 관리할 수 있다.\n"
        "\n"
        "## 차시별 교육 계획\n"
        "| 차시 | 주제 | 핵심 활동 |\n"
        "|------|------|----------|\n"
        "| 1차시 | 시스템 개요 및 로그인 | ERP 환경 구성, 권한 설정 실습 |\n"
        "| 2차시 | 발주 프로세스 | 구매 요청→발주→검수 End-to-End 실습 |\n"
        "| 3차시 | 정산 및 회계 연동 | 세금계산서 처리, 회계 전표 생성 |\n"
        "| 4차시 | KPI 리포팅 | Power BI 대시보드 조회 및 주간 보고서 작성 |\n"
        "| 5차시 | 감사 대비 실습 | 증빙 서류 체계 및 이상거래 탐지 사례 분석 |\n"
    ),
    docs=[
        DocumentSpec(
            key="edu_objective",
            template_file="edu_plan_kr/edu_objective.md.j2",
            json_schema={
                "type": "object",
                "required": ["vision", "target_learners", "core_competencies",
                             "learning_outcomes", "total_slides", "slide_outline"],
                "properties": {
                    "vision":             {"type": "string"},
                    "target_learners":    {"type": "array", "items": {"type": "string"}},
                    "core_competencies":  {"type": "array", "items": {"type": "string"}},
                    "learning_outcomes":  {"type": "array", "items": {"type": "string"}},
                    "total_slides":       {"type": "integer"},
                    "slide_outline":      {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "vision":            "",
                "target_learners":   [],
                "core_competencies": [],
                "learning_outcomes": [],
                "total_slides":      0,
                "slide_outline":     [],
            },
            lint_headings=["# 교육 목표:", "## 교육 비전", "## 교육 대상", "## 핵심 역량", "## PPT 구성 가이드"],
            validator_headings=["## 교육 비전", "## 교육 대상", "## 핵심 역량",
                                "## 학습 성취 기준", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 교육 비전", "## 핵심 역량"],
        ),
        DocumentSpec(
            key="curriculum",
            template_file="edu_plan_kr/curriculum.md.j2",
            json_schema={
                "type": "object",
                "required": ["subject_structure", "weekly_plan", "special_activities",
                             "materials_and_tools", "total_slides", "slide_outline"],
                "properties": {
                    "subject_structure":  {"type": "array", "items": {"type": "string"}},
                    "weekly_plan":        {"type": "array", "items": {"type": "string"}},
                    "special_activities": {"type": "array", "items": {"type": "string"}},
                    "materials_and_tools":{"type": "array", "items": {"type": "string"}},
                    "total_slides":       {"type": "integer"},
                    "slide_outline":      {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "subject_structure":   [],
                "weekly_plan":         [],
                "special_activities":  [],
                "materials_and_tools": [],
                "total_slides":        0,
                "slide_outline":       [],
            },
            lint_headings=["# 커리큘럼:", "## 교과목 구성", "## 주차별 계획", "## 교재 및 도구", "## PPT 구성 가이드"],
            validator_headings=["## 교과목 구성", "## 주차별 계획", "## 특별 활동",
                                "## 교재 및 도구", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 교과목 구성", "## 주차별 계획"],
        ),
        DocumentSpec(
            key="assessment",
            template_file="edu_plan_kr/assessment.md.j2",
            json_schema={
                "type": "object",
                "required": ["assessment_methods", "evaluation_criteria", "feedback_process",
                             "appeal_process", "total_slides", "slide_outline"],
                "properties": {
                    "assessment_methods":  {"type": "array", "items": {"type": "string"}},
                    "evaluation_criteria": {"type": "array", "items": {"type": "string"}},
                    "feedback_process":    {"type": "string"},
                    "appeal_process":      {"type": "string"},
                    "total_slides":        {"type": "integer"},
                    "slide_outline":       {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "assessment_methods":  [],
                "evaluation_criteria": [],
                "feedback_process":    "",
                "appeal_process":      "",
                "total_slides":        0,
                "slide_outline":       [],
            },
            lint_headings=["# 평가 방법:", "## 평가 유형", "## 평가 기준", "## 피드백 절차", "## PPT 구성 가이드"],
            validator_headings=["## 평가 유형", "## 평가 기준", "## 피드백 절차",
                                "## 이의신청 절차", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 평가 유형", "## 평가 기준"],
        ),
        DocumentSpec(
            key="operation_plan",
            template_file="edu_plan_kr/operation_plan.md.j2",
            json_schema={
                "type": "object",
                "required": ["facilities_and_staff", "annual_schedule", "budget_plan",
                             "emergency_plan", "total_slides", "slide_outline"],
                "properties": {
                    "facilities_and_staff": {"type": "array", "items": {"type": "string"}},
                    "annual_schedule":      {"type": "array", "items": {"type": "string"}},
                    "budget_plan":          {"type": "array", "items": {"type": "string"}},
                    "emergency_plan":       {"type": "string"},
                    "total_slides":         {"type": "integer"},
                    "slide_outline":        {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "facilities_and_staff": [],
                "annual_schedule":      [],
                "budget_plan":          [],
                "emergency_plan":       "",
                "total_slides":         0,
                "slide_outline":        [],
            },
            lint_headings=["# 운영 계획:", "## 시설 및 인력", "## 연간 일정", "## 예산 계획", "## PPT 구성 가이드"],
            validator_headings=["## 시설 및 인력", "## 연간 일정", "## 예산 계획",
                                "## 비상 운영 계획", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 시설 및 인력", "## 연간 일정"],
        ),
    ],
)

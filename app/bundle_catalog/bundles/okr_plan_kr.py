"""okr_plan_kr bundle — OKR 계획 (한국어).

4개 문서:
  1. objectives    — 목표 선언
  2. key_results   — 핵심 결과
  3. initiatives   — 이니셔티브 (실행 과제)
  4. tracking      — 트래킹 & 회고
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

OKR_PLAN_KR = BundleSpec(
    id="okr_plan_kr",
    name_ko="OKR 계획",
    name_en="OKR Plan",
    description_ko="팀·개인 OKR 수립을 위한 목표선언·핵심결과·이니셔티브·트래킹 4종 문서",
    icon="🎯",
    prompt_language="ko",
    prompt_hint=(
        "당신은 Google 방식 OKR을 5년 이상 도입·운영한 조직 전략 컨설턴트입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 이 목표가 조직의 상위 목표와 어떻게 연결되는가, "
        "(2) 핵심 결과가 측정 가능하고 도전적인가 (comfort zone을 20~30% 초과해야 함), "
        "(3) 이니셔티브가 핵심 결과를 실제로 달성하는 데 충분한가.\n"
        "- Objective는 영감을 주는 방향성 문장으로, 정성적이어야 합니다.\n"
        "- Key Result는 반드시 수치(숫자, %, 건수)로 측정 가능해야 합니다.\n"
        "- 이니셔티브는 KR을 달성하기 위한 구체적 실행 과제로, 담당자와 기한을 포함하세요.\n"
        "- 트래킹은 주간/월간 체크포인트와 회고 질문을 포함하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="internal",
    few_shot_example=(
        "## Objective\n"
        "2026년 Q2 말까지 AI 기반 고객 지원 자동화를 통해 운영 효율을 획기적으로 개선한다.\n"
        "\n"
        "## Key Results\n"
        "- **KR1**: 1차 응대 자동 해결률 45% → 72% 달성 (6월 30일 기준)\n"
        "- **KR2**: 평균 응대 시간 18분 → 6분으로 단축 (6월 30일 기준)\n"
        "- **KR3**: 고객 만족도(CSAT) 3.8점 → 4.3점/5점 달성 (분기 말 설문 기준)\n"
        "- **KR4**: AI 오분류율 12% → 3% 이하 (6월 30일 기준)\n"
    ),
    docs=[
        DocumentSpec(
            key="objectives",
            template_file="okr_plan_kr/objectives.md.j2",
            json_schema={
                "type": "object",
                "required": ["cycle", "team_context", "objective_statement",
                             "why_this_matters", "success_vision"],
                "properties": {
                    "cycle":               {"type": "string"},
                    "team_context":        {"type": "string"},
                    "objective_statement": {"type": "string"},
                    "why_this_matters":    {"type": "string"},
                    "success_vision":      {"type": "string"},
                },
            },
            stabilizer_defaults={
                "cycle":               "",
                "team_context":        "",
                "objective_statement": "",
                "why_this_matters":    "",
                "success_vision":      "",
            },
            lint_headings=["# 목표 선언:", "## OKR 사이클", "## 목표 (Objective)", "## 왜 이 목표인가"],
            validator_headings=["## OKR 사이클", "## 목표 (Objective)", "## 왜 이 목표인가",
                                "## 성공 비전"],
            critical_non_empty_headings=["## 목표 (Objective)", "## 왜 이 목표인가"],
        ),
        DocumentSpec(
            key="key_results",
            template_file="okr_plan_kr/key_results.md.j2",
            json_schema={
                "type": "object",
                "required": ["key_results", "baseline_values", "target_values",
                             "measurement_method", "data_sources"],
                "properties": {
                    "key_results":       {"type": "array", "items": {"type": "string"}},
                    "baseline_values":   {"type": "array", "items": {"type": "string"}},
                    "target_values":     {"type": "array", "items": {"type": "string"}},
                    "measurement_method":{"type": "array", "items": {"type": "string"}},
                    "data_sources":      {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "key_results":        [],
                "baseline_values":    [],
                "target_values":      [],
                "measurement_method": [],
                "data_sources":       [],
            },
            lint_headings=["# 핵심 결과:", "## KR 목록", "## 현재값 (Baseline)", "## 목표값 (Target)"],
            validator_headings=["## KR 목록", "## 현재값 (Baseline)", "## 목표값 (Target)",
                                "## 측정 방법", "## 데이터 소스"],
            critical_non_empty_headings=["## KR 목록", "## 목표값 (Target)"],
        ),
        DocumentSpec(
            key="initiatives",
            template_file="okr_plan_kr/initiatives.md.j2",
            json_schema={
                "type": "object",
                "required": ["initiative_list", "priority_order", "dependencies",
                             "resource_needs", "risk_factors"],
                "properties": {
                    "initiative_list": {"type": "array", "items": {"type": "string"}},
                    "priority_order":  {"type": "array", "items": {"type": "string"}},
                    "dependencies":    {"type": "array", "items": {"type": "string"}},
                    "resource_needs":  {"type": "array", "items": {"type": "string"}},
                    "risk_factors":    {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "initiative_list": [],
                "priority_order":  [],
                "dependencies":    [],
                "resource_needs":  [],
                "risk_factors":    [],
            },
            lint_headings=["# 이니셔티브:", "## 실행 과제 목록", "## 우선순위", "## 의존성"],
            validator_headings=["## 실행 과제 목록", "## 우선순위", "## 의존성",
                                "## 필요 자원", "## 리스크"],
            critical_non_empty_headings=["## 실행 과제 목록", "## 우선순위"],
        ),
        DocumentSpec(
            key="tracking",
            template_file="okr_plan_kr/tracking.md.j2",
            json_schema={
                "type": "object",
                "required": ["weekly_checkin", "monthly_review", "retrospective_questions",
                             "escalation_criteria", "celebration_milestones"],
                "properties": {
                    "weekly_checkin":          {"type": "array", "items": {"type": "string"}},
                    "monthly_review":          {"type": "array", "items": {"type": "string"}},
                    "retrospective_questions": {"type": "array", "items": {"type": "string"}},
                    "escalation_criteria":     {"type": "array", "items": {"type": "string"}},
                    "celebration_milestones":  {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "weekly_checkin":          [],
                "monthly_review":          [],
                "retrospective_questions": [],
                "escalation_criteria":     [],
                "celebration_milestones":  [],
            },
            lint_headings=["# 트래킹 & 회고:", "## 주간 체크인", "## 월간 리뷰", "## 회고 질문"],
            validator_headings=["## 주간 체크인", "## 월간 리뷰", "## 회고 질문",
                                "## 에스컬레이션 기준", "## 성과 축하"],
            critical_non_empty_headings=["## 주간 체크인", "## 회고 질문"],
        ),
    ],
)

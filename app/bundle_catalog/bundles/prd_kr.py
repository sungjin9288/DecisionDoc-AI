"""prd_kr bundle — 제품 요구사항 문서 (한국어).

4개 문서:
  1. product_overview          — 제품 개요 & 비전
  2. functional_requirements   — 기능 요구사항
  3. nonfunctional_requirements — 비기능 요구사항
  4. priority_matrix           — 우선순위 매트릭스
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

PRD_KR = BundleSpec(
    id="prd_kr",
    name_ko="제품 요구사항",
    name_en="Product Requirements",
    description_ko="스타트업·IT팀 PRD 작성을 위한 제품개요·기능요구사항·비기능요구사항·우선순위매트릭스 4종 문서",
    icon="📋",
    prompt_language="ko",
    prompt_hint=(
        "당신은 Google·카카오 출신의 시니어 프로덕트 매니저로, 수십 개의 PRD를 작성하고 팀을 이끈 경험이 있습니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 이 제품이 해결하는 핵심 고객 문제는 무엇인가, "
        "(2) 각 기능 요구사항이 비즈니스 목표와 어떻게 연결되는가, (3) 개발팀이 바로 작업을 시작할 수 있을 만큼 구체적인가.\n"
        "- 모든 기능 요구사항은 '사용자는 ~할 수 있어야 한다' 형식의 User Story로 작성하세요.\n"
        "- 비기능 요구사항은 측정 가능한 수치(응답시간 < 200ms, 가용성 99.9% 등)로 명시하세요.\n"
        "- 우선순위는 MoSCoW(Must/Should/Could/Won't) 프레임워크를 사용하세요.\n"
        "- 각 기능에는 수용 기준(Acceptance Criteria)을 포함하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="consulting",
    few_shot_example=(
        "## 제품 개요\n"
        "카카오페이 앱 내 '영수증 자동 분류' 기능을 신규 도입한다.\n"
        "월 4,200만 건의 결제 내역을 AI가 카테고리별로 자동 분류하여 소비 패턴 분석 리포트를 제공한다.\n"
        "\n"
        "## 기능 요구사항 (User Story)\n"
        "- **Must**: As a 가계부 사용자, 결제 직후 3초 내에 카테고리 자동 태깅을 받아, 수작업 분류 시간을 없앨 수 있다.\n"
        "- **Must**: As a 사용자, 월간 소비 리포트에서 카테고리별 지출 비율과 전월 대비 증감을 확인할 수 있다.\n"
        "- **Should**: As a 사용자, AI 분류 결과가 틀렸을 때 1번 탭으로 수정할 수 있다.\n"
        "- **Could**: As a Premium 사용자, 예산 초과 시 푸시 알림을 받을 수 있다.\n"
    ),
    docs=[
        DocumentSpec(
            key="product_overview",
            template_file="prd_kr/product_overview.md.j2",
            json_schema={
                "type": "object",
                "required": ["product_vision", "problem_statement", "target_users",
                             "success_metrics", "scope_boundaries"],
                "properties": {
                    "product_vision":   {"type": "string"},
                    "problem_statement":{"type": "string"},
                    "target_users":     {"type": "array", "items": {"type": "string"}},
                    "success_metrics":  {"type": "array", "items": {"type": "string"}},
                    "scope_boundaries": {"type": "object",
                                        "properties": {"in_scope": {"type": "array", "items": {"type": "string"}},
                                                       "out_of_scope": {"type": "array", "items": {"type": "string"}}}},
                },
            },
            stabilizer_defaults={
                "product_vision":    "",
                "problem_statement": "",
                "target_users":      [],
                "success_metrics":   [],
                "scope_boundaries":  {"in_scope": [], "out_of_scope": []},
            },
            lint_headings=["# 제품 개요:", "## 제품 비전", "## 문제 정의", "## 대상 사용자"],
            validator_headings=["## 제품 비전", "## 문제 정의", "## 대상 사용자",
                                "## 성공 지표", "## 범위 정의"],
            critical_non_empty_headings=["## 제품 비전", "## 문제 정의"],
        ),
        DocumentSpec(
            key="functional_requirements",
            template_file="prd_kr/functional_requirements.md.j2",
            json_schema={
                "type": "object",
                "required": ["user_stories", "acceptance_criteria", "edge_cases", "dependencies"],
                "properties": {
                    "user_stories":       {"type": "array", "items": {"type": "string"}},
                    "acceptance_criteria":{"type": "array", "items": {"type": "string"}},
                    "edge_cases":         {"type": "array", "items": {"type": "string"}},
                    "dependencies":       {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "user_stories":        [],
                "acceptance_criteria": [],
                "edge_cases":          [],
                "dependencies":        [],
            },
            lint_headings=["# 기능 요구사항:", "## User Stories", "## 수용 기준", "## 엣지 케이스"],
            validator_headings=["## User Stories", "## 수용 기준 (Acceptance Criteria)",
                                "## 엣지 케이스", "## 의존성"],
            critical_non_empty_headings=["## User Stories", "## 수용 기준 (Acceptance Criteria)"],
        ),
        DocumentSpec(
            key="nonfunctional_requirements",
            template_file="prd_kr/nonfunctional_requirements.md.j2",
            json_schema={
                "type": "object",
                "required": ["performance", "security", "scalability", "accessibility", "constraints"],
                "properties": {
                    "performance":   {"type": "array", "items": {"type": "string"}},
                    "security":      {"type": "array", "items": {"type": "string"}},
                    "scalability":   {"type": "array", "items": {"type": "string"}},
                    "accessibility": {"type": "array", "items": {"type": "string"}},
                    "constraints":   {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "performance":   [],
                "security":      [],
                "scalability":   [],
                "accessibility": [],
                "constraints":   [],
            },
            lint_headings=["# 비기능 요구사항:", "## 성능", "## 보안", "## 확장성"],
            validator_headings=["## 성능 (Performance)", "## 보안 (Security)",
                                "## 확장성 (Scalability)", "## 접근성", "## 제약사항"],
            critical_non_empty_headings=["## 성능 (Performance)", "## 보안 (Security)"],
        ),
        DocumentSpec(
            key="priority_matrix",
            template_file="prd_kr/priority_matrix.md.j2",
            json_schema={
                "type": "object",
                "required": ["must_have", "should_have", "could_have", "wont_have",
                             "release_phases"],
                "properties": {
                    "must_have":     {"type": "array", "items": {"type": "string"}},
                    "should_have":   {"type": "array", "items": {"type": "string"}},
                    "could_have":    {"type": "array", "items": {"type": "string"}},
                    "wont_have":     {"type": "array", "items": {"type": "string"}},
                    "release_phases":{"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "must_have":      [],
                "should_have":    [],
                "could_have":     [],
                "wont_have":      [],
                "release_phases": [],
            },
            lint_headings=["# 우선순위 매트릭스:", "## Must Have", "## Should Have", "## Could Have"],
            validator_headings=["## Must Have", "## Should Have", "## Could Have",
                                "## Won't Have", "## 출시 단계"],
            critical_non_empty_headings=["## Must Have", "## Should Have"],
        ),
    ],
)

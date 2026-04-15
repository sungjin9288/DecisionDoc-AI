"""proposal_kr bundle — 나라장터 AI 사업 제안서 (한국어).

4개 문서로 구성:
  1. business_understanding — 사업 이해
  2. tech_proposal          — 기술제안서
  3. execution_plan         — 수행계획서
  4. expected_impact        — 기대효과
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

PROPOSAL_KR = BundleSpec(
    id="proposal_kr",
    name_ko="AI 사업 제안서",
    name_en="Government AI Proposal",
    description_ko="나라장터 공공조달 AI 사업 제안서. 사업 이해·기술제안서·수행계획서·기대효과 4종 포함.",
    icon="🏛️",
    prompt_language="ko",
    prompt_hint=(
        "당신은 나라장터 공공조달 AI 사업 제안서 전문 컨설턴트로, 정부 평가위원의 시각으로 문서를 작성합니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 평가위원이 가장 주목할 차별화 포인트는 무엇인가, "
        "(2) 예산 대비 효과를 어떻게 수치로 증명할 것인가, (3) 기술적 실현 가능성을 어떻게 설득할 것인가.\n"
        "- executive_summary, technical_summary, delivery_summary, impact_summary 는 각각 3~5문장 분량으로 작성하고 첫 문장은 결론형 문장으로 시작하세요.\n"
        "- 모든 narrative 문장은 '문제 → 제안 → 입증 근거/운영 방식' 흐름을 유지하고, 추상적 슬로건만 단독으로 쓰지 마세요.\n"
        "- 제안서 문장은 평가위원이 바로 점수를 줄 수 있도록 차별화 포인트, 정량 KPI, 승인 기준, 산출물 제출 시점을 구체적으로 적으세요.\n"
        "- project_objectives는 `목표 항목 | 정량·정성 목표 | 측정 기준` 형식의 row 목록으로 작성하세요.\n"
        "- evaluation_alignment는 `평가 관점 | 대응 전략 | 입증 근거` 형식의 row 목록으로 작성하세요.\n"
        "- target_users는 `사용자군 | 주요 역할·니즈 | 기대 변화` 형식의 row 목록으로 작성하세요.\n"
        "- tech_stack은 `구성 영역 | 적용 기술 | 적용 목적` 형식의 row 목록으로 작성하세요.\n"
        "- implementation_principles는 `설계 원칙 | 적용 방안 | 검증 포인트` 형식의 row 목록으로 작성하세요.\n"
        "- security_measures는 `보안 영역 | 통제 방안 | 운영 기준` 형식의 row 목록으로 작성하세요.\n"
        "- differentiation은 `차별화 포인트 | 경쟁 우위 | 입증 근거` 형식의 row 목록으로 작성하세요.\n"
        "- team_structure는 `역할 | 인원·등급 | 책임 | 투입 시점` 형식의 row 목록으로 작성하세요.\n"
        "- milestones는 `마일스톤 | 시점 | 완료 기준 | 핵심 산출물` 형식의 row 목록으로 작성하세요.\n"
        "- risk_management는 `리스크 | 영향 | 대응 방안` 형식의 row 목록으로 작성하세요.\n"
        "- deliverables는 `산출물 | 제출 시점 | 형식 | 검수 방법` 형식의 row 목록으로 작성하세요.\n"
        "- quantitative_effects는 `지표 | 현재 수준 | 목표 수준 | 기대 효과` 형식의 row 목록으로 작성하세요.\n"
        "- qualitative_effects는 `영역 | 기대 효과 | 활용 관점` 형식의 row 목록으로 작성하세요.\n"
        "- kpi_commitments는 `핵심 KPI | 목표값 | 산정 기준 | 달성 시점` 형식의 row 목록으로 작성하세요.\n"
        "- monitoring_plan은 `모니터링 항목 | 주기 | 책임 | 목표 기준` 형식의 row 목록으로 작성하세요.\n"
        "- 공식적이고 격식 있는 한국어 문체를 사용하세요.\n"
        "- slide_outline 은 PPT 슬라이드별 구성안입니다. page·title·key_content·design_tip 을 채우세요.\n"
        "- 각 항목은 한국어로 작성하세요."
    ),
    category="consulting",
    few_shot_example=(
        "## 제안 요약\n"
        "본 제안은 복지급여 심사 업무의 병목을 해소하고 정책 집행의 예측 가능성을 높이기 위해, 데이터 통합·AI 자동심사·운영 통제 체계를 하나의 사업 범위로 설계한 안입니다. "
        "평가위원이 확인해야 할 사업 필요성, 기술 실현 가능성, 예산 대비 효과를 각각 별도 근거로 제시하지 않고 동일한 KPI 체계 안에서 연결해 설명하는 것이 핵심입니다. "
        "착수 3개월 내에는 가시적 프로토타입과 운영 대시보드를 제시하고, 중간검증 이후 전국 확산 여부를 판단할 수 있도록 단계별 승인 기준을 문서화합니다.\n\n"
        "## 사업 목적 및 필요성\n"
        "보건복지부는 연간 복지급여 신청 건수 840만 건 중 68%가 단순 반복 서류심사로 처리 인력의 "
        "73%가 소요되는 비효율 구조를 AI 자동심사 시스템 도입으로 개선하고자 한다. "
        "현재 심사 평균 소요일 21일을 7일로 단축하고, 오심률 3.2%를 0.5% 이하로 낮추는 것이 목표이다.\n\n"
        "## 평가 대응 포인트\n"
        "| 평가 관점 | 대응 전략 | 입증 근거 |\n"
        "|-----------|----------|-----------|\n"
        "| 사업 이해도 | 복지급여 심사 지연과 오심 문제를 정책 KPI와 직접 연결하여 제안 배경을 구성 | 사업 배경, 현황 문제점, 목표지표 |\n"
        "| 실행 가능성 | 12개월 로드맵과 단계별 승인 게이트로 납품 현실성을 제시 | 수행 계획, 마일스톤, 산출물 표 |\n"
        "| 효과성 | 처리시간·오심률·운영비 절감 지표를 사업 종료 시점 KPI로 고정 | 기대효과, ROI, 성과 모니터링 계획 |\n\n"
        "## 기술 제안 요약\n"
        "- **AI 엔진**: OCR + NLP 기반 서류 자동 판독 (정확도 목표 98.5%)\n"
        "- **아키텍처**: 온프레미스 하이브리드 클라우드 (개인정보 비식별화 후 클라우드 AI 활용)\n"
        "- **보안**: CC인증 등급 EAL4+, 개인정보 처리 시스템 ISMS-P 인증 보유\n"
        "- **차별점①**: 실시간 부정수급 탐지 모듈 — 유사 급여 중복 신청 98.2% 자동 차단\n"
        "- **차별점②**: 행정 DB 연계 자동 검증 — 가족관계·소득·재산 정보 즉시 대조\n"
        "- **차별점③**: 심사관 보조 UI — 이상 케이스 자동 플래그 + 근거 요약 제공\n\n"
        "## 수행 계획 (12개월)\n"
        "- 1단계 착수·분석 (1~2개월): 현업 인터뷰, 업무 프로세스 분석, 착수보고서 제출\n"
        "- 2단계 설계·학습 (3~5개월): 시스템 설계, AI 모델 학습 데이터 구축 (50만 건)\n"
        "- 3단계 개발·시범 (6~9개월): 핵심 기능 개발, 선도 주민센터 3개소 시범 운영\n"
        "- 4단계 전개·완료 (10~12개월): 전국 256개 주민센터 확산, 완료보고\n\n"
        "## 정량적 기대 효과\n"
        "- **심사 기간**: 21일 → 7일 (67% 단축) / 연간 비용 절감 43억 원\n"
        "- **오심률**: 3.2% → 0.5% (84% 개선) / 부정수급 환수 연 8.2억 원 추가\n"
        "- **처리 가능 건수**: 일 3,900건 → 9,600건 (146% 증가)\n"
        "- **시민 만족도**: 복지서비스 만족도 현 61점 → 목표 83점 (22점 상승)\n"
    ),
    docs=[
        DocumentSpec(
            key="business_understanding",
            template_file="proposal_kr/business_understanding.md.j2",
            json_schema={
                "type": "object",
                "required": ["executive_summary", "project_background", "current_issues", "project_objectives",
                             "evaluation_alignment",
                             "target_users", "scope_summary", "total_slides", "slide_outline"],
                "properties": {
                    "executive_summary": {"type": "string"},
                    "project_background": {"type": "string"},
                    "current_issues":     {"type": "array", "items": {"type": "string"}},
                    "project_objectives": {"type": "array", "items": {"type": "string"}},
                    "evaluation_alignment": {"type": "array", "items": {"type": "string"}},
                    "target_users":       {"type": "array", "items": {"type": "string"}},
                    "scope_summary":      {"type": "string"},
                    "total_slides":       {"type": "integer"},
                    "slide_outline":      {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "executive_summary": "",
                "project_background": "",
                "current_issues":     [],
                "project_objectives": [],
                "evaluation_alignment": [],
                "target_users":       [],
                "scope_summary":      "",
                "total_slides":       0,
                "slide_outline":      [],
            },
            lint_headings=["# 사업 이해:", "## 제안 요약", "## 사업 배경", "## 현황 및 문제점", "## 사업 목표", "## PPT 구성 가이드"],
            validator_headings=["## 사업 배경", "## 현황 및 문제점", "## 사업 목표",
                                "## 평가 대응 포인트", "## 대상 사용자", "## 사업 범위", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 제안 요약", "## 사업 배경", "## 사업 목표"],
        ),
        DocumentSpec(
            key="tech_proposal",
            template_file="proposal_kr/tech_proposal.md.j2",
            json_schema={
                "type": "object",
                "required": ["technical_summary", "tech_stack", "architecture_overview", "ai_approach",
                             "implementation_principles",
                             "security_measures", "differentiation", "total_slides", "slide_outline"],
                "properties": {
                    "technical_summary":      {"type": "string"},
                    "tech_stack":             {"type": "array", "items": {"type": "string"}},
                    "architecture_overview":  {"type": "string"},
                    "ai_approach":            {"type": "string"},
                    "implementation_principles": {"type": "array", "items": {"type": "string"}},
                    "security_measures":      {"type": "array", "items": {"type": "string"}},
                    "differentiation":        {"type": "array", "items": {"type": "string"}},
                    "total_slides":           {"type": "integer"},
                    "slide_outline":          {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "technical_summary":     "",
                "tech_stack":            [],
                "architecture_overview": "",
                "ai_approach":           "",
                "implementation_principles": [],
                "security_measures":     [],
                "differentiation":       [],
                "total_slides":          0,
                "slide_outline":         [],
            },
            lint_headings=["# 기술제안서:", "## 기술 제안 요약", "## 적용 기술", "## 시스템 아키텍처", "## AI 접근 방식", "## PPT 구성 가이드"],
            validator_headings=["## 적용 기술", "## 시스템 아키텍처", "## AI 접근 방식",
                                "## 기술 구현 원칙", "## 보안 대책", "## 차별성", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 기술 제안 요약", "## 적용 기술", "## 시스템 아키텍처", "## AI 접근 방식"],
        ),
        DocumentSpec(
            key="execution_plan",
            template_file="proposal_kr/execution_plan.md.j2",
            json_schema={
                "type": "object",
                "required": ["delivery_summary", "team_structure", "milestones", "methodology",
                             "governance_plan",
                             "risk_management", "deliverables", "total_slides", "slide_outline"],
                "properties": {
                    "delivery_summary": {"type": "string"},
                    "team_structure":   {"type": "array", "items": {"type": "string"}},
                    "milestones":       {"type": "array", "items": {"type": "string"}},
                    "methodology":      {"type": "string"},
                    "governance_plan":  {"type": "string"},
                    "risk_management":  {"type": "array", "items": {"type": "string"}},
                    "deliverables":     {"type": "array", "items": {"type": "string"}},
                    "total_slides":     {"type": "integer"},
                    "slide_outline":    {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "delivery_summary": "",
                "team_structure":  [],
                "milestones":      [],
                "methodology":     "",
                "governance_plan": "",
                "risk_management": [],
                "deliverables":    [],
                "total_slides":    0,
                "slide_outline":   [],
            },
            lint_headings=["# 수행계획서:", "## 수행 총괄 요약", "## 추진 체계", "## 추진 일정", "## 수행 방법론", "## PPT 구성 가이드"],
            validator_headings=["## 추진 체계", "## 추진 일정", "## 수행 방법론",
                                "## 거버넌스 및 보고 체계", "## 리스크 관리", "## 산출물", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 수행 총괄 요약", "## 추진 체계", "## 추진 일정", "## 수행 방법론"],
        ),
        DocumentSpec(
            key="expected_impact",
            template_file="proposal_kr/expected_impact.md.j2",
            json_schema={
                "type": "object",
                "required": ["impact_summary", "quantitative_effects", "qualitative_effects", "social_value",
                             "kpi_commitments",
                             "roi_estimate", "monitoring_plan", "total_slides", "slide_outline"],
                "properties": {
                    "impact_summary":         {"type": "string"},
                    "quantitative_effects": {"type": "array", "items": {"type": "string"}},
                    "qualitative_effects":  {"type": "array", "items": {"type": "string"}},
                    "social_value":         {"type": "string"},
                    "kpi_commitments":      {"type": "array", "items": {"type": "string"}},
                    "roi_estimate":         {"type": "string"},
                    "monitoring_plan":      {"type": "array", "items": {"type": "string"}},
                    "total_slides":         {"type": "integer"},
                    "slide_outline":        {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "impact_summary":         "",
                "quantitative_effects": [],
                "qualitative_effects":  [],
                "social_value":         "",
                "kpi_commitments":      [],
                "roi_estimate":         "",
                "monitoring_plan":      [],
                "total_slides":         0,
                "slide_outline":        [],
            },
            lint_headings=["# 기대효과:", "## 효과 요약", "## 정량적 효과", "## 정성적 효과", "## 사회적 가치", "## PPT 구성 가이드"],
            validator_headings=["## 정량적 효과", "## 정성적 효과", "## 사회적 가치",
                                "## KPI 달성 약속", "## 투자 대비 효과", "## 성과 모니터링", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 효과 요약", "## 정량적 효과", "## 정성적 효과"],
        ),
    ],
)

"""marketing_plan_kr bundle — 마케팅 기획서 (한국어).

3개 문서:
  1. market_analysis   — 시장 분석
  2. strategy_plan     — 마케팅 전략
  3. action_roadmap    — 실행 로드맵
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

MARKETING_PLAN_KR = BundleSpec(
    id="marketing_plan_kr",
    name_ko="마케팅 기획서",
    name_en="Marketing Plan",
    description_ko="시장 분석·마케팅 전략·실행 로드맵 3종. 신제품 출시·캠페인·브랜드 전략 수립에 활용.",
    icon="📣",
    prompt_language="ko",
    prompt_hint=(
        "당신은 대기업 마케팅 전략팀 출신의 마케팅 기획 전문가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 타깃 고객의 핵심 페인포인트는 무엇인가, "
        "(2) 경쟁사 대비 차별화 메시지는 무엇인가, (3) 예산 대비 ROI를 극대화할 채널은 무엇인가.\n"
        "- 시장 분석은 TAM/SAM/SOM 관점으로 수치화하세요.\n"
        "- 전략은 4P(Product·Price·Place·Promotion) 또는 STP 프레임워크를 활용하세요.\n"
        "- 실행 계획은 월 단위 타임라인과 KPI를 포함하세요.\n"
        "- 채널별 예산 배분 비율을 구체적으로 제시하세요.\n"
        "- 공식적이고 설득력 있는 한국어 문체를 사용하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="work",
    few_shot_example=(
        "## 시장 현황 분석\n"
        "국내 B2B SaaS 시장 규모는 2025년 4.2조 원으로 전년 대비 23% 성장하였으며, "
        "2028년까지 CAGR 27%로 8.9조 원에 도달할 전망이다 (IDC Korea, 2025).\n"
        "- **TAM**: 국내 전체 기업용 소프트웨어 시장 — 21조 원\n"
        "- **SAM**: AI 기반 문서 자동화 솔루션 잠재 시장 — 1.4조 원\n"
        "- **SOM**: 초기 3년 내 공략 가능 시장 — 210억 원 (중견·대기업 HR/기획팀 3,000개사)\n\n"
        "## 마케팅 전략\n"
        "**포지셔닝**: '한국 기업 문서 업무 시간 70% 절감' — 실측 데이터 기반 신뢰 포지셔닝\n"
        "- **Product**: AI 문서 생성 + 기업 스타일 학습 기능으로 기존 솔루션과 차별화\n"
        "- **Price**: Freemium(월 5건 무료) → Pro(월 49,000원) → Enterprise(맞춤 협의)\n"
        "- **Place**: 직접 판매(인바운드) 70% + 파트너사(회계·컨설팅펌) 30%\n"
        "- **Promotion**: 콘텐츠 마케팅(업무 효율 사례) + LinkedIn 광고 + 공공기관 레퍼런스 구축\n\n"
        "## 실행 로드맵 (6개월)\n"
        "| 월 | 주요 활동 | KPI | 예산 |\n"
        "|---|---------|-----|------|\n"
        "| 1~2월 | 브랜드 사이트 개편, 사례 3건 발행 | 방문자 5,000/월 | 800만 원 |\n"
        "| 3~4월 | LinkedIn 광고 런칭, 웨비나 2회 | 리드 200건 | 1,200만 원 |\n"
        "| 5~6월 | 파트너사 2곳 온보딩, 공공기관 PoC | 유료 전환 40건 | 900만 원 |\n"
    ),
    docs=[
        DocumentSpec(
            key="market_analysis",
            template_file="marketing_plan_kr/market_analysis.md.j2",
            json_schema={
                "type": "object",
                "required": ["market_overview", "target_segments", "competitor_analysis",
                             "market_trends", "opportunities_threats"],
                "properties": {
                    "market_overview":       {"type": "string"},
                    "target_segments":       {"type": "array", "items": {"type": "string"}},
                    "competitor_analysis":   {"type": "array", "items": {"type": "string"}},
                    "market_trends":         {"type": "array", "items": {"type": "string"}},
                    "opportunities_threats": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "market_overview":       "",
                "target_segments":       [],
                "competitor_analysis":   [],
                "market_trends":         [],
                "opportunities_threats": [],
            },
            lint_headings=["# 시장 분석:", "## 시장 현황", "## 타깃 고객"],
            validator_headings=["## 시장 현황", "## 타깃 고객", "## 경쟁사 분석",
                                "## 시장 트렌드", "## 기회 및 위협"],
            critical_non_empty_headings=["## 시장 현황", "## 타깃 고객"],
        ),
        DocumentSpec(
            key="strategy_plan",
            template_file="marketing_plan_kr/strategy_plan.md.j2",
            json_schema={
                "type": "object",
                "required": ["positioning", "value_proposition", "channel_strategy",
                             "messaging_framework", "budget_allocation"],
                "properties": {
                    "positioning":          {"type": "string"},
                    "value_proposition":    {"type": "string"},
                    "channel_strategy":     {"type": "array", "items": {"type": "string"}},
                    "messaging_framework":  {"type": "array", "items": {"type": "string"}},
                    "budget_allocation":    {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "positioning":         "",
                "value_proposition":   "",
                "channel_strategy":    [],
                "messaging_framework": [],
                "budget_allocation":   [],
            },
            lint_headings=["# 마케팅 전략:", "## 포지셔닝", "## 핵심 가치 제안"],
            validator_headings=["## 포지셔닝", "## 핵심 가치 제안", "## 채널 전략",
                                "## 메시지 프레임워크", "## 예산 배분"],
            critical_non_empty_headings=["## 포지셔닝", "## 핵심 가치 제안"],
        ),
        DocumentSpec(
            key="action_roadmap",
            template_file="marketing_plan_kr/action_roadmap.md.j2",
            json_schema={
                "type": "object",
                "required": ["quarterly_goals", "monthly_activities", "kpi_targets",
                             "resource_requirements", "success_metrics"],
                "properties": {
                    "quarterly_goals":      {"type": "array", "items": {"type": "string"}},
                    "monthly_activities":   {"type": "array", "items": {"type": "string"}},
                    "kpi_targets":          {"type": "array", "items": {"type": "string"}},
                    "resource_requirements": {"type": "array", "items": {"type": "string"}},
                    "success_metrics":      {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "quarterly_goals":       [],
                "monthly_activities":    [],
                "kpi_targets":           [],
                "resource_requirements": [],
                "success_metrics":       [],
            },
            lint_headings=["# 실행 로드맵:", "## 분기별 목표", "## 월별 활동 계획"],
            validator_headings=["## 분기별 목표", "## 월별 활동 계획", "## KPI 목표",
                                "## 필요 리소스", "## 성과 측정 지표"],
            critical_non_empty_headings=["## 분기별 목표", "## KPI 목표"],
        ),
    ],
)

"""investment_pitch_kr bundle — 투자제안서 / IR 자료 (한국어).

3개 문서:
  1. business_overview      — 사업 개요
  2. market_opportunity     — 시장 기회 및 성장 전략
  3. financial_projection   — 재무 계획 및 투자 조건
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

INVESTMENT_PITCH_KR = BundleSpec(
    id="investment_pitch_kr",
    name_ko="투자제안서 (IR)",
    name_en="Investment Pitch (IR)",
    description_ko="사업 개요·시장 기회·재무 계획 3종. 스타트업 시리즈 투자 및 사업 파트너십 유치용.",
    icon="💼",
    prompt_language="ko",
    prompt_hint=(
        "당신은 벤처캐피털 출신의 IR 전략 전문가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 투자자가 가장 우려할 리스크는 무엇이고 어떻게 해소할 것인가, "
        "(2) 유사 사례(경쟁사, 글로벌 성공 사례)와의 차별점은 명확한가, "
        "(3) 재무 가정이 현실적이고 검증 가능한가.\n"
        "- 팀 경쟁력을 가장 먼저 부각하세요 (VC는 팀에 투자한다).\n"
        "- 시장 규모는 Bottom-up 방식으로 추정하고 근거를 제시하세요.\n"
        "- 수익 모델과 Unit Economics(LTV/CAC)를 수치로 제시하세요.\n"
        "- 투자금 사용처를 항목별로 구체화하세요 (마일스톤 연계).\n"
        "- 간결하고 임팩트 있는 한국어 문체를 사용하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="work",
    few_shot_example=(
        "## 회사 소개\n"
        "**DecisionDoc AI**는 기업 내 반복적인 문서 작성 업무를 AI로 자동화하는 B2B SaaS 플랫폼이다. "
        "평균 3시간 소요되는 기획서·제안서 작성 시간을 15분으로 단축(95% 절감)하며, "
        "2026년 2월 출시 후 3개월 만에 엔터프라이즈 고객 47개사, MRR 2,800만 원을 달성했다.\n\n"
        "**핵심 팀**\n"
        "- CEO 김철수: 전 삼성SDS AI플랫폼팀 리드, KAIST CS 박사\n"
        "- CTO 이영희: 전 네이버 클로바 NLP 엔지니어, 특허 8건 보유\n"
        "- CSO 박민준: 전 맥킨지 시니어컨설턴트, 공공·금융 도메인 10년\n\n"
        "## 시장 기회\n"
        "- **TAM**: 글로벌 기업용 AI 문서 자동화 시장 — $48B (2028, Gartner)\n"
        "- **SAM**: 한국 중견·대기업 기획·영업·HR 부서 — 1.4조 원\n"
        "- **SOM**: 3년 내 국내 Top 500 기업 10% 침투 — 140억 원\n"
        "- 국내 문서 작업 비효율 비용: 직장인 1인당 연 1,200만 원 (McKinsey 2024)\n\n"
        "## 재무 계획\n"
        "| 지표 | 2026 (실적) | 2027 (목표) | 2028 (목표) |\n"
        "|------|------------|------------|------------|\n"
        "| MRR | 2,800만 원 | 1.8억 원 | 5.2억 원 |\n"
        "| 고객사 | 47개 | 320개 | 900개 |\n"
        "| ARR | 3.4억 원 | 21.6억 원 | 62.4억 원 |\n"
        "| CAC | 120만 원 | 85만 원 | 65만 원 |\n"
        "| LTV | 840만 원 | 1,200만 원 | 1,560만 원 |\n\n"
        "**투자금 사용처 (Series A 30억 원)**\n"
        "- 엔지니어링 인력 채용 (40%): AI 모델 고도화 + 엔터프라이즈 보안 강화\n"
        "- 영업·마케팅 (35%): 대기업 영업팀 구성, 파트너 채널 2개 구축\n"
        "- 인프라·운영 (15%): AWS 비용 최적화, ISMS-P 인증 취득\n"
        "- 운전자본 예비 (10%): 12개월 런웨이 확보\n"
    ),
    docs=[
        DocumentSpec(
            key="business_overview",
            template_file="investment_pitch_kr/business_overview.md.j2",
            json_schema={
                "type": "object",
                "required": ["company_summary", "problem_statement", "solution_description",
                             "team_highlights", "traction_metrics"],
                "properties": {
                    "company_summary":      {"type": "string"},
                    "problem_statement":    {"type": "string"},
                    "solution_description": {"type": "string"},
                    "team_highlights":      {"type": "array", "items": {"type": "string"}},
                    "traction_metrics":     {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "company_summary":      "",
                "problem_statement":    "",
                "solution_description": "",
                "team_highlights":      [],
                "traction_metrics":     [],
            },
            lint_headings=["# 사업 개요:", "## 회사 소개", "## 문제 정의"],
            validator_headings=["## 회사 소개", "## 문제 정의", "## 솔루션",
                                "## 팀 소개", "## 성과 지표"],
            critical_non_empty_headings=["## 회사 소개", "## 솔루션"],
        ),
        DocumentSpec(
            key="market_opportunity",
            template_file="investment_pitch_kr/market_opportunity.md.j2",
            json_schema={
                "type": "object",
                "required": ["market_size", "growth_strategy", "competitive_advantage",
                             "business_model", "go_to_market"],
                "properties": {
                    "market_size":           {"type": "string"},
                    "growth_strategy":       {"type": "array", "items": {"type": "string"}},
                    "competitive_advantage": {"type": "array", "items": {"type": "string"}},
                    "business_model":        {"type": "string"},
                    "go_to_market":          {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "market_size":           "",
                "growth_strategy":       [],
                "competitive_advantage": [],
                "business_model":        "",
                "go_to_market":          [],
            },
            lint_headings=["# 시장 기회:", "## 시장 규모", "## 비즈니스 모델"],
            validator_headings=["## 시장 규모", "## 성장 전략", "## 경쟁 우위",
                                "## 비즈니스 모델", "## 시장 진입 전략"],
            critical_non_empty_headings=["## 시장 규모", "## 비즈니스 모델"],
        ),
        DocumentSpec(
            key="financial_projection",
            template_file="investment_pitch_kr/financial_projection.md.j2",
            json_schema={
                "type": "object",
                "required": ["revenue_forecast", "unit_economics", "funding_ask",
                             "use_of_funds", "milestones"],
                "properties": {
                    "revenue_forecast": {"type": "array", "items": {"type": "string"}},
                    "unit_economics":   {"type": "array", "items": {"type": "string"}},
                    "funding_ask":      {"type": "string"},
                    "use_of_funds":     {"type": "array", "items": {"type": "string"}},
                    "milestones":       {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "revenue_forecast": [],
                "unit_economics":   [],
                "funding_ask":      "",
                "use_of_funds":     [],
                "milestones":       [],
            },
            lint_headings=["# 재무 계획:", "## 매출 전망", "## 투자 요청"],
            validator_headings=["## 매출 전망", "## Unit Economics", "## 투자 요청",
                                "## 투자금 사용처", "## 주요 마일스톤"],
            critical_non_empty_headings=["## 매출 전망", "## 투자 요청"],
        ),
    ],
)

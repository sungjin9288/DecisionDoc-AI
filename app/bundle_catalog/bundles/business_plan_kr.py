"""business_plan_kr bundle — 사업계획서 / 신사업 기획 (한국어).

4개 문서:
  1. business_overview  — 사업 개요
  2. market_analysis    — 시장 분석
  3. business_model     — 사업 모델
  4. execution_roadmap  — 실행 로드맵
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

BUSINESS_PLAN_KR = BundleSpec(
    id="business_plan_kr",
    name_ko="사업계획서",
    name_en="Business Plan",
    description_ko="스타트업·중소기업 신사업 기획을 위한 사업개요·시장분석·사업모델·실행로드맵 4종 문서",
    icon="📊",
    prompt_language="ko",
    prompt_hint=(
        "당신은 Series A 투자 유치를 도운 경험 많은 스타트업 컨설턴트입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 투자자가 가장 묻는 질문은 무엇인가, "
        "(2) 시장 데이터로 성장 가능성을 어떻게 증명할 것인가, (3) 수익 모델의 핵심 가정은 무엇인가.\n"
        "- 시장 규모는 TAM/SAM/SOM 프레임으로 구체적 수치를 제시하세요.\n"
        "- 경쟁사는 실제 기업명과 비교 우위를 명시하세요 (예: 'X사 대비 가격 30% 저렴, Y사 대비 처리속도 2배').\n"
        "- 수익 구조는 단계별 예상 매출과 수익성 달성 시점을 포함하세요.\n"
        "- 투자자 또는 경영진이 읽는 사업계획서 스타일로 작성하세요.\n"
        "- slide_outline 은 PPT 슬라이드별 구성안입니다. page·title·key_content·design_tip 을 채우세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="consulting",
    few_shot_example=(
        "## 시장 분석\n"
        "한국 B2B SaaS 시장 규모 2025년 3.2조 원, 연평균 성장률(CAGR) 18%.\n"
        "TAM: 국내 중소기업 결제 자동화 시장 8,500억 원 / SAM: 연 매출 50~500억 원 IT투자 여력 보유 기업 2,400억 원 / SOM: 1년차 공략 목표 24억 원.\n"
        "\n"
        "## 수익 모델\n"
        "- **SaaS 구독**: 기본 월 19만 원 / Pro 45만 원 / Enterprise 협의\n"
        "- **수수료**: 결제 처리 건당 0.15% (업계 평균 0.25% 대비 40% 저렴)\n"
        "- **손익분기**: 유료 전환 고객 320사, MAU 8,000명 달성 시 BEP (12개월차 예상)\n"
    ),
    docs=[
        DocumentSpec(
            key="business_overview",
            template_file="business_plan_kr/business_overview.md.j2",
            json_schema={
                "type": "object",
                "required": ["vision", "problem_statement", "solution",
                             "target_market", "unique_value", "total_slides", "slide_outline"],
                "properties": {
                    "vision":            {"type": "string"},
                    "problem_statement": {"type": "string"},
                    "solution":          {"type": "string"},
                    "target_market":     {"type": "array", "items": {"type": "string"}},
                    "unique_value":      {"type": "string"},
                    "total_slides":      {"type": "integer"},
                    "slide_outline":     {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "vision":            "",
                "problem_statement": "",
                "solution":          "",
                "target_market":     [],
                "unique_value":      "",
                "total_slides":      0,
                "slide_outline":     [],
            },
            lint_headings=["# 사업 개요:", "## 비전", "## 문제 정의", "## 솔루션", "## PPT 구성 가이드"],
            validator_headings=["## 비전", "## 문제 정의", "## 솔루션",
                                "## 타겟 시장", "## 핵심 가치", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 비전", "## 문제 정의", "## 솔루션"],
        ),
        DocumentSpec(
            key="market_analysis",
            template_file="business_plan_kr/market_analysis.md.j2",
            json_schema={
                "type": "object",
                "required": ["market_size", "competitors", "market_trends",
                             "customer_segments", "entry_strategy", "total_slides", "slide_outline"],
                "properties": {
                    "market_size":        {"type": "string"},
                    "competitors":        {"type": "array", "items": {"type": "string"}},
                    "market_trends":      {"type": "array", "items": {"type": "string"}},
                    "customer_segments":  {"type": "array", "items": {"type": "string"}},
                    "entry_strategy":     {"type": "string"},
                    "total_slides":       {"type": "integer"},
                    "slide_outline":      {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "market_size":       "",
                "competitors":       [],
                "market_trends":     [],
                "customer_segments": [],
                "entry_strategy":    "",
                "total_slides":      0,
                "slide_outline":     [],
            },
            lint_headings=["# 시장 분석:", "## 시장 규모", "## 경쟁 현황", "## 시장 트렌드", "## PPT 구성 가이드"],
            validator_headings=["## 시장 규모", "## 경쟁 현황", "## 시장 트렌드",
                                "## 고객 세그먼트", "## 진입 전략", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 시장 규모", "## 경쟁 현황"],
        ),
        DocumentSpec(
            key="business_model",
            template_file="business_plan_kr/business_model.md.j2",
            json_schema={
                "type": "object",
                "required": ["revenue_streams", "cost_structure", "key_partnerships",
                             "pricing_strategy", "growth_levers", "total_slides", "slide_outline"],
                "properties": {
                    "revenue_streams":  {"type": "array", "items": {"type": "string"}},
                    "cost_structure":   {"type": "array", "items": {"type": "string"}},
                    "key_partnerships": {"type": "array", "items": {"type": "string"}},
                    "pricing_strategy": {"type": "string"},
                    "growth_levers":    {"type": "array", "items": {"type": "string"}},
                    "total_slides":     {"type": "integer"},
                    "slide_outline":    {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "revenue_streams":  [],
                "cost_structure":   [],
                "key_partnerships": [],
                "pricing_strategy": "",
                "growth_levers":    [],
                "total_slides":     0,
                "slide_outline":    [],
            },
            lint_headings=["# 사업 모델:", "## 수익 구조", "## 비용 구조", "## 가격 전략", "## PPT 구성 가이드"],
            validator_headings=["## 수익 구조", "## 비용 구조", "## 주요 파트너십",
                                "## 가격 전략", "## 성장 동력", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 수익 구조", "## 가격 전략"],
        ),
        DocumentSpec(
            key="execution_roadmap",
            template_file="business_plan_kr/execution_roadmap.md.j2",
            json_schema={
                "type": "object",
                "required": ["short_term_goals", "mid_term_goals", "long_term_goals",
                             "key_milestones", "resource_requirements", "total_slides", "slide_outline"],
                "properties": {
                    "short_term_goals":     {"type": "array", "items": {"type": "string"}},
                    "mid_term_goals":       {"type": "array", "items": {"type": "string"}},
                    "long_term_goals":      {"type": "array", "items": {"type": "string"}},
                    "key_milestones":       {"type": "array", "items": {"type": "string"}},
                    "resource_requirements":{"type": "array", "items": {"type": "string"}},
                    "total_slides":         {"type": "integer"},
                    "slide_outline":        {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "short_term_goals":      [],
                "mid_term_goals":        [],
                "long_term_goals":       [],
                "key_milestones":        [],
                "resource_requirements": [],
                "total_slides":          0,
                "slide_outline":         [],
            },
            lint_headings=["# 실행 로드맵:", "## 단기 목표", "## 중기 목표", "## 주요 마일스톤", "## PPT 구성 가이드"],
            validator_headings=["## 단기 목표", "## 중기 목표", "## 장기 목표",
                                "## 주요 마일스톤", "## 필요 자원", "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 단기 목표", "## 주요 마일스톤"],
        ),
    ],
)

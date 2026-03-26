"""contract_kr bundle — 계약·협약서 초안 (한국어).

3개 문서:
  1. contract_overview    — 계약 개요
  2. terms_conditions     — 계약 조건
  3. obligations          — 의무 및 책임
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

CONTRACT_KR = BundleSpec(
    id="contract_kr",
    name_ko="계약·협약서 초안",
    name_en="Contract Draft",
    description_ko="계약 개요·조건·의무 3종 초안. 기업간 계약, 공공기관 협약, 용역 계약서 작성 지원.",
    icon="📜",
    prompt_language="ko",
    prompt_hint=(
        "당신은 기업법무팀 출신의 계약서 초안 전문가입니다. 이 문서는 법적 검토가 필요한 초안임을 명시하세요.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 계약 목적과 범위가 명확히 정의되었는가, "
        "(2) 의무와 책임이 양방향으로 균형 있게 기술되었는가, (3) 분쟁 해결 조항이 포함되었는가.\n"
        "- 계약 당사자, 목적, 기간, 금액을 첫 섹션에 명시하세요.\n"
        "- 각 조항은 번호를 매기고 명확하고 구체적으로 기술하세요.\n"
        "- 법적 모호성을 최소화하고 정확한 법률 용어를 사용하세요.\n"
        "- 공식적이고 격식 있는 한국어 법률 문체를 사용하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="internal",
    few_shot_example=(
        "## 계약 개요\n"
        "**계약명**: AI 기반 문서 자동화 시스템 구축 용역 계약\n"
        "**갑**: (주)한국공공서비스 (이하 '발주처') | **을**: (주)테크솔루션 (이하 '수급인')\n"
        "**계약 기간**: 2026년 4월 1일 ~ 2026년 10월 31일 (7개월)\n"
        "**계약 금액**: 금 오억원정 (₩500,000,000, 부가세 포함)\n"
        "\n"
        "## 주요 의무 사항\n"
        "**수급인 의무**:\n"
        "- 제1조: 수급인은 계약서에 명시된 산출물을 기한 내에 납품해야 한다.\n"
        "- 제2조: 납품물의 하자 발견 시 통보 후 14일 이내 무상 수정을 완료해야 한다.\n"
        "- 제3조: 계약 기간 중 취득한 발주처의 기밀정보를 제3자에게 누설할 수 없다.\n"
        "\n"
        "**발주처 의무**:\n"
        "- 제4조: 발주처는 착수금(계약금액의 30%)을 계약일로부터 7영업일 이내 지급한다.\n"
        "- 제5조: 수급인의 업무 수행에 필요한 자료 및 접근 권한을 제공해야 한다.\n"
    ),
    docs=[
        DocumentSpec(
            key="contract_overview",
            template_file="contract_kr/contract_overview.md.j2",
            json_schema={
                "type": "object",
                "required": ["parties", "purpose", "scope", "contract_period",
                             "contract_amount"],
                "properties": {
                    "parties":          {"type": "string"},
                    "purpose":          {"type": "string"},
                    "scope":            {"type": "array", "items": {"type": "string"}},
                    "contract_period":  {"type": "string"},
                    "contract_amount":  {"type": "string"},
                },
            },
            stabilizer_defaults={
                "parties":         "",
                "purpose":         "",
                "scope":           [],
                "contract_period": "",
                "contract_amount": "",
            },
            lint_headings=["# 계약 개요:", "## 계약 당사자", "## 계약 목적", "## 계약 범위"],
            validator_headings=["## 계약 당사자", "## 계약 목적", "## 계약 범위",
                                "## 계약 기간", "## 계약 금액"],
            critical_non_empty_headings=["## 계약 당사자", "## 계약 목적"],
        ),
        DocumentSpec(
            key="terms_conditions",
            template_file="contract_kr/terms_conditions.md.j2",
            json_schema={
                "type": "object",
                "required": ["payment_terms", "delivery_terms", "warranty",
                             "confidentiality", "termination_clause"],
                "properties": {
                    "payment_terms":      {"type": "string"},
                    "delivery_terms":     {"type": "array", "items": {"type": "string"}},
                    "warranty":           {"type": "string"},
                    "confidentiality":    {"type": "string"},
                    "termination_clause": {"type": "string"},
                },
            },
            stabilizer_defaults={
                "payment_terms":      "",
                "delivery_terms":     [],
                "warranty":           "",
                "confidentiality":    "",
                "termination_clause": "",
            },
            lint_headings=["# 계약 조건:", "## 대금 지급 조건", "## 납품 조건", "## 비밀 유지"],
            validator_headings=["## 대금 지급 조건", "## 납품 조건", "## 하자 보증",
                                "## 비밀 유지", "## 계약 해지"],
            critical_non_empty_headings=["## 대금 지급 조건", "## 납품 조건"],
        ),
        DocumentSpec(
            key="obligations",
            template_file="contract_kr/obligations.md.j2",
            json_schema={
                "type": "object",
                "required": ["party_a_obligations", "party_b_obligations",
                             "liabilities", "dispute_resolution"],
                "properties": {
                    "party_a_obligations": {"type": "array", "items": {"type": "string"}},
                    "party_b_obligations": {"type": "array", "items": {"type": "string"}},
                    "liabilities":         {"type": "string"},
                    "dispute_resolution":  {"type": "string"},
                },
            },
            stabilizer_defaults={
                "party_a_obligations": [],
                "party_b_obligations": [],
                "liabilities":         "",
                "dispute_resolution":  "",
            },
            lint_headings=["# 의무 및 책임:", "## 발주처 의무", "## 수급인 의무", "## 분쟁 해결"],
            validator_headings=["## 발주처 의무", "## 수급인 의무",
                                "## 손해배상 및 책임", "## 분쟁 해결"],
            critical_non_empty_headings=["## 발주처 의무", "## 수급인 의무"],
        ),
    ],
)

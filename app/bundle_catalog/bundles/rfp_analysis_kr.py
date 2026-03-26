"""rfp_analysis_kr bundle — RFP 분석서 (한국어).

2개 문서로 구성:
  1. rfp_summary    — RFP 핵심 분석 및 평가항목
  2. win_strategy   — 수주 전략서 (SWOT + 차별화)
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

RFP_ANALYSIS_KR = BundleSpec(
    id="rfp_analysis_kr",
    name_ko="RFP 분석서",
    name_en="RFP Analysis Report",
    description_ko="제안요청서(RFP) 자동 분석. 평가항목 추출, 요구사항 분류, 수주 전략 도출.",
    icon="🔍",
    prompt_language="ko",
    category="gov",
    prompt_hint=(
        "당신은 공공 IT 사업 수주 전문 컨설턴트로, RFP를 읽고 수주 전략을 설계합니다.\n"
        "작성 전 내부적으로 검토하세요: (1) 발주처의 핵심 Pain Point는 무엇인가, "
        "(2) 배점 기준상 어느 항목이 당락을 결정하는가, "
        "(3) 우리 회사의 강점과 RFP 요구사항의 교차점은 어디인가.\n"
        "- 평가항목은 반드시 배점과 함께 표시하세요 (예: '기술능력 40점 / 가격 30점').\n"
        "- 필수 요구사항과 선택 요구사항을 명확히 구분하세요.\n"
        "- 수주 가능성 판단 근거를 SWOT 관점에서 서술하세요.\n"
        "- 경쟁사 대비 차별화 가능 영역을 최소 3개 이상 식별하세요.\n"
        "- 위험 요소는 대응 방안과 함께 작성하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## RFP 핵심 요약\n"
        "사업명: 국토교통부 도로시설물 AI 안전점검 플랫폼 구축\n"
        "사업 규모: 2,200,000,000원 / 기간: 2025.05.01 ~ 2026.04.30 (12개월)\n"
        "발주처: 국토교통부 도로국 | 입찰방식: 협상에 의한 계약 (제안서 평가)\n"
        "발주처 핵심 Pain Point: 노후 교량·터널 6만 2천 개소 육안 점검 한계 — 점검 주기 2년 → "
        "연간 균열 미탐지율 34%, 긴급보수 지연으로 예산 낭비 연 120억 원\n\n"
        "## 평가항목 분석 (총 100점)\n"
        "- **기술능력 45점**: 유사 AI 비전 구축 실적 20점 + 드론·IoT 연계 기술력 15점 + 제안서 완성도 10점\n"
        "- **수행능력 25점**: PM 경력(국토부 과제 경험) 10점 + 전문인력 구성 15점\n"
        "- **가격 20점**: 예산 대비 낙찰 하한율 88% 기준\n"
        "- **사회적 가치 10점**: 장애인·고령자 고용, 중소기업 상생\n\n"
        "## 필수 요구사항 (당락 결정 항목)\n"
        "- 드론 + 지상 IoT 센서 하이브리드 수집 체계 (드론 자율비행 Level 4 이상)\n"
        "- 균열 탐지 AI 정확도 95% 이상 (공인기관 성능 확인서 제출 필수)\n"
        "- 국토부 시설물통합정보관리(FMS) 연계 API 규격 준수\n"
        "- CC인증 EAL3+ / 행정기관 망 분리 환경 배포 가능\n\n"
        "## 수주 전략 (SWOT 핵심)\n"
        "**강점**: 당사 드론 AI 비전 특허 3건, 교량 점검 실적 국내 1위 (18개 기관, 4,200개소)\n"
        "**차별점①**: 자체 경량화 AI 모델 — 현장 엣지 처리로 통신 두절 환경 대응\n"
        "**차별점②**: FMS 연계 사전 구현 완료 — 발주처 검증 시간 3개월 단축\n"
        "**차별점③**: 국내 최초 균열 진행속도 예측 모듈 — 6개월 내 보수 필요 구조물 자동 분류\n"
        "**리스크**: 드론 비행 허가 지연 → 착수 3개월 전 지역 항공청 사전 협의 착수\n"
    ),
    docs=[
        DocumentSpec(
            key="rfp_summary",
            template_file="rfp_analysis_kr/rfp_summary.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "project_overview", "budget_schedule", "issuer_needs",
                    "evaluation_criteria", "mandatory_requirements",
                    "optional_requirements", "win_probability",
                ],
                "properties": {
                    "project_overview":       {"type": "string"},
                    "budget_schedule":        {"type": "string"},
                    "issuer_needs":           {"type": "array", "items": {"type": "string"}},
                    "evaluation_criteria":    {"type": "array", "items": {"type": "string"}},
                    "mandatory_requirements": {"type": "array", "items": {"type": "string"}},
                    "optional_requirements":  {"type": "array", "items": {"type": "string"}},
                    "win_probability":        {"type": "string"},
                },
            },
            stabilizer_defaults={
                "project_overview": "",
                "budget_schedule": "",
                "issuer_needs": [],
                "evaluation_criteria": [],
                "mandatory_requirements": [],
                "optional_requirements": [],
                "win_probability": "",
            },
            lint_headings=[
                "# RFP 분석서:", "## RFP 핵심 요약", "## 평가항목 분석",
                "## 필수 요구사항", "## 수주 가능성",
            ],
            validator_headings=[
                "## RFP 핵심 요약", "## 평가항목 분석",
                "## 필수 요구사항", "## 선택 요구사항", "## 수주 가능성",
            ],
            critical_non_empty_headings=["## RFP 핵심 요약", "## 평가항목 분석"],
        ),
        DocumentSpec(
            key="win_strategy",
            template_file="rfp_analysis_kr/win_strategy.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "swot_analysis", "differentiation_points",
                    "risk_factors", "response_strategy", "key_messages",
                ],
                "properties": {
                    "swot_analysis":          {"type": "string"},
                    "differentiation_points": {"type": "array", "items": {"type": "string"}},
                    "risk_factors":           {"type": "array", "items": {"type": "string"}},
                    "response_strategy":      {"type": "string"},
                    "key_messages":           {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "swot_analysis": "",
                "differentiation_points": [],
                "risk_factors": [],
                "response_strategy": "",
                "key_messages": [],
            },
            lint_headings=[
                "# 수주 전략서:", "## SWOT 분석", "## 차별화 포인트",
                "## 리스크 요인", "## 핵심 메시지",
            ],
            validator_headings=[
                "## SWOT 분석", "## 차별화 포인트",
                "## 리스크 요인", "## 대응 전략", "## 핵심 메시지",
            ],
            critical_non_empty_headings=["## SWOT 분석", "## 차별화 포인트"],
        ),
    ],
)

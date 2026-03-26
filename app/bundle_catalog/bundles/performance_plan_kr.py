"""performance_plan_kr bundle — 사업수행계획서 (한국어).

2개 문서로 구성:
  1. performance_overview — 수행 개요, WBS, 투입 인력, 산출물
  2. quality_risk_plan    — 품질·리스크 관리 계획
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

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
        "- WBS는 월별로 구분하고 담당자를 명시하세요.\n"
        "- 납품물(산출물) 목록은 제출 일자, 형식, 검수 방법을 포함하세요.\n"
        "- 투입 인력은 등급(특급/고급/중급)과 M/M을 명시하세요.\n"
        "- 리스크는 발생 가능성(상/중/하)과 영향도(상/중/하)로 매트릭스화하세요.\n"
        "- 변경 관리 절차와 보고 체계를 명확히 기술하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## 사업 개요\n"
        "사업명: 기획재정부 국가재정정보시스템(NAFIS) AI 고도화 사업\n"
        "계약 기간: 2025.03.01 ~ 2026.08.31 (18개월)\n"
        "계약 금액: 3,500,000,000원 (부가세 포함) | 발주처: 기획재정부 재정정보화과\n\n"
        "## 수행 범위\n"
        "- 국가 세출예산 집행 이상 탐지 AI 엔진 개발 (예산 전용·과목 오류 자동 탐지)\n"
        "- 기관별 예산 집행 패턴 분석 대시보드 구축 (246개 중앙행정기관)\n"
        "- 차세대 예산회계 시스템(디브레인) 연계 API 개발\n"
        "- 사용자 교육 및 운영 이관 (50명 교육, 운영 매뉴얼 3종)\n\n"
        "## WBS (단계별 일정)\n"
        "- **1단계 착수·분석** (25.03~25.05, 3개월): 현황 진단, AS-IS/TO-BE 분석, 착수보고서\n"
        "- **2단계 AI 설계** (25.06~25.08, 3개월): AI 모델 아키텍처, 학습 데이터 정의서, 설계서\n"
        "- **3단계 개발·학습** (25.09~26.01, 5개월): 이상 탐지 엔진 개발, 10년치 데이터 학습, 중간보고\n"
        "- **4단계 연계·시험** (26.02~26.06, 5개월): 디브레인 API 연계, 통합 테스트, 파일럿 운영\n"
        "- **5단계 전개·완료** (26.07~26.08, 2개월): 전체 기관 배포, 교육, 최종보고\n\n"
        "## 투입 인력 (총 62.5M/M)\n"
        "- PM·총괄 (특급, PMP): 홍길동 / 18M/M — 재정정보화 사업 PMO 경력 8년\n"
        "- AI 리드 (특급, 박사): 김철수 / 15M/M — 이상 탐지 알고리즘 논문 4편\n"
        "- 백엔드 개발 (고급): 이영희 외 2명 / 각 8M/M — 디브레인 연계 경험 보유\n"
        "- 데이터 엔지니어 (중급): 박민준 / 7M/M — 공공 데이터 파이프라인 구축 3건\n"
        "- 품질관리 (고급): 최지수 / 6.5M/M — ISO 25010 기반 품질 검수\n"
    ),
    docs=[
        DocumentSpec(
            key="performance_overview",
            template_file="performance_plan_kr/performance_overview.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "project_info", "scope_of_work", "deliverables",
                    "team_structure", "wbs_summary",
                ],
                "properties": {
                    "project_info":   {"type": "string"},
                    "scope_of_work":  {"type": "array", "items": {"type": "string"}},
                    "deliverables":   {"type": "array", "items": {"type": "string"}},
                    "team_structure": {"type": "array", "items": {"type": "string"}},
                    "wbs_summary":    {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "project_info": "",
                "scope_of_work": [],
                "deliverables": [],
                "team_structure": [],
                "wbs_summary": [],
            },
            lint_headings=[
                "# 사업수행계획서:", "## 사업 개요", "## 수행 범위",
                "## 산출물 목록", "## WBS",
            ],
            validator_headings=[
                "## 사업 개요", "## 수행 범위", "## 산출물 목록",
                "## 투입 인력", "## WBS",
            ],
            critical_non_empty_headings=["## 사업 개요", "## WBS"],
        ),
        DocumentSpec(
            key="quality_risk_plan",
            template_file="performance_plan_kr/quality_risk_plan.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "quality_standards", "inspection_criteria",
                    "risk_matrix", "change_management", "reporting_structure",
                ],
                "properties": {
                    "quality_standards":   {"type": "array", "items": {"type": "string"}},
                    "inspection_criteria": {"type": "array", "items": {"type": "string"}},
                    "risk_matrix":         {"type": "array", "items": {"type": "string"}},
                    "change_management":   {"type": "string"},
                    "reporting_structure": {"type": "string"},
                },
            },
            stabilizer_defaults={
                "quality_standards": [],
                "inspection_criteria": [],
                "risk_matrix": [],
                "change_management": "",
                "reporting_structure": "",
            },
            lint_headings=[
                "# 품질·리스크 관리계획:", "## 품질 기준",
                "## 검수 기준", "## 리스크 매트릭스", "## 변경 관리",
            ],
            validator_headings=[
                "## 품질 기준", "## 검수 기준", "## 리스크 매트릭스",
                "## 변경 관리", "## 보고 체계",
            ],
            critical_non_empty_headings=["## 품질 기준", "## 리스크 매트릭스"],
        ),
    ],
)

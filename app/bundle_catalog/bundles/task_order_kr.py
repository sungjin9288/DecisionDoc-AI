"""task_order_kr bundle — 과업지시서 (한국어).

1개 문서로 구성:
  1. task_definition — 과업 범위, 기능/비기능 요구사항, 납품물, 검수 기준
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

TASK_ORDER_KR = BundleSpec(
    id="task_order_kr",
    name_ko="과업지시서",
    name_en="Statement of Work",
    description_ko="발주처용 과업지시서(SOW). 과업 범위, 요구사항, 검수 기준, 납품물 정의.",
    icon="📝",
    prompt_language="ko",
    category="gov",
    prompt_hint=(
        "당신은 공공기관 IT 사업 발주 담당자로, 수행사가 명확히 이해하고 이행할 수 있는 과업지시서를 작성합니다.\n"
        "작성 전 내부적으로 검토하세요: (1) 과업 범위가 명확하게 정의되어 분쟁 소지가 없는가, "
        "(2) 검수 기준이 객관적이고 측정 가능한가, "
        "(3) 납품물의 형식과 제출 시기가 구체적인가.\n"
        "- 과업 범위는 포함 항목과 제외 항목을 명시하세요 (in-scope / out-of-scope).\n"
        "- 기능 요구사항은 'SHALL' 표현으로 의무화하세요.\n"
        "- 비기능 요구사항(성능, 보안, 가용성)에 수치 기준을 포함하세요.\n"
        "- 납품물은 제출 시기, 형식(HWP/PDF/소스코드), 수량을 명시하세요.\n"
        "- 검수 절차와 합격 기준을 명확히 정의하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## 과업 개요\n"
        "과업명: 조달청 전자조달시스템 AI 계약관리 고도화\n"
        "예산: 1,500,000,000원 (부가세 포함) | 기간: 착수일로부터 12개월\n"
        "발주기관: 조달청 전자조달국 | 수행사 자격: 소프트웨어사업자 신고 + AI 관련 SI 실적 3건 이상\n\n"
        "## 과업 범위 (In-Scope)\n"
        "- 계약 문서 AI 자동 검토 엔진 (불공정 조항 탐지, 법령 위반 항목 자동 플래그)\n"
        "- 계약 이행 모니터링 대시보드 (납기 준수율, 검수 현황, 하자보수 이력)\n"
        "- 나라장터 계약관리시스템(KONEPS) 데이터 연계 API\n"
        "- 계약 담당자 AI 어시스턴트 챗봇 (법령 Q&A, 서식 자동 작성)\n\n"
        "## 제외 범위 (Out-of-Scope)\n"
        "- 기존 KONEPS 핵심 계약 처리 로직 변경\n"
        "- 전자입찰 모듈 (별도 사업)\n"
        "- 해외 조달 시스템 연계\n\n"
        "## 기능 요구사항 (SHALL 의무)\n"
        "- 시스템은 계약 문서 AI 검토 결과를 업로드 후 60초 이내에 제공SHALL.\n"
        "- 시스템은 불공정 조항 탐지 정확도 92% 이상을 달성SHALL (공인기관 검증 필수).\n"
        "- 시스템은 KONEPS API v4.2 규격을 완전히 준수SHALL.\n"
        "- 시스템은 동시 접속자 500명, 일 최대 처리 건수 10,000건을 지원SHALL.\n"
        "- 모든 계약 데이터는 AES-256 암호화 및 접근 이력 로깅SHALL.\n\n"
        "## 비기능 요구사항\n"
        "- **가용성**: 연간 서비스 가용률 99.9% 이상 (계획 유지보수 제외)\n"
        "- **성능**: 평균 응답시간 2초 이하 (95 백분위수 기준)\n"
        "- **보안**: 국가정보원 CC인증 EAL2+ 이상, 행정망 분리 운영 환경 지원\n\n"
        "## 납품물 목록\n"
        "- 착수보고서: 착수 후 14일 이내 / HWP+PDF / 계약담당관 승인\n"
        "- 요구사항 정의서: 2단계 완료 시 / HWP+PDF\n"
        "- 시스템 설계서 (아키텍처·DB·인터페이스): 3단계 완료 시 / HWP+PDF\n"
        "- AI 모델 성능 확인서 (공인기관 발급): 5단계 완료 시\n"
        "- 소스코드 (Git 저장소 이관) + 설치·운영 매뉴얼: 최종 납품 시\n"
        "- 완료보고서: 사업 종료 7일 이내\n"
    ),
    docs=[
        DocumentSpec(
            key="task_definition",
            template_file="task_order_kr/task_definition.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "task_overview", "scope_in", "scope_out",
                    "functional_requirements", "non_functional_requirements",
                    "deliverables", "inspection_criteria",
                ],
                "properties": {
                    "task_overview":               {"type": "string"},
                    "scope_in":                    {"type": "array", "items": {"type": "string"}},
                    "scope_out":                   {"type": "array", "items": {"type": "string"}},
                    "functional_requirements":     {"type": "array", "items": {"type": "string"}},
                    "non_functional_requirements": {"type": "array", "items": {"type": "string"}},
                    "deliverables":                {"type": "array", "items": {"type": "string"}},
                    "inspection_criteria":         {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "task_overview": "",
                "scope_in": [],
                "scope_out": [],
                "functional_requirements": [],
                "non_functional_requirements": [],
                "deliverables": [],
                "inspection_criteria": [],
            },
            lint_headings=[
                "# 과업지시서:", "## 과업 개요", "## 과업 범위",
                "## 기능 요구사항", "## 납품물 목록",
            ],
            validator_headings=[
                "## 과업 개요", "## 과업 범위", "## 기능 요구사항",
                "## 비기능 요구사항", "## 납품물 목록", "## 검수 기준",
            ],
            critical_non_empty_headings=["## 기능 요구사항", "## 납품물 목록"],
        ),
    ],
)

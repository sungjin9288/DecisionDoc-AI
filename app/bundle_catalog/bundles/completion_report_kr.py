"""completion_report_kr bundle — 준공(완료)보고서 (한국어).

1개 문서로 구성:
  1. completion_summary — 이행 실적, 납품물 목록, 성과 측정, 하자보수 계획
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

COMPLETION_REPORT_KR = BundleSpec(
    id="completion_report_kr",
    name_ko="준공(완료)보고서",
    name_en="Project Completion Report",
    description_ko="나라장터 과업 준공보고서. 이행 실적, 산출물 목록, 성과 측정, 하자보수 계획 포함.",
    icon="✅",
    prompt_language="ko",
    category="gov",
    prompt_hint=(
        "당신은 공공 IT 사업 준공 검수를 통과하기 위한 완료보고서 전문 작성자입니다.\n"
        "작성 전 내부적으로 검토하세요: (1) 계약서상 모든 납품물이 실제로 제출됐는가, "
        "(2) 당초 목표 대비 실제 달성치를 수치로 증명할 수 있는가, "
        "(3) 하자보수 기간과 지원 체계가 명확한가.\n"
        "- 납품물은 문서명, 제출일, 버전, 승인자를 표로 정리하세요.\n"
        "- 성과는 계획 대비 실적 형식으로 수치화하세요 (예: 목표 99% → 실적 99.3%).\n"
        "- 발생한 이슈와 해결 방법을 솔직하게 기술하고 재발 방지책을 포함하세요.\n"
        "- 하자보수는 기간, 담당자 연락처, 대응 시간 SLA를 명시하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## 사업 이행 실적\n"
        "사업명: 서울특별시 AI 민원상담 챗봇 구축\n"
        "계약 기간: 2025.03.01 ~ 2025.11.30 / 실제 완료: 2025.11.25 (5일 조기 완료)\n"
        "계약 금액: 800,000,000원 | 발주처: 서울특별시 디지털정책관\n"
        "납품물 제출: 계획 15종 → 실적 15종 (100% 완료, 모두 기한 내 제출)\n\n"
        "## 납품물 목록 (주요 항목)\n"
        "- 착수보고서 (2025.03.15 제출, v1.0, 담당 PM 홍길동 승인)\n"
        "- AI 챗봇 시스템 설계서 (2025.05.30, HWP+PDF, 감독관 이영희 승인)\n"
        "- 학습 데이터셋 및 전처리 보고서 (2025.07.31, 민원 유형 1,240개, 25만 건)\n"
        "- 중간보고서 (2025.08.15, 진척률 62% 확인)\n"
        "- 소스코드 및 설치 매뉴얼 (2025.11.20, Git 저장소 이관 완료)\n"
        "- 완료보고서 및 결과물 납품서 (2025.11.25)\n\n"
        "## 성과 측정 결과\n"
        "- **챗봇 응답 정확도**: 목표 90% → 실적 93.7% (목표 대비 104% 달성)\n"
        "- **민원 1차 해결률**: 목표 75% → 실적 78.2% (목표 초과)\n"
        "- **상담원 연결 감소율**: 목표 30% → 실적 38% (콜센터 일 평균 420건 절감)\n"
        "- **시스템 응답 속도**: 목표 2초 → 실적 평균 1.4초\n"
        "- **서비스 가동률**: 목표 99.5% → 실적 99.71% (배포 후 4개월 무중단)\n"
        "- **시민 만족도**: 목표 80점 → 실적 85.3점 (서울시 디지털 서비스 최고점)\n\n"
        "## 이슈 해결 내역\n"
        "- 이슈①: 6월 개인정보 보호법 개정으로 데이터 비식별화 기준 강화 → 일정 2주 지연 → "
        "팀원 추가 투입 및 야간 작업으로 중간보고 기한 내 만회\n"
        "- 이슈②: 서울시 내부망 방화벽 정책 변경 → API 연계 차단 → 서울시 정보화담당관 협조 후 "
        "포트 개방 조치, 3일 내 해결\n\n"
        "## 하자보수 계획\n"
        "하자보수 기간: 2025.12.01 ~ 2026.11.30 (1년) | 보수 유형: 무상 하자보수\n"
        "담당자: 박민준 수석 (010-1234-5678, pmj@company.com)\n"
        "장애 등급별 SLA: 긴급(서비스 중단) 2시간 내 / 일반(기능 오류) 8시간 내 / 경미 48시간 내\n"
    ),
    docs=[
        DocumentSpec(
            key="completion_summary",
            template_file="completion_report_kr/completion_summary.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "project_info", "deliverables_list", "performance_results",
                    "issues_resolved", "warranty_plan",
                ],
                "properties": {
                    "project_info":        {"type": "string"},
                    "deliverables_list":   {"type": "array", "items": {"type": "string"}},
                    "performance_results": {"type": "array", "items": {"type": "string"}},
                    "issues_resolved":     {"type": "array", "items": {"type": "string"}},
                    "warranty_plan":       {"type": "string"},
                },
            },
            stabilizer_defaults={
                "project_info": "",
                "deliverables_list": [],
                "performance_results": [],
                "issues_resolved": [],
                "warranty_plan": "",
            },
            lint_headings=[
                "# 준공보고서:", "## 사업 이행 실적", "## 납품물 목록",
                "## 성과 측정 결과", "## 하자보수 계획",
            ],
            validator_headings=[
                "## 사업 이행 실적", "## 납품물 목록",
                "## 성과 측정 결과", "## 이슈 해결 내역", "## 하자보수 계획",
            ],
            critical_non_empty_headings=["## 납품물 목록", "## 성과 측정 결과"],
        ),
    ],
)

"""interim_report_kr bundle — 중간보고서 (한국어).

1개 문서로 구성:
  1. progress_report — 진척 현황, 이슈, 향후 일정, 변경 요청
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

INTERIM_REPORT_KR = BundleSpec(
    id="interim_report_kr",
    name_ko="중간보고서",
    name_en="Interim Progress Report",
    description_ko="공공 과업 중간보고서. 진척률, 이슈 현황, 잔여 일정, 변경 사항 보고.",
    icon="📊",
    prompt_language="ko",
    category="gov",
    prompt_hint=(
        "당신은 발주처 담당자에게 신뢰를 주는 공공 IT 과업 중간보고서 작성 전문가입니다.\n"
        "작성 전 내부적으로 검토하세요: (1) 계획 대비 실제 진척률의 격차가 있다면 그 원인이 무엇인가, "
        "(2) 현재 이슈 중 일정에 영향을 줄 수 있는 것이 있는가, "
        "(3) 잔여 기간 내 완료 가능성에 대한 솔직한 판단은 무엇인가.\n"
        "- 진척률은 WBS 항목별로 계획/실적을 비교하세요.\n"
        "- 지연 항목은 원인, 영향, 만회 대책을 함께 기술하세요.\n"
        "- 이슈는 심각도(긴급/보통/낮음)와 담당자를 명시하세요.\n"
        "- 다음 보고까지의 주요 일정을 구체적으로 제시하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    few_shot_example=(
        "## 전체 진척 현황\n"
        "사업명: 경기도 복지 통합관리 플랫폼 구축\n"
        "계약 기간: 2025.02.01 ~ 2025.12.31 (11개월) | 계약 금액: 1,200,000,000원\n"
        "보고 기준일: 2025.07.31 / 보고 차수: 2차 중간보고\n"
        "**전체 진척률: 계획 62% → 실적 59% (3% 지연)**\n\n"
        "## 단계별 진척 현황\n"
        "- **1단계 착수·분석** (2~3월): 계획 100% → 실적 100% ✅ 완료\n"
        "- **2단계 시스템 설계** (4~5월): 계획 100% → 실적 97% ⚠️ (복지급여 연계 DB 설계 잔여)\n"
        "- **3단계 핵심 기능 개발** (6~8월): 계획 65% → 실적 58% ⚠️ (7% 지연)\n"
        "  - 복지대상자 통합 조회 모듈: 계획 90% → 실적 88% (거의 완료)\n"
        "  - AI 복지 사각지대 발굴 엔진: 계획 50% → 실적 38% (데이터 품질 이슈로 지연)\n"
        "  - 시군구 연계 API: 계획 40% → 실적 30% (31개 시군구 중 12개 연계 완료)\n"
        "- **4단계 통합 시험** (9~11월): 계획 0% → 실적 0% (미착수, 예정대로)\n\n"
        "## 주요 이슈 및 만회 대책\n"
        "| # | 심각도 | 이슈 내용 | 영향 | 만회 방안 | 담당 | 해결 예정 |\n"
        "|---|--------|-----------|------|-----------|------|-----------|\n"
        "| 1 | 긴급 | 복지부 사회보장정보원 API 규격 변경(v2.1→v3.0) | 연계 모듈 재개발 필요 | 규격 변경분 우선 반영, 개발 인력 1명 추가 투입 | 이영희 | 8/20 |\n"
        "| 2 | 보통 | 학습 데이터 품질 기준 미달 (결측률 18%) | AI 엔진 정확도 목표 미달 위험 | 데이터 정제 TF 구성, 경기도 복지과와 주 2회 협의 | 박민준 | 8/31 |\n"
        "| 3 | 낮음 | 시군구 담당자 교육 일정 조율 지연 | 연계 테스트 착수 지연 | 비대면 영상 교육으로 전환, 일괄 교육 9/5 확정 | 최지수 | 9/5 |\n\n"
        "## 향후 일정 (8~9월)\n"
        "- 8.20: 사회보장정보원 API v3.0 연계 완료 (이영희)\n"
        "- 8.31: 학습 데이터 정제 완료 및 AI 모델 재학습 (박민준)\n"
        "- 9.5: 31개 시군구 전체 연계 테스트 완료 목표\n"
        "- 9.30: 3단계 핵심 개발 100% 완료 → 지연 만회 예정\n"
    ),
    docs=[
        DocumentSpec(
            key="progress_report",
            template_file="interim_report_kr/progress_report.md.j2",
            json_schema={
                "type": "object",
                "required": [
                    "report_date", "overall_progress", "phase_progress",
                    "active_issues", "next_schedule", "change_requests",
                ],
                "properties": {
                    "report_date":      {"type": "string"},
                    "overall_progress": {"type": "string"},
                    "phase_progress":   {"type": "array", "items": {"type": "string"}},
                    "active_issues":    {"type": "array", "items": {"type": "string"}},
                    "next_schedule":    {"type": "array", "items": {"type": "string"}},
                    "change_requests":  {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "report_date": "",
                "overall_progress": "",
                "phase_progress": [],
                "active_issues": [],
                "next_schedule": [],
                "change_requests": [],
            },
            lint_headings=[
                "# 중간보고서:", "## 전체 진척 현황",
                "## 단계별 진척 현황", "## 주요 이슈", "## 향후 일정",
            ],
            validator_headings=[
                "## 전체 진척 현황", "## 단계별 진척 현황",
                "## 주요 이슈", "## 향후 일정", "## 변경 요청 사항",
            ],
            critical_non_empty_headings=["## 전체 진척 현황", "## 주요 이슈"],
        ),
    ],
)

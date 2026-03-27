"""project_report_kr bundle — 프로젝트 결과보고서 (한국어).

3개 문서:
  1. executive_summary  — 경영진 요약
  2. progress_report    — 진행 현황 보고
  3. lessons_learned    — 교훈 및 개선사항
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

PROJECT_REPORT_KR = BundleSpec(
    id="project_report_kr",
    name_ko="프로젝트 결과보고서",
    name_en="Project Result Report",
    description_ko="프로젝트 경영진 요약·진행현황·교훈 3종. 기업 프로젝트 완료보고 및 공공기관 사업 결과보고.",
    icon="📋",
    prompt_language="ko",
    prompt_hint=(
        "당신은 PMO(프로젝트 관리 오피스) 경력 10년의 프로젝트 결과보고서 전문가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 목표 대비 실제 성과가 수치로 비교되는가, "
        "(2) 일정/예산 편차의 원인이 명확히 분석되었는가, (3) 다음 프로젝트에 적용할 개선사항이 구체적인가.\n"
        "- 경영진 요약은 결론 먼저(BLUF), 1페이지 분량으로 작성하세요.\n"
        "- 목표 대비 달성률은 반드시 수치(%)로 표기하세요.\n"
        "- 교훈은 '문제 → 원인 → 개선방안' 구조로 기술하세요.\n"
        "- 공식적이고 간결한 한국어 문체를 사용하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="report",
    few_shot_example=(
        "## 프로젝트 개요\n"
        "**프로젝트명**: NIA 공공 AI 학습 데이터 구축 사업 (2025년도)\n"
        "**발주처**: 한국지능정보사회진흥원(NIA) | **계약 금액**: 2,400,000,000원\n"
        "**기간**: 2025.01.15 ~ 2025.12.15 (11개월) | **팀**: 38명 (PM 1 + 데이터 팀 28 + 개발 9)\n\n"
        "## 목표 대비 성과\n"
        "| 지표 | 목표 | 실적 | 달성률 | 비고 |\n"
        "|------|------|------|--------|------|\n"
        "| 학습 데이터 구축 건수 | 50만 건 | 52.3만 건 | 104.6% | 의료·법률·행정 3개 도메인 |\n"
        "| 데이터 품질 검수 합격률 | 95% | 97.1% | 102.2% | AI Hub 품질 기준 |\n"
        "| 납품 기한 준수 | 12/15 | 12/10 | 조기 완료 | 5일 앞당김 |\n"
        "| 예산 집행률 | 95%+ | 97.4% | — | 잔액 반납 6,240만원 |\n"
        "| 데이터 활용 기관 수 | 30개 | 47개 | 156.7% | AI Hub 공개 후 수요 급증 |\n\n"
        "## 핵심 성과 요약\n"
        "- 의료 영상 판독 AI 학습 데이터 18.2만 건 구축 — 국내 최대 규모 공공 의료 AI 데이터셋\n"
        "- 법률 문서 요약·분류 데이터 15.7만 건 — 법제처 법령 해석 AI 사전 학습에 즉시 활용\n"
        "- 행정 문서 OCR·구조화 데이터 18.4만 건 — 정부 24 민원 AI 자동처리 모델 정확도 8.3%p 향상\n\n"
        "## 주요 교훈\n"
        "- **문제**: 의료 데이터 비식별화 기준 강화(개인정보위 고시 개정, 3월) → 재작업 6주 소요\n"
        "  **원인**: 사업 착수 전 법령 개정 예고 모니터링 미흡\n"
        "  **개선**: 향후 데이터 사업 착수 시 법령 변경 모니터링 체크리스트 의무 적용\n"
        "- **문제**: 어노테이터 이직률 28% (데이터 작업 단순 반복으로 인한 피로)\n"
        "  **원인**: 장기 단순 작업에 대한 보상·동기 부여 체계 미흡\n"
        "  **개선**: 성과급 제도 도입 + AI 보조 도구로 단순 반복 50% 자동화\n"
    ),
    docs=[
        DocumentSpec(
            key="executive_summary",
            template_file="project_report_kr/executive_summary.md.j2",
            json_schema={
                "type": "object",
                "required": ["project_overview", "objectives_achieved", "key_outcomes",
                             "budget_summary", "timeline_summary"],
                "properties": {
                    "project_overview":     {"type": "string"},
                    "objectives_achieved":  {"type": "array", "items": {"type": "string"}},
                    "key_outcomes":         {"type": "array", "items": {"type": "string"}},
                    "budget_summary":       {"type": "string"},
                    "timeline_summary":     {"type": "string"},
                },
            },
            stabilizer_defaults={
                "project_overview":    "",
                "objectives_achieved": [],
                "key_outcomes":        [],
                "budget_summary":      "",
                "timeline_summary":    "",
            },
            lint_headings=["# 경영진 요약:", "## 프로젝트 개요", "## 목표 달성 현황", "## 핵심 성과"],
            validator_headings=["## 프로젝트 개요", "## 목표 달성 현황", "## 핵심 성과",
                                "## 예산 요약", "## 일정 요약"],
            critical_non_empty_headings=["## 프로젝트 개요", "## 핵심 성과"],
        ),
        DocumentSpec(
            key="progress_report",
            template_file="project_report_kr/progress_report.md.j2",
            json_schema={
                "type": "object",
                "required": ["milestone_status", "deliverables", "issues_resolved",
                             "pending_items", "kpi_tracking"],
                "properties": {
                    "milestone_status": {"type": "array", "items": {"type": "string"}},
                    "deliverables":     {"type": "array", "items": {"type": "string"}},
                    "issues_resolved":  {"type": "array", "items": {"type": "string"}},
                    "pending_items":    {"type": "array", "items": {"type": "string"}},
                    "kpi_tracking":     {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "milestone_status": [],
                "deliverables":     [],
                "issues_resolved":  [],
                "pending_items":    [],
                "kpi_tracking":     [],
            },
            lint_headings=["# 진행 현황 보고:", "## 마일스톤 현황", "## 산출물 목록", "## KPI 추적"],
            validator_headings=["## 마일스톤 현황", "## 산출물 목록", "## 해결된 이슈",
                                "## 미결 항목", "## KPI 추적"],
            critical_non_empty_headings=["## 마일스톤 현황", "## 산출물 목록", "## KPI 추적"],
        ),
        DocumentSpec(
            key="lessons_learned",
            template_file="project_report_kr/lessons_learned.md.j2",
            json_schema={
                "type": "object",
                "required": ["successes", "challenges", "improvements",
                             "recommendations", "knowledge_assets"],
                "properties": {
                    "successes":        {"type": "array", "items": {"type": "string"}},
                    "challenges":       {"type": "array", "items": {"type": "string"}},
                    "improvements":     {"type": "array", "items": {"type": "string"}},
                    "recommendations":  {"type": "array", "items": {"type": "string"}},
                    "knowledge_assets": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "successes":        [],
                "challenges":       [],
                "improvements":     [],
                "recommendations":  [],
                "knowledge_assets": [],
            },
            lint_headings=["# 교훈 및 개선사항:", "## 성공 요인", "## 도전 과제", "## 개선 방안"],
            validator_headings=["## 성공 요인", "## 도전 과제", "## 개선 방안",
                                "## 권고 사항", "## 지식 자산"],
            critical_non_empty_headings=["## 성공 요인", "## 도전 과제", "## 개선 방안"],
        ),
    ],
)

"""feasibility_report_kr bundle — 사업타당성 검토서 (한국어).

3개 문서:
  1. current_analysis        — 현황 분석 및 문제 도출
  2. feasibility_assessment  — 타당성 평가 (기술·경제·운영)
  3. recommendation          — 추진 권고안 및 실행 계획
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

FEASIBILITY_REPORT_KR = BundleSpec(
    id="feasibility_report_kr",
    name_ko="사업타당성 검토서",
    name_en="Feasibility Report",
    description_ko="현황 분석·타당성 평가·추진 권고안 3종. 신규 사업·R&D·시스템 도입 의사결정에 활용.",
    icon="🔍",
    prompt_language="ko",
    prompt_hint=(
        "당신은 경영전략 컨설팅 전문가이자 사업타당성 분석 전문가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 의사결정권자가 가장 우려하는 리스크는 무엇인가, "
        "(2) 투자 대비 수익성(ROI)을 어떻게 정량화할 것인가, "
        "(3) 대안이 있다면 현 안과의 비교 우위를 어떻게 설명할 것인가.\n"
        "- 기술적·경제적·운영적 타당성을 각각 평가하세요.\n"
        "- 정량적 수치와 근거 자료를 반드시 포함하세요.\n"
        "- 리스크 요인과 경감 방안을 구체적으로 제시하세요.\n"
        "- 최종 권고안은 '추진 권고', '조건부 추진', '보류/불가' 중 하나를 명시하세요.\n"
        "- 공식적이고 객관적인 한국어 문체를 사용하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="work",
    few_shot_example=(
        "## 현황 분석\n"
        "현재 행정안전부 민원처리 시스템은 2015년 구축된 레거시 온프레미스 환경으로 운영되고 있으며, "
        "연간 유지보수 비용 18억 원이 소요되나 시스템 가용성이 99.1%에 머물러 연 간 79시간 이상의 "
        "다운타임이 발생하고 있다. 처리 속도 기준 분당 1,200건 처리 한계로 민원 집중 시간대 "
        "(09:00~11:00) 응답 지연이 평균 8.3초에 달해 민원인 불만 건수가 분기 2,100건을 초과한다.\n\n"
        "## 타당성 평가 요약\n"
        "**기술적 타당성**: ✅ 클라우드 전환 기술력 확보 (AWS GovCloud 도입 사례 6건 국내 존재)\n"
        "**경제적 타당성**: ✅ 10년 TCO 분석 — 현행 유지 대비 클라우드 전환 시 총 비용 34% 절감\n"
        "  - 현행 유지 10년 TCO: 204억 원\n"
        "  - 클라우드 전환 10년 TCO: 135억 원 (초기 구축 23억 포함)\n"
        "  - 순절감 69억 원, ROI 300%, 투자회수기간 3.2년\n"
        "**운영적 타당성**: ⚠️ 전환 기간 6개월 서비스 안정성 리스크 → 단계적 전환(Blue-Green) 방식으로 경감\n\n"
        "## 최종 권고\n"
        "**추진 권고** — 2026년 하반기 착수, 단계적 클라우드 전환 권고\n"
        "- 1단계 (2026 H2): 비핵심 서비스 클라우드 이전, 성능 검증\n"
        "- 2단계 (2027): 핵심 민원 처리 시스템 전환, 레거시 병행 운영\n"
        "- 3단계 (2028): 레거시 완전 폐기, 클라우드 단일화\n"
    ),
    docs=[
        DocumentSpec(
            key="current_analysis",
            template_file="feasibility_report_kr/current_analysis.md.j2",
            json_schema={
                "type": "object",
                "required": ["background", "current_status", "identified_problems",
                             "analysis_objectives", "scope_and_methodology"],
                "properties": {
                    "background":             {"type": "string"},
                    "current_status":         {"type": "string"},
                    "identified_problems":    {"type": "array", "items": {"type": "string"}},
                    "analysis_objectives":    {"type": "array", "items": {"type": "string"}},
                    "scope_and_methodology":  {"type": "string"},
                },
            },
            stabilizer_defaults={
                "background":            "",
                "current_status":        "",
                "identified_problems":   [],
                "analysis_objectives":   [],
                "scope_and_methodology": "",
            },
            lint_headings=["# 현황 분석:", "## 검토 배경", "## 현황"],
            validator_headings=["## 검토 배경", "## 현황", "## 문제 도출",
                                "## 분석 목적", "## 분석 범위 및 방법론"],
            critical_non_empty_headings=["## 검토 배경", "## 문제 도출"],
        ),
        DocumentSpec(
            key="feasibility_assessment",
            template_file="feasibility_report_kr/feasibility_assessment.md.j2",
            json_schema={
                "type": "object",
                "required": ["technical_feasibility", "economic_feasibility",
                             "operational_feasibility", "risk_analysis",
                             "alternative_comparison"],
                "properties": {
                    "technical_feasibility":   {"type": "string"},
                    "economic_feasibility":    {"type": "string"},
                    "operational_feasibility": {"type": "string"},
                    "risk_analysis":           {"type": "array", "items": {"type": "string"}},
                    "alternative_comparison":  {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "technical_feasibility":   "",
                "economic_feasibility":    "",
                "operational_feasibility": "",
                "risk_analysis":           [],
                "alternative_comparison":  [],
            },
            lint_headings=["# 타당성 평가:", "## 기술적 타당성", "## 경제적 타당성"],
            validator_headings=["## 기술적 타당성", "## 경제적 타당성",
                                "## 운영적 타당성", "## 리스크 분석", "## 대안 비교"],
            critical_non_empty_headings=["## 기술적 타당성", "## 경제적 타당성"],
        ),
        DocumentSpec(
            key="recommendation",
            template_file="feasibility_report_kr/recommendation.md.j2",
            json_schema={
                "type": "object",
                "required": ["verdict", "rationale", "implementation_plan",
                             "success_conditions", "next_steps"],
                "properties": {
                    "verdict":             {"type": "string"},
                    "rationale":           {"type": "array", "items": {"type": "string"}},
                    "implementation_plan": {"type": "array", "items": {"type": "string"}},
                    "success_conditions":  {"type": "array", "items": {"type": "string"}},
                    "next_steps":          {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "verdict":             "",
                "rationale":           [],
                "implementation_plan": [],
                "success_conditions":  [],
                "next_steps":          [],
            },
            lint_headings=["# 추진 권고안:", "## 최종 판정", "## 추진 근거"],
            validator_headings=["## 최종 판정", "## 추진 근거", "## 실행 계획",
                                "## 성공 조건", "## 다음 단계"],
            critical_non_empty_headings=["## 최종 판정", "## 추진 근거"],
        ),
    ],
)

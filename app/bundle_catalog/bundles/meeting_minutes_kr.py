"""meeting_minutes_kr bundle — 회의록 (한국어).

3개 문서:
  1. meeting_summary  — 회의 요약
  2. action_items     — 액션 아이템
  3. decision_log     — 의사결정 기록
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

MEETING_MINUTES_KR = BundleSpec(
    id="meeting_minutes_kr",
    name_ko="회의록",
    name_en="Meeting Minutes",
    description_ko="회의 요약·액션 아이템·의사결정 기록 3종. 기업 내부 회의 및 공공기관 협의 문서.",
    icon="📝",
    prompt_language="ko",
    prompt_hint=(
        "당신은 기업 경영기획팀 출신의 회의록 전문 작성가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 의사결정 내용이 명확히 기록되었는가, "
        "(2) 액션 아이템에 담당자와 기한이 명시되었는가, (3) 다음 회의와의 연계성이 있는가.\n"
        "- 회의 목적과 배경을 첫 문단에 명시하세요.\n"
        "- 액션 아이템은 '누가·무엇을·언제까지' 형식으로 기술하세요.\n"
        "- 의사결정 사항은 결정 배경, 대안 검토, 최종 결정을 구분하여 기록하세요.\n"
        "- 공식적이고 간결한 한국어 문체를 사용하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="internal",
    few_shot_example=(
        "## 회의 개요\n"
        "**회의명**: 행정안전부 디지털정부 AI 전략 수립 킥오프 회의\n"
        "**일시**: 2026년 3월 17일 10:00~12:00 | **장소**: 행정안전부 3동 대회의실 및 화상 병행\n"
        "**주관**: 디지털정부실 AI정책과장 홍길동\n"
        "**참석자**: 홍길동(AI정책과장·주관), 김철수(디지털정부실 과장), 이영희(정보화총괄담당관), "
        "박민준(NIPA 기획처장), 최지수(NIA 공공AI팀장), 손지원(KT 공공사업부 이사)\n"
        "**목적**: 2026~2028 행안부 디지털정부 AI 전략 초안 검토 및 우선순위 확정\n\n"
        "## 주요 의사결정\n"
        "- **1호**: 3개년 AI 전략 핵심 과제 12개 중 2026년 집중 추진 과제 4개 선정\n"
        "  → ①민원 AI 자동화 ②공무원 AI 보조 도구 ③지능형 정책 분석 ④디지털 취약계층 지원\n"
        "- **2호**: 2026년 AI 전략 예산 총 482억 원 (행안부 본예산 310억 + 기재부 협의 172억)\n"
        "  → 기재부 협의분 172억은 4월 30일까지 행안부-기재부 장관급 협의 완료 조건\n"
        "- **3호**: 전략 이행 거버넌스 — 월 1회 차관 주재 추진위원회, 분기 1회 장관 보고\n"
        "- **4호**: 민간 협력 파트너 선정 방식 — 경쟁 입찰 原則, 단 R&D 과제는 수의 계약 허용\n\n"
        "## 주요 논의 사항\n"
        "- 공무원 AI 보조 도구의 개인정보 처리 적법성 검토 필요 (법제처 사전 의견 요청 합의)\n"
        "- AI 할루시네이션 대응 방안 — 행정 문서 생성 AI에 검증 레이어 의무화 방침 확정\n"
        "- NIPA·NIA 역할 분담: NIPA는 AI 기술 지원, NIA는 데이터 인프라 전담\n\n"
        "## 액션 아이템\n"
        "| # | 담당자 | 내용 | 기한 | 상태 |\n"
        "|---|--------|------|------|------|\n"
        "| 1 | 홍길동 | 4대 집중 과제 실행 계획서 초안 작성 | 3/31 | 진행 중 |\n"
        "| 2 | 이영희 | 법제처 개인정보 처리 적법성 사전 의견 요청 공문 발송 | 3/24 | 미착수 |\n"
        "| 3 | 박민준 | 기재부 협의 172억 관련 예산 협의 자료 작성 | 4/7 | 미착수 |\n"
        "| 4 | 최지수 | NIA 공공데이터 인프라 투자 계획 제출 | 4/14 | 미착수 |\n"
        "| 5 | 손지원 | 민간 협력 모델 사례 조사(일본·영국·싱가포르) 제출 | 4/7 | 미착수 |\n"
        "\n"
        "**다음 회의**: 2026년 4월 14일 (월) 10:00 / 실행 계획서 검토 및 예산 협의 결과 공유\n"
    ),
    docs=[
        DocumentSpec(
            key="meeting_summary",
            template_file="meeting_minutes_kr/meeting_summary.md.j2",
            json_schema={
                "type": "object",
                "required": ["meeting_info", "agenda_items", "discussion_points",
                             "decisions_made", "next_meeting"],
                "properties": {
                    "meeting_info":      {"type": "string"},
                    "agenda_items":      {"type": "array", "items": {"type": "string"}},
                    "discussion_points": {"type": "array", "items": {"type": "string"}},
                    "decisions_made":    {"type": "array", "items": {"type": "string"}},
                    "next_meeting":      {"type": "string"},
                },
            },
            stabilizer_defaults={
                "meeting_info":      "",
                "agenda_items":      [],
                "discussion_points": [],
                "decisions_made":    [],
                "next_meeting":      "",
            },
            lint_headings=["# 회의록:", "## 회의 개요", "## 안건", "## 주요 논의 사항"],
            validator_headings=["## 회의 개요", "## 안건", "## 주요 논의 사항",
                                "## 의사결정 사항", "## 다음 회의"],
            critical_non_empty_headings=["## 회의 개요", "## 의사결정 사항"],
        ),
        DocumentSpec(
            key="action_items",
            template_file="meeting_minutes_kr/action_items.md.j2",
            json_schema={
                "type": "object",
                "required": ["items", "priority_actions", "blockers", "review_date"],
                "properties": {
                    "items":            {"type": "array", "items": {"type": "string"}},
                    "priority_actions": {"type": "array", "items": {"type": "string"}},
                    "blockers":         {"type": "array", "items": {"type": "string"}},
                    "review_date":      {"type": "string"},
                },
            },
            stabilizer_defaults={
                "items":            [],
                "priority_actions": [],
                "blockers":         [],
                "review_date":      "",
            },
            lint_headings=["# 액션 아이템:", "## 전체 액션 목록", "## 우선순위 액션"],
            validator_headings=["## 전체 액션 목록", "## 우선순위 액션",
                                "## 차단 이슈", "## 점검일"],
            critical_non_empty_headings=["## 전체 액션 목록", "## 우선순위 액션"],
        ),
        DocumentSpec(
            key="decision_log",
            template_file="meeting_minutes_kr/decision_log.md.j2",
            json_schema={
                "type": "object",
                "required": ["decisions", "rationale", "alternatives_considered", "impact_assessment"],
                "properties": {
                    "decisions":              {"type": "array", "items": {"type": "string"}},
                    "rationale":              {"type": "string"},
                    "alternatives_considered":{"type": "array", "items": {"type": "string"}},
                    "impact_assessment":      {"type": "string"},
                },
            },
            stabilizer_defaults={
                "decisions":               [],
                "rationale":               "",
                "alternatives_considered": [],
                "impact_assessment":       "",
            },
            lint_headings=["# 의사결정 기록:", "## 결정 사항", "## 결정 배경"],
            validator_headings=["## 결정 사항", "## 결정 배경",
                                "## 검토한 대안", "## 영향도 평가"],
            critical_non_empty_headings=["## 결정 사항", "## 결정 배경"],
        ),
    ],
)

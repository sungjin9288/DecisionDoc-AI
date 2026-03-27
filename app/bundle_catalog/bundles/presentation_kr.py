"""presentation_kr bundle — 발표 자료 (한국어, 학생/직장인 공통).

3개 문서:
  1. slide_structure — 슬라이드 구성안
  2. slide_script    — 발표 스크립트
  3. qa_preparation  — Q&A 대비
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

PRESENTATION_KR = BundleSpec(
    id="presentation_kr",
    name_ko="발표 자료",
    name_en="Presentation",
    description_ko="수업·업무 발표를 위한 슬라이드 구성안·발표 스크립트·Q&A 대비 3종 문서.",
    icon="🎤",
    prompt_language="ko",
    prompt_hint=(
        "당신은 TED 강연 코치 경험이 있는 프레젠테이션 전문가입니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 청중이 3분 후에 기억할 핵심 메시지는 무엇인가, "
        "(2) 도입부가 청중의 호기심을 즉각 자극하는가, (3) 각 슬라이드가 스토리 흐름에 기여하는가.\n"
        "- 오프닝은 질문, 통계, 사례 중 하나로 시작해 청중의 관심을 즉시 끄세요.\n"
        "- 슬라이드당 핵심 메시지 1개 원칙을 엄수하고, 텍스트는 최소화하세요.\n"
        "- 스토리 구조(문제 제기 → 갈등/원인 → 해결책 → 행동 촉구)를 명확히 구성하세요.\n"
        "- Q&A는 예상 어려운 질문에 대한 구체적 답변 전략을 포함하세요.\n"
        "- slide_outline 은 PPT 슬라이드별 구성안입니다. page·title·key_content·design_tip 을 채우세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="consulting",
    few_shot_example=(
        "## 슬라이드 예시\n"
        "\n"
        "**[슬라이드 2] 핵심 문제**\n"
        "제목: \"왜 지금 바꿔야 하는가?\"\n"
        "핵심 내용: 현재 방식으로는 연간 35억 원 기회비용 발생. 경쟁사 A는 이미 전환 완료 후 NPS 22점 상승.\n"
        "디자인 힌트: 좌측 현황 수치(빨간 강조) vs 우측 전환 후 목표(녹색 강조) 대비 레이아웃\n"
        "\n"
        "**[슬라이드 3] 제안 솔루션**\n"
        "제목: \"3단계 전환 로드맵\"\n"
        "핵심 내용: Q1 파일럿(5개 팀) → Q2 전사 확대 → Q3 최적화. 추가 투자 없이 기존 라이선스 활용.\n"
        "디자인 힌트: 타임라인 인포그래픽, 각 단계 체크포인트 강조\n"
    ),
    docs=[
        DocumentSpec(
            key="slide_structure",
            template_file="presentation_kr/slide_structure.md.j2",
            json_schema={
                "type": "object",
                "required": ["presentation_goal", "target_audience", "key_messages",
                             "total_slides", "slide_outline"],
                "properties": {
                    "presentation_goal": {"type": "string"},
                    "target_audience":   {"type": "string"},
                    "key_messages":      {"type": "array", "items": {"type": "string"}},
                    "total_slides":      {"type": "integer"},
                    "slide_outline":     {"type": "array", "items": _SLIDE_ITEM},
                },
            },
            stabilizer_defaults={
                "presentation_goal": "",
                "target_audience":   "",
                "key_messages":      [],
                "total_slides":      0,
                "slide_outline":     [],
            },
            lint_headings=["# 슬라이드 구성안:", "## 발표 목표", "## 핵심 메시지", "## PPT 구성 가이드"],
            validator_headings=["## 발표 목표", "## 대상 청중", "## 핵심 메시지",
                                "## PPT 구성 가이드"],
            critical_non_empty_headings=["## 발표 목표", "## 핵심 메시지"],
        ),
        DocumentSpec(
            key="slide_script",
            template_file="presentation_kr/slide_script.md.j2",
            json_schema={
                "type": "object",
                "required": ["opening", "body_scripts", "closing", "time_allocation"],
                "properties": {
                    "opening":         {"type": "string"},
                    "body_scripts":    {"type": "array", "items": {"type": "string"}},
                    "closing":         {"type": "string"},
                    "time_allocation": {"type": "string"},
                },
            },
            stabilizer_defaults={
                "opening":         "",
                "body_scripts":    [],
                "closing":         "",
                "time_allocation": "",
            },
            lint_headings=["# 발표 스크립트:", "## 오프닝", "## 본론 스크립트", "## 클로징"],
            validator_headings=["## 오프닝", "## 본론 스크립트", "## 클로징", "## 시간 배분"],
            critical_non_empty_headings=["## 오프닝", "## 본론 스크립트", "## 클로징"],
        ),
        DocumentSpec(
            key="qa_preparation",
            template_file="presentation_kr/qa_preparation.md.j2",
            json_schema={
                "type": "object",
                "required": ["anticipated_questions", "answers", "difficult_questions",
                             "presentation_tips"],
                "properties": {
                    "anticipated_questions": {"type": "array", "items": {"type": "string"}},
                    "answers":               {"type": "array", "items": {"type": "string"}},
                    "difficult_questions":   {"type": "array", "items": {"type": "string"}},
                    "presentation_tips":     {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "anticipated_questions": [],
                "answers":               [],
                "difficult_questions":   [],
                "presentation_tips":     [],
            },
            lint_headings=["# Q&A 대비:", "## 예상 질문", "## 답변 준비", "## 어려운 질문"],
            validator_headings=["## 예상 질문", "## 답변 준비", "## 어려운 질문", "## 발표 팁"],
            critical_non_empty_headings=["## 예상 질문", "## 답변 준비"],
        ),
    ],
)

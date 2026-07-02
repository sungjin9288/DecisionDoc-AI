"""Mock fixture builders for the presentation_kr bundle."""
from app.providers.mock.shared import _slide


def _presentation_slide_structure(title: str, goal: str, ctx: str) -> dict:
    ctx_note = f" ({ctx})" if ctx else ""
    return {
        "presentation_goal": f"{title}에 관한 발표를 통해 {goal}을 청중에게 효과적으로 전달합니다.{ctx_note}",
        "target_audience": "수업 담당 교수 및 동료 학생 / 업무 발표 참석자",
        "key_messages": [
            f"{title}의 핵심 문제와 해결 방향",
            f"{goal}을 통해 기대되는 구체적 효과",
            "실행 가능한 다음 단계와 결론",
        ],
        "total_slides": 5,
        "slide_outline": [
            _slide(1, f"{title} — 발표 개요",
                   f"발표 배경: {goal}\n발표 구성: 문제 → 분석 → 해결책 → 기대 효과 → 결론",
                   "표지 슬라이드. 제목 중앙 대형 Bold, 배경 심플하게."),
            _slide(2, "문제 정의 및 배경",
                   f"{title}이 해결하려는 핵심 문제\n현재 Pain Point 2~3가지\n해결 시 기대 변화",
                   "좌측 현재 상황 아이콘, 우측 문제 카드. 핵심 수치 강조 박스."),
            _slide(3, "핵심 내용 및 분석",
                   f"{goal}을 달성하기 위한 핵심 접근법\n주요 근거 데이터 또는 논리 구조",
                   "2~3단 분할 또는 비교 테이블. 핵심 키워드 Bold."),
            _slide(4, "제안 및 기대 효과",
                   "제안하는 해결책 또는 결론\n예상 효과: 효율 향상, 비용 절감\n실행 로드맵",
                   "Before/After 비교 또는 로드맵 타임라인."),
            _slide(5, "결론 및 Q&A",
                   f"핵심 메시지 3줄 요약\n{title} 발표의 의의\nQ&A 안내",
                   "미니멀 마무리. 핵심 메시지 중앙 Bold. 하단 참고문헌."),
        ],
    }

def _presentation_slide_script(title: str, goal: str, ctx: str) -> dict:  # noqa: ARG001
    return {
        "opening": (
            f"안녕하세요. '{title}'을 주제로 발표를 맡은 [발표자]입니다. "
            f"{goal}에 대해 함께 살펴보겠습니다. 약 [X]분간 진행됩니다."
        ),
        "body_scripts": [
            f"[슬라이드 2] 먼저 문제 배경입니다. {title}과 관련하여 현재 [문제]가 발생하고 있습니다.",
            f"[슬라이드 3] {goal}을 달성하기 위해 [접근 방법]을 선택하였습니다.",
            "[슬라이드 4] 기대 효과는 [효과 1], [효과 2]이며 실행 계획은 [로드맵]입니다.",
        ],
        "closing": f"오늘 발표에서는 {title}의 문제, 분석, 제안을 살펴보았습니다. 청취해주셔서 감사합니다.",
        "time_allocation": "오프닝: 1분 / 본론: 11분 / 결론 및 Q&A: 3분 (총 15분)",
    }

def _presentation_qa_preparation(title: str, goal: str, ctx: str) -> dict:  # noqa: ARG001
    return {
        "anticipated_questions": [
            f"{goal}을 선택한 근거는 무엇인가요?",
            "제안의 한계점이나 위험 요소는 없나요?",
            "다른 대안과 비교 시 장점은 무엇인가요?",
            "실제 적용에 필요한 자원은 얼마나 되나요?",
        ],
        "answers": [
            f"{goal} 선택 이유는 [근거 1]과 [근거 2]입니다.",
            "한계로는 [한계 1]이 있으며, [대응 방안]을 준비했습니다.",
            "[대안 A]보다 [장점 1], [장점 2] 측면에서 우위입니다.",
            "[예상 기간]과 [예산]이 필요합니다.",
        ],
        "difficult_questions": [
            "데이터 신뢰성 → 복수 출처 교차 검증으로 보장.",
            "플랜 B → [대안 방안] 준비, 단계적 rollback 고려.",
        ],
        "presentation_tips": [
            "핵심 수치는 슬라이드에 미리 표시 후 구두로 강조.",
            "모르는 질문엔 솔직히 인정하고 추가 조사 후 공유 약속.",
            "각 슬라이드 배분 시간을 미리 연습하여 시간 준수.",
        ],
    }

"""app/storage/default_styles.py — Pre-built style profiles for immediate use.

These are loaded automatically on first startup via StyleStore.initialize_defaults().
"""

DEFAULT_STYLE_PROFILES = [
    {
        "style_id": "default-official",
        "name": "공식 보고서체",
        "description": "행안부·공공기관 표준 문체. 격식체, 3인칭, 밀도 높음.",
        "is_default": True,
        "is_system": True,
        "tone_guide": {
            "formality": "formal",
            "density": "dense",
            "perspective": "third_person",
            "sentence_style": "formal_korean",
        },
        "custom_rules": [
            "문장은 '~하였다', '~한다', '~임' 형태로 종결한다",
            "수치는 반드시 단위와 함께 표기한다",
            "항목 나열 시 번호 또는 기호(•)를 사용한다",
            "외래어는 처음 등장 시 영문 병기한다",
            "제목과 소제목은 명사형으로 종결한다",
        ],
        "forbidden_expressions": [
            "~인 것 같습니다", "~할 수도 있습니다", "아마도",
            "~하면 좋을 것 같습니다", "저희", "우리",
        ],
        "few_shot_example": (
            "## 1. 사업 개요\n\n"
            "본 사업은 공공기관 디지털 전환 촉진을 위하여 "
            "AI 기반 문서 자동화 시스템을 구축하는 것을 목적으로 한다. "
            "총 사업비는 5억원(VAT 포함)이며, 사업 기간은 "
            "2025년 3월부터 2025년 12월까지(10개월)로 계획하였다.\n\n"
            "## 2. 추진 배경\n\n"
            "공공부문의 문서 작성 업무는 전체 행정 업무의 약 40%를 차지하며, "
            "반복적·정형적 문서 작성에 소요되는 시간이 상당한 수준임. "
            "이에 AI 기술을 활용한 문서 자동화를 통해 업무 효율성 제고가 필요하다."
        ),
        "avatar_color": "#6366f1",
    },
    {
        "style_id": "default-consulting",
        "name": "컨설팅 제안서체",
        "description": "전략 컨설팅 스타일. 간결하고 임팩트 있는 문체.",
        "is_default": False,
        "is_system": True,
        "tone_guide": {
            "formality": "professional",
            "density": "concise",
            "perspective": "mixed",
            "sentence_style": "consulting",
        },
        "custom_rules": [
            "핵심 메시지를 첫 문장에 배치한다 (Pyramid 구조)",
            "문장은 2줄 이내로 작성한다",
            "수치와 데이터로 주장을 뒷받침한다",
            "액션 아이템은 동사로 시작한다",
            "전문용어 사용 시 간략한 설명을 병기한다",
        ],
        "forbidden_expressions": [
            "~라고 생각합니다", "~인 것 같습니다",
            "열심히", "최선을 다해", "노력하겠습니다",
        ],
        "few_shot_example": (
            "## Executive Summary\n\n"
            "본 제안은 귀사의 운영 효율을 **30% 향상**시키는 "
            "3단계 디지털 전환 로드맵을 제시합니다.\n\n"
            "**핵심 과제 3가지:**\n"
            "1. 레거시 시스템 현대화 (6개월, ROI 180%)\n"
            "2. 데이터 통합 플랫폼 구축 (4개월)\n"
            "3. AI 자동화 적용 (3개월, 연 2억원 절감)\n\n"
            "## 현황 진단\n\n"
            "현재 수동 처리 비율 78%, 데이터 사일로 5개 존재. "
            "업계 평균 대비 처리 속도 2.3배 느림."
        ),
        "avatar_color": "#0ea5e9",
    },
    {
        "style_id": "default-internal",
        "name": "사내 업무체",
        "description": "팀 내부 보고 및 협업용. 실무적이고 간명한 문체.",
        "is_default": False,
        "is_system": True,
        "tone_guide": {
            "formality": "semi-formal",
            "density": "balanced",
            "perspective": "first_person_plural",
            "sentence_style": "business_casual",
        },
        "custom_rules": [
            "문장은 '~했습니다', '~입니다', '~예정입니다' 로 종결한다",
            "항목별 현황과 조치사항을 함께 기술한다",
            "일정은 구체적인 날짜로 표기한다",
            "이슈는 원인-영향-조치 순으로 서술한다",
            "불필요한 수식어를 제거하고 핵심만 기술한다",
        ],
        "forbidden_expressions": [
            "~하여야 할 것으로 사료됩니다",
            "심심한 유감", "유감스럽게도",
            "~하는 바입니다",
        ],
        "few_shot_example": (
            "## 이번 주 진행 현황\n\n"
            "**완료:**\n"
            "- API 연동 개발 완료 (3/15)\n"
            "- 테스트 시나리오 20건 검증 완료\n\n"
            "**진행 중:**\n"
            "- UI 개선 작업 (진행률 70%, 3/20 완료 예정)\n"
            "- 성능 최적화 (담당: 개발팀)\n\n"
            "**이슈:**\n"
            "- 외부 API 응답 지연 (평균 3초 → 목표 1초)\n"
            "  → 캐싱 적용으로 해결 예정 (3/18)\n\n"
            "**다음 주 계획:**\n"
            "- QA 테스트 착수, 배포 준비"
        ),
        "avatar_color": "#10b981",
    },
]

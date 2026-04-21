"""app/bundle_catalog/system_prompt.py — Quality guidelines injected into all bundle prompts."""
from __future__ import annotations

QUALITY_IMPROVEMENTS = """
## 품질 기준 (반드시 준수)
### 구체성
- 수치, 일정, 담당자를 명시할 수 있는 경우 반드시 포함
- "약 X%" 보다 "X%" 형태로 작성
- 애매한 표현("적절히", "충분히", "빠르게") 사용 금지
### 완결성
- 각 섹션은 독립적으로 읽혀도 이해 가능해야 함
- 결론/요약 섹션에 핵심 내용이 반드시 포함될 것
- 마지막 섹션은 명확한 다음 단계(Next Steps)로 마무리
### 공공기관 문서 특화
- 법령/지침 인용 시 정확한 명칭 사용
- 예산 표기: "X억원(부가세 포함)" 형태
- 기간 표기: "YYYY년 M월 ~ YYYY년 M월 (N개월)" 형태
- 담당 부서/기관명은 공식 명칭 사용
### 금지 사항
- 내용 없는 placeholder 텍스트 ([내용 입력], TBD 등)
- 중복 섹션 또는 반복 내용
- 근거 없는 수치 또는 통계
- 근거 없는 날짜, 예산, 기관명, 기술명, 배점, 일정의 임의 생성
"""


def enhance_bundle_prompt(base_prompt: str) -> str:
    """Append quality guidelines to any bundle prompt."""
    return base_prompt + "\n\n" + QUALITY_IMPROVEMENTS.strip()

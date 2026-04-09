# DecisionDoc AI Sales Pack

이 디렉토리는 고객 설명, 내부 검토, 초기 제안 미팅에 바로 사용할 수 있는 영업용 문서를 모아 둔 경로입니다.

## 문서 구성

- `product_brief.md`
  - 제품 개요
  - 해결하는 문제
  - 주요 기능
  - 도입 효과

- `executive_intro.md`
  - 외부 대표 및 초기 미팅용 요약 소개서
  - 제품 포지셔닝, 핵심 가치, 도입 방식, 기대 효과
  - `scripts/build_sales_intro_pdf.py`로 PDF 재생성 가능
  - 기본 산출 경로: `output/pdf/decisiondoc_ai_executive_intro_ko.pdf`

- `notebooklm_comparison.md`
  - NotebookLM과의 차이
  - 우리 제품의 강점
  - 적합한 고객/시나리오

- `internal_deployment_brief.md`
  - 내부 설치형 운영 방식
  - `admin` / `dawool` 분리 운영 구조
  - 보안, 권한, 로그, 운영 포인트

## 권장 사용 순서

1. 첫 소개 미팅: `product_brief.md`
2. 경쟁 제품 비교 질문 대응: `notebooklm_comparison.md`
3. 보안/설치/운영 질문 대응: `internal_deployment_brief.md`

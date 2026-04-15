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

- `meeting_onepager.md`
  - 대표 미팅 직전 공유용 1장 요약본
  - 아주 짧은 포지셔닝, 차별점, 도입 방식, 후속 제안 정리
  - 같은 PDF 빌더 스크립트로 별도 PDF 생성 가능

- `talk_track.md`
  - 대표 미팅용 말하기 스크립트
  - 30초 / 2분 / 5분 버전으로 구성
  - 설치형 구조, 차별점, 질문 대응 문구 포함

- `notebooklm_comparison.md`
  - NotebookLM과의 차이
  - 우리 제품의 강점
  - 적합한 고객/시나리오

- `demo_runbook.md`
  - 외부 대표 및 초기 미팅용 시연 스크립트
  - 현재 검증 완료 범위와 선택 시연 구간 구분
  - 질문 대응 문구와 후속 액션 정리

- `internal_deployment_brief.md`
  - 내부 설치형 운영 방식
  - `admin` / `dawool` 분리 운영 구조
  - 보안, 권한, 로그, 운영 포인트

- `company_delivery_guide.md`
  - 회사 전달 순서
  - 외부/내부 발송 문구 템플릿
  - 첨부 패키지와 보안 경계 기준

## PDF 재생성

- 단일 소개서:
  - `python3 scripts/build_sales_intro_pdf.py`
- 소개 자료 패키지 일괄 생성:
  - `python3 scripts/build_sales_pack.py`

기본 생성 파일:

- `output/pdf/decisiondoc_ai_executive_intro_ko.pdf`
- `output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf`
- `output/pdf/decisiondoc_ai_notebooklm_comparison_ko.pdf`
- `output/pdf/decisiondoc_ai_internal_deployment_brief_ko.pdf`
- `output/pdf/decisiondoc_ai_company_delivery_guide_ko.pdf`

## 권장 사용 순서

1. 첫 소개 미팅: `product_brief.md`
2. 미팅 직전 1장 공유: `meeting_onepager.md`
3. 대표 앞 설명 준비: `talk_track.md`
4. 대표 시연 진행: `demo_runbook.md`
5. 경쟁 제품 비교 질문 대응: `notebooklm_comparison.md`
6. 보안/설치/운영 질문 대응: `internal_deployment_brief.md`
7. 실제 회사 전달 문구/순서: `company_delivery_guide.md`

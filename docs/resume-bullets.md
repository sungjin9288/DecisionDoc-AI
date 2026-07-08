# Resume Bullets

분석 기준: 2026-07-09 현재 저장소 코드, README, docs, evidence, completion readiness receipt, 최근 git log, worktree 상태, 최신 GitHub Actions CI/CD 결과를 기준으로 업데이트했다. 직접 설명 가능한 범위는 `docs/contribution-note.md`를 기준으로 한다.

## 1. 이력서용 프로젝트 제목 후보

- DecisionDoc AI - FastAPI 기반 AI 문서 생성 및 협업 플랫폼
- LLM Provider Abstraction 기반 의사결정 문서 자동화 서비스
- 프로젝트 지식 재사용과 문서 export를 지원하는 AI 업무 문서 생성 API

## 2. 한 줄 소개 후보

- FastAPI와 LLM provider abstraction을 활용해 의사결정 문서, 제안서, 보고서 초안을 생성하고 저장/export하는 AI 문서 생성 플랫폼을 개발 중입니다.
- 문서 유형별 bundle schema, Jinja2 template, validation/lint를 결합해 LLM 생성 결과를 업무 산출물로 관리하는 서비스를 구현했습니다.
- 파일/PDF 업로드, 프로젝트 지식 문서, 승인/공유/이력 흐름을 연결하는 AI 기반 문서 업무 자동화 MVP를 고도화하고 있습니다.

## 3. 현재 이력서에 넣어도 되는 bullet

- 반복적인 업무 문서 초안 작성 문제를 해결하기 위해 FastAPI 기반 `/generate` API를 구현하고, Pydantic `GenerateRequest`와 bundle schema로 입력/출력 구조를 표준화한 AI 문서 생성 MVP를 개발 중
- LLM provider 교체와 장애 대응을 고려해 Mock/OpenAI/Gemini/Claude/Local provider factory와 fallback chain을 구성하고, 모델 의존 로직을 route handler 밖으로 분리
- 문서 유형별 품질 편차를 줄이기 위해 `BundleSpec`/`DocumentSpec`, Jinja2 template, stabilizer, lint/validation 단계를 결합한 생성 파이프라인 설계
- 업로드 문서와 PDF에서 추출한 맥락을 기반으로 문서를 생성할 수 있도록 `/generate/from-documents`, `/generate/from-pdf`, attachment parsing 흐름을 구현
- 생성 결과를 단발성 응답에 그치지 않도록 project, knowledge, approval, history/share, export API와 연결해 후속 검토/공유 흐름을 지원
- 공공조달 decision package local evidence path를 fixture 기반으로 정리하고, `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`과 stdout JSON success/failure contract를 검증하는 CLI receipt 흐름 추가
- live provider, G2B 실데이터, 배포 smoke를 실행 전 readiness check로 분리하고, secret을 출력하지 않는 local receipt/checker 흐름 추가
- static PWA의 inline handler를 제거하고 CSP nonce 기본 적용 및 브라우저 screenshot/console/CSP evidence를 갱신
- Docker Compose, Dockerfile, AWS SAM, smoke script, pytest suite를 통해 로컬 개발, 배포, 검증 경로를 갖춘 Python 백엔드 프로젝트로 구성
- 문제정의, 요구사항 정리, 사용자 흐름, 문서화 역량을 활용해 문서 생성 문제를 입력 구조, 생성 파이프라인, 산출물 관리, 운영 검증 항목으로 분해

## 4. 구현 후 넣을 수 있는 bullet

- 구현 후 사용 가능: 실제 사용자 피드백과 사용 로그를 기반으로 문서 생성 품질 개선 루프를 운영하고, correction artifact를 fine-tuning/eval 데이터로 전환
- 구현 후 사용 가능: 검증된 배포 URL, smoke evidence, UAT 결과를 확보해 외부 접근 가능한 AI 문서 생성 서비스로 검증
- 구현 후 사용 가능: tenant별 권한, billing, SSO, audit 흐름을 실제 운영 환경에서 검증해 조직 단위 문서 협업 플랫폼으로 확장

## 5. 기술스택 한 줄

- 현재 사용 중: Python, FastAPI, Pydantic v2, Jinja2, OpenAI API, Google Gemini, Claude, local/mock provider, pytest, Docker, Docker Compose, AWS SAM/Lambda, boto3, Playwright, python-docx, python-pptx, xlsxwriter
- 예정/검증 필요: live provider route 운영, tenant별 운영 준비성, 사용자 성과 측정 dashboard

## 6. 지원 직무별 강조 포인트

### AI/IT 개발자

- FastAPI API 설계, provider abstraction, schema validation, storage/export, pytest 검증 경험을 강조

### AI 서비스 기획

- 문서 작성 업무를 bundle, 사용자 입력, 생성 결과, 검토/export 흐름으로 분해한 점을 강조

### AI 솔루션 엔지니어

- provider 교체, local/S3 storage, Docker/AWS 배포 경로, 운영 smoke script를 갖춘 통합형 구조를 강조

### DX/AI 컨설팅 주니어

- 조직의 반복 문서 업무를 AI 기반 워크플로우로 구조화하고 기대효과/운영 리스크를 함께 정리한 점을 강조

## 7. 쓰면 위험한 표현

- 실제 고객 사용 서비스라고 단정
- 실제 고객 생산성 개선 수치 달성
- 모든 기업 문서 자동화
- 완전한 보안 인증/컴플라이언스 완료
- 모든 LLM provider가 실제 운영 환경에서 안정 검증됐다고 단정

## 8. 보완 후 쓸 수 있는 표현

- 배포 URL과 smoke evidence 확보 후: Docker/AWS 기반 배포 및 운영 검증 경험
- 사용자 테스트 후: 실제 사용자 피드백을 반영한 AI 문서 생성 UX 개선 경험
- live provider 검증 후: OpenAI/Gemini/Claude fallback route를 활용한 provider resilience 설계 경험
- G2B stage smoke 후: 공공조달 실데이터 기반 Go/No-Go decision package 검증 경험
- local evidence 설명 시: `scripts/validate_procurement_decision_package_cli_contract_manifest.py`, `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`, `--write-result`, `--result-path` 기반의 fixture 검증 범위로 제한
- 성과 측정 후: 문서 초안 작성 시간 또는 재작업률 개선 수치

## 9. 최종 판단

- 현재 이력서 반영 가능 여부: 조건부 가능
- 이유: 코드 근거가 있는 API, service, provider/storage, bundle, export, 테스트/배포 구조가 충분하고, 로컬 non-live gate와 최신 GitHub Actions CI/CD, UI/CSP 및 post-login UI flow evidence가 있다. 다만 live provider, G2B 실데이터, 배포 URL, 사용자 성과는 아직 미검증이다.
- 이력서에 넣기 전 반드시 보완할 것: GitHub 링크, 검증된 데모 URL 또는 로컬 screenshot, 대표 API 호출 예시, 직접 설명 범위 확인
- 가장 먼저 개선해야 할 것: `docs/completion-readiness-runbook.md` 순서대로 M1 live provider, M2 G2B 실데이터, M6 배포 smoke 중 실제 외부 증거를 하나씩 확보

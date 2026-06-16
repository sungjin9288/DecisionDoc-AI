# README Improvement Plan

분석 기준: 2026-06-09 현재 저장소 코드, README, docs, 설정 파일, 최근 git log, worktree 상태를 기준으로 업데이트했다. `README.md`는 직접 수정하지 않고 개선안만 이 문서에 정리했다.

## 1. 현재 README의 문제점

- 현재 `README.md`는 일반 사용자나 채용 담당자를 위한 프로젝트 소개라기보다 `AGENTS.md` 성격의 저장소 운영 규칙에 가깝다.
- 프로젝트가 해결하는 문제, 핵심 사용자 흐름, 구현 완료 기능, 실행 예시가 첫 화면에서 바로 보이지 않는다.
- 구현 완료, 개발 중, 운영 문서상 존재, 검증 필요 항목이 분리되어 있지 않아 포트폴리오로 읽기 어렵다.
- 데모 링크, 스크린샷, API 예시, representative output이 부족하다.
- 기술적 강점인 provider abstraction, bundle schema, validation/export pipeline이 README 초반에 드러나지 않는다.

## 2. README에 추가해야 할 섹션

# DecisionDoc AI

## 1. 프로젝트 개요
## 2. 개발 배경
## 3. 주요 기능
  - 구현 완료
  - 개발 중
  - 향후 개선
## 4. 기술 스택
## 5. 시스템 구조
## 6. 핵심 구현 내용
## 7. 실행 방법
## 8. 환경변수
## 9. 화면 예시
## 10. 개발 과정에서 해결한 문제
## 11. 비즈니스/사용자 관점의 적용 가능성
## 12. 향후 개선 계획

## 3. README 초안

# DecisionDoc AI

DecisionDoc AI는 사용자의 요구사항, 참고 문서, PDF, 프로젝트 지식 문서를 기반으로 의사결정 문서와 업무 산출물 초안을 생성하고, 저장/검토/export 흐름까지 연결하는 FastAPI 기반 AI 문서 생성 플랫폼입니다.

현재 저장소는 MVP 구현 후 고도화 중인 상태입니다. 구현 완료 기능과 검증 필요 항목을 분리해 관리합니다.

## 1. 프로젝트 개요

- 프로젝트 유형: 개인 PoC / MVP 확장 프로젝트
- 현재 상태: MVP 구현 후 고도화 중
- 핵심 문제: 반복적인 업무 문서 작성, 참고 자료 반영, 검토/공유/export 흐름이 분산되는 문제
- 핵심 해결 방식: LLM 생성 결과를 bundle schema, template, validation, storage, export workflow로 관리

## 2. 개발 배경

LLM으로 문서 초안을 생성하는 것은 쉽지만, 실제 업무에서는 다음 문제가 남습니다.

- 문서 유형별 구조와 필수 항목이 매번 달라진다.
- 참고 문서와 프로젝트 지식을 일관되게 반영하기 어렵다.
- 생성 결과를 검토, 승인, 공유, export하는 흐름이 분리된다.
- 모델 출력이 자유 텍스트에 머물면 품질 검증과 재사용이 어렵다.

DecisionDoc AI는 이 문제를 API, schema, template, validation, workflow로 나누어 해결하는 것을 목표로 합니다.

## 3. 주요 기능

### 구현 완료

- FastAPI 기반 문서 생성 API
  - `POST /generate`
  - `POST /generate/stream`
  - `POST /generate/export`
  - `POST /generate/from-documents`
  - `POST /generate/from-pdf`
- 문서 bundle catalog
  - `BundleSpec`, `DocumentSpec`
  - 기술 의사결정, 제안서, 보고서, 회의록, PRD, RFP 분석 등 bundle
- LLM provider abstraction
  - mock, openai, gemini, claude, local
  - provider fallback chain
- 문서 렌더링과 export
  - Markdown
  - DOCX/PDF/HWP/XLSX/PPTX 관련 service
- 프로젝트 기반 업무 흐름
  - projects
  - knowledge documents
  - approvals
  - history/share
- 운영/검증 기능
  - `/health`, `/metrics`, `/version`
  - pytest test suite
  - smoke scripts
- 배포 경로
  - Docker Compose
  - AWS SAM/Lambda

### 개발 중

- report quality learning
- document ops agent
- correction artifact/training workflow
- fine-tuning/model registry workflow
- post-deploy evidence 자동화

### 향후 개선

- 데모 URL과 스크린샷 공개
- 실제 사용자 피드백 기반 개선
- live provider 검증 로그 확보
- README 중심의 포트폴리오 정리
- 성과 지표 수집

## 4. 기술 스택

| 영역 | 기술 |
|---|---|
| Language | Python 3.12 |
| Backend | FastAPI, Pydantic v2 |
| Template | Jinja2 |
| AI/LLM | OpenAI, Gemini, Claude, local provider, mock provider |
| Storage | Local filesystem, AWS S3 option |
| Export | python-docx, python-pptx, Playwright, xlsxwriter, pdfplumber |
| Deploy | Docker, Docker Compose, AWS SAM/Lambda |
| Test | pytest, pytest-playwright, smoke scripts |

## 5. 시스템 구조

```text
User / Browser PWA
-> FastAPI app
-> Middleware: request id, observability, tenant, auth, audit, billing, rate limit, security headers
-> Routers: generate, projects, knowledge, approvals, report-workflows, g2b, admin, health
-> Services: GenerationService, ReportWorkflowService, DecisionCouncilService
-> Providers: Mock / OpenAI / Gemini / Claude / Local / fallback chain
-> BundleSpec + Jinja2 templates + validation/lint
-> Storage: LocalStorage or S3Storage
-> Markdown / export / API response
```

## 6. 핵심 구현 내용

### Provider abstraction

`app/providers/factory.py`는 `DECISIONDOC_PROVIDER`와 capability-specific provider env를 읽어 provider를 생성합니다.
단일 provider뿐 아니라 comma-separated fallback chain도 지원합니다.

### Bundle schema

`app/bundle_catalog/spec.py`의 `BundleSpec`과 `DocumentSpec`은 문서 유형별 JSON schema, template, lint heading, stabilizer defaults를 한 곳에서 관리합니다.

### Generation pipeline

`app/services/generation_service.py`는 생성 요청을 받아 provider 호출, 안정화, 저장, 렌더링, lint/validation, metadata 기록을 수행합니다.

### Storage abstraction

`app/storage/factory.py`와 `app/storage/base.py`는 local 또는 S3 storage를 선택할 수 있게 합니다.
local JSON store는 atomic write helper를 사용합니다.

## 7. 실행 방법

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Docker Compose:

```bash
docker compose up -d
curl http://localhost:3300/health
```

테스트:

```bash
pytest tests/
```

Smoke:

```bash
python scripts/smoke.py
python scripts/ops_smoke.py
```

## 8. 환경변수

주요 환경변수:

| 변수 | 설명 |
|---|---|
| `DECISIONDOC_PROVIDER` | `mock`, `openai`, `gemini`, `claude`, `local` 또는 fallback chain |
| `DECISIONDOC_PROVIDER_GENERATION` | generation capability 전용 provider |
| `DECISIONDOC_PROVIDER_ATTACHMENT` | attachment parsing 전용 provider |
| `DECISIONDOC_PROVIDER_VISUAL` | visual asset 전용 provider |
| `DECISIONDOC_STORAGE` | `local` 또는 `s3` |
| `DATA_DIR` | local data directory |
| `DECISIONDOC_API_KEYS` | API 인증 키 목록 |
| `DECISIONDOC_OPS_KEY` | ops endpoint 인증 키 |
| `OPENAI_API_KEY` | OpenAI provider 사용 시 필요 |
| `GEMINI_API_KEY` | Gemini provider 사용 시 필요 |
| `ANTHROPIC_API_KEY` | Claude provider 사용 시 필요 |
| `DECISIONDOC_S3_BUCKET` | S3 storage 사용 시 필요 |

## 9. 화면 예시

추가 필요:

- Web UI 첫 화면
- bundle 선택 화면
- 문서 생성 결과
- 파일 업로드 생성
- export 결과
- report workflow 화면

## 10. 개발 과정에서 해결한 문제

- LLM 자유 출력 문제: JSON schema, stability checklist, stabilizer, lint/validation으로 보완
- provider lock-in 문제: provider factory와 fallback chain으로 분리
- 저장소 교체 문제: local/S3 storage abstraction으로 분리
- 생성 이후 업무 흐름 문제: project, knowledge, approval, history/share, export API로 연결
- 운영 확인 문제: health/metrics/version endpoint와 smoke/post-deploy script 제공

## 11. 비즈니스/사용자 관점의 적용 가능성

- 제안서, 회의록, PRD, 보고서, 계약서, RFP 분석 등 반복 문서 작성 업무에 적용 가능
- 프로젝트별 참고 문서와 생성 결과를 함께 관리하는 워크플로우로 확장 가능
- 조직 내부 문서 작성, 검토, 승인, 공유, export 과정을 AI 기반으로 보조할 수 있음

단, 실제 사용자 성과 수치와 운영 사례는 아직 확보가 필요합니다.

## 12. 향후 개선 계획

- README와 데모 자료 정비
- mock provider 기준 재현 가능한 로컬 데모 제공
- live provider 검증 기록 확보
- 배포 URL 또는 데모 영상 확보
- 품질 평가 결과와 사용자 피드백 기반 개선 사례 추가
- 본인 직접 구현 범위와 대표 commit 정리

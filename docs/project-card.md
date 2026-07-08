# Project Card

분석 기준: 2026-07-09 현재 저장소 코드, README, docs, evidence, completion readiness receipt, 최근 git log, worktree 상태, 최신 GitHub Actions CI/CD 결과를 기준으로 업데이트했다. post-login recommendation auth와 local UI flow evidence까지 반영한 상태다.

## 1. Snapshot

- 프로젝트명: DecisionDoc AI
- 프로젝트 유형: 개인 PoC / MVP 확장 프로젝트로 판단
- 기간: 확인 필요
- 현재 상태: MVP/PoC 구현 후 외부 실증 대기
- 내 역할: [contribution-note.md](./contribution-note.md)의 직접 설명 가능 범위를 기준으로 설명한다.
- GitHub 링크: https://github.com/sungjin9288/DecisionDoc-AI
- Release evidence: https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.77
- Demo 링크: 현재 README에는 검증된 Demo URL을 싣지 않는다. 최신 로컬 UI screenshot은 `evidence/screenshots/web-ui-home.png`에 있다.
- 핵심 기술스택: Python 3.12, FastAPI, Pydantic v2, Jinja2, OpenAI/Gemini/Claude/Local/Mock provider abstraction, Docker Compose, AWS SAM/Lambda, local/S3 storage, pytest
- 이력서 반영 가능 여부: 조건부 가능
- 판단 이유: 코드상 문서 생성 API, provider/storage abstraction, export, 프로젝트/승인/지식 문서/G2B/report workflow/ops 기능이 존재한다. 2026-07-09 기준 non-live pytest gate와 최신 GitHub Actions CI/CD는 통과했고 static PWA/CSP 및 post-login UI flow evidence도 존재한다. 다만 live provider, G2B 실데이터, 배포 URL, 사용자 사용 실적은 추가 증거가 필요하다.

## 2. One-liner

의사결정 문서와 업무 산출물을 빠르게 구조화해야 하는 사용자의 초안 작성, 첨부 문서 기반 생성, 프로젝트별 지식 재사용 문제를 해결하기 위해 FastAPI 기반 AI 문서 생성 및 협업 플랫폼을 개발 중인 서비스

## 3. Problem

- 이 프로젝트가 해결하려는 사용자 문제: 요구사항, 참고 문서, RFP, 회의/업무 자료를 일관된 의사결정 문서와 보고서 산출물로 바꾸는 과정이 반복적이고 품질 편차가 크다.
- 기존 방식의 불편함 또는 한계: 문서 유형별 구조를 매번 새로 잡아야 하고, 참고 자료 반영 여부를 추적하기 어렵고, 승인/공유/이력/내보내기 흐름이 분산되기 쉽다.
- 이 프로젝트에서 가장 중요한 문제정의: LLM 생성 결과를 단순 텍스트가 아니라 bundle schema, template, validation, storage, export, review workflow로 관리하는 것이다.
- 컨설팅 경험과 자연스럽게 연결되는 부분:
  - 문제정의: 사용자가 필요한 산출물과 의사결정 흐름을 문서 유형별 bundle로 구조화
  - 요구사항 정리: `GenerateRequest`, `BundleSpec`, `DocumentSpec`로 입력과 출력 구조 명확화
  - 사용자 관점: Web UI, `/generate/from-documents`, `/generate/from-pdf`, project/knowledge 흐름 제공
  - 문서화: `docs/architecture.md`, `docs/user_manual.md`, `docs/deployment/*` 운영 문서 존재
  - 기대효과 정리: 문서 초안 생성, export, approval/share/history로 업무 산출물 관리 흐름을 구조화

## 4. Solution

- 제공하려는 핵심 기능: AI 문서 bundle 생성, 첨부 문서/PDF 기반 생성, 프로젝트 관리, 지식 문서 재사용, 승인/공유/이력, 다양한 파일 export, 운영/평가 도구
- 현재 실제로 제공 가능한 기능:
  - `/generate`, `/generate/stream`, `/generate/export`, `/generate/from-documents`, `/generate/from-pdf`
  - bundle catalog와 Jinja2 template 기반 문서 렌더링
  - provider fallback chain: mock, openai, gemini, claude, local
  - local/S3 storage abstraction
  - project, knowledge, approval, history/share, report workflow, G2B search/fetch, health/metrics/version endpoints
  - local procurement decision package evidence path with versioned CLI stdout contract and receipt checking
  - DOCX, PDF, HWP, XLSX, PPTX 관련 service와 endpoint 테스트 파일
- 개발 중인 기능:
  - report quality learning, document ops agent, fine-tuning/training artifact workflow
  - 운영 자동화와 post-deploy evidence 고도화
  - 공공조달/Decision Council 흐름의 후속 튜닝
- 아직 할 수 없는 기능:
  - 실제 사용자 성과 수치 제시
  - 모든 provider live 동작 보장
  - 문서상 운영 URL의 현재 접근 가능성 보장
  - SaaS 과금/SSO/다중 테넌트의 실제 운영 안정성 단정
- 사용자 흐름:
  - 사용자 입력 또는 파일 업로드
  - bundle 선택
  - FastAPI API 요청
  - provider가 구조화 JSON 생성
  - schema/stabilizer/validator/lint 처리
  - Markdown 및 export 파일 생성
  - project/history/approval/share 흐름으로 후속 관리
- AI/IT 기술을 적용한 방식: LLM provider abstraction, bundle schema, prompt checklist, template rendering, deterministic validation, feedback/eval/fine-tune 데이터 축적 구조를 결합했다.

## 5. Tech Stack

| 영역 | 사용 기술 | 현재 사용 여부 | 근거 파일 |
|---|---|---|---|
| Language | Python 3.12 | 사용 중 | `Dockerfile`, `requirements.txt` |
| Frontend | FastAPI static PWA, HTML/CSS/JS | 사용 중 | `app/static/index.html`, `app/static/manifest.json`, `app/main.py` |
| Backend | FastAPI, Pydantic v2, Jinja2 | 사용 중 | `app/main.py`, `app/schemas.py`, `requirements.txt` |
| AI/LLM | OpenAI, Gemini, Claude, Local, Mock provider | 사용 중 | `app/providers/factory.py`, `app/providers/*_provider.py` |
| Database | 파일 기반 JSON/JSONL store, S3 storage option | 사용 중 | `app/storage/base.py`, `app/storage/factory.py`, `app/storage/local.py`, `app/storage/s3.py` |
| Infra/Deploy | Docker Compose, Dockerfile, AWS SAM/Lambda | 사용 중 | `docker-compose.yml`, `Dockerfile`, `infra/sam/template.yaml`, `app/aws_lambda.py` |
| Tools | Playwright, python-docx, python-pptx, xlsxwriter, pdfplumber, boto3 | 사용 중 | `requirements.txt`, `app/services/*_service.py` |
| Test | pytest, pytest-playwright, smoke scripts | 사용 중 | `tests/`, `scripts/smoke.py`, `scripts/report_workflow_smoke.py` |

## 6. Architecture

### 현재 아키텍처

```text
User / Browser PWA
-> FastAPI app (`app/main.py`)
-> Middleware: request id, observability, tenant, auth, audit, billing, rate limit, security headers
-> Routers: generate, projects, knowledge, approvals, report-workflows, g2b, admin, health
-> Services: GenerationService, ReportWorkflowService, DecisionCouncilService, SearchService
-> Provider abstraction: Mock / OpenAI / Gemini / Claude / Local / fallback chain
-> BundleSpec + Jinja2 templates + validation/lint
-> Storage abstraction: LocalStorage or S3Storage + JSON stores
-> Markdown/export/API response
```

### 목표 아키텍처

```text
User / Team
-> Web UI + API
-> Project workspace
-> Knowledge ingestion + generated document workflow
-> Review / approval / share / audit
-> Quality learning + curated correction artifacts
-> Tenant-aware deployment path
-> Operational smoke, post-deploy evidence, provider policy checks
```

### 설명

- 주요 데이터 흐름: 요청 입력 또는 파일 업로드가 `GenerateRequest`로 정규화되고, `GenerationService.generate_documents()`가 provider 호출, bundle 안정화, 저장, template 렌더링, lint/validation을 수행한다.
- 주요 모듈 구성: `app/routers/`, `app/services/`, `app/providers/`, `app/storage/`, `app/bundle_catalog/`, `app/eval/`, `app/static/`
- API 구조: `/generate*`, `/projects*`, `/knowledge*`, `/approvals*`, `/report-workflows*`, `/g2b*`, `/admin*`, `/health`, `/metrics`, `/bundles`
- AI/LLM 처리 흐름: bundle schema와 stability checklist로 JSON 출력을 유도하고, provider abstraction/fallback chain을 통해 모델별 호출을 분리한다.
- DB 또는 저장소 구조: 기본은 local filesystem 기반 JSON/JSONL store이며, bundle/export storage는 local 또는 S3를 선택한다.
- 인증/보안/환경변수 처리 방식: API key, JWT, ops key, tenant middleware, security headers, rate limit, production docs disable, environment variable 기반 provider/storage 설정을 사용한다.
- 배포 구조: Docker Compose와 AWS SAM/Lambda 경로가 존재한다.

## 7. My Contribution

- 직접 설명 가능한 기능: [contribution-note.md](./contribution-note.md)의 “직접 설명 가능한 구현 범위” 표를 기준으로 한다.
- 설계했다고 설명 가능한 구조: provider/storage abstraction, bundle catalog, FastAPI router/service 분리, validation pipeline, completion readiness chain.
- 문서화 또는 기획 측면 기여: product direction, execution plan, roadmap, evidence gallery, contribution boundary note를 근거로 설명한다.
- 문제 해결 또는 디버깅 사례: CSP nonce 적용, inline handler 제거, readiness receipt/checker, source-backed README metrics를 중심으로 설명한다.
- 면접에서 코드 수준으로 설명해야 할 부분: `app/main.py`, `app/services/generation_service/`, `app/providers/factory.py`, `app/storage/base.py`, `app/routers/generate/`, `scripts/check_completion_readiness.py`

## 8. Current Status

| 구분 | 기능 | 상태 | 근거 파일 | 이력서 반영 가능 여부 |
|---|---|---|---|---|
| 구현 완료 | FastAPI 앱 생성과 라우터 등록 | 구현 완료 | `app/main.py` | 가능 |
| 구현 완료 | 문서 생성 API와 export API | 구현 완료 | `app/routers/generate.py`, `app/services/generation_service.py` | 가능 |
| 구현 완료 | provider abstraction/fallback | 구현 완료 | `app/providers/factory.py`, `app/ai/pipeline.py` | 가능 |
| 구현 완료 | bundle catalog/schema/template 구조 | 구현 완료 | `app/bundle_catalog/spec.py`, `app/bundle_catalog/registry.py`, `app/templates/` | 가능 |
| 구현 완료 | local/S3 storage abstraction | 구현 완료 | `app/storage/base.py`, `app/storage/factory.py`, `app/storage/local.py`, `app/storage/s3.py` | 가능 |
| 구현 완료 | local procurement decision package evidence contract | 구현 완료 | `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`, `scripts/validate_procurement_decision_package_cli_contract_manifest.py`, `scripts/check_procurement_decision_package_cli_contract_manifest_result.py` | 가능 |
| 구현 완료 | health/metrics/version | 구현 완료 | `app/routers/health.py` | 가능 |
| 개발 중 | report workflow quality learning | 개발 중/고도화 중 | `app/routers/report_workflows.py`, `app/services/report_quality_learning.py` | 조건부 가능 |
| 개발 중 | document ops agent/training artifacts | 개발 중/고도화 중 | `app/agents/document_ops_agent.py`, `app/routers/document_ops_agent.py` | 조건부 가능 |
| 미구현 | 실제 사용자 성과 수치 | 현재 없음 | 저장소 내 근거 없음 | 보류 |
| 검증 필요 | 운영 URL 접근 가능성과 live provider 호출 | 검증 필요 | `scripts/check_completion_readiness.py`, env 필요 | 조건부 |
| 검증 필요 | 운영 안정성/고객 성과 | 현재 성과 수치 근거 없음 | `docs/contribution-note.md` | 보류 |

## 9. Evidence

- 주요 코드 파일: `app/main.py`, `app/routers/generate.py`, `app/services/generation_service.py`, `app/providers/factory.py`, `app/storage/base.py`
- 주요 함수/클래스: `create_app()`, `GenerationService`, `GenerateRequest`, `BundleSpec`, `DocumentSpec`, `get_provider()`, `get_provider_for_capability()`, `get_storage()`, `Storage`
- 주요 API 엔드포인트: `/generate`, `/generate/stream`, `/generate/export`, `/generate/from-documents`, `/generate/from-pdf`, `/bundles`, `/projects`, `/knowledge/{project_id}/documents`, `/approvals`, `/report-workflows`, `/g2b/search`, `/g2b/fetch`, `/health`, `/metrics`
- 설정 파일: `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `infra/sam/template.yaml`, `.github/workflows/*.yml`
- 실행 파일: `scripts/smoke.py`, `scripts/ops_smoke.py`, `scripts/report_workflow_smoke.py`, `scripts/run_deployed_smoke.py`
- 테스트 파일: `tests/test_generate.py`, `tests/test_storage.py`, `tests/test_auth_api_key.py`, `tests/test_report_workflows_api.py`, `tests/test_g2b.py`, `tests/test_pwa.py`
- README 또는 문서 근거: `README.md`, `docs/architecture.md`, `docs/user_manual.md`, `docs/product_local_demo_runbook.md`, `docs/product_demo_scenario.md`, `docs/development-plan.md`, `docs/roadmap.md`, `docs/contribution-note.md`, `docs/completion-readiness-runbook.md`
- Local evidence contract 근거: `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`, `scripts/validate_procurement_decision_package_cli_contract_manifest.py`, `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`, `--write-result`, `--result-path`
- Completion readiness 근거: `scripts/check_completion_readiness.py`, `scripts/check_completion_readiness_result.py`, gitignored `reports/completion-readiness/` local receipt.
- 최신 UI/CSP evidence: `evidence/screenshots/web-ui-home.png`, `evidence/cli-logs/ui_csp_nonce_check.log`, `evidence/cli-logs/playwright_console.log`, `evidence/cli-logs/ui_flow_evidence.json`.
- 최근 git 상태: `main` 브랜치가 `origin/main`과 동기화되어 있고 최신 확인 시점의 worktree는 clean이다. 후속 작업 전에는 항상 `git status --short --branch`와 최신 CI/CD 상태를 다시 확인한다.
- 실행 방법이 명확한지: 로컬 `pip install -r requirements.txt`, `python -m uvicorn app.main:app --reload`, Docker `docker compose up -d`가 문서와 설정에 존재한다.
- 스크린샷/데모가 필요한 부분: Web UI 첫 화면, `/generate` 결과, 문서 upload flow, report workflow, export 결과, admin/ops 화면

## 10. Consulting Angle

| 프로젝트 요소 | 연결되는 컨설팅 역량 | 이력서/면접 표현 | 근거 |
|---|---|---|---|
| bundle catalog | 요구사항 정리 | 문서 유형별 입력/출력 구조를 `BundleSpec`으로 정리해 생성 품질 편차를 줄이려 했다 | `app/bundle_catalog/spec.py` |
| generation pipeline | 업무 흐름 이해 | 초안 생성 이후 저장, 렌더링, 검증, export까지 후속 업무 흐름을 고려했다 | `app/services/generation_service.py` |
| project/knowledge flow | 사용자 관점 | 프로젝트 단위로 참고 문서를 재사용하는 흐름을 API에 반영했다 | `app/routers/projects.py`, `app/routers/knowledge.py` |
| approval/share/history | 문서화와 협업 | 문서 생성 결과를 단발성 출력이 아니라 검토와 공유 대상으로 관리하도록 설계했다 | `app/routers/approvals.py`, `app/routers/history.py` |
| eval/report quality workflow | 개선안 도출 | 생성 품질을 평가하고 correction artifact로 축적하는 개선 루프를 구성했다 | `app/eval/`, `app/routers/report_workflows.py` |

## 11. Safe vs Risky Expressions

### 써도 되는 표현

- FastAPI 기반 AI 문서 생성 API와 PWA를 개발 중
- LLM provider abstraction과 fallback chain을 적용
- bundle schema, Jinja2 template, validation/lint 기반 문서 생성 파이프라인 구성
- local/S3 storage abstraction과 Docker Compose/AWS SAM 배포 경로 구성
- pytest 기반 주요 API, storage, auth, export 기능 테스트 보유

### 조건부로 가능한 표현

- 운영 배포 경험: 실제 배포 접근과 본인 수행 여부 확인 후 가능
- multi-tenant/SaaS 구조 설계: 실제 운영 검증 범위를 명확히 제한하면 가능
- 공공조달 문서 지원 기능: 관련 코드와 feature flag 기준으로 설명하면 가능
- fine-tuning/quality learning workflow: 현재 개발/고도화 중임을 명시하면 가능

### 쓰면 위험한 표현

- 실제 고객이 사용 중인 서비스
- 사용자 생산성을 특정 수치만큼 개선
- 모든 기업 문서를 자동 완성하는 플랫폼
- 완전한 보안/컴플라이언스 인증 완료
- 모든 LLM provider를 실제 운영 환경에서 안정 검증

### 위험한 이유

- 저장소에는 성과 수치, 고객 사용량, 외부 인증 완료, live provider 운영 결과를 단정할 근거가 없다.
- 일부 기능은 문서와 코드가 함께 존재하지만, 현재 환경에서 실제 배포/운영 접근까지 검증하지 않았다.

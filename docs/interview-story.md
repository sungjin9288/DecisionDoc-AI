# Interview Story

분석 기준: 2026-06-09 현재 저장소 코드, README, docs, 설정 파일, 최근 git log, worktree 상태를 기준으로 업데이트했다. 면접 답변은 검증된 구현과 개발 중 항목을 분리하는 방향으로 작성했다.

## 1. 1분 프로젝트 소개

이 프로젝트는 반복적인 업무 문서 초안 작성과 산출물 관리 문제를 해결하기 위해 시작했습니다.
저는 확인 가능한 저장소 기준으로 FastAPI 기반 문서 생성 API, provider/storage abstraction, bundle schema 기반 생성 파이프라인을 중심으로 설명할 수 있습니다.
기술적으로는 Python, FastAPI, Pydantic v2, Jinja2, LLM provider abstraction, Docker, AWS SAM을 사용했고, 현재는 문서 생성 API와 project/knowledge/approval/export 흐름이 구현된 MVP 고도화 단계까지 구현했습니다.
최근에는 공공조달 decision package local evidence path를 fixture 기반으로 정리했고, `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`을 기준으로 stdout JSON contract를 검증하는 흐름을 추가했습니다.
개발 과정에서 LLM 출력 품질과 운영 가능한 구조를 분리하는 어려움이 있었고, 이를 bundle schema, stabilizer, lint/validation, provider factory로 해결했거나 해결 중입니다.
이 프로젝트를 통해 AI 기능도 일반적인 백엔드 구조와 검증 파이프라인 안에 넣어야 한다는 점을 배웠고, 향후에는 실제 사용자 피드백, 배포 evidence, 품질 개선 데이터를 확보하는 방향으로 고도화할 계획입니다.

## 2. 3분 상세 설명

- 프로젝트 배경: 개별 LLM 채팅만으로는 문서 작성 업무의 구조, 검토, 공유, 저장, export 흐름을 안정적으로 관리하기 어렵다는 문제에서 출발했다.
- 문제정의: 문서 초안 생성뿐 아니라 입력 자료 반영, 문서 유형별 구조화, 검증, 재사용, 승인/공유까지 연결해야 한다.
- 기술 선택 이유: FastAPI는 API 확장과 테스트가 쉽고, Pydantic은 외부 입력 검증에 적합하며, Jinja2는 문서 템플릿 분리에 적합하다. provider/storage factory는 모델과 저장소 교체 가능성을 높인다.
- 핵심 구현: `GenerationService.generate_documents()`, `BundleSpec`, provider factory, local/S3 storage, `/generate` 계열 endpoint, `/projects`, `/knowledge`, `/approvals`, `/report-workflows`, `/g2b`, local procurement decision package evidence contract
- 현재 상태: MVP 구현 후 고도화 중. 문서상 운영/배포 경로는 있으나 현재 접근 가능성, 사용자 성과, 본인 직접 구현 범위는 확인 필요하다.
- 앞으로의 개선 방향: README/데모 정리, 실행 검증 자동화, live provider 검증, 사용자 피드백 수집, quality learning workflow 안정화
- 컨설팅 경험과의 자연스러운 연결: 문제정의, 요구사항 정리, 사용자 업무 흐름 분석, 문서화, 기대효과 정리 역량이 프로젝트 구조화에 연결된다.

## 3. 기술 면접 예상 질문 10개

| 예상 질문 | 답변 방향 | 코드 근거 | 보완 필요 지식 |
|---|---|---|---|
| FastAPI 앱은 어떻게 초기화되나요? | `create_app()`에서 provider/storage/service/store/router/middleware를 wiring한다고 설명 | `app/main.py` | lifespan, dependency injection |
| provider abstraction은 왜 필요한가요? | 모델 교체, mock test, fallback chain을 위해 route와 provider를 분리 | `app/providers/factory.py`, `app/ai/pipeline.py` | retry/fallback design |
| LLM 출력 품질은 어떻게 관리하나요? | JSON schema, stabilizer, lint, validator, eval pipeline으로 후처리 | `app/services/generation_service.py`, `app/providers/stabilizer.py`, `app/eval/` | structured generation |
| bundle 구조는 무엇인가요? | 문서 유형별 prompt/schema/template/lint heading을 `BundleSpec`으로 관리 | `app/bundle_catalog/spec.py`, `app/bundle_catalog/registry.py` | schema design |
| 저장소는 어떻게 교체되나요? | `DECISIONDOC_STORAGE`로 local/S3 factory 선택 | `app/storage/factory.py`, `app/storage/base.py` | cloud storage consistency |
| 인증은 어떻게 구성되나요? | API key, JWT, ops key, tenant middleware 조합 | `app/auth/`, `app/middleware/auth.py`, `app/middleware/tenant.py` | RBAC/JWT security |
| 파일 업로드 생성은 어떻게 처리되나요? | multipart file을 읽고 attachment parser/context로 합쳐 GenerateRequest에 반영 | `app/routers/generate.py` | file validation |
| export는 어떤 방식인가요? | Markdown 저장과 DOCX/PDF/HWP/XLSX/PPTX service/endpoint가 존재 | `app/services/*_service.py`, `app/routers/generate.py` | document rendering |
| 테스트 전략은 무엇인가요? | mock provider 중심 pytest, API/storage/auth/export/workflow 테스트, smoke script, local evidence CLI success/failure contract test를 함께 설명 | `tests/`, `scripts/smoke.py`, `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json` | test pyramid |
| 운영 상태는 어떻게 확인하나요? | `/health`, `/metrics`, provider route checks, post-deploy scripts | `app/routers/health.py`, `scripts/post_deploy_check.py` | observability |

## 4. 프로젝트 면접 예상 질문 10개

| 예상 질문 | 답변 방향 | 근거 | 보완 필요 사항 |
|---|---|---|---|
| 왜 이 프로젝트를 만들었나요? | 반복 문서 업무를 AI와 workflow로 구조화하기 위해 | `docs/architecture.md`, `app/routers/generate.py` | 사용자 인터뷰 근거 |
| 현재 어디까지 구현됐나요? | API, provider/storage, bundle, export, project/approval 일부 구현 | `app/main.py`, `app/routers/` | 데모 영상 |
| 가장 어려웠던 점은? | LLM 자유 출력과 업무 산출물 품질 기준을 연결하는 것 | `BundleSpec`, stabilizer/eval | 실패 사례 정리 |
| 본인이 한 부분은 무엇인가요? | 확인 필요. 실제 커밋/작업 범위 기준으로 답변 | `git log`, changed files | 직접 기여 범위 |
| 기존 LLM 채팅과 차이는? | schema/template/workflow/export/eval로 관리한다는 점 | `app/bundle_catalog/`, `app/services/` | 사용자 비교 |
| 왜 파일 기반 store를 썼나요? | MVP와 로컬/테스트 단순성을 위해, S3 option으로 확장 | `app/storage/` | RDB 전환 계획 |
| 배포는 어떻게 하나요? | Docker Compose와 AWS SAM 경로가 있다 | `Dockerfile`, `docker-compose.yml`, `infra/sam/template.yaml` | 실제 배포 로그 |
| 품질 개선은 어떻게 하나요? | feedback/eval/report quality learning/fine-tune artifact 흐름 | `app/eval/`, `app/routers/report_workflows.py` | 운영 데이터 |
| 보안은 어떻게 고려했나요? | API key/JWT/tenant/audit/rate limit/security headers | `app/middleware/`, `app/auth/` | threat model |
| 다음 개발 우선순위는? | README/데모, 실행 검증, provider live 검증, 사용자 피드백 | 이 문서와 roadmap | 일정 계획 |
| 공공조달 local evidence는 어떻게 검증하나요? | `scripts/validate_procurement_decision_package_cli_contract_manifest.py`로 manifest를 검증하고 `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`로 persisted receipt를 확인한다고 설명. receipt는 `--write-result --result-path <path>`로 repo 밖에 남길 수 있음 | `cli_contract_manifest.json`, `contract_version` | live G2B와 fixture 검증 범위 구분 |

## 5. 컨설팅 경험과의 연결 질문 5개

| 예상 질문 | 답변 방향 | 주의할 점 |
|---|---|---|
| 컨설팅 경험이 개발에 어떻게 도움이 됐나요? | 문제를 사용자 업무 흐름, 요구사항, 산출물 기준으로 구조화하는 데 도움 | 특정 외부 도메인으로 억지 연결하지 않기 |
| 문서화 경험은 어떻게 반영됐나요? | README 개선안, architecture, roadmap, case study처럼 재사용 가능한 문서로 정리 | 구현하지 않은 기능을 완료처럼 말하지 않기 |
| 사용자 관점은 어떻게 반영했나요? | upload, project knowledge, approval/export 등 후속 흐름을 고려 | 실제 사용자 피드백은 아직 없음 |
| 요구사항을 어떻게 나눴나요? | API schema, bundle spec, service layer, storage/provider로 분해 | 본인 구현 범위 확인 필요 |
| 기대효과는 무엇인가요? | 초안 작성과 산출물 관리 부담을 줄일 가능성 | 수치 성과는 검증 전 단정 금지 |

## 6. 내가 추가로 공부해야 할 부분

- 기술: FastAPI dependency/lifespan, async/sync provider 호출, Pydantic v2 advanced validation
- 아키텍처: service boundary, repository/store pattern, event-driven workflow, multi-tenant design
- 보안: JWT/RBAC, tenant isolation, secret handling, CSP nonce, audit log integrity
- 배포: Docker production hardening, AWS SAM/Lambda, CI/CD, rollback, post-deploy smoke
- 테스트: contract test, integration test, snapshot/golden test, live provider test isolation
- AI/LLM: structured output, eval design, prompt/version management, fine-tuning data governance
- CS 기초: HTTP, concurrency, file IO atomicity, caching, reliability patterns

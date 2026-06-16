# Case Study

분석 기준: 2026-06-09 현재 저장소 코드, README, docs, 설정 파일, 최근 git log, worktree 상태를 기준으로 업데이트했다. 구현 완료 표현은 코드 근거가 있는 항목에만 사용했다.

## 1. 배경

- 이 프로젝트를 시작한 배경: 반복적으로 작성되는 의사결정 문서, 제안서, 보고서, 체크리스트를 LLM으로 초안화하되, 결과를 업무 흐름 안에서 관리할 수 있는 구조가 필요했다.
- 해결하려는 사용자 문제: 사용자는 참고 자료를 읽고, 문서 구조를 잡고, 초안을 쓰고, 검토/승인/공유/export를 반복해야 한다.
- 이 문제가 중요한 이유: 문서 작성은 단순 생성보다 구조, 근거, 검토 가능성, 재사용성이 중요하기 때문이다.
- 현재 개발 진행 상태: FastAPI 기반 MVP 구현 후 고도화 중. 문서 생성, 첨부/PDF 기반 생성, bundle catalog, provider/storage abstraction, project/knowledge/approval/history/report workflow 일부가 코드에 존재한다.

## 2. 문제 정의

### As-Is

- 현재 사용자는 어떤 방식으로 문제를 해결하고 있는가? 문서 템플릿, 기존 산출물, 회의/참고 자료, 개별 LLM 채팅을 조합해 수작업으로 초안을 만든다.
- 기존 방식의 한계는 무엇인가? 산출물 구조가 흔들리고, 참고 자료 반영 이력과 승인 흐름이 분산되며, export와 재사용이 일관되지 않다.

### Pain Points

- 불편 1: 문서 유형별 필수 구조와 품질 기준을 매번 다시 정해야 한다.
- 불편 2: 파일 업로드, RFP/PDF 해석, 프로젝트 지식 재사용이 단일 흐름으로 연결되지 않으면 반복 입력이 발생한다.
- 불편 3: 생성 결과를 검토, 승인, 공유, 품질 개선 데이터로 이어가기 어렵다.

## 3. 목표

### MVP 목표

- FastAPI API로 구조화된 문서 bundle을 생성한다.
- mock provider로 로컬/테스트 실행이 가능하게 한다.
- Markdown과 주요 export 형식으로 결과를 저장/반환한다.
- project, knowledge, history, approval의 기본 업무 흐름을 연결한다.

### 기술 목표

- provider와 storage를 추상화해 모델/저장소 교체 비용을 낮춘다.
- bundle schema와 template을 분리해 문서 유형 확장을 쉽게 한다.
- validation, lint, eval로 생성 결과의 최소 품질 기준을 확인한다.

### 사용자 목표

- 입력 자료에서 바로 업무 문서 초안을 만든다.
- 프로젝트별 참고 자료를 재사용한다.
- 결과를 공유, 승인, export 가능한 산출물로 관리한다.

### 학습 목표

- FastAPI 서비스 구조, Pydantic schema, LLM provider integration, storage abstraction, 테스트/운영 smoke 경로를 실전 프로젝트 안에서 학습한다.

## 4. 해결 접근

- 어떤 기능으로 문제를 해결하려 했는가? `/generate` 계열 API, bundle catalog, templates, project/knowledge/approval/history/report workflow를 결합했다.
- AI/IT 기술을 어디에 적용했는가? LLM은 구조화 JSON bundle 생성에 사용하고, deterministic logic은 schema validation, stabilizer, lint, storage, export에 사용했다.
- 왜 이 기술스택을 선택했는가? FastAPI/Pydantic은 API와 schema 검증에 적합하고, Jinja2는 문서 템플릿 분리에 적합하며, Docker/AWS SAM은 로컬과 서버리스 배포 경로를 제공한다.
- 현재 구현된 접근: provider abstraction과 bundle schema 기반 생성 파이프라인이 존재한다.
- 향후 목표 접근: 운영 환경에서 provider policy, 품질 학습, tenant별 운영, 배포 evidence를 더 안정화하는 것이다.

## 5. 구현 범위

### 구현 완료

- FastAPI 앱 초기화와 router/service/store wiring
- `/generate`, `/generate/stream`, `/generate/export`, `/generate/from-documents`, `/generate/from-pdf`
- bundle registry와 `BundleSpec`/`DocumentSpec`
- Mock/OpenAI/Gemini/Claude/Local provider factory와 fallback pipeline
- Local/S3 storage abstraction
- project, knowledge, approvals, history/share, health/metrics, G2B, report workflow API
- Dockerfile, Docker Compose, AWS SAM 설정
- pytest 테스트 suite와 smoke script

### 개발 중

- document ops agent와 trajectory/training artifact workflow
- report quality learning/correction artifact workflow
- fine-tuning/model registry 운영 흐름
- post-deploy evidence와 운영 자동화 고도화

### 미구현 / 예정

- 사용자 성과 수치 기반 포트폴리오 evidence
- 배포 URL의 현재 접근성 검증 자료
- 모든 provider live integration의 재현 가능한 검증 기록
- 실제 사용자 피드백/사용량 기반 개선 사례

### 이번 MVP에서 제외한 범위

- 제외한 기능: 상용 SaaS 수준의 운영 성과, 인증 완료, 고객사별 SLA, 성과 수치
- 제외한 이유: 현재 저장소에는 해당 내용을 단정할 근거가 없고, 포트폴리오에서는 개발 중 상태와 검증 필요 항목으로 분리해야 한다.

## 6. 시스템 설계

- 전체 구조: FastAPI single application 안에 middleware, routers, services, providers, storage, bundle catalog, eval, static PWA가 구성되어 있다.
- 데이터 흐름: 요청 검증 -> provider 생성 -> schema/stabilizer -> storage -> Jinja2 rendering -> lint/validation -> API response/export/history 저장
- API 구조: `/generate*`, `/projects*`, `/knowledge*`, `/approvals*`, `/report-workflows*`, `/g2b*`, `/admin*`, `/health`, `/metrics`, `/bundles`
- AI/LLM 처리 흐름: `GenerateRequest`와 bundle schema를 바탕으로 provider가 JSON bundle을 생성하고, 후처리 로직이 누락/품질/형식을 보정한다.
- 예외 처리: `app/api/exception_handlers.py`, provider/storage custom error, FastAPI `HTTPException` 사용
- 보안/환경변수 처리: API key, ops key, JWT, tenant middleware, rate limit, security headers, production docs disable, provider/storage env vars
- 배포 계획: Docker Compose와 AWS SAM/Lambda 경로가 존재하며, post-deploy smoke/evidence script가 문서화되어 있다.

## 7. 나의 역할

- 기획: 확인 필요. 다만 문서 유형, 사용자 흐름, 산출물 구조를 정리한 경험으로 설명 가능
- 요구사항 정의: 확인 필요. `GenerateRequest`, bundle catalog, project/knowledge 흐름을 요구사항 구조화 사례로 설명 가능
- 프론트엔드: 확인 필요. `app/static/index.html` 기반 PWA가 있으나 직접 구현 범위 확인 필요
- 백엔드: 확인 필요. FastAPI router/service/provider/storage 구조를 설명할 수 있어야 함
- AI/LLM: 확인 필요. provider abstraction, prompt/schema, validation 흐름을 설명할 수 있어야 함
- 데이터 처리: 확인 필요. JSON store, local/S3 storage, eval/report artifacts를 설명할 수 있어야 함
- 배포: 확인 필요. Docker/AWS SAM/post-deploy script 근거는 있음
- 문서화: 확인 필요. 이번 포트폴리오 문서 세트는 직접 산출물로 설명 가능

## 8. 결과

- 구현 완료 기능: 문서 생성 API, 파일/PDF 기반 생성, export, provider/storage abstraction, bundle catalog, 프로젝트/지식/승인/이력/report workflow 일부, health/ops 기능
- 로컬 실행 가능 여부: 설정상 가능. `pip install -r requirements.txt` 후 `python -m uvicorn app.main:app --reload`, 또는 `docker compose up -d`
- 테스트 여부: pytest 테스트 suite와 smoke script 존재. 이번 문서 작업에서는 코드 테스트가 아니라 문서 파일 존재/README 미수정 검증을 수행한다.
- 배포 여부: 문서상 Docker Compose, AWS SAM, 운영 URL 기준이 존재한다. 현재 접근 가능성은 검증 필요.
- 사용자 피드백: 현재 없음. 임의 생성 금지.
- 수치 성과:
  - 현재 없음. 임의 생성 금지.

## 9. 배운 점

- 기술적으로 배운 점: LLM 기능도 provider, schema, validation, storage, export 같은 일반 소프트웨어 경계 안에 넣어야 운영 가능한 기능이 된다.
- 설계에서 배운 점: router는 얇게, service는 orchestration, provider/storage는 factory로 분리하는 구조가 확장에 유리하다.
- 사용자 관점에서 배운 점: 사용자는 "생성"보다 "입력 자료 반영, 검토, 공유, export"까지 이어지는 전체 흐름을 필요로 한다.
- 다음 프로젝트에 반영할 점: 초기부터 데모 스크린샷, 사용자 시나리오, 실제 검증 로그, 본인 기여 범위를 함께 관리해야 한다.

## 10. 이 프로젝트가 보여주는 역량

- 개발 역량: FastAPI, Pydantic, service layer, provider/storage abstraction, Docker/AWS 배포 경로, pytest
- 문제정의 역량: 문서 생성 문제를 bundle, template, validation, workflow로 분해
- 데이터/AI 활용 역량: LLM 생성 결과를 구조화 JSON과 deterministic validation으로 관리
- 커뮤니케이션/문서화 역량: architecture, deployment, user manual, portfolio docs 정리
- 컨설팅형 사고: 사용자 업무 흐름을 문제정의, 요구사항, 산출물, 기대효과로 구조화

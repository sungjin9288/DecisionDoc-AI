# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows Semantic Versioning.

## [Unreleased]

### Added
- **Public Procurement Go/No-Go Copilot** — 프로젝트 상세 화면에서 공고 attach/import → deterministic 평가 → bid-readiness checklist → `bid_decision_kr` 생성 → `rfp_analysis_kr` / `proposal_kr` / `performance_plan_kr` downstream handoff까지 닫히는 project-scoped procurement workflow 추가
- **Project-scoped procurement state** — opportunity, hard-filter result, soft-fit scoring, recommendation, checklist, raw snapshot을 기존 `ProjectDocument`와 분리된 structured state로 저장
- **Procurement feature flag** — `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`와 `/version.features.procurement_copilot` 노출 추가

### Changed
- **Live dev runtime hardening** — Lambda local `/tmp` state 의존을 S3-backed durable state로 옮기고, login/bootstrap/UI shell 동작을 정리해 project/procurement flow가 실제 dev 배포에서 안정적으로 동작하도록 개선
- **Project detail integration** — procurement 문서가 기존 `/generate/stream`, project documents, approval, share, history 흐름을 그대로 재사용하도록 연결
- **CI alignment** — full `pytest tests/ -q --tb=short` 경로를 기본 test lane으로 고정하고, lint/security job은 advisory lane으로 정리
- **Dependency policy** — tracked `requirements.txt` / `requirements-lambda.txt`를 검증된 exact version으로 pinning하고 LDAP optional dependency `ldap3==2.9.1`까지 반영

### Security
- `bandit` 주요 finding을 모두 해소하고 SAML fallback parser를 fail-closed extractor로 교체
- dependency scan 기준에서 tracked requirements의 `0 vulnerabilities reported`, `0 vulnerabilities ignored` 상태를 확보

### Fixed
- authenticated browser session이 API-key-gated route와 충돌하던 live UI blocker 수정
- CSP / favicon / login-shell bootstrap / PWA public endpoint `HEAD` 호환성 문제 수정
- E2E 고정 포트, websocket warning, password-form/autocomplete console noise 제거

### Tests
- procurement API / handoff / project-detail E2E / audit / deploy-smoke 경로를 포함한 full suite 기준 `1613 passed, 3 skipped`
- warning-free test suite 복구 및 optional LDAP path regression coverage 유지

## [1.0.0] — 2026-03-18

### Added
- **엔터프라이즈 멀티테넌트** — JWT + RBAC, X-Tenant-ID 헤더 격리, 테넌트별 번들 화이트리스트
- **사용자 계정 시스템** — 회원가입/로그인/비밀번호 변경, bcrypt 해싱
- **SSO** — LDAP/AD, SAML 2.0, Google Cloud IAM 연동
- **결재 워크플로우** — 기안 → 검토 → 승인/반려, 불변 doc_snapshot, 상태 기계 검증
- **프로젝트 관리** — 연도별 아카이브, 문서 이력, 전문 검색, 삭제 엔드포인트
- **16종 번들** — 나라장터 특화 5종(RFP분석/수행계획/준공/중간보고/과업지시) 포함
- **나라장터(G2B) 연동** — 공고 검색, RFP 자동 파싱(PDF/DOCX/HWP 업로드)
- **2단계 스케치 플로우** — `POST /generate/sketch` (경량 LLM, 2~4초) → 구성 확인 → 풀 생성
- **웹 검색 연동** — Serper/Brave/Tavily 자동 감지, `DECISIONDOC_SEARCH_ENABLED=1`
- **파일 익스포트** — HWP(hwpx), DOCX(행안부 표준), PDF(Playwright), Excel, PPT
- **AI 품질 시스템** — 골든 예시 few-shot, 스타일 가이드 YAML, LLM judge 자동 평가
- **A/B 테스트 & 자기개선** — 저평점 누적 → 패턴 분석 → 프롬프트 오버라이드 → A/B 테스트
- **Fine-tuning 파이프라인** — 고평점 생성 수집 → JSONL 내보내기 → OpenAI 학습 트리거
- **로컬 LLM** — Ollama/vLLM/LM Studio 온프레미스 지원
- **과금 시스템** — Free/Pro/Enterprise 플랜, Stripe 웹훅, 월 사용량 추적
- **알림 시스템** — 결재 이벤트 인앱 알림, 이메일/Slack 채널
- **팀 메시지** — @멘션, 스레드형 채팅
- **스타일 프로필** — 문서 업로드로 AI 문체 학습
- **PWA** — 서비스 워커, 오프라인 폴백, 설치 가능
- **Prometheus 메트릭** — `/metrics`, `/health/live`, `/health/ready` (K8s 프로브)
- **감사 로그** — Append-only, ISMS 대응
- **개인정보 권리 API** — §35 열람, §35의2 이동, §36 삭제 (탈퇴 cascade 포함)
- **Docker** — Multi-stage 빌드, Nginx SSL, HA(3-replica) docker-compose
- **GS인증/CSAP** 준비 문서 (`docs/compliance/`)

### Security
- JWT tenant_id cross-validation (헤더 스푸핑 방지)
- 승인 완료/반려 문서 수정 차단 (결재 불변성)
- `/feedback`, `/eval/*`, `/ab-tests/*`, `/billing/*` 인증 적용
- Prometheus 메트릭 미들웨어 (UUID 경로 정규화로 카디널리티 제어)
- LDAP SSO 에러 메시지 한국어 통일

### Fixed
- `boto3` requirements.txt 미등록 → `boto3>=1.34.0` 추가
- `python3-saml` 미사용 패키지 제거
- LocalStorage 50MB 파일 크기 제한 추가
- 생성 컨텍스트 캐시 TTL 1시간 추가 (메모리 누수 방지)
- 에러 메시지 한국어 통일 (manifest, model, tenant, privacy 등)
- 응답 형식 통일 (`/ab-tests`, `/admin/auto-bundles`, `/admin/tenants`)
- 결재/프로젝트 목록 페이지네이션 추가 (limit/offset)

### Tests
- 310+ 자동화 테스트 (test_missing_coverage.py, test_local_llm_endpoints.py 추가)
- 승인 불변성, 동시 결재 race condition, 탈퇴 엣지케이스 커버리지

## [0.1.0] — 2025-01-01

- Initial MVP release:
  - FastAPI API-only service
  - Provider → Bundle(JSON) → Jinja2 → Eval Lints → Validator pipeline
  - `/health`, `/generate`, `/generate/export`
  - Offline test suite with golden snapshots

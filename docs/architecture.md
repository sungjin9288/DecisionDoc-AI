# DecisionDoc AI 시스템 아키텍처

## 전체 구성도

```
┌─────────────────────────────────────────────────────────┐
│                      클라이언트                           │
│  브라우저 (PWA) / 모바일 앱                              │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS (TLS 1.2+)
┌──────────────────────▼──────────────────────────────────┐
│                   Nginx (Reverse Proxy)                   │
│  - SSL/TLS 종단  - Rate Limiting  - 정적 파일 캐시       │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Application (Python 3.12)            │
│                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  Middleware  │  │   Routers   │  │    Services     │  │
│  │ - Auth(JWT) │  │ /auth       │  │ - Generation    │  │
│  │ - Tenant    │  │ /generate   │  │ - Eval Pipeline │  │
│  │ - Audit     │  │ /approvals  │  │ - Notification  │  │
│  │ - RateLimit │  │ /projects   │  │ - Billing       │  │
│  │ - Security  │  │ /billing    │  │ - G2B Collector │  │
│  │   Headers   │  │ /admin      │  │ - Style Analyzer│  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │                   Storage Layer                      │ │
│  │  UserStore │ ApprovalStore │ StyleStore │ ...       │ │
│  │  (local/S3 JSONL/JSON, shared process lock)         │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────┬──────────────────────────┬──────────────────┘
           │                          │
┌──────────▼──────────┐  ┌───────────▼─────────────────┐
│   LLM Providers     │  │      File Storage            │
│  - OpenAI API       │  │  - Local: /app/data/         │
│  - Google Gemini    │  │  - S3: AWS S3 Compatible     │
│  - Local Ollama     │  │  - Backup: /backup/          │
│  - vLLM / LM Studio │  └─────────────────────────────┘
└─────────────────────┘
```

## 기술 스택

| 계층 | 기술 | 버전 |
|------|------|------|
| 웹 프레임워크 | FastAPI | 최신 |
| 런타임 | Python | 3.12 |
| 데이터 검증 | Pydantic | v2 |
| 인증 | PyJWT + bcrypt | 2.8+ / 4.0+ |
| 암호화 | cryptography (Fernet) | 42.0+ |
| 문서 생성 | python-docx, python-pptx | 최신 |
| PDF | Playwright (Chromium) | 최신 |
| Excel | xlsxwriter, openpyxl | 최신 |
| 컨테이너 | Docker + Compose | 24.0+ |
| 리버스 프록시 | Nginx | 1.25 |

## 데이터 흐름 — 문서 생성

```
사용자 입력
    │
    ▼
POST /generate/stream (SSE)
    │
    ├─ 1. 인증/인가와 tenant 확인 (JWT + RBAC)
    ├─ 2. 결제 상태와 사용량 한도 확인 (BillingMiddleware)
    ├─ 3. 요청 검증 (Pydantic)
    ├─ 4. 번들 스펙 로드 (BundleRegistry)
    ├─ 5. 프롬프트 빌드 (build_bundle_prompt)
    │     ├─ 스타일 가이드 주입
    │     ├─ Few-shot 예시 주입
    │     └─ 검색 컨텍스트 주입 (옵션)
    ├─ 6. LLM 호출 (Provider + Retry)
    ├─ 7. 결과 검증 (JSON Schema + Heuristic)
    ├─ 8. 스토리지 저장
    ├─ 9. 사용량 기록 (UsageStore)
    └─ 10. SSE 스트림 반환
```

## 데이터 흐름 — 프로젝트 지식

```
Knowledge API / Report promotion
    │
    ▼
KnowledgeStore(tenant_id, project_id, selected StateBackend)
    ├─ index.json: ownership, schema, duplicate identity, content binding
    ├─ {doc_id}.txt: UTF-8, text length, size, SHA-256
    └─ {doc_id}_style.json: exact JSON object, size, SHA-256
    │
    ├─ generation context ranking
    ├─ procurement capability evaluation
    └─ approved report artifact reuse
```

모든 consumer는 앱이 선택한 local/S3 `StateBackend`를 공유한다. Read는 index와 object를 함께 검증하고 malformed·partial·orphan state를 빈 지식으로 축소하지 않는다. 동일 process의 read-modify-write는 logical index lock으로 직렬화하지만 distributed S3 multi-object transaction/CAS는 현재 보장하지 않는다.

## 데이터 흐름 — 프로젝트 import

```
프로젝트 상세 화면
    │
    ▼
POST /projects/{project_id}/imports/voice-brief
    │
    ├─ 1. JWT 인증 + tenant 확인
    ├─ 2. ProjectStore에서 대상 프로젝트 조회
    ├─ 3. VoiceBriefImportService가 upstream summary 패키지 조회
    ├─ 4. review/sync 상태 검증
    ├─ 5. source metadata와 함께 프로젝트 문서 저장
    └─ 6. 프로젝트 상세 재조회 시 imported document 노출
```

프로젝트 입력 소스는 단일 생성 요청만이 아니라 다음 경로도 포함합니다.

- 첨부 파일 기반 RFP 파싱: `POST /attachments/parse-rfp`
- 프로젝트 지식 문서 저장: `POST /knowledge/{project_id}/documents`
- Voice Brief summary import: `POST /projects/{project_id}/imports/voice-brief`
- G2B 공고 조회/자동 입력: `/g2b/search`, `/g2b/fetch`

## 멀티테넌시 구조

```
/app/data/
├── system/          ← 시스템 테넌트 (기본)
│   ├── users/
│   ├── audit/
│   └── settings/
└── {tenant_id}/     ← 기관별 격리 데이터
    ├── users/
    ├── approvals/
    ├── projects/
    ├── generations/
    ├── audit/
    └── billing/
```

테넌트 식별: `X-Tenant-ID` 헤더 → JWT 토큰 `tenant_id` 교차 검증

## 보안 계층

```
요청 → SecurityHeaders → RateLimit → Audit → Auth(JWT) → Tenant → Billing → 라우터
         (HSTS/CSP)      (429)       (로그)   (401/403)    (격리)    (402/503)
```

## SSO 연동 흐름

```
LDAP/AD:  로그인 폼 → POST /auth/ldap-login → ldap_auth.authenticate → JWT 발급
SAML 2.0: GET /saml/login → IdP Redirect → POST /saml/acs → JWT 발급
G-Cloud:  GET /sso/gcloud → Google OAuth → GET /sso/gcloud/callback → JWT 발급
```

SSO 설정은 `tenants/{tenant_id}/sso_config.json` relative path를 local/S3 shared state backend에서 공통으로 사용한다. Secret은 PBKDF2로 유도한 Fernet key로 암호화하며 admin 응답에서는 마스킹한다. Partial update는 process-local shared lock 안에서 수행한다. SAML ACS는 RelayState cookie, IdP certificate, signed assertion verifier를 요구하고 verifier가 없으면 인증을 거부한다. 실제 IdP 연동과 distributed S3 compare-and-swap은 별도 검증 범위다.

## 평가 파이프라인

```
문서 생성 완료
    │
    ▼ (백그라운드 스레드)
EvalPipeline.run()
    ├─ heuristic_score (길이/구조/한국어 비율)
    ├─ lint_checks (필수 섹션 존재 여부)
    └─ EvalStore.save() → JSONL 누적
         └─ GET /eval/report
```

Quality learning state는 feedback·eval·prompt override뿐 아니라 A/B prompt experiment와 freeform·sketch request pattern까지 `tenants/{tenant_id}/` 아래의 동일 local/S3 `StateBackend`에 저장한다. 모든 request-path caller는 `app.state.data_dir`와 `app.state.state_backend`를 전달한다. Persisted schema, identity, timestamp 또는 UTF-8/JSON 무결성이 깨지면 빈 품질 상태로 fallback하지 않고 요청을 중단하며 원본을 보존한다. 같은 process의 독립 store 인스턴스는 shared lock으로 read-modify-write를 직렬화하고, A/B winner override가 저장된 뒤에만 conclusion을 확정한다. Distributed S3 compare-and-swap과 실제 provider 품질은 별도 검증 범위다.

## 파일 형식 서비스

| 형식 | 서비스 | 의존성 |
|------|--------|--------|
| DOCX | docx_service.py | python-docx |
| HWP | hwp_service.py | zipfile (stdlib) |
| PDF | pdf_service.py | Playwright |
| XLSX | excel_service.py | xlsxwriter |
| PPTX | pptx_service.py | python-pptx |

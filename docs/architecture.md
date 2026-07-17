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

## 데이터 흐름 — G2B 즐겨찾기

```
GET / POST / DELETE /g2b/bookmarks
    │
    ├─ signed tenant/user 확인
    ▼
BookmarkStore(tenant_id, selected StateBackend)
    ├─ tenant별 g2b_bookmarks.json
    ├─ user bucket과 bid_number identity 검증
    └─ internal owner metadata는 저장하고 응답에서는 제거
```

Missing-state read는 object를 만들지 않는다. Malformed·invalid UTF-8 JSON, duplicate key·owned bid identity와 collection drift는 조회와 후속 변경을 중단하고 원본 bytes를 보존한다. Owner가 없는 기존 record는 tenant path와 user bucket 소유로 읽고, 다른 owner가 명시된 record는 숨긴 채 보존한다. 동일 process의 read-modify-write는 logical state lock으로 직렬화하지만 distributed S3 compare-and-swap은 현재 보장하지 않는다.

## 데이터 흐름 — 공공조달 판단 상태

```
G2B fixture/live collector 또는 operator input
  -> ProcurementDecisionService.evaluate()
  -> ProcurementDecisionStore
       -> tenants/{tenant_id}/procurement_decisions.json
       -> tenants/{tenant_id}/procurement_snapshots/{project_id}/{snapshot_id}.json
  -> project procurement API / generation context / Decision Council
```

`ProcurementDecisionStore`는 앱이 선택한 `StateBackend`와 data root를 사용한다. 판단 record의 read-modify-write는 backend의 bucket/prefix와 relative path로 계산한 logical state lock 안에서 직렬화하므로, 같은 S3 object를 가리키는 독립 store 인스턴스가 서로 다른 local base path를 사용해도 한 process 안에서는 동일 lock을 공유한다.

Missing-state read는 파일이나 object를 만들지 않는다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key, owned identity/path drift와 duplicate source snapshot metadata는 조회와 후속 mutation을 중단하고 원본 bytes를 보존한다. Snapshot payload는 JSON 직렬화 가능성과 finite number를 write 전에 확인하고, snapshot read도 blank·malformed·invalid UTF-8·duplicate key를 missing으로 축소하지 않는다. 이 경계는 persisted path와 JSON 구조의 무결성만 보장하며 외부 원천의 의미적 진위나 distributed S3 compare-and-swap은 보장하지 않는다.

## 데이터 흐름 — 공공조달 검토 증빙 상태

```text
검증된 project review packet
  -> ProcurementReviewStore.prepare()
       -> tenants/{tenant_id}/procurement_reviews/{project_id}/{packet_sha256}/
          ├─ record.json
          ├─ packet.zip
          └─ reviewed_packages/{reviewed_package_sha256}.zip
  -> reviewer inbox / one-time completion / downstream provenance
```

Record·packet·reviewed-package는 앱이 선택한 local/S3 `StateBackend`와 tenant/project/packet SHA-256 scope를 공유한다. Record는 exact field·receipt·identity를 검증하며 blank·malformed·invalid UTF-8·duplicate key와 canonical path drift를 빈 review로 축소하지 않는다. Packet과 reviewed-package는 persisted size·SHA-256뿐 아니라 receipt·embedded receipt·manifest의 semantic binding도 다시 대조한다. 기존 `reviewed_package.zip`은 읽기 호환 경로로만 유지한다.

Prepare는 packet을 `write-if-absent`로 확정하고 exact orphan packet만 재사용한 뒤 record를 create-if-absent로 만든다. Completion은 원본 packet을 다시 검증하고 reviewed-package를 content-addressed immutable object로 만든 뒤 pending record를 CAS로 completed record에 전환한다. Local backend는 conditional file lock과 atomic replace, S3 backend는 `If-None-Match`와 ETag `If-Match`를 사용한다. Commit 응답이 불확실하면 persisted bytes를 다시 읽어 성공 여부를 조정하며, record가 확정되지 않은 immutable artifact는 권위 상태로 사용하지 않는다. Persisted 오류는 review domain `ValueError`와 분리되어 API에서 `500 INTERNAL_ERROR`로 전달된다. 여러 object를 하나의 원자적 commit으로 묶는 distributed transaction은 보장하지 않는다.

## 데이터 흐름 — Decision Council

```
GET / POST /projects/{project_id}/decision-council
    │
    ├─ signed tenant와 현재 procurement binding 확인
    ▼
DecisionCouncilStore(caller tenant, selected StateBackend)
    ├─ tenant별 decision_council_sessions.json
    ├─ canonical project/use-case/bundle session key 검증
    └─ generation context에는 current session만 전달
```

Missing-state read는 파일이나 object를 만들지 않는다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key, canonical key drift와 owned session ID/key 중복은 조회·revision 갱신을 중단하고 원본 bytes를 보존한다. 기존 foreign·malformed record는 현재 tenant의 session으로 사용하지 않고 원본에 남긴다. Local/S3 write는 모두 선택된 `StateBackend`를 통하며 동일 process의 read-modify-write는 logical state object lock으로 직렬화한다. Distributed S3 compare-and-swap은 현재 보장하지 않는다.

## 데이터 흐름 — 프로젝트와 결재 상태

```
/projects*                         /approvals*
    │                                 │
    ▼                                 ▼
ProjectStore                      ApprovalStore
    ├─ tenants/{tenant_id}/projects.json
    └─ tenant/project/document identity 검증
                                      ├─ tenants/{tenant_id}/approvals.json
                                      └─ tenant/approval/status/comment 검증
```

두 store는 앱이 선택한 local/S3 `StateBackend`를 사용하고 tenant별 JSON object의 backend identity와 relative path로 process-local logical lock을 계산한다. 따라서 같은 S3 bucket/prefix/object를 가리키는 독립 store가 서로 다른 virtual base path를 사용해도 한 process 안에서는 같은 read-modify-write lock을 공유한다.

Missing-state read는 파일이나 object를 만들지 않는다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key/owned ID와 유효한 owned ID를 가진 schema drift는 조회와 후속 mutation을 중단하고 원본 bytes를 보존한다. Explicit foreign record와 owned ID가 없는 기존 malformed record는 호환을 위해 현재 tenant의 조회·변경 대상에서 제외한 채 보존한다. Persisted state 오류는 domain transition의 `ValueError`와 분리된 store error로 전달되어 approval API의 잘못된 400 응답으로 축소되지 않는다.

두 store는 각 mutation에서 검증된 원문을 expected value로 보존하고 missing state에는 conditional create, existing state에는 compare-and-swap을 적용한다. 충돌하면 최신 state를 다시 읽고 ownership·schema를 재검증하며, `ApprovalStore`는 transition도 다시 확인한 뒤 동일 operation identity로 재시도한다. S3는 `If-None-Match`와 ETag `If-Match`, local은 conditional file lock과 atomic replace를 사용한다.

`ProjectStore`는 project create·field update·delete와 document add/remove·voice brief upsert·approval sync를 이 retry loop로 통합한다. 서로 다른 worker의 독립 project 생성과 같은 project의 문서 추가를 모두 보존하고, field update와 approval sync 같은 disjoint mutation도 최신 state 위에 재적용한다. Delete가 다른 update와 경쟁해도 삭제가 확정된 project를 stale write로 되살리지 않는다. 각 project record에는 API에 노출하지 않는 최근 mutation ID를 최대 64개 보존한다. Conditional write가 commit된 뒤 응답이 유실되고 record가 남아 있는 후속 CAS가 발생해 exact payload가 달라져도 이 receipt로 원래 operation의 확정을 조정하며, receipt schema가 손상되면 원본을 보존하고 fail closed 처리한다.

`ApprovalStore`는 worker가 다른 결재를 동시에 생성하거나 같은 결재에 댓글을 추가해도 update를 잃지 않고, 최종 승인과 반려가 경쟁하면 먼저 확정된 terminal transition 하나만 성공하게 한다. Commit 응답이 불확실하면 exact persisted payload를 read-back한다. CAS 보장은 각각 tenant별 단일 project 또는 approval state object에 한정되며, 두 object를 하나의 commit으로 묶는 distributed transaction과 실제 AWS runtime은 현재 보장하지 않는다.

## 데이터 흐름 — 보고서 워크플로우 상태

```
/report-workflows*
    │
    ▼
ReportWorkflowStore
    ├─ tenants/{tenant_id}/report_workflows.json
    ├─ planning / slides / visual assets / approval / promotion
    └─ tenant/workflow/nested identity 검증
```

Workflow의 모든 read-modify-write는 앱이 선택한 local/S3 `StateBackend`와 tenant별 relative path로 계산한 logical lock 안에서 실행한다. 같은 S3 bucket/prefix/object를 가리키는 독립 store가 서로 다른 virtual base를 사용해도 한 process 안에서는 같은 lock을 공유한다. Worker 간 권위는 lock에 의존하지 않고, missing state에는 conditional create, existing state에는 검증된 원문을 expected value로 사용하는 compare-and-swap을 적용한다. 충돌하면 최신 state의 ownership·schema와 planning·slide·approval transition을 다시 검증한 뒤 mutation을 재적용한다.

Missing-state만 빈 목록으로 읽는다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key/workflow/nested identity, owned schema drift와 backend read/write failure는 조회와 후속 mutation을 중단하고 원본 bytes를 보존한다. Persisted state 오류는 planning·approval 같은 domain `ValueError`와 분리된 `ReportWorkflowStoreError`로 전달되어 API의 400 응답으로 축소되지 않는다. 각 workflow record에는 API에 노출하지 않는 최근 mutation ID를 최대 64개 보존한다. Conditional write가 commit된 뒤 응답이 유실되고 후속 CAS가 발생해 exact payload가 달라져도 receipt로 원래 operation을 조정하며, receipt schema가 손상되면 fail closed 처리한다. 이 보장은 tenant별 단일 report workflow state object 범위이고 실제 AWS runtime 및 다른 state object와의 multi-object transaction은 현재 보장하지 않는다.

## 데이터 흐름 — 감사 로그 상태

`AuditStore`는 tenant별 `tenants/{tenant_id}/audit_logs.jsonl`을 앱이 선택한 local/S3 `StateBackend`에 저장한다. Append 전에 caller entry와 기존 JSONL 전체의 tenant, required field, duplicate key와 `log_id`를 검증하고, malformed·foreign·duplicate evidence를 자동 복구하거나 덮어쓰지 않는다. 새 line을 붙일 때 기존 raw byte prefix와 trailing-newline 경계를 그대로 유지한다.

Worker 간 append 권위는 process-local lock에만 의존하지 않는다. Missing object는 conditional create, 기존 object는 검증된 원문을 expected value로 사용하는 compare-and-swap으로 갱신한다. 충돌하면 최신 JSONL을 다시 읽고 전체 무결성을 검증한 뒤 같은 entry를 최대 32회 재적용한다. S3는 `If-None-Match`와 ETag `If-Match`, local은 conditional file lock과 atomic replace를 사용한다. Conditional commit 응답이 유실되고 다른 worker의 successor append가 이어져 exact payload가 달라져도 `log_id`와 exact entry read-back으로 원래 append의 성공을 조정한다. 보장 범위는 tenant별 단일 audit JSONL object이며 실제 AWS runtime은 별도 검증 범위다.

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

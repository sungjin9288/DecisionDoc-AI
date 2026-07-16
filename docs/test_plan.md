# 시험 계획서 및 결과서
## DecisionDoc AI v1.0 — GS인증 시험

---

## 1. 시험 개요

| 항목 | 내용 |
|------|------|
| 시험 대상 | DecisionDoc AI v1.0 |
| 시험 기준 | TTA.KO-10.0169 (소프트웨어 품질 특성) |
| 시험 환경 | Python 3.12, Ubuntu 22.04, Docker |
| 자동화 도구 | pytest 9.0, httpx, playwright |
| 자동화 범위 | `tests/` 하위 단위/통합/E2E 및 smoke/load test 스크립트 |

---

## 2. 시험 범위

### 2.1 기능 시험
| 시험 항목 | 대표 시험 파일 | 비고 |
|-----------|----------------|------|
| 문서 생성 | `tests/test_generate.py`, `tests/test_quality_hardening.py`, `tests/test_self_improve.py`, `tests/test_tenant.py`, `tests/test_infrastructure.py` | bundle 생성, export, validation, explicit tenant contract, tenant별 cache/customization 격리, thread-local 복원 |
| 인증/인가 | `tests/test_auth_*.py`, `tests/test_identity_store_integrity.py` | JWT, API key, tenant/auth 흐름, 계정·초대 state 무결성 |
| 생성 이력 | `tests/test_history_store_integrity.py`, `tests/test_phase1_features.py`, `tests/test_history_favorites.py` | tenant ownership, JSONL 손상 보존, 재열기·즐겨찾기·시각자료·지식 승격, local/S3 동시성 |
| 회의 녹음 | `tests/test_meeting_recording_store_integrity.py`, `tests/test_meeting_recordings.py` | tenant/project/recording ownership, metadata·audio 손상 보존, UUID 충돌, local/S3 동시 전사·승인, source provenance |
| 청구/결제 | `tests/test_billing_store_integrity.py`, `tests/test_billing.py` | tenant/backend 결속, JSON 손상 보존, plan/status/Stripe identity 동시 변경, metered request 402/503, Price ID·subscription metadata, mock webhook lifecycle |
| 사용자 템플릿 | `tests/test_templates_api.py`, `tests/test_template_store_integrity.py` | tenant/backend 결속, JSONL 손상·중복 차단, local/fake-S3 동시 변경, CRUD lifecycle |
| 공개 공유 | `tests/test_phase3_features.py`, `tests/test_share_store_integrity.py` | tenant/backend 결속, JSON 손상·identity drift 차단, local/fake-S3 동시 create/access, public view/revoke lifecycle |
| Admin 테넌트 인증 | `tests/test_tenant.py`, `tests/test_infrastructure.py`, `tests/e2e/test_main_flow.py` | tenant 목록의 admin JWT/Ops key 경로, signed-token tenant 동기화, selector access preflight/rollback, logout draft 폐기 |
| 결재 워크플로우 | `tests/test_approval_workflow.py` | submit, approve, reject |
| 나라장터 연동 | `tests/test_g2b.py` | 검색/수집 흐름 |
| SSO | `tests/test_sso.py` | LDAP/SAML/GCloud 관련 검증 |
| SSO 설정 상태 무결성 | `tests/test_sso_store_integrity.py` | local/fake-S3 손상 보존·동시 부분 변경·secret/SAML/route/API 경계 |
| 파일 형식 | `tests/test_pdf_endpoint.py`, `tests/test_excel_endpoint.py` 등 | export 계열 |
| 프로젝트 관리 | `tests/test_project_management.py`, `tests/test_voice_brief_import.py` | 프로젝트 문서, Voice Brief import |
| 알림/협업 | `tests/test_notifications.py`, `tests/test_collaboration_store_integrity.py`, `tests/test_history_favorites.py` | 알림·메시지 흐름, tenant/backend 결속, 손상·중복 차단, 동시 쓰기 |
| DocumentOps 이력 | `tests/test_document_ops_agent_api.py`, `tests/storage/test_trajectory_store.py`, `tests/test_audit.py`, `tests/test_infrastructure.py`, `tests/e2e/test_main_flow.py` | explicit tenant contract, ownership drift·중복 ID 차단, shared-lock concurrent append, tenant/filter/search total, 양방향 pagination, summary/lazy detail, 열람·review audit, desktop/mobile 작업대 |
| Auto bundle 입력 | `tests/test_bundle_expander.py` | tenant별 request pattern, admin/Ops 조회, concurrent atomic write, provider contract와 path-safe bundle publication |
| 프로젝트 지식 | `tests/test_knowledge.py`, `tests/test_generate.py`, `tests/test_tenant.py`, `tests/test_infrastructure.py` | 같은 project ID의 tenant별 CRUD/context 격리, ownership drift·중복 ID 차단, concurrent atomic write, legacy system migration, production caller tenant binding |

### 2.2 보안 시험
| 시험 항목 | 대표 시험 파일 | 비고 |
|-----------|----------------|------|
| OWASP Top 10 대응 | `tests/test_security.py`, `tests/test_bundle_expander.py`, `tests/test_knowledge.py`, `tests/storage/test_trajectory_store.py` | XSS, auth, SSRF, project/approval/procurement/report-workflow/model-registry/trajectory의 tenant 필수 조회, tenant-bound billing/user/invite/style/SSO/template/notification/message/history/share/audit/meeting-recording/quality-learning/request-pattern/knowledge 상태, provider-derived path와 cross-tenant IDOR 차단 |
| 인프라 보안 | `tests/test_infrastructure.py` | 헤더, 운영 설정 |
| Rate Limiting | `tests/test_infrastructure.py` 포함 | 로그인/요청 제한 |

### 2.3 성능 시험
| 시험 항목 | 시험 파일 | 임계값 |
|-----------|-----------|--------|
| 응답시간 | test_performance.py | P95 < 2,000ms |
| 동시 처리 | test_performance.py | 100 req < 5s |
| 메모리 안정성 | test_performance.py | 증가 < 50MB |
| 부하 테스트 | scripts/load_test_full.py | 외부 서버 대상 |

---

## 3. 시험 실행 방법

### 전체 시험 실행
```bash
# 단위/통합 테스트
.venv/bin/pytest tests/ -q --ignore=tests/e2e

# 커버리지 포함
.venv/bin/pytest tests/ --cov=app --cov-report=html --ignore=tests/e2e

# 성능 테스트
.venv/bin/pytest tests/test_performance.py -v

# 보안 스캔
.venv/bin/bandit -r app/ -f json -o bandit_report.json
```

### 대표 bundle 구조 품질 evidence

```bash
python3 scripts/build_finished_doc_review_samples.py \
  --output-dir docs/samples/bundle_quality_evidence \
  --run-name current \
  --no-latest \
  --bundles proposal_kr,performance_plan_kr \
  --formats ''

python3 -m app.eval --out-dir reports/eval/v1
python3 scripts/manage_finished_doc_human_review.py validate \
  docs/samples/bundle_quality_evidence/current/human_review_receipt.json
pytest -q tests/test_finished_doc_human_review.py tests/test_build_finished_doc_review_samples.py tests/test_eval_runner.py tests/test_golden_examples.py
```

첫 번째 명령은 mock provider의 fictional fixture를 생성하고 schema validator, bundle-aware lint, request 대비 단위 수치 literal coverage, canonical golden hash를 manifest에 기록한다. 미근거 단위 수치가 있으면 package status는 `review_required`가 된다. 이 검사는 수치의 사실성·최신성·문맥 적합성을 증명하지 않으므로 factual grounding과 human visual review는 자동 통과로 간주하지 않는다. 두 번째 명령은 기본 10개 offline eval fixture의 validator/lint report를 갱신한다. 세 번째 명령은 companion human review receipt가 현재 manifest SHA256에 결속되어 있고 외부 action authorization을 모두 `false`로 유지하는지 확인한다. 모든 경로는 live provider API를 호출하지 않는다.

human review receipt는 manifest 순환 hash를 피하기 위해 manifest artifact 목록 밖에 둔다. 각 bundle의 factual grounding과 visual review를 함께 기록하며, 모든 bundle이 두 항목 모두 `passed`일 때만 `completed`가 된다. builder는 사람 입력이 기록된 receipt가 있는 evidence directory를 재생성하지 않는다. `human_review.html`은 receipt, validation, manifest-declared Markdown에서 재생성하는 작업공간이며 증적 원본으로 취급하지 않는다. 화면에서 생성한 review draft는 manifest SHA256과 receipt SHA256에 결속되고, `apply-draft`는 stale source, unknown bundle, 부분 입력, 외부 action 승인 값을 거부한 뒤 receipt를 atomic update한다. Markdown loader는 절대경로, `..`, symlink, evidence directory 밖의 파일을 거부한다.

Completed review packet 테스트는 pending receipt 거부, manifest-declared artifact 선별, source hash/size 확인, path traversal 차단, deterministic ZIP, embedded `packet_manifest.json`, archive 변조 탐지를 검증한다. Packet index와 receipt는 모든 external action을 계속 `false`로 유지해야 한다.

Procurement review packet 테스트는 검증된 12-artifact directory의 deterministic ZIP 생성, embedded `packet_manifest.json`, source symlink 차단, exact entry order와 path boundary, SHA256/size tamper detection, fingerprint를 다시 맞춘 semantic drift 거부, `review_ready`, `operational_approval: false`, create/verify CLI의 machine-readable success/failure 출력을 검증한다.

Procurement review receipt 테스트는 packet 밖 companion JSON의 deterministic pending state, `packet_sha256` binding, requested reviewer 일치, accepted/changes-requested/rejected 결정, non-empty rationale, canonical UTC timestamp, one-time `review_status` transition을 검증한다. Browser draft 경로는 packet/receipt SHA256·size, ordered schema, reviewer, authority boundary를 검사하고 stale source, 권한 상승, 재적용을 거부한 뒤 receipt를 atomic update하는지 확인한다.

Procurement reviewed package 테스트는 completed receipt만 허용하고 accepted/changes-requested/rejected 결과를 모두 보존하는지 확인한다. 원본 packet, receipt, `reviewed_package_manifest.json`의 fixed entry order와 SHA256/size, deterministic rebuild, inner semantic revalidation, pending receipt·tamper·authority drift·history overwrite 거부, `review_completed`, `operational_approval: false`를 검증한다.

Generation tenant 테스트는 service, DocumentOps agent, context cache, eval pipeline, provider preparation의 `tenant_id`가 required keyword인지와 production 호출부가 이를 명시하는지 AST로 확인한다. 같은 provider·schema·payload라도 tenant별 cache key가 달라야 하고, cache hit metadata는 현재 tenant를 보존해야 한다. Tenant context 없는 direct prompt build는 system A/B·override·eval feedback을 읽지 않으며, 다른 tenant의 feedback store 조회 실패가 injected system store로 이어지지 않는지 확인한다. Invalid tenant는 provider 호출 전에 거부하고 generation thread-local은 기존 값 유무와 관계없이 호출 뒤 원복한다. 이 테스트는 mock provider와 local store만 사용한다.

Quality-learning store 계약 테스트는 feedback, eval, A/B test, prompt override, fine-tune, request-pattern 생성자의 `tenant_id`가 required keyword인지와 cached factory의 tenant 기본값이 제거됐는지 AST로 확인한다. Production 호출부는 constructor keyword 또는 factory positional/keyword로 tenant를 반드시 선택해야 한다. 생성자 생략 호출은 `TypeError`, 빈 값·공백·경로 구분자·`.`·`..`·NUL tenant는 `ValueError`로 실패하고 `tenants/` 경로도 만들지 않아야 한다. 이 검증은 local filesystem만 사용한다.

Model lifecycle과 realtime event 테스트는 `ModelRegistry`와 `KnowledgeStore` 생성자의 tenant 필수 계약, model registry public API의 constructor-owned tenant 불변식, production caller의 명시적 tenant 전달을 AST로 고정한다. 같은 model/job ID의 cross-tenant 조회·상태 변경 차단, explicit foreign drift 보존, 20개 독립 registry 인스턴스의 concurrent registration, unsafe tenant의 경로 생성 전 거부를 local filesystem에서 검증한다. `/events`는 middleware 단계에서는 query token 인증을 위해 public path로 남지만 handler가 missing·invalid·refresh token과 tenant claim 누락을 401로 거부하고 access token의 tenant만 구독 범위로 선택하는지 확인한다.

Usage metering 테스트는 `UsageStore` 생성자의 required tenant와 public API의 constructor-owned tenant 계약, production caller의 명시적 tenant 전달을 AST로 고정한다. 다른 tenant의 `UsageEvent`는 경로를 만들기 전에 거부하고, tenant path에 섞인 foreign JSONL event는 일별 사용량에서 제외하며 원본을 보존해야 한다. Foreign monthly summary는 조회 결과와 한도 계산에 포함하지 않고 새 event 기록도 원본을 덮어쓰지 않은 채 중단한다. 같은 tenant path를 쓰는 20개 독립 store 인스턴스의 동시 기록은 event ID와 monthly generation count를 하나도 잃지 않아야 하며, 이 검증은 local filesystem과 mock billing plan만 사용한다.

G2B bookmark 테스트는 `BookmarkStore` 생성자의 required keyword-only tenant와 production caller의 명시적 tenant 전달을 AST로 고정한다. Unsafe tenant는 경로 생성 전에 거부하고, 저장 시 caller가 넣은 owner metadata는 현재 tenant/user로 덮어쓰되 public 응답에서는 제거해야 한다. Tenant path 안의 explicit foreign bookmark는 조회·중복 판단·삭제에서 제외하고 원본을 보존하며, 같은 path를 쓰는 20개 독립 store 인스턴스의 동시 추가는 bookmark를 하나도 잃지 않아야 한다. API 회귀는 같은 tenant의 다른 사용자가 bookmark를 조회하거나 삭제할 수 없음을 확인하고, S3 경로는 fake backend로 저장 owner와 public 비노출을 검증한다.

Decision Council 테스트는 root-scoped `DecisionCouncilStore`의 `get_latest`와 `upsert_latest`가 required caller tenant를 받고 production write caller가 이를 명시하는지 AST로 고정한다. Unsafe tenant는 경로 생성 전에 거부하고, session tenant와 canonical project/use-case/bundle key 및 procurement record의 tenant/project가 요청 scope와 다르면 저장하지 않아야 한다. Tenant path 안의 explicit foreign·malformed record는 보존하면서 owned record만 조회·revision 갱신하고, 동일 scope의 owned duplicate와 invalid top-level JSON document는 원본을 바꾸지 않은 채 중단해야 한다. 같은 tenant file을 쓰는 20개 독립 store 인스턴스의 동시 session 저장, fake S3 재로드와 기존 project API 연계도 no-cost regression으로 확인한다.

Procurement review evidence 테스트는 root-scoped `ProcurementReviewStore`의 packet/package read와 one-time completion이 required tenant/project/packet SHA-256을 받고 production caller가 세 값을 모두 명시하는지 AST로 고정한다. Unsafe tenant/project는 path 사용 전에 거부하고, forged record와 persisted tenant/project/hash drift는 artifact read나 completion에 사용할 수 없어야 한다. Malformed·foreign identity record와 project prefix의 nested alias는 목록에서 제외하되 원본을 바꾸지 않는다. 같은 review path를 쓰는 20개 독립 store 인스턴스의 concurrent prepare는 한 record만 생성하고 concurrent completion은 한 reviewed package만 확정해야 한다. Local/fake-S3 reload, project completion/download API와 generation handoff도 no-cost regression으로 확인하며 distributed S3 CAS나 외부 실행은 검증 범위가 아니다.

Tenant registry 무결성 테스트는 `TenantStore`가 unsafe tenant ID를 파일 생성 전에 거부하고 registry key와 persisted `tenant_id`가 다른 record를 조회·목록·custom hint·API-key 인증·변경에서 제외하는지 확인한다. Malformed record는 valid tenant를 숨기지 않으면서 원본에 남아야 하고, invalid top-level JSON과 duplicate key는 빈 registry로 대체하거나 다음 쓰기로 덮어쓰지 않아야 한다. 동일 registry를 쓰는 20개 독립 store 인스턴스의 concurrent create, duplicate create, system bootstrap은 tenant를 잃거나 중복 생성하지 않아야 한다. API-key hash가 둘 이상의 active tenant에 중복되면 인증은 fail closed로 끝나며, local/fake-S3 persistence와 admin·middleware 경계도 함께 검증한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

Shared state backend 무결성 테스트는 local/S3의 모든 public operation이 canonical relative path만 받는지 확인한다. Local 경로는 configured root 밖으로 나가는 dot segment와 절대경로뿐 아니라 file/directory symlink read·write·listing을 차단하고 외부 원본을 보존해야 한다. S3 listing은 `tenants/a`와 `tenants/alpha` 같은 adjacent prefix를 분리하고 1,000개 초과 pagination을 continuation token으로 끝까지 순회해야 하며, malformed returned key와 누락·반복 token은 부분 결과를 성공으로 반환하지 않고 중단해야 한다. 이 검증은 임시 filesystem과 fake S3 client만 사용한다.

Project/approval state 무결성 테스트는 tenant ID를 local/S3 path 사용 전에 검증하고 두 backend에서 같은 persistence contract를 사용하는지 확인한다. Invalid JSON, non-list document와 duplicate JSON key는 빈 state로 복구하거나 다음 쓰기로 교체하지 않아야 한다. Tenant path 안의 explicit foreign·identity-malformed record는 조회·목록·변경에서 제외하면서 원본에 남기고, owned duplicate project/approval ID는 mutation 전에 중단해야 한다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 concurrent create는 project와 approval record를 하나도 잃지 않아야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

Procurement decision/source snapshot 무결성 테스트는 tenant, project, snapshot ID를 state path 사용 전에 검증하고 local/S3 모두 shared backend를 통하도록 확인한다. Invalid JSON, non-list decision state와 duplicate JSON key는 빈 state나 missing snapshot으로 보지 않아야 한다. Tenant path 안의 explicit foreign decision은 owned record를 숨기지 않으면서 원본에 남기고, owned malformed record, duplicate project/decision ID와 source snapshot storage path drift는 mutation 전에 중단해야 한다. 같은 tenant file을 쓰는 20개 독립 store 인스턴스의 concurrent upsert는 서로 다른 project record를 잃지 않고 같은 project에는 하나의 decision identity만 유지해야 한다. Snapshot read는 tenant와 project를 바꾸면 같은 snapshot ID를 반환하지 않아야 하며 shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

Report workflow state 무결성 테스트는 tenant를 state path 선택 전에 검증하고 local/S3 모두 shared backend를 사용하도록 고정한다. Invalid JSON, non-list state와 duplicate JSON key는 빈 workflow 목록으로 복구하거나 다음 쓰기로 교체하지 않아야 한다. Tenant path 안의 explicit foreign record는 owned workflow를 숨기지 않으면서 원본에 남기고, owned malformed record, duplicate workflow ID와 slide/comment/approval nested identity는 mutation 전에 중단해야 한다. Persisted identity와 timestamp는 재로드 때 새 값으로 보정하지 않으며 caller가 전달한 invalid planning identity도 저장 전에 거부한다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 concurrent create와 visual asset update는 record를 잃지 않아야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

Audit evidence 무결성 테스트는 tenant를 JSONL path 선택 전에 검증하고 local/S3 모두 shared backend를 사용하도록 고정한다. Missing-state read는 빈 파일이나 object를 만들지 않아야 하고 append는 기존 byte prefix를 그대로 보존해야 한다. Malformed JSON, duplicate JSON key, non-object entry, foreign tenant, invalid required field와 duplicate log ID는 read와 후속 append를 중단하며 원본 bytes를 바꾸지 않아야 한다. Caller의 빈 log ID, invalid result, non-object detail과 foreign tenant도 write 전에 거부한다. 같은 path를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent append는 모든 log identity와 완전한 JSONL line을 보존해야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

협업 state 무결성 테스트는 `MessageStore`와 `NotificationStore`가 tenant를 path 선택 전에 검증하고 앱의 local/S3 backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 invalid·blank·non-list JSON, duplicate key, owned malformed record와 duplicate identity는 조회와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned create를 막거나 원본에서 제거하지 않는다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent post/create는 record를 잃지 않아야 하며, message route와 mention notification은 앱 state의 data root/backend를 전달해야 한다. 손상 state의 API 응답은 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 외부 SMTP·Slack 전달은 검증 범위가 아니다.

계정·초대 state 무결성 테스트는 `UserStore`와 `InviteStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 invalid·blank·non-object JSON, duplicate key, owned malformed identity·role·timestamp와 duplicate username은 인증·등록·초대 수락 및 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 조회·비밀번호 확인·초대 사용 대상에서 제외하되 owned create와 함께 원본에 남아야 한다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 distinct create는 record를 잃지 않고, 같은 username/invite ID의 concurrent create는 하나만 성공해야 한다. 초대 route는 앱 state의 data root/backend를 전달해야 하며 손상 state의 API는 빈 설치나 missing invite로 축소하지 않아야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 실제 초대 메일 전달은 검증 범위가 아니다.

사용자 템플릿 state 무결성 테스트는 `TemplateStore`가 tenant를 JSONL path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않고, 마지막 template 삭제 뒤 남는 빈 JSONL은 유효한 빈 lifecycle 상태로 읽어야 한다. Malformed JSON, duplicate JSON key, non-object·owned malformed record와 duplicate template ID는 조회와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned add와 함께 보존하고, tenant 필드가 없는 기존 record는 path-owned compatibility를 유지해야 한다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent add와 use-count 증가는 record와 증가분을 잃지 않아야 하며 route는 앱 state의 data root/backend를 전달해야 한다. 손상 state의 API는 빈 목록이나 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

생성 이력 state 무결성 테스트는 `HistoryStore`가 tenant를 JSONL path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않고, 마지막 entry 삭제 뒤 남는 빈 JSONL은 유효한 빈 lifecycle 상태로 읽어야 한다. Malformed JSON, duplicate JSON key, non-object·owned malformed record와 duplicate entry ID는 조회와 후속 add/favorite/delete/asset/promotion 변경을 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned add와 함께 보존하고, tenant 필드가 없는 기존 record는 path-owned compatibility를 유지해야 한다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent add와 favorite 변경은 record와 toggle parity를 잃지 않아야 하며 모든 caller는 앱 state의 data root/backend를 전달해야 한다. 손상 state의 API는 빈 목록이나 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나며 generation의 fire-and-forget history 기록도 손상 원본을 교체하지 않아야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

회의 녹음 state 무결성 테스트는 `MeetingRecordingStore`가 tenant/project/recording path component를 state 접근 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하고 malformed JSON, duplicate key, owned malformed metadata와 canonical audio path drift는 조회·목록·전사·승인을 중단하면서 metadata/audio 원본 bytes를 보존해야 한다. Explicit foreign metadata는 숨기고, audio read는 persisted size와 SHA-256을 실제 bytes와 다시 대조해야 한다. 같은 recording path를 쓰는 20개 독립 store 인스턴스의 concurrent UUID collision은 하나의 create만 성공시키고 concurrent transcript/approval 변경은 두 증거를 모두 보존해야 한다. 손상 metadata와 audio의 API 응답은 not-found나 provider failure로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 실제 OpenAI transcription은 검증 범위가 아니다.

결제 권한 state 무결성 테스트는 `BillingStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않은 채 free account를 반환해야 하며 blank·malformed·non-object JSON, duplicate key, tenant/field/plan/status/timestamp drift는 조회와 후속 변경을 중단하면서 원본 bytes를 보존해야 한다. 같은 state object를 쓰는 독립 store 인스턴스의 plan, status, Stripe identity 동시 변경은 필드를 잃지 않아야 하고 production caller는 앱 state의 data root/backend를 전달해야 한다. Middleware는 tenant/auth resolution 뒤에 실행되어 현재 tenant의 초과 사용량을 `402`로 차단하고 상태 검증 실패를 `503 BILLING_STATE_UNAVAILABLE`로 차단해야 한다. 손상 state의 billing read/write/webhook/checkout route는 입력 오류로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Production 환경은 webhook secret을 필수로 하고, secret이 설정된 webhook만 JWT 없이 원본 payload HMAC, timestamp와 복수 `v1` 서명을 검증해야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 실제 Stripe API는 검증 범위가 아니다.

스타일 프로필 state 무결성 테스트는 `StyleStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 blank·malformed·non-object JSON, duplicate key, owned profile/tone/example schema drift, storage identity 불일치, duplicate example ID와 multiple default는 조회·prompt build와 후속 변경을 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned create와 함께 보존하고 tenant 필드 없는 record는 기존 계약대로 untrusted state로 차단해야 한다. 같은 state object를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent create와 bundle override는 profile과 변경분을 잃지 않아야 하며 route는 앱 state의 data root/backend를 전달해야 한다. 손상 state의 style read/write API는 빈 목록이나 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 실제 provider style analysis는 검증 범위가 아니다.

SSO 설정 state 무결성 테스트는 `SSOStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않은 채 disabled 설정을 반환해야 하며 malformed·non-object JSON, duplicate key, unknown provider, exact nested schema/type·timestamp·암호문 형식 drift는 조회와 후속 save/update를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign 설정은 disabled로 숨기되 덮어쓰지 않고 tenant 필드 없는 기존 파일은 path-owned compatibility를 유지해야 한다. 같은 state object의 독립 store 인스턴스가 수행하는 local/fake-S3 partial update는 필드를 잃지 않아야 하며 route는 앱 state의 data root/backend를 전달해야 한다. Strict admin payload, masked secret 보존과 clear, wrong-key decryption failure, SAML private key 복호화, GCloud state와 SAML RelayState 거부를 mock HTTP로 확인한다. Signed assertion verifier가 없거나 IdP certificate가 없으면 SAML ACS는 인증을 거부해야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 실제 LDAP/SAML/GCloud 로그인은 검증 범위가 아니다.

품질 학습 state 무결성 테스트는 `FeedbackStore`, `EvalStore`, `PromptOverrideStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 malformed JSON/JSONL, blank line, duplicate key, owned schema/type/timestamp/score drift는 read와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨긴 채 보존하고 tenant 필드 없는 기존 record는 path-owned compatibility를 유지해야 한다. 독립 store 인스턴스의 local/fake-S3 동시 append/update는 record를 잃지 않아야 하며 quality route와 generation service는 앱 state의 data root/backend를 전달해야 한다. 손상된 feedback, eval, prompt override는 API와 prompt build에서 빈 품질 상태로 바뀌지 않아야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS, fine-tune dataset/export, model registry, provider API와 training execution은 검증 범위가 아니다.

Fine-tune dataset/export와 model authority 테스트는 `FineTuneStore`와 `ModelRegistry`가 tenant를 state path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 malformed JSON/JSONL, blank line, duplicate key, owned schema/type/timestamp/score drift, duplicate request/model/job identity는 조회와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Export는 messages-only JSONL의 record count, size와 SHA-256을 metadata에 결속하고 download와 provider upload 직전에 다시 검증해야 한다. Explicit foreign record는 숨긴 채 보존하고 tenant 필드 없는 기존 record와 hash가 없는 legacy export는 path-owned read compatibility를 유지해야 한다. 독립 store 인스턴스의 local/fake-S3 동시 append/register는 record를 잃지 않아야 하며 fine-tune/model route, generation provider selection과 orchestrator는 앱 data root/backend를 전달해야 한다. 손상된 model registry는 active model 없음으로 축소하지 않는다. 자동 provider training은 기본 비활성 opt-in과 명시적 execution authority를 요구하고 provider job 성공 모델은 promotion eval 전까지 active provider가 되어서는 안 된다. 회귀는 provider method mock만 사용하며 provider API, dataset upload, training execution, external polling, model promotion과 distributed S3 CAS는 검증 범위가 아니다.

공개 공유 state 무결성 테스트는 `ShareStore`가 tenant를 state path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 blank·malformed·non-object JSON, duplicate key, owned malformed record와 storage key/share ID drift는 공개 조회와 후속 create/access/revoke를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 공개·인증 조회와 변경에서 제외하되 owned create와 함께 보존하고, tenant 필드가 없는 기존 record는 path-owned compatibility를 유지해야 한다. 같은 data root를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent create와 access 증가는 link와 증가분을 잃지 않아야 하며 모든 route는 앱 state의 data root/backend를 전달해야 한다. 손상 state의 public/create/revoke API는 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS와 운영 URL 접근성은 검증 범위가 아니다.

Report quality correction 테스트는 server preview와 save artifact의 exact equality, SHA-256 fingerprint binding, fingerprint 누락과 stale input 거부, 동일 artifact 중복 저장 차단, review packet embedded artifact fingerprint 재검증을 포함한다. Summary 탐색은 tenant-scoped offset/limit, ready filter total, `has_more`, 페이지 경계를 검증하고 UI에서는 페이지 이동·ready 모드 전환 중 pilot 선택을 유지하는지 확인한다. Pilot export 테스트는 선택한 3~5개 artifact의 tenant-scoped resolve, 요청 순서, ready gate, alias 중복 거부, `preview_sha256` 누락·불일치 차단, preview/export JSONL SHA-256 일치, verification header와 append-only audit detail, 외부 학습 비승인 경계를 함께 확인한다. Pack-local review workspace는 현재 입력으로 draft를 다운로드하기 전까지 apply command를 잠그고, 다운로드 뒤 입력이 바뀌면 즉시 다시 잠그는지 확인한다. Pending draft는 일반 apply, 모든 결정이 accepted인 draft는 `--require-ready` 검증 경로를 선택하되 source artifact readiness 통과를 화면에서 미리 주장하지 않는다. Audit CSV 테스트는 같은 tenant와 action/result/기간 filter, date-only 종료일의 당일 포함, 1,000건 초과 export, 전체 detail과 pilot 식별자, spreadsheet formula injection 방어를 검증한다. Audit 조회 테스트는 검증된 offset/limit, filtered total, `has_more`, 첫·마지막 페이지 경계를 확인한다. UI는 조회와 CSV가 같은 filter를 전송하고 누락·역전 기간을 요청 전에 차단하며, 조회 조건 변경 시 첫 페이지로 돌아가고 페이지 이동 시 같은 filter를 유지하는지 확인한다. 단일-artifact local demo는 mock provider와 임시 storage만 사용하고 저장된 artifact와 preview가 동일한지 확인한다. Full pilot handoff demo는 3개 artifact의 API package부터 source-bound import, simulated review, ready sync, handoff finalize, exact HTML 검증까지 연결하고 provider key 제거·환경 복원·write-once receipt·`human_review_claimed=false` 경계를 검증한다. Receipt checker는 exact field contract, UTC timestamp, artifact count/order, SHA-256, stage 순서, simulated/no-training boundary, 대표 secret pattern을 read-only로 검사하고 tamper와 symlink input을 거부한다.

DocumentOps trajectory 이력 테스트는 모든 public store API의 explicit tenant 계약과 production `_trajectory_store` 호출부의 tenant keyword를 AST guard로 고정한다. 새 record와 SFT metadata의 ownership, unsafe tenant path 거부, 독립 store instance의 concurrent append, explicit foreign drift와 duplicate ID의 fail-closed 조회·review·통계·export 차단, foreign metadata 원본 보존, foreign training artifact의 readiness 제외를 확인한다. 기존 `get_records()` 최신 N건 호환성을 유지하면서 최신·오래된 순 offset pagination이 중복 없이 전체 기록을 순회하는지도 검증한다. API는 tenant·task·review filter와 제목·trajectory/request ID·검토자·task·skill·provider의 case-insensitive 검색 조합별 실제 `total`, `returned`, `has_more`, 적용된 `query`/`order`, 잘못된 offset·order·검색 길이 거부를 검증한다. 기본 full-list 호환과 `include_detail=false` summary projection, tenant-scoped 단건 상세, missing ID 404, 정적 stats route 보존도 같은 API 회귀에서 확인한다. 상세 열람과 review audit은 인증 실패 우선순위, 성공·실패 result, trajectory resource ID, 상태·결정·reviewer·버전·점수를 확인하고 입력·초안·notes가 detail에 들어가지 않는지 검증한다. Browser E2E는 mock provider로 13건을 저장한 뒤 검색, pagination, filter, 양방향 정렬, stale response 무시와 유효 page 복귀를 확인한다. 별도 상세 검토 E2E는 summary에서 lazy detail과 retry를 거쳐 사람 review를 저장하고, tenant 변경 전 시작된 stats 응답을 무시하는지, 입력 중 초안이 사용자·tenant·trajectory 복합 key로만 복원되는지, 같은 trajectory ID를 다른 tenant context에서 조회할 수 없는지, Admin audit 필터에 민감 본문이 없는지 확인하며 390px 가로 overflow 없음과 console/page error 0건을 검증한다. Multi-tenant auth E2E는 local tenant와 초대 사용자를 만들고 denied selector rollback, logout draft cleanup, stale browser tenant를 signed token tenant로 교정한 뒤 tenant-scoped DocumentOps stats 접근을 확인한다. Dataset upload, provider API, training, model promotion은 실행하지 않는다.

Training evidence 테스트는 packet evidence와 reviewer sign-off부터 discussion, experiment plan, final approval packet review, pending final approval record template까지의 hash와 권한 경계를 검증한다. 이 template은 `final_training_approval_granted=false`, required approval `pending`, provider job과 execution step `not_started`를 강제하는 terminal local artifact다. 이후 실행은 이 테스트 범위 밖의 별도 change control과 명시적 승인이 필요하다.

생성된 `review.html`과 `human_review.html`은 local static server에서 request 근거, 검증 상태, Markdown 본문, reviewer 입력, review draft 다운로드, responsive overflow를 확인한다. 2026-07-13에는 desktop `1440x1000`, mobile `390x844`에서 확인했으며 mobile `documentElement.scrollWidth == innerWidth`를 검증했다. 2026-07-14 report workflow UI도 mock/local server에서 pilot 사전 검토, server-confirmed hash-bound JSONL 다운로드, desktop `1280x900`, mobile `390x844`, mobile bottom navigation 비가림, console error 0건, `documentElement.scrollWidth == innerWidth`를 확인했다.

```bash
pytest -q tests/test_finished_document_packet.py tests/test_finished_doc_human_review.py tests/test_build_finished_doc_review_samples.py
pytest -q tests/test_procurement_decision_package_review_packet.py tests/test_procurement_decision_package_cli_success_contract.py tests/test_procurement_decision_package_cli_failure_contract.py
pytest -q tests/test_procurement_decision_package_review_receipt.py tests/test_procurement_decision_package_docs_contract.py
pytest -q tests/test_procurement_decision_package_reviewed_package.py tests/test_procurement_decision_package_cli_success_contract.py tests/test_procurement_decision_package_cli_failure_contract.py
pytest -q tests/test_report_workflows_api.py -k quality_correction
pytest -q tests/test_run_report_quality_learning_demo.py
pytest -q tests/test_run_report_quality_pilot_handoff_demo.py
pytest -q tests/test_check_report_quality_pilot_handoff_demo_receipt.py
pytest -q tests/test_report_quality_learning.py -k review_packet_validator
pytest -q tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py
pytest -q tests/e2e/test_main_flow.py::test_document_ops_trajectory_history_searches_filters_and_paginates_without_mobile_overflow
pytest -q tests/e2e/test_main_flow.py::test_document_ops_trajectory_detail_records_explicit_human_review
```

### E2E 시험 (Playwright)
```bash
.venv/bin/pytest tests/e2e/ --headed
```

### 부하 시험
```bash
# 서버 실행 후 (uvicorn 기본 8000 또는 docker compose 개발 3300 중 실제 포트 사용)
python scripts/load_test_full.py \
  --host http://localhost:<port> \
  --users 20 \
  --duration 60 \
  --output load_test_report.json
```

### UAT 시작 전 preflight
```bash
python3 scripts/uat_preflight.py --env-file .env.prod --report-dir ./reports/post-deploy

# 로컬에 운영 .env.prod가 없고 URL을 명시할 수 있는 경우
python3 scripts/uat_preflight.py \
  --base-url https://admin.decisiondoc.kr \
  --report-dir ./reports/post-deploy
```

### UAT 세션 파일 생성
```bash
python3 scripts/create_uat_session.py \
  --env-file .env.prod \
  --report-dir ./reports/post-deploy \
  --output-dir ./reports/uat \
  --session-name business-uat \
  --owner "<담당자>"

# 로컬에 운영 .env.prod가 없고 URL을 명시할 수 있는 경우
python3 scripts/create_uat_session.py \
  --base-url https://admin.decisiondoc.kr \
  --report-dir ./reports/post-deploy \
  --output-dir ./reports/uat \
  --session-name business-uat \
  --owner "<담당자>"
```

### UAT 결과 기록 추가
```bash
python3 scripts/record_uat_result.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --owner "<담당자>" \
  --scenario "시나리오 1. 기본 사업 제안서 생성" \
  --bundle proposal_kr \
  --input-data "기본 입력 요약" \
  --attachments "intro.pdf,concept.pptx" \
  --generation-status "성공" \
  --export-status "DOCX/PDF 성공" \
  --visual-asset-status "일치" \
  --history-restore-status "확인 완료" \
  --quality-notes "문서 구조는 안정적이나 결론 문장이 다소 장문임" \
  --issues "없음" \
  --follow-up "아니오"
```

### UAT 최종 요약 생성
```bash
python3 scripts/finalize_uat_session.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --output-dir ./reports/uat
```

`READY_FOR_PILOT` 판정은 기본 5개 필수 시나리오(`시나리오 1`~`시나리오 5`)가 모두 기록되고, blocker 및 follow-up이 없을 때만 가능하다. 일부 시나리오만 성공한 경우에는 `missing_required_scenarios`가 표시되고 `FOLLOW_UP_REQUIRED`로 유지한다.

### UAT 세션 요약 확인
```bash
python3 scripts/show_uat_session.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --limit 5
```

### UAT 최종 요약 보고서 생성
```bash
python3 scripts/finalize_uat_session.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --output-dir ./reports/uat
```

### Pilot handoff 생성
```bash
python3 scripts/create_pilot_handoff.py \
  --summary-file ./reports/uat/uat-session-<timestamp>-business-uat-summary.md \
  --env-file .env.prod \
  --report-dir ./reports/post-deploy \
  --output-dir ./reports/pilot
```

### Pilot launch checklist 생성
```bash
python3 scripts/create_pilot_launch_checklist.py \
  --handoff-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot.md \
  --output-dir ./reports/pilot
```

### Pilot run sheet 생성
```bash
python3 scripts/create_pilot_run_sheet.py \
  --checklist-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist.md \
  --output-dir ./reports/pilot
```

### Pilot run sheet 기록 업데이트
```bash
python3 scripts/record_pilot_run.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --target run1 \
  --field "started_at=2026-04-22T09:00:00+09:00" \
  --field "operator=<담당자>" \
  --field "request_id=<request_id>" \
  --field "bundle_id=<bundle_id>" \
  --field "stop_decision=continue"
```

### Pilot run sheet 상태 요약 확인
```bash
python3 scripts/show_pilot_run.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md
```

### Pilot sample Run 1/Run 2 실제 실행 및 기록
```bash
python3 scripts/run_pilot_sample.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --base-url https://admin.decisiondoc.kr \
  --operator "<담당자>" \
  --business-owner "<business owner>"
```

### Pilot close-out evidence 사전 채우기
```bash
python3 scripts/prepare_pilot_closeout.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md
```

### Pilot close-out 최종 판정 반영 및 artifact 생성
```bash
python3 scripts/complete_pilot_closeout.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --accepted-for-next-batch yes
```

### Pilot completion report 생성
```bash
python3 scripts/create_pilot_completion_report.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot stakeholder share note 생성
```bash
python3 scripts/create_pilot_share_note.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot delivery index 생성
```bash
python3 scripts/create_pilot_delivery_index.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot delivery bundle 생성
```bash
python3 scripts/create_pilot_delivery_bundle.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot delivery manifest 생성
```bash
python3 scripts/create_pilot_delivery_manifest.py \
  --bundle-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-bundle.zip \
  --output-dir ./reports/pilot
```

### Pilot delivery bundle 검증
```bash
python3 scripts/verify_pilot_delivery_bundle.py \
  --bundle-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-bundle.zip \
  --manifest-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-bundle-manifest.md
```

### Pilot delivery receipt 생성
```bash
python3 scripts/create_pilot_delivery_receipt.py \
  --bundle-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-bundle.zip \
  --manifest-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-bundle-manifest.md \
  --output-dir ./reports/pilot
```

### Pilot delivery audit 생성
```bash
python3 scripts/audit_pilot_delivery.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot delivery chain 전체 갱신
```bash
python3 scripts/refresh_pilot_delivery_chain.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot delivery chain 현재 상태 조회
```bash
python3 scripts/show_pilot_delivery_chain.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md
```

closeout이 더 최신이면 `Stale: true`와 stale artifact 목록이 출력된다. 이 경우 `refresh_pilot_delivery_chain.py`를 먼저 다시 실행하는 것이 맞다.

자동화에서 파싱해야 하면 `--json` 옵션을 사용한다.

상태를 artifact로 남겨야 하면:
```bash
python3 scripts/create_pilot_delivery_status_snapshot.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

stable latest 경로가 필요하면:
```bash
python3 scripts/publish_pilot_delivery_latest_status.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

사람이 바로 읽을 latest audit markdown이 필요하면:
```bash
python3 scripts/publish_pilot_delivery_latest_audit.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

latest status JSON과 latest audit markdown을 같이 동기화하려면:
```bash
python3 scripts/publish_pilot_delivery_latest_artifacts.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

gate 용도로 latest 상태만 판정하려면:
```bash
python3 scripts/assert_pilot_delivery_ready.py \
  --status-file ./reports/pilot/latest-pilot-delivery-status.json
```

latest publish와 gate를 한 번에 실행하려면:
```bash
python3 scripts/check_pilot_delivery_ready.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

latest status/audit 동기화와 gate를 한 번에 실행하려면:
```bash
python3 scripts/check_pilot_delivery_latest_artifacts_ready.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

최종 readiness 결과 자체를 stable JSON으로 남기려면:
```bash
python3 scripts/publish_pilot_delivery_latest_readiness.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

사람이 바로 읽을 latest readiness markdown이 필요하면:
```bash
python3 scripts/publish_pilot_delivery_latest_readiness_note.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

latest readiness JSON과 markdown을 같은 시점으로 같이 발행하려면:
```bash
python3 scripts/publish_pilot_delivery_latest_readiness_artifacts.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

운영자용 latest overview markdown 한 장을 만들려면:
```bash
python3 scripts/publish_pilot_delivery_latest_overview.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

현재 stable latest 파일들이 모두 맞는지 read-only로 보려면:
```bash
python3 scripts/show_pilot_delivery_latest_summary.py \
  --output-dir ./reports/pilot
```

latest overview까지 갱신한 뒤 바로 current latest summary를 보려면:
```bash
python3 scripts/check_pilot_delivery_latest_summary_ready.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot close-out 생성
```bash
python3 scripts/finalize_pilot_run.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --output-dir ./reports/pilot
```

---

## 3.1 현재 단계 판단

DecisionDoc AI는 현재 기준으로 핵심 개발 범위가 대부분 구현 및 회귀 검증된 상태이며, 다음 단계의 중심은 **신규 기능 개발보다 실사용 UAT(User Acceptance Test)** 이다.

### 현재 완료에 가까운 범위

- 문서 생성 기본 플로우
- 첨부 기반 생성(`/generate/with-attachments`, `/generate/from-documents`)
- 주요 export 흐름(DOCX/PDF/PPTX/HWPX/XLSX)
- visual asset 생성 및 export 재사용
- quality-first provider routing (`claude/openai/gemini`, `attachment/visual` route 포함)
- post-deploy report, ops dashboard, compare, legacy report empty-state
- 위 기능들에 대한 unit / integration / browser regression test

### 현재 우선순위

- 신규 기능 추가보다 **실제 업무 자료 기반 UAT**
- provider 품질 비교
- 대용량/복수 첨부 성능 및 실패 패턴 확인
- export 산출물 실사용 검수

즉, 현 단계의 목표는 “기능을 더 붙이는 것”보다 “실사용 시나리오에서 어떤 케이스가 남는지 수집하고 품질을 보정하는 것”이다.

---

## 3.2 UAT 실행 체크리스트

### 사전 준비

- [ ] 운영 환경 `/health`가 `status=ok` 인지 확인
- [ ] `provider_policy_checks.quality_first = ok` 인지 확인
- [ ] `post-deploy` latest report가 최근 배포 기준으로 `passed` 인지 확인
- [ ] 테스트용 API key / admin 계정 / Ops key 접근 확인
- [ ] 첨부 테스트 파일 세트 준비
  - [ ] PDF 1건
  - [ ] DOCX 또는 PPTX 1건
  - [ ] HWPX 1건
  - [ ] 구형 `.hwp` 1건(차단 메시지 확인용)

### 기능 검수

- [ ] 기본 문서 생성 3건 이상 실행
- [ ] 첨부 기반 문서 생성 3건 이상 실행
- [ ] 첨부 없는 생성과 첨부 기반 생성의 품질 차이 기록
- [ ] 결과 화면에서 visual asset 생성 후 export 결과와 일치하는지 확인
- [ ] `history` / `server history`에서 복원 후 export가 동일 자산을 재사용하는지 확인

### 산출물 검수

- [ ] DOCX 다운로드 후 Microsoft Word 또는 호환 뷰어에서 열기 확인
- [ ] PDF 다운로드 후 레이아웃 깨짐 여부 확인
- [ ] PPTX 다운로드 후 슬라이드 편집 가능 여부 확인
- [ ] HWPX 다운로드 후 한글에서 열기/수정/재저장 가능 여부 확인
- [ ] XLSX가 포함되는 번들은 수식/시트 구조 이상 여부 확인

### 실패/품질 검수

- [ ] 구형 `.hwp` 업로드 시 `HWPX/PDF/DOCX로 변환` 안내가 노출되는지 확인
- [ ] 느린 요청, 타임아웃, provider fallback 발생 여부 기록
- [ ] 결과 문체, 구조, 사업 맥락 적합성에 대한 주관 평가 기록
- [ ] export와 화면 결과가 불일치하는 케이스가 있는지 기록

### 종료 판단

- [ ] 치명적인 생성 실패 없이 핵심 시나리오를 반복 수행 가능
- [ ] export 산출물이 실제 업무 도구에서 열리고 수정 가능
- [ ] 품질 이슈가 남아도 “후속 보정 목록”으로 정리 가능한 수준

---

## 3.3 우선 UAT 시나리오

### 시나리오 1. 기본 사업 제안서 생성

목표:
- 첨부 없이도 실사용 가능한 초안이 안정적으로 생성되는지 확인

절차:
1. 번들을 선택한다.
2. 목표/배경/제약 조건을 입력한다.
3. 문서를 생성한다.
4. 결과 탭, export 버튼, history 저장 여부를 확인한다.

통과 기준:
- 생성 성공
- 결과 탭 정상 노출
- export 버튼 정상 동작
- 문서 구조가 입력 의도와 크게 어긋나지 않음

### 시나리오 2. 첨부 기반 제안서 생성

목표:
- 참고 문서 2~3건을 업로드했을 때 문맥 반영 품질을 확인

절차:
1. PDF + PPTX + DOCX/HWPX 중 2~3건을 업로드한다.
2. 문서로 초안 생성 또는 첨부 기반 생성을 실행한다.
3. 결과 문서에서 첨부 기반 서술이 들어갔는지 확인한다.

통과 기준:
- 생성 성공
- 첨부 파일 수, 반영된 문맥, 구조적 일관성이 확인됨
- provider timeout/504 없이 완료됨

### 시나리오 3. visual asset 생성 및 export 일관성

목표:
- 화면에서 본 visual asset이 export에도 동일하게 들어가는지 확인

절차:
1. 생성 결과에서 visual asset를 만든다.
2. DOCX/PDF/PPTX/HWPX로 각각 export한다.
3. 결과 파일에서 같은 asset이 재사용되는지 확인한다.

통과 기준:
- 화면과 export 결과가 동일 자산 기준으로 일치
- DOCX/PDF/PPTX에서 자산 누락 없음
- HWPX는 실제 파일 열림 및 이미지 노출 확인

### 시나리오 4. legacy `.hwp` 차단 메시지

목표:
- 지원하지 않는 입력이 명확히 차단되고 사용자가 다음 행동을 알 수 있는지 확인

절차:
1. 구형 `.hwp` 파일을 업로드한다.
2. RFP 분석 또는 첨부 기반 생성을 시도한다.

통과 기준:
- 서버가 무한 대기하지 않음
- UI 또는 API에서 변환 안내가 명시적으로 노출됨
- 사용자가 `HWPX/PDF/DOCX` 변환 필요를 이해할 수 있음

### 시나리오 5. history 복원 + 재export

목표:
- 저장된 결과를 다시 열었을 때 동일한 문서/visual asset/export 맥락이 유지되는지 확인

절차:
1. 결과를 생성하고 history/server history에 남긴다.
2. 페이지를 새로고침하거나 다시 접속한다.
3. history에서 결과를 연다.
4. 다시 export한다.

통과 기준:
- 문서 복원 성공
- visual asset snapshot 유지
- export 결과가 최초 결과와 실질적으로 동일

---

## 3.4 UAT 결과 기록 템플릿

```md
### UAT 기록
- 일시:
- 담당자:
- 시나리오:
- 사용 번들:
- 입력 데이터:
- 첨부 파일:
- 결과:
  - 생성 성공/실패:
  - export 성공/실패:
  - visual asset 일치 여부:
  - history 복원 여부:
- 품질 메모:
- 실패/이슈:
- 후속 조치 필요 여부:
```

---

## 4. 시험 결과 요약

### 운영 기준

| 구분 | 기준 |
|------|------|
| 단위/통합 테스트 | CI와 로컬에서 `pytest tests/ --ignore=tests/e2e -q` 통과 |
| 보안 스캔 | CI에서 Bandit, Safety 실행 |
| 커버리지 | CI에서 `--cov-fail-under=60` 유지 |
| 배포 smoke | `scripts/smoke.py`, `scripts/ops_smoke.py`, 필요 시 `scripts/voice_brief_smoke.py` |

### 성능 측정 결과
| 엔드포인트 | 평균 응답시간 | P95 | 판정 |
|------------|-------------|-----|------|
| /health | < 5ms | < 10ms | ✅ PASS |
| /bundles | < 20ms | < 50ms | ✅ PASS |
| /billing/plans | < 20ms | < 50ms | ✅ PASS |
| /dashboard/overview | < 100ms | < 200ms | ✅ PASS |

---

## 5. 결함 관리

| 결함 ID | 발견일 | 내용 | 상태 |
|---------|--------|------|------|
| BUG-001 | 2026-02 | tenant middleware 응답 순서 오류 | ✅ 수정 |
| BUG-002 | 2026-02 | outline:none CSS 접근성 위반 | ✅ 수정 |
| BUG-003 | 2026-02 | 모달 focus trap 미적용 | ✅ 수정 |

---

## 6. 시험 환경

```
OS: macOS (개발), Ubuntu 22.04 (CI)
Python: 3.12.x
pytest: 9.0.x
주요 의존성: fastapi, pydantic v2, PyJWT, bcrypt, cryptography
```

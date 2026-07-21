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
| 회의 녹음 | `tests/test_meeting_recording_store_integrity.py`, `tests/test_meeting_recordings.py` | tenant/project/recording ownership, metadata·audio 손상 보존, process lock 없는 local/S3 conditional create/CAS, bounded receipt, uncertain commit, source provenance |
| 청구/결제 | `tests/test_billing_store_integrity.py`, `tests/test_billing_store_cas.py`, `tests/test_billing.py` | tenant/backend 결속, JSON 손상 보존, process lock 없는 local/S3 conditional create/CAS, bounded receipt, uncertain commit, metered request 402/503, Price ID·subscription metadata, mock webhook lifecycle |
| 사용자 템플릿 | `tests/test_templates_api.py`, `tests/test_template_store_integrity.py` | tenant/backend 결속, JSONL 손상·중복 차단, local/fake-S3 동시 변경, CRUD lifecycle |
| 공개 공유 | `tests/test_phase3_features.py`, `tests/test_share_store_integrity.py` | tenant/backend 결속, JSON 손상·identity drift 차단, local/fake-S3 동시 create/access, public view/revoke lifecycle |
| Admin 테넌트 인증 | `tests/test_tenant.py`, `tests/test_infrastructure.py`, `tests/e2e/test_main_flow.py` | tenant 목록의 admin JWT/Ops key 경로, signed-token tenant 동기화, selector access preflight/rollback, logout draft 폐기 |
| 프로젝트·결재 워크플로우 | `tests/test_project_management.py`, `tests/test_approval_workflow.py`, `tests/test_project_approval_store_integrity.py` | project/document CRUD, submit/approve/reject, local/fake-S3 무결성과 worker CAS |
| 보고서 워크플로우 | `tests/test_report_workflow_store.py`, `tests/test_report_workflow_store_integrity.py`, `tests/test_report_workflows_api.py` | planning/slide/final approval/promotion lifecycle, local/fake-S3 손상 보존, conditional create/CAS, disjoint update·terminal decision 경쟁·commit reconciliation |
| 감사 로그 | `tests/test_audit.py`, `tests/test_audit_store_integrity.py`, `tests/test_document_ops_agent_api.py`, `tests/test_security.py` | tenant JSONL 손상·duplicate identity·byte-prefix 보존, process lock 없는 fake-S3 conditional create/CAS, bounded conflict retry, successor append 뒤 uncertain commit reconciliation, admin query/export 경계, DocumentOps governance view/handoff resource와 redacted detail |
| 나라장터 연동 | `tests/test_g2b.py` | 검색/수집 흐름 |
| SSO | `tests/test_sso.py` | LDAP/SAML/GCloud 관련 검증 |
| SSO 설정 상태 무결성 | `tests/test_sso_store_integrity.py` | local/fake-S3 손상 보존·동시 부분 변경·secret/SAML/route/API 경계 |
| 파일 형식 | `tests/test_pdf_endpoint.py`, `tests/test_excel_endpoint.py` 등 | export 계열 |
| 프로젝트 관리 | `tests/test_project_management.py`, `tests/test_voice_brief_import.py` | 프로젝트 문서, Voice Brief import |
| 알림/협업 | `tests/test_notifications.py`, `tests/test_collaboration_store_integrity.py`, `tests/test_history_favorites.py` | 알림·메시지 흐름, tenant/backend 결속, 손상·중복 차단, process lock 없는 local/S3 CAS, bounded receipt와 uncertain commit |
| DocumentOps 이력 | `tests/test_document_ops_agent_api.py`, `tests/storage/test_document_ops_run_operation_store.py`, `tests/storage/test_trajectory_store.py`, `tests/storage/test_trajectory_store_integrity.py`, `tests/storage/test_trajectory_artifact_authority.py`, `tests/test_audit.py`, `tests/test_infrastructure.py`, `tests/e2e/test_main_flow.py` | explicit tenant/backend contract, 손상·ownership drift·중복 ID 차단, process lock 없는 local/fake-S3 append/review와 governance operation CAS, captured Agent pre-provider claim, bounded private receipt·lost-response reconciliation, exact replay·changed-payload `409`, corrupt retry state `503`, tenant/filter/search total, exact trajectory search context와 양방향 pagination, summary/lazy detail, same-tenant latest stats/export/readiness/execution-request ordering, provider/model-bound audit checklist ordering, latest Agent result ownership과 filter-preserving stale-save observation, write/provider action single-flight, 열람·review audit, desktop/mobile 작업대 |
| Auto bundle 입력 | `tests/test_bundle_expander.py` | tenant별 request pattern, admin/Ops 조회, concurrent atomic write, provider contract와 path-safe bundle publication |
| 프로젝트 지식 | `tests/test_knowledge.py`, `tests/test_knowledge_store_integrity.py`, `tests/test_generate.py`, `tests/test_procurement_decision_service.py`, `tests/test_report_workflows_api.py`, `tests/test_infrastructure.py` | local/fake-S3 selected backend, tenant/project 격리, v2 index와 immutable content/style hash·size·incarnation binding, legacy migration·orphan 차단, process lock 없는 conditional create/CAS, 32회 conflict cap, 64개 private receipt, commit-then-successor reconciliation, stale replacement 차단, rollback·삭제와 generation/procurement/report consumer wiring |
| G2B 즐겨찾기 | `tests/test_bookmark_store_integrity.py`, `tests/test_phase1_features.py`, `tests/test_state_backend.py`, `tests/test_infrastructure.py` | local/fake-S3 selected backend, missing-state 무부작용, malformed/invalid UTF-8·duplicate·owned identity 차단, legacy/foreign owner 보존, 동시성, API 오류 경계 |
| 공공조달 판단 상태 | `tests/test_procurement_store.py`, `tests/test_procurement_store_integrity.py`, `tests/test_procurement_decision_service.py`, `tests/test_procurement_eval_regression.py`, `tests/test_state_backend.py`, `tests/test_infrastructure.py` | local/fake-S3 selected backend, missing-state 무부작용, 판단/snapshot 손상·중복·path drift·비직렬화 payload 차단, foreign 보존, process lock 없는 conditional create/CAS, bounded receipt·conflict·uncertain commit, API/downstream 회귀 |
| Decision Council | `tests/test_decision_council_store_integrity.py`, `tests/test_decision_council.py`, `tests/test_project_management.py`, `tests/test_state_backend.py`, `tests/test_infrastructure.py` | local/fake-S3 selected backend, missing-state 무부작용, 손상·canonical identity drift·중복 차단, legacy foreign/malformed 보존, process lock 없는 conditional create/CAS, revision·bounded receipt·uncertain commit, API 오류 경계 |

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

Usage metering 테스트는 `UsageStore` 생성자의 required tenant와 public API의 constructor-owned tenant 계약을 유지하고 billing middleware/API, overage 계산과 generation/direct/composite-provider 기록 caller가 앱 backend를 전달하는지 AST로 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 malformed/invalid UTF-8 JSON/JSONL, duplicate identity, field/token/timestamp drift는 조회·한도 검사·후속 기록을 중단하면서 원본 bytes를 보존해야 한다. Event append와 monthly summary 갱신은 각각 conditional create/CAS를 사용하고 32회 충돌 뒤 fail closed 처리해야 한다. Process lock을 제거한 local/fake-S3 독립 worker 20개의 서로 다른 event를 모두 보존하고, 같은 event는 한 번만 기록하며 event·summary commit 응답 유실 뒤 successor append도 조정해야 한다. Event와 summary를 읽는 사이 다른 worker가 두 문서를 갱신한 snapshot skew는 안정된 손상으로 오인하지 않고 bounded retry해야 한다. Monthly summary는 권위 event log에서 다시 계산한 coverage·total·bucket과 일치해야 한다. 정확히 하나의 검증된 trailing event gap은 CAS로 보완할 수 있지만 missing·tamper·복수 gap·foreign current-month collision은 빈 사용량으로 축소하지 않아야 한다. Generation·DocumentOps·meeting transcription·knowledge·G2B·style·procurement·report workflow·admin expansion provider route와 dynamic path를 admission 대상으로 분류하고 direct 작업은 generation event, 실제 provider를 호출한 attachment/visual 작업은 실패 token까지 합산한 auxiliary event로 남겨야 한다. DocumentOps usage write 실패는 trajectory 저장 전에 나타나고 singleton agent는 provider를 요청별로 분리해야 한다. 같은 process의 동시 한도 요청은 tenant lock으로 직렬화하고 취소된 waiter와 rewrite/SSE worker는 각각 획득 lock 반환, provider worker 종료 후 반환 계약을 지켜야 한다. Meeting transcription provider 원문은 HTTP response, persisted error와 observability log에 남지 않아야 한다. Provider visual을 새로 만들지 않는 edited export와 실제 `max_assets` 범위 밖 provider image는 한도 실패 상태에서도 local export를 유지하고 provider를 초기화하지 않아야 한다. Core usage write 실패는 bundle/cache/render/eval side effect보다 먼저 나타나야 하고 `/billing/usage`는 미인증 조회를 거부해야 한다. Sync API와 SSE error event는 `BILLING_STATE_UNAVAILABLE`/`USAGE_STATE_UNAVAILABLE` 계약을 유지한다. Event와 summary를 묶는 atomic transaction, exact distributed reservation, 실제 Stripe API와 provider API는 검증 범위가 아니다.

G2B bookmark 테스트는 `BookmarkStore` 생성자의 required keyword-only tenant와 production caller의 명시적 data root/backend 전달을 AST로 고정한다. Unsafe tenant와 잘못된 user/bid 입력은 state 생성 전에 거부하고 missing-state read는 파일이나 object를 만들지 않아야 한다. Blank·malformed·invalid UTF-8·non-object JSON, duplicate key, invalid user collection, owned malformed record와 duplicate bid identity는 조회와 후속 add/remove를 중단하면서 원본 bytes를 보존해야 한다. 저장 시 caller가 넣은 owner metadata는 현재 tenant/user로 덮어쓰되 public 응답에서는 제거하고, owner 없는 기존 record는 호환하며 explicit foreign/untrusted owner는 조회·중복 판단·삭제에서 제외한 채 보존한다. Local/fake-S3의 독립 store/backend 인스턴스 20개가 동시에 추가해도 bookmark를 잃지 않아야 하고 손상 state의 API는 빈 목록이나 정상 삭제로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Distributed S3 CAS와 실제 G2B API는 검증 범위가 아니다.

공공조달 판단 상태 테스트는 `ProcurementDecisionStore`가 앱이 선택한 local/S3 backend를 사용하고 process lock을 비활성화한 독립 store도 conditional create/CAS로 같은 tenant object를 갱신하는지 확인한다. Missing-state read는 파일이나 object를 만들지 않아야 한다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key, duplicate source snapshot metadata, forged storage path, invalid notes와 비직렬화/non-finite snapshot payload는 조회와 후속 mutation 전에 거부하고 원본 bytes를 보존해야 한다. Explicit foreign decision은 현재 tenant의 조회·변경 대상에서 제외하되 저장 시 그대로 보존한다. 서로 다른 project의 20-way mutation은 record를 잃지 않고 같은 project의 20-way upsert는 하나의 decision identity를 유지해야 한다. Upsert와 notes 변경은 충돌 때 최신 state에 재적용하고 32회 뒤 fail closed 처리하며 private receipt는 최근 64개만 보존하고 public model/API에서 제거해야 한다. Commit-then-error 뒤 successor notes/upsert가 이어져도 원래 operation을 조정하고 source snapshot은 immutable create와 exact read-back으로 lost-success를 판정해야 한다. 손상 state의 procurement GET/evaluate API는 빈 판단이나 새 평가로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 하며 generation과 Decision Council downstream 회귀도 함께 확인한다. CAS는 decision 단일 object 범위이고 snapshot과의 transaction, 외부 원천 진위, 실제 AWS/G2B/provider API는 검증 범위가 아니다.

Decision Council 테스트는 root-scoped `DecisionCouncilStore`의 `get_latest`와 `upsert_latest`가 required caller tenant를 받고 앱이 선택한 data root/backend를 사용하는지 AST와 실제 local backend write로 고정한다. Unsafe tenant는 경로 생성 전에 거부하고, session tenant와 canonical project/use-case/bundle key 및 procurement record의 tenant/project가 요청 scope와 다르면 저장하지 않아야 한다. Missing-state read는 파일이나 object를 만들지 않고 blank·malformed·invalid UTF-8·non-list JSON, duplicate key, owned canonical key drift와 duplicate session ID/key는 조회와 후속 upsert를 중단하면서 원본 bytes를 보존해야 한다. Tenant path 안의 explicit foreign·malformed record는 현재 tenant session으로 사용하지 않되 원본에 남긴다. Process lock을 비활성화한 local/fake-S3 독립 store의 20-way distinct session은 모두 보존하고 same-key 20-way upsert는 canonical session identity와 정확한 revision 증가를 유지해야 한다. 충돌 때 최신 state에 mutation을 재적용하고 32회 뒤 fail closed 처리하며 최근 64개 private receipt와 commit-then-error 뒤 successor update reconciliation을 확인한다. Project API는 private metadata를 노출하지 않고 손상 state를 `INTERNAL_ERROR`로 처리해야 한다. CAS는 Council 단일 object 범위이고 procurement decision과의 transaction, 실제 AWS/provider/G2B API는 검증 범위가 아니다.

Procurement review evidence 테스트는 root-scoped `ProcurementReviewStore`의 packet/package read와 one-time completion이 required tenant/project/packet SHA-256을 받고 production caller가 세 값을 모두 명시하는지 AST로 고정한다. Unsafe tenant/project는 path 사용 전에 거부하고, forged record와 persisted tenant/project/hash drift는 artifact read나 completion에 사용할 수 없어야 한다. Blank·malformed·invalid UTF-8·duplicate key/identity와 backend read/list/write failure는 빈 목록이나 review 입력 충돌로 축소하지 않고 원본 bytes를 보존해야 한다. Canonical owned record의 손상은 project/tenant list와 API를 fail closed로 중단하되 nested path alias는 canonical record로 해석하지 않는다. Packet/reviewed-package의 누락·hash/size 변조, duplicate authority field와 receipt/package semantic drift는 거부하고 completion은 원본 packet을 다시 검증해야 한다. Exact orphan packet recovery, content-addressed package, symlink-safe local conditional lock, fake-S3 `If-None-Match`/ETag CAS, commit-then-error read-back reconciliation과 CAS 패자 package 정리를 검증한다. Process lock을 비활성화한 20-way fake-S3 concurrent prepare는 한 record만 생성하고 concurrent completion은 한 package authority와 artifact만 남겨야 한다. Project inbox/list/download, downstream project/share/approval freshness와 generation handoff의 corrupt state는 `500 INTERNAL_ERROR`로 끝나야 한다. Multi-object distributed transaction과 실제 AWS/provider/G2B 실행은 검증 범위가 아니다.

Tenant registry 무결성 테스트는 `TenantStore`가 unsafe tenant ID를 파일 생성 전에 거부하고 registry key와 persisted `tenant_id`가 다른 record를 조회·목록·custom hint·API-key 인증·변경에서 제외하는지 확인한다. Malformed record는 valid tenant를 숨기지 않으면서 원본에 남아야 하고, invalid top-level JSON과 duplicate key는 빈 registry로 대체하거나 다음 쓰기로 덮어쓰지 않아야 한다. Process lock을 비활성화한 local/fake-S3 20개 독립 store의 concurrent create, duplicate create, system bootstrap은 tenant를 잃거나 중복 생성하지 않아야 한다. Create/update/custom hint/API-key rotation은 conditional create/CAS로 최신 registry에 재적용하고 최대 32회 충돌 뒤 fail closed 처리해야 한다. 최근 64개 private receipt는 tenant 목록·인증에서 제외하고 commit-then-error 뒤 successor mutation을 조정해야 하며, API key rotation은 최초 생성한 plaintext와 persisted hash의 결속을 유지해야 한다. API-key hash가 둘 이상의 active tenant에 중복되면 인증은 fail closed로 끝나야 한다. CAS는 root registry 단일 object 범위이며 실제 AWS runtime은 검증 범위가 아니다.

Shared state backend 무결성 테스트는 local/S3의 모든 public operation이 canonical relative path만 받는지 확인한다. Local 경로는 configured root 밖으로 나가는 dot segment와 절대경로뿐 아니라 file/directory symlink read·write·listing을 차단하고 외부 원본을 보존해야 한다. S3 listing은 `tenants/a`와 `tenants/alpha` 같은 adjacent prefix를 분리하고 1,000개 초과 pagination을 continuation token으로 끝까지 순회해야 하며, malformed returned key와 누락·반복 token은 부분 결과를 성공으로 반환하지 않고 중단해야 한다. 이 검증은 임시 filesystem과 fake S3 client만 사용한다.

Project/approval state 무결성 테스트는 tenant ID를 local/S3 path 사용 전에 검증하고 두 backend에서 같은 persistence contract를 사용하는지 확인한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 blank·invalid UTF-8·invalid JSON·non-list document·duplicate JSON key와 backend read/write 실패는 빈 state로 복구하거나 다음 쓰기로 교체하지 않아야 한다. Tenant path 안의 explicit foreign·ID 없는 legacy malformed record는 조회·목록·변경에서 제외하면서 원본에 남기고, 유효한 owned ID를 가진 schema drift와 duplicate project/approval ID는 mutation 전에 중단해야 한다. 서로 다른 local/virtual base를 쓰더라도 같은 local path 또는 S3 bucket/prefix/object를 가리키는 20개 독립 store 인스턴스의 concurrent create는 project와 approval record를 하나도 잃지 않아야 한다. Corrupt-state project read/create와 approval read/transition API는 `500 INTERNAL_ERROR`를 반환하고 원본 bytes를 보존해야 한다.

Project/approval worker 동시성 테스트는 process-local lock을 비활성화한 fake-S3에서 conditional create와 ETag CAS를 직접 경쟁시킨다. Project에서는 20개 worker의 독립 create와 같은 project의 document add가 모두 보존되어야 하고, disjoint field update와 approval sync가 서로를 덮어쓰지 않아야 한다. Delete/update 경쟁 뒤에는 삭제된 project가 stale update로 되살아나지 않아야 한다. Conditional write가 실제로 commit된 뒤 오류를 반환하고 다른 worker가 후속 CAS까지 완료한 경우에도 bounded mutation receipt로 원래 project/document operation을 성공으로 조정해야 한다. Receipt는 최근 64개로 제한되고 duplicate·invalid entry는 조회와 후속 mutation을 fail closed로 막아야 한다. Approval에서는 20개 worker의 create와 같은 approval의 comment append가 모두 보존되어야 하고, 동일한 `in_review` state에서 시작한 final approve/reject 경쟁은 terminal decision 하나만 확정해야 한다. Approval create/final transition의 commit-then-error는 exact persisted payload read-back으로 조정한다. Multi-object distributed transaction과 실제 AWS S3 runtime은 검증 범위가 아니다.

Procurement decision/source snapshot 무결성 테스트는 tenant, project, snapshot ID를 state path 사용 전에 검증하고 local/S3 모두 shared backend를 통하도록 확인한다. Invalid JSON, non-list decision state와 duplicate JSON key는 빈 state나 missing snapshot으로 보지 않아야 한다. Tenant path 안의 explicit foreign decision은 owned record를 숨기지 않으면서 원본에 남기고, owned malformed record, duplicate project/decision ID와 source snapshot storage path drift는 mutation 전에 중단해야 한다. 같은 tenant file을 쓰는 20개 독립 store 인스턴스의 concurrent upsert는 서로 다른 project record를 잃지 않고 같은 project에는 하나의 decision identity만 유지해야 한다. Snapshot read는 tenant와 project를 바꾸면 같은 snapshot ID를 반환하지 않아야 하며 shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

Report workflow state 무결성 테스트는 tenant를 state path 선택 전에 검증하고 local/S3 모두 shared backend를 사용하도록 고정한다. Missing-state만 side effect 없는 빈 목록으로 읽으며 blank·invalid UTF-8·invalid JSON·non-list state, duplicate JSON key와 backend read/write failure는 빈 workflow로 복구하거나 다음 쓰기로 교체하지 않아야 한다. Tenant path 안의 explicit foreign record는 owned workflow를 숨기지 않으면서 원본에 남기고, owned malformed record, duplicate workflow ID와 slide/comment/approval nested identity는 mutation 전에 중단해야 한다. Persisted identity와 timestamp는 재로드 때 새 값으로 보정하지 않으며 caller가 전달한 invalid planning identity도 저장 전에 거부한다. 같은 local root의 독립 store뿐 아니라 서로 다른 virtual base에서 같은 S3 bucket/prefix/object를 가리키는 20개 store의 concurrent create와 visual asset update도 record를 잃지 않아야 한다. Corrupt-state list/create API는 `500 INTERNAL_ERROR`를 반환하고 원본 bytes를 보존해야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

Audit evidence 무결성 테스트는 tenant를 JSONL path 선택 전에 검증하고 local/S3 모두 shared backend를 사용하도록 고정한다. Missing-state read는 빈 파일이나 object를 만들지 않아야 하고 append는 기존 byte prefix를 그대로 보존해야 한다. Malformed JSON, duplicate JSON key, non-object entry, foreign tenant, invalid required field와 duplicate log ID는 read와 후속 append를 중단하며 원본 bytes를 바꾸지 않아야 한다. Caller의 빈 log ID, invalid result, non-object detail과 foreign tenant도 write 전에 거부한다. 같은 path를 쓰는 20개 독립 store 인스턴스의 local/fake-S3 concurrent append는 모든 log identity와 완전한 JSONL line을 보존해야 한다. Shared lock은 process-local 보장이고 distributed S3 CAS는 검증 범위가 아니다.

협업 state 무결성 테스트는 `MessageStore`와 `NotificationStore`가 tenant를 path 선택 전에 검증하고 앱의 local/S3 backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 invalid·blank·non-list JSON, duplicate key, owned malformed record·duplicate identity와 손상 private receipt는 조회와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned create를 막거나 원본에서 제거하지 않는다. Process-local lock을 비활성화한 20개 독립 local/fake-S3 worker의 concurrent post/create와 disjoint message/notification update는 record와 field를 잃지 않아야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존해야 하며 commit-then-error 뒤 successor mutation과 hard-delete를 read-back으로 조정해야 한다. Local lock-file 최초 동시 create도 별도 backend 회귀로 반복 검증한다. Message route와 mention notification은 앱 state의 data root/backend를 전달하고 손상 state API는 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. 객체별 CAS는 메시지와 notification state를 함께 묶는 distributed transaction이 아니며 실제 AWS runtime과 외부 SMTP·Slack 전달은 검증 범위가 아니다.

계정·초대 state 무결성 테스트는 `UserStore`와 `InviteStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 invalid·blank·non-object JSON, duplicate key, owned malformed identity·role·timestamp, duplicate username과 손상 private receipt는 인증·등록·초대 수락 및 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 조회·비밀번호 확인·초대 사용 대상에서 제외하되 owned create와 함께 원본에 남아야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 worker의 distinct create와 disjoint profile/password 또는 invite update/create는 record와 field를 잃지 않아야 한다. 같은 username/invite ID와 첫 관리자 등록은 하나만 성공하고 초대 수락은 claim winner 하나만 account callback을 실행해야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존하며 commit-then-error 뒤 successor mutation을 read-back으로 조정해야 한다. Callback 실패는 invite claim을 되돌리고 duplicate username API는 400을 반환한 뒤 초대를 다시 사용할 수 있어야 한다. 초대 route는 앱 state의 data root/backend를 전달하며 손상 state의 API는 빈 설치, missing invite 또는 caller 4xx로 축소하지 않아야 한다. 객체별 CAS는 user와 invite state를 함께 묶는 distributed transaction이나 process crash claim recovery가 아니며 실제 AWS runtime과 초대 메일 전달은 검증 범위가 아니다.

사용자 템플릿 state 무결성 테스트는 `TemplateStore`가 tenant를 JSONL path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않고, 마지막 template 삭제 뒤 남는 빈 JSONL은 유효한 빈 lifecycle 상태로 읽어야 한다. Malformed JSON, duplicate JSON key, non-object·owned malformed record와 duplicate template ID·손상 private receipt는 조회와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned add와 함께 보존하고, tenant 필드가 없는 기존 record는 path-owned compatibility를 유지해야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 worker의 concurrent add와 use-count 증가는 record와 증가분을 잃지 않아야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존하며 commit-then-error 뒤 successor create를 read-back으로 조정해야 한다. 대상 mutation과 delete reconciliation은 private immutable incarnation token에 결속해 timestamp가 같은 동일 ID successor도 변경하거나 제거하지 않아야 한다. 직접 호출자의 malformed input은 `ValueError`, persisted-state 손상과 CAS 실패는 `TemplateStoreError`로 분리한다. Route는 앱 state의 data root/backend를 전달하고 손상 state API는 빈 목록이나 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. CAS는 단일 template state object 범위이며 실제 AWS runtime은 검증 범위가 아니다.

생성 이력 state 무결성 테스트는 `HistoryStore`가 tenant를 JSONL path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않고, 마지막 entry 삭제 뒤 남는 빈 JSONL은 유효한 빈 lifecycle 상태로 읽어야 한다. Malformed JSON, duplicate JSON key, non-object·owned malformed record와 duplicate entry ID·손상 private receipt는 조회와 후속 add/favorite/delete/asset/promotion 변경을 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned add와 함께 보존하고, tenant 필드가 없는 기존 record는 path-owned compatibility를 유지해야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 worker의 concurrent add와 favorite toggle은 record와 parity를 잃지 않아야 하고 visual asset과 favorite, promotion과 visual asset 같은 disjoint mutation도 함께 보존해야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존하며 commit-then-error 뒤 successor add를 read-back으로 조정해야 한다. 대상 mutation과 delete는 private immutable incarnation token에 결속해 timestamp가 같은 동일 ID successor도 변경하거나 제거하지 않아야 하며, retention이 원래 add record를 제거한 뒤에도 transferred receipt로 commit을 조정해야 한다. 직접 호출자의 malformed input은 `ValueError`, persisted-state 손상과 CAS 실패는 `HistoryStoreError`로 분리한다. 모든 caller는 앱 state의 data root/backend를 전달하고 손상 state API와 generation의 fire-and-forget 기록은 원본을 교체하지 않아야 한다. CAS는 단일 history state object 범위이며 실제 AWS runtime은 검증 범위가 아니다.

회의 녹음 state 무결성 테스트는 `MeetingRecordingStore`가 tenant/project/recording path component를 state 접근 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하고 malformed JSON, duplicate key, owned malformed metadata와 canonical audio path drift는 조회·목록·전사·승인을 중단하면서 metadata/audio 원본 bytes를 보존해야 한다. Explicit foreign metadata는 숨기고, audio read는 persisted size와 SHA-256을 실제 bytes와 다시 대조해야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 store의 concurrent UUID collision은 하나의 metadata create만 성공시키고 concurrent transcript/approval 변경은 두 증거를 모두 보존해야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존하며, commit-then-error 뒤 successor update를 read-back으로 조정해야 한다. Audio conditional create는 같은 bytes의 orphan만 재사용하고 다른 bytes는 보존한 채 거부해야 한다. 손상 metadata와 audio의 API 응답은 not-found나 provider failure로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. CAS는 recording별 단일 metadata object 범위이며 metadata/audio multi-object transaction, 실제 AWS runtime과 실제 OpenAI transcription은 검증 범위가 아니다.

결제 권한 state 무결성 테스트는 `BillingStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않은 채 free account를 반환해야 하며 blank·malformed·non-object JSON, duplicate key, tenant/field/plan/status/timestamp drift와 손상 private receipt는 조회와 후속 변경을 중단하면서 원본 bytes를 보존해야 한다. Process lock을 비활성화한 독립 local/fake-S3 store의 plan, status, Stripe identity 동시 변경은 필드를 잃지 않아야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존하며 commit-then-error 뒤 successor update를 read-back으로 조정해야 한다. Production caller는 앱 state의 data root/backend를 전달해야 한다. Middleware는 tenant/auth resolution 뒤에 실행되어 현재 tenant의 초과 사용량을 `402`로 차단하고 상태 검증 실패를 `503 BILLING_STATE_UNAVAILABLE`로 차단해야 한다. 손상 state의 billing read/write/webhook/checkout route는 입력 오류로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. Production 환경은 webhook secret을 필수로 하고, secret이 설정된 webhook만 JWT 없이 원본 payload HMAC, timestamp와 복수 `v1` 서명을 검증해야 한다. CAS는 단일 billing object 범위이며 billing/usage transaction, 실제 AWS runtime과 Stripe API는 검증 범위가 아니다.

스타일 프로필 state 무결성 테스트는 `StyleStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 blank·malformed·non-object JSON, duplicate key, owned profile/tone/example schema drift, storage identity 불일치, duplicate example ID와 multiple default는 조회·prompt build와 후속 변경을 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨기되 owned create와 함께 보존하고 tenant 필드 없는 record는 기존 계약대로 untrusted state로 차단해야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 store의 concurrent create와 bundle override는 profile과 변경분을 잃지 않아야 한다. Conditional create/CAS는 32회로 제한하고 private profile incarnation과 최근 64개 receipt는 public/profile-only read에서 숨겨야 하며 commit-then-error 뒤 successor create/update와 delete/recreate identity를 조정해야 한다. Route는 앱 state의 data root/backend를 전달하고 손상 state API는 빈 목록이나 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. CAS는 단일 style profile object 범위이며 실제 provider style analysis는 검증 범위가 아니다.

SSO 설정 state 무결성 테스트는 `SSOStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않은 채 disabled 설정을 반환해야 하며 malformed·non-object JSON, duplicate key, unknown provider, exact nested schema/type·timestamp·암호문 형식 drift는 조회와 후속 save/update를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign 설정은 disabled로 숨기되 덮어쓰지 않고 tenant 필드 없는 기존 파일은 path-owned compatibility를 유지해야 한다. Process lock을 비활성화한 독립 local/fake-S3 store의 partial update는 필드를 잃지 않아야 하고 conditional create/CAS는 32회로 제한해야 한다. 최근 64개 private receipt는 public config에서 숨기고 commit-then-error 뒤 successor update를 조정해야 한다. Route는 앱 state의 data root/backend를 전달하고 strict admin payload, masked secret 보존과 clear, wrong-key decryption failure, SAML private key 복호화, GCloud state와 SAML RelayState 거부를 mock HTTP로 확인한다. Signed assertion verifier가 없거나 IdP certificate가 없으면 SAML ACS는 인증을 거부해야 한다. CAS는 단일 SSO config object 범위이며 실제 LDAP/SAML/GCloud 로그인은 검증 범위가 아니다.

품질 학습 state 무결성 테스트는 `FeedbackStore`, `EvalStore`, `PromptOverrideStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 malformed JSON/JSONL, blank line, duplicate key, owned schema/type/timestamp/score와 feedback/eval append identity drift는 read와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record와 기존 JSONL byte prefix는 append 뒤에도 보존하고 tenant 필드 없는 기존 record는 path-owned compatibility를 유지해야 한다. Feedback와 eval은 process lock을 비활성화한 20개 독립 local/fake-S3 worker의 concurrent append를 conditional create/CAS로 모두 보존해야 한다. Commit-then-error 직후 successor append가 이어져도 feedback ID 또는 private eval append identity read-back으로 원래 append를 한 번만 확정하고, private identity는 public `EvalRecord`에 노출하지 않아야 한다. Prompt override도 worker 간 concurrent save와 applied-count 증가를 보존하고 refresh 경쟁에서 same incarnation의 누적 count를 잃지 않아야 한다. Incarnation 필드가 없는 기존 record는 worker마다 같은 deterministic lineage를 계산해 refresh와 increment를 한 생명주기에 적용해야 한다. 모든 CAS는 32회 충돌 cap을 가지며 prompt override는 payload-bound save receipt, immutable incarnation delete/recreate와 operation ID payload mismatch 거부도 검증해야 한다. Feedback/eval route와 generation service는 앱 state의 data root/backend를 전달하고 손상 state를 빈 품질 힌트로 바꾸지 않아야 한다. 각 CAS는 단일 state object 범위이며 fine-tune authority는 별도 CAS 계약으로 검증하고 provider API·training execution은 검증 범위가 아니다.

품질 실험·요청 패턴 state 무결성 테스트는 `ABTestStore`와 `RequestPatternStore`가 tenant를 path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 blank·malformed·invalid UTF-8 JSON/JSONL, duplicate key·identity, non-object와 owned schema/type/timestamp drift는 read와 후속 create/assign/result/conclude/append/clear를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 숨긴 채 보존하고 tenant 필드 없는 기존 record는 path-owned compatibility를 유지해야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 worker의 experiment create·variant assignment·request append는 record와 counter를 잃지 않아야 하며 conditional create/CAS는 32회로 제한한다. Variant·hint·experiment identity는 한 assignment CAS에서 결속하고 background result와 conclusion은 같은 identity에만 적용해야 한다. Pending winner는 persisted result·hint·mutation receipt와 일치해야 하며 mismatch는 원본 보존 상태로 차단한다. Assignment·append·clear·conclusion claim의 commit 응답 유실 뒤 successor mutation을 read-back으로 조정하고 same-key create receipt와 immutable incarnation으로 replacement와 delete/recreate를 구분해야 한다. Pending reset은 성공으로 오보하지 않고 `409`로 거부한다. Request clear는 첫 snapshot의 unmatched identity만 제거해 후속 append를 남겨야 한다. Generation/eval/dashboard/admin/freeform·sketch caller는 앱 state의 data root/backend를 사용하며 손상 state의 API를 빈 목록이나 정상 생성으로 축소하지 않아야 한다. CAS는 prompt override, A/B, request-pattern 각 단일 object 범위이고 A/B와 override를 함께 묶는 distributed transaction, 실제 AWS/provider API는 검증 범위가 아니다.

Fine-tune dataset/export와 model authority 테스트는 `FineTuneStore`와 `ModelRegistry`가 tenant를 state path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 malformed JSON/JSONL, blank line, duplicate key, owned schema/type/timestamp/score drift, duplicate request/model/job/private identity와 손상 bounded receipt는 조회와 후속 write를 중단하면서 원본 bytes를 보존해야 한다. Dataset append·snapshot-bound clear, export metadata append와 model register/status/eval/deprecate는 process lock을 비활성화한 독립 local/fake-S3 worker에서도 conditional create/CAS로 record와 disjoint successor mutation을 잃지 않아야 하며 32회 충돌 뒤 fail closed 처리해야 한다. Dataset private append identity는 clear 후 같은 request ID로 재생성된 successor를 보존하고 public record에서 제거해야 한다. Model private incarnation과 최근 64개 mutation receipt도 public/API 응답에서 제거하고 commit-then-error 뒤 successor update를 조정해야 한다. Export는 messages-only JSONL을 immutable conditional create하고 record count, size와 SHA-256을 metadata에 결속해 download와 provider upload 직전에 다시 검증해야 한다. Metadata 확정에 실패한 orphan content는 권위가 아니며 두 객체를 distributed transaction으로 주장하지 않는다. Explicit foreign record는 숨긴 채 보존하고 tenant 필드 없는 기존 record와 hash가 없는 legacy export는 path-owned read compatibility를 유지해야 한다. Fine-tune/model route, generation provider selection과 orchestrator는 앱 data root/backend를 전달하고 손상된 registry를 active model 없음으로 축소하지 않아야 한다. 자동 provider training은 기본 비활성 opt-in과 명시적 execution authority를 요구하고 provider job 성공 모델은 promotion eval 전까지 active provider가 되어서는 안 된다. 회귀는 provider method mock만 사용하며 실제 AWS runtime, provider API, dataset upload, training execution, external polling과 model promotion은 검증 범위가 아니다.

공개 공유 state 무결성 테스트는 `ShareStore`가 tenant를 state path 선택 전에 검증하고 local/S3 shared backend를 사용하도록 고정한다. Missing-state read는 파일이나 object를 만들지 않아야 하며 blank·malformed·non-object JSON, duplicate key, owned malformed record, storage key/share ID drift와 손상 private receipt는 공개 조회와 후속 create/access/revoke를 중단하면서 원본 bytes를 보존해야 한다. Explicit foreign record는 공개·인증 조회와 변경에서 제외하되 owned create와 함께 보존하고, tenant 필드가 없는 기존 record는 path-owned compatibility를 유지해야 한다. Process lock을 비활성화한 20개 독립 local/fake-S3 worker의 concurrent create와 access 증가는 link와 증가분을 잃지 않아야 하고 access와 revoke가 경쟁해도 두 변경이 함께 보존되어야 한다. Conditional create/CAS는 32회로 제한하고 private receipt는 최근 64개만 보존하며 commit-then-error 뒤 successor create를 read-back으로 조정해야 한다. 이미 취소된 link의 최초 revoker와 timestamp는 후속 revoke가 덮어쓰지 않아야 한다. 모든 route는 앱 state의 data root/backend를 전달하고 손상 state API는 not-found로 축소하지 않고 `INTERNAL_ERROR`로 끝나야 한다. CAS는 단일 share state object 범위이며 실제 AWS runtime과 운영 URL 접근성은 검증 범위가 아니다.

Report quality correction 테스트는 server preview와 save artifact의 exact equality, SHA-256 fingerprint binding, fingerprint 누락과 stale input 거부, 동일 artifact 중복 저장 차단, review packet embedded artifact fingerprint 재검증을 포함한다. Summary 탐색은 tenant-scoped offset/limit, ready filter total, `has_more`, 페이지 경계를 검증하고 UI에서는 페이지 이동·ready 모드 전환 중 pilot 선택을 유지하는지 확인한다. Pilot export 테스트는 선택한 3~5개 artifact의 tenant-scoped resolve, 요청 순서, ready gate, alias 중복 거부, `preview_sha256` 누락·불일치 차단, preview/export JSONL SHA-256 일치, verification header와 append-only audit detail, 외부 학습 비승인 경계를 함께 확인한다. Pack-local review workspace는 현재 입력으로 draft를 다운로드하기 전까지 apply command를 잠그고, 다운로드 뒤 입력이 바뀌면 즉시 다시 잠그는지 확인한다. Pending draft는 일반 apply, 모든 결정이 accepted인 draft는 `--require-ready` 검증 경로를 선택하되 source artifact readiness 통과를 화면에서 미리 주장하지 않는다. Audit CSV 테스트는 같은 tenant와 action/result/기간 filter, date-only 종료일의 당일 포함, 1,000건 초과 export, 전체 detail과 pilot 식별자, spreadsheet formula injection 방어를 검증한다. Audit 조회 테스트는 검증된 offset/limit, filtered total, `has_more`, 첫·마지막 페이지 경계를 확인한다. UI는 조회와 CSV가 같은 filter를 전송하고 누락·역전 기간을 요청 전에 차단하며, 조회 조건 변경 시 첫 페이지로 돌아가고 페이지 이동 시 같은 filter를 유지하는지 확인한다. 단일-artifact local demo는 mock provider와 임시 storage만 사용하고 저장된 artifact와 preview가 동일한지 확인한다. Full pilot handoff demo는 3개 artifact의 API package부터 source-bound import, simulated review, ready sync, handoff finalize, exact HTML 검증까지 연결하고 provider key 제거·환경 복원·write-once receipt·`human_review_claimed=false` 경계를 검증한다. Receipt checker는 exact field contract, UTC timestamp, artifact count/order, SHA-256, stage 순서, simulated/no-training boundary, 대표 secret pattern을 read-only로 검사하고 tamper와 symlink input을 거부한다.

DocumentOps trajectory 이력 테스트는 모든 public store API의 explicit tenant 계약, 앱이 선택한 `StateBackend` 결속과 production `_trajectory_store` 호출부의 tenant keyword를 AST guard로 고정한다. 새 record와 SFT metadata의 ownership, unsafe tenant path 거부, explicit foreign drift와 duplicate ID의 fail-closed 조회·review·통계·export 차단, foreign metadata 원본 보존, foreign training artifact의 readiness 제외를 확인한다. Blank·malformed·non-object JSONL, duplicate key, non-finite number와 손상 private receipt는 read와 후속 write를 중단하고 원본 bytes를 보존해야 한다. Process lock을 비활성화한 local/fake-S3 독립 worker의 20-way append와 review는 record, review version과 history를 잃지 않아야 하며 expected review version 경쟁에서는 하나만 성공해야 한다. Conditional create/CAS는 32회로 제한하고 private append/incarnation identity와 최근 64개 review receipt는 public/SFT projection에서 숨겨야 한다. Append/review commit-then-error 뒤 successor mutation은 read-back으로 조정하고, same-content legacy path-owned retry는 원본을 바꾸지 않되 같은 ID의 다른 content는 거부해야 한다. Governance 회귀는 `trajectory_metadata.json`의 duplicate key·identity와 count drift를 fail closed 처리하고, process lock 없는 local/fake-S3 concurrent freeze append를 모두 보존하며 32회 conflict cap과 metadata lost-response 뒤 successor append를 확인한다. Export, freeze, approval, request, audit artifact는 immutable selected-backend object로 존재하고 index identity·size·SHA-256 binding이 일치해야 한다. Artifact write lost-success는 exact bytes read-back으로 조정하고 tampered export는 quality report에서 관찰할 수 있어도 일반/reviewed download에서 차단해야 한다. Reviewer sign-off summary는 같은 backend prefix만 읽는다. Ops-key inventory는 다섯 managed collection의 권위 reference와 selected-backend object를 대조해 verified·missing·tampered·invalid·unreferenced exact count를 반환하고, corrupt metadata를 빈 inventory로 축소하지 않으며, legacy hash-only artifact의 size binding을 과장하지 않고 어떤 object도 삭제하지 않아야 한다. 기존 `get_records()` 최신 N건 호환성을 유지하면서 최신·오래된 순 offset pagination이 중복 없이 전체 기록을 순회하는지도 검증한다. API는 tenant·task·review filter와 제목·trajectory/request ID·검토자·task·skill·provider의 case-insensitive 검색 조합별 실제 `total`, `returned`, `has_more`, 적용된 `query`/`order`, 잘못된 offset·order·검색 길이 거부를 검증한다. 기본 full-list 호환과 `include_detail=false` summary projection, tenant-scoped 단건 상세, missing ID 404, 정적 stats route 보존도 같은 API 회귀에서 확인한다. 상세 열람과 review audit은 인증 실패 우선순위, 성공·실패 result, trajectory resource ID, 상태·결정·reviewer·버전·점수를 확인하고 입력·초안·notes가 detail에 들어가지 않는지 검증한다. Browser E2E는 mock provider로 13건을 저장한 뒤 검색, pagination, filter, 양방향 정렬, stale response 무시와 유효 page 복귀를 확인한다. 별도 상세 검토 E2E는 summary에서 lazy detail과 retry를 거쳐 사람 review를 저장하고, tenant 변경 전 시작된 stats 응답을 무시하는지, 입력 중 초안이 사용자·tenant·trajectory 복합 key로만 복원되는지, 같은 trajectory ID를 다른 tenant context에서 조회할 수 없는지, Admin audit 필터에 민감 본문이 없는지 확인하며 390px 가로 overflow 없음과 console/page error 0건을 검증한다. Stats와 Reviewed SFT export list concurrency E2E는 same-tenant success-success와 stale-error 순서를 뒤집어 최신 count와 task-filtered artifact/freeze 목록만 남는지 확인한다. Training Readiness와 Training Execution Request Records concurrency E2E도 같은 순서를 뒤집어 최신 export·freeze chain, dry-run 승인 대상, two-person guard 기록만 유지하는지 확인한다. Execution request 저장 뒤 시작한 새 목록 조회는 저장 전에 시작한 read보다 우선해야 한다. Training Audit Checklist concurrency E2E는 provider/model 조건이 다른 success와 stale error 순서를 뒤집고, planning 변경 뒤 기존 audit action 제거와 audit 저장 뒤 진행 중 이전 read 폐기를 확인한다. Adapter Contract과 Rehearsal concurrency E2E는 서로 다른 provider/model의 success와 stale error 순서를 뒤집어 최신 config·freeze·audit reference만 남는지 확인하고, planning 입력 변경 즉시 기존 evidence가 `RECHECK REQUIRED`로 대체되어야 한다. Export Preview와 artifact list는 시작 시점의 task가 현재 선택과 일치할 때만 결과를 남기고, Training Plan Preview도 동일한 방식으로 provider/model query를 확인해야 한다. Task 또는 planning 입력 변경은 진행 중 success/error와 열린 evidence를 모두 무효화해야 한다. Concurrent Agent run E2E는 latest initiated run과 tenant만 결과 패널을 갱신하고, 늦은 same-tenant trajectory 저장은 현재 filter/page를 보존한 목록 refresh와 알림으로 관측하며 stale failure가 최신 결과를 대체하지 않는지 확인한다. Multi-tenant auth E2E는 local tenant와 초대 사용자를 만들고 denied selector rollback, logout draft cleanup, stale browser tenant를 signed token tenant로 교정한 뒤 tenant-scoped DocumentOps stats 접근을 확인한다. CAS 보장은 trajectory JSONL과 metadata index 각각의 단일 mutable object 범위이며 두 object와 여러 artifact를 묶는 transaction, 비권위 orphan 자동 GC는 제공하지 않는다. Inventory는 atomic metadata snapshot을 기준으로 한 non-transactional multi-object scan이므로 concurrent write 가능성과 실제 cleanup 전에 재확인이 필요하다. Dataset upload, provider API, training, model promotion은 실행하지 않는다.

Governance review overview 회귀는 service가 training governance, artifact inventory, reviewer sign-off를 독립적으로 읽고 boundary drift, artifact integrity, governance blocker, human sign-off 순서로 상태와 다음 검토 행동을 선택하는지 확인한다. API는 Ops-key 단일 GET만 허용하고 세 원본 report, `combined_snapshot_atomic=false`, 수동 재확인, 외부 실행 권한 false를 반환해야 한다. Source fingerprint는 각 report의 top-level `generated_at` 변화에는 안정적이고 실제 검토 상태 변화에는 달라져야 하며, 세 hash를 묶은 review-state fingerprint와 `persisted=false`를 제공해야 한다. Browser는 한 overview 응답으로 세부 패널을 렌더링하고 성공한 동일 tenant 관측만 메모리에서 최초·동일·변경으로 비교해야 한다. 하나의 request version으로 tenant 전환 전 stale 응답이 화면과 비교 기준을 덮어쓰지 않아야 한다. Export·freeze·dry-run approval·execution request·pre-execution audit 저장과 planning provider/model 변경 뒤에는 진행 중 overview를 무효화하고 열린 badge를 `RECHECK REQUIRED`로 바꿔 이전 관측임을 보여야 한다. Fingerprint 기준은 보존하고 성공한 재조회만 fresh 상태를 복구하며 실패·download·read-only 조회는 freshness를 올리지 않아야 한다. Governance summary·overview·inventory·sign-off 조회와 sign-off handoff 다운로드는 trajectory와 분리된 audit action/resource를 남겨야 하고, detail에는 surface·aggregate status·read-only 여부만 허용하며 fingerprint 값, source report, reviewer record는 없어야 한다. 실제 Chromium에서 attention→ready 변경, ready→ready 동일 재확인, mutation/조건 변경 뒤 stale→fresh 복구, 문제 상세와 무삭제 경계, Admin audit filter/render, desktop/mobile 배치, 390px 가로 overflow 없음, console/page error 0건을 검증한다.

Trajectory search ordering 회귀는 새 검색어 입력 뒤 debounce가 replacement request를 시작하기 전에 이전 응답을 완료시킨다. 이전 card가 현재 검색어 아래 렌더링되지 않아야 하며, 새 요청이 완료된 뒤에는 현재 card만 남아야 한다. Static contract는 request version, tenant, task/review filter, query, order가 모두 현재 snapshot과 일치하는지 확인한다.

DocumentOps governance write idempotency 회귀는 freeze·dry-run approval·execution request·audit export에 optional `operation_id`를 전달하고 exact canonical request payload hash와 private metadata receipt를 함께 검증한다. 같은 tenant·collection의 동일 operation과 payload를 local/fake-S3 독립 store에서 동시에 실행해 하나의 authoritative record ID로 수렴해야 하며, 이후 chain이 진행된 뒤 replay해도 원래 size·SHA-256·tenant·identity가 결속된 artifact를 반환해야 한다. 동일 operation의 payload가 달라지면 store conflict와 API `409`로 중단하고 metadata count는 늘지 않아야 한다. Partial receipt, invalid hash와 duplicate operation identity는 원본 bytes를 덮어쓰지 않고 fail closed 처리하며 private fields는 public 목록에 노출하지 않는다. Concurrent CAS loser의 unreferenced immutable artifact는 허용된 관측 한계이고 automatic cleanup과 distributed transaction은 검증 범위가 아니다.

Captured DocumentOps Agent retry 회귀는 `capture_trajectory=true`와 optional `operation_id`를 함께 보낸다. Local/fake-S3 독립 store가 provider 호출 전 conditional claim에서 owner 하나만 허용하고, exact replay는 저장된 result를 반환해 provider call, usage event, trajectory count를 늘리지 않아야 한다. Changed payload와 running/failed receipt는 API `409`, malformed receipt는 provider 실행 전 `503`이어야 하며 원본 bytes를 보존해야 한다. Conditional create와 terminal CAS 응답이 유실된 경우 exact receipt read-back으로 성공을 조정한다. Tenant-scoped status는 running/failed/succeeded receipt에서 operation ID·상태·시각·replay 여부·다음 행동만 반환하고 owner·request/result hash·결과 본문은 응답과 audit에 포함하지 않아야 한다. Missing은 `404`, malformed는 `503`으로 닫는다. Chromium은 initial response loss 뒤 status schema·operation identity·state fields·read-only·provider-call 비승인을 확인하고 succeeded status에서만 최초 payload를 exact replay해야 한다. Mismatched success와 running status는 page-memory pending recovery를 유지하고 Agent 버튼과 상태 재확인 버튼의 동시 click도 status GET과 replay POST 하나로 수렴해야 한다. Status GET은 `no-store`여야 한다. Captured POST 전 shared marker는 tenant-scoped key 아래 schema version, tenant ID, browser UUID operation ID만 포함하고 payload나 extra field를 저장하지 않아야 한다. 두 tab이 거의 동시에 시작하면 tenant별 Web Lock claim 뒤 Agent POST 1건과 marker-bound status GET 1건만 발생해야 한다. Owner tab을 닫은 뒤에도 다른 same-origin tab은 shared marker를 읽어 POST 없이 status-only 화면을 보여야 한다. Tenant A/B marker는 같은 origin에서 함께 유지되고 foreign tenant read/write/clear로 서로 삭제되지 않아야 한다. 승인된 tenant 전환은 이전 tenant marker만 제거해야 한다. H96 base-key marker는 owning tenant만 호환해 읽고, shared/tab scoped marker가 함께 있으면 scoped marker가 legacy보다 우선해야 한다. Shared storage가 예외를 내면 tenant-scoped tab marker fallback이 동작하고 두 storage가 모두 예외를 내도 same-page helper가 요청 흐름을 중단하지 않아야 한다. Tenant-scoped slot의 wrong schema·tenant·UUID와 extra-field marker는 제거하며, logout·invalid session은 current-context pending payload와 marker를 지운다. Capture하지 않는 요청은 operation identity를 거부하며 복구 상태를 만들지 않는다. Payload 없는 exact replay, 다른 browser/device, Web Locks 미지원 환경의 완전 동시 claim, process-crash recovery, 서로 다른 operation ID의 의미상 중복, exactly-once provider 실행, receipt expiry·GC와 live-provider 품질은 검증 범위가 아니다.

DocumentOps write action 회귀는 record를 생성하는 export·freeze·dry-run approval·execution request·audit export와 provider-backed Agent control이 pending 동안 비활성화되고 action 종료 뒤 복구되는지 static wiring으로 확인한다. Browser governance write와 captured Agent run은 action마다 `crypto.randomUUID()`를 한 번 생성해 request body에 포함해야 한다. Chromium은 execution request와 Agent button을 연속 클릭해 POST가 한 건만 시작되고 body의 action-specific UUID, pending 중 disabled, 완료 뒤 enabled 상태가 유지되는지 확인한다. Capture를 끈 Agent 요청에는 operation identity가 없어야 한다. 이 UI gate는 같은 browser control의 accidental duplicate만 다루고, backend operation receipt는 별도 storage/API gate가 검증한다.

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
pytest -q tests/storage/test_trajectory_store.py tests/storage/test_trajectory_store_integrity.py tests/test_document_ops_agent_api.py
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

# Implementation Evidence

분석 기준: 2026-07-20 현재 로컬 repo, mock provider 기반 runtime evidence, OpenAI live proof, non-live pytest gate, completion readiness/proof receipt, static PWA/CSP evidence.

## 1. 프로젝트 유형 판단

| 항목 | 판단 |
|---|---|
| 프로젝트명 | DecisionDoc AI |
| 프로젝트 유형 | 개인 PoC / MVP 확장 프로젝트로 판단 |
| 현재 상태 | MVP/PoC 구현 후 외부 실증 보류, no-cost local evidence 강화 중 |
| 핵심 스택 | Python 3.12, FastAPI, Pydantic v2, Jinja2, provider abstraction, local/S3 storage, Docker Compose, AWS SAM, pytest |
| 이력서 반영 가능 여부 | 조건부 가능 |

판단 이유: 코드상 FastAPI 앱, 문서 생성 API, provider/storage abstraction, export, static PWA, pytest 테스트가 존재하고 로컬 mock provider 기준으로 API 응답과 테스트를 검증했다. 2026-07-20 H74 기준 non-live 전체 게이트는 `4212 passed, 2 skipped, 4 deselected, 1 warning`으로 통과했고, static PWA는 CSP nonce와 inline handler 제거를 확인했다. 2026-07-13 OpenAI live generation은 1회 통과했지만 Gemini는 quota, Claude는 credit balance 때문에 blocked이며 fallback 성공 proof도 남아 있다. 잔여 paid provider proof와 G2B 실데이터, production deployment, 실제 사용자 성과 검증은 현재 보류했다.

## 2. 구현 증거가 필요한 기능

| 기능 | 상태 | 증거 파일 | 검증 방식 | 비고 |
|---|---|---|---|---|
| FastAPI 앱 기동 및 health endpoint | 검증 완료 | `evidence/api-responses/health.json` | local uvicorn + curl | provider는 mock |
| 버전/환경 정보 endpoint | 검증 완료 | `evidence/api-responses/version.json` | curl `/version` | dev 환경 |
| bundle catalog 노출 | 검증 완료 | `evidence/api-responses/bundles.json` | curl `/bundles` | 20개 bundle 반환 확인 |
| API key 보호된 문서 생성 | 검증 완료 | `evidence/api-responses/generate-tech-decision.json` | curl `POST /generate` | mock provider |
| Markdown export 생성 | 검증 완료 | `evidence/api-responses/generate-export-tech-decision.json`, `evidence/output-artifacts/export_adr.md`, `evidence/output-artifacts/export_onepager.md` | curl `POST /generate/export` | local storage |
| 생성/인증/스토리지 테스트 | 검증 완료 | `evidence/cli-logs/pytest_generate_auth_storage.log` | `pytest tests/test_generate.py tests/test_auth_api_key.py tests/test_storage.py -q` | 60 passed |
| 사용자 템플릿 상태 무결성 | 검증 완료 | `app/storage/template_store.py`, `app/routers/templates.py`, `tests/test_template_store_integrity.py` | process lock 없는 local/fake-S3 20-way conditional create/CAS, use-count, bounded private receipt, successor mutation·immutable incarnation reconciliation, API 회귀와 mock/local HTTP lifecycle | CAS는 단일 template JSONL object 범위. 실제 AWS runtime은 범위 밖 |
| 생성 이력 상태 무결성 | 검증 완료 | `app/storage/history_store.py`, `app/routers/history.py`, `app/routers/generate/_shared.py`, `tests/test_history_store_integrity.py` | process lock 없는 local/fake-S3 20-way conditional create/CAS, favorite parity, disjoint visual/promotion update, bounded private receipt, retention carry-forward·immutable incarnation reconciliation, API 회귀와 mock/local HTTP lifecycle | CAS는 단일 history JSONL object 범위. 실제 AWS runtime은 범위 밖 |
| Tenant registry 상태 무결성 | 검증 완료 | `app/storage/tenant_store.py`, tenant admin/auth/middleware caller, `tests/test_tenant_store_integrity.py` | process lock 없는 local/fake-S3 conditional create/CAS, 20-way create/bootstrap, API key rotation, bounded private receipt·successor reconciliation과 caller 회귀 | CAS는 root registry 단일 object 범위. 실제 AWS runtime은 범위 밖 |
| 프로젝트 지식 상태 무결성 | 검증 완료 | `app/storage/knowledge/`, `app/routers/knowledge.py`, generation/procurement/report workflow caller, `tests/test_knowledge_store_integrity.py` | local/fake-S3 v2 index conditional create/CAS, immutable content/style, hash/size/incarnation binding, 32회 conflict cap, 64개 private receipt, lost-response·successor·replacement·legacy migration·API/consumer 회귀 | CAS는 단일 index object 범위. Multi-object transaction, inert artifact 자동 GC와 실제 AWS runtime은 범위 밖 |
| DocumentOps trajectory와 governance artifact 상태 무결성 | 검증 완료 | `app/storage/trajectory/core_mixin.py`, `app/storage/trajectory/state_mixin.py`, `app/storage/trajectory/artifact_state_mixin.py`, `app/main.py`, `tests/storage/test_trajectory_store.py`, `tests/storage/test_trajectory_store_integrity.py`, `tests/storage/test_trajectory_artifact_authority.py`, `tests/test_document_ops_agent_api.py` | 선택된 local/fake-S3 backend의 trajectory JSONL과 metadata index conditional create/CAS, process lock 없는 append/review와 concurrent metadata append, 32회 conflict cap, lost-response·successor reconciliation, immutable export/freeze/approval/request/audit artifact의 identity·size·SHA-256 binding, 손상·중복·tamper·public projection 회귀 | CAS는 trajectory JSONL과 metadata index 각각의 단일 mutable object 범위. 두 object와 여러 artifact의 transaction, 비권위 orphan 자동 GC와 실제 AWS/provider/training runtime은 범위 밖 |
| G2B 즐겨찾기 상태 무결성 | 검증 완료 | `app/storage/bookmark_store.py`, `app/routers/history.py`, `tests/test_bookmark_store_integrity.py` | process lock 없는 local/fake-S3 conditional create/CAS, owner/identity·20-way mutation·bounded receipt·successor reconciliation·API 회귀 | CAS는 단일 bookmark object 범위. 실제 G2B/AWS API는 범위 밖 |
| 공공조달 판단 상태 무결성 | 검증 완료 | `app/storage/procurement_store.py`, procurement project/generation/Decision Council caller, `tests/test_procurement_store_integrity.py` | process lock 없는 local/fake-S3 conditional create/CAS, distinct/same-project 20-way mutation, bounded private receipt·conflict, commit-then-successor reconciliation, immutable snapshot lost-success, API/downstream 회귀와 mock/local HTTP lifecycle | CAS는 decision 단일 object 범위. Snapshot과의 transaction, 외부 원천 진위, 실제 AWS/G2B/provider API는 범위 밖 |
| 공공조달 검토 증빙 상태 무결성 | 검증 완료 | `app/storage/procurement_review_store.py`, `app/storage/state_backend.py`, `app/services/procurement_review_evidence.py`, project review/generation caller, `tests/test_procurement_review_store.py` | local/fake-S3 record·packet·content-addressed package 손상/누락, exact orphan recovery, conditional create/ETag CAS, uncertain commit read-back, receipt/package semantic drift와 API 500 회귀 | multi-object distributed transaction과 실제 AWS/provider/G2B/입찰 실행은 범위 밖 |
| Decision Council 상태 무결성 | 검증 완료 | `app/storage/decision_council_store.py`, `app/routers/projects/procurement.py`, generation context caller, `tests/test_decision_council_store_integrity.py` | process lock 없는 local/fake-S3 conditional create/CAS, distinct/same-session 20-way mutation, canonical identity·revision, bounded private receipt·conflict, commit-then-successor reconciliation, API 회귀와 mock/local HTTP lifecycle | CAS는 Council 단일 object 범위. Procurement decision과의 transaction, 실제 AWS/provider/G2B API는 범위 밖 |
| 프로젝트·결재 상태 무결성 | 검증 완료 | `app/storage/project_store.py`, `app/storage/project_state_mutation.py`, `app/storage/approval_store.py`, `app/storage/state_backend.py`, project/approval router, `tests/test_project_approval_store_integrity.py` | local/fake-S3 missing-state·blank/invalid UTF-8·backend failure·owned schema/duplicate identity·logical lock과 두 store의 conditional create/CAS·project bounded mutation receipt·disjoint mutation·delete 경쟁·competing approval terminal decision·uncertain commit reconciliation·API 회귀와 mock/local lifecycle | ID 없는 legacy malformed record는 숨긴 채 보존. CAS는 각각 단일 tenant project/approval state object 범위이며 multi-object transaction과 실제 AWS runtime은 범위 밖 |
| 보고서 워크플로우 상태 무결성 | 검증 완료 | `app/storage/report_workflow/`, report workflow router/service, `tests/test_report_workflow_store_integrity.py` | local/fake-S3 blank/invalid UTF-8·backend failure·workflow/nested identity·conditional create/CAS·disjoint slide update·competing final decision·bounded receipt·uncertain commit reconciliation·API 500 회귀와 mock/local lifecycle | CAS는 tenant별 단일 state object 범위. 실제 AWS runtime, multi-object transaction과 provider-backed 생성은 범위 밖 |
| 감사 로그 상태 무결성 | 검증 완료 | `app/storage/audit_store.py`, `app/storage/state_backend.py`, audit middleware/router, `tests/test_audit_store_integrity.py`, `tests/test_audit.py` | local/fake-S3 tenant/field/duplicate 검증·byte-prefix 보존, conditional create/CAS, process lock 없는 20-way append, bounded conflict, successor append 뒤 uncertain commit reconciliation, admin API 회귀 | CAS는 tenant별 단일 JSONL object 범위. 실제 AWS runtime은 범위 밖 |
| 협업 상태 무결성 | 검증 완료 | `app/storage/message_store.py`, `app/storage/notification_store.py`, `app/storage/state_backend.py`, message/notification router/service, `tests/test_collaboration_store_integrity.py`, `tests/test_notifications.py` | local/fake-S3 손상·ownership·duplicate 검증, process lock 없는 20-way conditional create/CAS, disjoint update, bounded private receipt, successor mutation·hard-delete uncertain commit reconciliation, API·mock/local HTTP lifecycle | CAS는 각각 단일 message/notification object 범위. 두 object의 transaction, 실제 AWS runtime과 SMTP·Slack 전달은 범위 밖 |
| 계정·초대 상태 무결성 | 검증 완료 | `app/storage/user_store.py`, `app/storage/invite_store.py`, auth/invite router, `tests/test_identity_store_integrity.py`, `tests/test_auth.py`, `tests/test_phase_final.py` | local/fake-S3 손상·ownership·duplicate 검증, process lock 없는 20-way conditional create/CAS, atomic first-admin, disjoint account/invite update, bounded private receipt, uncertain commit reconciliation, invite claim·rollback과 API·mock/local HTTP lifecycle | CAS는 각각 단일 user/invite object 범위. 두 object의 transaction, process crash claim recovery, 실제 AWS runtime과 초대 메일 전달은 범위 밖 |
| 회의 녹음 상태 무결성 | 검증 완료 | `app/storage/meeting_recording_models.py`, `app/storage/meeting_recording_store.py`, `app/services/meeting_recording_service.py`, `tests/test_meeting_recording_store_integrity.py` | process lock 없는 local/fake-S3 metadata conditional create/CAS, concurrent transcript/approval, bounded private receipt, uncertain commit, immutable audio/orphan 경계, API 회귀와 mock/offline HTTP lifecycle | CAS는 recording별 단일 metadata object 범위. Metadata/audio transaction, 실제 AWS runtime과 실제 OpenAI transcription은 범위 밖 |
| 결제 권한 상태 무결성 | 검증 완료 | `app/storage/billing_store.py`, `app/middleware/billing.py`, `app/routers/billing.py`, `tests/test_billing_store_integrity.py`, `tests/test_billing_store_cas.py` | process lock 없는 local/fake-S3 conditional create/CAS, disjoint plan/status/Stripe identity update, bounded private receipt, uncertain commit, middleware/API 회귀와 mock/local webhook lifecycle | CAS는 tenant별 단일 billing object 범위. Billing/usage transaction, 실제 AWS runtime과 Stripe API는 범위 밖 |
| 사용량 계량 상태 무결성 | 검증 완료 | `app/storage/usage_store.py`, `app/middleware/billing.py`, `app/services/generation/context_store.py`, `app/agents/document_ops_agent.py`, `tests/test_usage_store_integrity.py` | process lock 없는 local/fake-S3 event conditional create/CAS와 summary CAS, 20-way append, same-event deduplication, two-document snapshot skew retry, exact one-event gap repair, 32회 conflict cap, event·summary uncertain commit reconciliation, provider route admission·DocumentOps/meeting transcription/direct/composite metering·실패 token 보존·provider 오류 redaction·취소 안전 lock·auth/API 회귀와 mock generation lifecycle | Event/summary atomic transaction·exact distributed reservation, 실제 AWS runtime과 provider usage는 범위 밖 |
| 스타일 프로필 상태 무결성 | 검증 완료 | `app/storage/style_store.py`, `app/storage/style_store_validation.py`, `app/routers/styles.py`, `app/domain/schema.py`, `tests/test_style_store_integrity.py` | process lock 없는 local/fake-S3 conditional create/CAS, concurrent create/override, bounded receipt·private incarnation·successor reconciliation과 prompt/API 회귀 | CAS는 단일 style profile object 범위. 실제 provider style analysis는 범위 밖 |
| SSO 설정 상태 무결성 | 검증 완료 | `app/storage/sso_store.py`, `app/routers/sso.py`, `app/services/sso/saml_auth.py`, `tests/test_sso_store_integrity.py` | process lock 없는 local/fake-S3 conditional create/CAS, concurrent partial update, bounded receipt·successor reconciliation과 secret/SAML/API 회귀 | CAS는 단일 SSO config object 범위. 실제 LDAP/SAML/GCloud 로그인은 범위 밖. 기본 requirements에서는 SAML ACS fail closed |
| 품질 학습·실험 상태 무결성 | 검증 완료 | `app/storage/feedback_store.py`, `app/eval/eval_store.py`, `app/storage/conditional_state.py`, `app/storage/prompt_override_store.py`, `app/storage/ab_test_store.py`, `app/storage/ab_test_conclusion.py`, `app/storage/request_pattern_store.py`, `app/domain/schema.py`, `tests/test_quality_learning_store_integrity.py`, `tests/test_quality_experiment_state_integrity.py` | Feedback/eval·prompt override·A/B·request pattern은 process lock 없는 local/fake-S3 conditional create/CAS와 32회 cap을 검증. Feedback/eval은 JSONL byte prefix, stable/private append identity, 20-way append와 commit-then-successor reconciliation을 확인하고 public eval 계약을 유지한다. Override/A/B/request pattern은 payload-bound save receipt, refresh 경쟁 applied count, atomic variant/hint/identity assignment, experiment-bound result, pending semantic/receipt, uncertain commit·successor mutation과 API/prompt caller를 검증 | 각 단일 object CAS까지만 검증했으며 A/B와 override의 distributed transaction, 실제 AWS/provider API는 범위 밖 |
| Fine-tune dataset와 model authority 무결성 | 검증 완료 | `app/storage/finetune_store.py`, `app/storage/model_registry.py`, `app/services/finetune_orchestrator.py`, `tests/test_finetune_model_state_integrity.py` | process lock 없는 local/fake-S3 dataset append·snapshot clear·export metadata·model lifecycle conditional create/CAS, immutable export, private append/incarnation receipt, 20-way mutation, 32회 cap, uncertain commit·orphan authority·API·provider-selection·mocked execution guard 회귀 | CAS는 dataset/metadata/registry 각 단일 object 범위. Export content/metadata transaction, 실제 AWS/provider API, dataset upload, training execution, external polling과 model promotion은 범위 밖 |
| 공개 공유 상태 무결성 | 검증 완료 | `app/storage/share_store.py`, `app/routers/history.py`, `tests/test_share_store_integrity.py` | process lock 없는 local/fake-S3 20-way conditional create/CAS, access/revoke disjoint update, bounded private receipt, successor mutation reconciliation, public/auth API 회귀와 mock/local HTTP lifecycle | CAS는 단일 share JSON object 범위. 실제 AWS runtime과 운영 URL 접근성은 범위 밖 |
| Procurement decision package local evidence contract | 재현 가능 | `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json` | `python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py --write-result --result-path /tmp/decisiondoc-cli-contract-manifest-validation-result.json` | `contract_version` 기준 stdout JSON contract |
| Procurement decision package persisted receipt check | 재현 가능 | `/tmp/decisiondoc-cli-contract-manifest-validation-result.json` | `python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py /tmp/decisiondoc-cli-contract-manifest-validation-result.json` | repo 밖 receipt 검증 |
| Static PWA 화면 제공 | 검증 완료 | `evidence/screenshots/web-ui-home.png` | Playwright screenshot | 2026-07-08 기준 로그인 화면 확인 |
| Static PWA CSP boundary | 검증 완료 | `evidence/cli-logs/ui_csp_nonce_check.log`, `tests/test_pwa.py`, `tests/test_infrastructure.py` | HTTP header/body check + pytest | CSP nonce 있음, `script-src 'unsafe-inline'` 없음, inline handler 0개 |
| Completion readiness receipt | 재현 가능 | `reports/completion-readiness/latest.json` (gitignored local receipt) | `python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json` | 외부 호출 없이 M1/M2/M6 입력 부족 확인 |
| Completion readiness receipt checker | 재현 가능 | `reports/completion-readiness/latest-check.json` (gitignored local receipt) | `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json` | schema/order/command/excluded action contract 확인 |
| Completion proof receipt checker | 재현 가능 | `reports/completion-readiness/*-proof.json` (gitignored local receipt) | `python3 scripts/check_completion_proof_receipt.py --print-template M1`, `python3 scripts/check_completion_proof_receipt.py <receipt>` | 실제 proof 이후 command/timestamp/evidence refs/secret boundary contract 확인 |
| M2/M6 smoke-owned proof receipt | 재현 가능 | `reports/completion-readiness/m2-*.json`, `m6-*.json` (gitignored) | smoke runner `--proof-receipt` + checker | preflight 외부 미실행 상태와 실제 pass/fail을 atomic 기록, secret/query 미보존 |
| Source-backed README metrics | 검증 완료 | `scripts/count_readme_metrics.py`, `tests/test_count_readme_metrics.py` | AST/source parser 기반 count | README 수치 drift 방지 |
| Contribution boundary note | 생성 완료 | `docs/contribution-note.md` | 문서 marker/hygiene check | 직접 설명 가능한 범위와 금지 주장 분리 |
| Provider fallback/live provider | 부분 검증 | `app/providers/factory.py`, `reports/completion-readiness/m1-live-provider-proof.json` (gitignored) | 승인된 live pytest + v2 receipt | OpenAI 통과; Gemini/Claude/fallback은 외부 quota/billing blocker |
| Production deployment | 검증 필요 | `Dockerfile`, `docker-compose.yml`, `infra/sam/template.yaml` | 설정 파일 근거만 확인 | 배포 실행 안 함 |
| 사용자 성과 수치 | 미구현/현재 없음 | 저장소 근거 없음 | 해당 없음 | 임의 생성 금지 |

## 3. 실행한 검증

### Targeted tests

```bash
DECISIONDOC_PROVIDER=mock \
DECISIONDOC_PROVIDER_GENERATION=mock \
DECISIONDOC_PROVIDER_ATTACHMENT=mock \
DECISIONDOC_PROVIDER_VISUAL=mock \
DECISIONDOC_STORAGE=local \
DATA_DIR="$PWD/evidence/runtime-data/test-data" \
EXPORT_DIR="$PWD/evidence/runtime-data/test-data" \
python -m pytest tests/test_generate.py tests/test_auth_api_key.py tests/test_storage.py -q
```

결과: `60 passed in 63.53s`.

### Full non-live gate

```bash
pytest tests/ -m "not live" -q
```

결과: `4212 passed, 2 skipped, 4 deselected, 1 warning` (2026-07-20 H74 실측, 외부 provider·G2B·Stripe key를 process에서 제거하고 provider capability를 mock으로 고정).

### CI advisory lint / security scan

```bash
ruff check app/ --select=E,F,W --ignore=E501
bandit -r app/ -x app/providers/mock_provider.py -ll
```

결과(2026-07-09 로컬 실측): `ruff`는 `All checks passed!`, `bandit -ll`은 `No issues identified`. `bandit -ll`은 medium/high severity 기준이며 low severity 항목 전체 해소를 의미하지 않는다.

### Local server

```bash
DECISIONDOC_PROVIDER=mock \
DECISIONDOC_PROVIDER_GENERATION=mock \
DECISIONDOC_PROVIDER_ATTACHMENT=mock \
DECISIONDOC_PROVIDER_VISUAL=mock \
DECISIONDOC_ENV=dev \
DECISIONDOC_API_KEYS=<local_mock_api_key> \
DECISIONDOC_API_KEY=<local_mock_api_key> \
DECISIONDOC_STORAGE=local \
DATA_DIR="$PWD/evidence/runtime-data/server-data" \
EXPORT_DIR="$PWD/evidence/runtime-data/server-data" \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

Captured API responses:

- `evidence/api-responses/health.json`
- `evidence/api-responses/version.json`
- `evidence/api-responses/bundles.json`
- `evidence/api-responses/generate-tech-decision.json`
- `evidence/api-responses/generate-export-tech-decision.json`

### Local procurement decision package contract

```bash
CONTRACT_RESULT=/tmp/decisiondoc-cli-contract-manifest-validation-result.json
python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py \
  --write-result \
  --result-path "$CONTRACT_RESULT"
python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py "$CONTRACT_RESULT"
```

이 명령은 `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`과 local evidence CLI stdout JSON success/failure contract를 확인한다. Provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않는다.

### Completion readiness receipt

```bash
python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
```

이 명령은 M1 live provider, M2 G2B live smoke, M6 deployment smoke의 실행 준비 조건을 확인한다. 2026-07-13 receipt에서 M1은 `ready_to_execute`, M2/M6는 입력 부족으로 `blocked`다. Readiness checker는 provider API, G2B live API, AWS runtime 또는 다른 외부 action을 실행하지 않는다.

### M1 live provider proof

```bash
DECISIONDOC_PROVIDER=openai python3 -m pytest -q tests/test_live_providers.py::test_live_openai_generate_ok -m live -rs
DECISIONDOC_PROVIDER=gemini python3 -m pytest -q tests/test_live_providers.py::test_live_gemini_generate_ok -m live -rs
DECISIONDOC_PROVIDER=claude python3 -m pytest -q tests/test_live_providers.py::test_live_claude_generate_ok -m live -rs
DECISIONDOC_PROVIDER=openai,gemini DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1 \
  python3 -m pytest -q tests/test_live_providers.py::test_live_openai_gemini_fallback_chain_ok -m live -rs
```

2026-07-13 결과: OpenAI는 `1 passed in 23.26s`. Gemini는 `gemini-2.5-pro`와 repo 기본 `gemini-2.0-flash` 모두 HTTP 429, Claude는 HTTP 400과 account credit balance 부족으로 blocked. Fallback은 OpenAI 강제 401 뒤 Gemini 호출까지 확인했으나 Gemini 429로 성공 assertion을 충족하지 못했다. `reports/completion-readiness/m1-live-provider-proof.json`은 `status: blocked`이며 v2 checker `ok: true`다. Secret은 receipt에 기록하지 않았다.

### Static PWA / CSP evidence

```bash
python3 -m pytest -q tests/test_pwa.py \
  tests/test_infrastructure.py::test_csp_nonce_enabled_by_default \
  tests/test_infrastructure.py::test_csp_root_has_nonce_and_matches_inline_scripts \
  tests/test_infrastructure.py::test_csp_nonce_differs_per_request
```

결과: `53 passed`. 추가로 `evidence/cli-logs/ui_csp_nonce_check.log`는 root HTML 응답의 `200 OK`, CSP nonce 존재, `script-src 'unsafe-inline'` 부재, inline handler 0개를 기록한다.

## 4. 검증 완료 기능

- FastAPI 앱이 mock provider/local storage 설정으로 로컬 실행됨.
- `/health`가 `status: ok`, `provider: mock`을 반환함.
- `/version`이 앱 버전, dev 환경, provider/storage 정보를 반환함.
- `/bundles`가 bundle catalog 목록을 반환함.
- `POST /generate`가 API key 인증 후 문서 bundle JSON을 반환함.
- `POST /generate/export`가 Markdown export 경로와 파일 목록을 반환하고 실제 Markdown 파일을 생성함.
- Web UI root가 로그인 화면으로 렌더링됨.
- Static PWA root가 CSP nonce 적용 상태로 렌더링되고 inline `on*=` handler가 남아 있지 않음.
- Procurement decision package local evidence contract manifest와 persisted receipt checker가 repo 밖 `/tmp` receipt 경로로 재현 가능함.
- Completion readiness receipt/checker가 M1/M2/M6의 남은 외부 입력을 secret 출력 없이 확인함.
- OpenAI provider가 승인된 live key로 실제 `/generate` bundle을 1회 생성하고 live test를 통과함.
- Contribution note가 포트폴리오/면접에서 설명 가능한 범위와 금지 주장을 분리함.

## 5. 검증 실패 기능

- 이번 evidence 수집 범위에서 실패로 확정된 구현 기능은 없음. Gemini HTTP 429와 Claude credit 부족은 외부 account 상태로 분류함.
- 참고: `/health`의 `provider_policy_checks.quality_first`는 mock provider 설정 때문에 `degraded`로 표시된다. 이는 portfolio evidence에서 local mock verification을 사용했기 때문이며, production provider policy는 별도 검증 필요 항목이다.

## 6. 미구현 / 검증 필요

- live Gemini/Claude provider 성공: API 호출은 도달했으나 각각 quota와 credit balance 때문에 성공 proof가 없음.
- live provider fallback chain: OpenAI 강제 실패 뒤 Gemini 전환 호출은 확인했으나 Gemini quota 때문에 성공 proof가 없음.
- 실제 production deployment: 배포하지 않음.
- live G2B/procurement provider flow: fixture 기반 local evidence contract 검증과 별도이며, 승인된 API key/credential 환경에서만 확인 가능.
- 사용자 성과 수치: 저장소 내 근거 없음.
- 로그인 이후 전체 UI workflow: 계정 생성/로그인 후 화면 전환은 이번 evidence 범위에서 수행하지 않음.
- 고객/기관 내부자료 기반 사례: 포함하지 않음.

## 7. 문서 생성 도구 우선 증거

| 증거 유형 | 파일 | 설명 |
|---|---|---|
| 입력 샘플 | `evidence/input-samples/generate-tech-decision-request.json` | `POST /generate` 요청 payload |
| 입력 샘플 | `evidence/input-samples/generate-export-request.json` | `POST /generate/export` 요청 payload |
| 입력 샘플 | `evidence/input-samples/upload-document-sample.txt` | 업로드 기반 생성 검증에 사용할 수 있는 비민감 샘플 문서 |
| 생성 결과 샘플 | `evidence/generated-samples/generated_adr.md` | `/generate` 응답에서 추출한 ADR Markdown |
| 생성 결과 샘플 | `evidence/generated-samples/generated_onepager.md` | `/generate` 응답에서 추출한 one-pager Markdown |
| 생성 결과 샘플 | `evidence/generated-samples/generated_eval_plan.md` | `/generate` 응답에서 추출한 eval plan Markdown |
| 생성 결과 샘플 | `evidence/generated-samples/generated_ops_checklist.md` | `/generate` 응답에서 추출한 ops checklist Markdown |
| Export 결과 샘플 | `evidence/generated-samples/exported_adr.md` | `/generate/export`가 생성한 Markdown export |
| Export 결과 샘플 | `evidence/generated-samples/exported_onepager.md` | `/generate/export`가 생성한 Markdown export |
| API 응답 | `evidence/api-responses/doc-evidence-generate.json` | 문서 생성 API 응답 |
| API 응답 | `evidence/api-responses/doc-evidence-generate-export.json` | export API 응답 |
| Swagger/OpenAPI | `evidence/swagger/openapi.json` | FastAPI OpenAPI schema |
| Swagger/OpenAPI | `evidence/swagger/swagger-ui.html` | FastAPI Swagger UI HTML |
| Swagger/OpenAPI | `evidence/swagger/openapi-summary.md` | 문서 생성 관련 endpoint 요약 |
| 실행 로그 | `evidence/execution-logs/document_generation_api_capture.log` | curl 기반 evidence capture 로그 |

Swagger UI screenshot은 이 환경에서 CDN 리소스 로딩 오류로 빈 화면이 되어 검증 증거에서 제외했다. 대신 `/openapi.json`, Swagger HTML, endpoint summary, 실행 로그를 Swagger/API 증거로 남겼다.

# DecisionDoc AI Contribution Note

기준일: 2026-07-20

이 문서는 DecisionDoc AI를 포트폴리오나 면접에서 설명할 때 사용할 수 있는 직접 구현 범위와 검증 범위를 정리한다. 제품 성과나 운영 상태를 과장하기 위한 문서가 아니라, 코드와 증거로 설명 가능한 범위를 좁히기 위한 문서다.

## 1. 한 문장 설명

DecisionDoc AI는 LLM이 만든 문서를 단발성 텍스트가 아니라 evidence, review, sign-off, export boundary가 붙은 decision package로 다루기 위한 FastAPI 기반 문서 운영 PoC/MVP다.

## 2. 직접 설명 가능한 구현 범위

| 영역 | 설명 가능한 내용 | 근거 |
|---|---|---|
| API application | FastAPI 앱 구조, route/service/storage/provider 경계, app state 기반 dependency wiring | `app/main.py`, `app/routers/`, `app/services/`, `app/storage/`, `app/providers/` |
| Document generation | requirements 입력을 bundle JSON으로 만들고, template rendering과 storage 저장을 거쳐 문서 산출물을 반환하는 흐름 | `app/services/generation_service/`, `app/templates/v1/`, `tests/test_generate.py` |
| Provider abstraction | mock/openai/gemini/claude/local provider를 factory와 capability route 뒤에 둔 구조 | `app/providers/`, `tests/test_live_providers.py` |
| Storage abstraction | local/S3 storage를 같은 interface 뒤에 두고 local path에서는 atomic write를 유지하는 구조 | `app/storage/`, `tests/test_storage.py` |
| Reusable template integrity | 사용자 문서 입력 템플릿을 tenant별 local/S3 JSONL에 저장하고 malformed state·duplicate key/identity를 덮어쓰지 않는다. Worker mutation은 conditional create/CAS 충돌마다 최신 state 위에 add/delete/use-count를 재적용하고 bounded private receipt로 불확실 commit을 조정하며, delete는 같은 ID로 재생성된 후속 record를 제거하지 않는다 | `app/storage/template_store.py`, `app/routers/templates.py`, `tests/test_template_store_integrity.py` |
| Generation history integrity | 생성 문서의 재열기·즐겨찾기·시각자료·지식 승격 이력을 tenant별 local/S3 JSONL에 저장하고 malformed state·duplicate key/identity를 덮어쓰지 않는다. Worker mutation은 conditional create/CAS로 add/delete/favorite/visual-asset/promotion 유실을 막고 bounded private receipt와 target identity read-back으로 불확실 commit을 조정한다 | `app/storage/history_store.py`, `app/routers/history.py`, `app/routers/generate/_shared.py`, `tests/test_history_store_integrity.py` |
| Project and approval state integrity | Project/approval record를 tenant별 local/S3 object에 결속하고 missing-state 무부작용, blank·invalid UTF-8·backend failure·owned schema/duplicate identity를 원본 보존 상태로 차단한다. 서로 다른 worker의 mutation은 conditional create/CAS 충돌 때 최신 state를 다시 검증해 project/document update 유실과 삭제 후 부활, approval create/comment/terminal overwrite를 방지한다. Project는 bounded mutation receipt로 commit 응답 유실 뒤의 후속 CAS도 조정한다 | `app/storage/project_store.py`, `app/storage/project_state_mutation.py`, `app/storage/approval_store.py`, `tests/test_project_approval_store_integrity.py` |
| Report workflow state integrity | Planning·slide·visual asset·approval·promotion state를 tenant별 local/S3 object에 결속하고 blank·invalid UTF-8·backend failure·workflow/nested identity drift를 원본 보존 상태로 차단한다. Worker mutation은 conditional create/CAS 충돌마다 최신 state와 transition을 재검증해 update 유실과 상충하는 최종 결정을 방지하고, bounded private receipt로 commit 응답 유실 뒤의 후속 CAS도 조정한다 | `app/storage/report_workflow/`, `tests/test_report_workflow_store_integrity.py` |
| Audit evidence integrity | Tenant별 append-only JSONL의 기존 byte prefix를 보존하고 malformed·foreign·duplicate evidence를 fail closed 처리한다. Worker append는 conditional create/CAS 충돌마다 최신 JSONL을 다시 검증하며, `log_id`와 exact entry read-back으로 commit 응답 유실 뒤 successor append도 조정한다 | `app/storage/audit_store.py`, `app/storage/state_backend.py`, `tests/test_audit_store_integrity.py`, `tests/test_audit.py` |
| Collaboration state integrity | Tenant별 message·notification object의 손상·foreign·duplicate identity를 fail closed 처리하고 worker mutation을 conditional create/CAS로 확정한다. Bounded private receipt와 hard-delete target read-back으로 commit 응답 유실 뒤 successor update도 조정하며 public API에는 receipt를 노출하지 않는다 | `app/storage/message_store.py`, `app/storage/notification_store.py`, `app/storage/state_backend.py`, `tests/test_collaboration_store_integrity.py`, `tests/test_notifications.py` |
| Account and invitation state integrity | Tenant별 user·invite object의 손상·foreign·duplicate identity를 fail closed 처리하고 worker mutation을 conditional create/CAS로 확정한다. Empty-tenant first-admin precondition과 invite claim을 mutation 안에서 처리하며 bounded private receipt로 commit 응답 유실 뒤 successor update도 조정한다 | `app/storage/user_store.py`, `app/storage/invite_store.py`, `app/routers/auth.py`, `app/routers/admin/_invite.py`, `tests/test_identity_store_integrity.py`, `tests/test_phase_final.py` |
| Meeting recording integrity | 녹음 metadata와 audio digest·크기를 tenant/project/recording 경로에 결속하고 malformed state·identity drift·UUID 충돌·audio 변조를 원본 보존 상태로 차단한다. Recording별 metadata mutation은 conditional create/CAS와 bounded private receipt로 worker 간 전사·승인 유실 및 불확실 commit을 조정하고, audio는 정확히 같은 orphan bytes만 재사용한다 | `app/storage/meeting_recording_models.py`, `app/storage/meeting_recording_store.py`, `app/services/meeting_recording_service.py`, `tests/test_meeting_recording_store_integrity.py` |
| Billing authority integrity | tenant별 plan·status·Stripe identity를 local/S3 state에 결속하고 malformed state·unknown value를 원본 보존 상태로 차단한다. Worker mutation은 conditional create/CAS 충돌마다 최신 account 위에 변경을 재적용하고 bounded private receipt로 불확실 commit을 조정한다. Tenant/auth resolution 뒤 metered request 한도를 적용하고 checkout은 환경별 recurring Price ID와 subscription metadata를 사용한다 | `app/storage/billing_store.py`, `app/middleware/billing.py`, `app/routers/billing.py`, `app/services/billing_service.py`, `tests/test_billing_store_integrity.py`, `tests/test_billing_store_cas.py` |
| Style profile integrity | tenant별 tone guide·bundle override·분석 예시·default/system metadata를 local/S3 state에 결속하고 malformed state·schema/identity drift·multiple default를 덮어쓰지 않으며 독립 store의 process-local 동시 변경을 보존하는 구조 | `app/storage/style_store.py`, `app/routers/styles.py`, `app/domain/schema.py`, `tests/test_style_store_integrity.py` |
| SSO configuration integrity | tenant별 LDAP·SAML·GCloud·OAuth2 설정과 암호화된 secret을 local/S3 state에 결속하고 malformed state·unknown provider·foreign ownership·복호화 실패를 원본 보존 상태로 차단하는 구조. SAML은 signed assertion과 RelayState를 요구하며 verifier가 없으면 fail closed | `app/storage/sso_store.py`, `app/routers/sso.py`, `app/services/sso/saml_auth.py`, `tests/test_sso_store_integrity.py` |
| Quality learning and experiment integrity | tenant별 feedback·eval evidence·runtime prompt override·A/B experiment·request pattern을 local/S3 state에 결속하고 malformed state·duplicate key/identity·owned schema drift를 원본 보존 상태로 차단한다. Feedback/eval append는 JSONL byte prefix와 public 계약을 유지하면서 stable identity 기반 conditional CAS로 worker 유실과 불확실 commit 중복을 막는다. Prompt override refresh는 payload-bound receipt와 stable incarnation으로 applied count를 보존하고, A/B variant·hint·experiment identity와 result를 같은 CAS lifecycle에 결속한다. Pending winner는 persisted result와 receipt에 맞을 때만 재개하며 request clear는 후속 append를 보존한다 | `app/storage/feedback_store.py`, `app/eval/eval_store.py`, `app/storage/conditional_state.py`, `app/storage/prompt_override_store.py`, `app/storage/ab_test_store.py`, `app/storage/ab_test_conclusion.py`, `app/storage/request_pattern_store.py`, `app/domain/schema.py`, `tests/test_quality_learning_store_integrity.py`, `tests/test_quality_experiment_state_integrity.py` |
| Public share integrity | 공개 share link의 tenant ownership, 만료·접근 횟수·취소 lifecycle을 local/S3 state에 결속하고 malformed state와 identity drift를 덮어쓰지 않는다. Worker mutation은 conditional create/CAS로 create/access/revoke 유실을 막고 bounded private receipt로 불확실 commit을 조정하며 최초 취소 증거를 보존한다 | `app/storage/share_store.py`, `app/routers/history.py`, `tests/test_share_store_integrity.py` |
| Export surfaces | Markdown, DOCX, PDF, PPTX, HWP, Excel 계열 export와 local artifact 경로 | `app/services/*_service.py`, `app/routers/generate/export.py` |
| Procurement decision package | local fixture 기반 procurement decision package, CLI contract manifest, persisted receipt checker | `docs/samples/procurement_decision_package_local_demo/`, `scripts/validate_procurement_decision_package_cli_contract_manifest.py` |
| Procurement review lifecycle | tenant/project/packet SHA-256에 묶인 review record·packet·content-addressed reviewed-package를 selected local/S3 backend에서 fail closed로 검증하고, conditional create/CAS와 read-back reconciliation으로 단일 authority를 확정하며 검토함·downstream freshness·share/approval drift acknowledgement를 운영 실행 권한과 분리 | `app/storage/procurement_review_store.py`, `app/storage/state_backend.py`, `app/services/procurement_review_evidence.py`, `app/routers/projects/procurement_reviews.py`, `tests/test_procurement_review_store.py` |
| DocumentOps review operations | tenant-scoped trajectory를 summary-first로 탐색하고 선택 상세만 불러온 뒤 사람 점수와 메모를 기록하며, 상세 열람·review 결정은 입력·초안·메모를 제외한 append-only audit으로 추적한다. Governance review overview는 training governance, selected-backend artifact inventory, reviewer sign-off를 독립적으로 읽어 경계·무결성·blocker·sign-off 우선순위와 다음 검토 행동을 보여준다. Export·freeze·dry-run approval·execution request·audit 저장 또는 planning provider/model 변경 뒤에는 기존 overview를 이전 관측으로 낮추고, 성공한 새 조회에서만 fresh 상태를 복구한다. Trajectory Stats, task-filtered Reviewed SFT export 목록, Training Readiness는 same-tenant request version으로 이전 success/error를 폐기해 최신 count, artifact 목록, freeze 승인 대상만 유지한다. Governance 조회와 sign-off handoff 다운로드도 별도 action/resource로 추적하지만 audit detail에는 surface·aggregate status·read-only 여부만 남기고 fingerprint·source report·reviewer record를 복사하지 않는다. 합성 snapshot은 atomic이 아니며 cleanup이나 외부 실행 action을 제공하지 않는다 | `app/routers/document_ops_agent.py`, `app/services/document_ops_service.py`, `app/services/document_ops_governance.py`, `app/storage/trajectory/artifact_inventory_mixin.py`, `app/static/index.html`, `app/middleware/audit.py`, `app/middleware/document_ops_audit.py`, `tests/storage/test_trajectory_artifact_authority.py`, `tests/test_document_ops_governance.py`, `tests/test_document_ops_agent_api.py`, `tests/e2e/test_main_flow.py` |
| Report quality pilot review | 같은 tenant의 ready correction artifact 3~5개를 검증 가능한 ZIP으로 handoff하고, 교정 전후 evidence·validation blocker·required action과 사람의 결정을 잇는 source-bound browser workspace를 준비한다. 수신자는 같은 UI에서 ZIP을 선택해 브라우저와 서버 SHA-256을 대조하고, 서버 저장 없이 tenant·membership·entry hash·receipt·권한 경계를 확인할 수 있다. Decision template과 SHA 기반 browser-draft 보관본은 write-once publication으로 먼저 존재한 파일을 보존하며, 내려받은 draft 검증·보관·draft 반영·application receipt를 한 명령으로 연결한다. Finalize는 current manifest와 accepted decision receipt를 확인하는 ready sync를 private temporary JSONL로 실행하고 최종 draft·검수·source evidence를 deterministic handoff ZIP에 묶은 뒤 중간 파일을 삭제한다. Handoff v2는 evidence-bound Markdown과 script-free HTML summary를 함께 제공하고 verifier가 두 파일을 exact bytes로 재검증한 뒤 선택한 한 형식만 write-once로 추출한다. Mock-only full-chain demo는 3-artifact wiring을 simulated review로 재현하되 실제 사람 검수 완료를 주장하지 않는 write-once receipt를 남기고, read-only checker가 receipt drift와 권한 경계를 다시 검사한다. | `app/routers/report_workflows.py`, `app/routers/_report_workflow_quality.py`, `app/services/report_quality_pilot_package.py`, `scripts/create_report_quality_pilot_pack.py`, `scripts/create_report_quality_review_sheet.py`, `scripts/create_report_quality_review_workspace.py`, `scripts/apply_report_quality_review_decisions.py`, `scripts/sync_report_quality_pilot_pack.py`, `scripts/manage_report_quality_pilot_handoff.py`, `scripts/report_quality_pilot_handoff_summary.py`, `scripts/run_report_quality_pilot_handoff_demo.py`, `scripts/check_report_quality_pilot_handoff_demo_receipt.py`, `scripts/local_write_once.py`, `tests/test_report_workflows_api.py`, `tests/test_report_quality_pilot_package.py`, `tests/test_apply_report_quality_review_decisions.py`, `tests/test_manage_report_quality_pilot_handoff.py`, `tests/test_run_report_quality_pilot_handoff_demo.py`, `tests/test_check_report_quality_pilot_handoff_demo_receipt.py`, `tests/test_local_write_once.py`, `tests/test_sync_report_quality_pilot_pack.py` |
| Review and approval boundary | approval, sign-off, handoff는 운영 실행 승인과 분리한다는 구조 | `app/routers/approvals.py`, `docs/product_direction.md`, `docs/product_execution_plan.md` |
| CSP and static PWA hardening | inline handler 제거, per-request CSP nonce, static PWA root rendering evidence | `app/middleware/security_headers.py`, `app/static/index.html`, `tests/test_pwa.py`, `evidence/cli-logs/ui_csp_nonce_check.log` |
| Completion readiness / proof receipt | live provider, G2B live smoke, deployment smoke를 실행 전 readiness와 실행 후 no-secret proof receipt로 분리. M2/M6 runner는 preflight와 실제 pass/fail receipt를 직접 atomic 기록 | `scripts/check_completion_readiness.py`, `scripts/check_completion_readiness_result.py`, `scripts/check_completion_proof_receipt.py`, `scripts/run_stage_procurement_smoke.py`, `scripts/run_deployed_smoke.py` |
| Source-backed README metrics | route/test/env 수치를 AST와 source parser로 재계산해 README drift를 줄이는 검증 경로 | `scripts/count_readme_metrics.py`, `tests/test_count_readme_metrics.py` |
| Portfolio evidence pack | tracked 문서/evidence allowlist를 source와 byte 단위로 동기화하고 SHA-256 manifest와 deterministic ZIP을 검증 | `scripts/manage_portfolio_pack.py`, `tests/test_manage_portfolio_pack.py`, `portfolio_manifest.md` |

Report Quality receiver inspection은 ZIP 무결성만 확인하지 않는다. 기존 correction artifact validator를 다시 실행해 schema, scan, 점수, 사람 검토와 learning-ready 조건을 확인하고, 통과한 artifact의 reviewer·score·교정 전후 기획·claim 구분·change request와 다음 검토 행동을 raw JSON 없이 보여준다. Package와 workflow record는 저장하지 않으며 semantic gate 결과는 audit evidence에 남는다.

## 3. 검증된 범위

현재 로컬에서 증거로 말할 수 있는 범위는 다음과 같다.

| 검증 | 현재 증거 |
|---|---|
| Non-live pytest gate | 외부 provider·G2B·Stripe key를 process에서 제거하고 provider capability를 mock으로 고정한 `pytest tests/ -m "not live" -q` -> `4229 passed, 2 skipped, 4 deselected, 1 warning` (2026-07-21 H83 실측) |
| GitHub Actions CI | 마지막으로 확인한 main 자동화 증적: commit `5c7813c`, CI `29766346149` success (`4228 passed, 5 skipped`) |
| GitHub Actions CD | 마지막으로 확인한 main 자동화 증적: commit `5c7813c`, CD `29766346150` success. image digest는 `sha256:5ea5675f00d08e5808710635983b2434db053ff8d0fbdf78bd48f259f2c9095e`이며 staging deploy/smoke와 production deploy는 skip되어 M6 proof로 보지 않는다 |
| README metric count | `python3 scripts/count_readme_metrics.py --json` |
| Completion readiness receipt | `python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json` |
| Completion receipt contract | `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json` |
| Completion proof receipt contract | M1은 `--print-template M1`을 실제 결과로 채우고, M2/M6는 runner `--proof-receipt`로 생성한 receipt를 `check_completion_proof_receipt.py <receipt>`로 검증 |
| Completion proof runbook | `docs/completion-readiness-runbook.md` |
| Static PWA screenshot | `evidence/screenshots/web-ui-home.png` |
| Static PWA CSP boundary | `evidence/cli-logs/ui_csp_nonce_check.log` |
| Playwright console check | `evidence/cli-logs/playwright_console.log` |
| Post-login UI flow | `python3 scripts/capture_ui_flow_evidence.py` -> `evidence/cli-logs/ui_flow_evidence.json`, `evidence/screenshots/ui-flow-01-after-login.png`, `evidence/screenshots/ui-flow-02-generate-ready.png`, `evidence/screenshots/ui-flow-03-results.png`, `evidence/screenshots/ui-flow-04-export-complete.png` |
| Portfolio pack integrity | `python3 scripts/manage_portfolio_pack.py sync --prune`, `check`, `package`, `verify-zip` |

## 4. 아직 설명하면 안 되는 범위

아래 항목은 코드나 준비 경로가 있어도 현재 완료로 말하면 안 된다.

| 항목 | 이유 | 필요한 증거 |
|---|---|---|
| OpenAI/Gemini/Claude live provider 전체 완료 | OpenAI 1회 proof만 존재하며 Gemini/Claude와 성공 fallback proof는 비용·quota 의존으로 보류했다 | 잔여 provider별 `pytest -m live` 통과 로그 |
| OpenAI -> Gemini fallback 실증 완료 | fallback test path는 있으나 live fallback 호출 증거가 없다 | `test_live_openai_gemini_fallback_chain_ok` 실행 로그 |
| G2B 실데이터 end-to-end 완료 | `G2B_API_KEY`, stage URL/API key가 필요하다 | `scripts/run_stage_procurement_smoke.py` 실행 receipt |
| 운영 배포 완료 | `.env.prod`, runtime URL, post-deploy smoke 증거가 필요하다 | `scripts/run_deployed_smoke.py`, `scripts/ops_smoke.py` 결과 |
| 실제 입찰 제출, 법적 승인, 계약 확약 | 제품 boundary 밖이며 현재 로컬 evidence는 이를 실행하지 않는다 | 별도 승인/법무/운영 절차 |
| 사용자 성과 수치 | 측정 데이터가 없다 | 수집 방법과 원자료가 있는 metric evidence |
| production readiness | 현재 README는 MVP/PoC로 제한한다 | 운영 URL, SLO, incident/runbook, deployed smoke evidence |

## 5. 면접에서 안전한 설명 방식

다음처럼 말할 수 있다.

```text
DecisionDoc AI에서는 문서 생성 자체보다 생성 결과가 검토 가능한 decision package가 되도록 구조를 잡았습니다.
FastAPI route는 얇게 두고, provider와 storage를 factory 뒤로 분리했습니다.
mock provider와 local storage를 기본 경로로 유지해서 외부 비용 없이 regression test를 돌릴 수 있게 했고,
live provider, G2B, deployment는 readiness checker로 분리해 secret이나 외부 호출 없이 필요한 입력값을 먼저 확인하게 했습니다.
```

다음 표현은 피한다.

```text
실제 운영 환경에서 검증됐다고 말한다.
실제 고객 성과를 냈습니다.
provider fallback은 실제 운영 환경에서 검증됐습니다.
G2B 실데이터 end-to-end가 완료됐습니다.
입찰 제출이나 법적 승인을 자동화합니다.
```

## 6. 다음 증거 순서

비용이 발생하는 provider proof는 사용자 요청에 따라 보류한다. 외부 실증을 재개할 때는 아래 순서로 증거를 확보한다.

1. M1 live provider validation note
2. M2 G2B stage smoke receipt
3. M6 deployment and post-deploy smoke report
4. 필요 시 짧은 UI recording

위 작업은 API key, stage credential, runtime environment, 비용 또는 외부 시스템 접근이 필요하므로 readiness checker 결과와 [completion-readiness-runbook.md](./completion-readiness-runbook.md)를 먼저 확인한 뒤 진행한다.

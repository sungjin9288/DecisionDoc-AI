# DecisionDoc AI Contribution Note

기준일: 2026-07-14

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
| Export surfaces | Markdown, DOCX, PDF, PPTX, HWP, Excel 계열 export와 local artifact 경로 | `app/services/*_service.py`, `app/routers/generate/export.py` |
| Procurement decision package | local fixture 기반 procurement decision package, CLI contract manifest, persisted receipt checker | `docs/samples/procurement_decision_package_local_demo/`, `scripts/validate_procurement_decision_package_cli_contract_manifest.py` |
| Procurement review lifecycle | tenant/project에 묶인 review packet과 receipt, 검토함, downstream freshness, share/approval drift acknowledgement를 운영 실행 권한과 분리 | `app/routers/projects/procurement_reviews.py`, `app/routers/history.py`, `app/routers/approvals.py`, `tests/test_procurement_review_inbox_api.py` |
| Review and approval boundary | approval, sign-off, handoff는 운영 실행 승인과 분리한다는 구조 | `app/routers/approvals.py`, `docs/product_direction.md`, `docs/product_execution_plan.md` |
| CSP and static PWA hardening | inline handler 제거, per-request CSP nonce, static PWA root rendering evidence | `app/middleware/security_headers.py`, `app/static/index.html`, `tests/test_pwa.py`, `evidence/cli-logs/ui_csp_nonce_check.log` |
| Completion readiness / proof receipt | live provider, G2B live smoke, deployment smoke를 실행 전 readiness와 실행 후 no-secret proof receipt로 분리. M2/M6 runner는 preflight와 실제 pass/fail receipt를 직접 atomic 기록 | `scripts/check_completion_readiness.py`, `scripts/check_completion_readiness_result.py`, `scripts/check_completion_proof_receipt.py`, `scripts/run_stage_procurement_smoke.py`, `scripts/run_deployed_smoke.py` |
| Source-backed README metrics | route/test/env 수치를 AST와 source parser로 재계산해 README drift를 줄이는 검증 경로 | `scripts/count_readme_metrics.py`, `tests/test_count_readme_metrics.py` |
| Portfolio evidence pack | tracked 문서/evidence allowlist를 source와 byte 단위로 동기화하고 SHA-256 manifest와 deterministic ZIP을 검증 | `scripts/manage_portfolio_pack.py`, `tests/test_manage_portfolio_pack.py`, `portfolio_manifest.md` |

## 3. 검증된 범위

현재 로컬에서 증거로 말할 수 있는 범위는 다음과 같다.

| 검증 | 현재 증거 |
|---|---|
| Non-live pytest gate | `pytest -q tests/ -m "not live" --tb=short` -> 2026-07-14 실측 결과는 README와 roadmap에 동일하게 기록 |
| GitHub Actions CI | 최근 확인한 main 자동화 증적: commit `01b9fbc`, CI `29027090095` success |
| GitHub Actions CD | 최근 확인한 main 자동화 증적: commit `01b9fbc`, CD `29027088935` success. staging deploy/smoke는 설정 부재로 skip되어 M6 proof로 보지 않는다 |
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
| 실제 OpenAI/Gemini/Claude live provider 완료 | API key와 비용이 필요한 live test를 아직 실행하지 않았다 | provider별 `pytest -m live` 통과 로그 |
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

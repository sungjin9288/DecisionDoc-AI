# Evidence Gallery

## 1. Screenshots

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/screenshots/web-ui-home.png` | 로컬 FastAPI static PWA root 화면. 2026-07-08 기준 로그인 폼 렌더링 확인 | 검증 완료 |

## 2. API Responses

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/api-responses/health.json` | `/health` 응답. mock provider/local storage 상태 확인 | 검증 완료 |
| `evidence/api-responses/version.json` | `/version` 응답. 앱 버전, provider, storage, feature flags 확인 | 검증 완료 |
| `evidence/api-responses/bundles.json` | `/bundles` 응답. bundle catalog 노출 확인 | 검증 완료 |
| `evidence/api-responses/generate-tech-decision.json` | `POST /generate` 응답. 문서 bundle 생성 확인 | 검증 완료 |
| `evidence/api-responses/generate-export-tech-decision.json` | `POST /generate/export` 응답. export_dir/files 반환 확인 | 검증 완료 |
| `evidence/api-responses/doc-evidence-generate.json` | 입력 샘플 기반 `POST /generate` 응답 | 검증 완료 |
| `evidence/api-responses/doc-evidence-generate-export.json` | 입력 샘플 기반 `POST /generate/export` 응답 | 검증 완료 |

## 3. CLI Logs

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/cli-logs/pytest_generate_auth_storage.log` | generation/auth/storage targeted pytest 결과 | 검증 완료 |
| `evidence/cli-logs/api_capture.exitcodes` | curl response capture exit code 기록 | 검증 완료 |
| `evidence/cli-logs/playwright_open.log` | Playwright UI open/resize 실행 로그 | 검증 완료 |
| `evidence/cli-logs/playwright_snapshot.log` | Playwright accessibility snapshot 로그 | 검증 완료 |
| `evidence/cli-logs/playwright_screenshot.log` | Playwright screenshot 저장 로그 | 검증 완료 |
| `evidence/cli-logs/playwright_console.log` | Playwright console warning/error 확인 로그. warning 이상 0건 | 검증 완료 |
| `evidence/cli-logs/playwright_requests.log` | Playwright network request 확인 로그 | 검증 완료 |
| `evidence/cli-logs/ui_csp_nonce_check.log` | 로컬 UI 응답의 CSP nonce, `unsafe-inline` 부재, inline handler 0개 확인 로그 | 검증 완료 |

## 3-1. Reproducible Local Evidence Commands

| 항목 | 설명 | 상태 |
|---|---|---|
| `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json` | Procurement decision package local evidence CLI stdout JSON contract manifest. `contract_version` 기준으로 success/failure field를 고정 | 재현 가능 |
| `scripts/validate_procurement_decision_package_cli_contract_manifest.py --write-result --result-path /tmp/decisiondoc-cli-contract-manifest-validation-result.json` | manifest validation receipt를 repo 밖 `/tmp` 경로에 기록 | 재현 가능 |
| `scripts/check_procurement_decision_package_cli_contract_manifest_result.py /tmp/decisiondoc-cli-contract-manifest-validation-result.json` | persisted receipt가 현재 manifest와 일치하는지 확인 | 재현 가능 |
| `python3 scripts/check_completion_readiness.py --print-env-template` | M1/M2/M6 readiness 입력값만 env parser가 읽을 수 있는 형태로 출력. secret 값 없음 | 재현 가능 |
| `python3 scripts/check_completion_readiness.py --print-proof-plan` | readiness receipt와 M1/M2/M6 no-secret proof receipt 생성·검증 명령을 실행 없이 출력 | 재현 가능 |
| `python3 scripts/check_completion_readiness.py --env-file .env.prod` | gitignore된 env file에서 M1/M2/M6 readiness 입력값을 읽어 점검. secret 값은 출력하지 않음 | 재현 가능 |
| `python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json` | gitignore된 env file에서 M1/M2/M6 readiness 입력값을 읽고, 실행 준비 조건을 gitignore된 `reports/` 경로에 JSON receipt로 기록. 외부 호출 없음 | 재현 가능 |
| `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json` | completion readiness JSON receipt가 현재 schema, milestone order, command list, excluded action contract와 일치하는지 확인 | 재현 가능 |
| `python3 scripts/check_completion_proof_receipt.py --print-template M1` | 실제 proof 이후 채울 no-secret proof receipt template 출력. placeholder가 남아 있으면 checker가 거부 | 재현 가능 |
| `python3 scripts/run_report_quality_pilot_handoff_demo.py --output /tmp/decisiondoc-report-quality-pilot-handoff-demo.json` | mock API의 3-artifact package부터 simulated local review, final handoff, exact HTML 검증까지 temporary storage에서 실행하고 `human_review_claimed=false` write-once receipt만 남김 | 재현 가능 |
| `python3 scripts/run_stage_procurement_smoke.py --preflight --proof-receipt <path>` | M2 preflight를 외부 미실행 `blocked` receipt로 atomic 기록. 실제 smoke는 같은 옵션으로 pass/fail과 안전한 host/target evidence를 기록 | 재현 가능 |
| `python3 scripts/run_deployed_smoke.py --preflight --proof-receipt <path>` | M6 preflight를 외부 미실행 `blocked` receipt로 atomic 기록. 실제 smoke는 같은 옵션으로 pass/fail과 안전한 runtime host evidence를 기록 | 재현 가능 |
| `python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m1-live-provider-proof.json` | v2 proof receipt의 command, timestamp, evidence refs, secret boundary, milestone별 미실행 action 계약 확인. checker 자체는 외부 호출 없음 | 재현 가능 |
| `docs/completion-readiness-runbook.md` | M1/M2/M6 proof 실행 전후 순서, 중단 기준, 문서 갱신 순서를 고정한 runbook | 재현 가능 |

이 섹션은 파일이 `evidence/` package 안에 저장됐다고 주장하지 않는다. 필요할 때 위 명령으로 local-only receipt를 다시 생성한다.

## 3-2. M1 Live Provider Proof (2026-07-13)

| 실행 | 결과 | 증적 |
|---|---|---|
| OpenAI `/generate` live test | `1 passed in 23.26s` | `reports/completion-readiness/m1-openai-junit.xml` (gitignored local receipt) |
| Gemini `/generate` live test | `gemini-2.5-pro`, `gemini-2.0-flash` 모두 API HTTP 429로 blocked | `reports/completion-readiness/m1-gemini-2.5-pro-quota-failure-junit.xml`, `m1-gemini-junit.xml` |
| Claude `/generate` live test | API HTTP 400. no-secret 진단에서 account credit balance 부족 확인 | `reports/completion-readiness/m1-claude-junit.xml` |
| OpenAI -> Gemini fallback live test | OpenAI 강제 401 뒤 Gemini 호출 확인. Gemini HTTP 429로 성공 assertion은 미달 | `reports/completion-readiness/m1-fallback-junit.xml` |
| M1 no-secret receipt | `status: blocked`, v2 checker `ok: true` | `reports/completion-readiness/m1-live-provider-proof.json`, `m1-live-provider-proof-check.json` |

M1 DoD는 아직 충족하지 않았다. Gemini quota/billing과 Anthropic credits를 복구한 뒤 Gemini, Claude, fallback test를 다시 통과해야 한다. G2B live API, AWS runtime, dataset upload, training, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않았다.

## 3-3. Portfolio / Interview Boundary

| 파일 | 설명 | 상태 |
|---|---|---|
| `docs/contribution-note.md` | 직접 설명 가능한 구현 범위, 검증된 범위, 아직 말하면 안 되는 범위를 구분한 포트폴리오/면접용 boundary note | 생성 완료 |
| `docs/completion-readiness-runbook.md` | live provider, G2B stage smoke, deployed smoke 증적 실행 경계를 정리한 completion runbook | 생성 완료 |

## 4. Output Artifacts

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/output-artifacts/export_adr.md` | `/generate/export`로 생성된 ADR Markdown export | 검증 완료 |
| `evidence/output-artifacts/export_onepager.md` | `/generate/export`로 생성된 One-pager Markdown export | 검증 완료 |

## 5. Input Samples

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/input-samples/generate-tech-decision-request.json` | 문서 생성 API 요청 샘플 | 생성 완료 |
| `evidence/input-samples/generate-export-request.json` | 문서 export API 요청 샘플 | 생성 완료 |
| `evidence/input-samples/upload-document-sample.txt` | 비민감 업로드 문서 샘플 | 생성 완료 |

## 6. Generated Samples

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/generated-samples/generated_adr.md` | `POST /generate` 생성 결과 | 검증 완료 |
| `evidence/generated-samples/generated_onepager.md` | `POST /generate` 생성 결과 | 검증 완료 |
| `evidence/generated-samples/generated_eval_plan.md` | `POST /generate` 생성 결과 | 검증 완료 |
| `evidence/generated-samples/generated_ops_checklist.md` | `POST /generate` 생성 결과 | 검증 완료 |
| `evidence/generated-samples/exported_adr.md` | `POST /generate/export` 산출물 | 검증 완료 |
| `evidence/generated-samples/exported_onepager.md` | `POST /generate/export` 산출물 | 검증 완료 |

## 7. Swagger / OpenAPI

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/swagger/openapi.json` | FastAPI OpenAPI schema | 검증 완료 |
| `evidence/swagger/swagger-ui.html` | FastAPI Swagger UI HTML | 검증 완료 |
| `evidence/swagger/openapi-summary.md` | 문서 생성 관련 endpoint 요약 | 검증 완료 |

## 8. Architecture

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/architecture/system-architecture.md` | 현재 구현 기준 Mermaid architecture diagram | 생성 완료 |
| `evidence/architecture/generation-sequence.md` | `/generate` 처리 흐름 Mermaid sequence diagram | 생성 완료 |

# Evidence Checklist

## 1. 검증 완료

| 체크 항목 | 상태 | 증거 |
|---|---|---|
| 프로젝트 루트 확인 | 완료 | `<repo_root>` |
| 테스트 실행 | 완료 | `evidence/cli-logs/pytest_generate_auth_storage.log` |
| 로컬 서버 실행 | 완료 | `http://127.0.0.1:8787` |
| Health API 응답 저장 | 완료 | `evidence/api-responses/health.json` |
| Version API 응답 저장 | 완료 | `evidence/api-responses/version.json` |
| Bundle catalog 응답 저장 | 완료 | `evidence/api-responses/bundles.json` |
| Generate API 응답 저장 | 완료 | `evidence/api-responses/generate-tech-decision.json` |
| Export API 응답 저장 | 완료 | `evidence/api-responses/generate-export-tech-decision.json` |
| Export 산출물 저장 | 완료 | `evidence/output-artifacts/export_adr.md`, `evidence/output-artifacts/export_onepager.md` |
| UI screenshot 저장 | 완료 | `evidence/screenshots/web-ui-home.png` |
| Architecture diagram 생성 | 완료 | `evidence/architecture/system-architecture.md` |
| Sequence diagram 생성 | 완료 | `evidence/architecture/generation-sequence.md` |
| 입력 샘플 저장 | 완료 | `evidence/input-samples/` |
| 생성 결과 샘플 저장 | 완료 | `evidence/generated-samples/` |
| Swagger/OpenAPI 저장 | 완료 | `evidence/swagger/openapi.json`, `evidence/swagger/swagger-ui.html`, `evidence/swagger/openapi-summary.md` |
| 문서 생성 API 실행 로그 저장 | 완료 | `evidence/execution-logs/document_generation_api_capture.log` |
| 최신 static PWA screenshot 갱신 | 완료 | `evidence/screenshots/web-ui-home.png` |
| Static PWA CSP nonce 확인 | 완료 | `evidence/cli-logs/ui_csp_nonce_check.log` |
| Static PWA console warning/error 확인 | 완료 | `evidence/cli-logs/playwright_console.log` |
| 로그인 이후 전체 UI flow | 완료 | `python3 scripts/capture_ui_flow_evidence.py` -> `evidence/cli-logs/ui_flow_evidence.json`, `evidence/screenshots/ui-flow-01-after-login.png`, `evidence/screenshots/ui-flow-02-generate-ready.png`, `evidence/screenshots/ui-flow-03-results.png`, `evidence/screenshots/ui-flow-04-export-complete.png` |
| Non-live 전체 pytest gate | 완료 | `pytest tests/ -m "not live" -q` -> `2803 passed, 2 skipped, 4 deselected` |
| GitHub Actions CI | 완료 | main `1cf75b8`, CI `28958935201` success |
| GitHub Actions CD | 완료 | main `1cf75b8`, CD `28958935333` success. staging deploy/smoke는 설정 부재로 skip되어 배포 proof에서 제외 |
| 직접 구현/설명 가능 범위 정리 | 완료 | `docs/contribution-note.md` |

## 1-1. 재현 가능한 Local Evidence Contract

| 체크 항목 | 상태 | 증거 / 재현 명령 |
|---|---|---|
| Procurement decision package CLI contract manifest | 재현 가능 | `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version` |
| Manifest validation receipt | 재현 가능 | `python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py --write-result --result-path /tmp/decisiondoc-cli-contract-manifest-validation-result.json` |
| Persisted receipt checker | 재현 가능 | `python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py /tmp/decisiondoc-cli-contract-manifest-validation-result.json` |
| Completion readiness env template | 재현 가능 | `python3 scripts/check_completion_readiness.py --print-env-template` |
| Completion readiness local receipt | 재현 가능 | `python3 scripts/check_completion_readiness.py --json --output reports/completion-readiness/latest.json` |
| Completion readiness receipt checker | 재현 가능 | `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json` |
| Completion proof receipt template/checker | 재현 가능 | `python3 scripts/check_completion_proof_receipt.py --print-template M1`, `python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m1-live-provider-proof.json` |
| Completion readiness proof runbook | 재현 가능 | `docs/completion-readiness-runbook.md` |
| Local post-login UI flow evidence | 재현 가능 | `python3 scripts/capture_ui_flow_evidence.py` |

위 local evidence contract 검증은 repo 밖 `/tmp` receipt를 사용한다. Provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않는다.

Completion readiness/proof receipt는 gitignored `reports/completion-readiness/` 경로를 사용한다. 이 검증도 readiness와 proof receipt 계약만 확인하며 provider API, G2B live API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않는다.

## 2. 검증 실패

| 체크 항목 | 상태 | 사유 |
|---|---|---|
| 실패로 확정된 구현 기능 | 없음 | 이번 수집 범위의 테스트/API/UI screenshot은 성공 |

## 3. 검증 필요

| 체크 항목 | 상태 | 필요한 후속 작업 |
|---|---|---|
| Live provider 호출 | 검증 필요 | 실제 API key가 있는 별도 안전 환경에서 live smoke 실행 |
| Live provider fallback chain | 검증 필요 | `DECISIONDOC_PROVIDER=openai,gemini`와 승인된 provider key로 fallback live test 실행 |
| Production deployment | 검증 필요 | 배포 URL, post-deploy smoke log, 운영 접근성 확인 |
| Swagger UI 브라우저 렌더링 | 검증 필요 | 로컬 HTML은 저장했으나 CDN 리소스 오류로 screenshot은 빈 화면이어서 `/openapi.json`으로 대체 |
| 사용자 성과 수치 | 현재 없음 | 실제 사용자 피드백 또는 측정 지표 확보 전까지 사용 금지 |
| Live G2B / provider procurement flow | 검증 필요 | local fixture contract 검증과 별개로 `G2B_API_KEY`와 승인된 provider credential이 있는 안전 환경에서만 확인 |

## 4. 민감정보 제외 점검

- `.env`, `.env.*`: evidence package에 포함하지 않음
- API key/token/password 파일: 포함하지 않음
- 고객/기관 내부자료: 포함하지 않음
- 소스코드 전체 폴더: portfolio zip에는 포함하지 않음
- generated runtime data: zip에는 포함하지 않음

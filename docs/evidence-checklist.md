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
| 사용자 템플릿 상태 무결성 | 완료 | `pytest -q tests/test_template_store_integrity.py --tb=short` -> `30 passed`; local/fake-S3 손상 보존·동시 변경·route backend 결속과 API 오류 경계 검증 |
| 사용자 템플릿 HTTP lifecycle | 완료 | mock provider와 임시 local state에서 create/list/get(use count 1)/delete/final empty JSONL 확인; 외부 API 호출 없음 |
| 생성 이력 상태 무결성 | 완료 | `pytest -q tests/test_history_store_integrity.py --tb=short` -> `36 passed`; local/fake-S3 손상 보존·동시 add/favorite·caller backend 결속과 API 오류 경계 검증 |
| 생성 이력 HTTP lifecycle | 완료 | mock provider와 임시 local state에서 register/generate/list/detail(문서 4개)/favorite/delete/final empty 확인; 외부 API 호출 없음 |
| 회의 녹음 상태 무결성 | 완료 | `pytest -q tests/test_meeting_recording_store_integrity.py --tb=short` -> `47 passed`; local/fake-S3 metadata 손상 보존·audio digest/size·UUID 충돌·동시 전사/승인·API 오류 경계 검증 |
| 회의 녹음 HTTP lifecycle | 완료 | mock provider와 임시 local state에서 upload/list/detail, offline transcript/approval, 2개 bundle 생성과 source recording provenance 확인; OpenAI transcription 호출 없음 |
| 결제 권한 상태 무결성 | 완료 | `pytest -q tests/test_billing_store_integrity.py --tb=short` -> `49 passed`; local/fake-S3 손상 보존·동시 변경·caller context 결속·middleware 순서와 API 오류 경계 검증 |
| 결제 권한 HTTP lifecycle | 완료 | mock provider와 임시 local state에서 webhook `free -> pro/active -> free/canceled`, local HMAC valid/invalid/malformed 계약, metered request 402와 corrupt-state 503 확인. Fake HTTP client로 recurring Price ID와 subscription metadata를 검증했으며 Stripe API 호출 없음 |
| 스타일 프로필 상태 무결성 | 완료 | `pytest -q tests/test_style_store_integrity.py --tb=short` -> `32 passed`; local/fake-S3 손상 보존·동시 create/override·route backend 결속·prompt/API 오류 경계 검증 |
| 스타일 프로필 HTTP lifecycle | 완료 | mock provider와 임시 local state에서 create/tone/bundle override/detail/list/default/delete/final empty 확인; provider API 호출 없음 |
| SSO 설정 상태 무결성 | 완료 | `pytest -q tests/test_sso_store_integrity.py --tb=short` -> `40 passed`; local/fake-S3 손상 보존·동시 partial update·route backend 결속·secret/SAML/API 오류 경계 검증 |
| SSO 설정 HTTP/UI lifecycle | 완료 | mock provider와 임시 local state의 실제 uvicorn에서 public status, disabled gate, LDAP/SAML/GCloud 전환, secret 마스킹 보존, SAML/GCloud callback 사전 차단 확인. Playwright 비로그인 화면에서 LDAP form 표시와 console error 0건 확인; LDAP·IdP·GCloud 외부 호출 없음 |
| 품질 학습 상태 무결성 | 완료 | `pytest -q tests/test_quality_learning_store_integrity.py` -> `43 passed`; feedback/eval/prompt override local/fake-S3 손상 원본 보존, foreign/legacy 경계, 독립 store 동시 쓰기, app backend 결속, API·generation context·prompt build fail-closed 검증 |
| 공개 공유 상태 무결성 | 완료 | `pytest -q tests/test_share_store_integrity.py --tb=short` -> `36 passed`; local/fake-S3 손상 보존·동시 생성/접근·route backend 결속과 public/auth API 오류 경계 검증 |
| 공개 공유 HTTP lifecycle | 완료 | mock provider와 임시 local state에서 create 200/public view 200/access count 1/revoke 200/post-revoke 404 확인; 외부 API 호출 없음 |
| 공공조달 판단 상태 무결성 | 완료 | `pytest -q tests/test_procurement_store_integrity.py` -> `47 passed`; local/fake-S3 missing-state·판단/snapshot 손상 원본·identity/path·입력 검증·logical lock 동시성·API 오류 경계 검증 |
| 공공조달 판단 HTTP/downstream lifecycle | 완료 | mock provider와 임시 local state에서 health·project create·snapshot/decision seed·GET·override·Decision Council run/get 및 동일 procurement decision/session 결속 확인; 외부 API 호출 없음 |
| 공공조달 검토 증빙 상태 무결성 | 완료 | `pytest -q tests/test_procurement_review_store.py` -> `49 passed`; local/fake-S3 record·packet·reviewed-package 손상/누락, exact orphan recovery, conditional write/CAS, uncertain commit reconciliation, 패자 package 정리, semantic drift와 API 500 경계 검증 |
| Decision Council 상태 무결성 | 완료 | `pytest -q tests/test_decision_council_store_integrity.py` -> `14 passed`; local/fake-S3 missing-state·손상 원본·canonical identity·독립 backend 동시성·app backend 결속과 project API 오류 경계 검증. Mock/local uvicorn lifecycle에서 health·project create·council run/get과 session identity 일치 확인 |
| 프로젝트·결재 상태 무결성 | 완료 | `pytest -q tests/test_project_approval_store_integrity.py` -> `47 passed`; local/fake-S3 missing-state·blank/invalid UTF-8·backend failure·owned schema/duplicate identity와 process lock 없는 project/approval conditional create/CAS·bounded mutation receipt·disjoint mutation·delete 경쟁·terminal decision·commit reconciliation·API 오류 경계 검증 |
| 프로젝트·결재 HTTP lifecycle | 완료 | H58 mock provider와 임시 local state에서 health·project create/update·document add·approval create/sync·stats·admin delete를 확인하고 project document의 approval ID/status가 `draft` state와 일치함을 확인; 외부 provider 호출 0건 |
| 보고서 워크플로우 상태 무결성 | 완료 | `pytest -q tests/test_report_workflow_store_integrity.py` -> `32 passed`; local/fake-S3 blank/invalid UTF-8·backend failure·workflow/nested identity·process lock 없는 conditional create/CAS·disjoint slide update·competing final decision·bounded receipt·commit reconciliation·API 500 경계 검증 |
| 보고서 워크플로우 HTTP lifecycle | 완료 | H59 mock provider와 임시 local state에서 health·workflow create·planning/slide generate·각 단계 승인·linked approval·최종 승인을 확인. Persisted private receipt 12개, public response 비노출, 외부 provider 호출 0건 |
| 보고서 워크플로우 확장 회귀 | 완료 | report workflow·quality learning·knowledge·project/approval·security·state·infrastructure 묶음 -> `430 passed`; provider API 호출 없음 |
| H59 report workflow CAS gate | 완료 | store focused gate -> `47 passed`; process lock 없는 fake-S3 20-way create/asset update, disjoint slide approval, competing final decision, commit-then-error 뒤 successor CAS와 bounded receipt 포함 |
| H56 procurement review 확장 회귀 | 완료 | review packet/package/state/project/procurement/approval/report/generation/security/infrastructure 묶음 -> `610 passed`; provider API와 외부 실행 없음 |
| H57 approval CAS 확장 회귀 | 완료 | project/approval/report/security/state/infrastructure 묶음 -> `541 passed`; process lock 없는 fake-S3 conditional create/CAS 포함, provider API와 외부 실행 없음 |
| H58 project CAS 확장 회귀 | 완료 | project/approval/report/security/state/infrastructure 묶음 -> `546 passed`; process lock 없는 fake-S3 project conditional create/CAS, bounded mutation receipt, disjoint update와 delete 경쟁 포함, provider API와 외부 실행 없음 |
| Non-live 전체 pytest gate | 완료 | provider API key를 process에서 제거한 `pytest tests/ -m "not live" -q` -> `4012 passed, 2 skipped, 4 deselected` (2026-07-17 H59 실측) |
| GitHub Actions CI | 완료 | 마지막으로 문서화한 main 자동화 증적: commit `e286f2f`, CI `29502322163` success (`3554 passed, 5 skipped`) |
| GitHub Actions CD | 완료 | 마지막으로 문서화한 main 자동화 증적: commit `e286f2f`, CD `29502322086` success. image digest `sha256:c72c286bcaabea41d59081631e4cf5ef6a1496f2f0cafaf01a96114732e6a384`; staging deploy/smoke와 production deploy는 skip되어 배포 proof에서 제외 |
| 직접 구현/설명 가능 범위 정리 | 완료 | `docs/contribution-note.md` |
| OpenAI live provider 호출 | 완료 | 2026-07-13 `tests/test_live_providers.py::test_live_openai_generate_ok` -> `1 passed in 23.26s`; local JUnit receipt는 gitignored `reports/completion-readiness/m1-openai-junit.xml` |

## 1-1. 재현 가능한 Local Evidence Contract

| 체크 항목 | 상태 | 증거 / 재현 명령 |
|---|---|---|
| Procurement decision package CLI contract manifest | 재현 가능 | `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version` |
| Manifest validation receipt | 재현 가능 | `python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py --write-result --result-path /tmp/decisiondoc-cli-contract-manifest-validation-result.json` |
| Persisted receipt checker | 재현 가능 | `python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py /tmp/decisiondoc-cli-contract-manifest-validation-result.json` |
| Completion readiness env template | 재현 가능 | `python3 scripts/check_completion_readiness.py --print-env-template` |
| Completion readiness proof plan | 재현 가능 | `python3 scripts/check_completion_readiness.py --print-proof-plan` |
| Completion readiness local receipt | 재현 가능 | `python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json` |
| Completion readiness receipt checker | 재현 가능 | `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json` |
| Completion proof receipt template/checker | 재현 가능 | `python3 scripts/check_completion_proof_receipt.py --print-template M1`, `python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m1-live-provider-proof.json` |
| M2/M6 runner-owned proof receipt | 재현 가능 | `run_stage_procurement_smoke.py`와 `run_deployed_smoke.py`의 `--proof-receipt`; preflight blocked, 실제 smoke passed/failed, secret-free checker 계약 |
| Completion readiness proof runbook | 재현 가능 | `docs/completion-readiness-runbook.md` |
| Local post-login UI flow evidence | 재현 가능 | `python3 scripts/capture_ui_flow_evidence.py` |

위 local evidence contract 검증은 repo 밖 `/tmp` receipt를 사용한다. Provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않는다.

Completion readiness/proof receipt는 gitignored `reports/completion-readiness/` 경로를 사용한다. Receipt checker 자체는 외부 호출을 실행하지 않는다. v2 proof receipt는 해당 milestone에서 승인·실행한 action을 제외 목록에서 빼고, 나머지 외부 action 경계를 유지한다.

## 2. 검증 실패

| 체크 항목 | 상태 | 사유 |
|---|---|---|
| 실패로 확정된 구현 기능 | 없음 | Gemini/Claude live 실패는 각각 외부 quota와 credit blocker이며 구현 회귀로 확정하지 않음 |

## 3. 검증 필요

| 체크 항목 | 상태 | 필요한 후속 작업 |
|---|---|---|
| Gemini live provider 호출 | blocked | API key/project의 quota 또는 billing 복구 후 live smoke 재실행 |
| Claude live provider 호출 | blocked | Anthropic credits 복구 후 live smoke 재실행 |
| Live provider fallback chain | 부분 확인 / blocked | OpenAI 강제 401 뒤 Gemini 호출은 확인. Gemini quota 복구 후 성공 fallback assertion 재실행 |
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

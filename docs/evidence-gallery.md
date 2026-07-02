# Evidence Gallery

## 1. Screenshots

| 파일 | 설명 | 상태 |
|---|---|---|
| `evidence/screenshots/web-ui-home.png` | 로컬 FastAPI static PWA root 화면. 로그인 폼 렌더링 확인 | 검증 완료 |

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

## 3-1. Reproducible Local Evidence Commands

| 항목 | 설명 | 상태 |
|---|---|---|
| `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json` | Procurement decision package local evidence CLI stdout JSON contract manifest. `contract_version` 기준으로 success/failure field를 고정 | 재현 가능 |
| `scripts/validate_procurement_decision_package_cli_contract_manifest.py --write-result --result-path /tmp/decisiondoc-cli-contract-manifest-validation-result.json` | manifest validation receipt를 repo 밖 `/tmp` 경로에 기록 | 재현 가능 |
| `scripts/check_procurement_decision_package_cli_contract_manifest_result.py /tmp/decisiondoc-cli-contract-manifest-validation-result.json` | persisted receipt가 현재 manifest와 일치하는지 확인 | 재현 가능 |

이 섹션은 파일이 `evidence/` package 안에 저장됐다고 주장하지 않는다. 필요할 때 위 명령으로 local-only receipt를 다시 생성한다.

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

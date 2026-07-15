# Implementation Evidence

분석 기준: 2026-07-16 현재 로컬 repo, mock provider 기반 runtime evidence, OpenAI live proof, non-live pytest gate, completion readiness/proof receipt, static PWA/CSP evidence.

## 1. 프로젝트 유형 판단

| 항목 | 판단 |
|---|---|
| 프로젝트명 | DecisionDoc AI |
| 프로젝트 유형 | 개인 PoC / MVP 확장 프로젝트로 판단 |
| 현재 상태 | MVP/PoC 구현 후 외부 실증 진행 중 |
| 핵심 스택 | Python 3.12, FastAPI, Pydantic v2, Jinja2, provider abstraction, local/S3 storage, Docker Compose, AWS SAM, pytest |
| 이력서 반영 가능 여부 | 조건부 가능 |

판단 이유: 코드상 FastAPI 앱, 문서 생성 API, provider/storage abstraction, export, static PWA, pytest 테스트가 존재하고 로컬 mock provider 기준으로 API 응답과 테스트를 검증했다. 2026-07-16 기준 non-live 전체 게이트는 `3120 passed, 2 skipped, 4 deselected`로 통과했고, static PWA는 CSP nonce와 inline handler 제거를 확인했다. 2026-07-13 OpenAI live generation은 1회 통과했지만 Gemini는 quota, Claude는 credit balance 때문에 blocked이며 fallback 성공 proof도 남아 있다. G2B 실데이터, production deployment, 실제 사용자 성과는 검증하지 않았다.

## 2. 구현 증거가 필요한 기능

| 기능 | 상태 | 증거 파일 | 검증 방식 | 비고 |
|---|---|---|---|---|
| FastAPI 앱 기동 및 health endpoint | 검증 완료 | `evidence/api-responses/health.json` | local uvicorn + curl | provider는 mock |
| 버전/환경 정보 endpoint | 검증 완료 | `evidence/api-responses/version.json` | curl `/version` | dev 환경 |
| bundle catalog 노출 | 검증 완료 | `evidence/api-responses/bundles.json` | curl `/bundles` | 20개 bundle 반환 확인 |
| API key 보호된 문서 생성 | 검증 완료 | `evidence/api-responses/generate-tech-decision.json` | curl `POST /generate` | mock provider |
| Markdown export 생성 | 검증 완료 | `evidence/api-responses/generate-export-tech-decision.json`, `evidence/output-artifacts/export_adr.md`, `evidence/output-artifacts/export_onepager.md` | curl `POST /generate/export` | local storage |
| 생성/인증/스토리지 테스트 | 검증 완료 | `evidence/cli-logs/pytest_generate_auth_storage.log` | `pytest tests/test_generate.py tests/test_auth_api_key.py tests/test_storage.py -q` | 60 passed |
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

결과: `3120 passed, 2 skipped, 4 deselected` (2026-07-16 실측).

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

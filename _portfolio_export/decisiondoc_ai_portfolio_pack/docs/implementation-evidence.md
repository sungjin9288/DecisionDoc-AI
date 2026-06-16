# Implementation Evidence

분석 기준: 2026-06-09 현재 로컬 repo와 mock provider 기반 런타임 검증 결과.

## 1. 프로젝트 유형 판단

| 항목 | 판단 |
|---|---|
| 프로젝트명 | DecisionDoc AI |
| 프로젝트 유형 | 개인 PoC / MVP 확장 프로젝트로 판단 |
| 현재 상태 | MVP 구현 후 고도화 중 |
| 핵심 스택 | Python 3.12, FastAPI, Pydantic v2, Jinja2, provider abstraction, local/S3 storage, Docker Compose, AWS SAM, pytest |
| 이력서 반영 가능 여부 | 조건부 가능 |

판단 이유: 코드상 FastAPI 앱, 문서 생성 API, provider/storage abstraction, export, static PWA, pytest 테스트가 존재하고 로컬 mock provider 기준으로 API 응답과 테스트를 검증했다. 다만 live provider, production deployment, 실제 사용자 성과는 이번 evidence 범위에서 검증하지 않았다.

## 2. 구현 증거가 필요한 기능

| 기능 | 상태 | 증거 파일 | 검증 방식 | 비고 |
|---|---|---|---|---|
| FastAPI 앱 기동 및 health endpoint | 검증 완료 | `evidence/api-responses/health.json` | local uvicorn + curl | provider는 mock |
| 버전/환경 정보 endpoint | 검증 완료 | `evidence/api-responses/version.json` | curl `/version` | dev 환경 |
| bundle catalog 노출 | 검증 완료 | `evidence/api-responses/bundles.json` | curl `/bundles` | 20개 bundle 반환 확인 |
| API key 보호된 문서 생성 | 검증 완료 | `evidence/api-responses/generate-tech-decision.json` | curl `POST /generate` | mock provider |
| Markdown export 생성 | 검증 완료 | `evidence/api-responses/generate-export-tech-decision.json`, `evidence/output-artifacts/export_adr.md`, `evidence/output-artifacts/export_onepager.md` | curl `POST /generate/export` | local storage |
| 생성/인증/스토리지 테스트 | 검증 완료 | `evidence/cli-logs/pytest_generate_auth_storage.log` | `pytest tests/test_generate.py tests/test_auth_api_key.py tests/test_storage.py -q` | 60 passed |
| Static PWA 화면 제공 | 검증 완료 | `evidence/screenshots/web-ui-home.png` | Playwright screenshot | 로그인 화면 확인 |
| Provider fallback/live provider | 검증 필요 | `app/providers/factory.py` | 코드 근거만 확인 | 실제 cloud key 사용 안 함 |
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

## 4. 검증 완료 기능

- FastAPI 앱이 mock provider/local storage 설정으로 로컬 실행됨.
- `/health`가 `status: ok`, `provider: mock`을 반환함.
- `/version`이 앱 버전, dev 환경, provider/storage 정보를 반환함.
- `/bundles`가 bundle catalog 목록을 반환함.
- `POST /generate`가 API key 인증 후 문서 bundle JSON을 반환함.
- `POST /generate/export`가 Markdown export 경로와 파일 목록을 반환하고 실제 Markdown 파일을 생성함.
- Web UI root가 로그인 화면으로 렌더링됨.

## 5. 검증 실패 기능

- 이번 evidence 수집 범위에서 실패로 확정된 구현 기능은 없음.
- 참고: `/health`의 `provider_policy_checks.quality_first`는 mock provider 설정 때문에 `degraded`로 표시된다. 이는 portfolio evidence에서 local mock verification을 사용했기 때문이며, production provider policy는 별도 검증 필요 항목이다.

## 6. 미구현 / 검증 필요

- live OpenAI/Gemini/Claude provider 호출: API key를 사용하지 않아 검증하지 않음.
- 실제 production deployment: 배포하지 않음.
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

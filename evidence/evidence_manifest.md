# Evidence Manifest

## 1. Collection Summary

- Project: DecisionDoc AI
- Date: 2026-07-14
- Project type: personal PoC / MVP expansion project
- Evidence scope: local mock-provider verification, API response capture, static and post-login UI flow, CSP nonce check, architecture diagrams, generated document samples
- External execution: live provider, G2B live API, AWS runtime, training, model promotion, production resume, bid submission not performed

## 2. Verified Features

| Feature | Verification | Artifact |
|---|---|---|
| FastAPI app health | local `curl /health` | `evidence/api-responses/health.json` |
| Version/config surface | local `curl /version` | `evidence/api-responses/version.json` |
| Bundle catalog | local `curl /bundles` | `evidence/api-responses/bundles.json` |
| Document generation API | local mock `POST /generate` | `evidence/api-responses/generate-tech-decision.json` |
| Markdown export API | local mock `POST /generate/export` | `evidence/api-responses/generate-export-tech-decision.json` |
| Export output files | local storage output capture | `evidence/output-artifacts/` |
| Auth/generation/storage tests | targeted pytest | `evidence/cli-logs/pytest_generate_auth_storage.log` |
| Static PWA screen | Playwright screenshot and snapshot | `evidence/screenshots/web-ui-home.png`, `evidence/cli-logs/playwright_snapshot.log` |
| Post-login local UI flow | local mock browser capture | `evidence/cli-logs/ui_flow_evidence.json`, `evidence/screenshots/ui-flow-01-after-login.png` through `ui-flow-04-export-complete.png` |
| Static PWA CSP boundary | local HTTP header/body check | `evidence/cli-logs/ui_csp_nonce_check.log` |
| Browser console | local Playwright console capture | `evidence/cli-logs/playwright_console.log` |
| Input and generated samples | sanitized local artifacts | `evidence/input-samples/`, `evidence/generated-samples/` |
| OpenAPI/Swagger schema | local `curl /openapi.json`, `curl /docs` | `evidence/swagger/` |
| Architecture views | source-backed Markdown diagrams | `evidence/architecture/` |

## 3. Evidence Boundary

이 디렉터리의 UI와 API 자료는 local mock 환경에서 수집됐다. Post-login 화면은 로컬 인증 흐름과 생성/export 동선을 보여주지만 production identity provider, 배포 URL, 외부 provider 품질을 검증하지 않는다. 과거 실행 로그는 그 시점의 결과이며 현재 전체 regression pass를 대신하지 않는다.

## 4. Unverified / Needs Follow-up

- Gemini/Claude와 fallback을 포함한 잔여 paid live-provider proof
- G2B 실데이터 end-to-end smoke
- Production deployment and post-deploy smoke
- External login/tenant operation in a deployed environment
- User outcome metrics and factual quality review

## 5. Sensitive Data Policy

Portfolio pack에서 다음 내용을 제외한다.

- `.env`, `.env.*`, API key, token, password, credential files
- customer/internal data and personal information
- application source folders such as `app/` and `tests/`
- dependency/build/cache folders and `.git/`
- runtime data not explicitly selected by the tracked source allowlist

## 6. Artifact Index

- `docs/implementation-evidence.md`
- `docs/evidence-checklist.md`
- `docs/evidence-gallery.md`
- `evidence/api-responses/`
- `evidence/architecture/`
- `evidence/cli-logs/`
- `evidence/execution-logs/`
- `evidence/generated-samples/`
- `evidence/input-samples/`
- `evidence/output-artifacts/`
- `evidence/screenshots/`
- `evidence/swagger/`

Pack membership과 각 artifact의 SHA-256은 generated `portfolio_manifest.json`에서 검증한다.

# Evidence Manifest

## 1. Collection Summary

- Project: DecisionDoc AI
- Date: 2026-06-09
- Project type: personal PoC / MVP expansion project
- Evidence scope: local mock-provider verification, API response capture, targeted pytest, UI screenshot, architecture diagrams
- Document-generation evidence priority: input samples, generated Markdown samples, API responses, OpenAPI/Swagger artifacts, execution logs
- App source modified: no
- New feature development: no

## 2. Verified Features

| Feature | Verification | Artifact |
|---|---|---|
| FastAPI app health | `curl /health` | `evidence/api-responses/health.json` |
| Version/config surface | `curl /version` | `evidence/api-responses/version.json` |
| Bundle catalog | `curl /bundles` | `evidence/api-responses/bundles.json` |
| Document generation API | `curl POST /generate` with API key | `evidence/api-responses/generate-tech-decision.json` |
| Markdown export API | `curl POST /generate/export` with API key | `evidence/api-responses/generate-export-tech-decision.json` |
| Export output files | local storage output copied | `evidence/output-artifacts/export_adr.md`, `evidence/output-artifacts/export_onepager.md` |
| Auth/generation/storage tests | targeted pytest | `evidence/cli-logs/pytest_generate_auth_storage.log` |
| Static PWA screen | Playwright screenshot | `evidence/screenshots/web-ui-home.png` |
| Input request samples | sanitized JSON/text files | `evidence/input-samples/` |
| Generated document samples | extracted Markdown outputs | `evidence/generated-samples/` |
| OpenAPI/Swagger schema | `curl /openapi.json`, `curl /docs` | `evidence/swagger/` |
| Document generation execution log | curl capture log | `evidence/execution-logs/document_generation_api_capture.log` |

## 3. Failed Verification

- None in the collected local mock-provider evidence set.

## 4. Unverified / Needs Follow-up

- Live cloud provider calls
- Production deployment and post-deploy smoke
- Login-authenticated full UI workflow
- User outcome metrics

## 5. Sensitive Data Policy

Excluded from the intended portfolio zip:

- `.env`, `.env.*`
- API keys, tokens, passwords, credential files
- customer/internal data
- full source folders such as `app/`, `src/`, `backend/`, `frontend/`
- dependency/build/cache folders such as `node_modules/`, `.venv/`, `venv/`, `build/`, `dist/`, `.git/`

## 6. Artifact Index

- `docs/implementation-evidence.md`
- `docs/evidence-checklist.md`
- `docs/evidence-gallery.md`
- `evidence/evidence_manifest.md`
- `evidence/api-responses/`
- `evidence/cli-logs/`
- `evidence/execution-logs/`
- `evidence/input-samples/`
- `evidence/generated-samples/`
- `evidence/swagger/`
- `evidence/output-artifacts/`
- `evidence/screenshots/`
- `evidence/architecture/`

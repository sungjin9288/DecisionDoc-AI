# Phase 41 Production Post-Deploy Smoke Evidence

Status: `PRODUCTION_POST_DEPLOY_SMOKE_PASSED_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-13T02:26:53+09:00`

## Purpose

Phase 41 records the separate production post-deploy smoke after Phase 40 completed the reviewer sign-off evidence gate.

This phase intentionally exercised normal production document-generation paths. Unlike the reviewer sign-off probe, this smoke made normal generation provider calls and created runtime artifacts such as bundles, exports, report workflow records, a promoted project document, a PPTX export, and a post-deploy report.

This phase still did not authorize or start model training, dataset upload, provider fine-tune API calls, provider job creation/polling, model candidate emission, or model promotion.

## Runtime

- Target: `https://admin.decisiondoc.kr`
- Remote report: `/opt/decisiondoc/reports/post-deploy/post-deploy-20260512T172507Z.json`
- Latest report SHA-256: `604adb69d21e9b5bb62dbccc2a41fec6256817cc38474a4bb7e6e785ab29abb0`
- Started at: `2026-05-12T17:25:07.025556+00:00`
- Finished at: `2026-05-12T17:26:53.647022+00:00`
- Provider routes: `generation=claude,openai,gemini`, `attachment=gemini,claude,openai`, `visual=openai`
- Provider policy: `quality_first=ok`

## Health And Infra Checks

| Check | Result |
|---|---|
| `GET /health` | `200` |
| provider route checks | `ok` |
| docker compose ps | `passed` |
| nginx config test | `passed` |
| deployed smoke preflight | `passed` |

## Document Generation Smoke

| Check | Result |
|---|---|
| `POST /generate` without API key | `401` |
| `POST /generate` with API key | `200` |
| `POST /generate/export` with API key | `200`, `files=4` |
| `POST /generate/with-attachments` without API key | `401` |
| `POST /generate/with-attachments` with API key | `200`, `files=1`, `docs=4` |
| `POST /generate/from-documents` without API key | `401` |
| `POST /generate/from-documents` with API key | `200`, `files=1`, `docs=2` |

## Report Workflow Smoke

| Check | Result |
|---|---|
| `POST /report-workflows` without API key | `401` |
| `POST /report-workflows` with API key | `200` |
| `POST /slides/generate` before planning approval | `400` |
| `POST /planning/generate` | `200`, `slide_plans=2` |
| `POST /planning/approve` | `200` |
| `POST /slides/generate` | `200`, `slides=2` |
| `POST /final/submit` before slide approvals | `400` |
| slide approvals | `200`, `approved=2` |
| `POST /final/submit` | `200` |
| `POST /final/executive-approve` before PM | `400` |
| PM approval | `200` |
| executive approval | `200` |
| project creation | `200` |
| workflow promote | `200` |
| PPTX export | `200`, `bytes=43480` |
| snapshot export | `200`, `decisiondoc_report_workflow_snapshot.v1` |

## Boundary Statement

Allowed and observed in this phase:

- Normal production generation provider calls
- Runtime bundle/export creation
- Report workflow planning/slides/final approval smoke records
- Project and promoted project-document smoke records
- PPTX and snapshot export responses
- Local production post-deploy report file write

Still not allowed and not observed:

- External dataset upload
- Provider fine-tune API calls
- Provider job creation or polling
- Training execution
- Model candidate emission
- Model promotion
- Server-generated reviewer approval records

## Next Step

The production backend smoke is now passed. The next practical gate is browser-level UAT for the admin UI: create a document from the production UI, download/open PDF/PPTX/HWP where applicable, and confirm the step-based report workflow UX is usable end-to-end.

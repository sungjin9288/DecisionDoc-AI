# STATUS — Public Procurement Go/No-Go Copilot

## Current milestone
Milestone 6 completed

---

## Initiative summary

Add a project-linked procurement decision capability inside DecisionDoc AI for small public-sector consulting firms.

The feature should:
- reuse existing project/workspace flows
- reuse existing G2B and RFP-related capabilities
- produce `GO`, `CONDITIONAL_GO`, or `NO_GO`
- generate a structured bid-readiness checklist
- generate a new decision-stage bundle: `bid_decision_kr`
- hand off reusable context into:
  - `rfp_analysis_kr`
  - `proposal_kr`
  - `performance_plan_kr`

---

## Fixed decisions

- Build inside DecisionDoc AI
- Do not create a standalone procurement app
- Reuse existing project, document, knowledge, G2B, approval, share, history, export, eval, and audit flows
- Keep provider abstraction intact
- Keep local and S3 storage abstractions intact
- Keep `mock` provider deterministic and working
- Run deterministic hard filters before model-generated narrative
- Recommendation values are:
  - `GO`
  - `CONDITIONAL_GO`
  - `NO_GO`
- Checklist must exist in:
  - structured machine-readable form
  - human-readable document form
- New bundle id:
  - `bid_decision_kr`
- Prefer additive rollout behind:
  - `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`

---

## Repository map discovered in Milestone 0

- project/workspace integration:
  - `app/main.py`
  - `app/routers/projects.py`
  - `app/storage/project_store.py`
  - `app/static/index.html`
  - `create_app()` wires `project_store`; the current project detail surface already exists in the single-file web UI; the current project-level import pattern is `POST /projects/{project_id}/imports/voice-brief`.
- G2B integration:
  - `app/routers/g2b.py`
  - `app/services/g2b_collector.py`
  - `app/routers/history.py`
  - Existing surfaces are `/g2b/status`, `/g2b/search`, `/g2b/fetch`, plus tenant/user-scoped G2B bookmarks.
- attachment / RFP parsing:
  - `app/routers/generate.py`
  - `app/services/attachment_service.py`
  - `app/services/rfp_parser.py`
  - Existing surfaces are `POST /attachments/parse-rfp` and `POST /generate/with-attachments`; both produce structured RFP signals but do not persist them into project state.
- knowledge document flow:
  - `app/routers/knowledge.py`
  - `app/storage/knowledge_store.py`
  - `app/services/generation_service.py`
  - `GenerateRequest.project_id` triggers knowledge-context injection via `KnowledgeStore(project_id)`.
- bundle registry:
  - `app/bundle_catalog/registry.py`
  - `app/bundle_catalog/bundles/*`
  - New decision bundle must register through `BUNDLE_REGISTRY` / `get_bundle_spec(...)`; existing downstream targets already present are `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr`.
- generation/export path:
  - `app/routers/generate.py`
  - `app/services/generation_service.py`
  - `app/storage/base.py`
  - `app/storage/factory.py`
  - Core flow is bundle generation, render, validation, then `storage.save_export(...)`.
- approval/share/history/audit path:
  - `app/routers/approvals.py`
  - `app/storage/approval_store.py`
  - `app/routers/history.py`
  - `app/storage/history_store.py`
  - `app/storage/share_store.py`
  - `app/middleware/audit.py`
  - Approval finalization already updates linked project documents by `request_id`.
- provider abstraction path:
  - `app/providers/base.py`
  - `app/providers/factory.py`
  - `app/providers/*`
- storage abstraction path:
  - `app/storage/base.py`
  - `app/storage/factory.py`
  - `app/storage/local.py`
  - `app/storage/s3.py`
- tests / fixtures / smoke path:
  - `tests/test_project_management.py`
  - `tests/test_g2b.py`
  - `tests/test_rfp_parsing.py`
  - `tests/test_knowledge.py`
  - `tests/test_approval_workflow.py`
  - `tests/test_bundle_eval.py`
  - `tests/test_eval_pipeline.py`
  - `tests/test_history_favorites.py`
  - `tests/test_voice_brief_import.py`
  - `tests/test_audit.py`
  - `scripts/smoke.py`
  - `scripts/ops_smoke.py`
  - `scripts/voice_brief_smoke.py`
- feature-flag integration point:
  - `app/config.py`
  - `app/main.py`
  - `app/static/index.html`
  - `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED` now exists, is resolved through `app.config.is_procurement_copilot_enabled()`, and is exposed to the UI via `/version.features.procurement_copilot`.

## Plan corrections discovered from the real repository

- assumption:
  the initiative should extend a small monolithic `app/main.py`-centric app
- actual repository reality:
  the live app is router-based with multiple stores/services plus a single-file web UI
- correction:
  implement later changes in `app/routers/*`, `app/services/*`, `app/storage/*`, and `app/static/index.html`
- impact on next milestone:
  avoid inventing a new frontend/module structure
- assumption:
  project-linked generation artifacts are generally persisted whenever `project_id` is supplied
- actual repository reality:
  only `POST /generate/stream` auto-calls `project_store.add_document(...)`; synchronous `/generate`, `/generate/export`, and download/export endpoints do not project-link automatically
- correction:
  treat project linkage as an explicit design decision for procurement docs
- impact on next milestone:
  do not assume the current sync generation path already lands artifacts in project history
- assumption:
  existing G2B and RFP parsing already create project-linked procurement state
- actual repository reality:
  `/g2b/fetch` and `/attachments/parse-rfp` return structured context for immediate use but do not persist normalized opportunity or RFP state into `ProjectStore`
- correction:
  Milestone 2 needs a dedicated project attach/import step
- impact on next milestone:
  persistence must be introduced before UI handoff
- assumption:
  knowledge storage follows the same tenant-scoped layout as projects
- actual repository reality:
  `app/storage/knowledge_store.py` stores under `data/knowledge/{project_id}` and generation loads it only by `project_id`
- correction:
  v1 should reuse this existing capability-profile path as-is
- impact on next milestone:
  do not broaden Milestone 1 into a storage redesign
- assumption:
  adding a new feature flag is mostly a config-file task
- actual repository reality:
  there is no generic feature-flag system, only thin env helpers
- correction:
  later flagging should be a narrow gate in router and UI bootstrap paths
- impact on next milestone:
  keep rollout control simple and local
- assumption:
  audit reuse is automatic once a new route exists
- actual repository reality:
  `app/middleware/audit.py` only audits `ALWAYS_AUDIT_PREFIXES` plus auth failures, so adding `AUDIT_RULES` alone is not sufficient
- correction:
  if procurement endpoints need audit coverage, treat audit wiring as explicit work
- impact on next milestone:
  Milestone 6 must not assume audit comes for free
- assumption:
  procurement v1 needs a new admin/workspace UI
- actual repository reality:
  the existing project detail page in `app/static/index.html` already hosts project-level import actions and document management
- correction:
  extend the current project detail surface
- impact on next milestone:
  smallest UI blast radius is project detail, not a new screen
- assumption:
  project access is consistently tenant-scoped in project routes
- actual repository reality:
  some routes use tenant-scoped lookups, but `get` / `update` / `archive` still call unscoped `project_store` helpers
- correction:
  new procurement routes should follow the tenant-scoped pattern already used by the Voice Brief import route
- impact on next milestone:
  avoid copying legacy unscoped access patterns

---

## Completed milestones

- Milestone 0 — Repository discovery and integration map
- Milestone 1 — Domain model and persistence shape
- Milestone 2 — Opportunity intake and project attachment
- Milestone 3 — Hard filters and fit scoring
- Milestone 4 — Recommendation narrative and bid-readiness checklist
- Milestone 5 — Decision bundle and downstream handoff
- Milestone 6 — UI/API integration, approval/audit/eval/docs

---

## Next milestone

None — initiative complete

---

## Smallest valid persistence default for Milestone 1

- inference:
  the smallest valid shape is a new additive project-linked procurement state store/service, separate from `ProjectDocument`, while continuing to write rendered decision artifacts into existing `ProjectStore.documents`
- rationale:
  `ProjectDocument` is optimized for rendered doc snapshots, approval status, and downloads; structured opportunity state, scoring, checklist payloads, and raw source snapshots fit the repository's existing separate JSON-backed store-per-concern pattern more cleanly

---

## Open implementation notes

- Milestone 1 implementation added strict procurement decision models in `app/schemas.py`
- Milestone 1 implementation added `app/storage/procurement_store.py`
- Procurement decision state now persists at `data/tenants/{tenant_id}/procurement_decisions.json`
- Raw procurement source snapshots now persist at `data/tenants/{tenant_id}/procurement_snapshots/{project_id}/{snapshot_id}.json`
- `app.main.py` now wires `app.state.procurement_store` for later milestone routes
- Milestone 2 implementation added `POST /projects/{project_id}/imports/g2b-opportunity`
- Milestone 2 implementation added `GET /projects/{project_id}/procurement`
- Milestone 3 implementation added `POST /projects/{project_id}/procurement/evaluate`
- Milestone 4 implementation added `POST /projects/{project_id}/procurement/recommend`
- Milestone 3 implementation added `app/services/procurement_decision_service.py`
- Project-scoped G2B attachment now normalizes the selected announcement into `NormalizedProcurementOpportunity`
- Project-scoped G2B attachment now stores the imported source payload as a procurement snapshot together with `announcement`, `extracted_fields`, and `structured_context`
- If pre-parsed RFP signals are supplied to the import route, the route reuses them instead of reparsing raw text
- If pre-parsed RFP signals are not supplied and scraped raw text exists, the route reuses the current `rfp_analysis_kr` provider path through `parse_rfp_fields(...)`
- Milestone 2 import preserves existing capability profile, hard filters, score breakdown, checklist items, recommendation, and notes when updating the primary project opportunity
- Milestone 3 evaluation now resolves project capability profile from `KnowledgeStore(project_id)` when documents exist
- Milestone 3 evaluation now persists deterministic hard-filter results into `hard_filters`
- Milestone 3 evaluation now persists weighted factor-level score breakdown into `score_breakdown`
- Milestone 3 evaluation now persists `soft_fit_score`, `soft_fit_status`, and explicit `missing_data` into the procurement decision record
- Milestone 3 evaluation caps the persisted soft-fit score below the `GO` threshold when a blocking hard-filter failure exists so downstream recommendation input remains internally consistent
- Milestone 4 recommendation is now derived deterministically from persisted hard filters, weighted score, and explicit missing-data state
- Milestone 4 recommendation now persists `GO`, `CONDITIONAL_GO`, or `NO_GO` into the structured `recommendation` field without introducing model-generated authority
- Milestone 4 checklist now persists categorized `ProcurementChecklistItem` records covering eligibility, certifications, domain fit, references, staffing and partner readiness, schedule, scope clarity, security and infrastructure obligations, budget risk, and internal readiness
- Milestone 4 uses the existing deterministic evaluation service path and does not require a provider call, keeping the mock path stable and reproducible
- Milestone 5 implementation added the `bid_decision_kr` bundle through the existing bundle registry, schema validation path, Jinja render path, and export path
- Milestone 5 generation now injects project-scoped procurement handoff context into `bid_decision_kr`, `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` when `project_id` is present and procurement state exists
- Milestone 5 keeps procurement structured state primary by building handoff context from the persisted decision record and latest source snapshot rather than introducing a parallel document handoff store
- Milestone 5 keeps cache correctness aligned with project knowledge and procurement state by injecting those project-derived contexts before cache key calculation
- Milestone 6 adds local feature gating via `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`, exposes it as `/version.features.procurement_copilot`, and blocks procurement routes plus `bid_decision_kr` generation with `403 FEATURE_DISABLED` when disabled
- Milestone 6 attaches the procurement workflow to the existing project-detail UI with the smallest controls needed to import a G2B opportunity, run the 1-click evaluate→recommend sequence, generate `bid_decision_kr`, and start downstream `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` flows
- Milestone 6 keeps project procurement generation on the existing `/generate/stream` path so generated decision documents auto-link back into project documents without creating a second document flow
- Milestone 6 reuses the existing approval and share routes from project document rows, and syncs project-document approval state across draft / in_review / changes_requested / approved / rejected transitions
- Milestone 6 adds explicit audit action coverage for procurement import/evaluate/recommend and share create/revoke instead of assuming prefix-based audit behavior
- Milestone 6 updates deployment wiring, local env examples, smoke coverage, and operator docs so procurement rollout can be toggled per stage without guessing
- Milestone 1 validation baseline repairs updated login-aware e2e setup, removed CSP-unsafe waits, fixed duplicate script nonce injection on `/`, aligned `style_profile_id` request payload handling, and repaired translate/review content lookup against the current `generatedDocs` result model
- Keep new procurement routes tenant-scoped even where older project routes are not
- Reuse `KnowledgeStore(project_id)` as the v1 capability-profile source path unless later milestones prove it insufficient
- Treat project linkage for synchronous generation/export as an explicit product decision, not an existing default
- Treat audit coverage for new procurement endpoints as explicit work when those routes are introduced

---

## Known risks

- Existing project/document linkage patterns still constrain the smallest safe persistence choice
- `KnowledgeStore` is project-keyed but not tenant-scoped, so reuse must stay minimal in v1
- Sync generation paths outside `/generate/stream` do not currently auto-link into project history
- Audit coverage is not automatic for new procurement routes
- The feature must not break `mock` provider workflows
- The feature must not introduce a parallel document or approval system
- Milestone 2 keeps a single primary `opportunity` on the procurement decision record; the broader PRD allowance for multiple opportunity records remains future work
- Current scoring heuristics are deterministic and intentionally conservative, but the factor weights and keyword rules are still v1 defaults that will likely need tuning through later eval work
- Recommendation summary and checklist language are deterministic v1 text, not polished executive prose yet; richer explanation quality remains future work

---

## Post-closeout hardening

- Lambda-local state drift was removed from the live dev path by moving core tenant/user/project/procurement state stores onto the shared S3-backed state backend when `DECISIONDOC_STORAGE=s3`
- Live auth/bootstrap blockers were closed so authenticated browser sessions can use project and procurement routes without falling back to API-key-only access
- The login shell no longer emits the earlier `addSSOLoginButtons`, favicon, password-form, autocomplete, service-worker, or CDN console errors/warnings observed during dev rollout hardening
- Public shell and PWA routes now support `HEAD` as well as `GET`, which keeps browser/probe/header-only checks off the earlier `405` path
- Test verification is now warning-free: JWT short-key fixtures, `datetime.utcnow()` fixture usage, deprecated uvicorn websocket startup in the E2E fixture, and fixed-port E2E server binding have all been cleaned up
- Latest verified branch closeout commits:
  - `6974114` — public shell `HEAD` support
  - `163214f` — JWT/UTC test warning cleanup
  - `f2d18e6` — E2E websocket warning cleanup
  - `fe4a695` — dynamic E2E port allocation

---

## Next-step development plan

- Initiative complete:
  future work, if any, should be tracked as post-launch tuning or follow-up tasks rather than new milestone work inside this plan

---

## Validation log

- date/time:
  2026-03-25 17:31:23 KST
- milestone:
  Milestone 0 — Repository discovery and integration map
- commands run:
  `sed -n '1,240p' AGENTS.md`
  `sed -n '1,260p' docs/specs/public_procurement_copilot/{PRD,PLAN,IMPLEMENT,STATUS}.md`
  repository `rg -n` inspection across routers, stores, services, UI, tests, and smoke scripts
- result:
  repository map confirmed; no feature code added
- notes:
  `STATUS.md` updated to reflect the real file map and minimal plan corrections discovered during repository inspection
- date/time:
  2026-03-25 17:42:59 KST
- milestone:
  Milestone 1 — Domain model and persistence shape
- commands run:
  `.venv/bin/pytest -q tests/test_procurement_store.py tests/test_project_management.py`
  `.venv/bin/pytest -q tests/`
- result:
  targeted procurement + project regression tests passed (`92 passed in 45.85s`)
  full suite failed (`47 failed, 1473 passed, 2 skipped`) due unrelated existing baseline failures outside procurement persistence scope
- notes:
  repaired procurement-store serialization issues and hardened `tests/test_project_management.py` to run hermetically against the current API key header and local env handling
- date/time:
  2026-03-25 18:06:58 KST
- milestone:
  Milestone 1 — Validation gate triage
- commands run:
  `.venv/bin/pytest -q tests/test_billing.py::test_webhook_checkout_completed -q`
  `.venv/bin/pytest -q tests/test_g2b.py::TestSearchAnnouncements::test_no_api_key_returns_empty -q`
  `.venv/bin/pytest -q tests/test_style_system.py::test_analyze_document_style_mock_provider -q`
  `.venv/bin/pytest -q tests/e2e/test_main_flow.py::test_bundle_selection_enables_generate_button -q`
  `sed -n '1,240p' tests/e2e/test_main_flow.py`
  `sed -n '7038,7105p' app/static/index.html`
  `sed -n '7655,7755p' app/static/index.html`
  `sed -n '4250,4315p' app/static/index.html`
- date/time:
  2026-03-25 22:25:04 KST
- milestone:
  Milestone 1 — Validation baseline repaired and closed
- commands run:
  `.venv/bin/pytest -q tests/e2e/test_main_flow.py`
  `.venv/bin/pytest -q tests/test_procurement_store.py tests/test_generate.py::test_generate_accepts_optional_style_profile_id tests/test_sketch_endpoint.py::test_sketch_accepts_optional_style_profile_id tests/test_translate_endpoint.py tests/test_review_endpoint.py tests/e2e/test_main_flow.py`
  `.venv/bin/pytest -q tests/test_billing.py tests/test_g2b.py tests/test_local_provider.py tests/test_notifications.py tests/test_pdf_endpoint.py tests/test_security.py tests/test_style_system.py`
  `.venv/bin/pytest -q tests/test_metrics_alerting.py tests/test_quality_hardening.py`
  `.venv/bin/pytest -q tests/`
- result:
  targeted procurement and repaired baseline regression set passed (`52 passed, 1 skipped`)
  expanded async and provider baseline subset passed (`203 passed`)
  full suite passed (`1521 passed, 3 skipped`)
- notes:
  repaired login-aware e2e bootstrap, CSP-safe waits, duplicate root script nonce injection, result-action content lookup for translate and review, test async runner compatibility, hermetic local LLM endpoint fixture setup, and OpenAI provider event-loop safety without advancing to Milestone 2
- date/time:
  2026-03-25 22:41:51 KST
- milestone:
  Milestone 2 — Opportunity intake and project attachment
- commands run:
  `.venv/bin/pytest -q tests/test_project_management.py tests/test_procurement_store.py`
  `.venv/bin/pytest -q tests/`
- result:
  targeted procurement and project attachment tests passed (`98 passed in 2.38s`)
  full suite passed (`1527 passed, 3 skipped`)
- notes:
  added the smallest project-scoped G2B opportunity import route and procurement retrieval route, preserved raw procurement source snapshots, reused pre-parsed RFP signals when available, and kept existing structured decision fields intact without advancing into hard filters, scoring, narrative generation, bundle registration, or UI work
- date/time:
  2026-03-25 22:58:57 KST
- milestone:
  Milestone 3 — Hard filters and fit scoring
- commands run:
  `.venv/bin/pytest -q tests/test_procurement_decision_service.py tests/test_project_management.py tests/test_procurement_store.py`
  `.venv/bin/pytest -q tests/`
- result:
  targeted procurement scoring and project regression tests passed (`104 passed in 2.30s`)
  full suite passed (`1533 passed, 3 skipped`)
- notes:
  added deterministic project-scoped procurement evaluation that resolves capability profile from project knowledge, computes hard filters and weighted factor breakdown, persists explicit missing-data state, and exposes the smallest evaluation route without advancing into recommendation narrative, checklist generation, bundle registration, downstream handoff, or UI work
- date/time:
  2026-03-26 09:13:31 KST
- milestone:
  Milestone 4 — Recommendation narrative and bid-readiness checklist
- commands run:
  `.venv/bin/pytest -q tests/test_procurement_decision_service.py tests/test_project_management.py tests/test_procurement_store.py`
  `.venv/bin/pytest -q tests/`
- result:
  targeted procurement recommendation, checklist, and project regression tests passed (`109 passed in 2.55s`)
  full suite passed (`1538 passed, 3 skipped`)
- notes:
  added deterministic project-scoped recommendation and categorized checklist generation on top of the persisted evaluation state, exposed the smallest recommendation endpoint, and preserved the deterministic mock path without advancing into bundle generation, downstream handoff, feature-flag rollout, audit wiring, or UI work
- date/time:
  2026-03-26 09:37:56 KST
- milestone:
  Milestone 5 — Decision bundle and downstream handoff
- commands run:
  `python3 -m py_compile app/bundle_catalog/bundles/bid_decision_kr.py app/services/generation_service.py app/domain/schema.py app/providers/mock_provider.py tests/test_procurement_bundle_handoff.py tests/test_gov_bundles.py tests/test_bundle_specs.py`
  `.venv/bin/pytest -q tests/test_procurement_bundle_handoff.py tests/test_gov_bundles.py tests/test_bundle_specs.py tests/test_project_management.py tests/test_procurement_store.py tests/test_procurement_decision_service.py tests/test_generate.py`
  `.venv/bin/pytest -q tests/`
- result:
  targeted procurement bundle, handoff, registry, and regression tests passed (`313 passed in 12.37s`)
  full suite passed (`1562 passed, 3 skipped`)
- notes:
  added `bid_decision_kr` through the existing bundle registry and template pipeline, injected project-scoped procurement handoff context into `bid_decision_kr`, `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr`, kept the mock provider deterministic with bundle-specific builders, and moved project-derived knowledge/procurement context injection ahead of cache key calculation so regenerated bundle output tracks persisted decision-state changes
- date/time:
  2026-03-26 11:34:00 KST
- milestone:
  Milestone 6 — UI/API integration, approval/audit/eval/docs
- commands run:
  `python3 -m py_compile app/config.py app/main.py app/routers/health.py app/services/generation_service.py app/routers/projects.py app/routers/generate.py app/middleware/audit.py app/routers/approvals.py scripts/smoke.py`
  `node -e "...Validated inline script blocks..."`
  `.venv/bin/pytest -q tests/test_version_and_validate.py tests/test_project_management.py tests/test_procurement_bundle_handoff.py tests/test_audit.py`
  `.venv/bin/pytest -q tests/e2e/test_main_flow.py`
  `.venv/bin/pytest -q tests/`
- result:
  feature flag, project-detail UI, project-doc approval/share reuse, audit mapping, smoke/docs rollout coverage, targeted regression tests, e2e, and full suite all passed
- notes:
  closed the project-detail procurement workflow without creating new public routes or parallel approval/share systems, reused `/generate/stream` for project auto-link behavior, and wired deploy-time rollout control through the existing SAM + GitHub Actions path
- date/time:
  2026-03-27 00:28:00 KST
- milestone:
  Post-closeout hardening — live dev rollout and verification hygiene
- commands run:
  `python3 -m py_compile app/main.py tests/test_pwa.py tests/test_auth.py tests/test_notifications.py tests/test_sso.py tests/test_audit.py tests/test_history_favorites.py tests/e2e/conftest.py tests/e2e/test_main_flow.py`
  `.venv/bin/pytest -q tests/test_pwa.py tests/test_infrastructure.py`
  `.venv/bin/pytest -q tests/test_auth.py tests/test_notifications.py tests/test_sso.py tests/test_audit.py tests/test_history_favorites.py`
  `.venv/bin/pytest -q tests/e2e/test_main_flow.py`
  `.venv/bin/pytest -q tests/`
  `curl -I -s https://jawzr3widk.execute-api.ap-northeast-2.amazonaws.com/`
  `curl -I -s https://jawzr3widk.execute-api.ap-northeast-2.amazonaws.com/favicon.ico`
  `gh api repos/sungjin9288/DecisionDoc-AI/actions/runs/23603114976`
- result:
  local targeted regression, warning cleanup, E2E, and full suite all passed (`1608 passed, 3 skipped`) with warning summary reduced to zero; live dev `HEAD /` and `HEAD /favicon.ico` both returned `200`; `deploy-smoke` run `23603114976` completed successfully
- notes:
  post-Milestone 6 hardening closed live Lambda state drift, public shell bootstrap noise, favicon/public asset regressions, public `HEAD` compatibility, JWT/UTC test warnings, deprecated E2E websocket startup, and fixed-port E2E collision risk without reopening procurement scope

---

## Files touched

- file path
  `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  record Milestone 0 repository discovery, Milestone 1 implementation state, validation-baseline repair progress, and milestone completion status
- file path
  `app/schemas.py`
- reason for change
  add strict procurement decision domain models for opportunity, capability profile reference, hard filters, score breakdown, checklist items, recommendation, source snapshot metadata, persisted decision records, accept the current optional `style_profile_id` payload used by the UI, add the strict Milestone 2 project opportunity import request model, and add top-level Milestone 3 score and missing-data fields
- file path
  `app/routers/projects.py`
- reason for change
  add the tenant-scoped Milestone 2 G2B opportunity attachment/import endpoint and procurement retrieval endpoint, add the Milestone 3 deterministic procurement evaluation endpoint, add the Milestone 4 recommendation endpoint, normalize imported G2B data into the procurement store, preserve raw source snapshots, and keep existing structured procurement decision fields intact on update
- file path
  `app/services/procurement_decision_service.py`
- reason for change
  add deterministic project-scoped procurement evaluation logic that resolves knowledge-backed capability profile context, computes hard filters, computes weighted soft-fit score breakdown, persists explicit missing-data state, and derives structured recommendation plus categorized checklist without invoking model-generated narrative
- file path
  `app/storage/procurement_store.py`
- reason for change
  add additive tenant-scoped procurement decision persistence and raw source snapshot storage
- file path
  `app/main.py`
- reason for change
  wire `procurement_store` into `GenerationService` for Milestone 5 project-scoped handoff injection, while preserving the existing `app.state.procurement_store` dependency used by procurement routes and services
- file path
  `app/config.py`
- reason for change
  add the local procurement copilot rollout helper used by app creation, route gating, and `/version` feature exposure
- file path
  `app/domain/schema.py`
- reason for change
  add dedicated procurement handoff prompt injection and keep the internal procurement context out of prompt requirement serialization and sketch payload cleanup
- file path
  `app/bundle_catalog/bundles/bid_decision_kr.py`
- reason for change
  add the new decision-stage procurement bundle specification and validator/lint schema for opportunity brief, Go/No-Go memo, bid-readiness checklist, and proposal kickoff handoff summary
- file path
  `app/bundle_catalog/registry.py`
- reason for change
  register `bid_decision_kr` in the built-in bundle registry so it flows through the existing bundle lookup, metadata, and generation pipeline
- file path
  `app/templates/v1/bid_decision_kr/opportunity_brief.md.j2`
- reason for change
  render the decision-stage opportunity brief through the existing Jinja template pipeline
- file path
  `app/templates/v1/bid_decision_kr/go_no_go_memo.md.j2`
- reason for change
  render the decision-stage Go/No-Go memo through the existing Jinja template pipeline
- file path
  `app/templates/v1/bid_decision_kr/bid_readiness_checklist.md.j2`
- reason for change
  render the decision-stage bid-readiness checklist through the existing Jinja template pipeline
- file path
  `app/templates/v1/bid_decision_kr/proposal_kickoff_summary.md.j2`
- reason for change
  render the decision-stage downstream handoff summary through the existing Jinja template pipeline
- file path
  `app/services/generation_service.py`
- reason for change
  inject project-derived procurement handoff context for `bid_decision_kr` and downstream bundles, and make cache invalidation follow project knowledge/procurement state changes by injecting project-derived context before cache key calculation
- file path
  `app/providers/mock_provider.py`
- reason for change
  keep mock generation deterministic for the new decision-stage bundle and downstream handoff path by preferring project procurement context and adding bundle-specific mock builders for procurement-aware bundles
- file path
  `app/static/index.html`
- reason for change
  repair translate and review actions to read the current result document from `generatedDocs` and the current doc pane structure instead of the stale pre-refactor DOM selectors
- file path
  `app/providers/openai_provider.py`
- reason for change
  keep the synchronous provider API usable when invoked under an already-running event loop by offloading the `anyio.run(...)` call to a worker thread
- file path
  `tests/test_procurement_store.py`
- reason for change
  add targeted serialization and persistence coverage for the new procurement state store
- file path
  `tests/test_project_management.py`
- reason for change
  make existing project API regression tests hermetic against the current API key header and local env loading so Milestone 1 validation is meaningful, add Milestone 2 project-scoped procurement opportunity import and retrieval coverage, add Milestone 3 procurement evaluation route coverage, and add Milestone 4 procurement recommendation route coverage
- file path
  `tests/test_procurement_decision_service.py`
- reason for change
  add deterministic Milestone 3 and Milestone 4 evaluation coverage for clear high-fit, conditional-fit, blocking hard-fail, insufficient-data, recommendation, and checklist cases
- file path
  `tests/test_procurement_bundle_handoff.py`
- reason for change
  add Milestone 5 targeted coverage for bid-decision bundle registration, project-scoped decision bundle generation and export, and automatic downstream handoff into `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr`
- file path
  `tests/test_gov_bundles.py`
- reason for change
  extend existing government-bundle structural and integration coverage to include `bid_decision_kr`
- file path
  `tests/test_bundle_specs.py`
- reason for change
  update built-in bundle registry expectations to account for the new `bid_decision_kr` bundle
- file path
  `tests/e2e/conftest.py`
- reason for change
  bootstrap a real authenticated user and suppress onboarding so the e2e lane matches the current login-gated home bootstrap
- file path
  `tests/e2e/test_main_flow.py`
- reason for change
  align the baseline UI flow with the current login, sketch-confirm, translate/review modal, export, and CSP-safe waiting behavior
- file path
  `tests/test_generate.py`
- reason for change
  verify `/generate` accepts the UI's optional `style_profile_id` payload
- file path
  `tests/test_sketch_endpoint.py`
- reason for change
  verify `/generate/sketch` accepts the UI's optional `style_profile_id` payload
- file path
  `tests/async_helper.py`
- reason for change
  provide a loop-safe helper for running awaitables from sync tests under the current pytest environment
- file path
  `tests/test_billing.py`, `tests/test_g2b.py`, `tests/test_local_provider.py`, `tests/test_metrics_alerting.py`, `tests/test_notifications.py`, `tests/test_pdf_endpoint.py`, `tests/test_security.py`, `tests/test_style_system.py`
- reason for change
  replace fragile direct `asyncio.run(...)` or `anyio` runner assumptions with the shared loop-safe test helper and make the local LLM endpoint fixture hermetic

---

## Demo / smoke notes

The initiative now exposes an executable project-detail procurement workflow through `POST /projects/{project_id}/imports/g2b-opportunity`, `GET /projects/{project_id}/procurement`, `POST /projects/{project_id}/procurement/evaluate`, `POST /projects/{project_id}/procurement/recommend`, and project-scoped `POST /generate/stream` generation for `bid_decision_kr`, `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr`. Validation is closed through targeted regression tests, E2E coverage, full `pytest tests/ -q`, and successful dev `deploy-smoke` execution.

---

## Release notes draft

Internal only. Public Procurement Go/No-Go Copilot is now fully integrated into DecisionDoc AI as a project-scoped upstream decision workflow. Users can attach a public opportunity to a project, run deterministic Go/Conditional-Go/No-Go evaluation with structured evidence and checklist output, generate `bid_decision_kr`, and hand the resulting context directly into `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` without creating a parallel document or approval system. Post-closeout hardening also stabilized live dev rollout behavior, public shell/PWA delivery, and warning-free test verification.

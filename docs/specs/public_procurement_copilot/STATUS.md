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

### 2026-04-16 — Post-generation slide_outline guidance now repairs procurement-grounded PPT metadata

- Background:
  - Procurement PDF normalization and prompt grounding were already generating `페이지 분류`, `PPT 페이지 설계 힌트`, and `발표/PPT 후보 페이지`, but the final provider output could still return slide metadata that ignored or under-filled those hints.
  - This left a gap between procurement page classification and the actual structured PPT contract used by `proposal_kr` / `performance_plan_kr`.
- What changed:
  - added a parser for the normalized procurement context block so downstream services can recover page-classification, page-design-hint, and PPT-candidate metadata from the injected text
  - updated the generation post-processing path to repair `slide_outline` items when procurement context exists:
    - backfill `visual_type`, `layout_hint`, `visual_brief`
    - append procurement-grounded evidence lines
    - synthesize a minimal fallback outline when the provider omits the slide list entirely
- Impact:
  - `proposal_kr` and `performance_plan_kr` PPT design output is now materially more likely to stay aligned with real procurement source pages even when the model under-specifies slide metadata
  - the fix is additive and isolated to the generation/stabilizer phase; provider implementations and route contracts remain unchanged
- Validation:
  - added parser tests for normalized procurement context round-tripping
  - added generation-service tests covering slide metadata backfill and fallback outline synthesis

### 2026-04-16 — Procurement page classifier now prioritizes schedule/process/governance signals over broad evaluation keywords

- Background:
  - Real kickoff/evaluation PDFs often repeat broad words such as `평가` and `경영평가` on every page.
  - That caused schedule and process pages to be misclassified as `평가기준/지표`, which in turn dropped `일정 및 마일스톤` candidates and let generic provider visuals survive.
- What changed:
  - reordered procurement page classification so `일정`, `로드맵`, `마일스톤`, `절차`, `프로세스`, `조직`, `거버넌스` signals win before broad evaluation keywords
  - updated slide-outline repair logic so procurement hints can override generic provider visuals when the matched procurement page is strong enough
- Impact:
  - schedule pages now generate `타임라인` guidance and `일정 및 마일스톤` candidate slides more reliably
  - evaluation/criteria pages keep `평가기준 표` guidance even when the provider initially emits a generic comparison layout
- Validation:
  - added classifier regression coverage for real-world `경영평가추진일정` headings
  - extended slide-outline repair tests so procurement hints override already-filled generic visual metadata

### 2026-04-16 — Document-ingestion path now reuses procurement summary blocks during slide_outline repair

- Background:
  - `/generate/from-documents` merges procurement normalization into the freeform `context` string rather than passing `_procurement_context` as a first-class request field.
  - Without a recovery step, procurement-aware slide repair only applied when project handoff injected `_procurement_context` directly.
- What changed:
  - generation post-processing now detects the normalized procurement summary block directly from `context` when `_procurement_context` is absent
  - title replacement logic was tightened so generic or partially matched slide titles are renamed to procurement-grounded `candidate_label — detail` titles when the source page hint is more specific
- Impact:
  - uploaded procurement PDFs now influence final `slide_outline` output even on document-ingestion routes, not only on project-linked handoff routes
  - generated PPT guide tables are more likely to expose concrete procurement page topics such as 평가 지표 체계 or 세부 추진 일정

### 2026-04-06 — Fresh-stack preflight corrected for create-path validation

- Background:
  - `deployment_suffix=-green` fresh-stack workaround was already merged, but `deploy-smoke [dev-green]` still failed in preflight because the workflow always executed `lambda UpdateFunctionCode --dry-run` even when the suffixed stack did not exist yet.
  - In practice this blocked the intended "new stack/function create" validation path and reduced fresh-stack deploys back to the same AWS-side Lambda update restriction seen on in-place stage stacks.
- What changed:
  - updated `.github/workflows/deploy-smoke.yml` so the preflight records whether the stack exists
  - when `decisiondoc-ai-<stage><suffix>` does not exist, the workflow now skips `UpdateFunctionCode` dry-run and proceeds directly to `SAM build` / `SAM deploy`
  - documented the corrected fresh-stack contract in deploy/prod runbooks
- Impact:
  - `deploy-smoke [dev-green]` and other suffixed first-deploy runs now validate the actual create path instead of failing early on an update-only API
  - existing non-suffixed or already-created stack behavior is unchanged: stack rollback state is still checked first and mutability dry-run still applies to existing stacks

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

---

## Post-launch quality loop baseline

- added a reusable quality operations guide:
  - `docs/specs/public_procurement_copilot/QUALITY.md`
- added a labeling template for future procurement eval cases:
  - `tests/fixtures/procurement/procurement_eval_labeling_template.json`
- baseline regression fixture now carries `slice_tags` for future slice-based analysis
- regression test coverage now includes a fixture contract guard so recommendation labels, score status values, and slice tags stay structured as the eval set grows
- regression fixture baseline expanded to 12 labeled procurement cases with minimum bucket/slice coverage checks
- added a read-only fixture summary report script:
  - `scripts/procurement_eval_summary.py`
- added a tenant-scoped read-only runtime quality view:
  - `GET /admin/tenants/{tenant_id}/procurement-quality-summary`
  - runtime view now includes recommendation follow-through and `NO_GO` override candidate summary derived from project documents
  - runtime view now also includes recent procurement / approval audit activity for investigation context
- added project-scoped override reason capture:
  - `POST /projects/{project_id}/procurement/override-reason`
  - persists a structured override reason block into the existing procurement `notes` field for later investigation
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
- Notification unread-count polling now stays off on unauth/login screens, stops on logout and hidden tabs, and only resumes on visible restore according to the existing SSE/polling fallback rules
- Public shell and PWA routes now support `HEAD` as well as `GET`, which keeps browser/probe/header-only checks off the earlier `405` path
- `deploy-smoke` now has an optional procurement smoke lane that reuses the existing procurement endpoints plus the existing `/approvals` and `/share` routes to verify post-deploy procurement flow closure
- The optional procurement smoke lane now retries stale G2B bid/detail targets through raw-number, detail-URL, and live-discovery fallbacks, and downgrades exhausted all-`404` upstream drift to `SKIP` instead of failing the whole deploy lane
- Existing structured logs now carry procurement-specific action, score, recommendation, checklist, and downstream handoff signals so post-launch quality analysis can start from current observability paths without adding a new analytics subsystem
- A labeled procurement regression fixture set now exists to guard deterministic recommendation drift offline
- Test verification is now warning-free: JWT short-key fixtures, `datetime.utcnow()` fixture usage, deprecated uvicorn websocket startup in the E2E fixture, and fixed-port E2E server binding have all been cleaned up
- `main` release-line verification now includes both dev and prod `deploy-smoke` runs with `include_procurement_smoke=true`, and prod `/version` continues to expose `features.procurement_copilot=true`
- Latest verified branch closeout commits:
  - `6974114` — public shell `HEAD` support
  - `163214f` — JWT/UTC test warning cleanup
  - `f2d18e6` — E2E websocket warning cleanup
  - `fe4a695` — dynamic E2E port allocation
  - `91a2840` — optional procurement smoke G2B upstream-drift skip hardening

---

## Next-step development plan

- Initiative complete:
  future work, if any, should be tracked as post-launch tuning or follow-up tasks rather than new milestone work inside this plan
- Current post-launch direction:
  stabilization is prioritized over feature expansion; the shipped follow-up work now covers notification polling closeout, repeatable procurement smoke, and procurement decision observability/regression guards

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
- date/time:
  2026-03-28 00:20:00 KST
- milestone:
  Post-launch follow-up — procurement smoke release-line hardening
- commands run:
  `python3 -m py_compile scripts/smoke.py tests/test_smoke_script.py`
  `.venv/bin/pytest -q tests/test_smoke_script.py`
  `.venv/bin/pytest tests/ -q --tb=short`
  GitHub Actions `deploy-smoke` run `23658292888` on `codex/g2b-upstream-retry-hardening`
  GitHub Actions `deploy-smoke` run `23658635203` on `main` (`stage=dev`, `include_procurement_smoke=true`)
  GitHub Actions `deploy-smoke` run `23659665533` on `main` (`stage=prod`, `include_procurement_smoke=true`)
  `curl -i -s https://m06niff7bj.execute-api.ap-northeast-2.amazonaws.com/health`
  `curl -s https://m06niff7bj.execute-api.ap-northeast-2.amazonaws.com/version`
- result:
  targeted procurement smoke regression tests passed (`4 passed`)
  full suite passed (`1637 passed, 3 skipped`)
  branch and `main` release-line `deploy-smoke` verification passed on both `dev` and `prod`
  prod `/health` returned `200`, and prod `/version` confirmed `features.procurement_copilot=true`
- notes:
  hardened optional procurement smoke against external G2B fixture drift without masking non-`404` regressions, then verified the merged behavior on both dev and prod release lines

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

---

## Post-launch hardening follow-up — NO_GO downstream override enforcement

- what changed
  - added a narrow server-side generation guard for project-scoped procurement downstream handoff
  - when procurement recommendation is `NO_GO`, `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` now require a saved override reason before generation proceeds
  - the generate contract now returns `409` with `code=procurement_override_reason_required`, `project_id`, `bundle_type`, `recommendation`, and `focus_field`
  - the project-detail procurement panel now surfaces that error, focuses the override textarea, and keeps downstream buttons available once a recommendation exists so the policy is enforced by the server instead of a silent UI dead-end
  - the procurement schemas now normalize both enum inputs and string inputs under `strict=True`, so current service code, stores, and tests remain compatible
  - bid-decision mock bundle output now keeps a longer procurement context excerpt so latest snapshot / missing-data evidence continues to appear in rendered docs
- file path
  - `app/routers/generate.py`
- reason for change
  - enforce the quality-loop rule at the actual downstream generation boundary without changing unrelated generate flows
- file path
  - `app/static/index.html`
- reason for change
  - show the new downstream block naturally in the reused project-detail procurement panel and steer users into override reason capture
- file path
  - `app/schemas.py`
- reason for change
  - reconcile strict procurement models with the enum-based service/test usage already present in the repository
- file path
  - `app/providers/mock_provider.py`
- reason for change
  - keep procurement handoff evidence visible in bid-decision docs after the stricter downstream enforcement pass
- file path
  - `tests/test_project_management.py`
- reason for change
  - add backend contract coverage for blocked `NO_GO` downstream generation and the allowed path after override reason capture
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - add a single project-detail E2E path proving the blocked downstream click focuses the override reason input
- validation
  - `.venv/bin/pytest -q tests/test_project_management.py`
  - `.venv/bin/pytest -q tests/test_tenant.py`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k project_detail_blocks_no_go_downstream_until_override_reason`
  - `.venv/bin/pytest -q tests/test_procurement_bundle_handoff.py`
  - `.venv/bin/pytest -q tests/ --tb=short`

---

## Post-launch hardening follow-up — blocked override-required attempts in quality loop

- what changed
  - promoted `409 procurement_override_reason_required` generate failures into a dedicated audit action `procurement.downstream_blocked`
  - when the block happens on `/generate*`, audit logs now keep the linked `project_id`, `bundle_type`, `error_code`, and `recommendation`
  - tenant procurement quality summary now counts that blocked action and links it back into override candidate `latest_activity` / `recent_events`
- file path
  - `app/routers/generate.py`
- reason for change
  - attach procurement project context to blocked downstream attempts before the request exits so later audit aggregation can attribute the event correctly
- file path
  - `app/middleware/audit.py`
- reason for change
  - record override-required downstream failures as a procurement-specific operational signal instead of a generic document generation failure
- file path
  - `app/routers/admin.py`
- reason for change
  - reuse the existing admin quality summary activity flow so operations can see blocked attempts without introducing a new summary subsystem
- file path
  - `tests/test_audit.py`
- reason for change
  - verify both helper resolution and end-to-end audit logging for blocked downstream attempts
- file path
  - `tests/test_tenant.py`
- reason for change
  - verify procurement quality summary now includes blocked downstream attempts in action counts and override candidate activity
- validation
  - `.venv/bin/pytest -q tests/test_audit.py`
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
  - `.venv/bin/pytest -q tests/test_project_management.py -k 'generate_stream_blocks_no_go_downstream_without_override_reason or generate_stream_allows_no_go_downstream_after_override_reason_saved'`

---

## Post-launch hardening follow-up — admin location summary surfaces blocked attempts

- what changed
  - added an admin-auth location endpoint for procurement quality summary so the browser admin flow can consume the same tenant summary builder without requiring an ops key in the UI
  - extended the location management card with a procurement quality modal that reuses the existing summary data to show blocked downstream counts, override candidate investigation context, and recent quality-loop events
  - recent procurement activity payloads now include linked project names, so blocked events are traceable in the admin modal without forcing operators to map raw ids by hand
- file path
  - `app/routers/admin.py`
- reason for change
  - expose the existing procurement quality summary through the authenticated admin surface already used by the location management flow
- file path
  - `app/static/index.html`
- reason for change
  - reuse the existing location/admin summary flow to make blocked override-required downstream attempts visible and actionable in the browser
- file path
  - `tests/test_tenant.py`
- reason for change
  - verify the new admin-auth route returns the same procurement summary payload as the ops-key endpoint
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify an admin can open the location procurement modal and see blocked downstream activity in the rendered summary
- validation
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k locations_page_shows_procurement_quality_summary`

---

## Post-launch hardening follow-up — admin summary jumps into project override flow

- what changed
  - added direct action buttons inside the location procurement summary modal so operators can jump from a blocked event or override candidate straight into the existing project detail flow
  - blocked downstream events now open project detail and focus the override reason textarea, while other items open the relevant project detail without introducing a parallel remediation screen
- file path
  - `app/static/index.html`
- reason for change
  - turn the admin quality summary from a read-only signal into an actionable handoff back into the reused project detail / procurement panel workflow
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify the admin can open the modal, jump into the relevant project, and land directly on the override reason input for a blocked downstream case
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'locations_page_shows_procurement_quality_summary or location_procurement_summary_opens_project_override_flow'`

---

## Post-launch hardening follow-up — project detail keeps admin remediation context

- what changed
  - added a small remediation strip inside the reused project detail procurement panel when the operator arrives from the location procurement quality summary
  - blocked downstream events now preserve their quality-loop context in project detail with bundle/error chips, an explicit remediation message, a direct jump back to the override textarea, and a dismiss action
  - override candidate jumps reuse the same mechanism so the admin handoff does not lose why the project was opened
- file path
  - `app/static/index.html`
- reason for change
  - keep the admin summary → project detail handoff actionable without introducing a separate remediation screen or forcing the operator to infer why they were sent to the project
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify the blocked downstream jump shows the remediation strip in project detail, preserves textarea focus, and allows the operator to dismiss the context after landing
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k location_procurement_summary_opens_project_override_flow`

---

## Post-launch hardening follow-up — blocked downstream remediation can retry inline

- what changed
  - when a blocked downstream event is opened from the admin/location procurement summary, saving an override reason now upgrades the remediation strip from "why you are here" into a same-screen retry CTA for the blocked bundle
  - once the retry succeeds, the remediation strip is cleared and the project detail status message confirms the blocked bundle was retried, so the admin loop closes without another round-trip through the summary modal
- file path
  - `app/static/index.html`
- reason for change
  - close the highest-friction quality-loop gap after policy enforcement: operators should not have to manually infer when a blocked bundle is now retryable or hunt for the correct downstream button after recording the override reason
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify the blocked downstream path now supports override save → retry CTA → successful downstream document creation in one reused project-detail flow
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'location_procurement_summary_opens_project_override_flow or location_procurement_summary_blocked_event_retries_after_override_reason'`

---

## Post-launch hardening follow-up — admin summary tracks resolved override handoffs

- what changed
  - successful downstream generation on a `NO_GO` project that already has an override reason is now audited as a separate procurement action instead of disappearing into a generic generate success
  - tenant/location procurement quality summary now counts that resolved handoff signal and exposes it through recent activity so operators can see both blocked attempts and closed-loop retries in the same view
  - the location procurement modal reuses that signal with a dedicated KPI card and activity label, so the admin loop shows not only backlog but also resolution throughput
- file path
  - `app/routers/generate.py`
  - `app/middleware/audit.py`
  - `app/routers/admin.py`
  - `app/storage/audit_store.py`
  - `app/static/index.html`
- reason for change
  - once inline retry was available, the next gap was operational visibility: admins could see blocks but not whether those blocks were later resolved after override capture
- file path
  - `tests/test_audit.py`
  - `tests/test_tenant.py`
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify helper resolution, end-to-end audit logging, admin summary aggregation, and browser visibility for the new resolved-handoff signal
- validation
  - `.venv/bin/pytest -q tests/test_audit.py -k 'procurement_downstream'`
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k location_procurement_summary_blocked_event_retries_after_override_reason`
  - `.venv/bin/pytest -q tests/ --tb=short`

---

## Post-launch hardening follow-up — admin summary exposes active follow-up backlog

- what changed
  - override candidate summary now distinguishes project-level remediation state instead of treating all `NO_GO + downstream` cases as a flat bucket
  - admin/location procurement summary now separates:
    - `needs_override_reason`
    - `ready_to_retry`
    - `resolved`
  - candidate ordering now pushes unresolved follow-up to the top so the modal highlights active backlog before already-resolved cases
  - the location modal now surfaces backlog-specific KPI cards and copy for unresolved follow-up, retry-ready projects, and resolved handoffs
- file path
  - `app/routers/admin.py`
  - `app/static/index.html`
- reason for change
  - blocked/resolved counts alone still forced operators to infer which project needed action now versus which project had already been closed out after override capture
  - same-second save timing exposed a contract gap: note-embedded override timestamps only carried second precision, so a later save could still look older than the blocked audit event; retry-readiness detection now prefers the audited `procurement.override_reason` timestamp when available
- file path
  - `tests/test_tenant.py`
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify backend status aggregation/sorting and one-path browser visibility for blocked event → override save → retry-ready candidate → resolved handoff
- validation
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'locations_page_shows_procurement_quality_summary or location_procurement_summary_blocked_event_retries_after_override_reason'`

---

## Post-launch hardening follow-up — retry-ready navigation clears stale remediation UI

- what changed
  - jumping from the location procurement summary back into project detail now clears the previously rendered project-detail DOM before loading the next remediation context, so operators do not briefly see stale blocked-event strips while opening a retry-ready candidate
  - retry success now clears remediation context not only for blocked-event entries but also for `ready_to_retry` override candidates, so the strip is removed after the downstream retry actually closes the backlog
- file path
  - `app/static/index.html`
- reason for change
  - the previous loop closed operationally, but the reused SPA detail panel could still retain stale remediation UI between admin-summary hops, and retry-ready candidate retries left the strip visible even after success
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify the retry-ready candidate path shows the correct remediation copy and that the strip detaches after a successful downstream retry
- validation
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k location_procurement_summary_blocked_event_retries_after_override_reason`

---

## Post-launch hardening follow-up — project detail can return directly to location quality summary

- what changed
  - when an operator opens project detail from the location procurement quality summary, the reused project detail header now keeps a direct return CTA back to the same tenant's quality summary modal
  - the return CTA survives override save and downstream retry success, so admins can confirm the backlog moved to `resolved` without manually switching pages and reopening the modal
  - standard project-list entry now clears that return context, keeping the CTA specific to the admin quality-loop handoff instead of leaking into ordinary project browsing
- file path
  - `app/static/index.html`
- reason for change
  - the loop already supported summary → remediation → retry, but operators still had to navigate back manually to verify the final summary state; this kept the quality loop technically closed but operationally slower than necessary
- file path
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify the blocked-event remediation path can round-trip back into the same tenant summary modal after retry success and immediately show the resolved state
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k location_procurement_summary_blocked_event_retries_after_override_reason`

---

## Post-launch hardening follow-up — summary return highlights the just-remediated project

- what changed
  - when project detail returns to the tenant's procurement quality summary, the modal now highlights the same project card or recent-event item and scrolls it into view automatically
  - the highlighted item carries a small `방금 확인한 프로젝트` chip so operators can confirm the resolved or retry-ready state without scanning the whole backlog again
  - when that just-remediated project would normally fall outside the modal's top `override candidate` or `recent event` slice, the UI now swaps it into the visible subset so the highlight still appears instead of silently disappearing behind truncation
  - the admin/location procurement summary route now accepts `focus_project_id`, and the backend keeps at least one recent event for that project inside `recent_events` even when the default top-10 audit truncation would otherwise drop it
  - the same focus query now returns a dedicated `focused_project` payload, and the modal renders it as a compact focus card so operators keep a stable anchor even if the project is not an override candidate and only survives through the focused-event include path
  - focused project fallback no longer depends entirely on `AuditStore.query(... )[:1000]`; the admin summary now uses an append-order latest-entry lookup to recover the newest matching project or approval event even when it has already fallen outside the capped audit query window
  - focused project fallback now also rehydrates `remediation_status`, blocked/resolved bundle metadata, and a minimal `latest_activity` list for the focus card, so an old `NO_GO` project does not fall back to a stale `monitor` state merely because its follow-up audit entries are outside the capped dashboard window
  - the same uncapped follow-up hydration now also feeds tenant-wide `override_candidates` and `override_candidate_status_counts`, so older `NO_GO + downstream` projects do not quietly remain in stale `monitor` backlog buckets just because their blocked/resolved audit trail fell outside the capped summary query
  - admin procurement summary activity counts now also read from the uncapped audit view, so high-volume tenants do not silently lose older procurement blocked/resolved/import actions from `action_counts` while the rest of the quality loop is already using hydrated follow-up state
  - override candidate payloads now include `followup_updated_at` and `followup_reference_kind`, and the admin summary sorts same-status candidates by the newest follow-up timestamp instead of falling back to project-name ordering
  - the location procurement modal now shows an explicit `운영 기준` line for both the focused project card and override candidates, so operators can see whether the current priority is driven by a recent block, override save, resolved retry, or general activity
  - summary outcomes now also expose `oldest_unresolved_followup`, and the modal surfaces that item above the cards so operators can see the longest-waiting unresolved project even while the main candidate list stays sorted by the freshest same-status follow-up
  - the oldest unresolved hint now reuses the same remediation context wiring as override candidates, so operators can jump directly from that hint into the existing project detail / override or retry path instead of scanning the list first
  - the location procurement modal now also exposes an ordering toggle between `최신 follow-up 순` and `오래된 미해소 순`, so operators can temporarily switch from the default freshest-signal view into a stale-first queue inside the same summary flow
  - that ordering toggle persists across the existing project-detail return path, so once an operator flips into stale-first triage they do not have to re-toggle after opening an unresolved candidate and coming back to the same tenant summary
  - the location/admin procurement summary routes now also accept `candidate_view=stale_unresolved`, and the modal uses that query on reopen/return so stale-first triage is backed by the same server contract instead of only a client-side reorder of the current payload
- file path
  - `app/routers/admin.py`
  - `app/storage/audit_store.py`
  - `app/static/index.html`
- reason for change
  - direct summary return removed one navigation step, but operators still had to visually search the modal for the same project; highlighting the returning project reduces that last manual step inside the quality loop
  - the previous implementation still had a slice-size hole: returning to a tenant with many resolved candidates could hide the just-remediated project outside the top 4/5 cards even though highlight context existed
  - there was still a server-side gap for older activity: if the returning project was not an override candidate and its last event had already fallen out of the backend top-10 list, the client had nothing left to highlight
  - a stable focus card keeps the admin loop legible even when the visible lists change category or only retain the project through the focused-event fallback
  - the remaining gap was the audit-store cap itself: very active tenants could still lose the focused project's latest event once it fell behind the newest 1000 rows, so the summary needed a project-scoped fallback that did not change the existing capped query behavior for general dashboards
  - after recovering only `latest_event`, the remaining operator risk was stale follow-up labeling: an older `NO_GO` project could still render as `monitor` even though its blocked/resolved audit trail existed outside the capped query set, which made the focused summary anchor less trustworthy
  - the same stale-label problem also affected the backlog itself: even if a focused card could recover the right state, the tenant-wide candidate list and follow-up counts still stayed wrong, which weakened the admin quality loop as an operational queue
  - once backlog hydration was fixed, the next inconsistency was aggregate activity telemetry: the same high-volume tenant could still show incorrect blocked/resolved action counts because `activity.action_counts` was built from the capped audit query instead of the full tenant audit view
  - after backlog and KPI accuracy were aligned, the next operator gap was prioritization: unresolved candidates were still effectively ordered by status then project name, which made busy admin queues harder to triage than necessary
  - even after shifting same-status ordering to follow-up recency, operators still lacked an explicit signal for the oldest unresolved item, which is often the one that needs escalation or manual follow-up first
  - once that hint existed, the next gap was actionability: operators could see the oldest unresolved item but still had to locate its card in the list to start remediation, which added avoidable friction to the loop
  - even with the actionable oldest hint, the main candidate list still stayed optimized for freshest follow-up only; operators who wanted to clear stale backlog first had no way to temporarily reorder the queue inside the same modal
  - after adding the toggle, the remaining consistency risk was that stale-first ordering still lived only in browser state; reopening the modal or returning from project detail should use the same server-backed candidate view to avoid drifting from the backend summary contract
- file path
  - `tests/test_audit.py`
  - `tests/test_tenant.py`
  - `tests/e2e/test_main_flow.py`
- reason for change
  - verify the new audit-store latest-entry helper can still find a matching procurement event after the regular capped query has already dropped it
  - verify the browser-facing location summary route re-includes an older focused project event when `focus_project_id` is supplied
  - verify the same focus route still rehydrates `resolved` follow-up state and blocked/resolved bundle metadata for an older `NO_GO` project after the shared backlog hydration logic is applied
  - verify tenant-wide override candidate status counts now also rehydrate that older `NO_GO` project to `resolved`, eliminating the stale `monitor` backlog bucket instead of only fixing the focused return card
  - verify tenant-wide activity counts also retain older blocked/resolved procurement actions after more than 1000 newer audit rows are appended, so admin quality KPI cards stay aligned with the restored backlog state
  - verify same-status override candidates are now ordered by the latest follow-up timestamp and expose that timestamp in the response contract
  - verify the modal renders an explicit `운영 기준` line in the retry-ready summary path so the new time-axis signal is visible to operators, not just present in the JSON
  - verify the response contract also exposes the oldest unresolved follow-up item and that the modal renders the corresponding `가장 오래 미해소 follow-up` hint in the unresolved path
  - verify the same hint now includes a direct CTA into the remediation flow, so the oldest unresolved item can be opened without scanning the candidate list first
  - verify the modal can switch unresolved candidates into `오래된 미해소 순`, open the oldest retry-ready project from that reordered list, and preserve the stale-first mode after returning from project detail
  - verify the browser-facing location summary route also honors `candidate_view=stale_unresolved` so the stale-first queue is not just a client-side sort of the default payload
  - verify the browser-facing location summary route also honors `candidate_scope=unresolved_only`, so operators can drop resolved or monitor noise without changing the aggregate backlog KPI counts
  - verify the modal preserves both the stale-first ordering and the unresolved-only scope after opening a retry-ready project and returning to the quality summary
  - verify `candidate_scope=unresolved_only` now narrows the recent activity list to the same unresolved queue, while still re-including the focused project event during remediation return so operators do not lose context after a successful retry
  - verify the modal now surfaces scope-aware queue metrics for `unresolved_only`, so operators can read the visible candidate/event counts without confusing them with the tenant-wide aggregate KPI cards
  - verify the same queue strip now exposes a direct `전체 candidate 보기` CTA whenever unresolved-only is hiding resolved or monitor candidates, so operators can reopen the broader queue without manually hunting for the scope toggle after remediation
  - verify `resolved_only` scope is now available in the summary contract and modal, so operators can review closed-loop follow-through without mixing it back into the unresolved queue
  - verify `monitor_only` scope is now available in the summary contract and modal, so operators can review watch-list style `NO_GO` candidates separately from active unresolved remediation and already resolved follow-through
  - verify `review_only` scope is now available in the summary contract and modal, so operators can review the combined resolved-plus-monitor backlog without mixing it back into the active unresolved remediation queue
  - verify `candidate_statuses` multi-select filtering now composes with the existing scope contract and modal state, so operators can further narrow queue or review backlog slices by remediation status without adding another preset per combination
  - verify the summary contract now exposes scope-aware remediation status counts and the modal renders those counts directly on the status filter chips, so operators can see the impact of a status filter before clicking it
  - verify the summary contract now also exposes scope-aware activity counts and the modal surfaces them as a compact `현재 범위 활동` strip, so filtered queue activity no longer has to be inferred from tenant-wide aggregate KPI cards
  - verify filtered scope/status views now render a dedicated `현재 범위 queue KPI` strip above the tenant-wide cards, so operators can read scoped candidate/event/blocked/retry/resolved counts without mentally separating them from the aggregate dashboard cards
  - verify recent-event filtering now supports server-backed `activity_actions`, so operators can isolate blocked, override-save, resolved, or evaluation events inside the current queue/review scope without disturbing the candidate list
  - verify the modal now exposes quick triage presets for retry queue, resolved review, and monitor review, so operators can jump into common procurement follow-up slices without manually recombining scope, remediation status, and activity filters each time
  - verify switching scope after a preset now drops incompatible remediation-status filters instead of leaving the target queue empty, so `review backlog 보기` and similar scope CTAs keep working after `retry queue` style presets
  - verify the location procurement modal now persists each tenant's last triage view in localStorage, so reopening the same tenant after the previous in-memory modal state is gone restores the last scope, order, status-filter, and activity-filter combination instead of dropping back to a generic default
  - verify default location-card entry now restores tenant-scoped saved preferences only for that tenant, which closes the remaining gap where modal-level triage presets were useful but still session-bound
  - verify the location procurement modal now mirrors the open tenant, focus project, candidate view, scope, and filters into URL query params, so the same triage view can survive refresh or be re-opened from a deep-link instead of only relying on browser-local preferences
  - verify closing the modal or jumping into project detail clears those procurement summary query params again, so the locations review deep-link does not leak into unrelated page states
  - verify the modal now surfaces a `현재 review 링크 복사` CTA that copies the live URL-backed tenant/filter state, so operators can hand the exact procurement triage slice to another reviewer without asking them to recombine the same scope/status/activity controls manually
  - verify the summary-to-detail jump now rewrites the remediation context and summary return state into project-detail URL params, so the blocked-event remediation strip and `거점 조달 품질 요약으로` CTA survive a refresh or in-memory reset after leaving the modal
  - verify returning from a URL-restored project detail now reopens the same tenant summary with the stored queue view and filters instead of reusing stale global modal state, so the remediation round-trip stays deterministic even after browser state loss
  - verify project detail remediation strips now surface a `현재 remediation 링크 복사` CTA that copies the exact `project_procurement_*` URL state, so operators can hand off a blocked-event or override-candidate investigation without first bouncing back through the tenant summary
  - verify the copied project detail remediation link preserves both the project-specific remediation context and the summary return tenant marker, so the recipient can restore the same detail context and still jump back into the correct quality-summary queue
  - verify focused-project cards, override candidates, and recent events in the tenant summary now surface a direct `remediation 링크 복사` CTA, so operators can hand off a specific blocked-event or review candidate without first opening project detail
  - verify summary-level remediation link copy builds the exact `project_procurement_*` deep-link without mutating the live `location_procurement_*` review URL in the current page, so queue review can continue uninterrupted after a handoff copy
  - verify remediation link copy now also posts a lightweight `procurement.remediation_link_copied` audit signal with source/context metadata, so quality-summary recent events and action counts can show that a blocked or review case was actually handed off instead of only inferring it from later retries
  - verify the tenant summary can filter and render that new remediation-link-share activity, including whether the copy originated from `tenant summary` or `project detail` and which remediation context (`blocked remediation`, `override candidate`, `recent event`) was handed off
  - verify URL-restored project-detail remediation views now also post a lightweight `procurement.remediation_link_opened` audit signal, so shared handoff links are tracked when another operator actually opens the remediation context instead of only when the link was copied
  - verify the tenant summary can filter and render that new remediation-link-open activity separately from link share, including the `shared link restore` source label and the inherited remediation context metadata
  - verify the blocked-event remediation path still highlights the same project after downstream retry success even when four alphabetically earlier resolved candidates already occupy the default visible slice
- verify the return modal now also renders a focused-project card, not just list-level highlighting
- validation
  - `.venv/bin/pytest -q tests/test_audit.py -k find_latest_entry_bypasses_query_cap`
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k location_procurement_summary_blocked_event_retries_after_override_reason`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k location_procurement_summary_can_toggle_stale_first_override_candidates`

## 2026-04-01 — Remediation Handoff Queue And Release Closeout

- shipped
  - admin/location procurement quality summary now derives an explicit remediation handoff queue from existing audit events plus current follow-up hydration, without introducing any new persistence layer
  - the new queue groups cases by `project_id + procurement_context_kind + bundle_type + error_code + recommendation` and surfaces:
    - `shared_not_opened`
    - `opened_unresolved`
    - `opened_resolved`
  - focused project cards and the summary modal now show handoff lifecycle copy directly, while reusing the existing project detail remediation CTA, remediation link copy CTA, and current review link copy CTA
  - the existing recent-event filters, candidate scopes, project detail remediation strip, and URL/local preference review-state model remain intact; the new handoff review path is layered on top of them instead of introducing a separate saved-view subsystem
  - release docs now treat the current procurement copilot as a `post-launch ops hardening + release closeout` surface, not an open-ended product expansion track
- file path
  - `app/routers/admin.py`
  - `app/static/index.html`
  - `tests/test_tenant.py`
  - `tests/e2e/test_main_flow.py`
  - `docs/specs/public_procurement_copilot/QUALITY.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
  - `docs/deploy_aws.md`
- reason for change
  - recent activity already showed remediation link copy/open events, but operators still had to infer whether a shared case was never opened, opened but still unresolved, or opened and fully resolved
  - a dedicated handoff queue closes that operator gap using the existing audit trail and remediation status model, which keeps blast radius small and avoids adding server-side saved preset or shared-view persistence
  - release-complete for this feature is now defined as keeping the current admin quality loop, project detail remediation flow, audit evidence, and URL handoff stable enough to run and verify in production, then documenting that closeout explicitly
- completion criteria
  - import/evaluate/recommend/generate/approval/share were not widened
  - procurement quality loop now covers blocked attempt, remediation handoff, opened-unresolved investigation, and opened-resolved follow-through inside the existing UI and audit contract
  - runbook and quality docs now name the handoff lifecycle as a first-class weekly review target
  - no new persistence model was introduced
- validation
  - `.venv/bin/pytest -q tests/test_audit.py -k 'remediation_link or procurement_remediation'`
    - `4 passed, 48 deselected`
  - `.venv/bin/pytest -q tests/test_tenant.py -k procurement_quality_summary`
    - `9 passed, 28 deselected`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'location_procurement_summary_opens_project_override_flow or location_procurement_summary_blocked_event_retries_after_override_reason or location_procurement_summary_can_toggle_stale_first_override_candidates' --tb=short`
    - `3 passed, 27 deselected`
  - `.venv/bin/pytest -q tests/ --tb=short`
    - `1693 passed, 3 skipped`
  - external procurement smoke / deployed manual sanity
    - skipped in this turn because no configured external stage/env was available from the local workspace session

## 2026-04-01 — Procurement Smoke Covers Remediation Handoff Lifecycle

- shipped
  - `scripts/smoke.py` now extends the optional procurement smoke lane with a release-closeout remediation check when the live recommendation resolves to `NO_GO`
  - the scripted path reuses existing APIs only:
    - downstream `proposal_kr` block without override reason
    - remediation link copy/open audit endpoints
    - project-scoped override reason save
    - downstream retry success
    - procurement quality summary handoff queue, preferring the ops-key tenant route when available
  - no new persistence model was introduced; the new sub-check is conditional and now prefers the existing ops-key tenant summary route, logging `SKIP` only when the recommendation is not `NO_GO` or no summary access path is available
- file path
  - `scripts/smoke.py`
  - `tests/test_smoke_script.py`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - release-closeout had already documented remediation handoff as a first-class operational loop, but the optional scripted smoke still stopped at decision-doc generation plus approval/share
  - adding the smallest possible audit-derived handoff verification makes the deploy lane check the same blocked → shared → opened → resolved lifecycle the admin summary now exposes, without widening procurement scope or adding a new subsystem
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/smoke.py tests/test_smoke_script.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_smoke_script.py -k procurement --tb=short`
    - `4 passed, 2 deselected`

## 2026-04-03 — Decision Council v0 UI And Procurement Handoff Closure

- shipped
  - `Decision Council v0` is now exposed in the existing project-detail procurement panel instead of remaining backend-only
  - the panel accepts a user goal plus optional context/constraints, runs the existing procurement-scoped deterministic council API, and renders:
    - latest recommended direction
    - disagreements
    - top risks
    - structured role opinions
    - generation handoff cues
  - the same panel now exposes an explicit `Council handoff로 의사결정 문서 생성` CTA that reuses the existing `bid_decision_kr` generation path
  - project detail now loads the latest council session only when procurement context is eligible, so the UI stays narrow and project-scoped
  - project-linked `bid_decision_kr` rows now surface Decision Council provenance tags (`Council v0`, revision, direction), which makes the already-added backend provenance visible in the existing project document list
  - procurement README/runbook/quality docs now describe the council step as part of the real release-complete workflow instead of leaving it implicit
- file path
  - `app/static/index.html`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/QUALITY.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
  - `docs/deploy_aws.md`
  - `tests/e2e/test_main_flow.py`
- reason for change
  - the backend thin slice already supported deterministic council runs and `bid_decision_kr` handoff injection, but the product still lacked a first-class project-detail entrypoint for entering the user goal, reviewing the structured council output, and visibly carrying provenance into generated project documents
  - the smallest correct closure is to reuse the existing procurement panel and project-doc list rather than adding a new screen, a second review system, or a generic orchestration shell
- completion criteria
  - council remains procurement/G2B only
  - council remains deterministic and API-first
  - `bid_decision_kr` generation path remains the existing `/generate/stream` + project auto-link path
  - approval/share/export flows remain unchanged
  - documentation now covers runtime UX, quality loop, and deploy/manual smoke expectations
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council or procurement_panel or project_detail_shows_procurement or location_procurement_summary_opens_project_override_flow or location_procurement_summary_blocked_event_retries_after_override_reason' --tb=short`
    - `6 passed, 26 deselected`
  - `.venv/bin/pytest -q tests/test_decision_council.py tests/test_project_management.py -k 'decision_council or bid_decision_generation_uses_decision_council_handoff_and_project_provenance' --tb=short`
    - `6 passed, 101 deselected`

## 2026-04-03 — Procurement Smoke Verifies Decision Council Provenance

- shipped
  - `scripts/smoke.py` now runs `POST /projects/{project_id}/decision-council/run` inside the optional procurement smoke lane before `bid_decision_kr` generation
  - the same smoke lane now fails if the auto-linked project document does not keep the latest council provenance:
    - `source_decision_council_session_id`
    - `source_decision_council_session_revision`
    - `source_decision_council_direction`
  - the existing `NO_GO` remediation handoff smoke remains unchanged after the council step and still validates `shared_not_opened -> opened_unresolved -> opened_resolved`
- file path
  - `scripts/smoke.py`
  - `tests/test_smoke_script.py`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the deploy runbook had already documented Decision Council as part of the procurement release path, but the optional scripted smoke still skipped that route and never checked whether the generated `bid_decision_kr` document actually preserved council provenance
  - aligning the scripted smoke with the documented runtime flow closes that last release-gap without widening product scope, adding persistence, or touching approval/share/export behavior
- validation
  - `.venv/bin/pytest -q tests/test_smoke_script.py -k 'procurement or council' --tb=short`
    - `5 passed, 2 deselected`

## 2026-04-03 — Decision Council Stale Guard And Audit Primary Action Fix

- shipped
  - `bid_decision_kr` generation no longer injects a stale council session purely by `project_id/use_case/target_bundle_type`
  - the latest council handoff now applies only when the stored session still matches the current procurement record by:
    - `source_procurement_decision_id`
    - `source_procurement_updated_at`
    - active `opportunity + recommendation` eligibility
  - successful `/generate*` requests now keep `doc.generate` as the primary audit action even when procurement override resolution or Decision Council handoff metadata is present
  - procurement resolved and council handoff signals are still preserved as supplemental audit entries, so existing admin/ops summaries keep working without dropping legacy document-generation metrics
- file path
  - `app/schemas.py`
  - `app/services/decision_council_service.py`
  - `app/services/generation_service.py`
  - `app/middleware/audit.py`
  - `tests/test_decision_council.py`
  - `tests/test_project_management.py`
  - `tests/test_audit.py`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - stale Decision Council reuse could diverge from the current procurement recommendation/checklist state because procurement updates keep the same `decision_id` while replacing the record contents
  - the previous audit override logic also rewrote `doc.generate` into `decision_council.handoff_used` or `procurement.downstream_resolved`, which would silently break existing generation metrics and consumers
- validation
  - `.venv/bin/pytest -q tests/test_decision_council.py tests/test_project_management.py -k 'decision_council or stale' --tb=short`
    - `7 passed, 101 deselected`
  - `.venv/bin/pytest -q tests/test_audit.py -k 'decision_council or downstream_resolved or supplemental_actions' --tb=short`
    - `7 passed, 50 deselected`

## 2026-04-03 — Decision Council Freshness Contract Surfaced In Project Detail

- shipped
  - `GET /projects/{project_id}/decision-council` and `POST /projects/{project_id}/decision-council/run` now return explicit procurement-binding metadata:
    - `current_procurement_binding_status`
    - `current_procurement_binding_reason_code`
    - `current_procurement_binding_summary`
  - the same binding metadata is derived from current procurement state at response time instead of being persisted as canonical council state, so API callers can distinguish:
    - current council handoff
    - stale council handoff that must be rerun
  - the existing project-detail procurement panel now renders a stale-council warning when the latest saved session no longer matches the current procurement recommendation/checklist state
  - the same panel now disables `Council handoff로 의사결정 문서 생성` for stale sessions and switches the primary CTA to `Decision Council 다시 실행`
  - if a linked `bid_decision_kr` row exists, the panel now clarifies that it was generated from an earlier council state instead of implying it still matches the latest procurement recommendation
- file path
  - `app/schemas.py`
  - `app/storage/decision_council_store.py`
  - `app/services/decision_council_service.py`
  - `app/services/generation_service.py`
  - `app/routers/projects.py`
  - `app/static/index.html`
  - `tests/test_decision_council.py`
  - `tests/test_project_management.py`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/QUALITY.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the stale-injection guard fixed incorrect council reuse at generation time, but the API/UI still made the stored session look current, which could mislead operators into believing the next `bid_decision_kr` would use that outdated handoff
  - surfacing freshness through the response contract and existing project-detail panel closes that operator-facing gap without adding new persistence, touching approval/share/export, or widening Decision Council into a broader workflow product
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile app/schemas.py app/storage/decision_council_store.py app/services/decision_council_service.py app/services/generation_service.py app/routers/projects.py tests/test_decision_council.py tests/test_project_management.py tests/e2e/test_main_flow.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_decision_council.py --tb=short`
    - `4 passed`
  - `.venv/bin/pytest -q tests/test_project_management.py -k 'decision_council or stale' --tb=short`
    - `4 passed, 101 deselected`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `3 passed, 30 deselected`

## 2026-04-03 — Generation Metadata Explains Why Council Handoff Was Skipped

- shipped
  - `bid_decision_kr` generation metadata now distinguishes a missing council handoff from a stale one
  - when the latest saved council session exists but no longer matches current procurement state, generation now returns:
    - `decision_council_handoff_used=false`
    - `decision_council_handoff_skipped_reason=stale_procurement_context`
  - the same skip reason is propagated into request-scoped generate logs and `doc.generate` audit detail so API callers and ops tooling can explain why council provenance was absent without inferring it from project state separately
- file path
  - `app/services/generation_service.py`
  - `app/routers/generate.py`
  - `app/middleware/audit.py`
  - `tests/test_project_management.py`
  - `tests/test_audit.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after surfacing stale council state in the project-detail panel, API callers still only saw `decision_council_handoff_used=false` on generation responses, which did not tell them whether no saved council existed or an existing council was skipped because procurement state had changed
  - adding an explicit skip reason keeps the contract narrow while making audit/debugging and downstream client behavior deterministic
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile app/services/generation_service.py app/routers/generate.py app/middleware/audit.py tests/test_project_management.py tests/test_audit.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_project_management.py -k 'decision_council or stale' --tb=short`
    - `4 passed, 101 deselected`
  - `.venv/bin/pytest -q tests/test_audit.py -k 'decision_council or stale or supplemental_actions' --tb=short`
    - `6 passed, 52 deselected`

## 2026-04-03 — Stale Council Warning Now Shows Source And Current Procurement Drift

- shipped
  - stale Decision Council responses now include the council-run baseline:
    - `source_procurement_recommendation_value`
    - `source_procurement_missing_data_count`
    - `source_procurement_action_needed_count`
    - `source_procurement_blocking_hard_filter_count`
  - the same response now also includes the current procurement snapshot at read time:
    - `current_procurement_recommendation_value`
    - `current_procurement_missing_data_count`
    - `current_procurement_action_needed_count`
    - `current_procurement_blocking_hard_filter_count`
  - the project-detail stale warning now renders concrete drift cues such as:
    - `당시 권고안 GO → 현재 NO_GO`
    - current `action needed`
    - current `missing data`
- file path
  - `app/schemas.py`
  - `app/storage/decision_council_store.py`
  - `app/services/decision_council_service.py`
  - `app/static/index.html`
  - `tests/test_decision_council.py`
  - `tests/test_project_management.py`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous stale warning correctly blocked council-assisted generation, but it still forced operators to infer what had changed by scanning the rest of the procurement panel
  - surfacing the source council baseline and current procurement drift directly in the stale alert makes rerun decisions explainable without broadening Decision Council into a second review workflow
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile app/schemas.py app/storage/decision_council_store.py app/services/decision_council_service.py app/static/index.html tests/test_decision_council.py tests/test_project_management.py tests/e2e/test_main_flow.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_decision_council.py --tb=short`
    - `4 passed`
  - `.venv/bin/pytest -q tests/test_project_management.py -k 'decision_council or stale' --tb=short`
    - `4 passed, 101 deselected`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `3 passed, 30 deselected`

## 2026-04-03 — Stale Council Warning Now Shows When The Drift Happened

- shipped
  - stale Decision Council responses now include `current_procurement_updated_at`
  - the project-detail stale alert now shows the council baseline time and current procurement update time together:
    - `council 기준 YYYY-MM-DD → 현재 procurement YYYY-MM-DD`
  - this makes it clear not just that the handoff is stale, but when the currently visible procurement state moved beyond the saved council
- file path
  - `app/schemas.py`
  - `app/storage/decision_council_store.py`
  - `app/services/decision_council_service.py`
  - `app/static/index.html`
  - `tests/test_decision_council.py`
  - `tests/test_project_management.py`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after showing source/current recommendation drift, operators still had to infer the timing of the mismatch by reading separate timestamps elsewhere in the panel
  - adding the council baseline time and current procurement updated time keeps the stale warning self-contained and makes rerun urgency easier to judge
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile app/schemas.py app/storage/decision_council_store.py app/services/decision_council_service.py tests/test_decision_council.py tests/test_project_management.py tests/e2e/test_main_flow.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_decision_council.py tests/test_project_management.py -k 'decision_council or stale' --tb=short`
    - `8 passed, 101 deselected`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `3 passed, 30 deselected`

## 2026-04-03 — Project Document List Now Marks Current vs Outdated Council Docs

- shipped
  - the existing project detail document list now reuses the same council freshness contract instead of only showing static provenance tags
  - council-backed `bid_decision_kr` rows are now labeled as:
    - `현재 council 기준`
    - `이전 council revision (rN)`
    - `현재 procurement 대비 이전 council 기준`
  - the linked `bid_decision_kr` copy inside the Decision Council panel now also uses the same status logic, so the latest linked doc no longer implies freshness when the saved council is stale or behind the latest revision
- file path
  - `app/static/index.html`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - even after the stale council warning was made explicit, operators still had to infer whether the already-generated `bid_decision_kr` row itself was current or outdated
  - surfacing the same council freshness state directly on the document row closes that last gap without adding a new screen or widening the API contract
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `pass`

## 2026-04-03 — Project Detail API Now Exposes Council Document Freshness

- shipped
  - `GET /projects/{project_id}` now adds explicit council freshness metadata to council-backed `bid_decision_kr` rows:
    - `decision_council_document_status`
    - `decision_council_document_status_tone`
    - `decision_council_document_status_copy`
    - `decision_council_document_status_summary`
  - the route uses the same latest-session + procurement-binding contract as the project-detail council panel instead of making API callers re-derive freshness client-side
  - the UI still keeps its local fallback logic, but now prefers the route-provided metadata when it exists
- file path
  - `app/services/decision_council_service.py`
  - `app/routers/projects.py`
  - `app/static/index.html`
  - `tests/test_project_management.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous document-row status work only lived in the browser, so API consumers still could not tell whether a council-backed `bid_decision_kr` row was current, behind the latest council revision, or stale against current procurement state without duplicating UI logic
  - lifting that status into the existing project-detail response keeps the contract explicit while staying additive and project-scoped
- validation
  - `.venv/bin/pytest -q tests/test_project_management.py -k 'decision_council or stale or revision' --tb=short`
    - `pass`

## 2026-04-03 — Outdated Council Docs Now Guard Approval And Share Actions

- shipped
  - stale council-backed `bid_decision_kr` rows now expose a direct follow-up CTA in the existing project document actions:
    - `Council 다시 실행`
    - `최신 기준으로 재생성`
    - `현재 council 확인`
  - the same outdated rows now show a confirm guard before `결재 요청` or `공유` continues, so operators do not push an outdated council-backed decision doc into the existing review/share flow without seeing the mismatch
  - current council-backed rows keep the existing approval/share flow unchanged and do not show a follow-up CTA
- file path
  - `app/static/index.html`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after adding row-level freshness labels, the remaining operator gap was execution: stale council-backed docs could still be sent into approval/share with the same one-click actions as current docs
  - adding a narrow confirm guard preserves the existing lifecycle while making the outdated-state risk explicit at the handoff boundary
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `pass`

## 2026-04-03 — Approval Request Modal Keeps Stale Council Warning Visible

- shipped
  - project-document approval request source now carries council document freshness metadata for stale council-backed `bid_decision_kr` rows
  - after accepting the outdated-doc confirm, the approval request modal now still shows the same council warning inside the modal instead of dropping the context
  - that warning also includes a direct follow-up CTA back to the relevant council action, so operators can exit the approval request and jump straight to rerun/regenerate from the same boundary
- file path
  - `app/static/index.html`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous confirm guard prevented accidental approval/share clicks, but once an operator accepted the confirm and entered the approval modal, the outdated council context disappeared
  - keeping the warning visible inside the modal makes the stale-state risk explicit all the way through the approval boundary without changing the approval lifecycle itself
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `pass`

## 2026-04-03 — Share Link Modal Keeps Stale Council Warning Visible

- shipped
  - project-document share source now carries the same council document freshness metadata used by the project detail row and approval request modal
  - after accepting the outdated-doc confirm, the share-link modal now still shows the same stale council warning instead of implying that the newly copied share URL is current
  - the share-link modal warning also keeps the same direct follow-up CTA back to the relevant council action so operators can close the modal and jump straight to rerun or regeneration
- file path
  - `app/static/index.html`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous confirm guard made the stale-state risk explicit before sharing, but once the share modal opened, the outdated council context disappeared again
  - keeping the warning visible inside the share-link modal closes the last handoff gap without widening the share lifecycle or adding a new UI surface
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `pass`

## 2026-04-03 — Public Shared Page Now Preserves Stale Council Warning

- shipped
  - `/share` now stores optional council document freshness metadata when a council-backed project document is shared
  - `/shared/{share_id}` now reuses that metadata to render the same stale council warning on the public shared-document page instead of implying that the shared link is always current
  - generic share links remain unchanged because the warning block only renders when council freshness metadata is present and not `current`
- file path
  - `app/schemas.py`
  - `app/storage/share_store.py`
  - `app/routers/history.py`
  - `app/static/index.html`
  - `tests/test_phase3_features.py`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous share-link modal warning made the risk explicit only for the person creating the link; once the recipient opened `/shared/{id}`, the stale council context disappeared again
  - carrying the same warning into the public share page closes the last provenance gap in the existing share flow without introducing a new share model or a new approval/export path
- validation
  - `.venv/bin/pytest -q tests/test_phase3_features.py -k 'share' --tb=short`
    - `pass`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council' --tb=short`
    - `pass`

## 2026-04-03 — Share Audit Now Preserves Council Freshness Context

- shipped
  - `POST /share` now copies optional council document freshness metadata into `request.state` before audit logging
  - `share.create` audit entries now preserve:
    - `share_decision_council_document_status`
    - `share_decision_council_document_status_tone`
    - `share_decision_council_document_status_copy`
    - `share_decision_council_document_status_summary`
  - generic share links remain unchanged because these detail fields are only populated when council-backed project documents provide freshness metadata
- file path
  - `app/routers/history.py`
  - `app/middleware/audit.py`
  - `tests/test_audit.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after preserving stale council context in the share modal and public shared page, the remaining traceability gap was operations: `share.create` still looked generic in audit logs
  - carrying the same freshness signal into audit closes that gap without changing the share lifecycle or adding a new audit action
- validation
  - `.venv/bin/pytest -q tests/test_audit.py -k 'share_create_and_revoke_logged' --tb=short`
    - `pass`

## 2026-04-03 — Procurement Summary Now Flags Stale External Shares

- shipped
  - project-document sharing now sends optional `project_id` / `project_document_id` alongside council freshness metadata when a council-backed doc is shared
  - admin procurement quality summary now treats stale council-backed `share.create` as a procurement activity signal:
    - it appears in `recent_events`
    - it participates in `scope_action_counts` / `visible_action_counts`
    - it is filterable through the existing activity-action chips
  - only stale council-backed `bid_decision_kr` shares are included, so generic share links and current council shares do not add noise to the procurement review surface
- file path
  - `app/schemas.py`
  - `app/routers/history.py`
  - `app/middleware/audit.py`
  - `app/routers/admin.py`
  - `app/static/index.html`
  - `tests/test_audit.py`
  - `tests/test_tenant.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after preserving stale council context in the share modal, public share page, and share audit detail, operators still had to open raw audit logs to notice that an outdated council-backed doc had been shared externally
  - lifting that signal into the existing procurement recent-event/activity-filter surface keeps the review loop inside the current admin summary instead of inventing a new queue
- validation
  - `.venv/bin/pytest -q tests/test_audit.py -k 'share_create_and_revoke_logged' --tb=short`
    - `pass`
  - `.venv/bin/pytest -q tests/test_tenant.py -k 'procurement_quality_summary and stale_share' --tb=short`
    - `pass`

## 2026-04-03 — Procurement Summary Adds External Share Review Preset

- shipped
  - the existing procurement summary preset bar now adds `외부 공유 review (N)` when stale council-backed external share activity exists
  - the preset reuses the current server-backed activity filter model by applying `activity_actions=share.create` without introducing a new scope, queue, or saved-view persistence
  - local modal state, URL state, and existing filter copy all continue to work because the preset is layered on top of the existing activity-action filter mechanism
- file path
  - `app/static/index.html`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after stale external shares became visible in recent events, operators still had to manually click the `share.create` activity chip to isolate them
  - adding one preset keeps the triage path as fast as the existing handoff/retry/resolved review presets and avoids introducing a separate queue model
- validation
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'stale_share_review or locations_page_shows_procurement_quality_summary or location_procurement_summary_blocked_event_retries_after_override_reason' --tb=short`
    - `pass`

## 2026-04-03 — Procurement Summary Derives A Stale External Share Queue

- shipped
  - the admin/location procurement quality summary now derives a dedicated `외부 공유 재확인 queue` from stale council-backed `share.create` audit entries
  - queue items are keyed by `project_id + share_project_document_id` and preserve the latest stale external share per project document
  - the `외부 공유 review (N)` preset now follows that same unique queue count instead of raw event volume, while the queue header still shows cumulative stale `share.create` event count as a separate context metric
  - the queue surfaces:
    - project/document linkage
    - latest external share timestamp
    - latest stale-share actor and stale-share count
    - live share-link state (`share_id`, public `share_url`, active/inactive, access count, last public access, expiry)
    - council freshness drift copy (`stale_procurement`, `stale_revision`)
    - the same stale-share summary text already shown in recent activity
  - active public links now sort ahead of inactive or missing-record links, and the queue header breaks out active/inactive/missing-record counts so operators can prioritize live external exposure first
  - active stale links with recorded public access now sort ahead of active-but-unopened links, and the queue header breaks those counts apart as `최근 public 열람 있음` vs `아직 열람 없음`
  - when any active stale public link remains, the procurement summary modal now raises a top-level exposure alert with an `외부 공유 review 열기` CTA that activates the existing stale-share preset directly
  - the locations overview card now consumes `/admin/locations?include_procurement=1` and surfaces the same active stale-share exposure as a compact risk strip, including a direct `외부 공유 review` CTA before the operator opens the full procurement modal
  - the locations overview snapshot now comes from a dedicated stale-share aggregation path instead of rebuilding the full procurement summary per tenant card, while keeping the same `include_procurement=1` contract
  - the locations overview grid now also sorts tenants with active stale public exposure ahead of normal tenants, and among exposed tenants it lifts recently accessed stale public links first
  - the locations overview card now also surfaces the top stale shared document with live share-link state plus direct `공유 링크 열기` and `공유 링크 복사` actions
  - the same card now also surfaces the latest stale-share actor, timestamp, and cumulative stale-share count for that top document, so operator handoff does not require opening the modal first
  - the same card now also exposes `외부 공유 review 링크`, which copies the tenant-wide stale-share review URL with the existing stale-share activity filter preserved
  - active stale public links can now be revoked directly from the locations overview card and the stale-share review modal by reusing the existing `DELETE /share/{share_id}` flow, and admin operators are allowed to revoke stale links even when another user created them
  - the same card now also exposes `위험 문서 review`, which opens the summary already focused on the top stale shared project while keeping the stale-share activity filter active
  - the same card now also exposes `위험 문서 review 링크`, which copies the exact internal procurement-summary review URL with tenant, focused project, and stale-share filter preserved
  - focused project cards now also expose the latest stale external share item when present
  - the queue intentionally reuses only existing actions:
    - project open
    - current review link copy
    - shared link open
    - shared link copy
- file path
  - `app/routers/admin.py`
  - `app/static/index.html`
  - `tests/test_tenant.py`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the new preset made stale external shares easy to isolate, but operators still had to scan raw recent events to reconstruct which exact project document was last shared on an outdated council basis
  - deriving a compact queue closes that gap without introducing another persistence model or widening the share workflow
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile app/routers/admin.py tests/test_tenant.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_tenant.py -k 'procurement_quality_summary and stale_share' --tb=short`
    - `pass`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'stale_share_review or locations_page_shows_procurement_quality_summary or location_procurement_summary_blocked_event_retries_after_override_reason' --tb=short`
    - `pass`
  - `.venv/bin/pytest -q tests/test_tenant.py -k 'procurement_quality_summary and stale_share' --tb=short`
    - `1 passed, 37 deselected`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'stale_share_review or locations_page_shows_procurement_quality_summary or location_procurement_summary_blocked_event_retries_after_override_reason' --tb=short`
    - `3 passed, 31 deselected`

## 2026-04-04 — Local Stale-Share Demo Seed For Direct Operator Verification

- shipped
  - a dedicated local helper script now seeds one deterministic stale-share demo into a fresh `DATA_DIR`
  - the helper creates:
    - one system admin login
    - one council-backed `bid_decision_kr` project document
    - one later procurement update that makes the saved council stale
    - one active stale public share with one recorded public access
    - one clean contrast tenant so the locations overview risk ordering is visible immediately
  - the helper prints:
    - seeded login credentials
    - tenant-wide stale-share review URL
    - focused stale-share review URL
    - exact public `/shared/{id}` URL
  - a companion verifier script now checks a running local app against that seeded state:
    - admin login
    - locations overview stale-share exposure
    - focused stale-share procurement summary
    - stale Decision Council binding
    - public shared-page warning
  - a one-command launcher now starts local `uvicorn`, waits for `/health`, runs the seed helper, runs the verifier, and optionally keeps the app alive for manual checks
  - the launcher now also writes a deterministic demo manifest into the chosen `DATA_DIR` and can optionally open the focused internal review URL plus the exact public share URL in a browser
  - the helper intentionally rejects a non-empty `DATA_DIR` because append-only audit/share state would otherwise make the stale-share counts noisy and non-deterministic
- file path
  - `scripts/seed_procurement_stale_share_demo.py`
  - `scripts/check_procurement_stale_share_demo.py`
  - `scripts/run_procurement_stale_share_demo.py`
  - `tests/test_procurement_demo_seed.py`
  - `tests/test_procurement_demo_verify.py`
  - `tests/test_procurement_demo_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the stale-share review flow was already closed inside the product, but local reproduction still required manual store edits or brittle ad-hoc setup
  - adding one deterministic seed helper lets operators and reviewers boot a fresh local demo and verify the real UI flow directly without widening the product surface
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/seed_procurement_stale_share_demo.py tests/test_procurement_demo_seed.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_procurement_demo_seed.py --tb=short`
    - `pass`
  - `DATA_DIR=/tmp/decisiondoc-stale-share-demo-check .venv/bin/python scripts/seed_procurement_stale_share_demo.py --data-dir /tmp/decisiondoc-stale-share-demo-check --base-url http://127.0.0.1:8765`
    - `pass`
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/check_procurement_stale_share_demo.py tests/test_procurement_demo_verify.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_procurement_demo_verify.py --tb=short`
    - `pass`
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_procurement_stale_share_demo.py tests/test_procurement_demo_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_procurement_demo_run.py --tb=short`
    - `pass`

## 2026-04-04 — Decision Council v1 Proposal-First Expansion Closed

- shipped
  - the stored canonical procurement council session remains keyed to `target_bundle_type=bid_decision_kr`, but the same latest session is now reused for both:
    - `bid_decision_kr`
    - `proposal_kr`
  - `GET /projects/{project_id}/decision-council` now exposes `supported_bundle_types=["bid_decision_kr","proposal_kr"]`
  - generation metadata and audit detail now distinguish:
    - the stored council source bundle via `decision_council_target_bundle=bid_decision_kr`
    - the actual applied downstream bundle via `decision_council_applied_bundle`
  - current procurement binding validation remains unchanged:
    - `opportunity + recommendation` must exist
    - `source_procurement_decision_id` must still match
    - `source_procurement_updated_at` must still match
  - if that binding is stale, both `bid_decision_kr` and `proposal_kr` generation now skip council handoff with:
    - `decision_council_handoff_used=false`
    - `decision_council_handoff_skipped_reason=stale_procurement_context`
  - the project-detail procurement panel now treats Decision Council as `v1` and exposes proposal-first generation alongside the existing bid-decision path
  - council-backed `proposal_kr` project documents now reuse the same freshness contract, stale warnings, follow-up CTA, approval/share confirm guard, modal warning, public shared-page warning, and stale external share triage path as council-backed `bid_decision_kr`
  - stale external share review and admin overview now preserve bundle-level labeling so operators can distinguish `의사결정 문서` from `제안서` without creating a new queue model
  - the optional procurement smoke lane now validates proposal-first council provenance and the local OpenSpace bridge remains docs/skill scaffolding only; no runtime OpenSpace dependency was introduced
  - request-level audit for `/generate/stream` is now deferred until the stream finishes so stale council skip reason and applied-bundle metadata are preserved in the primary `doc.generate` entry without duplicating generate counts
  - the share HTML regression test now reads from the app-scoped share store path instead of a bare default store, which makes full-suite execution stable under mixed `DATA_DIR` test runs
- file path
  - `app/schemas.py`
  - `app/storage/decision_council_store.py`
  - `app/services/decision_council_service.py`
  - `app/services/generation_service.py`
  - `app/routers/generate.py`
  - `app/middleware/audit.py`
  - `app/routers/admin.py`
  - `app/routers/projects.py`
  - `app/domain/schema.py`
  - `app/static/index.html`
  - `scripts/smoke.py`
  - `tests/test_decision_council.py`
  - `tests/test_project_management.py`
  - `tests/test_audit.py`
  - `tests/test_tenant.py`
  - `tests/test_smoke_script.py`
  - `tests/test_phase3_features.py`
  - `tests/e2e/test_main_flow.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/QUALITY.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
  - `docs/deploy_aws.md`
  - `docs/openspace_integration.md`
  - `.agents/skills/decisiondoc-openspace-bootstrap/SKILL.md`
  - `.agents/skills/decisiondoc-openspace-docgen/SKILL.md`
  - `.agents/skills/decisiondoc-openspace-eval/SKILL.md`
- reason for change
  - Decision Council v0 closed the pre-generation decision step for `bid_decision_kr`, but proposal drafting still depended only on generic procurement handoff and lacked the same provenance, stale guard, and operator review visibility
  - extending the existing canonical session to `proposal_kr` preserves the current project/approval/share/export model while closing the actual downstream operator gap
  - the stream audit fix was required because proposal-first observability would otherwise look complete in structured logs but remain missing in persisted audit records
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile app/schemas.py app/storage/decision_council_store.py app/services/decision_council_service.py app/services/generation_service.py app/routers/generate.py app/middleware/audit.py app/routers/admin.py app/routers/projects.py app/routers/history.py scripts/smoke.py tests/test_decision_council.py tests/test_project_management.py tests/test_audit.py tests/test_tenant.py tests/test_smoke_script.py tests/test_phase3_features.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_audit.py::test_audit_logs_stale_decision_council_skip_reason_on_generate --tb=short`
    - `1 passed`
  - `.venv/bin/pytest -q tests/test_decision_council.py tests/test_project_management.py tests/test_audit.py tests/test_tenant.py tests/test_smoke_script.py tests/test_phase3_features.py -k 'decision_council or stale_share or share or procurement_quality_summary or procurement' --tb=short`
    - `79 passed, 156 deselected`
  - `.venv/bin/pytest -q tests/e2e/test_main_flow.py -k 'decision_council or stale_share_review or locations_page_shows_procurement_quality_summary' --tb=short`
    - `5 passed, 30 deselected`
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile tests/test_phase3_features.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_phase3_features.py::test_shared_view_returns_html --tb=short`
    - `1 passed`
  - `.venv/bin/pytest -q tests/ --tb=short`
    - `1728 passed, 3 skipped`

## 2026-04-04 — Local Demo Shifted To Proposal-First Council Stale Share

- shipped
  - the local stale-share seed/verify/launcher flow now makes the stale public share target the council-backed `proposal_kr` document instead of the older bid-only path
  - the same seeded project still includes both:
    - one council-backed `bid_decision_kr` document
    - one council-backed `proposal_kr` document
  - both documents reuse the same canonical Decision Council session so local manual verification now demonstrates the real `Decision Council v1` contract instead of only the older bid-decision subset
  - the focused review URL still lands on the existing stale-share review preset, but the top stale share is now expected to be the `proposal_kr` document
  - the verifier now proves that the live overview and focused summary agree on that proposal bundle identity before checking the stale public shared-page warning
  - the launcher manifest now includes the shared bundle id plus both linked project document ids so operators can confirm proposal-first provenance without opening the JSON stores directly
- file path
  - `scripts/seed_procurement_stale_share_demo.py`
  - `scripts/check_procurement_stale_share_demo.py`
  - `scripts/run_procurement_stale_share_demo.py`
  - `tests/test_procurement_demo_seed.py`
  - `tests/test_procurement_demo_verify.py`
  - `tests/test_procurement_demo_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the product surface had already expanded to proposal-first council handoff, but the local demo still reproduced only a stale `bid_decision_kr` share, which meant the most recent v1 behavior could not be confirmed directly from the provided launcher
  - shifting the seeded stale share to `proposal_kr` closes that gap while keeping the same deterministic local verification flow and without introducing any new runtime path
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/seed_procurement_stale_share_demo.py scripts/check_procurement_stale_share_demo.py scripts/run_procurement_stale_share_demo.py tests/test_procurement_demo_seed.py tests/test_procurement_demo_verify.py tests/test_procurement_demo_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_procurement_demo_seed.py tests/test_procurement_demo_verify.py tests/test_procurement_demo_run.py --tb=short`
    - `3 passed`
  - `DATA_DIR=/tmp/decisiondoc-stale-share-demo-v1-proposal .venv/bin/python scripts/run_procurement_stale_share_demo.py --data-dir /tmp/decisiondoc-stale-share-demo-v1-proposal --port 8881 --exit-after-verify`
    - `pass`
    - live output confirmed:
      - shared bundle id = `proposal_kr`
      - the seeded project includes both council-backed bid/proposal document ids
      - overview/focused review/public share verification all passed against the live app

## 2026-04-04 — Local Demo Browser Playtest Helper Added, Live Modal Restore Still Open

- shipped
  - the local launcher now supports `--playtest-ui` so the seeded proposal-first stale-share demo can be browser-checked in one command
  - the browser helper first attempts the exact focused internal review URL from the manifest, then falls back to the same app action behind `거점 관리 -> 위험 문서 review` when direct modal restore is not visible in time
  - the playtest verifies:
    - stale `proposal_kr` focus card copy
    - `Decision Council v1` panel visibility
    - disabled proposal regenerate CTA under stale procurement binding
    - public `/shared/{id}` stale warning
- file path
  - `scripts/playtest_procurement_stale_share_demo.py`
  - `scripts/run_procurement_stale_share_demo.py`
  - `tests/test_procurement_demo_playtest.py`
  - `tests/test_procurement_demo_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - API-level seed and verifier checks were already green, but local operators still had to manually click through the focused stale-share review path to confirm the actual browser surface
  - the direct review URL can race the modal restore path on a cold browser boot, so the helper needed a bounded fallback to the real locations-card CTA instead of failing the whole run
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/playtest_procurement_stale_share_demo.py scripts/run_procurement_stale_share_demo.py tests/test_procurement_demo_playtest.py tests/test_procurement_demo_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_procurement_demo_playtest.py tests/test_procurement_demo_run.py tests/test_procurement_demo_seed.py tests/test_procurement_demo_verify.py --tb=short`
    - `6 passed`
  - live `--playtest-ui` runs on fresh data dirs continue to expose a remaining UI flake:
    - API seed + verifier portions pass
    - the helper now retries through authenticated in-app stale-share review open, re-login, and modal-visibility fallbacks
    - browser phase still times out after the stale-share summary fetch when modal actionability does not stay stable
    - manual `--open-browser` verification remains the reliable local operator path until that UI restore contract is tightened

## 2026-04-05 — Local Demo Browser Playtest Closed

- shipped
  - the local demo `--playtest-ui` path now completes end-to-end against a fresh seeded stale-share demo
  - the playtest helper dismisses onboarding before project-detail navigation and uses forced project-open click semantics so the onboarding overlay no longer intercepts the focused review handoff
  - the same run still verifies the stale `proposal_kr` focus card, `Decision Council v1` panel, disabled proposal regenerate CTA, and public `/shared/{id}` stale warning
- file path
  - `scripts/playtest_procurement_stale_share_demo.py`
  - `tests/test_procurement_demo_playtest.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the remaining blocker was no longer modal restore itself; the focused review surface rendered, but the onboarding overlay intercepted the project-open CTA during the live playtest
  - tightening the helper was the narrowest fix because the production stale-share flow was already correct and the failure lived in the demo/browser verification path
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/playtest_procurement_stale_share_demo.py tests/test_procurement_demo_playtest.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_procurement_demo_playtest.py tests/test_procurement_demo_run.py tests/test_procurement_demo_seed.py tests/test_procurement_demo_verify.py --tb=short`
    - `6 passed`
  - `DATA_DIR=/tmp/decisiondoc-stale-share-demo-v1-ui-18 .venv/bin/python scripts/run_procurement_stale_share_demo.py --data-dir /tmp/decisiondoc-stale-share-demo-v1-ui-18 --port 8900 --exit-after-verify --playtest-ui`
    - `pass`
    - live output confirmed:
      - seeded API verification passed
      - browser playtest completed
      - focused review and public share screenshots were written under `output/playwright/procurement-stale-share-demo/`

## 2026-04-06 — Fresh Full Suite Re-verified After Local Demo Close-Out

- shipped
  - no new product surface was added in this step; the goal was to refresh the strongest local verification gate after the demo/browser close-out work
  - the repo-wide pytest gate was rerun from a fresh local session so the latest Decision Council v1, proposal-first stale-share triage, and local demo helper changes are backed by an up-to-date full-suite result
- file path
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous full-suite evidence (`1728 passed, 3 skipped`) predated the final local demo browser-playtest closure
  - after the helper and docs moved again, the strongest relevant next step was to refresh the repo-wide regression baseline instead of adding more feature surface
- validation
  - `.venv/bin/pytest -q tests/ --tb=short`
    - `1731 passed, 3 skipped in 760.53s (0:12:40)`
  - scope note:
    - this rerun includes the targeted procurement, council, stale-share, smoke-script, e2e, and demo-playtest tests already covered in the repo suite
    - external stage/env deploy smoke remains outside this local verification pass

## 2026-04-06 — Fresh Local Runtime Smoke Re-verified

- shipped
  - no new feature surface was added in this step; the goal was to refresh the local runtime smoke path after the full-suite rerun
  - a fresh local `uvicorn` app was started with `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=1`, mock provider, local storage, and a clean `DATA_DIR`, then the repo smoke script was run against that live server
- file path
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - repo-wide pytest proves the code-level regression surface, but the release-closeout path in this repo also expects a live runtime smoke for auth, generate, and export endpoints
  - external deploy smoke is still environment-bound, so the strongest available next step in this local session was to refresh the local live `scripts/smoke.py` evidence
- validation
  - `DECISIONDOC_ENV=dev DECISIONDOC_PROVIDER=mock DECISIONDOC_STORAGE=local DATA_DIR=/tmp/decisiondoc-local-release-smoke DECISIONDOC_API_KEY=local-smoke-api-key JWT_SECRET_KEY=test-local-release-smoke-secret-32chars DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=1 .venv/bin/uvicorn app.main:app --port 8901`
    - `pass`
  - `SMOKE_BASE_URL=http://127.0.0.1:8901 SMOKE_API_KEY=local-smoke-api-key SMOKE_PROVIDER=mock .venv/bin/python scripts/smoke.py`
    - `pass`
    - output confirmed:
      - `GET /health -> 200`
      - `POST /generate (no key) -> 401`
      - `POST /generate (auth) -> 200`
      - `POST /generate/export (auth) -> 200`
  - scope note:
    - procurement smoke lane was intentionally not executed in this local runtime pass because `scripts/smoke.py` requires `SMOKE_INCLUDE_PROCUREMENT=1` plus a live `SMOKE_PROCUREMENT_URL_OR_NUMBER` and working `G2B_API_KEY`
    - external stage/env deploy smoke remains outside this local verification pass

## 2026-04-06 — Procurement Smoke Lane Blocker Re-confirmed Locally

- shipped
  - no product code changed in this step; the goal was to determine whether the remaining procurement live smoke lane could be closed from the current local shell
  - the local shell still does not provide the two upstream prerequisites that `scripts/smoke.py` needs for the procurement lane:
    - `G2B_API_KEY`
    - `SMOKE_PROCUREMENT_URL_OR_NUMBER`
- file path
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after the full-suite rerun and fresh core runtime smoke pass, the remaining gap was the optional procurement smoke lane
  - before treating that lane as purely external, the local shell prerequisites were re-checked explicitly so the boundary is evidence-based rather than assumed
- validation
  - `printenv G2B_API_KEY`
    - empty / exit code `1`
  - `printenv SMOKE_PROCUREMENT_URL_OR_NUMBER`
    - empty / exit code `1`
  - `.venv/bin/pytest -q tests/test_smoke_script.py -k 'procurement or council' --tb=short`
    - `5 passed, 2 deselected`
- scope note
  - the procurement smoke implementation remains locally covered by unit tests, including the proposal-first council lane
  - the only remaining path that cannot be closed from this shell is the live upstream import lane that depends on external G2B credentials and a live bid target

## 2026-04-06 — Local Procurement Smoke Runner Added

- shipped
  - added a thin local helper that starts a fresh app instance and runs `scripts/smoke.py` with the procurement lane enabled
  - the helper is intentionally wrapper-only: it does not change runtime behavior, provider abstractions, or smoke semantics
  - it auto-wires a local API key and local ops key so the procurement NO_GO remediation summary path can be exercised without requiring an admin smoke user in the local tenant
- file path
  - `scripts/run_local_procurement_smoke.py`
  - `tests/test_local_procurement_smoke_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after closing the local demo/browser path, the remaining friction was operational: even when a user does have `G2B_API_KEY` and a live bid target, they still had to hand-compose local server env plus smoke env to run the procurement lane
  - this helper collapses that into one local command while keeping the existing `scripts/smoke.py` contract unchanged
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_local_procurement_smoke.py tests/test_local_procurement_smoke_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_local_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or local_procurement_smoke' --tb=short`
    - `7 passed, 2 deselected`
  - `.venv/bin/python scripts/run_local_procurement_smoke.py`
    - `pass` for env-missing fail-fast behavior
    - output confirmed:
      - `Missing required procurement smoke prerequisite: SMOKE_PROCUREMENT_URL_OR_NUMBER`
  - local env-missing path should fail fast with:
    - missing `SMOKE_PROCUREMENT_URL_OR_NUMBER`
    - or missing `G2B_API_KEY`

## 2026-04-06 — Procurement Smoke Runner Preflight Added

- shipped
  - extended the local procurement smoke runner with two operator-focused helper modes:
    - `--preflight`
    - `--print-env-template`
  - these modes do not start the app or touch runtime behavior; they only expose readiness state and the exact command an operator should run next
- file path
  - `scripts/run_local_procurement_smoke.py`
  - `tests/test_local_procurement_smoke_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the wrapper already collapsed local boot + smoke execution, but when credentials were missing the next operator still had to infer which env was required and what exact command shape to use
  - `--preflight` and `--print-env-template` reduce that last bit of handoff friction without expanding runtime scope
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_local_procurement_smoke.py tests/test_local_procurement_smoke_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_local_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or local_procurement_smoke' --tb=short`
    - `10 passed, 2 deselected`
  - `.venv/bin/python scripts/run_local_procurement_smoke.py --preflight`
    - current shell result: missing required procurement smoke prerequisites are printed before any server boot

## 2026-04-06 — Procurement Smoke Runner Env-File Support Added

- shipped
  - extended the local procurement smoke runner with `--env-file`
  - added a focused example file at `scripts/local_procurement_smoke.env.example`
  - the runner now uses file-provided required and optional values for:
    - procurement smoke prerequisites
    - optional smoke tenant/login values
    - local JWT secret override when desired
- file path
  - `scripts/run_local_procurement_smoke.py`
  - `scripts/local_procurement_smoke.env.example`
  - `tests/test_local_procurement_smoke_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - `--preflight` and `--print-env-template` reduced ambiguity, but operators still had to export values into the current shell before running the actual procurement smoke
  - `--env-file` closes that gap and makes the remaining external-bound step copy-edit-run instead of export-and-remember
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_local_procurement_smoke.py tests/test_local_procurement_smoke_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_local_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or local_procurement_smoke' --tb=short`
    - `10 passed, 2 deselected`
  - `.venv/bin/python scripts/run_local_procurement_smoke.py --preflight`
    - current shell still reports missing required upstream values before any server boot

## 2026-04-06 — Procurement Smoke Runner Default JWT Secret Hardened

- shipped
  - changed the local procurement smoke runner default `JWT_SECRET_KEY` to a validated local secret
  - updated the focused env example so file-based runs show the same tested local secret explicitly
  - updated runner tests and helper output so the file-based path prints the validated inline `JWT_SECRET_KEY=...` launch form
- file path
  - `scripts/run_local_procurement_smoke.py`
  - `scripts/local_procurement_smoke.env.example`
  - `tests/test_local_procurement_smoke_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the procurement smoke runner was failing before `/health` with `operation not permitted` while direct local `uvicorn` boot still worked
  - narrowing the issue showed the stable path in this workspace is to start the top-level Python process with an inline `JWT_SECRET_KEY` prefix, so the simplest reliable fix was to keep the validated default and make the helper print that exact command for file-based runs
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_local_procurement_smoke.py tests/test_local_procurement_smoke_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_local_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or local_procurement_smoke' --tb=short`
    - `pass`
  - `.venv/bin/python scripts/run_local_procurement_smoke.py --env-file /tmp/local_procurement_smoke.auto.env --preflight`
    - `pass`
  - `JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars /Users/sungjin/dev/personal/DecisionDoc-AI/.venv/bin/python /Users/sungjin/dev/personal/DecisionDoc-AI/scripts/run_local_procurement_smoke.py --env-file /tmp/local_procurement_smoke.clean.env --data-dir /tmp/decisiondoc-local-procurement-smoke-cleancheck`
    - runner reached the live procurement smoke lane end-to-end and completed successfully against the local app

## 2026-04-06 — Deployed Stage Procurement Smoke Helper Added

- shipped
  - added a thin deployed-stage helper that runs the existing `scripts/smoke.py` procurement lane against an already deployed base URL
  - added `--env-file`, `--preflight`, and `--print-env-template` so the remaining external-bound verification path is copy-edit-run instead of hand-composed `SMOKE_*` exports
  - kept runtime, auth, provider, storage, and deploy workflow semantics unchanged; this is wrapper/doc/test work only
- file path
  - `scripts/run_stage_procurement_smoke.py`
  - `scripts/stage_procurement_smoke.env.example`
  - `tests/test_stage_procurement_smoke_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - local verification is already closed, but the remaining deployed procurement smoke lane still required operators to manually compose `SMOKE_BASE_URL`, `SMOKE_API_KEY`, procurement target, and optional tenant/login values
  - the new helper makes that external stage path repeatable without broadening product/runtime scope
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_stage_procurement_smoke.py tests/test_stage_procurement_smoke_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_stage_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or stage_procurement_smoke' --tb=short`
    - `pass`
  - `.venv/bin/python scripts/run_stage_procurement_smoke.py --preflight`
    - expected fail-fast in the current shell when required deployed-stage env is missing
- remaining boundary
  - the helper is ready, but an actual deployed-stage procurement smoke run still depends on a real `SMOKE_BASE_URL`, `SMOKE_API_KEY`, `G2B_API_KEY`, and live `SMOKE_PROCUREMENT_URL_OR_NUMBER`

## 2026-04-06 — GitHub Actions Env Exporter for Stage Procurement Smoke Added

- shipped
  - added an exporter that turns `.github-actions.env` stage values into the exact deployed-stage smoke env file expected by `scripts/run_stage_procurement_smoke.py`
  - kept the deployed endpoint explicit through `--base-url`, while reusing repo-level stage secrets/vars for API key, ops key, procurement target, and optional smoke login context
- file path
  - `scripts/export_stage_procurement_smoke_env.py`
  - `tests/test_export_stage_procurement_smoke_env.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after adding the deployed-stage runner, operators still had to re-copy values that already existed in `.github-actions.env`
  - the exporter closes that last local handoff gap and makes the deployed verification flow `import -> export -> preflight -> run`
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/export_stage_procurement_smoke_env.py tests/test_export_stage_procurement_smoke_env.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_export_stage_procurement_smoke_env.py tests/test_stage_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or stage_procurement_smoke or export_stage_procurement_smoke_env' --tb=short`
    - `pass`
- remaining boundary
  - the exporter removes repo-env remapping work, but a real deployed smoke still needs:
    - a current stage `base_url`
    - live stage credentials
    - a live procurement target that has not drifted out of the upstream G2B window

## 2026-04-06 — Stage Smoke Exporter Now Resolves Base URL From Stack Output

- shipped
  - extended `scripts/export_stage_procurement_smoke_env.py` so it can resolve `SMOKE_BASE_URL` directly from the deployed stack's `HttpApiUrl` output
  - mirrored the same `aws cloudformation describe-stacks` lookup already used in `.github/workflows/deploy-smoke.yml`
  - kept manual `--base-url` support and added `--stack-name` / `--aws-region` overrides for non-default stacks or shells that do not already expose region
- file path
  - `scripts/export_stage_procurement_smoke_env.py`
  - `tests/test_export_stage_procurement_smoke_env.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after the GitHub Actions env exporter landed, the last repeated manual input was still the deployed `base_url`
  - reusing the stack output path closes that final local operator lookup step when AWS credentials are already available
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/export_stage_procurement_smoke_env.py tests/test_export_stage_procurement_smoke_env.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_export_stage_procurement_smoke_env.py tests/test_stage_procurement_smoke_run.py tests/test_smoke_script.py -k 'procurement or council or stage_procurement_smoke or export_stage_procurement_smoke_env' --tb=short`
    - `pass`
- remaining boundary
  - real deployed-stage smoke still needs valid AWS access, live stage credentials, and a current procurement target; this change only removes the manual base URL lookup step

## 2026-04-06 — Stage Runner Now Embeds GitHub Actions Export Path

- shipped
  - extended `scripts/run_stage_procurement_smoke.py` so it can consume `.github-actions.env` directly through `--github-actions-env-file`
  - the runner now reuses the stage exporter internally, including `--resolve-base-url-from-stack`, `--stack-name`, and `--aws-region`
  - this makes the operator-facing deployed smoke path one command instead of `export -> run`
- file path
  - `scripts/run_stage_procurement_smoke.py`
  - `tests/test_stage_procurement_smoke_run.py`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after the exporter and stack-output lookup shipped, the remaining friction was procedural: operators still had to run two commands to get from `.github-actions.env` to a deployed procurement smoke run
  - embedding the export path in the runner closes that last local orchestration gap without changing smoke semantics
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/run_stage_procurement_smoke.py tests/test_stage_procurement_smoke_run.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py tests/test_smoke_script.py -k 'procurement or council or stage_procurement_smoke or export_stage_procurement_smoke_env' --tb=short`
    - `pass`
- remaining boundary
  - actual deployed smoke still depends on live AWS access, valid stage credentials, and a current procurement target; this change only removes the extra local wrapper step

## 2026-04-06 — Full Local Regression Gate Refreshed After Stage Smoke Helper Closeout

- shipped
  - reran the full local pytest suite after the deployed-stage procurement smoke helper stack was folded into the runner
  - this was a verification-only closeout step; no product/runtime behavior changed in this pass
- file path
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - helper work accumulated across exporter, stack-output resolution, and one-command runner integration, so the strongest remaining local gate was to refresh the full suite rather than rely only on targeted smoke-helper tests
- validation
  - `.venv/bin/pytest -q tests/ --tb=short`
    - `1753 passed, 3 skipped in 196.85s (0:03:16)`
- remaining boundary
  - local verification is now refreshed end-to-end
  - the only real remaining external step is an actual deployed-stage procurement smoke run with live AWS access, stage credentials, and a current procurement target

## 2026-04-06 — Procurement Smoke Now Supports Discovery-First Live Target Selection

- shipped
  - extended `scripts/smoke.py` so the optional procurement lane can start from recent live G2B discovery when `SMOKE_PROCUREMENT_URL_OR_NUMBER` is absent
  - preserved the existing preferred-fixture path when a known URL or bid number is configured, and kept the existing raw-number/detail-url/discovery retry ladder for stale fixed targets
  - relaxed local/stage smoke helpers and the GitHub Actions env exporter so `G2B_API_KEY` remains the only hard procurement prerequisite while the fixed target becomes optional operator context
- file path
  - `scripts/smoke.py`
  - `scripts/run_local_procurement_smoke.py`
  - `scripts/run_stage_procurement_smoke.py`
  - `scripts/export_stage_procurement_smoke_env.py`
  - `tests/test_smoke_script.py`
  - `tests/test_local_procurement_smoke_run.py`
  - `tests/test_stage_procurement_smoke_run.py`
  - `tests/test_export_stage_procurement_smoke_env.py`
  - `scripts/local_procurement_smoke.env.example`
  - `scripts/stage_procurement_smoke.env.example`
  - `README.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - requiring a hand-maintained `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` made the deployed procurement smoke lane more brittle than the actual product path, which already supports search and live G2B selection
  - the new behavior keeps stable fixtures available for repeatability but stops treating upstream result drift as a manual operator prerequisite before every smoke pass
- validation
  - `PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile scripts/smoke.py scripts/run_local_procurement_smoke.py scripts/run_stage_procurement_smoke.py scripts/export_stage_procurement_smoke_env.py tests/test_smoke_script.py tests/test_local_procurement_smoke_run.py tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py`
    - `pass`
  - `.venv/bin/pytest -q tests/test_smoke_script.py tests/test_local_procurement_smoke_run.py tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py --tb=short`
    - `pass`
- remaining boundary
  - deployed procurement smoke still depends on real AWS access, a valid `G2B_API_KEY`, and live upstream G2B availability
  - fixed fixture variables remain recommended when you want the release lane pinned to one known procurement record

## 2026-04-06 — Deploy Workflow And GitHub Actions Checker Aligned With Discovery-First Smoke

- shipped
  - updated `.github/workflows/deploy-smoke.yml` so the procurement precheck now requires `G2B_API_KEY_<STAGE>` and only logs an informational note when `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` is blank
  - updated `scripts/check-github-actions-config.sh` with the same contract so repo-level config checks no longer fail when operators intentionally rely on discovery-first smoke
  - documented the same behavior in the GitHub Actions env scaffold and deploy runbook
- file path
  - `.github/workflows/deploy-smoke.yml`
  - `scripts/check-github-actions-config.sh`
  - `scripts/github-actions.env.example`
  - `tests/test_check_github_actions_config.py`
  - `README.md`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/IMPLEMENT.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after the smoke runtime and local/stage runners were relaxed, the remaining inconsistency lived in GitHub Actions prechecks and operator config validation
  - without this alignment, deployed smoke would still fail before reaching the new discovery-first import path
- validation
  - `bash -n scripts/check-github-actions-config.sh`
    - `pass`
  - `.venv/bin/pytest -q tests/test_check_github_actions_config.py tests/test_smoke_script.py tests/test_local_procurement_smoke_run.py tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py --tb=short`
    - `pass`
- remaining boundary
  - GitHub Actions workflow semantics are now aligned locally, but the actual deployed `deploy-smoke` run still requires live AWS access and a valid `G2B_API_KEY_<STAGE>`

## 2026-04-06 — Prod Deploy-Smoke Lambda AccessDenied Narrowed And Artifact Bucket Path Hardened

- shipped
  - reran `deploy-smoke` on the latest merged `main` after PR #17 and confirmed the workflow reached `SAM deploy` before failing, so the remaining blocker is no longer local CI, local smoke helpers, or application test coverage
  - inspected the live prod stack, Lambda function configuration, deploy role policy, artifact objects, and CloudTrail management events to separate application regressions from infrastructure-path failures
  - updated `.github/workflows/deploy-smoke.yml` so `sam deploy` now uploads artifacts into the stage-owned `DECISIONDOC_S3_BUCKET_<STAGE>` under `sam-artifacts/<stage>/` instead of the SAM CLI managed default source bucket
  - documented the same mitigation and the required stack recovery command for environments already left in `UPDATE_ROLLBACK_FAILED`
- file path
  - `.github/workflows/deploy-smoke.yml`
  - `docs/deploy_aws.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - GitHub Actions run `24017366147` failed at `SAM deploy`, and CloudFormation showed `DecisionDocFunction` update failing with Lambda `AccessDeniedException` before any post-deploy smoke ran
  - live inspection showed the GitHub OIDC deploy role still has broad `cloudformation:*`, `iam:*`, `lambda:*`, and `s3:*` permissions, the prod Lambda execution role trust is still valid, and both the previous and newly uploaded SAM artifacts exist in S3 with `AES256` object encryption
  - given that evidence, the smallest practical mitigation is to remove one more external dependency from deploy time and pin artifact uploads to the stage-owned bucket already managed by the application stack
- validation
  - `gh api 'repos/sungjin9288/DecisionDoc-AI/actions/runs/24017366147/jobs'`
    - `deploy` failed, `smoke` skipped
  - `gh api -i 'repos/sungjin9288/DecisionDoc-AI/actions/jobs/70039282183/logs'`
    - `SAM deploy` failed while CloudFormation was updating `DecisionDocFunction`
  - `aws cloudformation describe-stack-events --stack-name decisiondoc-ai-prod --region ap-northeast-2 --max-items 20`
    - stack status confirmed as `UPDATE_ROLLBACK_FAILED`
  - `aws lambda get-function-configuration --function-name decisiondoc-ai-prod --region ap-northeast-2`
    - current prod Lambda still reflects the March 28 successful deployment
  - `aws iam get-role-policy --role-name decisiondoc-github-actions-deploy-prod --policy-name decisiondoc-github-actions-deploy-prod`
    - deploy role still allows broad CloudFormation/Lambda/S3 actions
  - `aws s3api head-object --bucket aws-sam-cli-managed-default-samclisourcebucket-gy2eizrxryln --key f9f70fe09e95717d845a21b5e66154a9`
    - previous artifact exists
  - `aws s3api head-object --bucket aws-sam-cli-managed-default-samclisourcebucket-gy2eizrxryln --key 6234372955d514664bcd7d42961d14cd`
    - failing-run artifact also exists
- remaining boundary
  - prod stack is currently `UPDATE_ROLLBACK_FAILED`, so the next live rerun still needs:
    - `aws cloudformation continue-update-rollback --stack-name decisiondoc-ai-prod --region ap-northeast-2`
  - after rollback recovery, `deploy-smoke` must be rerun from the latest merged `main` to verify the stage-bucket artifact path actually clears the prior Lambda update failure

## 2026-04-06 — Prod Lambda Update Blocker Classified As AWS-Side Restriction And Week-1 Operating Docs Added

- shipped
  - added long-term operating guidance in `docs/operating_model_roadmap.md` with a concrete 4-week execution plan centered on environment separation, stage-first release discipline, immutable deploy preference, and smoke/operator isolation
  - updated `docs/deploy_aws.md` with a deploy ownership map, prod rerun gate, and explicit recovery/diagnostic commands so operators stop treating repeated `deploy-smoke` reruns as a normal incident response
  - updated `docs/deployment/prod_checklist.md` so production deployment now calls out ownership boundaries, rerun stop conditions, and the known `DecisionDocFunction` access-denied pattern
- file path
  - `docs/operating_model_roadmap.md`
  - `docs/deploy_aws.md`
  - `docs/deployment/prod_checklist.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - after the stage-owned artifact bucket mitigation landed, the remaining production blocker was still `DecisionDocFunction` update failure with Lambda `AccessDeniedException`
  - the next question was no longer “how to rerun deploy-smoke” but “how to prevent operators from repeatedly using the wrong recovery move while the underlying AWS restriction remains unresolved”
  - a durable operating model was needed because the repo is now large enough that deployment discipline, smoke identity separation, and environment roles matter as much as feature correctness
- validation
  - `aws cloudformation describe-stacks --stack-name decisiondoc-ai-prod --region ap-northeast-2 --query 'Stacks[0].[StackStatus,StackStatusReason]' --output text`
    - stack failure remained isolated to `DecisionDocFunction`
  - `aws iam get-role-policy --role-name decisiondoc-github-actions-deploy-prod --policy-name decisiondoc-github-actions-deploy-prod`
    - deploy role inline policy still included broad `lambda:*`, `s3:*`, and `cloudformation:*`
  - `aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::217139788460:role/decisiondoc-github-actions-deploy-prod --action-names lambda:UpdateFunctionCode ...`
    - IAM simulation result was `allowed`
  - `aws iam list-attached-user-policies --user-name community_`
    - local admin user had `AdministratorAccess`
  - `aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::217139788460:user/community_ --action-names lambda:UpdateFunctionCode ...`
    - local admin IAM simulation result was also `allowed`
  - `aws lambda update-function-code --function-name decisiondoc-ai-prod --region ap-northeast-2 --s3-bucket decisiondoc-ai-prod-217139788460-apne2 --s3-key sam-artifacts/prod//d2ee02e06f0045f866cc6eb4efd0ce26 --dry-run`
    - still failed with `AccessDeniedException`
  - `aws lambda update-function-code --function-name decisiondoc-ai-prod --region ap-northeast-2 --zip-file fileb://... --dry-run`
    - inline zip dry-run also failed with `AccessDeniedException`
  - `aws organizations list-policies-for-target --target-id 217139788460 --filter SERVICE_CONTROL_POLICY`
    - returned `AWSOrganizationsNotInUseException`, so SCP was ruled out
  - `git diff --check -- README.md docs/deploy_aws.md docs/deployment/prod_checklist.md docs/operating_model_roadmap.md docs/specs/public_procurement_copilot/STATUS.md`
    - pass
- remaining boundary
  - current evidence points away from repo code, workflow artifact path, ordinary IAM allow, or Organizations SCP
  - the remaining blocker is an AWS-side Lambda update restriction that still prevents `UpdateFunctionCode`, even for a local admin user with `AdministratorAccess`
  - until that restriction is resolved, `prod deploy-smoke` reruns should remain paused and `prod` should be treated as a recovery/diagnosis target rather than a feature-validation environment

## 2026-04-06 — Deploy-Smoke Fail-Fast Guard Added For Broken Prod Stack And Lambda Dry-Run Deny

- shipped
  - updated `.github/workflows/deploy-smoke.yml` so the deploy job now checks stack mutability before `SAM build` and `SAM deploy`
  - the new preflight stops immediately when the target stack is already `UPDATE_ROLLBACK_FAILED`
  - the same preflight also runs `aws lambda update-function-code --dry-run` against the target function and fails fast when Lambda code update is blocked
  - aligned `docs/deploy_aws.md` and `docs/deployment/prod_checklist.md` with the same fail-fast semantics
- file path
  - `.github/workflows/deploy-smoke.yml`
  - `docs/deploy_aws.md`
  - `docs/deployment/prod_checklist.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the current prod failure mode is not a normal application regression but an AWS-side Lambda update restriction, and repeated `deploy-smoke` reruns only recreate `UPDATE_ROLLBACK_FAILED`
  - a release workflow should surface that state before trying `SAM deploy`, not after another failed stack update
- validation
  - `git diff --check -- .github/workflows/deploy-smoke.yml docs/deploy_aws.md docs/deployment/prod_checklist.md docs/specs/public_procurement_copilot/STATUS.md`
    - pass
  - `.venv/bin/pytest -q tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py tests/test_smoke_script.py --tb=short`
    - planned as touched-area regression gate for deploy/procurement smoke helpers
- remaining boundary
  - this guardrail reduces operator error and repeated failed deploy attempts, but it does not resolve the underlying AWS-side Lambda update restriction
  - production redeploy still remains blocked until that AWS-side restriction is cleared

## 2026-04-06 — Dev-First Release Gate Added To Deploy-Smoke For Prod Promotion Discipline

- shipped
  - updated `.github/workflows/deploy-smoke.yml` so `prod` dispatch now requires `main` plus an already successful `deploy-smoke [dev]` run for the same `head_sha`
  - added optional `workflow_dispatch` input `break_glass_reason` so true incident recovery can still override the gate with an explicit operator reason
  - aligned `docs/deploy_aws.md`, `docs/deployment/prod_checklist.md`, and `docs/operating_model_roadmap.md` with the new stage-first semantics
- file path
  - `.github/workflows/deploy-smoke.yml`
  - `docs/deploy_aws.md`
  - `docs/deployment/prod_checklist.md`
  - `docs/operating_model_roadmap.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - the previous fail-fast guard only stopped obviously broken prod reruns after stack or Lambda mutability checks, but it still allowed operators to treat `prod` as the first deployment target for a newly merged `main` SHA
  - the Week 2 operating-model goal was to make stage-first promotion a workflow-enforced contract, not just a documentation preference
  - because a dedicated `stage` stack does not exist yet, `dev` is temporarily used as the stage-equivalent release gate
- validation
  - `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/deploy-smoke.yml"); puts "yaml-ok"'`
    - pass
  - `.venv/bin/pytest -q tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py tests/test_smoke_script.py --tb=short`
    - pass
  - `git diff --check -- .github/workflows/deploy-smoke.yml docs/deploy_aws.md docs/deployment/prod_checklist.md docs/operating_model_roadmap.md docs/specs/public_procurement_copilot/STATUS.md`
    - planned as final formatting gate for the touched workflow/docs set
- remaining boundary
  - this gate improves release discipline, but it does not create a real dedicated `stage` stack yet
  - `break_glass_reason` remains an operator override, not a substitute for solving the AWS-side Lambda update restriction that still blocks normal prod redeploy

## 2026-04-06 — Fresh-Stack Deployment Suffix Added For Lambda Update Restriction Workaround

- shipped
  - added optional `DeploymentSuffix` support to `infra/sam/template.yaml` so Lambda function names can move from `decisiondoc-ai-<stage>` to `decisiondoc-ai-<stage><suffix>` without changing the default path
  - updated `.github/workflows/deploy.yml` and `.github/workflows/deploy-smoke.yml` so manual dispatch can supply `deployment_suffix` and deploy a separate stack/function pair instead of overwriting the currently blocked stage stack
  - made the `prod` dev-first gate suffix-aware, so `prod` with `deployment_suffix=-green` now requires a successful `deploy-smoke [dev-green]` run for the same `main` SHA
  - documented the same fresh-stack workaround in deploy/prod operating docs
- file path
  - `infra/sam/template.yaml`
  - `.github/workflows/deploy.yml`
  - `.github/workflows/deploy-smoke.yml`
  - `docs/deploy_aws.md`
  - `docs/deployment/prod_checklist.md`
  - `docs/operating_model_roadmap.md`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - `decisiondoc-ai-dev` and `decisiondoc-ai-prod` both now fail `aws lambda update-function-code --dry-run` with `AccessDeniedException`, so normal in-place update is blocked before any application smoke can run
  - the next smallest repo-level mitigation is to support a fresh stack/function name so deployment can test whether `CreateFunction` or new-stack provisioning is still allowed even while updates to the old function stay denied
  - because `prod` promotion discipline must survive this workaround too, the same suffix has to propagate into the dev-first release gate rather than creating an untracked side path
- validation
  - planned local verification:
    - `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/deploy.yml"); YAML.load_file(".github/workflows/deploy-smoke.yml"); puts "yaml-ok"'`
    - `.venv/bin/pytest -q tests/test_stage_procurement_smoke_run.py tests/test_export_stage_procurement_smoke_env.py tests/test_smoke_script.py --tb=short`
    - `git diff --check -- infra/sam/template.yaml .github/workflows/deploy.yml .github/workflows/deploy-smoke.yml docs/deploy_aws.md docs/deployment/prod_checklist.md docs/operating_model_roadmap.md docs/specs/public_procurement_copilot/STATUS.md`
- remaining boundary
  - this workaround only creates a fresh naming path; it does not prove that the AWS account will allow a new `CreateFunction` or new stack create
  - the next live check still has to be `deploy-smoke [dev-green]` or a similar suffixed `dev` run before any suffixed `prod` promotion is considered

## 2026-04-16 — Procurement PDF Normalization Added To Attachment/RFP Parsing

- shipped
  - added `app/services/procurement_pdf_normalizer.py` to turn structured PDF extraction into a procurement-oriented summary block with document type guess, key sections, procurement signals, PPT candidate pages, and review notes
  - updated `POST /generate/with-attachments`, `POST /generate/from-documents`, and `POST /attachments/parse-rfp` so PDF attachments prepend this normalized context before the raw extracted text
  - kept the change additive and PDF-only so existing non-PDF attachment flows, provider boundaries, and storage behavior stay unchanged
- file path
  - `app/services/procurement_pdf_normalizer.py`
  - `app/services/rfp_parser.py`
  - `app/routers/generate.py`
  - `tests/test_procurement_pdf_normalizer.py`
  - `tests/test_rfp_parsing.py`
  - `tests/test_generate_from_documents.py`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - real public-sector kickoff/evaluation PDFs were readable but still too flat for downstream generation because raw text alone did not preserve heading hierarchy, procurement signals, or slide-worthy structure
  - the smallest safe improvement was to reuse the existing structured PDF extraction and add a procurement-specific normalization layer rather than rewriting attachment parsing or provider prompts
- validation
  - `python3 -m py_compile app/services/procurement_pdf_normalizer.py app/services/rfp_parser.py app/routers/generate.py tests/test_procurement_pdf_normalizer.py tests/test_rfp_parsing.py tests/test_generate_from_documents.py`
  - `.venv/bin/pytest -q tests/test_procurement_pdf_normalizer.py tests/test_rfp_parsing.py tests/test_generate_from_documents.py tests/test_pdf_enhanced.py --tb=short`
- remaining boundary
  - this improves generation inputs for procurement PDFs, but it does not yet classify embedded images/diagrams or fully reconstruct multi-column slide layouts from the source PDF

## 2026-04-16 — Procurement PDF Page Classifier Added For Better PPT/Section Planning

- shipped
  - extended `extract_pdf_structured()` so structured PDF extraction now returns per-page summaries with page number, detected headings, preview text, and table presence
  - upgraded `app/services/procurement_pdf_normalizer.py` to classify pages into document-oriented buckets such as `개요/배경`, `평가기준/지표`, `일정/마일스톤`, `추진절차/방법`, and `조직/거버넌스`
  - added a new `페이지 분류:` block and made `발표/PPT 후보 페이지:` prefer page-classifier output over heading-only heuristics when page metadata is available
- file path
  - `app/services/attachment_service.py`
  - `app/services/procurement_pdf_normalizer.py`
  - `tests/test_pdf_enhanced.py`
  - `tests/test_procurement_pdf_normalizer.py`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - heading-only normalization improved procurement PDF ingestion but still mixed true section headings with fragmented legal/body text on real kickoff and evaluation slides
  - the next smallest safe step was to add page-level structure so downstream generation can distinguish `개요`, `평가기준`, `일정`, and `거버넌스` pages even when heading extraction is imperfect
- validation
  - `python3 -m py_compile app/services/attachment_service.py app/services/procurement_pdf_normalizer.py tests/test_pdf_enhanced.py tests/test_procurement_pdf_normalizer.py`
  - `.venv/bin/pytest -q tests/test_procurement_pdf_normalizer.py tests/test_rfp_parsing.py tests/test_generate_from_documents.py tests/test_pdf_enhanced.py --tb=short`
- remaining boundary
  - this page classifier improves slide/chapter planning inputs, but it still does not classify embedded images/diagrams or fully recover multi-column slide layouts

## 2026-04-16 — Prompt Contract Updated To Use Procurement PDF Slide Hints In slide_outline

- shipped
  - updated `build_bundle_prompt()` so bundles that declare `slide_outline` now receive an explicit `공공조달 PPT 설계 적용 규칙` block when procurement context is present
  - the prompt now tells the model to treat `페이지 분류`, `PPT 페이지 설계 힌트`, and `발표/PPT 후보 페이지` as source-of-truth inputs for `slide_outline.title`, `core_message`, `evidence_points`, `visual_type`, `visual_brief`, and `layout_hint`
- file path
  - `app/domain/schema.py`
  - `tests/test_pdf_enhanced.py`
  - `docs/specs/public_procurement_copilot/STATUS.md`
- reason for change
  - procurement PDF normalization and page classification were already being injected into context, but the prompt still left it implicit whether the model must use those hints when composing slide-by-slide structure
  - the next minimal improvement was to make the contract explicit instead of relying on the model to infer that relationship on its own
- validation
  - `python3 -m py_compile app/domain/schema.py tests/test_pdf_enhanced.py`
  - `.venv/bin/pytest -q tests/test_procurement_pdf_normalizer.py tests/test_rfp_parsing.py tests/test_generate_from_documents.py tests/test_pdf_enhanced.py --tb=short`
- remaining boundary
  - this strengthens prompt grounding, but it does not yet enforce post-generation validation that every `slide_outline` item actually matches the classified procurement pages

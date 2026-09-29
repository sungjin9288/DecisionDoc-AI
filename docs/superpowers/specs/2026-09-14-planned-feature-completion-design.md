# Planned Feature Completion Design

Status: approved local workflows have recorded implementation and verification;
user-data activation, human UAT and external readiness remain open.

Current reconciliation (2026-09-28): the dated diagnosis below is historical.
The procurement opportunity/applicability admission records are approved, not
draft. Implementation-plan steps 1-8 have local/fake-S3 and isolated browser
evidence; steps 9-11 add read-only preflight, persisted transition and cold-process
fixture restore checks. See the [implementation plan](../plans/2026-09-21-procurement-opportunity-and-applicability.md)
and [dated verification records](../../specs/public_procurement_copilot/STATUS.md)
for commands, results and limits. This documentation reconciliation is not a new
test run or whole-product completion claim.

The factory still defaults to `procurement_multi_opportunity_enabled=False`.
The new workflow is available only through an explicitly opted-in app. Existing
user data has not been inspected, copied or converted by this continuation;
fixture restore is not an operational backup or user-data migration acceptance.

Current update: the separately approved [edited-copy save design](./2026-09-14-edited-project-document-save-design.md)
is implemented with local save/reload/download verification. The gap statements
in the two correction records below describe the earlier diagnosis, not the
current edited-copy capability. Subsequent reconciliation is recorded above.

2026-09-15: [style import and reuse](./2026-09-15-local-style-example-import-design.md)
has local source/prompt and browser verification. The
[review completion lifecycle](./2026-09-04-generated-document-review-completion-design.md#9-real-local-multi-session-verification-2026-09-15)
now also has real local, separate-session assignment/completion/package proof,
including non-assignee rejection and reload byte equality. Row 4 was the next
specification reconciliation at that point; this was not whole-product or human-UAT completion.

2026-09-15 knowledge follow-up: the existing local upload/reload/context/generation
path now has end-to-end and project-isolation verification. The upload batching
defect and correction are recorded below. This closes one knowledge-reuse path,
not the remaining procurement specification reconciliation.

2026-09-21 procurement follow-up: source refresh previously retained filters,
scores and recommendation from the old source; reevaluation also retained the
old recommendation and checklist. Both paths now invalidate dependent judgment
state while retaining source snapshots, notes and completed review evidence.
The rule is recorded in procurement `IMPLEMENT.md`, with local regression
evidence in its `STATUS.md`. At that point row 4 was partially verified: backend source,
evaluation and downstream handoff checks are not a procurement browser UAT or
whole-PRD completion claim.

2026-09-21 summary follow-up: the procurement PRD now distinguishes the current
checklist wire values from the earlier vocabulary and identified FR1's
multiple-opportunity requirement as incomplete at that point. Snapshot retention does not
fulfill independently selectable opportunities. The summary now displays blocked
and unknown items before routine actions and no longer reports an empty,
invalidated checklist as ready. Current `action_needed` counts and backend
decision/approval contracts are unchanged. Browser and adjacent regression
evidence is recorded in procurement `STATUS.md`. Multiple-opportunity identity,
review/document bindings and `not_applicable` semantics then required a bounded
admission design; they were not removed from the completion matrix.

The [2026-09-21 opportunity and applicability design](./2026-09-21-procurement-opportunity-and-applicability-design.md)
specifies these two contracts. Both admission records were subsequently approved
for bounded local/fake-S3 implementation, now recorded in steps 1-8 of the plan.
Independent opportunity identity and handoffs precede requirement-level
applicability evidence. Real user-data transition remains outside that approval.

## Objective

Complete the planned local product workflows before optional presentation work.
Do not equate an existing button, route, mock response, or historical test count
with end-to-end completion. Do not invent additional features to extend a phase.

The user approved this order: generation, style reuse, review and collaboration,
then reconciliation of the wider product plan. This document makes that direction
testable; it does not claim that every implementation gap is already known.

## Model Selection

- Planning and design: gpt-6-astra / medium.
- Ordinary implementation: gpt-5.6-sol / high.
- Complex cross-layer correctness work: gpt-5.6-terra / xhigh.
- Narrow tests and documentation: gpt-5.6-luna / max.

These are requested settings, not execution evidence. The current task has no
verified in-turn model-switch tool. Use the app model selector before a stage
that requires a specific model; never report a model as used without evidence.
Keep work in this task. Do not create additional tasks solely to change models.

## Existing Architecture And Alternatives

Keep FastAPI routes, generation services, strict request schemas, tenant-scoped
stores, provider adapters, and the existing browser shell. Repair the smallest
broken connection in that architecture.

Rewriting the shell or introducing another workflow engine would increase the
scope before establishing the actual defects. Closing documentation alone would
not establish usable functionality. Neither is the selected approach.

## Completion Matrix

| Order | User outcome | Existing implementation anchors | Required proof |
|---|---|---|---|
| 1 | Generate, edit, save, reopen, and export a document without losing intended content | `app/routers/generate/core.py`, `app/routers/generate/export.py`, `app/routers/projects/core.py`, `app/routers/history.py`, `app/static/index.html` | Real local browser-to-API lifecycle, reload, persisted content comparison, downloaded edited content |
| 2 | Reuse examples and selected style in later generation | `app/routers/styles.py`, `app/services/style_analyzer.py`, `app/services/generation/style_context.py` | Save/reload examples, inspect generation input, change/default/delete isolation, cache invalidation |
| 3 | Assign a reviewer, record a decision, and retrieve the correct completed package | `app/routers/projects/generated_document_reviews.py`, `app/services/generated_document_review_service.py`, `app/storage/generated_document_review_store.py` | Separate user sessions with real local persistence, assignee/non-assignee behavior, packet integrity and source drift |
| 4 | Reuse project knowledge and complete planned procurement handoffs | `app/routers/knowledge.py`, `app/storage/knowledge_store.py`, `app/routers/projects/procurement.py` | Reconcile relevant specifications first, then synthetic/local source-to-output checks; live integrations remain separate |

These anchors are observed code paths, not declarations of complete behavior.
Before changing a row, read its existing tests and reproduce the missing outcome.
Mark each requirement as verified locally, confirmed development gap, not yet
verified, or external verification deferred. A test not run is not a defect.

### Current Local Evidence And Remaining Conditions

| Matrix row | Recorded local verification | Remaining condition |
|---|---|---|
| 1 | Edited-copy save/reload/download and browser lifecycle in the linked edited-copy design | Human acceptance of generated content and native Office open/edit/save are not established by these checks |
| 2 | Local example import, selected-style prompt reuse and browser lifecycle in the linked style design | Prompt conditioning is not model-weight training; real-provider semantic quality remains unverified |
| 3 | Separate-session assignment/completion, non-assignee denial and exact completed-package replay in the linked review design | No external publication, legal approval or operational acceptance is granted |
| 4 | Knowledge upload/context isolation plus opportunity/applicability services, APIs, browser flow and bound exports in procurement STATUS | Default activation and real-data transition remain open; live G2B/AWS/provider and native Office checks are separate |

The next usability check can use a fresh synthetic dataset in an isolated opt-in
app without converting existing data. If an existing dataset is selected instead,
first obtain its exact approved path and read/copy scope, then follow the existing
transition plan. Neither path implicitly authorizes original-data activation.

## First Implementation Boundary

Start with the document edit/save/reopen/export lifecycle. Inspect the actual
project-document save flow and history restoration before selecting the store
to change. A browser-local history snapshot must not be treated as server-side
saved content. Conversely, immutable generation history must not silently become
editable document state.

Use synthetic content with a unique edited sentence. Generate with mock, edit,
explicitly save through the intended product action, reload, reopen the saved
document, and export it. Compare the edited sentence at each step. If the current
UI has no durable save action, record that as an admission candidate rather than
inventing a new endpoint or rewriting original generation evidence silently.

Failure checks include interrupted generation, failed save, wrong tenant,
non-assigned reviewer, and a source changed after review creation. A failed save
must not display success; an unverified completion event must not produce a
successful generation state. Preserve existing audit and source identity rules.

## Verification Strategy

Use existing tests as entry points, not as substitutes for missing lifecycle
coverage: `tests/test_generate.py`, `tests/test_export_edited.py`,
`tests/test_project_management.py`, `tests/test_generation_style_selection.py`,
`tests/test_style_system.py`, `tests/test_generated_document_reviews.py`,
`tests/storage/test_generated_document_review_store.py`, and
`tests/e2e/test_main_flow.py`.

Run Python checks in an isolated mock/local environment with dotenv loading
disabled and a temporary data root. Do not reuse user accounts or UAT data.
Run browser E2E separately from standalone tests that own a sync Playwright
runtime. Stub external integrations, not the local API whose persistence is
under test. Use local/fake-S3 tests for the existing backend contract.

For each confirmed gap: reproduce, fix narrowly, rerun the reproduction, run
adjacent regression tests, review the diff, and update the existing status
document with commands and actual results. Do not sum historical and focused
test counts into a new full-suite claim. Run `git diff --check` before handoff.

## Learning And External Boundaries

Style examples, prompt conditioning, and project knowledge reuse are not model
weight training. Mock proves workflow behavior, not semantic quality of a real
model. Real document quality and Office layout still need human evaluation.

No paid/provider calls, dataset uploads, model training or promotion, live AWS,
live G2B, deployment, publication, bid submission, or operational/legal approval
are authorized. M1/M2/M6 external readiness remains separate from local product
completion. Preserve existing dirty files and all review evidence. Do not commit,
push, install, change credentials, or modify global configuration.

## Admission And Delivery

Existing approved capabilities may be tested and repaired within their original
boundaries. New capabilities or changed interfaces/authority require the existing
`docs/future_feature_gate.md` process and a bounded acceptance record; this broad
direction approval does not fabricate an approved feature-gate artifact.

After written-design review, prepare the first bounded implementation plan from
the actual save/reopen findings. Complete one usable workflow before advancing
to the next matrix row. Report implemented behavior, verification, remaining
gaps, and deferred external checks separately. Completion of this design is not
completion of the product.

## Knowledge Upload Scope Correction (2026-09-15)

The upload loop previously resolved `_knowledgeCurrentProject` and auth headers
for each file after asynchronous waits. Switching projects or accounts during a
batch therefore sent subsequent files under the new context. The delayed refresh
also read the mutable project selection, and late list responses could overwrite
the currently selected project's list. Five controlled browser cases reproduced
these defects before correction.

The batch now captures project/auth once, blocks duplicate concurrent batches,
checks context before each subsequent file and after each response, and refreshes
only the initiating project's current view. List reads also enforce current
project/auth and newest-request ownership. File controls are restored in finally;
the file input is cleared without automatic retry. Project switching hides the
previous upload status. Long filenames wrap rather than expanding the upload row.

A request already dispatched before a switch may still persist in its original
project. This correction does not cancel, undo, move or clean up stored files.
Remaining files are not sent in the changed context. The user must inspect the
original project's list before explicitly selecting unsent files again.

Verification used mock/local isolated temporary data and disabled dotenv loading:

- `python3 -m pytest -q tests/test_knowledge_upload_ui.py
  tests/test_knowledge_generation_lifecycle.py tests/test_knowledge.py
  tests/test_knowledge_store_integrity.py tests/test_knowledge_search.py
  --tb=short --show-capture=no`: **84 passed**, one existing Starlette/httpx
  deprecation warning, 7.31 seconds. Includes upload/preview/prompt reuse,
  exclusion of another project's source, deletion removing context from later
  generation, tenant/store integrity, partial failure and stale UI responses.
- `python3 -m pytest -q -p pytest_playwright.pytest_playwright
  tests/e2e/test_knowledge_local_lifecycle.py --browser chromium --tb=short
  --show-capture=no`: **2 passed**. Actual local TXT upload, current-project list,
  reload and context retrieval on mobile/desktop; no substituted API responses,
  horizontal overflow or page errors. Long-filename screenshots were captured.
- Targeted Ruff E/F/W excluding E501 and `git diff --check` passed.

Security guidance was consulted because files must retain the initiating
project/auth context. No backend authorization or storage contract was changed.
No user data, provider/OCR calls, model training, live G2B/AWS, installation,
deployment, commit or push was performed. Full-suite and human UAT remain separate.

## First Correction: Explicit Empty Edits

The existing browser edit action records an empty string when the user removes
all content. Truthiness fallback incorrectly replaced that intentional edit
with the original text in export, review, approval-source construction, and
knowledge-promotion preparation. Nullish fallback now preserves the empty edit;
the original generation record is unchanged. Existing downstream validation
continues to decide whether an empty document is acceptable.

Reproduction: `tests/test_edited_document_content_ui.py` initially returned
`1 failed, 3 passed`; the empty-edit case returned original content instead of
an empty string. Expanded regression checks include knowledge exclusion and
explicit original-export selection.

Verification in isolated mock/local environments with dotenv disabled:

- `pytest -q tests/test_edited_document_content_ui.py tests/test_export_edited.py tests/test_generation_style_selection.py --tb=short`: 43 passed, 1 existing Starlette/httpx deprecation warning, 6.41s.
- Separate process: `pytest -p pytest_playwright.pytest_playwright -q tests/e2e/test_main_flow.py -k manual_style_generation_and_edited_docx_download --browser chromium --tb=short`: 3 passed, 113 deselected, 11.51s.
- `git diff --check`: passed.

The focused browser regression executes extracted production functions with a
stubbed export response. The separate E2E checks real local generation and DOCX
download at desktop and mobile sizes. Neither proves the full durable edited
project save/reopen flow, which remains the next investigation. No full-suite,
human UAT, real model quality, model-switch, or external-readiness claim is made.

## Second Correction: Document-Scoped Editing

The edit-completion handler enumerated the single visible pane from index zero,
so editing a later tab wrote into the first document. `showDoc()` also rendered
only original Markdown. The browser now binds the rendered pane to its document
object, captures edits before replacing it, and renders the edited text through
the existing safe Markdown renderer. Empty content remains empty; tab changes
retain edit mode. Capturing into the bound object avoids using an already-changed
active tab or overwriting a newly loaded result's document by index.

- RED: `pytest -q tests/test_edited_document_content_ui.py --tb=short` reported
  1 failed, 5 passed because the second document had no recorded edit.
- GREEN: the same command reported 6 passed in 2.92s, including editing a second
  document, switching during editing, and preserving an empty draft.
- Separate isolated mock/local Chromium run with
  `pytest -p pytest_playwright.pytest_playwright -q tests/e2e/test_main_flow.py -k manual_style_generation_and_edited_docx_download --browser chromium --tb=short`
  reported 3 passed, 113 deselected in 12.11s.

Confirmed remaining gap: generation auto-link in `app/routers/generate/export.py`
stores the generation-time snapshot. The browser's edit-completion action does
not persist an edited project document. `openServerHistoryEntry()` reads original
history, and `saveHistory()` is browser-local generation history. No new save
endpoint, draft store, or silent original-history overwrite was introduced.
Durable edited-document save/reopen needs its own bounded admission design,
including source identity, authorization, duplicate submission, and failure
semantics. Local in-memory tab persistence is not durable server persistence.

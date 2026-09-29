# Edited Project Document Save

Status: explicitly approved by the repository operator; implemented and locally verified.

## User Flow

An authenticated tenant member opens a generated document already linked to a
project, edits it, and selects `Save edited copy`. A successful save creates a
new project document. The user can reload the page, open that document from the
project list, and download exactly its saved content. The original generated
document and any reviews or approval records remain unchanged.

Generation without a persisted project document is not admitted in this slice.
Do not infer a parent from title or silently select the first matching request.
Resolve the exact document identity from project detail; ambiguous or missing
identity disables saving and explains the missing condition.

## Storage And Identity

Reuse ProjectStore and its selected local/fake-S3 conditional mutation backend.
Add a distinct edited-copy operation rather than changing legacy add-document
semantics. Keep each saved copy immutable through this operation. Editing a saved
copy creates another document linked to that copy; no history record is replaced.

The new strict request includes an operation UUID, expected parent content hash,
title, and typed document content. The route identifies the parent by project ID
and document ID. Parent hash covers its canonical document snapshot, title,
bundle and formatting settings. Reject blank title, duplicate document types,
and blank document content before mutation; never recover deleted content from
the parent. Preserve the parent's document-type set. The existing edited export
schema has no aggregate size bound; this save request adds a 100-document and
5,000,000 UTF-8 Markdown byte limit, with a 200-character title limit.

Persist actor ID, operation UUID, canonical request hash, parent document ID,
parent hash, and creation time with the new document. Derive tenant, bundle,
formatting and lineage server-side. Do not inherit approval ID, approval status,
review completion, or verified-original export authority. A generated request
reference is lineage only, not proof that edited bytes were issued by a provider.

An identical operation in the same tenant/project/actor returns the same saved
document after restart; changed payload or parent under that operation conflicts.
Check replay before parent freshness, then verify the parent and append the copy
within the same conditional project mutation. Competing state writes must not
overwrite unrelated documents. Fail closed on invalid stored state.

## API And Access

Proposed write: `POST /projects/{project_id}/documents/{doc_id}/edited-copies`.
Use current active session identity and current tenant membership for writes,
following existing session-bound access helpers. Permit the existing `admin`
and `member` roles; `viewer`, API-key-only callers and foreign tenants cannot
write. Recheck persisted active tenant membership, not just client role claims.
Do not add a new role or treat reviewer assignment as general project ownership.

Read and download use existing project APIs and their existing access policy.
Do not suggest that copies are private to the author within a shared project.
Render saved copies as unreviewed and disable original-issued verification paths
for edited content. Keep existing review records and immutable packages untouched.

## Browser Behavior

Use one save action and a project-list open action. Before save, capture the
currently edited pane, then freeze the request payload and operation identity.
Disable duplicate submission while pending. After an ambiguous response retain
the same payload and operation for explicit retry; never silently regenerate.
Edits made after submission remain unsaved unless separately saved.

Only a confirmed matching response marks that snapshot saved. Check auth, tenant,
project, parent document and operation context before applying a response.
Keep unsaved content on validation, authorization or network failure. Reopening
a saved copy renders persisted Markdown through the existing safe renderer, not
stored HTML. Downloads use its immutable snapshot rather than current UI state.

## Verification And Delivery

1. Add failure-first store tests for independent reload, exact replay, changed
   replay, stale/missing/foreign parent, corrupt state, concurrent saves, and
   unchanged original document/review records using local and fake-S3 backends.
2. Add API tests for strict input, session/membership access, parent binding,
   conflict responses and redacted audit metadata without content or credentials.
3. Add real local browser E2E: generate into a project, edit, save, reload, open
   the copy and inspect downloaded DOCX content. Verify the original remains
   unchanged and repeat on desktop and mobile.
4. Add controlled failure-response UI tests for duplicate clicks, ambiguous
   response retry, stale context and unsaved input preservation. These supplement
   rather than replace the real persistence E2E.

Keep implementation in route/service/schema/store/browser boundaries. Use
targeted modules and preserve existing public contracts. No new dependency,
provider call, upload, training, live AWS/G2B, deployment, operational approval,
commit or push is included. Model preferences remain those in the parent design;
this document does not claim a model switch occurred.

## Implementation And Verification

Implemented modules: `app/schemas/edited_project_copies.py`,
`app/services/edited_project_copy_service.py`,
`app/storage/edited_project_copy_records.py`, and
`app/routers/projects/edited_copies.py`. ProjectStore stores nullable lineage on
copies and validates it when reading state. Existing conditional project
mutation handles CAS and uncertain-commit readback. The browser resolves the
exact generated parent or opens it through `editable-source`; no title matching
or implicit first-result selection is used.

Copies have an empty generation request ID and no inherited approval. Original
verification, handoff and approval UI actions are not offered for these copies.
The existing project download route exports the stored copy. The new read-source
route requires an active admin/member session, while existing project reads and
downloads retain their existing policy. Save/open audit events reuse the redacted
generated-document audit path without recording document text or operation UUIDs.

Verification on 2026-09-14, using temporary data roots, dotenv disabled, mock
providers, local/fake-S3 storage and existing installed Chromium:

- `pytest -q tests/test_edited_project_copies.py tests/test_edited_project_copy_api.py tests/test_project_management.py tests/test_project_approval_store_integrity.py tests/test_generated_document_reviews.py tests/test_future_feature_gate.py --tb=short --show-capture=no`: **208 passed**, 1 existing Starlette/httpx deprecation warning, 35.06s.
- Separate process: `pytest -q tests/test_edited_project_copy_ui.py tests/test_edited_document_content_ui.py --tb=short --show-capture=no`: **10 passed**, 4.30s.
- Separate process: `pytest -p pytest_playwright.pytest_playwright -q tests/e2e/test_edited_project_copy.py tests/e2e/test_main_flow.py -k 'edited_project_copy or manual_style_generation_and_edited_docx_download' --browser chromium --tb=short --show-capture=no`: **5 passed**, 113 deselected, 26.82s on the final browser changes, including the saved-copy/no-AI-generation badge.
- Targeted Ruff E/F/W checks, Python compilation and `git diff --check`: passed.

The broader test invocation initially omitted `PLAYWRIGHT_BROWSERS_PATH` after
isolating HOME. Three existing PDF review tests failed because their Chromium
runtime was unavailable. Rerunning with the installed browser path passed; no
PDF behavior or tests were weakened. The new E2E also exposed long project names
forcing mobile form overflow; constrained form/select widths resolved it.

Tests cover unchanged original snapshots, reload and exact replay, changed replay,
duplicate persisted operations, corrupt-copy preservation, parent changes during
CAS, replay after parent removal, foreign/viewer/inactive access, redacted audit,
response-loss retry, stale auth/result responses, real saved DOCX content, and
editing a saved copy into another parent-linked copy. Browser-route stubs are
used only for controlled failure tests; lifecycle E2E uses the real local API.

Limitations: this is local workflow verification, not human UAT, Word layout
approval, live S3/provider proof or full-repository regression evidence. Unsaved
edits and an uncertain operation pending in a browser tab are not recoverable
after closing that tab. Users can inspect the project list after an uncertain
save; no automatic second save is attempted. No provider, deployment, commit,
push, new dependency or model-switch operation was performed.

The existing user-facing server at `http://127.0.0.1:8788/` was restarted with
the same `/tmp/decisiondoc-goal-human-uat-x6d7dlr6/data` root. Health returned
`status=ok`, `provider=mock`, `free_mode=true`; no account reset or document
creation was performed on that user data. Security-best-practices guidance was
consulted for the new authenticated write boundary, and Playwright verified the
real browser-to-storage workflow. No independent model review is claimed.

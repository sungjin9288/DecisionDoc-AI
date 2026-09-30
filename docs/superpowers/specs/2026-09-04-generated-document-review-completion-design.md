# Generated Document Review Completion Design

Date: 2026-09-04  
Status: implemented locally; live AWS/S3 runtime and external effects not authorized

## 1. Purpose

The persisted generated-document handoff no longer has to remain `pending`
after the assigned reviewer finishes an inspection. The current stable assignee
can record one terminal decision and download a deterministic evidence package
that contains the unchanged handoff packet and a packet-bound completion
receipt.

This workflow records human review evidence. It does not approve a project,
submit a bid, call a provider, deploy software, or create legal, contractual,
or operational authority.

## 2. Authority Boundary

Completion is available only to an authenticated browser session whose current
tenant user record is active, has an `admin` or `member` role, and exactly
matches the stable assignee stored on the pending handoff. Admin visibility does
not permit an admin to complete another user's assignment.

API keys, Ops keys, sessionless JWTs, viewers, inactive users, foreign tenant
users, and changed username or role bindings are rejected before mutation. All
stored records, ZIP manifests, receipts, response headers, and audit details
retain `operational_approval=false` and the seven all-false authority fields.

## 3. Persisted Contracts

The existing
`decisiondoc.generated_document_review_handoff.v1` record remains the canonical
pending format and keeps its original byte shape. Completion changes only its
`record.json` through exact compare-and-swap and writes a v2 record with:

- one UUIDv4 completion operation identity,
- `accepted`, `changes_requested`, or `rejected`,
- the private rationale and stable completion assignment,
- the review timestamp,
- the receipt SHA-256,
- the reviewed-package SHA-256 and byte length,
- `review_status=completed` and `human_review_completed=true`,
- all operational and external authority fields false.

The public summary omits the operation identity, rationale, stable user IDs,
and completion assignment. It exposes only the decision, review time, package
fingerprints, safe usernames and roles, source status, and current-user
assignment flag.

## 4. Reviewed Package

The reviewed package is a deterministic ZIP with this exact order:

1. `generated_document_review_packet.zip`
2. `generated_document_review_receipt.json`
3. `reviewed_package_manifest.json`

The receipt binds tenant, project, document, request, bundle, title, source
SHA-256, original packet and manifest SHA-256, artifact formats, prepared time,
stable reviewer assignment, operation identity, decision, rationale, and review
time. The manifest binds the exact packet and receipt bytes by path, size, and
SHA-256.

Before a package is stored or returned, the server validates ZIP metadata and
order, canonical JSON, the embedded original packet, all source bindings, the
receipt and package hashes, the completed record, and the false-authority
boundary. Missing, corrupt, non-canonical, duplicate-key, foreign, or
hash-drifted state fails closed without rewriting the observed bytes.

The verifier also distinguishes JSON booleans from numbers: authority `0`,
manifest completion `1`, and boolean artifact counts are rejected even when
the ZIP and receipt hashes are self-consistent. Expected-record verification
binds the original packet byte length as well as its hash. These are strict
validation requirements of the existing completion contract, not a new schema.

## 5. Transition And Replay

The store writes the content-addressed reviewed package first, reads back the
exact bytes, and then replaces the pending record with the completed record by
exact CAS. A concurrent loser may leave an inert unreferenced package, but it
cannot replace the winning record.

An exact retry must repeat the same stable assignee, operation ID, decision,
and rationale. It returns the already stored and revalidated package without a
second record transition. Reusing the operation with changed input or targeting
a competing completion returns a conflict. A failed or uncertain state is not
silently repaired or deleted.

The source document is re-derived and must be `current` before completion.
`changed` or `missing` preserves the pending handoff and requires a new handoff.
The source object and review record are separate backend objects, so this check
does not claim a distributed transaction across both objects.

## 6. HTTP Surface

- `POST /projects/{project_id}/generated-document-reviews/{packet_sha256}/complete`
  accepts strict `operation_id`, `decision`, and `rationale` fields and returns
  the verified reviewed package.
- `GET /generated-document-reviews?review_status=completed` returns safe
  completed summaries for the current assigned or tenant-admin scope.
- `GET /projects/{project_id}/generated-document-reviews` returns pending and
  completed history under the existing authorization rules.
- `GET /projects/{project_id}/generated-document-reviews/{packet_sha256}/reviewed-package`
  returns only a stored package that passes complete semantic revalidation.

The completion and reviewed-package audit actions remove stable user ID,
session ID, IP address, User-Agent, operation ID, and rationale. Audit detail
keeps only the project/document/packet references, safe review decision, status,
scope, replay flag, source status, and false operational-approval state.

## 7. Browser Contract

The generated-document inbox has separate pending and completed modes. A
completion button appears only for a pending, current-source record assigned to
the signed-in user. Project history shows the same safe action and exposes a
reviewed-package download after completion.

The dialog generates one UUID per completion attempt and retains it after an
ambiguous failure so an unchanged retry is idempotent. Completion and download
are single-flight. Before creating a Blob, the browser validates content type
and length, original packet SHA-256, reviewed-package and receipt SHA-256,
review status and decision, reviewer binding, replay state, false authority,
source status, and the actual response-body SHA-256.

Every async stage checks the captured auth revision, tenant, stable user,
project detail generation, project/document/request identity, packet SHA-256,
operation identity, and current list membership. A stale response cannot change
the current list, close a new dialog, create an object URL, start a download, or
show a success result.

## 8. Verification

```bash
python3 scripts/validate_future_feature_gate.py docs/future_feature_gates/generated_document_review_completion.json --require-approved --json
python3 -m pytest -q tests/storage/test_generated_document_review_store.py tests/test_generated_document_reviews.py --tb=short
python3 -m pytest -q tests/test_generated_document_review_ui_static.py tests/test_infrastructure.py -k generated_document_review --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k generated_document_review --browser chromium --tb=short
python3 -m pytest -q tests/ -m 'not live' --tb=short
```

Local and fake-S3 tests do not establish live AWS/S3 behavior. Provider calls,
G2B operations, training, deployment, publication, bid submission, service
resume, legal approval, and contractual commitment remain outside this scope.

## 9. Real Local Multi-Session Verification (2026-09-15)

Added `tests/e2e/test_generated_review_local_lifecycle.py` to complement the
controlled-response browser tests. It uses real local APIs and independent
browser sessions for the administrator, assigned member and unassigned member.
The administrator generates a mock document in a project and sends a DOCX review
packet through the UI. Both non-assignees receive the existing privacy-preserving
404 response when attempting completion; the record remains pending. No document
generation AI assignment is added to the reviewers.

The assigned reviewer completes through the UI and downloads the real reviewed
package. The server-side verifier checks the downloaded ZIP, receipt and source
bindings. Its embedded packet equals the originally downloaded packet, reload
and re-download return identical package bytes, and the original project document
snapshot is unchanged. The operational approval header remains false.

The desktop lifecycle passed immediately after aligning test setup with the
existing API/login contracts. Mobile then exposed a real layout defect: the long
SHA-based fallback filename expanded the review section. The shared
`.download-fallback` now permits wrapping without shortening filenames or
changing links. Desktop/mobile screenshots were inspected after correction;
horizontal-overflow and page-error checks pass.

Verification used isolated temporary data, mock generation, local storage and
local-only browser requests; no API response was fulfilled or substituted in the
new lifecycle test.

- `python3 -m pytest -q -p pytest_playwright.pytest_playwright
  tests/e2e/test_generated_review_local_lifecycle.py tests/e2e/test_main_flow.py
  -k 'real_review_assignment or generated_document_review' --browser chromium
  --tb=short --show-capture=no`: **10 passed, 108 deselected**, 14.73 seconds.
- `python3 -m pytest -q tests/test_generated_document_reviews.py
  tests/storage/test_generated_document_review_store.py
  tests/test_generated_document_review_ui_static.py --tb=short --show-capture=no`:
  **38 passed**, one existing Starlette/httpx deprecation warning, 12.97 seconds.
  Includes source drift, assignment restrictions, replay and package validation.
- Approved feature-gate validation, targeted Ruff E/F/W excluding E501, and
  `git diff --check` passed.

The procurement-eval skill was consulted for existing tenant/reviewer boundaries;
no procurement or authorization semantics changed. Full repository tests, human
UAT and live external verification are not established by these results. No user
data, credentials, provider services, AWS, commits or pushes were changed.

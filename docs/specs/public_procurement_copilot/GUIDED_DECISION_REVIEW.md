# Guided Decision Review

## Purpose

`Guided Decision Review` is a read-only project-detail navigator. It groups
already-loaded decision, evidence, review, and document records into four
inspection targets:

1. Decision
2. Evidence
3. Review
4. Documents

It does not create a workflow state, change an approval, call a provider,
submit a bid, or create a legal or contractual commitment. H126 adds an explicit
review-only JSON download described in
[Guided Decision Review Handoff](./GUIDED_DECISION_REVIEW_HANDOFF.md). That
attachment is non-atomic, not persisted, and must be rechecked before reliance.
H127 adds a
[Guided Decision Review Handoff Recheck](./GUIDED_DECISION_REVIEW_RECHECK.md)
receipt that compares a browser-verified source with a fresh observation while
keeping all operational authority false. H128 adds a
[Guided Decision Review Disposition](./GUIDED_DECISION_REVIEW_DISPOSITION.md)
receipt that binds one allowlisted review disposition to an exact verified H127
receipt without persistence, reviewer identity, approval, or execution
authority.

## Render boundary

The panel renders only when the current project already has a valid
`decision_evidence_map.v1` response with all of the following exact values:

- `read_only: true`
- `snapshot_atomic: false`
- `authority.mutation: false`
- `authority.approval: false`
- `authority.export_execution: false`
- `authority.provider_call: false`
- `authority.bid_submission: false`
- `authority.legal_contractual_commitment: false`

The map must also belong to the displayed project and satisfy the complete
`decision_evidence_map.v1` response shape. The browser checks exact top-level
and nested fields for source revisions, nodes, edges and provenance, coverage,
diagnostics, limits, Proposal Blueprint slides, and authority. It also checks
unique node/edge IDs, edge endpoints, projection limits, coverage totals and
item count. Missing, malformed, authority-drifted, or authority-extended maps
hide the panel. The authority object must contain exactly the six v1 false flags
above, and the fingerprint must be a 64-character lowercase SHA-256 value. The
browser never reconstructs an evidence state from another project payload.

## Interpretation rules

Stage vocabulary is limited to `not_observed`, `needs_attention`, `in_review`,
and `observed`. An observed acceptance or approval record is not a statement
that it remains current, authorized, or operationally effective.

The panel derives one overall state and one recommended next check using this
precedence:

1. truncated projection or error diagnostic: Evidence
2. missing opportunity or recommendation: Decision
3. blocking hard filter, missing data or requirement, or unwaived `NO_GO`: Decision
4. stale Council binding or recommendation conflict: Decision
5. latest review rejected or changes requested: Review
6. latest review pending: Review
7. no review record: Review
8. target bundle document absent or stale/invalid provenance: Documents
9. warning diagnostic or candidate/unverifiable coverage: Evidence
10. otherwise: Evidence overview

`council_binding_stale` and `recommendation_council_conflict` diagnostics carry
the Decision precedence even when the separately loaded Council response is
absent. A target document is current only when at least one canonical
procurement-review, Council, or provenance status is observed and every observed
status is `current`. Missing or unknown freshness remains `needs_attention`.
The Decision summary distinguishes `NO_GO not applicable`, a recorded exception
context, and a missing exception context; none of these is operational approval.

The latest review is selected by `(prepared_at, packet_sha256)` descending. The
target bundle document is selected by `(generated_at, doc_id)` descending.
`export_evidence_not_observed` is informational and is excluded from this
precedence.

## Interaction and accessibility

Each stage control scrolls to and focuses an existing project-detail target.
It does not invoke any existing control. The panel owns one polite live region
for the navigation announcement. Reduced-motion preference changes scrolling
to immediate movement. At mobile width, the summary and the ordered stages are
single-column and controls use the full available width.

Browser tests cover both the pure render boundary and the existing
session-authenticated `loadProjectDetail()` request path. The latter continues
to load the project, procurement decision, review summaries, Council state, and
Evidence Map independently. The guide adds no request until an authorized user
explicitly selects the handoff download.

The handoff control downloads only after the browser validates the response
contract, exact body SHA-256, safe response headers, current
tenant/user/auth-revision/project scope, projection fingerprint, and the same
four stage states shown in the panel. A malformed, stale, authority-drifted, or
scope-drifted response is blocked. Downloading does not persist the handoff or
turn the observed states into approval or currentness evidence.

The recheck control is disabled until that H126 response is verified. The
browser retains the exact source only in page memory, submits it to the
session-bound H127 route, and independently verifies both handoff hashes,
semantic fingerprints, receipt hash, headers, status, and scope. Only
`source_generated_at` is excluded from the semantic comparison. `unchanged`
does not promise future currentness or atomicity. The verified H127 receipt is
kept in page memory only for an H128 disposition. `unchanged` allows only
`acknowledged_unchanged` or `review_deferred`; `changed` invalidates the old
H126 source and allows only `new_handoff_required` or `review_deferred`. A new
handoff, recheck, project load, or scope drift invalidates the prior
disposition source.

The panel displays `READ ONLY · NON-ATOMIC · NO APPROVAL/EXPORT/PROVIDER
EXECUTION`, the selected `bundle_type`, and the first 16 fingerprint characters
because the underlying project detail is assembled from independent requests,
not one atomic snapshot.

## Verification

No-cost local verification on 2026-07-27:

```bash
# H125 static and Chromium E2E: 7 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_ui_static.py \
  tests/e2e/test_guided_decision_review.py

# H124 + H125 static and Chromium E2E: 13 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_ui_static.py \
  tests/e2e/test_guided_decision_review.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_decision_evidence_map.py

# H125 current full non-live: 4477 passed, 1 skipped, 4 deselected
.venv/bin/pytest -q tests/ -m "not live"
```

H126 handoff-focused verification on 2026-07-28:

```bash
# H126 service/API/static/Chromium: 15 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_guided_decision_review_handoff_ui_static.py \
  tests/e2e/test_guided_decision_review.py

# H123-H126 map and guided review integration: 38 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_guided_decision_review_handoff_ui_static.py \
  tests/test_guided_decision_review_ui_static.py \
  tests/test_decision_evidence_service.py \
  tests/test_decision_evidence_api.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_guided_decision_review.py \
  tests/e2e/test_decision_evidence_map.py

# H126 historical full non-live: 4487 passed, 1 skipped, 4 deselected
.venv/bin/pytest -q tests/ -m "not live"

# H126/H127 service, API, static, and Chromium: 23 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_guided_decision_review_handoff_ui_static.py \
  tests/e2e/test_guided_decision_review.py

# H123-H127 map and guided-review integration: 46 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_guided_decision_review_handoff_ui_static.py \
  tests/test_guided_decision_review_ui_static.py \
  tests/test_decision_evidence_service.py \
  tests/test_decision_evidence_api.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_guided_decision_review.py \
  tests/e2e/test_decision_evidence_map.py

# H127 historical full non-live: 4495 passed, 1 skipped, 4 deselected
.venv/bin/pytest -q tests/ -m "not live"
```

H128 disposition-focused verification on 2026-07-29:

```bash
# H126-H128 service, API, static, and Chromium: 37 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_guided_decision_review_handoff_ui_static.py \
  tests/e2e/test_guided_decision_review.py

# H123-H128 map and guided-review integration: 60 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_guided_decision_review_handoff_ui_static.py \
  tests/test_guided_decision_review_ui_static.py \
  tests/test_decision_evidence_service.py \
  tests/test_decision_evidence_api.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_guided_decision_review.py \
  tests/e2e/test_decision_evidence_map.py

# Authorization/audit/security/infrastructure expansion: 488 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_decision_evidence_api.py \
  tests/test_procurement_review_authorization.py \
  tests/test_project_management.py \
  tests/test_audit.py \
  tests/test_audit_store_integrity.py \
  tests/test_infrastructure.py \
  tests/test_security.py

# H128 current full non-live: 4509 passed, 1 skipped, 4 deselected
.venv/bin/pytest -q tests/ -m "not live"
```

The E2E suite includes the real local `DecisionEvidenceMapResponse`, the
existing session-authenticated project loading path, malformed and
authority-drifted maps, precedence combinations, canonical document freshness,
local-only navigation, response/body hash verification, download scope
invalidation, reduced motion, and mobile layout. Provider APIs, AWS,
G2B live data, dataset upload, training, model promotion, production resume,
bid submission, legal approval, and contractual commitment were not executed.

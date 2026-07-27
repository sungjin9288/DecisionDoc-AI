# Guided Decision Review

## Purpose

`Guided Decision Review` is a read-only project-detail navigator. It groups
already-loaded decision, evidence, review, and document records into four
inspection targets:

1. Decision
2. Evidence
3. Review
4. Documents

It does not create a workflow state, change an approval, download an artifact,
call a provider, submit a bid, or create a legal or contractual commitment.

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
Evidence Map independently; the guide does not add another request.

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

The E2E suite includes the real local `DecisionEvidenceMapResponse`, the
existing session-authenticated project loading path, malformed and
authority-drifted maps, precedence combinations, canonical document freshness,
local-only navigation, reduced motion, and mobile layout. Provider APIs, AWS,
G2B live data, dataset upload, training, model promotion, production resume,
bid submission, legal approval, and contractual commitment were not executed.

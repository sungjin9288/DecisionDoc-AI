# Guided Decision Review Handoff Recheck

## Purpose

`guided-decision-review-recheck-receipt.v1` compares one exact Guided Decision
Review handoff with a freshly derived handoff for the same project and bundle.
It reports whether the review-state content is semantically unchanged after
excluding only the newly observed `source_generated_at`.

The recheck is review-only. Although the HTTP method is `POST` because the
source handoff is submitted in the request body, it does not persist a recheck,
approve a decision, mutate project state, execute an export, or call a provider.
H128 can bind an allowlisted review disposition to one browser-verified receipt
as described in
[Guided Decision Review Disposition](./GUIDED_DECISION_REVIEW_DISPOSITION.md).
That follow-up remains non-persistent, does not bind reviewer identity, and
creates no approval or execution authority.

## Route and access

```http
POST /projects/{project_id}/guided-decision-review-handoff/recheck
Content-Type: application/json

{
  "contract_version": "guided-decision-review-recheck-request.v1",
  "source_handoff": { "...": "guided-decision-review-handoff.v1" },
  "source_handoff_sha256": "<64-character lowercase SHA-256>"
}
```

The route uses the same session-bound procurement reviewer dependency as the
Decision Evidence Map and H126 handoff:

- a current tenant admin may recheck a tenant project;
- a member must have the exact active review assignment;
- API key, Ops key, sessionless JWT, viewer, foreign tenant, unassigned member,
  and nonexistent project access do not create recheck authority.

Authorization is resolved before project evidence is returned. The submitted
handoff must pass the strict H126 schema, exact canonical body hash,
route-project binding, and current bundle binding.

## Source trust boundary

The request body is client supplied. A valid source hash proves only that the
submitted object and hash agree; it does not prove that this server issued the
source earlier, that it was persisted, or that it was approved.

The product UI narrows this boundary further. It enables recheck only after an
H126 download response has passed body-hash, response-header, contract,
authority, current map, and browser-scope validation. The verified source is
kept in page memory only. Project, tenant, user, auth revision, project-load, or
newer-request drift clears that source. It is not written to `localStorage`,
`sessionStorage`, a server store, or an audit body.

## Comparison semantics

The service derives a fresh `guided-decision-review-handoff.v1` through the same
authorized map and project-document path as H126. It then computes two
SHA-256 fingerprints over canonical handoff JSON after removing exactly:

```json
["source_generated_at"]
```

All other fields remain in the comparison, including project, bundle,
projection fingerprint, overall state, recommended next check, four stage
records, read-only fields, and the exact false authority object.

- `unchanged` means those semantic handoff fields matched during this request.
- `changed` means at least one compared field differed.

`unchanged` is not a currentness guarantee after the response and does not make
the independent source reads atomic. `changed` is a normal read-only result,
not an error. The browser keeps the verified H127 receipt in page memory only
so H128 can bind an allowed disposition. A `changed` receipt discards the old
H126 source and disables recheck, while still allowing only
`new_handoff_required` or `review_deferred`. A new handoff, recheck, project
load, or browser-scope drift invalidates the prior H127 disposition source.

## Receipt contract

The response is UTF-8 canonical JSON with sorted keys, compact separators,
ASCII escaping, and one trailing newline. It fixes:

- `contract_version: guided-decision-review-recheck-receipt.v1`
- exact source and current H126 handoffs plus each canonical SHA-256
- source and current review-state fingerprint SHA-256
- `review_state_status: unchanged | changed`
- `fingerprint_algorithm: sha256`
- `volatile_fields_excluded: ["source_generated_at"]`
- `review_state_only: true`
- `review_only: true`
- `read_only: true`
- `snapshot_atomic: false`
- `requires_recheck_before_reliance: true`
- `recheck_persisted: false`
- the same six false mutation, approval, export, provider, bid, and
  legal/contractual authority fields as H126

Response headers bind the exact receipt and current observation:

- `X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256`
- `X-DecisionDoc-Projection-Fingerprint`
- `X-DecisionDoc-Review-State-Status`
- `X-DecisionDoc-Operational-Approval: false`
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`
- attachment `Content-Disposition`

The browser independently recalculates both handoff hashes, both semantic
fingerprints, expected status, exact receipt body hash, safe headers, current
projection fingerprint, and current tenant/user/auth/project scope before
download.

## Audit and limitations

Successful requests record
`procurement.guided_review_handoff_recheck` with source/current handoff hashes,
source/current review-state fingerprint hashes, status, and fixed read-only
fields. The audit entry omits the source and current handoff bodies, review
rationale, session ID, token, IP, and User-Agent.

The receipt does not prove prior server issuance, external authenticity,
requirement satisfaction, approval, export execution, provider execution, bid
submission, legal or contractual commitment, dataset upload, training, model
promotion, deployment, or service resume. It is not persisted and does not
freeze future state.

## Verification

No-cost local verification on 2026-07-28:

```bash
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

# Authorization/audit/security/infrastructure expansion: 481 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_decision_evidence_api.py \
  tests/test_procurement_review_authorization.py \
  tests/test_project_management.py \
  tests/test_audit.py \
  tests/test_audit_store_integrity.py \
  tests/test_infrastructure.py \
  tests/test_security.py

# H127 historical full non-live: 4495 passed, 1 skipped, 4 deselected
.venv/bin/pytest -q tests/ -m "not live"
```

These checks use local/mock records and Chromium. They do not call a paid
provider, AWS runtime, G2B live API, dataset upload, training, model promotion,
deployment, production service, bid, legal, or contractual endpoint.

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

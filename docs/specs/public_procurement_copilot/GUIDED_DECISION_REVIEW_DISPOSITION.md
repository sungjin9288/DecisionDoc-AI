# Guided Decision Review Disposition Receipt

## Purpose

`guided-decision-review-disposition-receipt.v1` binds one allowlisted review
disposition to one exact H127 recheck receipt. Before a successful canonical
H128 body returns, the server creates and exact-read-backs a hash-only,
same-backend issuance metadata object for that exact body SHA-256. It lets an authorized reviewer
carry a deterministic statement such as “unchanged state acknowledged” or “new
handoff required” without creating reviewer identity evidence, workflow state,
approval, persistence, or execution authority.

The route uses `POST` because the exact source receipt and selected disposition
are submitted in the request body. It does not mutate the project.

## Route and access

```http
POST /projects/{project_id}/guided-decision-review-handoff/review-disposition
Content-Type: application/json

{
  "contract_version": "guided-decision-review-disposition-request.v1",
  "source_recheck_receipt": {
    "...": "guided-decision-review-recheck-receipt.v1"
  },
  "source_recheck_receipt_sha256": "<64-character lowercase SHA-256>",
  "review_disposition": "acknowledged_unchanged"
}
```

The route uses the current session-bound procurement reviewer dependency and
the same project access boundary as the Decision Evidence Map:

- a current tenant admin may issue a receipt for a tenant project;
- a member must have the exact active review assignment;
- API key, Ops key, sessionless JWT, viewer, foreign tenant, unassigned member,
  and nonexistent project access do not create disposition authority.

The access check does not recompute a fresh Decision Evidence projection. H128
binds an already verified H127 observation rather than claiming another current
observation.

## Source verification

The server reparses the strict H127 contract and independently verifies:

- exact canonical source receipt SHA-256;
- route project and source/current handoff project binding;
- source/current bundle equality;
- source and current canonical handoff SHA-256;
- source and current semantic fingerprint SHA-256;
- expected `unchanged` or `changed` status;
- the H127 read-only, non-atomic, recheck-required, non-persisted, and false
  authority fields.

A client-supplied receipt and matching hash still do not prove prior server
issuance. The product UI narrows the source to the exact H127 response that it
already verified and retained in page memory. It does not import a receipt from
browser storage or a local file.

## Disposition matrix

Only these combinations are valid:

| H127 status | Allowed disposition |
|---|---|
| `unchanged` | `acknowledged_unchanged`, `review_deferred` |
| `changed` | `new_handoff_required`, `review_deferred` |

`acknowledged_unchanged` means only that the submitted H127 semantic comparison
was unchanged. `new_handoff_required` records only the bounded handling of a
changed comparison. `review_deferred` postpones the human review. None of these
values approve a decision or replace a fresh handoff and recheck.

## Receipt contract

The response is UTF-8 canonical JSON with sorted keys, compact separators,
ASCII escaping, and one trailing newline. It fixes:

- `contract_version: guided-decision-review-disposition-receipt.v1`
- route project and bundle
- exact source H127 receipt and canonical SHA-256
- current handoff and review-state fingerprint SHA-256
- H127 `review_state_status`
- allowlisted `review_disposition`
- canonical `disposition_binding_sha256`
- `receipt_status: issued`
- `review_state_only: true`
- `review_only: true`
- `read_only: true`
- `reviewer_identity_bound: false`
- `snapshot_atomic: false`
- `requires_recheck_before_reliance: true`
- `disposition_receipt_persisted: false`
- the same six false mutation, approval, export, provider, bid, and
  legal/contractual authority fields

The disposition binding covers project, bundle, source receipt hash, current
handoff hash, current semantic fingerprint, H127 status, and disposition.

Response headers include:

- `X-DecisionDoc-Guided-Review-Disposition-Receipt-SHA256`
- `X-DecisionDoc-Projection-Fingerprint`
- `X-DecisionDoc-Review-State-Status`
- `X-DecisionDoc-Operational-Approval: false`
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`
- attachment `Content-Disposition`

## Browser boundary

The disposition control remains disabled until an H127 response has passed
body/header, embedded handoff, semantic fingerprint, status, authority, and
scope validation. The browser:

- keeps the verified H127 receipt in page memory only;
- enables only dispositions allowed for the verified status;
- submits the exact receipt and body hash;
- independently recalculates source receipt and disposition binding hashes;
- verifies the response body hash, safe headers, project, bundle, status,
  disposition, current tenant/user/auth/project-load scope, and false authority;
- discards stale sources and late completions after project, tenant, user, auth,
  selection, handoff, recheck, or newer-request drift.

A `changed` H127 receipt can still issue `new_handoff_required` or
`review_deferred` after the old H126 source is discarded. It cannot issue
`acknowledged_unchanged`.

## Local mock browser demo

The following local-only capture starts an ephemeral FastAPI server with the
mock provider and temporary storage. It uses the actual app shell to create a
project, load its Decision Evidence Map, render Guided Review, and download the
H126 handoff, an unchanged H127 recheck, and the H128
`acknowledged_unchanged` receipt.

```bash
python3 scripts/capture_guided_decision_review_demo_evidence.py

python3 scripts/capture_guided_decision_review_demo_evidence.py --check-only
```

It writes five screenshots to `evidence/screenshots/`, the secret-free
`decisiondoc.guided_review_local_demo.v1` receipt to
`evidence/cli-logs/guided_review_h126_h128_demo.json`, and sanitized H126,
H127, and H128 JSON bodies beside that receipt. Each saved body and screenshot
has an exact allowlisted basename, size, and SHA-256 binding in the receipt.
The persisted-receipt validator rereads those local artifacts and independently
rechecks the canonical H126/H127/H128 Pydantic and service chain without
starting a browser. An artifact-directory flock serializes the complete capture
so concurrent runs cannot mix outputs. The capture snapshots and restores
`os.environ`; its summary receipt records no credentials, tokens, project
identifier, or server URL. The downloaded canonical contract bodies retain
their local fixture `project_id` for exact binding. The flow does not add H129
persistence or authority.

H129 is a separate immutable reviewer-attribution registry defined in
[`GUIDED_DECISION_REVIEW_DISPOSITION_REGISTRY.md`](./GUIDED_DECISION_REVIEW_DISPOSITION_REGISTRY.md).
The H128 local demo deliberately does not create that record.

The repeatable local fixture uses the locked `ProcurementDecisionStore.upsert`
path to populate Decision and Evidence without a G2B/provider call. It does not
persist a procurement review or project document, so Review and Documents remain
`not_observed`; the receipt states that boundary rather than simulating a later
authority-bearing workflow.

## Audit and limitations

Successful requests record `procurement.guided_review_disposition` with only
the source receipt SHA-256, current handoff/fingerprint SHA-256, status,
disposition, binding SHA-256, response SHA-256, and fixed false boundary fields.
The audit entry omits source receipt and handoff bodies, rationale, reviewer
identity binding, session ID, token, IP, and User-Agent.

The H128 receipt body is not persisted server-side. Its separate issuance
metadata proves only that the selected backend contains one strict metadata
object for this exact canonical body hash; it stores no receipt body, reviewer,
session, network value, token, rationale, secret, approval, or execution
authority. This same-backend existential proof is not a signature, actor
attestation, currentness proof, atomic snapshot, approval, or external
authenticity. It does not prove prior issuance,
human identity, human approval, future currentness, an atomic snapshot,
requirement satisfaction, export execution, provider execution, bid submission,
legal or contractual commitment, dataset upload, training, model promotion,
deployment, or service resume.

## Verification

No-cost local verification on 2026-07-29:

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

These checks use local/mock records and Chromium. They do not call a paid
provider, AWS runtime, G2B live API, dataset upload, training, model promotion,
deployment, production service, bid, legal, or contractual endpoint.

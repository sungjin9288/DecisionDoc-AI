# Guided Decision Review Handoff

## Purpose

`guided-decision-review-handoff.v1` packages the current Guided Decision Review
observation as a canonical JSON attachment. It lets an authorized reviewer carry
the current Decision, Evidence, Review, and Documents checklist into a separate
human review without granting workflow or operational authority.

The handoff is derived on request. It is not persisted, approved, submitted, or
sent to a provider.

H127 adds a bounded comparison described in
[Guided Decision Review Handoff Recheck](./GUIDED_DECISION_REVIEW_RECHECK.md).
It compares one exact handoff with a fresh observation and returns a
non-persisted review-only receipt. It does not make either observation atomic or
grant workflow authority.

## Route and access

```http
GET /projects/{project_id}/guided-decision-review-handoff?bundle_type=proposal_kr
```

The route uses the same session-bound procurement reviewer dependency as the
Decision Evidence Map:

- a current tenant admin may read a tenant project;
- a member must have the exact active review assignment;
- API key, Ops key, sessionless JWT, viewer, foreign tenant, unassigned member,
  and nonexistent project access do not create handoff authority.

Authorization is completed before project evidence is returned. The response
uses `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, an attachment
filename derived from the projection fingerprint, and these binding headers:

- `X-DecisionDoc-Guided-Review-Handoff-SHA256`
- `X-DecisionDoc-Projection-Fingerprint`
- `X-DecisionDoc-Operational-Approval: false`

## Contract

The response is UTF-8 canonical JSON with sorted keys, compact separators, ASCII
escaping, and one trailing newline. Its SHA-256 header binds the exact downloaded
bytes.

The contract fixes:

- `contract_version: guided-decision-review-handoff.v1`
- `source_contract_version: decision_evidence_map.v1`
- source timestamp, project, bundle type, and full projection fingerprint
- `read_only: true`
- `snapshot_atomic: false`
- `requires_recheck_before_reliance: true`
- `handoff_persisted: false`
- one overall state and one recommended next check
- exactly four ordered stages: Decision, Evidence, Review, Documents
- the same six false mutation, approval, export, provider, bid, and
  legal/contractual authority flags as the source map

The server derives the handoff from the authorized current map and separately
observed project records. These reads are not one transaction. A matching hash
therefore proves exact response bytes, not currentness, external authenticity,
or a stable snapshot.

## Browser boundary

The browser requests the handoff only from the existing Guided Decision Review
panel. Before creating a download, it verifies:

- HTTP content type, attachment disposition, `no-store`, and `nosniff`;
- exact body SHA-256 and projection fingerprint headers;
- contract versions, project, bundle, non-empty fresh-route source timestamp,
  fingerprint, and all fixed read-only/non-atomic/recheck/persistence fields;
- exact four-stage order, status vocabulary, overall state, and recommended next
  check against the currently rendered Guided Decision Review;
- exact six-field false authority object;
- current tenant, user, auth revision, project, and project-load scope.

Malformed, stale, authority-drifted, or scope-drifted responses do not download.
Changing project or leaving project detail invalidates the handoff scope.
The route recomputes the source projection, so its `source_generated_at` may
differ from the already displayed map even when the semantic fingerprint is
unchanged. The browser uses exact fingerprint equality, not timestamp equality,
as the source-state binding.

After a successful H126 verification, the browser keeps the exact source
handoff and hash in page memory and enables the H127 recheck control. It does
not recover a source from browser storage or an arbitrary file. Project,
tenant, user, auth revision, project-load, or newer-request drift clears the
source. A verified `changed` receipt also clears the source and requires a fresh
project load and handoff.

## Audit and limitations

Successful requests record
`procurement.guided_review_handoff_download` with aggregate review-only fields,
the projection fingerprint, and exact handoff SHA-256. Session ID, token, IP,
User-Agent, private review rationale, and artifact bytes are not copied into the
audit entry.

The handoff does not persist a review record, freeze source state, satisfy a
requirement, approve a decision, execute an export, call a provider, submit a
bid, upload a dataset, start training, promote a model, resume a service, or
create legal or contractual commitment. Re-read current canonical records before
relying on it.

## Verification

No-cost local verification on 2026-07-28:

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

# Authorization/audit/security/infrastructure expansion: 477 passed
.venv/bin/pytest -q \
  tests/test_guided_decision_review_handoff.py \
  tests/test_decision_evidence_api.py \
  tests/test_procurement_review_authorization.py \
  tests/test_project_management.py \
  tests/test_audit.py \
  tests/test_audit_store_integrity.py \
  tests/test_infrastructure.py \
  tests/test_security.py

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

# H127 current full non-live: 4495 passed, 1 skipped, 4 deselected
.venv/bin/pytest -q tests/ -m "not live"
```

These checks use local/mock records and Chromium. They do not call a paid
provider, AWS runtime, G2B live API, deployment, training, promotion, or
production service.

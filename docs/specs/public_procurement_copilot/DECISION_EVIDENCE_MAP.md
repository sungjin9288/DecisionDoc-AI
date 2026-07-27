# Decision Evidence Map

## Status

Implemented as a local, read-only project projection behind
`DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`.

The map helps an authorized reviewer inspect how procurement evidence, Decision
Council reasoning, generated documents, reviews, approvals, and report workflow
state relate to one another. It does not create operational authority.

## API contract

```http
GET /projects/{project_id}/decision-evidence-map?bundle_type=proposal_kr
```

Supported bundle types:

- `bid_decision_kr`
- `rfp_analysis_kr`
- `proposal_kr`
- `performance_plan_kr`

The route requires a current session-bound procurement reviewer:

- a tenant admin can inspect projects in the active tenant;
- a member can inspect a project only when an authorized review record is
  assigned to that member;
- API keys, Ops keys, sessionless JWTs, and viewers do not grant access;
- unassigned, differently assigned, and nonexistent project IDs return the same
  not-found response to a member.

Responses set `Cache-Control: no-store`, include a deterministic projection
fingerprint, and declare:

```json
{
  "contract_version": "decision_evidence_map.v1",
  "read_only": true,
  "snapshot_atomic": false,
  "authority": {
    "mutation": false,
    "approval": false,
    "export_execution": false,
    "provider_call": false,
    "bid_submission": false,
    "legal_contractual_commitment": false
  }
}
```

The projection is bounded to 200 nodes and 400 edges. Nodes and edges are sorted
deterministically. The fingerprint excludes `generated_at`, so the same observed
records produce the same fingerprint while the response timestamp can change.

## Evidence model

Node types:

- source
- claim
- requirement
- alternative
- risk
- recommendation
- document
- review
- approval
- export

Every edge carries its source kind, source identity, source revision, field
path, content SHA-256, and evidence level. Source revisions are also listed
separately so a reviewer can identify which record versions were observed.

The projection reads existing tenant-scoped records only:

- procurement decision and immutable source snapshot metadata;
- the latest Decision Council session with current procurement binding;
- project documents and their stored provenance;
- review-safe procurement review summaries;
- project approval records;
- report workflow planning, slide, and export-readiness state;
- project knowledge metadata.

Private review receipt, rationale, stable user ID, attestation, session, network,
and tenant fields are not projected.

## Coverage rules

Requirement coverage uses four values:

- `explicit`: a persisted project document stores the exact canonical
  requirement node ID in `source_evidence_refs`;
- `candidate`: reserved by the contract for a future non-authoritative review
  candidate;
- `missing`: the authoritative procurement record marks the item failed,
  blocked, action-needed, unknown, or missing;
- `unverifiable`: the source record exists, but no exact downstream reference
  proves that a document used it.

Text similarity, keyword overlap, and fuzzy matching never produce `explicit`
coverage. An exact reference proves only that the document stored the canonical
requirement reference. It does not prove that the requirement was satisfied.

Generation stores canonical references only for procurement context that was
actually injected into a supported downstream bundle. Manual project document
creation can accept the same validated references. Final report workflow
promotion carries `requirement:` references from approved slide source and
reference metadata into the resulting project document.

## Proposal Blueprint and export boundary

The Proposal Blueprint selects the current project report workflow for the
requested bundle and projects:

- narrative arc;
- slide titles and statuses;
- source and reference IDs;
- required evidence and data needs;
- open questions and risk notes.

The export node means that the existing report workflow has enough state to use
its PPTX export path. `actual_export_observed` remains false because the current
export path does not persist a durable export receipt. Loading the map does not
generate a PPTX, call a provider, approve a document, submit a bid, or create a
legal commitment.

## UI

The project detail screen renders:

- a pointer-selectable decorative fixed-column SVG for up to 60 filtered nodes,
  prioritizing the selected node and its direct neighbors;
- the canonical accessible table for the complete bounded result, with native
  button keyboard behavior and pressed state;
- search, node-type, status, gaps-only, lineage-only, and source-visibility
  filters with an explicit filtered count and reset control;
- keyboard-selectable table node details with one-hop focus/dimming and focus
  restoration after rerender;
- separate inbound and outbound relation detail, including stored edge
  provenance: relation type and status, counterpart node, source kind/ID/
  revision, field path, content SHA-256, and provenance level;
- diagnostic targets that select an in-projection node without silently
  substituting another filtered node; a filtered target is explicitly included
  and announced, while a target outside the bounded projection is reported as
  omitted;
- an Escape-exit presentation layout that changes only the panel CSS layout;
- coverage, Proposal Blueprint reference counts, and diagnostic summaries.

Browser state is scoped to the current tenant, user, authorization revision,
project, bundle type, and projection fingerprint. A changed scope resets
selection, filters, and presentation layout rather than carrying an earlier
reader's interpretation into a new projection. The browser builds an O(N+E)
adjacency index from the bounded response; it does not request additional data
or infer new relationships.

`Gaps only` includes non-explicit requirement coverage, explicit failure
states, and warning/error diagnostic targets. `pending` and `in_review` do not
become gaps solely because of their status. `Lineage only` narrows the table and
SVG to the selected node plus its direct neighbors. Hiding sources removes source
nodes, their incident edges, and source counterparts from relation detail. If a
diagnostic targets a hidden source, the browser reports that conflict and does
not silently reinsert or substitute a node. Visible and full-projection relation
counts remain separately labeled. Full labels remain available through SVG
titles, detail, and the canonical table.

The SVG is `aria-hidden` and not keyboard-focusable because the table is the
canonical accessible surface. Pointer selection on the SVG remains available
and restores focus to the corresponding table button. Presentation mode changes
only panel layout, remains one column at mobile width, and exits with Escape.
Reduced-motion preference removes node and edge transitions.

`authoritative` is presented as a provenance level only. It does not establish
truth, approval authority, requirement satisfaction, or an external source's
authenticity. A source revision or content SHA-256 records what this projection
observed; it is not an external verification claim.

Edge line style provides a non-color provenance cue: `authoritative` is solid,
`record_binding` is dashed, and `derived` is dotted. These styles describe stored
provenance level only; they are not proof or approval.

Proposal Blueprint labels slide counts with any stored source/reference string
as `Referenced slides`. That count is navigation metadata, not verified
coverage; requirement proof remains governed by the exact coverage rules above.

The UI repeats the read-only and non-atomic boundary. It has no mutation,
approval, export, provider, or submission control.

Project detail also renders [Guided Decision Review](./GUIDED_DECISION_REVIEW.md)
only after validating the complete v1 response shape, coverage totals, bounded
graph references, fingerprint, and exact false authority object. The guide
derives conservative Decision, Evidence, Review, and Documents observations
from the already-loaded records and only scrolls/focuses the matching existing
section. It does not add a request or reconstruct missing evidence from another
payload.

## Verification

No-cost verification:

```bash
# H124 UI/service/E2E subset: 17 passed (2026-07-27)
.venv/bin/pytest -q \
  tests/test_decision_evidence_service.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_decision_evidence_map.py

# H124 focused with API boundary: 21 passed (2026-07-27)
.venv/bin/pytest -q \
  tests/test_decision_evidence_service.py \
  tests/test_decision_evidence_api.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_decision_evidence_map.py

# Adjacent authorization/workflow: 387 passed (2026-07-27)
.venv/bin/pytest -q \
  tests/test_decision_evidence_api.py \
  tests/test_project_management.py \
  tests/test_report_workflow_store.py \
  tests/test_report_workflow_store_integrity.py \
  tests/test_report_workflows_api.py \
  tests/test_approval_workflow.py \
  tests/test_procurement_review_authorization.py \
  tests/test_decision_council.py \
  tests/test_decision_council_store_integrity.py \
  tests/test_project_approval_store_integrity.py \
  tests/test_pptx_endpoint.py

# Combined focused + adjacent: 404 passed (2026-07-27)
# Run the union of the two file lists above.

# H124 historical full non-live: 4470 passed, 1 skipped, 4 deselected (2026-07-27)
.venv/bin/pytest -q tests/ -m "not live"

# H125 Guided Review focused: 7 passed (2026-07-27)
.venv/bin/pytest -q \
  tests/test_guided_decision_review_ui_static.py \
  tests/e2e/test_guided_decision_review.py

# H124 + H125 static/E2E: 13 passed (2026-07-27)
.venv/bin/pytest -q \
  tests/test_guided_decision_review_ui_static.py \
  tests/e2e/test_guided_decision_review.py \
  tests/test_decision_evidence_ui_static.py \
  tests/e2e/test_decision_evidence_map.py

# H125 current full non-live: 4477 passed, 1 skipped, 4 deselected (2026-07-27)
.venv/bin/pytest -q tests/ -m "not live"
```

These checks use mock/local fixtures. Provider APIs, AWS runtime, G2B live API,
dataset upload, training execution, model promotion, production service resume,
bid submission, legal approval, and contractual commitment are outside this
verification boundary.

# Hermes-Inspired DecisionDoc Agent Implementation Plan

## Scope

Continue the DecisionDoc-native DocumentOps path without importing the Hermes runtime. Development
must preserve the existing route, service, provider, storage, tenant, approval, and audit boundaries.

## Non-Goals

- Do not add Hermes as a production dependency.
- Do not enable terminal, browser, or remote execution tools for document generation.
- Do not bypass the DecisionDoc provider factory.
- Do not upload tenant data or reviewed datasets without explicit approval.
- Do not create provider training jobs or promote models in a local development slice.
- Do not weaken the deterministic mock-provider path used by CI.

## Completed Foundation

The current codebase already provides:

- first-party Markdown skills and deterministic skill selection
- structured provider output parsing and local fallback drafts
- task-specific QA gates and score reporting
- tenant-scoped, redacted trajectory capture
- human review and quality-score recording
- SFT preview, export, quality report, and reviewed-artifact download
- dataset freeze manifests with provenance metadata
- dry-run approval, readiness, execution-request, and audit records
- ops-key governance and reviewer sign-off summaries
- a disabled provider adapter contract and side-effect-free rehearsal

The source of truth for the implemented boundary is `STATUS.md` and the referenced runtime code, not
historical phase numbers.

## Active No-Cost Development Sequence

### 1. QA Diagnostics

Goal: make local failures actionable without another evidence wrapper.

Status: implemented for the current hard-gate set. Extend the same contract when a new gate is
added.

Work:

- add a deterministic fixture for each new hard-gate failure mode
- return a stable issue code, severity, affected field, and remediation hint
- keep task-specific requirements in `app/evals/document_ops/`
- avoid provider-specific logic in the evaluation layer

Acceptance:

- a failed gate identifies what must change, not only that the gate failed
- mock-provider and fallback behavior remain deterministic
- focused agent/eval tests pass

### 2. Review Integrity

Goal: ensure only traceable human-reviewed records become training candidates.

Status: implemented. Reviewer identity and JSON-compatible metadata are validated at the storage
boundary. Identical reviews and exports are reused, while changed reviews retain prior feedback in
versioned history.

Work:

- validate reviewer identity and review metadata at the storage boundary
- keep rejected and pending trajectories out of accepted-only exports
- make duplicate review/export behavior explicit and idempotent
- preserve tenant isolation for list, review, export, and download operations

Acceptance:

- malformed or cross-tenant review attempts fail without changing stored records
- repeated valid operations have a deterministic result
- trajectory-store and API tests cover success and rejection paths

### 3. Dataset Quality

Goal: strengthen local dataset inspection before any upload decision.

Status: implemented. Candidate and file reports validate message roles, user/assistant JSON shape,
accepted review provenance, source trajectory IDs, and file checksum integrity. Reviewed exports
cannot omit provenance metadata, and checksum mismatches block dataset freeze.

Work:

- verify role/content shape for every exported message record
- report blocker counts and representative samples without exposing unrelated tenant data
- retain export checksum, source trajectory IDs, skill versions, and review provenance
- reject unsafe filenames and paths at the storage boundary

Acceptance:

- quality reports explain why records are eligible or blocked
- reviewed export artifacts can be traced back to accepted trajectories
- no network request is required

### 4. Governance Consistency

Goal: keep approval records useful while preventing them from becoming execution authority.

Status: implemented for the selected-backend, no-execution governance chain. Freeze, approval,
execution-request, and audit artifacts retain their own SHA-256 in metadata. Readiness and audit
summaries reject a missing, tampered, or stale
`export -> freeze -> approval -> request -> audit` reference.

Work:

- keep two-person request, freeze, audit, and sign-off references internally consistent
- verify artifact checksums and cross-artifact IDs before reporting a ready state
- reject `start_training`, `upload_dataset`, and `call_provider_api` in local workflows
- keep provider adapter contract and rehearsal read-only
- expose config errors when an execution flag is enabled against the stub

Acceptance:

- all governance summaries preserve `no_side_effects=true`
- execution attempts fail before provider or network code can run
- ops-key API and training-adapter tests pass

### 5. Local Product Flow

Goal: keep the browser flow aligned with the tested API contract.

Status: implemented for the local review and governance workbench. The browser now exposes the
named-actor review, export, freeze, dry-run approval, execution-request, audit, and integrity
summary paths already supported by the API. Tenant-scoped trajectory history reports the actual
filtered total and supports title/identifier/reviewer search, task/review filters, and newest- or
oldest-first page traversal without exposing an execution path. The browser requests summary-only
pages and loads a tenant-scoped full record only when a reviewer expands it. Each trajectory can then expose the stored input, full draft, evidence
status, QA gate, and review history before a reviewer records notes and an explicit human score.

Work:

- expose only controls supported by current endpoints
- show review, export eligibility, freeze, and governance state without claiming training completion
- preserve CSP nonce, API-key, ops-key, and maintenance-mode behavior
- add browser QA only when the UI behavior changes
- keep desktop and mobile controls readable without unrelated fixed navigation covering inputs
- keep trajectory history pagination aligned across storage, API, and browser state
- keep tenant-scoped search and newest/oldest ordering aligned across storage, API, and browser state
- keep summary lists and lazy-loaded detail on the same tenant and review contract
- keep training execution request records bound to the latest same-tenant read, and let the refresh
  after a successful record save supersede any read that began before the save
- keep the training audit checklist bound to the latest tenant and provider/model planning context,
  remove stale audit actions after a planning change, and do not let an older read hide a completed audit export
- keep Adapter Contract and Rehearsal bound to their latest tenant and provider/model planning context,
  and replace old configuration or artifact evidence with an explicit recheck state when that context changes
- keep SFT Export Preview and the reviewed artifact list bound to the selected task, and Training Plan Preview
  bound to its exact provider/model query; replace open evidence with a recheck state when either input changes
- append detail views and review decisions to the tenant audit log without copying inputs, drafts, or review notes
- compare the submitted review version inside the storage lock, preserve idempotent retries, and reject
  a different stale review with `409` before it can overwrite newer human evidence
- capture an unsaved review draft in user-tenant-trajectory keyed page memory as the reviewer types,
  restore it after ordinary list refreshes or conflict recovery only in that authenticated context,
  clear it on logout or invalid session, and never persist it to storage or local browser data
- align browser tenant headers from every access-token login and refresh path, reject unauthorized selector changes
  without weakening `TENANT_MISMATCH`, and reload the entire app after an authorized tenant change
- ignore stale trajectory responses when operators change filters before an earlier request completes
- return to the first or last valid page when filters or reviews change the visible result set
- require review notes and an explicit human score in the browser before accepting a trajectory

Acceptance:

- visible labels match runtime state and authorization boundaries
- stale review conflicts refresh the browser with the latest stored version instead of retrying a write
- reviewer notes and score survive that refresh only for the same user and tenant; clearing both inputs,
  completing a write, logout, or session invalidation removes the draft, and another auth context cannot read it
- stale local tenant state is replaced by the authenticated token tenant before tenant-scoped requests,
  while denied selector changes leave both the active context and persisted selector value unchanged
- no hidden control can trigger upload, training, or production operations
- infrastructure and report-workflow integration tests pass

## Deferred Live Proof

Live provider evaluation is a separate task. It begins only after the user approves the provider,
budget, scenario count, and evidence-retention policy.

Required preconditions:

1. Select provider and model explicitly.
2. Set a hard request/token budget.
3. Use synthetic or approved non-sensitive inputs.
4. Capture request ID, model, latency, usage, and redacted output.
5. Review the trajectory manually before export.
6. Stop after the approved sample count.

This live proof does not authorize dataset upload, fine-tuning, model promotion, AWS deployment, or
production service resume.

## Verification Gates

Focused local gate:

```bash
pytest -q \
  tests/agents/test_document_ops_agent.py \
  tests/evals/test_document_ops_gates.py \
  tests/test_document_ops_agent_api.py \
  tests/test_document_ops_training_adapter.py \
  tests/storage/test_trajectory_store.py
```

Integration gate when API or UI behavior changes:

```bash
pytest -q tests/test_report_workflows_api.py tests/test_infrastructure.py
```

Repository regression gate before handoff:

```bash
pytest -q tests/ -m "not live" --tb=short
```

## Approval Gate For Real Training

Do not implement or run real training until a separate decision records:

- approved provider and base model
- dataset classification and transfer permission
- cost ceiling and billing owner
- named requester and independent approver
- cancellation, monitoring, evaluation, promotion, and rollback procedures
- explicit authorization for each external side effect

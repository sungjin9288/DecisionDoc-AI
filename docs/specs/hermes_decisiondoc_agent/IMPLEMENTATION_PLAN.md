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
- latest-run browser ownership for concurrent Agent results, with stale same-tenant saves observed without replacing the current draft or filters

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
- bind trajectory list responses to the exact tenant, task/review filters, search query, and newest/oldest ordering captured when the request starts, including the search debounce window
- keep summary lists and lazy-loaded detail on the same tenant and review contract
- keep training execution request records bound to the latest same-tenant read, and let the refresh
  after a successful record save supersede any read that began before the save
- keep the training audit checklist bound to the latest tenant and provider/model planning context,
  remove stale audit actions after a planning change, and do not let an older read hide a completed audit export
- keep Adapter Contract and Rehearsal bound to their latest tenant and provider/model planning context,
  and replace old configuration or artifact evidence with an explicit recheck state when that context changes
- keep SFT Export Preview and the reviewed artifact list bound to the selected task, and Training Plan Preview
  bound to its exact provider/model query; replace open evidence with a recheck state when either input changes
- keep export, freeze, dry-run approval, execution-request, audit-export, and provider-backed Agent controls
  single-flight while pending, restore their button after success or failure, and leave read-only refresh independent
- for captured Agent runs, claim an optional payload-bound operation identity in the shared backend
  before provider execution and replay only a verified terminal result
- reject changed-payload reuse, concurrent duplicate execution, failed or corrupt retry state before
  another provider call; uncaptured runs retain the existing non-persisted behavior
- expose only tenant-scoped retry-decision fields from an authenticated operation status read, and audit
  the operation identity and status without copying private owner, hash, or result data
- after a lost browser response, require the status schema, exact operation identity, state-specific timestamps,
  replay decision, next action, read-only flag, and provider-call denial to agree before acting
- keep the captured tenant and payload only in current-page memory while status is mismatched, unavailable,
  or running; let the Agent button and explicit status recheck share one recovery promise instead of creating a new operation
- read recovery status without cache, exact-replay only a verified terminal success, end pending recovery with
  an evidence-review warning for failed state, and clear pending data on logout or invalid session
- before a captured POST, persist only the marker schema, tenant, and operation identity in same-origin
  shared storage; never persist the request payload or treat this marker as replay authority
- scope marker storage keys by tenant so foreign tenant reads, writes, and cleanup preserve each other;
  clear only the previous context on an authorized switch and keep owner-only base-key compatibility
- persist the next browser tenant before changing in-memory context or clearing previous-context evidence;
  preserve the current tenant, draft, recovery promise, and marker when that storage write fails
- commit login, registration, refresh, and LDAP browser sessions through one helper after token-claim validation;
  restore the previous access/refresh credentials and tenant when any browser write fails
- issue new register, login, invite, LDAP, SAML, GCloud, and password-change token pairs against one
  tenant-scoped persisted session identity; preserve it across refresh and revoke only that exact session on logout
- start exact-session server revocation before local logout cleanup, but never retain browser credentials or
  page-memory evidence while waiting; report an unavailable endpoint as unconfirmed server revocation
- return an explicit refresh outcome to 401 callers; retry only a refreshed session, clear evidence only for rejected
  credentials, and preserve the previous session for endpoint or browser-storage failures
- where supported, serialize marker inspection and claim with a tenant-scoped Web Lock so simultaneous tabs
  converge on one POST; use tab storage only when shared storage is unavailable
- after reload, from another tab, or after the owner tab closes, inspect only the strict current-tenant status,
  block a new POST, and require explicit confirmation that backend execution is not canceled before release
- keep payload-free exact replay, cross-device coordination, process-crash recovery, and atomic simultaneous claims
  without Web Locks outside this browser contract; never retry corrupt state or treat status as execution authority
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
- a failed auth-session tenant commit keeps the prior credentials, current user, draft, recovery promise,
  and marker instead of exposing a partially refreshed identity
- upper 401 recovery reports storage and temporary refresh failures without clearing those restored credentials or
  DocumentOps evidence, while an explicitly rejected refresh credential still ends the invalid session
- concurrent 401 callers join one browser refresh; generic mutating requests require an explicit retry after refresh,
  and a late refresh response cannot replace a newer login session
- same-origin auth storage changes invalidate an older in-flight refresh even when another tab reuses the same
  refresh-token bytes, while unrelated storage keys do not change auth revision
- a different signed user or tenant from another tab reloads the receiving page once so page-memory evidence is
  rebuilt under the new session; same-identity token rotation stays quiet and preserves current work
- a persisted role or active-state change takes effect on the next protected request and new SSE subscription;
  another tab's role-changing token reloads stale page authorization state while same-role rotation stays quiet
- a password change increments the persisted credential version with the password hash, rejects every older access
  and refresh token, commits a replacement pair in the initiating browser, and reloads another same-origin tab
  whose credential version is stale
- exact logout rejects the signed current session without invalidating a separate login; copied same-session
  credentials fail on the next protected request, refresh, or open SSE recheck
- corrupt or unavailable session state fails closed without changing the original object, and logout audit copies
  neither access/refresh credentials nor the private session identity
- legacy sessionless credentials remain bounded by expiry and credential version but cannot use exact logout,
  inventory, selected revoke, or bulk revoke; User-Agent/IP inventory, current-inclusive all-device logout,
  administrator mass revoke, expired-session GC, and immediate push stay outside this contract
- self-service inventory validates every direct object under the selected-backend tenant session prefix before
  returning active current-version sessions; selected revoke preserves the current browser, hides foreign/missing
  target differences, and treats an already-revoked owned target as retry-safe success
- strict-confirmed bulk revoke preserves current, revokes every other session in the validated snapshot, converges
  to count zero on retry, and fails before mutation when the prefix is corrupt; sequential writes do not claim a
  multi-object transaction or include sessions created after the snapshot
- the browser renders only current/other and start/expiry metadata, keeps session IDs out of the DOM, gives selected
  and bulk actions one single-flight, and rejects stale list/revoke completions by token, modal, request, and revoke
  generations; audit stores the bulk count without credentials or session IDs
- an open SSE subscription rechecks token expiry and persisted user/session authority within 15 seconds, stops application
  events on revocation or authority failure, and preserves browser credentials when the failure is retryable
- no hidden control can trigger upload, training, or production operations
- an exact captured-run replay does not call the provider or record usage twice, while an uncertain
  prior attempt requires explicit evidence review and a new operation identity
- mismatched success and running status produce no Agent POST, while a later same-operation success recovers
  the original payload and operation identity
- simultaneous Agent-button and status-recheck actions join one status read and one exact replay
- reload, another tab, and a page reopened after owner-tab close perform status reads and no Agent POST until
  explicit release; simultaneous Web-Lock-capable tabs produce one POST, while storage failure preserves same-page use
- different tenant markers coexist in one origin, tenant-scoped cleanup preserves foreign markers, and a valid
  legacy base-key marker remains visible only to its owning tenant
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

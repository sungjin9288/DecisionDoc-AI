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

Work:

- keep two-person request, freeze, audit, and sign-off references internally consistent
- reject `start_training`, `upload_dataset`, and `call_provider_api` in local workflows
- keep provider adapter contract and rehearsal read-only
- expose config errors when an execution flag is enabled against the stub

Acceptance:

- all governance summaries preserve `no_side_effects=true`
- execution attempts fail before provider or network code can run
- ops-key API and training-adapter tests pass

### 5. Local Product Flow

Goal: keep the browser flow aligned with the tested API contract.

Work:

- expose only controls supported by current endpoints
- show review, export eligibility, freeze, and governance state without claiming training completion
- preserve CSP nonce, API-key, ops-key, and maintenance-mode behavior
- add browser QA only when the UI behavior changes

Acceptance:

- visible labels match runtime state and authorization boundaries
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

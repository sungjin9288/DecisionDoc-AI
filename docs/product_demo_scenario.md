# DecisionDoc AI Local Product Demo Scenario

Updated: 2026-06-23

This document defines the first local demo scenario for the product direction in [DecisionDoc AI Product Direction](./product_direction.md) and the execution plan in [DecisionDoc AI Product Execution Plan](./product_execution_plan.md).

It is a planning and implementation target. It does not claim customer adoption, deployed availability, measured business impact, live provider execution, or autonomous operational approval.

## 1. Scenario Goal

Prove the core DecisionDoc AI product loop with one procurement-oriented decision package:

> Given a public procurement opportunity and a simple company capability profile, produce a reviewable decision package that shows recommendation, evidence, hard gaps, validation status, reviewer handoff, pending sign-off, and export boundaries.

The demo must run locally with deterministic inputs, `mock` provider behavior where provider output is needed, and local storage.

## 2. Target Reviewer

The scenario is designed for a proposal lead, delivery lead, or executive reviewer who needs to answer:

- Should we pursue this opportunity?
- What evidence supports the recommendation?
- What blocks or weakens the bid?
- What must be reviewed before proposal drafting starts?
- What is not authorized by this package?

## 3. Demo Inputs

Sample fixture files are available under [docs/samples/procurement_decision_package_local_demo](./samples/procurement_decision_package_local_demo/).

### 3.1 Procurement opportunity

Use a small fixture-style opportunity record with these fields:

```json
{
  "opportunity_id": "local-procurement-demo-001",
  "title": "Public Agency Document Workflow Modernization Pilot",
  "buyer": "Sample Public Agency",
  "budget_range": "KRW 80M-120M",
  "deadline_days": 21,
  "required_capabilities": [
    "document workflow analysis",
    "secure web application delivery",
    "public-sector reporting",
    "operator training"
  ],
  "mandatory_requirements": [
    "recent public-sector project reference",
    "security handling plan",
    "Korean proposal package"
  ],
  "source_type": "local_fixture"
}
```

### 3.2 Capability profile

Use a local company capability profile with:

- service lines,
- public-sector references,
- delivery team availability,
- security and compliance notes,
- partner assumptions,
- excluded risk conditions,
- preferred budget range,
- internal go/no-go rules.

### 3.3 Operator notes

Use short operator notes to model reviewer context:

- target outcome,
- known uncertainty,
- reviewer owner,
- proposal deadline sensitivity,
- required follow-up before drafting.

## 4. Expected Decision Package

The scenario should produce a package with these sections or files:

| Artifact | Purpose | Required content |
|---|---|---|
| decision package JSON | structured product object | opportunity, recommendation, scores, evidence, gaps, boundaries |
| decision summary Markdown | reviewer-readable summary | recommendation, rationale, hard gaps, next actions |
| evidence summary | trust layer | source references, known missing data, confidence notes |
| bid-readiness checklist | proposal preparation view | required docs, owners, blockers, due state |
| validation summary | deterministic guardrail | schema status, boundary status, unresolved gaps |
| reviewer handoff | human review workflow | reviewer, requested decision, non-authorization note |
| pending sign-off | explicit review state | pending status, reviewer fields, no operational approval |
| export manifest | package boundary | included artifacts and excluded operational actions |

The expected package shape is captured in [expected_decision_package.json](./samples/procurement_decision_package_local_demo/expected_decision_package.json). It is a fixture target, not proof that a package builder has already executed.

## 5. Recommendation Contract

The package must output exactly one recommendation:

- `GO`
- `CONDITIONAL_GO`
- `NO_GO`

The local demo should initially use `CONDITIONAL_GO` because it is the most useful scenario for review workflow:

- no hard-fail is present,
- score or readiness is not strong enough for unconditional `GO`,
- missing evidence and follow-up actions remain visible,
- reviewer sign-off is required before proposal drafting.

## 6. Evidence Rules

The package must not hide uncertainty. It should separate:

- source facts from inferred notes,
- available evidence from missing evidence,
- hard blockers from remediable gaps,
- reviewer acceptance from operational approval.

Every recommendation rationale should point to at least one evidence item or explicitly say that the evidence is missing.

## 7. Authorization Boundary

The local demo package does not authorize:

- provider API execution,
- AWS runtime execution,
- dataset upload,
- training execution,
- model promotion,
- production service resume,
- bid submission,
- legal approval,
- contractual commitment.

Reviewer sign-off means the decision package was reviewed. It does not mean any operational action is approved.

## 8. Demo Walkthrough

The target local walkthrough is:

1. Load the procurement opportunity fixture.
2. Load the capability profile fixture.
3. Build or generate the decision package.
4. Show recommendation and hard-gap state.
5. Show evidence summary and missing data.
6. Show bid-readiness checklist.
7. Validate the package.
8. Generate reviewer handoff.
9. Generate pending sign-off.
10. Export or list the package artifacts.
11. Confirm excluded operational actions remain unauthorized.

Current local fixture builder:

```bash
python3 scripts/build_procurement_decision_package_sample.py --out-dir /tmp/decisiondoc-procurement-demo
```

This command builds the fixture package artifacts through `app/services/procurement_decision_package_service.py`. The same service also contains the adapter from `ProcurementDecisionRecord` into the review package shape. It does not call a provider, run AWS, upload data, train a model, promote a model, resume a service, submit a bid, or grant operational approval.
Before writing review artifacts, the package writer checks the package document for stable field order, package id consistency, handoff alignment, export boundaries, and pending review-only sign-off state.
The generated `decision_package.json` keeps fixed top-level and package field order, plus non-empty scenario and update metadata, so the central review artifact remains stable for readers and automation. Its `opportunity_ref` keeps fixed `opportunity_id`, `title`, and `source_type` identity fields so reviewers can trace the package back to the source opportunity without stale reference drift.
The generated package also keeps reviewed item shapes for hard filters, soft-fit factors, evidence rows, and bid-readiness checklist rows. The sample validator and artifact checker reject field-order drift, invalid score ranges, unreviewed package statuses, unknown evidence types, and empty reviewer-facing text.
The generated `validation_summary.json` includes an operator-readable validation summary: `operator_summary` explains that the package is review evidence and not approval to act, while `next_review_action` keeps the next step scoped to package review. The local checker validates validation_summary field order so the reviewer-facing summary remains stable across generated artifacts and receipts.
The generated `reviewer_handoff.json` records reviewer handoff metadata. The artifact checker verifies field order, reviewer, requested decision, review prompt, and non-authorization boundary.
The generated `proposal_handoff.json` adds package-to-proposal handoff metadata for drafting preparation only. It carries the same excluded operational actions as the package export manifest, keeps allowed next steps fixed, keeps `blocked_until` aligned with required inputs, and does not authorize bid submission, legal approval, or contractual commitment.
The generated `pending_signoff.json` remains a pending review record only. The artifact checker verifies field order, pending status, reviewer, review-only scope, and false operational approval.
The generated `signoff_summary.md` gives a reviewer-readable sign-off summary for the pending review state and repeats that operational approval is false.
The generated `audit_manifest.json` is the audit packet index. It keeps the included artifact list, decision/evidence/validation/handoff/sign-off groupings, and excluded external actions in one local-only manifest before export review. The artifact checker treats those groupings as fixed lists, so local evidence catches packet structure drift before handoff.
The generated `export_manifest.json` keeps a fixed field order and repeats the included artifacts and excluded actions that the artifact checker validates before handoff.
Successful local evidence CLI runs return JSON with `status: "passed"` and exit `0`. Handled failures return JSON with `status: "failed"`, `error_type`, and `error`, then exit non-zero.
The local evidence CLI set is described in `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`, validated by `scripts/validate_procurement_decision_package_cli_contract_manifest.py`, and covered by shared success/failure contract regression matrices so automation stays machine-readable across the fixture builder, validator, exporter, demo runner, artifact checker, gate, smoke wrapper, smoke checker, contract manifest validator, and manifest validation-result checker. The manifest validator rejects unreviewed top-level fields, nested `stdout_json_contract` drift, extra fields in `cli_contracts[]`, manifest field order drift, stdout_json_contract field order drift, cli_contracts[] field order drift, and stdout field order drift for success and handled-failure payloads. Its persisted receipt keeps a fixed validation result field order, a stable success and failure case-map order, and a fixed check result field order after receipt recheck. It emits `contract_version`, `sha256`, `size_bytes`, `success_required_fields_by_case`, `failure_required_fields_by_case`, and `cli_contract_fingerprint` for the checked contract file and exact stdout field contract, can persist the validation JSON with `--write-result --result-path <path>`, and the persisted validation result can be checked with `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`.

Operator runbook: [DecisionDoc AI Local Demo Runbook](./product_local_demo_runbook.md).

Project-record export wrapper:

```bash
python3 scripts/export_procurement_decision_package.py --tenant-id <tenant_id> --project-id <project_id> --out-dir /tmp/decisiondoc-procurement-project-package
```

Failures return JSON with `status: "failed"`, `error_type`, and `error`, then exit non-zero.

Seeded project-record demo:

```bash
python3 scripts/run_procurement_decision_package_demo.py \
  --out-dir /tmp/decisiondoc-procurement-package-demo-output \
  --clean-output
```

The seeded demo runner performs artifact validation before returning.
It also writes `demo_run_result.json` in the output directory with package artifact SHA256 and byte-size inventory, writes `demo_evidence_receipt.md` for reviewer-readable evidence, verifies both evidence files, and returns final `artifact_check.demo_result_checked`, `artifact_check.artifact_inventory_checked`, and `artifact_check.demo_receipt_checked` values of `true` so the local evidence can be inspected after stdout is gone.
Failures are returned as JSON with a non-zero exit code, including `error_type` and `error`, so automation does not need to parse Python tracebacks.
The `--clean-output` flag clears only the output directory before export, which keeps repeated local runs from retaining stale artifacts.

One-command local smoke path:

```bash
python3 scripts/smoke_procurement_decision_package_demo_gate.py \
  --out-dir /tmp/decisiondoc-procurement-package-demo-output
```

The smoke wrapper runs the seeded demo, runs the local evidence gate, writes `demo_gate_result.json`, writes `demo_smoke_result.json`, and writes `demo_smoke_check_result.json`.
Like the gate command, smoke wrapper failures are returned as JSON with a non-zero exit code so the one-command path remains automation-readable.
Use `--no-write-smoke-result` to skip the final smoke summary file or `--smoke-result-path <path>` to store it elsewhere. When a custom smoke summary path is used, run the persisted smoke result checker against that custom path; the final smoke check receipt keeps the same path in its evidence references.
Use `--no-write-smoke-check-result` to skip the final smoke checker receipt or `--smoke-check-result-path <path>` to store it elsewhere.
Custom gate result, smoke result, and smoke check result paths are rejected when their corresponding write option is disabled, so automation does not silently ignore requested handoff paths.
Persisted smoke summaries require a persisted gate result; combine `--no-write-gate-result` with `--no-write-smoke-result` for an in-memory-only gate run.
The smoke summary reports `gate_result_written`, `smoke_result_written`, and `package_artifacts_checked` so the evidence persistence and package recheck state is explicit.
It also records the local demo tenant, project, and seeded decision identifiers for reviewer traceability.
Its `evidence_files` block groups the local evidence paths, including the final smoke check receipt, that a reviewer should inspect.
When the smoke summary is written, the wrapper runs the persisted smoke result checker, records `smoke_result_checked: true` only after that check passes, and persists the final checker receipt when smoke check result writing is enabled.

Persisted smoke result checker:

```bash
python3 scripts/check_procurement_decision_package_smoke_result.py \
  /tmp/decisiondoc-procurement-package-demo-output/demo_smoke_result.json
```

The checker verifies the saved smoke summary, requires final `smoke_result_checked: true`, checks the evidence file paths it records, top-level path consistency with the `evidence_files` block, gate evidence path references, smoke check receipt references, demo identity, demo run metadata, the current package artifact inventory, the recorded smoke check receipt, required excluded external actions, and consistency with the persisted demo and gate results.
Use `--write-result` to persist or refresh that checker output as `demo_smoke_check_result.json` for local handoff review. Use `--result-path <path>` only with `--write-result` and only when a separate automation copy is needed; the smoke summary's recorded `smoke_check_result_path` remains the canonical local receipt.

Generated artifact checker:

```bash
python3 scripts/check_procurement_decision_package_artifacts.py /tmp/decisiondoc-procurement-package-demo-output
```

When `demo_run_result.json` exists, the checker validates that evidence file, its recorded artifact inventory, and the reviewer-readable receipt markers as well as the generated package artifacts.
Failures are returned as JSON with a non-zero exit code, including `error_type` and `error`, so automation can handle artifact drift without traceback parsing.

Local evidence gate:

```bash
python3 scripts/gate_procurement_decision_package_demo.py /tmp/decisiondoc-procurement-package-demo-output
```

The gate reuses the checker and returns a compact reviewer-facing JSON summary for the existing output directory.
Failures are also returned as JSON with a non-zero exit code so automation can parse the reason without relying on Python tracebacks.
Use `--write-result` to persist the latest gate summary as `demo_gate_result.json`; use `--result-path <path>` only with `--write-result` when a separate location is needed. This file records the gate outcome and is not included in the package artifact checksum inventory.

## 9. Implementation Backlog

| Priority | Work item | Expected output | Verification |
|---|---|---|---|
| 1 | Define package shape | schema or typed internal object | required fields test |
| 2 | Add local fixture input | opportunity and capability profile fixture | fixture loads deterministically |
| 3 | Add package builder | JSON and Markdown package output | unit or infrastructure test |
| 4 | Add evidence summary | evidence and missing-data summary | test checks source and uncertainty fields |
| 5 | Add validation summary | deterministic validator output | validator rejects missing boundaries |
| 6 | Add handoff and pending sign-off | review workflow artifacts | test proves non-approval boundary |
| 7 | Add export manifest | included artifact list | test proves excluded actions are listed |

## 10. Done Criteria

This scenario is ready when:

- one local command or pytest path creates the package deterministically,
- package output can be inspected without external credentials,
- validation fails if authorization boundaries are missing,
- reviewer handoff and pending sign-off remain separate from operational approval,
- docs describe only local verified behavior after implementation.

Until these checks exist, this document should be treated as the target scenario, not evidence that the product loop is already implemented end to end.

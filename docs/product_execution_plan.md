# DecisionDoc AI Product Execution Plan

Updated: 2026-07-13

This document translates [DecisionDoc AI Product Direction](./product_direction.md) into an execution plan. It is an internal planning document and does not claim production readiness, customer adoption, measured business impact, or autonomous approval capability.

## 1. Execution Goal

The next product goal is to turn DecisionDoc AI from a broad document generation platform into a focused, reviewable decision package workflow.

The first execution target is:

> A local, mock-provider-compatible workflow that produces a procurement-oriented decision package with evidence, validation, reviewer handoff, pending sign-off, and exportable artifacts.

This should become the product's demonstrable core loop.

## 2. Product Loop To Prove

The product loop should be simple enough to explain in one demo:

1. Define or import a decision topic or procurement opportunity.
2. Attach or reference supporting source material.
3. Generate a structured decision package.
4. Show evidence, hard gaps, readiness state, and uncertainty.
5. Generate a reviewer handoff.
6. Create a pending sign-off record.
7. Validate a completed review record.
8. Export the final package.

The loop is complete only when a non-engineering reviewer can inspect the package and understand what is recommended, what evidence was used, and what remains explicitly unauthorized.

## 3. 30-Day Plan

### Objective

Make the product direction tangible through a narrow local demo path.

### Build

- Define a `Decision Package` schema or internal shape.
- Map existing generated documents into package sections.
- Add a procurement-oriented package example using current public procurement copilot specs.
- Produce a local evidence summary for the package.
- Produce a reviewer handoff and pending sign-off from that package.
- Add a project-record adapter that maps recommended procurement decision state into the package shape.
- Add a local project-record export CLI for existing procurement decision records.
- Add a seeded local demo runner that creates a demo procurement decision record and exports the package artifacts.
- Add an artifact checker that validates generated package directories and authorization boundaries.
- Persist local demo run evidence as `demo_run_result.json`.
- Add an operator-readable validation summary with `operator_summary` and `next_review_action` so a reviewer can see the review state without inferring it from raw JSON flags.
- Add package-to-proposal handoff metadata for drafting preparation while preserving the same non-authorization boundary.
- Add `procurement_review.html` as a script-free, read-only browser workspace that presents recommendation, hard filters, score factors, evidence gaps, bid readiness, handoff state, and authorization boundaries in one artifact.
- Version the local evidence CLI stdout contract in `cli_contract_manifest.json` so automation can rely on stable `status`, `error_type`, and `error` fields instead of traceback parsing.
- Validate the CLI contract manifest and persisted manifest validation receipt through `validate_procurement_decision_package_cli_contract_manifest.py` and `check_procurement_decision_package_cli_contract_manifest_result.py`.
- Keep all flows runnable with `mock` provider and local storage.

### Documentation

- Add a product demo scenario document: [DecisionDoc AI Local Product Demo Scenario](./product_demo_scenario.md).
- Add one sample input and expected output package: [procurement decision package local demo sample](./samples/procurement_decision_package_local_demo/).
- Add a local demo runbook: [DecisionDoc AI Local Demo Runbook](./product_local_demo_runbook.md).
- Link product direction, execution plan, roadmap, and procurement PRD.

### Verification

- Unit or infrastructure tests for package shape.
- Local command or pytest path that proves package creation.
- Shared success and handled-failure contract tests for the local evidence CLI set.
- Manifest validation that records `contract_version`, manifest SHA256, and byte size with `--write-result --result-path`.
- No provider API call required.
- No AWS runtime required.
- No training or model promotion path touched.

### Acceptance Criteria

- A reviewer can open one folder or output bundle and see:
  - generated decision documents,
  - structured recommendation,
  - evidence references,
  - validation result,
  - handoff,
  - pending sign-off.
- The workflow passes a deterministic local test.
- The local evidence CLI contract manifest is versioned, validated, and referenced by the runbook and sample README.
- README or public docs are not updated with unverified claims.

## 4. 60-Day Plan

### Objective

Turn the local demo path into a practical product workflow.

### Build

- Add procurement go/no-go decision output:
  - `GO`,
  - `CONDITIONAL_GO`,
  - `NO_GO`.
- Add deterministic hard filters.
- Add soft-fit score breakdown.
- Add bid-readiness checklist.
- Expand package-to-proposal handoff metadata beyond the local fixture path.
- Expand the operator-readable validation summary as the package moves beyond the local fixture path.

### UI Or CLI Surface

Choose the smallest surface that makes the workflow inspectable:

- CLI summary first if UI work would slow the core model.
- UI review console next if the package structure is stable.

The surface must answer:

- Is the package valid?
- What evidence supports the recommendation?
- What is missing?
- Who needs to review?
- Does this authorize any operational action?

Current local evidence slice:

- Project detail now exposes `POST /projects/{project_id}/procurement/review-packet` and a reviewer-owned ZIP download control. The route reads the current tenant's injected procurement store, builds the existing 12-artifact package in a temporary directory, verifies the packet before responding, and returns SHA256 plus `operational_approval: false` metadata without provider or external runtime execution.
- The project page now includes a tenant-scoped procurement review inbox backed by `GET /procurement/reviews`. It filters pending, completed, and all review records, carries lightweight project context, opens the existing project review workspace, and reuses the verified reviewed-package download route instead of creating another completion path.
- Downstream `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` generation now reuses a completed review only while its packet source matches the current procurement record. Applied evidence carries packet SHA256, decision, and reviewed time into generation metadata and the saved project document; stale evidence is skipped, and every path keeps `operational_approval: false`.
- Saved review-bound documents also retain the packet source timestamp. Project detail compares that timestamp and tenant-scoped review record with the current procurement decision, exposes current/stale/missing/invalid evidence, and carries non-current warnings through approval requests, share creation audit, and the public shared page without blocking local inspection or granting operational authority.
- `procurement_review.html` gives non-engineering reviewers one read-only procurement package surface and remains part of the same 12-artifact audit, export, fingerprint, and tamper-check contract. It does not create a second approval workflow.
- `manage_procurement_decision_review_packet.py` wraps those 12 validated artifacts in a deterministic ZIP with an embedded SHA256 manifest. The packet remains `review_ready`, keeps `operational_approval: false`, and can be independently reverified after handoff.
- `manage_procurement_review_receipt.py` creates `procurement_review_receipt.json` outside the packet, binds it to `packet_sha256`, and moves `review_status` once from `pending` to `completed` for the requested reviewer. Completion records review evidence only and keeps operational approval false.
- `manage_procurement_review_receipt.py render/apply-draft` adds a packet/receipt-bound browser input path without changing the script-free packet artifact. The downloaded draft is rejected when source bytes, reviewer identity, field order, UTC time, or the false operational-approval boundary drift.
- `manage_procurement_reviewed_package.py create/verify` closes the local export loop after review completion by wrapping the unchanged packet and completed receipt in a deterministic three-entry audit envelope. `review_completed` records the outcome for accepted, changes-requested, or rejected reviews and never grants operational approval.
- `review.html` shows generated documents and automatic validation evidence.
- `human_review.html` combines request evidence, automatic validation, generated Markdown, manifest-bound receipt state, reviewer notes, and the external-action boundary in one workspace. Reviewer input is downloaded as a source-bound draft rather than written directly to evidence.
- `manage_finished_doc_human_review.py` validates and atomically applies a draft only when its manifest and receipt hashes still match, without provider or AWS execution.
- A completed receipt can produce a deterministic review packet containing only manifest-declared artifacts and an embedded SHA256 index; pending review cannot be packaged as final.

### Verification

- Mock-provider end-to-end package test.
- Golden sample for at least one procurement decision package.
- Versioned CLI contract manifest test proving local evidence commands keep machine-readable stdout JSON.
- Boundary test proving accepted review does not authorize service resume, provider calls, dataset upload, training execution, or model promotion.

### Acceptance Criteria

- One procurement opportunity can move from source data to reviewable decision package.
- A project reviewer can download that package from the existing procurement UI without switching to a separate CLI workflow.
- Hard filters and unknown data are visible.
- Reviewer sign-off remains separate from operational approval.
- A local reviewer decision can be recorded once and revalidated against the exact packet bytes.
- A completed review can be exported and independently reverified without modifying its source packet or receipt.
- A completed review can inform downstream drafting without granting operational approval, and a procurement update prevents stale review evidence from being reused.
- A previously generated review-bound document visibly becomes stale after its procurement decision changes, and approval or sharing requires an explicit acknowledgement while preserving the warning as evidence.
- The demo does not depend on live provider or AWS availability.

## 5. 90-Day Plan

### Objective

Prepare the product workflow for external evaluation without overstating operational maturity.

### Build

- Exportable audit packet:
  - deterministic ZIP for the 12-artifact procurement review package,
  - embedded `packet_manifest.json` with SHA256 and byte-size fingerprints,
  - exact membership and path-boundary verification,
  - semantic revalidation after archive extraction,
  - explicit `review_ready` and false operational-approval state.
- Optional live provider lane.
- Optional deployment lane with clear stage/prod separation.
- Admin or review console only after package and validation contracts are stable.

### Documentation

- Update case study with verified local demo evidence.
- Update README only with measured or directly verified claims.
- Add `Scope & Limitations` to any public-facing material.
- Separate product capability from deployment status.

### Verification

- Full relevant local pytest gate.
- Mock end-to-end smoke.
- Optional live-provider validation note if credentials and approval exist.
- Optional deployed smoke only if environment access is available and approved.

### Acceptance Criteria

- A third party can run or inspect the local demo.
- The product story is consistent across README, roadmap, case study, and resume materials.
- No public material claims customer adoption, production deployment, or measured business impact without evidence.

## 6. Immediate Backlog

| Priority | Work item | Output | Completion check |
|---|---|---|---|
| 1 | Define `Decision Package` shape | schema or typed internal structure | local test validates required fields |
| 2 | Create procurement package sample | sample input and output folder | deterministic mock run produces package |
| 3 | Add evidence summary | Markdown or JSON summary | source references and uncertainty visible |
| 4 | Add package handoff | handoff JSON/MD | validator confirms no authorization boundary break |
| 5 | Add pending sign-off path | template and generator | pending record validates and remains non-approval |
| 6 | Add export packet | deterministic ZIP plus embedded manifest | create/verify path proves package, evidence, validation, sign-off, tamper detection, and non-approval boundary |
| 7 | Add demo runbook | concise operator instructions | new user can follow local path |
| 8 | Add versioned CLI evidence contract | `cli_contract_manifest.json` plus validator/checker receipt | success/failure matrix and docs contract tests pass |
| 9 | Add packet-bound review receipt | companion `procurement_review_receipt.json` | pending/init, completed record, stale packet, reviewer, re-record, and non-approval checks pass |

## 7. Engineering Guardrails

- Preserve route, service, schema, provider, and storage boundaries.
- Keep `mock` provider deterministic.
- Prefer additive workflow objects over broad rewrites.
- Do not put AWS, provider, dataset upload, training, or service resume inside the default demo path.
- Keep approval records separate from operational execution approval.
- Add tests around boundaries, not only happy-path document generation.

## 8. Product Guardrails

- Do not build a generic document marketplace.
- Do not optimize for many document types before one high-stakes workflow is clear.
- Do not hide uncertainty behind polished prose.
- Do not merge reviewer acceptance with service resume or training approval.
- Do not update public claims without verification evidence.

## 9. Demo Script Target

The target demo should take less than ten minutes and follow this script:

1. Open a sample procurement opportunity.
2. Show source evidence and missing fields.
3. Generate the decision package.
4. Show the recommendation and bid-readiness checklist.
5. Show validation status.
6. Generate reviewer handoff.
7. Generate pending sign-off.
8. Explain that provider calls, training, deployment, and service resume remain unauthorized.
9. Export the package.

## 10. Definition Of Done

The product execution plan is working when the repository contains:

- a stable package shape,
- one deterministic local sample,
- one reviewer handoff path,
- one sign-off path,
- one export or handoff artifact,
- tests that validate the package and authorization boundary,
- a versioned local evidence CLI contract and manifest validation receipt path,
- docs that describe only verified behavior as implemented.

Until then, DecisionDoc AI should be described as an actively developed MVP with strong local governance and review workflow foundations.

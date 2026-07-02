# Procurement Decision Package Local Demo Sample

Updated: 2026-06-23

This folder contains fixture-style sample artifacts for the local product demo scenario in [DecisionDoc AI Local Product Demo Scenario](../../product_demo_scenario.md).

These files are target examples and local validation receipts for implementation and review. They do not claim live provider execution, deployed availability, customer adoption, or operational approval.

## Files

| File | Purpose |
|---|---|
| `sample_input.json` | Deterministic local input containing opportunity, capability profile, and operator notes |
| `expected_decision_package.json` | Expected reviewable package shape for a `CONDITIONAL_GO` scenario |
| `cli_contract_manifest.json` | Versioned machine-readable stdout JSON contract for the local evidence CLIs, including success/failure fields and excluded external actions |
| `cli_contract_manifest_validation_result.json` | Persisted local validation receipt for `cli_contract_manifest.json` |
| `cli_contract_manifest_validation_check_result.json` | Persisted local check receipt proving the validation result still matches the current manifest |

## Intended Use

Use these samples to guide the first local package builder and validator:

1. Load `sample_input.json`.
2. Build a decision package.
3. Compare required fields against `expected_decision_package.json`.
4. Validate that recommendation, evidence, gaps, handoff, sign-off, and authorization boundaries are explicit.

## Validation

Build the local package artifacts:

```bash
python3 scripts/build_procurement_decision_package_sample.py --out-dir /tmp/decisiondoc-procurement-demo
```

The CLI uses `app/services/procurement_decision_package_service.py` for package construction, then validates the generated package against the local fixture contract.
The artifact writer also runs a local package self-check before writing files, so malformed handoff metadata is rejected before partial review artifacts are created.
The generated `decision_package.json` keeps fixed top-level and package field order, plus non-empty scenario and update metadata, so the central review artifact remains stable for readers and automation. Its `opportunity_ref` also keeps fixed `opportunity_id`, `title`, and `source_type` order and must match the source opportunity identity fields from `sample_input.json`.
The package internals also keep fixed item shapes for `hard_filters`, `soft_fit_score.factors`, `evidence_summary`, and `bid_readiness_checklist`; validators check score ranges, reviewed status values, evidence types, and non-empty reviewer-facing text.
The generated `validation_summary.json` contains an operator-readable validation summary. `operator_summary` makes the non-approval boundary visible in one sentence, and `next_review_action` keeps the next reviewer step limited to the package scope. The local checker validates validation_summary field order so the sample, generated artifact, and evidence receipt stay aligned.
The generated `reviewer_handoff.json` records reviewer handoff metadata. The sample validator and artifact checker verify field order, reviewer, requested decision, review prompt, and non-authorization boundary.
The generated `proposal_handoff.json` contains package-to-proposal handoff metadata for drafting preparation only. It keeps excluded operational actions attached to the handoff, keeps allowed next steps fixed, and keeps `blocked_until` aligned with required inputs so proposal drafting cannot be mistaken for bid submission, legal approval, or contractual commitment.
The generated `pending_signoff.json` remains a pending review record only. The sample validator and artifact checker verify field order, pending status, reviewer, review-only scope, and false operational approval.
The generated `signoff_summary.md` gives a reviewer-readable sign-off summary for the pending review state and repeats that operational approval is false.
The generated `audit_manifest.json` is the audit packet index. It groups the local review artifacts and repeats the excluded external actions so the packet can be checked without treating it as operational approval. The sample validator and artifact checker both verify those grouped artifact sections as fixed lists.
The generated `export_manifest.json` keeps a fixed field order and repeats the included artifacts and excluded actions that the sample validator and artifact checker verify before handoff.

Run the local sample validator:

```bash
python3 scripts/validate_procurement_decision_package_sample.py
```

Validate the local evidence CLI contract manifest and write a receipt. The validator checks the exact manifest field set and manifest field order, the nested stdout_json_contract field order, each cli_contracts[] field order, and the stdout field order declared for every success and handled-failure case. The persisted validation result keeps a fixed validation result field order, preserves the success and failure case-map order, and can be checked through a fixed check result field order. The validation result includes `contract_version`, `manifest_sha256`, `manifest_size_bytes`, `success_required_fields_by_case`, `failure_required_fields_by_case`, and `cli_contract_fingerprint` so automation can record which exact stdout field contract was checked:

```bash
python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py --write-result
python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py --write-result
```

Use `--result-path` when the validation or check receipt should be written
outside this sample directory.

Run the focused regression tests:

```bash
pytest -q tests/test_procurement_decision_package_sample.py tests/test_procurement_decision_package_builder.py tests/test_procurement_decision_package_cli_contract_manifest.py tests/test_check_procurement_decision_package_cli_contract_manifest_result.py tests/test_procurement_decision_package_docs_contract.py tests/test_procurement_decision_package_cli_failure_contract.py tests/test_procurement_decision_package_cli_success_contract.py
```

## Boundary

This sample does not authorize:

- provider API execution,
- AWS runtime execution,
- dataset upload,
- training execution,
- model promotion,
- production service resume,
- bid submission,
- legal approval,
- contractual commitment.

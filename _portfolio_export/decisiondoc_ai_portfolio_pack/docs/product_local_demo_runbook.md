# DecisionDoc AI Local Demo Runbook

Updated: 2026-06-23

This runbook shows how to run the first local DecisionDoc AI product loop from deterministic fixture input to reviewable procurement decision package artifacts.

It covers only the local fixture path. It does not claim customer adoption, deployed availability, live provider execution, measured business impact, or operational approval.

## 1. Demo Scope

The local demo proves that the repository can:

1. load a procurement opportunity and capability profile fixture,
2. build a `CONDITIONAL_GO` decision package,
3. emit reviewer-readable Markdown artifacts,
4. emit JSON artifacts for validation, handoff, pending sign-off, and export manifest,
5. validate that operational boundaries remain explicit.

Source scenario:

- [DecisionDoc AI Local Product Demo Scenario](./product_demo_scenario.md)

Sample input and expected package:

- [procurement decision package local demo sample](./samples/procurement_decision_package_local_demo/)

## 2. Prerequisites

Run from the repository root:

```bash
cd /path/to/DecisionDoc-AI
```

No external credentials are required for this runbook.

This local path does not require:

- provider API key,
- AWS credentials,
- dataset upload access,
- training runtime,
- model registry access,
- deployed service access.

All local evidence CLIs in this workflow return stdout JSON. Successful runs include `status: "passed"` and exit `0`; handled failures include `status: "failed"`, `error_type`, and `error`, then exit non-zero. The machine-readable contract manifest is `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`; the regression suite includes shared CLI success/failure contract matrices that read it so automation can rely on stdout JSON instead of Python traceback parsing.

Validate the contract manifest itself:

```bash
CONTRACT_RESULT=/tmp/decisiondoc-cli-contract-manifest-validation-result.json
python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py \
  --write-result \
  --result-path "$CONTRACT_RESULT"
```

The validator rejects unreviewed manifest fields, including nested `stdout_json_contract` fields and extra fields in any `cli_contracts[]` entry. It also checks manifest field order, stdout_json_contract field order, cli_contracts[] field order, and the declared stdout field order for every success and handled-failure case. The persisted receipt keeps a fixed validation result field order, a stable success and failure case-map order, and a fixed check result field order when the receipt is rechecked. The validator emits the manifest `contract_version`, `sha256`, `size_bytes`, `success_required_fields_by_case`, `failure_required_fields_by_case`, and `cli_contract_fingerprint` so local automation can record exactly which contract file and stdout field contract were checked.
Use `--write-result` to persist `cli_contract_manifest_validation_result.json` next to the manifest, or pair it with `--result-path <path>` for a custom receipt location. `--result-path` is rejected without `--write-result`.
Check a persisted manifest validation result with:

```bash
python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py "$CONTRACT_RESULT"
```

## Report Quality Learning Local Demo

Report Workflow 생성부터 최종 승인, 사람 검수 correction artifact preview와 저장, ready 목록 조회, JSONL export 재검증까지 한 번에 실행한다.

```bash
python3 scripts/run_report_quality_learning_demo.py \
  --output /tmp/decisiondoc-report-quality-learning-demo.json

python3 -m json.tool /tmp/decisiondoc-report-quality-learning-demo.json
```

이 명령은 실행 중 provider를 `mock`, storage를 임시 local directory로 강제한다. 현재 shell이나 `.env.prod`에 OpenAI, Gemini, Claude 키가 있어도 provider API를 호출하지 않으며, 임시 workflow 데이터는 실행 종료와 함께 삭제한다.

receipt의 `status`는 모든 단계와 exported JSONL validator가 통과한 경우에만 `passed`가 된다. `external_actions`의 provider API, AWS runtime, dataset upload, provider job, training execution, model promotion, production service resume 값은 모두 `false`로 유지된다. 이 결과는 사람이 승인한 learning candidate의 로컬 생성·검증 증거이며 fine-tuning 실행이나 운영 재개 승인이 아니다.

### Full Pilot Handoff Demo

3개 ready artifact를 API에서 만들고 최종 browser handoff까지 전체 local chain을 확인할 때는 다음 명령을 실행한다.

```bash
python3 scripts/run_report_quality_pilot_handoff_demo.py \
  --output /tmp/decisiondoc-report-quality-pilot-handoff-demo.json

python3 scripts/check_report_quality_pilot_handoff_demo_receipt.py \
  /tmp/decisiondoc-report-quality-pilot-handoff-demo.json \
  --json

python3 -m json.tool /tmp/decisiondoc-report-quality-pilot-handoff-demo.json
```

이 명령은 provider를 `mock`으로 고정하고 OpenAI, Gemini, Anthropic API key를 demo context에서 제거한 뒤 종료 시 원래 환경을 복원한다. API pilot preview/package, verified source import, simulated local review, ready sync, deterministic handoff, exact browser summary verification은 모두 temporary local directory에서 수행하며 실행 후 삭제한다. 최종 receipt만 write-once로 남고 기존 파일이나 symlink는 덮어쓰지 않는다.

Checker는 receipt exact field contract, UTC timestamp, artifact count/order, SHA-256 형식, completed stage 순서, simulated review, no-training/external-action boundary, 대표 secret pattern을 읽기 전용으로 재검증한다. Receipt의 `review_evidence=simulated_demo_input`, `human_review_claimed=false`, `local_review.simulated=true`는 이 실행이 제품 wiring의 로컬 증거일 뿐 실제 사람 검수 완료 증거가 아님을 뜻한다. Checker는 삭제된 temporary artifact를 다시 검증하지 않으며 provider API, AWS runtime, dataset upload, provider job, training, model promotion, production service resume을 실행하지 않는다.

## 3. Build The Local Package

Use a temporary output directory:

```bash
rm -rf /tmp/decisiondoc-procurement-demo
python3 scripts/build_procurement_decision_package_sample.py --out-dir /tmp/decisiondoc-procurement-demo
```

Failures return JSON with `status: "failed"`, `error_type`, and `error`, then exit non-zero.

Expected command result includes:

```json
{
  "authorization_boundary": "explicit",
  "recommendation": "CONDITIONAL_GO"
}
```

The actual output also lists the generated artifact names and output directory.
The package also writes `validation_summary.json` with an operator-readable validation summary. The `operator_summary` field states whether the package is review evidence rather than approval to act, and `next_review_action` keeps the next step scoped to package review. The artifact checker validates validation_summary field order so local handoff tools read the same reviewer-facing fields in the same sequence.

To seed a project-scoped procurement decision record and export package artifacts in one local command:

```bash
rm -rf /tmp/decisiondoc-procurement-package-demo-data /tmp/decisiondoc-procurement-package-demo-output
python3 scripts/run_procurement_decision_package_demo.py \
  --data-dir /tmp/decisiondoc-procurement-package-demo-data \
  --out-dir /tmp/decisiondoc-procurement-package-demo-output \
  --clean-output
```

This command remains local-only. It seeds a demo `ProcurementDecisionRecord`, exports package artifacts, and keeps the same non-authorization boundary.
It also runs the artifact checker before returning, so the command fails if the generated package is missing required files or breaks the non-authorization boundary.
Failures are returned as JSON with `status: "failed"`, `error_type`, and `error`, then exit non-zero, so local automation does not need to parse Python tracebacks.
The runner writes `demo_run_result.json` into the output directory as local evidence of the seed, export, artifact inventory, and artifact-check result, then writes and verifies `demo_evidence_receipt.md` for reviewer-readable local evidence.
The `--clean-output` flag removes only the output directory before export so stale local artifacts do not mix with the fresh evidence run. It does not remove the procurement decision data directory.

For a one-command local smoke path that generates the demo, runs the evidence gate, writes `demo_gate_result.json`, writes `demo_smoke_result.json`, and writes `demo_smoke_check_result.json`:

```bash
python3 scripts/smoke_procurement_decision_package_demo_gate.py \
  --data-dir /tmp/decisiondoc-procurement-package-demo-data \
  --out-dir /tmp/decisiondoc-procurement-package-demo-output
```

This wrapper remains local-only and reuses the same runner and gate commands described below.
If the wrapper fails, it returns JSON with `status: "failed"`, `error_type`, and `error`, then exits non-zero. When gate result writing is enabled, the failure payload is also written to the configured gate result path.
The wrapper writes `demo_smoke_result.json` by default so the final one-command summary survives after stdout is gone. Use `--no-write-smoke-result` to skip that file, or `--smoke-result-path <path>` to store it elsewhere. When a custom smoke result path is used, run the persisted smoke checker against that custom summary path; the smoke check receipt records the same path in `smoke_result_path` and `evidence_files.smoke_result`.
It also writes `demo_smoke_check_result.json` by default after the smoke summary is finalized. Use `--no-write-smoke-check-result` to skip that receipt, or `--smoke-check-result-path <path>` to store it elsewhere.
Custom gate, smoke result, and smoke check result paths require their corresponding result writing to be enabled; the wrapper rejects path options that would otherwise be ignored.
Persisted smoke summaries require a persisted gate result because the smoke checker reopens and compares `demo_gate_result.json`. If `--no-write-gate-result` is used for an in-memory-only gate run, also use `--no-write-smoke-result`.
The smoke summary includes `gate_result_written`, `smoke_result_written`, and `package_artifacts_checked` flags so reviewers can tell whether the JSON evidence was only printed, persisted, and rechecked against the current package artifacts.
It also records the local demo tenant, project, and seeded decision identifiers so reviewers can tie the smoke result back to the demo run record.
It also includes an `evidence_files` block that groups the demo result, demo receipt, gate result, smoke result, and smoke check result paths for handoff review.
When `demo_smoke_result.json` is written, the wrapper immediately runs the persisted smoke result checker, records `smoke_result_checked: true` only after that check passes, and then persists the final checker receipt when smoke check result writing is enabled.

Check a persisted smoke summary after stdout is gone:

```bash
python3 scripts/check_procurement_decision_package_smoke_result.py \
  /tmp/decisiondoc-procurement-package-demo-output/demo_smoke_result.json
```

This verifies that the persisted smoke summary passed, recorded `smoke_result_checked: true`, preserved the non-approval boundary, recorded both result files as written, points to existing local evidence files, keeps top-level evidence paths aligned with the `evidence_files` block, rechecks the current package artifact inventory, validates the recorded smoke check receipt when present, lists the required excluded external actions, and matches the persisted demo and gate results on recommendation, boundary, artifact count, demo identity, run metadata, self-check flags, gate evidence path references, and smoke check receipt references. The checker result also repeats the output directory, clean-output flag, smoke check receipt path and written flag, demo tenant, project, and seeded decision identifiers.

Persist the checker result when stdout is not enough:

```bash
python3 scripts/check_procurement_decision_package_smoke_result.py \
  /tmp/decisiondoc-procurement-package-demo-output/demo_smoke_result.json \
  --write-result
```

This writes or refreshes `/tmp/decisiondoc-procurement-package-demo-output/demo_smoke_check_result.json`. Use `--result-path <path>` with `--write-result` to store a copy of the checker output somewhere else for automation handoff; `--result-path` is rejected without `--write-result`. The smoke summary still treats its recorded `smoke_check_result_path` as the canonical receipt path, so custom copies should not be used as a different approval source. The persisted check result records only the local verification outcome and does not authorize operational action.

## 4. Inspect The Artifacts

List generated files:

```bash
find /tmp/decisiondoc-procurement-demo -maxdepth 1 -type f -print | sort
```

Expected artifacts:

- `bid_readiness_checklist.md`
- `decision_package.json`
- `decision_summary.md`
- `demo_evidence_receipt.md` when produced by the seeded demo runner
- `demo_gate_result.json` when produced by the smoke wrapper or gate command
- `demo_run_result.json` when produced by the seeded demo runner
- `demo_smoke_check_result.json` when produced by the smoke wrapper or persisted smoke checker
- `demo_smoke_result.json` when produced by the smoke wrapper
- `evidence_summary.md`
- `audit_manifest.json`
- `export_manifest.json`
- `pending_signoff.json`
- `procurement_review.html`
- `proposal_handoff.json`
- `reviewer_handoff.json`
- `signoff_summary.md`
- `validation_summary.json`

Recommended inspection order:

1. `procurement_review.html`
2. `decision_summary.md`
3. `evidence_summary.md`
4. `bid_readiness_checklist.md`
5. `reviewer_handoff.json`
6. `proposal_handoff.json`
7. `pending_signoff.json`
8. `signoff_summary.md`
9. `audit_manifest.json`
10. `export_manifest.json`
11. `demo_run_result.json` when present
12. `demo_evidence_receipt.md` when present

`demo_run_result.json` includes SHA256 and byte-size inventory entries for the generated package artifacts. This inventory covers the package files listed above, not `demo_run_result.json` itself, because the evidence file would otherwise need to checksum its own changing content.
`demo_evidence_receipt.md` summarizes the final local evidence state for human review and repeats the non-authorization boundary.
The package artifact writer runs a local package self-check before creating files, so stale package ids, malformed handoff metadata, and unreviewed export entries are rejected before partial artifacts are written.
`decision_package.json` keeps fixed top-level and package field order, plus non-empty scenario and update metadata, so the central review artifact remains stable for readers and automation. Its `opportunity_ref` preserves the fixed `opportunity_id`, `title`, and `source_type` identity fields checked by the fixture validator and artifact checker.
The local checker also validates the item-level shapes inside `hard_filters`, `soft_fit_score.factors`, `evidence_summary`, and `bid_readiness_checklist`, including score ranges, reviewed package status values, evidence types, and non-empty reviewer-facing fields.
`reviewer_handoff.json` records reviewer handoff metadata. The local checker validates its field order, reviewer, requested decision, review prompt, and non-authorization boundary.
`proposal_handoff.json` records package-to-proposal handoff metadata for drafting preparation only; it does not authorize bid submission, legal approval, or contractual commitment. The local checker also verifies allowed next steps and keeps `blocked_until` aligned with the required inputs.
`pending_signoff.json` stays as a pending review record only. The local checker validates its field order, pending status, reviewer, review-only scope, and false operational approval.
`signoff_summary.md` gives a reviewer-readable sign-off summary for the pending review state and repeats that operational approval is false.
`procurement_review.html` is the script-free one-screen review workspace. It projects the same validated package and remains one of the 12 package artifacts; it is not a separate approval surface.
`audit_manifest.json` is the audit packet index. It lists the review package artifacts, groups decision, evidence, validation, handoff, and sign-off files, and repeats the excluded external actions before `export_manifest.json` is inspected. The local checker validates those grouped artifact sections as fixed lists so packet structure drift is caught with the other local evidence checks.
`export_manifest.json` keeps a fixed field order and repeats the included artifacts and excluded actions that the local checker validates before handoff.

## 5. Validate The Fixture Contract

Validate the source sample and expected package:

```bash
python3 scripts/validate_procurement_decision_package_sample.py
```

Failures return JSON with `status: "failed"`, `error_type`, and `error`, then exit non-zero.

Expected result includes:

```json
{
  "authorization_boundary": "explicit",
  "recommendation": "CONDITIONAL_GO",
  "status": "passed"
}
```

Validate JSON syntax for the fixture and generated package:

```bash
python3 -m json.tool docs/samples/procurement_decision_package_local_demo/sample_input.json >/tmp/decisiondoc_sample_input.json
python3 -m json.tool docs/samples/procurement_decision_package_local_demo/expected_decision_package.json >/tmp/decisiondoc_expected_package.json
python3 -m json.tool /tmp/decisiondoc-procurement-demo/decision_package.json >/tmp/decisiondoc_built_package.json
```

Check a generated package output directory:

```bash
python3 scripts/check_procurement_decision_package_artifacts.py /tmp/decisiondoc-procurement-package-demo-output
```

The checker returns JSON on success and failure. Failures exit non-zero with `status: "failed"`, `error_type`, and `error`, so automation does not need to parse Python tracebacks.
The seeded demo runner already performs this check automatically and rewrites `demo_run_result.json` with the final self-check result. Use the standalone checker when inspecting an existing output directory; if `demo_run_result.json` is present, the checker also verifies that evidence file, compares the recorded artifact inventory against the current package files, and checks the reviewer-readable receipt markers.

Create a portable review packet after the directory check passes, then verify the saved ZIP independently:

```bash
python3 scripts/manage_procurement_decision_review_packet.py create /tmp/decisiondoc-procurement-package-demo-output --packet /tmp/decisiondoc-procurement-review.zip
python3 scripts/manage_procurement_decision_review_packet.py verify /tmp/decisiondoc-procurement-review.zip
```

The output is a deterministic ZIP containing the 12 package artifacts plus embedded `packet_manifest.json`. It remains `review_ready`, preserves `operational_approval: false`, and does not turn pending sign-off into final approval. Verification checks exact entry order, path boundaries, SHA256 and size fingerprints, excluded actions, and the package's semantic artifact contract, so a fingerprint-adjusted but internally inconsistent archive is still rejected.

Initialize the companion review receipt, render the packet-bound browser form, apply its downloaded draft, and validate the completed receipt:

```bash
python3 scripts/manage_procurement_review_receipt.py init /tmp/decisiondoc-procurement-review.zip --receipt /tmp/procurement_review_receipt.json
python3 scripts/manage_procurement_review_receipt.py render /tmp/decisiondoc-procurement-review.zip --receipt /tmp/procurement_review_receipt.json --output procurement_review_receipt.html
python3 scripts/manage_procurement_review_receipt.py apply-draft /tmp/decisiondoc-procurement-review.zip --receipt /tmp/procurement_review_receipt.json --draft /tmp/procurement_review_draft.json
python3 scripts/manage_procurement_review_receipt.py validate /tmp/decisiondoc-procurement-review.zip --receipt /tmp/procurement_review_receipt.json
```

Open `/tmp/procurement_review_receipt.html` and download `procurement_review_draft.json` after entering the reviewer decision and rationale. Both are companion files, not a 13th package artifact. The draft carries packet and pending-receipt SHA256/size values, the requested reviewer, UTC review time, the explicit boundary, and `operational_approval: false`; `apply-draft` rejects stale or elevated input and atomically updates the receipt once.

For a terminal-only review, use `record` instead of `render` and `apply-draft`:

```bash
python3 scripts/manage_procurement_review_receipt.py record /tmp/decisiondoc-procurement-review.zip --receipt /tmp/procurement_review_receipt.json --reviewer executive-reviewer --decision accepted --rationale "Reviewed against package evidence." --reviewed-at 2026-07-13T14:30:00Z
```

`procurement_review_receipt.json` stays outside the ZIP and records the packet's `packet_sha256`, package identity, requested reviewer, `review_status`, decision, rationale, and UTC review time. A completed receipt cannot be recorded again, cannot be used with a different packet, and always preserves `operational_approval: false`; review acceptance authorizes no provider, deployment, training, bid, legal, or contractual action.

Create the final local audit envelope from the unchanged review packet and completed receipt, then verify the saved copy:

```bash
python3 scripts/manage_procurement_reviewed_package.py create /tmp/decisiondoc-procurement-review.zip --receipt /tmp/procurement_review_receipt.json --output /tmp/procurement-reviewed-package.zip
python3 scripts/manage_procurement_reviewed_package.py verify /tmp/procurement-reviewed-package.zip
```

`procurement-reviewed-package.zip` contains the original packet, completed receipt, and `reviewed_package_manifest.json` in a fixed order. `review_completed` means the reviewer outcome is recorded, including `changes_requested` or `rejected`; it does not authorize external action. The verifier rechecks inner packet semantics, receipt completion, source SHA256/size values, reviewer outcome, and the false operational-approval boundary. `create` refuses to overwrite an existing completed receipt audit package so prior evidence remains intact.

Run the local evidence gate for a reviewer-facing summary:

```bash
python3 scripts/gate_procurement_decision_package_demo.py /tmp/decisiondoc-procurement-package-demo-output
```

The gate reuses the artifact checker, requires both `demo_run_result.json` and `demo_evidence_receipt.md`, and returns a compact JSON summary of recommendation, boundary, self-check flags, artifact count, and excluded external actions.
If the gate fails, it still prints JSON with `status: "failed"`, `error_type`, and `error`, then exits non-zero. This keeps local automation machine-readable without hiding failed evidence checks.

Persist the gate result when stdout is not enough:

```bash
python3 scripts/gate_procurement_decision_package_demo.py \
  /tmp/decisiondoc-procurement-package-demo-output \
  --write-result
```

This writes `/tmp/decisiondoc-procurement-package-demo-output/demo_gate_result.json`. Use `--result-path <path>` with `--write-result` to store the result somewhere else; `--result-path` is rejected without `--write-result`. The persisted gate result is not part of the package artifact checksum inventory; it records the latest gate outcome for local automation and reviewer handoff.

## 6. Run Focused Regression Tests

Run the local package validator and builder tests:

```bash
pytest -q tests/test_procurement_decision_package_sample.py tests/test_procurement_decision_package_builder.py tests/test_procurement_decision_package_service.py tests/test_export_procurement_decision_package.py tests/test_run_procurement_decision_package_demo.py tests/test_check_procurement_decision_package_artifacts.py tests/test_gate_procurement_decision_package_demo.py tests/test_smoke_procurement_decision_package_demo_gate.py tests/test_check_procurement_decision_package_smoke_result.py tests/test_procurement_decision_package_review_packet.py tests/test_procurement_decision_package_review_receipt.py tests/test_procurement_decision_package_reviewed_package.py tests/test_procurement_decision_package_cli_contract_manifest.py tests/test_check_procurement_decision_package_cli_contract_manifest_result.py tests/test_procurement_decision_package_docs_contract.py tests/test_procurement_decision_package_cli_failure_contract.py tests/test_procurement_decision_package_cli_success_contract.py
```

Expected result:

```text
all listed tests pass
```

## 7. Review Checklist

Before treating the demo output as ready for review, confirm:

- recommendation is exactly `CONDITIONAL_GO`,
- evidence summary includes both source facts and missing evidence,
- bid-readiness checklist includes unresolved blockers,
- reviewer handoff includes a non-authorization note,
- pending sign-off has `"operational_approval": false`,
- export manifest lists excluded operational actions.

## 8. Boundary

This runbook does not authorize:

- provider API execution,
- AWS runtime execution,
- dataset upload,
- training execution,
- model promotion,
- production service resume,
- bid submission,
- legal approval,
- contractual commitment.

Reviewer sign-off in this local package means only that the package is ready for human review. It does not approve any operational action.

## 9. Next Implementation Step

The local fixture path now uses the reusable internal package builder in `app/services/procurement_decision_package_service.py`.
That service also exposes a project-record adapter for `ProcurementDecisionRecord` so a recommended procurement decision state can be transformed into the same review package shape.

The next implementation step is to add a CLI or route-level integration that loads an existing project-scoped procurement decision record and writes the package artifacts while preserving:

- deterministic local execution,
- strict validation,
- explicit evidence and missing-data fields,
- reviewer handoff separation,
- pending sign-off non-approval boundary.

Current project-record export CLI:

```bash
python3 scripts/export_procurement_decision_package.py \
  --data-dir data \
  --tenant-id <tenant_id> \
  --project-id <project_id> \
  --out-dir /tmp/decisiondoc-procurement-project-package
```

Use this only after a project-scoped procurement decision record already exists and includes a recommendation. Failures return JSON with `status: "failed"`, `error_type`, and `error`, then exit non-zero.

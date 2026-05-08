# Phase 36 Observed Probe Execution Workflow

Status: `OBSERVED_PROBE_EXECUTION_WORKFLOW_READY_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-09T01:14:23+09:00`

## Purpose

Phase 36 provides a one-shot operator workflow that validates runtime inputs, runs the Phase 34 read-only staging/deployed probe, and archives a passing result with the Phase 35 helper.

The local execution environment checked during this turn did not have `PHASE36_BASE_URL`, `PHASE36_EXPECT_RECORD_IDS`, or process-level `DECISIONDOC_OPS_KEY`. `.github-actions.env` contains an ops key, but the workflow still blocks without a target base URL and expected imported reviewer sign-off record ids.

## Runtime Inputs

The wrapper accepts values from command-line arguments, process environment, or one or more `--env-file` files:

- `PHASE36_BASE_URL`, `PHASE35_BASE_URL`, or `SMOKE_BASE_URL`
- `DECISIONDOC_OPS_KEY`
- `PHASE36_TENANT_ID`, defaulting to `system`
- `PHASE36_EXPECT_RECORD_IDS` or `PHASE34_EXPECT_RECORD_IDS`, comma-separated

The wrapper never prints the ops key.

## Dry-Run Preflight

```bash
python docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py \
  --env-file .github-actions.env \
  --base-url https://admin.decisiondoc.kr \
  --expect-record-id <completed_signoff_record_id> \
  --expect-record-id <pending_signoff_record_id> \
  --dry-run
```

Expected ready status:

```text
ready_for_observed_probe_execution
```

If any runtime input is missing, the wrapper returns:

```text
blocked_missing_runtime_inputs
```

## Execute Probe And Archive

```bash
python docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py \
  --env-file .github-actions.env \
  --base-url https://admin.decisiondoc.kr \
  --expect-record-id <completed_signoff_record_id> \
  --expect-record-id <pending_signoff_record_id> \
  --output-dir reports/phase36-observed-probe
```

On success, the wrapper writes:

- `reports/phase36-observed-probe/phase34-staging-readiness.json`
- `reports/phase36-observed-probe/phase35-observed-staging-probe-evidence.json`
- `reports/phase36-observed-probe/phase36-observed-probe-workflow-result.json`

## Boundary Statement

This wrapper does not import sign-off records, create reviewer approvals, upload datasets, call provider fine-tune APIs, create or poll provider jobs, start model training, or promote models.

Its only intended local side effects during a non-dry run are:

- local Phase 34 probe result JSON
- local Phase 35 evidence archive JSON
- local Phase 36 workflow result JSON

## Next Step

Phase 37 should run this wrapper with real base URL, ops key, tenant id, and expected imported sign-off record ids, then review the archived evidence before any separate production smoke.

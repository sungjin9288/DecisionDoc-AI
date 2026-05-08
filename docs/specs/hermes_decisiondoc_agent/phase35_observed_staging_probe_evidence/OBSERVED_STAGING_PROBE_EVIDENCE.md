# Phase 35 Observed Staging Probe Evidence

Status: `OBSERVED_STAGING_PROBE_ARCHIVE_READY_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-09T00:53:03+09:00`

## Purpose

Phase 35 defines how to archive an actual Phase 34 staging/deployed probe result after an operator runs the read-only probe with real environment credentials and expected imported sign-off record ids.

This phase does not claim that staging has passed yet. The current local environment does not contain `DECISIONDOC_OPS_KEY`, `PHASE35_BASE_URL`, or expected sign-off record ids, so no real deployed probe was executed in this turn.

## Operator Sequence

1. Import expected pending/completed sign-off records into the target environment with the Phase 31 helper.
2. Run the Phase 34 probe against the target environment:

```bash
python docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/run_staging_readiness_probe.py \
  --base-url https://admin.decisiondoc.kr \
  --ops-key "$DECISIONDOC_OPS_KEY" \
  --tenant-id system \
  --expect-record-id <completed_signoff_record_id> \
  --expect-record-id <pending_signoff_record_id> \
  --output reports/phase34-staging-readiness.json
```

3. Archive the passing result locally:

```bash
python docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/archive_staging_probe_result.py \
  reports/phase34-staging-readiness.json \
  --output-dir reports \
  --output-filename phase35-observed-staging-probe-evidence.json \
  --evidence-owner release_owner
```

## Archive Acceptance Criteria

The archive helper accepts only Phase 34 probe results that satisfy all of these conditions:

- `report_type=document_ops_phase34_staging_readiness_probe_result`
- `phase=34`
- `status=pass`
- `target.base_url` is present and is not a fixture URL
- `/health` returned `200`
- summary endpoint required ops key
- summary endpoint returned records
- download endpoint returned records
- download endpoint reported `server_file_written=false`
- expected imported record ids were visible in both payloads
- `failures=[]`
- all guard flags remain `false`
- all side-effect boundary values remain `false`

## Boundary Statement

The archive helper writes only a local evidence JSON file. It does not write server-side export artifacts, does not import sign-off records, does not create reviewer approvals, does not upload datasets, does not call provider fine-tune APIs, does not create or poll provider jobs, does not start model training, and does not promote models.

## Current Result

Current status is `observed_staging_probe_pending_missing_runtime_credentials`. The probe can be executed once the operator provides:

- target base URL
- `DECISIONDOC_OPS_KEY`
- tenant id
- expected completed sign-off record id
- expected pending sign-off record id

## Next Step

Phase 36 should review an archived Phase 35 observed staging evidence file, then decide whether to proceed to a separate production smoke. Production smoke remains separate from training approval and model promotion.

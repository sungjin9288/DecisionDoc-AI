# Phase 34 Staging-Readiness Dry-Run

Status: `STAGING_READINESS_PROBE_READY_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-08T20:14:50+09:00`

## Purpose

Phase 34 turns the Phase 33 release packet into an operator-run staging dry-run. It provides a read-only HTTP probe that checks the deployed DocumentOps reviewer sign-off flow without importing records, generating approvals, uploading datasets, calling provider fine-tune APIs, creating provider jobs, or promoting a model.

This phase prepares the staging dry-run command path and validates the probe logic locally. It does not claim that a real staging or production environment has passed until an operator runs the probe with the actual staging base URL and ops key.

## Prerequisites

- Phase 30 operator packet guide has been followed to create or collect reviewer sign-off records.
- Phase 31 import helper has copied pending or locally validated completed records into the target environment's tenant-local `DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/`.
- Phase 32 local browser QA is available as the expected UI/API behavior reference.
- The operator has the target environment base URL and `DECISIONDOC_OPS_KEY`.
- The target environment exposes `GET /health` and the DocumentOps reviewer sign-off read-only endpoints.

## Command

```bash
python docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/run_staging_readiness_probe.py \
  --base-url https://admin.decisiondoc.kr \
  --ops-key "$DECISIONDOC_OPS_KEY" \
  --tenant-id system \
  --expect-record-id dsr_example_completed \
  --expect-record-id dsr_example_pending \
  --output reports/phase34-staging-readiness.json
```

The probe performs only these HTTP requests:

- `GET /health`
- `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50` without ops key, expecting `401` or `403`
- `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50` with `X-DecisionDoc-Ops-Key`
- `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary/download?limit=50` with `X-DecisionDoc-Ops-Key`

## Pass Criteria

- Health returns `200`.
- Reviewer sign-off summary rejects unauthenticated or API-key-only access.
- Ops-key summary returns `document_ops_phase25_signoff_summary_endpoint`.
- Ops-key JSON download returns `document_ops_phase27_reviewer_signoff_summary_export`.
- Expected imported sign-off record ids appear in both summary and download JSON.
- Download JSON reports `server_file_written=false`.
- Summary/download guard flags and side-effect boundaries remain false.
- The probe result reports:
  - `training_authorized=false`
  - `external_dataset_upload_authorized=false`
  - `provider_fine_tune_api_call_authorized=false`
  - `provider_job_creation_authorized=false`
  - `model_promotion_authorized=false`
  - `production_smoke_completed=false`

## Failure Handling

If the probe fails, do not proceed to training, production smoke, or model promotion. Fix the failed checkpoint first:

- `health endpoint did not return 200`: confirm deployment, nginx/upstream health, and base URL.
- `summary did not require ops key`: check `DECISIONDOC_OPS_KEY` and route dependencies.
- `summary missing expected sign-off record ids`: confirm the Phase 31 import destination and tenant id.
- `download JSON missing expected sign-off record ids`: check the download endpoint and summary export payload shape.
- Any guard or side-effect violation: stop and treat as a release blocker.

## Boundary Statement

This dry-run probe is read-only. It does not create reviewer records, does not import files, does not write server artifacts, does not approve reviewer sign-off, does not start model training, does not upload datasets, does not call provider fine-tune APIs, does not create or poll provider jobs, and does not promote models.

## Next Step

Phase 35 should record an actual staging/deployed probe result after the operator runs this command with real environment credentials and expected imported sign-off record ids.

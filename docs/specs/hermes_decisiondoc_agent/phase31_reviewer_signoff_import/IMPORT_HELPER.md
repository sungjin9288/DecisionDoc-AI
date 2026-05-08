# Phase 31 Tenant-Local Reviewer Sign-Off Import Helper

## Summary

- Status: IMPORT_HELPER_READY_NO_TRAINING_AUTHORIZATION
- Created at: 2026-05-08T19:25:37+09:00
- Scope: Controlled local import of pending or validated completed reviewer sign-off records into `DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/`.
- Helper: `docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py`

This helper is local file placement only. It does not create reviewer approval, does not authorize model training, does not upload datasets, does not call provider fine-tune APIs, does not create or poll provider jobs, and does not promote a model.

## Why This Exists

Phase 30 documented a manual copy step for browser inspection:

```bash
cp reports/reviewer-signoff/*.json "$DATA_DIR/tenants/system/trajectory_reviewer_signoffs/"
```

Manual copying is easy to get wrong. Phase 31 replaces that step with a constrained helper that validates the record shape, tenant id, destination filename, and no-training boundary before placing the file where the existing DocumentOps `Sign-off summary` and `Sign-off JSON` actions can read it.

## Accepted Inputs

The helper accepts only:

- Pending sign-off records with `status=pending_manual_signoff`, pending reviewer decisions, and protected authorization flags set to `false`.
- Completed sign-off records that pass `validate_signoff_record.py`, use `status=manual_signoff_complete`, and keep protected training/provider authorization flags set to `false`.

The helper rejects:

- non-JSON files
- JSON arrays or scalar payloads
- malformed `signoff_record_id`
- tenant ids outside `[A-Za-z0-9_-]{1,64}`
- output filenames with path separators or unsafe characters
- records with training/upload/provider/model-promotion authorization flags set to `true`
- incomplete completed records that try to look approved without passing local validation

## Usage

Dry-run first:

```bash
python docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py \
  reports/reviewer-signoff/<record>.json \
  --data-dir "$DATA_DIR" \
  --tenant-id system \
  --dry-run
```

Import into tenant-local DocumentOps storage:

```bash
python docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py \
  reports/reviewer-signoff/<record>.json \
  --data-dir "$DATA_DIR" \
  --tenant-id system
```

Optional deterministic filename:

```bash
python docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py \
  reports/reviewer-signoff/<record>.json \
  --data-dir "$DATA_DIR" \
  --tenant-id system \
  --output-filename dsr_example_completed_signoff.json
```

## Expected Output

The command writes a JSON result to stdout:

```json
{
  "ok": true,
  "report_type": "document_ops_phase31_reviewer_signoff_import_result",
  "tenant_id": "system",
  "record_state": "pending_manual_signoff_no_training_authorization",
  "destination_path": ".../DATA_DIR/tenants/system/trajectory_reviewer_signoffs/dsr_example_pending_signoff.json",
  "validation_valid": false,
  "import_boundary": {
    "actual_reviewer_approval_recorded_by_import": false,
    "training_execution_authorized": false,
    "external_dataset_upload_authorized": false,
    "server_side_generated_approval_record": false,
    "provider_fine_tune_api_call_authorized": false,
    "provider_job_creation_authorized": false,
    "provider_job_polling_authorized": false,
    "model_candidate_emission_authorized": false,
    "model_promotion_authorized": false
  }
}
```

For completed records, `validation_valid=true` and `record_state=manual_signoff_complete_no_training_authorization`.

## Post-Import Check

After import, inspect through the existing read-only endpoint or UI:

```text
GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50
```

In the admin UI:

- Open `DocumentOps`.
- Enter the ops key.
- Click `Sign-off summary`.
- Click `Sign-off JSON` if JSON export inspection is required.

## Boundary Statement

This helper copies an operator-provided record into tenant-local storage. It does not edit reviewer fields, does not set `actual_reviewer_approval_recorded`, does not generate completed approval records, does not write a server-side export artifact, and does not call any provider.

The only intended side effect is `tenant_local_record_copied=true` when `--dry-run` is not used.

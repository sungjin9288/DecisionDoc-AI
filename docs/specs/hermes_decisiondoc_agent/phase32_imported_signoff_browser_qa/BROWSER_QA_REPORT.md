# Phase 32 Imported Reviewer Sign-Off Browser QA Report

Result: PASS

## Scope

Phase 32 verified that reviewer sign-off records imported by the Phase 31 helper are visible through the existing DocumentOps `Sign-off summary` and `Sign-off JSON` UI actions.

This QA was evidence-only. It copied operator-provided records into tenant-local storage for inspection, but it did not create reviewer approval, authorize model training, upload datasets, write a server-side export artifact, call provider fine-tune APIs, create provider jobs, or promote a model.

## Environment

- App URL: `http://127.0.0.1:8770/?ops=1&phase32=1778150148160`
- App runtime: local `uvicorn` with `DECISIONDOC_PROVIDER=mock`
- Data root: `/tmp/decisiondoc-phase32-browser-qa`
- Source record root: `/tmp/decisiondoc-phase32-browser-qa-source`
- Tenant: `system`
- Auth path: local first-admin registration, browser login, ops key entered in the local Ops panel
- Import helper: `docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py`

## Imported Records

The Phase 31 helper imported two records:

- Pending record: `dsr_phase32pending`
- Completed record: `dsr_phase32done`

The helper reported:

- `record_state=pending_manual_signoff_no_training_authorization` for `dsr_phase32pending`
- `record_state=manual_signoff_complete_no_training_authorization` for `dsr_phase32done`
- `tenant_local_record_copied=true`
- `training_execution_authorized=false`
- `external_dataset_upload_authorized=false`
- `provider_fine_tune_api_call_authorized=false`
- `server_side_generated_approval_record=false`
- `model_promotion_authorized=false`

## API Checkpoints

The read-only summary endpoint returned:

- Endpoint: `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50`
- Status: `200`
- Report type: `document_ops_phase25_signoff_summary_endpoint`
- Overall status: `pending_manual_signoff_no_training_authorization`
- Record count: `2`
- Pending record present: `dsr_phase32pending`
- Completed record present: `dsr_phase32done`
- Blocker: `dsr_phase32pending_pending_signoff.json: pending_manual_signoff`
- Guard flags: all training/upload/provider/model-promotion flags `false`

The JSON download endpoint returned:

- Endpoint: `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary/download?limit=50`
- Status: `200`
- Content-Type: `application/json`
- Content-Disposition: `attachment; filename="reviewer_signoff_summary_system_20260508T104522Z.json"`
- Report type: `document_ops_phase27_reviewer_signoff_summary_export`
- Record count: `2`
- Pending record present: `dsr_phase32pending`
- Completed record present: `dsr_phase32done`
- `server_file_written=false`
- Guard flags: all training/upload/provider/model-promotion flags `false`

## Observed Browser Steps

1. Loaded the local admin UI in the browser.
2. Created a local admin account and logged in.
3. Dismissed the onboarding overlay.
4. Opened the `DocumentOps` page tab.
5. Entered the local ops key.
6. Clicked `Sign-off summary`.
7. Confirmed the imported pending and completed records rendered in the `Reviewer Sign-Off Summary` panel.
8. Clicked `Sign-off JSON`.
9. Confirmed a browser download event for `reviewer_signoff_summary_system_20260508T105427Z.json`.
10. Confirmed the fallback save/open link also rendered.
11. Opened the downloaded JSON artifact and confirmed it contains both imported record IDs.

## Observed UI Evidence

- Active tab: `DocumentOps`
- `Reviewer Sign-Off Summary` was visible.
- Read-only copy was visible: `read-only sign-off evidence · no training · no upload · no provider calls`.
- Overall status badge showed `SIGN-OFF PENDING`.
- Count cards showed `records=2`, `completed=1`, `pending=1`, `follow-up=0`, and `boundary alerts=0`.
- Completed imported record `dsr_phase32done` was visible with `validation=valid`, `training=false`, and `provider_api=false`.
- Pending imported record `dsr_phase32pending` was visible with `validation=pending`, `training=false`, and `provider_api=false`.
- Sign-off blocker was visible: `dsr_phase32pending_pending_signoff.json: pending_manual_signoff`.
- `Sign-off JSON` generated the downloaded filename `reviewer_signoff_summary_system_20260508T105427Z.json`.
- Download fallback link was visible for the same filename.
- Success notification was visible: `Reviewer sign-off summary JSON 다운로드 시작`.
- No-training notification copy was visible: `학습/업로드/provider 호출은 시작되지 않았습니다`.

## Guard Evidence

The imported-record browser flow preserved these boundaries:

- `actual_reviewer_approval_recorded_by_import=false`
- `server_side_generated_approval_record=false`
- `training_execution_authorized=false`
- `external_dataset_upload_authorized=false`
- `provider_fine_tune_api_call_authorized=false`
- `provider_job_creation_authorized=false`
- `provider_job_polling_authorized=false`
- `model_candidate_emission_authorized=false`
- `model_promotion_authorized=false`
- `training_execution_started=false`
- `external_dataset_uploaded=false`
- `provider_fine_tune_api_called=false`
- `provider_job_created=false`
- `provider_job_polled=false`
- `model_candidate_emitted=false`
- `model_promoted=false`
- `server_file_written=false`

The only intended local side effect was copying operator-provided JSON records into the tenant-local inspection directory.

## Boundary Statement

This QA proves the local app can read records imported by the Phase 31 helper and expose them through the existing DocumentOps summary/download UI. It does not prove production deployment behavior, does not record actual reviewer approval, does not approve training execution, and does not replace actual Product/PM, ML/AI owner, Compliance/Security, or Release owner sign-off.

# Phase 28 Reviewer Sign-Off JSON Download Browser QA Report

Result: PASS

## Scope

Phase 28 verified the DocumentOps `Sign-off JSON` UI action against the local mock-provider app and the ops-key protected reviewer sign-off summary download endpoint.

This QA was evidence-only. It did not authorize model training, upload datasets, write a server-side artifact, call provider fine-tune APIs, create provider jobs, or promote a model.

## Environment

- App URL: `http://127.0.0.1:8769/?ops=1&phase28=1778150148160`
- App runtime: local `uvicorn` with `DECISIONDOC_PROVIDER=mock`
- Data root: `/tmp/decisiondoc-phase28-browser-qa`
- Tenant: `system`
- Auth path: local first-admin registration, browser login, ops key entered in the local Ops panel
- Seed records:
  - Pending record: `dsr_phase28pending`
  - Completed record: `dsr_phase28done`

## API Checkpoint

The download endpoint returned an attachment JSON response:

- Endpoint: `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary/download?limit=50`
- Status: `200`
- Content-Type: `application/json`
- Content-Disposition: `attachment; filename="reviewer_signoff_summary_system_20260508T060752Z.json"`
- Report type: `document_ops_phase27_reviewer_signoff_summary_export`
- Summary status: `pending_manual_signoff_no_training_authorization`
- Record count: `2`
- Pending record present: `dsr_phase28pending`
- Completed record present: `dsr_phase28done`
- Guard flags: all `false`
- Side-effect boundary flags: all `false`

## Observed Browser Steps

1. Loaded the local admin UI in the Codex in-app browser.
2. Created a local admin account and logged in.
3. Dismissed the welcome overlay that blocked tab clicks.
4. Opened the `DocumentOps` page tab.
5. Entered the local ops key in the Ops panel.
6. Confirmed the `Sign-off JSON` button was visible.
7. Clicked `Sign-off JSON`.
8. Confirmed the UI success notification was visible.
9. Confirmed the DocumentOps download fallback panel rendered a `reviewer_signoff_summary_system_*.json` link.

## Observed UI Evidence

- `Sign-off JSON` button was visible in DocumentOps.
- Success notification was visible: `Reviewer sign-off summary JSON 다운로드 시작`.
- No-training notification copy was visible: `학습/업로드/provider 호출은 시작되지 않았습니다`.
- Download fallback panel was visible.
- Fallback link filename was visible: `reviewer_signoff_summary_system_20260508T061250Z.json`.
- Current-port browser console errors were empty.

## Runtime Limitation

Codex in-app browser reported: `Downloads are not supported by Codex In-app Browser.`

This limitation prevents native OS download-event verification in this QA environment. The browser-side UI still fetched the JSON blob successfully before calling the download helper, rendered the fallback link, and displayed the success notification. That is the observed evidence that the browser received the JSON artifact payload.

## Guard Evidence

The endpoint, UI flow, and QA result preserved these no-side-effect guards:

- `server_file_written=false`
- `training_execution_allowed=false`
- `provider_api_calls_allowed=false`
- `external_upload_allowed=false`
- `provider_job_started=false`
- `model_promotion_allowed=false`
- `actual_reviewer_approval_recorded_by_export=false`
- `training_execution_started=false`
- `external_dataset_uploaded=false`
- `provider_fine_tune_api_called=false`
- `provider_job_created=false`
- `model_promoted=false`

## Boundary Statement

This QA proves the local browser flow can request the reviewer sign-off JSON export and render a save fallback for the returned JSON blob. It does not prove production download behavior, does not record actual reviewer approval, does not approve training execution, and does not replace actual Product/PM, ML/AI owner, Compliance/Security, or Release owner sign-off.

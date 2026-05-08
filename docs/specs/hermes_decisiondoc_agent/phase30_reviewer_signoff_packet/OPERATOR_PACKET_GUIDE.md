# Phase 30 Operator Reviewer Sign-Off Packet Guide

## Summary

- Status: OPERATOR_PACKET_READY_NO_TRAINING_AUTHORIZATION
- Created at: 2026-05-08T19:25:37+09:00
- Scope: Operator-ready procedure for creating, collecting, validating, summarizing, and inspecting DocumentOps human reviewer sign-off records.
- Source handoff: `docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/RELEASE_HANDOFF_INDEX.md`
- Machine-readable checklist: `docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/operator_packet_checklist.json`

This guide is a reviewer packet procedure only. It does not authorize model training, does not authorize dataset upload, does not authorize provider fine-tune API calls, does not authorize server-side export artifact writes, does not authorize provider job creation or polling, does not authorize model candidate emission, and does not authorize model promotion.

## Preconditions

- You are working from the repository root.
- The reviewer group has four roles: Product / PM reviewer, ML / AI owner, Compliance / Security reviewer, and Release owner.
- The operator has a safe local directory for sign-off records. Recommended examples below use `reports/reviewer-signoff`.
- If browser inspection is needed, the target app must already be running and the operator must have the ops key. Do not paste ops keys into docs or committed files.
- The DocumentOps UI reads tenant-local records from `DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/*.json`.

## Packet Contents

The packet for reviewers should include these paths:

- `docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/RELEASE_HANDOFF_INDEX.md`
- `docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json`
- `docs/specs/hermes_decisiondoc_agent/STATUS.md`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/SIGNOFF_RECORD_TEMPLATE.md`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py`
- `docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/BROWSER_QA_REPORT.md`
- `docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/BROWSER_QA_REPORT.md`

## Operator Flow

1. Create a local packet directory.

```bash
mkdir -p reports/reviewer-signoff
```

2. Generate a pending sign-off record.

```bash
python docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py \
  --output-dir reports/reviewer-signoff
```

Expected result:

- A file named `dsr_<id>_pending_signoff.json` exists in `reports/reviewer-signoff`.
- The command output says `status=pending_manual_signoff`.
- `training_execution_authorized=false`.
- `provider_fine_tune_api_call_authorized=false`.

3. Give reviewers the pending JSON record and the packet contents.

Each reviewer must fill:

- `reviewer_name`
- `reviewer_title_or_team`
- `reviewed_at`
- `decision`
- `evidence_reviewed`
- `notes`
- every `required_acknowledgements` value

Allowed decisions:

- `sign_off_ready_for_human_review`
- `changes_requested`
- `blocked`

Do not change protected boundary fields to `true`.

4. Validate the completed record.

```bash
python docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py \
  reports/reviewer-signoff/<completed_signoff_record>.json
```

Pass criteria:

- Exit code is `0`.
- `valid=true`.
- `error_count=0`.
- all required reviewer roles are present.
- all protected no-training boundary keys remain `false`.

If the validator fails, do not continue to release approval. Return the record to the reviewer group with the validation errors.

5. Summarize the packet directory.

```bash
python docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py \
  reports/reviewer-signoff \
  --output reports/reviewer-signoff/signoff_summary.json
```

Pass criteria:

- `record_count` is at least `1`.
- `overall_status=manual_signoff_complete_no_training_authorization` only after all records validate.
- `aggregate.all_protected_training_flags_false=true`.
- `side_effect_boundary.training_execution_started=false`.
- `side_effect_boundary.provider_fine_tune_api_called=false`.

6. Optional: inspect the same records in DocumentOps UI.

To use the app UI, import completed or pending records with the Phase 31 helper:

```bash
python docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py \
  reports/reviewer-signoff/<record>.json \
  --data-dir "$DATA_DIR" \
  --tenant-id system
```

Then open DocumentOps and use:

- `Sign-off summary` to inspect reviewer completion, blockers, validation state, and boundary flags.
- `Sign-off JSON` to request the in-memory reviewer summary JSON attachment.

If the browser does not support native downloads, the UI should render a fallback link. Codex in-app browser has this limitation; Phase 28 verified JSON blob receipt and fallback visibility.

## Do Not Do

- Do not treat a pending record as approval.
- Do not edit `training_execution_authorized`, `external_dataset_upload_authorized`, `provider_fine_tune_api_call_authorized`, `provider_job_creation_authorized`, `provider_job_polling_authorized`, `model_candidate_emission_authorized`, or `model_promotion_authorized` to `true`.
- Do not upload sign-off records or datasets to external providers as part of this packet.
- Do not call OpenAI, Gemini, Claude, or any provider fine-tune API from this packet.
- Do not create, poll, or promote provider training jobs from this packet.
- Do not commit secrets, ops keys, raw customer documents, or reviewer private contact details.

## Completion Checklist

- [ ] Pending sign-off record generated from the Phase 21 template or Phase 23 generator.
- [ ] All four reviewer roles completed their fields and acknowledgements.
- [ ] Validator returned `valid=true` and exit code `0`.
- [ ] Summary returned no protected boundary violations.
- [ ] Operator confirmed the DocumentOps `Sign-off summary` view if browser inspection is required.
- [ ] Operator confirmed the DocumentOps `Sign-off JSON` action or fallback link if JSON export inspection is required.
- [ ] No model training, dataset upload, server-side reviewer JSON artifact write, provider fine-tune API call, provider job, or model promotion was started.

## Example Completed Decision Block

Use this as a content example only. Reviewer identity and evidence should reflect the actual review.

```json
{
  "reviewer_role": "product_pm_reviewer",
  "reviewer_name": "Reviewer Name",
  "reviewer_title_or_team": "Product / PM",
  "reviewed_at": "2026-05-08T19:25:37+09:00",
  "decision": "sign_off_ready_for_human_review",
  "evidence_reviewed": [
    "docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/RELEASE_HANDOFF_INDEX.md",
    "docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/BROWSER_QA_REPORT.md",
    "docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/BROWSER_QA_REPORT.md"
  ],
  "notes": "Reviewed reviewer sign-off packet and no-training boundary.",
  "required_acknowledgements": {
    "reviewed_phase20_handoff_for_role": true,
    "does_not_authorize_model_training": true,
    "does_not_authorize_dataset_upload": true,
    "does_not_authorize_provider_fine_tune_api_calls": true,
    "does_not_authorize_provider_job_creation_or_polling": true,
    "does_not_authorize_model_promotion": true,
    "blocking_issues_recorded_in_notes": true
  }
}
```

## Boundary Statement

The packet is complete only when the local validator and summary reporter pass. Even then, the result is `human_reviewer_use_ready_no_training_authorization`; it is not `ready_for_training_execution`.

A future training execution still requires a separate approved execution workflow, implemented provider adapter, security review, live deployment smoke, explicit training authorization, and provider-side execution controls.

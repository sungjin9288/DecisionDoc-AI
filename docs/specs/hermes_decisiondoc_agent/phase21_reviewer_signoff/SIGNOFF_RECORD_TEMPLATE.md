# Phase 21 Manual Reviewer Sign-Off Record Template

## Summary

- Status: TEMPLATE_ONLY_NO_ACTUAL_SIGNOFF
- Created at: 2026-05-07T23:59:59+09:00
- Scope: Manual reviewer sign-off record format for the Phase 20 DocumentOps governance handoff.
- Source handoff: `docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/RELEASE_HANDOFF_INDEX.md`
- Machine-readable template: `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json`

This template records how human reviewers should sign off the no-training governance package. It does not record actual reviewer approval, authorize model training, upload datasets, call provider fine-tune APIs, create provider jobs, or promote a model.

## Required Reviewers

| Order | Reviewer Role | Required Evidence | Decision Field |
|---:|---|---|---|
| 1 | Product / PM reviewer | Browser QA report, DocumentOps UI flow, accepted trajectory visibility | `sign_off_ready_for_human_review` or `changes_requested` |
| 2 | ML / AI owner | Training/data plan, QA gates, freeze/approval/rehearsal evidence | `sign_off_ready_for_human_review` or `changes_requested` |
| 3 | Compliance / Security reviewer | Redaction, no-upload guard, no-provider-call guard, audit packet | `sign_off_ready_for_human_review` or `changes_requested` |
| 4 | Release owner | Status ledger, verification commands, handoff manifest completeness | `sign_off_ready_for_human_review` or `changes_requested` |

## Reviewer Record Fields

Each reviewer record must include:

- `reviewer_role`
- `reviewer_name`
- `reviewer_title_or_team`
- `reviewed_at`
- `decision`
- `evidence_reviewed`
- `notes`
- `required_acknowledgements`

Allowed `decision` values:

- `pending`
- `sign_off_ready_for_human_review`
- `changes_requested`
- `blocked`

## Required Acknowledgements

Each reviewer must explicitly acknowledge all of the following:

- I reviewed the Phase 20 handoff package for my reviewer role.
- I understand this sign-off does not authorize model training.
- I understand this sign-off does not authorize dataset upload.
- I understand this sign-off does not authorize provider fine-tune API calls.
- I understand this sign-off does not authorize provider job creation or polling.
- I understand this sign-off does not authorize model promotion.
- I recorded any blocking issues in `notes`.

## Manual Record Template

```text
Reviewer role:
Reviewer name:
Reviewer title or team:
Reviewed at:
Decision:

Evidence reviewed:
- <artifact path or title>

Required acknowledgements:
- [ ] I reviewed the Phase 20 handoff package for my reviewer role.
- [ ] I understand this sign-off does not authorize model training.
- [ ] I understand this sign-off does not authorize dataset upload.
- [ ] I understand this sign-off does not authorize provider fine-tune API calls.
- [ ] I understand this sign-off does not authorize provider job creation or polling.
- [ ] I understand this sign-off does not authorize model promotion.
- [ ] I recorded any blocking issues in notes.

Notes:
```

## Sign-Off Boundary

This template is explicitly non-executable. It is a human governance record format only.

The template keeps these release boundary values fixed:

- `actual_reviewer_approval_recorded=false`
- `training_execution_authorized=false`
- `external_dataset_upload_authorized=false`
- `provider_fine_tune_api_call_authorized=false`
- `provider_job_creation_authorized=false`
- `model_promotion_authorized=false`

## Completion Rule

The sign-off process is complete only when every required reviewer record has:

- a non-empty reviewer name
- a timestamp
- a decision other than `pending`
- all required acknowledgements checked
- notes present when the decision is `changes_requested` or `blocked`

Even after all reviewer records are complete, training execution still requires a separate approved execution workflow, implemented provider adapter, security review, and live deployment smoke.

## Phase 22 Local Validation

Use the local validator after reviewers fill a copy of `signoff_record_template.json`.

```bash
python docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py path/to/completed_signoff_record.json
```

The validator exits with code `0` only when:

- all required reviewer roles are present
- reviewer names, teams/titles, timestamps, decisions, evidence lists, and acknowledgements are complete
- `changes_requested` or `blocked` decisions include notes
- all protected no-training boundary flags remain `false`
- `completion_rule.manual_signoff_complete=true`

The validator exits non-zero for the pending template because it is not an actual completed sign-off record.

## Phase 23 Pending Record Generation

Use the local generator to create a fillable pending sign-off record from the template.

```bash
python docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py \
  --output-dir path/to/signoff_records
```

The generator writes `<record_id>_pending_signoff.json` with:

- generated `signoff_record_id`
- generated `created_at`
- status `pending_manual_signoff`
- blank reviewer names, titles/teams, timestamps, and notes
- reviewer decisions set to `pending`
- all acknowledgements unchecked
- `completion_rule.manual_signoff_complete=false`
- no-training boundary flags preserved as `false`

Generated pending records are fillable records only. They are expected to fail `validate_signoff_record.py` until human reviewers complete the fields and acknowledgements.

## Phase 24 Sign-Off Record Summary

Use the local summary command to inspect generated or completed sign-off records.

```bash
python docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py \
  path/to/signoff_records \
  --output path/to/signoff_summary.json
```

The summary command reports:

- total sign-off records found
- reviewer completion counts per record
- pending, changes-requested, and blocked reviewer decisions
- completed-validation pass/fail metadata
- protected no-training/no-upload/no-provider-call boundary flags

The summary report is status evidence only. It does not approve reviewer sign-off, authorize model training, upload datasets, call provider fine-tune APIs, create provider jobs, or promote a model.

## Phase 25 Read-Only UI Endpoint

The DocumentOps governance UI can read tenant-local sign-off summaries through an ops-key protected endpoint:

```text
GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50
```

The endpoint reads tenant-local JSON records from `DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/*.json`, does not accept arbitrary file paths, and returns reviewer completion, blocker, validation, and no-training boundary metadata as evidence. It remains read-only and does not approve reviewer sign-off, authorize model training, upload datasets, call provider fine-tune APIs, create provider jobs, or promote a model.

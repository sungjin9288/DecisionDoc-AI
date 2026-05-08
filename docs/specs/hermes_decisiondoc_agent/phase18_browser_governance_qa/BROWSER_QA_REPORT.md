# Phase 18 Browser Governance QA Report

## Summary

- Date: 2026-05-07 23:45:58 KST
- Result: PASS
- Browser URL: `http://127.0.0.1:8767/?ops=1&phase18=1778150148160`
- Scope: DocumentOps no-training governance UI flow after Phase 17 dry-run provider execution rehearsal.
- Boundary: No model training, no external upload, no provider fine-tune API call, no provider job, and no model promotion were performed.

## Environment

- App server: local `uvicorn` on `127.0.0.1:8767`
- Provider: `mock`
- Storage: local temp `DATA_DIR=/tmp/decisiondoc-phase18-browser-qa`
- Auth: local temporary admin session plus local ops-key path
- Browser surface: Codex in-app browser through Browser Use `iab`
- Secrets: local test keys were used only in the running local process and are not recorded in this artifact.

## Seeded Metadata Artifacts

These artifacts were created against the local mock server to render the full governance dashboard in a ready state. They are metadata-only local QA records.

| Artifact | ID / Filename |
|---|---|
| Accepted trajectory | `trj_7bf3cf6707944c84b73ae57776218a70` |
| Reviewed SFT export | `sft_decision_brief_20260507T144245.jsonl` |
| Dataset freeze manifest | `dsf_2d63dbe7b3ce4e77997bde2e03e93922` |
| Dry-run training approval | `tap_be35e98c7b28452b8e42e375920d020a` |
| Training execution request record | `ter_5f4b873ef1944727adf85fb534297de6` |
| Pre-execution audit export | `tea_8bb3e5e7ceab42758c06942c4ad57294` |

## Browser Checklist

| Check | Evidence | Result |
|---|---|---|
| DocumentOps tab opens | `DocumentOps Agent` region visible | PASS |
| Seeded trajectory is visible | accepted `decision_brief` trajectory rendered with QA PASS | PASS |
| Reviewed JSONL list renders | task filter switched to `decision_brief`; export filename visible | PASS |
| Readiness renders ready state | `Training Readiness Summary` and `READY FOR DECISION` visible | PASS |
| Plan preview renders dry-run plan | `Training Execution Plan Preview` and `PREVIEW READY` visible | PASS |
| Audit checklist renders review packet | `Training Pre-Execution Audit Checklist`, `READY FOR REVIEW`, and audit artifact visible | PASS |
| Governance summary renders aggregate | `Training Governance Dashboard Summary` and `GOVERNANCE READY` visible | PASS |
| Adapter contract renders safe stub | `Training Provider Adapter Contract`, `CONFIG SAFE`, and `Forbidden in stub` visible | PASS |
| Rehearsal renders dry-run steps | `Training Execution Rehearsal`, `REHEARSAL READY`, and `side_effect=false` visible | PASS |
| No-side-effect copy is visible | `no training`, `no upload`, and `no provider calls` visible | PASS |

## Guard Evidence

The local API seed and browser-rendered panels confirmed the following guard values:

```json
{
  "ready_for_training_execution": true,
  "governance_status": "governance_ready_for_human_review",
  "rehearsal_status": "rehearsal_ready",
  "training_execution_allowed": false,
  "provider_api_calls_allowed": false,
  "external_upload_allowed": false,
  "provider_job_started": false,
  "model_promotion_allowed": false,
  "guard_counts": {
    "reviewed_sft_exports": 1,
    "dataset_freezes": 1,
    "dry_run_training_approvals": 1,
    "training_execution_requests": 1,
    "pre_execution_audit_exports": 1
  }
}
```

## Notes

- The prompt-based `Request record` and `Audit export` create buttons were not triggered from the browser during final QA to avoid duplicate records. Equivalent local metadata records were seeded through the existing ops-key API path, then verified through the browser-rendered Audit and Governance panels.
- The first reviewed JSONL click used the default `policy_planning_brief` task filter and therefore showed no matching file. The filter was corrected to `decision_brief`, and the reviewed JSONL artifact rendered successfully.
- This QA pass validates local mock-provider browser behavior. Production smoke remains a separate deployment validation step.

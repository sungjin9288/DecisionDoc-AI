# Phase 37 Deployed Probe Failure Evidence

Status: `DEPLOYED_PROBE_BLOCKED_OPS_KEY_AUTH_FAILED_NO_TRAINING_AUTHORIZATION`

Observed at: `2026-05-09T01:45:22+09:00`

## Purpose

Phase 37 attempted the real read-only deployed probe against `https://admin.decisiondoc.kr` using the ops key available in `.github-actions.env`. The probe did not pass, so no Phase 35 passing evidence archive was created.

This failure evidence preserves the deployed checkpoint results without exposing the ops key and without starting training, uploading datasets, generating approvals, creating provider jobs, or promoting models.

## Observed Result

| Checkpoint | Result |
|---|---|
| `GET /health` | `200` |
| `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50` without ops key | `401` |
| `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary?limit=50` with `.github-actions.env` ops key | `401` |
| `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary/download?limit=50` with `.github-actions.env` ops key | `401` |
| Expected record ids | not supplied |
| Phase 35 archive | not created |

## Interpretation

The deployed service is reachable and healthy, but the ops-key-protected DocumentOps reviewer sign-off endpoints rejected the locally available ops key. Because both ops-key summary and download returned `401`, the likely issue is one of:

- `.github-actions.env` does not contain the current deployed `DECISIONDOC_OPS_KEY`.
- The deployed environment was restarted with a different `DECISIONDOC_OPS_KEY`.
- The target environment is not the environment that uses the local `.github-actions.env` key.

This is an inference from the observed HTTP status codes. It should be confirmed on the server by checking the deployed runtime env, without printing the secret value.

## Required Remediation

1. Confirm the deployed `DECISIONDOC_OPS_KEY` source of truth on the server or deployment secret store.
2. Provide the correct ops key to the Phase 36 wrapper by process env or a local env-file.
3. Ensure the expected completed and pending reviewer sign-off records have been imported into `DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/`.
4. Re-run Phase 36 with the correct base URL, tenant id, ops key, and expected record ids.
5. Archive only a passing Phase 34 result with the Phase 35 helper.

## Safe Re-Run Command

```bash
python docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py \
  --env-file <env-file-with-current-deployed-ops-key> \
  --base-url https://admin.decisiondoc.kr \
  --tenant-id system \
  --expect-record-id <completed_signoff_record_id> \
  --expect-record-id <pending_signoff_record_id> \
  --output-dir reports/phase36-observed-probe
```

## Boundary Statement

This failed probe evidence is read-only. It did not import files, did not create reviewer approvals, did not write a passing evidence archive, did not upload datasets, did not call provider fine-tune APIs, did not create provider jobs, did not start model training, and did not promote models.

## Next Step

Phase 38 should fix or supply the correct deployed ops key and expected record ids, then re-run the Phase 36 wrapper. If the wrapper passes, archive the evidence and decide whether to run a separate production smoke.

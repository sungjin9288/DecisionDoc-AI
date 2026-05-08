# Phase 38 Observed Probe Retry Evidence

Status: `DEPLOYED_PROBE_RETRIED_OPS_KEY_AUTH_FAILED_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-09T02:08:06+09:00`

## Purpose

Phase 38 reran the guarded Phase 36 observed-probe workflow after hardening the wrapper to create its output directory before invoking the Phase 34 probe.

This retry was still read-only. It did not import sign-off records, create reviewer approvals, upload datasets, call provider fine-tune APIs, start provider jobs, train models, or promote models.

## Wrapper Fix Confirmed

The first retry attempt exposed a local wrapper bug: a missing `--output-dir` parent directory caused the Phase 34 probe to fail before it could write its result JSON.

The wrapper now creates `output_dir` before launching the Phase 34 probe. The second retry wrote both local runtime files under `/tmp/decisiondoc-phase38-observed-probe/`:

- `phase34-staging-readiness.json`
- `phase36-observed-probe-workflow-result.json`

## Runtime Inputs

- Base URL: `https://admin.decisiondoc.kr`
- Tenant: `system`
- Ops key source: `.github-actions.env`
- Ops key value recorded in evidence: `false`
- Expected sign-off record ids: `dsr_phase32done`, `dsr_phase32pending`

## Observed Checkpoints

| Check | Result |
|---|---|
| `GET /health` | `200` |
| reviewer sign-off summary without ops key | `401` |
| reviewer sign-off summary with `.github-actions.env` ops key | `401` |
| reviewer sign-off JSON download with `.github-actions.env` ops key | `401` |
| expected record ids visible | `false` |
| passing Phase 35 archive written | `false` |

## Inferred Blocker

The deployed app is reachable and the ops-key protected endpoints are enforcing authentication. The current blocker is that the local `.github-actions.env` `DECISIONDOC_OPS_KEY` does not authenticate against the deployed server, or the deployed runtime secret is missing/different.

Because summary/download both returned `401`, the probe cannot yet prove that deployed imported sign-off records are visible. The missing expected ids are therefore downstream of the authentication blocker.

## Boundary Statement

This retry did not start model training, upload datasets, call provider fine-tune APIs, create provider jobs, poll provider jobs, promote models, generate approvals, or write server-side export artifacts.

## Next Step

Rotate or copy the current deployed `DECISIONDOC_OPS_KEY` into the probe environment without printing it, ensure imported sign-off records exist for `dsr_phase32done` and `dsr_phase32pending` or provide the actual deployed ids, then rerun the Phase 36 wrapper.

# Phase 39 Remote Runtime Gap Evidence

Status: `REMOTE_RUNTIME_GAP_IDENTIFIED_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-09T02:51:54+09:00`

## Purpose

Phase 39 narrowed the deployed probe blocker after Phase 38 showed `401` with the local `.github-actions.env` ops key.

The current deployed `/opt/decisiondoc/.env.prod` ops key was read through SSH and used only in memory for a read-only probe. The key value was not printed, written into repo files, or stored in evidence.

## Findings

- `admin.decisiondoc.kr` resolves to `13.209.238.126`.
- SSH access to the production host works with the existing production key.
- Remote host: `ip-10-20-3-177`
- Remote checkout path: `/opt/decisiondoc`
- Remote commit: `011aec5`
- Remote branch state: detached `HEAD`
- Remote `system` tenant sign-off directory: missing
- Remote code search for `reviewer-signoff/summary` under `app/` and `tests/`: `0` files

## Ops Key Result

- Remote `/opt/decisiondoc/.env.prod` has `DECISIONDOC_OPS_KEY`.
- Local `.github-actions.env` ops key does not match the deployed ops key.
- Using the deployed ops key in memory changed the protected endpoint response from `401` to `404`.
- Inference: the deployed ops key is valid, but the DocumentOps reviewer sign-off routes are not present in the currently running deployed code.

## Observed Checkpoints

| Check | Result |
|---|---|
| `GET /health` | `200` |
| reviewer sign-off summary without ops key | `401` |
| reviewer sign-off summary with deployed ops key | `404` |
| reviewer sign-off JSON download with deployed ops key | `404` |
| safe response body | `{"detail": "Not Found"}` |
| expected sign-off record ids visible | `false` |
| passing Phase 35 archive written | `false` |

## Current Blocker

The blocker is no longer just ops-key mismatch. The runtime gap is:

1. The production deployment does not include the current local DocumentOps reviewer sign-off routes.
2. The target tenant sign-off storage directory is not present on the production host.
3. Expected sign-off record ids cannot be verified until the route exists and records are imported.

## Boundary Statement

This phase did not deploy code, import records, create reviewer approvals, upload datasets, call provider fine-tune APIs, start provider jobs, train models, promote models, or write server-side export artifacts.

## Next Step

Prepare a deployable commit/release containing the current DocumentOps route, service, store, UI, and evidence changes. After deploying it to `admin.decisiondoc.kr`, import the intended reviewer sign-off records into the production tenant-local sign-off directory and rerun the Phase 36 wrapper with the deployed ops key and actual record ids.

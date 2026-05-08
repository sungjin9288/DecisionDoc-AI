# Phase 18 Local Browser QA Checklist and Evidence

## Scope

This artifact covers the full no-training DocumentOps governance flow from local browser setup through provider execution rehearsal.

It does not authorize model training, dataset upload, provider fine-tune API calls, provider job creation, or model promotion.

## No-Training Boundary

Required invariant for every browser/API observation:

- `training_execution_allowed=false`
- `provider_api_calls_allowed=false`
- `external_upload_allowed=false`
- `provider_job_started=false`
- `model_promotion_allowed=false`

The provider execution rehearsal is a dry run only. Any step named like provider dataset preparation, fine-tune job creation, training polling, evaluation collection, or model candidate emission must remain skipped or not-started and must report `side_effect=false`.

## Local Browser Setup

Use a temporary data directory and mock provider so the browser run is repeatable and has no external provider dependency.

```bash
export DATA_DIR="$(mktemp -d)"
export DECISIONDOC_PROVIDER=mock
export DECISIONDOC_API_KEY=phase18-local-api-key
export DECISIONDOC_OPS_KEY=phase18-local-ops-key
export DECISIONDOC_ENV=dev
export DECISIONDOC_TEMPLATE_VERSION=v1
export JWT_SECRET_KEY=test-secret-key-for-phase18-local-browser-32chars
python -m uvicorn app.main:app --host 127.0.0.1 --port 8767
```

Open:

```text
http://127.0.0.1:8767/?ops=1
```

Browser headers/actions must use:

- API key: `phase18-local-api-key`
- Ops key: `phase18-local-ops-key`
- Tenant: `system` unless a different local tenant is intentionally under test

## Browser Checklist

### 1. Open DocumentOps Surface

- Open the local URL with `?ops=1`.
- Confirm the DocumentOps controls render.
- Confirm the governance action buttons are visible:
  - `Reviewed JSONL`
  - `Readiness`
  - `Plan preview`
  - `Request record`
  - `Audit checklist`
  - `Export audit`
  - `Governance`
  - `Adapter`
  - `Rehearsal`

Evidence to capture:

- URL
- visible action list
- absence of any button or prompt that starts provider training

### 2. Create One Reviewed Trajectory

- Run a synthetic DocumentOps task with `capture_trajectory=true`.
- Use non-sensitive content only.
- Review the trajectory as accepted with a quality score above the export gate.

Expected evidence:

- trajectory id exists
- `human_review_status=accepted`
- QA hard gate passes
- no provider training fields are present

### 3. Preview and Export Reviewed SFT JSONL

- Run `Export preview`.
- Confirm `dry_run=true`, `would_export=true`, and `eligible_count>=1`.
- Run `SFT export`.
- Run `Reviewed JSONL`.
- Download the reviewed artifact.

Expected evidence:

- reviewed-only list reports `reviewed_only=true`
- artifact filename ends with `.jsonl`
- download content type starts with `application/x-ndjson`
- JSONL content has `system`, `user`, and `assistant` messages

### 4. Quality Report and Dataset Freeze

- Open the export quality report for the generated JSONL artifact.
- Freeze the reviewed export with a dataset owner reviewer.
- Confirm freeze listing shows the new manifest.

Expected evidence:

- quality report has `schema_invalid_count=0`
- quality report has `ready_for_training=true` as dataset quality only, not execution permission
- freeze manifest has `training_allowed=false`
- freeze manifest includes export and quality-report SHA-256 values

### 5. Dry-Run Training Approval

- Create training approval from the freeze with a different approver.
- Keep `dry_run=true`.
- Do not set `start_training=true`.

Expected evidence:

- approval record exists
- requester/reviewer separation is enforced
- `provider_job_started=false`
- `training_execution_allowed=false`

### 6. Readiness and Plan Preview

- Run `Readiness`.
- Run `Plan preview`.

Expected evidence:

- readiness summary combines reviewed export, freeze, approval, eval plan, and quality status
- plan preview is `dry_run=true`, `preview_only=true`, and `read_only=true`
- plan preview references only dataset metadata and hashes, not raw JSONL body
- all future execution steps are not started

### 7. Two-Person Request Record

- Run `Request record` using a requester distinct from the prior dry-run approver.
- Leave upload, provider API, and start-training flags disabled.

Expected evidence:

- request record exists
- `two_person_guard_satisfied=true`
- `external_upload_started=false`
- `provider_job_started=false`
- `model_promotion_allowed=false`

### 8. Final Audit Checklist and Export

- Run `Audit checklist`.
- Run `Export audit` with an auditor distinct from the requester and prior approver.
- Download the audit artifact.

Expected evidence:

- checklist status is `ready_for_human_pre_execution_review`
- audit export contains the human-review packet
- audit export references metadata and hashes only
- no raw JSONL dataset body is embedded in the audit artifact

### 9. Governance Dashboard

- Run `Governance`.

Expected evidence:

- status is `governance_ready_for_human_review`
- counts show one reviewed export, freeze, approval, request, and audit export after a single-path run
- guard counters for training execution, provider API calls, upload, provider jobs, and model promotion remain zero

### 10. Adapter Contract and Rehearsal

- Run `Adapter`.
- Run `Rehearsal`.

Expected evidence:

- adapter status is `stub_only`
- adapter config is disabled by default
- rehearsal status is `rehearsal_ready`
- rehearsal validates governance summary, adapter contract, and dataset/audit references
- all rehearsal steps report `side_effect=false`
- provider dataset preparation and provider fine-tune job creation remain skipped dry-run steps

## API Checkpoints

These endpoints are expected to be ops-key protected unless otherwise noted:

```text
POST /api/agent/document-ops/run
POST /api/agent/document-ops/trajectories/{trajectory_id}/review
POST /api/agent/document-ops/trajectories/export/preview
POST /api/agent/document-ops/trajectories/export/quality-report
GET  /api/agent/document-ops/trajectories/reviewed-sft-exports
GET  /api/agent/document-ops/trajectories/reviewed-sft-exports/{filename}/download
GET  /api/agent/document-ops/trajectories/exports/{filename}/quality-report
POST /api/agent/document-ops/trajectories/exports/{filename}/freeze
GET  /api/agent/document-ops/trajectories/freezes
POST /api/agent/document-ops/trajectories/freezes/{manifest_id}/training-approval
GET  /api/agent/document-ops/trajectories/training-readiness
GET  /api/agent/document-ops/trajectories/training-plan/preview
POST /api/agent/document-ops/trajectories/training-execution-requests
GET  /api/agent/document-ops/trajectories/training-audit/checklist
POST /api/agent/document-ops/trajectories/training-audit/export
GET  /api/agent/document-ops/trajectories/training-governance/summary
GET  /api/agent/document-ops/trajectories/training-provider-adapter/contract
GET  /api/agent/document-ops/trajectories/training-provider-adapter/rehearsal
```

## Current Automated Evidence

Phase 18 adds this checklist and evidence artifact only. It does not run a model training job.

Automated checks to keep attached to this artifact:

```text
python -m py_compile app/services/document_ops_training_adapter.py app/services/document_ops_service.py app/routers/document_ops_agent.py tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py
pytest tests/storage/test_trajectory_store.py tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_phase18_browser_qa_evidence_artifact_documents_no_training_flow
perl -0ne 'while (m{<script>(.*?)</script>}sg) { print $1 }' app/static/index.html > /tmp/decisiondoc-index-scripts.js && node --check /tmp/decisiondoc-index-scripts.js
git diff --check
```

Expected result:

- Python compile: pass
- Phase 18 artifact test: pass
- Existing no-training governance API tests: pass
- Static browser script check: pass
- Whitespace diff check: pass

## Evidence Capture Template

Use this section when performing the manual local browser run.

```text
Run date:
Tester:
Commit or branch:
DATA_DIR:
URL:
Provider:
Tenant:

Trajectory id:
Reviewed JSONL filename:
Freeze manifest id:
Dry-run approval id:
Training execution request id:
Audit export filename:
Governance status:
Adapter status:
Rehearsal status:

No-training invariant:
- training_execution_allowed=false:
- provider_api_calls_allowed=false:
- external_upload_allowed=false:
- provider_job_started=false:
- model_promotion_allowed=false:
- all rehearsal side_effect=false:

Notes:
```

## Blockers

Treat any of the following as a blocker:

- provider upload or provider fine-tune job starts
- a governance response sets any no-training invariant to true
- rehearsal reports `side_effect=true`
- raw JSONL dataset content appears in readiness, plan preview, request records, governance summary, adapter contract, or rehearsal output
- same-person approval is accepted where separation of duties is required
- reviewed JSONL download is available without the ops key

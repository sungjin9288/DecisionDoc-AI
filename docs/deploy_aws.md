# Deploy to AWS (Manual)

This runbook covers manual deployment with GitHub Actions `workflow_dispatch`.

## Prerequisites

- AWS account and target region
- S3 bucket per stage for DecisionDoc artifacts
- IAM role per stage that GitHub OIDC can assume
- GitHub repository secrets configured:
  - `AWS_REGION`
  - `AWS_ROLE_ARN_DEV`, `AWS_ROLE_ARN_PROD`
  - `DECISIONDOC_S3_BUCKET_DEV`, `DECISIONDOC_S3_BUCKET_PROD`
  - `DECISIONDOC_API_KEY`

## Deploy via GitHub Actions

1. Open `Actions -> deploy`.
2. Click `Run workflow`.
3. Select:
   - `stage`: `dev` or `prod`
   - `template_version`: default `v1`
4. Run.

The workflow builds and deploys SAM template `infra/sam/template.yaml`.

## Deploy + Smoke Workflow

`deploy-smoke` workflow is `workflow_dispatch` only and runs:

1. Deploy (`infra/sam/template.yaml`)
2. Post-deploy smoke checks (`scripts/smoke.py`)

Smoke validates:
- `GET /health` returns `200`
- `POST /generate` without key returns `401 UNAUTHORIZED`
- `POST /generate` with key returns `200` with `bundle_id`
- `POST /generate/export` with key returns `200` with export metadata

## Runtime Storage Configuration

Deployment template sets:

- `DECISIONDOC_STORAGE=s3`
- `DECISIONDOC_S3_BUCKET=<stage bucket>`
- `DECISIONDOC_S3_PREFIX=decisiondoc-ai/`
- `DECISIONDOC_ENV=<stage>`
- `DECISIONDOC_API_KEY=<GitHub secret>`
- `DECISIONDOC_MAINTENANCE=<0|1>`

Notes:
- `prod` stage disables `/docs`, `/redoc`, and `/openapi.json` by design.
- For key rotation, you can migrate to `DECISIONDOC_API_KEYS` (comma-separated) while keeping legacy `DECISIONDOC_API_KEY` support.

Cost safety rails are set in SAM parameters:
- HTTP API throttling (`ThrottlingBurstLimit`, `ThrottlingRateLimit`)
- Lambda reserved concurrency (`ReservedConcurrentExecutions`)

No API keys or secrets are stored in source files.

## Post-deploy checks

1. Call `/health` and confirm status is `ok`.
2. Call `/generate` with mock provider payload.
3. Verify S3 objects are created under:
   - `decisiondoc-ai/bundles/<bundle_id>.json`
   - `decisiondoc-ai/exports/<bundle_id>/<doc_type>.md` (if `/generate/export` used)

## Kill Switch (Maintenance Mode)

Use maintenance mode when you need to immediately block write traffic:

1. Run `deploy` (or `deploy-smoke`) with `maintenance_mode=1`.
2. Expected behavior:
   - `POST /generate` -> `503 MAINTENANCE_MODE`
   - `POST /generate/export` -> `503 MAINTENANCE_MODE`
   - `GET /health` stays `200`
3. To resume service, redeploy with `maintenance_mode=0`.

## Incident Runbook

### Cost spike / abuse response

1. Enable maintenance mode (`maintenance_mode=1`) and redeploy.
2. Rotate API keys (`DECISIONDOC_API_KEYS` preferred; keep temporary overlap).
3. Lower safety rails:
   - HTTP API throttling (`ApiThrottlingBurstLimit`, `ApiThrottlingRateLimit`)
   - Lambda reserved concurrency (`LambdaReservedConcurrentExecutions`)
4. Re-run smoke checks before reopening traffic.

### Key rotation (summary)

1. Deploy with both old and new keys in `DECISIONDOC_API_KEYS`.
2. Move clients to the new key.
3. Redeploy removing the old key.

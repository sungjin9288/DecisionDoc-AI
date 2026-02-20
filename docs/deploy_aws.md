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

## Runtime Storage Configuration

Deployment template sets:

- `DECISIONDOC_STORAGE=s3`
- `DECISIONDOC_S3_BUCKET=<stage bucket>`
- `DECISIONDOC_S3_PREFIX=decisiondoc-ai/`
- `DECISIONDOC_ENV=<stage>`
- `DECISIONDOC_API_KEY=<GitHub secret>`

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

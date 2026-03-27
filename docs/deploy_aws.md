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
  - `DECISIONDOC_OPS_KEY`
  - optional: `STATUSPAGE_PAGE_ID`, `STATUSPAGE_API_KEY` (for automated Investigating posts)
- Optional for Voice Brief import:
  - `VOICE_BRIEF_API_BASE_URL_DEV`, `VOICE_BRIEF_API_BASE_URL_PROD`
  - `VOICE_BRIEF_API_BEARER_TOKEN_DEV`, `VOICE_BRIEF_API_BEARER_TOKEN_PROD`
- Optional for procurement opportunity import by bid number:
  - `G2B_API_KEY_DEV`, `G2B_API_KEY_PROD`
- Optional GitHub repository/environment variables:
  - `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_DEV`, `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_PROD`
  - `VOICE_BRIEF_TIMEOUT_SECONDS_DEV`, `VOICE_BRIEF_TIMEOUT_SECONDS_PROD`
  - `VOICE_BRIEF_SMOKE_RECORDING_ID_DEV`, `VOICE_BRIEF_SMOKE_RECORDING_ID_PROD`
  - `VOICE_BRIEF_SMOKE_REVISION_ID_DEV`, `VOICE_BRIEF_SMOKE_REVISION_ID_PROD`
  - `VOICE_BRIEF_SMOKE_TENANT_ID_DEV`, `VOICE_BRIEF_SMOKE_TENANT_ID_PROD`
- Optional GitHub repository secrets for smoke auth on non-empty tenants:
  - `VOICE_BRIEF_SMOKE_USERNAME_DEV`, `VOICE_BRIEF_SMOKE_USERNAME_PROD`
  - `VOICE_BRIEF_SMOKE_PASSWORD_DEV`, `VOICE_BRIEF_SMOKE_PASSWORD_PROD`

## GitHub Actions Configuration Checklist

이 섹션은 `deploy` 와 `deploy-smoke` 를 실제로 실행하기 전에 GitHub repository/environment에 어떤 값을 넣어야 하는지 바로 확인할 수 있는 체크리스트입니다.

### 1. 공통 Repository Secrets

아래 값은 stage와 무관하게 공통으로 사용됩니다.

| 타입 | 이름 | 필수 여부 | 설명 |
|------|------|-----------|------|
| Secret | `AWS_REGION` | 필수 | 예: `ap-northeast-2` |
| Secret | `DECISIONDOC_API_KEY` | 필수 | 앱 smoke와 runtime auth에 사용 |
| Secret | `DECISIONDOC_OPS_KEY` | 필수 | ops smoke와 `/ops/*` 보호에 사용 |
| Secret | `STATUSPAGE_PAGE_ID` | 선택 | ops investigate notify 경로 |
| Secret | `STATUSPAGE_API_KEY` | 선택 | Statuspage API 인증 |

### 2. Stage별 Repository Secrets

아래 값은 `dev` 와 `prod` 를 구분해서 각각 넣어야 합니다.

| 타입 | 이름 | dev 최초 deploy | Voice Brief smoke | 설명 |
|------|------|-----------------|-------------------|------|
| Secret | `AWS_ROLE_ARN_DEV` / `AWS_ROLE_ARN_PROD` | 필수 | 필수 | GitHub OIDC가 assume할 IAM role |
| Secret | `DECISIONDOC_S3_BUCKET_DEV` / `DECISIONDOC_S3_BUCKET_PROD` | 필수 | 필수 | bundle/export/report 저장 버킷 |
| Secret | `G2B_API_KEY_DEV` / `G2B_API_KEY_PROD` | 선택 | 선택 | 공고번호 기반 import에 필요, URL import만 쓸 경우 생략 가능 |
| Secret | `VOICE_BRIEF_API_BASE_URL_DEV` / `VOICE_BRIEF_API_BASE_URL_PROD` | 선택 | 필수 | 비어 있으면 Voice Brief import 비활성 |
| Secret | `VOICE_BRIEF_API_BEARER_TOKEN_DEV` / `VOICE_BRIEF_API_BEARER_TOKEN_PROD` | 선택 | upstream 요구 시 필수 | Voice Brief upstream bearer token |
| Secret | `VOICE_BRIEF_SMOKE_USERNAME_DEV` / `VOICE_BRIEF_SMOKE_USERNAME_PROD` | 선택 | non-empty tenant면 필수 | 기존 사용자 로그인 방식 smoke용 |
| Secret | `VOICE_BRIEF_SMOKE_PASSWORD_DEV` / `VOICE_BRIEF_SMOKE_PASSWORD_PROD` | 선택 | non-empty tenant면 필수 | 기존 사용자 로그인 방식 smoke용 |

### 3. Stage별 Repository Variables

아래 값은 GitHub Variables로 넣는 것이 현재 workflow와 맞습니다.

| 타입 | 이름 | dev 최초 deploy | Voice Brief smoke | 설명 |
|------|------|-----------------|-------------------|------|
| Variable | `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_DEV` / `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_PROD` | 필수 | 선택 | `1`이면 project detail procurement UI/API 활성화, 비어 있으면 기본 `0` |
| Variable | `VOICE_BRIEF_TIMEOUT_SECONDS_DEV` / `VOICE_BRIEF_TIMEOUT_SECONDS_PROD` | 선택 | 선택 | 비어 있으면 기본값 `10.0` 사용 |
| Variable | `VOICE_BRIEF_SMOKE_RECORDING_ID_DEV` / `VOICE_BRIEF_SMOKE_RECORDING_ID_PROD` | 선택 | 필수 | happy-path import smoke 대상 recording |
| Variable | `VOICE_BRIEF_SMOKE_REVISION_ID_DEV` / `VOICE_BRIEF_SMOKE_REVISION_ID_PROD` | 선택 | 선택 | 특정 revision 고정 시 사용 |
| Variable | `VOICE_BRIEF_SMOKE_TENANT_ID_DEV` / `VOICE_BRIEF_SMOKE_TENANT_ID_PROD` | 선택 | 선택 | 멀티테넌트 환경에서 대상 tenant 지정 |

### 4. 최초 dev 배포에 필요한 최소 세트

Voice Brief smoke까지 포함해서 `dev` 환경을 처음 올릴 때 필요한 최소 세트는 아래입니다.

#### 필수 Secrets

- `AWS_REGION`
- `AWS_ROLE_ARN_DEV`
- `DECISIONDOC_S3_BUCKET_DEV`
- `DECISIONDOC_API_KEY`
- `DECISIONDOC_OPS_KEY`
- `VOICE_BRIEF_API_BASE_URL_DEV`
- 필요 시 `VOICE_BRIEF_API_BEARER_TOKEN_DEV`

#### 필수 Variables

- `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_DEV`
- `VOICE_BRIEF_SMOKE_RECORDING_ID_DEV`
- 선택: `VOICE_BRIEF_TIMEOUT_SECONDS_DEV`
- 선택: `VOICE_BRIEF_SMOKE_REVISION_ID_DEV`
- 선택: `VOICE_BRIEF_SMOKE_TENANT_ID_DEV`

#### non-empty tenant 추가 Secrets

- `VOICE_BRIEF_SMOKE_USERNAME_DEV`
- `VOICE_BRIEF_SMOKE_PASSWORD_DEV`

#### 선택 Secrets

- `STATUSPAGE_PAGE_ID`
- `STATUSPAGE_API_KEY`

tenant가 비어 있으면 `scripts/voice_brief_smoke.py` 가 `POST /auth/register` 로 smoke 사용자를 직접 생성하려고 시도합니다. tenant에 이미 사용자가 있으면 위 username/password를 반드시 넣어야 합니다.

### 5. 첫 deploy-smoke 실행 순서

로컬에서 값을 채우고 검증할 때는 아래 helper를 사용할 수 있습니다.

```bash
cp scripts/github-actions.env.example .github-actions.env
bash scripts/import-github-actions-env-file.sh \
  --stage dev \
  --source .env

vi .github-actions.env

bash scripts/check-github-actions-config.sh \
  --stage dev \
  --env-file .github-actions.env \
  --voice-brief \
  --voice-brief-smoke
```

GitHub에 실제 반영할 때는 `gh` CLI가 로그인된 상태에서 아래처럼 적용할 수 있습니다.

```bash
bash scripts/apply-github-actions-config.sh \
  --stage dev \
  --env-file .github-actions.env \
  --voice-brief \
  --voice-brief-smoke
```

tenant에 기존 사용자가 이미 있으면 `--non-empty-tenant` 옵션을 추가합니다. 현재 `deploy` / `deploy-smoke` workflow는 GitHub `environment` scope가 아니라 repo-level `secrets.*` / `vars.*` 를 읽으므로, helper도 기본적으로 repo scope로 적용하는 것이 맞습니다.

`import-github-actions-env-file.sh` 는 로컬 `.env` 또는 지정한 source file에서 재사용 가능한 값만 stage 형식으로 옮깁니다. 현재 source에 없는 값은 빈 칸으로 남겨 두므로, import 이후 `check-github-actions-config.sh` 로 부족한 항목만 확인하면 됩니다.

`DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_<STAGE>` 는 helper가 기본적으로 요구합니다. `0` 또는 `1` 중 하나를 명시적으로 넣어야 stage별 rollout 의도가 문서화됩니다.

주의:
`VOICE_BRIEF_API_BASE_URL_<STAGE>` 에 `http://127.0.0.1:4000`, `http://localhost:4000` 같은 loopback URL을 넣으면 GitHub-hosted runner에서 upstream에 접근할 수 없습니다. helper는 이런 값의 자동 import를 건너뛰고, `check-github-actions-config.sh` 도 이를 invalid로 거부합니다.

1. 공통 Secrets 5개를 먼저 설정합니다.
2. `dev` stage용 `AWS_ROLE_ARN_DEV`, `DECISIONDOC_S3_BUCKET_DEV` 를 설정합니다.
3. Voice Brief import를 검증할 예정이면 `VOICE_BRIEF_API_BASE_URL_DEV` 와 `VOICE_BRIEF_SMOKE_RECORDING_ID_DEV` 를 설정합니다.
4. tenant가 비어 있지 않으면 `VOICE_BRIEF_SMOKE_USERNAME_DEV`, `VOICE_BRIEF_SMOKE_PASSWORD_DEV` 를 추가합니다.
5. `Actions -> deploy-smoke -> Run workflow` 에서 아래 입력으로 실행합니다.

권장 첫 실행값:

| 입력 | 값 |
|------|----|
| `stage` | `dev` |
| `provider` | `mock` |
| `template_version` | `v1` |
| `maintenance_mode` | `0` |
| `include_ops_smoke` | `false` |
| `include_voice_brief_smoke` | `true` |

`dev` stage는 `include_ops_smoke=false` 여도 ops smoke가 기본 실행됩니다. 이 입력은 주로 `prod` stage에서만 의미가 있습니다.

### 6. 실패 시 우선 확인할 항목

| 증상 | 먼저 확인할 값 |
|------|----------------|
| workflow 초반에 role assume 실패 | `AWS_REGION`, `AWS_ROLE_ARN_<STAGE>` |
| SAM deploy 중 bucket 관련 실패 | `DECISIONDOC_S3_BUCKET_<STAGE>` |
| app smoke에서 401 또는 5xx | `DECISIONDOC_API_KEY`, stack output URL, app runtime env |
| ops smoke 실패 | `DECISIONDOC_OPS_KEY`, `STATUSPAGE_*`, S3 접근 권한 |
| Voice Brief smoke가 disabled/configured 에서 멈춤 | `VOICE_BRIEF_API_BASE_URL_<STAGE>`, `VOICE_BRIEF_SMOKE_RECORDING_ID_<STAGE>` |
| Voice Brief smoke가 login 단계에서 실패 | `VOICE_BRIEF_SMOKE_USERNAME_<STAGE>`, `VOICE_BRIEF_SMOKE_PASSWORD_<STAGE>`, `VOICE_BRIEF_SMOKE_TENANT_ID_<STAGE>` |

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
3. Optional Voice Brief import smoke (`scripts/voice_brief_smoke.py`)
4. Ops smoke on `dev` by default (`scripts/ops_smoke.py`)
   - `prod` runs ops smoke only when workflow input `include_ops_smoke=true`

Smoke validates:
- `GET /health` returns `200`
- `GET /version` exposes `features.procurement_copilot`
- `POST /generate` without key returns `401 UNAUTHORIZED`
- `POST /generate` with key returns `200` with `bundle_id`
- `POST /generate/export` with key returns `200` with export metadata
- optional procurement smoke via `scripts/smoke.py`:
  - set `SMOKE_INCLUDE_PROCUREMENT=1`
  - set `SMOKE_PROCUREMENT_URL_OR_NUMBER=<known url or bid number>`
  - creates a project
  - calls `POST /projects/{project_id}/imports/g2b-opportunity`
  - calls `POST /projects/{project_id}/procurement/evaluate`
  - calls `POST /projects/{project_id}/procurement/recommend`
  - calls `POST /generate/stream` with `bundle_type=bid_decision_kr`
  - verifies the generated decision document is auto-linked back into project documents
- optional Voice Brief smoke:
  - creates or logs in a smoke user
  - creates a project
  - calls `POST /projects/{project_id}/imports/voice-brief`
  - verifies imported project metadata is stored
- `POST /ops/investigate` with `notify=false` returns `200` and stores report to S3
- immediate second `/ops/investigate` call returns `deduped=true`

## Runtime Storage Configuration

Deployment template sets:

- `DECISIONDOC_STORAGE=s3`
- `DECISIONDOC_S3_BUCKET=<stage bucket>`
- `DECISIONDOC_S3_PREFIX=decisiondoc-ai/`
- `DECISIONDOC_ENV=<stage>`
- `DECISIONDOC_API_KEY=<GitHub secret>`
- `DECISIONDOC_OPS_KEY=<GitHub secret>`
- `DECISIONDOC_MAINTENANCE=<0|1>`
- `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=<GitHub variable or 0 default>`
- `STATUSPAGE_PAGE_ID=<GitHub secret or empty>`
- `STATUSPAGE_API_KEY=<GitHub secret or empty>`
- `G2B_API_KEY=<GitHub secret or empty>`
- `VOICE_BRIEF_API_BASE_URL=<GitHub secret or empty>`
- `VOICE_BRIEF_API_BEARER_TOKEN=<GitHub secret or empty>`
- `VOICE_BRIEF_TIMEOUT_SECONDS=<GitHub variable or 10.0 default>`

Notes:
- `prod` stage disables `/docs`, `/redoc`, and `/openapi.json` by design.
- Procurement copilot rollout is controlled only by `/version.features.procurement_copilot`, which is backed by `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`.
- If `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=0`, project procurement routes return `403 FEATURE_DISABLED`, `bid_decision_kr` generation is blocked, and the project-detail procurement panel stays hidden.
- Statuspage integration is optional for deploy and smoke. If `STATUSPAGE_PAGE_ID` / `STATUSPAGE_API_KEY` are empty, `/ops/investigate` still works with `notify=false`, but automated incident posting is skipped.
- `G2B_API_KEY` is optional, but bid-number import without a full URL depends on it. URL import continues to work without the key when scraping succeeds.
- Voice Brief integration remains optional. If `VOICE_BRIEF_API_BASE_URL` is empty, the project import UI stays visible but import calls return `voice_brief_not_configured`.
- For key rotation, you can migrate to `DECISIONDOC_API_KEYS` (comma-separated) while keeping legacy `DECISIONDOC_API_KEY` support.
- Investigation reports are written to S3 under `reports/incidents/<incident_key>/<run_id>/`.
- Investigation dedupe uses deterministic `incident_key` + time bucket:
  - `DECISIONDOC_INVESTIGATE_DEDUP_TTL_SECONDS` (default `300`)
  - `DECISIONDOC_INVESTIGATE_BUCKET_SECONDS` (default `300`)
  - Use request body `force=true` to bypass dedupe and run a fresh collection.
- Statuspage duplicate prevention and spam control:
  - same `incident_key` reuses existing incident id
  - deduped requests only post update when min interval passes:
    `DECISIONDOC_INVESTIGATE_STATUSPAGE_UPDATE_MIN_SECONDS` (default `600`)
- Statuspage failure policy:
  - default soft mode (`DECISIONDOC_OPS_STATUSPAGE_STRICT=0`): investigation succeeds and evidence is stored
  - strict mode (`DECISIONDOC_OPS_STATUSPAGE_STRICT=1`): investigate request fails if notify fails
- Recommended lifecycle: expire incident report objects after N days (e.g., 30-90 days).

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
4. Run ops smoke and confirm:
   - first call has report json key and S3 object exists
   - second call is deduped (`deduped=true`)
5. If Voice Brief integration is enabled, verify one happy-path import manually:
   - open a project in the web UI
   - import a known-good `recording_id` and optional `revision_id`
   - confirm a `voice_brief_import` document appears in project detail
   - confirm blocked states map correctly (`stale_summary`, `unapproved_summary`, `voice_brief_not_found`, `voice_brief_upstream_error`)

For `deploy-smoke`, you can automate the happy-path check by setting:

- workflow input `include_voice_brief_smoke=true`
- stage variable `VOICE_BRIEF_SMOKE_RECORDING_ID_<STAGE>`
- optional `VOICE_BRIEF_SMOKE_REVISION_ID_<STAGE>`
- optional `VOICE_BRIEF_SMOKE_TENANT_ID_<STAGE>`

If the target tenant already has users, also set:

- `VOICE_BRIEF_SMOKE_USERNAME_<STAGE>`
- `VOICE_BRIEF_SMOKE_PASSWORD_<STAGE>`

If no smoke credentials are provided, the script attempts `POST /auth/register` and only succeeds on an empty tenant.

## Kill Switch (Maintenance Mode)

Use maintenance mode when you need to immediately block write traffic:

1. Run `deploy` (or `deploy-smoke`) with `maintenance_mode=1`.
2. Expected behavior:
   - `POST /generate` -> `503 MAINTENANCE_MODE`
   - `POST /generate/export` -> `503 MAINTENANCE_MODE`
   - `GET /health` stays `200`
3. To resume service, redeploy with `maintenance_mode=0`.

## User-Reported Incident Protocol (10-minute flow)

1. Start investigation immediately:
   - `POST /ops/investigate` with `window_minutes=30`
   - include `X-DecisionDoc-Ops-Key`
   - set `notify=false` for smoke/probe scenarios to avoid Statuspage spam
2. Confirm response fields:
   - `incident_id`
   - `summary` (`api_5xx`, `api_4xx`, throttles, p95 latency)
   - `statuspage_incident_url`
   - `report_s3_key`
3. Notify user with:
   - "조사 시작"
   - "현재 영향 범위 (5xx/429 여부)"
   - "다음 업데이트 시간(예: 30분 이내)"
4. If deeper analysis is needed, re-run:
   - `window_minutes=120`

## Incident Runbook

### Cost spike / abuse response

1. Enable maintenance mode (`maintenance_mode=1`) and redeploy.
2. Rotate API keys (`DECISIONDOC_API_KEYS` preferred; keep temporary overlap).
3. Lower safety rails:
   - HTTP API throttling (`ApiThrottlingBurstLimit`, `ApiThrottlingRateLimit`)
   - Lambda reserved concurrency (`LambdaReservedConcurrentExecutions`)
4. Re-run smoke checks before reopening traffic.
5. Keep Status Page incident in `investigating` until error/latency signals normalize.

### Key rotation (summary)

1. Deploy with both old and new keys in `DECISIONDOC_API_KEYS`.
2. Move clients to the new key.
3. Redeploy removing the old key.

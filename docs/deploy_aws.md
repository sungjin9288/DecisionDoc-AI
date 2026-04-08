# Deploy to AWS (Manual)

This runbook covers manual deployment with GitHub Actions `workflow_dispatch`.

Long-term environment separation, immutable release preference, and operating-model hardening guidance lives in:

- `docs/operating_model_roadmap.md`
- `docs/deployment/account_security_incident_checklist.md`

## Prerequisites

- AWS account and target region
- S3 bucket per stage for DecisionDoc artifacts
- IAM role per stage that GitHub OIDC can assume
- GitHub repository secrets configured:
  - `AWS_REGION`
  - `AWS_ROLE_ARN_DEV`, `AWS_ROLE_ARN_PROD`
  - `DECISIONDOC_S3_BUCKET_DEV`, `DECISIONDOC_S3_BUCKET_PROD`
  - `DECISIONDOC_API_KEY`
  - optional: `DECISIONDOC_API_KEYS` (comma-separated runtime overlap rotation list; if set, include `DECISIONDOC_API_KEY`)
  - `DECISIONDOC_OPS_KEY`
  - optional: `STATUSPAGE_PAGE_ID`, `STATUSPAGE_API_KEY` (for automated Investigating posts)
- Optional for Voice Brief import:
  - `VOICE_BRIEF_API_BASE_URL_DEV`, `VOICE_BRIEF_API_BASE_URL_PROD`
  - `VOICE_BRIEF_API_BEARER_TOKEN_DEV`, `VOICE_BRIEF_API_BEARER_TOKEN_PROD`
- Optional for native meeting recording transcription:
  - `OPENAI_API_KEY_DEV`, `OPENAI_API_KEY_PROD`
- Optional for procurement opportunity import by bid number:
  - `G2B_API_KEY_DEV`, `G2B_API_KEY_PROD`
- Optional GitHub repository/environment variables:
  - `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_DEV`, `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_PROD`
  - `OPENAI_API_BASE_URL_DEV`, `OPENAI_API_BASE_URL_PROD`
  - `MEETING_RECORDING_TRANSCRIPTION_MODEL_DEV`, `MEETING_RECORDING_TRANSCRIPTION_MODEL_PROD`
  - `MEETING_RECORDING_MAX_UPLOAD_BYTES_DEV`, `MEETING_RECORDING_MAX_UPLOAD_BYTES_PROD`
  - `MEETING_RECORDING_CONTEXT_CHAR_LIMIT_DEV`, `MEETING_RECORDING_CONTEXT_CHAR_LIMIT_PROD`
  - `PROCUREMENT_SMOKE_URL_OR_NUMBER_DEV`, `PROCUREMENT_SMOKE_URL_OR_NUMBER_PROD`
  - `PROCUREMENT_SMOKE_TENANT_ID_DEV`, `PROCUREMENT_SMOKE_TENANT_ID_PROD`
  - `VOICE_BRIEF_TIMEOUT_SECONDS_DEV`, `VOICE_BRIEF_TIMEOUT_SECONDS_PROD`
  - `VOICE_BRIEF_SMOKE_RECORDING_ID_DEV`, `VOICE_BRIEF_SMOKE_RECORDING_ID_PROD`
  - `VOICE_BRIEF_SMOKE_REVISION_ID_DEV`, `VOICE_BRIEF_SMOKE_REVISION_ID_PROD`
  - `VOICE_BRIEF_SMOKE_TENANT_ID_DEV`, `VOICE_BRIEF_SMOKE_TENANT_ID_PROD`
- Optional GitHub repository secrets for smoke auth on non-empty tenants:
  - `PROCUREMENT_SMOKE_USERNAME_DEV`, `PROCUREMENT_SMOKE_USERNAME_PROD`
  - `PROCUREMENT_SMOKE_PASSWORD_DEV`, `PROCUREMENT_SMOKE_PASSWORD_PROD`
  - `VOICE_BRIEF_SMOKE_USERNAME_DEV`, `VOICE_BRIEF_SMOKE_USERNAME_PROD`
  - `VOICE_BRIEF_SMOKE_PASSWORD_DEV`, `VOICE_BRIEF_SMOKE_PASSWORD_PROD`

## Deploy ownership map

배포 실패를 application regression으로 오해하지 않도록, 운영 주체를 먼저 구분한다.

| Actor | Path | Primary responsibility | Allowed move | Forbidden default |
|------|------|------------------------|--------------|-------------------|
| GitHub Actions OIDC deploy role | `deploy` / `deploy-smoke` workflow | canonical stage/prod deploy path | `sam build`, `sam deploy`, post-deploy smoke | console hotfix를 정상 release path로 대체 |
| Local admin AWS user | AWS CLI + console investigation | stack 상태 확인, rollback recovery, dry-run triage | read-only inspection, `continue-update-rollback`, permission diagnosis | 원인 미분리 상태에서 prod redeploy 반복 |
| Break-glass operator | exceptional production recovery | account/service-side restriction 해소 후 controlled rerun | 최소 범위 인프라 복구 | 신규 기능 검증을 prod에서 직접 수행 |
| Smoke user / tenant | deployed smoke auth context | procurement/ops/live lane verification | smoke login, tenant-scoped scenario execution | 운영자 일상 계정과 혼용 |

운영 원칙:

- `stage`는 first deployment target, `prod`는 promote target
- `prod` write는 IaC/workflow 또는 명시적 break-glass 절차로만 수행
- `UPDATE_ROLLBACK_FAILED` 상태에서는 rerun보다 recovery와 root-cause 분리가 먼저
- fresh-stack workaround가 필요하면 기존 stack을 덮어쓰지 말고 `deployment_suffix` 를 붙인 별도 stack/function 이름을 사용

## GitHub Actions Configuration Checklist

이 섹션은 `deploy` 와 `deploy-smoke` 를 실제로 실행하기 전에 GitHub repository/environment에 어떤 값을 넣어야 하는지 바로 확인할 수 있는 체크리스트입니다.

### 1. 공통 Repository Secrets

아래 값은 stage와 무관하게 공통으로 사용됩니다.

| 타입 | 이름 | 필수 여부 | 설명 |
|------|------|-----------|------|
| Secret | `AWS_REGION` | 필수 | 예: `ap-northeast-2` |
| Secret | `DECISIONDOC_API_KEY` | 필수 | 앱 smoke와 runtime auth에 사용 |
| Secret | `DECISIONDOC_API_KEYS` | 선택 | comma-separated runtime auth keys. 비어 있으면 workflow가 `DECISIONDOC_API_KEY` 단일 값을 runtime fallback으로 사용 |
| Secret | `DECISIONDOC_OPS_KEY` | 필수 | ops smoke와 `/ops/*` 보호에 사용 |
| Secret | `STATUSPAGE_PAGE_ID` | 선택 | ops investigate notify 경로 |
| Secret | `STATUSPAGE_API_KEY` | 선택 | Statuspage API 인증 |

### 2. Stage별 Repository Secrets

아래 값은 `dev` 와 `prod` 를 구분해서 각각 넣어야 합니다.

| 타입 | 이름 | dev 최초 deploy | Voice Brief smoke | 설명 |
|------|------|-----------------|-------------------|------|
| Secret | `AWS_ROLE_ARN_DEV` / `AWS_ROLE_ARN_PROD` | 필수 | 필수 | GitHub OIDC가 assume할 IAM role |
| Secret | `DECISIONDOC_S3_BUCKET_DEV` / `DECISIONDOC_S3_BUCKET_PROD` | 필수 | 필수 | bundle/export/report 저장 버킷 |
| Secret | `OPENAI_API_KEY_DEV` / `OPENAI_API_KEY_PROD` | 선택 | 선택 | native meeting recording transcription runtime key. 비어 있으면 repo-level `OPENAI_API_KEY` secret fallback을 먼저 사용하고, 그것도 없으면 업로드는 가능하지만 전사는 `meeting_recording_transcription_not_configured` |
| Secret | `G2B_API_KEY_DEV` / `G2B_API_KEY_PROD` | 선택 | 선택 | 공고번호 기반 import에 필요, URL import만 쓸 경우 생략 가능 |
| Secret | `PROCUREMENT_SMOKE_USERNAME_DEV` / `PROCUREMENT_SMOKE_USERNAME_PROD` | 선택 | 선택 | procurement smoke가 기존 사용자가 있는 tenant에서 로그인해야 할 때 사용 |
| Secret | `PROCUREMENT_SMOKE_PASSWORD_DEV` / `PROCUREMENT_SMOKE_PASSWORD_PROD` | 선택 | 선택 | procurement smoke 로그인 비밀번호 |
| Secret | `VOICE_BRIEF_API_BASE_URL_DEV` / `VOICE_BRIEF_API_BASE_URL_PROD` | 선택 | 필수 | 비어 있으면 Voice Brief import 비활성 |
| Secret | `VOICE_BRIEF_API_BEARER_TOKEN_DEV` / `VOICE_BRIEF_API_BEARER_TOKEN_PROD` | 선택 | upstream 요구 시 필수 | Voice Brief upstream bearer token |
| Secret | `VOICE_BRIEF_SMOKE_USERNAME_DEV` / `VOICE_BRIEF_SMOKE_USERNAME_PROD` | 선택 | non-empty tenant면 필수 | 기존 사용자 로그인 방식 smoke용 |
| Secret | `VOICE_BRIEF_SMOKE_PASSWORD_DEV` / `VOICE_BRIEF_SMOKE_PASSWORD_PROD` | 선택 | non-empty tenant면 필수 | 기존 사용자 로그인 방식 smoke용 |

### 3. Stage별 Repository Variables

아래 값은 GitHub Variables로 넣는 것이 현재 workflow와 맞습니다.

| 타입 | 이름 | dev 최초 deploy | Voice Brief smoke | 설명 |
|------|------|-----------------|-------------------|------|
| Variable | `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_DEV` / `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_PROD` | 필수 | 선택 | `1`이면 project detail procurement UI/API 활성화, 비어 있으면 기본 `0` |
| Variable | `OPENAI_API_BASE_URL_DEV` / `OPENAI_API_BASE_URL_PROD` | 선택 | 선택 | OpenAI-compatible transcription endpoint override. 비어 있으면 `https://api.openai.com/v1` 사용 |
| Variable | `MEETING_RECORDING_TRANSCRIPTION_MODEL_DEV` / `MEETING_RECORDING_TRANSCRIPTION_MODEL_PROD` | 선택 | 선택 | 기본값 `gpt-4o-mini-transcribe` |
| Variable | `MEETING_RECORDING_MAX_UPLOAD_BYTES_DEV` / `MEETING_RECORDING_MAX_UPLOAD_BYTES_PROD` | 선택 | 선택 | 기본값 `26214400` (25MB) |
| Variable | `MEETING_RECORDING_CONTEXT_CHAR_LIMIT_DEV` / `MEETING_RECORDING_CONTEXT_CHAR_LIMIT_PROD` | 선택 | 선택 | 회의록/보고서 생성 prompt에 주입할 transcript 최대 길이 |
| Variable | `PROCUREMENT_SMOKE_URL_OR_NUMBER_DEV` / `PROCUREMENT_SMOKE_URL_OR_NUMBER_PROD` | 선택 | 선택 | known 공고 URL 또는 공고번호 1건. 없으면 smoke가 최근 live G2B 결과를 자동 탐색 |
| Variable | `PROCUREMENT_SMOKE_TENANT_ID_DEV` / `PROCUREMENT_SMOKE_TENANT_ID_PROD` | 선택 | 선택 | procurement smoke 대상 tenant가 `system` 이 아닐 때 사용 |
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
- `OPENAI_API_KEY_DEV`

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
  --procurement-smoke \
  --voice-brief \
  --voice-brief-smoke
```

Security note:

- `.github-actions.env` is a local-only secret file and must remain untracked.
- Do not store raw AWS IAM access keys in `.github-actions.env`; GitHub Actions deploy paths in this repo use OIDC `role-to-assume`, not static AWS credentials.
- For local AWS CLI work, prefer a named profile in `~/.aws/credentials` or temporary session credentials rather than copying long-lived keys into repo-adjacent files.
- If AWS Support opens a suspicious-activity case or Lambda APIs start failing with account-wide `AccessDeniedException`, follow `docs/deployment/account_security_incident_checklist.md` before retrying deploy workflows.

GitHub에 실제 반영할 때는 `gh` CLI가 로그인된 상태에서 아래처럼 적용할 수 있습니다.

```bash
bash scripts/apply-github-actions-config.sh \
  --stage dev \
  --env-file .github-actions.env \
  --procurement-smoke \
  --voice-brief \
  --voice-brief-smoke
```

tenant에 기존 사용자가 이미 있으면 `--non-empty-tenant` 옵션을 추가합니다. procurement smoke도 기존 사용자가 있는 tenant라면 `PROCUREMENT_SMOKE_USERNAME_<STAGE>` / `PROCUREMENT_SMOKE_PASSWORD_<STAGE>` 를 넣어 두는 편이 안전합니다. 현재 `deploy` / `deploy-smoke` workflow는 GitHub `environment` scope가 아니라 repo-level `secrets.*` / `vars.*` 를 읽으므로, helper도 기본적으로 repo scope로 적용하는 것이 맞습니다.

`import-github-actions-env-file.sh` 는 로컬 `.env` 또는 지정한 source file에서 재사용 가능한 값만 stage 형식으로 옮깁니다. 현재 source에 없는 값은 빈 칸으로 남겨 두므로, import 이후 `check-github-actions-config.sh` 로 부족한 항목만 확인하면 됩니다.

`DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_<STAGE>` 는 helper가 기본적으로 요구합니다. `0` 또는 `1` 중 하나를 명시적으로 넣어야 stage별 rollout 의도가 문서화됩니다.

주의:
`VOICE_BRIEF_API_BASE_URL_<STAGE>` 에 `http://127.0.0.1:4000`, `http://localhost:4000` 같은 loopback URL을 넣으면 GitHub-hosted runner에서 upstream에 접근할 수 없습니다. helper는 이런 값의 자동 import를 건너뛰고, `check-github-actions-config.sh` 도 이를 invalid로 거부합니다.

1. 공통 Secrets 5개를 먼저 설정합니다.
2. `dev` stage용 `AWS_ROLE_ARN_DEV`, `DECISIONDOC_S3_BUCKET_DEV` 를 설정합니다.
3. procurement smoke를 더 안정적으로 고정하려면 `PROCUREMENT_SMOKE_URL_OR_NUMBER_DEV` 를 설정합니다. 값이 없어도 `G2B_API_KEY_DEV` 만 있으면 `deploy-smoke` workflow와 local runner가 최근 live G2B 결과를 먼저 탐색합니다.
4. Voice Brief import를 검증할 예정이면 `VOICE_BRIEF_API_BASE_URL_DEV` 와 `VOICE_BRIEF_SMOKE_RECORDING_ID_DEV` 를 설정합니다.
5. native meeting recording transcription을 검증할 예정이면 `OPENAI_API_KEY_DEV` 를 넣습니다. stage-specific secret이 없더라도 repo-level `OPENAI_API_KEY` fallback이 있으면 deploy/runtime은 그대로 사용합니다.
6. tenant가 비어 있지 않으면 필요한 smoke 로그인 정보를 추가합니다.
   - procurement: `PROCUREMENT_SMOKE_USERNAME_DEV`, `PROCUREMENT_SMOKE_PASSWORD_DEV`
   - Voice Brief: `VOICE_BRIEF_SMOKE_USERNAME_DEV`, `VOICE_BRIEF_SMOKE_PASSWORD_DEV`
7. `Actions -> deploy-smoke -> Run workflow` 에서 아래 입력으로 실행합니다.

권장 첫 실행값:

| 입력 | 값 |
|------|----|
| `stage` | `dev` |
| `provider` | `mock` |
| `template_version` | `v1` |
| `maintenance_mode` | `0` |
| `include_ops_smoke` | `false` |
| `include_procurement_smoke` | `true` |
| `include_voice_brief_smoke` | `true` |
| `include_meeting_recording_smoke` | `false` (`OPENAI_API_KEY*` 가 준비된 lane이면 `true`) |
| `break_glass_reason` | 빈 값 유지 |
| `deployment_suffix` | 기본은 빈 값, fresh-stack 검증 시 `-green` 같은 suffix 사용 |

`dev` stage는 `include_ops_smoke=false` 여도 ops smoke가 기본 실행됩니다. 이 입력은 주로 `prod` stage에서만 의미가 있습니다.
`include_meeting_recording_smoke=true` 는 deployed stage에 transcription runtime이 실제로 연결돼 있을 때만 켭니다. 이 lane은 fixture wav 업로드 뒤 `transcribe -> approve -> generate-documents` 까지 수행하므로, runtime key가 비어 있으면 fail-fast 대신 application-level `meeting_recording_transcription_not_configured` 오류로 종료됩니다.

현재 `deploy-smoke` workflow는 `prod` 실행 전에 같은 `main` SHA에 대해 성공한 `dev` deploy-smoke run이 있는지 먼저 확인합니다. `deployment_suffix` 를 사용하는 경우에는 같은 suffix를 가진 `deploy-smoke [dev<suffix>]` evidence가 필요합니다. 정상 release 경로에서는 `break_glass_reason` 을 비워 두고, 정말 예외적인 운영 복구 상황에서만 이유를 명시해 override 합니다.

fresh-stack workaround 예시:

```text
stage = dev
deployment_suffix = -green
```

그러면 workflow는 아래 이름을 사용합니다.

- stack: `decisiondoc-ai-dev-green`
- function: `decisiondoc-ai-dev-green`
- run title: `deploy-smoke [dev-green] @ main`

fresh-stack preflight contract:

- `decisiondoc-ai-<stage><suffix>` stack이 아직 없으면 `deploy-smoke` 는 이를 first deploy로 간주한다.
- 이 경우 preflight는 `lambda update-function-code --dry-run` 을 건너뛰고 바로 `SAM build` / `SAM deploy` create path로 진행한다.
- 반대로 stack이 이미 존재하면 기존대로 `UpdateFunctionCode` dry-run으로 mutability를 확인한다.
- 따라서 `dev-green` 같은 새 suffix path는 "기존 Lambda update가 deny돼도 fresh create는 가능한가"를 확인하는 우회 검증 경로로 해석해야 한다.

### 6.1 Security incident escalation path

아래 조건 중 하나라도 보이면 application bug triage보다 account security incident 절차를 먼저 탄다.

- AWS Support가 `Suspicious activity in your AWS account` 케이스를 열었음
- leaked access key suffix가 명시적으로 통보됨
- local admin user와 GitHub Actions role이 모두 Lambda `CreateFunction` / `UpdateFunctionCode` 에서 `AccessDeniedException` 을 반환함
- Lambda console 수동 생성도 `UnknownError` 또는 동일한 deny로 실패함

이 경우:

1. leaked key rotation / deletion
2. suspicious-activity case reply
3. restriction lifted 확인
4. Lambda dry-run check
5. `dev-green -> dev -> prod` recovery deploy

세부 절차와 reply template은 `docs/deployment/account_security_incident_checklist.md` 를 기준으로 한다.

### 6. 실패 시 우선 확인할 항목

| 증상 | 먼저 확인할 값 |
|------|----------------|
| workflow 초반에 role assume 실패 | `AWS_REGION`, `AWS_ROLE_ARN_<STAGE>` |
| SAM deploy 중 bucket 관련 실패 | `DECISIONDOC_S3_BUCKET_<STAGE>` |
| SAM deploy 중 `AWS::Lambda::Function` update 가 `AccessDeniedException` 으로 실패 | 최신 `main` 이 stage bucket artifact path를 쓰는지 확인하고, stack 이 `UPDATE_ROLLBACK_FAILED` 면 `aws cloudformation continue-update-rollback --stack-name decisiondoc-ai-<stage> --region <region>` 이후 rerun |
| local admin `aws lambda update-function-code --dry-run` 도 같은 `AccessDeniedException` 으로 실패 | repo/workflow 문제가 아니라 AWS-side Lambda update restriction으로 분류하고, `prod deploy-smoke` 재실행을 중단 |
| app smoke에서 401 또는 5xx | `DECISIONDOC_API_KEY`, stack output URL, app runtime env |
| ops smoke 실패 | `DECISIONDOC_OPS_KEY`, `STATUSPAGE_*`, S3 접근 권한 |
| procurement smoke가 workflow precheck 단계에서 멈춤 | `G2B_API_KEY_<STAGE>` |
| procurement smoke가 import 단계에서 멈춤 | `G2B_API_KEY_<STAGE>`, 필요하면 `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` |
| procurement smoke가 `SKIP` 으로 끝남 | 검색된 recent live 공고도 모두 import 실패했는지 확인하고, 고정 fixture를 쓰는 운영이면 `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` 를 최신 값으로 갱신 |
| procurement smoke가 login 단계에서 멈춤 | `PROCUREMENT_SMOKE_USERNAME_<STAGE>`, `PROCUREMENT_SMOKE_PASSWORD_<STAGE>`, `PROCUREMENT_SMOKE_TENANT_ID_<STAGE>` |
| Voice Brief smoke가 disabled/configured 에서 멈춤 | `VOICE_BRIEF_API_BASE_URL_<STAGE>`, `VOICE_BRIEF_SMOKE_RECORDING_ID_<STAGE>` |
| Voice Brief smoke가 login 단계에서 실패 | `VOICE_BRIEF_SMOKE_USERNAME_<STAGE>`, `VOICE_BRIEF_SMOKE_PASSWORD_<STAGE>`, `VOICE_BRIEF_SMOKE_TENANT_ID_<STAGE>` |

### 6.1 Prod rerun gate

아래 중 하나라도 해당되면 `prod deploy-smoke` 를 바로 다시 실행하지 않는다.

- stack status가 `UPDATE_ROLLBACK_FAILED`
- 최근 `deploy` job이 `DecisionDocFunction` update `AccessDeniedException` 으로 종료
- local admin `aws lambda update-function-code --dry-run` 이 동일하게 실패

이 경우 절차는 아래 순서를 따른다.

1. stack recovery
2. `UPDATE_ROLLBACK_COMPLETE` 확인
3. repo/workflow 문제와 AWS-side restriction을 분리
4. restriction 해소 전에는 `prod` redeploy 중단

### 6.2 Dev-first gate for prod

`prod deploy-smoke` 는 이제 아래 조건을 기본으로 강제합니다.

- branch/ref는 반드시 `main`
- 같은 `main` SHA에 대해 성공한 `deploy-smoke [dev]` run이 이미 존재

이 gate를 통과하지 못하면 `SAM deploy` 전에 즉시 실패합니다.

예외는 하나만 허용합니다.

- `workflow_dispatch` input `break_glass_reason` 에 운영 복구 사유를 명시

이 override는 정상 release lane이 아니라 break-glass path입니다. 즉, 새 feature 검증이나 편의상 `prod`를 먼저 누르기 위한 용도로는 사용하지 않습니다.

### 6.3 Recovery and diagnosis commands

기본 recovery:

```bash
aws cloudformation continue-update-rollback \
  --stack-name decisiondoc-ai-prod \
  --region ap-northeast-2

aws cloudformation describe-stacks \
  --stack-name decisiondoc-ai-prod \
  --region ap-northeast-2 \
  --query 'Stacks[0].StackStatus' \
  --output text
```

필요 시 skipped-resource recovery:

```bash
aws cloudformation continue-update-rollback \
  --stack-name decisiondoc-ai-prod \
  --region ap-northeast-2 \
  --resources-to-skip DecisionDocFunction
```

AWS-side restriction 분리용 dry-run:

```bash
aws lambda update-function-code \
  --function-name decisiondoc-ai-prod \
  --region ap-northeast-2 \
  --s3-bucket decisiondoc-ai-prod-217139788460-apne2 \
  --s3-key sam-artifacts/prod//d2ee02e06f0045f866cc6eb4efd0ce26 \
  --dry-run
```

## Deploy via GitHub Actions

1. Open `Actions -> deploy`.
2. Click `Run workflow`.
3. Select:
   - `stage`: `dev` or `prod`
   - `template_version`: default `v1`
4. Run.

The workflow builds and deploys SAM template `infra/sam/template.yaml`.

`deploy` / `deploy-smoke` 는 이제 SAM build artifact를 stage runtime bucket(`DECISIONDOC_S3_BUCKET_<STAGE>`)의 `sam-artifacts/<stage>/` prefix로 올립니다. SAM CLI managed default source bucket path에 추가로 의존하지 않도록 맞춘 것으로, GitHub Actions post-merge deploy verification에서 artifact bucket drift를 한 단계 줄이는 목적입니다.

두 workflow 모두 optional `deployment_suffix` 입력을 지원합니다. 이 값이 비어 있지 않으면 stack/function 이름은 `decisiondoc-ai-<stage><suffix>` 로 바뀌고, 기존 stack을 덮어쓰지 않는 fresh-stack 검증 경로로 동작합니다.

`deploy-smoke` deploy job은 이제 `SAM build` 전에 아래 두 가지를 fail-fast preflight로 검사합니다.

- stack status가 이미 `UPDATE_ROLLBACK_FAILED` 인지
- `aws lambda update-function-code --dry-run` 이 현재 stage function에 대해 허용되는지
- `prod`인 경우 같은 `main` SHA에 성공한 `deploy-smoke [dev]` 또는 `deploy-smoke [dev<suffix>]` run이 이미 있는지

이 preflight가 `AccessDeniedException` 으로 멈추면, 이는 deploy rerun보다 AWS-side Lambda update restriction 분리가 먼저라는 뜻입니다.
`prod` preflight가 dev-first gate에서 멈추면, 이는 stage-equivalent `dev` release evidence 없이 `prod`를 먼저 실행하려는 시도라는 뜻입니다.

## Deploy + Smoke Workflow

`deploy-smoke` workflow is `workflow_dispatch` only and runs:

1. Deploy (`infra/sam/template.yaml`)
2. Post-deploy smoke checks (`scripts/smoke.py`)
3. Optional Voice Brief import smoke (`scripts/voice_brief_smoke.py`)
4. Optional native meeting recording smoke (`scripts/meeting_recording_smoke.py`)
5. Ops smoke on `dev` by default (`scripts/ops_smoke.py`)
   - `prod` runs ops smoke only when workflow input `include_ops_smoke=true`

Smoke validates:
- `GET /health` returns `200`
- `GET /version` exposes `features.procurement_copilot`
- `POST /generate` without key returns `401 UNAUTHORIZED`
- `POST /generate` with key returns `200` with `bundle_id`
- `POST /generate/export` with key returns `200` with export metadata
- optional procurement smoke via `scripts/smoke.py` when workflow input `include_procurement_smoke=true`:
  - prefers `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` from GitHub Variables when a stable fixture is configured
  - optionally uses `PROCUREMENT_SMOKE_TENANT_ID_<STAGE>` when the smoke tenant is not `system`
  - auto-registers a smoke user on empty tenants
  - or logs in with `PROCUREMENT_SMOKE_USERNAME_<STAGE>` / `PROCUREMENT_SMOKE_PASSWORD_<STAGE>` on non-empty tenants
  - creates a project
  - calls `POST /projects/{project_id}/imports/g2b-opportunity`
  - calls `POST /projects/{project_id}/procurement/evaluate`
  - calls `POST /projects/{project_id}/procurement/recommend`
  - calls `POST /projects/{project_id}/decision-council/run`
  - calls `POST /generate/stream` with `bundle_type=bid_decision_kr`
  - verifies the generated decision document is auto-linked back into project documents
  - verifies the project-linked `bid_decision_kr` document keeps Decision Council provenance when the council step ran successfully
  - when the recommendation is `GO` or `CONDITIONAL_GO`, also calls `POST /generate/stream` with `bundle_type=proposal_kr`
  - verifies the auto-linked `proposal_kr` document keeps the same Decision Council provenance and applied-bundle metadata
  - verifies the generated procurement document can enter existing `/approvals` and `/share` routes
  - when the recommendation is `NO_GO`, also verifies the release-closeout remediation path:
    - downstream `proposal_kr` generation is blocked until an override reason is saved
    - remediation link copy/open audit endpoints accept the existing blocked-event context
    - procurement quality summary moves the same case through `shared_not_opened` → `opened_unresolved` → `opened_resolved`
    - override 저장 후 retry된 `proposal_kr` document가 council provenance를 유지하는지 확인
  - auto-discovers a recent live G2B bid first when no fixed target is configured
  - retries raw bid/detail variants plus live discovery candidates when the configured target has drifted out of the live G2B upstream
  - logs `SKIP` instead of failing the whole optional smoke lane when every procurement import candidate still returns `404`
  - prefers the ops-key tenant summary route when `SMOKE_OPS_KEY` is available, and logs `SKIP` only when the live recommendation is not `NO_GO` or neither admin summary access nor ops-key access is available
  - still fails the smoke job on non-`404` procurement errors so runtime/auth regressions remain visible
- optional Voice Brief smoke:
  - creates or logs in a smoke user
  - creates a project
  - calls `POST /projects/{project_id}/imports/voice-brief`
  - verifies imported project metadata is stored
- optional native meeting recording smoke when workflow input `include_meeting_recording_smoke=true`:
  - uploads the fixture wav file to `POST /projects/{project_id}/recordings`
  - calls `POST /projects/{project_id}/recordings/{recording_id}/transcribe`
  - calls `POST /projects/{project_id}/recordings/{recording_id}/approve`
  - calls `POST /projects/{project_id}/recordings/{recording_id}/generate-documents`
  - verifies `meeting_minutes_kr` and `project_report_kr` are generated and source-linked back into the project detail document list
- `POST /ops/investigate` with `notify=false` returns `200` and stores report to S3
- immediate second `/ops/investigate` call returns `deduped=true`

## Runtime Storage Configuration

Deployment template sets:

- `DECISIONDOC_STORAGE=s3`
- `DECISIONDOC_S3_BUCKET=<stage bucket>`
- `DECISIONDOC_S3_PREFIX=decisiondoc-ai/`
- `DECISIONDOC_ENV=<stage>`
- `DECISIONDOC_API_KEY=<GitHub secret>`
- `DECISIONDOC_API_KEYS=<GitHub secret or DECISIONDOC_API_KEY fallback>`
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
- AWS manual deploy path now passes `DECISIONDOC_API_KEYS` when the repo secret exists, and otherwise falls back to the single `DECISIONDOC_API_KEY` value.
- Because `deploy-smoke` still uses `DECISIONDOC_API_KEY` as the header value for smoke calls, any overlap rotation list in `DECISIONDOC_API_KEYS` should include the current `DECISIONDOC_API_KEY` until smoke callers are intentionally moved.
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
5. If procurement smoke is enabled, confirm one live URL or bid number passes:
   - project create
   - `imports/g2b-opportunity`
   - `procurement/evaluate`
   - `procurement/recommend`
   - `decision-council/run`
   - `generate/stream` with `bid_decision_kr`
   - if recommendation is `GO` or `CONDITIONAL_GO`, `generate/stream` with `proposal_kr`
   - project document auto-link
   - Decision Council provenance on the auto-linked `bid_decision_kr` / `proposal_kr` row
   - `/approvals` and `/share` route availability
  - if the smoke output says `SKIP`, treat it as upstream-discovery drift rather than deploy failure; when you operate with a fixed fixture, refresh `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` before the next release
6. Run one manual web sanity check on the deployed environment:
   - log in through the web UI
   - open `거점 관리 -> 조달 품질` and confirm blocked attempt / remediation handoff / recent activity render without errors
   - open a project detail page
   - confirm the procurement panel is visible
   - import `R26BK01398367` or a known-good detail URL
   - click `판단 갱신`
   - enter a council goal in `Decision Council v1` and click `Decision Council 실행`
   - confirm the panel now shows latest direction, risks, disagreements, role cards, and council-assisted generate CTAs for `의사결정 문서 생성` and `제안서 생성`
   - click `의사결정 문서 생성`
   - confirm the generated `bid_decision_kr` row shows council provenance (`Council v1`, revision, direction)
   - if recommendation is `GO` or `CONDITIONAL_GO`, click `제안서 생성` and confirm the generated `proposal_kr` row shows the same council freshness/provenance contract
   - if the recommendation is `NO_GO`, confirm downstream without override reason is blocked and the project detail remediation strip guides override input
   - copy one remediation link from the summary and open it once to confirm the summary queue moves through `공유됨, 아직 미열람` -> `열람됨, 미해소`
   - save an override reason and retry one downstream bundle to confirm the same queue item lands in `열람 후 해소`
   - confirm the generated procurement document shows `결재 요청` and `공유`
   - confirm `/version` reports the intended app version and `features.procurement_copilot=true`
7. When you want to rerun only the deployed procurement lane outside GitHub Actions, use the thin stage wrapper:

```bash
cp scripts/stage_procurement_smoke.env.example /tmp/stage_procurement_smoke.env
$EDITOR /tmp/stage_procurement_smoke.env
.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.env --preflight
.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.env
```

Required env for this ad hoc deployed-stage path:
- `SMOKE_BASE_URL`
- `SMOKE_API_KEY`
- `G2B_API_KEY`

Optional env:
- `SMOKE_PROCUREMENT_URL_OR_NUMBER`
- `SMOKE_OPS_KEY`
- `SMOKE_PROVIDER`
- `SMOKE_TIMEOUT_SEC`
- `SMOKE_TENANT_ID`
- `PROCUREMENT_SMOKE_USERNAME`
- `PROCUREMENT_SMOKE_PASSWORD`

If you already maintain `.github-actions.env`, you can export the stage-specific deployed smoke file instead of filling every value manually:

```bash
.venv/bin/python scripts/export_stage_procurement_smoke_env.py \
  --stage dev \
  --env-file .github-actions.env \
  --base-url https://your-dev-stage.example.com \
  --output /tmp/stage_procurement_smoke.dev.env

.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.dev.env --preflight
.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.dev.env
```

This exporter reuses the same repository-level stage values already prepared for `deploy-smoke`, and only asks for the deployed `base_url` explicitly.

If your AWS CLI session can already describe the deployed stack, you can also skip manual base URL lookup and reuse the same CloudFormation output path that `deploy-smoke` uses:

```bash
.venv/bin/python scripts/run_stage_procurement_smoke.py \
  --github-actions-env-file .github-actions.env \
  --stage dev \
  --resolve-base-url-from-stack \
  --preflight

.venv/bin/python scripts/run_stage_procurement_smoke.py \
  --github-actions-env-file .github-actions.env \
  --stage dev \
  --resolve-base-url-from-stack
```

Notes:
- default stack names are `decisiondoc-ai-dev` and `decisiondoc-ai-prod`
- pass `--stack-name` when you are checking a non-default stack name such as blue/green variants
- `AWS_REGION` can come from `.github-actions.env`, the shell, or `--aws-region`
- this one-command path now includes the stage-env export step implicitly; use `scripts/export_stage_procurement_smoke_env.py` only when you want to persist the generated smoke env file separately
8. If Voice Brief integration is enabled, verify one happy-path import manually:
   - open a project in the web UI
   - import a known-good `recording_id` and optional `revision_id`
   - confirm a `voice_brief_import` document appears in project detail
   - confirm blocked states map correctly (`stale_summary`, `unapproved_summary`, `voice_brief_not_found`, `voice_brief_upstream_error`)

For `deploy-smoke`, you can automate the happy-path check by setting:

- workflow input `include_procurement_smoke=true`
- stage variable `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>`
- optional stage variable `PROCUREMENT_SMOKE_TENANT_ID_<STAGE>`
- optional stage secrets `PROCUREMENT_SMOKE_USERNAME_<STAGE>`, `PROCUREMENT_SMOKE_PASSWORD_<STAGE>`
- workflow input `include_voice_brief_smoke=true`
- stage variable `VOICE_BRIEF_SMOKE_RECORDING_ID_<STAGE>`
- optional `VOICE_BRIEF_SMOKE_REVISION_ID_<STAGE>`
- optional `VOICE_BRIEF_SMOKE_TENANT_ID_<STAGE>`

If the target tenant already has users, also set:

- `VOICE_BRIEF_SMOKE_USERNAME_<STAGE>`
- `VOICE_BRIEF_SMOKE_PASSWORD_<STAGE>`

Reserved concurrency note:
- `deploy` / `deploy-smoke` no longer force a default reserved concurrency for `prod`.
- If you need reserved concurrency in production, set `LambdaReservedConcurrentExecutions` intentionally in a follow-up change after confirming account-level unreserved concurrency headroom.

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
2. Rotate API keys by updating `DECISIONDOC_API_KEYS` first and keeping the current `DECISIONDOC_API_KEY` included during overlap.
3. Lower safety rails:
   - HTTP API throttling (`ApiThrottlingBurstLimit`, `ApiThrottlingRateLimit`)
   - Lambda reserved concurrency (`LambdaReservedConcurrentExecutions`)
4. Re-run smoke checks before reopening traffic.
5. Keep Status Page incident in `investigating` until error/latency signals normalize.

### Key rotation (summary)

1. Deploy with both old and new keys in `DECISIONDOC_API_KEYS`, while keeping `DECISIONDOC_API_KEY` set to one of the allowed runtime keys used by smoke callers.
2. Move clients to the new key.
3. Redeploy removing the old key.

### Key rotation (operator checklist)

이 섹션은 GitHub Actions secret 기준으로 `DECISIONDOC_API_KEYS` runtime allowlist와
`DECISIONDOC_API_KEY` smoke / caller key를 안전하게 교체하는 절차를 정리한다.

#### What you need to prepare

- 새 client key 1개
- 현재 운영 중인 old key 식별
- `main` 기준 `deploy-smoke [dev]` 실행 권한
- prod rotation일 경우 같은 SHA에서 먼저 성공한 `deploy-smoke [dev]` evidence

#### Safe rollout order

1. Update overlap allowlist first.
   - `DECISIONDOC_API_KEYS=old,new`
   - `DECISIONDOC_API_KEY=old`
2. Run `deploy-smoke [dev]`.
   - `Run smoke`
   - `Run meeting recording smoke`
   - `Run ops smoke`
   위 세 단계가 모두 성공해야 다음으로 진행한다.
3. Move smoke caller or external clients.
   - smoke caller를 먼저 바꿀 경우 `DECISIONDOC_API_KEY=new`
   - 외부 클라이언트를 먼저 바꿀 경우 `DECISIONDOC_API_KEYS=old,new` 상태를 유지한 채 rollout 한다.
4. Run `deploy-smoke [prod]`.
   - prod는 같은 `main` SHA에 성공한 `dev` smoke evidence가 있을 때만 진행한다.
5. Finalize the rotation.
   - 모든 caller가 new key를 사용 중임을 확인한 뒤
   - `DECISIONDOC_API_KEYS=new`
   - `DECISIONDOC_API_KEY=new`
6. Record the cutover time and owner.
   - 누가
   - 언제
   - 어떤 old key를 제거했는지 운영 로그나 ticket에 남긴다.

#### Rollback rule

- `deploy-smoke [dev]` 또는 `deploy-smoke [prod]` 가 실패하면 즉시 baseline으로 되돌린다.
  - `DECISIONDOC_API_KEYS=old`
  - `DECISIONDOC_API_KEY=old`
- rollback 후에는 failure 원인을 정리하기 전까지 old key 삭제를 진행하지 않는다.

#### Notes

- `DECISIONDOC_API_KEYS` 는 runtime이 허용하는 key 목록이다.
- `DECISIONDOC_API_KEY` 는 현재 smoke script나 일부 caller가 실제로 헤더에 넣는 단일 key다.
- 따라서 overlap 기간에는 `DECISIONDOC_API_KEY` 값이 항상 `DECISIONDOC_API_KEYS` 안에 포함되어 있어야 한다.
- native meeting recording smoke를 같이 돌릴 때는 `OPENAI_API_KEY_<STAGE>` 또는 repo-level `OPENAI_API_KEY` fallback도 유효해야 한다.

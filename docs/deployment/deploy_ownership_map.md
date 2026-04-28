# Deploy Ownership Map

이 문서는 DecisionDoc AI의 배포 권한, 책임, secret ownership을 한 곳에서 확인하기 위한 운영 기준이다.
목표는 deploy failure를 code issue, config issue, infra/account issue로 빠르게 분리하고, `prod`를 feature 실험 환경이 아니라 promote target으로 유지하는 것이다.

## 1. Ownership Matrix

| 주체 | 책임 | 허용 작업 | 금지/주의 작업 |
|------|------|-----------|----------------|
| GitHub Actions deploy role | 표준 CI/CD 실행자 | `deploy-smoke`, Docker server CD, OIDC 기반 AWS deploy | console 수동 변경, 운영 secret 원문 조회 |
| Local admin | 진단과 복구 보조 | `aws sts get-caller-identity`, stack status 확인, dry-run, server SSH 상태 확인 | 정상 release를 우회하는 임의 prod 변경 |
| Break-glass operator | 계정/서비스 제한 해소 | AWS Support 대응, compromised key rotation, restriction 해소 후 controlled rerun | 일반 기능 배포 경로로 사용 |
| Product operator | 배포 승인과 smoke 판정 | release note 확인, smoke evidence 확인, prod go/no-go 결정 | IAM/secret 직접 수정 |

## 2. Environment Ownership

| 환경 | 목적 | 기본 배포 경로 | 필수 evidence |
|------|------|----------------|---------------|
| `dev` | feature integration, destructive 실험 | `deploy-smoke [dev]` 또는 local compose | targeted tests, smoke report |
| `stage` | release candidate 검증 | Docker server CD staging 또는 stage-equivalent `dev` gate | staging deploy summary, smoke pass |
| `prod` | promote-only 운영 | tag 기반 Docker server CD 또는 `deploy-smoke [prod]` | 같은 `main` SHA의 dev/stage evidence, post-deploy report |

현재 dedicated `stage` stack이 완전히 분리되지 않은 구간에서는 `dev`를 stage-equivalent gate로 사용한다.
즉, `prod deploy-smoke`는 같은 `main` SHA에 성공한 `dev deploy-smoke` evidence가 있을 때만 정상 경로로 허용한다.

## 3. Secret Ownership

| Secret / Variable | 소유자 | 사용처 | 설정 단위 |
|-------------------|--------|--------|-----------|
| `DECISIONDOC_API_KEY`, `DECISIONDOC_API_KEYS` | Product operator + deploy owner | runtime API auth, smoke auth | repo/environment secret |
| `DECISIONDOC_OPS_KEY` | deploy owner | `/ops/*`, post-deploy diagnostics | repo/environment secret |
| `AWS_ROLE_ARN_DEV`, `AWS_ROLE_ARN_PROD` | infra owner | AWS OIDC deploy | repo/environment variable or secret |
| `DECISIONDOC_S3_BUCKET_DEV`, `DECISIONDOC_S3_BUCKET_PROD` | infra owner | storage backend | repo/environment variable |
| `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY` | server deploy owner | Docker server staging CD | repo secret, all-or-none |
| `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY` | server deploy owner | Docker server production CD | repo secret, all-or-none |
| `OPENAI_API_KEY_DEV`, `OPENAI_API_KEY_PROD` | provider owner | live provider generation | repo/environment secret |
| `G2B_API_KEY_DEV`, `G2B_API_KEY_PROD` | procurement owner | procurement live smoke | repo/environment secret |

Rules:

- `STAGING_*` and `PROD_*` deploy secrets must be configured as an all-or-none set.
- `DECISIONDOC_API_KEY` must remain included in `DECISIONDOC_API_KEYS` during key rotation.
- `.github-actions.env` is a local-only scaffold and must not be committed.
- `scripts/import-github-actions-env-file.sh --stage dev|prod` may be used to copy stage-specific values from `.env` or `.env.prod` into the local scaffold.
- `scripts/check-github-actions-config.sh --stage dev|prod --env-file .github-actions.env --docker-deploy` must pass before enabling Docker server deploy for that stage.

## 4. Normal Release Flow

1. Run local verification for the changed scope.
2. Push to `main` and confirm CI success.
3. Confirm Docker CD image build success.
4. If staging secrets are configured, confirm staging deploy and smoke success.
5. If staging secrets are not configured, confirm CD summary explicitly says staging was skipped due missing `STAGING_*`.
6. For production, create and push a `v*.*.*` tag only after stage-equivalent evidence exists.
7. Run or confirm post-deploy report and retain `reports/post-deploy/latest.json` on the target server.

## 5. Failure Classification

| Symptom | Classification | Next action |
|---------|----------------|-------------|
| CI unit/lint/security job fails | code or test issue | Fix in repo before deploy retry |
| CD says staging secrets are partially configured | config issue | Set or remove all `STAGING_*` together |
| CD says staging skipped because secrets are empty | expected optional staging skip | Continue only if this is intentional |
| Docker compose pull/up fails on remote server | server/runtime issue | Inspect remote `/opt/decisiondoc`, Docker daemon, GHCR auth |
| `deploy-smoke [prod]` blocks on missing dev evidence | release gate issue | Run `deploy-smoke [dev]` for same `main` SHA or use documented break-glass |
| Lambda `UpdateFunctionCode` returns 403 in workflow and local dry-run | AWS-side restriction | Stop reruns, follow account security / AWS Support path |
| Stack is `UPDATE_ROLLBACK_FAILED` | CloudFormation recovery issue | `continue-update-rollback` before any deploy rerun |

## 6. Break-glass Rules

Break-glass is allowed only when the normal gate blocks an urgent recovery and the operator records the reason.

Required record:

- incident or support case reference
- current stack/server state
- exact workflow run or command that failed
- reason normal stage-first evidence cannot be produced
- rollback path if the recovery deploy fails

Never use break-glass for routine feature release or to bypass failing tests.

## 7. Operator Checklist

Before `main` push:

- [ ] Relevant local tests passed.
- [ ] No production secret or `.env` file is staged.
- [ ] Change does not require external smoke, or smoke plan is named.

Before staging deploy:

- [ ] `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY` are either all set or all intentionally empty.
- [ ] If staging deploy is expected, `check-github-actions-config.sh --stage dev --docker-deploy` passes.
- [ ] The target server has `/opt/decisiondoc` checkout and `.env.prod`.
- [ ] The server can pull GHCR images.

Before production deploy:

- [ ] CI for the target SHA is green.
- [ ] Stage-equivalent smoke evidence exists for the same SHA.
- [ ] `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY` are all set.
- [ ] `check-github-actions-config.sh --stage prod --docker-deploy` passes.
- [ ] API key rotation overlap, if any, is documented.
- [ ] Rollback owner is available.

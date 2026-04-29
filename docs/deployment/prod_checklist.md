# 프로덕션 배포 체크리스트

## 1. 필수 환경변수 (반드시 설정)

| 변수 | 예시 값 | 설명 |
|------|---------|------|
| `DECISIONDOC_ENV` | `prod` | 프로덕션 모드 활성화 (Swagger UI 비활성, API 키 강제) |
| `DECISIONDOC_PROVIDER` | `openai` | LLM 프로바이더 |
| `OPENAI_API_KEY` | `sk-...` | OpenAI API 키 (`provider=openai` 시 필수) |
| `DECISIONDOC_API_KEYS` | `generated-runtime-key` | 클라이언트 인증 키 (콤마 구분 가능) |
| `DECISIONDOC_OPS_KEY` | `ops-secret-key` | `/ops/*` 엔드포인트 인증 키 |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | JWT 서명 키 (32바이트 이상) |
| `ALLOWED_ORIGINS` | `https://your-domain.com` | 허용 오리진 |

## 2. 권장 환경변수

| 변수 | 권장 값 | 설명 |
|------|---------|------|
| `DECISIONDOC_CORS_ENABLED` | `1` | CORS 활성화 (프론트엔드 분리 시) |
| `ALLOWED_ORIGINS` | `https://yourdomain.com` | 허용 오리진 |
| `DECISIONDOC_CACHE_ENABLED` | `1` | 번들 캐싱 (응답속도 향상) |
| `DECISIONDOC_LOG_LEVEL` | `INFO` | 로그 레벨 |
| `DECISIONDOC_STORAGE` | `s3` | S3 스토리지 권장 |
| `DECISIONDOC_S3_BUCKET` | `my-bucket` | S3 버킷 이름 (`storage=s3` 시 필수) |
| `AWS_REGION` | `ap-northeast-2` | AWS 리전 |

## 3. 선택 환경변수

| 변수 | 설명 |
|------|------|
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | 이메일 알림 |
| `SLACK_WEBHOOK_URL` | Slack 알림 |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | 결제 |
| `STATUSPAGE_PAGE_ID`, `STATUSPAGE_API_KEY` | Statuspage 연동 |
| `DECISIONDOC_SEARCH_ENABLED=1` + `SERPER_API_KEY` | 웹검색 스케치 |
| `G2B_API_KEY` | 나라장터 API |
| `VOICE_BRIEF_API_BASE_URL`, `VOICE_BRIEF_API_BEARER_TOKEN`, `VOICE_BRIEF_TIMEOUT_SECONDS` | 프로젝트 상세 Voice Brief import |
| `SSO_ENCRYPTION_KEY` | SSO 시크릿 암호화 (별도 키 분리 시) |

## 4. 프로덕션 서버 배포

```bash
# 1. .env.prod 생성
python3 scripts/bootstrap_prod_env.py \
  --profile admin \
  --output .env.prod \
  --openai-api-key 'sk-...'

# 2. preflight
python3 scripts/check_prod_env.py \
  --env-file .env.prod \
  --expected-origin https://admin.decisiondoc.kr

# 3. local build rollout
python3 scripts/deploy_compose_local.py \
  --env-file .env.prod \
  --image decisiondoc-admin-local \
  --post-check

# 4. post-deploy check
python3 scripts/post_deploy_check.py --env-file .env.prod

# 4-1. shareable JSON report
python3 scripts/post_deploy_check.py \
  --env-file .env.prod \
  --report-file ./reports/post-deploy.json

# 4-2. history + latest
python3 scripts/post_deploy_check.py \
  --env-file .env.prod \
  --report-dir ./reports/post-deploy

# 4-3. Report Workflow ERP smoke (post_deploy_check에 기본 포함)
SMOKE_BASE_URL=https://admin.decisiondoc.kr \
SMOKE_API_KEY=<runtime-api-key> \
python3 scripts/report_workflow_smoke.py
```

`scripts/deploy_compose_local.py --post-check` 와 `./scripts/deploy.sh production <tag>` 는 기본적으로 `./reports/post-deploy/` 아래 timestamped report, `latest.json`, `index.json` 을 함께 남깁니다.

`scripts/post_deploy_check.py` 는 기본 smoke 이후 `scripts/report_workflow_smoke.py` 도 app container 안에서 실행합니다. 이 smoke는 `[SMOKE]` report workflow를 생성하고 planning blueprint, planning approval guard, slide generation/approval, final approval, project promotion, PPTX export, snapshot export(redacted handoff artifact)를 검증합니다. 기본값은 `X-Tenant-ID`를 보내지 않으며, tenant별 검증이 필요할 때만 `SMOKE_TENANT_ID=<tenant-id>`를 명시합니다.

## 5. Docker Compose / HA

```bash
# 단일 서버 compose
python3 scripts/deploy_compose_local.py --env-file .env.prod --image decisiondoc-<site>-local

# GHCR tag 기반 compose 배포
./scripts/deploy.sh production v1.0.0

# HA compose
docker compose --env-file .env.prod -f docker-compose.ha.yml up -d
```

## 6. GitHub Actions CI/CD

- **CI**: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 에서 테스트, security scan, lint 실행
- **Docker server CD**: [`.github/workflows/cd.yml`](../../.github/workflows/cd.yml) 에서 `main` 브랜치와 numeric semver `vMAJOR.MINOR.PATCH` 태그 기준으로 배포
- **AWS manual deploy**: [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml), [`.github/workflows/deploy-smoke.yml`](../../.github/workflows/deploy-smoke.yml) 에서 `workflow_dispatch`

운영 모델과 장기 release 방향은 [../operating_model_roadmap.md](../operating_model_roadmap.md) 를 기준으로 합니다.
배포 주체, 권한 경계, secret ownership은 [deploy_ownership_map.md](./deploy_ownership_map.md) 를 기준으로 합니다.

```bash
# Docker server production deploy
git tag v1.0.0
python3 scripts/check_release_tag_source.py v1.0.0
git push origin v1.0.0
```

Docker server CD 필수 GitHub Secrets:
- `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY`
- `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`

참고:
- `scripts/import-github-actions-env-file.sh --stage dev|prod` 는 stage에 맞는 `STAGING_*` 또는 `PROD_*` deploy secrets를 `.github-actions.env` scaffold로 복사한다.
- 실제 Docker server deploy를 준비할 때는 `scripts/check-github-actions-config.sh --stage dev|prod --env-file .github-actions.env --docker-deploy` 로 deploy secret 3종을 필수값으로 검증한다.
- staging deploy secret 세 개가 모두 비어 있으면 `main` push CD는 Docker image build/push까지만 수행하고 staging deploy/smoke를 명시적으로 skip한다.
- staging deploy skip/configured/blocked 판단은 CD run의 GitHub Step Summary `Staging deployment` 섹션에 기록된다.
- staging deploy를 활성화하려면 `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY`를 반드시 함께 설정한다.
- `vMAJOR.MINOR.PATCH` tag production deploy는 staging job에 의존하지 않고 Docker image build/push 성공 후 `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY` preflight를 통과해야 실행된다.
- `vfoo.bar.baz`처럼 numeric semver가 아닌 `v*.*.*` tag는 Docker image publish 전에 CD가 먼저 실패한다.
- `vMAJOR.MINOR.PATCH` tag가 `origin/main`에서 도달 불가능하면 Docker image publish 전에 CD가 먼저 실패한다. 이 경우 semver GHCR image가 생성되지 않아야 한다.
- tag push 전에는 `python3 scripts/check_release_tag_source.py vX.Y.Z` 로 동일한 release source rule을 로컬에서 먼저 확인한다.
- Docker image publish 전 release tag source 판정은 CD run의 GitHub Step Summary `Release tag source` 섹션에 기록된다.
- `vMAJOR.MINOR.PATCH` tag는 반드시 `origin/main`에서 도달 가능한 commit을 가리켜야 한다. CD가 `release tag does not point to a commit reachable from origin/main`으로 block하면 검증된 `main` commit으로 tag를 다시 잡아야 한다.
- release tag source gate는 annotated tag와 lightweight tag를 모두 지원하기 위해 tag object를 commit으로 dereference한 뒤 `origin/main` 도달 가능성을 판정한다.
- production tag source gate는 `git merge-base` 판정을 위해 full git history checkout을 사용한다. 이 checkout을 shallow clone으로 바꾸면 과거 `main` commit에 찍은 정상 release tag가 잘못 block될 수 있다.
- production deploy secret preflight 결과는 CD run의 GitHub Step Summary `Production deployment` 섹션에 기록된다. `blocked`면 tag 재실행 전에 `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`를 모두 설정해야 한다.
- Docker server CD는 원격 `/opt/decisiondoc` checkout을 해당 GitHub SHA로 맞춘 뒤 `docker-compose.prod.yml`을 실행한다. staging은 GHCR `main` tag를, production은 Git tag의 `v` prefix를 제거한 semver image tag를 사용한다. 예: Git tag `v1.1.4` -> Docker image tag `1.1.4`.
- `scripts/deploy.sh production vX.Y.Z` 도 Docker server CD와 동일하게 release tag source preflight를 실행하고 GHCR image tag `X.Y.Z`로 정규화한다. 전체 image ref를 직접 넘기는 긴급 rollback 경로는 release tag source preflight를 건너뛴다.
- Docker server CD는 GHCR repository 이름을 lowercase로 정규화하고, 모든 remote compose 명령은 `--env-file .env.prod`를 명시한다. `docker compose pull/up` 실패는 job failure로 처리되어야 한다.
- Production deploy의 사전 data backup은 `DECISIONDOC_BACKUP_DIR`가 있으면 해당 경로, 없으면 `/opt/decisiondoc/backups` 상대 경로(`./backups`)를 사용한다. backup directory 생성 실패는 경고 후 배포를 계속하지만 compose pull/up 실패는 실패로 처리한다.

참고:
- GHCR 로그인은 현재 `.github/workflows/cd.yml`에서 built-in `GITHUB_TOKEN`과 `packages:write` 권한으로 처리한다.
- 별도 `GHCR_TOKEN` secret은 현재 workflow contract의 필수값이 아니다.

AWS SAM 배포 시 필요한 secret/variable은 [../deploy_aws.md](../deploy_aws.md)를 기준으로 설정합니다.
native meeting recording을 prod에서 실제로 열려면 `OPENAI_API_KEY_PROD` 와 선택적 `MEETING_RECORDING_*_PROD` variable도 같은 runbook에 맞춰 설정합니다.
계정 보안 incident와 access key rotation 대응은 [./account_security_incident_checklist.md](./account_security_incident_checklist.md)를 기준으로 합니다.

## 6.1 프로덕션 배포 ownership

상세 ownership matrix와 운영자 checklist는 [deploy_ownership_map.md](./deploy_ownership_map.md) 를 source of truth로 사용합니다.

| 주체 | 역할 | 기본 경로 |
|------|------|-----------|
| GitHub Actions deploy role | canonical prod deploy | `deploy` / `deploy-smoke` workflow |
| Local admin AWS user | 상태 확인, rollback recovery, dry-run 진단 | AWS CLI / read-only console |
| Break-glass operator | exceptional recovery only | 제한 해소 후 controlled rerun |

기본 원칙:

- `prod`는 feature 실험 환경이 아니라 promote target
- console edit는 정상 배포 경로가 아니라 예외 복구 수단
- `UPDATE_ROLLBACK_FAILED` 상태에서는 재배포보다 recovery와 root-cause 분리가 먼저
- `prod deploy-smoke` 는 같은 `main` SHA에 대해 성공한 `dev` deploy-smoke evidence가 있을 때만 정상 경로로 허용

API key rotation 시 운영자 체크:

- 먼저 `DECISIONDOC_API_KEYS=old,new` 로 overlap allowlist를 연다.
- overlap 동안 `DECISIONDOC_API_KEY` 값은 반드시 `DECISIONDOC_API_KEYS` 안에 포함되게 유지한다.
- `deploy-smoke [dev]` 성공 후에만 `prod deploy-smoke` 로 넘어간다.
- 모든 caller cutover가 끝난 뒤에만 `DECISIONDOC_API_KEYS=new`, `DECISIONDOC_API_KEY=new` 로 finalize 한다.
- 이 repo 밖에서 기존 key 를 쓰는 caller 가 없으면 `DECISIONDOC_API_KEYS=new` + `DECISIONDOC_API_KEY=new` direct cutover 도 가능하다.
- 상세 순서와 rollback 규칙은 [../deploy_aws.md#key-rotation-operator-checklist](../deploy_aws.md#key-rotation-operator-checklist) 를 따른다.
- change window용 기록 템플릿은 [./api_key_rotation_change_plan.md](./api_key_rotation_change_plan.md) 를 사용한다.

## 6.2 현재 알려진 prod blocker 패턴

`DecisionDocFunction` update가 `AccessDeniedException` 으로 실패하고, local admin의 `aws lambda update-function-code --dry-run` 도 동일하게 실패하면 다음처럼 해석합니다.

- repo code 문제 아님
- workflow artifact path 문제 아님
- 일반 IAM allow 누락 문제도 아닐 가능성이 큼
- AWS-side Lambda update restriction으로 분류

이 상태에서는 `deploy-smoke` 재실행을 반복하지 말고, 먼저 stack recovery와 권한/서비스 제한 원인 분리를 수행합니다.

## 7. 배포 전 최종 확인

```bash
# 1. 전체 테스트 통과 확인
pytest tests/ --ignore=tests/e2e -q

# 2. 배포 env preflight
python3 scripts/check_prod_env.py \
  --env-file .env.prod \
  --expected-origin https://your-domain.com

# 3. 배포 smoke 테스트
python3 scripts/run_deployed_smoke.py --env-file .env.prod

# 4. post-deploy check
python3 scripts/post_deploy_check.py --env-file .env.prod

# 5. ops smoke 테스트
SMOKE_BASE_URL=http://localhost:8000 \
SMOKE_OPS_KEY=your-ops-key \
SMOKE_S3_BUCKET=your-bucket \
AWS_REGION=ap-northeast-2 \
python3 scripts/ops_smoke.py

# 6. 보안 스캔
pip install bandit safety
bandit -r app/ -ll
# Safety CLI v3의 `scan`은 auth/API key가 필요하므로,
# 현재 무인 환경에서는 legacy `check` 경로를 사용한다.
HOME=/tmp safety check -r requirements.txt
```

## 7.1 프로덕션 재실행 금지 조건

아래 조건 중 하나라도 만족하면 `prod deploy-smoke` 를 다시 누르지 않습니다.

- stack status가 `UPDATE_ROLLBACK_FAILED`
- 최근 deploy 로그가 `DecisionDocFunction` `AccessDeniedException` 403으로 종료
- local admin `aws lambda update-function-code --dry-run` 이 동일하게 실패

이 경우 순서는 아래입니다.

1. `continue-update-rollback`
2. `UPDATE_ROLLBACK_COMPLETE` 확인
3. dry-run 기반 원인 분리
4. AWS-side restriction 해소 전에는 rerun 금지

현재 `deploy-smoke` workflow도 같은 기준을 deploy preflight로 먼저 검사하도록 맞췄습니다. 즉, stack이 이미 깨져 있거나 Lambda code update dry-run이 막혀 있으면 `SAM deploy` 전에 fail-fast로 종료됩니다.

또한 `prod` dispatch는 같은 `main` SHA에 성공한 `deploy-smoke [dev]` run이 있어야 합니다. `deployment_suffix=-green` 같이 fresh-stack 경로를 쓰면 `deploy-smoke [dev-green]` evidence가 필요합니다. 이 evidence가 없으면 `SAM deploy` 전에 멈추고, 정말 예외적인 운영 복구일 때만 `break_glass_reason` 입력으로 override 할 수 있습니다.

기존 stack을 덮어쓰지 않고 우회 검증이 필요하면 `deployment_suffix` 입력으로 별도 stack/function 이름을 만들 수 있습니다. 예: `decisiondoc-ai-dev-green`, `decisiondoc-ai-prod-green`.

fresh-stack preflight note:

- suffix를 붙인 새 stack이 아직 존재하지 않으면 `deploy-smoke` preflight는 이를 create path로 판단하고 `UpdateFunctionCode` dry-run을 생략한다.
- 즉 `dev-green` 검증은 "in-place update 가능 여부"가 아니라 "new stack/function create 가능 여부"를 보는 단계다.

## 7.2 보안 incident 시 우선 순서

아래 상황이면 배포 runbook보다 account security runbook이 먼저다.

- AWS Support suspicious-activity case open
- leaked IAM access key notification 수신
- local admin user / GitHub Actions role / console 수동 생성이 모두 Lambda `AccessDeniedException` 으로 막힘

이 경우에는:

1. leaked key rotation / deletion
2. CloudTrail IAM / STS review
3. Support case reply
4. restriction lifted 확인
5. 그 다음에만 `dev-green -> dev -> prod`

상세 checklist와 reply template은 [./account_security_incident_checklist.md](./account_security_incident_checklist.md) 에 정리한다.

## 7.3 운영 smoke가 필요한 변경 vs 필요 없는 변경

`prod` 또는 `dev` deploy-smoke는 "변경이 실제 서비스 동작 또는 배포 경로를 바꿨는가"를 기준으로 결정한다.

운영 smoke가 필요한 변경:

- `app/` 아래 runtime code
- `infra/sam/template.yaml`
- `.github/workflows/deploy.yml`
- `.github/workflows/deploy-smoke.yml`
- smoke script 자체 변경 (`scripts/smoke.py`, `scripts/ops_smoke.py`, `scripts/voice_brief_smoke.py` 등)
- stage/prod env contract 또는 IAM/OIDC deploy path 변경

운영 smoke가 필요 없는 변경:

- `tests/test_check_secret_hygiene.py` 같은 test-only regression 추가
- `scripts/check_secret_hygiene.py` 와 local pre-commit hook처럼 repo secret guard만 강화하는 변경
- 운영 배포와 무관한 docs-only update

권장 판단 순서:

1. 변경이 deploy artifact 또는 runtime path를 바꾸면 `dev` smoke를 포함한다.
2. 변경이 scanner/test/docs 경계에만 머물면 local/CI verification으로 닫는다.
3. test-only secret hygiene PR은 micro-PR 체인으로 무한 확장하지 말고, 관련 safe-path / fail-path coverage가 충분해지면 통합 검증 후 종료한다.

## 8. 운영 모니터링

- `/health` — 전체 헬스체크
- `/health/live` — Kubernetes liveness probe
- `/health/ready` — Kubernetes readiness probe
- `/metrics` — Prometheus 메트릭
- `/ops/investigate` — 장애 조사 (OPS_KEY 필요)

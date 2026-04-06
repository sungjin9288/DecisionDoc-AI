# 프로덕션 배포 체크리스트

## 1. 필수 환경변수 (반드시 설정)

| 변수 | 예시 값 | 설명 |
|------|---------|------|
| `DECISIONDOC_ENV` | `prod` | 프로덕션 모드 활성화 (Swagger UI 비활성, API 키 강제) |
| `ENVIRONMENT` | `production` | 표준 환경 변수 |
| `DECISIONDOC_PROVIDER` | `openai` | LLM 프로바이더 |
| `OPENAI_API_KEY` | `sk-...` | OpenAI API 키 (`provider=openai` 시 필수) |
| `DECISIONDOC_API_KEYS` | `key1,key2` | 클라이언트 인증 키 (콤마 구분) |
| `DECISIONDOC_OPS_KEY` | `ops-secret-key` | `/ops/*` 엔드포인트 인증 키 |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | JWT 서명 키 (32바이트 이상) |
| `DATA_DIR` | `/data` | 파일 스토리지 경로 |

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

## 4. Docker 배포

```bash
# 이미지 빌드
docker build -t decisiondoc-ai:latest .

# 프로덕션 실행 (S3 스토리지)
docker run -d \
  -p 8000:8000 \
  -e DECISIONDOC_ENV=prod \
  -e ENVIRONMENT=production \
  -e DECISIONDOC_PROVIDER=openai \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e DECISIONDOC_API_KEYS=$DECISIONDOC_API_KEYS \
  -e DECISIONDOC_OPS_KEY=$DECISIONDOC_OPS_KEY \
  -e JWT_SECRET_KEY=$JWT_SECRET \
  -e DECISIONDOC_STORAGE=s3 \
  -e DECISIONDOC_S3_BUCKET=$S3_BUCKET \
  -e AWS_REGION=ap-northeast-2 \
  decisiondoc-ai:latest

# 헬스체크 확인
curl http://localhost:8000/health
```

## 5. Docker Compose / HA

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose --env-file .env.prod -f docker-compose.ha.yml up -d
```

## 6. GitHub Actions CI/CD

- **CI**: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 에서 테스트, security scan, lint 실행
- **Docker server CD**: [`.github/workflows/cd.yml`](../../.github/workflows/cd.yml) 에서 `main` 브랜치와 `v*.*.*` 태그 기준으로 배포
- **AWS manual deploy**: [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml), [`.github/workflows/deploy-smoke.yml`](../../.github/workflows/deploy-smoke.yml) 에서 `workflow_dispatch`

운영 모델과 장기 release 방향은 [../operating_model_roadmap.md](../operating_model_roadmap.md) 를 기준으로 합니다.

```bash
# Docker server production deploy
git tag v1.0.0
git push origin v1.0.0
```

Docker server CD 필수 GitHub Secrets:
- `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY`
- `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`
- `GHCR_TOKEN` (GitHub Container Registry)

AWS SAM 배포 시 필요한 secret/variable은 [../deploy_aws.md](../deploy_aws.md)를 기준으로 설정합니다.

## 6.1 프로덕션 배포 ownership

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

# 2. 도커 빌드 확인
docker build -t decisiondoc-ai:test .

# 3. 앱 smoke 테스트
SMOKE_BASE_URL=http://localhost:8000 \
SMOKE_API_KEY=your-api-key \
python scripts/smoke.py

# 4. ops smoke 테스트
SMOKE_BASE_URL=http://localhost:8000 \
SMOKE_OPS_KEY=your-ops-key \
SMOKE_S3_BUCKET=your-bucket \
AWS_REGION=ap-northeast-2 \
python scripts/ops_smoke.py

# 5. 보안 스캔
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

## 8. 운영 모니터링

- `/health` — 전체 헬스체크
- `/health/live` — Kubernetes liveness probe
- `/health/ready` — Kubernetes readiness probe
- `/metrics` — Prometheus 메트릭
- `/ops/investigate` — 장애 조사 (OPS_KEY 필요)

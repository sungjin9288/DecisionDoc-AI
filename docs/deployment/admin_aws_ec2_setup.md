# `admin.decisiondoc.kr` AWS EC2 구축 가이드

이 문서는 `admin.decisiondoc.kr` 를 AWS EC2에 배포하는 절차를 repo 기준으로 정리한 가이드입니다.

현재 v1 기준에서 이 문서는 **canonical deployment path** 입니다.

즉, 이번 handoff에서 실제 운영 기준선으로 보는 경로는 아래입니다.

- `admin.decisiondoc.kr`
- AWS EC2 1대
- Docker Compose
- `scripts/run_deployed_smoke.py`
- `scripts/post_deploy_check.py`

`dawool` live rollout과 AWS `stage-first / promote-only` lane은 이번 완료 범위가 아니라 다음 phase입니다.

권장 대상:

- 당신이 이동하면서 접속하는 공용 운영 환경
- 데모, 운영 점검, 테스트, 내부 문서 작업을 함께 처리하는 환경

이 가이드는 현재 repo의 `docker-compose.prod.yml`, `nginx/nginx.conf`, `scripts/setup.sh`, `scripts/setup_ssl.sh` 흐름에 맞춰 작성했습니다.

## 1. 권장 아키텍처

- 리전: AWS Seoul (`ap-northeast-2`)
- 서버: EC2 1대
- 고정 IP: Elastic IP 1개
- 도메인: `admin.decisiondoc.kr`
- 배포 방식: Docker Compose
- SSL: Let's Encrypt

현재 구조에서는 AWS Lambda/SAM보다 EC2가 더 단순합니다.
이유는 `nginx + docker-compose.prod.yml + local volume` 흐름이 이미 정리되어 있기 때문입니다.

## 2. EC2 생성

AWS Console에서 아래 순서로 진행합니다.

1. 리전을 `Asia Pacific (Seoul)` 로 선택
2. `EC2` → `Instances` → `Launch instances`
3. 아래 값으로 생성

### 인스턴스 권장값

- Name: `decisiondoc-admin-prod`
- AMI: `Ubuntu Server 22.04 LTS`
- Architecture: `64-bit (x86)`
- Instance type: `t3.medium`
- Key pair: 새로 생성
- Storage: `gp3 40GB`

권장 이유:

- `docker-compose.prod.yml` 에 app 리소스 제한이 `2 CPU / 2GB RAM` 으로 잡혀 있음
- `nginx` 와 운영 여유분까지 생각하면 `t3.medium` 이 가장 무난함

## 3. 보안 그룹

보안 그룹은 새로 만들고 아래처럼 설정합니다.

### Inbound

- `SSH` / TCP 22 / Source: `My IP`
- `HTTP` / TCP 80 / Source: `0.0.0.0/0`
- `HTTPS` / TCP 443 / Source: `0.0.0.0/0`

### Outbound

- 기본 전체 허용 유지

주의:

- `8000` 포트는 열지 않습니다.
- 앱 컨테이너는 호스트의 `8000` 에 바인딩되지만 외부에는 `80/443` 만 노출하는 구조로 운영합니다.

참고:

- AWS EC2 security group rules: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html>

## 4. Elastic IP 할당

EC2 생성 후 아래 순서로 고정 IP를 붙입니다.

1. `EC2` → `Elastic IPs`
2. `Allocate Elastic IP address`
3. 새로 생성된 IP 선택
4. `Actions` → `Associate Elastic IP address`
5. 대상 인스턴스로 `decisiondoc-admin-prod` 선택

이때 나온 IP가 `admin.decisiondoc.kr` 이 가리킬 고정 IP입니다.

참고:

- AWS Elastic IP: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html>

## 5. DNS 설정

`decisiondoc.kr` 을 구매한 곳의 DNS 관리 화면에서 아래 A 레코드를 추가합니다.

| Type | Host | Value |
|------|------|-------|
| A | `admin` | `<elastic-ip>` |

확인:

```bash
dig +short admin.decisiondoc.kr
```

결과가 Elastic IP와 같아야 합니다.

도메인을 Route 53으로 옮길 필요는 없습니다.
현재 도메인 구매처 DNS에서 A 레코드만 등록하면 됩니다.

## 6. 서버 접속

로컬에서 SSH 접속:

```bash
chmod 400 ~/Downloads/decisiondoc-admin-prod.pem
ssh -i ~/Downloads/decisiondoc-admin-prod.pem ubuntu@<elastic-ip>
```

키 파일 이름은 실제 다운로드한 이름으로 바꿉니다.

## 7. 서버 패키지 설치

Ubuntu 서버에서 아래 명령을 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y git curl openssl python3 ca-certificates
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

다시 SSH로 재접속합니다.

```bash
ssh -i ~/Downloads/decisiondoc-admin-prod.pem ubuntu@<elastic-ip>
docker --version
docker compose version
```

## 8. 코드 배치

```bash
sudo mkdir -p /opt
sudo chown -R ubuntu:ubuntu /opt
cd /opt
git clone https://github.com/sungjin9288/DecisionDoc-AI.git decisiondoc
cd /opt/decisiondoc
```

## 9. `.env.prod` 생성

권장 방식은 bootstrap 스크립트로 `.env.prod`를 바로 생성하는 것입니다.

```bash
python3 scripts/bootstrap_prod_env.py \
  --profile admin \
  --output .env.prod \
  --openai-api-key 'sk-...'
```

수동으로 생성하려면 템플릿 복사 후 값을 직접 넣습니다.

템플릿 복사:

```bash
cp docs/deployment/env_templates/admin.env .env.prod
```

키 생성:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

각 값을 아래에 넣습니다.

- 첫 번째: `JWT_SECRET_KEY`
- 두 번째: `DECISIONDOC_API_KEYS`
- 세 번째: `DECISIONDOC_OPS_KEY`

수동 편집:

```bash
vi .env.prod
```

최소 필수값:

```bash
DECISIONDOC_ENV=prod
DECISIONDOC_PROVIDER=openai
DECISIONDOC_STORAGE=local
JWT_SECRET_KEY=<generated-secret>
ALLOWED_ORIGINS=https://admin.decisiondoc.kr
DECISIONDOC_API_KEYS=<generated-api-key>
DECISIONDOC_OPS_KEY=<generated-ops-key>
OPENAI_API_KEY=<your-openai-key>
```

작성 직후 preflight 검증:

```bash
python3 scripts/check_prod_env.py \
  --env-file .env.prod \
  --expected-origin https://admin.decisiondoc.kr
```

## 10. 첫 부팅

`scripts/setup.sh` 는 아래를 자동으로 해줍니다.

- `data/` 생성
- `nginx/ssl/` 생성
- self-signed 인증서 생성

즉, 실제 Let's Encrypt 인증서가 오기 전에도 `nginx` 컨테이너를 부팅할 수 있게 준비합니다.

```bash
cd /opt/decisiondoc
bash scripts/setup.sh
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

정상 기준:

- `app` 컨테이너 `healthy`
- `nginx` 컨테이너 `running`
- `curl http://localhost:8000/health` 응답 200

repo 최신 소스를 다시 빌드해서 재배포할 때는 아래 helper를 사용합니다.

```bash
cd /opt/decisiondoc
python3 scripts/deploy_compose_local.py \
  --env-file .env.prod \
  --image decisiondoc-admin-local \
  --post-check
```

## 11. SSL 적용

DNS가 반영된 뒤 아래 명령을 실행합니다.

```bash
cd /opt/decisiondoc
sudo ./scripts/setup_ssl.sh admin.decisiondoc.kr <your-email>
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

확인:

```bash
curl -I https://admin.decisiondoc.kr/health
docker compose --env-file .env.prod -f docker-compose.prod.yml exec nginx nginx -t
```

정상 기준:

- `https://admin.decisiondoc.kr/health` 응답
- nginx 설정 테스트 통과
- `sudo crontab -l` 에 `certbot renew --quiet --deploy-hook '/opt/decisiondoc/scripts/refresh_ssl_certs.sh admin.decisiondoc.kr'` 가 보임
- `curl -I https://admin.decisiondoc.kr/health` 는 HEAD 특성상 `405` 가 나올 수 있지만, TLS handshake와 response header 확인 용도로는 정상입니다.

갱신 반영만 수동으로 다시 하고 싶으면 아래 helper를 직접 실행합니다.

```bash
cd /opt/decisiondoc
sudo ./scripts/refresh_ssl_certs.sh admin.decisiondoc.kr
```

## 12. 스모크 테스트

배포 서버에서는 아래 helper로 실제 운영 환경 기준 smoke를 실행합니다.

```bash
cd /opt/decisiondoc
python3 scripts/run_deployed_smoke.py --env-file .env.prod
```

이 스모크는 아래를 확인합니다.

- `/health`
- 인증 없는 `/generate` 차단
- 인증 있는 `/generate` 성공
- `/generate/export` 성공
- `/generate/from-documents` 업로드 성공

## 13. 운영 기본 체크

배포 후 아래 helper를 한 번 실행하면 health, compose 상태, nginx 설정, deployed smoke preflight, deployed smoke를 묶어서 확인할 수 있습니다.

```bash
cd /opt/decisiondoc
python3 scripts/post_deploy_check.py --env-file .env.prod
```

점검 결과를 파일로 남기려면 아래처럼 JSON 리포트를 같이 저장할 수 있습니다.

```bash
cd /opt/decisiondoc
python3 scripts/post_deploy_check.py --env-file .env.prod --report-file ./reports/post-deploy.json
```

히스토리를 같이 보관하려면 디렉터리 기준으로 실행합니다.

```bash
cd /opt/decisiondoc
python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy
```

이 경우 아래 파일들이 같이 갱신됩니다.

- `./reports/post-deploy/post-deploy-<timestamp>.json`
- `./reports/post-deploy/latest.json`
- `./reports/post-deploy/index.json`

최신 상태와 최근 이력을 콘솔에서 바로 보려면 아래 helper를 실행합니다.

```bash
cd /opt/decisiondoc
python3 scripts/show_post_deploy_reports.py --report-dir ./reports/post-deploy --latest
```

자동화 파서나 외부 스크립트에서 읽어야 하면 JSON 모드로 실행합니다.

```bash
cd /opt/decisiondoc
python3 scripts/show_post_deploy_reports.py --report-dir ./reports/post-deploy --latest --json
```

SSH 없이 브라우저나 API client에서 보려면 아래 endpoint를 사용합니다.

```text
GET https://admin.decisiondoc.kr/ops/post-deploy/reports?limit=5&latest=true

GET https://admin.decisiondoc.kr/ops/post-deploy/reports/post-deploy-20260414T041000Z.json

POST https://admin.decisiondoc.kr/ops/post-deploy/run
{"skip_smoke": false}
```

- 인증: `admin JWT` 또는 `X-DecisionDoc-Ops-Key`
- 용도: 최근 post-deploy history와 latest report detail을 JSON으로 바로 확인
- post-deploy run: 서버에서 `scripts/post_deploy_check.py` 실행 (ENV `DECISIONDOC_OPS_ALLOW_POST_DEPLOY_RUN=1` 필요, docker/compose 접근 가능한 호스트에서만 사용)

개별 확인이 필요하면 아래 4개를 순서대로 봅니다.

1. `https://admin.decisiondoc.kr/health`
2. `docker compose --env-file .env.prod -f docker-compose.prod.yml ps`
3. `docker compose --env-file .env.prod -f docker-compose.prod.yml logs app --tail=100`
4. `python3 scripts/run_deployed_smoke.py --env-file .env.prod`

## 14. 백업 / 복구 기준선

운영 baseline에는 데이터 백업과 복구 절차가 포함됩니다.

수동 백업:

```bash
cd /opt/decisiondoc
./scripts/backup.sh
ls -lt /backup/decisiondoc/
```

보존 기간을 줄이거나 늘리려면:

```bash
cd /opt/decisiondoc
BACKUP_KEEP_DAYS=14 ./scripts/backup.sh
```

권장 cron:

```bash
0 2 * * * /opt/decisiondoc/scripts/backup.sh >> /var/log/decisiondoc-backup.log 2>&1
```

복구:

```bash
cd /opt/decisiondoc
./scripts/restore.sh /backup/decisiondoc/data-YYYYMMDD-HHMMSS.tar.gz
```

복구 직후에는 아래를 다시 확인합니다.

1. `docker compose --env-file .env.prod -f docker-compose.prod.yml ps`
2. `curl https://admin.decisiondoc.kr/health`
3. `python3 scripts/run_deployed_smoke.py --env-file .env.prod`

## 15. 운영 키 보관 / rotation 상태

이 환경에서는 아래 3개를 따로 관리합니다.

- `DECISIONDOC_API_KEYS`
- `DECISIONDOC_OPS_KEY`
- `OPENAI_API_KEY`

기본 원칙:

- `DECISIONDOC_API_KEYS` 와 `DECISIONDOC_OPS_KEY` 는 같은 값으로 두지 않습니다.
- 키는 `.env.prod` 와 별도 운영 기록에만 남기고, 채팅/문서 본문에는 직접 복사하지 않습니다.
- rotation 절차는 [api_key_rotation_change_plan.md](./api_key_rotation_change_plan.md) 와 [prod_checklist.md](./prod_checklist.md) 기준으로 진행합니다.

## 16. 지금 당장 필요한 것

이 문서를 따라 진행하려면 아직 아래 값이 필요합니다.

1. AWS 계정 접근 권한
2. `admin.decisiondoc.kr` A 레코드를 수정할 수 있는 DNS 계정 접근 권한
3. Let's Encrypt 발급에 사용할 이메일 주소
4. `OPENAI_API_KEY`

## 17. 참고 문서

- EC2 getting started: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html>
- Elastic IP: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html>
- Route 53 routing concepts: <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-to-aws-resources.html>
- Repo DNS guide: `docs/deployment/dns_setup_decisiondoc_kr.md`
- Repo multi-site guide: `docs/deployment/multi_site_operations.md`
- Repo handoff index: `docs/deployment/admin_v1_handoff.md`

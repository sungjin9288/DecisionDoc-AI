# `dawool.decisiondoc.kr` 고객 전용 배포 Runbook

이 문서는 `dawool.decisiondoc.kr` 를 고객 전용 환경으로 배포할 때 필요한 값, 실행 순서, 점검 항목, 컷오버 체크리스트를 한 번에 정리한 runbook입니다.

실제 입력값과 실행 결과는 아래 worksheet에 같이 기록하는 것을 권장합니다.

- `docs/deployment/dawool_rollout_worksheet.md`

현재 기준은 아래를 전제로 합니다.

- 공용 운영/데모 환경: `admin.decisiondoc.kr`
- 고객 전용 환경: `dawool.decisiondoc.kr`
- 배포 방식: Docker Compose
- 저장 방식: `DECISIONDOC_STORAGE=local`
- SSL: Let's Encrypt

이 문서는 이미 검증된 `admin` 배포 절차를 고객 전용 환경에 그대로 복제하는 흐름으로 작성합니다.

## 1. 먼저 결정해야 할 것

배포 전에 아래 5개를 먼저 확정합니다.

1. `dawool` 서버 위치
   - 온프레미스 서버
   - 고객사 VM
   - 별도 클라우드 VM

2. `dawool` 서버 공인 IP
   - DNS `A` 레코드 연결에 필요

3. `dawool`용 OpenAI API 키
   - `admin`과 분리할지 여부 포함

4. `dawool` 운영 책임자
   - 현재는 운영자 1인 관리 기준

5. 운영 데이터 보관 방식
   - 로컬 볼륨 유지
   - 백업 경로 별도 정의 여부

## 2. 준비해야 할 값

아래 값은 `dawool` 환경 전용으로 새로 준비합니다.

| 항목 | 설명 | 생성/확인 방법 |
|------|------|----------------|
| `JWT_SECRET_KEY` | 세션/JWT 서명용 키 | `openssl rand -hex 32` |
| `DECISIONDOC_API_KEYS` | 고객 환경 API 키 | `openssl rand -hex 32` |
| `DECISIONDOC_OPS_KEY` | 운영용 키 | `openssl rand -hex 32` |
| `OPENAI_API_KEY` | 실제 OpenAI 키 | OpenAI 콘솔 |
| `ALLOWED_ORIGINS` | 고객 환경 도메인 | `https://dawool.decisiondoc.kr` |
| `dawool` 공인 IP | DNS 연결값 | 서버/VM 할당값 |

주의:

- `DECISIONDOC_API_KEYS` 와 `DECISIONDOC_OPS_KEY` 는 반드시 다른 값이어야 합니다.
- `admin` 환경과 키를 공유하지 않는 것을 권장합니다.

## 3. DNS 연결

도메인 DNS에서 아래 레코드를 추가합니다.

| Type | Host | Value |
|------|------|-------|
| A | `dawool` | `<dawool-public-ip>` |

확인:

```bash
dig +short dawool.decisiondoc.kr
```

결과가 `dawool` 서버 공인 IP와 같아야 합니다.

## 4. 서버 기본 준비

Ubuntu 계열 서버 기준:

```bash
sudo apt-get update
sudo apt-get install -y git curl openssl python3 ca-certificates
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

다시 로그인 후 확인:

```bash
docker --version
docker compose version
```

## 5. 코드 배치

```bash
sudo mkdir -p /opt
sudo chown -R $USER:$USER /opt
cd /opt
git clone https://github.com/sungjin9288/DecisionDoc-AI.git decisiondoc
cd /opt/decisiondoc
```

## 6. `.env.prod` 작성

템플릿 복사:

```bash
cp docs/deployment/env_templates/dawool.env .env.prod
```

최소 필수값:

```env
DECISIONDOC_ENV=prod
DECISIONDOC_PROVIDER=openai
DECISIONDOC_STORAGE=local
JWT_SECRET_KEY=<generated-secret>
ALLOWED_ORIGINS=https://dawool.decisiondoc.kr
DECISIONDOC_API_KEYS=<generated-api-key>
DECISIONDOC_OPS_KEY=<generated-ops-key>
OPENAI_API_KEY=<real-openai-key>
```

## 7. 첫 부팅

초기 self-signed 인증서와 데이터 경로를 준비한 뒤 부팅합니다.

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

## 8. 고객 환경은 로컬 빌드 기준으로 맞추는 것을 권장

현재 `admin` 환경은 repo 최신 상태를 직접 빌드해서 검증했습니다.
따라서 `dawool`도 최초 배포 시에는 GHCR 기본 이미지 대신, 같은 commit 기준으로 로컬 빌드해서 올리는 것을 권장합니다.

```bash
cd /opt/decisiondoc
export DOCKER_IMAGE=decisiondoc-dawool-local
docker build -t "$DOCKER_IMAGE" .
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate
```

이 방식의 장점:

- `admin`과 동일한 소스 기준으로 맞추기 쉬움
- 아직 registry 태그와 실제 운영 commit이 어긋나는 상황을 피하기 쉬움
- 고객 환경 첫 배포에서 drift를 줄일 수 있음

## 9. SSL 적용

DNS가 반영된 뒤 실행:

```bash
cd /opt/decisiondoc
sudo ./scripts/setup_ssl.sh dawool.decisiondoc.kr <operator-email>
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yml exec nginx nginx -t
curl -s https://dawool.decisiondoc.kr/health
```

정상 기준:

- Let's Encrypt 발급 성공
- `nginx -t` 성공
- `https://dawool.decisiondoc.kr/health` 정상 JSON 응답

## 10. 스모크 테스트

고객 환경에서는 반드시 실제 도메인 기준으로 스모크를 한 번 실행합니다.

```bash
cd /opt/decisiondoc
SMOKE_API_KEY="$(grep '^DECISIONDOC_API_KEYS=' .env.prod | cut -d= -f2- | cut -d, -f1)"
docker compose --env-file .env.prod -f docker-compose.prod.yml exec \
  -e SMOKE_BASE_URL=https://dawool.decisiondoc.kr \
  -e SMOKE_API_KEY="$SMOKE_API_KEY" \
  -e SMOKE_PROVIDER=openai \
  app python scripts/smoke.py
```

정상 기준:

- `GET /health -> 200`
- `POST /generate (no key) -> 401`
- `POST /generate (auth) -> 200`
- `POST /generate/export (auth) -> 200`

## 11. 컷오버 전 체크리스트

아래 항목이 모두 맞아야 고객 환경을 열어도 됩니다.

- `dawool.decisiondoc.kr` DNS 응답 정상
- HTTPS 인증서 정상
- `.env.prod` 값이 `admin`과 다름
- `DECISIONDOC_API_KEYS` / `DECISIONDOC_OPS_KEY` 가 `admin`과 다름
- health 정상
- smoke 정상
- 운영 로그 위치와 백업 정책 확인

## 12. 컷오버 후 체크리스트

배포 후 실제 사용 직전 아래를 다시 확인합니다.

1. 브라우저에서 `https://dawool.decisiondoc.kr` 접속
2. 로그인 또는 운영자 접근 흐름 확인
3. 문서 생성 1회 확인
4. export 1회 확인
5. app/nginx 로그 tail 확인
6. 고객 전달용 접속 URL과 운영 키 보관 상태 확인

## 13. 운영자 메모

- `admin` 은 공용 운영/데모 환경으로 설명
- `dawool` 은 고객 전용 분리 환경으로 설명
- 같은 날 두 환경을 함께 점검할 때는 항상 `admin` 먼저, `dawool` 나중 순서로 진행
- 장애 범위가 섞이지 않도록 `.env.prod`, 키, 데이터 백업을 반드시 따로 관리

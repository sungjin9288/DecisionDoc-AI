# Docker 배포 가이드

## 개발 환경
```bash
# 1. 설정
./scripts/setup.sh

# 2. .env 확인
vi .env

# 3. 실행
docker compose up -d

# 4. 헬스체크
curl http://localhost:3300/health

# 5. 로그 확인
docker compose logs -f app
```

- 개발용 Compose는 `docker-compose.yml` 기준으로 `3300:8000` 포트를 사용합니다.
- 브라우저 접속 주소는 `http://localhost:3300` 입니다.

## 프로덕션 배포
```bash
# 1. 프로덕션 환경 파일 준비
cp .env.example .env.prod
vi .env.prod

# 필수 예시
# DECISIONDOC_ENV=prod
# ENVIRONMENT=production
# JWT_SECRET_KEY=<32bytes+>
# ALLOWED_ORIGINS=https://your-domain.com
# DECISIONDOC_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# 2. 배포
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 3. 확인
curl http://localhost:8000/health
docker compose -f docker-compose.prod.yml ps
```

GHCR 이미지 태그를 명시적으로 배포할 때는 `scripts/deploy.sh` 를 사용할 수 있습니다.

```bash
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export ALLOWED_ORIGINS=https://your-domain.com
./scripts/deploy.sh production v1.0.0
```

- `scripts/deploy.sh` 는 `docker-compose.prod.yml` 를 사용하고, 내부적으로 health check까지 수행합니다.
- AWS Lambda/SAM 경로는 이 문서가 아니라 [../deploy_aws.md](../deploy_aws.md)를 사용합니다.

## 온프레미스 (로컬 LLM)
```bash
# Ollama 포함 실행
docker compose --profile local-llm up -d

# 모델 다운로드
docker compose exec ollama ollama pull llama3.1:8b
```

## 헬스체크
```bash
curl http://localhost:3300/health   # 개발 Compose
curl http://localhost:8000/health   # 프로덕션 Compose
```

## 로그
```bash
docker compose logs app --tail=100 -f
docker compose -f docker-compose.prod.yml logs app --tail=100 -f
```

## 운영 체크리스트 (Docker)
- `.env` / `.env.prod` 에 `JWT_SECRET_KEY`(32bytes 이상)와 `ALLOWED_ORIGINS` 를 반드시 설정
- `DECISIONDOC_PROVIDER`와 provider API 키(`OPENAI_API_KEY` 등) 확인
- `DECISIONDOC_STORAGE=local` 기준이면 `decisiondoc_data` 볼륨 백업 정책 수립
- 헬스체크: `curl http://localhost:3300/health` 또는 `http://localhost:8000/health`
- smoke: `python scripts/smoke.py` (필요 시 `python scripts/ops_smoke.py`)
- 감사 로그는 `data/tenants/<tenant_id>/audit_logs.jsonl` (볼륨 내)로 저장됨

여러 장소로 분리 운영할 때는 [Multi-site 운영 가이드](multi_site_operations.md)를 확인하세요.

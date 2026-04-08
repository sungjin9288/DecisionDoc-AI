# High Availability (HA) 배포 가이드

## 아키텍처

```
인터넷 -> Nginx (Load Balancer)
              | least_conn
    +---------+---------+
  app:1     app:2     app:3
    +---------+---------+
              |
      /app/data (공유 볼륨)
```

## 실행

```bash
# HA 모드로 시작 (.env.prod 사용 권장)
docker compose --env-file .env.prod -f docker-compose.ha.yml up -d --scale app=3

# 상태 확인
./scripts/ha_check.sh docker-compose.ha.yml 3

# 스케일 조정
docker compose --env-file .env.prod -f docker-compose.ha.yml up -d --scale app=5
```

## 롤링 업데이트

```bash
# 새 이미지 태그 지정 후 롤링 업데이트
export DOCKER_IMAGE=ghcr.io/sungjin9288/decisiondoc-ai:v1.0.1
docker compose --env-file .env.prod -f docker-compose.ha.yml up -d --scale app=3
```

## 롤백

```bash
export DOCKER_IMAGE=ghcr.io/sungjin9288/decisiondoc-ai:<previous_tag>
docker compose --env-file .env.prod -f docker-compose.ha.yml up -d --scale app=3
```

- `docker compose rollback` 명령은 사용하지 않습니다.
- 실제 롤백은 이전 정상 이미지 태그로 다시 `up -d` 하는 방식으로 수행합니다.

## 모니터링

```bash
# 레플리카 상태
docker compose -f docker-compose.ha.yml ps

# 실시간 로그 (모든 레플리카)
docker compose -f docker-compose.ha.yml logs -f app

# 리소스 사용량
docker stats $(docker compose -f docker-compose.ha.yml ps -q app)
```

## RTO / RPO

| 항목 | 목표 | 구현 방법 |
|------|------|-----------|
| RTO (복구 시간) | 4시간 | 자동 재시작 + 롤링 업데이트 |
| RPO (데이터 손실) | 24시간 | 일별 볼륨 스냅샷 |
| 가용성 | 99.5%+ | 3레플리카 + Nginx 헬스체크 |

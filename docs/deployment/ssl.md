# SSL/TLS 설정 가이드

## Let's Encrypt (권장)

```bash
# 프로덕션 환경 파일 준비
cp .env.example .env.prod
vi .env.prod

# 인증서 발급
./scripts/setup_ssl.sh your-domain.com admin@company.kr

# 프로덕션 nginx 시작/재시작
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d nginx
```

자동으로 처리되는 사항:
- SSL 인증서 발급 (90일 유효)
- Nginx 설정 업데이트
- 매일 새벽 3시 자동 갱신 크론 등록

## 기관 발급 인증서

```bash
# 1. 인증서 파일을 nginx/ssl/ 에 복사
cp your-cert.pem nginx/ssl/cert.pem
cp your-key.pem nginx/ssl/key.pem
chmod 600 nginx/ssl/key.pem

# 2. nginx 설정 적용
cp nginx/nginx.ssl.conf nginx/nginx.conf
docker compose --env-file .env.prod -f docker-compose.prod.yml restart nginx
```

- 수동 인증서 적용은 `docker-compose.prod.yml` 기반 nginx 운영을 전제로 합니다.
- 개발용 `docker-compose.yml` 에는 nginx 서비스가 없으므로 이 절차를 그대로 사용하지 않습니다.

## SSL 검증

```bash
# 인증서 만료일 확인
openssl x509 -enddate -noout -in nginx/ssl/cert.pem

# TLS 버전 확인
curl -v --tlsv1.2 https://your-domain.com/health 2>&1 | grep TLS

# nginx 설정 문법 확인
docker compose --env-file .env.prod -f docker-compose.prod.yml exec nginx nginx -t
```

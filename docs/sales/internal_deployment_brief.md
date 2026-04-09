# DecisionDoc AI 내부 설치형 도입 설명서

## 1. 권장 운영 구조

현재 권장 구조는 웹 브라우저 기반 내부 설치형 운영입니다.
사용자는 브라우저로 접속하고, 서비스는 고객사 서버 또는 지정된 장비에서 Docker Compose로 실행합니다.

## 2. 이번 운영 시나리오

운영 대상은 아래 3개 장소입니다.

- 사무실
- 회사 A
- 회사 B

세 장소는 서로 완전히 분리된 네트워크로 가정합니다.

따라서 권장 구조는 **한 개의 루트 도메인 + 장소별 서브도메인 + 장소별 독립 배포**입니다.

예시:

- `office.decisiondoc.kr`
- `company-a.decisiondoc.kr`
- `company-b.decisiondoc.kr`

## 3. 왜 분리 운영이 필요한가

- 한 장소의 장애가 다른 장소에 영향을 주지 않게 하기 위해
- 고객사별 데이터가 섞이지 않게 하기 위해
- 키 유출이나 설정 실수가 전체 환경으로 번지지 않게 하기 위해
- 고객사별 유지보수 일정을 독립적으로 가져가기 위해

## 4. 운영 방식

각 장소는 동일한 코드 버전을 사용하되, 아래 항목은 반드시 분리합니다.

- `.env.prod`
- `DECISIONDOC_API_KEYS`
- `DECISIONDOC_OPS_KEY`
- `JWT_SECRET_KEY`
- 데이터 볼륨
- 도메인/서브도메인

필요 시 OpenAI API 키도 장소별로 분리할 수 있습니다.

## 5. 보안/권한/로그 포인트

### 권한

- 사용자 인증: JWT
- 역할 기반 접근 제어: admin / member / viewer
- 운영 엔드포인트 보호: `DECISIONDOC_OPS_KEY`

### 로그

- 감사 로그 위치: `data/tenants/<tenant_id>/audit_logs.jsonl`
- 운영 로그: Docker logs 또는 CloudWatch
- 로그는 운영 추적과 사고 대응 기준으로 활용

### 키 관리

- 각 장소별로 별도 키 발급
- 키 교체는 순차 진행
- 운영자만 키 보관 및 변경 권한 보유

## 6. 설치 방식

기본 설치 방식은 Docker Compose입니다.

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
curl http://localhost:8000/health
python3 scripts/smoke.py
```

각 장소별 템플릿은 아래 문서를 사용합니다.

- `docs/deployment/env_templates/office.env`
- `docs/deployment/env_templates/company_a.env`
- `docs/deployment/env_templates/company_b.env`

도메인/DNS 설정은 아래 문서를 기준으로 진행합니다.

- `docs/deployment/dns_setup_decisiondoc_kr.md`

## 7. 운영자 관점의 장점

- 고객사별 독립 운영이 쉬움
- 배포/점검 절차를 표준화하기 좋음
- 사고 범위를 한 장소로 제한 가능
- 감사 및 보안 설명이 쉬움
- SaaS 의존보다 내부 통제 설명이 명확함

## 8. 고객 설명용 문구

DecisionDoc AI는 외부 SaaS에 민감 문서를 올려서 쓰는 방식이 아니라, 고객사 환경에 맞게 내부 설치형으로 운영할 수 있는 문서 생성 플랫폼입니다.
필요하면 사무실, 회사 A, 회사 B처럼 장소별로 완전히 분리된 구조로 운영할 수 있어 데이터 통제와 운영 안정성을 동시에 확보할 수 있습니다.

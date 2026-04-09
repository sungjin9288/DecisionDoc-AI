# Multi-site 운영 가이드 (`admin` + `dawool`)

이 문서는 `admin` 환경과 `dawool` 환경의 2개 운영 구성을 기준으로 DecisionDoc AI를 운영하는 절차를 정리합니다.
권장 방향은 운영자 공용 환경과 고객 전용 환경을 분리하고, 각 환경마다 독립된 배포 스택, 독립된 키, 독립된 데이터 저장소를 유지하는 것입니다.

---

## 운영 원칙 (요약)

1. 운영 분리: `admin`과 `dawool`의 환경/데이터/키를 분리
2. 독립 운영: 한 환경의 장애나 키 유출이 다른 환경에 영향 주지 않게 설계
3. 일관 버전: 동일 버전 릴리즈를 두 환경에 순차 배포
4. 중앙 관리: 운영자 1인이 배포, 키, 점검, 백업을 관리

---

## 권장 배포 모델

각 환경에 아래 구성을 **독립적으로** 배포합니다.

- 배포 방식: Docker Compose (on-prem 서버/VM)
- 저장소: `DECISIONDOC_STORAGE=local`
- 데이터 볼륨: 환경별로 다른 `decisiondoc_data` 볼륨
- API 키: 환경별로 서로 다른 `DECISIONDOC_API_KEYS` / `DECISIONDOC_OPS_KEY`

추가로, 내부 규정이 허용되면 환경별 S3 버킷을 사용하는 것도 가능합니다.
이 경우에도 버킷/접근 권한은 반드시 환경별로 분리합니다.

---

## 환경별 환경 파일 템플릿

각 환경마다 `.env.prod` 파일을 분리합니다.
아래 템플릿을 기반으로 두 환경에 각각 값을 채웁니다.

필수 값 생성/확인 방법은 다음 섹션에 정리되어 있습니다.

템플릿 샘플 파일:
- `docs/deployment/env_templates/admin.env`
- `docs/deployment/env_templates/dawool.env`

실제 고객 전용 배포 절차는 아래 문서를 함께 사용합니다.

- `docs/deployment/dawool_rollout_runbook.md`
- `docs/deployment/dawool_rollout_worksheet.md`

### 공통 템플릿

```bash
DECISIONDOC_ENV=prod
DECISIONDOC_PROVIDER=openai
DECISIONDOC_STORAGE=local
JWT_SECRET_KEY=<32bytes+>
ALLOWED_ORIGINS=https://<site-domain>
DECISIONDOC_API_KEYS=<comma-separated-keys>
DECISIONDOC_OPS_KEY=<ops-key>
OPENAI_API_KEY=<openai-api-key>
```

---

## 준비해야 할 값 (운영자 체크리스트)

아래 값은 환경별로 분리해서 준비합니다.

1. `JWT_SECRET_KEY`
   - 사용자 인증/세션 암호화용 비밀 키
   - 생성 예시: `openssl rand -hex 32`

2. `DECISIONDOC_API_KEYS`
   - API 접근용 키 목록
   - 환경별로 서로 다른 키 사용 권장
   - 키 형식은 임의 문자열(길이 32자 이상 권장)

3. `DECISIONDOC_OPS_KEY`
   - `/ops/*` 엔드포인트 접근용 키
   - 환경별로 서로 다른 키 사용 권장

4. `OPENAI_API_KEY`
   - OpenAI API 키
   - `admin`과 `dawool`을 완전히 나누려면 환경별 별도 키 사용 권장
   - 단일 키를 써도 되지만 사용량 모니터링 기준은 분리 관리

5. `ALLOWED_ORIGINS`
   - 프론트엔드 도메인
   - 현재 권장값:
     - `admin`: `https://admin.decisiondoc.kr`
     - `dawool`: `https://dawool.decisiondoc.kr`
   - 환경별 도메인을 정확히 지정

6. DNS 레코드
   - `admin.decisiondoc.kr`
   - `dawool.decisiondoc.kr`
   - 상세 절차: `docs/deployment/dns_setup_decisiondoc_kr.md`

7. env preflight 검증
   - `.env.prod` 작성 직후 `python3 scripts/check_prod_env.py --env-file .env.prod --expected-origin https://<site-domain>` 실행
   - placeholder 미치환, OpenAI 키 오기입, API/OPS 키 중복, origin mismatch를 컷오버 전에 차단

---

## 배포 절차 (환경별 반복)

```bash
# 1. 코드 배포
git clone https://github.com/sungjin9288/DecisionDoc-AI.git
cd DecisionDoc-AI

# 2. 프로덕션 환경 파일 준비
cp .env.example .env.prod
vi .env.prod  # 환경별 값 입력

# 3. 배포
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 4. 헬스체크
curl http://localhost:8000/health

# 5. 기본 스모크
python3 scripts/smoke.py
```

---

## 점검 / 운영 체크리스트 (환경별)

- 헬스체크: `curl http://localhost:8000/health`
- API 스모크: `python3 scripts/smoke.py`
- ops 스모크: `python3 scripts/ops_smoke.py` (필요 시)
- 감사 로그 위치: `data/tenants/<tenant_id>/audit_logs.jsonl`
- 데이터 백업: `decisiondoc_data` 볼륨을 주기적으로 백업

---

## 업데이트/롤백 절차

### 업데이트
```bash
git pull
docker compose -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
python3 scripts/smoke.py
```

### 롤백
```bash
# 이전 버전 태그로 배포
export JWT_SECRET_KEY=<same-as-prod>
export ALLOWED_ORIGINS=<same-as-prod>
./scripts/deploy.sh production <previous-tag>
```

---

## 중앙 운영자 (1인 관리) 운영 팁

- 배포/점검/키 로테이션은 `admin` 후 `dawool` 순서로 진행
- 각 환경의 `.env.prod` 파일은 별도 보관
- 키 로테이션 변경 계획: `docs/deployment/api_key_rotation_change_plan.md`
- 운영 체크리스트(장애 대응 포함): `docs/deployment/prod_checklist.md`
- 고객 전용 rollout 순서와 컷오버 점검표: `docs/deployment/dawool_rollout_runbook.md`
- 고객 전용 입력값/진행 기록 시트: `docs/deployment/dawool_rollout_worksheet.md`

---

## 환경 분리 체크 (필수)

1. `admin`과 `dawool`의 `.env.prod` 파일이 서로 다름
2. `DECISIONDOC_API_KEYS` / `DECISIONDOC_OPS_KEY`가 서로 다름
3. `decisiondoc_data` 볼륨 공유 없음
4. OpenAI API 사용량/계정 분리 정책 확정

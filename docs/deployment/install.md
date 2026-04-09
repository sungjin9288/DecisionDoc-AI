# DecisionDoc AI 설치 가이드

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| CPU | 2 core | 4 core |
| RAM | 2 GB | 8 GB |
| 디스크 | 20 GB | 100 GB SSD |
| Docker | 24.0+ | 최신 |
| 네트워크 | 인터넷 연결 | 인터넷 연결 |

---

## 1. 빠른 설치 (Docker)

```bash
# 1. 저장소 클론
git clone https://github.com/sungjin9288/DecisionDoc-AI.git
cd DecisionDoc-AI

# 2. 초기 설정 (자동)
chmod +x scripts/*.sh
./scripts/setup.sh

# 3. API 키 설정
vi .env
# OPENAI_API_KEY=sk-... 입력

# 4. 서비스 시작
docker compose up -d

# 5. 접속 확인
curl http://localhost:3300/health
```

브라우저에서 `http://localhost:3300` 접속

---

## 배포 경로 선택 기준 (Docker vs AWS SAM)

| 구분 | Docker Compose | AWS SAM/Lambda |
|------|----------------|----------------|
| 운영 난이도 | 내부 서버 1~2대 기준 빠르게 운영 가능 | AWS 계정/IAM/OIDC 설정 필요 |
| 배포 방식 | VM/서버에 `docker compose`로 배포 | GitHub Actions + SAM deploy |
| 확장성 | 수평 확장은 운영자가 직접 구성 | Lambda 자동 확장 |
| 로그/관측 | Docker logs/호스트 로그 | CloudWatch 기반 |
| 권한 통제 | 서버 접근 권한 중심 | IAM 역할/정책 중심 |
| 추천 상황 | 온프레미스/내부망, 빠른 PoC/내부 운영 | SaaS/다중 환경 운영, 배포 규율 필요 |

선택 요약:
- 내부망/간단 운영이면 Docker 경로가 가장 빠릅니다.
- 배포 권한 분리, 자동 확장, stage/prod 분리 운영이 필요하면 AWS SAM 경로를 사용합니다.

AWS 배포 세부 절차는 [deploy_aws.md](../deploy_aws.md)를 따릅니다.

여러 환경(`admin` / `dawool`)으로 분리 운영할 경우에는
[Multi-site 운영 가이드](multi_site_operations.md)를 먼저 확인하세요.

---

## 2. 최초 관리자 계정 생성

```bash
curl -X POST http://localhost:3300/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "display_name": "관리자",
    "email": "admin@company.kr",
    "password": "안전한비밀번호123!"
  }'
```

---

## 3. 프로덕션 배포

```bash
# SSL 인증서 설정
./scripts/setup_ssl.sh your-domain.com admin@company.kr

# 프로덕션 환경 변수 설정
cp .env.example .env.prod
vi .env.prod  # 실제 값 입력

# 프로덕션 시작
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 프로덕션 헬스체크
curl http://localhost:8000/health
```

---

## 4. 온프레미스 (로컬 LLM)

인터넷 차단 환경에서 Ollama로 운영:

```bash
# Ollama 설치
curl -fsSL https://ollama.ai/install.sh | sh

# 모델 다운로드 (인터넷 연결 시)
ollama pull llama3.1:8b

# .env 설정
DECISIONDOC_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3.1:8b

# 서비스 시작
docker compose up -d
```

---

## Voice Brief 연동 설정

기존 프로젝트 상세 화면에서 Voice Brief summary를 바로 가져오려면 아래 환경변수를 추가합니다.

```bash
VOICE_BRIEF_API_BASE_URL=https://voice-brief.example.com
VOICE_BRIEF_API_BEARER_TOKEN=vb_xxx
VOICE_BRIEF_TIMEOUT_SECONDS=10.0
```

- `VOICE_BRIEF_API_BASE_URL` 이 비어 있으면 import 호출은 가능하지만 `voice_brief_not_configured` 를 반환합니다.
- `VOICE_BRIEF_API_BEARER_TOKEN` 은 upstream이 bearer auth를 요구할 때만 설정합니다.
- `VOICE_BRIEF_TIMEOUT_SECONDS` 는 upstream document-package 요청 timeout입니다.

사용 방법:

1. 웹 UI에서 `프로젝트` 탭으로 이동합니다.
2. 대상 프로젝트 상세를 엽니다.
3. `Voice Brief 요약 가져오기` 카드에서 `Recording ID` 를 입력합니다.
4. 특정 summary revision이 필요하면 `Revision ID` 를 함께 입력합니다.
5. `가져오기` 를 누르면 기존 endpoint `POST /projects/{project_id}/imports/voice-brief` 가 호출됩니다.

실패 시 주요 에러:

- `stale_summary`: 최신 summary가 아님
- `unapproved_summary`: summary 승인 전 상태
- `voice_brief_not_found`: upstream recording/revision 없음
- `voice_brief_upstream_error`: upstream 장애 또는 일시 오류

---

## Native Meeting Recording 설정

프로젝트 안에서 직접 회의 녹음 파일을 업로드하고, OpenAI transcription으로 전사한 뒤 `meeting_minutes_kr` / `project_report_kr`를 생성하려면 아래 값을 설정합니다.

```bash
OPENAI_API_KEY=sk-...
OPENAI_API_BASE_URL=https://api.openai.com/v1
MEETING_RECORDING_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
MEETING_RECORDING_MAX_UPLOAD_BYTES=26214400
MEETING_RECORDING_CONTEXT_CHAR_LIMIT=12000
```

- `OPENAI_API_KEY` 가 비어 있으면 업로드는 가능하지만 전사 endpoint는 `meeting_recording_transcription_not_configured` 를 반환합니다.
- `OPENAI_API_BASE_URL` 은 OpenAI-compatible proxy를 쓸 때만 override 합니다. 비어 있으면 기본 OpenAI endpoint를 사용합니다.
- `MEETING_RECORDING_MAX_UPLOAD_BYTES` 기본값은 25MB이며, OpenAI transcription 업로드 제한과 맞춰 둡니다.
- `MEETING_RECORDING_CONTEXT_CHAR_LIMIT` 은 승인된 transcript 중 문서 생성 prompt에 넣는 최대 길이입니다.

사용 방법:

1. 웹 UI에서 `프로젝트` 탭으로 이동합니다.
2. 대상 프로젝트 상세를 엽니다.
3. `회의 녹음 업로드` 카드에서 파일을 올립니다.
4. `전사 실행`으로 transcript를 생성합니다.
5. transcript 내용을 확인한 뒤 `전사 승인`을 누릅니다.
6. `회의록/보고서 생성`을 누르면 프로젝트 문서 목록에 결과가 연결됩니다.

---

## 5. 업그레이드

```bash
git pull
docker compose pull
docker compose up -d
```

---

## 6. 제거

```bash
docker compose down -v  # 데이터 포함 삭제
# 또는
docker compose down     # 데이터 보존
```

---

## 문제 해결

| 증상 | 해결 |
|------|------|
| 포트 8000 충돌 | `docker compose down` 후 재시작 |
| 메모리 부족 | 스왑 설정: `fallocate -l 4G /swapfile` |
| PDF 생성 실패 | `docker compose exec app playwright install chromium` |
| LDAP 연결 실패 | 방화벽에서 389/636 포트 허용 확인 |

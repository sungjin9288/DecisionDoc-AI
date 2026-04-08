# CLAUDE.md — DecisionDoc AI

의사결정 문서(ADR, One-pager, Eval Plan, Ops Checklist)를 LLM으로 자동 생성하는 FastAPI 서버. AWS Lambda(Mangum) 위에서 동작하며, Provider·Storage를 환경변수로 교체 가능한 플러그인 아키텍처를 사용한다.

---

## Tech Stack

| 구분 | 기술 | 비고 |
|------|------|------|
| Runtime | Python 3.12 | SAM 배포 시 python3.11 |
| Web Framework | FastAPI | ASGI |
| Data Validation | Pydantic v2 (`>=2,<3`) | strict 모드 기본 |
| Template Engine | Jinja2 | `.md.j2` 파일 |
| ASGI Server | uvicorn[standard] | 로컬 개발 |
| Lambda Adapter | Mangum | `app.aws_lambda.handler` |
| HTTP Client | httpx | 테스트용 |
| Test Framework | pytest | |
| Config | python-dotenv | `.env` 로드 |
| Infrastructure | AWS SAM (CloudFormation) | `infra/sam/template.yaml` |
| Storage | 로컬 파일 or AWS S3 | 환경변수로 선택 |
| LLM Providers | OpenAI / Google Gemini / Mock | 환경변수로 선택 |
| Ops | AWS CloudWatch + Statuspage.io | |

---

## 디렉토리 구조

```
app/
├── main.py                  # FastAPI 앱 생성·라우트 정의, create_app() 진입점
├── aws_lambda.py            # Lambda 핸들러: handler = Mangum(app)
├── schemas.py               # 전체 Pydantic 요청/응답 모델 (단일 파일)
├── providers/
│   ├── base.py              # Provider ABC + UsageTokenMixin
│   ├── factory.py           # get_provider() — 환경변수로 구현체 선택
│   ├── openai_provider.py   # OpenAI 연동 (anyio 타임아웃 20s)
│   ├── gemini_provider.py   # Google Gemini 연동
│   ├── mock_provider.py     # 정적 응답, 외부 API 없음 (개발·테스트용)
│   └── stabilizer.py        # 번들 안정화 및 스키마 검증 후처리
├── storage/
│   ├── base.py              # Storage ABC (save_bundle, load_bundle, save_export …)
│   ├── factory.py           # get_storage() — local / s3 선택
│   ├── local.py             # 파일 기반 스토리지, atomic write
│   ├── s3.py                # AWS S3 스토리지 (boto3 lazy import)
├── services/
│   └── generation_service.py  # 핵심 파이프라인 오케스트레이션
├── domain/
│   └── schema.py            # BUNDLE_JSON_SCHEMA_V1 정의
├── middleware/
│   ├── observability.py     # 요청/응답 구조화 로깅 미들웨어
│   └── request_id.py        # X-Request-Id 헤더 주입·검증
├── auth/
│   ├── api_key.py           # X-DecisionDoc-Api-Key HMAC 검증
│   └── ops_key.py           # /ops/* 엔드포인트용 인증
├── observability/
│   ├── logging.py           # JSON 로그 포매터, log_event(), setup_logging()
│   └── timing.py            # Timer 컨텍스트 매니저
├── ops/
│   ├── service.py           # CloudWatch 조사, Statuspage 연동, S3 리포트
│   ├── factory.py           # get_ops_service()
│   └── statuspage.py        # Statuspage.io API 클라이언트
├── eval/                    # 오프라인 품질 평가 파이프라인 (python -m app.eval)
├── eval_live/               # 실제 Provider로 live 평가 (python -m app.eval_live)
├── maintenance/
│   └── mode.py              # is_maintenance_mode(), require_not_maintenance
├── api/
│   └── exception_handlers.py  # 전역 예외 → JSON 응답 변환
└── templates/
    └── v1/                  # Jinja2 템플릿 (.md.j2)
        ├── adr.md.j2
        ├── onepager.md.j2
        ├── eval_plan.md.j2
        └── ops_checklist.md.j2

infra/sam/template.yaml      # AWS SAM 배포 정의
tests/                       # pytest 테스트 슈트
scripts/
├── smoke.py                 # 기본 엔드포인트 스모크 테스트
└── ops_smoke.py             # Ops 서비스 스모크 테스트
```

---

## 빌드 & 실행 명령어

```bash
# 의존성 설치
pip install -r requirements.txt

# 로컬 개발 서버 (hot reload)
python -m uvicorn app.main:app --reload

# 테스트 전체 실행
pytest tests/

# 실제 Provider API 호출 포함 테스트 (네트워크 필요)
pytest tests/ -m live

# 오프라인 품질 평가
python -m app.eval

# Live Provider 평가
python -m app.eval_live

# AWS SAM 로컬 테스트
sam local start-api -t infra/sam/template.yaml

# AWS SAM 배포
sam deploy --guided --template-file infra/sam/template.yaml

# 스모크 테스트 (서버 실행 후)
python scripts/smoke.py
python scripts/ops_smoke.py
```

---

## 환경 변수

`.env.example` 참조. 핵심 변수:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DECISIONDOC_PROVIDER` | `mock` | `mock` \| `openai` \| `gemini` |
| `DECISIONDOC_ENV` | `dev` | `dev` \| `prod` (prod에서 docs_url 비활성화) |
| `DECISIONDOC_API_KEYS` | — | 콤마 구분 API 키 목록 |
| `DECISIONDOC_API_KEY` | — | 단일 API 키 (레거시) |
| `DECISIONDOC_OPS_KEY` | — | `/ops/*` 인증 키 |
| `DECISIONDOC_STORAGE` | `local` | `local` \| `s3` |
| `DECISIONDOC_S3_BUCKET` | — | S3 사용 시 필수 |
| `DECISIONDOC_MAINTENANCE` | `0` | 유지보수 모드 (`1`/`true`/`yes`/`on`) |
| `DECISIONDOC_CACHE_ENABLED` | `0` | 번들 캐싱 활성화 |
| `OPENAI_API_KEY` | — | provider=openai 시 필수 |
| `GEMINI_API_KEY` | — | provider=gemini 시 필수 |

---

## 코딩 규칙

### DO

**Pydantic 모델**
```python
# strict=True + extra="forbid" — 알 수 없는 필드 거부
class GenerateRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    title: str = Field(..., min_length=1)
    doc_types: list[DocType] = Field(default_factory=default_doc_types, min_length=1)
```

**추상 클래스 패턴** — Provider와 Storage는 반드시 ABC 상속
```python
class Provider(ABC):
    name: str

    @abstractmethod
    def generate_bundle(self, requirements: dict[str, Any], *, schema_version: str, request_id: str) -> dict[str, Any]:
        raise NotImplementedError
```

**키워드 전용 인자** — 핵심 파라미터는 `*` 뒤에 배치
```python
def generate_bundle(self, requirements, *, schema_version, request_id): ...
def generate_documents(self, requirements, *, request_id) -> dict: ...
```

**Atomic Write** — 모든 파일 쓰기는 tmp + fsync + os.replace
```python
tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
with tmp.open("w") as f:
    f.write(text); f.flush(); os.fsync(f.fileno())
os.replace(tmp, path)
```

**구조화 로깅** — `log_event(logger, event_name, **fields)` 사용
```python
log_event(logger, "generate.completed", request_id=..., provider=..., cache_hit=...)
```

**Factory 함수** — 환경변수를 읽어 구현체를 반환하는 `get_X()` 패턴
```python
def get_provider() -> Provider: ...   # app/providers/factory.py
def get_storage() -> Storage: ...     # app/storage/factory.py
def get_ops_service() -> OpsService: ...
```

**app.state를 통한 의존성 전달** — 라우트 핸들러에서 `request.app.state.service` 접근
```python
service = GenerationService(...)
app.state.service = service  # create_app() 내부
```

**타입 힌트** — `dict[str, Any]`, `list[DocType]`, `str | None` 등 Python 3.10+ 스타일

### DON'T

- `os.getenv` 직접 호출을 라우트 핸들러 내부에 넣지 말 것 — `create_app()` 시점에 수집
- `json.loads(response.text)` 직접 파싱 금지 — Provider 구현체 내부에서 처리
- `boto3` 최상위 import 금지 — s3 스토리지에서 lazy import
- 테스트에서 실제 파일시스템 대신 mock 남용 금지 — `test_storage.py`는 실제 `tmp_path` 사용
- `model_config = ConfigDict(strict=True)` 없이 새 Request 모델 만들지 말 것

---

## 핵심 설계 원칙

### 1. Provider 패턴
- `Provider` ABC → `OpenAIProvider` / `GeminiProvider` / `MockProvider`
- `UsageTokenMixin`: 토큰 사용량 `consume_usage_tokens()` — 한 번 읽으면 None 리셋
- `ProviderError` 단일 예외 클래스 — 모든 Provider 오류를 이 타입으로 감쌈
- Provider는 `generate_bundle()` 하나만 노출, 상태를 최소화

### 2. Generation 파이프라인 (`GenerationService.generate_documents`)
```
요청 → 캐시 조회 → Provider.generate_bundle() → JSON 스키마 검증
     → Stabilizer 후처리 → Storage 저장 → Jinja2 렌더링 → Lint → 반환
```
- 각 단계의 소요 시간은 `Timer` 컨텍스트로 측정 → `timings_ms` 딕셔너리
- 캐시 키: `{provider}/{schema_version}/{SHA256(payload)}.json`

### 3. Storage 추상화
- `Storage` ABC → `LocalStorage` / `S3Storage`
- `LocalStorage`: `data/{bundle_id}.json`, `data/{bundle_id}/{doc_type}.md`
- `S3Storage`: `{prefix}bundles/{bundle_id}.json`, `{prefix}exports/{bundle_id}/{doc_type}.md`
- 공통 Atomic Write 패턴 — 로컬과 S3 모두 적용

### 4. FastAPI 레이어 구조
```
main.py (라우트)
  └─ Depends(require_api_key / require_ops_key / require_not_maintenance)
  └─ request.app.state.service  →  GenerationService
  └─ request.app.state.storage  →  Storage 구현체
  └─ request.state.*            →  observability 미들웨어가 읽음
```
- `create_app()`이 앱 전체 초기화 담당, 모듈 레벨 side-effect 없음
- 미들웨어 순서: CORS → Observability → Request-ID → 예외 핸들러

### 5. Lambda 배포
- `app/aws_lambda.py`: `handler = Mangum(app)` 한 줄
- SAM 파라미터로 stage, S3 bucket, API key, throttle 설정
- Lambda timeout 30s, Memory 512MB, 기본 concurrency 2
- `DECISIONDOC_ENV=prod` 시 `/docs`, `/redoc`, `/openapi.json` 비활성화

### 6. Observability
- 모든 요청: JSON 한 줄 로그 (request_id, method, path, status_code, latency_ms …)
- `request.state`에 필드를 설정하면 observability 미들웨어가 자동으로 로그에 포함
- `X-Request-Id`: 인바운드 헤더 재사용 또는 UUID4 생성, 응답 헤더에 반영

---

## 테스트

```bash
# 전체 (mock provider, 로컬 스토리지)
pytest tests/

# 특정 파일
pytest tests/test_generate.py -v

# live 마커 제외 (기본값)
pytest tests/ -m "not live"

# live 테스트 포함 (실제 API 키 필요)
pytest tests/ -m live
```

**주요 테스트 파일**

| 파일 | 커버리지 |
|------|----------|
| `test_generate.py` | 전체 generate 파이프라인, 캐싱 |
| `test_auth_api_key.py` | API 키 검증, HMAC, OPTIONS bypass |
| `test_storage.py` | LocalStorage / S3Storage (fake S3 client 기반) |
| `test_stabilizer.py` | 번들 안정화 로직 |
| `test_ops_investigate.py` | Ops 조사 엔드포인트 |
| `test_golden_snapshots.py` | 골든 스냅샷 비교 |
| `test_observability.py` | 구조화 로그 필드 검증 |
| `test_maintenance_mode.py` | 유지보수 모드 차단 |

**Fixtures**: `tests/fixtures/` — 기본 10개 JSON 시나리오 + procurement fixture 2개

---

## 주의사항

### Legacy Compatibility
- `DECISIONDOC_API_KEY`는 단일 키 fallback으로만 유지한다. 신규 설정은 `DECISIONDOC_API_KEYS`를 우선한다.
- `app.storage.tenant_store.migrate_legacy_data()`는 flat data에서 tenant 경로로 올리는 호환 레일이다. 앱 초기화에서 이 흐름을 우회하지 말 것.

### AWS 관련
- `DECISIONDOC_S3_BUCKET` 없이 `DECISIONDOC_STORAGE=s3` 설정 시 런타임 오류
- boto3는 `requirements.txt`에 포함되어 있다. S3 스토리지는 런타임에서 lazy import 패턴을 유지한다.
- SAM 배포 전 `DECISIONDOC_API_KEY` 또는 `DECISIONDOC_API_KEYS` 파라미터 필수 (`prod` 환경)
- CloudWatch 조사(`/ops/investigate`) 기능은 `DECISIONDOC_OPS_KEY` 없으면 인증 실패

### Prod 환경
- `DECISIONDOC_ENV=prod` 시 API 키 없으면 앱 시작 자체가 실패 (`RuntimeError`)
- Swagger UI(`/docs`, `/redoc`)는 prod에서 자동 비활성화
- CORS는 기본 비활성화 — 필요 시 `DECISIONDOC_CORS_ENABLED=1` + `DECISIONDOC_CORS_ALLOW_ORIGINS` 명시

### Provider
- `mock` Provider는 외부 API 없이 정적 응답 반환 — CI/CD 기본값으로 적합
- OpenAI Provider: 20초 타임아웃(`anyio.fail_after(20)`) — Lambda 30s 타임아웃과 여유 확보
- Provider 추가 시: `Provider` ABC 상속 → `UsageTokenMixin` mixin → `factory.py`에 분기 추가

### 미완료 항목 (아키텍처 부채)
- CSP Nonce 미적용 (`security_headers.py`는 현재 `script-src 'unsafe-inline'`에 의존)

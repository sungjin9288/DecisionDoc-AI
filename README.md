# DecisionDoc AI

> 의사결정 문서·제안서·보고서를 **생성 → 검증 → 검토·승인 → 내보내기**까지 하나의 워크플로로 관리하는 FastAPI 기반 AI 문서 생성 플랫폼.

LLM이 만든 결과를 단발성 텍스트가 아니라 **업무 산출물**로 다루는 데 초점을 둔 프로젝트입니다. 멀티 LLM provider 추상화, bundle/template/validation 파이프라인, 승인·이력·감사 워크플로, 공공조달(G2B) Go/No-Go 보조 흐름을 포함합니다.

> ⚠️ 상태: **MVP 구현 후 고도화 중**. 운영 플랫폼이 아닌 PoC/MVP이며, 검증되지 않은 성과 수치는 사용하지 않습니다. 아래 수치는 모두 소스 코드에서 직접 카운트한 값이며 측정 커맨드를 함께 표기합니다.

---

## Why I Built This

컨설팅 현장에서 제안서·평가보고서의 품질이 작성자 숙련도에 따라 들쭉날쭉하고, 같은 문서 구조를 매번 다시 잡는 낭비를 직접 겪었습니다. "문서 품질을 사람의 숙련도가 아니라 시스템으로 보장할 수 없을까"가 출발점입니다. 컨설팅 경험에서 나온 문제 정의를 작동하는 서비스로 옮긴 사례입니다.

핵심 문제는 **LLM 생성 결과를 단순 텍스트가 아니라 검토·승인 가능한 업무 산출물로 관리하는 구조**를 만드는 것입니다.

---

## Features

| Feature | 설명 |
|---------|------|
| 문서 생성 API | `/generate` 계열 — 입력/출력을 Pydantic 모델로 표준화 |
| 참고 문서 기반 생성 | `/generate/from-documents`, `/generate/from-pdf` — 첨부 자료 반영 |
| Bundle / Template / Validation | BundleSpec·DocumentSpec + Jinja2 + lint 단계로 문서 유형별 품질 편차 축소 |
| 멀티 LLM Provider | `mock` / `openai` / `gemini` / `claude` / `local` — factory + fallback chain |
| 검토·승인 워크플로 | `/approvals` 계열 — submit / review / approve / reject / download |
| 감사·프라이버시 | `/admin/audit-logs`, `/auth/export-my-data`, `/auth/withdraw` 등 |
| 멀티테넌시·관리자 | `/admin/tenants`, 모델 학습/승격(`/admin/models/...`) |
| 공공조달 Go/No-Go | G2B 연동 기반 procurement copilot 흐름 (`G2B_API_KEY`, 스모크 옵션 제공) |
| 로컬 procurement decision package evidence | mock/local fixture 기반 decision package, handoff, sign-off, export boundary, CLI contract 검증 경로 |

---

## Tech Stack

| Area | Stack |
|------|-------|
| Language | Python 3.12 |
| Backend | FastAPI, Pydantic v2 |
| Template | Jinja2 (BundleSpec / DocumentSpec) |
| AI / LLM | provider abstraction (mock / openai / gemini / claude / local) + fallback chain |
| Storage | local filesystem / AWS S3 (storage abstraction) |
| Infra | Docker Compose, AWS SAM / Lambda |
| Test | pytest (live / not-live 마커 분리), smoke scripts |
| Ops | request tracking·logging·metrics middleware, secret-hygiene git hook |

---

## Architecture

```text
Client
 → FastAPI Routes (/generate, /approvals, /admin, /auth, /billing, /dashboard ...)
 → Generate Service
    → Bundle Catalog / DocumentSpec
    → Jinja2 Template
    → Provider Factory ─ Mock / OpenAI / Gemini / Claude / Local (+ fallback chain)
    → Stabilizer / Validation / Lint
 → Storage Layer ─ Local / S3
 → Export Service (Markdown 등)
 → Project / Knowledge / Approval / History / Audit 워크플로
```

배포 모드: 로컬 개발 · Docker Compose · AWS SAM/Lambda. Provider는 `DECISIONDOC_PROVIDER`에 단일 또는 콤마 구분 fallback chain(`openai,gemini`)으로 지정.

---

## Key Design Decisions

- **검토·승인 워크플로를 1급 기능으로** — 컨설팅 산출물은 검토 단계가 필수다. 단순 생성기는 실무에서 안 쓰인다고 판단해 approval/history를 생성 흐름의 일부로 설계.
- **LLM provider abstraction** — 특정 모델 종속은 비용·정책 변화에 취약. Mock/OpenAI/Gemini/Claude/Local을 factory + fallback chain으로 추상화해 교체 가능하게 함. `mock`은 테스트·개발에서 결정론적으로 동작하도록 유지.
- **schema / template / validation 결합** — 문서 유형별 품질 편차를 사람 숙련도가 아니라 구조로 줄이기 위해 BundleSpec/DocumentSpec + Jinja2 + lint 단계를 결합.
- **storage abstraction (local/S3)** — 로컬 개발과 클라우드 운영을 같은 코드 경로로 지원.

---

## Getting Started

```bash
# 1. 설치
pip install -r requirements.txt
cp .env.example .env
bash scripts/install_git_hooks.sh        # commit 전 secret hygiene 검사 hook

# 2. 실행 (로컬)
python -m uvicorn app.main:app --reload   # http://localhost:8000

# 3. 실행 (Docker)
docker compose up -d
curl http://localhost:8000/health
```

> `install_git_hooks.sh`는 `scripts/check_secret_hygiene.py`를 pre-commit으로 걸어, AWS 자격증명이 커밋에 들어가는 것을 차단합니다.

### Environment (주요 그룹)

`.env.example`에 **90개** 키가 정의돼 있습니다. 대표 그룹만 정리합니다.

```bash
grep -E '^[A-Z0-9_]+=' .env.example | wc -l   # → 90
```

| 그룹 | 대표 키 |
|------|---------|
| Runtime/Provider | `DECISIONDOC_PROVIDER`, `DECISIONDOC_ENV`, `DECISIONDOC_TEMPLATE_VERSION` |
| Provider Keys | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `LOCAL_LLM_*` |
| Auth/Security | `DECISIONDOC_API_KEY(S)`, `DECISIONDOC_OPS_KEY`, `JWT_SECRET_KEY`, `DECISIONDOC_CORS_*` |
| Storage | `DECISIONDOC_STORAGE`, `DATA_DIR`, `EXPORT_DIR`, `DECISIONDOC_S3_BUCKET`, `AWS_REGION` |
| Search/Retrieval | `DECISIONDOC_SEARCH_ENABLED`, `SERPER_API_KEY`, `BRAVE_API_KEY`, `TAVILY_API_KEY` |
| 공공조달(G2B) | `G2B_API_KEY`, `G2B_SEARCH_DAYS`, `G2B_MAX_RESULTS` |
| 부가 기능 | `VOICE_BRIEF_*`, `MEETING_RECORDING_*`, `SMTP_*` |

---

## API / Usage

FastAPI 라우트는 **254개**입니다.

```bash
grep -rE "@(app|router)\.(get|post|put|delete|patch)\(" app | wc -l   # → 254
```

대표 도메인:

| Domain | 예시 엔드포인트 |
|--------|----------------|
| Generate | `/generate`, `/generate/export`, `/generate/from-documents`, `/generate/from-pdf` |
| Bundles | `GET /bundles`, `GET /bundles/{bundle_id}` |
| Auth | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/withdraw` |
| Approvals | `/approvals`, `/approvals/{id}/submit`, `/review/approve`, `/reject`, `/download/{fmt}` |
| Admin | `/admin/tenants`, `/admin/models/{id}/promote`, `/admin/audit-logs` |
| Dashboard | `/overview`, `/bundle-performance`, `/score-history/{bundle_id}` |
| Billing | `/billing/status`, `/billing/usage`, `/billing/checkout` |

스모크 검증 (문서화된 대표 시나리오):

```bash
python scripts/smoke.py
# 검증: /health, 미인증 /generate 거부, 인증 /generate 성공,
#       /generate/export 성공, /generate/from-documents 업로드 성공
```

로컬 공공조달 decision package evidence 검증:

```bash
CONTRACT_RESULT=/tmp/decisiondoc-cli-contract-manifest-validation-result.json
python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py \
  --write-result \
  --result-path "$CONTRACT_RESULT"
python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py "$CONTRACT_RESULT"
```

이 경로는 `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`을 검증하고, local evidence CLI의 stdout JSON success/failure contract를 확인합니다. fixture 기반 검증이며 provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment를 실행하지 않습니다.

---

## Testing

```bash
pytest tests/                 # 전체
pytest tests/ -m "not live"   # 외부 의존 없는 테스트만
pytest tests/ -m live         # live 마커 테스트
```

테스트 함수는 **2,447개**, **205개 파일**입니다 (소스 정의 기준 카운트). 자동생성 phase 영수증 검증 테스트(제품 기능과 무관)는 2026-07-02 정리에서 제거해 수치에서 제외했습니다.

```bash
grep -rE "def test_" tests | wc -l    # → 2447
find tests -name "test_*.py" | wc -l  # → 205
```

> 위 수치는 `def test_` 정의 개수입니다. 각 테스트의 현재 pass 여부는 환경 구성 후 `pytest`로 재확인하세요. 검증되지 않은 커버리지·통과율 수치는 표기하지 않습니다.

---

## Scope & Limitations

- 완전한 문서관리 시스템이 아니라 **AI-assisted documentation MVP/PoC**입니다.
- 운영 URL(예: `admin.decisiondoc.kr`) **접근성은 추가 검증이 필요**하며, 현재 README에서 동작 보장을 하지 않습니다.
- 실제 사용자 성과 수치·운영 안정성은 검증되지 않았습니다. 검증 범위 밖의 운영 보장은 표기하지 않습니다.
- 다수 기능이 단독 구현/실험 단계이며, **본인 직접 기여 범위는 포트폴리오·면접 설명 시 별도 정리**가 필요합니다.
- 공공조달(G2B) 연동은 외부 API 키·실데이터에 의존하므로, 키 없이는 해당 흐름이 동작하지 않습니다.
- 로컬 procurement decision package evidence 경로는 fixture 검증이며, 실제 입찰 제출·법적 승인·계약상 확약을 의미하지 않습니다.

---

## Links

- GitHub: [sungjin9288/DecisionDoc-AI](https://github.com/sungjin9288/DecisionDoc-AI)
- Release evidence: [DecisionDoc AI v1.1.77 Production Release](https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.77)
- Demo: (접근 검증 후 추가)
- 엔지니어링/기여 가이드: [`docs/`](./docs/) 및 `AGENTS.md`

---

<sub>이 README의 모든 정량 수치(라우트 254 · 테스트 2,447 · env 키 90 등)는 소스 코드에서 직접 카운트했으며, 재현 커맨드를 함께 표기했습니다. 측정 근거가 없는 비용 절감률·자동화율·정확도 수치는 사용하지 않습니다.</sub>

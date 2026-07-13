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
| 완성 문서 review packet | completed human review receipt 기반 deterministic ZIP, embedded SHA256 index, tamper/path boundary 검증 |

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

레이어 수치는 실측 기반입니다 (재현 커맨드는 [docs/development-plan.md](./docs/development-plan.md) §2 참조).

```text
Client (Web UI / CLI / API)
  │
  ▼
FastAPI (app/main.py — create_app(), 모듈 레벨 side-effect 없음)
  ├─ Middleware 체인 (9): CORS → observability → request_id → security_headers
  │     → rate_limit → auth → tenant → billing → audit → metrics
  ├─ Routers (20 top-level files, 라우트 254): generate / approvals / projects / knowledge
  │     / report_workflows / auth / sso / admin / audit / billing / dashboard
  │     / history / eval / finetune / local_llm / g2b / templates / health ...
  ▼
Services (37) — 도메인 오케스트레이션
  ├─ generation_service ─ 핵심 파이프라인:
  │     요청 → 캐시 → Provider.generate_bundle() → 스키마 검증
  │        → Stabilizer → Storage 저장 → Jinja2 렌더 → Lint → 반환
  ├─ export 계열: docx / pptx / pdf / hwp / excel (5종)
  ├─ 조달 계열: g2b_collector → procurement_decision_service
  │     → procurement_decision_package/ (13-모듈 패키지)
  └─ 품질 계열: report_quality_learning / prompt_optimizer / validator
  │
  ├────────────────┬─────────────────────┐
  ▼                ▼                     ▼
Providers (5)    Storage (36 스토어)    Ops
  factory +        factory +             CloudWatch 조사
  fallback chain   Local / S3            Statuspage 연동
  mock/openai/     (atomic write 공통)   eval / eval_live
  gemini/claude/local
```

**설계 불변식**: Provider·Storage는 ABC + factory(환경변수로만 교체) · 모든 파일 쓰기는 atomic write(tmp + fsync + os.replace) · 라우트 핸들러는 `request.app.state.*`로 의존성 접근 · Request 모델은 `strict=True, extra="forbid"` · mock provider는 결정론적(CI 기준 경로).

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

`.env.example`에 **91개** 키가 정의돼 있습니다. 대표 그룹만 정리합니다.

```bash
python3 scripts/count_readme_metrics.py --field env_keys  # → 91
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
python3 scripts/count_readme_metrics.py --field route_decorators  # → 254
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

대표 bundle sample과 구조 품질 evidence를 local mock provider로 재생성합니다.

```bash
python3 scripts/build_finished_doc_review_samples.py \
  --output-dir docs/samples/bundle_quality_evidence \
  --run-name current \
  --no-latest \
  --bundles proposal_kr,performance_plan_kr \
  --formats ''

python3 -m app.eval --out-dir reports/eval/v1
```

2026-07-13 위 명령으로 확인한 결과는 [bundle quality manifest](./docs/samples/bundle_quality_evidence/current/manifest.json) 기준 2개 bundle, 생성 문서 6개, validator 2건 통과, bundle lint 2건 통과, request 대비 단위 수치 literal coverage 2건 통과(미근거 수치 0건)입니다. [review dashboard](./docs/samples/bundle_quality_evidence/current/review.html)는 manifest가 hash로 관리하는 자동 검증 원본이며, [reviewer workspace](./docs/samples/bundle_quality_evidence/current/human_review.html)는 request 근거, 자동 검증, 생성 Markdown, bundle별 사람 검토 상태와 외부 action 경계를 한 화면에 보여줍니다. 증적 원본인 [human review receipt](./docs/samples/bundle_quality_evidence/current/human_review_receipt.json)는 현재 manifest SHA256에 결속된 `pending` 상태입니다. 아직 사람 검토 완료를 주장하지 않으므로 final review packet도 생성하지 않았습니다. Completed receipt에서는 manifest-declared artifact와 embedded SHA256 index만 담은 deterministic ZIP을 만들고 다시 검증할 수 있습니다. [offline eval report](./reports/eval/v1/eval_report.md)는 fixture 10건 중 10건 통과입니다. 모두 mock/local 검증 결과이며 numeric coverage는 수치의 사실성·최신성·문맥 적합성을 보증하지 않습니다. 화면 노출도 factual grounding이나 human visual review 완료를 뜻하지 않으며 live provider 품질을 증명하지 않습니다.

```bash
pytest tests/                 # 전체
pytest tests/ -m "not live"   # 외부 의존 없는 테스트만
pytest tests/ -m live         # live 마커 테스트
```

테스트 함수는 **2,591개**, **215개 파일**입니다 (AST source definition 기준 카운트). 자동생성 phase 영수증 검증 테스트(제품 기능과 무관)는 2026-07-02 정리에서 제거해 수치에서 제외했습니다.

```bash
python3 scripts/count_readme_metrics.py --field test_functions  # → 2591
python3 scripts/count_readme_metrics.py --field test_files      # → 215
```

> 위 수치는 Python AST로 확인한 `test_` 함수 정의 개수입니다. 각 테스트의 현재 pass 여부는 환경 구성 후 `pytest`로 재확인하세요. 검증되지 않은 커버리지·통과율 수치는 표기하지 않습니다.

CI advisory와 동일한 code quality / security scan:

```bash
ruff check app/ --select=E,F,W --ignore=E501
bandit -r app/ -x app/providers/mock_provider.py -ll
```

2026-07-09 로컬 기준 `ruff`는 `All checks passed!`, `bandit -ll`은 `No issues identified`입니다. Bandit `-ll`은 medium/high severity 기준이며, low severity 항목 전체 해소를 의미하지 않습니다.

---

## Development Plan — 완성까지 남은 것

mock/local 경로는 전 기능이 테스트로 검증됐습니다 (`pytest tests/ -m "not live" -q` → 2,805 passed, 2 skipped, 4 deselected, 2026-07-09 실측). "완성"을 막는 갭과 마일스톤은 [docs/development-plan.md](./docs/development-plan.md)에 정의돼 있습니다.

```bash
python3 scripts/check_completion_readiness.py --print-env-template
python3 scripts/check_completion_readiness.py --print-proof-plan
python3 scripts/check_completion_readiness.py
python3 scripts/check_completion_readiness.py --env-file .env.prod
python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
python3 scripts/check_completion_proof_receipt.py --print-template M1
```

위 명령은 남은 M1/M2/M6 실행 준비 조건을 로컬에서 점검하고, 저장된 JSON receipt가 현재 계약과 맞는지 확인합니다. `--print-env-template`은 `.env.prod`에 옮겨 적을 입력값만 출력하고, `--print-proof-plan`은 readiness와 no-secret proof receipt 생성·검증 명령을 별도로 출력합니다. `.env.prod`와 `reports/`는 gitignore된 runtime 경로라서 secret과 receipt를 커밋하지 않습니다. provider API, G2B live API, AWS runtime, dataset upload, training, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않습니다. 실제 proof 이후에는 `scripts/check_completion_proof_receipt.py`로 secret 없는 proof receipt를 검증하고, 자세한 증적 실행 순서는 [docs/completion-readiness-runbook.md](./docs/completion-readiness-runbook.md)를 따릅니다.

| 마일스톤 | 내용 | 외부 의존 | 상태 (2026-07-13) |
|----------|------|-----------|--------------------|
| **M1** | Live provider 실증 — openai/gemini/claude 실호출 `-m live` 통과 + 증적 | Gemini quota/billing, Anthropic credits | 진행 중 — 2026-07-13 OpenAI 1회 통과; 나머지 blocked |
| **M2** | G2B 실데이터 end-to-end 1건 — 수집→정규화→decision package | `G2B_API_KEY` | 미착수 |
| **M3** | excel export를 타 4종 포맷과 동등 수준으로 보강 | 없음 | ✅ 완료 |
| **M4** | CSP nonce 적용 — served HTML `script-src 'unsafe-inline'` 제거 | 없음 | ✅ 완료 — inline handler 0개, HTML nonce 기본 on, local diagnostic opt-out 유지 |
| **M5** | 800줄 초과 모듈 분할 (procurement 패키지 분할 패턴 재사용) | 없음 | ✅ 완료 — 15개 전부 분할, 800줄 초과 0개 |
| **M6** | 배포 재검증 + post-deploy smoke 증적 + 데모 URL 접근성 | 배포 환경 | 미착수 |

우선순위는 **M1·M2** — 코드가 아니라 "실증 증거"가 현재 완성의 병목입니다. 각 마일스톤의 완료 정의(DoD)·리스크·실행 순서는 계획 문서 참조.

---

## Scope & Limitations

- 완전한 문서관리 시스템이 아니라 **AI-assisted documentation MVP/PoC**입니다.
- 운영 URL(예: `admin.decisiondoc.kr`) **접근성은 추가 검증이 필요**하며, 현재 README에서 동작 보장을 하지 않습니다.
- 실제 사용자 성과 수치·운영 안정성은 검증되지 않았습니다. 검증 범위 밖의 운영 보장은 표기하지 않습니다.
- 다수 기능이 단독 구현/실험 단계이며, **본인 직접 기여 범위는 포트폴리오·면접 설명 시 별도 정리**가 필요합니다.
- 공공조달(G2B) 연동은 외부 API 키·실데이터에 의존하므로, 키 없이는 해당 흐름이 동작하지 않습니다.
- Live provider proof는 2026-07-13 OpenAI 1회만 통과했습니다. Gemini는 API quota, Claude는 account credits로 blocked이며 성공 fallback proof도 남아 있습니다.
- 로컬 procurement decision package evidence 경로는 fixture 검증이며, 실제 입찰 제출·법적 승인·계약상 확약을 의미하지 않습니다.
- Final review packet은 모든 bundle의 사람 검토가 완료된 receipt에서만 생성됩니다. 현재 tracked sample은 `pending`이라 packet을 제공하지 않습니다.

---

## Links

- GitHub: [sungjin9288/DecisionDoc-AI](https://github.com/sungjin9288/DecisionDoc-AI)
- Release evidence: [DecisionDoc AI v1.1.77 Production Release](https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.77)
- Demo: (접근 검증 후 추가)
- 엔지니어링/기여 가이드: [`docs/`](./docs/) 및 `AGENTS.md`

---

<sub>이 README의 모든 정량 수치(라우트 254 · 테스트 2,591 · env 키 91 등)는 소스 코드에서 직접 카운트했으며, 재현 커맨드를 함께 표기했습니다. 측정 근거가 없는 비용 절감률·자동화율·정확도 수치는 사용하지 않습니다.</sub>

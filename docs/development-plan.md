# DecisionDoc AI — 완성을 위한 기능 개발 계획 (Development Plan)

> 기준일: **2026-07-17** (저장소 점검 [docs/inspection-20260630.md](./inspection-20260630.md), 2026-07-02 정리 커밋, M4 CSP nonce 완료, 최근 확인한 CI/CD success 기준)
> 원칙: AGENTS.md 정직성 규칙 준수 — 모든 정량 수치는 재현 커맨드를 병기하고, 검증되지 않은 성과·운영 표현은 사용하지 않는다.
> 상위 방향 문서: [product_direction.md](./product_direction.md) · [product_execution_plan.md](./product_execution_plan.md) · [roadmap.md](./roadmap.md)

---

## 1. "완성"의 정의

이 프로젝트에서 완성은 "기능이 많다"가 아니라 다음 3가지를 충족한 상태로 정의한다.

| 축 | 현재 | 완성 기준 |
|----|------|-----------|
| **기능 검증** | non-live test suite 통과 (`pytest tests/ -m "not live" -q` → 3,931 passed, 1 skipped, 4 deselected, 2026-07-17) | 외부 의존 경로(live LLM, G2B 실데이터)도 최소 1회 실증 + 증적 |
| **아키텍처 위생** | ✅ 달성 (2026-07-14: 829줄 상수 모듈을 604줄 facade + 314줄 foundation으로 분리하고 800줄 guard 추가 → 초과 0개). CI advisory Ruff E/F/W와 Bandit medium/high 0건 기준 유지 | 전 모듈 800줄 이하 (전역 코딩 가이드), 계층 간 의존 방향 일관 |
| **운영 준비성** | Docker/SAM 설정 존재, CSP nonce 부채 해소, GitHub Actions CI/CD success 증적 존재. 단, staging deploy/smoke는 설정 부재로 skip되어 배포 접근성은 미검증 | 배포 절차 재검증 + post-deploy smoke 증적 |

```bash
# 재현: 테스트 베이스라인
pytest tests/ -m "not live" -q     # 2026-07-17 실측: 3931 passed, 1 skipped, 4 deselected

# 재현: CI advisory lint/security 베이스라인
ruff check app/ --select=E,F,W --ignore=E501
bandit -r app/ -x app/providers/mock_provider.py -ll

# 재현: 남은 외부 실증 준비 조건 점검(외부 호출 없음)
python3 scripts/check_completion_readiness.py --print-env-template
python3 scripts/check_completion_readiness.py --print-proof-plan
python3 scripts/check_completion_readiness.py
python3 scripts/check_completion_readiness.py --env-file .env.prod
python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
```

---

## 2. 현재 아키텍처 (실측 기반)

배포·인프라 관점 구성도(Nginx/TLS/PWA 포함)는 [architecture.md](./architecture.md) 참조. 여기서는 코드 레이어 관점을 다룬다. 레이어 수치는 아래 커맨드로 재측정 가능하다.

```bash
python3 scripts/count_readme_metrics.py --field router_files      # → 23 (top-level 라우터 파일)
python3 scripts/count_readme_metrics.py --field service_files     # → 42 (서비스)
python3 scripts/count_readme_metrics.py --field storage_files     # → 38 (스토어)
python3 scripts/count_readme_metrics.py --field middleware_files  # → 9 (미들웨어)
python3 scripts/count_readme_metrics.py --field route_decorators  # → 266 (라우트)
```

```text
Client (Web UI / CLI / API)
  │
  ▼
FastAPI (app/main.py — create_app(), 모듈 레벨 side-effect 없음)
  │
  ├─ Middleware 체인 (9): CORS → observability → request_id → security_headers
  │     → rate_limit → auth → tenant → billing → audit → metrics
  │
  ├─ Routers (23 top-level files, 라우트 266):
  │     generate / approvals / projects / knowledge / report_workflows
  │     auth / sso / admin / audit / billing / dashboard / history
  │     eval / finetune / local_llm / g2b / document_ops_agent
  │     templates / styles / messages / notifications / events / health
  │
  ▼
Services (42) — 도메인 오케스트레이션
  ├─ generation_service ─ 핵심 파이프라인:
  │     요청 → 캐시 → Provider.generate_bundle() → 스키마 검증
  │        → Stabilizer → Storage 저장 → Jinja2 렌더 → Lint → 반환
  ├─ export 계열: docx / pptx / pdf / hwp / excel (5종)
  ├─ 조달 계열: g2b_collector → procurement_decision_service
  │     → procurement_decision_package/ (16-모듈 패키지, 2026-07-02 분할 후 확장)
  └─ 품질 계열: report_quality_learning / prompt_optimizer / validator
  │
  ├────────────────┬─────────────────────┐
  ▼                ▼                     ▼
Providers (5)    Storage (38 스토어)    Ops
  factory +        factory +             CloudWatch 조사
  fallback chain   Local / S3            Statuspage 연동
  mock / openai    (atomic write 공통)   eval / eval_live
  gemini / claude
  local
```

**설계 불변식** (변경 시 이 문서를 갱신할 것):

1. Provider·Storage는 ABC + factory — 구현 교체는 환경변수로만.
2. 모든 파일 쓰기는 atomic write(tmp + fsync + os.replace).
3. 라우트 핸들러는 `request.app.state.*`로 의존성 접근, `os.getenv` 직접 호출 금지.
4. 신규 Request 모델은 `ConfigDict(strict=True, extra="forbid")` 필수.
5. mock provider는 결정론적 — CI/CD와 로컬 데모의 기준 경로.

---

## 3. 갭 분석 — 무엇이 완성을 막고 있나

| # | 갭 | 근거 (실측) | 심각도 | 상태 (2026-07-13) |
|---|-----|------------|--------|--------------------|
| G1 | **Live provider 부분 실증** — OpenAI 1회 통과, Gemini/Claude/fallback 성공 proof 잔여 | 2026-07-13 M1 blocked receipt | HIGH | 진행 중 (Gemini quota, Anthropic credits 필요) |
| G2 | **G2B 실데이터 미실증** — collector 코드 존재, `G2B_API_KEY` 없이 비동작 | `app/services/g2b_collector.py` | HIGH | 미착수 (키 필요) |
| G3 | **800줄 초과 모듈** — 계획 수립 시 15개 | `find app -name '*.py' -print0 \| xargs -0 wc -l \| awk '$2 != "total" && $1 > 800 {print}'` | MED | **✅ 해소 및 guard 적용** (2026-07-14, 상수 모듈 drift 재분할 → 초과 0개) |
| G4 | **excel export 비대칭** — 84줄로 타 export 대비 최소 구현 | `wc -l app/services/excel_service.py` | MED | **완료** (커밋 e9ecabc, 309줄·테스트 14개) |
| G5 | **CSP nonce 부채** — served HTML `script-src 'unsafe-inline'` 의존 해소 필요 | `app/middleware/security_headers.py`, `app/static/index.html` | MED | **✅ 완료** — inline `on*=` 핸들러 0개, HTML 응답 nonce 기본 on, `DECISIONDOC_CSP_NONCE_ENFORCED=0` local diagnostic opt-out 유지 |
| G6 | **배포 접근성 미검증** — 최근 확인한 GitHub Actions CD는 성공했지만 staging deploy/smoke와 production deploy는 skip되어 운영 URL 동작 보장 없음 (README §Scope 명시) | GitHub Actions CD `29484598720` success, image build/push passed, deploy/smoke skipped | MED | 미착수 |
| G7 | **모듈 레벨 side-effect** — `app/main.py`의 `app = create_app()`이 import 시점에 `.env`를 로드해 테스트 격리를 해침 | — | MED | **✅ 해결** (2026-07-02, 커밋 0023c7c) — PEP 562 모듈 `__getattr__`로 lazy 생성(캐싱). `uvicorn app.main:app`·Mangum·기존 import 전부 무변경 동작 |

---

## 4. 마일스톤 계획

### M1 — Live Provider 실증 (G1) · 외부 의존: API 키, 소액 비용

- 작업:
  1. openai / gemini / claude 각 1회 실호출로 `pytest -m live` 통과.
  2. fallback chain(`DECISIONDOC_PROVIDER=openai,gemini`) 실측 1회 — 1차 실패 시 2차 전환 확인.
  3. 실행 로그·타임스탬프·커맨드를 `docs/evidence-gallery.md`에 증적으로 기록.
- 완료 정의(DoD): live 테스트 통과 로그가 docs에 남고, README의 "live 미검증" 한계 문구를 "N회 실증(날짜·커맨드)"으로 갱신.
- 리스크: provider별 요금·rate limit → mock 대비 diff가 큰 응답은 stabilizer 회귀로 흡수.
- 2026-07-13 실행 결과: OpenAI live generation은 `1 passed in 23.26s`. Gemini는 `gemini-2.5-pro`와 `gemini-2.0-flash` 모두 HTTP 429, Claude는 account credit balance 부족으로 HTTP 400. Fallback은 OpenAI 강제 401 뒤 Gemini 호출까지 확인했지만 Gemini 429로 성공하지 못했다. M1은 `blocked`이며 quota/credits 복구 후 잔여 3개 test를 재실행한다.

### M2 — G2B 실데이터 End-to-End (G2) · 외부 의존: `G2B_API_KEY` (data.go.kr)

- 작업:
  1. 실 공고 1건 수집 → 정규화 → decision package 산출까지 단일 케이스 통과.
  2. 산출 결과를 fixture로 고정해 회귀 테스트화 (키 없는 CI에서도 재현).
  3. GO / CONDITIONAL_GO / NO_GO 판정 재현성 확인.
- DoD: 실데이터 1건의 end-to-end 실행 증적 + 해당 케이스의 키-불필요 회귀 테스트. 입찰 제출·법적 승인은 범위 밖(기존 boundary 유지).
- 2026-07-14 local 준비: `run_stage_procurement_smoke.py --proof-receipt`가 preflight를 미실행 `blocked` 상태로, 실제 smoke를 `passed` 또는 `failed` 상태로 atomic 기록한다. Host와 안전한 공고 식별자만 남기고 API key, password, URL userinfo/query는 receipt에서 제외한다. 실 G2B 호출은 아직 실행하지 않았다.

### M3 — Export 5종 대칭성 (G4) · 외부 의존 없음 · ✅ 완료 (2026-07-02, 커밋 e9ecabc)

- 결과: 표지+요약(메트릭)+doc_type별 다중 시트, 헤더 서식/열 너비/text_wrap, 빈 입력·특수문자·32,767자 한계·시트명 정규화 방어. `build_excel` 시그니처 무변경. 테스트 6→14개(openpyxl 재오픈 검증 포함).

### M4 — 보안 성숙: CSP Nonce (G5) · 외부 의존 없음 · ✅ 완료 (2026-07-08)

- 완료: 요청별 nonce 생성/HTML 스탬핑/헤더 배선 + 테스트. page-tab, mobile bottom navigation, PWA install prompt, local LLM setup guide, SSO tabs, header user menu, notification bell/list, profile modal, AI rank roster, generation quick controls, G2B static/dynamic controls, batch results, bundle related modal, attachment actions, upload modals, static shell controls, ops static controls, SSO/Billing dynamic controls, RFP result modal, knowledge page/doc actions, report workflow shell/list/artifact/detail/quality/slide actions, locations shell, DocumentOps toolbar/dynamic actions, history dynamic actions, message thread, onboarding, result-download, share/auth/approval-request/project modal/list, project detail/search, dashboard retry, meeting recording, procurement role actions, style profile actions, location procurement summary, bundle recommendation close action까지 inline handler 없이 `addEventListener` 또는 delegated listener로 전환 완료.
- 완료 증거: `app/static/index.html`의 inline `on*=` 핸들러 0개. served HTML은 기본적으로 per-request nonce를 받고, nonce가 존재하는 `script-src`에서는 `'unsafe-inline'`을 제거한다. `DECISIONDOC_CSP_NONCE_ENFORCED=0`은 local diagnostic opt-out으로만 유지한다.
- DoD 달성: 이벤트 위임 완료 + nonce enforcement 기본 on + served HTML `script-src`에서 unsafe-inline 부재 + 관련 UI/CSP guard 통과.

```bash
python3 - <<'PY'
from pathlib import Path
import re
html = Path('app/static/index.html').read_text(encoding='utf-8')
print(len(re.findall(r'\son[a-zA-Z]+\s*=', html)))  # → 0
PY
```

### M5 — 코드 위생: 800줄 초과 모듈 분할 (G3) · 외부 의존 없음 · ✅ 완료 및 guard 적용 (2026-07-14, 800줄 초과 0개)

`procurement_decision_package_service.py`(4,883줄) 분할 패턴(순수 코드 이동 + facade re-export + AST 동일성 검증)을 재사용한다.

**완료 (2026-07-02):**

| 모듈 | 이전 | 결과 | 커밋 |
|------|------|------|------|
| `app/storage/trajectory_store.py` | 2,665 | 13모듈 mixin 패키지 (최대 446줄) | dd2562f |
| `app/services/generation_service.py` | 2,331 | 13모듈 패키지 (최대 347줄) | 5596499 |
| `app/routers/admin.py` | 2,246 | 9모듈 sub-router 패키지 (최대 747줄) | 9c56d4a |
| `app/routers/generate.py` | 2,170 | 6모듈 sub-router 패키지 (최대 698줄) | 195dc43 |
| `app/providers/mock_provider.py` | 1,794 | 9모듈 fixture 패키지 (최대 421줄) | 806531e |

**잔여 10개도 완료 (2026-07-02):**

| 모듈 | 이전 | 결과 | 커밋 |
|------|------|------|------|
| `app/routers/projects.py` | 1,468 | 4모듈 sub-router (최대 658줄) | d27d0c5 |
| `app/services/pptx_service.py` | 1,410 | 6모듈 (최대 558줄) | a7f76e7 |
| `app/services/report_workflow_service.py` | 1,322 | 6모듈 mixin (최대 371줄) | 9af900f |
| `app/services/procurement_decision_service.py` | 1,252 | 7모듈 mixin (최대 402줄) | 41bd6e2 |
| `app/schemas.py` | 1,179 | 12모듈 도메인 분할, OpenAPI byte-identical | b883254 |
| `app/storage/report_workflow_store.py` | 1,159 | 8모듈 mixin (최대 280줄) | ba32780 |
| `app/ops/service.py` | 990 | 7모듈 mixin (최대 314줄) | 0e4be91 |
| `app/storage/knowledge_store.py` | 973 | 7모듈 mixin (최대 303줄) | 44c06fe |
| `app/services/attachment_service.py` | 881 | 5모듈 (최대 312줄) | 4ecaa97 |
| `app/services/decision_council_service.py` | 805 | 4모듈 (최대 415줄) | 683457c |

- 2026-07-14 후속 점검에서 `app/services/procurement_decision_package/constants.py`가 829줄로 다시 커진 drift를 확인했다. package foundation 상수를 `package_constants.py`로 이동해 기존 import facade 604줄과 foundation 314줄로 분리했고, 126개 기존 export의 AST 이름 및 runtime 값 동일성을 확인했다.
- DoD 달성: `find app -name '*.py' -print0 | xargs -0 wc -l | awk '$2 != "total" && $1 > 800 {print}'` → **0개**. `tests/test_infrastructure.py`가 app 모듈 상한과 foundation re-export identity를 계속 검증한다.

### M6 — 운영 준비성 (G6) · 외부 의존: 배포 환경

- 작업:
  1. Docker Compose · AWS SAM 배포 절차 재실행/재검증.
  2. post-deploy smoke(`scripts/smoke.py`, `scripts/ops_smoke.py`) 결과 증적화.
  3. 데모 URL 접근성 확인 후 README Links의 "Demo: (접근 검증 후 추가)" 갱신.
- DoD: 신규 환경에서 README 절차만으로 배포 재현 + smoke 통과 로그.
- 2026-07-14 local 준비: `run_deployed_smoke.py --proof-receipt`가 preflight와 실제 deployed smoke의 상태·UTC 시각·runtime host·남은 제한을 validator-compatible receipt로 남긴다. Preflight는 AWS runtime 실행 증거로 취급하지 않으며 실제 runtime은 아직 실행하지 않았다.

---

## 5. 실행 순서와 의존 관계

```text
M1 (live 실증) ──┐
                 ├──> README/evidence 갱신 ──> M6 (배포 검증)
M2 (G2B e2e)  ──┘
M3 (excel)  ── 완료
M4 (CSP)    ── 완료
M5 (분할)   ── 완료
```

- **M1·M2가 최우선**: 코드가 아닌 "증거"가 완성의 병목이다.
- M1·M2·M6 실행 전에는 `python3 scripts/check_completion_readiness.py --print-env-template`으로 필요한 env 입력값을 확인하고, `python3 scripts/check_completion_readiness.py --print-proof-plan`으로 readiness와 no-secret proof receipt 명령을 확인한다. secret은 gitignore된 `.env.prod` 같은 파일에 둔 뒤 `python3 scripts/check_completion_readiness.py --env-file .env.prod`로 provider key, G2B/stage smoke, 배포 smoke 입력값을 먼저 확인한다. 필요하면 `python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json`으로 gitignore된 local receipt를 남기고 `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json`로 receipt 계약을 확인한다. 이 명령은 readiness만 확인하며 live provider, G2B live API, AWS runtime은 실행하지 않는다. 실제 proof 실행과 문서 갱신 순서는 [completion-readiness-runbook.md](./completion-readiness-runbook.md)를 따른다.
- M3·M4·M5는 외부 의존 없는 정리 마일스톤으로 완료됐다.
- 각 마일스톤 완료 시 [roadmap.md](./roadmap.md)와 README 수치·한계 문구를 함께 갱신한다 (정직성 규칙).

## 6. 하지 않을 것 (Non-Goals)

- phase 클로저 영수증·documentops 산출물 재생성 (2026-07-02 정리 완료, `.gitignore`로 차단).
- 측정 근거 없는 성과 수치(비용 절감률, 정확도 등) 표기.
- 실제 입찰 제출·법적 승인·계약 확약을 암시하는 기능/문구.

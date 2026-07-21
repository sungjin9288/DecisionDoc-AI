# DecisionDoc AI — 완성을 위한 기능 개발 계획 (Development Plan)

> 기준일: **2026-07-21** (저장소 점검 [docs/inspection-20260630.md](./inspection-20260630.md), 2026-07-02 정리 커밋, M4 CSP nonce 완료, 최근 확인한 CI/CD success 기준)
> 원칙: AGENTS.md 정직성 규칙 준수 — 모든 정량 수치는 재현 커맨드를 병기하고, 검증되지 않은 성과·운영 표현은 사용하지 않는다.
> 상위 방향 문서: [product_direction.md](./product_direction.md) · [product_execution_plan.md](./product_execution_plan.md) · [roadmap.md](./roadmap.md)

---

## 1. "완성"의 정의

이 프로젝트에서 완성은 "기능이 많다"가 아니라 다음 3가지를 충족한 상태로 정의한다.

| 축 | 현재 | 완성 기준 |
|----|------|-----------|
| **기능 검증** | non-live test suite 통과 (`pytest tests/ -m "not live" -q` → 4,250 passed, 2 skipped, 4 deselected, 1 warning, 2026-07-21 H91) | 외부 의존 경로(live LLM, G2B 실데이터)도 최소 1회 실증 + 증적 |
| **아키텍처 위생** | ✅ 달성 (2026-07-14: 829줄 상수 모듈을 604줄 facade + 314줄 foundation으로 분리하고 800줄 guard 추가 → 초과 0개). CI advisory Ruff E/F/W와 Bandit medium/high 0건 기준 유지 | 전 모듈 800줄 이하 (전역 코딩 가이드), 계층 간 의존 방향 일관 |
| **운영 준비성** | Docker/SAM 설정 존재, CSP nonce 부채 해소, GitHub Actions CI/CD success 증적 존재. 단, staging deploy/smoke는 설정 부재로 skip되어 배포 접근성은 미검증 | 배포 절차 재검증 + post-deploy smoke 증적 |

```bash
# 재현: 테스트 베이스라인
pytest tests/ -m "not live" -q     # 2026-07-21 H91 실측: 4250 passed, 2 skipped, 4 deselected, 1 warning

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
python3 scripts/count_readme_metrics.py --field service_files     # → 44 (서비스)
python3 scripts/count_readme_metrics.py --field storage_files     # → 45 (top-level storage modules)
python3 scripts/count_readme_metrics.py --field middleware_files  # → 10 (미들웨어)
python3 scripts/count_readme_metrics.py --field route_decorators  # → 268 (라우트)
```

```text
Client (Web UI / CLI / API)
  │
  ▼
FastAPI (app/main.py — create_app(), 모듈 레벨 side-effect 없음)
  │
  ├─ Middleware layer (10개 Python 모듈)
  │     request chain: CORS → observability → request_id → security_headers
  │       → rate_limit → auth → tenant → billing → audit → metrics
  │     audit context helper: document_ops_audit
  │
  ├─ Routers (23 top-level files, 라우트 268):
  │     generate / approvals / projects / knowledge / report_workflows
  │     auth / sso / admin / audit / billing / dashboard / history
  │     eval / finetune / local_llm / g2b / document_ops_agent
  │     templates / styles / messages / notifications / events / health
  │
  ▼
Services (44) — 도메인 오케스트레이션
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
Providers (5)    Storage (45 modules)   Ops
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
6. Persisted review evidence는 missing과 corrupt를 구분하고, immutable artifact를 먼저 검증한 뒤 record를 conditional create/CAS로 확정하며 domain conflict와 store failure를 다른 오류 경계로 전달한다.
7. Project/approval mutation은 각 tenant별 단일 state object의 검증된 원문을 expected value로 사용하고, conditional create/CAS 충돌마다 최신 ownership·schema를 다시 검증한다. Approval은 상태 transition도 다시 검증한다.
8. Report workflow mutation은 tenant별 단일 state object에서 conditional create/CAS를 사용하고, 충돌마다 최신 workflow state와 domain transition을 재검증한다. Bounded mutation receipt는 public schema와 분리하고 손상 시 fail closed 처리한다.
9. Audit append는 기존 JSONL byte prefix를 보존한 채 conditional create/CAS로 확정하고, 충돌마다 최신 evidence를 다시 검증한다. 불확실 commit은 `log_id`와 exact entry read-back으로 조정한다.
10. Template/history/share mutation은 각각 tenant별 단일 state object에서 conditional create/CAS를 사용하고, 충돌마다 최신 ownership·schema·lifecycle 위에 변경을 재적용한다. Bounded private receipt와 target identity read-back은 public schema와 분리하고 손상 시 fail closed 처리한다.
11. Billing account mutation은 tenant별 단일 `billing.json`에서 conditional create/CAS를 사용하고, 충돌마다 최신 tenant·account schema 위에 plan·status·Stripe identity 변경을 재적용한다. Bounded private receipt는 public billing response와 분리하고 손상 시 fail closed 처리한다.
12. Usage event append와 summary 갱신은 각각 `usage.jsonl`과 `usage_summary.json`의 conditional create/CAS로 확정한다. Event log를 권위 원본으로 유지하고 정확히 하나의 검증된 trailing event gap만 summary에 재적용하며, 손상·변조·복수 gap은 원본 보존 상태로 fail closed 처리한다.
13. Prompt override, A/B experiment, request pattern mutation은 각 tenant별 state object의 conditional create/CAS로 확정한다. Override save receipt는 operation payload에 결속하고 refresh는 incarnation과 applied count를 유지한다. A/B assignment와 result는 같은 experiment identity에 결속하며, conclusion은 persisted result와 receipt에 맞는 private pending claim만 재개한다. Request clear는 최초 snapshot identity만 제거한다.
14. Bookmark, style profile, SSO config와 root tenant registry mutation은 각 단일 state object의 conditional create/CAS로 확정한다. 최대 32회 충돌마다 최신 ownership·schema·target identity 위에 operation을 재적용하고 최근 64개 private receipt로 commit 응답 유실 뒤 successor mutation을 조정한다. Bookmark/style target은 private identity/incarnation으로 replacement lifecycle을 구분하며 private metadata는 API와 profile-only reader에 노출하지 않는다.
15. Project knowledge는 tenant/project별 `index.json`을 단일 mutable authority로 두고 conditional create/CAS 충돌마다 최신 문서 집합에 mutation을 재적용한다. Content/style은 private incarnation 아래 immutable object로 발행하고 canonical path·size·SHA-256 binding이 있는 index record만 사용한다. 최근 64개 receipt와 object metadata는 public knowledge response에서 제거하며 여러 artifact와 index를 하나의 distributed transaction으로 과장하지 않는다.
16. DocumentOps는 tenant별 `trajectories.jsonl`과 `trajectory_metadata.json`을 선택된 `StateBackend`의 서로 분리된 mutable authority로 사용한다. Trajectory append/review와 governance metadata append는 각각 conditional create/CAS 충돌마다 최신 state에 최대 32회 재적용한다. SFT export, freeze, dry-run approval, execution request, pre-execution audit는 immutable object로 먼저 발행하고 metadata의 identity·size·SHA-256 binding이 있어야 download와 governance authority가 된다. Reviewer sign-off summary도 같은 backend prefix를 read-only로 읽는다. 두 mutable object와 여러 artifact를 한 distributed transaction으로 과장하지 않으며 private trajectory metadata는 public/SFT projection에서 제거한다.
17. DocumentOps governance artifact inventory는 Ops-key가 있는 read-only route에서만 제공한다. Metadata authority를 먼저 엄격 검증하고 다섯 managed directory의 object를 `referenced_verified`, `referenced_missing`, `referenced_tampered`, `invalid_reference`, `unreferenced`로 분류한다. Metadata snapshot 하나는 atomic하지만 여러 object 관측은 transaction이 아니며 자동 삭제 권한도 없으므로 concurrent write 가능성과 실제 cleanup 전에 재확인이 필요하다. Local browser는 같은 Ops-key route를 GET으로만 읽어 exact count와 문제 artifact를 보여주며, tenant 전환이나 후속 재조회보다 늦게 도착한 응답을 폐기하고 삭제 action을 제공하지 않는다.
18. DocumentOps governance review overview는 training governance, artifact inventory, reviewer sign-off를 service에서 각각 읽어 reviewer-facing 상태로 합성한다. 경계 drift, artifact integrity, governance blocker, human sign-off 순서로 먼저 조치할 문제를 선택하고 다음 검토 행동과 원본 report를 함께 반환한다. 세 조회를 하나의 atomic snapshot으로 과장하지 않으며 수동 재확인과 dataset upload, provider call, training, model promotion 권한 `false`를 응답과 화면에서 유지한다.
19. Governance overview의 수동 재확인은 source report의 top-level `generated_at`만 제외한 canonical SHA-256을 사용한다. Browser는 성공한 동일 tenant 응답만 현재 인증 세션 메모리에서 비교해 최초·동일·변경을 표시하고 logout·invalid session에서 기준을 제거한다. Fingerprint는 상태 비교용 read-only 값이며 persisted receipt, atomic snapshot, 외부 실행 권한으로 해석하지 않는다.
20. DocumentOps governance summary·overview·inventory·reviewer sign-off 조회와 sign-off handoff 다운로드는 route가 명시한 action으로 tenant append-only audit에 기록한다. Audit detail은 surface, aggregate status, read-only 여부와 fingerprint 비저장 사실만 보존하고 fingerprint 값, source report, reviewer record를 복사하지 않는다. Governance resource는 trajectory resource와 분리해 Admin Ops에서 독립적으로 필터링한다.
21. Browser에서 governance source를 바꾸는 export·freeze·dry-run approval·execution request·pre-execution audit 저장과 planning provider/model 변경이 성공하면 기존 overview는 즉시 stale 상태가 된다. 이 전환은 진행 중 overview 응답도 무효화하고 이전 fingerprint 기준은 유지한다. 성공한 새 overview 조회만 fresh 상태와 ready badge를 복구하며 실패·download·read-only 조회는 freshness를 올리지 않는다.
22. DocumentOps Trajectory Stats는 같은 tenant의 연속 조회마다 request version을 증가시키고, 가장 최근 요청의 성공 또는 오류만 화면에 반영한다. 이전 성공·실패와 tenant 전환 전 응답은 accepted·pending·export count나 오류 상태를 덮어쓰지 않는다.
23. DocumentOps Reviewed SFT export 목록은 export와 freeze 목록을 함께 읽는 요청마다 version을 증가시키고 현재 tenant의 가장 최근 요청만 렌더링한다. 늦게 끝난 이전 성공, HTTP 오류, JSON parse 오류는 최신 task-filtered artifact 목록과 오류 surface를 덮어쓰거나 stale 알림을 만들지 않는다.
24. DocumentOps Training Readiness는 같은 tenant의 연속 조회마다 독립 request version을 증가시키고 response, JSON parse, error branch에서 최신 여부를 다시 확인한다. 늦은 이전 성공이나 오류는 최신 export·freeze chain을 되돌리거나 과거 freeze를 dry-run 승인 대상으로 다시 노출하지 않는다.
25. DocumentOps Training Audit Checklist는 request version, tenant, provider/model query가 모두 현재 조건과 일치할 때만 checklist와 audit 목록을 렌더링한다. Planning 조건이 바뀌면 열린 checklist를 `RECHECK REQUIRED`로 낮추고 `Audit 저장` action을 제거하며, 성공한 audit 저장은 진행 중 이전 read를 무효화해 새 evidence를 가리지 않게 한다.
26. DocumentOps Training Execution Request Records는 같은 tenant의 연속 조회마다 독립 request version을 증가시키고 response, JSON parse, error branch에서 최신 여부를 확인한다. 늦은 이전 성공이나 오류는 최신 two-person guard 기록을 되돌리지 않으며, execution request 저장 뒤 시작되는 새 조회가 저장 전 진행 중 read보다 우선한다.
27. DocumentOps Training Adapter Contract과 Training Execution Rehearsal은 각자 request version, tenant, provider/model query가 현재 planning 조건과 일치할 때만 결과를 렌더링한다. Planning 조건이 변경되면 진행 중 응답을 무효화하고 이전 config 안전 표시와 artifact reference를 `RECHECK REQUIRED`로 대체한다.
28. DocumentOps SFT Export Preview와 Reviewed SFT artifact 목록은 요청을 시작한 tenant와 task 조건이 현재 선택과 일치할 때만 렌더링한다. Training Plan Preview도 독립 request version, tenant, provider/model query를 함께 확인한다. Task 또는 planning 조건이 바뀌면 진행 중 success/error를 폐기하고 열린 evidence를 `RECHECK REQUIRED`로 대체한다.

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

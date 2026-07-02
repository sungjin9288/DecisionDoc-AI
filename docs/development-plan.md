# DecisionDoc AI — 완성을 위한 기능 개발 계획 (Development Plan)

> 기준일: **2026-07-02** (저장소 점검 [docs/inspection-20260630.md](./inspection-20260630.md) 및 후속 정리 커밋 기준)
> 원칙: AGENTS.md 정직성 규칙 준수 — 모든 정량 수치는 재현 커맨드를 병기하고, 검증되지 않은 성과·운영 표현은 사용하지 않는다.
> 상위 방향 문서: [product_direction.md](./product_direction.md) · [product_execution_plan.md](./product_execution_plan.md) · [roadmap.md](./roadmap.md)

---

## 1. "완성"의 정의

이 프로젝트에서 완성은 "기능이 많다"가 아니라 다음 3가지를 충족한 상태로 정의한다.

| 축 | 현재 | 완성 기준 |
|----|------|-----------|
| **기능 검증** | mock/local 경로에서 전 기능 테스트 통과 (`pytest -m "not live"` → 2,690 passed, 2026-07-02) | 외부 의존 경로(live LLM, G2B 실데이터)도 최소 1회 실증 + 증적 |
| **아키텍처 위생** | ✅ 달성 (2026-07-02: 800줄 초과 15개 전부 분할 → 0개) | 전 모듈 800줄 이하 (전역 코딩 가이드), 계층 간 의존 방향 일관 |
| **운영 준비성** | Docker/SAM 설정 존재, 배포 접근성 미검증 | 배포 절차 재검증 + post-deploy smoke 증적, 보안 부채(CSP nonce) 해소 |

```bash
# 재현: 테스트 베이스라인
pytest tests/ -m "not live" -q     # 2026-07-02 실측: 2690 passed, 2 skipped
```

---

## 2. 현재 아키텍처 (실측 기반)

배포·인프라 관점 구성도(Nginx/TLS/PWA 포함)는 [architecture.md](./architecture.md) 참조. 여기서는 코드 레이어 관점을 다룬다. 레이어 수치는 아래 커맨드로 재측정 가능하다.

```bash
ls app/routers/*.py | grep -v __init__ | wc -l   # → 23 (라우터)
ls app/services/*.py | wc -l                     # → 37 (서비스)
ls app/storage/*.py | wc -l                      # → 36 (스토어)
ls app/middleware/*.py | grep -v __init__ | wc -l # → 9 (미들웨어)
grep -rE "@(app|router)\.(get|post|put|delete|patch)\(" app | wc -l  # → 254 (라우트)
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
  ├─ Routers (23, 라우트 254):
  │     generate / approvals / projects / knowledge / report_workflows
  │     auth / sso / admin / audit / billing / dashboard / history
  │     eval / finetune / local_llm / g2b / document_ops_agent
  │     templates / styles / messages / notifications / events / health
  │
  ▼
Services (37) — 도메인 오케스트레이션
  ├─ generation_service ─ 핵심 파이프라인:
  │     요청 → 캐시 → Provider.generate_bundle() → 스키마 검증
  │        → Stabilizer → Storage 저장 → Jinja2 렌더 → Lint → 반환
  ├─ export 계열: docx / pptx / pdf / hwp / excel (5종)
  ├─ 조달 계열: g2b_collector → procurement_decision_service
  │     → procurement_decision_package/ (13-모듈 패키지, 2026-07-02 분할)
  └─ 품질 계열: report_quality_learning / prompt_optimizer / validator
  │
  ├────────────────┬─────────────────────┐
  ▼                ▼                     ▼
Providers (5)    Storage (36 스토어)    Ops
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

| # | 갭 | 근거 (실측) | 심각도 | 상태 (2026-07-02) |
|---|-----|------------|--------|--------------------|
| G1 | **Live provider 미실증** — openai/gemini/claude 연동 코드는 완비, 실 API 호출 검증 0회 | `pytest -m live` 미실행 (키 필요) | HIGH | 미착수 (키 필요) |
| G2 | **G2B 실데이터 미실증** — collector 코드 존재, `G2B_API_KEY` 없이 비동작 | `app/services/g2b_collector.py` | HIGH | 미착수 (키 필요) |
| G3 | **800줄 초과 모듈** — 계획 수립 시 15개 | `find app -name '*.py' \| xargs wc -l \| awk '$1>800'` | MED | **✅ 완전 해소** (2026-07-02, 15개 전부 분할 → 초과 0개) |
| G4 | **excel export 비대칭** — 84줄로 타 export 대비 최소 구현 | `wc -l app/services/excel_service.py` | MED | **완료** (커밋 e9ecabc, 309줄·테스트 14개) |
| G5 | **CSP nonce 미적용** — `script-src 'unsafe-inline'` 의존 | `app/middleware/security_headers.py` | MED | **부분 완료** — nonce 배관 + `DECISIONDOC_CSP_NONCE_ENFORCED` 게이팅(기본 off). CSP 스펙상 nonce 존재 시 브라우저가 `'unsafe-inline'`을 전면 무시해 inline `on*=` 핸들러 ~340개가 파손되므로, 이벤트 위임 리팩토링(후속) 후 플래그 on |
| G6 | **배포 접근성 미검증** — 운영 URL 동작 보장 없음 (README §Scope 명시) | — | MED | 미착수 |
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

### M2 — G2B 실데이터 End-to-End (G2) · 외부 의존: `G2B_API_KEY` (data.go.kr)

- 작업:
  1. 실 공고 1건 수집 → 정규화 → decision package 산출까지 단일 케이스 통과.
  2. 산출 결과를 fixture로 고정해 회귀 테스트화 (키 없는 CI에서도 재현).
  3. GO / CONDITIONAL_GO / NO_GO 판정 재현성 확인.
- DoD: 실데이터 1건의 end-to-end 실행 증적 + 해당 케이스의 키-불필요 회귀 테스트. 입찰 제출·법적 승인은 범위 밖(기존 boundary 유지).

### M3 — Export 5종 대칭성 (G4) · 외부 의존 없음 · ✅ 완료 (2026-07-02, 커밋 e9ecabc)

- 결과: 표지+요약(메트릭)+doc_type별 다중 시트, 헤더 서식/열 너비/text_wrap, 빈 입력·특수문자·32,767자 한계·시트명 정규화 방어. `build_excel` 시그니처 무변경. 테스트 6→14개(openpyxl 재오픈 검증 포함).

### M4 — 보안 성숙: CSP Nonce (G5) · 외부 의존 없음 · ◐ 부분 완료 (2026-07-02, 커밋 0f9ff1e)

- 완료: 요청별 nonce 생성/HTML 스탬핑/헤더 배선 + 테스트. `DECISIONDOC_CSP_NONCE_ENFORCED` 플래그 게이팅(기본 off).
- 차단 요인(실측): index.html에 inline `on*=` 핸들러 ~340개(일부 JS 템플릿 리터럴로 런타임 생성). CSP 스펙상 script-src에 nonce가 존재하면 CSP L2+ 브라우저는 `'unsafe-inline'`을 **inline 핸들러 포함** 전면 무시하므로, 지금 nonce를 켜면 실브라우저에서 UI 파손.
- 후속(M4b): inline 핸들러를 `data-action` + 이벤트 위임으로 리팩토링 → 플래그 on → `'unsafe-inline'` 완전 제거.
- 갱신된 DoD: 이벤트 위임 완료 + 플래그 기본 on + CSP에 unsafe-inline 부재 + UI 스모크 정상.

### M5 — 코드 위생: 800줄 초과 모듈 분할 (G3) · 외부 의존 없음 · ✅ 완료 (2026-07-02, 800줄 초과 0개)

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

- DoD 달성: `find app -name '*.py' | xargs wc -l | awk '$1>800'` → **0개**. 전 분할이 순수 코드 이동(AST 동일성 검증) + facade(import 경로 무변경).

### M6 — 운영 준비성 (G6) · 외부 의존: 배포 환경

- 작업:
  1. Docker Compose · AWS SAM 배포 절차 재실행/재검증.
  2. post-deploy smoke(`scripts/smoke.py`, `scripts/ops_smoke.py`) 결과 증적화.
  3. 데모 URL 접근성 확인 후 README Links의 "Demo: (접근 검증 후 추가)" 갱신.
- DoD: 신규 환경에서 README 절차만으로 배포 재현 + smoke 통과 로그.

---

## 5. 실행 순서와 의존 관계

```text
M1 (live 실증) ──┐
                 ├──> README/evidence 갱신 ──> M6 (배포 검증)
M2 (G2B e2e)  ──┘
M3 (excel)  ── 독립, 수시 진행
M4 (CSP)    ── 독립, 수시 진행
M5 (분할)   ── 독립, 단 M1·M2와 같은 파일을 만질 때는 실증 후 진행
```

- **M1·M2가 최우선**: 코드가 아닌 "증거"가 완성의 병목이다.
- M3·M4·M5는 외부 의존이 없어 언제든 병행 가능.
- 각 마일스톤 완료 시 [roadmap.md](./roadmap.md)와 README 수치·한계 문구를 함께 갱신한다 (정직성 규칙).

## 6. 하지 않을 것 (Non-Goals)

- phase 클로저 영수증·documentops 산출물 재생성 (2026-07-02 정리 완료, `.gitignore`로 차단).
- 측정 근거 없는 성과 수치(비용 절감률, 정확도 등) 표기.
- 실제 입찰 제출·법적 승인·계약 확약을 암시하는 기능/문구.

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
| **아키텍처 위생** | 800줄 초과 모듈 15개 잔존 | 전 모듈 800줄 이하 (전역 코딩 가이드), 계층 간 의존 방향 일관 |
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

| # | 갭 | 근거 (실측) | 심각도 |
|---|-----|------------|--------|
| G1 | **Live provider 미실증** — openai/gemini/claude 연동 코드는 완비, 실 API 호출 검증 0회 | `pytest -m live` 미실행 (키 필요) | HIGH |
| G2 | **G2B 실데이터 미실증** — collector 코드 존재, `G2B_API_KEY` 없이 비동작 | `app/services/g2b_collector.py` | HIGH |
| G3 | **800줄 초과 모듈 15개** | `find app -name '*.py' \| xargs wc -l \| awk '$1>800'` | MED |
| G4 | **excel export 비대칭** — 84줄로 타 export(777~1,410줄) 대비 최소 구현 | `wc -l app/services/excel_service.py` | MED |
| G5 | **CSP nonce 미적용** — `script-src 'unsafe-inline'` 의존 | `app/middleware/security_headers.py` | MED |
| G6 | **배포 접근성 미검증** — 운영 URL 동작 보장 없음 (README §Scope 명시) | — | MED |

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

### M3 — Export 5종 대칭성 (G4) · 외부 의존 없음

- 작업: excel export를 타 포맷과 동등한 수준으로 — 다중 시트(문서 유형별), 헤더 서식, 메타데이터 시트. endpoint 테스트를 docx/pptx 수준으로 보강.
- DoD: 5종 export 모두 동등한 테스트 커버리지(생성·다운로드·경계 케이스), excel 산출물 샘플 저장.

### M4 — 보안 성숙: CSP Nonce (G5) · 외부 의존 없음

- 작업:
  1. `security_headers.py`에 요청별 nonce 생성 → 템플릿/정적 HTML의 inline script에 nonce 부여.
  2. `script-src 'unsafe-inline'` 제거.
  3. 보안 헤더 회귀 테스트 갱신 (`tests/test_infrastructure.py` CSP 테스트).
- DoD: CSP에 unsafe-inline 부재 + nonce 검증 테스트 통과 + UI 스모크 정상.

### M5 — 코드 위생: 800줄 초과 모듈 분할 (G3) · 외부 의존 없음

2026-07-02에 `procurement_decision_package_service.py`(4,883줄)를 13-모듈 패키지로 분할한 패턴(순수 코드 이동 + facade re-export + AST 동일성 검증)을 재사용한다. 우선순위:

| 순서 | 모듈 | 줄 수 | 분할 방향 |
|------|------|------|-----------|
| 1 | `app/storage/trajectory_store.py` | 2,665 | 기록/조회/집계 분리 |
| 2 | `app/services/generation_service.py` | 2,331 | 파이프라인 단계별 (cache/provider 호출/렌더/lint) |
| 3 | `app/routers/admin.py` | 2,246 | 도메인별 sub-router (tenants/models/audit) |
| 4 | `app/routers/generate.py` | 2,170 | 생성/부가기능(refine·translate·review) 분리 |
| 5 | `app/providers/mock_provider.py` | 1,794 | 번들 유형별 fixture 모듈 분리 |
| … | 나머지 10개 (805~1,468줄) | — | 위 5개 완료 후 동일 패턴 |

- DoD: 분할 대상 모듈 800줄 이하 + 기존 import 경로 무변경 + 전체 회귀 통과.

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

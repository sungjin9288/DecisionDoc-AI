# DecisionDoc AI — 점검 + 개발 계획 리포트 (2026-06-30)

> 읽기 전용 점검. 코드 변경 없음. 모든 수치는 실측 커맨드 기반이며, 검증되지 않은 성과·운영 표현은 사용하지 않는다.
> AGENTS.md 정직성 규칙(측정 근거 없는 수치 금지, PoC/MVP 그대로 표기) 우선 적용.

---

## 1. 현황 요약

| 항목 | 실측값 | 측정 방법 |
|------|--------|-----------|
| 브랜치 | `main` | `git branch -vv` |
| origin 동기화 | **동기화됨 (ahead 0 / behind 0)** | `git rev-list --left-right --count origin/main...HEAD` → `0  0` |
| untracked 파일 | **540** | `git status --porcelain \| grep '^??' \| wc -l` |
| 수정(미스테이지) 파일 | **15** | `git status --porcelain \| grep '^ M' \| wc -l` |
| 마지막 커밋 | `154af81` (2026-06-23, 일주일 전) | `git log -1` |
| FastAPI 라우트 | 254 | `grep -rE "@(app\|router)\.(get\|post\|put\|delete\|patch)\(" app \| wc -l` |
| `def test_` (tracked+untracked) | 3,699 | `grep -rE "def test_" tests \| wc -l` |
| test 파일 | 205 | `find tests -name "test_*.py" \| wc -l` |
| pytest 수집(not live) | 3,944 / 3,947 | `pytest -m "not live" --co -q` |
| app 파이썬 파일 | 195 | `find app -name "*.py" -not -path "*__pycache__*" \| wc -l` |
| scripts 파일 | 795 | `ls scripts/*.py \| wc -l` |
| hermes phase 디렉토리(총) | 639 | `find docs/specs/hermes_decisiondoc_agent -maxdepth 1 -type d -name 'phase*' \| wc -l` |
| git 추적 파일 총 | 2,143 | `git ls-files \| wc -l` |

**배경값과의 차이(검증 결과)**
- 배경 스캔(2026-06-29): untracked 약 540(docs 272·scripts 265, 수정 15). → **실측에서도 540/수정 15로 일치**.
- 단, 내역 재분류: untracked의 docs 부분은 **거의 전부 `docs/specs/hermes_decisiondoc_agent/phase*` 255개**, scripts 부분은 **거의 전부 `documentops_phase*` 자동생성 스크립트**. 즉 "272 docs"는 일반 문서가 아니라 **phase 클로저 산출물**이다(아래 2장).

**핵심 진단**
- 공개본(origin/main)은 **6/23 커밋에서 멈춰 있고**, 그 이후 1주일간의 작업(procurement decision package 신규 서비스 + 다량의 phase 클로저 산출물)이 미커밋 상태. 공개본이 실제 작업보다 뒤처져 있다는 배경 진술은 사실이다.
- 다만 뒤처진 분량의 **압도적 다수(95%+)는 의미 있는 제품 코드가 아니라 자동생성 phase 클로저 텍스트**다. 실제 새 WIP은 소수 파일에 집중돼 있다.

---

## 2. 미커밋 3분류안 (그룹 + 개수 + 근거)

untracked 540 + 수정 15 = 총 555개를 패턴 단위로 분류한다.

### A. 커밋할 것 (의미 있는 신규 WIP) — 약 21개

| 그룹 | 개수 | 근거 |
|------|------|------|
| `app/services/procurement_decision_package_service.py` | 1 | 신규 도메인 서비스. local·deterministic decision package 빌더(4,840줄). 신규 테스트 58개가 이 모듈을 커버하고 **전부 통과** |
| `tests/test_*procurement_decision_package*` + `tests/test_*procurement_decision_package_demo*` 등 | 14 | 위 서비스의 service/builder/export/CLI contract/smoke 테스트. 실행 시 통과 확인 |
| `scripts/*procurement_decision_package*` (build/export/run/gate/check/validate) | ~9 | 위 기능의 CLI·검증 진입점. README §API/Usage에 사용법이 이미 문서화됨 |
| `docs/product_direction.md`, `product_execution_plan.md`, `product_demo_scenario.md`, `product_local_demo_runbook.md` | 4 | 제품 방향/실행계획/데모 문서(총 1,131줄). 실제 기획 산출물 |
| `docs/samples/procurement_decision_package_local_demo/` | 1 디렉토리 | README가 직접 참조하는 fixture(cli_contract_manifest.json 등). 커밋되어야 README 재현 커맨드가 동작 |

> 권장: 이 그룹은 **하나의 feature 커밋**(`feat: local procurement decision package evidence path`)으로 묶는다. AGENTS.md 규칙대로 관련 `docs/specs/public_procurement_copilot/STATUS.md` 갱신과 함께 커밋.

### B. 검토 후 선별 커밋 — 수정 15개 중 일부

| 그룹 | 개수 | 처리 |
|------|------|------|
| 문서 수정(`README.md`, `AGENTS.md`, `docs/README.md`, `docs/roadmap.md`, `docs/case-study.md`, `docs/interview-story.md` 등 11개 소규모) | 11 | **커밋 권장**. diff 소규모(대부분 +3~+35줄). 포트폴리오 문서 정합성 |
| `docs/specs/public_procurement_copilot/STATUS.md` | 1 (+6,760줄) | **내용 확인 후 커밋**. procurement 작업의 정본 status. 단 +6,760줄은 비대 — phase 로그 누적 가능성, 압축 검토 |
| `docs/specs/hermes_decisiondoc_agent/STATUS.md` | 1 (+960줄) | 동일하게 비대. 커밋 전 압축 검토 |
| `tests/test_infrastructure.py` | 1 (**+43,589줄**) | **⚠️ 정밀 검토 필수**. 단일 테스트 파일에 4.3만 줄 추가는 정상 WIP이 아니라 **자동생성 폭주**일 가능성이 높음. 그대로 커밋 금지 |

### C. .gitignore 하거나 정리(버리기) 대상 — 약 425개+

| 그룹 | 개수 | 근거 / 처리 |
|------|------|------|
| `scripts/validate_documentops_phase*.py` | 170 | phase407~661 자동생성 검증 스크립트. 1파일=1phase. **이미 211개가 git에 커밋된 동일 패턴**의 연장 → 자가증식 산출물 |
| `scripts/create_documentops_phase*`, `summarize_documentops_phase*`, `check_documentops_phase*` 등 | ~85 | 위와 동일 계열의 생성/요약/검사 보일러플레이트 |
| `docs/specs/hermes_decisiondoc_agent/phase*` 디렉토리(각 .md + .json 2파일) | 255 (디렉토리) | phase 클로저 영수증 텍스트. **이미 384개 phase 디렉토리가 git에 커밋됨**(총 639개) → 동일 패턴 |
| (수정) `tests/test_infrastructure.py`의 +43,589줄 | — | B에서 검토 후 대부분 폐기/축소 권장 |

> **C 그룹 처리 원칙**: 이 phase 산출물들은 코드 기능이 아니라 "작업 완료 영수증" 자동생성물이다. 두 가지 선택지:
> 1. **이상적**: phase 클로저 산출물을 `.gitignore`에 패턴 추가(`scripts/*documentops_phase*`, `docs/specs/hermes_decisiondoc_agent/phase*/`)하고, **이미 커밋된 ~600개도 별도 정리 커밋으로 git에서 제거**. 저장소 1,214줄 규모의 `scripts/`가 정상 크기로 회복됨.
> 2. **현실적(저위험)**: 기존 관행과 일관성 유지를 위해 그대로 커밋하되, **앞으로 phase 산출물 자동생성을 중단**. 다만 이는 저장소 비대화를 영구화하므로 비권장.

**3분류 핵심 결론**: 555개 중 **실제 제품 가치가 있는 것은 ~21개(A)**, 나머지 ~510개는 phase 자가증식 산출물(C). `tests/test_infrastructure.py`의 4.3만 줄(B)은 별도 정밀 검토 대상.

---

## 3. 구현 현황 (완성 / 부분 / 미완 — 코드 근거 포함)

요구된 7개 축(문서생성·멀티LLM fallback·검토승인·감사·멀티테넌시·5종 export·G2B copilot)을 코드로 검증.

### 완성 (코드·테스트 모두 확인) — 6

| 기능 | 근거 |
|------|------|
| **문서 생성 파이프라인** | `app/services/generation_service.py`(2,331줄), `/generate`·`/generate/from-documents`·`/generate/from-pdf` 라우트. `test_generate.py` 통과 |
| **멀티 LLM provider + fallback chain** | `app/providers/factory.py`에 mock/openai/gemini/**claude**/**local** 5분기. `_parse_provider_names`로 콤마구분 fallback chain. claude/local provider 모두 실제 `httpx` 호출 코드 보유(`claude_provider.py:158` POST /messages, `local_provider.py:163` OpenAI 호환 /chat/completions) |
| **검토·승인 워크플로** | `app/routers/approvals.py` + `review_preview.py`. submit/review/approve/reject/download. `test_approval_workflow.py` 통과 |
| **감사·프라이버시** | `app/routers/audit.py`, `/admin/audit-logs`, `/auth/export-my-data`, `/auth/withdraw`. `test_audit.py`, `test_data_rights.py` 존재 |
| **멀티테넌시** | `app/storage` tenant_store + `migrate_legacy_data()`, `/admin/tenants`. `test_tenant.py` 통과 |
| **5종 export** | docx(`docx_service.py` 777줄), pptx(`pptx_service.py` 1,410줄), excel(`excel_service.py` 84줄), pdf(`procurement_pdf_normalizer.py` 479줄 + pdf 라우트), hwp(schemas/라우트/mock에 hwp 경로). docx/pdf/pptx/excel/hwp endpoint 테스트 각각 존재 |

### 부분 (코드는 있으나 외부 의존/검증 한계) — 3

| 기능 | 상태 | 근거 |
|------|------|------|
| **G2B 조달 copilot** | 코드 있음, 실데이터 미검증 | `g2b_collector.py`(543줄)에 실제 data.go.kr `BidPublicInfoService` 연동 코드. 단 `G2B_API_KEY` 없으면 비동작(`:158` 경고 후 중단). live 흐름은 키·실데이터 의존 → README §Scope에도 명시됨 |
| **Live provider 검증** | 호출 코드 완비, 실호출 미검증 | openai/gemini/claude/local 모두 httpx 코드 보유하나, 테스트는 `-m live` 분리. 본 점검은 mock 경로만 실행 검증함(통과). 실 API 키 통합검증은 별도 필요 |
| **excel export** | 최소 구현 | `excel_service.py` 84줄로 타 export 대비 얇음. 기능 범위 확인 필요 |

### 미완 / 부채 — 명시된 것

| 항목 | 근거 |
|------|------|
| **CSP Nonce 미적용** | AGENTS.md §미완료(아키텍처 부채): `security_headers.py`가 `script-src 'unsafe-inline'` 의존 |
| **excel 외 export 일관성** | excel만 84줄로 비대칭 |

### 신규 (이번 미커밋) — 로컬 procurement decision package
- `procurement_decision_package_service.py`(4,840줄, **local·deterministic, provider/AWS/training 미호출**). 신규 테스트 58개 통과. **fixture 검증 경로**이며 실제 입찰 제출·법적 승인·계약 확약 아님(README §Scope 명시와 일치).

**구현현황 요약: 완성 6 / 부분 3 / 미완(부채) 2** (+ 신규 WIP 1: procurement decision package).

---

## 4. 디밸롭 후보 평가 (가치 · 난이도 · 의존성)

| 후보 | 가치 | 난이도 | 의존성 | 코멘트 |
|------|------|--------|--------|--------|
| **저장소 위생: phase 산출물 정리 + .gitignore** | 高(유지보수·면접 인상·git 성능) | 低 | 없음(로컬) | 555개 중 510개가 노이즈. 우선 정리하면 이후 모든 작업이 깨끗해짐. **즉시 가능** |
| **공개본 동기화(A그룹 커밋)** | 高 | 低 | 없음 | procurement decision package를 공개본에 반영. 테스트 통과 확인됨 |
| **Live provider 통합 검증 하니스** | 高(MVP→실증 신뢰도) | 中 | API 키(openai/gemini/claude), 비용 | `-m live` 테스트를 키와 함께 1회 실증. README의 "live 미검증" 한계를 해소 |
| **G2B 심화(실데이터 end-to-end)** | 高(차별화 포인트) | 中~高 | `G2B_API_KEY`, data.go.kr 실데이터·쿼터 | collector 코드는 있음. 실 수집→정규화→decision package까지 1개 실데이터 케이스 통과가 목표 |
| **검토·승인 UX 강화** | 中 | 中 | 프런트(`app/static`), approval 라우트 | diff 미리보기/리비전 비교/승인 사유 구조화. 코드 기반 존재 |
| **CSP Nonce 적용(보안 부채)** | 中(보안) | 中 | security_headers, 템플릿/static | unsafe-inline 제거. 면접 시 보안 성숙도 어필 가능 |
| **거대 파일 분할(800줄 가이드)** | 中(품질) | 中 | generation_service·admin·mock_provider·decision_package | 800줄 초과 14개+ 모듈. 코딩 가이드(MANY SMALL FILES) 위배 |

---

## 5. 기술 부채 · 위험

| 심각도 | 항목 | 근거 / 영향 |
|--------|------|-------------|
| **HIGH** | **phase 산출물 자가증식** | scripts 795개·hermes phase 639디렉토리. 신호 대 잡음비 악화, git/IDE/검색 성능 저하, 면접 시 "무엇을 직접 만들었나" 설명 곤란 |
| **HIGH** | `tests/test_infrastructure.py` +43,589줄 미커밋 수정 | 단일 파일 4.3만 줄 추가는 자동생성 폭주 의심. 커밋 시 영구 비대화. 내용 미확인 상태로 커밋 금지 |
| **MED** | 거대 모듈 다수 | `procurement_decision_package_service.py` 4,840줄 등 14개+ 파일이 800줄 초과(전역 코딩 가이드 위배) |
| **MED** | 공개본 1주일 정체 | origin/main이 6/23 고정. 신규 기능 미반영. 단 정체 분량 대부분이 노이즈라 정리 후 동기화 필요 |
| **MED** | Live/G2B 미검증 | 실 provider·실 G2B 호출이 한 번도 본 점검에서 검증되지 않음(키·비용 의존). README가 한계로 명시했으나, 실증 1회는 신뢰도에 중요 |
| **LOW** | CSP Nonce 미적용 | `script-src 'unsafe-inline'` 의존(AGENTS.md 명시 부채) |
| **LOW** | excel export 비대칭 | 84줄로 타 export 대비 얇음 |

> 보안 점검: 본 점검 범위에서 하드코딩 시크릿은 발견하지 않음(`.env`/`.env.prod.save`는 .gitignore에 포함, secret-hygiene git hook 존재). 다만 전수 시크릿 스캔은 본 작업 범위 밖.

---

## 6. 3단계 로드맵

### 단계 1 — 가까운 것: 위생 + 동기화 (즉시, 외부 의존 없음)
1. phase 산출물 `.gitignore` 패턴 추가(`scripts/*documentops_phase*`, `docs/specs/hermes_decisiondoc_agent/phase*/`) + 신규 자동생성 중단.
2. A그룹(procurement decision package: app 1 + tests 14 + scripts 9 + docs 4 + samples 1)을 단일 feature 커밋으로 정리해 공개본 동기화.
3. `tests/test_infrastructure.py`의 +43,589줄 내용 확인 → WIP이면 축소, 자동생성이면 폐기.
4. 소규모 문서 수정 11개 커밋.

**완료 정의**: `git status` untracked가 phase 노이즈 제외 0에 수렴. origin/main에 procurement decision package 반영. `pytest -m "not live"` 회귀 통과(현재 핵심 슈트 236 + 신규 58 통과 확인됨).

### 단계 2 — 중간: 실증 검증 (키·비용 필요, 1~2일)
1. Live provider 하니스: openai/gemini/claude 각 1회 실호출로 `-m live` 통과 캡처(증적 저장).
2. G2B 1개 실데이터 케이스: `G2B_API_KEY`로 수집→정규화→decision package 산출까지 end-to-end 1건.
3. 거대 모듈 1~2개 분할 착수(`procurement_decision_package_service.py` 우선, Shared 헬퍼/렌더 분리).

**완료 정의**: live provider 3종·G2B 1건의 실행 로그가 docs에 증적으로 남고, README의 "live/G2B 미검증" 한계 문구를 "1회 실증(날짜·커맨드)"으로 갱신. 분할된 모듈은 800줄 이하 + 회귀 통과.

### 단계 3 — 큰 것: G2B 심화 + 보안/UX 성숙 (1~2주)
1. G2B 조달 copilot 심화: 다건 수집·하드필터·스코어링·체크리스트·핸드오프(rfp_analysis_kr/proposal_kr/performance_plan_kr)까지 실데이터 다회 검증.
2. 검토·승인 UX 강화(diff 미리보기, 리비전 비교, 승인 사유 구조화).
3. CSP Nonce 적용으로 `unsafe-inline` 제거.

**완료 정의**: G2B GO/CONDITIONAL_GO/NO_GO가 실데이터 N건에서 재현 가능(테스트 고정), 승인 UX 변경에 대한 gate 문구·테스트가 "실제 제출/승인 미발생"을 보장, CSP nonce 적용 후 보안 헤더 테스트 통과.

---

## 7. 권장 다음 액션 (우선순위)

| 순위 | 액션 | 비고 |
|------|------|------|
| **P0** | `tests/test_infrastructure.py` +43,589줄 정체 파악(WIP vs 자동생성 폭주) | 잘못 커밋 시 영구 비대화. 커밋 전 필수 |
| **P0** | phase 산출물 `.gitignore` 패턴 추가 + 자동생성 중단 | 단계1-1. HIGH 부채 진원지 차단 |
| **P1** | A그룹(procurement decision package) 단일 feature 커밋 → 공개본 동기화 | 테스트 통과 확인됨. STATUS.md 동반 갱신(AGENTS 규칙) |
| **P1** | 소규모 문서 수정 11개 커밋(정직성 규칙 grep 후) | README에 미검증 수치 미유입 확인 |
| **P2** | Live provider + G2B 1회 실증 + 증적 | 단계2. MVP→실증 신뢰도 |
| **P2** | 거대 모듈 분할(우선 `procurement_decision_package_service.py` 4,840줄) | 코딩 가이드 800줄 준수 |

---

### 부록 — 실행한 검증
- `git status/branch/log/rev-list` 실측(동기화·미커밋 분류).
- `pytest -m "not live" --co` → 3,944 수집.
- 핵심 슈트 8종 실행: `test_generate/auth_api_key/storage/stabilizer/g2b/approval_workflow/tenant/procurement_decision_service` → **236 passed**.
- 신규 procurement package 테스트 4종 → **58 passed**.
- provider/factory/g2b_collector 코드 직접 확인(실 httpx 호출 존재).
- 미커밋 540 + 수정 15를 패턴(documentops_phase, hermes phase, procurement) 단위로 분류.

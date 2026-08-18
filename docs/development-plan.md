# DecisionDoc AI — 완성을 위한 기능 개발 계획 (Development Plan)

> 기준일: **2026-08-17** (저장소 점검 [docs/inspection-20260630.md](./inspection-20260630.md), DocumentOps strict skill binding focused no-cost verification, local live G2B smoke와 current-main deploy-smoke 시도 기준)
> 원칙: AGENTS.md 정직성 규칙 준수 — 모든 정량 수치는 재현 커맨드를 병기하고, 검증되지 않은 성과·운영 표현은 사용하지 않는다.
> 상위 방향 문서: [product_direction.md](./product_direction.md) · [product_execution_plan.md](./product_execution_plan.md) · [roadmap.md](./roadmap.md)

---

## 1. "완성"의 정의

이 프로젝트에서 완성은 "기능이 많다"가 아니라 다음 3가지를 충족한 상태로 정의한다.

| 축 | 현재 | 완성 기준 |
|----|------|-----------|
| **기능 검증** | DocumentOps browser provenance verification + free local runtime no-cost gate: full non-live `4,576 passed, 4 deselected` (2026-08-17). 2026-08-11 local live G2B smoke 1건 통과 | live LLM 잔여 provider와 G2B durable receipt/stage 경로도 실증 + 증적 |
| **아키텍처 위생** | ✅ 달성 (2026-07-14: 829줄 상수 모듈을 604줄 facade + 314줄 foundation으로 분리하고 800줄 guard 추가 → 초과 0개). CI advisory Ruff E/F/W와 Bandit medium/high 0건 기준 유지 | 전 모듈 800줄 이하 (전역 코딩 가이드), 계층 간 의존 방향 일관 |
| **운영 준비성** | Docker/SAM 설정 존재, CSP nonce 부채 해소, 과거 GitHub Actions CI/CD success 증적 존재. 2026-08-11 current-main dev deploy-smoke는 AWS 진입 전 OIDC role assume에서 실패 | OIDC trust 복구 + 배포 절차 재검증 + post-deploy smoke 증적 |

```bash
# 재현: 테스트 베이스라인
PYTHONDONTWRITEBYTECODE=1 pytest tests/ -q --ignore=tests/e2e -m 'not live' --tb=short --disable-warnings
# 2026-08-17 current: 4576 passed, 4 deselected

# 재현: CI advisory lint/security 베이스라인
ruff check app/ tests/ --select=E,F,W --ignore=E501
bandit -r app/ -x app/providers/mock_provider.py -ll

# 재현: 남은 외부 실증 준비 조건 점검(외부 호출 없음)
python3 scripts/check_completion_readiness.py --print-env-template
python3 scripts/check_completion_readiness.py --print-proof-plan
python3 scripts/check_completion_readiness.py
python3 scripts/check_completion_readiness.py --env-file .env.prod
python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
```

2026-08-12 DocumentOps strict skill binding focused gate는 registry·Agent·API·operation store·audit `143 passed`였다. 이는 mock provider와 local/fake-S3 범위의 재측정이며 위 full non-live baseline, live provider 품질 또는 AWS runtime 증거를 대체하지 않는다.

같은 날짜 browser binding boundary의 static focused command는 `4 passed`, local Chromium focused command는 `9 passed`였다. Static check는 exact eight-field binding validator, top-level skill/version agreement, invalid response의 pre-success 차단과 allowlisted provenance renderer를 검사한다. Chromium check는 valid first run과 exact replay, malformed·authority-widened·mismatched response rejection, 기존 Agent recovery 흐름을 검증했고 desktop과 390px mobile screenshot에서 provenance overlap과 horizontal overflow가 없음을 확인했다. Browser console과 page error도 비어 있었다. 이 결과는 local loopback과 mock response 범위이며 live provider나 배포 runtime 증거를 대체하지 않는다.

DocumentOps comparison review는 source-grounded task와 함께 UI에서 선택할 수 있는 first-party skill이다. 비교 입력은 provider·captured-operation claim 전에 검증하고, `comparison_criteria`는 생략 시 `[]`이며 최대 8개·각 120자다. Local mock/backend와 loopback Chromium 측정은 exact UTF-8 hash context, raw-input trajectory redaction, exact replay, malformed context pre-success rejection과 390px overflow를 대상으로 하며 semantic change·policy/legal/operational effect는 사람 재확인 대상으로 남긴다. GitHub-derived skill-pattern reference는 [external repository analysis](./specs/external_repo_integration/ANALYSIS_20260812.md)의 clean-room design 기록만 사용하며 remote skill loading, dynamic install, provider/training/deploy/publication authority를 추가하지 않는다. Live provider, AWS runtime, external completion proof는 M1/M6의 기존 갭으로 변함없다.

Comparison file intake는 동일 task 안의 optional local convenience path다. Existing attachment parser의 20 MB upload와 12,000-character cap을 그대로 사용하고 `.hwp` legacy binary, unsupported, empty, unreadable input을 bounded `422`로 거부한다. API response와 browser check는 exact selected source bytes와 returned UTF-8 text hash를 결속하지만, semantic equivalence, source authenticity, policy/legal effect 또는 file retention을 주장하지 않는다. 이 path는 deterministic server-memory extraction만 제공하며 provider fallback/OCR, storage persistence, training, AWS, deployment, publication과 approval authority를 추가하지 않는다.

Verified line change set은 Agent provider 요청보다 먼저 local-only deterministic evidence를 만든다. 하나의 `SequenceMatcher(autojunk=False)` 결과로 full aggregate와 hunk를 계산하고 response 전체의 양쪽 exposed line 합계를 200으로 제한한 contiguous zero-prefix만 반환한다. 첫 초과 hunk는 exposed array와 half-open range를 함께 clip하며, `total_hunk_count`와 `hunks_truncated`는 전체 opcode coverage를 보존한다. Browser가 exact response bytes/header hash, fatal UTF-8, canonical JSON, strict schema, source hash/line/range/count, all-false authority와 current provenance를 모두 확인해야 Agent POST와 download가 열리고, 입력·criteria·task·tenant·auth 또는 request generation 변경은 evidence와 object URL을 폐기한다. 이 local change set은 semantic review, live provider 품질, AWS/deployment/public edge, persistence, training, approval 또는 external effect evidence가 아니다.

```bash
python3 -m pytest -q tests/test_infrastructure.py -k document_ops_agent --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k document_ops_agent --tb=short
python3 -m pytest -q tests/agents/test_skill_registry.py tests/agents/test_document_ops_agent.py tests/evals/test_document_ops_gates.py tests/test_document_ops_agent_api.py --tb=short
python3 -m pytest -q tests/test_infrastructure.py -k document_ops --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k document_ops --tb=short
python3 -m pytest -q tests/test_document_ops_agent_api.py -k comparison_document --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k comparison_file_intake --tb=short
python3 -m pytest -q tests/agents/test_document_ops_agent.py -k comparison --tb=short
python3 -m pytest -q tests/test_document_ops_agent_api.py -k comparison --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k comparison_change_set --tb=short
```

### H120 local slice

Project procurement packet은 활성 tenant admin/member의 stable user ID에 담당자를 결속하고, completion은 같은 current session-bound principal만 허용한다. v2 reviewed package attestation은 trusted tenant/project/user scope로 재검증하며 approval, bid, legal, contractual authority를 만들지 않는다. Focused H120 `64 passed`, auth/security/tenant `216 passed`, focused Chromium `1 passed`, 전체 non-live `4437 passed, 1 skipped, 4 deselected`로 no-cost 검증했다.

### H121 session-bound review access

Review packet preparation, inbox, project history와 reviewed package download는 current session-bound admin/member만 접근한다. Admin은 tenant-wide review를 관리하고 member는 자신에게 결속된 v2 evidence만 읽는다. HTTP와 browser surface는 stable target ID, receipt, rationale, attestation, session/network metadata를 노출하지 않으며 current assignment와 access scope만 사용한다. 기존 v1 storage와 reviewed package는 admin read compatibility를 유지한다. Focused procurement/auth/storage `191 passed`, focused Chromium `3 passed`, 최종 전체 non-live `4444 passed, 2 skipped, 4 deselected`로 no-cost 검증했다.

### H122 verified original review packet re-download

현재 session-bound admin 또는 stable v2 assignee는 저장된 원본 review packet을 다시 내려받을 수 있다. Route는 authorization 뒤에만 bytes를 읽고 SHA-256, receipt/record binding, package semantics와 recommendation을 다시 검증한다. Browser는 safe response headers, byte length와 SHA-256을 확인한 뒤 download를 시작하며 auth, tenant, user, project context가 바뀌면 scoped object URL과 fallback link를 폐기한다. Legacy v1은 admin-only이고 review reassignment/completion, operational approval, bid submission, provider/training/deploy authority는 추가하지 않았다. Post-review focused API/audit/infrastructure `286 passed`, focused Chromium `3 passed`, 전체 Chromium `88 passed, 1 skipped`, 전체 non-live `4448 passed, 2 skipped, 4 deselected`로 no-cost 검증했다.

### H123 Decision Evidence Map

Project detail은 procurement, Decision Council, project document, authorized
review summary, approval, report workflow와 knowledge metadata를
`decision_evidence_map.v1` read-only projection으로 연결한다. Member는 자신의
exact review assignment가 확인된 뒤에만 project를 읽고, unassigned,
differently assigned, nonexistent ID는 동일한 not-found 결과로 닫는다.
Canonical `requirement:` reference만 explicit reference coverage를 만들며
requirement 만족 증명으로 승격하지 않는다. Proposal Blueprint는 stored
reference count와 PPTX readiness만 보여주고 export/provider/approval/bid/legal
authority를 만들지 않는다. Luna 독립 review에서 발견한 assignment access,
existence oracle, misleading evidence label과 800-line guide 문제를 모두
해소했다. Focused Decision Evidence `16 passed`, 인접 project/report/review/
approval/Council/PPTX `383 passed`, focused+infrastructure `184 passed`, 최종
전체 non-live `4465 passed, 1 skipped, 4 deselected`로 no-cost 검증했다.
이 수치는 2026-07-24 H123 historical baseline이며 H124 current pass 수치가 아니다.

### H124 Evidence Neighborhood Explorer

H123 projection을 변경하지 않고 project detail의 read-only 탐색성을 강화한다.
Browser state는 tenant, user, auth revision, project, bundle, projection
fingerprint에 결속하고 scope 변경 시 선택·filter·presentation layout을 초기화한다.
Bounded response에서 O(N+E) adjacency index를 만들고 selected node의 inbound/
outbound relation과 stored provenance를 표시한다. One-hop focus/dimming,
gaps/lineage/source visibility filter, diagnostic target navigation, keyboard
focus restoration, reduced-motion, 60-node SVG priority와 complete table을
제공한다. 이 surface는 approval, export execution, provider/training, bid
submission 또는 legal authority를 만들지 않는다.

Luna review 반영으로 filtered diagnostic target은 다른 node로 대체하지 않고
명시적으로 포함하며 filter summary에 그 상태를 표시한다. Source visibility는
detail relation과 incident edge에도 적용한다. SVG는 pointer interaction만 남긴
장식 surface이고 table button이 canonical keyboard surface다. Provenance level은
authoritative=solid, record binding=dashed, derived=dotted line style로
비색상 설명하며 proof/approval을 뜻하지 않는다. Content SHA-256도 projection이
관측한 field-content binding일 뿐 external authenticity 검증이 아니다.
2026-07-27 no-cost fresh gate는 H124 UI/service/E2E subset `17 passed`, API를
포함한 focused `21 passed`, adjacent authorization/workflow `387 passed`,
combined union `404 passed`, full non-live `4,470 passed, 1 skipped,
4 deselected`다.

### H125 Guided Decision Review

Project detail의 existing decision, Evidence Map, review, document record를
Decision → Evidence → Review → Documents 순서의 읽기 전용 검토 navigator로
묶는다. 하나의 overall state와 recommended next check만 표시하며 status는
`not_observed`, `needs_attention`, `in_review`, `observed`로 제한한다.
`decision_evidence_map.v1`의 exact top-level/nested shape, coverage invariant,
bounded graph, fingerprint와 여섯 false authority flag가 모두 유효할 때만
panel을 렌더링한다. Map이 없거나 malformed, authority-drifted이면 다른
project payload에서 evidence state를 재구성하지 않고 숨긴다.

Stage control은 기존 section으로 scroll/focus만 수행한다. 승인, export,
provider, bid submission, legal/contractual action을 호출하지 않는다.
Accepted review는 acceptance record 관측일 뿐 current freshness가 아니며,
document는 canonical review/Council/provenance status 중 하나 이상이
관측되고 모두 `current`일 때만 current로 표시한다. Council payload가
독립 요청에서 빠져도 map의 stale/conflict diagnostic은 Decision
precedence를 유지한다. Luna independent review의 malformed map, document
freshness, Council diagnostic, NO_GO copy, informational diagnostic severity,
loading-path 회귀를 모두 보완했다.

2026-07-27 no-cost fresh gate는 H125 focused `7 passed`, H124+H125 static/E2E
`13 passed`, adjacent authorization/workflow `387 passed`, combined union
`411 passed`, full non-live `4,477 passed, 1 skipped, 4 deselected`다.

### H126 Guided Decision Review Handoff

현재 Guided Decision Review의 four-stage observation을 current
session-bound admin 또는 exact stable v2 assignee가 canonical JSON attachment로
내려받을 수 있다. Route는 authorized `decision_evidence_map.v1` context와
project document provenance를 다시 관측하고
`guided-decision-review-handoff.v1`을 만든다. Exact body SHA-256과 source
projection fingerprint를 response header에 결속하고 `no-store`, `nosniff`,
attachment disposition을 고정한다.

Browser는 body hash, contract/source version, tenant/user/auth revision/project
load scope, project/bundle/fingerprint, non-empty fresh-route source timestamp,
exact four-stage status, overall/next check와 six false authority fields를
현재 panel과 다시 대조한 뒤 download한다. Route가 projection을 새로
계산하므로 source timestamp는 화면 map과 달라질 수 있고 semantic binding은
timestamp equality가 아니라 exact fingerprint equality를 사용한다.
Handoff는 저장하지 않으며
`read_only=true`, `snapshot_atomic=false`,
`requires_recheck_before_reliance=true`, `handoff_persisted=false`다. 따라서
download hash는 exact bytes만 증명하며 currentness, atomic snapshot, proof,
approval, export/provider/bid/legal authority를 만들지 않는다.

2026-07-28 no-cost focused gate는 H126 service/API/static/Chromium
`15 passed`, H123-H126 map/guided-review integration `38 passed`, reusable
document provenance serializer를 포함한 project/map regression `149 passed`,
authorization/audit/security/infrastructure expansion `477 passed`다. 전체
non-live는 `4,487 passed, 1 skipped, 4 deselected`다.

### H127 Guided Decision Review Handoff Recheck

Browser가 H126 response의 exact body hash, safe headers, contract, current map과
tenant/user/auth/project scope를 검증한 경우에만 source handoff를 page memory에
보존하고 recheck를 활성화한다. Session-bound read-only POST route는 strict H126
source와 canonical SHA-256, route project와 current bundle binding을 확인한 뒤
같은 service path로 fresh H126 observation을 만든다.

`guided-decision-review-recheck-receipt.v1`은 source/current handoff와 각 exact
hash, `source_generated_at`만 제외한 두 semantic fingerprint, expected
`unchanged|changed` status를 canonical JSON으로 결속한다. Receipt와 audit은
review-only/read-only/non-atomic/recheck-required/non-persisted 경계와 six false
authority를 유지한다. `changed`는 정상 비교 결과이며 browser는 receipt를
검증·다운로드한 뒤 old source를 폐기하고 fresh project load/handoff를
요구한다. Client-supplied source는 prior server issuance를 증명하지 않고
`unchanged`도 future currentness나 atomic snapshot을 보장하지 않는다.

2026-07-28 no-cost gate는 H126/H127 service/API/static/Chromium `23 passed`,
H123-H127 map/guided-review integration `46 passed`, authorization/audit/
security/infrastructure expansion `481 passed`, full non-live `4,495 passed,
1 skipped, 4 deselected`다. Provider, AWS, G2B, dataset upload, training,
promotion, deployment와 service resume은 실행하지 않았다.

### H128 Guided Decision Review Disposition

Browser가 exact body/header/contract/scope를 검증한 H127 receipt만 page memory에
보존하고 allowlisted disposition을 선택할 수 있다. Session-bound read-only
POST route는 strict H127 receipt, canonical receipt hash, route project/current
bundle, current handoff/fingerprint, expected status를 다시 검증한다.

`guided-decision-review-disposition-receipt.v1`은 source receipt hash, current
handoff/fingerprint hash, `unchanged|changed` status와 disposition을 canonical
binding으로 결속한다. `unchanged`에는
`acknowledged_unchanged|review_deferred`, `changed`에는
`new_handoff_required|review_deferred`만 허용한다. Receipt는 review-only,
read-only, non-atomic, recheck-required, non-persisted이며 reviewer identity,
approval, mutation, export, provider, bid 또는 legal/contractual authority를
만들지 않는다.

Luna review에서 nested fixed-field 누락이 Pydantic default로 복원되던 문제,
POST bundle allowlist 우회, auth/tenant invalidation 뒤 page-memory source가
남던 문제를 찾았다. Terra remediation은 raw request의 명시 필드 검증,
schema-level bundle allowlist, 중앙 source cleanup으로 세 경계를 닫았다.
재검토에서 cross-tab auth event의 cleanup 우회와 pre-parsed service receipt의
field-set 소실을 추가로 찾아 같은 validator와 cleanup 경로로 보완했고, final
Luna review는 findings 없이 종료됐다.

2026-07-29 no-cost gate는 H126-H128 service/API/static/Chromium `37 passed`,
H123-H128 map/guided-review integration `60 passed`, authorization/audit/
security/infrastructure expansion `488 passed`, full non-live `4,509 passed,
1 skipped, 4 deselected`다. Provider, AWS, G2B, dataset upload, training,
promotion, deployment와 service resume은 실행하지 않았다.

### H129 Guided Decision Review Disposition Registry

H129 persists one exact H128 receipt as immutable reviewer-attributed evidence
under tenant/project/bundle/hashed-operation scope. First create returns 201;
an exact replay after username or role drift returns 200 with the original
canonical bytes and historical identity, while stable reviewer or source drift
conflicts without rewriting the authoritative record. All registry paths
strictly revalidate the nested H126-H128 chain, request/full-record bindings,
scope, matrix, hashes, and false authority before returning data.

Admin access is project-wide and assigned member access is stable-user scoped.
Browser create is enabled only from current verified page-memory H128 evidence,
uses one UUID per source/scope plus request-owned single flight, and discards
late responses after auth/tenant/user/project/bundle/source drift. H129 closes
no M1/M2/M6, human UAT, deployment, prior H128 server-issuance, or external
approval gap; provider, AWS, G2B, upload, training, promotion, deploy, approval,
bid, legal, and contractual effects remain outside the slice.

2026-08-18 local/mock verification은 H129 focused storage/API/auth/audit
`16 passed`, adjacent handoff/static `28 passed`, focused Chromium
`1 passed, 13 deselected`, full non-E2E non-live `4,596 passed, 4 deselected`,
full non-live E2E `121 passed, 1 skipped`를 확인했다. Ruff E/F/W, `py_compile`,
Bandit medium/high, secret hygiene, portfolio와 diff gates도 통과했다.

---

## 2. 현재 아키텍처 (실측 기반)

배포·인프라 관점 구성도(Nginx/TLS/PWA 포함)는 [architecture.md](./architecture.md) 참조. 여기서는 코드 레이어 관점을 다룬다. 레이어 수치는 아래 커맨드로 재측정 가능하다.

```bash
python3 scripts/count_readme_metrics.py --field router_files      # → 23 (top-level 라우터 파일)
python3 scripts/count_readme_metrics.py --field service_files     # → 50 (서비스)
python3 scripts/count_readme_metrics.py --field storage_files     # → 52 (top-level storage modules)
python3 scripts/count_readme_metrics.py --field middleware_files  # → 12 (미들웨어)
python3 scripts/count_readme_metrics.py --field route_decorators  # → 296 (라우트)
python3 scripts/count_readme_metrics.py --field test_files        # → 277 (테스트 파일)
python3 scripts/count_readme_metrics.py --field test_functions    # → 3833 (Python AST test_ 정의; pass 수 아님)
```

```text
Client (Web UI / CLI / API)
  │
  ▼
FastAPI (app/main.py — create_app(), 모듈 레벨 side-effect 없음)
  │
  ├─ Middleware layer (12개 Python 모듈)
  │     request chain: CORS → observability → request_id → security_headers
  │       → rate_limit → auth → tenant → billing → audit → metrics
  │     audit context helpers: document_ops_audit / auth_session_retention_audit
  │       / procurement_review_audit
  │
  ├─ Routers (23 top-level files, 라우트 296):
  │     generate / approvals / projects / knowledge / report_workflows
  │     auth / sso / admin / audit / billing / dashboard / history
  │     eval / finetune / local_llm / g2b / document_ops_agent
  │     templates / styles / messages / notifications / events / health
  │
  ▼
Services (50) — 도메인 오케스트레이션
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
Providers (5)    Storage (51 modules)   Ops
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
16. DocumentOps는 tenant별 `trajectories.jsonl`과 `trajectory_metadata.json`을 선택된 `StateBackend`의 서로 분리된 mutable authority로 사용한다. Trajectory append/review와 governance metadata append는 각각 conditional create/CAS 충돌마다 최신 state에 최대 32회 재적용한다. SFT export, freeze, dry-run approval, execution request, pre-execution audit는 immutable object로 먼저 발행하고 metadata의 identity·size·SHA-256 binding이 있어야 download와 governance authority가 된다. Reviewer sign-off summary도 같은 backend prefix를 read-only로 읽는다. Agent run은 service가 operation claim 전에 first-party skill을 strict public binding으로 resolve하고 canonical request identity에 포함한다. Binding은 schema version, skill name/version, risk, content SHA-256, catalog fingerprint와 code-execution/external-runtime false authority만 포함하며 instruction과 source path는 제외한다. Agent는 expected binding drift, unknown skill과 unsupported task mapping을 provider 접근 전에 거부한다. 성공 결과·trajectory·stored replay는 같은 binding을 유지하고 legacy `skill_name`/`skill_version`을 보존한다. 두 mutable object와 여러 artifact를 한 distributed transaction으로 과장하지 않으며 private trajectory metadata는 public/SFT projection에서 제거한다.
17. DocumentOps governance artifact inventory는 Ops-key가 있는 read-only route에서만 제공한다. Metadata authority를 먼저 엄격 검증하고 다섯 managed directory의 object를 `referenced_verified`, `referenced_missing`, `referenced_tampered`, `invalid_reference`, `unreferenced`로 분류한다. Metadata snapshot 하나는 atomic하지만 여러 object 관측은 transaction이 아니며 자동 삭제 권한도 없으므로 concurrent write 가능성과 실제 cleanup 전에 재확인이 필요하다. Local browser는 같은 Ops-key route를 GET으로만 읽어 exact count와 문제 artifact를 보여주며, tenant 전환이나 후속 재조회보다 늦게 도착한 응답을 폐기하고 삭제 action을 제공하지 않는다.
18. DocumentOps governance review overview는 training governance, artifact inventory, reviewer sign-off를 service에서 각각 읽어 reviewer-facing 상태로 합성한다. 경계 drift, artifact integrity, governance blocker, human sign-off 순서로 먼저 조치할 문제를 선택하고 다음 검토 행동과 원본 report를 함께 반환한다. 세 조회를 하나의 atomic snapshot으로 과장하지 않으며 수동 재확인과 dataset upload, provider call, training, model promotion 권한 `false`를 응답과 화면에서 유지한다.
19. Governance overview의 수동 재확인은 source report의 top-level `generated_at`만 제외한 canonical SHA-256을 사용한다. Browser는 성공한 동일 tenant 응답만 현재 인증 세션 메모리에서 비교해 최초·동일·변경을 표시하고 logout·invalid session에서 기준을 제거한다. Fingerprint는 상태 비교용 read-only 값이며 persisted receipt, atomic snapshot, 외부 실행 권한으로 해석하지 않는다.
20. DocumentOps governance summary·overview·inventory·reviewer sign-off 조회와 sign-off handoff 다운로드는 route가 명시한 action으로 tenant append-only audit에 기록한다. Audit detail은 surface, aggregate status, read-only 여부와 fingerprint 비저장 사실만 보존하고 fingerprint 값, source report, reviewer record를 복사하지 않는다. Authenticated Agent run은 별도 action/resource로 task type, binding SHA-256, replay 여부와 code-execution/external-runtime false authority만 DocumentOps detail에 더하고 instruction, source path, request/source body, credential, provider response는 남기지 않는다. Governance resource는 trajectory 및 Agent run resource와 분리해 Admin Ops에서 독립적으로 필터링한다.
21. Browser에서 governance source를 바꾸는 export·freeze·dry-run approval·execution request·pre-execution audit 저장과 planning provider/model 변경이 성공하면 기존 overview는 즉시 stale 상태가 된다. 이 전환은 진행 중 overview 응답도 무효화하고 이전 fingerprint 기준은 유지한다. 성공한 새 overview 조회만 fresh 상태와 ready badge를 복구하며 실패·download·read-only 조회는 freshness를 올리지 않는다.
22. DocumentOps Trajectory Stats는 같은 tenant의 연속 조회마다 request version을 증가시키고, 가장 최근 요청의 성공 또는 오류만 화면에 반영한다. 이전 성공·실패와 tenant 전환 전 응답은 accepted·pending·export count나 오류 상태를 덮어쓰지 않는다.
23. DocumentOps Reviewed SFT export 목록은 export와 freeze 목록을 함께 읽는 요청마다 version을 증가시키고 현재 tenant의 가장 최근 요청만 렌더링한다. 늦게 끝난 이전 성공, HTTP 오류, JSON parse 오류는 최신 task-filtered artifact 목록과 오류 surface를 덮어쓰거나 stale 알림을 만들지 않는다.
24. DocumentOps Training Readiness는 같은 tenant의 연속 조회마다 독립 request version을 증가시키고 response, JSON parse, error branch에서 최신 여부를 다시 확인한다. 늦은 이전 성공이나 오류는 최신 export·freeze chain을 되돌리거나 과거 freeze를 dry-run 승인 대상으로 다시 노출하지 않는다.
25. DocumentOps Training Audit Checklist는 request version, tenant, provider/model query가 모두 현재 조건과 일치할 때만 checklist와 audit 목록을 렌더링한다. Planning 조건이 바뀌면 열린 checklist를 `RECHECK REQUIRED`로 낮추고 `Audit 저장` action을 제거하며, 성공한 audit 저장은 진행 중 이전 read를 무효화해 새 evidence를 가리지 않게 한다.
26. DocumentOps Training Execution Request Records는 같은 tenant의 연속 조회마다 독립 request version을 증가시키고 response, JSON parse, error branch에서 최신 여부를 확인한다. 늦은 이전 성공이나 오류는 최신 two-person guard 기록을 되돌리지 않으며, execution request 저장 뒤 시작되는 새 조회가 저장 전 진행 중 read보다 우선한다.
27. DocumentOps Training Adapter Contract과 Training Execution Rehearsal은 각자 request version, tenant, provider/model query가 현재 planning 조건과 일치할 때만 결과를 렌더링한다. Planning 조건이 변경되면 진행 중 응답을 무효화하고 이전 config 안전 표시와 artifact reference를 `RECHECK REQUIRED`로 대체한다.
28. DocumentOps SFT Export Preview와 Reviewed SFT artifact 목록은 요청을 시작한 tenant와 task 조건이 현재 선택과 일치할 때만 렌더링한다. Training Plan Preview도 독립 request version, tenant, provider/model query를 함께 확인한다. Task 또는 planning 조건이 바뀌면 진행 중 success/error를 폐기하고 열린 evidence를 `RECHECK REQUIRED`로 대체한다.
29. Captured DocumentOps Agent 응답을 잃은 browser는 status schema, operation ID, state별 timestamp·replay·next-action, read-only와 provider-call 비승인을 모두 확인한다. Mismatched·unavailable·running 상태의 tenant와 payload는 현재 page memory에만 보존하고 Agent 버튼과 상태 재확인 버튼을 recovery promise 하나에 결속한다. Terminal success만 exact replay를 허용하며 logout·invalid session은 pending payload를 제거한다. Reload 이후 복구와 외부 provider 실행 권한은 이 browser state가 제공하지 않는다.
30. Captured Agent POST 직전에는 schema version, tenant ID, browser UUID operation ID만 browser marker로 남기고 payload는 browser storage에 저장하지 않는다. Marker는 strict `no-store` status 확인과 새 POST 차단에만 사용하며 exact replay authority가 아니다. Operator가 backend 실행 비취소와 evidence 확인 경고를 승인해 상태 추적을 종료해야 marker를 제거한다. Invalid marker와 auth/tenant context 변경은 marker를 폐기하고, storage 접근 실패는 same-page Agent 실행을 막지 않는다.
31. Captured Agent browser marker는 same-origin `localStorage`를 shared primary로 사용하고 접근 실패 시 현재 tab의 `sessionStorage`로 내려간다. 지원 browser에서는 tenant별 Web Lock 안에서 기존 marker 확인과 새 marker 기록을 직렬화해 동시 tab 중 owner 하나만 POST를 시작하게 한다. 다른 tab과 owner tab 종료 뒤 다시 연 화면은 payload 없는 marker로 status만 조회하며 explicit release 전까지 새 POST를 막는다. 두 storage가 모두 막히면 reload/cross-tab guard는 없고, Web Locks 미지원 환경에서는 완전 동시 claim의 atomicity를 보장하지 않는다. 다른 browser/device, process-crash recovery, cross-ID semantic deduplication, exactly-once provider execution과 external provider authority도 이 marker가 제공하지 않는다.
32. Captured Agent marker storage key는 tenant별로 분리한다. 같은 origin의 foreign tenant read/write/clear는 다른 tenant marker를 보존하고, 승인된 tenant 전환은 previous tenant marker만 제거한다. H96 base-key marker는 strict schema를 통과한 뒤 owning tenant만 legacy fallback으로 읽고 제거하며 foreign tenant는 이를 잘못된 marker로 삭제하지 않는다. Marker body의 exact 3-field payload-free contract와 backend operation authority는 바꾸지 않는다.
33. Browser tenant context는 signed token 또는 selector access preflight만으로 부분 전환하지 않는다. `dd_tenant_id` 저장이 성공한 뒤에만 in-memory tenant와 previous-context draft/recovery/marker를 변경하며, storage write 실패는 기존 context evidence를 그대로 보존한다. Browser storage는 durable handoff를 위한 commit point일 뿐 authorization authority가 아니다.
34. Browser auth session은 login, register, refresh, LDAP login 모두 같은 commit helper를 사용한다. Token claims를 먼저 검증하고 access/refresh token을 쓴 뒤 signed tenant ID를 마지막 commit point로 저장한다. Snapshot을 확보한 뒤 write가 하나라도 실패하면 이전 access/refresh token과 tenant를 복원하고 current user와 DocumentOps evidence를 바꾸지 않는다. 동시 401은 tab 내 하나의 refresh promise에 합류한다. Generic API 오류 경로는 refresh 성공 뒤에도 실패한 mutating request를 자동 replay하지 않고 명시적 재시도를 요구한다. 현재 tab의 commit/cleanup뿐 아니라 같은 origin의 다른 tab에서 access token, refresh token, tenant ID 또는 전체 local storage가 바뀌어도 session revision을 올려 진행 중인 이전 refresh 응답을 폐기하며, unrelated storage key는 revision에 영향을 주지 않는다. 다른 tab의 최종 signed user·tenant·role·credential version이 현재 page와 다르면 reload를 한 번만 요청해 page-memory evidence를 새 authorization context에서 다시 구성하고, 네 값이 같은 token rotation은 reload하지 않는다.
35. Browser 401 recovery는 refresh 결과를 성공, credential 거절, 일시적 endpoint 장애, browser storage commit 실패로 구분한다. 성공만 원 요청을 한 번 재시도하고 credential 거절만 invalid-session cleanup을 수행한다. 일시 장애와 storage 실패는 기존 token, tenant, current user, review draft와 pending recovery evidence를 보존하고 재시도 가능한 오류를 표시한다.
36. Protected request authorization은 access token의 signed tenant/user identity를 tenant `UserStore`의 현재 role과 `is_active`에 다시 결속한다. Persisted user가 없거나 비활성이면 token 만료 전에도 `401`, role이 바뀌면 현재 role로 RBAC를 적용하고 state read가 실패하면 `503`으로 fail closed 처리한다. Middleware public 예외인 `/events`도 query access token을 같은 authority로 검사한다. Auth와 SSO user lifecycle route는 앱이 생성될 때 확정한 data root와 `StateBackend`를 공유하므로 process env drift가 request authority를 분리하지 않는다. Fresh install에 user state가 전혀 없는 legacy compatibility만 token payload를 유지하며, 별도 revocation table이나 cross-device push invalidation은 제공하지 않는다.
37. Password change는 password hash와 persisted `credential_version` 증가를 한 user-state CAS mutation으로 확정한다. Access/refresh token은 발급 시 version을 포함하고 protected request, SSE query token, refresh exchange가 현재 user version과 다르면 `401`로 거부한다. 변경 요청을 보낸 browser만 응답의 새 token pair를 atomic session helper로 commit하고, 같은 origin의 다른 tab은 version mismatch에서 reload한다. Legacy versionless record/token은 현재 version 0일 때만 호환한다. 이는 password change 기반 전체 token 폐기이며 exact-session 선택 폐기는 다음 불변식에서 별도로 정의한다.
38. 열린 `/events` SSE는 연결 시점의 인증만으로 계속 전달하지 않는다. 최대 15초 간격으로 같은 query token의 expiry와 persisted user/session authority를 다시 확인하고, invalid이면 `auth_revoked`, authority read가 실패하면 `auth_unavailable` control event만 보낸 뒤 unsubscribe한다. Browser는 revoked event를 기존 single-flight refresh에 연결하고 refresh credential 거절만 invalid-session cleanup으로 처리한다. Temporary authority·endpoint·storage failure는 token, current user와 page-memory evidence를 보존하고 polling과 reconnect를 사용한다. Stale source callback은 현재 replacement EventSource를 닫거나 reconnect timer를 만들 수 없다. 이는 bounded revalidation이며 즉시 cross-device push나 15초보다 짧은 termination SLA는 제공하지 않는다.
39. Register·login·invite·LDAP·SAML·GCloud·password-change token pair는 selected local/S3 backend에 conditional create한 tenant-scoped `auth-session.v2` object의 random session ID를 공유하고 refresh도 그 ID를 유지한다. 기존 `auth-session.v1` object는 strict read compatibility를 유지하고 label mutation 시 v2로 승격한다. Protected request, refresh와 `/events`는 exact owner·credential version·expiry·revoked state를 확인한다. `/auth/logout`은 현재 signed session만 CAS로 폐기하고 다른 로그인 session을 보존한다. 본인 inventory는 tenant prefix 전체를 strict 검증한 뒤 현재 credential version의 active record만 `no-store`로 반환한다. `PATCH /auth/sessions/label`은 본인 active session에 최대 40자의 user-supplied 기기 이름 또는 `null`을 CAS 저장하고 foreign·missing·inactive target을 같은 `404`로 숨긴다. Selected revoke는 current target을 `409`, foreign/missing target을 같은 `404`로 거부하고 already-revoked owner retry를 success로 조정한다. Other-session bulk revoke는 strict `confirm=true` 뒤 current를 제외한 active snapshot을 폐기하고, all-device bulk revoke는 같은 user·version의 snapshot 전체를 current-last 순서로 폐기한다. Browser profile은 session ID를 DOM에 넣지 않고 label/save/revoke action에 같은 single-flight와 stale-response guard를 적용하며 all-device 성공 뒤에만 local credential과 page-memory evidence를 정리한다. Corrupt·unavailable state는 원본 보존 `503`으로 닫고 audit은 action/result, aggregate count만 남기며 token, session ID와 user-supplied label을 복사하지 않는다. Bulk 작업은 distributed transaction이 아니므로 중간 write failure가 일부 다른 session 폐기를 남길 수 있고 current-write response-loss와 요청 뒤 생성된 session도 원자적으로 조정하지 않는다. 일반 browser logout은 local cleanup을 즉시 수행하고 endpoint failure를 서버 폐기 미확인 경고로 구분한다. Legacy sessionless token은 exact logout·inventory·label·selected/bulk revoke를 사용할 수 없다. Session state/inventory에 User-Agent/IP를 자동 결합하는 기능, admin mass revoke, expired-session GC와 즉시 push는 제공하지 않는다.
40. Auth-session label은 request boundary에서 trim한 뒤 40자로 제한하고 API schema와 persisted-state decode가 같은 validator를 사용한다. Unicode control, surrogate, line/paragraph separator와 bidirectional·invisible format 문자는 거부하되 ZWNJ/ZWJ는 자연어와 emoji 조합을 위해 허용한다. Direct storage mutation의 비정규 입력과 persisted drift는 원본 bytes를 다시 쓰지 않고 fail closed 처리한다.
41. Auth-session retention preview는 admin JWT 또는 Ops key만 허용하고 selected local/S3 backend의 tenant prefix 전체를 strict 검증한다. `auth-session-retention-preview.v1` 응답과 audit은 user ID, session ID와 label을 제외한 aggregate만 사용하고 `read_only=true`, `deletion_authorized=false`, `no-store`를 유지한다. 조회는 object를 쓰거나 삭제하지 않으며 corrupt·unavailable state는 원본 보존 `503`으로 닫는다. 실제 deletion, scheduler와 retention policy 적용은 별도 명시 승인 전까지 이 계약 밖이다.
42. Ops auth-session retention UI는 access token 또는 Ops key가 있을 때만 preview를 호출하고 30/90/180/365일 selector와 icon refresh만 제공한다. Browser는 version, read/delete boundary, aggregate count와 timestamp consistency를 strict 검증하고 현재 tenant의 최신 request generation만 렌더링한다. Invalid/stale 응답은 aggregate를 표시하지 않으며 삭제·scheduler·mutation control은 추가하지 않는다.
43. Auth-session retention policy comparison은 admin JWT 또는 Ops key 아래 한 번의 strict prefix inspection에서 30/90/180/365일 aggregate를 함께 계산한다. `auth-session-retention-comparison.v1`은 exact policy order와 count/timestamp monotonicity를 유지하고 `read_only=true`, `deletion_authorized=false`, `snapshot_atomic=false`, `requires_recheck_before_mutation=true`를 명시한다. Browser selector는 검증된 comparison만 다시 렌더링하고 refresh만 새 request를 시작한다. 응답·audit에는 user ID, session ID, label과 token을 포함하지 않으며 실제 deletion과 scheduler 권한은 추가하지 않는다.
44. Auth-session retention review handoff는 선택한 30/90/180/365일 policy와 한 번 strict inspection한 comparison을 tenant-bound `auth-session-retention-review-handoff.v2` JSON attachment로 전달한다. Canonical comparison SHA-256와 exact response-body SHA-256을 함께 검증하며 `review_only=true`, `policy_change_authorized=false`, `deletion_authorized=false`, `scheduler_authorized=false`, `snapshot_atomic=false`, `requires_recheck_before_mutation=true`, `handoff_persisted=false`를 고정한다. v1은 역사적 evidence로만 남고 recheck 입력으로는 사용하지 않는다. Browser는 hash, flag, current tenant/request generation을 통과한 response만 화면과 download에 사용하고, audit은 selected policy·aggregate count·read-only 경계만 남긴다. Session delete, scheduler, policy 저장/적용과 server-side handoff persistence는 추가하지 않는다.
45. Auth-session retention handoff freshness recheck는 exact v2 source handoff와 canonical source hash를 tenant/authority/comparison contract까지 검증한 뒤 같은 policy의 fresh inspection을 `auth-session-retention-recheck-receipt.v1`으로 전달한다. Receipt는 source/current handoff와 SHA-256, stable aggregate fingerprint SHA-256, `aggregate_status`, `fingerprint_algorithm=sha256`, `volatile_fields_excluded`, `aggregate_only=true`, false policy/delete/scheduler authority, `snapshot_atomic=false`, `requires_recheck_before_mutation=true`, `recheck_persisted=false`를 고정한다. `unchanged`는 aggregate equivalence일 뿐 session set identity나 mutation safety가 아니며, `changed`는 정상적인 read-only 결과로 새 handoff가 필요함을 뜻한다. Browser는 page memory의 verified source만 사용하고 selector, refresh, tenant·auth context change와 newer request가 이전 source 또는 completion을 폐기한다. Durable history는 aggregate-only audit에 한정하며 session, policy, scheduler, handoff와 receipt를 저장하지 않는다.

---

## 3. 갭 분석 — 무엇이 완성을 막고 있나

| # | 갭 | 근거 (실측) | 심각도 | 상태 (2026-07-13) |
|---|-----|------------|--------|--------------------|
| G1 | **Live provider 부분 실증** — OpenAI 1회 통과, Gemini/Claude/fallback 성공 proof 잔여 | 2026-07-13 M1 blocked receipt | HIGH | 진행 중 (Gemini quota, Anthropic credits 필요) |
| G2 | **G2B stage proof 잔여** — local live 수집·평가 1건은 통과했지만 durable receipt와 AWS stage 경로는 미검증 | `scripts/run_local_procurement_smoke.py`, `docs/specs/public_procurement_copilot/STATUS.md` | HIGH | 부분 완료 (2026-08-11 local live smoke) |
| G3 | **800줄 초과 모듈** — 계획 수립 시 15개 | `find app -name '*.py' -print0 \| xargs -0 wc -l \| awk '$2 != "total" && $1 > 800 {print}'` | MED | **✅ 해소 및 guard 적용** (2026-07-14, 상수 모듈 drift 재분할 → 초과 0개) |
| G4 | **excel export 비대칭** — 84줄로 타 export 대비 최소 구현 | `wc -l app/services/excel_service.py` | MED | **완료** (커밋 e9ecabc, 309줄·테스트 14개) |
| G5 | **CSP nonce 부채** — served HTML `script-src 'unsafe-inline'` 의존 해소 필요 | `app/middleware/security_headers.py`, `app/static/index.html` | MED | **✅ 완료** — inline `on*=` 핸들러 0개, HTML 응답 nonce 기본 on, `DECISIONDOC_CSP_NONCE_ENFORCED=0` local diagnostic opt-out 유지 |
| G6 | **배포 접근성 미검증** — current-main dev deploy-smoke가 AWS OIDC `AssumeRoleWithWebIdentity`에서 차단돼 stack inspection과 runtime smoke에 도달하지 못함 | GitHub Actions `deploy-smoke` run `31452991725` | MED | OIDC trust 복구 필요 |
| G7 | **모듈 레벨 side-effect** — `app/main.py`의 `app = create_app()`이 import 시점에 `.env`를 로드해 테스트 격리를 해침 | — | MED | **✅ 해결** (2026-07-02, 커밋 0023c7c) — PEP 562 모듈 `__getattr__`로 lazy 생성(캐싱). `uvicorn app.main:app`·Mangum·기존 import 전부 무변경 동작 |

---

생성 export packet의 source는 이제 selected local/S3 backend에 bounded durable state로 보존되어 restart·독립 worker 재다운로드를 지원한다. 이는 local implementation/integrity 범위를 보강한 것이며 M1 live provider, M2 G2B stage receipt, M6 AWS deploy/runtime proof의 외부 실증 갭을 해소하지 않는다.

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
- 2026-07-14 local 준비: `run_stage_procurement_smoke.py --proof-receipt`가 preflight를 미실행 `blocked` 상태로, 실제 smoke를 `passed` 또는 `failed` 상태로 atomic 기록한다. Host와 안전한 공고 식별자만 남기고 API key, password, URL userinfo/query는 receipt에서 제외한다.
- 2026-08-11 local 실증: real FastAPI app, temporary local storage, mock LLM provider와 live G2B auto-discovery로 공고 `R26BK01664082`를 수집·정규화·평가하고 `NO_GO`, Decision Council, downstream block/override/retry smoke를 통과했다. 이 결과는 no-AWS local evidence이며 M2 durable proof receipt나 deployed stage runtime을 대신하지 않는다.

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
- 2026-08-11 무료 local baseline: `DECISIONDOC_FREE_MODE=1`에서 cloud provider 직접 생성과 factory chain, S3 bundle/state storage, remote local-LLM endpoint를 fail closed로 차단한다. `run_free_local.py`는 mock 또는 loopback Ollama만 선택하고 provider capability, local data root, search/finetune disablement와 cloud secret clearing을 강제한다. Inherited AWS profile/container/web-identity source를 제거하고 metadata/shared config credential lookup도 비활성화한다. 기본 `docker-compose.yml`도 mock/local/free mode로 시작하며 production compose와 SAM 전환은 별도 proof 경계로 유지한다.

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

### H119 local reviewer registry

H119 is a completed no-cost local slice. It adds a session-admin-only immutable disposition registry while retaining H118 as a non-persistent deterministic receipt. Parent/Luna review findings were remediated, focused retention `36 passed, 238 deselected`, broad auth/security `500 passed`, full Chromium `84 passed, 1 skipped`, and full non-live `4429 passed, 1 skipped, 4 deselected`. Paid provider, G2B, AWS runtime, Stripe, Statuspage, deployment, and service resume were not run.

## 6. 하지 않을 것 (Non-Goals)

- phase 클로저 영수증·documentops 산출물 재생성 (2026-07-02 정리 완료, `.gitignore`로 차단).
- 측정 근거 없는 성과 수치(비용 절감률, 정확도 등) 표기.
- 실제 입찰 제출·법적 승인·계약 확약을 암시하는 기능/문구.

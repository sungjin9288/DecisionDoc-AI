# Procurement Opportunity And Applicability Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for native execution in this task. Checkboxes below are the progress record; do not create a second ledger or task.

**Goal:** 같은 프로젝트에서 공고별 판단과 문서를 분리하고, 근거가 있는 개별 요구사항의 적용 여부를 기록한다.

**Architecture:** 기존 StateBackend의 CAS에 프로젝트 aggregate를 저장한다. decision_id로 공고를 고정하고 revision을 평가, Council, 검토, 생성, 문서 조회까지 전달한다. N/A는 이 식별 체계 위의 요구사항 증빙이며 점수나 승인 우회 기능이 아니다.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, local/fake-S3 StateBackend, 기존 JavaScript shell, pytest/Playwright.

**Spec:** [승인된 설계](../specs/2026-09-21-procurement-opportunity-and-applicability-design.md)

## Global Constraints

- 2026-09-21 사용자 승인에 따른 로컬·fake-S3 개발과 검증만 수행한다.
- 실사용 DATA_DIR 전환, live G2B/AWS/provider, 학습, 배포, install, commit/push는 제외한다.
- 현재 branch의 기존 dirty 변경을 보존한다. 별도 worktree에 미반영 코드를 누락시키지 않는다.
- 구현과 통합은 현재 task에서 직접 수행한다. 보조 Agent를 사용한 경우 실제
  모델·역할·검토 범위를 실행 기록에 구분하고 task 자체의 모델 전환으로 표현하지 않는다.
- 저장 계층 완성은 기능 전체 완료가 아니다. 모든 consumer가 준비되기 전에는 기존 앱에 v2 write를 연결하지 않는다.
- 기존 단일 공고와 immutable snapshot/ZIP/receipt를 보존한다.
- 신규 Request는 strict/extra-forbid. 권한·tenant·assignee 검사와 감사 증빙을 약화하지 않는다.
- 각 작업에서 RED→GREEN→관련 회귀→diff 검토를 수행한다. 이미 유효한 회귀를 이유 없이 반복하지 않는다.

## Review Focus

1. 응답 유실 후 같은 operation 재전송: 중복 실행 대신 최초 receipt 반환. 다른 payload면 충돌. 작업 2.
2. A 평가 중 B 선택: A 결과의 소속을 바꾸지 않고 선택이 덮이지 않음. 작업 2·3·5.
3. 기존 record에 현재와 다른 공고 snapshot이 섞인 경우: 역사 자료를 새 독립 평가로 복원하지 않음. 작업 1·2.
4. source 확인과 다른 store 문서 쓰기 사이의 경합: 원자성을 주장하지 않고 pinned revision으로 stale 표시. 작업 5.
5. N/A 또는 미지 상태가 export 변환기에서 ready가 되는 경우: 명시적 형식 처리 또는 거부. 작업 7·8.

## 작업 1. v2 데이터 계약과 순수 상태 검증

**Files:** create `app/storage/procurement_project_state.py`, `tests/test_procurement_multi_opportunity.py`.
기존 `ProcurementDecisionRecord`와 snapshot ownership 규칙을 재사용한다.

**Interfaces:** `ProcurementProjectState`는 schema_version, tenant_id, project_id,
active_decision_id, selection_revision, entries, receipts를 가진다.
entry는 record, decision_revision, 기존 mutation_ids를 가진다.
`decode_project(raw, *, tenant_id, project_id)`는 v1/v2 dict를 읽으며 I/O하지 않는다.

- [x] 테스트 작성: legacy record 내용/ID/원본 dictionary 불변, private mutation 이력 보존.
- [x] duplicate decision/source identity, 다른 tenant/project, invalid active ID, bool/음수 revision, unknown field 거부.
- [x] 최소 모델·decoder 구현 후 round-trip 및 입력 비변경 검증.
- [x] 기존 store integrity 테스트와 함께 검사.

```python
before = copy.deepcopy(legacy)
project = decode_project(legacy, tenant_id="alpha", project_id="project-a")
assert project.entries[0].record.decision_id == legacy["decision_id"]
assert legacy == before
assert project.selection_revision == 0
```

## 작업 2. 명시적으로 주입된 backend에서 CAS 저장·선택

**Files:** create `app/storage/procurement_project_store.py`; expand 작업 1 테스트.
기존 앱 factory에 연결하지 않는다. Store 생성에는 명시적 backend가 필요하다.

**Interfaces:**
- `get(project_id, *, tenant_id) -> ProcurementProjectState | None`
- `import_opportunity(payload: ProcurementDecisionUpsert, *, expected_selection_revision: int, expected_decision_revision: int, operation_id: str) -> ProcurementMutationReceipt`
- `select(project_id, *, tenant_id, decision_id, expected_selection_revision, operation_id) -> ProcurementMutationReceipt`
- `save_evaluation(record: ProcurementDecisionRecord, *, expected_decision_revision, operation_id) -> ProcurementMutationReceipt`

신규 프로젝트·신규 source의 expected revision은 0이다. import는 active 선택을
같은 CAS에서 바꾸고 해당 decision revision을 올린다. 같은 source import는 이전
snapshot/notes를 보존하며 새 snapshot을 추가하고 파생 판단을 비운다.
save_evaluation은 identity/source/snapshot 소속을 바꾸지 않고 선택 revision은 건드리지 않는다.
반환 receipt는 operation_id/request_sha256/decision_id/decision_revision/
selection_revision이다. 후속 작업이 있어도 같은 요청은 최초 receipt를 반환한다.

- [x] A/B 추가·갱신·선택, 동일 source exact match, legacy 무쓰기 GET/첫 write 전환 테스트.
- [x] 동시 CAS 충돌은 자동 rebase/retry 없이 conflict. 잘못된 operation UUID나 revision은 쓰기 전에 거부.
- [x] 같은 operation/payload 재전송은 receipt 반환, 재사용된 operation의 다른 payload는 conflict.
- [x] local/fake-S3 응답 유실 후 exact receipt reconciliation 및 read 실패 보존.
- [x] snapshot 경로·내용 메타데이터 변조, duplicate project, 다른 tenant 변경 금지.
- [x] caller가 backend의 실제 v2 state를 다시 읽어 결과를 확인.

```python
first = store.import_opportunity(a, expected_selection_revision=0,
    expected_decision_revision=0, operation_id=op_a)
second = store.import_opportunity(b, expected_selection_revision=1,
    expected_decision_revision=0, operation_id=op_b)
assert first.decision_id != second.decision_id
assert len(store.get("project-a", tenant_id="alpha").entries) == 2
assert store.import_opportunity(a, expected_selection_revision=0,
    expected_decision_revision=0, operation_id=op_a) == first
```

Run: `pytest -q tests/test_procurement_multi_opportunity.py tests/test_procurement_store_integrity.py tests/test_procurement_store.py`.
완료 조건: 위 저장 계약의 실제 local/fake-S3 증거. 이 단계는 API/사용자 데이터 전환 권한이 아니다.

## 작업 3. scoped 평가 서비스와 API

**Files:** modify `app/schemas/procurement.py`,
`app/services/procurement_decision/service_core_mixin.py`,
`app/routers/projects/procurement.py`; create `tests/test_procurement_multi_opportunity_api.py`.
추가 책임 분리: `app/services/procurement_opportunity_service.py`와
`app/routers/projects/procurement_opportunities.py`에 scoped 동작을 둔다.
`procurement_project_store.py`는 계산 전 replay와 단일 CAS를 담당하고,
`app/middleware/audit.py`, `observability.py`는 공고·receipt 식별자를 기록한다.

- [x] 설계 §4의 목록/상세/선택/evaluate/recommend route를 격리 테스트 앱에서 구현한다.
- [x] 서비스의 계산과 저장을 분리하여 v2에서는 한 번 읽은 record를 계산하고 expected revision으로 저장한다. 기존 v1 entrypoint는 유지한다.
- [x] single-opportunity GET/evaluate/recommend 호환, multi에서 ID 없는 evaluate/recommend는 409, 잘못된 UUID/revision은 422, 없는/외부 tenant ID는 기존 not-found 정책.
- [x] 목록 기본 20/최대 100, summary only, 선택된 항목이 페이지 밖이어도 active ID 유지.
- [x] operation receipt replay와 실패 시 원본 보존, 세션 권한·tenant·감사 로그 검증.

새 mutation 응답은 `{project_id, receipt}`다. receipt는 요청 ID/action/decision/revision에
결속되어 계산 전에 replay를 판별한다. 이후 detail GET은 현재 상태이며 과거 receipt의
결과 본문이라고 표시하지 않는다. 추천은 중간 평가를 따로 저장하지 않고 단일 CAS로 저장한다.
기존 v1 recommend entrypoint의 저장 흐름은 유지한다.

경합 시 선택만 바뀌어도 aggregate CAS는 409로 멈춘다. A 결과를 B에 붙이거나
선택을 A로 되돌리지 않고 자동 재시도하지 않는다. UI의 최신 상태 조회는 작업 6이다.
기존 G2B import/override와 generation 등 나머지 consumer의 v2 전환은 이 단계에서
활성화하지 않는다. 작업 4-6에서 해당 경로의 ID/revision·호환성 검사를 완료해야 한다.

```python
assert client.post(f"/projects/{pid}/procurement/evaluate", headers=owner).status_code == 409
assert client.post(f"/projects/{pid}/procurement/opportunities/{a_id}/evaluate",
    json={"expected_decision_revision": a_rev, "operation_id": operation},
    headers=owner).status_code == 200
```

Run: `pytest -q tests/test_procurement_multi_opportunity_api.py tests/test_project_management.py tests/test_procurement_decision_service.py tests/test_tenant.py`.
v2 activation은 작업 6의 통합 완료 전까지 기본 실행 경로에서 비활성으로 유지한다.

## 작업 4. Council·검토 패키지의 공고 binding

### 상세 실행 범위

1. `ProcurementSourceBinding` strict 계약: tenant/project/decision ID, decision revision,
   record canonical SHA-256, source timestamp, snapshot ID별 exact-byte SHA/size.
   캡처는 주입된 backend의 원문을 읽고 누락/잘못된 소속이면 중단한다.
   원문은 ZIP에 새로 복제하지 않는다. 휴대용 검증은 해시 선언과 패키지의
   결속을 확인하며 원문을 다시 조회하지 않은 상태를 원문 검증 완료로 표현하지 않는다.
2. Council 신규 bound session은 decision ID가 포함된 키를 사용한다. legacy 키는
   보존하고 명시된 source decision ID가 일치할 때만 read-only fallback한다.
   신규 bound session은 revision/record hash/snapshot hash로 freshness를 판정한다.
   동일 timestamp로 내용이 바뀌거나 tenant/project/ID가 다르면 current가 될 수 없다.
3. 검토 packet v2에 source binding을 추가하고 v1 생성·검증 경로는 그대로 유지한다.
   package ID/source timestamp와 교차 검증한다. receipt와 reviewed-package는
   실제 내장 packet 버전에 결속하고 expected tenant/project와도 확인한다.
   저장 전·읽을 때 scope mismatch를 차단하며 기존 ZIP/receipt bytes를 보존한다.
4. 검토 목록의 optional decision filter는 기존 assignee 권한 검사 이후 적용한다.
   미배정 기록의 artifact를 filter 때문에 읽거나 권한을 넓히지 않는다.
   v1에는 decision binding을 추정하지 않는다. unknown 기록을 v2 current로 표시하지 않는다.
5. local/fake-S3에서 A/B 세션 분리, A-only stale, 원문 변조/누락, tampered manifest,
   receipt/완료 package round-trip, 기존 v1 bytes 불변, assignee 필터를 검증한다.
   기본 factory 활성화·브라우저 연결·실사용 데이터 전환은 하지 않는다.

Ruling: 기존 store key와 packet format을 일괄 변환하지 않고 opt-in binding을
추가한다. 기존 consumer 검증과 증빙 보존을 유지하기 위한 선택이며 실제 앱에서
공고별 Council 실행/패킷 생성·완료를 연결하는 일은 활성화 전 별도 통합 검사 대상이다.

**Files:** modify `app/storage/decision_council_store.py`,
`app/services/decision_council/binding.py`, `app/services/decision_council/service.py`,
`app/routers/projects/procurement_reviews.py`, `app/storage/procurement_review_store.py`,
`app/services/procurement_decision_package/`; create `tests/test_procurement_opportunity_bindings.py`.

- [x] Council key에 decision ID 추가, 기존 source_decision_id로만 legacy 연결.
- [x] 패키지 새 버전에 decision ID/revision/snapshot SHA를 명시하고 구버전 verifier를 유지.
- [x] assigned reviewer의 공고 필터는 권한 확대가 아님을 검증.
- [x] A 변경은 A만 stale, B evidence는 그대로. 과거 ZIP/receipt hash 불변.
- [x] 활성화 통합: 공고별 Council 실행/packet 생성과 pending v2 완료의 원문 resolve를
  API에 연결하고 ID/revision/raw hash 경합·완료 ZIP replay를 검사한다. 작업 5·6과
  함께 완료하기 전에는 다중 공고 end-to-end 완료로 표시하지 않는다.

```python
assert binding(a_session, updated_a)["status"] == "stale"
assert binding(b_session, unchanged_b)["status"] == "current"
assert old_packet_bytes == review_store.read_packet(old_review, **scope)
```

Run: `pytest -q tests/test_procurement_opportunity_bindings.py tests/test_decision_council.py tests/test_procurement_review_store.py tests/test_procurement_review_authorization.py tests/test_procurement_decision_package_builder.py`.

## 작업 5. 생성·편집본·share·evidence map 출처

**Files:** modify `app/schemas/generate.py`, `app/services/generation/service_context_injection_mixin.py`,
`app/services/generation/service_core_mixin.py`, `app/routers/generate/export.py`,
`app/storage/project_store.py`, `app/services/edited_project_copy_service.py`;
공고 출처를 읽는 share/evidence-map consumer는 rg로 실제 파일을 재확인하고 같은 작업에 포함한다.
Create `tests/test_procurement_generation_binding.py`.

### 상세 실행과 완료 조건

1. strict 생성 입력 `procurement_decision_id`/`expected_procurement_decision_revision`은
   함께 제공하고 project가 필요하다. 명시 주입된 resolver에서만 v2를 허용한다.
   다중 공고에서 ID 생략, foreign ID, 오래된 revision은 provider 호출 전에 거부한다.
2. 한 번 캡처한 record와 검증한 snapshot bytes로 prompt·Council·완료 review·evidence
   refs를 구성한다. 현재 선택이나 project-only store를 다시 읽어 섞지 않는다.
   NO_GO override는 해당 record의 notes만 확인한다. cache identity에 전체 binding을 넣는다.
3. provider/cache 결과를 저장하기 전에 같은 ID의 revision/record/raw hash를 다시 확인한다.
   선택만의 변경은 허용하지만 원문 변경은 409이며 자동 재호출은 없다. 저장 후 경합은
   원래 binding을 보존한 채 조회 때 stale로 표시한다. 다중 파일 원자성은 주장하지 않는다.
4. 생성 응답과 각 doc, ProjectDocument, durable export source에 같은
   `source_procurement_binding`을 보존한다. 편집본은 출처만 상속하고 검토 승인 상태는
   상속하지 않는다. 새 ZIP manifest 버전은 binding을 결속하고 v1 bytes/verifier는 유지한다.
5. share/evidence-map은 저장된 document binding으로만 표시하고 다른 선택으로 재귀속하지
   않는다. 출처가 없거나 resolver가 비활성이면 unknown이다. public 응답의 기존 노출 범위를
   넓히지 않고 내부 tenant/원문 메타데이터 노출을 점검한다.
6. RED→GREEN 뒤 local/fake-S3에서 A/B 독립, 선택/원문 경합, cache 분리, 변조/다른 tenant,
   legacy, 편집 이력·ZIP·share를 검사한다. 사용자 화면 연결·실데이터 전환은 작업 6에 남긴다.

Ruling: 이번 작업은 기존 source-binding 객체를 전달하며 ID/revision의 별도 중복 저장을
최소화한다. 기본 factory의 v2 비활성은 유지한다. 부모 task는 생성 파이프라인과 route,
Sol/high worker는 충돌하지 않는 문서 저장·편집·패킷/조회 계층을 맡고 통합 후 함께 검증한다.

- [x] 생성 입력에서 decision/revision을 한 번 resolve하고 cache key·출력 metadata로 전달.
- [x] 생성 중 선택 변화는 소속 변경 금지, source 변경 발견 시 409, 저장 후 경합은 stale.
- [x] 원본·편집본·다운로드·share에서 같은 binding을 유지. project-selected 상태로 출처를 덮지 않음.
- [x] legacy 출처가 불명확하면 unknown이지 current가 아님. override 사유 공고 간 전이 금지.

```python
assert saved_doc.source_procurement_binding["decision_id"] == a_id
assert saved_doc.source_procurement_binding["decision_revision"] == a_rev
assert current_selection == b_id
assert describe_freshness(saved_doc, updated_a) == "stale"
```

Run: `pytest -q tests/test_procurement_generation_binding.py tests/test_procurement_bundle_handoff.py tests/test_edited_project_copy_api.py tests/test_generate.py`.

## 작업 6. 공고 선택 UI와 실제 로컬 lifecycle

**Files:** modify `app/static/index.html`, `app/static/sw.js`, `app/main.py`,
`app/routers/projects/procurement.py`, `procurement_reviews.py`, `decision_evidence.py`,
`app/schemas/procurement.py`, `app/storage/procurement_project_store.py`와 필요한
Council 검증 경계; create `tests/test_procurement_scoped_lifecycle.py`,
`tests/e2e/test_procurement_multi_opportunity.py`.

### 상세 실행 범위 (2026-09-22)

1. 기존 factory 기본값을 유지하고 Python keyword opt-in으로만 테스트 인스턴스에
   aggregate/service/resolver/router를 연결한다. 환경변수나 기본 runner의 자동 전환은 없다.
2. G2B import는 expected selection/decision revisions와 operation ID를 요구한다.
   replay는 재수집·재분석하지 않으며 신규 요청은 revision preflight 뒤 실행한다.
   override notes는 선택 상태가 아닌 명시한 decision의 CAS로 저장한다.
3. Council GET/run과 review packet은 기존 URL의 decision ID/revision query pair로
   exact source를 resolve한다. pending v2 완료는 packet binding을 resolve하며 현재
   선택을 쓰지 않는다. 완료된 package의 replay는 저장 bytes를 반환한다.
4. UI는 목록 전체를 읽고 선택 revision이 도중 바뀌면 중단한다. selection POST 이후에는
   receipt를 최신 상태로 간주하지 않고 다시 조회한다. 공고 선택이 평가·생성을 호출하지 않는다.
5. 화면 request identity는 auth/tenant/user/project/load sequence/decision/selection을
   포함한다. 생성에는 decision/revision을 고정하고 늦은 응답은 결과 화면에 채택하지 않는다.
   프로젝트 전체 문서는 원래 공고를 표시하고, 선택 공고의 역할/검토 안내에는 다른 공고
   문서를 넣지 않는다. Guided handoff의 서버/브라우저 계산도 같은 범위를 사용한다.
6. 프로젝트 조회는 service worker의 offline cache fallback을 사용하지 않는다.
   원문·선택·검토의 과거 응답을 최신으로 표시하지 않기 위한 관련 수정이다.
7. 실제 loopback API와 collector stub, mock provider로 desktop/mobile lifecycle을
   실행하고, selection/auth/generation/evaluation 경합을 별도 browser tests로 확인한다.
   DOCX ZIP 구조·binding 검증은 native Office 시각 검수나 실제 수집 품질 검증이 아니다.

Ruling: 이미 승인된 계획을 현재 task에서 실행한다. Sol/high worker는 backend,
부모는 UI/Guided integration/browser verification을 맡는다. 추가 ledger, worktree,
기본 앱 활성화, 실사용 DATA_DIR 전환, commit/push는 하지 않는다.

- [x] 선택 메뉴는 조회/선택만 수행. 자동 평가/자동 provider 호출 금지.
- [x] auth/project/decision/selection revision/request sequence로 늦은 응답 차단.
- [x] 다른 공고를 고르면 이전 자료는 해당 공고의 자료로 표시하지 않는다.
- [x] 실제 local API로 A/B import(collector만 stub), 평가, 검토, 생성, reload, export를 desktop/mobile에서 수행.
- [x] 선택·생성 경합 및 잘못된 tenant/assignee를 확인하고 캡처를 시각 검수.
- [x] 모든 consumer 회귀 통과 후 isolated local/fake-S3 환경에만 v2 write 연결.
- [x] 기존 G2B import의 expected revisions/operation receipt, notes override의 공고 소속,
  project-only generation의 multi-opportunity 409 호환성을 확인한 뒤 활성화한다.

```python
page.get_by_role("combobox", name="공고").select_option(b_id)
expect(page.locator("[data-active-decision]")).to_have_attribute("data-active-decision", b_id)
assert download_binding["decision_id"] == b_id
```

Run: `pytest -q -p pytest_playwright.pytest_playwright tests/e2e/test_procurement_multi_opportunity.py --browser chromium`.
작업 1-6 완료가 다중 공고 기능의 최소 완료 기준이다.

## 작업 7. 요구사항·적용 여부 이력

**Files:** create `app/schemas/procurement_applicability.py`,
`app/services/procurement_applicability_service.py`,
`app/routers/projects/procurement_applicability.py`,
`tests/test_procurement_requirement_applicability.py`; extend v2 entry state.

### 실행 범위 (2026-09-22)

- v2 entry에 요구사항과 append-only 주석 이력을 저장하고 같은 aggregate CAS/receipt를
  재사용한다. legacy decision record 및 기존 체크리스트 점수·추천은 변경하지 않는다.
- raw JSON exact-byte SHA와 `announcement.raw_text`의 Unicode code-point 인용을
  결속한다. 인용한 snapshot이 남아 있어도 source set이 바뀌면 기존 판단은 unknown/stale다.
- 세션 admin만 작성하며 actor/time은 서버에서 기록한다. tenant·project·decision을
  확인하고 잘못된 revision, operation 재사용, source drift는 자동 재시도 없이 거부한다.
- Ruling: 이력 조회는 기존 API-key 공고 상세에 추가하지 않고 session-protected
  `GET /opportunities/{decision_id}/requirements`로 분리한다. 기존 상세의 넓은 읽기
  권한으로 actor 이력이 노출되는 것을 피한다. admin 또는 해당 공고 배정 member만 읽으며
  member에는 내부 actor ID를 제외한다. API 소비자는 이 전용 조회를 함께 호출해야 한다.
- Astra/medium은 계약 검토, Sol/high는 schema/service/store와 단위 검증, 부모는
  router/factory/권한 API 검증과 통합을 맡는다. 현재 task의 모델 전환을 주장하지 않는다.
  기존 계획을 실행 기록으로 사용하며 별도 ledger/worktree나 자동 commit은 만들지 않는다.
- 작업 7은 backend 계약 완성 범위다. 작업 8의 새 package verifier/renderer와
  실제 UI 통합이 끝나기 전에는 N/A 편집 UI를 노출하지 않는다. 기본 factory 비활성,
  실사용 DATA_DIR 보존, 외부 호출·설치·배포·Git 미실행 경계를 유지한다.

- [x] requirement ID, category, raw-text quote code-point range, snapshot exact-byte SHA 계약.
- [x] 세션 admin이 unknown 요구사항을 작성하고 applies/not_applicable/unknown 주석 이력을 추가.
- [x] actor/time은 서버가 기록. blank rationale, 잘못된 quote/hash, 다른 scope, fail/unknown 관련 filter면 거부.
- [x] 기존 10개 범주와 점수/추천/operational flags는 그대로. unknown으로 되돌리는 행위도 삭제가 아니라 이력.
- [x] source 변경은 annotation stale, 요구사항 적용 여부는 unknown, dependent evidence는 stale.
- [x] expected revision과 operation receipt를 작업 2 계약에 결합.

### 검증 결과 (2026-09-22)

- 완료 직전 snapshot의 31-file 광범위 회귀는 **1005 passed**, 425.36s.
  정확한 파일 목록은 procurement STATUS에 기록했다. 마지막 core 보완과 원문 변경
  HTTP 검사까지 포함한 현재 영향 범위의 기준은 아래 139개 결과다.
- 최종 core/HTTP/권한/aggregate/평가 회귀: **139 passed**, 71.33s.
  `pytest -q tests/test_procurement_requirement_applicability.py
  tests/test_procurement_requirement_applicability_api.py
  tests/test_procurement_multi_opportunity.py tests/test_procurement_review_authorization.py
  tests/test_procurement_eval_regression.py --tb=short --show-capture=no`.
- dotenv 차단, 임시 DATA_DIR, mock, local/fake-S3와 아래 명시된 clean Python 환경을 사용했다.
  기존 Starlette/httpx deprecation warning 1건은 비차단이다.
- 권한 API는 미연결 404의 RED부터 검증했다. 부모 통합 검토에서 source 재읽기 경쟁,
  같은 source set 안의 인용 변경과 주석 operation 추적을 보완했다. 최종 gate는
  같은 파일 bytes 변경의 stale 표시, 원문 조회 장애의 503, 원래 receipt replay도 검증한다.
- Astra/medium 계약 검토와 Sol/high core 구현을 통합했다. 별도 Sol/high read-only
  integration review는 route/factory/권한/감사에서 actionable finding 없음으로 종료했다.
  해당 reviewer는 core 구현 판단과 테스트 재실행을 하지 않았으며 부모가 실제 core와
  최종 검증 결과를 확인했다. 전체 dirty branch 리뷰를 의미하지 않는다.
- Ruff E/F/W(E501 제외), 변경 Python 11개 파일의 in-memory compile 통과.
  UI/export는 작업 8로 남고 기본 앱 활성화·실사용 데이터 변경·외부 실행·stage/commit/push는 하지 않았다.

```python
with pytest.raises(ApplicabilityConflict):
    service.annotate(blocked_requirement, applicability="not_applicable", **admin_command)
assert decision.soft_fit_score == before.soft_fit_score
assert decision.recommendation == before.recommendation
```

Run: `pytest -q tests/test_procurement_requirement_applicability.py tests/test_procurement_review_authorization.py tests/test_procurement_multi_opportunity.py`.

## 작업 8. N/A 표시·내보내기·통합

실행 결정 (2026-09-22): 별도 export를 만들지 않고 기존 검토 패키지에
versioned applicability projection을 통합한다. opt-in 공고의 새 export는 v3이며
기존 v1/v2 builder 기본값과 이미 발급한 패키지의 완료 검증은 원래 버전을 유지한다.
원문·요구사항·revision을 같은 entry에서 캡처하고 저장 직전 다시 확인한다.
portable projection에서는 내부 actor ID를 제거하되 원문 인용, 이유, 시각과 이력을 보존한다.
기존 JSON/Markdown/HTML에 반영하고 v3에만 요구사항 DOCX를 추가한다.
원문 선택 API는 관리자 전용이며, 기존 요구사항이 있는 공고를 미배정 검토자가
스스로 export하여 조회 권한을 얻는 경로는 차단한다. 기본 factory 활성화는 이 범위가 아니다.

**Files:** modify `app/services/procurement_decision_package/`, 관련 procurement renderer,
`app/static/index.html`; create `tests/e2e/test_procurement_requirement_applicability.py`.

- [x] 미지 상태는 ready fallback을 제거하고 오류로 처리. 기존 package enum을 몰래 확장하지 않음.
- [x] 새 버전의 하위 requirement/applicability 표현을 HTML/Markdown/DOCX와 verifier가 보존.
- [x] 세부 unknown/stale/N/A 건수를 부모 범주 점수와 별도로 표시.
- [x] 관리자 작성 → 배정 검토자 읽기 → export → 원문 변경 → stale의 실제 local lifecycle 검증.
- [x] 승인된 local 수용 기준을 대조하고 STATUS/설계에서 local 완료와 외부 미검증을 구분.

완료 기록 (2026-09-22): 통합 gate 436 passed / 177.02s, 마지막 DOCX 제목 테두리
제거 후 affected gate 85 passed / 60.77s, Chromium desktop/mobile 및 기존 공고별
생성·검토 lifecycle 6 passed / 76.46s (8 deselected). 명령은 procurement STATUS의
동일 날짜 Step 8 기록에 있다. UI microtask context 경쟁, 403/404 후 빈 요구사항
self-prepare 복구, 완료 직전 source 장애 503 보존에 대한 리뷰 지적을 수정·회귀 검증했다.
HTML 시각 검수와 bundled LibreOffice의 DOCX 2페이지 렌더 검수를 수행했다.
Native Word 편집/저장 및 실제 앱·데이터 활성화는 이 완료 범위가 아니다.
독립 계약 검토 Astra/medium, 패키지 구현 Astra/high, UI 구현·통합 리뷰 Sol/high를
사용했으며 주관 작업에서 실제 코드와 최종 검증을 확인했다. 모델 교체용 별도 task나
retired Orca routing은 만들지 않았다.

```python
assert exported_requirement["applicability"] == "not_applicable"
assert exported_category["status"] != "ready" or category_was_ready_before_annotation
assert verified_packet["operational_approval"] is False
```

Run: `pytest -q tests/test_procurement_requirement_applicability.py tests/test_procurement_decision_package_builder.py tests/test_export_procurement_decision_package.py`.
Run separately: `pytest -q -p pytest_playwright.pytest_playwright tests/e2e/test_procurement_requirement_applicability.py --browser chromium`.

## 작업 9. 활성화 전 오프라인 상태 검사 (2026-09-22)

실사용 데이터 전환 승인과 분리된 준비 작업이다. 기존 storage decoder를
재사용하는 `scripts/procurement_transition_preflight.py`를 추가했다.

- [x] 명시한 단일 파일/tenant만 읽고 SHA-256과 v1/v2 계약을 검사한다.
- [x] 다른 tenant, 중복 ID, 손상된 이력·revision·snapshot 소속을 차단한다.
- [x] 파일 읽기 중 변경, leaf symlink, 특수 파일, 16 MiB 초과 입력을 차단한다.
- [x] local/fake-S3 fixture와 독립 CLI에서 무수정·내용 비노출을 검증한다.
- [x] 기존 저장·feature gate를 포함한 5개 파일 회귀: 176 passed, 3.23s.
- [ ] 승인된 대상 데이터의 일관된 복사본 확보와 원문/문서/검토 증빙 대조.
- [ ] 해당 복사본에서 첫 write 전환·재시작·과거 packet 재생 검증 후
  대상/backup/복구 범위를 확정한 실제 앱 활성화. 이번 작업에서는 수행하지 않는다.

`pass`는 캡처한 상태 파일의 구조 검증일 뿐이며 항상
`activation_allowed=false`, `source_bytes_verified=false`다. v2 row가 있으면
`legacy_reader_compatible=false`; 기능 플래그만 끄는 방식은 rollback이 아니다.
정확한 명령과 제한은 설계의 오프라인 검사 항목 및 procurement STATUS에 둔다.

## 작업 10. 전환·앱 재생성·기존 검토 호환성 (2026-09-22)

실사용 복사본 확보 전, 새 fixture의 동일 저장 위치에서 기본 앱 → opt-in 앱 →
새 opt-in 앱 인스턴스를 순서대로 열어 검증한다. local/fake-S3 모두 procurement
state, snapshot, review store가 같은 backend를 사용하며 이전 앱은 먼저 닫는다.
OS 프로세스 재시작이나 실제 운영 backup/restore 시험으로 확대하지 않는다.

- [x] 시작/GET 무전환, 첫 명시적 선택의 v2 전환, 다른 프로젝트 row 보존 확인.
- [x] 재생성 후 operation replay가 최초 receipt를 반환하고 상태를 다시 쓰지 않음 확인.
- [x] 과거 snapshot/packet/완료 ZIP/receipt bytes 보존 및 기존 담당자 권한 유지.
- [x] mixed v1/v2 tenant에서 미완료 v1 검토가 잘못 막히는 결함 RED 재현 및 수정.
- [x] 검증된 v1 package ID와 같은 공고를 찾아 전체 packet SHA를 다시 비교한다.
  활성 공고를 대신 쓰거나 과거 packet을 v2/v3로 업그레이드하지 않는다.
- [x] 완료 저장 직전 legacy record 재검사, 변경 409/조회 불가 503 및 무쓰기 확인.
- [x] v3 pending packet의 재생성 후 완료와 변경 원문 차단 확인.

초기 fixture의 fake-S3 list API 누락은 기존 review-store fake 재사용으로 수정했다.
제품 RED는 local/fake-S3 모두 다른 프로젝트의 v2 row 때문에 legacy 완료가
409로 차단된 2건이다. 수정 후 focused gate 14 passed, 36.51s.
별도 읽기 전용 리뷰에서 추가 구현 결함은 없었고, 원본 삭제/ID 교체의 negative
coverage 의견을 반영했다. 인접 회귀 227 passed, 222.73s 이후 최종 affected gate는
22 passed, 66.99s다. 정확한 파일 목록과 환경은 procurement STATUS에 기록했다.
승인된 실사용 데이터 복사본 검사와 실제 활성화는 여전히 미수행이다.

## 작업 11. 별도 프로세스·오프라인 fixture 복구 (2026-09-22)

`tests/test_procurement_transition_process.py`에서 local 임시 fixture만 사용한다.
외부 네트워크 연결과 dotenv를 차단하고, 자식 프로세스 환경을 명시적으로 구성한다.
fake-S3 재개는 작업 10의 검증 범위이며 이번 파일은 local filesystem 대상이다.

- [x] 별도 Python 프로세스에서 v1 상태와 검토 완료 ZIP을 생성하고 종료한다.
- [x] 모든 쓰기가 끝난 fixture 전체를 백업하고 파일별 SHA inventory를 비교한다.
- [x] 백업의 복사본에서 다른 프로세스로 첫 v2 write와 v3 검토 완료를 수행한다.
- [x] 세 번째 프로세스에서 선택·operation receipt·v1/v3 ZIP의 동일 bytes를 확인한다.
- [x] 백업을 새 경로에 복구하고 네 번째 프로세스의 기본 앱에서 v1 상태·ZIP을 확인한다.
- [x] fixture 원본/백업 전체와 전환된 복사본이 복구 과정에서 바뀌지 않음을 확인한다.

최초 focused 실행은 1 passed, 14.43s. 이 한 테스트가 네 자식 프로세스를 실행한다.
제품 결함은 재현되지 않았으며 이번 단계에는 제품 코드 변경이 없다.
최종 관련 gate는 76 passed, 71.97s다. 명령과 제한은 procurement STATUS에 기록했다.
이 결과는 합성 데이터의
정상 종료 후 오프라인 복구 검증이며, 실사용 backup/restore·동시 작성자·강제 종료·
서비스 관리자/uvicorn 재시작·기본 앱 활성화까지 검증했다는 뜻이 아니다.

## 검증 실행 환경

매번 dotenv 로딩을 app import 전에 비활성화하고 임시 DATA_DIR, mock provider,
local 또는 메모리 fake-S3를 사용한다. 실제 credential 파일을 읽지 않는다.
브라우저 E2E와 standalone sync Playwright는 별도 process로 실행한다.
새 테스트 명령은 해당 파일이 작성된 뒤 실행하며 예정 명령을 통과 증거로 쓰지 않는다.
각 변경 묶음의 Ruff E/F/W(기존 E501 제외)와 git diff --check를 수행한다.

## 실행 기록

- 설계와 로컬/fake-S3 범위 승인: 2026-09-21 현재 사용자 메시지.
- 작업 3 checkpoint: 작업 1·2 저장 계층과 작업 3 scoped API·평가의 격리 구현 완료.
  당시 작업 4-8 및 실제 앱 활성화는 미완료였다. 작업 4 진행은 아래 별도 기록한다.
- 최초 RED는 미구현 store import 실패였다. 이후 중복 snapshot과 미지원 schema
  입력 거부 테스트에서 local/fake-S3 합계 4건 실패를 재현하고 수정했다.
- 저장 관련 명령(작업 2)의 최종 결과: 123 passed, 1 warning, 2.56s.
  그중 신규 파일은 62개 실행 사례이며 나머지는 기존 store 회귀다.
- 두 store의 동시 conditional write와 동일 요청 경합, 다른 프로젝트가 후속
  저장한 뒤의 응답 유실, 재조회 실패를 검증했다. 충돌 시 자동 재시도는 없다.
- snapshot 검증은 ID·소속 경로·메타데이터를 대상으로 한다. raw snapshot
  bytes의 SHA 확인과 downstream 문서 binding은 작업 4·5·7의 잔여 범위다.
- 모든 검증은 임시 데이터 또는 메모리 fake-S3다. 기존 사용자 DATA_DIR에는
  v2 데이터를 쓰지 않았고 app runtime wiring도 바꾸지 않았다.
- 기존 프로젝트/평가/Council/검토/package/gate를 포함한 인접 회귀:
  421 passed, 1 existing Starlette/httpx warning, 71.58s. 정확한 파일 목록과
  환경은 procurement STATUS의 동일 날짜 storage foundation 항목에 기록했다.
- 대상 파일 Ruff E/F/W(E501 제외) 및 git diff --check 통과.
- 작업 3 신규 API 검증: 62 passed, 1 existing Starlette/httpx warning, 8.33s.
  최초에는 새 router가 없었고, 추가 RED에서 감사 로그 누락 2건과 legacy GET의
  v2 읽기 실패 2건을 재현해 수정했다. 정상·충돌 receipt, viewer 쓰기 거부,
  member 평가, JWT tenant 위조, A 원문 기반 판단, 선택/원문 경합,
  identity 변조 거부, 저장 응답 유실과 재계산 없는 replay를 검사했다.
- repo-intake/procurement-eval/TDD/verify-gate를 적용했고 신규 API의 세션·tenant
  권한 경계 확인에 security-best-practices를 추가했다. 브라우저나 외부 Agent는
  사용하지 않았다.
- 작업 3 최종 인접 gate: 754 passed, 1 existing Starlette/httpx warning,
  115.66s. STATUS의 scoped opportunity API 항목에 전체 명령과 환경을 기록했다.
  9개 변경 Python 파일 syntax, 대상 Ruff E/F/W(E501 제외), git diff --check 통과.
  전체 repository suite와 browser/UAT는 수행하지 않았다.
- 작업 3 이후의 다음 작업은 작업 4의 Council·검토 패키지 공고 binding이었다. 기존 import/override와
  생성 경로까지 준비되기 전에 기본 앱에서 v2를 활성화하지 않는다.
- 작업 3까지는 별도 Agent 도구 실행이나 branch 전체 독립 리뷰를 수행하지 않았다.

### 작업 4 내부 binding checkpoint

- 위 상세 계획의 네 내부 구현 항목을 local/fake-S3에서 검증했다. 기본 앱에
  공고별 Council 실행/packet 생성/신규 완료를 연결한 것은 아니다. API 원문 resolve,
  생성·문서 binding, UI 및 N/A가 남아 있으므로 기능 전체 완료로 표시하지 않는다.
- `gpt-6-astra/medium` 보조 Agent가 읽기 전용 계약 검토를 수행했다. 저장 전
  scope/receipt 검증, actual packet version, 권한 검사 후 filter, portable proof
  구분을 반영했다. 구현과 검증은 현재 task에서 직접 수행했으며 task의 모델을
  전환했다고 주장하지 않는다.
- foreign-project packet prepare가 차단되지 않는 RED를 재현하고 저장 전
  필수 검증을 추가했다. 이후 local/fake-S3, reviewer attestation 유무, v1 ZIP
  불변, downgrade 거부, unassigned artifact 미조회, 역사 ZIP/receipt 보존을 검사했다.
- 리뷰 보완 후 최종 인접 gate: **863 passed**, 1 existing Starlette/httpx warning, 152.92s.
  전체 27개 테스트 파일과 실행 환경은 STATUS의 동일 날짜 opportunity-bound
  Council 항목에 기록했다. 전체 repository suite나 browser 검증은 아니다.
- 추가한 완료 실패 시 무쓰기/receipt downgrade와 pending-v2 활성화 차단 및
  아래 리뷰 보완 검증:
  `pytest -q tests/test_procurement_opportunity_bindings.py tests/test_procurement_review_authorization.py
  --tb=short --show-capture=no`: **53 passed**, 같은 warning, 28.27s.
- `gpt-5.6-sol/high` 별도 Agent가 위 코드 범위를 읽기 전용으로 리뷰했다.
  snapshot 없는 record도 bound 증빙으로 만들 수 있다는 P2 하나를 확인했고,
  local/fake-S3 캡처와 verifier에서 4건 RED를 재현했다. schema에 최소 1개
  fingerprint를 요구하도록 수정하고 위 gate로 검증했다. branch 전체 리뷰나
  수정 후 Agent 재리뷰까지 수행했다고 표시하지 않는다.
- 변경 Python 13개 syntax(in-memory compile), Ruff E/F/W(E501 제외),
  `git diff --check` 통과. 실제 DATA_DIR, provider/G2B/AWS/training, install,
  deploy, stage/commit/push에 대한 효과는 없다.
- 다음 구현은 작업 5의 생성·편집본·export/share 출처 결속이다. 작업 4의
  pending API 통합 조건을 함께 유지하고 작업 6의 모든 consumer 회귀 전까지
  v2 runtime write를 활성화하지 않는다.

### 작업 5 내부 생성·문서 binding checkpoint

- Astra/medium의 구조 검토를 바탕으로 위 상세 실행 기준을 보완했다. 부모 task는
  생성 파이프라인·입력·SSE·직접 binary provenance를 구현하고, Sol/high worker는
  분리된 문서 저장·편집본·ZIP·share·evidence map consumer를 구현했다.
- source가 다른 Council/review/override를 차단하고 A/B cache를 분리했다.
  source 변경 후 결과 저장 차단, 선택만 변경 시 A 유지, 저장 후 원문 변경의
  stale 표시를 local/fake-S3에서 검증했다. SSE의 source 오류 code와 bound
  project link 실패 시 complete 금지도 RED 이후 수정해 확인했다.
- v2 ZIP manifest의 null binding 거부, 편집본 출처만 상속, v1 bytes와 legacy
  source hash 보존, public share의 문서 snapshot·민감 metadata 비노출을 검사했다.
  binary 단독 파일의 portable source proof는 주장하지 않는다.
- 첫 통합 gate의 legacy 상태 표시 회귀 7건을 기존 assertion을 유지한 채 수정했다.
  이후 generation/downstream/project targeted gate는 178 passed였다.
- 별도 Sol/high 리뷰가 이미 stale인 원문의 재변경을 승인 fingerprint가 놓치는
  P1을 발견했다. 부모가 local/fake-S3 2건 RED를 재현하고 bound 경로에만 현재
  exact binding을 포함해 GREEN으로 수정했다. 수정 후 독립 재검토는 남은 scoped
  blocker 없음, 신규 source-binding 관련 54 passed였다. 전체 branch 리뷰는 아니다.
- 최종 관련 gate: **1353 passed**, 1 existing Starlette/httpx warning, 271.20s.
  STATUS의 decision-pinned generation 항목에 51개 파일의 정확한 pytest 인자와
  clean environment/temporary DATA_DIR/mock/local/fake-S3 조건을 기록했다.
  Python 26개 syntax, 대상 Ruff E/F/W(E501 제외), git diff --check 통과.
- repo-intake/procurement-eval/security/verify-gate 기준으로 tenant·승인·share를
  검사했다. native Office 시각 검수, browser/UAT, 전체 repository suite는 미실행이다.
  기존 dirty tree와 기본 factory 비활성을 보존했으며 실사용 데이터 전환, live
  provider/G2B/AWS/training, install/deploy/stage/commit/push는 실행하지 않았다.
- 다음은 작업 6의 scoped Council/review API 완료·UI lifecycle·격리 활성화다.
  저장 전 검증과 다른 store 쓰기 사이의 원자성을 주장하지 않는다. 작업 7-8의
  개별 요구사항 적용 여부/N/A도 아직 완료하지 않았으므로 전체 기능 완료가 아니다.

### 작업 6 격리 API·브라우저 통합 checkpoint (2026-09-22)

- 기존 계획을 보완해 부모가 UI/Guided integration, Sol/high worker가 scoped
  backend를 구현했다. 기본 factory는 false이며 임시 앱의 Python keyword로만
  opt-in했다. 사용자 실행 환경이나 기존 데이터는 전환하지 않았다.
- import receipt-only replay와 preflight, override CAS, Council exact source 재포착,
  pending v2 검토 완료의 저장 직전 재검증 및 tenant/assignee 거부를 검사했다.
- 실제 loopback API에서 A/B 수집(stub)·평가·Council·검토 ZIP 완료·mock 생성·
  선택·새로고침·DOCX ZIP source binding을 desktop/mobile로 확인했다. 늦은 생성,
  평가, 세션 변경 및 새로고침 중 다른 선택에 완료 알림을 표시하는 경합도 검사했다.
- 별도 Sol/high 리뷰의 P1 cross-decision member 접근과 P2 Evidence 문서 혼입,
  역할 유지 문제를 재현했다. 선택 공고 배정 재확인과 projection 문서 필터,
  공고별 역할 재계산으로 수정했다. 프로젝트 전체 문서와 원래 출처는 보존한다.
- 부모 추가 리뷰에서 post-refresh 완료 상태 혼입을 RED로 재현하고 다섯 handler에
  같은 scope/다음 load sequence 검사를 적용했다. 기존 Council browser fixture의
  새로고침 대역을 실제 load sequence 증가에 맞췄고 성공 assertion은 유지했다.
- 넓은 Python 관련 gate: **1495 passed**, 기존 Starlette/httpx warning 1건,
  303.33s. scoped lifecycle 별도 실행: **25 passed**, 16.45s. 이 결과는 아래
  마지막 세 보완 전이며, 보완 후 영향받는 13개 파일은 **153 passed**, 39.56s로 재검증했다.
- 재리뷰에서 다른 공고의 approval/workflow projection, 거부 시 필터 전 audit count,
  일반 페이지 이동 시 요청 미무효화를 확인했다. 각각 RED를 재현한 뒤 문서 ID로
  연결 기록 필터, 거부 전 감사 건수 갱신, 페이지 이탈 시 load ID 증가로 수정했다.
- 수정 후 별도 Sol/high 재리뷰는 해당 세 수정의 추가 P1/P2 없음으로 종료했다.
  리뷰어가 독립 실행한 focused regression은 **6 passed**, 10.47s이며 부모 gate와 구분한다.
- 최종 browser gate: **26 passed**, 100 deselected, 50.51s. 신규 파일은 10개 사례다.
  파일 목록/명령/환경은 procurement STATUS의 2026-09-22 항목에 기록했다.
  모바일 badge의 세로 줄바꿈을 수정했고 desktop/mobile 선택·문서 캡처를 검수했다.
- Python syntax, Ruff E/F/W(E501 제외), inline JS 3개와 service worker syntax,
  git diff --check 통과. procurement-eval/verify-gate에 더해 실제 브라우저 동선에
  Playwright, scoped authorization 경계에 security-best-practices를 적용했다.
- 작업 4의 API 통합과 작업 6은 격리 검증 범위에서 완료다. 전체 repository suite,
  native Office 시각 검수, 실사용 데이터 전환, live provider/G2B/AWS/training,
  install/deploy/stage/commit/push는 하지 않았다. 저장 간 원자성을 주장하지 않는다.
- 다음 범위는 작업 7-8의 개별 요구사항 applicability/N/A와 export 통합이다.

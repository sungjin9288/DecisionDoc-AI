# DecisionDoc AI Product Execution Plan

Updated: 2026-09-05

This document translates [DecisionDoc AI Product Direction](./product_direction.md) into an execution plan. It is an internal planning document and does not claim production readiness, customer adoption, measured business impact, or autonomous approval capability.

Current completion/readiness is owned only by the [Development Plan — Current
Completion/Readiness Snapshot](./development-plan.md#0-current-completionreadiness-snapshot).

## 0. Current Local Completion Goal

2026-09-14 priority update: the user approved the
Planned Feature Completion Design (`docs/superpowers/specs/2026-09-14-planned-feature-completion-design.md`).
Prioritize generation/edit/save/reopen/export, then style reuse, review, and
wider planned workflow reconciliation. The first explicit-empty-edit correction
and its focused verification are recorded in that design. The separately approved
edited-copy save slice (`docs/superpowers/specs/2026-09-14-edited-project-document-save-design.md`)
now has local save/reload/download and original-preservation verification.
The separately approved local style example import (`docs/superpowers/specs/2026-09-15-local-style-example-import-design.md`)
now has source-text import/reload and generation-prompt verification, without
provider analysis or model training.
This does not mark all product workflows complete. The checklist below preserves the
earlier review-completion scope; it is not a checklist of all product features.

이번 Goal은 **전체 설계를 현재 코드와 맞추고, 승인된 generated-document review
completion의 local/fake-S3 구현과 검증을 마무리하는 것**이다. 전체 제품의 운영
완료나 새 기능의 포괄 승인이 아니다. 설계 기준은
[Local-First Product Design](./architecture.md#local-first-product-design)이다.

기존 30/60/90-day 항목에는 이미 구현된 작업이 포함되어 있다. 아래의 의존 순서가
현재 실행 순서이며, 이후 numbered sections는 제품 방향과 과거 실행 근거로
보존한다. 새 phase 번호나 handoff wrapper를 추가하는 것은 제품 진척으로 세지 않는다.

### 현재 Goal 체크리스트

- [x] 실제 branch/dirty diff, 승인된 completion gate, source/storage/browser 계약 확인.
- [x] Verifier의 JSON 타입 혼동, 잘못된 decision, expected packet size 누락을 실패 테스트로 재현하고 보완.
- [x] 기존 문서에 제품 설계, 상태/권한 경계, dependency-ordered 계획 통합.
- [x] 관련 local/fake-S3/browser regression, gate, lint, metrics, portfolio 정합성 검증.
- [x] 현재 결과와 잔여 human/external evidence를 canonical snapshot에 구분해 기록.

### 의존 순서

| 순서 | 사용자에게 남는 결과 | 선행 조건 | 완료 기준 / 현재 범위 |
|---|---|---|---|
| A. Approved completion 안정화 | 작성자 → 담당자 → 완료 ZIP 흐름의 검증된 구현 | 기존 approved completion gate | integrity regressions GREEN, API/storage/browser 증거; 이 Goal에서 수행 |
| B. 다운로드 후 독립 검증 | 서버 없이 완료 ZIP의 내부 무결성을 확인하는 CLI | A + 별도 candidate admission | 2026-09-05 후속 승인에 따라 구현; 아래 실행 체크리스트와 canonical snapshot 기준 |
| C. 실제 검토자 사용성 확인 | 사람이 자료·결정·불확실성·비승인 경계를 이해하는지 관측 | A; B는 독립 CLI 검수가 필요할 때만 선행 | local synthetic-data UAT의 실제 수행자 결과; 아직 미실행 |
| D. 관측된 결함만 개선 | UAT에서 막힌 동작 해소 | C의 재현 가능한 observation | 기존 승인 계약의 버그는 regression, 새 동작은 새 gate; 범용 기능 확장 제외 |
| E. Local pilot 인계 | 설치 전제, 사용 흐름, 검증 명령과 한계가 일치하는 전달물 | 필요한 A-D 완료 | 미해결 blocker 표시, local runbook 검수; 배포/공개 아님 |
| F. 외부 실증 | 실제 provider/G2B/cloud 환경의 별도 증거 | 비용/데이터/환경별 명시 승인 | M1/M2/M6 각각의 canonical proof; 현재 보류 |

기간을 임의로 확정하지 않는다. 각 단계는 검증 가능한 결과로 종료하고, 실패나
scope drift가 생기면 원인과 남은 조건을 기록한다. 이전 자동화 Goal이나
Codex-Orca routing은 재가동하지 않고 현재 Codex task에서 진행한다.

### Reviewed-Package Verifier CLI

2026-09-05 후속 실행: 사용자가 앞서 제시한 CLI·회귀 테스트·관련 문서의 완성을
승인했다. Draft SHA-256 `d44ffb960c266ab5f1bb525e88596238184b36a27ed4f8bb3c3d048efb7dce22`에
결속해 gate decision을 기록했다. 기존 completion Goal과 구분되는 후속 local 구현이다.

- [x] Exact draft와 기존 verifier bytes 확인, 사용자 승인 기록.
- [x] CLI 계약 실패 재현과 bounded read-only 구현.
- [x] 변조·입출력·정보 노출·무변경 CLI 전용 회귀 검증.
- [x] Usage, canonical snapshot, metrics와 portfolio 동기화.

Local 구현과 관련 회귀 검증까지 완료했다. 상세 명령·결과는 canonical snapshot의
Reviewed-Package Verifier CLI 절에 기록한다. 다음 남은 단계는 실제 검토자의
synthetic-data UAT이며, 이 CLI의 자동 검증으로 대신 완료 처리하지 않는다.

승인 전 repository evidence: `scripts/verify_generation_export_packet.py`는 원본 packet만
검증했고, 완료 ZIP의 verifier는 `app/storage/generated_document_review_models.py`의
Python 함수로만 노출되어 있었다. 다운로드한 완료 ZIP을 검증하려면 Python
호출을 직접 작성해야 했다. 이는 코드로 확인한 사용 경로의 공백이지 실제 고객의
불편, 수요 또는 사용률을 측정한 결과는 아니다.

Approved record: `docs/future_feature_gates/generated_document_reviewed_package_verifier.json`.
계획 요청만으로 승격하지 않았고, 구체적 범위에 대한 후속 사용자 승인으로
`approved` decision을 기록했다. 기존 terminal completion decision은 보존했다.

구현은 새 read-only CLI `scripts/verify_generated_document_reviewed_package.py`와
그 회귀 테스트로 제한한다. 기존 pure verifier를 호출하고 ZIP을 추출하지 않으며
backend, app startup, credentials, provider 또는 network에 접근하지 않는다.
성공 stdout은 versioned JSON의 status, packet/receipt/package SHA-256, package
size, decision, `operational_approval=false`만 포함한다. Rationale, stable identity,
tenant/project/title/operation/timestamp와 local path는 출력하지 않는다.
실패는 payload를 노출하지 않는 stderr와 nonzero exit code로 닫는다.
내부 검증 성공을 발급자 신원, 현재 source 또는 법적 승인으로 설명하지 않는다.

검증 순서: CLI 미존재/실패 계약 RED → bounded file read와 pure
verifier 호출 → 결정별 GREEN → tamper/size/type/IO failure → stdout redaction과
read-only/hash 보존 → 관련 packet/review regression. Dependencies나 새 API/UI는
추가하지 않는다. CLI와 전용 test 파일은 후속 승인 이후에 추가했다. macOS/Linux의
`O_NOFOLLOW`와 `O_NONBLOCK`으로 입력을 열고 descriptor의 regular-file 여부와
읽기 전후 크기를 확인한다. 안전한 open flag가 없는 플랫폼은 fail closed한다.
기존 verifier가 간접 참조하는 Provider ABC는 타입 정의만 import하며, concrete
provider/factory, backend, `.env`와 AWS SDK import 없이 동작하는지 별도 process에서 검사한다.

### 완료와 전달 규칙

Local technical completion, human UAT, external readiness는 서로 다른 상태다.
Mock은 구조와 흐름을 검증하지만 실제 생성 품질을 증명하지 않는다. Fake-S3는
storage 계약의 테스트이며 live AWS 결과가 아니다. CLI의 내부 무결성 검증은
실제 사람의 UAT나 출력 문서의 내용·레이아웃 검수를 대체하지 않는다.

현재 Goal에는 commit/push가 필요조건이 아니다. 별도 명시 요청이 생기면 서로
의존하는 completion 코드·tests·spec·snapshot·README/portfolio를 하나의 단위로
묶어 검토하고, 후속 candidate 구현은 별도 단위로 묶는다. 각 테스트 실행마다
commit하지 않는다. Push/merge 전에는 실제 CI/CD trigger와 외부 효과를 확인한다.

## 1. Execution Goal

The next product goal is to turn DecisionDoc AI from a broad document generation platform into a focused, reviewable decision package workflow.

The first execution target is:

> A local, mock-provider-compatible workflow that produces a procurement-oriented decision package with evidence, validation, reviewer handoff, pending sign-off, and exportable artifacts.

This should become the product's demonstrable core loop.

## 2. Product Loop To Prove

The product loop should be simple enough to explain in one demo:

1. Define or import a decision topic or procurement opportunity.
2. Attach or reference supporting source material.
3. Generate a structured decision package.
4. Show evidence, hard gaps, readiness state, and uncertainty.
5. Generate a reviewer handoff.
6. Create a pending sign-off record.
7. Validate a completed review record.
8. Export the final package.

The loop is complete only when a non-engineering reviewer can inspect the package and understand what is recommended, what evidence was used, and what remains explicitly unauthorized.

## 3. 30-Day Plan

### Objective

Make the product direction tangible through a narrow local demo path.

### Build

- Define a `Decision Package` schema or internal shape.
- Map existing generated documents into package sections.
- Add a procurement-oriented package example using current public procurement copilot specs.
- Produce a local evidence summary for the package.
- Produce a reviewer handoff and pending sign-off from that package.
- Add a project-record adapter that maps recommended procurement decision state into the package shape.
- Add a local project-record export CLI for existing procurement decision records.
- Add a seeded local demo runner that creates a demo procurement decision record and exports the package artifacts.
- Add an artifact checker that validates generated package directories and authorization boundaries.
- Persist local demo run evidence as `demo_run_result.json`.
- Add an operator-readable validation summary with `operator_summary` and `next_review_action` so a reviewer can see the review state without inferring it from raw JSON flags.
- Add package-to-proposal handoff metadata for drafting preparation while preserving the same non-authorization boundary.
- Add `procurement_review.html` as a script-free, read-only browser workspace that presents recommendation, hard filters, score factors, evidence gaps, bid readiness, handoff state, and authorization boundaries in one artifact.
- Version the local evidence CLI stdout contract in `cli_contract_manifest.json` so automation can rely on stable `status`, `error_type`, and `error` fields instead of traceback parsing.
- Validate the CLI contract manifest and persisted manifest validation receipt through `validate_procurement_decision_package_cli_contract_manifest.py` and `check_procurement_decision_package_cli_contract_manifest_result.py`.
- Keep all flows runnable with `mock` provider and local storage.

### Documentation

- Add a product demo scenario document: [DecisionDoc AI Local Product Demo Scenario](./product_demo_scenario.md).
- Add one sample input and expected output package: [procurement decision package local demo sample](./samples/procurement_decision_package_local_demo/).
- Add a local demo runbook: [DecisionDoc AI Local Demo Runbook](./product_local_demo_runbook.md).
- Link product direction, execution plan, roadmap, and procurement PRD.

### Verification

- Unit or infrastructure tests for package shape.
- Local command or pytest path that proves package creation.
- Shared success and handled-failure contract tests for the local evidence CLI set.
- Manifest validation that records `contract_version`, manifest SHA256, and byte size with `--write-result --result-path`.
- No provider API call required.
- No AWS runtime required.
- No training or model promotion path touched.

### Acceptance Criteria

- A reviewer can open one folder or output bundle and see:
  - generated decision documents,
  - structured recommendation,
  - evidence references,
  - validation result,
  - handoff,
  - pending sign-off.
- The workflow passes a deterministic local test.
- The local evidence CLI contract manifest is versioned, validated, and referenced by the runbook and sample README.
- README or public docs are not updated with unverified claims.

## 4. 60-Day Plan

### Objective

Turn the local demo path into a practical product workflow.

### Build

- Add procurement go/no-go decision output:
  - `GO`,
  - `CONDITIONAL_GO`,
  - `NO_GO`.
- Add deterministic hard filters.
- Add soft-fit score breakdown.
- Add bid-readiness checklist.
- Expand package-to-proposal handoff metadata beyond the local fixture path.
- Expand the operator-readable validation summary as the package moves beyond the local fixture path.

### UI Or CLI Surface

Choose the smallest surface that makes the workflow inspectable:

- CLI summary first if UI work would slow the core model.
- UI review console next if the package structure is stable.

The surface must answer:

- Is the package valid?
- What evidence supports the recommendation?
- What is missing?
- Who needs to review?
- Does this authorize any operational action?

Current local evidence slice:

- The Ops dashboard compares 30/90/180/365-day auth-session retention policies from one validated in-memory inspection. It does not issue an unauthenticated probe, validates `auth-session-retention-comparison.v1`, exact policy order, aggregate monotonicity, the non-atomic snapshot boundary, and false deletion authority, then discards stale request or tenant completions. A selected policy can be downloaded as tenant-bound `auth-session-retention-review-handoff.v2`; a verified page-memory source can then produce `auth-session-retention-recheck-receipt.v1` after source/current schema, exact body SHA-256, comparison and aggregate fingerprint SHA-256, tenant, selected policy, review-only authority, current auth-session revision, and request generation all agree. A verified H117 receipt can then issue deterministic `auth-session-retention-review-disposition-receipt.v1` evidence for an allowlisted operator disposition. The source stays in page memory, request/tenant/auth/Ops-key invalidation discards it, and the receipt leaves reviewer identity, approval, execution, policy, deletion, scheduler, and mass-revoke authority false. Ops Key rotation invalidates only the H118 generation/source and does not supersede an unrelated JWT refresh. Selector change, refresh, tenant or auth-context change, handoff and recheck supersede older evidence. `unchanged` is only aggregate equivalence, while `changed` requires a fresh handoff without creating approval authority. No deletion, scheduler, policy persistence/application, provider call, or external runtime action is exposed.
- The DocumentOps workbench now reduces three separate governance reads to one reviewer-facing overview request. The service reads training governance, selected-backend artifact inventory, and reviewer sign-off independently, then returns the first actionable state and next review action while preserving all source reports. It fingerprints each source after excluding only its top-level generation time and combines those values into a review-state fingerprint. The browser compares successful same-tenant observations in memory, labels the recheck as first, unchanged, or changed, and keeps one stale tenant/request guard. A successful export, freeze, dry-run approval, execution request, pre-execution audit write, or a planning provider/model change invalidates an in-flight read and marks the open result as a previous observation; only a successful new overview request restores the fresh state. Trajectory Stats, the task-filtered Reviewed SFT export/freeze list, Training Readiness, and Training Execution Request Records increment independent same-tenant request versions and accept only the latest success or error, so older responses cannot roll back current counts, artifact rows, the freeze offered for dry-run approval, or two-person guard evidence. The list refresh after a successful execution request also supersedes a read that started before the save. Training Audit Checklist applies the same ordering guard with an exact tenant and provider/model query binding. Planning changes remove the previous audit action until recheck, and a completed audit export invalidates an older in-flight checklist read. Adapter Contract and Rehearsal use separate request versions and exact tenant/provider/model bindings, reject older success and error responses, and replace an open result with `RECHECK REQUIRED` as soon as the planning selection changes. SFT Export Preview and the reviewed artifact list also bind their results to the selected task, while Training Plan Preview binds to the exact provider/model query; changing those inputs invalidates both in-flight and open evidence. Governance views and sign-off handoff downloads append a redacted tenant audit entry containing only the surface, aggregate status, and read-only state; the fingerprint and source reports are not copied into audit history. The comparison is not persisted, does not make the combined snapshot atomic, and keeps dataset upload, provider calls, training, job creation, and model promotion unauthorized.
- Concurrent DocumentOps Agent runs bind the result panel to the latest initiated run and tenant. A late same-tenant trajectory save refreshes history without resetting the current filters or replacing the latest draft, while a stale failure remains warning-only.
- DocumentOps controls that can create an export, freeze, dry-run approval, execution request, audit artifact, or provider-backed Agent request run as browser single-flight actions. The initiating button is disabled before the async action starts and restored after success or failure, while read-only refresh controls remain independent. The browser assigns one UUID operation identity to each governance write and captured Agent run. Governance records bind it to the canonical request payload in private metadata, return the original verified artifact for an exact replay, and reject changed input with `409`. Captured Agent runs claim a separate private receipt before provider execution; exact replay returns the stored trajectory-bound result without another provider call or usage event. The API-key protected status route reads only the current tenant receipt, omits private owner/hash/result fields, and audits the operation ID, status, and replay decision. After a lost response, the browser reads status without cache and requires the schema, operation ID, state-specific fields, read-only flag, and provider-call denial to agree. Mismatched, unavailable, or running state keeps the captured tenant and payload only in page memory, and both the Agent button and status recheck join one recovery promise. Failed state ends pending recovery after surfacing the evidence action; verified success alone exact-replays the original payload. A captured POST first records an exact three-field marker in a tenant-scoped same-origin storage key and serializes the claim with a tenant-scoped Web Lock when supported. Reload, another tab, and a page reopened after the owner tab closes use that marker for status-only inspection and block a new POST without persisting or reconstructing payload. Different tenant markers coexist; foreign tenant read/write/clear does not remove them, and H96 base-key markers remain owner-readable. Login, registration, refresh, and LDAP login validate token claims before one helper commits access/refresh credentials and the signed tenant. Any failed browser write restores the previous session and prevents current user or DocumentOps evidence from changing. The upper 401 recovery path consumes an explicit refresh outcome and joins concurrent callers to one refresh promise. The provider retry helper retries once only after refresh, while generic mutating requests require an explicit retry and are never replayed automatically. Rejected credentials clear the current auth context; endpoint or storage failures preserve credentials and unsaved evidence, and a superseded response cannot overwrite a newer login session. Authorized switching likewise writes the next tenant ID before clearing the previous context, so storage failure leaves the current tenant, draft, recovery promise, and marker intact. Explicit release confirms that backend execution continues and trajectory/audit evidence still requires review. Strict marker validation rejects extra fields and mismatched schema, tenant, or UUID in the scoped slot; logout and invalid session clear the current context. Shared storage failure uses tenant-scoped tab storage, and failure of both stores keeps only same-page execution available. Uncaptured runs keep their existing behavior. Governance CAS can still leave an unreferenced immutable artifact, while Agent receipts do not provide cross-device coordination, atomic simultaneous claims without Web Locks, process-crash recovery, cross-ID semantic deduplication, exactly-once execution, or automatic GC.
- Same-origin auth storage changes now advance the receiving tab's session revision for access token, refresh token, tenant ID, and full local-storage clear events. An older in-flight refresh is discarded even when another tab reuses the same refresh-token bytes; unrelated storage keys are ignored. The receiving page compares the final signed user, tenant, and role with its current context. A mismatch requests one reload so current user and page-memory evidence are rebuilt under the new authorization context, while a same-identity and same-role token rotation leaves current work in place. Protected requests and SSE Bearer-header subscriptions resolve current role and active state from tenant user storage, so a stale JWT role cannot preserve removed privileges and a deactivated user cannot open a new subscription. The browser uses an authenticated fetch stream instead of placing the access token in the event URL. This is per-request backend authorization plus same-origin browser reconciliation; it does not provide an administrator-wide revocation table or cross-device push coordination.
- Password change also advances a persisted credential version in the same CAS as the password hash. Older access and refresh tokens fail on their next protected request or refresh exchange, the profile flow commits the returned replacement pair, and another same-origin tab reloads when the version changes. Register, login, invite, LDAP, SAML, GCloud, and password-change pairs additionally share a random tenant-scoped `auth-session.v2` identity; refresh preserves it, and strict v1 reads remain compatible. `POST /auth/logout` revokes only the signed current session through selected-backend CAS, so a separate login remains active while copied same-session credentials fail on their next protected request, refresh, or open SSE recheck. Self-service inventory validates every direct object in the tenant session prefix, then returns only the current user's active current-version sessions with `no-store`. `PATCH /auth/sessions/label` lets the owner set or clear a bounded user-supplied device name through CAS without adding User-Agent or IP fields to session state or inventory; missing, foreign, stale-version, revoked, and expired targets share one `404`. Selected revoke is strict, owner-bound, retry-safe, protects current, and hides foreign versus missing targets. Confirmed other-session bulk revoke preserves current, while confirmed all-device revoke writes the same validated snapshot with current last. The scan and writes are not a multi-object transaction: a mid-operation backend failure may leave partial other-session progress, a lost current-write response may leave the server revoked before browser cleanup, and a session created after the snapshot remains for the next inspection. `GET /admin/auth-sessions/retention-preview` gives an admin JWT or Ops key an aggregate-only view of old expired/revoked state after strict whole-prefix validation. Its read-only contract discloses no user, session, or label identity and grants no deletion authority. The profile keeps session IDs out of the DOM and uses one single-flight plus request/token/modal/mutation generations for label and revoke actions. All-device success clears browser credentials and page-memory evidence; a failed response preserves the initiating browser. Open SSE subscriptions revalidate expiry and persisted user/session authority every 15 seconds. General browser logout completes local cleanup immediately even if server revocation is unavailable. Corrupt session state fails closed and audit omits tokens, user IDs, target session IDs, and user-supplied labels while retaining aggregate counts. Legacy sessionless exact logout/inventory/label/selected/bulk revoke, immediate cross-device push, automatic User-Agent/IP session inventory, administrator mass revoke, actual expired-session deletion or scheduling, and a shorter stream-termination SLA remain outside this plan.
- Auth-session labels use one API/storage validator. It trims request input, limits the result to 40 characters, rejects Unicode control and display-direction formatting characters, and preserves ZWNJ/ZWJ for natural text and emoji composition.
- Trajectory history reads bind each response to the exact tenant, task/review filters, search query, and ordering captured at request start. A query change during the search debounce invalidates the older response immediately, before the replacement request begins.
- Report quality pilot export now has a server-enforced reviewer preflight before download. The tenant-scoped preview preserves the selected 3-5 ready artifacts in order and returns the exact JSONL SHA256 plus explicit false dataset-upload, provider-fine-tune, training, and model-promotion boundaries. Export requires that hash as `preview_sha256`, rejects stale content, returns a verification header, and records matching preview/export audit evidence.
- Imported report quality pilot packs now include a local browser review workspace bound to the source manifest and current draft SHA256 values. It presents before/after planning and slide evidence, visible claims, workflow/final references, validation blockers, and required actions before capturing human decisions, scores, scans, rationale, and structured change requests into a downloaded JSON draft. Decision templates and SHA-derived browser-draft archives use write-once publication, so a concurrent destination preserves the earlier file and stops before draft application. The apply CLI validates the external draft without moving it, preserves the exact bytes under a pack-local name, applies the all-or-nothing decision batch, writes a matching receipt, and refreshes the worksheet and human review manifest against the resulting draft hashes. Ready sync then requires that current manifest and a validated `require_ready` accepted decision receipt, rechecks both before writing, and returns their hashes with the JSONL hash. Dry-run, invalid batches, pending local review, and unsafe evidence targets leave downstream output unchanged, and no path authorizes external training actions.
- The browser workspace now closes the next local handoff step by rendering pack-bound dry-run and apply commands itself. Python shell-quoting preserves paths with spaces or apostrophes. Both commands stay disabled until the current form has produced a valid downloaded draft, and any later input change locks them again so a stale Downloads file cannot be mistaken for the visible decisions. The command variant follows that downloaded draft: `--require-ready` appears only when every artifact decision is accepted, while pending, changes-requested, and rejected batches keep the non-ready apply path. Clipboard-restricted local pages use a selection-copy fallback without external requests.
- A reviewed pack can now be finalized as a deterministic handoff ZIP without a caller-managed JSONL path. The command runs the existing ready sync in a private temporary directory, packages the exact JSONL with the current human-review manifest, accepted decision receipt and decision file, final draft bytes, and available source provenance sidecars, then removes the temporary file. Handoff v2 includes both the exact Markdown summary and a responsive script-free HTML summary that a non-engineering reviewer can open directly. The standalone verifier regenerates both views from the same evidence and rechecks membership, hashes, artifact readiness, review transitions, source binding, and the no-training boundary without the original pack; v1 Markdown-only archives remain readable. A receiver can write either verified view to a new local file, but not both in one command, and existing or symlink targets are preserved. Package and summary publication use a write-once local file contract so a concurrent destination cannot replace earlier evidence. The separate sync and `create --jsonl` path remains available when a standalone JSONL is intentionally required.
- A receiver can now select a pilot review package in the Report Workflow UI and inspect it without a CLI or server-side package persistence. The browser computes the ZIP SHA256 before upload, while the API reuses the independent verifier and the full correction-artifact validator in memory. Exact membership, entry hashes, receipt binding, tenant ownership, artifact count, semantic validity, learning readiness, and false external-action boundaries must all pass. The response then presents an operator summary, next review action, reviewer and score, before/after planning evidence, claim counts, and change requests for each artifact. Tampered, not-ready, oversized, and cross-tenant packages are rejected, while success and denial evidence remain visible in the existing audit console.
- The mock-only full pilot demo now proves the complete three-artifact path in one command: API workflow and ready correction creation, ordered preview/package, verified source import, simulated local review, ready sync, handoff finalization, and exact browser-summary extraction. It removes provider API keys inside the temporary demo context, restores the caller environment afterward, and leaves only a write-once JSON receipt. A read-only checker revalidates the receipt schema, artifact identity, SHA-256 fields, stage order, secret boundary, and excluded external actions without writing files. The receipt explicitly sets `human_review_claimed: false`; it is wiring evidence, not live-provider quality or completed human-review evidence, and the checker does not recreate the deleted temporary artifacts.
- Project detail exposes `POST /projects/{project_id}/procurement/review-packet` only to a current session-bound admin/member. Admin may assign any active reviewer; member may assign only itself. The route reads the current tenant's injected procurement store, builds the existing 12-artifact package in a temporary directory, verifies the packet before responding, and returns SHA256 plus `operational_approval: false` metadata without provider or external runtime execution.
- The project page includes a tenant-scoped procurement review inbox backed by `GET /procurement/reviews`. Admin receives the tenant view while member receives only assigned v2 records. Project history and reviewed-package download follow the same policy, and the browser uses safe assignment/completion fields rather than storage identity or attestation structure.
- Downstream `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` generation now reuses a completed review only while its packet source matches the current procurement record. Applied evidence carries packet SHA256, decision, and reviewed time into generation metadata and the saved project document; stale evidence is skipped, and every path keeps `operational_approval: false`.
- Saved review-bound documents also retain the packet source timestamp. Project detail compares that timestamp and tenant-scoped review record with the current procurement decision and exposes current/stale/missing/invalid evidence. Project-linked share creation validates the tenant/project/document identity and stores a deterministic source fingerprint; public share access revalidates the current source, renders post-share drift warnings, and writes `share.view` audit evidence without blocking local inspection or granting operational authority. The admin procurement quality summary and Locations overview merge those drift observations into the stale-share review queue, retain the latest risk observation separately from share creation, and count repeated views by affected unique link. Link-level latest-state tracking removes a recovered link from the risk queue only after a current public observation and reports that recovery separately without rewriting audit history. Revocation stores actor/time evidence, expiry remains a separate lifecycle state, and queue aggregation evaluates every risky sibling link so one closed link cannot conceal another active exposure.
- Project-linked approval creation validates or uniquely recovers the tenant-scoped project/document binding, stores request-time freshness evidence, and rejects mismatched or ambiguous identities. Approval detail and final approval recalculate the current status; a stale or missing source requires an explicit acknowledgement before final approval, with actor and timestamp persisted in the approval record and audit.
- `procurement_review.html` gives non-engineering reviewers one read-only procurement package surface and remains part of the same 12-artifact audit, export, fingerprint, and tamper-check contract. It does not create a second approval workflow.
- `manage_procurement_decision_review_packet.py` wraps those 12 validated artifacts in a deterministic ZIP with an embedded SHA256 manifest. The packet remains `review_ready`, keeps `operational_approval: false`, and can be independently reverified after handoff.
- `manage_procurement_review_receipt.py` creates `procurement_review_receipt.json` outside the packet, binds it to `packet_sha256`, and moves `review_status` once from `pending` to `completed` for the requested reviewer. Completion records review evidence only and keeps operational approval false.
- `manage_procurement_review_receipt.py render/apply-draft` adds a packet/receipt-bound browser input path without changing the script-free packet artifact. The downloaded draft is rejected when source bytes, reviewer identity, field order, UTC time, or the false operational-approval boundary drift.
- `manage_procurement_reviewed_package.py create/verify` closes the local export loop after review completion by wrapping the unchanged packet and completed receipt in a deterministic three-entry audit envelope. `review_completed` records the outcome for accepted, changes-requested, or rejected reviews and never grants operational approval.
- `review.html` shows generated documents and automatic validation evidence.
- `human_review.html` combines request evidence, automatic validation, generated Markdown, manifest-bound receipt state, reviewer notes, and the external-action boundary in one workspace. Reviewer input is downloaded as a source-bound draft rather than written directly to evidence.
- `manage_finished_doc_human_review.py` validates and atomically applies a draft only when its manifest and receipt hashes still match, without provider or AWS execution.
- A completed receipt can produce a deterministic review packet containing only manifest-declared artifacts and an embedded SHA256 index; pending review cannot be packaged as final.

### Verification

- Mock-provider end-to-end package test.
- Golden sample for at least one procurement decision package.
- Versioned CLI contract manifest test proving local evidence commands keep machine-readable stdout JSON.
- Boundary test proving accepted review does not authorize service resume, provider calls, dataset upload, training execution, or model promotion.

### Acceptance Criteria

- One procurement opportunity can move from source data to reviewable decision package.
- A project reviewer can download that package from the existing procurement UI without switching to a separate CLI workflow.
- Hard filters and unknown data are visible.
- Reviewer sign-off remains separate from operational approval.
- A local reviewer decision can be recorded once and revalidated against the exact packet bytes.
- A completed review can be exported and independently reverified without modifying its source packet or receipt.
- A completed review can inform downstream drafting without granting operational approval, and a procurement update prevents stale review evidence from being reused.
- A previously generated review-bound document visibly becomes stale after its procurement decision changes, and approval or sharing requires an explicit acknowledgement while preserving the warning as evidence.
- A stale project-linked approval cannot reach final approval through the API without a freshness acknowledgement, and the completed record identifies who acknowledged it and when.
- The demo does not depend on live provider or AWS availability.

## 5. 90-Day Plan

### Objective

Prepare the product workflow for external evaluation without overstating operational maturity.

### Build

- Exportable audit packet:
  - deterministic ZIP for the 12-artifact procurement review package,
  - embedded `packet_manifest.json` with SHA256 and byte-size fingerprints,
  - exact membership and path-boundary verification,
  - semantic revalidation after archive extraction,
  - explicit `review_ready` and false operational-approval state.
- Optional live provider lane.
- Optional deployment lane with clear stage/prod separation.
- Admin or review console only after package and validation contracts are stable.

### Documentation

- Update case study with verified local demo evidence.
- Update README only with measured or directly verified claims.
- Add `Scope & Limitations` to any public-facing material.
- Separate product capability from deployment status.

### Verification

- Full relevant local pytest gate.
- Mock end-to-end smoke.
- Optional live-provider validation note if credentials and approval exist.
- Optional deployed smoke only if environment access is available and approved.

### Acceptance Criteria

- A third party can run or inspect the local demo.
- The product story is consistent across README, roadmap, case study, and resume materials.
- No public material claims customer adoption, production deployment, or measured business impact without evidence.

## 6. Completed Core-Loop Evidence

The original nine-item local core loop is implemented. This is an evidence map,
not an Immediate Backlog and not a claim of deployed, live-provider, human-UAT,
or operational approval completion. All paths below are repository evidence for
the local/mock scope.

H129 historical reviewer-attributed evidence and H129.1 current server-issued provenance
are distinct: H128 same-backend metadata is server-issued local
provenance, not a signature, actor attestation, currentness, atomic snapshot,
approval, or external authenticity. M1 remains partial/blocked after historical
OpenAI proof; M2 has completed local live G2B smoke but no durable stage proof;
M6, human UAT, and external approval remain unproven.

| Implemented capability | Repository evidence | Local contract boundary |
|---|---|---|
| Decision Package shape | `docs/samples/procurement_decision_package_local_demo/expected_decision_package.json`, `tests/test_procurement_decision_package_builder.py` | Required package shape is compared locally. |
| Deterministic sample | `docs/samples/procurement_decision_package_local_demo/sample_input.json`, `docs/samples/procurement_decision_package_local_demo/expected_decision_package.json` | Fixture input and expected output remain deterministic. |
| Evidence summary | `app/services/procurement_decision_package/artifact_evidence.py`, `tests/test_procurement_decision_package_sample.py` | Evidence and uncertainty remain review material, not approval. |
| Package handoff | `app/services/procurement_decision_package/package_builder.py`, `scripts/build_procurement_decision_package_sample.py` | Handoff stays limited to local drafting/review preparation. |
| Pending sign-off | `app/services/procurement_decision_package/review_receipt.py`, `scripts/manage_procurement_review_receipt.py` | Pending/completed receipt is not operational approval. |
| Export packet | `app/services/procurement_decision_package/review_packet.py`, `scripts/manage_procurement_decision_review_packet.py` | Deterministic packet verification remains local. |
| Demo runbook | `docs/product_local_demo_runbook.md`, `scripts/run_procurement_decision_package_demo.py` | Demo forces the local evidence workflow. |
| CLI evidence contract | `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`, `tests/test_procurement_decision_package_docs_contract.py` | Versioned stdout JSON success/failure contract. |
| Packet-bound review receipt | `app/services/procurement_decision_package/review_receipt_workspace.py`, `app/services/procurement_decision_package/reviewed_package.py`, `scripts/manage_procurement_reviewed_package.py` | Receipt and reviewed package bind exact local packet bytes. |

## 7. Future Feature Gate

No new capability enters a backlog until a decision record supplies all of the
following: target user; concrete observed problem/evidence; current workaround;
desired outcome; bounded acceptance criteria; affected boundaries; explicit authority scope;
and a local verification path. The authority scope must state
whether the proposal remains review-only and what approval, provider, storage,
browser, deployment, or external action is explicitly excluded.

The versioned record contract, draft template, and validation commands are
defined in [Future Feature Gate](./future_feature_gate.md). A structurally valid
`draft`, `deferred`, or `rejected` record does not admit work. Implementation
requires a successful local run with `--require-approved`; that result scopes
only the implementation written in the record and does not grant external or
operational authority.

## 8. Engineering Guardrails

- Preserve route, service, schema, provider, and storage boundaries.
- Keep `mock` provider deterministic.
- Prefer additive workflow objects over broad rewrites.
- Do not put AWS, provider, dataset upload, training, or service resume inside the default demo path.
- Keep approval records separate from operational execution approval.
- Add tests around boundaries, not only happy-path document generation.

## 9. Product Guardrails

- Do not build a generic document marketplace.
- Do not optimize for many document types before one high-stakes workflow is clear.
- Do not hide uncertainty behind polished prose.
- Do not merge reviewer acceptance with service resume or training approval.
- Do not update public claims without verification evidence.

## 10. Demo Script Target

The target demo should take less than ten minutes and follow this script:

1. Open a sample procurement opportunity.
2. Show source evidence and missing fields.
3. Generate the decision package.
4. Show the recommendation and bid-readiness checklist.
5. Show validation status.
6. Generate reviewer handoff.
7. Generate pending sign-off.
8. Explain that provider calls, training, deployment, and service resume remain unauthorized.
9. Export the package.

## 11. Definition Of Done

The product execution plan is working when the repository contains:

- a stable package shape,
- one deterministic local sample,
- one reviewer handoff path,
- one sign-off path,
- one export or handoff artifact,
- tests that validate the package and authorization boundary,
- a versioned local evidence CLI contract and manifest validation receipt path,
- docs that describe only verified behavior as implemented.

H119 adds a local immutable reviewer-evidence step after H118: validate the exact source, conditionally create one canonical record, then list/read/download it without policy mutation, provider calls, training, deployment, or service resume.

H120 adds the project procurement counterpart: packet preparation resolves an active tenant admin/member to a stable reviewer identity, and completion accepts only that current session-bound principal. The v2 reviewed package adds a deterministic reviewer attestation while preserving v1 local CLI artifacts and all approval, bid, legal, contractual, provider, training, deployment, and service-resume boundaries as false or unavailable.

H121 applies the same session boundary to assignment and read access. It preserves the v1/v2 storage contracts while making the HTTP projection and browser state explicitly role-scoped.

H122 completes the evidence retrieval loop with a verified original-packet re-download. The route authorizes before reading, revalidates the immutable bytes and record binding, returns only safe evidence headers, and keeps browser downloads bound to the current review projection and auth context. It adds no reassignment, review completion, approval, provider, training, deployment, or service-resume authority.

H129 historical evidence adds the immutable reviewer-evidence boundary to Guided Decision
Review dispositions. It conditionally creates one canonical record per
tenant/project/bundle/operation, binds replay to the stable reviewer and exact
H128 source, and exposes only strictly revalidated scoped list/read/download
views. Browser work starts only from verified page-memory H128 evidence and
uses request-owned single flight. This execution slice does not close M1, M2,
M6, human UAT, deployment, or external approval and
does not authorize any provider, AWS, G2B, upload, training, promotion, deploy,
bid, legal, or contractual effect.

H128 now conditionally creates and exact-read-backs one hash-only same-backend
issuance metadata object per canonical receipt SHA-256. H129.1 server-issued
provenance independently validates and embeds only that metadata plus its hash;
v1 stays immutable and Legacy issuance unrecorded. This proof is not a signature,
actor attestation, currentness, atomic snapshot, approval, or external authenticity, and stores no
H128 body, reviewer/session/network/token value, rationale, secret, or
execution authority.

Until then, DecisionDoc AI should be described as an actively developed MVP with strong local governance and review workflow foundations.

## Generated export packet execution slice

The current generated-document export slice keeps the existing `GET /generate/export-zip` user flow but binds it to a signed tenant/request source held in the selected local/S3 `StateBackend`. `GenerationExportSourceStore` publishes an immutable content-addressed source object then conditional-create/CAS updates the tenant index, so the same local `DATA_DIR` supports restart and independent-worker export. The fixed source boundary is one hour, 500 references, 8 MiB per source, and 64 MiB referenced bytes per tenant with deterministic oldest-first eviction; missing/expired/foreign remains one no-store `404`, while corrupt/tampered/unavailable state fails closed as generic `503 EXPORT_SOURCE_UNAVAILABLE`. It canonicalizes the requested conversion set, produces only fixed artifact paths, builds all conversions before delivery, then independently verifies the exact ZIP bytes and canonical manifest. The transient result and a project document with a non-empty server-loaded `request_id` each expose one `검증된 검토 ZIP` action; both use the same browser path and request exactly `docx,pdf,pptx,hwp,excel`. The browser passes only that request identity to the existing route, checks ZIP media type, packet and manifest SHA-256 header shapes, `verified=true`, `operational_approval=false`, and the exact packet bytes before any Blob/download action. Project export captures auth revision, tenant, signed user, project-detail generation, project/document identity, and request ID; stale completions cannot create a Blob, download, notification, or current-page mutation, while successful project URLs use bounded scoped cleanup on detail close/reload/project change. A missing or expired source gives regeneration guidance without a project snapshot fallback; malformed evidence, hash/crypto failure, fetch failure, and `503` remain non-disclosing and do not download.

This is execution evidence for local integrity and review readiness only. Source persistence does not persist the packet or create an approval record: `review_only=true`, `packet_persisted=false`, false human-review/operational-approval state, and the all-false external authority object remain part of the packet contract. This slice adds no human completion, provider call, AWS runtime, G2B action, dataset upload, training, deployment, or publishing path, and does not close M1/M2/M6, human UAT, deployment, or external-approval proof gaps.

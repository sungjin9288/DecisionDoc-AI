# Status: Hermes-Inspired DocumentOps Agent

## Current Decision

DocumentOps는 DecisionDoc 내부 기능으로 구현되어 있다. Hermes는 agent loop, skill,
trajectory, evaluation, approval UX를 검토하기 위한 reference architecture이며 runtime
dependency가 아니다.

현재 개발 범위는 다음 원칙을 따른다.

- DecisionDoc의 route, service, provider, storage, tenant 경계를 유지한다.
- 외부 Hermes runtime, terminal/browser execution, remote tool execution을 연결하지 않는다.
- trajectory와 reviewed SFT dataset은 외부 실행 없는 검토 및 품질 증적까지만 다룬다.
- trajectory/review JSONL과 governance metadata index는 선택된 local/S3 `StateBackend`에서 각각 conditional create/CAS authority를 가진다.
- export/freeze/approval/request/audit artifact는 같은 backend에 immutable object로 발행하고 metadata의 identity·size·SHA-256 binding으로 검증한다.
- training provider adapter는 `stub_only`이며 upload, provider job, training, model promotion을
  실행하지 않는다.
- 유료 provider 호출과 AWS runtime 검증은 별도 승인 작업으로 분리한다.

## Implemented Runtime

| Area | Current implementation | Boundary |
|---|---|---|
| Agent loop | `app/agents/document_ops_agent.py` | skill 선택, prompt 구성, provider draft, local QA, fallback, trajectory capture |
| Skills | `app/agents/skills/` | first-party Markdown assets만 로드 |
| QA and eval | `app/evals/document_ops/` | task-specific hard gates, stable issue code, affected field, remediation hint와 rubric |
| API | `app/routers/document_ops_agent.py` | tenant-aware run, review, export, freeze, approval, audit, governance endpoints |
| Service | `app/services/document_ops_service.py`, `app/services/document_ops_governance.py` | agent와 trajectory storage를 route에서 분리하고 세 read model의 reviewer-facing 상태를 합성 |
| Trajectory storage | `app/storage/trajectory_store.py`, `app/storage/trajectory/core_mixin.py`, `app/storage/trajectory/state_mixin.py`, `app/storage/trajectory/artifact_state_mixin.py`, `app/storage/trajectory/artifact_inventory_mixin.py` | tenant-scoped trajectory/metadata CAS, review, stats; selected-backend immutable governance artifact와 read-only integrity inventory |
| Training adapter | `app/services/document_ops_training_adapter.py` | disabled contract와 read-only rehearsal만 제공 |

The implemented flow is:

```text
request
  -> DocumentOpsService
  -> DocumentOpsAgent
  -> SkillRegistry
  -> configured Provider
  -> local QA gates
  -> tenant-scoped TrajectoryStore
  -> human review
  -> reviewed SFT export
  -> dataset freeze and selected-backend governance evidence
```

## Review And Dataset Flow

The no-execution governance workflow supports:

1. Capture a redacted trajectory from a DocumentOps run.
2. Record a named human review with bounded notes, quality score, redacted metadata, version, and history.
3. Preview or export accepted trajectories as SFT JSONL; rejected, pending, and reviewer-less records stay blocked.
4. Inspect role/content schema, evidence and provenance coverage, source trajectory IDs, and SHA-256 integrity.
5. Reuse an identical export by fingerprint, or freeze a new export with checksum, source trajectory IDs, and reviewer metadata.
6. Record a checksum-bound dry-run training approval and verify that it references the latest freeze and export.
7. Create a two-person execution request only from the current approval chain, without starting execution.
8. Export a pre-execution audit and reject stale or tampered request/audit references in governance summaries.
9. Rehearse the provider adapter contract with no external side effects.
10. Compare governance metadata authority with selected-backend objects through the Ops-key read-only inventory.
11. Read training governance, artifact inventory, and reviewer sign-off independently through one Ops-key overview; prioritize the first review issue, preserve each source report, and show the non-atomic recheck boundary without performing cleanup or external execution.

These records are approval evidence. They are not authorization to upload a dataset, call a
provider training API, start a training job, or promote a model.

## Local Browser Flow

The static DocumentOps workbench now follows the same no-execution governance chain as the API:

- reviewers, freeze reviewers, dry-run approvers, execution requesters, and auditors are entered
  explicitly instead of falling back to a generic operator identity
- the ops key is available and persisted from the DocumentOps page without requiring `?ops=1`
- the Review 상태 action loads one service-composed overview, shows the prioritized review state and next action before the three source reports, and keeps one stale-response guard and refresh read-only
- each source report has a stable SHA-256 that excludes only its top-level generation time; the browser compares successful same-tenant observations in session memory and labels the recheck as first, unchanged, or changed without persisting it
- Trajectory Stats accepts only the latest same-tenant request outcome, so an older success or error cannot replace current accepted, pending, or export counts
- the task-filtered Reviewed SFT export list accepts only the latest same-tenant export/freeze response, so an older success or error cannot replace current artifact rows or emit a stale failure notice
- Training Readiness accepts only the latest same-tenant response, so an older success or error cannot restore a superseded export/freeze chain or expose an old freeze for dry-run approval
- reviewed exports can be frozen, and a matching verified freeze can receive a dry-run approval
- trajectory history uses tenant/filter/search-aware totals, title/identifier/reviewer search,
  task/review filters, and 10-record newest- or oldest-first pages so review evidence remains reachable
- browser history requests summary records and loads the full tenant-scoped trajectory only when
  a reviewer opens its detail, while existing API callers retain the default full-list response
- detail views and human review requests append success/failure audit events with trajectory and
  compact review provenance; inputs, drafts, and review notes are not copied into audit detail
- governance summary, overview, inventory, and reviewer sign-off reads plus sign-off handoff
  downloads use separate governance audit resources; only surface, aggregate status, and read-only
  state are retained, while fingerprints, source reports, and reviewer records are not copied
- a successful reviewed export, freeze, dry-run approval, execution request, or pre-execution
  audit write marks the open governance overview stale; planning provider/model changes do the same,
  and only a successful new overview read restores its fresh status
- review requests carry the version loaded with the detail record; storage compares it against the
  latest conditional-CAS state, returns an identical retry unchanged, and rejects a different stale decision
  with `409` plus expected/current version evidence
- review inputs update a user-tenant-trajectory keyed page-memory draft as the reviewer types, so
  ordinary list refreshes and conflict recovery can restore notes and score only in the same authenticated
  context; empty inputs, a successful write, logout, or invalid session clear the applicable draft state
- the browser aligns its tenant header context from the signed access token during login, registration,
  refresh, and LDAP login; denied selector changes roll back without weakening `TENANT_MISMATCH`, while an allowed
  change reloads the whole app so prior-tenant page state and delayed responses cannot remain visible
- each trajectory exposes stored input, full draft, plan, evidence status, QA issues, and review
  history before the browser accepts reviewer notes and an explicit human quality score
- readiness and governance panels show checksum and current-chain consistency for freeze,
  approval, execution-request, and audit artifacts
- provider and base-model values remain planning metadata; every request keeps training, upload,
  provider API, and model promotion disabled
- the workbench uses a compact responsive layout and hides unrelated fixed navigation/history
  controls while active so they do not cover mobile inputs

Desktop and 390-pixel mobile browser checks used a mock provider and temporary local storage. A
13-record trajectory history showed the newest or oldest 10 records on the first page and the
remaining three on the next page. Title/reviewer search and task/review filters returned the expected
sets, reset pagination, ignored an intentionally delayed stale response during rapid filter changes,
and returned to the last valid page after a filtered record changed state.
The detail check confirmed that source evidence was absent from the summary card, recovered a
malformed first response through the card retry control, then loaded the full record through the
tenant-scoped detail endpoint before accepting reviewer input.
The same browser flow filtered Admin Ops audit logs to the review action and confirmed the accepted
decision, reviewer, version, score, and stale expected/current versions without rendering the review notes.
Controls remained correct with no horizontal overflow or unexpected browser console error. This check did not
create a dataset upload, provider API call, training job, promotion, or production action.

A separate browser review check opened one `develop_quality_improvement` trajectory, matched the
full displayed draft to the API response, confirmed provenance, source evidence, and QA state,
blocked approval without a human score, rejected an intentionally stale approval after another reviewer
stored version 1, preserved the note through an ordinary list refresh, verified that the same trajectory
ID cannot read the draft under a different tenant, reloaded the latest record
without re-entering the note or score, then
persisted reviewer identity, notes, and score `0.88`
as version 2 while retaining version 1 in review history.
The reviewed record remained readable on desktop and 390-pixel mobile without horizontal overflow.
Another browser check created a local tenant and invited member, confirmed that a system admin's denied
cross-tenant selector change retained the system context, cleared page-memory review drafts on logout,
then replaced stale `system` browser state with the invited member's signed tenant claim and read the
tenant-scoped DocumentOps stats endpoint successfully. No external provider or deployment action ran.

## Access Boundaries

- Agent run, trajectory list/stats, and trajectory review require the DecisionDoc API key. Review
  writes also require the non-negative version returned by the current detail record.
- Dataset exports, freezes, training approval/readiness/plan, audit, governance, reviewer sign-off,
  and provider adapter endpoints require the ops key.
- Storage methods receive the current tenant ID. Trajectory/review JSONL uses the app-selected
  backend while export and download paths remain local handoff artifacts resolved inside the tenant boundary.
- Agent execution is blocked by maintenance mode. Read-only review surfaces remain separately
  authenticated.
- Training request schemas and storage reject `start_training`, `upload_dataset`, and
  `call_provider_api` attempts in this local workflow.

## Training Execution Status

The current provider adapter contract always reports:

```text
adapter_status=stub_only
training_execution_allowed=false
provider_api_calls_allowed=false
external_upload_allowed=false
provider_job_started=false
model_promotion_allowed=false
```

Setting `DECISIONDOC_TRAINING_EXECUTION_ENABLED=1` does not enable execution. The stub reports a
configuration error so an accidental flag change cannot turn local rehearsal into a provider job.

Real training requires a separate implementation and approval covering:

- provider and base model selection
- dataset privacy and external transfer review
- cost ceiling and billing owner
- two-person execution authorization
- provider job monitoring and cancellation
- offline/online evaluation acceptance criteria
- model registry promotion and rollback

## Verification Surface

The focused local suite is:

```bash
pytest -q \
  tests/agents/test_document_ops_agent.py \
  tests/evals/test_document_ops_gates.py \
  tests/test_document_ops_agent_api.py \
  tests/test_document_ops_training_adapter.py \
  tests/storage/test_trajectory_store.py \
  tests/storage/test_trajectory_store_integrity.py
```

The seven files currently define 94 test functions. Reproduce the source count with:

```bash
python3 -c 'import ast, pathlib; files=[pathlib.Path(p) for p in ["tests/agents/test_document_ops_agent.py","tests/evals/test_document_ops_gates.py","tests/test_document_ops_agent_api.py","tests/test_document_ops_training_adapter.py","tests/storage/test_trajectory_store.py","tests/storage/test_trajectory_store_integrity.py","tests/storage/test_trajectory_artifact_authority.py"]]; print(sum(sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith("test_") for n in ast.walk(ast.parse(f.read_text()))) for f in files))'
```

Integration coverage also exists in:

- `tests/test_report_workflows_api.py`
- `tests/test_infrastructure.py`

Before release or handoff, run the focused suite and the repository non-live gate. A test-function
source count is not a pass claim.

Last local verification on 2026-07-21:

- trajectory/API focused gate: 79 passed, 1 warning
- DocumentOps, report-workflow integration, and infrastructure expansion: 280 passed, 1 warning
- governance index/artifact storage gate: 82 passed
- governance index/artifact and DocumentOps caller expansion: 296 passed, 1 warning
- governance artifact inventory trajectory storage gate: 84 passed
- governance artifact inventory and DocumentOps caller expansion: 333 passed, 1 warning
- governance artifact browser static/PWA gate: 199 passed, 1 warning
- governance artifact storage/API/Chromium connection gate: 24 passed, 1 warning
- governance review overview backend/API gate: 12 passed, 1 warning
- governance review overview static gate: 7 passed, 143 deselected, 1 warning
- governance review overview Chromium gate: 1 passed
- governance recheck fingerprint backend/API/static gate: 7 passed, 1 warning
- governance recheck fingerprint Chromium gate: 1 passed
- governance browser freshness static contract: 2 passed, 1 warning
- governance browser freshness Chromium gate: 1 passed
- trajectory stats latest-response static gate: 1 passed, 1 warning
- trajectory stats same-tenant Chromium gate: 1 passed
- reviewed export list latest-response static gate: 1 passed, 1 warning
- reviewed export list same-tenant Chromium gate: 1 passed
- training readiness latest-response static gate: 1 passed, 1 warning
- training readiness same-tenant Chromium gate: 1 passed
- DocumentOps static expansion gate: 23 passed, 131 deselected, 1 warning
- related DocumentOps Chromium expansion gate: 5 passed, 40 deselected
- full repository non-live gate: 4229 passed, 2 skipped, 4 deselected, 1 warning
- mock/local uvicorn lifecycle: capture/detail/review version 1/stale `409`, private receipt persisted and public-hidden, external calls 0
- no live-provider or external-runtime tests were run

## Deferred External Proof

The following actions are intentionally deferred because they can incur cost or affect external
systems:

- OpenAI, Gemini, or Claude live API calls
- dataset upload to any provider
- provider training or fine-tuning job creation
- model candidate promotion
- AWS deploy, Lambda invocation, CloudWatch investigation, or S3 runtime write
- production service resume or production browser UAT

Local mock-provider, storage, API, lint, compile, and non-live pytest verification may continue.

## Historical Evidence Cleanup

The former Phase 1-346 closure chain repeated the same local no-cost boundary across generated
handoff, receipt, summary, and validator layers. Those generated artifacts were removed when they
stopped contributing runtime behavior or independent verification. Git history remains the source
for historical phase records.

Three remaining freeze validators were removed because their required artifact directories and
imported validator modules no longer existed. Keeping commands that fail at import time would make
the status surface misleading.

## Next Development Work

No-cost development should focus on runtime value rather than adding another evidence wrapper:

1. Keep the local browser flow aligned with the implemented review, export, freeze, and governance states.
2. Extend task-specific QA diagnostics only when a new deterministic failure mode is identified.
3. Preserve trajectory, tenant, artifact-integrity, and audit coverage as API surfaces evolve.
4. Run live-provider proof only in a separately approved, budget-capped task.

## Source Documents

- `ANALYSIS.md`: Hermes adoption decision and risk analysis
- `ARCHITECTURE.md`: current DecisionDoc-native component boundaries
- `IMPLEMENTATION_PLAN.md`: active no-cost development sequence and approval gates
- `TRAINING_AND_DATASET_PLAN.md`: dataset lifecycle and future training policy

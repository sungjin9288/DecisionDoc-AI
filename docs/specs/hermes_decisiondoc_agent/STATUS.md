# Status: Hermes-Inspired DocumentOps Agent

## Current Decision

DocumentOps는 DecisionDoc 내부 기능으로 구현되어 있다. Hermes는 agent loop, skill,
trajectory, evaluation, approval UX를 검토하기 위한 reference architecture이며 runtime
dependency가 아니다.

현재 개발 범위는 다음 원칙을 따른다.

- DecisionDoc의 route, service, provider, storage, tenant 경계를 유지한다.
- 외부 Hermes runtime, terminal/browser execution, remote tool execution을 연결하지 않는다.
- trajectory와 reviewed SFT dataset은 로컬 검토 및 품질 증적까지만 다룬다.
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
| Service | `app/services/document_ops_service.py` | agent와 trajectory storage를 route에서 분리해 orchestration |
| Trajectory storage | `app/storage/trajectory_store.py`, `app/storage/trajectory/` | tenant-scoped persistence, review, stats, export, freeze, approval records |
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
  -> dataset freeze and local governance evidence
```

## Review And Dataset Flow

The local workflow supports:

1. Capture a redacted trajectory from a DocumentOps run.
2. Record a named human review with bounded notes, quality score, redacted metadata, version, and history.
3. Preview or export accepted trajectories as SFT JSONL; rejected, pending, and reviewer-less records stay blocked.
4. Inspect role/content schema, evidence and provenance coverage, source trajectory IDs, and SHA-256 integrity.
5. Reuse an identical export by fingerprint, or freeze a new export with checksum, source trajectory IDs, and reviewer metadata.
6. Record a checksum-bound dry-run training approval and verify that it references the latest freeze and export.
7. Create a two-person execution request only from the current approval chain, without starting execution.
8. Export a pre-execution audit and reject stale or tampered request/audit references in governance summaries.
9. Rehearse the provider adapter contract with no external side effects.

These records are approval evidence. They are not authorization to upload a dataset, call a
provider training API, start a training job, or promote a model.

## Access Boundaries

- Agent run, trajectory list/stats, and trajectory review require the DecisionDoc API key.
- Dataset exports, freezes, training approval/readiness/plan, audit, governance, reviewer sign-off,
  and provider adapter endpoints require the ops key.
- Storage methods receive the current tenant ID; export and download paths are resolved inside the
  tenant boundary.
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
  tests/storage/test_trajectory_store.py
```

The five files currently define 58 test functions. Reproduce the source count with:

```bash
python3 -c 'import ast, pathlib; files=[pathlib.Path(p) for p in ["tests/agents/test_document_ops_agent.py","tests/evals/test_document_ops_gates.py","tests/test_document_ops_agent_api.py","tests/test_document_ops_training_adapter.py","tests/storage/test_trajectory_store.py"]]; print(sum(sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith("test_") for n in ast.walk(ast.parse(f.read_text()))) for f in files))'
```

Integration coverage also exists in:

- `tests/test_report_workflows_api.py`
- `tests/test_infrastructure.py`

Before release or handoff, run the focused suite and the repository non-live gate. A test-function
source count is not a pass claim.

Last local verification on 2026-07-14:

- focused DocumentOps suite: 54 passed
- report-workflow and infrastructure integration: 140 passed
- full `pytest -q tests/ -m "not live" --tb=short`: 2898 passed, 2 skipped, 4 deselected
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

# AGENTS.md — DecisionDoc AI

DecisionDoc AI is a FastAPI-based AI document generation and collaboration platform.
This file defines durable repository-wide engineering rules for Codex and human contributors.

If this file conflicts with the actual repository state, trust the real codebase first.
For ambiguous or cross-cutting work, inspect the repository, identify the real integration points, and avoid broad implementation until the change surface is clear.

---

## 1) Working agreement

- Treat this file as the repository-wide engineering contract.
- Keep changes additive and backward compatible unless the task explicitly requires a breaking change.
- Reuse existing product flows before inventing new subsystems.
- Prefer narrow, verifiable diffs over large speculative rewrites.
- For difficult tasks, plan first, then implement, then validate.
- When repository-specific task docs exist under `docs/specs/...`, treat them as the task-level source of truth.
- If assumptions are wrong, update the relevant task status/spec document before widening the implementation.

---

## 2) Product scope

DecisionDoc AI provides:
- AI-assisted document generation
- project/workspace management
- document collaboration, review, approval, sharing, and history
- public procurement / G2B support
- knowledge document ingestion and reuse
- export flows (DOCX, PDF, HWP, XLSX, PPTX, ZIP)
- evaluation, A/B testing, dataset and operations tooling
- web UI and API from the same FastAPI application

This repository is not just a simple generation API.
When implementing new features, preserve the platform model:

**project + knowledge + generation + approval/share + export + audit + ops**

---

## 3) Representative repository map

> Note:
> The paths below are a high-level reference, not a guaranteed exhaustive map.
> If the repository has evolved, prefer the actual code layout over this summary.

Representative areas include:
- `app/main.py` — application entrypoint / app creation
- `app/aws_lambda.py` — Lambda handler
- `app/routers/` or equivalent API route modules
- `app/services/` — service-layer orchestration
- `app/providers/` — LLM provider abstractions and implementations
- `app/storage/` — storage abstractions and implementations
- `app/templates/` — document templates
- `app/bundle_catalog/` — bundle registry and bundle metadata
- `app/domain/` — domain schema / domain rules
- `app/auth/` — auth and permission helpers
- `app/middleware/` and `app/observability/` — request tracking, logging, metrics
- `app/ops/` — operations tooling
- `app/eval/`, `app/eval_live/` — evaluation pipelines
- `app/static/` — UI assets when served from the same app
- `data/` — local storage data
- `tests/` — automated tests
- `scripts/` — smoke and operational helper scripts
- `infra/sam/` — AWS SAM deployment
- `docs/` — product, deployment, and task-specific specs
- `.github/workflows/` — CI/CD workflows

Do not assume this summary is complete.
Inspect the real repository before making cross-cutting changes.

---

## 4) Runtime, deployment, and environment model

- Primary backend framework: FastAPI
- Primary language: Python
- Data validation: Pydantic v2
- Template engine: Jinja2
- Deployment modes:
  - local development
  - Docker Compose
  - AWS SAM / Lambda
- Storage modes:
  - local filesystem
  - AWS S3
- Provider modes may include:
  - `openai`
  - `gemini`
  - `local`
  - `mock`

Important rules:
- `mock` provider must remain usable and deterministic for development and test flows.
- Local filesystem and S3 storage abstractions must both be preserved unless an explicit architecture change is requested.
- Long-term operating direction and environment hardening roadmap:
  - `docs/operating_model_roadmap.md`

---

## 5) Core commands

Use the real repository commands if they differ, but these are the default expectations.

### Local setup

```bash
pip install -r requirements.txt
cp .env.example .env
bash scripts/install_git_hooks.sh
python -m uvicorn app.main:app --reload
```

`bash scripts/install_git_hooks.sh` configures a local `pre-commit` hook that runs `python3 scripts/check_secret_hygiene.py` before each commit, so tracked AWS credentials are blocked before they ever reach CI.

### Docker

```bash
docker compose up -d
curl http://localhost:8000/health
```

### Tests

```bash
pytest tests/
pytest tests/ -m "not live"
pytest tests/ -m live
```

### Targeted example

```bash
pytest tests/test_voice_brief_import.py -q
```

### Smoke

```bash
python scripts/smoke.py
python scripts/ops_smoke.py
python scripts/voice_brief_smoke.py
python scripts/openspace_smoke.py
```

### OpenSpace integration

- integration guide: `docs/openspace_integration.md`
- wiring smoke: `python scripts/openspace_smoke.py`
- current expectation: local skill discovery and MCP wiring should pass; end-to-end `execute_task` may still be blocked or time out depending on host-side LLM auth/session exposure

### Eval

```bash
python -m app.eval
python -m app.eval_live
```

### AWS SAM

```bash
sam local start-api -t infra/sam/template.yaml
sam deploy --guided --template-file infra/sam/template.yaml
```

If linting or type-check commands are configured in the repository, run them for touched areas as part of validation.

---

## 6) Configuration guidance

Prefer reading configuration once during app startup / dependency wiring rather than inside request handlers.

Important environment groups include:

### Runtime / Provider
- `DECISIONDOC_PROVIDER`
- `DECISIONDOC_ENV`
- `ENVIRONMENT`
- `DECISIONDOC_TEMPLATE_VERSION`

### Auth / Security
- `DECISIONDOC_API_KEY`
- `DECISIONDOC_API_KEYS`
- `DECISIONDOC_OPS_KEY`
- `JWT_SECRET_KEY`
- `DECISIONDOC_CORS_ENABLED`
- `ALLOWED_ORIGINS`

### Storage
- `DECISIONDOC_STORAGE`
- `DATA_DIR`
- `EXPORT_DIR`
- `DECISIONDOC_S3_BUCKET`
- `DECISIONDOC_S3_PREFIX`
- `AWS_REGION`

### Search / LLM / Retrieval
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `LOCAL_LLM_*`
- `DECISIONDOC_SEARCH_ENABLED`
- `SERPER_API_KEY`
- `BRAVE_API_KEY`
- `TAVILY_API_KEY`

### Enterprise integrations
- `G2B_API_KEY`
- `STRIPE_*`
- `STATUSPAGE_*`
- `SSO_ENCRYPTION_KEY`

### Voice Brief
- `VOICE_BRIEF_API_BASE_URL`
- `VOICE_BRIEF_API_BEARER_TOKEN`
- `VOICE_BRIEF_TIMEOUT_SECONDS`

Rules:
- Do not scatter raw `os.getenv(...)` calls through route handlers.
- Prefer configuration collection and validation at app creation time.
- Preserve production behavior such as disabling docs/openapi routes when production mode is enabled.

---

## 7) Engineering rules

### 7.1 Pydantic and request/response models

Use strict validation for external input models.

Preferred pattern:

```python
class ExampleRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
```

Rules:
- New request models should reject unknown fields unless there is a strong reason not to.
- Preserve clear field constraints and explicit defaults.
- Prefer stable, explicit schemas over loosely typed payloads.

### 7.2 Provider and storage abstractions

Provider and storage logic must stay behind clear abstractions.

Rules:
- Provider implementations should follow the repository’s provider interface / ABC pattern.
- Storage implementations should follow the repository’s storage interface / ABC pattern.
- Add or extend provider/storage implementations through the existing factory pattern.
- Do not bypass factory wiring with ad-hoc instantiation in route handlers.

### 7.3 Function signatures

Prefer keyword-only arguments for important operational parameters.

Preferred style:

```python
def generate_documents(self, requirements: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    ...
```

### 7.4 File writes and persistence

Use safe persistence patterns.
For local file writes, prefer atomic write patterns such as:
- write temp file
- flush
- fsync
- replace

Do not introduce fragile partial-write behavior.

### 7.5 Logging and observability

Use structured logging.
Prefer repository utilities such as `log_event(...)` and request-scoped structured fields.

Rules:
- Preserve request id propagation.
- Preserve structured logs for API and ops flows.
- Prefer explicit operational metadata over free-form print statements.

### 7.6 Dependency wiring

Prefer application-level dependency wiring and `app.state` style dependency access where that is the repository pattern.

Rules:
- Keep route handlers thin.
- Put orchestration in services.
- Put provider/storage selection in factories or startup wiring.
- Do not hide architectural decisions inside handlers.

### 7.7 Types

Use modern Python typing consistently:
- `dict[str, Any]`
- `list[str]`
- `str | None`

Prefer explicit types for service boundaries and persisted data structures.

---

## 8) Architecture principles

### 8.1 Reuse the existing platform

When adding features:
- reuse project/workspace concepts
- reuse document generation flows
- reuse bundle registry and export flows
- reuse knowledge document flows
- reuse approval/share/history/audit mechanisms
- reuse eval and smoke patterns
- reuse existing integration points such as G2B and attachment/RFP parsing where applicable

Do not create:
- a second document system
- a second project system
- a second approval workflow
- a second storage model without explicit need
- a standalone side-app unless explicitly requested

### 8.2 Keep deterministic logic separate from generated prose

For any decisioning or analysis feature:
- prefer deterministic validation, normalization, and scoring first
- use LLM generation to explain, summarize, draft, or transform
- do not make model prose the sole source of truth when structured logic exists

### 8.3 Preserve provider abstraction

- Keep provider-specific behavior inside provider implementations or provider-facing service layers.
- Do not spread provider branching across routers.
- `mock` mode must remain safe for local and CI use.

### 8.4 Preserve storage abstraction

- Keep local and S3 support compatible.
- Do not couple core product logic tightly to only one storage backend.

### 8.5 Additive rollout

When introducing substantial new capability:
- prefer feature flags
- prefer project-scoped rollout before platform-wide redesign
- prefer backward-compatible schema and API extensions

---

## 9) Do-not rules

Do NOT:
- add new code to deprecated or legacy provider layers
- modify or revive legacy storage paths such as deprecated file-repo code without explicit instruction
- duplicate existing config helpers such as enable/disable utility functions when a shared config helper already exists
- call `os.getenv(...)` directly inside route handlers unless there is a compelling local-only reason
- top-level import `boto3` in modules where lazy import is the established pattern
- replace real filesystem tests with excessive mocking when `tmp_path` or equivalent repository testing patterns are available
- create external-input request models without strict validation unless the task explicitly needs permissive parsing
- hardcode long prompt strings in multiple places
- build a parallel templating pipeline when the bundle/template system already exists
- bypass auth, tenant isolation, audit, or approval expectations
- broaden scope beyond the current task or milestone

---

## 10) Validation and definition of done

A change is not done just because the code compiles.

Default completion checklist:
1. The requested behavior is implemented or the bug is fixed.
2. Existing platform flows are not broken.
3. Relevant tests are added or updated.
4. Targeted tests for changed areas are run.
5. `pytest tests/ -q` passes unless the repo/task explicitly calls for a narrower validation scope.
6. If applicable, smoke scripts for touched flows are run.
7. If applicable, lint/type-check commands already used by the repo are run.
8. `mock` provider behavior still works for non-live workflows.
9. Storage abstraction behavior is preserved.
10. Any task-specific status/spec document is updated.

When a change touches:
- deployment or infra behavior → run the appropriate deployment/smoke validation
- storage behavior → validate both logic and persistence paths
- provider behavior → validate `mock` plus the affected provider path when credentials are available
- API contracts → verify route behavior and backward compatibility
- bundle generation → verify generation, export, and any downstream handoff paths

If validation fails, repair first.
Do not continue expanding scope on top of a broken baseline.

---

## 11) Tests

Use the repository’s real testing patterns.

General expectations:
- prefer targeted tests plus a repository-wide safety pass
- use fixtures and golden/snapshot patterns where the repo already uses them
- keep tests deterministic in default/mock mode
- reserve live/provider tests for explicit cases with credentials configured

When adding a new feature:
- add tests for structured data contracts
- add tests for service behavior
- add tests for route behavior if routes are introduced or changed
- add smoke coverage when the feature changes a primary user workflow

---

## 12) Legacy and hot spots

Be careful around these areas:
- deprecated provider paths
- deprecated file-repo style storage code
- duplicated config helpers
- old architectural seams left for backward compatibility
- production-mode behavior such as docs/openapi disablement
- multi-tenant and auth-sensitive endpoints
- ops and audit paths

If you are unsure whether a path is current or legacy, inspect usage first.

---

## 13) Security and operational expectations

- Preserve authentication and tenant isolation.
- Preserve auditability for sensitive actions.
- Do not expose secrets in logs or generated artifacts.
- Keep production-safe behavior intact.
- Preserve request id and observability metadata for operational troubleshooting.
- Avoid introducing unaudited external dependencies unless the task clearly justifies them.

---

## 14) Active initiative — Public Procurement Go/No-Go Copilot

When a task mentions procurement, G2B, bid decision, go/no-go, bid readiness, RFP analysis handoff, or `bid_decision_kr`, treat the following as the active initiative.

### 14.1 Task-level source of truth

When these files exist, read them before making changes:
- `docs/specs/public_procurement_copilot/PRD.md`
- `docs/specs/public_procurement_copilot/PLAN.md`
- `docs/specs/public_procurement_copilot/IMPLEMENT.md`
- `docs/specs/public_procurement_copilot/STATUS.md`

Current repository state:
- the initial milestone plan is complete
- project-detail procurement UI, structured decision state, `bid_decision_kr`, and downstream handoff are implemented
- `Decision Council v1` now exists as a project-scoped, procurement-only pre-generation step for `bid_decision_kr` and `proposal_kr`
- latest closeout and rollout hardening status lives in `docs/specs/public_procurement_copilot/STATUS.md`
- new procurement work should be treated as follow-up tuning or extension work, not as incomplete baseline implementation

### 14.2 Scope rules

Build this capability **inside DecisionDoc AI**.

Do not create:
- a standalone procurement app
- a second document system
- a second project/workspace concept
- a parallel approval or export flow

Reuse existing:
- project/workspace flows
- document generation and export flows
- bundle registry
- knowledge documents
- G2B integration
- attachment / RFP parsing
- approval / share / history / audit
- evaluation and smoke patterns

### 14.3 Decision policy

Recommendation values must be:
- `GO`
- `CONDITIONAL_GO`
- `NO_GO`

Rules:
- deterministic hard filters run before model-generated narrative
- hard-fail conditions may force `NO_GO`
- `CONDITIONAL_GO` is only valid when the missing items are realistically remediable before the bid deadline
- human approval remains the final authority

### 14.4 Checklist policy

The bid-readiness checklist must exist in both:
- structured machine-readable form
- human-readable document form

### 14.5 Integration expectations

Prefer:
- project-scoped integration
- reuse of current bundle and export flows
- reuse of structured metadata for downstream handoff

Avoid:
- provider logic in routers
- prose-only decision logic without structured backing data
- destructive schema changes
- broad UI redesign for v1

### 14.6 Rollout and validation

Prefer additive rollout behind:
- `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`

When extending this area, work milestone-by-milestone if a plan/status file exists for the follow-up task.

For follow-up milestones or significant changes:
- run targeted validation
- run `pytest tests/ -q`
- update the relevant `STATUS.md`
- stop if validation fails

### 14.7 Decision Council v1

Current proposal-first slice:
- procurement/G2B projects only
- API-first
- deterministic synthesis only
- one canonical latest council session per `project_id + use_case + target_bundle_type`
- the stored canonical council session remains keyed to `target_bundle_type=bid_decision_kr`
- the same council handoff is reused for both `bid_decision_kr` and `proposal_kr` generation
- stored council sessions are treated as historical artifacts until they are revalidated against the current procurement record
- `GET /projects/{project_id}/decision-council` now returns explicit procurement-binding metadata so callers can distinguish:
  - current council handoff
  - stale council handoff that must be rerun before `bid_decision_kr` or `proposal_kr`
  - `supported_bundle_types=["bid_decision_kr","proposal_kr"]`
- stale council responses now also expose the source council baseline and current procurement drift summary:
  - source recommendation / missing-data / checklist counts at council run time
  - current recommendation / missing-data / checklist counts at read time
  - source council timestamp vs current procurement `updated_at` so callers can see when the council became stale
- generation metadata now distinguishes:
  - `decision_council_handoff_used=true` when the latest council handoff was actually injected
  - `decision_council_handoff_used=false` plus `decision_council_handoff_skipped_reason=stale_procurement_context` when a saved council session exists but was skipped because current procurement state no longer matches it
  - `decision_council_target_bundle=bid_decision_kr` for the canonical stored session source
  - `decision_council_applied_bundle` for the actual current generation target (`bid_decision_kr` or `proposal_kr`)

Current routes:
- `POST /projects/{project_id}/decision-council/run`
- `GET /projects/{project_id}/decision-council`

Local manual verification:
- fastest path: run the all-in-one local launcher on a fresh `DATA_DIR`

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py
```

- default behavior:
  - starts the app on `http://127.0.0.1:8765`
  - seeds one deterministic stale-share demo with the same council session linked to `bid_decision_kr` and `proposal_kr`
  - makes the stale public share target `proposal_kr` so the Decision Council v1 proposal-first path is directly visible
  - verifies the live app against that seeded state
  - writes `/tmp/decisiondoc-stale-share-demo/procurement-stale-share-demo.json`
  - keeps the server running for manual checks until `Ctrl-C`
- optional browser assist:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --open-browser
```

- this opens:
  - the focused internal stale-share review URL
  - the exact public `/shared/{id}` URL
- optional browser playtest:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --playtest-ui --exit-after-verify
```

- this headless Playwright helper is useful for local debugging and unit-covered flow checks:
  - logs in with the seeded admin account
  - opens the stale-share review from the authenticated app shell for a more deterministic browser path
  - if that flow still loses state, it retries through re-login and modal-visibility fallbacks instead of failing immediately
  - verifies the stale `proposal_kr` review card, the Decision Council panel, the disabled proposal regenerate CTA, and the public `/shared/{id}` warning
- current note:
  - the local live `--playtest-ui` path is now green in this workspace and can be used as the fast browser gate for the seeded stale-share demo
  - `--open-browser` is still useful when you want to inspect the focused review surface and public share page manually after the automated browser pass
- visual debug path:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --playtest-ui --playtest-headed --open-browser
```

- CI-style quick check:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --port 8876 --data-dir /tmp/decisiondoc-stale-share-demo-ci --exit-after-verify
```

Local procurement live smoke when G2B env is available:

```bash
G2B_API_KEY=... \
JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars \
.venv/bin/python scripts/run_local_procurement_smoke.py
```

Env-file path:

```bash
cp scripts/local_procurement_smoke.env.example /tmp/local_procurement_smoke.env
$EDITOR /tmp/local_procurement_smoke.env
JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars \
.venv/bin/python scripts/run_local_procurement_smoke.py --env-file /tmp/local_procurement_smoke.env
```

- this helper:
  - starts a fresh local app with procurement copilot enabled
  - injects a local API key and ops key for the smoke lane
  - runs `scripts/smoke.py` with `SMOKE_INCLUDE_PROCUREMENT=1`
  - uses `SMOKE_PROCUREMENT_URL_OR_NUMBER` when provided, but can auto-discover a recent live G2B opportunity when only `G2B_API_KEY` is configured
- optional:
  - add `--keep-running` if you want the local app to stay up after the smoke pass
  - set `PROCUREMENT_SMOKE_USERNAME` / `PROCUREMENT_SMOKE_PASSWORD` when the target tenant already has users
  - keep the inline `JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars` prefix on the file-based path; that is the validated local launch form in this workspace
  - the runner defaults `JWT_SECRET_KEY` to a validated local secret; override it in the current shell or the env file only when you need a different local auth context
  - run `./.venv/bin/python scripts/run_local_procurement_smoke.py --preflight` to see which required env is still missing and print the exact suggested command
  - run `./.venv/bin/python scripts/run_local_procurement_smoke.py --print-env-template` for a copy-paste export block
  - pass `--env-file /path/to/local_procurement_smoke.env` to the Python runner together with the inline `JWT_SECRET_KEY=...` prefix

Deployed stage procurement live smoke:

```bash
cp scripts/stage_procurement_smoke.env.example /tmp/stage_procurement_smoke.env
$EDITOR /tmp/stage_procurement_smoke.env
.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.env --preflight
.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.env
```

- this helper:
  - does not boot a local app
  - runs the existing `scripts/smoke.py` procurement lane against an already deployed `SMOKE_BASE_URL`
  - keeps the current stage contract explicit: `SMOKE_BASE_URL`, `SMOKE_API_KEY`, and `G2B_API_KEY`
  - treats `SMOKE_PROCUREMENT_URL_OR_NUMBER` as a preferred stable fixture, not a hard requirement
- optional:
  - set `SMOKE_OPS_KEY` if you want the remediation summary path to prefer the ops-key route on the deployed environment
  - set `SMOKE_TENANT_ID`, `PROCUREMENT_SMOKE_USERNAME`, and `PROCUREMENT_SMOKE_PASSWORD` when the stage tenant is non-`system` or already has users
  - run `./.venv/bin/python scripts/run_stage_procurement_smoke.py --print-env-template` for a copy-paste export block when you do not want to edit a file first

GitHub Actions env to stage smoke env:

```bash
.venv/bin/python scripts/export_stage_procurement_smoke_env.py \
  --stage dev \
  --env-file .github-actions.env \
  --base-url https://your-dev-stage.example.com \
  --output /tmp/stage_procurement_smoke.dev.env

.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.dev.env --preflight
.venv/bin/python scripts/run_stage_procurement_smoke.py --env-file /tmp/stage_procurement_smoke.dev.env
```

- this helper maps stage-scoped GitHub Actions values into the exact env names expected by `run_stage_procurement_smoke.py`
- it reuses:
  - `DECISIONDOC_API_KEY` -> `SMOKE_API_KEY`
  - `DECISIONDOC_OPS_KEY` -> `SMOKE_OPS_KEY`
  - `G2B_API_KEY_<STAGE>` -> `G2B_API_KEY`
  - `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` -> `SMOKE_PROCUREMENT_URL_OR_NUMBER` when a stable known target is available
  - `PROCUREMENT_SMOKE_TENANT_ID_<STAGE>` / `PROCUREMENT_SMOKE_USERNAME_<STAGE>` / `PROCUREMENT_SMOKE_PASSWORD_<STAGE>` -> deployed smoke login context
- `check-github-actions-config.sh --procurement-smoke` and `deploy-smoke` now require `G2B_API_KEY_<STAGE>` but only treat `PROCUREMENT_SMOKE_URL_OR_NUMBER_<STAGE>` as optional stable fixture input
- only `--base-url` stays explicit because the deployed endpoint is resolved outside the repository env scaffold

If AWS CLI credentials already point at the target account, you can skip manual `base_url` lookup and resolve it from the stage stack output:

```bash
.venv/bin/python scripts/run_stage_procurement_smoke.py \
  --github-actions-env-file .github-actions.env \
  --stage dev \
  --resolve-base-url-from-stack \
  --preflight

.venv/bin/python scripts/run_stage_procurement_smoke.py \
  --github-actions-env-file .github-actions.env \
  --stage dev \
  --resolve-base-url-from-stack
```

- default stack name:
  - `decisiondoc-ai-dev`
  - `decisiondoc-ai-prod`
- optional:
  - pass `--stack-name decisiondoc-ai-prod-blue` when the deployed stack name differs from the default convention
  - pass `--aws-region ap-northeast-2` when you do not want to rely on `AWS_REGION` from `.github-actions.env` or the current shell
- this path internally reuses the exporter logic, so the older `export_stage_procurement_smoke_env.py -> run_stage_procurement_smoke.py` two-step flow is still available when you want a persistent generated env file

- manual path when you want separate control over server, seed, and verify:
- use a fresh empty `DATA_DIR`; the demo seed script intentionally refuses an existing directory because append-only audit/share state would otherwise make the stale-share counts noisy
- start the app on the same port already used by `.claude/launch.json`

```bash
DEMO_DIR=/tmp/decisiondoc-stale-share-demo
DATA_DIR="$DEMO_DIR" DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=1 .venv/bin/uvicorn app.main:app --port 8765 --reload
```

- in a second shell, seed one deterministic stale-share demo:

```bash
DEMO_DIR=/tmp/decisiondoc-stale-share-demo
DATA_DIR="$DEMO_DIR" .venv/bin/python scripts/seed_procurement_stale_share_demo.py --data-dir "$DEMO_DIR" --base-url http://127.0.0.1:8765
```

- once seeded, run the narrow verifier:

```bash
.venv/bin/python scripts/check_procurement_stale_share_demo.py --base-url http://127.0.0.1:8765
```

- the script prints:
  - seeded admin credentials
  - focused internal stale-share review URL
  - tenant-wide stale-share review URL
  - exact public `/shared/{id}` URL
  - shared bundle id and both linked project document ids
- the verifier checks:
  - seeded admin login works
  - locations overview exposes active stale-share risk
  - focused procurement summary resolves the same stale share
  - the top stale share is the council-backed `proposal_kr` document
  - latest Decision Council is marked stale against current procurement
  - the public `/shared/{id}` page still renders the stale warning
- manual click-path after login:
  - open the focused review URL and confirm the procurement summary lands on `share.create` stale-share review with the seeded project focused
  - switch to locations overview and confirm the top risk card shows stale public exposure plus `공유 링크 열기`, `공유 링크 복사`, `공유 링크 비활성화`, `위험 문서 review`, and review-link actions
  - open the printed public share URL, then revoke it from the card or modal and confirm the same `/shared/{id}` URL becomes `404`

Current UI expectation:
- reuse the existing project-detail procurement panel
- accept a user goal before council-assisted `bid_decision_kr` / `proposal_kr` generation
- show structured role opinions, risks, disagreements, and recommended direction
- show when the latest saved council is stale relative to the current procurement recommendation/checklist, and block council-assisted generation until rerun
- mark council-backed `bid_decision_kr` and `proposal_kr` rows in the existing project document list as:
  - `현재 council 기준`
  - `이전 council revision`
  - `현재 procurement 대비 이전 council 기준`
- expose the same document freshness contract from `GET /projects/{project_id}` for council-backed `bid_decision_kr` / `proposal_kr` rows:
  - `decision_council_document_status`
  - `decision_council_document_status_tone`
  - `decision_council_document_status_copy`
  - `decision_council_document_status_summary`
- stale council-backed `bid_decision_kr` / `proposal_kr` rows now also:
  - show a follow-up CTA (`Council 다시 실행`, `최신 기준으로 재생성`, or `현재 council 확인`)
  - warn before `결재 요청` or `공유` continues on an outdated council-backed document
  - keep the same outdated-state warning visible inside the approval-request modal, with a direct follow-up CTA back to the relevant council action
  - keep the same outdated-state warning visible inside the share-link modal for stale council-backed project documents
  - carry the same outdated-state warning into the public shared-document page when a stale council-backed project document is shared
- `share.create` audit entries now also preserve stale council freshness metadata when a council-backed project document is shared, so operators can trace whether an external share started from a current or outdated council basis
- admin procurement quality summary now treats stale council-backed `share.create` as a reviewable activity signal, so operators can see outdated external shares in the same recent-events/activity-filter surface instead of digging through raw audit logs
- admin procurement quality summary now also exposes an `외부 공유 review` preset that jumps straight to stale external share activity using the existing activity-filter state model
- admin procurement quality summary now also derives an `외부 공유 재확인 queue` from stale council-backed external shares, so operators can review the latest outdated public shares by project/document, latest sharer, and stale-share count without opening raw audit logs
- the preset label now follows unique queue count, while the queue header keeps raw stale `share.create` event volume as a separate context metric
- stale external share queue items now also expose live share-link state (`share_id`, public `share_url`, active/inactive, access count, expiry) and a direct `공유 링크 열기` CTA, so operators can inspect the current public link without leaving the existing review loop
- the same stale external share surfaces now also expose `공유 링크 복사`, which copies the exact public `/shared/{id}` URL for incident follow-up or operator handoff without leaving the queue
- the stale external share queue now prioritizes still-active public links first and exposes active/inactive/missing-record counts in the queue header, so operators can focus on live external exposure before historical noise
- stale external share queue items now also show the latest public access timestamp when available, so operators can tell whether a stale public link is merely still active or has been opened recently
- among active stale links, the queue now lifts `최근 public 열람 있음` items ahead of untouched links and shows accessed-vs-unaccessed counts in the header, so operators can review externally-seen stale documents before dormant exposure
- when any active stale public link remains, the procurement summary modal now raises a top-level exposure alert with an `외부 공유 review 열기` CTA, so operators can jump into stale-share triage without first finding the preset bar
- the locations overview card now also pulls a compact procurement stale-share risk snapshot via `/admin/locations?include_procurement=1` and shows a direct `외부 공유 review` CTA when active stale public exposure remains, so operators can jump into stale-share triage before opening the full modal
- that locations overview snapshot is now built through a dedicated stale-share aggregation path instead of re-running the full tenant procurement summary per card, so the overview keeps the same contract with lower backend work
- the same locations overview now sorts cards with active stale public exposure ahead of normal tenants, and among risky tenants lifts recently accessed public stale links first so urgent exposure is visible before operators scan the whole grid
- the same locations overview card now also surfaces the top stale shared document and direct `공유 링크 열기` / `공유 링크 복사` actions, so operators can inspect or hand off the exact public URL without entering the modal first
- the same card now also shows who last created that stale external share, when it happened, and how many stale-share events accumulated for that document, so incident follow-up does not require opening the modal first
- the same card now also exposes `외부 공유 review 링크`, which copies the tenant-wide stale-share review URL with the existing `share.create` activity filter preserved for operator handoff
- active stale public links can now be revoked directly from the locations overview card and the stale-share review modal by reusing the existing `DELETE /share/{share_id}` flow, and admin operators can revoke links even when another user originally created them
- the same card now also exposes `위험 문서 review`, which opens the procurement summary already focused on that exact stale shared project while keeping the existing `share.create` review filter active
- the same card now also exposes `위험 문서 review 링크`, which copies the exact internal procurement-summary review URL with tenant, focused project, and stale-share activity filter preserved for operator handoff
- `scripts/smoke.py` now also validates the proposal-first lane:
  - `GO` / `CONDITIONAL_GO` recommendation이면 council-backed `proposal_kr` generation과 provenance를 확인
  - `NO_GO` recommendation이면 override 이후 retry된 `proposal_kr` provenance를 확인
- preserve provenance through project docs, audit, approval/share/export

Do not extend this into:
- generic multi-agent chat
- a separate orchestration shell
- a new approval or export flow

### 14.8 Downstream handoff target

When implemented, the procurement decision flow should hand off cleanly to existing document workflows such as:
- `rfp_analysis_kr`
- `proposal_kr`
- `performance_plan_kr`

Preserve structured context so users do not have to re-enter the same opportunity, fit, risk, and checklist information multiple times.

---

## 15) Final rule

Keep this file practical and durable.

If a rule here repeatedly causes confusion because the repository has changed:
- update this file
- keep it shorter, clearer, and closer to reality
- move task-specific detail into task-specific docs instead of bloating root guidance

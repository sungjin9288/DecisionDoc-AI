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

---

## 5) Core commands

Use the real repository commands if they differ, but these are the default expectations.

### Local setup

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

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
```

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
### 14.7 Downstream handoff target

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

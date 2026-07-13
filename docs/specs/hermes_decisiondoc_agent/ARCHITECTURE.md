# DecisionDoc DocumentOps Agent Architecture

## Goal

Build an AI layer for document generation and policy planning that can produce public-sector proposals, decision documents, PPT/DOCX reports, and review-ready planning artifacts with traceable evidence, QA gates, and training data capture.

This should develop Hermes-inspired capabilities inside DecisionDoc instead of replacing DecisionDoc with Hermes.

## Target Platform Shape

```text
project
  -> knowledge
  -> document_ops_agent
  -> generation
  -> export
  -> approval/share
  -> audit
  -> training/evaluation
```

## Current Components

### 1. DocumentOps Agent Service

Current module:

```text
app/agents/document_ops_agent.py
```

Responsibilities:

- Select a task skill.
- Build a prompt from the supplied requirements, project context, and source references.
- Generate structured drafts through existing providers.
- Run self-review and QA checks.
- Return a structured draft and optionally write a redacted trajectory record.

The agent resolves a DecisionDoc provider through the existing capability factory; it does not call
external model SDKs directly.

### 2. Skill Registry

Current modules:

```text
app/agents/skills/
app/agents/skill_registry.py
```

Current curated skills:

| Skill | Purpose |
|---|---|
| `policy-planning` | Build policy logic, implementation pathway, governance, and risk structure |
| `evidence-gap-checker` | Separate confirmed, assumed, and TODO claims |
| `decision-brief-builder` | Produce executive decision documents and recommendation memos |
| `develop-document-improver` | Critique an existing draft and return concrete revision tasks and an improved draft |

Skills should be data, not arbitrary executable code.

### 3. Trajectory Store

Current facade and implementation package:

```text
app/storage/trajectory_store.py
app/storage/trajectory/
```

Reason:

`FineTuneStore` currently stores OpenAI message records. That is useful for SFT but too thin for agent learning because it loses the planning, evidence, critique, QA, and revision process.

Trajectory records preserve:

- user task and constraints
- selected skill and skill version
- context sources
- plan
- draft output
- critique and revision tasks
- QA result
- human feedback
- review and export metadata

### 4. Evaluation Harness

Current module:

```text
app/evals/document_ops/
```

Hard gates:

- forbidden expression present
- missing required sections
- unsupported statistics or invented institution
- privacy/security/governance omissions
- wrong document type wording
- export artifact missing
- deterministic mock provider broken

Rubric dimensions:

- public-sector persuasiveness
- policy logic
- evidence grounding
- implementation specificity
- operational governance
- document density and readability
- export readiness

### 5. Optional Hermes Sidecar

Future optional module:

```text
app/providers/hermes_sidecar_provider.py
```

Use only for local research:

- behind `HERMES_SIDECAR_ENABLED=false` by default
- no production route dependency
- no tenant document access by default
- no terminal/browser/remote execution tools unless separately approved

## Request Flow

```text
Client request
  -> FastAPI route
  -> DocumentOpsService
  -> DocumentOpsAgent
  -> SkillRegistry
  -> configured Provider
  -> structured draft
  -> QA/Eval gates
  -> tenant-scoped TrajectoryStore
  -> human review and SFT export
```

## Training Flow

```text
Human-reviewed successful work
  -> TrajectoryStore
  -> QA scoring
  -> Export as SFT JSONL
  -> Dataset freeze
  -> Dry-run approval, readiness, and audit records
  -> Disabled provider-adapter rehearsal
```

Provider-specific dataset upload, fine-tuning, evaluation, model promotion, and capability routing
remain outside the implemented execution boundary and require separate approval.

## Security Boundaries

- Tenant/project documents must not be sent to external services unless the selected provider and tenant settings allow it.
- Skills are curated first-party text assets.
- External repo skills are reference material only until reviewed.
- Terminal/browser/remote execution is disabled for production document generation.
- Every generated claim that looks factual must be either confirmed, assumed, or TODO.
- Audit must record skill version, provider, model, context IDs, and QA result.

## Integration Principle

Hermes should influence the agent design, not own the DecisionDoc runtime. DecisionDoc remains the source of truth for projects, knowledge, generation workflows, approvals, exports, audit, providers, and model registry.

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

## Proposed Components

### 1. DocumentOps Agent Service

Future module:

```text
app/agents/document_ops_agent.py
```

Responsibilities:

- Select a task skill.
- Build an evidence-grounded plan.
- Retrieve project and knowledge context.
- Generate structured drafts through existing providers.
- Run self-review and QA checks.
- Produce artifact-ready payloads for PPTX/DOCX/report services.
- Write trajectory records for training.

The service should call DecisionDoc providers through `ProviderFactory`; it should not call external model SDKs directly.

### 2. Skill Registry

Future module:

```text
app/agents/skills/
```

Initial curated skills:

| Skill | Purpose |
|---|---|
| `proposal-intake` | Convert raw RFP/user notes into scope, audience, constraints, and deliverables |
| `policy-planning` | Build policy logic, implementation pathway, governance, and risk structure |
| `public-sector-style` | Enforce public-sector consulting tone and non-exaggerated wording |
| `evidence-gap-checker` | Separate confirmed, assumed, and TODO claims |
| `forbidden-expression-checker` | Catch banned terms and unsafe claims |
| `deckops-native-ppt` | Convert slide spec into PPT-ready layout and content blocks |
| `decision-brief-builder` | Produce executive decision documents and recommendation memos |
| `red-team-review` | Challenge persuasiveness, evidence gaps, security/privacy, and operational feasibility |
| `export-readiness-qa` | Check that PPTX/DOCX/PDF deliverables are complete and shareable |

Skills should be data, not arbitrary executable code.

### 3. Trajectory Store

Future module:

```text
app/storage/trajectory_store.py
```

Reason:

`FineTuneStore` currently stores OpenAI message records. That is useful for SFT but too thin for agent learning because it loses the planning, evidence, critique, QA, and revision process.

Trajectory records should preserve:

- user task and constraints
- selected skill and skill version
- context sources
- plan
- tool trace summary
- draft output
- critique/review findings
- revised output
- QA result
- human feedback
- export status
- safety flags

### 4. Evaluation Harness

Future module:

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
  -> GenerationService
  -> DocumentOpsAgent
  -> SkillRegistry
  -> Project/Knowledge stores
  -> ProviderFactory
  -> Draft artifact payload
  -> QA/Eval gates
  -> PPTX/DOCX/PDF service
  -> Audit + TrajectoryStore
```

## Training Flow

```text
Human-reviewed successful work
  -> TrajectoryStore
  -> QA scoring
  -> Export as SFT JSONL
  -> FineTuneStore / FineTuneOrchestrator
  -> Provider-specific fine-tuning
  -> ModelRegistry promotion
  -> Capability-specific provider routing
```

## Security Boundaries

- Tenant/project documents must not be sent to external services unless the selected provider and tenant settings allow it.
- Skills are curated first-party text assets.
- External repo skills are reference material only until reviewed.
- Terminal/browser/remote execution is disabled for production document generation.
- Every generated claim that looks factual must be either confirmed, assumed, or TODO.
- Audit must record skill version, provider, model, context IDs, and QA result.

## Integration Principle

Hermes should influence the agent design, not own the DecisionDoc runtime. DecisionDoc remains the source of truth for projects, knowledge, generation workflows, approvals, exports, audit, providers, and model registry.

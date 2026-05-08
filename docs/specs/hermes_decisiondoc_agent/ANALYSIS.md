# Hermes Agent Applicability Analysis for DecisionDoc

## Decision

Hermes Agent should be treated as a reference architecture and research prototype source, not as a direct production dependency in DecisionDoc yet.

The right path is to build a DecisionDoc-native DocumentOps/PolicyOps agent layer that borrows the useful Hermes concepts: skills, tool-using agent loops, trajectory capture, evaluator/reward design, and optional local sidecar experimentation. This keeps DecisionDoc's existing provider abstraction, mock mode, export pipeline, project model, auditability, and deployment shape intact.

## Source Reviewed

- Hermes Agent repository: `/Users/sungjin/dev/research/hermes-agent`
- Hermes commit reviewed: `49c3c2e`
- Hermes license: MIT
- DecisionDoc repository: `/Users/sungjin/dev/personal/DecisionDoc-AI`
- DecisionDoc integration precedents:
  - `docs/specs/external_repo_integration/ANALYSIS_20260427.md`
  - `docs/specs/external_repo_integration/ANALYSIS_20260428.md`

## Hermes Capabilities Relevant to DecisionDoc

| Area | Hermes capability | DecisionDoc fit | Recommendation |
|---|---|---:|---|
| Agent loop | OpenAI-style messages/tools loop, tool call parsing, delegation | High | Rebuild the pattern inside DecisionDoc rather than importing runtime wholesale |
| Skills | Reusable procedural instructions and slash-command style skill loading | High | Create curated DecisionDoc skills for proposal intake, policy planning, deck QA, evidence checks |
| Trajectories | Research-oriented trajectory generation for self-improvement | High | Add trajectory capture beside existing fine-tune examples |
| RL/eval environments | Atropos-style environments and reward functions | Medium | Use as long-term evaluation/training reference only |
| Memory/session | Agent state, history, retrieval, session context | Medium | Map to DecisionDoc project/knowledge/workflow/audit stores |
| Browser/web/tools | Rich external tool ecosystem | Low for production | Keep disabled unless isolated and tenant-approved |
| Cron/automation | Scheduled agent work | Medium later | Useful after stable document QA workflows exist |
| Remote execution backends | Modal, Daytona, Vercel, terminal backends | Low now | Do not enable in production until sandbox/security review |

## Why Direct Integration Is Not Recommended Now

Hermes is an agent runtime with broad tool access and optional extras for remote execution, web browsing, messaging, voice, and RL research. DecisionDoc is a document generation and collaboration platform with provider routing, exports, project storage, approvals, audit, and deterministic mock mode.

Directly importing Hermes as a production dependency would create avoidable risks:

- Dependency blast radius: Hermes extras pull many runtime packages unrelated to core DecisionDoc document generation.
- Security surface: terminal, browser, remote execution, messaging, and gateway features need isolation before tenant documents can be processed.
- Architectural mismatch: DecisionDoc already has `Provider`, `GenerationService`, `FineTuneStore`, `ModelRegistry`, project stores, and export services.
- Testing risk: deterministic `mock` provider behavior must remain stable.
- Data governance risk: proposal/RFP/company documents can contain sensitive materials and cannot be sent to external services by default.

## What To Port Conceptually

1. Skill registry
   - Versioned skill documents for proposal, policy, deck, evidence, and red-team tasks.
   - Skills must be curated first-party content, not untrusted external imports.

2. Agent loop pattern
   - Plan, retrieve evidence, draft, critique, revise, package, QA.
   - Route LLM calls through existing DecisionDoc providers.

3. Trajectory capture
   - Store task input, selected skill, tool trace summary, draft, critique, final artifact, human feedback, QA result.
   - Export both OpenAI SFT-style messages and richer Hermes-style trajectory JSONL.

4. Evaluation harness
   - Hard gates for forbidden terms, unsupported claims, privacy/security omissions, and export-readiness.
   - Rubric scoring for policy logic, persuasion, evidence grounding, public-sector tone, and implementation clarity.

5. Optional Hermes sidecar
   - Use only as a local research sandbox behind an environment flag.
   - No production API path should depend on it until security and dependency review pass.

## Immediate DecisionDoc Opportunity

DecisionDoc already contains the right seams:

- `app/services/generation_service.py` can remain the orchestration boundary.
- `app/providers/base.py` and `app/providers/factory.py` keep model calls provider-neutral.
- `app/storage/finetune_store.py` already exports OpenAI-style fine-tuning records.
- `app/services/finetune_orchestrator.py` can promote fine-tuned OpenAI models through the existing registry flow.
- Existing document/export services can remain artifact producers.

The missing layer is not a raw model. It is a governed DocumentOps agent that produces higher-quality training examples and applies proposal-specific QA before artifacts are accepted.

## Recommended Status

- Adopt now: Hermes concepts for skills, trajectories, evaluation, and agent loop design.
- PoC first: local DocumentOps agent service inside DecisionDoc.
- Reference only: Hermes RL/Atropos training environments.
- Hold: Hermes terminal/browser/remote execution in production.
- Avoid direct integration now: installing Hermes as a production dependency or exposing Hermes tool runtime to tenant documents.

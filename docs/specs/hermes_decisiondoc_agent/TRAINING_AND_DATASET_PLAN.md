# Training and Dataset Plan

## Objective

Develop a document-generation and policy-planning AI for DecisionDoc by collecting high-quality reviewed work as training data, then using the existing fine-tuning and model registry path for promotion.

The first model target should not be a general chatbot. It should be a DocumentOps assistant that improves proposal planning, public-sector policy framing, evidence discipline, and artifact-ready structure.

## Dataset Types

### 1. SFT Message Records

Use existing `FineTuneStore` style records for provider-compatible supervised fine-tuning.

Minimum message shape:

```json
{
  "messages": [
    {"role": "system", "content": "You are DecisionDoc DocumentOps..."},
    {"role": "user", "content": "Create a public-sector proposal plan..."},
    {"role": "assistant", "content": "Structured final answer..."}
  ],
  "metadata": {
    "task_type": "proposal_plan",
    "quality_score": 0.92,
    "skill": "policy-planning",
    "skill_version": "0.1.0"
  }
}
```

This can feed existing OpenAI-oriented fine-tuning infrastructure after export.

### 2. Rich Trajectory Records

Add a richer internal format before compressing to SFT messages.

Recommended shape:

```json
{
  "trajectory_id": "trj_...",
  "project_id": "proj_...",
  "task_type": "proposal_deck_planning",
  "input": {
    "user_request": "...",
    "requirements": ["..."],
    "source_documents": ["doc_...", "deck_..."]
  },
  "skill": {
    "name": "deckops-native-ppt",
    "version": "0.1.0"
  },
  "plan": ["..."],
  "context_summary": {
    "confirmed": ["..."],
    "assumed": ["..."],
    "todo": ["..."]
  },
  "tool_trace_summary": [
    {"tool": "knowledge_search", "purpose": "find RFP constraints"},
    {"tool": "export_qa", "purpose": "check forbidden terms"}
  ],
  "draft_output": "...",
  "critique": {
    "issues": ["..."],
    "risk_level": "medium"
  },
  "final_output": "...",
  "qa": {
    "hard_gate_pass": true,
    "scores": {
      "policy_logic": 0.9,
      "evidence_grounding": 0.85,
      "public_sector_tone": 0.95
    }
  },
  "human_feedback": {
    "accepted": true,
    "reviewer": "pm-owner",
    "notes": "...",
    "quality_score": 0.92,
    "review_version": 1,
    "reviewed_at": "2026-07-14T00:00:00+00:00"
  },
  "human_review_history": [],
  "safety_flags": []
}
```

Accepted-only export requires a named reviewer. Repeating the same review preserves its timestamp;
changing a review increments `review_version` and moves the prior feedback into
`human_review_history`. Export metadata records a dataset fingerprint, content SHA-256, and source
trajectory IDs so the same dataset request reuses one artifact and changed inputs create a new one.

## Data Sources

Use only approved project data:

- accepted proposal drafts
- final PPT/DOCX/PDF outputs
- user edits that improved quality
- red-team review notes
- QA reports
- evidence registers
- forbidden expression checks
- project-specific style guides
- approved company profile snippets

Do not train on:

- unreviewed hallucinated drafts
- raw confidential material without redaction/authorization
- external repo docs as if they were client/project examples
- failed outputs unless labeled as negative examples
- screenshots with unverified OCR text as authoritative content

## Labeling Rules

Every training example should include:

- `task_type`
- `document_type`
- `audience`
- `source_confidence`
- `confirmed_claims`
- `assumed_claims`
- `todo_claims`
- `forbidden_terms_scan`
- `privacy_security_scan`
- `human_review_status`
- `quality_score`

## Reward and Evaluation Rubric

Hard fail conditions:

- prohibited words remain in visible/submitted content
- required section missing
- invented statistic, institution, budget, contact, or performance claim
- privacy/security/governance is ignored where required
- document type is wrong
- cost, period, or KPI presented as confirmed when only tentative
- output cannot be exported or audited

Positive scoring:

| Dimension | What good looks like |
|---|---|
| Policy logic | Problem, cause, intervention, operation, and expected effect connect clearly |
| Persuasiveness | Executive can see why the project should be approved |
| Evidence discipline | Claims are confirmed, assumed, or TODO |
| Public-sector tone | Concrete, restrained, non-marketing language |
| Implementation detail | Roles, process, timeline, data, governance, and risk are specified |
| Artifact readiness | Content can become PPT/DOCX with minimal manual rewrite |

## Model Development Phases

### Phase 0.5: Report Quality Correction Gate

- Before any fine-tuning run, create reviewed before/after correction artifacts for real report and proposal outputs.
- Use `docs/specs/report_quality_learning/QUALITY_RUBRIC.md` to score logic, evidence discipline, slide structure, visual design, public-sector tone, export readiness, and learning value.
- Use `docs/specs/report_quality_learning/correction_artifact_template.json` and `validate_correction_artifact.py` to reject weak, unsafe, unreviewed, or non-opt-in samples.
- Keep provider fine-tune API calls, external dataset upload, provider job creation, training execution, and model promotion unauthorized until the correction dataset passes the stop gate.

### Phase 1: Dataset Capture Without Training

- Add trajectory capture for reviewed document work.
- Keep existing model/provider behavior unchanged.
- Export examples for inspection only.

### Phase 2: Small SFT Experiment

- Use existing fine-tune pipeline with a small, high-quality dataset.
- Target narrow tasks first:
  - proposal planning
  - evidence gap review
  - policy logic improvement
  - red-team review

### Phase 3: Evaluation Gate

- Compare base provider vs fine-tuned provider on fixed eval prompts.
- Promote only if hard gates pass and rubric improves.
- Keep `mock` provider deterministic.

### Phase 4: Hermes-Inspired Trajectory Learning

- Convert rich trajectories into training/eval environments.
- Explore Hermes/Atropos style loops outside production runtime.
- Promote only through DecisionDoc `ModelRegistry`.

## Promotion Criteria

A trained model can be made active only when:

- regression eval passes
- forbidden expression scan passes
- evidence discipline improves or remains equal
- mock provider tests are unaffected
- export workflows still pass
- rollback is available through model registry

## Initial Training Target

First fine-tune target:

```text
decisiondoc-documentops-policy-planner
```

Primary tasks:

- turn raw proposal/RFP notes into structured decision documents
- produce public-sector proposal page plans
- identify evidence gaps and unsafe claims
- improve policy logic and governance sections

Do not fine-tune first on visual PPT layout. Layout should remain deterministic service logic plus style templates.

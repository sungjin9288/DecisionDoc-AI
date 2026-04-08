# PRD — Public Procurement Go/No-Go Copilot

## 1. Objective

Add a procurement decision module to DecisionDoc AI for small public-sector consulting firms.

The module must help teams:
1. identify a relevant public opportunity,
2. attach or import the opportunity into a project,
3. evaluate whether the company should pursue it,
4. identify missing bid-readiness items,
5. hand off cleanly into proposal and execution-document workflows.

This feature must live **inside** DecisionDoc AI and reuse the current project, document, knowledge, approval, sharing, export, and evaluation capabilities.

---

## 2. Why this should exist inside DecisionDoc AI

DecisionDoc AI already provides core product surfaces that are directly relevant to this workflow:
- project workspace and document linkage,
- knowledge documents,
- G2B opportunity lookup,
- attachment-based RFP parsing,
- bundle-based document generation,
- export,
- approval / share / history,
- evaluation and operations tooling.

The procurement decision feature should become an integrated upstream stage in the existing document workflow, not a separate standalone product.

Expected product flow:

1. opportunity search or import
2. project-linked procurement decision
3. bid-readiness checklist
4. decision package generation
5. handoff to existing proposal / RFP / performance-plan bundles
6. approval / sharing / audit trail

---

## 3. Primary users

### 3.1 Proposal / Business Development Lead
Needs a fast first-pass answer:
- should we bid,
- what blocks us,
- what must be fixed before drafting begins.

### 3.2 Delivery Lead / PM
Needs to validate:
- delivery capability fit,
- staffing readiness,
- required partner path,
- schedule and deliverable realism.

### 3.3 Executive Approver
Needs:
- clear go / conditional go / no-go recommendation,
- evidence,
- major risks,
- missing internal approvals or qualifications.

---

## 4. Jobs to be done

1. Search or import a public opportunity into a DecisionDoc AI project.
2. Attach RFP or supporting files if available.
3. compare opportunity requirements with company capability profile and project knowledge.
4. produce a recommendation: `GO`, `CONDITIONAL_GO`, or `NO_GO`.
5. show score breakdown and hard-fail reasons.
6. generate a bid-readiness checklist.
7. generate decision-stage documents.
8. hand off reusable structured context into proposal and delivery planning workflows.

---

## 5. Scope

## 5.1 In scope

- G2B opportunity search reuse and project-scoped import
- normalized opportunity record linked to a project
- raw opportunity payload snapshot retention
- capability profile resolution using existing knowledge document mechanisms
- deterministic hard-filter evaluation
- weighted soft-fit scoring
- recommendation summary with evidence and uncertainty notes
- bid-readiness checklist generation
- new decision-stage bundle generation
- structured handoff to existing downstream bundles
- approval / share / history / audit reuse
- evaluation coverage for core decision behavior
- additive rollout behind a feature flag

## 5.2 Out of scope for v1

- automatic bid submission
- competitor intelligence
- advanced bid pricing optimization
- legal opinion automation
- unofficial crawling or scraping
- broad UI redesign
- standalone procurement microservice
- replacement of existing proposal-generation system

---

## 6. Product principles

1. Build inside DecisionDoc AI.
2. Reuse current project and document workflows.
3. Do deterministic checks before LLM narrative.
4. Preserve provider abstraction.
5. Preserve local and S3 storage abstraction.
6. Keep `mock` provider deterministic and testable.
7. Human approval remains final authority.
8. Produce both structured data and human-readable documents.
9. Prefer additive rollout over platform-wide redesign.
10. Preserve auditability.

---

## 7. Inputs

The module may use the following inputs:

- G2B opportunity metadata
- parsed RFP / attachment signals
- project knowledge documents
- tenant or project capability profile documents
- reference project documents
- staffing / partner assumptions
- internal policy notes
- optional user-entered decision notes

### 7.1 Capability profile for v1

v1 should not start by building a large new admin subsystem.

Preferred v1 sources:
1. existing knowledge document designated as company capability profile,
2. project-scoped capability profile document,
3. a generated capability profile template document that users can fill in.

The capability profile should support at least:
- company overview
- service lines
- target public-sector domains
- relevant certifications / licenses
- reference projects
- staffing capabilities
- partner / consortium capability
- preferred budget range
- excluded risk conditions
- preferred delivery types
- internal go/no-go rules if available

---

## 8. Decision model

## 8.1 Recommendation output

The system must output exactly one of:
- `GO`
- `CONDITIONAL_GO`
- `NO_GO`

## 8.2 Hard filters

Hard filters are deterministic checks that can force `NO_GO`.

Initial hard-filter categories:
- mandatory eligibility mismatch
- missing mandatory certification or license
- explicit regional or participation restriction mismatch
- mandatory consortium requirement with no viable partner path
- impossible deadline against internal readiness threshold
- prohibited risk condition
- required deliverable capability clearly unavailable
- mandatory domain experience requirement clearly missing

Hard-filter output must be structured and explainable.

## 8.3 Soft-fit score

The soft-fit score ranges from 0 to 100.

Initial scoring dimensions:
- domain fit
- reference project fit
- staffing readiness
- delivery capability fit
- strategic fit
- profitability / budget fit
- partner readiness
- document readiness
- schedule readiness
- compliance readiness

Rules:
- weights should be configurable
- defaults may be opinionated in v1
- factor-level breakdown must be preserved
- unknown or missing data must be explicit, not silently ignored

## 8.4 Initial threshold policy

Initial defaults:
- `GO`: score >= 75 and no hard-fail
- `CONDITIONAL_GO`: score 55–74, or remediable gaps
- `NO_GO`: score < 55, or any hard-fail

These are initial defaults only and should be easy to tune later.

## 8.5 Conditional-go rule

`CONDITIONAL_GO` is valid only when:
- missing items are remediable before the bid deadline,
- no hard-fail exists,
- the operational burden is still acceptable.

---

## 9. Bid-readiness checklist

The checklist must exist in two forms:
1. structured machine-readable data
2. human-readable document output

Each checklist item should support:
- category
- title
- status (`ready`, `missing`, `warning`, `not_applicable`)
- severity
- evidence
- remediation note
- optional owner
- optional due date

Required checklist categories:
- eligibility and compliance
- certifications and licenses
- domain capability fit
- reference cases and proof points
- staffing and partner readiness
- schedule and deadline readiness
- deliverables and scope clarity
- security / data / infrastructure obligations
- pricing / budget / contract risk
- executive approval / internal readiness

---

## 10. Output artifacts

Add a new bundle:

- `bundle_id = bid_decision_kr`

Initial documents in the bundle:
1. Opportunity Brief
2. Go/No-Go Memo
3. Bid Readiness Checklist
4. Proposal Kickoff Summary

The bundle must:
- use the existing bundle registry conventions,
- flow through existing generation and export paths,
- remain project-linked,
- preserve structured metadata for downstream reuse.

---

## 11. Downstream handoff

If the decision is `GO` or `CONDITIONAL_GO`, the feature should support clean handoff to:
- `rfp_analysis_kr`
- `proposal_kr`
- `performance_plan_kr`

The handoff should reuse structured context rather than forcing users to re-enter:
- opportunity basics
- fit rationale
- risk summary
- missing items
- decision notes
- parsed RFP signals
- readiness checklist highlights

---

## 12. Functional requirements

### FR1. Opportunity intake
- Reuse the existing G2B search capability.
- Support attaching or importing a selected opportunity into a project.
- Allow a project to hold one or more opportunity records, even if v1 operates on a primary opportunity.

### FR2. Source normalization
- Normalize imported opportunity data into a stable internal structure.
- Retain raw source snapshot for audit, debugging, and future reprocessing.

### FR3. RFP and attachment integration
- Reuse existing attachment / RFP parsing flows where available.
- Link parsed signals to the project-scoped procurement decision context.

### FR4. Capability profile resolution
- Resolve capability profile using current knowledge document mechanisms first.
- If missing, support a templated profile document flow.

### FR5. Hard-filter engine
- Evaluate deterministic hard filters before any narrative generation.
- Return explicit fail reasons and supporting evidence.

### FR6. Soft-fit scoring engine
- Compute weighted score with factor-level breakdown.
- Preserve structured intermediate data for later review and evaluation.

### FR7. Recommendation narrative
- Generate a human-readable recommendation summary from structured outputs.
- Include decision, evidence, uncertainty, missing-data notes, and recommended next action.

### FR8. Bid-readiness checklist
- Generate checklist items grouped by required categories.
- Persist checklist in structured form and render it into document form.

### FR9. Decision-stage bundle
- Add and register `bid_decision_kr`.
- Generate all decision-stage documents through existing bundle and export pipelines.

### FR10. Workflow handoff
- Support downstream handoff to proposal and execution bundles using structured context.

### FR11. Approval / share / history / audit
- Reuse existing platform mechanisms rather than creating new ones.
- Keep the decision path traceable and reviewable.

### FR12. Provider abstraction
- Preserve the current provider abstraction.
- `mock` mode must remain deterministic and usable for tests.

### FR13. Storage abstraction
- Preserve the existing local vs S3 storage abstractions.
- Do not couple the new feature to a single storage implementation.

### FR14. Feature flag
- Roll out behind:
  - `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`

### FR15. Evaluation coverage
Add evaluation and regression coverage for:
- hard-filter behavior
- threshold behavior
- structured score integrity
- checklist completeness
- decision bundle generation smoke
- downstream handoff correctness

---

## 13. Non-functional requirements

- additive and backward compatible
- project-linked and audit-friendly
- compatible with Docker and AWS SAM / Lambda modes
- compatible with local filesystem and S3 storage modes
- does not break current document generation flows
- keeps production safety behavior intact
- avoids unnecessary external dependencies
- remains understandable under `mock` provider mode
- preserves tenant isolation and auth expectations

---

## 14. Success criteria for v1

v1 is successful when:
1. a user can move from opportunity search/import to decision package inside one workspace,
2. the recommendation is traceable and reviewable,
3. major bid-readiness gaps are surfaced before proposal drafting begins,
4. the decision package can be exported through current flows,
5. downstream proposal and performance-plan workflows can start with reused context.

---

## 15. Explicit non-goals for v1 execution

During implementation, do not let scope drift into:
- full procurement intelligence platform redesign
- deep pricing engine
- legal automation suite
- competitor intelligence pipeline
- new standalone UI shell
- separate procurement datastore disconnected from project context
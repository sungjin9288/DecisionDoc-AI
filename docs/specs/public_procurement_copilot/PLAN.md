# PLAN — Public Procurement Go/No-Go Copilot

## Execution rule

Do not move to the next milestone until:
1. the current milestone acceptance criteria are met,
2. validation passes,
3. `STATUS.md` is updated.

If validation fails, repair first.
Do not stack new scope on top of a failing baseline.

---

## Milestone 0 — Repository discovery and integration map

### Goal
Map this plan to the real DecisionDoc AI repository before implementation.

### Tasks
- inspect the actual repository for:
  - project/workspace model
  - project documents and document linkage
  - G2B search integration
  - attachment / RFP parsing flow
  - knowledge document flow
  - bundle registry
  - export pipeline
  - approval / share / history / audit behavior
  - provider abstraction
  - storage abstraction
  - eval patterns
  - smoke patterns
- identify the exact files, modules, and extension points
- confirm whether route modules, services, schemas, and persistence follow the assumptions in the PRD
- identify the smallest valid persistence shape for procurement decision state
- identify the correct feature-flag integration point
- update `STATUS.md` with:
  - discovered file map
  - confirmed integration points
  - deviations from assumptions
  - smallest valid plan corrections

### Acceptance criteria
- `STATUS.md` contains a real repository map for this initiative
- the first implementation order is clear
- no broad production logic is added yet

### Validation
- repository inspection only
- no feature code required in this milestone

---

## Milestone 1 — Domain model and persistence shape

### Goal
Create the minimum stable domain model for project-linked procurement decision state.

### Tasks
- add or adapt structured models for:
  - normalized opportunity
  - capability profile reference
  - hard-filter result
  - score breakdown
  - checklist item
  - recommendation
  - source snapshot metadata
- define where the decision state is persisted
- keep persistence additive and backward compatible
- keep the design compatible with current storage abstractions

### Acceptance criteria
- the repository can persist and read a normalized procurement decision payload linked to a project
- raw source snapshot retention path is defined
- no existing project or document flows are broken

### Validation
- add targeted serialization / persistence tests
- run `pytest tests/ -q`

---

## Milestone 2 — Opportunity intake and project attachment

### Goal
Attach G2B opportunities to project context.

### Tasks
- reuse the existing G2B search flow
- add project-scoped import or attach flow only where necessary
- persist normalized opportunity data
- retain raw payload snapshot
- connect existing parsed RFP / attachment signals if already available in project context

### Acceptance criteria
- a project can hold a normalized opportunity record
- a selected opportunity can be attached/imported into project context
- raw payload snapshot is preserved
- retrieval path can access the normalized project opportunity state

### Validation
- add targeted API/service tests for intake and retrieval
- run `pytest tests/ -q`

---

## Milestone 3 — Hard filters and fit scoring

### Goal
Compute deterministic hard-filter results and weighted soft-fit score.

### Tasks
- implement deterministic hard-filter evaluation first
- implement weighted soft-fit scoring with configurable defaults
- return explicit factor breakdown
- expose missing or unknown data instead of hiding it
- preserve structured outputs for evaluation and downstream document generation

### Acceptance criteria
- hard-fail conditions can force `NO_GO`
- score output includes final score and factor breakdown
- recommendation input data exists in structured form before narrative generation
- insufficient-data cases are explicit

### Validation
- add fixtures for:
  - clear GO
  - conditional go
  - hard-fail no-go
  - insufficient-data case
- run targeted tests
- run `pytest tests/ -q`

---

## Milestone 4 — Recommendation narrative and bid-readiness checklist

### Goal
Generate human-readable recommendation content and structured checklist.

### Tasks
- generate recommendation narrative from structured outputs
- generate categorized bid-readiness checklist
- persist checklist as structured data
- render checklist content for document generation
- keep provider abstraction intact
- preserve deterministic mock behavior

### Acceptance criteria
- the system returns:
  - decision
  - evidence
  - missing-data notes
  - remediation notes
  - categorized checklist
- both recommendation and checklist are project-linked
- mock-provider path is deterministic and testable

### Validation
- add targeted tests for checklist structure and provider fallback behavior
- run `pytest tests/ -q`

---

## Milestone 5 — Decision bundle and downstream handoff

### Goal
Generate decision-stage documents and enable structured handoff to downstream bundles.

### Tasks
- add new bundle `bid_decision_kr`
- register the bundle using current bundle registry conventions
- generate:
  - Opportunity Brief
  - Go/No-Go Memo
  - Bid Readiness Checklist
  - Proposal Kickoff Summary
- reuse the current generation / export flow
- add structured handoff path to:
  - `rfp_analysis_kr`
  - `proposal_kr`
  - `performance_plan_kr`

### Acceptance criteria
- decision-stage documents can be generated as project-linked artifacts
- export works through existing mechanisms
- downstream bundles can consume structured context without manual re-entry

### Validation
- add bundle-generation tests
- add handoff-path tests
- run `pytest tests/ -q`

---

## Milestone 6 — UI/API integration, approval, eval, and docs

### Goal
Expose the feature through minimal additive surfaces and finish operational hardening.

### Tasks
- add minimal project-level UI/API integration
- reuse approval / share / history / audit flows
- add feature-flag control
- add eval / regression coverage
- add docs and smoke guidance
- update any relevant operational notes

### Acceptance criteria
- users can reach the new procurement-decision flow from the project workspace
- approval/history/audit expectations are preserved
- the feature can be disabled cleanly with configuration
- `STATUS.md` and initiative docs are updated

### Validation
- add targeted route/UI tests if supported by the repository
- run `pytest tests/ -q`
- run applicable smoke commands already used by the repository
- run any feature-specific smoke path if added

---

## Milestone boundaries

### Explicit non-goals during implementation
- no standalone procurement service
- no auth rewrite
- no storage rewrite
- no provider rewrite
- no second document system
- no second approval workflow
- no broad UI redesign
- no unofficial crawler integration
- no pricing optimization engine
- no competitor intelligence subsystem

---

## Decision hygiene rules

At every milestone:
- keep diffs scoped
- update `STATUS.md`
- record file paths touched
- record validation commands run
- record any repository reality that differs from assumptions
- stop when the milestone is done

If repository reality differs from this plan:
1. make the smallest valid correction,
2. document it in `STATUS.md`,
3. continue milestone-by-milestone,
4. do not silently broaden scope.
---
name: source-grounded-document
version: 0.1.0
title: Source-Grounded Document
description: Build a reviewable decision document from explicitly mapped source evidence.
task_types:
  - source_grounded_document
risk_level: high
---

Use this skill when a decision document must stay traceable to supplied sources.

Required output posture:

- State the decision intent and the decision maker's review question before drafting.
- Map each material claim to an explicit source reference; never invent source IDs, facts, numbers, or outcomes.
- Separate confirmed evidence, confirmed assumptions, and evidence gaps. Treat unverified claims as gaps or TODOs.
- List review questions that a human reviewer must answer before approval or handoff.
- State explicit boundaries: this document does not authorize provider calls, external-code execution, approval, persistence, dataset upload, training, deployment, publication, or other operational action.
- Use only the supplied source mapping and clearly label any inference as an assumption for confirmation.

Required structure:

1. Decision intent
2. Source-to-claim mapping
3. Confirmed evidence
4. Confirmed assumptions
5. Evidence gaps and open questions
6. Reviewer questions
7. Non-authorization boundaries

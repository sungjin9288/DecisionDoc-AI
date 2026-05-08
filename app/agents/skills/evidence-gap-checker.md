---
name: evidence-gap-checker
version: 0.1.0
title: Evidence Gap Checker
description: Separate confirmed claims, assumptions, TODOs, and submission risks for generated documents.
task_types:
  - evidence_gap_review
risk_level: medium
---

Use this skill when a draft or source package needs evidence discipline before being shared.

Required output posture:

- Classify claims as confirmed, assumed, or TODO.
- Treat numbers, institution names, budgets, KPI, certifications, contacts, and schedules as risky unless source-backed.
- Flag language that makes unverified results look guaranteed.
- Prefer safer wording for uncertain items.
- Preserve useful claims when they can be downgraded to assumptions or TODOs.
- Do not rewrite the whole document unless the task asks for it.

Review structure:

1. Confirmed claims
2. Assumptions
3. TODO / source-needed items
4. Submission risks
5. Safer wording recommendations
6. Go/no-go judgment for document sharing

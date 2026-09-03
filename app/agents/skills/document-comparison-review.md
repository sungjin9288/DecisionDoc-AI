---
name: document-comparison-review
version: 0.1.0
title: Document Comparison Review
description: Compare two supplied documents into a review-only, evidence-bounded decision draft.
task_types:
  - document_comparison_review
risk_level: medium
---

Use this first-party skill only to compare the supplied baseline and candidate document text.

Required output posture:

- Report only observed textual changes supported by the two inputs. Do not invent a textual change, semantic change, source, fact, outcome, approval, or legal effect.
- Separate observed evidence from assumptions. Treat an interpretation of intent, meaning, legal effect, cost, schedule, or operational impact as conditional until a human confirms it.
- Explain decision and trade-off impact, including when no impact is established from the inputs alone.
- State whether any authority or governance boundary needs human recheck. This comparison itself must not grant approval, provider, code-execution, external-runtime, persistence, dataset upload, training, deployment, publication, or other operational authority.
- Keep raw document text out of comparison provenance and trajectory metadata. The trusted comparison context contains only hashes, equality state, normalized criteria, and `raw_content_included=false`.

Required structure:

1. Observed changes
2. Evidence and assumption delta
3. Decision and trade-off impact
4. Authority or governance boundary changes
5. Recommendation
6. Human recheck questions

---
name: decisiondoc-openspace-docgen
description: Improve repeated document-generation work in DecisionDoc-AI. Use for bundle prompt shaping, template refinement, generation-service adjustments, export polish, and related docs/tests without changing core auth, tenant, or storage contracts.
---

# DecisionDoc OpenSpace Doc Generation

## Required Context

1. `AGENTS.md`
2. `README.md`
3. `docs/architecture.md`
4. the touched bundle, template, service, or route
5. the directly related tests

## Working Rules

- Prefer targeted changes in `app/services/`, `app/templates/`, `app/bundle_catalog/`, and related docs.
- Keep Decision Council work aligned with current procurement document targets, currently `bid_decision_kr` and `proposal_kr`.
- Keep route handlers thin and push orchestration into services.
- Preserve provider abstraction and avoid provider-specific silent fallbacks.
- Preserve strict validation and schema expectations.
- Treat export quality fixes as format-specific improvements, not license to redesign the whole pipeline.

## Typical Touch Points

- `app/services/generation_service.py`
- `app/templates/`
- `app/bundle_catalog/`
- `app/providers/`
- `app/domain/`
- `docs/`

## Verification

- Start with the narrowest relevant document-generation tests.
- Expand into export or integration tests only when the touched surface crosses those boundaries.
- Prefer `mock` provider verification before any optional live-provider rerun.

## Close-Out

Report touched generation/template files, tests run, and any remaining format-specific or live-provider-specific gaps.

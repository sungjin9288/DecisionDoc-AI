---
name: decisiondoc-openspace-bootstrap
description: Bootstrap OpenSpace-assisted work in DecisionDoc-AI. Use before non-trivial work that relies on evolved skills so the agent reads the repo contracts first and preserves provider, storage, auth, tenant, and export boundaries.
---

# DecisionDoc OpenSpace Bootstrap

## Required Context

1. `AGENTS.md`
2. `README.md`
3. `docs/architecture.md`
4. `docs/security_policy.md`
5. `docs/test_plan.md`
6. the touched module and the directly related tests

## Working Rules

- Treat repo files as the source of truth over OpenSpace memory or prior runs.
- Treat OpenSpace as repo-local bridge guidance only; app runtime integration is out of scope.
- Preserve the current FastAPI app shape and startup wiring.
- Preserve provider, storage, auth, tenant, export, and observability boundaries.
- Keep `mock` provider behavior deterministic for local and test flows.
- Do not move environment lookups into request handlers.
- Do not widen security or tenant semantics without explicit repo support.

## Typical Touch Points

- `app/main.py`
- `app/services/`
- `app/providers/`
- `app/storage/`
- `app/templates/`
- `app/static/`
- `tests/`
- `docs/`

## Verification

- Run the narrowest relevant pytest files first.
- When startup wiring changes, verify app creation directly.
- When static UI changes, prefer the relevant static/PWA tests if available.

## Close-Out

Report changed files, checks run, and any remaining env-dependent or live-provider-dependent risks.

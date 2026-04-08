---
name: decisiondoc-procurement-eval
description: Handle DecisionDoc-AI procurement and G2B evaluation work. Use when changing public procurement copilot specs, G2B collection, procurement evaluation logic, related admin routes, or the targeted tests and docs that prove those flows still work.
---

# DecisionDoc Procurement Eval

## Required Context

1. `AGENTS.md`
2. the relevant files under `docs/specs/public_procurement_copilot/`
3. the touched route, service, or collector module
4. the directly related tests

Prefer the procurement spec docs before changing implementation behavior.

## Working Rules

- Respect the repo's provider, storage, and service boundaries.
- Keep request validation strict and avoid pushing config lookups into request handlers.
- Prefer targeted edits in routes, services, schemas, or collectors over broad rewrites.
- Update spec or status docs when behavior or workflow expectations change.
- Keep local runtime assumptions aligned with `.claude/launch.json` when a manual server run is needed.

## Typical Touch Points

- `app/services/g2b_collector.py`
- `app/routers/admin.py`
- procurement or tenant services under `app/services/`
- procurement regression fixtures under `tests/fixtures/procurement/`
- procurement docs under `docs/specs/public_procurement_copilot/`

## Verification

- Run the narrowest relevant pytest files first.
- Use these targeted checks when they match the change:
  - `tests/test_g2b.py`
  - `tests/test_procurement_eval_regression.py`
  - `tests/test_procurement_eval_summary.py`
  - `tests/e2e/test_main_flow.py`
  - `tests/test_infrastructure.py`
  - `tests/test_tenant.py`
- Expand to broader verification only when the touched surface crosses route, infrastructure, or tenant boundaries.

## Close-Out

Report code changes, test files run, spec docs updated, and any remaining environment-dependent checks.

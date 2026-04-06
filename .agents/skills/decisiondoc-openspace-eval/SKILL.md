---
name: decisiondoc-openspace-eval
description: Handle evaluation, quality hardening, and failure triage work in DecisionDoc-AI. Use for offline eval, live eval classification, lint/regression analysis, and repeated quality-repair loops grounded in the repo's current test and eval contracts.
---

# DecisionDoc OpenSpace Eval

## Required Context

1. `AGENTS.md`
2. `docs/test_plan.md`
3. `docs/security_policy.md` when the change affects review or policy-sensitive outputs
4. the touched eval, service, schema, or fixture files
5. the directly related tests

## Working Rules

- Keep offline eval and live eval semantics separate.
- When procurement / Decision Council regressions are involved, preserve proposal-first coverage for `proposal_kr` as well as `bid_decision_kr`.
- Treat missing live-provider env as an environment condition, not an automatic product failure.
- Prefer fixing repeated quality issues in templates, services, schemas, or eval rules rather than adding ad-hoc output patches.
- Preserve fixture readability and regression intent when updating test data.

## Typical Touch Points

- `app/eval/`
- `app/eval_live/`
- `tests/test_quality_*`
- `tests/test_*eval*`
- `tests/fixtures/`
- `docs/test_plan.md`

## Verification

- Run the narrowest eval or quality pytest targets first.
- Keep optional live-provider reruns clearly separate from required local verification.
- Record whether results came from mock/local, offline eval, or live provider calls.

## Close-Out

Report touched eval files, test files run, fixture updates, and whether any live-provider checks were skipped.

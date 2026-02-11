# ADR: Budget Guardrail

## Goal
Keep monthly spend within strict cap

## Context


## Constraints
Monthly budget must remain under USD 20

## Decision
Use FastAPI API-only service with schema-first provider bundle generation.

## Options
- Option A: Keep mock provider default and add adapters.
- Option B: Immediate full LLM dependency (deferred).

## Risks
- Provider SDK integration may fail due to missing keys or environment setup.
- Generated bundle may violate schema if provider output drifts.

## Assumptions
- Current requirements are stable for this MVP.
- Windows local development is the primary environment.

## Checks
- Validate document section completeness.
- Confirm output readability for mixed audience.

## Next actions
- Run live-provider tests in secured CI or local env.
- Add provider-specific prompt/version tracking.

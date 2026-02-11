# ADR: Auth Secret Handling

## Goal
Document how to handle secrets safely

## Context


## Constraints
Never log tokens, API keys, or passwords; redact at source

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

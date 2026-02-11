# Onepager: Auth Secret Handling

## Problem
Decision documentation workflows are inconsistent and manual.

## Recommendation
Generate standardized bundle once, then render all docs from templates.

## Impact
- Improves consistency across ADR, onepager, eval plan, and ops checklist.
- Enables regression testing for structure and validator conformance.

## Constraints
Never log tokens, API keys, or passwords; redact at source

## Checks
- Validate document section completeness.
- Confirm output readability for mixed audience.

# Eval Plan: MVP Delivery Baseline

## Metrics
- Generation success rate
- Validator pass rate
- Response latency

## Test cases
- Minimal payload with defaults
- Invalid input returns 422
- Provider failure returns PROVIDER_FAILED

## Failure criteria
- Missing required bundle keys
- Rendered docs fail validator checks

## Monitoring
- Track status codes and provider name in metadata.
- Avoid logging raw payloads containing sensitive text.

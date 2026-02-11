# Ops Checklist: Quick Choice

## Security
- [ ] Use environment variables for provider API keys only.
- [ ] Never include keys in source, logs, or docs examples.

## Reliability
- [ ] Enforce one provider call per request with timeout guard.
- [ ] Fail closed on JSON/schema validation errors.

## Cost
- [ ] Default provider is mock for offline and low-cost operation.
- [ ] Use optional cache to reduce repeated live-provider calls.

## Operations
- [ ] Use provider env switch: mock|openai|gemini.
- [ ] Run networked tests only with pytest -m live.

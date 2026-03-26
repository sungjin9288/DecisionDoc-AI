## Goal
Decide whether to migrate KakaoPay's payment service (20M monthly transactions) from monolith to MSA.
Current 3-week deployment cycles and cascading failures are causing measurable business impact.

## Decision
**Adopt Strangler Fig pattern** — new features built as independent microservices; legacy monolith decomposed in 3 phases by Q3 2026.

## Options
- **Option A (Selected): Strangler Fig** — risk distribution, 18-month roadmap, no service interruption
- **Option B: Big Bang Rewrite** — 6-month full stop, unacceptable for 24/7 payment service
- **Option C: Status Quo** — bottleneck reaches critical point within 12 months; not viable

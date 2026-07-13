# Bundle Quality Evidence

- generated_at: `2026-07-13T06:14:52.773968+00:00`
- provider: `mock`
- status: `passed`

## Summary

- bundles: `2`
- generated documents: `6`
- validator passes: `2`
- lint passes: `2`
- numeric grounding passes: `2`
- unsupported numeric claims: `0`

| bundle | docs | validator | bundle lint | numeric coverage | unsupported claims | canonical golden SHA256 |
| --- | ---: | --- | --- | --- | ---: | --- |
| `proposal_kr` | 4 | pass | pass | passed | 0 | `7daba879e518aeaa6083bc815da528c40a5f5da7867cd31c5b5f4086ffdc2f7d` |
| `performance_plan_kr` | 2 | pass | pass | passed | 0 | `78a04001f3108a389a1006ab2640af6986ef71b311f2a560b4ffc0e130e863b5` |

## Scope And Limitations

- These are deterministic fictional fixtures generated with the local mock provider.
- Numeric coverage checks whether unit-bearing output numbers also appear in the request; unmatched values remain review items.
- Numeric coverage does not prove factual truth, freshness, or correct contextual use.
- Factual grounding and human visual review are not marked complete by this report.
- No provider API, AWS runtime, dataset upload, training, model promotion, or production resume action ran.

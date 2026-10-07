# Future Feature Gate Records

This directory contains repository-owned candidate decision records. A valid
record is planning evidence only. Implementation remains blocked until the
record has an `approved` decision and passes:

```bash
python3 scripts/validate_future_feature_gate.py \
  path/to/record.json \
  --require-approved \
  --json
```

Current records:

- [Procurement multi-opportunity](./procurement_multi_opportunity.json):
  `approved`; local/fake-S3 independent opportunity identity, selection and
  source-bound evaluation/review/document lifecycle implementation is admitted.
  User-data migration and external effects remain excluded.
- [Procurement requirement applicability](./procurement_requirement_applicability.json):
  `approved`; local/fake-S3 source-bound, session-admin-authored requirement applicability without
  bypassing filters or granting operational approval. Depends on the reviewed
  opportunity identity design; no operational authority is granted.

Both procurement candidates use the
[2026-09-21 design](../superpowers/specs/2026-09-21-procurement-opportunity-and-applicability-design.md).
The [implementation plan](../superpowers/plans/2026-09-21-procurement-opportunity-and-applicability.md)
records steps 1-8 as locally implemented and verified across storage, API,
browser, source binding and requirement applicability. Steps 9-11 record offline
preflight, persisted transition and cold-process fixture restore verification.
Commands, dated results and limitations are maintained in
[procurement STATUS](../specs/public_procurement_copilot/STATUS.md).
Default-app activation and actual user-data migration remain outside this scope.

An approved record preserves the admission-time acceptance targets; wording such
as "planned" in its `local_verification` field is not a current implementation
status. Do not rewrite a terminal decision to refresh progress. Conversely, a
command listed in that record is not pass evidence without its execution result.

- [Generated document review completion](./generated_document_review_completion.json):
  `approved`; admitted only for the exact local and fake-S3 implementation
  scope recorded in the file.
- [Generated document reviewed-package verifier](./generated_document_reviewed_package_verifier.json):
  `approved`; admitted for the standalone read-only CLI, regression tests and
  coupled local documentation only. External effects remain excluded.
- [Agent-authored local generation](./agent_authored_local_generation.json):
  `approved`; a local Claude Code or Codex session writes the bundle and the
  server validates, stores and exports it without any provider call. Design
  and verification: the
  [2026-10-07 spec](../superpowers/specs/2026-10-07-agent-authored-local-generation-design.md).

Do not overwrite a prior terminal decision. Create a new record when the
problem, acceptance criteria, or authority scope changes.

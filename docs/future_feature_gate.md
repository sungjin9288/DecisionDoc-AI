# Future Feature Gate

Updated: 2026-09-04

This contract turns the product plan's feature-admission checklist into a
versioned local decision record. It does not select a feature and does not grant
operational authority.

## Admission Rule

A candidate may enter implementation only when all of the following are true:

1. The record uses `decisiondoc.future_feature_gate.v1` and contains only the
   defined fields.
2. The target user, observed problem, evidence, workaround, desired outcome,
   acceptance criteria, affected boundaries, authority scope, and local
   verification path are complete.
3. `decision.status` is `approved` with a decision owner, UTC decision time,
   and rationale.
4. `python3 scripts/validate_future_feature_gate.py <record> --require-approved`
   exits successfully.

`draft`, `deferred`, and `rejected` records may be structurally valid, but they
are not admitted for implementation.

## Record Workflow

Start from [the draft template](./samples/future_feature_gate/template.json).
Keep the record beside the relevant spec or in a task-specific evidence path;
do not overwrite a prior decision when the problem, authority, or acceptance
criteria change. Replace every `<replace>` marker and the
`draft-feature-gate-id` value before requesting approval. An approved record
containing either marker fails validation.

Validate record structure while drafting:

```bash
python3 scripts/validate_future_feature_gate.py path/to/record.json --json
```

Before implementation, require an approved decision:

```bash
python3 scripts/validate_future_feature_gate.py \
  path/to/record.json \
  --require-approved \
  --json
```

The JSON result separates `record_valid` from
`admitted_for_implementation`. It also fixes `decision_identity_verified` and
`operational_authority_granted` to `false`. Automation must check command exit
status and must not treat a valid draft as approval.

## Field Contract

| Field | Requirement |
|---|---|
| `gate_id` | Stable lowercase identifier, 3-80 characters |
| `target_user` | Specific user or operator with the observed problem |
| `observed_problem` | Problem statement without embedding the proposed solution |
| `evidence` | One or more repository, test, user-feedback, or external-source observations |
| `current_workaround` | Current manual or technical path and its limitation |
| `desired_outcome` | User-visible result rather than implementation detail |
| `acceptance_criteria` | Non-empty, bounded, observable completion conditions |
| `affected_boundaries` | Explicit route, service, schema, storage, provider, browser, or documentation surfaces |
| `authority_scope` | Review-only state plus allowed, excluded, and separately approved effects |
| `local_verification` | Exact commands and the behavior or boundary each command proves |
| `decision` | `draft`, `approved`, `deferred`, or `rejected`; terminal decisions require owner and UTC time |

Unknown keys, duplicate JSON keys, empty required lists, duplicate list values,
invalid decision metadata, and non-finite JSON values fail validation.

## Authority Boundary

The validator reads one local JSON file and writes nothing. It verifies record
shape, not the identity or authority of `decided_by`; repository ownership and
review remain separate controls. It does not call a provider, access
application storage, mutate tenant state, use AWS or G2B, deploy, publish,
submit a bid, approve an operational action, or prove human UAT. An approved
feature gate admits only the implementation scope written in that record. Any
effect listed under `separate_approval_required_for` still requires its own
approval.

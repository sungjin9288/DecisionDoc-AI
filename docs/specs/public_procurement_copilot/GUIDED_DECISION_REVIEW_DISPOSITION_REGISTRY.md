# Guided Decision Review Disposition Registry

## Purpose

H129 v1 is the immutable legacy reviewer-attribution record for one exact H128
`guided-decision-review-disposition-receipt.v1`. New public operations create
v2 only; an existing v1 operation can only exact-replay its historical identity
and canonical bytes without approving the project, mutating review workflow
state, executing an export, calling a provider, submitting a bid, or creating
legal or contractual authority.

The H128 source remains reviewer-unbound and non-persistent. H129 v2 additionally
requires the exact same-backend H128 issuance metadata before it can create a
new record. Only the H129
wrapper fixes `reviewer_identity_bound=true` and
`registry_record_persisted=true`.

## Routes and access

All routes require a current session-bound procurement reviewer and a required
allowlisted `bundle_type` query value:

```http
POST /projects/{project_id}/guided-decision-review-dispositions?bundle_type=proposal_kr
GET  /projects/{project_id}/guided-decision-review-dispositions?bundle_type=proposal_kr
GET  /projects/{project_id}/guided-decision-review-dispositions/{operation_id}?bundle_type=proposal_kr
GET  /projects/{project_id}/guided-decision-review-dispositions/{operation_id}/download?bundle_type=proposal_kr
```

Create uses the v2 shape below for a new operation. The legacy v1 shape is
accepted only to exact-replay an already-stored matching v1 operation; a missing
v1 operation returns non-disclosing `422` without any conditional write. v1
objects already stored in the registry are never migrated or rewritten:

```json
{
  "contract_version": "guided-decision-review-disposition-record-request.v1",
  "operation_id": "lowercase UUIDv4",
  "source_disposition_receipt": {
    "contract_version": "guided-decision-review-disposition-receipt.v1"
  },
  "source_disposition_receipt_sha256": "lowercase SHA-256"
}
```

`guided-decision-review-disposition-record-request.v2` keeps the same source
fields. The server independently reads the content-addressed H128 issuance
metadata by the source body SHA-256 in the selected tenant/project/bundle
backend, then embeds only that strict metadata and its exact SHA-256 in
`guided-decision-review-disposition-record.v2`. A missing, tampered,
foreign-scope, corrupt, or unavailable issuance record prevents v2 creation;
invalid submitted source is a non-disclosing `422`, while unavailable
authoritative state is a fail-closed `503`.

- tenant admin sees the current tenant/project/bundle registry;
- an assigned member creates and lists only records bound to that stable user
  ID;
- assigned non-owner direct read/download returns the same `404` as a missing
  record;
- API-key-only, Ops-key-only, sessionless JWT, viewer, foreign tenant,
  nonexistent project, and unassigned member do not gain registry access.

The project/assignment check runs before any registry read. The routes reuse the
existing non-disclosing procurement policy rather than adding a second auth
system.

## Storage identity and conditional create

The selected `StateBackend` stores a record under:

```text
tenants/{tenant_id}/projects/{project_id}/
guided_decision_review_dispositions/{bundle_type}/
{sha256(lowercase_uuidv4_operation_id)}.json
```

The object path never contains the raw operation ID. Tenant, project, bundle,
and operation components are canonical and path-safe. Local storage uses the
backend conditional file lock plus atomic write; S3 uses `If-None-Match: *`.

The request binding SHA-256 covers exactly:

- tenant ID;
- project ID;
- bundle type;
- operation ID;
- stable reviewer user ID;
- exact canonical H128 source SHA-256.

It intentionally excludes reviewer username, role, and `recorded_at`. An exact
retry after username or role drift therefore returns `200` with the first
canonical bytes, historical username/role, and historical timestamp. Reusing
the operation ID with another stable reviewer or H128 source returns `409`
without rewriting the authoritative object.

If the conditional-write response is uncertain, success is reconciled only by
reading, fully validating, and matching the persisted request binding. Missing,
foreign, corrupt, or differently bound state is not treated as success.

## Record contract

`guided-decision-review-disposition-record.v1` includes the complete H128
source and its canonical SHA-256, tenant/project/bundle/operation identity,
stable and historical reviewer fields, canonical UTC `recorded_at`, projected
H127/H128 hashes/status/disposition, request binding, and full-record binding.

The full-record binding is canonical SHA-256 over every field except
`record_binding_sha256` itself. It therefore protects reviewer username, role,
timestamp, stable user ID, wrapper fields, full nested H128/H127/H126 source,
all projected hashes, status/disposition, and every false authority boundary.

`guided-decision-review-disposition-record.v2` adds only
`source_issuance_metadata`, `source_issuance_metadata_sha256`, and
`issuance_provenance=server_issued`; its request and full-record bindings cover
that proof. Metadata is hash-only H128 issuance evidence, not a signature,
actor attestation, currentness, atomic snapshot, approval, or external
authenticity.

Wrapper invariants are:

- `record_status: recorded`
- `review_state_only: true`
- `review_only: true`
- `read_only: true`
- `reviewer_identity_bound: true`
- `registry_record_persisted: true`
- `snapshot_atomic: false`
- `requires_recheck_before_reliance: true`
- all six `authority` fields false.

The nested H128 source must still have
`reviewer_identity_bound=false`,
`disposition_receipt_persisted=false`, and all H126–H128 review-only,
read-only, non-atomic, recheck-required, and false-authority fields.

## Revalidation and failure policy

Create, list, read, and download independently reparse and verify:

- exact record field set and canonical JSON bytes;
- exact H129 record and request bindings;
- tenant, project, bundle, operation, reviewer and object-path scope;
- exact H128 source body SHA-256 and explicit field set;
- nested H127 source/current handoff SHA-256 values;
- nested H126 semantic fingerprints and route project/bundle;
- `unchanged|changed` derivation and disposition matrix;
- H128 disposition binding;
- H126, H127, H128, and H129 false authority boundaries.

Malformed JSON/UTF-8, noncanonical bytes, unexpected or duplicate paths,
foreign scope, path identity drift, list-time disappearance, or backend
unavailability fails closed. Validation never rewrites or repairs source bytes,
and list never returns a partial result after one corrupt entry.

## List, read, and download

Summaries sort by `(recorded_at, operation_id)` descending. They expose only
allowlisted contract, operation, tenant/project/bundle, historical reviewer
username/role, timestamp, projected workflow/hash fields and fixed boundaries.
They exclude the nested receipt, stable reviewer user ID, request binding, and
full-record binding.
Legacy v1 summaries explicitly state `legacy_issuance_unrecorded`; v2 summaries
state `server_issued` and expose only the issuance metadata hash. Read/download
keep v1 canonical bytes unchanged and expose the legacy/server issuance state
through safe response headers.

Read and download return the same revalidated canonical bytes. Record and list
responses use `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
exact body SHA-256 headers, and `X-DecisionDoc-Operational-Approval: false`.
Download adds a UUID-derived safe JSON attachment filename only after the path
operation ID is canonical.

## Browser boundary

The browser enables create only after an H128 response has passed current
page-memory source, canonical body/header SHA-256, nested H126/H127 validation,
scope, disposition matrix, and false-authority checks. It assigns one lowercase
UUIDv4 per tenant/user/project/bundle/source-hash scope and reuses it for an
uncertain exact retry.

Each create owns a distinct in-memory request token. A context invalidation may
start a newer request B, but stale request A can neither clear B's token nor
start a third POST while B is pending. Tenant, user, auth revision, project
load, bundle, H126/H127/H128 source, or newer-request drift discards pending
state and late responses.

Create/list/download verify strict schemas, canonical body/header hash,
project/bundle, reviewer visibility, sorting, safe attachment metadata and all
false boundaries before rendering a record or constructing a Blob. Operation
identity, source receipts, and pending tokens remain page-memory only; browser
storage is not used.

## Audit and limitations

Create/list/read/download audit actions retain only the authenticated actor,
operation ID when applicable, allowlisted record/source hashes,
status/disposition/replay fields, and fixed boundaries. They omit session ID,
IP, User-Agent, tokens, rationale, nested receipts, and any separate stable
target identity.

H129 is local integrity and reviewer-attribution evidence. Its same-backend
issuance metadata does not prove a signature, actor attestation, currentness,
external authenticity, approval, or an atomic snapshot; it does not close M1
live provider, M2 durable G2B, M6 deployment/runtime, human UAT, external
approval, or atomic-snapshot gaps. Dataset
upload, training, promotion, provider/AWS/G2B calls, deployment, service resume,
bid submission, legal approval, and contractual commitment remain outside this
path.

## Local verification evidence

On 2026-08-18, the v2-only public-create remediation plus H128 unavailable,
corrupt, and disappearing issuance fail-closed paths passed the combined
storage/API/handoff/static gate (`58 passed`), focused Chromium registry
selection (`1 passed, 13 deselected`), and adjacent authorization/audit/security
gate (`172 passed`). Static quality, security scanning, source-derived README
metrics, portfolio sync/package verification, and diff gates also passed.
These focused results do not change the external gaps above.

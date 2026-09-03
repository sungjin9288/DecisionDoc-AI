# Generated Document Review Handoff v1 Design

Status: Approved for specification review

Date: 2026-09-03

## 1. Decision

DecisionDoc will add a review-only handoff for generated project documents. The
handoff will build and independently verify one deterministic export packet,
persist the exact packet bytes in the selected `StateBackend`, bind the packet
to one stable reviewer identity, and expose scoped list and re-download paths.

This feature is not a second approval workflow. It records that a specific
reviewer received a specific packet for review. It does not record a review
decision, approve a document, authorize an operational action, or change the
existing `/approvals` lifecycle.

The first implementation slice ends at `pending` handoff creation, inbox
visibility, project history, and exact packet re-download. Review completion,
reassignment, reminders, expiry, and deletion are separate future decisions.

## 2. Future Feature Gate

### Target user

- A project manager preparing generated DecisionDoc documents for internal
  review.
- An admin or member assigned to review the exact exported document packet.

### Concrete observed problem and evidence

The current `GET /generate/export-zip` path builds and verifies a deterministic
multi-format ZIP, but its manifest deliberately states
`packet_persisted=false` and `human_review_completed=false`. A browser can
download the packet, but DecisionDoc does not retain the exact bytes or bind
that delivery to a stable reviewer identity.

The existing `/approvals` workflow cannot be reused as the handoff record. It
models draft, review, and final `approved` states and therefore carries a
different business meaning. Reusing it would blur the repository rule that
review evidence and operational approval remain separate.

The procurement workflow already demonstrates the required safety properties:
session-bound reviewer access, immutable packet storage, packet-bound pending
records, exact re-download, tenant scoping, and non-authorization headers.
Those patterns are evidence for the design, not a reason to couple generated
documents to procurement-specific schemas or storage paths.

### Current workaround

The user downloads a verified ZIP and coordinates review outside DecisionDoc.
The reviewer, packet hash, packet bytes, and project document are not available
as one re-checkable in-product handoff.

### Desired outcome

From a persisted project document, an authorized user can create one immutable
review-only packet for a stable reviewer. The assigned reviewer can find the
pending handoff and re-download the exact verified bytes without provider,
AWS, training, deployment, or approval effects.

### Bounded acceptance criteria

1. The server accepts only a current tenant project document with a non-empty
   request ID, bundle ID, title, and valid stored document snapshot.
2. The packet binds tenant, project, document, request, bundle, title, canonical
   document-source fingerprint, formats, manifest hash, packet hash, artifact
   count, creator, and reviewer.
3. The packet is built completely in memory, independently verified, written
   with immutable conditional create, and read back before the handoff is
   returned.
4. The pending record is created only after packet verification and packet
   read-back. An orphan packet is never treated as a handoff.
5. Exact creation replay for the same packet, creator, and reviewer returns the
   existing record and bytes. Creator, reviewer, or source drift returns `409`
   without rewriting existing evidence.
6. Admin can assign an active admin or member. Member can assign only their own
   stable identity. Viewer, API-key-only, Ops-key-only, sessionless, inactive,
   missing, and foreign principals cannot create or read a handoff.
7. Admin can list all tenant handoffs. Member can list only handoffs assigned to
   their stable user ID. Missing, foreign, and unauthorized record identities
   share a non-disclosing not-found response.
8. Packet re-download verifies record schema, immutable packet size and hash,
   manifest hash, project/document binding, and packet semantics before sending
   bytes.
9. List and re-download responses compare the stored document-source
   fingerprint with the current project document and report exactly `current`,
   `changed`, or `missing`. A historical packet remains downloadable with a
   visible warning; currentness never rewrites the immutable record.
10. Browser download begins only after validating media type, content length,
   packet and manifest hashes, artifact count, `review_status=pending`,
   `review_only=true`, reviewer binding, and all false authority headers.
11. Tenant, signed user, auth revision, project, document, request, or handoff
    selection changes invalidate in-flight responses and revoke created object
    URLs.
12. Focused unit, API, storage, static browser, and Chromium tests pass in
    mock/local mode. The full non-live gate remains green.
13. README metrics, product direction, development plan, roadmap, and portfolio
    pack remain source-derived and synchronized.

### Affected boundaries

- `app/services/generation_export_packet.py`: additive persisted review-packet
  schema while preserving the current transient packet contract.
- New generated-document review service and store modules.
- Project router and strict request/response schemas.
- `app/main.py` dependency construction and `app.state` registration.
- Project detail and reviewer inbox browser surfaces.
- Audit projection, documentation, tests, and portfolio evidence.

### Explicit authority scope

Every packet and handoff must keep these values false:

- `approval_authorized`
- `aws_execution_authorized`
- `dataset_upload_authorized`
- `deployment_authorized`
- `g2b_submission_authorized`
- `provider_execution_authorized`
- `training_execution_authorized`

The handoff additionally states:

- `review_only=true`
- `packet_persisted=true`
- `human_review_completed=false`
- `operational_approval=false`

Creation and re-download do not call a provider, fetch G2B, upload a dataset,
run training, deploy, publish, resume a service, submit a bid, create a legal or
contractual commitment, or mutate the existing approval workflow.

### Local verification path

The implementation will use deterministic mock/local tests only:

```bash
python3 -m pytest -q \
  tests/test_generation_export_packet.py \
  tests/storage/test_generated_document_review_store.py \
  tests/test_generated_document_reviews.py \
  tests/test_infrastructure.py -k generated_document_review --tb=short

python3 -m pytest -q tests/e2e/test_main_flow.py \
  -k generated_document_review --browser chromium --tb=short

python3 -m pytest tests/ -m "not live" -q
ruff check app/ tests/ --select=E,F,W --ignore=E501
python3 scripts/check_secret_hygiene.py
python3 scripts/manage_portfolio_pack.py check
git diff --check
```

## 3. Options Considered

### Option A: Separate review-only handoff record

Selected.

This option reuses proven storage and authorization patterns while keeping the
record semantics narrow. It adds one generated-document review domain with no
completion state in the first slice.

Trade-off: it introduces a new store and API surface. The separation is
intentional because the record does not mean approval and must not inherit the
legacy approval lifecycle.

### Option B: Add packet fields to `ApprovalRecord`

Rejected.

This would minimize the number of stores but would attach review-delivery
evidence to a lifecycle that can end in `approved`. It would make it difficult
for API and UI consumers to distinguish packet receipt from approval authority.

### Option C: Add only a read-only package summary

Rejected for this slice.

The existing Decision Evidence Map already supplies a broad read-only project
projection. Another summary would improve presentation but would not preserve
the exact reviewed bytes or reviewer assignment.

## 4. Packet Contract

The current transient packet remains
`decisiondoc.generate_export_review_packet.v1` with
`packet_persisted=false`. Existing callers and tests keep their current bytes.

The handoff introduces
`decisiondoc.generated_document_review_packet.v1`. Its manifest uses the same
deterministic ZIP metadata, fixed artifact paths, conversion limits, and
authority object, with these differences:

- `packet_persisted=true`
- source fields are exactly `tenant_id`, `project_id`,
  `project_document_id`, `request_id`, `bundle_id`, `title`, and
  `document_source_sha256`
- canonical formats remain ordered by the existing `FORMAT_ORDER`

The verifier selects validation rules from the exact schema value. Unknown
schemas, mixed source fields, unsupported authority fields, duplicate entries,
non-canonical JSON, unsafe ZIP metadata, and content/hash mismatch fail closed.
The existing v1 verifier behavior remains unchanged.

## 5. Stored Record

The record schema is
`decisiondoc.generated_document_review_handoff.v1`. It contains:

- tenant, project, project-document, request, and bundle identities
- packet SHA-256, packet size, manifest SHA-256, artifact count, and formats
- canonical document-source fingerprint computed from the server-loaded
  project/document/request/bundle/title/document-snapshot inputs
- title and `prepared_at`
- stable creator assignment: user ID, username, and role snapshot
- stable reviewer assignment: user ID, username, and role snapshot
- `review_status="pending"`
- `review_only=true`
- `packet_persisted=true`
- `human_review_completed=false`
- `operational_approval=false`
- the closed all-false authority object

Stable user IDs are private storage fields. Public summaries expose usernames,
role snapshots, hashes, sizes, timestamps, project/document identity, and review
state. They also expose the derived `source_status` value `current`, `changed`,
or `missing`, but not stable IDs, tokens, session IDs, IP addresses, user agents,
document bodies, packet entries, or storage paths.

No mutable status transition exists in v1. A record is either absent or an
immutable pending handoff.

## 6. Storage Design

The selected local/S3 `StateBackend` is the only persistence dependency.

```text
tenants/{tenant_id}/generated_document_reviews/
  packets/{packet_sha256}.zip
  projects/{project_id}/{project_document_id}/{packet_sha256}/record.json
```

Creation order:

1. Validate session, role, project, document, snapshot, and reviewer.
2. Build and independently verify the persisted packet schema in memory.
3. Write packet bytes with `write_bytes_if_absent`.
4. On an existing packet object, require byte-for-byte equality.
5. Read the packet back and verify bytes and semantics again.
6. Build the immutable canonical record.
7. Write the record with `write_text_if_absent`.
8. If the record exists, accept only exact canonical equality and return replay.
9. Read and validate the record and packet once more before returning.

If packet creation succeeds but record creation fails, the packet is an
unreferenced object, not a handoff. The request reports a generic unavailable
error and does not delete or overwrite the packet. Cleanup and garbage
collection are outside this slice.

## 7. API Design

### Create handoff

`POST /projects/{project_id}/documents/{document_id}/generated-reviews`

Strict request body:

```json
{
  "reviewer": "reviewer@example.com",
  "formats": ["docx", "pdf", "xlsx", "hwp", "pptx"]
}
```

The server reads document content and source identity from `ProjectStore`; it
never accepts document bodies, tenant IDs, packet hashes, stable user IDs, or
authority values from the client.

Success returns the exact ZIP bytes. Headers include packet and manifest hashes,
artifact count, review status, reviewer-identity binding, replay state,
`review_only=true`, `packet_persisted=true`, and
`operational_approval=false`.

### Reviewer inbox

`GET /generated-document-reviews?review_status=pending&limit=50&offset=0`

Only `pending` is accepted in v1. Results are newest-first with bounded
pagination. Admin sees tenant records; member sees only their assigned records.

### Project history

`GET /projects/{project_id}/generated-document-reviews`

The same access policy applies. Project existence is resolved before records are
returned, without exposing foreign record presence. Each summary compares its
stored document-source fingerprint with the current project document and reports
`current`, `changed`, or `missing` without mutating the record.

### Packet re-download

`GET /projects/{project_id}/generated-document-reviews/{packet_sha256}/packet`

The server authorizes before reading packet bytes, then revalidates record and
packet. Success returns the same safe headers as creation plus the derived source
status. Historical `changed` and `missing` packets remain available to an
authorized reviewer because they are evidence of what was handed off, but the
browser must show that status before download. Missing, foreign, unassigned, and
unauthorized references return the same `404` shape.

### Error mapping

- `400`: invalid format selection or pagination
- `401`: missing or invalid authenticated session
- `403`: authenticated role cannot use the review surface
- `404`: project, document, handoff, or authorization-scoped record unavailable
- `409`: project document is not exportable, or existing handoff identity drifts
- `503`: stored state or packet cannot be trusted or persistence is unavailable

Error bodies never include stored bytes, internal exception text, stable user
IDs, storage paths, or existence details outside the caller's scope.

## 8. Browser Design

The project document action row gains one command:
`검토 패킷 전달`. The action is available only for documents with a valid
request ID and stored snapshot. The existing verified export download remains
unchanged.

The creation dialog selects an active reviewer visible to the current role and
the existing five canonical formats. It states `검토 증빙이며 운영 승인 아님`
next to the primary action. The action is single-flight.

Project detail shows pending handoffs under a plain `문서 검토 전달` section.
The reviewer inbox adds a generated-document tab next to the existing
procurement review surface. Each row shows project, document title, reviewer,
creator, format count, prepared time, packet hash prefix, and a verified packet
download command. `changed` and `missing` source status is visible on the row and
requires an explicit browser confirmation before download.

Browser state is bound to auth revision, tenant, signed user, project,
document, packet, and request generation. A stale response cannot create a
Blob, click a fallback link, show success, or replace a newer inbox result.
Logout, invalid session, tenant change, project close, document removal, or a
newer request revokes associated object URLs.

## 9. Security And Integrity

- Creation and reads require current session-bound admin or member identity.
- UserStore is consulted for current active role and stable user ID.
- Client-provided usernames are selectors only; the server resolves and stores
  trusted identity fields.
- Packet creation uses only server-loaded project document data.
- Record and packet paths validate every path segment before construction.
- Local writes remain atomic through `StateBackend`; S3 uses conditional create.
- Existing object mismatch, duplicate JSON keys, malformed UTF-8, schema drift,
  non-canonical JSON, and hash drift fail closed without repair.
- Audit logs include action, tenant, project, document, packet hash, review
  status, access scope, and replay state. They exclude packet bytes, document
  bodies, stable user IDs, session/token values, and reviewer credentials.
- No notification provider is called in v1.

## 10. Testing Strategy

### Packet tests

- Existing transient v1 bytes and verification remain stable.
- Persisted packet schema binds project/document/request/bundle source fields.
- Mixed schema/source/persistence values, ZIP metadata drift, artifact mismatch,
  duplicate members, unsafe paths, and non-canonical manifest fail.

### Store tests

- Local and fake-S3 exact creation and read-back.
- Exact replay and lost-response reconciliation.
- Packet collision, record collision, reviewer drift, source drift, corrupt
  packet, corrupt record, duplicate key, unsafe path segment, and foreign tenant
  failure.
- Packet orphan remains non-authoritative when record creation fails.
- Current, changed, and missing source projections preserve the immutable record.

### API and authorization tests

- Admin assignment, member self-assignment, inbox filtering, project history,
  and exact re-download.
- Member assignment to another user, viewer, API-key-only, Ops-key-only,
  sessionless, inactive, missing, cross-tenant, and forged path denial.
- Safe headers and generic error bodies.
- Provider and converter failures do not create a record.

### Browser tests

- Valid creation, header/hash verification, download, inbox, and project history.
- Changed and missing source warnings precede historical packet download.
- Duplicate-click single-flight behavior.
- Malformed response and authority-widening rejection.
- Tenant/auth/project/document/request changes discard stale responses and
  object URLs.
- Desktop and 390 px mobile layout have no overlap or horizontal overflow.

## 11. Delivery Sequence

1. Add the persisted review-packet contract and failure-first packet tests.
2. Add immutable store and local/fake-S3 tests.
3. Add strict schemas, service, routes, app wiring, and authorization tests.
4. Add project history and reviewer inbox UI with static tests.
5. Add Chromium workflow and stale-response tests.
6. Update product docs, README source metrics, and portfolio pack.
7. Run focused gates, independent review, full non-live tests, and Git safety
   checks before any commit or push.

## 12. Non-Goals

- Review completion, acceptance, rejection, or requested changes
- Reviewer reassignment, delegation, reminders, due dates, or notifications
- Synchronizing a handoff with `ApprovalStore`
- Persisting transient packets created by the existing export route
- Editing project documents or regenerating document content
- Provider, G2B, OCR, transcription, training, model, AWS, deploy, publish, bid,
  legal, contractual, or production runtime execution
- Packet deletion, retention policy, garbage collection, or migration of prior
  downloads
- Signatures, external attestations, atomic multi-object transactions, or proof
  that a reviewer opened or understood the packet

## 13. Completion Boundary

This slice is complete only when one authenticated local user can create a
pending handoff from a persisted project document, the assigned reviewer can
discover and re-download the same verified packet, every stored and public
authority field remains false, stale and foreign contexts fail closed, and the
full non-live gate passes.

Completion does not change M1, M2, or M6 readiness and does not establish human
UAT, deployment, external approval, or production operation.

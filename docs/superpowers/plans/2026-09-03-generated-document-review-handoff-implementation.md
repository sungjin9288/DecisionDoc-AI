# Generated Document Review Handoff v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist one exact generated-document export packet as immutable review-only evidence, bind it to a stable reviewer, and expose scoped creation, inbox, history, and re-download flows.

**Architecture:** Extend the existing deterministic export packet module with a second schema while preserving the transient v1 bytes. A dedicated immutable store owns packet and handoff records in `StateBackend`; a focused service resolves source freshness and public projections; project routes enforce current session identity before any artifact read. The static browser consumes only the new review-only API and never maps the handoff to `ApprovalStore`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `StateBackend`, pytest, static HTML/JavaScript, Playwright Chromium.

**Spec:** `docs/superpowers/specs/2026-09-03-generated-document-review-handoff-design.md`

## Global Constraints

- Preserve `decisiondoc.generate_export_review_packet.v1` bytes and `packet_persisted=false` behavior.
- New packet schema is exactly `decisiondoc.generated_document_review_packet.v1`.
- New record schema is exactly `decisiondoc.generated_document_review_handoff.v1`.
- Canonical formats remain `docx`, `pdf`, `xlsx`, `hwp`, `pptx` in `FORMAT_ORDER`.
- Every authority key remains false; `review_only=true`, `packet_persisted=true`, `human_review_completed=false`, and `operational_approval=false`.
- Admin may assign an active admin or member; member may assign only their own stable identity.
- Viewer, API-key-only, Ops-key-only, sessionless, inactive, missing, and foreign principals fail closed.
- The first slice has only immutable `pending` records. Completion, disposition, reassignment, reminders, expiry, deletion, and notifications remain out of scope.
- No provider, G2B, AWS, dataset, training, deployment, publish, bid, legal, or contractual effect is permitted.
- README counts and portfolio artifacts must remain source-derived and synchronized.

---

### Task 1: Persisted Packet Contract

**Files:**
- Modify: `app/services/generation_export_packet.py`
- Modify: `tests/test_generation_export_packet.py`

**Interfaces:**
- Consumes: existing `canonicalize_export_formats()`, artifact converters, deterministic ZIP writer, and transient packet verifier.
- Produces: `PERSISTED_PACKET_SCHEMA`, `build_generated_document_review_packet(...) -> dict[str, Any]`, and schema-aware `verify_generation_export_packet(content: bytes) -> dict[str, Any]`.

- [x] **Step 1: Write failing persisted-packet tests**

Add tests that call:

```python
packet = run_async(
    build_generated_document_review_packet(
        docs=DOCS,
        title="검토 문서",
        tenant_id="tenant-a",
        project_id="project-a",
        project_document_id="document-a",
        request_id="request-a",
        bundle_id="bundle-a",
        document_source_sha256="a" * 64,
        formats=("pptx", "docx"),
    )
)
evidence = verify_generation_export_packet(packet["content"])
assert evidence["schema"] == PERSISTED_PACKET_SCHEMA
assert evidence["packet_persisted"] is True
assert evidence["formats"] == ["docx", "pptx"]
```

Also mutate the manifest to prove that mixed source keys, a transient schema with `packet_persisted=true`, a persisted schema with `packet_persisted=false`, unknown schema, duplicate ZIP members, and source hash drift are rejected.

- [x] **Step 2: Run packet tests and confirm RED**

Run: `python3 -m pytest -q tests/test_generation_export_packet.py -k 'persisted or schema_selection' --tb=short`

Expected: collection or assertion failure because the persisted schema builder does not exist.

- [x] **Step 3: Add schema-selected manifest construction and validation**

Keep `build_generation_export_packet()` unchanged. Add a shared private builder receiving a complete source object and expected persistence flag, then expose the new persisted builder. Change only the verifier dispatch:

```python
TRANSIENT_SOURCE_KEYS = {"tenant_id", "request_id", "title"}
PERSISTED_SOURCE_KEYS = {
    "tenant_id", "project_id", "project_document_id", "request_id",
    "bundle_id", "title", "document_source_sha256",
}

schema_rules = {
    PACKET_SCHEMA: (False, TRANSIENT_SOURCE_KEYS),
    PERSISTED_PACKET_SCHEMA: (True, PERSISTED_SOURCE_KEYS),
}
```

Require exact source keys, non-empty identity strings, a lowercase 64-character source SHA for the persisted schema, canonical format order, exact authority keys, and exact canonical manifest bytes. Return `schema`, `packet_persisted`, `formats`, `source`, packet SHA, manifest SHA, and artifact count in verification evidence.

- [x] **Step 4: Run packet tests and confirm GREEN**

Run: `python3 -m pytest -q tests/test_generation_export_packet.py --tb=short`

Expected: all packet tests pass, including existing transient byte-stability tests.

- [x] **Step 5: Commit the packet contract with the immutable store in Task 2**

Do not make a standalone setup commit. Group this contract with its only consumer after Task 2 is green.

---

### Task 2: Immutable Generated Review Store

**Files:**
- Create: `app/storage/generated_document_review_models.py`
- Create: `app/storage/generated_document_review_store.py`
- Create: `tests/storage/test_generated_document_review_store.py`
- Modify: `tests/test_state_backend.py`

**Interfaces:**
- Consumes: `StateBackend.write_bytes_if_absent`, `write_text_if_absent`, exact reads, `require_tenant_id`, and packet verification from Task 1.
- Produces: `GeneratedDocumentReviewRecord`, `GeneratedDocumentReviewStore.prepare(...)`, `get(...)`, `list_by_tenant(...)`, `list_by_project(...)`, and `read_packet(...)`.

- [x] **Step 1: Write failing local-store tests**

Cover exact create/read-back, exact replay, immutable packet mismatch, immutable record mismatch, creator/reviewer/source drift, corrupt packet, corrupt record, duplicate JSON key rejection, path-segment rejection, and orphan packet behavior. The central prepare assertion is:

```python
record, created = store.prepare(
    tenant_id="tenant-a",
    project_id="project-a",
    project_document_id="document-a",
    packet_content=packet["content"],
    packet_verification=verification,
    prepared_at="2026-09-03T00:00:00+00:00",
    creator_assignment=creator,
    reviewer_assignment=reviewer,
)
assert created is True
assert store.read_packet(record, tenant_id="tenant-a") == packet["content"]
```

- [x] **Step 2: Run local-store tests and confirm RED**

Run: `python3 -m pytest -q tests/storage/test_generated_document_review_store.py --tb=short`

Expected: collection failure because the store modules do not exist.

- [x] **Step 3: Implement closed record validation and immutable persistence**

Use a frozen dataclass whose serialized fields are exact. Validate all path segments before path construction. Store objects at:

```text
tenants/{tenant_id}/generated_document_reviews/packets/{packet_sha256}.zip
tenants/{tenant_id}/generated_document_reviews/projects/{project_id}/{project_document_id}/{packet_sha256}/record.json
```

`prepare()` must build and verify in memory, conditionally create packet bytes, require exact read-back, conditionally create canonical record JSON, accept only exact canonical replay, then read and validate both again. Never delete an orphan packet.

- [x] **Step 4: Add fake-S3 parity tests**

Extend `tests/test_state_backend.py` to prepare and re-read the same record through the fake S3 backend, including exact replay and packet mismatch rejection.

- [x] **Step 5: Run store suites and confirm GREEN**

Run: `python3 -m pytest -q tests/storage/test_generated_document_review_store.py tests/test_state_backend.py -k 'generated_document_review' --tb=short`

Expected: all selected local and fake-S3 tests pass.

- [x] **Step 6: Commit backend evidence persistence**

Stage only Task 1 and Task 2 files. Commit with a detailed bilingual `feat:` message explaining the additive packet schema, immutable conditional writes, replay semantics, affected storage paths, and test results.

---

### Task 3: Session-Bound Service And API

**Files:**
- Create: `app/schemas/generated_document_reviews.py`
- Modify: `app/schemas/__init__.py`
- Create: `app/services/generated_document_review_service.py`
- Create: `app/routers/projects/generated_document_reviews.py`
- Modify: `app/routers/projects/__init__.py`
- Modify: `app/main.py`
- Create: `tests/test_generated_document_reviews.py`
- Modify: `tests/test_infrastructure.py`

**Interfaces:**
- Consumes: `ProjectStore`, `UserStore`, Task 1 packet builder/verifier, Task 2 store, current session principal, and tenant dependency.
- Produces: strict `CreateGeneratedDocumentReviewRequest`; source fingerprint/projection helpers; create, inbox, project-history, and packet-download endpoints.

- [x] **Step 1: Write failing API creation and authorization tests**

Create a project, add a valid stored document, create active admin/member/viewer users, and issue real session tokens. Assert:

```python
response = client.post(
    f"/projects/{project_id}/documents/{document_id}/generated-reviews",
    headers=admin_headers,
    json={"reviewer": "member", "formats": ["docx", "pdf"]},
)
assert response.status_code == 200
assert response.headers["X-DecisionDoc-Review-Status"] == "pending"
assert response.headers["X-DecisionDoc-Review-Only"] == "true"
assert response.headers["X-DecisionDoc-Packet-Persisted"] == "true"
assert response.headers["X-DecisionDoc-Operational-Approval"] == "false"
```

Add denial cases for member-to-other assignment, viewer, API-key-only, Ops-key-only, sessionless, inactive/missing reviewer, cross-tenant project/document, malformed formats, invalid snapshot, and source identity drift.

- [x] **Step 2: Run creation tests and confirm RED**

Run: `python3 -m pytest -q tests/test_generated_document_reviews.py -k 'create or assignment or session' --tb=short`

Expected: `404` or missing-route failures.

- [x] **Step 3: Implement strict schema, identity resolution, and creation route**

Use:

```python
class CreateGeneratedDocumentReviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    reviewer: str = Field(min_length=1, max_length=254)
    formats: list[Literal["docx", "pdf", "xlsx", "hwp", "pptx"]] = Field(
        min_length=1, max_length=5
    )
```

Resolve creator and reviewer from the current `UserStore`, store stable IDs privately, parse `doc_snapshot` as a non-empty list of document objects, and compute a canonical SHA-256 over tenant/project/document/request/bundle/title/snapshot. Map format errors to `400`, missing scoped resources to `404`, unexportable or replay drift to `409`, and untrusted state to `503` without internal details.

- [x] **Step 4: Write failing inbox, history, freshness, and download tests**

Assert admin tenant scope, member assignment scope, newest-first pagination, only `pending`, source statuses `current|changed|missing`, no stable IDs in public payloads, exact packet bytes, and authorization before packet read. Confirm changed/missing packets remain downloadable and response headers include source status.

- [x] **Step 5: Run read-path tests and confirm RED**

Run: `python3 -m pytest -q tests/test_generated_document_reviews.py -k 'inbox or history or download or source_status' --tb=short`

Expected: missing endpoints or assertions fail.

- [x] **Step 6: Implement read paths and safe public summaries**

Expose:

```text
GET /generated-document-reviews?review_status=pending&limit=50&offset=0
GET /projects/{project_id}/generated-document-reviews
GET /projects/{project_id}/generated-document-reviews/{packet_sha256}/packet
```

Authorize the record before `read_packet()`. Compare each immutable record fingerprint with the current project document to derive freshness without rewriting the record. Response summaries must omit stable user IDs, session material, document bodies, packet entries, and storage paths.

- [x] **Step 7: Wire the store and audit fields**

Construct `GeneratedDocumentReviewStore(backend=state_backend, base_dir=data_dir)` in `create_app()`, register it at `app.state.generated_document_review_store`, include the project sub-router, and set request observability fields for action, project, document, packet hash, review status, access scope, and replay state only.

- [x] **Step 8: Run API and infrastructure tests and confirm GREEN**

Run: `python3 -m pytest -q tests/test_generated_document_reviews.py tests/test_infrastructure.py -k 'generated_document_review' --tb=short`

Expected: all selected tests pass.

- [x] **Step 9: Commit the complete backend API slice**

Stage only Task 3 files. Commit with a detailed bilingual `feat:` message covering session authorization, scoped query behavior, source freshness, re-download verification, app wiring, and focused tests.

---

### Task 4: Browser Creation, Project History, And Reviewer Inbox

**Files:**
- Modify: `app/static/index.html`
- Create: `tests/test_generated_document_review_ui_static.py`
- Modify: `tests/e2e/test_main_flow.py`

**Interfaces:**
- Consumes: Task 3 endpoints and response headers.
- Produces: project-document handoff action, immutable pending history, generated-document reviewer inbox tab, and verified packet download flow.

- [x] **Step 1: Write failing static contract tests**

Assert the HTML contains the exact API paths, visible copy `검토 증빙이며 운영 승인 아님`, all five canonical formats, required response-header checks, source-status warning copy, single-flight state, auth/request epoch checks, and object-URL revocation.

- [x] **Step 2: Run static tests and confirm RED**

Run: `python3 -m pytest -q tests/test_generated_document_review_ui_static.py --tb=short`

Expected: assertions fail because the browser controls are absent.

- [x] **Step 3: Implement browser state and rendering**

Add one generated-review state object with monotonically increasing request epoch and tracked object URLs. Render `검토 패킷 전달` only for documents with a request ID and snapshot. Add the creation dialog, project `문서 검토 전달` section, and generated-document inbox tab without changing the procurement review workflow.

- [x] **Step 4: Implement verified download and stale-response rejection**

Before creating a Blob require `application/zip`, exact `Content-Length`, packet and manifest SHA-256 headers, artifact count, `pending`, reviewer-bound, review-only, persisted, and all non-authorization headers. Recompute packet SHA in the browser. Reject stale auth revision, tenant, user, project, document, packet, or request epoch. Revoke tracked URLs on replacement and context reset.

- [x] **Step 5: Add Chromium workflow tests**

Exercise valid creation/download, duplicate-click single flight, pending inbox/history rendering, changed/missing confirmation, malformed headers, authority widening, logout, and project/document changes. Check desktop and 390 px viewports for horizontal overflow and overlapping controls.

- [x] **Step 6: Run browser tests and confirm GREEN**

Run:

```bash
python3 -m pytest -q tests/test_generated_document_review_ui_static.py --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k generated_document_review --browser chromium --tb=short
```

Expected: static and Chromium tests pass.

- [x] **Step 7: Commit the browser slice**

Stage only Task 4 files. Commit with a detailed bilingual `feat:` message covering the review-only copy, header/hash gate, stale-response protection, source warnings, responsive behavior, and tests.

---

### Task 5: Product Documentation And Portfolio Synchronization

**Files:**
- Modify: `README.md`
- Modify: `docs/product_direction.md`
- Modify: `docs/development-plan.md`
- Modify: `docs/roadmap.md`
- Modify: `_portfolio_export/decisiondoc_ai_portfolio_pack/README.md` through the pack sync command
- Modify: matching generated files reported by `python3 scripts/manage_portfolio_pack.py check`

**Interfaces:**
- Consumes: verified behavior and source-derived metrics from Tasks 1–4.
- Produces: public documentation that describes review handoff without claiming approval, human review completion, deployment, or production readiness.

- [x] **Step 1: Measure source-derived documentation facts**

Run `python3 scripts/count_readme_metrics.py --json` and the exact README-listed field commands. Record defined test counts separately from executed pass counts. Inspect route and environment-variable sources before changing tables.

- [x] **Step 2: Update product documents**

Document the new pending-only handoff, exact packet persistence, stable reviewer assignment, freshness warning, and explicit non-approval boundary. Keep completion/reassignment/notifications and provider/AWS execution in `Scope & Limitations` or future roadmap.

- [x] **Step 3: Synchronize the portfolio pack**

Run: `python3 scripts/manage_portfolio_pack.py sync`

Then run: `python3 scripts/manage_portfolio_pack.py check`

Expected: check exits zero and reports no drift.

- [x] **Step 4: Run README honesty scans**

Run:

```bash
rg -n '99\.8|94\.2|production-ready|enterprise|상용 운영|엔터프라이즈' README.md _portfolio_export/decisiondoc_ai_portfolio_pack/README.md
python3 scripts/count_readme_metrics.py --json
```

Expected: no unsupported claims; metric check passes.

- [x] **Step 5: Commit documentation as part of final verified feature commit**

Tasks 1-5 are intentionally grouped into one verified feature commit so packet,
store, API, browser, tests, source-derived documentation, and portfolio evidence
remain reviewable as one behavioral unit.

Keep documentation with the verification or browser group if no independent reviewer boundary justifies another commit.

---

### Task 6: Final Verification And Review

**Files:**
- Review: all changed files from Tasks 1–5

**Interfaces:**
- Consumes: complete implementation.
- Produces: decisive local verification evidence and a clean scoped diff ready for user review.

- [x] **Step 1: Run focused backend gate**

Run:

```bash
python3 -m pytest -q \
  tests/test_generation_export_packet.py \
  tests/storage/test_generated_document_review_store.py \
  tests/test_generated_document_reviews.py \
  tests/test_infrastructure.py -k generated_document_review --tb=short
```

- [x] **Step 2: Run focused browser gate**

Run:

```bash
python3 -m pytest -q tests/test_generated_document_review_ui_static.py --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k generated_document_review --browser chromium --tb=short
```

- [x] **Step 3: Run full local quality gate**

Run:

```bash
python3 -m pytest tests/ -m "not live" -q
ruff check app/ tests/ --select=E,F,W --ignore=E501
python3 scripts/check_secret_hygiene.py
python3 scripts/manage_portfolio_pack.py check
git diff --check
```

- [x] **Step 4: Review the diff from independent angles**

Check contract compatibility, tenant/auth isolation, immutable persistence/CAS behavior, artifact-before-authorization ordering, error disclosure, browser stale-response handling, source-derived docs, and unrelated-diff exclusion. Fix findings with a fresh RED-to-GREEN cycle.

- [x] **Step 5: Inspect commit and worktree state**

Run: `git status --short --branch && git log --oneline --decorate -5`

Expected: only intentional files remain, commits are grouped by coherent feature boundary, and no push/merge/deploy has occurred.

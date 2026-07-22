# DecisionDoc AI Product Direction

Updated: 2026-06-23

This document defines the product direction for DecisionDoc AI. It is an internal planning artifact, not a public performance claim or launch announcement.

Execution plan: [DecisionDoc AI Product Execution Plan](./product_execution_plan.md).

## 1. Product Thesis

DecisionDoc AI should become a decision documentation system for high-stakes work.

The product should not be positioned as only an AI writing tool. Its stronger position is:

> Generate, review, and approve important decision documents with evidence traceability, human review, and explicit operational boundaries.

In practical terms, DecisionDoc AI should help teams answer:

- What decision are we making?
- What evidence supports it?
- What risks or gaps remain?
- Who reviewed it?
- What is approved, and what is explicitly not approved?

## 2. Core Positioning

### Primary positioning

DecisionDoc AI is an evidence-backed document operations platform for teams that need traceable decision packages, review workflows, and exportable business documents.

### Short positioning

DecisionDoc AI helps teams create, review, and hand off decision documents with evidence and approval boundaries attached.

### What this means

- Document generation is the entry point.
- Evidence tracking is the trust layer.
- Review and sign-off are the workflow layer.
- Export and handoff are the operational layer.

## 3. Initial Wedge

The first strong wedge should be:

> Public procurement and proposal decision workflows for teams that need go/no-go judgment, bid-readiness checks, and reviewable decision packages.

This wedge fits the current repository because DecisionDoc AI already has relevant surfaces:

- project and document workflows,
- provider and storage abstraction,
- procurement copilot specifications,
- approval and sign-off artifacts,
- export-oriented document generation,
- local no-cost and no-training evidence chains.

## 4. Ideal Initial Users

### Proposal or business development lead

Needs:

- quick opportunity triage,
- go / conditional go / no-go recommendation,
- missing evidence and readiness gaps,
- decision package for internal review.

### Delivery lead or project manager

Needs:

- delivery feasibility review,
- staffing and partner readiness check,
- scope and schedule risk notes,
- structured handoff into proposal or execution planning.

### Executive or compliance reviewer

Needs:

- concise recommendation,
- evidence-backed risk view,
- approval boundary,
- audit-friendly review record.

## 5. Product Principles

1. Evidence before prose.
   Generated language is useful only when the source evidence and uncertainty are preserved.

2. Human approval remains final.
   AI can recommend and summarize. It must not become the final approver.

3. Boundaries must be explicit.
   Service resume, provider calls, dataset upload, training, model promotion, and operational changes require separate approval paths.

4. Deterministic checks come before LLM narrative.
   Hard filters, schema validation, source hashes, and readiness checks should run before narrative generation where possible.

5. Local-safe mode matters.
   Mock provider, local storage, no-cost evidence generation, and no-training workflows are product strengths, not temporary scaffolding.

6. Provider abstraction should remain.
   OpenAI, Gemini, and mock providers should stay behind a stable provider contract.

7. Local automation contracts should be explicit.
   Local evidence commands should return versioned stdout JSON contracts, with `status: "passed"` for successful runs and `status: "failed"`, `error_type`, and `error` for handled failures. The current procurement decision package local demo records this in `cli_contract_manifest.json`, validates it with `validate_procurement_decision_package_cli_contract_manifest.py`, and checks persisted receipts with `check_procurement_decision_package_cli_contract_manifest_result.py`. The manifest validation output includes `contract_version` and can be persisted with `--write-result --result-path`.

8. Export is part of the product.
   The final artifact should be useful as DOCX, PDF, PPTX, XLSX, ZIP, Markdown, or JSON depending on workflow needs.

9. Scope honesty is mandatory.
   Planning docs, README, sales docs, and portfolio docs must separate implemented, validated, planned, and unverified capabilities.

10. Current context owns interactive evidence.
    When browser operations overlap, only the latest tenant-bound request may replace the visible result. Earlier operations that completed a durable side effect must remain observable without rewriting the user's current filters or evidence panel.

## 6. Product Pillars

### Pillar 1: Decision Package Generation

Create structured document bundles from requirements, source documents, procurement opportunities, or project knowledge.

Expected artifacts:

- decision memo,
- ADR,
- one-pager,
- evaluation plan,
- ops checklist,
- bid-readiness checklist,
- procurement go/no-go package,
- proposal or execution handoff.

### Pillar 2: Evidence and Traceability

Every generated package should preserve the evidence relationship.

Expected capabilities:

- source file references,
- extracted requirements,
- hard-filter findings,
- score or readiness breakdowns,
- source hashes for local governance artifacts,
- uncertainty notes,
- validation result summaries.

### Pillar 3: Review and Sign-Off

DecisionDoc should support human-in-the-loop review without confusing review evidence with operational approval.

Expected capabilities:

- pending review records,
- completed review records,
- sign-off validation,
- summary reports,
- handoff packages,
- closure receipts,
- explicit no-resume and no-training boundaries.

### Pillar 4: Workflow Handoff

Decision output should feed downstream work.

Expected handoffs:

- procurement decision to proposal draft,
- proposal draft to reviewer packet,
- reviewed packet to export package,
- release or ops decision to operator checklist,
- quality correction to training approval workflow only when separately authorized.

### Pillar 5: Operational Trust

The system should make it hard to accidentally perform external or costly actions.

Expected controls:

- mock-provider default path,
- local-only evidence workflows,
- versioned CLI contract manifests for local automation,
- explicit provider-call mode,
- explicit training approval records,
- deployment and production verification gates,
- audit-friendly operational logs.

## 7. Near-Term Product Shape

### Now

Focus on a narrow, demonstrable workflow:

1. Import or define an opportunity, requirement, or decision topic.
2. Attach or reference supporting documents.
3. Generate a decision package.
4. Show evidence and gaps.
5. Generate reviewer handoff.
6. Create pending sign-off.
7. Validate completed review.
8. Export the final package.

### Current reviewer foundation

- DocumentOps now presents training governance, selected-backend artifact integrity, and reviewer sign-off through one read-only review overview. The service preserves the three source reports, prioritizes boundary drift before artifact, governance, and sign-off issues, and gives the reviewer one next action. Stable source fingerprints let the browser label a same-tenant recheck as first, unchanged, or changed without persisting the comparison. When a browser action changes an export, freeze, dry-run approval, execution request, pre-execution audit, provider, or model selection, the open overview becomes an explicitly stale previous observation until a new overview request succeeds. Trajectory Stats, the task-filtered Reviewed SFT export list, Training Readiness, and Training Execution Request Records keep only the latest same-tenant response, so an older success or error cannot roll back current counts, artifact rows, the freeze exposed for dry-run approval, or the latest two-person guard record. A successful execution request refresh also supersedes a read that started before the save. Training Audit Checklist binds its result to the latest request, tenant, and provider/model query. A planning change removes the previous audit action until recheck, and a completed audit export cannot be hidden by an older in-flight read. Training Adapter Contract and Training Execution Rehearsal independently bind their result to the latest request, tenant, and provider/model query. A planning change replaces their previous configuration and artifact evidence with an explicit recheck state, so an old safe result cannot describe the current selection. SFT Export Preview and the reviewed artifact list are bound to the task selection that started their request, while Training Plan Preview is bound to its exact provider/model query; input changes invalidate both in-flight and open evidence. The combined view remains explicitly non-atomic and grants no dataset upload, provider, training, job, or model-promotion authority.
- DocumentOps browser controls that create governance records or start a provider-backed Agent request are single-flight while pending. Freeze, dry-run approval, execution request, and audit export send a per-action UUID that the backend binds to a private canonical payload hash. Exact replays return the original verified governance artifact and changed-payload reuse returns `409`. Captured Agent runs also send an operation identity, but claim it in a separate private shared-backend receipt before provider execution; exact replay returns the saved result without another provider or usage event, while running, failed, changed, or corrupt state fails closed. A tenant-scoped read-only status route exposes only retry-decision fields and records a redacted audit entry. After a lost response, the browser validates the status schema, exact operation identity, state fields, read-only flag, and provider-call denial before acting. Mismatched, unavailable, or running state keeps the captured tenant and payload only in page memory; the main Agent button and explicit status recheck share one recovery promise and do not start a new operation. Only verified success replays the original payload. Before a captured POST, the browser writes only schema version, tenant ID, and operation ID to a tenant-scoped same-origin storage key and, where available, serializes the claim with a tenant-scoped Web Lock. Nearly simultaneous tabs therefore converge on one POST; another tab or a page reopened after the owner tab closes follows the marker with a no-cache status read and blocks a new POST. Different tenant markers coexist without foreign reads, writes, or cleanup deleting each other, and H96 base-key markers remain owner-readable for compatibility. Login, registration, refresh, and LDAP login first validate token claims, then commit access/refresh credentials and the signed tenant through one browser helper. A failed write restores the previous session and leaves current user and DocumentOps evidence unchanged. The 401 recovery path distinguishes a refreshed session, rejected refresh credential, temporary endpoint failure, browser storage failure, and a superseded response. Concurrent callers join one refresh promise. Generic mutating requests are never replayed automatically after refresh. Current-tab commits and same-origin auth storage changes advance a monotonic session revision, so a late response cannot overwrite a newer session even when the replacement reuses the same refresh-token bytes; unrelated storage keys do not invalidate refresh. Only explicit credential rejection clears session evidence; temporary and storage failures keep the prior session and unsaved work available for a later retry. An authorized switch also persists the next tenant before clearing previous-context evidence, so storage failure leaves the current tenant, draft, recovery promise, and marker untouched. Payload is never persisted, so these paths cannot exact-replay. Explicit release requires confirmation that backend execution is not canceled and evidence still needs review. Invalid markers and current auth-context termination clear the applicable marker. Shared storage failure falls back to tenant-scoped tab storage, while failure of both stores preserves only same-page execution. Governance artifacts can still leave a CAS-loser orphan, and Agent receipts do not provide cross-device coordination, atomic simultaneous claims without Web Locks, process-crash recovery, semantic deduplication across different IDs, exactly-once execution, or automatic GC.
- A receiving tab reconciles same-origin auth changes against the final signed user, tenant, and role. Same-identity and same-role token rotation invalidates any older refresh but keeps the current page and unsaved work. A different user, tenant, role, or logged-out session requests one reload so current user, review drafts, pending recovery state, and visible controls are rebuilt under the new authorization context. Protected requests and new SSE subscriptions also resolve the signed identity against current tenant user state, so role changes take effect before token expiry and inactive users cannot reuse an existing token. Browser storage remains coordination evidence rather than authorization authority; an administrator-wide revocation table and cross-device push coordination are not provided.
- Password rotation is the exception to quiet same-identity token replacement: password hash and persisted credential version advance together, every older access/refresh token is rejected, the initiating browser commits a replacement pair, and another same-origin tab reloads when its version is stale. New token pairs also share a persisted tenant-scoped session identity. Exact logout revokes only that session, while separate logins remain active; copied same-session credentials fail on the next protected request, refresh, or open SSE recheck. The profile can list active current-version sessions, revoke one owned non-current login, preserve the current browser while revoking the other sessions in a validated snapshot, or revoke that snapshot including current. The all-device path validates the full prefix before mutation and writes current last, so an earlier backend failure preserves the initiating browser when possible. Bulk writes remain sequential rather than transactional: partial other-session progress can survive a failure, a lost current-write response can leave the server revoked before browser cleanup, and a session created after the snapshot remains for the next inspection. The browser exposes only current/other and start/expiry times, keeps session IDs out of the DOM, and applies one single-flight plus stale token/modal/request/revoke generations to every action. It clears local credentials and page-memory evidence only after confirmed all-device success. Audit stores the bulk count without tokens or session IDs. An open SSE connection rechecks the same token and current user/session authority at most every 15 seconds. This is bounded invalidation, not immediate cross-device push or a termination guarantee shorter than the recheck interval. Legacy sessionless tokens cannot use exact logout, inventory, selected revoke, or either bulk revoke; User-Agent/IP inventory, administrator mass revoke, and expired-session GC are not included.
- The project procurement surface connects a tenant-resolved recommendation directly to a verified review packet download. The server reuses the local package contract, returns packet identity and SHA256 evidence, and keeps operational approval false.
- The same project surface now persists the original packet and pending receipt under the tenant, project, and packet SHA256 boundary; it exposes pending and completed review history without creating a second approval workflow.
- A tenant-scoped review inbox now gathers pending and completed records across projects, supports project or reviewer lookup, opens the existing project detail workflow, and reuses verified completed-package downloads without exposing tenant identifiers or receipt internals.
- A reviewer can record `accepted`, `changes_requested`, or `rejected` exactly once. Completion rebuilds the current decision packet to reject stale source state, creates and independently verifies the deterministic reviewed package, and keeps it available for verified re-download.
- Current completed review evidence now follows `rfp_analysis_kr`, `proposal_kr`, and `performance_plan_kr` generation without becoming a new gate. The service compares the review packet source timestamp with the current procurement record, skips stale evidence, and preserves packet SHA256, review decision, reviewed time, and `operational_approval: false` on generated project documents.
- Project detail recalculates each review-bound document against the current tenant's packet record and procurement update time. Current, stale, missing, and invalid evidence remain visible; stale or unverifiable documents require an explicit confirmation before approval or sharing. Project-linked shares preserve that share-time baseline, while every public view resolves the current tenant-scoped source again and records any post-share drift in audit history. Admin procurement review surfaces turn those drift observations into a unique-link queue with separate creation and latest-risk timestamps, so repeated public views improve recency evidence without exaggerating exposure volume. A later current observation closes only that link's queue exposure and records the recovered-link count without deleting its audit history. Link revocation preserves actor and time evidence, natural expiry remains distinct, and document-level queue selection keeps another active link visible even when a newer sibling link has already closed.
- A project-linked approval preserves its request-time council and procurement-review snapshot, while approval detail and final approval resolve the current tenant-scoped source document again. Non-current evidence requires explicit final acknowledgement, recorded with actor and time in both the approval record and audit history.
- `procurement_review.html` provides one script-free view for package, evidence, gaps, and sign-off state.
- The procurement review packet packages the validated 12-artifact directory as a deterministic ZIP with embedded `packet_manifest.json`.
- Packet status stays `review_ready`; `operational_approval` remains false and independent verification rejects path, fingerprint, membership, and semantic drift.
- `manage_procurement_review_receipt.py` keeps `procurement_review_receipt.json` outside the packet, binds it to `packet_sha256`, and records one requested-reviewer decision through a validated `review_status` transition.
- `manage_procurement_reviewed_package.py` exports the unchanged packet and completed receipt as a deterministic review-completed audit envelope while preserving the same non-authorization boundary.
- Validation summaries and authorization boundaries remain visible to non-engineering reviewers.

### Next

Connect this local reviewer foundation to explicitly approved external evaluation lanes without weakening the local evidence contract.

### Later

Expand into higher-leverage workflows:

- procurement go/no-go,
- proposal readiness,
- compliance review,
- release decision review,
- model-training approval review,
- customer-specific document operations.

## 8. Product Surface Priorities

Priority order:

1. Reviewable decision package.
2. Evidence and validation summary.
3. Reviewer sign-off workflow.
4. Export bundle.
5. Procurement-specific scoring and bid readiness.
6. Admin and audit console.
7. External provider and deployment polish.

This order matters. A polished generator without evidence and review boundaries would weaken the product's strongest differentiation.

## 9. What To Stop Doing

Stop treating phase accumulation as the product itself.

The phase chain is useful as local governance evidence, but the user-facing product should be simpler:

- package,
- evidence,
- validation,
- review,
- export,
- handoff.

Stop expanding into unrelated document categories until the first high-stakes workflow is clear.

Stop describing unverified deployment, customer, or performance outcomes as completed product facts.

## 10. What To Build Next

### Product artifact

Create a thin "Decision Package" abstraction that can contain:

- generated documents,
- structured decision data,
- source evidence,
- validation results,
- reviewer status,
- export metadata.

### Workflow artifact

Create a reviewer console or CLI summary that answers:

- Is the package valid?
- What evidence was used?
- What is missing?
- Who needs to review?
- Is this only review evidence, or does it authorize an operational action?
- Can the local evidence path be verified from a versioned `contract_version` manifest and persisted validation receipt?

### Procurement artifact

Connect the public procurement copilot into the package workflow:

- opportunity import,
- hard filters,
- soft-fit score,
- bid-readiness checklist,
- go / conditional go / no-go recommendation,
- proposal handoff.

Current connection status: opportunity, recommendation, hard filters, score, checklist, reviewer ownership, deterministic review packet export, packet-bound receipt completion, completed review history, verified reviewed-package re-download, current-review downstream provenance, and redacted DocumentOps governance read-access audit are connected. Any explicitly approved external evaluation lane remains a separate follow-up workflow.

## 11. Decision Checklist For Future Work

Before adding a feature, answer:

- Does this improve package generation, evidence traceability, review, export, or operational trust?
- Can it run in mock/local mode?
- Does it preserve provider and storage abstraction?
- Does it require explicit approval before external cost, training, deployment, or service resume?
- Is the output inspectable by a non-engineering reviewer?
- Is the claim backed by code, tests, logs, or clearly marked as planned?

If the answer is no for most of these, defer the feature.

## 12. Scope And Limitations

This direction does not claim:

- active customer adoption,
- verified production deployment,
- measured business impact,
- automated legal or compliance judgment,
- automatic bid submission,
- autonomous operational approval,
- training execution approval.

Those claims require separate evidence before they appear in public-facing material.

## 13. Working Narrative

DecisionDoc AI should be described as follows:

> DecisionDoc AI turns source material and project context into reviewable decision packages. It keeps evidence, validation, reviewer sign-off, and operational boundaries attached so teams can move from draft to decision without losing traceability.

This narrative should guide roadmap, README, UI, demo, and implementation priorities.

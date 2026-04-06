# IMPLEMENT — Execution Runbook for Codex

## 1. Operating mode

This initiative must be executed milestone-by-milestone.

Before each coding pass:
1. read `AGENTS.md`
2. read `docs/specs/public_procurement_copilot/PRD.md`
3. read `docs/specs/public_procurement_copilot/PLAN.md`
4. read `docs/specs/public_procurement_copilot/IMPLEMENT.md`
5. read `docs/specs/public_procurement_copilot/STATUS.md`

If this is the first run for the initiative, do **Milestone 0 only**.

---

## 2. Decisions already fixed

These are already decided and should not be reopened unless the repository makes them impossible:

1. Build the capability inside DecisionDoc AI.
2. Reuse the current project/workspace model.
3. Reuse current document generation and export flows.
4. Reuse current G2B integration instead of inventing a new source path.
5. Reuse current attachment / RFP parsing where possible.
6. Reuse current knowledge document infrastructure for capability profile input.
7. Preserve current provider abstraction.
8. Preserve local and S3 storage abstractions.
9. Keep `mock` provider deterministic and working.
10. Use deterministic hard filters before narrative generation.
11. Recommendation values are:
    - `GO`
    - `CONDITIONAL_GO`
    - `NO_GO`
12. The checklist must exist as:
    - structured machine-readable data
    - human-readable document content
13. New bundle id is:
    - `bid_decision_kr`
14. Downstream handoff targets are:
    - `rfp_analysis_kr`
    - `proposal_kr`
    - `performance_plan_kr`
15. Rollout should prefer feature flagging:
    - `DECISIONDOC_PROCUREMENT_COPILOT_ENABLED`

---

## 3. Repository discovery rule

Do not trust assumptions over the actual codebase.

Milestone 0 must identify:
- exact route modules
- exact service-layer extension points
- exact bundle registration path
- exact project-linking pattern
- exact knowledge document pattern
- exact export path reuse point
- exact persistence shape already used by the platform
- exact testing and smoke patterns

If any assumption in PRD or PLAN is wrong:
- update `STATUS.md`
- make the smallest valid correction
- continue with the corrected implementation path

---

## 4. Preferred implementation shape

Unless the real repository strongly suggests a better existing pattern, prefer the following shape:

- project-scoped procurement decision service layer
- normalized internal opportunity structure
- structured recommendation payload
- structured checklist payload
- raw source snapshot retention
- additive route integration under existing project or procurement patterns
- bundle generation through current bundle registry and export pipeline
- downstream handoff through structured context, not duplicated free-form prompts
- tests and eval fixtures added alongside the feature

---

## 5. Integration rules

## 5.1 Project integration
Prefer attaching procurement decision state to existing project context.
Do not create a separate workspace concept.

## 5.2 G2B integration
Reuse existing G2B search and selection behavior.
Only add the minimum attach/import step needed for project linkage.

## 5.3 RFP and attachment integration
Reuse existing attachment / parse-RFP flows.
If parsed signals already exist, consume them instead of reparsing in a new subsystem.

## 5.4 Knowledge and capability profile integration
Use current knowledge document flows as the first source of company capability data.
If structured capability input is missing, introduce the lightest-weight document/template path that fits current patterns.

## 5.5 Bundle integration
Register the new decision-stage bundle through the current bundle registry conventions.
Do not create a parallel templating or export subsystem.

## 5.6 Approval/share/history/audit integration
Reuse existing platform controls and traces.
Do not create procurement-specific parallel approval logic for v1.

---

## 6. Decision engine rule

The recommendation engine must operate in two layers.

### Layer 1 — Deterministic layer
This layer must:
- normalize opportunity data
- resolve capability profile
- run hard filters
- compute weighted soft-fit score
- identify missing data
- preserve structured outputs

### Layer 2 — Generated explanation layer
This layer may use the provider to generate:
- executive recommendation summary
- evidence narrative
- remediation notes
- checklist language
- proposal kickoff summary

Model-generated text must not be the sole source of truth for the decision.
The structured result remains authoritative.

---

## 7. Checklist rule

The checklist must support the following required categories:
- eligibility and compliance
- certifications and licenses
- domain capability fit
- reference cases and proof points
- staffing and partner readiness
- schedule and deadline readiness
- deliverables and scope clarity
- security / data / infrastructure obligations
- pricing / budget / contract risk
- executive approval / internal readiness

Each checklist item should preferably support:
- category
- title
- status
- severity
- evidence
- remediation note
- optional owner
- optional due date

The checklist must be preserved in structured form for downstream reuse.

---

## 8. Bundle rule

The new bundle `bid_decision_kr` should generate four artifacts:
1. Opportunity Brief
2. Go/No-Go Memo
3. Bid Readiness Checklist
4. Proposal Kickoff Summary

Rules:
- use the existing bundle registry
- use the existing generation pipeline
- use the existing export pipeline
- keep documents project-linked
- preserve structured metadata for reuse

---

## 9. Downstream handoff rule

If decision is `GO` or `CONDITIONAL_GO`, preserve structured context for downstream bundle generation.

The downstream path should not force users to manually re-enter:
- opportunity basics
- key requirements
- fit rationale
- key risks
- missing items
- readiness signals
- RFP-derived signals
- suggested proposal focus points

## 9.1 Decision Council v1 rule

Decision Council v1 is an additive pre-generation step, not a second orchestration product.

Rules:
- procurement/G2B projects only
- API-first proposal-first slice
- deterministic synthesis only
- no provider debate or multi-agent chat shell
- store one canonical latest council session per:
  - `project_id`
  - `use_case`
  - `target_bundle_type`
- keep the canonical stored session keyed to `target_bundle_type=bid_decision_kr`
- reuse that same canonical session for:
  - `bid_decision_kr`
  - `proposal_kr`
- inject only when the latest council session is still bound to the current procurement state:
  - current project procurement record must still have `opportunity` + `recommendation`
  - `source_procurement_decision_id` must match
  - `source_procurement_updated_at` must match
- expose the same freshness contract back to callers:
  - `GET /projects/{project_id}/decision-council` should explicitly mark the latest saved council as `current` or `stale`
  - `GET /projects/{project_id}/decision-council` should also return `supported_bundle_types=["bid_decision_kr","proposal_kr"]`
  - the project-detail procurement panel should block council-assisted generation when the latest saved council is stale and require rerun first
  - the existing project document list should also label council-backed `bid_decision_kr` / `proposal_kr` rows against that same freshness contract so operators can tell whether a saved document is current, from an older council revision, or from a council that is now stale against procurement state
  - `GET /projects/{project_id}` should expose the same document-level freshness metadata for council-backed `bid_decision_kr` / `proposal_kr` rows so non-browser callers do not have to re-derive that status themselves
  - when a council-backed project document is shared, the shared-document page should preserve the same stale/current warning contract instead of implying that the shared link is always current
- expose the same outcome in generation metadata:
  - when council handoff is applied, keep `decision_council_handoff_used=true`
  - when the latest saved council is skipped because procurement state changed, return `decision_council_handoff_used=false` and `decision_council_handoff_skipped_reason=stale_procurement_context`
  - keep `decision_council_target_bundle=bid_decision_kr` as the stored session source and add `decision_council_applied_bundle` for the actual current generation target
- keep procurement structured state authoritative; council output refines direction and drafting handoff, not the underlying decision record
- preserve existing approval/share/export flow unchanged

Do not:
- add a transcript store
- add a new review or approval layer for council
- widen this into generic mission/council/execution runtime work

### 9.1.a Local stale-share demo helper

For local operator verification, prefer the dedicated launcher/seed helpers instead of hand-editing tenant files.

Fastest runbook:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py
```

This one command:
- starts a local FastAPI app on `127.0.0.1:8765`
- seeds one deterministic stale-share scenario into a fresh `DATA_DIR`
- verifies the live app against that seeded state
- writes `procurement-stale-share-demo.json` into the chosen `DATA_DIR`
- keeps the server running for manual checks until interrupted

Optional browser assist:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --open-browser
```

This opens the focused internal review URL and the exact public share URL after verification succeeds.

Optional browser playtest:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --playtest-ui --exit-after-verify
```

This Playwright helper:
- logs in with the seeded admin account
- opens the stale-share review from the authenticated app shell
- retries through re-login and modal-visibility fallbacks when that browser path still loses state
- verifies the stale `proposal_kr` review focus, Decision Council panel, disabled proposal regenerate CTA, and public shared-page warning

Current note:
- the helper is unit-covered and the live `--playtest-ui` launcher path is now green in this workspace
- use `--playtest-ui --exit-after-verify` as the fast local browser gate for the seeded proposal-first stale-share demo
- use `--open-browser` when you want to inspect the focused review URL and public share page manually after the automated browser pass

CI-style verification only:

```bash
.venv/bin/python scripts/run_procurement_stale_share_demo.py --port 8876 --data-dir /tmp/decisiondoc-stale-share-demo-ci --exit-after-verify
```

Local procurement live smoke helper:

```bash
G2B_API_KEY=... \
JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars \
SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00 \
.venv/bin/python scripts/run_local_procurement_smoke.py
```

File-based variant:

```bash
cp scripts/local_procurement_smoke.env.example /tmp/local_procurement_smoke.env
$EDITOR /tmp/local_procurement_smoke.env
JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars \
.venv/bin/python scripts/run_local_procurement_smoke.py --env-file /tmp/local_procurement_smoke.env
```

Notes:
- this helper starts a fresh local app and then runs `scripts/smoke.py` with `SMOKE_INCLUDE_PROCUREMENT=1`
- it auto-wires a local API key and local ops key so the NO_GO remediation summary path can still be verified without requiring an admin smoke user
- add `--keep-running` if you want the local app to remain up after the smoke pass
- add `--preflight` when you want a fail-fast readiness check for `G2B_API_KEY` and `SMOKE_PROCUREMENT_URL_OR_NUMBER`
- add `--print-env-template` when you want a copy-paste export block plus the exact run command
- keep the inline `JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars` prefix on the file-based path; that is the validated local launch form in this workspace
- the Python runner still accepts `--env-file`, and the env file continues to carry the procurement target and optional smoke credentials
- the runner defaults `JWT_SECRET_KEY` to a validated local secret and still lets the shell or env file override it when a different local auth context is needed

Manual split runbook:

Runbook:

```bash
DEMO_DIR=/tmp/decisiondoc-stale-share-demo
DATA_DIR="$DEMO_DIR" DECISIONDOC_PROCUREMENT_COPILOT_ENABLED=1 .venv/bin/uvicorn app.main:app --port 8765 --reload
```

In a second shell:

```bash
DEMO_DIR=/tmp/decisiondoc-stale-share-demo
DATA_DIR="$DEMO_DIR" .venv/bin/python scripts/seed_procurement_stale_share_demo.py --data-dir "$DEMO_DIR" --base-url http://127.0.0.1:8765
```

Then verify the live app against that seeded state:

```bash
.venv/bin/python scripts/check_procurement_stale_share_demo.py --base-url http://127.0.0.1:8765
```

Rules:
- use a fresh empty `DATA_DIR`
- the helper seeds:
  - system admin user
  - one shared Decision Council session reused by both a council-backed `bid_decision_kr` document and a council-backed `proposal_kr` document
  - one stale procurement update that makes the saved council outdated
  - one active stale public share on the council-backed `proposal_kr` document with one public access
  - one clean contrast tenant for locations-card sorting
- use the printed focused review URL and public share URL as the primary manual validation entrypoints
- the verifier is intentionally narrow:
  - login
  - locations overview stale-share exposure
  - focused stale-share procurement summary
  - stale Decision Council binding
  - public shared page warning
- the launcher is intentionally thin orchestration:
  - local `uvicorn`
  - `/health` wait
  - seed helper function reuse
  - verifier helper function reuse
  - manifest write for manual handoff
  - optional browser open for exact review/public URLs
  - optional keep-running for manual UI checks
- do not widen this helper into a generic fixture loader or long-lived demo environment manager
- bypass existing project-scoped provenance or audit behavior

---

## 10. Anti-patterns

Do NOT:
- create a standalone procurement app
- create a second document system
- create a second project/workspace concept
- create a second approval workflow
- add provider-specific logic to routers
- call the model before deterministic hard filters run
- rely on prose-only recommendations with no structured backing data
- make destructive schema changes for v1
- broaden scope beyond the current milestone
- hide repository deviations without updating `STATUS.md`
- break `mock` provider flows
- couple the feature to only one storage backend

---

## 11. Validation rule

After each milestone:
1. run targeted tests for the changed area
2. run `pytest tests/ -q`
3. run repository lint/type-check commands if already configured
4. update `STATUS.md`
5. stop if validation fails

If new routes, services, or bundles are introduced, add corresponding tests where the repository pattern supports them.

If the repository has smoke scripts relevant to the touched flow, run them as appropriate.

---

## 12. Documentation rule

`STATUS.md` is the execution log for this initiative.

Update it after each milestone with:
- what changed
- where it changed
- validations run
- deviations discovered
- open risks
- next milestone

Do not leave major implementation decisions undocumented if they change the original assumptions.

---

## 13. If the repository differs from the spec

When the actual repository differs from this runbook:
1. inspect the real code path,
2. prefer the real codebase,
3. update `STATUS.md`,
4. make the smallest valid adjustment,
5. continue milestone-by-milestone.

Do not rewrite the architecture just to match the initial draft.

---

## 14. Preferred first command for Codex

The first execution should be discovery-only.

Recommended first instruction:

Read `AGENTS.md` and `docs/specs/public_procurement_copilot/{PRD,PLAN,IMPLEMENT,STATUS}.md`.
Do not implement yet.
Perform Milestone 0 only: inspect the current repository, map the exact integration points, update `STATUS.md` with the real file map and any minimal plan corrections, then stop.

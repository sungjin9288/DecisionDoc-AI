# Status: Hermes-Inspired DocumentOps Agent

## Current State

Research and architecture planning are complete. Phase 1 DocumentOps agent skeleton, Phase 2 trajectory persistence/export foundation, Phase 3 QA gates/evaluation rubric, Phase 4 internal API/service integration, the first DocumentOps UI surface, Phase 5 browser QA for SFT export inspection/export, Phase 6 secure export artifact list/download, Phase 7 live-provider pilot capture/export, Phase 8 offline dataset quality reporting, Phase 9 dataset freeze manifesting, Phase 10 dry-run model-training approval gates, Phase 11 read-only training readiness summary, Phase 12 training execution plan preview, Phase 13 two-person training execution request records, Phase 14 final pre-execution audit checklist/export, Phase 15 read-only training governance dashboard summary, Phase 16 provider adapter contract stub, Phase 17 dry-run provider execution rehearsal, Phase 18 local browser QA checklist/evidence artifact, Phase 19 observed local browser governance QA pass, Phase 20 release handoff index/manifest packaging, Phase 21 manual reviewer sign-off record template, Phase 22 local sign-off record validator, Phase 23 pending sign-off record generator, Phase 24 local sign-off summary reporting, Phase 25 ops-key sign-off summary endpoint/UI, Phase 26 observed local browser sign-off summary QA, Phase 27 ops-key reviewer sign-off JSON download, Phase 28 observed local browser sign-off JSON download QA, Phase 29 reviewer sign-off release handoff refresh, Phase 30 operator reviewer sign-off packet guide, Phase 31 tenant-local reviewer sign-off import helper, Phase 32 observed browser QA for imported sign-off records, Phase 33 operator release packet summary, Phase 34 staging-readiness dry-run probe, Phase 35 observed staging probe evidence archive, Phase 36 observed probe execution workflow, Phase 37 deployed probe failure evidence, Phase 38 observed probe retry evidence, Phase 39 remote runtime gap evidence, Phase 40 production sign-off completion evidence, Phase 41 production post-deploy smoke evidence, and Phase 42 production browser UAT evidence have been implemented as DecisionDoc-native work. Hermes is still not installed as a dependency.

## Completed

- Reviewed Hermes Agent repository.
- Reviewed DecisionDoc provider, generation, fine-tune, and storage seams.
- Confirmed Hermes license is MIT.
- Confirmed direct production import is not the recommended first step.
- Defined DecisionDoc-native architecture path.
- Defined training and trajectory plan.
- Defined phased implementation plan.
- Added `app/agents` package with a curated Markdown skill registry.
- Added `DocumentOpsAgent` that calls existing DecisionDoc providers through `generate_raw()`.
- Added three first-party skills: policy planning, evidence gap review, and decision brief building.
- Added deterministic unit tests for skill loading, mock-provider prompting, evidence warnings, fallback warnings, provider-error propagation, preferred skill selection, trajectory metadata, and trajectory persistence from the agent.
- Added tenant-scoped `TrajectoryStore` for rich JSONL trajectory persistence.
- Added human-review metadata updates for accepted/rejected trajectories.
- Added SFT-compatible JSONL export for reviewed/accepted trajectories.
- Added redaction for raw attachments, base64/file bytes, source document text, and long input text before trajectory storage/export.
- Added deterministic DocumentOps hard gates for forbidden terms, unsupported confirmed claims, overconfident claims with open gaps, missing governance/privacy/security review, missing output body, and missing plan.
- Added rubric scoring for policy logic, evidence grounding, public-sector tone, implementation detail, and artifact readiness.
- Updated `DocumentOpsAgent` local QA to reuse the same gate result used by evaluation tests.
- Added `DocumentOpsService` as the service-layer integration point for running the agent and saving trajectories.
- Added internal `/api/agent/document-ops/*` endpoints for run, trajectory list, stats, review, and SFT export.
- Protected run/list/review with existing API key/JWT behavior and protected SFT export with the existing ops key gate.
- Wired `TrajectoryStore` and `DocumentOpsService` into `create_app()` through `app.state`.
- Added a `DocumentOps` page-tab to the static admin shell.
- Added UI controls for agent run, task/skill selection, source summaries, source references, explicit trajectory capture, QA result rendering, trajectory review, trajectory stats, and SFT export trigger.
- Added SFT export preview/dry-run selection that reports eligible records, blocked records, blocker reasons, quality score summary, task/skill counts, and sample trajectory metadata without writing a JSONL file.
- Updated SFT export to skip records that are accepted but structurally unsafe for SFT export, such as missing plan, missing assistant output, missing skill/task type, or failed QA hard gate.
- Added a DocumentOps UI preview panel for checking SFT export readiness before triggering an export.
- Fixed the duplicate page-tab click listener so the new `DocumentOps` tab remains visible after navigation.
- Fixed DocumentOps SFT export and export preview buttons to include the existing ops key header path.
- Completed local browser QA with the mock provider: account setup, DocumentOps tab navigation, agent run, QA result rendering, trajectory list/stats rendering, reviewed trajectory state, ops-key export preview, SFT JSONL export, artifact list, and download action.
- Added ops-key protected SFT export artifact listing and download endpoints.
- Restricted SFT export downloads to metadata-recorded `.jsonl` files generated by `TrajectoryStore`, with filename validation and resolved path containment checks.
- Added DocumentOps UI export artifact list and download actions.
- Added reviewed-only SFT JSONL list/download aliases that expose only metadata-recorded `accepted_only=true` exports behind the ops-key gate.
- Updated the DocumentOps UI download action to use the reviewed-only JSONL endpoints.
- Added `docs/specs/hermes_decisiondoc_agent/PHASE18_BROWSER_QA_EVIDENCE.md` as the reusable local browser QA checklist and evidence capture artifact for the full no-training governance flow.
- Added static infrastructure coverage that verifies the Phase 18 artifact documents the governance actions, browser URL, no-training invariants, rehearsal side-effect guard, and provider fine-tune API prohibition.
- Added Phase 19 observed local browser QA evidence under `phase18_browser_governance_qa/`, including a human-readable report and machine-readable result JSON.
- Completed observed local browser QA against a mock-provider no-training governance setup: reviewed JSONL, readiness, plan preview, audit checklist, governance summary, adapter contract, and rehearsal panels rendered with no-training/no-upload/no-provider-call guards visible.
- Added Phase 20 release handoff artifacts under `phase20_release_handoff/`, including a reviewer-facing handoff index and a machine-readable manifest.
- Packaged the required DocumentOps governance evidence for Product/PM, ML/AI owner, Compliance/Security, and Release owner sign-off while explicitly preserving the no-training/no-upload/no-provider-call boundary.
- Added Phase 21 manual reviewer sign-off record template artifacts under `phase21_reviewer_signoff/`, including a reviewer-facing Markdown template and machine-readable JSON template.
- Defined required reviewer records for Product/PM, ML/AI owner, Compliance/Security, and Release owner with reviewer name, title/team, timestamp, decision, evidence reviewed, notes, and explicit no-training boundary acknowledgements.
- Kept all Phase 21 reviewer decisions pending by default and recorded that no actual reviewer approval, training execution, upload, provider fine-tune API call, provider job, or model promotion is authorized.
- Added Phase 22 local sign-off validator at `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py`.
- The validator accepts completed reviewer sign-off JSON records only when required reviewer roles, names, teams/titles, ISO timestamps, non-pending decisions, evidence lists, acknowledgements, conditional notes, and completion rules are satisfied.
- The validator rejects any completed sign-off record that authorizes training execution, dataset upload, provider fine-tune API calls, provider job creation/polling, model candidate emission, or model promotion.
- Added Phase 23 pending sign-off record generator at `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py`.
- The generator copies the Phase 21 template into a fillable pending JSON record with generated `signoff_record_id`, `created_at`, template provenance, and no-side-effect generation metadata.
- Generated pending records preserve blank reviewer identity/timestamp/note fields, `decision=pending`, unchecked acknowledgements, incomplete completion rules, and unauthorized no-training/no-upload/no-provider-call boundary flags.
- Added Phase 24 local sign-off summary reporter at `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py`.
- The reporter scans pending or completed sign-off JSON records, reports reviewer completion counts, pending/changes-requested/blocked decisions, validator pass/fail state, and protected boundary status.
- Phase 24 summary reports remain evidence-only and explicitly keep training execution, dataset upload, provider fine-tune API calls, provider job creation, and model promotion unauthorized.
- Added Phase 25 tenant-local reviewer sign-off summary support to `TrajectoryStore` and `DocumentOpsService`.
- Exposed ops-key protected `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary` for read-only sign-off summary status.
- The endpoint scans only `DATA_DIR/tenants/{tenant}/trajectory_reviewer_signoffs/*.json`, avoiding arbitrary local file path input.
- Added a DocumentOps UI `Sign-off summary` action that renders reviewer completion counts, record status, blockers, validation state, and no-training/no-upload/no-provider-call guard state.
- Phase 25 sign-off summaries remain evidence-only and explicitly keep training execution, dataset upload, provider fine-tune API calls, provider job creation, and model promotion unauthorized.
- Added Phase 26 observed local browser QA evidence under `phase26_reviewer_signoff_browser_qa/`, including a human-readable report and machine-readable result JSON.
- Completed observed local browser QA against a mock-provider reviewer sign-off setup: local admin login, DocumentOps tab navigation, ops-key entry, `Sign-off summary` panel rendering, pending/completed record visibility, blocker visibility, and no-training/no-upload/no-provider-call guard visibility.
- Phase 26 browser QA remains evidence-only and explicitly keeps training execution, dataset upload, provider fine-tune API calls, provider job creation, and model promotion unauthorized.
- Added Phase 27 ops-key protected `GET /api/agent/document-ops/trajectories/reviewer-signoff/summary/download` for read-only reviewer sign-off summary JSON download.
- Added a DocumentOps UI `Sign-off JSON` action that downloads the summary JSON using the existing ops-key header path and browser download helper.
- Phase 27 summary download computes the JSON response in memory, writes no server-side file, and explicitly keeps training execution, dataset upload, provider fine-tune API calls, provider job creation, and model promotion unauthorized.
- Added a DocumentOps-specific download fallback panel for reviewer sign-off JSON downloads so unsupported browser download runtimes still expose a save/open link after the JSON blob is fetched.
- Added Phase 28 observed local browser QA evidence under `phase28_reviewer_signoff_json_download_qa/`, including a human-readable report and machine-readable result JSON.
- Completed observed local browser QA against a mock-provider reviewer sign-off download setup: local admin login, DocumentOps tab navigation, ops-key entry, `Sign-off JSON` click, success notification, fallback filename/link visibility, API attachment checkpoint, and no-training/no-upload/no-provider-call guard visibility.
- Phase 28 browser QA records the Codex in-app browser limitation that native download events are unsupported, while confirming the browser received the JSON blob and rendered the fallback link.
- Refreshed the Phase 20 handoff index as Phase 29 reviewer sign-off release packaging, covering Phase 21-28 reviewer templates, validators, summary tooling, endpoint/UI, JSON download, and browser QA evidence for actual human reviewer use.
- Updated the handoff manifest to `document_ops_phase29_reviewer_signoff_handoff_refresh`, including reviewer-use steps, Phase 21-28 coverage, required artifacts, observed QA summaries, and explicit no-training/no-upload/no-server-artifact-write/no-provider-call guard flags.
- Added Phase 30 operator-ready reviewer sign-off packet guide under `phase30_reviewer_signoff_packet/`, including packet contents, exact generator/validator/summary commands, reviewer completion fields, DocumentOps UI inspection steps, and no-training/no-upload/no-provider-call boundaries.
- Added Phase 30 machine-readable operator checklist with pass criteria, packet artifacts, command steps, authorization boundary flags, and side-effect boundary flags.
- Linked the Phase 30 guide and checklist into the handoff manifest so the reviewer-use package has both human-readable and machine-readable operator instructions.
- Added Phase 31 tenant-local reviewer sign-off import helper under `phase31_reviewer_signoff_import/`.
- The Phase 31 helper copies pending or locally validated completed sign-off records into `DATA_DIR/tenants/{tenant_id}/trajectory_reviewer_signoffs/` with tenant id validation, output filename validation, atomic local write, record-shape validation, and no-training/no-upload/no-provider-call boundary checks.
- Added Phase 31 tests that verify pending and completed records import safely, summary tooling can read the imported records, traversal output filenames are rejected, traversal tenant ids are rejected, boundary-breaking records are rejected, and incomplete completed records cannot be imported as generated approval records.
- Updated the Phase 30 operator packet guide/checklist and Phase 29 handoff manifest to use the Phase 31 helper instead of manual `cp` for DocumentOps UI inspection.
- Added Phase 32 observed local browser QA evidence under `phase32_imported_signoff_browser_qa/`, including a human-readable report and machine-readable result JSON.
- Completed observed browser QA against a mock-provider setup with Phase 31 imported pending/completed reviewer sign-off records: DocumentOps `Sign-off summary` rendered both imported records, `Sign-off JSON` downloaded a summary JSON containing both records, and the fallback link/notifications were visible.
- Updated the handoff manifest and infrastructure coverage to include Phase 32 imported-record browser QA evidence and no-training/no-upload/no-provider-call/no-generated-approval boundaries.
- Added Phase 33 operator release packet summary under `phase33_operator_release_packet_summary/`, including a human-readable packet summary and machine-readable release packet criteria.
- Linked the Phase 30 operator guide, Phase 31 import helper, and Phase 32 observed browser QA evidence into one staging-readiness packet without authorizing model training, dataset upload, provider fine-tune API calls, generated approvals, or production smoke completion.
- Updated the handoff manifest and infrastructure coverage to include Phase 33 packet artifacts, staging-readiness criteria, and the next Phase 34 staging dry-run boundary.
- Added Phase 34 staging-readiness dry-run artifacts under `phase34_staging_readiness_dry_run/`, including an operator guide, a machine-readable probe contract, and a read-only HTTP probe CLI.
- The Phase 34 probe checks `/health`, ops-key enforcement, reviewer sign-off summary, reviewer sign-off JSON download, imported record visibility, guard flags, side-effect boundaries, and `server_file_written=false`.
- Validated the Phase 34 probe in fixture mode so the probe result shape, pass/fail criteria, and no-training/no-upload/no-provider-call/no-generated-approval boundaries are covered without requiring real staging credentials.
- Updated the handoff manifest and infrastructure coverage to include Phase 34 probe artifacts and to move the next observed evidence step to Phase 35.
- Added Phase 35 observed staging probe evidence artifacts under `phase35_observed_staging_probe_evidence/`, including an operator guide, a machine-readable archive contract, and a local archive helper.
- The Phase 35 archive helper accepts only passing non-fixture Phase 34 probe results, verifies ops-key requirement, record visibility, `server_file_written=false`, clear guard flags, and no side-effect boundaries, then writes a local evidence archive JSON.
- Passing real staging/deployed probe execution remains pending because the deployed runtime currently lacks the DocumentOps reviewer sign-off routes and the target tenant sign-off storage, even though the deployed ops key is available through the server env.
- Updated the handoff manifest and infrastructure coverage to include Phase 35 archive artifacts and to move the next observed environment execution decision to Phase 36.
- Added Phase 36 observed probe execution workflow artifacts under `phase36_observed_probe_execution_workflow/`, including an operator guide, a machine-readable workflow contract, and a one-shot runtime preflight/execution wrapper.
- The Phase 36 wrapper reads command-line args, process env, or env files, validates base URL, ops key, tenant id, and expected imported sign-off record ids, then runs Phase 34 probe and Phase 35 archive when all inputs are present.
- Verified Phase 36 in dry-run mode with a temporary env file and confirmed the ops key is never printed; actual deployed probe execution remains pending until real base URL and expected imported record ids are supplied.
- Updated the handoff manifest and infrastructure coverage to include Phase 36 workflow artifacts and no-training/no-upload/no-provider-call boundaries.
- Ran a real read-only deployed probe attempt against `https://admin.decisiondoc.kr` using the ops key available in `.github-actions.env`.
- Recorded Phase 37 deployed probe failure evidence: `/health` returned `200`, unauthenticated summary returned `401`, and ops-key summary/download also returned `401`.
- Inferred the blocker as deployed ops-key mismatch or missing current runtime secret, without printing or storing the ops key.
- No passing Phase 35 archive was created because ops-key authentication failed and expected sign-off record ids were not supplied.
- Hardened the Phase 36 observed-probe wrapper so it creates `--output-dir` before invoking the Phase 34 probe, preventing missing-directory failures from masking deployed endpoint results.
- Reran the guarded read-only deployed probe against `https://admin.decisiondoc.kr` with expected imported ids `dsr_phase32done` and `dsr_phase32pending`.
- Recorded Phase 38 observed probe retry evidence: wrapper output files were written locally, `/health` returned `200`, unauthenticated summary returned `401`, and ops-key summary/download still returned `401`.
- Confirmed the remaining blocker is deployed ops-key mismatch or missing current runtime secret; expected record visibility cannot be verified until ops-key authentication succeeds.
- Confirmed through SSH that the deployed `/opt/decisiondoc/.env.prod` ops key exists and does not match local `.github-actions.env`.
- Reran Phase 36 with the deployed ops key in memory only; reviewer sign-off summary/download changed from `401` to `404`, confirming the deployed ops key is valid but the route is absent.
- Recorded Phase 39 remote runtime gap evidence: production host is reachable, remote checkout is at `011aec5`, remote code search found zero `reviewer-signoff/summary` route references, and the `system` tenant sign-off directory is missing.
- Identified the next blocker as undeployed local DocumentOps route/service/store/UI changes plus missing production sign-off record import, not a provider/model issue.
- Recorded Phase 40 production sign-off completion evidence after deploying the DocumentOps reviewer sign-off routes and importing production tenant records.
- Validated completed record `dsr_phase41prod_done` locally and in the production checkout with `error_count=0`, then imported it into `/app/data/tenants/system/trajectory_reviewer_signoffs/`.
- Reran the Phase 36 wrapper against `https://admin.decisiondoc.kr` with the deployed ops key held in memory only; `/health`, ops-key enforcement, summary, JSON download, expected record visibility, and `server_file_written=false` checks passed.
- Confirmed production summary/download both observe `dsr_phase41prod_pending` and `dsr_phase41prod_done` while preserving no-training/no-upload/no-provider-fine-tune/no-provider-job/no-model-promotion boundaries.
- Ran the separate production post-deploy smoke with `SMOKE_TIMEOUT_SEC=180` on the production host.
- Recorded Phase 41 production post-deploy smoke evidence: health, provider routing, docker compose, nginx config, deployed document-generation smoke, and report workflow smoke all passed.
- Confirmed general generation endpoints returned expected auth behavior and success responses: `/generate`, `/generate/export`, `/generate/with-attachments`, and `/generate/from-documents`.
- Confirmed Report Workflow production smoke covered planning approval gates, slide approval gates, final PM/executive approval order, project creation, workflow promotion, PPTX export, and snapshot export.
- Recorded that Phase 41 intentionally made normal generation provider calls and created runtime artifacts, while still not authorizing training, external dataset upload, fine-tune provider APIs, provider jobs, or model promotion.
- Ran production browser UAT in the Codex in-app browser against `https://admin.decisiondoc.kr`.
- Recorded Phase 42 production browser UAT evidence: admin page load, PM session visibility, synthetic document-generation input, sketch rendering/acceptance, generated result rendering, result action buttons, individual download controls, and Report Workflow tab/detail UX all passed.
- Confirmed PDF/PPTX/HWP download controls are reachable and produced no browser console errors, while recording that Codex in-app browser cannot emit native download events.
- Complemented the browser limitation with production backend export integrity checks for PDF, PPTX, and HWP/HWPX response structures and required magic bytes/ZIP entries.
- Recorded a non-blocking UI polish follow-up: the result screen rendered but global generation status text stayed stale as `AI가 문서를 생성하는 중...`.
- Hardened `DocumentOpsAgent` live-provider parsing for fenced JSON, common nested payload wrappers, `draft_output`/`content` aliases, dict-based evidence/source references, and scalar warning/plan values.
- Updated the DocumentOps prompt to request Korean planning/draft/evidence output and explicit 개인정보, 보안, 운영책임, 리스크, 로그/감사 coverage for policy/public-sector tasks.
- Completed a non-sensitive live OpenAI pilot through the DocumentOps API path: generated one policy planning trajectory, passed QA hard gate, marked it reviewed/accepted, previewed SFT export eligibility, exported JSONL, downloaded the artifact, and manually inspected the JSONL message structure.
- Added offline SFT dataset quality reporting for the next reviewed export selection, including schema validation, role sequence summary, QA hard-gate/quality-score summary, source/evidence coverage, blocker/rejection reason summary, readiness flags, and actionable recommendations.
- Added offline SFT JSONL file inspection for metadata-recorded export artifacts, including JSONL parse errors, message schema validation, assistant payload validation, role sequence summary, QA/evidence coverage, and training-readiness status.
- Exposed the dataset quality reports through ops-key protected endpoints:
  - `POST /api/agent/document-ops/trajectories/export/quality-report`
  - `GET /api/agent/document-ops/trajectories/exports/{filename}/quality-report`
- Added dataset freeze manifests for metadata-recorded SFT exports that pass the file quality report, including export filename, export SHA-256, record count, quality report SHA-256, schema/QA/evidence summary, reviewer gate status, and a no-training-by-default guard.
- Added tenant-scoped freeze metadata listing so operators can audit which export artifacts have been frozen.
- Exposed freeze controls through ops-key protected endpoints:
  - `POST /api/agent/document-ops/trajectories/exports/{filename}/freeze`
  - `GET /api/agent/document-ops/trajectories/freezes`
- Added explicit rejection for `training_allowed=true`; dataset freeze does not start training or grant model promotion approval.
- Added manual training approval records that consume a frozen dataset manifest, require a non-empty eval plan, require an approver different from the dataset-freeze reviewer, redact sensitive eval-plan fields, and remain dry-run/no-provider-job only.
- Added tenant-scoped training approval metadata listing so operators can audit who approved a frozen dataset for the future training workflow.
- Exposed dry-run training approval controls through ops-key protected endpoints:
  - `POST /api/agent/document-ops/trajectories/freezes/{manifest_id}/training-approval`
  - `GET /api/agent/document-ops/trajectories/training-approvals`
- Added explicit rejection for `start_training=true` and `dry_run=false`; Phase 10 records approval intent only and never starts a provider job or model promotion.
- Added a read-only training readiness summary that combines reviewed SFT exports, dataset freeze manifests, dry-run training approvals, latest export quality, eval-plan required metrics, and remaining blockers.
- Exposed the readiness summary through the ops-key protected `GET /api/agent/document-ops/trajectories/training-readiness` endpoint.
- Added a DocumentOps UI `Readiness` action that displays read-only readiness status, latest gate IDs, eval coverage, training guard counters, and blockers without starting training or uploading files.
- Added a provider-agnostic training execution plan preview that converts the readiness state into a dry-run job spec with dataset freeze/export references, eval suite/metrics, training parameter placeholders, and execution steps.
- Exposed the plan preview through the ops-key protected `GET /api/agent/document-ops/trajectories/training-plan/preview` endpoint.
- Added a DocumentOps UI `Plan preview` action that renders the dry-run job spec while explicitly keeping training execution, provider API calls, external uploads, provider jobs, and model promotion disabled.
- Added a two-person training execution request record that references the dry-run plan preview, requires the requester to differ from the prior dry-run training approver, and remains record-only.
- Exposed training execution request records through ops-key protected `GET` and `POST /api/agent/document-ops/trajectories/training-execution-requests`.
- Added a DocumentOps UI `Request record` action and request-record rendering while explicitly keeping training execution, upload, provider API calls, provider jobs, and model promotion disabled.
- Added a final pre-execution audit checklist that bundles readiness, dry-run plan preview, execution request records, blockers, and a metadata-only human-review packet.
- Added pre-execution audit export records with separation-of-duties checks requiring the auditor to differ from both execution requester and prior dry-run training approver.
- Exposed audit checklist/export/list/download through ops-key protected `training-audit` and `training-audits` endpoints.
- Added a DocumentOps UI `Audit checklist` action and `Export audit` action while explicitly keeping training execution, upload, provider API calls, provider jobs, and model promotion disabled.
- Added a read-only training governance dashboard summary that aggregates reviewed exports, freezes, dry-run approvals, execution requests, audit exports, blockers, latest gate IDs, and no-side-effect guard counters.
- Exposed the governance summary through the ops-key protected `GET /api/agent/document-ops/trajectories/training-governance/summary` endpoint.
- Added a DocumentOps UI `Governance` action while explicitly keeping training execution, upload, provider API calls, provider jobs, and model promotion disabled.
- Added a stub-only provider training adapter contract with required future methods, forbidden stub operations, and disabled-by-default execution configuration validation.
- Exposed the adapter contract through the ops-key protected `GET /api/agent/document-ops/trajectories/training-provider-adapter/contract` endpoint.
- Added a DocumentOps UI `Adapter` action while explicitly keeping training execution, upload, provider API calls, provider jobs, and model promotion disabled.
- Added a dry-run provider execution rehearsal that validates governance artifacts against the adapter contract and returns a step-by-step no-side-effect rehearsal log.
- Exposed the rehearsal through the ops-key protected `GET /api/agent/document-ops/trajectories/training-provider-adapter/rehearsal` endpoint.
- Added a DocumentOps UI `Rehearsal` action while explicitly keeping training execution, upload, provider API calls, provider jobs, and model promotion disabled.

## Files Added

- `docs/specs/hermes_decisiondoc_agent/ANALYSIS.md`
- `docs/specs/hermes_decisiondoc_agent/ARCHITECTURE.md`
- `docs/specs/hermes_decisiondoc_agent/TRAINING_AND_DATASET_PLAN.md`
- `docs/specs/hermes_decisiondoc_agent/IMPLEMENTATION_PLAN.md`
- `docs/specs/hermes_decisiondoc_agent/STATUS.md`
- `app/agents/__init__.py`
- `app/agents/schemas.py`
- `app/agents/skill_registry.py`
- `app/agents/document_ops_agent.py`
- `app/agents/skills/policy-planning.md`
- `app/agents/skills/evidence-gap-checker.md`
- `app/agents/skills/decision-brief-builder.md`
- `tests/agents/test_skill_registry.py`
- `tests/agents/test_document_ops_agent.py`
- `app/storage/trajectory_store.py`
- `tests/storage/test_trajectory_store.py`
- `app/evals/__init__.py`
- `app/evals/document_ops/__init__.py`
- `app/evals/document_ops/rubric.py`
- `app/evals/document_ops/gates.py`
- `tests/evals/test_document_ops_gates.py`
- `app/services/document_ops_service.py`
- `app/routers/document_ops_agent.py`
- `tests/test_document_ops_agent_api.py`
- `app/static/index.html`
- `docs/specs/hermes_decisiondoc_agent/phase7_live_provider_pilot/PILOT_REPORT.md`
- `docs/specs/hermes_decisiondoc_agent/phase7_live_provider_pilot/pilot_result.json`
- `docs/specs/hermes_decisiondoc_agent/phase18_browser_governance_qa/BROWSER_QA_REPORT.md`
- `docs/specs/hermes_decisiondoc_agent/phase18_browser_governance_qa/browser_qa_result.json`
- `docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/RELEASE_HANDOFF_INDEX.md`
- `docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/SIGNOFF_RECORD_TEMPLATE.md`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/signoff_record_template.json`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py`
- `docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py`
- `docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/BROWSER_QA_REPORT.md`
- `docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/browser_qa_result.json`
- `docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/BROWSER_QA_REPORT.md`
- `docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/browser_qa_result.json`
- `docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/OPERATOR_PACKET_GUIDE.md`
- `docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/operator_packet_checklist.json`
- `docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/IMPORT_HELPER.md`
- `docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py`
- `docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/BROWSER_QA_REPORT.md`
- `docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/browser_qa_result.json`
- `docs/specs/hermes_decisiondoc_agent/phase33_operator_release_packet_summary/RELEASE_PACKET_SUMMARY.md`
- `docs/specs/hermes_decisiondoc_agent/phase33_operator_release_packet_summary/release_packet_summary.json`
- `docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/STAGING_READINESS_DRY_RUN.md`
- `docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/staging_readiness_dry_run.json`
- `docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/run_staging_readiness_probe.py`
- `docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/OBSERVED_STAGING_PROBE_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/observed_staging_probe_evidence.json`
- `docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/archive_staging_probe_result.py`
- `docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/OBSERVED_PROBE_EXECUTION_WORKFLOW.md`
- `docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/observed_probe_execution_workflow.json`
- `docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py`
- `docs/specs/hermes_decisiondoc_agent/phase37_deployed_probe_failure_evidence/DEPLOYED_PROBE_FAILURE_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase37_deployed_probe_failure_evidence/deployed_probe_failure_evidence.json`
- `docs/specs/hermes_decisiondoc_agent/phase38_observed_probe_retry/DEPLOYED_PROBE_RETRY_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase38_observed_probe_retry/deployed_probe_retry_evidence.json`
- `docs/specs/hermes_decisiondoc_agent/phase39_remote_runtime_gap/REMOTE_RUNTIME_GAP_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase39_remote_runtime_gap/remote_runtime_gap_evidence.json`
- `docs/specs/hermes_decisiondoc_agent/phase40_production_signoff_completion_evidence/PRODUCTION_SIGNOFF_COMPLETION_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase40_production_signoff_completion_evidence/production_signoff_completion_evidence.json`
- `docs/specs/hermes_decisiondoc_agent/phase41_production_post_deploy_smoke_evidence/PRODUCTION_POST_DEPLOY_SMOKE_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase41_production_post_deploy_smoke_evidence/production_post_deploy_smoke_evidence.json`
- `docs/specs/hermes_decisiondoc_agent/phase42_production_browser_uat_evidence/PRODUCTION_BROWSER_UAT_EVIDENCE.md`
- `docs/specs/hermes_decisiondoc_agent/phase42_production_browser_uat_evidence/production_browser_uat_evidence.json`

## Not Done Yet

- No Hermes dependency installed in DecisionDoc.
- No production code imported from Hermes.
- No external provider bypass introduced; agent model calls still use the configured DecisionDoc provider path.
- No model training started.
- No background automatic capture added; trajectory capture is explicit via `capture_trajectory=true`.
- No automatic model promotion or fine-tune run introduced.
- Browser QA covered local mock provider flows only; Phase 7 live-provider validation was executed through FastAPI `TestClient` with a non-sensitive scenario and temp `DATA_DIR`, and Phase 19 observed governance QA used local mock metadata only.
- The production reviewer sign-off deployed probe, general post-deploy backend smoke, and browser-level production UAT now pass; OS-level download-open verification in Chrome/Safari remains separate if release sign-off requires actual local files.
- Dataset quality reports are read-only; they do not freeze a dataset, upload data, or start training.
- Dataset freeze manifests are still no-training-by-default; a separate approval workflow is required before any model training or promotion.
- Training approval records are dry-run/no-provider-job only; they do not upload data, start fine-tuning, or promote a model.
- Governance dashboard summaries are read-only; they do not upload datasets, start provider jobs, or approve model promotion.
- Provider execution rehearsals are dry-run only; they validate metadata and contract state without uploading datasets, creating provider jobs, or promoting models.
- Phase 18 browser QA evidence is a checklist/template artifact plus automated static coverage; it does not execute browser actions, upload datasets, call provider APIs, or start training.
- Phase 20 handoff packaging is reviewer sign-off preparation only; it does not record actual reviewer approvals, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 21 sign-off artifacts define a pending manual record format only; they do not record actual reviewer approvals or authorize training execution, uploads, provider calls, provider jobs, or model promotion.
- Phase 22 validation is local JSON validation only; it does not record reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 23 generation is local pending JSON creation only; it does not record actual reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 24 summary reporting is local JSON inspection only; it does not record reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 25 endpoint/UI summary is ops-key protected read-only local JSON inspection only; it does not record reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 26 observed browser QA used local mock-provider seed data only; it does not record real reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 27 summary download is an in-memory JSON attachment only; it does not write a server artifact, record reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 28 observed browser QA verified local browser blob receipt and fallback visibility only; native OS file-save verification is not available in Codex in-app browser because the runtime reports downloads are unsupported.
- Phase 29 handoff refresh packages the reviewer-use path only; it does not create an actual completed reviewer approval record, authorize training execution, upload datasets, write server artifacts, call provider APIs, create provider jobs, or promote a model.
- Phase 30 operator packet guide is procedural documentation only; it does not collect actual reviewer approvals, authorize training execution, upload datasets, write server artifacts, call provider APIs, create provider jobs, or promote a model.
- Phase 31 import helper copies only operator-provided pending or locally validated sign-off records into tenant-local storage; it does not create reviewer approvals, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 32 observed browser QA used local mock-provider seed data and Phase 31 imported records only; it does not record real reviewer approval, authorize training execution, upload datasets, call provider APIs, create provider jobs, or promote a model.
- Phase 42 production browser UAT used normal production generation/export paths and UI inspection, but it does not authorize training execution, upload datasets, call provider fine-tune APIs, create provider jobs, or promote a model.
- Phase 42 did not prove host OS file-save/open behavior because Codex in-app browser reports native downloads are unsupported; backend export integrity was checked separately.

## Current Verification

```text
python3 -m py_compile app/services/document_ops_service.py app/routers/document_ops_agent.py app/main.py app/schemas.py tests/test_document_ops_agent_api.py
pytest -q tests/test_document_ops_agent_api.py --tb=short
pytest -q tests/agents --tb=short
pytest -q tests/test_document_ops_agent_api.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py --tb=short
pytest tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py -q
pytest tests/test_document_ops_agent_api.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py tests/test_finetune.py -q
python3 -m py_compile app/storage/trajectory_store.py app/services/document_ops_service.py app/routers/document_ops_agent.py tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py
pytest -q tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py --tb=short
python3 -m py_compile app/storage/trajectory_store.py app/services/document_ops_service.py app/routers/document_ops_agent.py app/schemas.py tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py
python3 -m py_compile app/storage/trajectory_store.py app/services/document_ops_service.py app/routers/document_ops_agent.py app/main.py app/schemas.py tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py
python3 -m py_compile app/storage/trajectory_store.py app/services/document_ops_service.py app/routers/document_ops_agent.py app/main.py app/schemas.py tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py
python3 -m py_compile app/services/document_ops_training_adapter.py app/services/document_ops_service.py app/routers/document_ops_agent.py app/main.py app/schemas.py tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py
pytest -q tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_shows_pre_execution_audit_checklist_export --tb=short
pytest -q tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_shows_pre_execution_audit_checklist_export tests/test_infrastructure.py::test_index_html_document_ops_shows_training_governance_dashboard_summary --tb=short
pytest -q tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_shows_training_execution_rehearsal --tb=short
python -m py_compile app/services/document_ops_training_adapter.py app/services/document_ops_service.py app/routers/document_ops_agent.py tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py
pytest tests/storage/test_trajectory_store.py tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_phase18_browser_qa_evidence_artifact_documents_no_training_flow
pytest -q tests/test_infrastructure.py::test_phase18_browser_qa_evidence_artifact_documents_no_training_flow tests/test_infrastructure.py::test_phase19_browser_qa_result_records_observed_no_training_pass tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py --tb=short
pytest -q tests/test_infrastructure.py::test_phase29_release_handoff_refresh_packages_reviewer_signoff_artifacts --tb=short
pytest -q tests/test_infrastructure.py::test_phase21_manual_reviewer_signoff_template_preserves_no_training_boundary --tb=short
pytest -q tests/test_infrastructure.py::test_phase22_signoff_validator_accepts_completed_records_and_rejects_boundary_breaks --tb=short
pytest -q tests/test_infrastructure.py::test_phase23_pending_signoff_generator_creates_fillable_no_training_record --tb=short
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/generate_pending_signoff_record.py docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/summarize_signoff_records.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase21_manual_reviewer_signoff_template_preserves_no_training_boundary tests/test_infrastructure.py::test_phase22_signoff_validator_accepts_completed_records_and_rejects_boundary_breaks tests/test_infrastructure.py::test_phase23_pending_signoff_generator_creates_fillable_no_training_record tests/test_infrastructure.py::test_phase24_signoff_summary_reports_reviewer_completion_without_training_authorization --tb=short
python -m py_compile app/storage/trajectory_store.py app/services/document_ops_service.py app/routers/document_ops_agent.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py
pytest -q tests/test_document_ops_agent_api.py::test_document_ops_reviewer_signoff_summary_is_ops_key_read_only tests/test_infrastructure.py::test_index_html_document_ops_shows_reviewer_signoff_summary --tb=short
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase26_reviewer_signoff_browser_qa_result_records_observed_no_training_pass --tb=short
pytest -q tests/test_document_ops_agent_api.py::test_document_ops_reviewer_signoff_summary_is_ops_key_read_only tests/test_infrastructure.py::test_index_html_document_ops_shows_reviewer_signoff_summary tests/test_infrastructure.py::test_phase26_reviewer_signoff_browser_qa_result_records_observed_no_training_pass --tb=short
pytest -q tests/test_infrastructure.py --tb=short
python -m py_compile app/services/document_ops_service.py app/routers/document_ops_agent.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py
pytest -q tests/test_document_ops_agent_api.py::test_document_ops_reviewer_signoff_summary_is_ops_key_read_only tests/test_infrastructure.py::test_index_html_document_ops_shows_reviewer_signoff_summary --tb=short
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase28_reviewer_signoff_json_download_browser_qa_result_records_blob_received --tb=short
pytest -q tests/test_infrastructure.py::test_index_html_document_ops_shows_reviewer_signoff_summary tests/test_infrastructure.py::test_phase28_reviewer_signoff_json_download_browser_qa_result_records_blob_received --tb=short
local browser QA at http://127.0.0.1:8769/?ops=1&phase28=1778150148160 with mock provider, local admin session, pending/completed reviewer sign-off records, ops-key sign-off JSON download action, success notification, fallback save link, and no-training/no-upload/no-provider-call guard checks
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase28_reviewer_signoff_json_download_qa/browser_qa_result.json >/tmp/phase28_browser_qa_result.pretty.json
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json >/tmp/phase29_handoff_manifest.pretty.json
pytest -q tests/test_infrastructure.py::test_phase29_release_handoff_refresh_packages_reviewer_signoff_artifacts --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase30_reviewer_signoff_packet/operator_packet_checklist.json >/tmp/phase30_operator_packet_checklist.pretty.json
pytest -q tests/test_infrastructure.py::test_phase30_operator_reviewer_signoff_packet_guide_documents_operational_flow --tb=short
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase31_reviewer_signoff_import/import_signoff_record.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase31_signoff_import_helper_copies_pending_and_completed_records_safely tests/test_infrastructure.py::test_phase31_signoff_import_helper_rejects_path_traversal_and_generated_approval --tb=short
local browser QA at http://127.0.0.1:8770/?ops=1&phase32=1778150148160 with mock provider, Phase 31 imported pending/completed reviewer sign-off records, ops-key Sign-off summary, Sign-off JSON download, fallback link, and downloaded JSON inspection
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase32_imported_signoff_browser_qa/browser_qa_result.json >/tmp/phase32_browser_qa_result.pretty.json
pytest -q tests/test_infrastructure.py::test_phase32_imported_signoff_browser_qa_result_records_observed_pass --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase33_operator_release_packet_summary/release_packet_summary.json >/tmp/phase33_release_packet_summary.pretty.json
pytest -q tests/test_infrastructure.py::test_phase33_operator_release_packet_summary_packages_staging_readiness --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/staging_readiness_dry_run.json >/tmp/phase34_staging_readiness_dry_run.pretty.json
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase34_staging_readiness_dry_run/run_staging_readiness_probe.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase34_staging_readiness_dry_run_probe_contract_and_fixture_pass --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/observed_staging_probe_evidence.json >/tmp/phase35_observed_staging_probe_evidence.pretty.json
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/archive_staging_probe_result.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase35_observed_staging_probe_evidence_archive_helper_validates_results --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/observed_probe_execution_workflow.json >/tmp/phase36_observed_probe_execution_workflow.pretty.json
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase36_observed_probe_execution_workflow_preflights_runtime_inputs --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase37_deployed_probe_failure_evidence/deployed_probe_failure_evidence.json >/tmp/phase37_deployed_probe_failure_evidence.pretty.json
pytest -q tests/test_infrastructure.py::test_phase37_deployed_probe_failure_evidence_records_ops_key_auth_blocker --tb=short
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase36_observed_probe_workflow_creates_output_dir_before_probe --tb=short
python docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py --env-file .github-actions.env --base-url https://admin.decisiondoc.kr --expect-record-id dsr_phase32done --expect-record-id dsr_phase32pending --output-dir /tmp/decisiondoc-phase38-observed-probe --timeout 20
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase38_observed_probe_retry/deployed_probe_retry_evidence.json >/tmp/phase38_deployed_probe_retry_evidence.pretty.json
pytest -q tests/test_infrastructure.py::test_phase38_observed_probe_retry_records_wrapper_fix_and_remaining_ops_key_blocker --tb=short
ssh read-only remote runtime inspection for /opt/decisiondoc commit, route references, deployed ops-key match, and tenant sign-off directory presence without printing secrets
python docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py with deployed ops key passed through process env only and output-dir /tmp/decisiondoc-phase39-observed-probe
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase39_remote_runtime_gap/remote_runtime_gap_evidence.json >/tmp/phase39_remote_runtime_gap_evidence.pretty.json
pytest -q tests/test_infrastructure.py::test_phase39_remote_runtime_gap_records_route_and_signoff_storage_blockers --tb=short
python3 docs/specs/hermes_decisiondoc_agent/phase21_reviewer_signoff/validate_signoff_record.py ~/Downloads/dsr_phase41prod_done_completed_signoff.json
remote production validation and import into /app/data/tenants/system/trajectory_reviewer_signoffs/dsr_phase41prod_done_completed_signoff.json without printing secrets
python docs/specs/hermes_decisiondoc_agent/phase36_observed_probe_execution_workflow/run_observed_probe_workflow.py with deployed ops key passed through process env only and output-dir /tmp/decisiondoc-phase41-prod-completed-probe
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase40_production_signoff_completion_evidence/production_signoff_completion_evidence.json >/tmp/phase40_production_signoff_completion_evidence.pretty.json
pytest -q tests/test_infrastructure.py::test_phase40_production_signoff_completion_evidence_records_deployed_probe_pass --tb=short
SMOKE_TIMEOUT_SEC=180 python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy on production host
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase41_production_post_deploy_smoke_evidence/production_post_deploy_smoke_evidence.json >/tmp/phase41_production_post_deploy_smoke_evidence.pretty.json
pytest -q tests/test_infrastructure.py::test_phase41_production_post_deploy_smoke_evidence_records_generation_and_workflow_pass --tb=short
Codex in-app browser UAT at https://admin.decisiondoc.kr for document generation, sketch acceptance, result controls, download control clicks, and report workflow UI
production export endpoint integrity checks for PDF, PPTX, and HWP/HWPX with non-sensitive synthetic documents
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase42_production_browser_uat_evidence/production_browser_uat_evidence.json >/tmp/phase42_production_browser_uat_evidence.pretty.json
pytest -q tests/test_infrastructure.py::test_phase42_production_browser_uat_evidence_records_ui_export_and_workflow_checks --tb=short
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/observed_staging_probe_evidence.json >/tmp/phase35_observed_staging_probe_evidence.pretty.json
PYTHONPYCACHEPREFIX=/tmp/decisiondoc-pycache python3 -m py_compile docs/specs/hermes_decisiondoc_agent/phase35_observed_staging_probe_evidence/archive_staging_probe_result.py tests/test_infrastructure.py
pytest -q tests/test_infrastructure.py::test_phase35_observed_staging_probe_evidence_archive_helper_validates_results --tb=short
pytest -q tests/test_document_ops_agent_api.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py tests/test_finetune.py --tb=short
pytest -q tests/test_document_ops_agent_api.py tests/test_document_ops_training_adapter.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py tests/test_finetune.py --tb=short
perl -0ne 'while (m{<script>(.*?)</script>}sg) { print $1 }' app/static/index.html > /tmp/decisiondoc-index-scripts.js && node --check /tmp/decisiondoc-index-scripts.js && git diff --check
local browser QA at http://127.0.0.1:8767/?ops=1 with mock provider and test ops key
local browser QA at http://127.0.0.1:8767/?ops=1&phase18=1778150148160 with mock provider, local admin session, reviewed JSONL/freeze/approval/request/audit metadata, and no-training governance panels
local browser QA at http://127.0.0.1:8768/?ops=1&phase26=1778150148160 with mock provider, local admin session, pending/completed reviewer sign-off records, ops-key sign-off summary panel, and no-training/no-upload/no-provider-call guard checks
python -m json.tool docs/specs/hermes_decisiondoc_agent/phase18_browser_governance_qa/browser_qa_result.json >/tmp/phase18_browser_qa_result.pretty.json
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase26_reviewer_signoff_browser_qa/browser_qa_result.json >/tmp/phase26_browser_qa_result.pretty.json
python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json >/tmp/phase20_handoff_manifest.pretty.json
live provider Phase 7 pilot with DECISIONDOC_PROVIDER_GENERATION=openai, temp DATA_DIR, non-sensitive traffic-safety scenario
python -m json.tool docs/specs/hermes_decisiondoc_agent/phase7_live_provider_pilot/pilot_result.json >/tmp/phase7_pilot_result.pretty.json
rg -n "sk-|OPENAI_API_KEY|GEMINI_API_KEY|ANTHROPIC_API_KEY|DECISIONDOC_API_KEYS|DECISIONDOC_OPS_KEY|phase7-local-api-key|phase7-local-ops-key" docs/specs/hermes_decisiondoc_agent/phase7_live_provider_pilot || true
```

Result:

- `py_compile`: pass
- `tests/test_document_ops_agent_api.py`: 5 passed after Phase 25 reviewer sign-off summary endpoint addition
- `tests/agents`: 12 passed after live-provider parser hardening
- `tests/test_document_ops_agent_api.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py`: 54 passed
- `tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py`: 18 passed after dry-run training approval gate addition
- `tests/test_document_ops_agent_api.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py tests/test_finetune.py`: 70 passed
- `tests/test_document_ops_agent_api.py tests/test_document_ops_training_adapter.py tests/evals/test_document_ops_gates.py tests/storage/test_trajectory_store.py tests/agents tests/test_ai_structured.py tests/test_ai_pipeline.py tests/test_finetune.py`: 89 passed after Phase 25 reviewer sign-off summary endpoint addition
- `tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_downloads_reviewed_sft_jsonl_exports`: 20 passed after reviewed-only SFT JSONL list/download endpoint and UI action update
- `tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_shows_pre_execution_audit_checklist_export`: 24 passed after final pre-execution audit checklist/export addition
- `tests/storage/test_trajectory_store.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_shows_pre_execution_audit_checklist_export tests/test_infrastructure.py::test_index_html_document_ops_shows_training_governance_dashboard_summary`: 26 passed after governance dashboard summary addition
- `tests/test_document_ops_training_adapter.py tests/test_document_ops_agent_api.py tests/test_infrastructure.py::test_index_html_document_ops_shows_training_execution_rehearsal`: 9 passed after dry-run provider execution rehearsal addition
- `tests/test_infrastructure.py`: 54 passed after Phase 39 remote runtime gap evidence addition
- `tests/storage/test_trajectory_store.py`: 20 passed after Phase 25 sign-off summary store changes
- `node --check` extracted static script: pass
- `git diff --check`: pass
- Local browser QA: pass for DocumentOps tab navigation, agent run/API-reviewed trajectory setup, QA PASS rendering, trajectory list/stats, accepted trajectory state, SFT export preview READY, SFT JSONL export creation, export artifact list rendering, and download action notification
- Phase 7 live pilot: OpenAI provider returned 200; `/api/agent/document-ops/run` returned 200; QA hard gate passed with overall score `0.925`; trajectory review returned 200; SFT export preview showed `eligible_count=1`, `blocked_count=0`; export returned `sft_policy_planning_brief_20260507T115037.jsonl`; download returned 200; manual JSONL inspection confirmed one JSONL line, `messages` plus `metadata`, role sequence `system/user/assistant`, source references present, no redaction/internal scan hits, and no training started.
- Phase 7 pilot report JSON parse and secret-marker scan: pass
- Phase 8 dataset quality report tests: candidate quality report returns schema/role/QA/evidence/rejection summary; exported JSONL file quality report returns schema-valid role sequence and training-readiness status; ops-key API protection verified.
- Phase 9 dataset freeze tests: SFT export freeze writes a manifest with export/quality-report digests and reviewer gate metadata, freeze metadata listing verifies the manifest file exists, ops-key protection is enforced, and `training_allowed=true` is rejected.
- Phase 10 dry-run training approval tests: approval consumes a frozen manifest, rejects same approver as freeze reviewer, rejects `start_training=true`, rejects `dry_run=false`, redacts sensitive eval-plan fields, lists approval metadata, enforces ops-key protection, and confirms no provider job or model promotion flag is set.
- Phase 11 readiness tests: readiness summary combines reviewed export, freeze manifest, dry-run approval, eval-plan required metrics, quality readiness, and guard counters; API ops-key protection verified; UI static readiness action verified; no training or upload path started.
- Phase 12 plan preview tests: provider-agnostic dry-run job spec includes freeze/export hashes, eval suite/required metrics, execution steps, and no-side-effect flags; API ops-key protection verified; UI static plan preview action verified; no provider API call, upload, training job, or model promotion path started.
- Phase 13 request-record tests: request record references the dry-run plan preview, enforces separate requester and prior dry-run approver, rejects `start_training`, upload, and provider API flags, lists request metadata, enforces ops-key protection, and confirms no training execution/upload/provider job/model promotion flag is set.
- Phase 14 audit tests: audit checklist bundles readiness, plan preview, request records, required checklist items, and human-review packet; audit export enforces auditor separation of duties, rejects `start_training`, upload, and provider API flags, lists/downloads audit metadata JSON, enforces ops-key protection, and confirms no training execution/upload/provider job/model promotion flag is set.
- Phase 15 governance tests: governance summary aggregates counts and latest gate IDs across reviewed exports, freezes, approvals, execution requests, and audit exports; guard counters remain zero; API ops-key protection verified; UI static governance action verified; no training execution/upload/provider job/model promotion flag is set.
- Phase 16 adapter tests: adapter contract remains stub-only and disabled by default, blocks enabled execution configuration, exposes required future methods/forbidden stub operations, enforces ops-key protection, and confirms no training execution/upload/provider job/model promotion flag is set.
- Phase 17 rehearsal tests: rehearsal validates governance readiness, no-side-effect guard state, adapter contract validity, dataset/audit references, and step-by-step dry-run modes; API ops-key protection verified; UI static rehearsal action verified; no training execution/upload/provider job/model promotion flag is set.
- Phase 18 artifact test: local browser QA checklist/evidence artifact documents the full no-training governance flow, browser URL, action list, no-training invariant, rehearsal side-effect guard, and provider fine-tune API prohibition.
- Phase 19 observed QA result test: browser QA report and result JSON record `pass`, governance/rehearsal ready status, reviewed JSONL visibility, and all no-side-effect guard flags set to false.
- Phase 19 browser QA: local `uvicorn` mock server and Codex in-app browser rendered DocumentOps reviewed JSONL, readiness, plan preview, audit checklist, governance, adapter, and rehearsal panels with no-training/no-upload/no-provider-call copy visible; browser QA result JSON is `pass`; no training execution/upload/provider job/model promotion flag was set.
- Phase 29 handoff refresh test: release handoff index and manifest package Phase 21-28 reviewer sign-off templates, validators, summary tooling, endpoint/UI, JSON download, observed browser QA evidence, reviewer-use steps, and all no-side-effect guard flags.
- Phase 21 sign-off template test: reviewer-facing and machine-readable templates include required reviewer roles, pending decisions, blank identity/timestamp fields, unchecked acknowledgements, and false no-training/no-upload/no-provider-call authorization flags.
- Phase 22 sign-off validator test: local validator accepts a completed temp sign-off record, rejects a temp record that authorizes provider fine-tune API calls, and emits machine-readable validation JSON.
- Phase 23 pending generator test: local generator creates a fillable pending temp sign-off record with generated id/timestamp, blank reviewer fields, pending decisions, unchecked acknowledgements, false no-training boundary flags, and expected validator failure until humans complete it.
- Phase 24 summary reporter test: local reporter summarizes one pending and one completed temp sign-off record, reports reviewer completion counts and completed-validation status, writes a summary JSON, and keeps all training/upload/provider-call authorization flags false.
- Phase 25 endpoint/UI tests: ops-key protected reviewer sign-off summary endpoint summarizes one pending and one completed tenant-local temp sign-off record, rejects API-key-only access, exposes no-training/no-upload/no-provider-call flags as false, and the UI static check verifies the `Sign-off summary` action and read-only guard copy.
- Phase 26 observed browser QA result test: browser QA report and result JSON record `pass`, pending/completed sign-off record visibility, blocker visibility, read-only endpoint checkpoint, empty browser console errors, and all no-side-effect guard flags set to false.
- Phase 26 browser QA: local `uvicorn` mock server and Codex in-app browser rendered the DocumentOps `Reviewer Sign-Off Summary` panel from tenant-local sign-off JSON records; `dsr_phase26done` and `dsr_phase26pending` were visible; `SIGN-OFF PENDING` and `pending_manual_signoff` blocker were visible; no training execution/upload/provider job/model promotion flag was set.
- Phase 27 endpoint/UI tests: ops-key protected reviewer sign-off summary download rejects API-key-only access, returns an attachment JSON filename scoped to the tenant, includes the Phase 25 summary payload, records `server_file_written=false`, and the UI static check verifies the `Sign-off JSON` action and read-only download endpoint.
- Phase 28 observed browser QA result test: browser QA report and result JSON record `pass`, API attachment checkpoint, pending/completed sign-off payload visibility, browser JSON blob receipt, fallback link visibility, success/no-training notification visibility, download runtime limitation, empty current-port console errors, and all no-side-effect guard flags set to false.
- Phase 28 browser QA: local `uvicorn` mock server and Codex in-app browser rendered the DocumentOps `Sign-off JSON` action; clicking it fetched the reviewer sign-off JSON blob and rendered `reviewer_signoff_summary_system_20260508T061250Z.json` fallback link; native download event verification was blocked by Codex in-app browser's unsupported-download limitation; no training execution/upload/provider job/model promotion flag was set.
- Phase 29 handoff manifest JSON parse: pass for the refreshed reviewer-use manifest through Phase 28.
- Phase 29 handoff refresh regression: `tests/test_infrastructure.py` 42 passed, including the refreshed handoff index/manifest coverage and existing reviewer sign-off evidence checks.
- Phase 30 operator packet checklist JSON parse: pass for machine-readable operator steps and no-side-effect boundaries.
- Phase 30 operator packet guide test: guide and checklist document generator, validator, summary reporter, DocumentOps `Sign-off summary`, DocumentOps `Sign-off JSON`, packet artifacts, pass criteria, and no-training/no-upload/no-provider-call boundaries.
- Phase 31 import helper py_compile: pass for the local import CLI and infrastructure tests.
- Phase 31 import helper tests: pending and completed sign-off records copy safely into tenant-local DocumentOps storage, imported records are readable by the summary reporter, traversal filenames/tenant ids are rejected, incomplete generated approval-like records are rejected, and provider/training boundary breaks are rejected.
- Phase 32 imported-record browser QA result test: browser QA report and result JSON record `pass`, Phase 31 imported pending/completed records visible in DocumentOps summary, Sign-off JSON downloaded summary contains both imported records, fallback link and success/no-training notifications are visible, and all training/upload/provider/generated-approval guard flags remain false except the intended tenant-local record copy.
- Phase 33 operator release packet summary test: packet summary and JSON link the Phase 30 guide, Phase 31 import helper, Phase 32 observed QA evidence, staging-readiness criteria, ops-key requirement, and no-training/no-upload/no-provider-call/no-generated-approval boundaries.
- Phase 34 staging-readiness dry-run probe test: guide, JSON contract, and probe CLI define read-only health/ops-key/sign-off summary/JSON download checks; fixture probe returns pass with expected imported records, `server_file_written=false`, clear guard flags, and no training/upload/provider/generated-approval side effects.
- Phase 35 observed staging probe evidence archive test: archive guide, JSON contract, and archive helper accept only passing non-fixture Phase 34 probe results, write a local evidence archive with source SHA-256, reject fixture probe results, and keep training/upload/provider/generated-approval boundaries false.
- Phase 36 observed probe execution workflow test: guide, JSON contract, and wrapper dry-run validate env-file/runtime inputs, require expected sign-off record ids, avoid printing ops keys, block missing inputs, and preserve no-training/no-upload/no-provider-call boundaries.
- Phase 36 wrapper output-dir hardening test: non-dry-run creates a previously missing output directory before invoking Phase 34, writes local failure evidence, avoids `FileNotFoundError`, and never prints the ops key.
- Phase 37 deployed probe failure evidence test: deployed health is recorded as reachable, ops-key summary/download are recorded as `401`, ops key value is not stored, expected record ids remain missing, and no training/upload/provider/generated-approval side effects are authorized.
- Phase 38 observed probe retry evidence test: wrapper output creation is recorded, deployed health remains `200`, ops-key summary/download remain `401`, expected ids are still not visible, and no training/upload/provider/generated-approval side effects are authorized.
- Phase 39 remote runtime gap evidence test: deployed ops key is recorded as present and used only in memory, local probe key mismatch is recorded, summary/download return `404` with deployed key, remote route references are absent, sign-off storage is missing, and no training/upload/provider/generated-approval side effects are authorized.
- Phase 40 production sign-off completion evidence test: deployed health and ops-key routes are recorded as passing, expected pending/completed record ids are visible in summary and JSON download, completed sign-off validation is recorded as valid, JSON download remains server-file-free, and no training/upload/provider/generated-approval/model-promotion side effects are authorized.
- Phase 41 production post-deploy smoke evidence test: health/provider routing/docker/nginx checks pass, document generation smoke and report workflow smoke pass, normal generation provider/runtime artifact side effects are explicitly recorded, and training/upload/fine-tune/provider-job/model-promotion side effects remain false.

## Next Approval Needed

Approve the next implementation slice:

```text
Proceed with browser-level production UAT for the admin UI: generate a document from the production UI, verify PDF/PPTX/HWP download/open behavior where applicable, and review the step-based report workflow UX without starting training, uploading datasets, creating provider fine-tune jobs, or promoting models.
```

## Open Risks

| Risk | Status | Mitigation |
|---|---|---|
| Sensitive documents sent to external APIs | Controlled for Phase 7 | Pilot used only synthetic/redacted summaries and source-reference labels; keep raw document upload out of live-provider pilot data until separately approved |
| Hermes tool runtime overreach | Not introduced | Do not import runtime into production |
| Poor training data quality | Reduced before training | Capture only reviewed trajectories with QA metadata, run Phase 8 dataset quality reports, and freeze Phase 9 manifests before training approval |
| Fine-tuned model regression | Open | Promote only through eval gates and model registry |
| Accidental provider training job start | Controlled through Phase 10 | Training approval gate rejects `start_training=true` and `dry_run=false`; no OpenAI upload/job API is called |
| Visual PPT quality conflated with LLM training | Open | Keep layout generation deterministic; train model on planning/content/evidence first |
| Live provider output shape drift | Mitigated for common variants | Parser now normalizes fenced JSON, nested wrappers, aliases, and dict source refs; keep adding cases from failed pilots |

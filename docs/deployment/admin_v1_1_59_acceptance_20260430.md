# DecisionDoc AI Admin v1.1.59 Acceptance Record — 2026-04-30

이 문서는 `admin.decisiondoc.kr` 운영 환경에 `v1.1.59` production release가 정상 반영되었음을 고정하기 위한 acceptance record입니다.

## 1. Acceptance Summary

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| release tag | `v1.1.59` |
| release commit | `d0e0683ab08f8b7ca93a48ba8876613ff9206956` |
| Docker image | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.59` |
| Docker digest | `sha256:3e08f085aa80c208c1154886f3ebd0dce449574dc6aab71f563312d5c9972f3b` |
| GitHub tag | `https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.59` |
| GitHub Actions CD run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/25160810439` |
| CD result | `success` |
| post-deploy timestamped report | `reports/post-deploy/post-deploy-20260430T103752Z.json` |
| acceptance recorded at | `2026-04-30 19:39 KST` |

## 2. Production Verification

Latest live health check:

| 항목 | 결과 |
|------|------|
| `/health` status | `ok` |
| provider summary | `claude,gemini,openai` |
| maintenance | `false` |
| provider | `ok` |
| provider_generation | `ok` |
| provider_attachment | `ok` |
| provider_visual | `ok` |
| storage | `ok` |
| eval_store | `ok` |
| quality_first policy | `ok` |

Provider routing:

| route | provider order |
|-------|----------------|
| default | `claude,gemini,openai` |
| generation | `claude,openai,gemini` |
| attachment | `gemini,claude,openai` |
| visual | `openai` |

Container verification from production deploy log:

| service | result |
|---------|--------|
| app | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.59`, healthy |
| nginx | `nginx:alpine`, running |
| compose env file | `/opt/decisiondoc/.env.prod` |
| nginx config | `nginx -t` passed |

## 3. Post-Deploy Smoke Evidence

Server-side post-deploy check:

| 항목 | 결과 |
|------|------|
| deploy started | `2026-04-30T10:37:09Z` |
| deploy completed | `2026-04-30T10:39:39Z` |
| production job duration | `2m30s` |
| report status | `passed` |
| smoke_results_available | `true` |

Smoke route results:

| check | result |
|-------|--------|
| `GET /health` | `200` |
| `POST /generate` without key | `401` |
| `POST /generate` with key | `200` |
| `POST /generate/export` with key | `200`, `files=4` |
| `POST /generate/with-attachments` without key | `401` |
| `POST /generate/with-attachments` with key | `200`, `files=1`, `docs=4` |
| `POST /generate/from-documents` without key | `401` |
| `POST /generate/from-documents` with key | `200`, `files=1`, `docs=2` |

Report Workflow ERP smoke results:

| check | result |
|-------|--------|
| `GET /health` | `200` |
| `POST /report-workflows` without key | `401` |
| `POST /report-workflows` with key | `200` |
| `POST /slides/generate` before planning approval | `400` |
| `POST /planning/generate` | `200`, `slide_plans=2` |
| `POST /planning/approve` | `200` |
| `POST /slides/generate` | `200`, `slides=2` |
| `POST /final/submit` before slide approvals | `400` |
| slide approvals | `200`, `approved=2` |
| `POST /final/submit` | `200` |
| `POST /final/executive-approve` before PM approval | `400` |
| `POST /final/pm-approve` | `200` |
| `POST /final/executive-approve` | `200` |
| `POST /projects` | `200` |
| `POST /report-workflows/{id}/promote` | `200` |
| `GET /export/pptx` | `200`, `43237` bytes |
| `GET /export/snapshot` | `200`, `decisiondoc_report_workflow_snapshot.v1` |

## 4. Release Scope

`v1.1.59`는 company handoff packaging evidence hardening release입니다.

주요 변경:

- `scripts/package_company_handoff.py` one-shot final package command 추가
- company handoff bundle 생성, manifest 검증, zip archive, `.zip.sha256` sidecar 생성 자동화
- handoff readiness report, bundle manifest, bundle README, package summary, verifier output에 `source_commit`, `source_describe`, `source_exact_tag`, `exact_release_tag` metadata 추가
- tag 이후 생성된 handoff package도 실제 source commit을 추적할 수 있도록 traceability 강화
- company delivery guide와 admin handoff index에 package source metadata 확인 절차 추가

## 5. Handoff Decision

| 항목 | 판정 |
|------|------|
| release tag source | `ACCEPTED` |
| Docker image publish | `ACCEPTED` |
| production deploy | `ACCEPTED` |
| deployed smoke | `ACCEPTED` |
| Report Workflow ERP smoke | `ACCEPTED` |
| provider routing | `ACCEPTED` |
| company handoff package evidence | `ACCEPTED` |
| ready for continued production use | `YES` |

## 6. Remaining Exclusions

- 이 record는 `v1.1.59` production deploy acceptance이며, customer-specific isolated environment rollout은 포함하지 않습니다.
- AWS SAM stage-first / promote-only lane conversion은 이 acceptance 범위가 아닙니다.
- `.env.prod`, provider API key, ops key, server SSH key 등 secret 원문은 이 문서와 repository에 포함하지 않습니다.

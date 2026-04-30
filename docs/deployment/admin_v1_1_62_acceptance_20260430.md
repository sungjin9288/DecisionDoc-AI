# DecisionDoc AI Admin v1.1.62 Acceptance Record — 2026-04-30

이 문서는 `admin.decisiondoc.kr` 운영 환경에 `v1.1.62` production release가 정상 반영되었음을 고정하기 위한 acceptance record입니다.

## 1. Acceptance Summary

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| release tag | `v1.1.62` |
| release commit | `53a5d78d30bfe34869b07b300dfa7097778d8e21` |
| Docker image | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.62` |
| Docker digest | `sha256:2bd5095422cdbb6ec051de33f5082c283fa26fd05f7ed81646d632dc53a62be7` |
| GitHub tag | `https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.62` |
| GitHub Actions CD run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/25166117185` |
| CD result | `success` |
| post-deploy timestamped report | `reports/post-deploy/post-deploy-20260430T124744Z.json` |
| acceptance recorded at | `2026-04-30 21:51 KST` |

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
| app | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.62`, healthy |
| nginx | `nginx:alpine`, running |
| compose env file | `/opt/decisiondoc/.env.prod` |
| nginx config | `nginx -t` passed |

## 3. Post-Deploy Smoke Evidence

Server-side post-deploy check:

| 항목 | 결과 |
|------|------|
| deploy started | `2026-04-30T12:46:54Z` |
| deploy completed | `2026-04-30T12:49:34Z` |
| production job duration | `2m40s` |
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
| `GET /export/pptx` | `200`, `43653` bytes |
| `GET /export/snapshot` | `200`, `decisiondoc_report_workflow_snapshot.v1` |

## 4. Release Scope

`v1.1.62`는 `v1.1.61` production deploy acceptance와 company handoff evidence를 tag source에 포함시키기 위한 follow-up release입니다.

주요 변경:

- `docs/deployment/admin_v1_1_61_acceptance_20260430.md`를 추가해 직전 production deploy acceptance를 repository에 고정
- `docs/deployment/admin_v1_handoff.md`의 최신 production acceptance 기준을 v1.1.61로 갱신
- company handoff readiness gate와 bundle 생성 기준을 v1.1.61 acceptance evidence로 갱신
- company handoff regression tests를 최신 release evidence 기준으로 보강
- runtime API feature 동작은 v1.1.61 배포 기준과 동일하며, 이 release는 acceptance/handoff evidence를 태그에 포함하는 운영 증적 release로 정의

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

- 이 record는 `v1.1.62` production deploy acceptance이며, customer-specific isolated environment rollout은 포함하지 않습니다.
- AWS SAM stage-first / promote-only lane conversion은 이 acceptance 범위가 아닙니다.
- `.env.prod`, provider API key, ops key, server SSH key 등 secret 원문은 이 문서와 repository에 포함하지 않습니다.

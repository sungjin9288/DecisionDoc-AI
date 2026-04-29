# DecisionDoc AI Admin v1.1.58 Acceptance Record — 2026-04-30

이 문서는 `admin.decisiondoc.kr` 운영 환경에 `v1.1.58` production release가 정상 반영되었음을 고정하기 위한 acceptance record입니다.

## 1. Acceptance Summary

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| release tag | `v1.1.58` |
| release commit | `c517f8d4b200e13efcb14ccdf51ad45db5fe99f1` |
| Docker image | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.58` |
| Docker digest | `sha256:f426979e30fb7dcd11b7da559c2cef437ef74eeb0b5436cf9c021b70ed5d2f8d` |
| GitHub release | `https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.58` |
| GitHub Actions CD run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/25115696808` |
| CD result | `success` |
| post-deploy timestamped report | `reports/post-deploy/post-deploy-20260429T144537Z.json` |
| acceptance recorded at | `2026-04-30 00:06 KST` |

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
| app | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.58`, healthy |
| nginx | `nginx:alpine`, running |
| compose env file | `/opt/decisiondoc/.env.prod` |
| nginx config | `nginx -t` passed |

## 3. Post-Deploy Smoke Evidence

Server-side post-deploy check:

| 항목 | 결과 |
|------|------|
| deploy started | `2026-04-29T14:44:16Z` |
| deploy completed | `2026-04-29T14:47:37Z` |
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
| `POST /report-workflows/{id}/promote` | `200` |
| `GET /export/pptx` | `200`, `43598` bytes |
| `GET /export/snapshot` | `200`, `decisiondoc_report_workflow_snapshot.v1` |

## 4. Release Scope

`v1.1.58`는 runtime feature release라기보다 production release governance hardening release입니다.

주요 변경:

- `scripts/check_release_readiness.py` release tag dry-run helper 추가
- production tag 생성 전 numeric semver, clean tracked tree, `origin/main` 도달 가능성, local/remote tag 중복 검증
- remote tag lookup 실패 시 fail-closed 처리
- release target이 `origin/main`에는 포함되지만 최신 tip이 아닐 때 stale target warning 노출
- production tag source gate, deploy script, GHCR semver normalization, CD summary/test coverage 보강
- operator runbook에 readiness warning 해석 기준 추가

## 5. Handoff Decision

| 항목 | 판정 |
|------|------|
| release tag source | `ACCEPTED` |
| Docker image publish | `ACCEPTED` |
| production deploy | `ACCEPTED` |
| deployed smoke | `ACCEPTED` |
| Report Workflow ERP smoke | `ACCEPTED` |
| provider routing | `ACCEPTED` |
| ready for continued production use | `YES` |

## 6. Remaining Exclusions

- 이 record는 `v1.1.58` production deploy acceptance이며, sales PDF pack 재생성은 포함하지 않습니다.
- 별도 customer-specific isolated environment rollout은 이 acceptance 범위가 아닙니다.
- AWS SAM stage-first / promote-only lane conversion은 이 acceptance 범위가 아닙니다.
- `.env.prod`, provider API key, ops key, server SSH key 등 secret 원문은 이 문서와 repository에 포함하지 않습니다.

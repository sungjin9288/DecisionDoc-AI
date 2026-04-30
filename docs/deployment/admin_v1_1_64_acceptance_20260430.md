# DecisionDoc AI Admin v1.1.64 Acceptance Record — 2026-04-30

이 문서는 `admin.decisiondoc.kr` 운영 환경에 `v1.1.64` production release가 정상 반영되었음을 고정하기 위한 acceptance record입니다.

## 1. Acceptance Summary

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| release tag | `v1.1.64` |
| release commit | `c8fa29c406a65b51059ff7e947372d98a6133cf7` |
| Docker image | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.64` |
| Docker digest | `sha256:2aa30fc11b9126b79b39e7a3a645a03b1f91f5ac97b91d9087036d400f394405` |
| GitHub tag | `https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.64` |
| GitHub Actions CD run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/25168186232` |
| CD result | `success` |
| post-deploy timestamped report | `reports/post-deploy/post-deploy-20260430T133136Z.json` |
| acceptance recorded at | `2026-04-30 22:39 KST` |

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
| app | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.64`, healthy |
| nginx | `nginx:alpine`, running |
| compose env file | `/opt/decisiondoc/.env.prod` |
| nginx config | `nginx -t` passed |

## 3. Post-Deploy Smoke Evidence

Server-side post-deploy check:

| 항목 | 결과 |
|------|------|
| deploy started | `2026-04-30T13:30:55Z` |
| deploy completed | `2026-04-30T13:33:20Z` |
| production job duration | `2m25s` |
| report status | `passed` |
| smoke_results_available | `true` |

Smoke route results:

| check | result |
|-------|--------|
| `GET /health` | `200`, request_id=`a252fd06-0cb0-4633-aef3-82ae0b2de4a0` |
| `POST /generate` without key | `401` |
| `POST /generate` with key | `200`, request_id=`373763bf-8c21-4d04-8f9c-09b3ac121e8b`, bundle_id=`a1c3869b-4d13-4b38-bbf5-7d3030e153cd` |
| `POST /generate/export` with key | `200`, request_id=`24e44328-239e-45e6-aa18-ceb9426e5ee7`, bundle_id=`f4ea0d30-9aec-4182-b270-14e3b1d62281`, files=`4` |
| `POST /generate/with-attachments` without key | `401` |
| `POST /generate/with-attachments` with key | `200`, request_id=`48644ba3-96e1-4c26-80dd-18490e07f70d`, bundle_id=`bf9d7f76-2eb1-4061-909d-0a8a9c573e87`, files=`1`, docs=`4` |
| `POST /generate/from-documents` without key | `401` |
| `POST /generate/from-documents` with key | `200`, request_id=`847ed4e2-f052-4878-95f9-10c9b59e1117`, bundle_id=`207097a6-99be-4aa2-a687-fe17b10ff6c2`, files=`1`, docs=`2` |

Report Workflow ERP smoke results:

| check | result |
|-------|--------|
| `GET /health` | `200` |
| `POST /report-workflows` without key | `401` |
| `POST /report-workflows` with key | `200`, workflow_id=`93ca01d6-f1fb-4f75-b192-8ede2e4923a2` |
| `POST /slides/generate` before planning approval | `400` |
| `POST /planning/generate` | `200`, `slide_plans=2` |
| `POST /planning/approve` | `200` |
| `POST /slides/generate` | `200`, `slides=2` |
| `POST /final/submit` before slide approvals | `400` |
| slide approvals | `200`, `approved=2` |
| `POST /final/submit` | `200`, approval_id=`7c90f67d-2262-4cfe-b607-84a69865d216` |
| `POST /final/executive-approve` before PM approval | `400` |
| `POST /final/pm-approve` | `200` |
| `POST /final/executive-approve` | `200` |
| `POST /projects` | `200`, project_id=`abcf220a-af71-4f7f-b5de-d4fd9447f395` |
| `POST /report-workflows/{id}/promote` | `200`, project_document_id=`ba21f38c-f068-4b29-8795-17a58b6565e4` |
| `GET /export/pptx` | `200`, `43431` bytes |
| `GET /export/snapshot` | `200`, `decisiondoc_report_workflow_snapshot.v1` |

## 4. Release Scope

`v1.1.64`는 Report Workflow ERP의 결재 책임자 metadata와 최종 승인 handoff 구조를 production에 반영한 release입니다.

주요 변경:

- Report Workflow 생성/수정 API와 UI에 `owner`, `pm_reviewer`, `executive_approver` assignee metadata를 추가
- 최종 제출 시 workflow assignee를 기존 `ApprovalStore`의 PM review / executive approval step metadata로 연결
- PM과 대표 결재자가 동일한 경우 또는 제출자와 최종 결재자가 같은 경우 backend가 차단하지 않고 `quality_warnings`에 self-approval risk로 기록
- assignee 불일치 승인 시에도 요청자는 차단하지 않고 audit metadata와 quality warning을 남겨 운영자가 확인 가능하도록 처리
- `docs/specs/report_workflow_erp/PRD.md`와 `IMPLEMENT.md`에 승인 역할/책임자 구조를 고정
- 기존 `/generate`, `/generate/export`, `/generate/with-attachments`, `/generate/from-documents` 원클릭 문서 생성 흐름은 동작 변경 없이 유지

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

- 이 record는 `v1.1.64` production deploy acceptance이며, customer-specific isolated environment rollout은 포함하지 않습니다.
- AWS SAM stage-first / promote-only lane conversion은 이 acceptance 범위가 아닙니다.
- role 기반 다중 사용자 인증과 조직별 실제 사용자 directory 연동은 다음 phase 범위입니다.
- `.env.prod`, provider API key, ops key, server SSH key 등 secret 원문은 이 문서와 repository에 포함하지 않습니다.

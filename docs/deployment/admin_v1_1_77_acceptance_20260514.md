# DecisionDoc AI Admin v1.1.77 Acceptance Record — 2026-05-14

이 문서는 `admin.decisiondoc.kr` 운영 환경에 `v1.1.77` production release가 정상 반영되었고, runtime version display가 실제 배포 tag와 동기화되었음을 고정하기 위한 acceptance record입니다.

## 1. Acceptance Summary

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| release tag | `v1.1.77` |
| release commit | `efd350b0b237a3709284dc16394186b85e64b28f` |
| Docker image | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.77` |
| Docker digest | `sha256:6bb14d8ccb05dca242b2d24fdcf50b5f705bd528f04c13be82b964313e9efc44` |
| GitHub tag | `https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.77` |
| GitHub Actions CI run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/25835487045` |
| GitHub Actions CD run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/25835735647` |
| CI result | `success` |
| CD result | `success` |
| post-deploy timestamped report | `reports/post-deploy/post-deploy-20260514T011408Z.json` |
| UAT session evidence | `reports/uat/uat-session-20260514T021318Z-v1-1-77-version-display-post-deploy-uat.md` |
| acceptance recorded at | `2026-05-14 11:18 KST` |

## 2. Production Verification

Latest live `/version` check:

| 항목 | 결과 |
|------|------|
| version | `1.1.77` |
| api_version | `v1` |
| environment | `prod` |
| provider | `claude,gemini,openai` |
| storage | `local` |
| maintenance | `false` |

Latest live `/health` check:

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
| app | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.77`, healthy |
| nginx | `nginx:alpine`, running |
| compose env file | `/opt/decisiondoc/.env.prod` |
| nginx config | `nginx -t` passed |

## 3. Version Display Verification

`v1.1.77`의 핵심 acceptance 기준은 runtime release metadata와 UI 표시가 같은 release를 바라보는지입니다.

| check | result |
|-------|--------|
| `GET /version` | `200`, `version=1.1.77` |
| production footer render | headless Chromium에서 `DecisionDoc AI v1.1.77` 확인 |
| stale footer text | production HTML에 `DecisionDoc AI v1.1.57` 없음 |
| service worker cache | production `sw.js`가 `decisiondoc-static-shell-v2` 사용 |
| runtime version injection | production deploy log에서 `DECISIONDOC_APP_VERSION="$IMAGE_TAG"` 확인 |

## 4. Post-Deploy Smoke Evidence

Server-side post-deploy check:

| 항목 | 결과 |
|------|------|
| deploy started | `2026-05-14T01:13:18Z` |
| deploy completed | `2026-05-14T01:16:14Z` |
| production job duration | `3m1s` |
| report status | `passed` |
| smoke_results_available | `true` |

Smoke route results:

| check | result |
|-------|--------|
| `GET /health` | `200`, request_id=`b741d70f-8821-4382-b6bc-7825632127bd` |
| `POST /generate` without key | `401` |
| `POST /generate` with key | `200`, request_id=`17793528-ab57-4b51-87b2-1ac634e7e011`, bundle_id=`1198cfbf-8fe7-40df-81a2-6ff1e4d21dfd` |
| `POST /generate/export` with key | `200`, request_id=`41278ba8-9962-48e4-b84c-ce2fca84f12a`, bundle_id=`bbe80291-71d6-47ff-a0f8-2a5615037a17`, files=`4` |
| `POST /generate/export-edited PDF` with key | `200`, bytes=`117909` |
| `POST /generate/export-edited HWPX` with key | `200`, bytes=`4940`, ext=`hwpx` |
| `POST /generate/with-attachments` without key | `401` |
| `POST /generate/with-attachments` with key | `200`, request_id=`ed5eb53e-c9a4-49e4-9c01-aa5d1148d8f2`, bundle_id=`38668387-3ad0-485a-b186-72e4515c5ba1`, files=`1`, docs=`4` |
| `POST /generate/from-documents` without key | `401` |
| `POST /generate/from-documents` with key | `200`, request_id=`c7d5287a-6739-4195-9e59-ed0537f40246`, bundle_id=`9c13240b-e8d7-4165-ae90-670ad22f17e9`, files=`1`, docs=`2` |

Report Workflow ERP smoke results:

| check | result |
|-------|--------|
| `GET /health` | `200` |
| `POST /report-workflows` without key | `401` |
| `POST /report-workflows` with key | `200`, workflow_id=`2bedfb20-bc32-4b29-a1c8-4a4812c77ce2` |
| `POST /slides/generate` before planning approval | `400` |
| `POST /planning/generate` | `200`, `slide_plans=2` |
| `POST /planning/approve` | `200` |
| `POST /slides/generate` | `200`, `slides=2` |
| `POST /final/submit` before slide approvals | `400` |
| slide approvals | `200`, `approved=2` |
| `POST /final/submit` | `200`, approval_id=`7ec6a26a-e3b1-4579-a31c-2061efbd5577` |
| `POST /final/executive-approve` before PM approval | `400` |
| `POST /final/pm-approve` | `200` |
| `POST /final/executive-approve` | `200` |
| `POST /projects` | `200`, project_id=`94234e15-228e-475b-8075-885bca1c53e4` |
| `POST /report-workflows/{id}/promote` | `200`, project_document_id=`bfd2f03b-77a1-4f25-95b1-926917ee622b` |
| `GET /export/pptx` | `200`, `43945` bytes |
| `GET /export/snapshot` | `200`, `decisiondoc_report_workflow_snapshot.v1` |

## 5. Release Scope

`v1.1.77`는 운영 release metadata 신뢰성을 보강하기 위한 application/runtime alignment release입니다.

주요 변경:

- `DECISIONDOC_APP_VERSION` runtime config를 추가해 `/version`, FastAPI metadata, Docker Compose production deploy가 Docker image tag 기준 version을 사용하도록 연결
- static footer의 stale hardcoded `DecisionDoc AI v1.1.57` 표시 제거
- service worker cache name을 release-number hardcode에서 분리
- production CD에서 release tag image version을 container env로 주입
- version/PWA/CD/deploy regression tests 보강

직전 production baseline에서 유지되는 핵심 기능:

- HWP 버튼 결과는 `.hwpx` export path로 유지
- PDF/HWPX export-edited smoke 통과
- Report Workflow ERP smoke 통과
- 기존 one-click document generation flow 유지

## 6. Handoff Decision

| 항목 | 판정 |
|------|------|
| release tag source | `ACCEPTED` |
| Docker image publish | `ACCEPTED` |
| production deploy | `ACCEPTED` |
| runtime version display | `ACCEPTED` |
| deployed smoke | `ACCEPTED` |
| Report Workflow ERP smoke | `ACCEPTED` |
| provider routing | `ACCEPTED` |
| company handoff package evidence | `ACCEPTED` |
| ready for continued production use | `YES` |

## 7. Remaining Exclusions

- 이 record는 `v1.1.77` production deploy acceptance이며, customer-specific isolated environment rollout은 포함하지 않습니다.
- AWS SAM stage-first / promote-only lane conversion은 이 acceptance 범위가 아닙니다.
- 일반 Chrome/Safari에서의 실제 파일 다운로드/열기 검수는 로컬 UAT 세션의 후속 체크리스트로 분리합니다.
- `.env.prod`, provider API key, ops key, server SSH key 등 secret 원문은 이 문서와 repository에 포함하지 않습니다.

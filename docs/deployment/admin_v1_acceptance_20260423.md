# DecisionDoc AI Admin v1 Acceptance Record — 2026-04-23

이 문서는 `admin.decisiondoc.kr` 운영 환경을 회사 전달 가능한 상태로 고정하기 위한 acceptance record입니다.

## 1. Acceptance Summary

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| 운영 기준 서버 | `decisiondoc-admin-prod` |
| release tag | `v1.1.4` |
| server checkout | `1bb01f1` / `v1.1.4` |
| Docker image | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.4` |
| GitHub release | `https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.4` |
| GitHub Actions CD run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/24837361929` |
| post-deploy latest report | `./reports/post-deploy/latest.json` |
| post-deploy timestamped report | `./reports/post-deploy/post-deploy-20260423T131803Z.json` |
| acceptance recorded at | `2026-04-23 23:03 KST` |

## 2. Production Verification

Latest live health check:

| 항목 | 결과 |
|------|------|
| `/health` status | `ok` |
| provider | `claude,gemini,openai` |
| maintenance | `false` |
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

Container verification:

| service | result |
|---------|--------|
| app | `ghcr.io/sungjin9288/decisiondoc-ai:1.1.4`, healthy |
| nginx | `nginx:alpine`, running |
| compose env file | `/opt/decisiondoc/.env.prod` |

## 3. Post-Deploy Smoke Evidence

Latest server-side post-deploy check:

| 항목 | 결과 |
|------|------|
| report status | `passed` |
| finished_at | `2026-04-23T13:19:27.652163+00:00` |
| skip_smoke | `false` |
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

## 4. Company Delivery Pack

Sales PDF pack regenerated from the latest tracked sales documents:

| file | size |
|------|------|
| `output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf` | `209130` bytes |
| `output/pdf/decisiondoc_ai_executive_intro_ko.pdf` | `240160` bytes |
| `output/pdf/decisiondoc_ai_notebooklm_comparison_ko.pdf` | `268144` bytes |
| `output/pdf/decisiondoc_ai_internal_deployment_brief_ko.pdf` | `248642` bytes |
| `output/pdf/decisiondoc_ai_company_delivery_guide_ko.pdf` | `288032` bytes |

Validation performed:

- `python3 scripts/build_sales_pack.py`
- PDF header and EOF marker check for all 5 PDFs
- first-page PNG render check for generated PDFs
- company delivery guide first page visually checked

## 5. Security Boundary

Do not include these secrets in email, chat, or this repository:

- `.env.prod` raw file
- `DECISIONDOC_API_KEYS`
- `DECISIONDOC_OPS_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- server SSH private key

Secret transfer must use a separate secure channel approved by the operator.

## 6. Handoff Decision

| 항목 | 판정 |
|------|------|
| production deploy | `ACCEPTED` |
| deployed smoke | `ACCEPTED` |
| provider routing | `ACCEPTED` |
| company delivery pack | `ACCEPTED` |
| ready for company handoff | `YES` |

## 7. Post-Acceptance Repo Baseline

운영 acceptance 이후 `main` repo baseline도 다시 정리했습니다. 이 항목은 **새 production deploy 기록이 아니라**, handoff 이후 repo hardening과 CI 상태를 고정하기 위한 참고 증적입니다.

| 항목 | 결과 |
|------|------|
| latest main head | `b064c6a` |
| latest main CI run | `https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/24847952826` |
| CI result | `success` |
| latest repo hardening scope | `XML attachment parsing defusedxml 전환` + `Security Scan advisory false red 제거` |
| production acceptance decision changed | `NO` |

Remaining exclusions:

- `dawool.decisiondoc.kr` live rollout is not included in this acceptance.
- AWS SAM stage-first / promote-only lane conversion is not included in this acceptance.
- Customer-specific isolated environment rollout is the next phase, not part of this admin v1 baseline.

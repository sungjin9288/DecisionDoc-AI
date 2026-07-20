# DecisionDoc AI

> 의사결정 문서·제안서·보고서를 **생성 → 검증 → 검토·승인 → 내보내기**까지 하나의 워크플로로 관리하는 FastAPI 기반 AI 문서 생성 플랫폼.

LLM이 만든 결과를 단발성 텍스트가 아니라 **업무 산출물**로 다루는 데 초점을 둔 프로젝트입니다. 멀티 LLM provider 추상화, bundle/template/validation 파이프라인, 승인·이력·감사 워크플로, 공공조달(G2B) Go/No-Go 보조 흐름을 포함합니다.

> ⚠️ 상태: **MVP 구현 후 고도화 중**. 운영 플랫폼이 아닌 PoC/MVP이며, 검증되지 않은 성과 수치는 사용하지 않습니다. 아래 수치는 모두 소스 코드에서 직접 카운트한 값이며 측정 커맨드를 함께 표기합니다.

---

## Why I Built This

컨설팅 현장에서 제안서·평가보고서의 품질이 작성자 숙련도에 따라 들쭉날쭉하고, 같은 문서 구조를 매번 다시 잡는 낭비를 직접 겪었습니다. "문서 품질을 사람의 숙련도가 아니라 시스템으로 보장할 수 없을까"가 출발점입니다. 컨설팅 경험에서 나온 문제 정의를 작동하는 서비스로 옮긴 사례입니다.

핵심 문제는 **LLM 생성 결과를 단순 텍스트가 아니라 검토·승인 가능한 업무 산출물로 관리하는 구조**를 만드는 것입니다.

---

## Features

| Feature | 설명 |
|---------|------|
| 문서 생성 API | `/generate` 계열 — 입력/출력을 Pydantic 모델로 표준화 |
| 참고 문서 기반 생성 | `/generate/from-documents`, `/generate/from-pdf` — 첨부 자료 반영 |
| Bundle / Template / Validation | BundleSpec·DocumentSpec + Jinja2 + lint 단계로 문서 유형별 품질 편차 축소 |
| 멀티 LLM Provider | `mock` / `openai` / `gemini` / `claude` / `local` — factory + fallback chain |
| 검토·승인 워크플로 | `/approvals` 계열 — submit / review / approve / reject / download |
| 프로젝트·결재 상태 무결성 | 프로젝트와 결재 record를 tenant별 local/S3 state에 결속하고 blank·malformed·invalid UTF-8·duplicate key/identity와 owned schema drift를 원본 보존 상태로 차단. 두 store의 mutation은 conditional create/CAS와 충돌 재시도로 worker 간 overwrite를 방지 |
| 보고서 워크플로우 상태 무결성 | 기획·장표·시각자료·최종 승인·승격 state를 tenant별 local/S3 object에 결속하고 blank·malformed·invalid UTF-8·duplicate workflow/nested identity와 backend failure를 원본 보존 상태로 차단. Conditional create/CAS와 충돌 재시도로 worker 간 update 유실과 상충하는 최종 결정을 방지 |
| 감사·프라이버시 | tenant별 append-only JSONL을 local/S3 공통 backend로 보존하고 손상·foreign·중복 identity를 fail closed 처리. Conditional create/CAS와 `log_id` commit reconciliation으로 worker 간 append 유실을 방지. `/admin/audit-logs`, `/auth/export-my-data`, `/auth/withdraw` 제공 |
| 멀티테넌시·관리자 | `/admin/tenants`, 모델 학습/승격(`/admin/models/...`). Root tenant registry mutation은 conditional create/CAS와 bounded private receipt로 worker 간 create·update·API key rotation 유실을 방지 |
| Fine-tune·model authority 무결성 | dataset JSONL, export metadata와 model lifecycle을 tenant별 local/S3 state에 결속하고 손상·중복 identity를 fail closed 처리. 객체별 conditional create/CAS, private append/incarnation receipt와 immutable export create로 worker 간 append·clear·export·model update 유실과 불확실 commit을 조정 |
| DocumentOps governance review overview | Ops 전용 read-only API가 training governance, selected-backend artifact inventory, reviewer sign-off를 독립적으로 읽어 하나의 검토 상태와 다음 행동으로 정리. Source report 생성 시각만 제외한 SHA-256으로 직전 browser 관측과 `최초·동일·변경`을 구분하되 비교값을 저장하지 않음. Export·freeze·dry-run approval·execution request·audit 저장 또는 planning provider/model 변경 뒤에는 열린 overview를 즉시 `RECHECK REQUIRED`로 낮추고, 성공한 새 조회가 끝나야 ready 표시를 복구함. Trajectory Stats, task-filtered Reviewed SFT export 목록, Training Readiness는 같은 tenant의 연속 요청 중 최신 success/error만 반영해 이전 응답이 현재 count, artifact 목록, freeze 승인 대상을 되돌리지 못함. Training Audit Checklist도 최신 request·tenant·provider/model 조건만 반영하며 조건 변경 시 기존 `Audit 저장` control을 제거하고, audit 저장 결과를 진행 중 이전 read가 가리지 못하게 함. Governance 조회와 sign-off handoff 다운로드는 surface·aggregate status·read-only 여부만 append-only audit에 남기고 fingerprint와 source report는 복사하지 않음. 합성 snapshot의 원자성을 주장하지 않고 object 삭제, dataset upload, provider call, training, model promotion을 허용하지 않음 |
| 계정·초대 상태 무결성 | 사용자 계정과 초대 lifecycle을 tenant별 local/S3 state에 결속하고 손상·중복 identity를 fail closed 처리. Conditional create/CAS, atomic first-admin precondition과 claim-before-account-create로 worker 간 계정 변경 유실·복수 초기 관리자·초대 중복 수락을 방지 |
| SSO 설정 상태 무결성 | LDAP·SAML·GCloud·OAuth2 설정과 암호화된 secret을 tenant별 local/S3 state에 결속하고 손상·unknown provider·foreign ownership·복호화 실패를 fail closed 처리. Partial update는 conditional create/CAS로 최신 설정에 재적용 |
| 사용자 템플릿 상태 무결성 | 재사용 문서 입력을 tenant별 local/S3 JSONL에 결속하고 손상·중복 identity를 원본 보존 상태로 fail closed 처리 |
| 생성 이력 상태 무결성 | 문서 생성·재열기·즐겨찾기·시각자료·지식 승격 이력을 tenant별 local/S3 JSONL에 결속하고 손상·중복 identity를 원본 보존 상태로 fail closed 처리 |
| 프로젝트 지식 상태 무결성 | 참고 문서 `index.json`을 tenant/project별 local/S3 conditional create/CAS authority로 두고 충돌 시 최신 문서 집합에 mutation을 재적용. 본문·style은 private incarnation 아래 immutable object로 발행하며 SHA-256·크기·ownership·중복·legacy orphan을 검증하고, 최근 64개 private receipt로 불확실 commit을 조정. 생성 context, procurement 평가, report promotion도 같은 backend를 사용 |
| G2B 즐겨찾기 상태 무결성 | 공고 즐겨찾기를 tenant/user별 local/S3 state에 결속하고 손상·중복 identity를 빈 목록으로 축소하지 않는다. 기존 owner 없는 record는 호환하고 foreign owner는 노출·변경하지 않으며 add/remove는 conditional create/CAS와 private bookmark identity로 조정 |
| 공공조달 판단 상태 무결성 | Go/No-Go 판단 record와 source snapshot을 tenant/project별 local/S3 state에 결속하고 손상 JSON·중복 snapshot metadata·경로 drift·비직렬화 payload를 원본 보존 상태로 차단. 판단 mutation은 conditional create/CAS와 bounded private receipt로 worker 간 update 유실과 불확실 commit을 조정하고 snapshot은 immutable create로 저장 |
| 공공조달 검토 증빙 상태 무결성 | Review record·원본 packet·content-addressed reviewed-package를 tenant/project/packet SHA-256별 local/S3 state에 결속하고 손상·누락·부분 쓰기를 fail closed 처리. S3 conditional create와 ETag CAS로 worker 간 record overwrite를 차단 |
| Decision Council 상태 무결성 | 조달 의사결정 session을 tenant/project별 local/S3 state에 결속하고 blank·malformed·invalid UTF-8·duplicate key와 owned session identity drift를 원본 보존 상태로 차단. Session upsert는 conditional create/CAS, canonical identity와 bounded private receipt로 worker 간 revision 유실과 불확실 commit을 조정 |
| 회의 녹음 상태 무결성 | 녹음 metadata와 audio SHA-256·크기를 tenant/project/recording 경로에 결속하고 손상·identity drift·UUID 충돌·audio 변조를 fail closed 처리. Recording별 metadata mutation은 conditional create/CAS와 bounded private receipt로 worker 간 전사·승인 유실과 불확실 commit을 조정 |
| 결제 권한 상태 무결성 | plan·status·Stripe identity를 tenant별 local/S3 state에 결속하고 손상·unknown value를 원본 보존 상태로 fail closed 처리. Conditional create/CAS와 bounded private receipt로 worker 간 plan·status·Stripe identity 유실과 불확실 commit을 조정 |
| 스타일 프로필 상태 무결성 | tone guide·bundle override·분석 예시·기본 스타일을 tenant별 local/S3 state에 결속하고 손상·중복 identity·다중 default를 원본 보존 상태로 fail closed 처리. Profile mutation은 conditional create/CAS와 private incarnation으로 replacement lifecycle을 구분 |
| 품질 학습 상태 무결성 | feedback·eval evidence·runtime prompt override를 tenant별 local/S3 state에 결속하고 손상·중복 JSON key·owned schema drift를 원본 보존 상태로 fail closed 처리. Override mutation은 conditional create/CAS, payload-bound save receipt와 stable incarnation으로 refresh 경쟁 중 applied count와 불확실 commit을 조정 |
| 품질 실험·요청 패턴 상태 무결성 | A/B prompt experiment와 freeform·sketch request pattern을 tenant별 local/S3 state에 결속하고 손상·중복 identity를 빈 상태로 축소하지 않는다. Variant·hint·experiment identity를 한 CAS assignment로 결속하고 result도 같은 incarnation에만 기록하며, resumable winner claim과 snapshot-bound clear로 worker 경쟁을 조정 |
| 공개 공유 상태 무결성 | 외부 공개 링크의 생성·조회·접근 횟수·취소 lifecycle을 tenant별 local/S3 state에 결속하고 손상·identity drift를 원본 보존 상태로 fail closed 처리 |
| 공공조달 Go/No-Go | G2B 기반 판단부터 tenant별 검토 패킷, 검토함, 1회 완료 receipt, 검증된 reviewed-package 이력과 review-bound downstream provenance까지 연결 (`G2B_API_KEY`, 스모크 옵션 제공) |
| 로컬 procurement decision package evidence | mock/local fixture 기반 12개 artifact, one-screen 검토, deterministic review ZIP, packet-bound browser review draft와 reviewer receipt, review-completed audit envelope, handoff, sign-off, export boundary, CLI contract 검증 경로 |
| 완성 문서 review packet | completed human review receipt 기반 deterministic ZIP, embedded SHA256 index, tamper/path boundary 검증 |
| 품질 교정 파일럿 | Ready artifact 3~5개의 순서·readiness·JSONL SHA-256·외부 학습 비승인 경계를 먼저 검토하고, server-side export package와 local human-review handoff를 각각 exact-membership ZIP으로 고정해 독립 재검증 |
| 보고서 검토 이력 무결성 | 기획안·장표·댓글·승인 단계·시각자료 이력을 tenant에 결속하고, 손상·중복 identity는 원본을 덮어쓰지 않은 채 fail closed 처리 |
| 협업 상태 무결성 | 메시지·알림을 tenant별 local/S3 state에 결속하고 손상 문서·중복 identity를 fail closed 처리. 객체별 conditional create/CAS와 bounded private receipt로 worker 간 게시·수정·읽음·전송 상태 유실을 방지 |
| 재현 가능한 제출형 export | 같은 runtime과 입력에서 DOCX·PDF·PPTX·XLSX·HWPX 반복 생성 bytes와 SHA-256을 안정적으로 유지 |
| DocumentOps 검토 작업대 | tenant-scoped trajectory JSONL을 선택된 local/S3 `StateBackend`의 단일 conditional create/CAS authority로 관리한다. Append와 사람 review는 충돌 시 최신 record 집합에 최대 32회 재적용하고, private append/incarnation identity와 최근 64개 review receipt로 commit 응답 유실 뒤 successor mutation을 조정한다. Expected review version은 최신 CAS state에서 비교해 오래 열린 화면의 덮어쓰기를 `409`로 차단하며 private metadata는 목록·상세·SFT source에 노출하지 않는다. 검색·필터·정렬, summary-first 상세 조회, 사용자·tenant·trajectory별 page-memory 초안, signed tenant context, 민감 본문을 제외한 audit 추적도 유지한다. |

---

## Tech Stack

| Area | Stack |
|------|-------|
| Language | Python 3.12 |
| Backend | FastAPI, Pydantic v2 |
| Template | Jinja2 (BundleSpec / DocumentSpec) |
| AI / LLM | provider abstraction (mock / openai / gemini / claude / local) + fallback chain |
| Storage | local filesystem / AWS S3 (storage abstraction) |
| Infra | Docker Compose, AWS SAM / Lambda |
| Test | pytest (live / not-live 마커 분리), smoke scripts |
| Ops | request tracking·logging·metrics middleware, secret-hygiene git hook |

---

## Architecture

레이어 수치는 실측 기반입니다 (재현 커맨드는 [docs/development-plan.md](./docs/development-plan.md) §2 참조).

```text
Client (Web UI / CLI / API)
  │
  ▼
FastAPI (app/main.py — create_app(), 모듈 레벨 side-effect 없음)
  ├─ Middleware 구성 (10개 파일): request_id / observability / security_headers
  │     / rate_limit / audit / auth / tenant / billing / metrics / document_ops_audit
  │     billing은 tenant/auth context가 확정된 뒤 metered request를 검사
  ├─ Routers (23 top-level files, 라우트 268): generate / approvals / projects / knowledge
  │     / report_workflows / auth / sso / admin / audit / billing / dashboard
  │     / history / eval / finetune / local_llm / g2b / templates / health ...
  ▼
Services (44) — 도메인 오케스트레이션
  ├─ generation_service ─ 핵심 파이프라인:
  │     요청 → 캐시 → Provider.generate_bundle() → 스키마 검증
  │        → Stabilizer → Storage 저장 → Jinja2 렌더 → Lint → 반환
  ├─ export 계열: docx / pptx / pdf / hwp / excel (5종)
  ├─ 조달 계열: g2b_collector → procurement_decision_service
  │     → procurement_decision_package/ (16-모듈 패키지)
  └─ 품질 계열: report_quality_learning / prompt_optimizer / validator
  │
  ├────────────────┬─────────────────────┐
  ▼                ▼                     ▼
Providers (5)    Storage (45 modules)   Ops
  factory +        factory +             CloudWatch 조사
  fallback chain   Local / S3            Statuspage 연동
  mock/openai/     (atomic write 공통)   eval / eval_live
  gemini/claude/local
```

**설계 불변식**: Provider·Storage는 ABC + factory(환경변수로만 교체) · 모든 파일 쓰기는 atomic write(tmp + fsync + os.replace) · 라우트 핸들러는 `request.app.state.*`로 의존성 접근 · Request 모델은 `strict=True, extra="forbid"` · mock provider는 결정론적(CI 기준 경로).

배포 모드: 로컬 개발 · Docker Compose · AWS SAM/Lambda. Provider는 `DECISIONDOC_PROVIDER`에 단일 또는 콤마 구분 fallback chain(`openai,gemini`)으로 지정.

---

## Key Design Decisions

- **검토·승인 워크플로를 1급 기능으로** — 컨설팅 산출물은 검토 단계가 필수다. 단순 생성기는 실무에서 안 쓰인다고 판단해 approval/history를 생성 흐름의 일부로 설계.
- **LLM provider abstraction** — 특정 모델 종속은 비용·정책 변화에 취약. Mock/OpenAI/Gemini/Claude/Local을 factory + fallback chain으로 추상화해 교체 가능하게 함. `mock`은 테스트·개발에서 결정론적으로 동작하도록 유지.
- **schema / template / validation 결합** — 문서 유형별 품질 편차를 사람 숙련도가 아니라 구조로 줄이기 위해 BundleSpec/DocumentSpec + Jinja2 + lint 단계를 결합.
- **storage abstraction (local/S3)** — 로컬 개발과 클라우드 운영을 같은 코드 경로로 지원.
- **학습 준비 증적은 실행 권한과 분리** — reviewed export부터 freeze, dry-run approval, execution request, audit까지 ID와 SHA-256을 대조한다. stale 또는 변조 artifact는 로컬 governance ready 상태를 차단하며, 이 흐름은 provider API 호출이나 dataset upload를 허용하지 않는다.

---

## Getting Started

```bash
# 1. 설치
pip install -r requirements.txt
cp .env.example .env
bash scripts/install_git_hooks.sh        # commit 전 secret hygiene 검사 hook

# 2. 실행 (로컬)
python -m uvicorn app.main:app --reload   # http://localhost:8000

# 3. 실행 (Docker)
docker compose up -d
curl http://localhost:8000/health
```

> `install_git_hooks.sh`는 `scripts/check_secret_hygiene.py`를 pre-commit으로 걸어, AWS 자격증명이 커밋에 들어가는 것을 차단합니다.

### Environment (주요 그룹)

`.env.example`에 **94개** 키가 정의돼 있습니다. 대표 그룹만 정리합니다.

```bash
python3 scripts/count_readme_metrics.py --field env_keys  # → 94
```

| 그룹 | 대표 키 |
|------|---------|
| Runtime/Provider | `DECISIONDOC_PROVIDER`, `DECISIONDOC_ENV`, `DECISIONDOC_TEMPLATE_VERSION` |
| Provider Keys | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `LOCAL_LLM_*` |
| Auth/Security | `DECISIONDOC_API_KEY(S)`, `DECISIONDOC_OPS_KEY`, `JWT_SECRET_KEY`, `DECISIONDOC_CORS_*` |
| Storage | `DECISIONDOC_STORAGE`, `DATA_DIR`, `EXPORT_DIR`, `DECISIONDOC_S3_BUCKET`, `AWS_REGION` |
| Search/Retrieval | `DECISIONDOC_SEARCH_ENABLED`, `SERPER_API_KEY`, `BRAVE_API_KEY`, `TAVILY_API_KEY` |
| 공공조달(G2B) | `G2B_API_KEY`, `G2B_SEARCH_DAYS`, `G2B_MAX_RESULTS` |
| Quality Learning | `FINETUNE_AUTO_ENABLED`, `FINETUNE_AUTO_THRESHOLD`, `FINETUNE_BASE_MODEL` |
| 부가 기능 | `VOICE_BRIEF_*`, `MEETING_RECORDING_*`, `STRIPE_*`, `SMTP_*` |

---

## API / Usage

FastAPI 라우트는 **268개**입니다.

```bash
python3 scripts/count_readme_metrics.py --field route_decorators  # → 268
```

대표 도메인:

| Domain | 예시 엔드포인트 |
|--------|----------------|
| Generate | `/generate`, `/generate/export`, `/generate/from-documents`, `/generate/from-pdf` |
| Bundles | `GET /bundles`, `GET /bundles/{bundle_id}` |
| Auth | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/withdraw` |
| Approvals | `/approvals`, `/approvals/{id}/submit`, `/review/approve`, `/reject`, `/download/{fmt}` |
| Admin | `/admin/tenants`, `/admin/models/{id}/promote`, `/admin/audit-logs` |
| Dashboard | `/overview`, `/bundle-performance`, `/score-history/{bundle_id}` |
| Billing | `/billing/status`, `/billing/usage`, `/billing/checkout` |
| Report quality | `/report-workflows/learning/correction-artifacts`, `/report-workflows/learning/correction-artifacts/{artifact_id}`, `/report-workflows/learning/correction-artifacts/pilot-export/preview`, `/report-workflows/learning/correction-artifacts/pilot-export`, `/report-workflows/learning/correction-artifacts/pilot-export/package`, `/report-workflows/learning/correction-artifacts/pilot-package/verify`, `/report-workflows/learning/correction-artifacts/export` |
| Public procurement | `GET /procurement/reviews`, `/projects/{id}/procurement/evaluate`, `/projects/{id}/procurement/review-packet`, `/projects/{id}/procurement/reviews/{sha}/complete`, `/projects/{id}/procurement/reviews/{sha}/reviewed-package`, `/projects/{id}/decision-council/run` |
| DocumentOps | `/api/agent/document-ops/trajectories`, `/api/agent/document-ops/trajectories/governance/overview`, `/api/agent/document-ops/trajectories/governance-artifacts/inventory` |

UI에서 내려받은 품질 교정 검토 패키지를 local review pack으로 가져옵니다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --source-package ~/Downloads/report_quality_pilot_review_package_<sha12>.zip \
  --output-root reports/report-quality
```

입력은 같은 tenant의 ready artifact 3~5개여야 합니다. UI는 export 전에 ordered artifact, resolved/ready count, 전체 JSONL SHA-256, dataset upload·provider fine-tune·training execution·model promotion 비승인 경계를 보여줍니다. Export 요청은 preview의 hash를 `preview_sha256`으로 다시 제출해야 하며, 서버가 현재 ordered JSONL과 일치하지 않으면 `400`으로 차단합니다. 성공한 검토 패키지는 JSONL, server-issued receipt, entry별 size/SHA-256·tenant·artifact 순서·외부 실행 비승인 경계를 기록한 manifest를 포함합니다. 서버와 브라우저가 ZIP 전체 SHA-256을 대조하고 importer도 package membership, receipt, tenant, 순서, no-training boundary를 다시 검증합니다. 수신자는 같은 UI에서 ZIP을 다시 선택해 브라우저 SHA-256과 서버 검증 결과를 대조할 수 있습니다. 서버는 active tenant, exact membership, entry hash, receipt binding, artifact 권한 경계를 메모리에서 확인하고 `persisted=false` 요약만 반환하며, 성공·변조·tenant 차단 결과는 audit에 남깁니다. Importer는 원본 receipt와 embedded package manifest를 각각 `SOURCE_EXPORT_RECEIPT.json`, `SOURCE_PACKAGE_MANIFEST.json`으로 보존하고 `SOURCE_MANIFEST.json` v3에 hash·size·request ID·tenant·artifact 순서를 결속합니다. 따라서 원본 ZIP이 이동되거나 삭제되어도 downstream sync가 pack-local 증빙만으로 manifest hash와 semantics를 다시 검증합니다. Pack 생성 명령은 같은 binding을 사용하는 `HUMAN_REVIEW_WORKSHEET.md`, `human_review_manifest.json`, `review_decisions.json`, `HUMAN_REVIEW_WORKSPACE.html`까지 함께 준비합니다. Browser workspace는 raw JSON을 열지 않아도 교정 전후 planning summary·장표 구조·검토 대상 claim, workflow 상태, final reference, validation error·warning과 필요한 조치를 같은 화면에서 보여줍니다. 검수자는 이 근거를 확인한 뒤 결정·점수·scan·차원별 근거·보완 요청을 입력하고, 원본 pack 파일을 직접 바꾸지 않는 source-bound `review_decisions.browser-draft.json`을 내려받을 수 있습니다. 자동 decision template은 이전 상태를 `previous_decision`으로 남기되 새 파일럿 판단은 모두 `pending`에서 시작합니다. `--browser-draft` apply 경로는 내려받은 파일을 이동하지 않고 읽기 전용 검증한 뒤 정확한 바이트를 SHA 기반 이름으로 pack에 보존하고, draft 반영과 같은 suffix의 receipt 생성을 한 명령으로 수행합니다. 적용으로 draft hash와 상태가 바뀌면 worksheet와 human review manifest도 현재 binding으로 즉시 갱신합니다. 모든 pack mode는 기존 batch 디렉터리나 symlink를 거부하고 decision template, workspace, SHA 보관본, receipt도 기존 파일을 덮어쓰지 않아 사람의 수정 이력을 보존합니다. Decision template과 SHA 보관본은 write-once publication을 사용해 사전 검사 직후 같은 경로가 생겨도 기존 파일을 보존하고 draft 적용 전에 중단합니다. 기존 v1/v2 source manifest와 JSONL + receipt 개별 입력도 호환 경로로 유지합니다. Stale decision이나 일부만 유효한 batch는 draft를 쓰기 전에 전체 차단하며 dry-run이나 실패 batch에서는 draft와 파생 검수 증거를 변경하지 않습니다. 적용 성공 시에는 decision SHA-256과 before/after draft hash 전이를 pack-local receipt로 남기고 현재 pack과 다시 검증할 수 있습니다. Ready JSONL sync는 현재 artifact 상태·count와 일치하는 review manifest 및 `require_ready=true` accepted decision receipt를 요구하고, 성공 결과에 두 evidence SHA를 함께 반환합니다. 따라서 source artifact가 이미 ready여도 새 로컬 검수가 pending이면 downstream batch로 넘어가지 않습니다. 이 로컬 경로는 provider API, dataset upload, training execution, model promotion을 실행하거나 승인하지 않습니다. 자세한 검수 절차는 [Pilot Review Runbook](./docs/specs/report_quality_learning/PILOT_REVIEW_RUNBOOK.md)을 따릅니다.

수신 package 검증은 ZIP 구조 확인에서 끝나지 않습니다. 각 correction artifact의 schema, scan, score, 사람 검토 상태와 learning-ready 조건까지 다시 검사합니다. 통과한 경우에만 reviewer, score, 교정 전후 기획, claim 구분, change request, operator summary와 다음 검토 행동을 `persisted=false` 결과로 보여줍니다. 검증 완료 화면은 package SHA-256에서 local batch ID를 만들고 실제 파일명을 POSIX shell argument로 escape한 importer 명령을 보여주며, 버튼으로 복사할 수 있습니다. 명령은 기본 Downloads 폴더를 가정하므로 다른 위치의 파일은 `--source-package`만 바꿔야 하고, 기존 batch 디렉터리를 덮어쓰지 않습니다. 변조·not-ready·tenant 차단은 audit에 남고 package나 workflow record는 저장하지 않습니다.

Pack-local `HUMAN_REVIEW_WORKSPACE.html`은 browser draft를 내려받은 다음 실행할 dry-run 검증 명령과 결정 반영 명령도 현재 pack 절대경로에 결속해 보여줍니다. 명령은 현재 입력으로 draft를 성공적으로 다운로드한 뒤에만 활성화되고, 그 후 어떤 입력이든 바뀌면 자동으로 다시 잠겨 오래된 Downloads 파일을 새 결정으로 오인하지 않게 합니다. 공백이나 작은따옴표가 있는 경로는 POSIX shell-safe하게 처리되며, 다운로드한 draft의 모든 artifact 결정이 `accepted`일 때만 두 명령에 `--require-ready`를 붙입니다. `changes_requested`, `rejected`, `pending`이 하나라도 있으면 일반 apply 경로를 유지해 사람의 결정을 기록하되 downstream-ready 증거로 과장하지 않습니다. Clipboard API를 쓸 수 없는 local browser에서는 같은 명령을 선택 복사하는 fallback을 사용합니다.

스모크 검증 (문서화된 대표 시나리오):

```bash
python scripts/smoke.py
# 검증: /health, 미인증 /generate 거부, 인증 /generate 성공,
#       /generate/export 성공, /generate/from-documents 업로드 성공
```

로컬 공공조달 decision package evidence 검증:

```bash
CONTRACT_RESULT=/tmp/decisiondoc-cli-contract-manifest-validation-result.json
python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py \
  --write-result \
  --result-path "$CONTRACT_RESULT"
python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py "$CONTRACT_RESULT"
```

이 경로는 `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`을 검증하고, local evidence CLI의 stdout JSON success/failure contract를 확인합니다. fixture 기반 검증이며 provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment를 실행하지 않습니다.

---

## Testing

대표 bundle sample과 구조 품질 evidence를 local mock provider로 재생성합니다.

```bash
python3 scripts/build_finished_doc_review_samples.py \
  --output-dir docs/samples/bundle_quality_evidence \
  --run-name current \
  --no-latest \
  --bundles proposal_kr,performance_plan_kr \
  --formats ''

python3 -m app.eval --out-dir reports/eval/v1
```

2026-07-13 위 명령으로 확인한 결과는 [bundle quality manifest](./docs/samples/bundle_quality_evidence/current/manifest.json) 기준 2개 bundle, 생성 문서 6개, validator 2건 통과, bundle lint 2건 통과, request 대비 단위 수치 literal coverage 2건 통과(미근거 수치 0건)입니다. [review dashboard](./docs/samples/bundle_quality_evidence/current/review.html)는 manifest가 hash로 관리하는 자동 검증 원본이며, [reviewer workspace](./docs/samples/bundle_quality_evidence/current/human_review.html)는 request 근거, 자동 검증, 생성 Markdown, bundle별 사람 검토 상태와 외부 action 경계를 한 화면에 보여줍니다. Reviewer가 화면에서 작성한 값은 현재 manifest와 receipt SHA256에 결속된 local draft JSON으로만 내려받으며, `apply-draft` 검증을 통과해야 증적 원본인 [human review receipt](./docs/samples/bundle_quality_evidence/current/human_review_receipt.json)에 atomic update됩니다. Tracked receipt는 현재 `pending` 상태이고 아직 사람 검토 완료를 주장하지 않으므로 final review packet도 생성하지 않았습니다. Completed receipt에서는 manifest-declared artifact와 embedded SHA256 index만 담은 deterministic ZIP을 만들고 다시 검증할 수 있습니다. [offline eval report](./reports/eval/v1/eval_report.md)는 fixture 10건 중 10건 통과입니다. 모두 mock/local 검증 결과이며 numeric coverage는 수치의 사실성·최신성·문맥 적합성을 보증하지 않습니다. 화면 노출과 draft 생성도 factual grounding이나 human visual review 완료를 뜻하지 않으며 live provider 품질을 증명하지 않습니다.

검수가 끝난 Report Quality pilot은 `finalize` 한 명령으로 ready sync와 deterministic handoff 생성을 마칩니다. Ready JSONL은 private temporary directory에서만 생성·검증한 뒤 ZIP에 포함하고 삭제하므로 사용자가 중간 파일 경로를 연결할 필요가 없습니다. ZIP은 원문 전달용 `HANDOFF_SUMMARY.md`와 브라우저에서 바로 여는 script-free `HANDOFF_SUMMARY.html`을 함께 담습니다. 두 요약 모두 검수자·점수·결정 상태·핵심 hash·권한 경계를 보여주며, v2 verifier는 같은 evidence에서 Markdown과 HTML을 다시 생성해 exact bytes를 대조합니다. 기존 v1 archive는 Markdown 검증 경로로 계속 읽을 수 있습니다. `--browser-summary-output` 또는 `--summary-output`을 선택하면 전체 archive 검증을 통과한 exact HTML 또는 Markdown 하나만 별도 파일로 write-once 발행합니다. 두 옵션은 상호 배타적이며 package와 summary publication은 동시 생성 경쟁에서도 먼저 존재한 증거를 덮어쓰지 않습니다. Standalone JSONL이 필요한 분석 경로에서는 기존 `sync --require-ready`와 `create --jsonl`을 그대로 사용할 수 있습니다.

```bash
python3 scripts/manage_report_quality_pilot_handoff.py finalize \
  reports/report-quality/pilot-rqc-001

python3 scripts/manage_report_quality_pilot_handoff.py verify \
  reports/report-quality/pilot-rqc-001/report_quality_pilot_review_handoff_<sha12>.zip \
  --browser-summary-output reports/report-quality/pilot-rqc-001-handoff-summary.html
```

같은 3-artifact 체인의 wiring을 외부 호출 없이 한 번에 재현할 때는 mock-only demo receipt를 생성합니다.

```bash
python3 scripts/run_report_quality_pilot_handoff_demo.py \
  --output /tmp/decisiondoc-report-quality-pilot-handoff-demo.json

python3 scripts/check_report_quality_pilot_handoff_demo_receipt.py \
  /tmp/decisiondoc-report-quality-pilot-handoff-demo.json \
  --json
```

이 demo는 현재 shell의 provider API key를 실행 중 제거하고 mock provider와 temporary local storage만 사용합니다. API pilot package, source-bound import, simulated local review, ready sync, handoff finalize, exact HTML 검증을 통과한 뒤 write-once JSON receipt만 남깁니다. Read-only checker는 receipt schema, UTC timestamp, 3개 artifact identity, SHA-256 형식, stage 순서, simulated review와 외부 action 경계를 다시 검사하고 파일을 쓰거나 외부 요청을 보내지 않습니다. Receipt의 `human_review_claimed=false`와 `review_evidence=simulated_demo_input`은 이 결과가 실제 사람 검수나 live provider 품질 증거가 아님을 명시합니다.

```bash
pytest tests/                 # 전체
pytest tests/ -m "not live"   # 외부 의존 없는 테스트만
pytest tests/ -m live         # live 마커 테스트
```

테스트 함수는 **3,480개**, **255개 파일**입니다 (AST source definition 기준 카운트). 자동생성 phase 영수증 검증 테스트(제품 기능과 무관)는 2026-07-02 정리에서 제거해 수치에서 제외했습니다.

```bash
python3 scripts/count_readme_metrics.py --field test_functions  # → 3480
python3 scripts/count_readme_metrics.py --field test_files      # → 255
```

> 위 수치는 Python AST로 확인한 `test_` 함수 정의 개수입니다. 각 테스트의 현재 pass 여부는 환경 구성 후 `pytest`로 재확인하세요. 검증되지 않은 커버리지·통과율 수치는 표기하지 않습니다.

포트폴리오 문서와 local evidence는 tracked source allowlist에서 pack으로 동기화하고, 파일별 SHA-256 manifest와 deterministic ZIP으로 재검증할 수 있습니다.

```bash
python3 scripts/manage_portfolio_pack.py sync --prune
python3 scripts/manage_portfolio_pack.py check
python3 scripts/manage_portfolio_pack.py package
python3 scripts/manage_portfolio_pack.py verify-zip
```

ZIP은 로컬 전달용으로 생성되어 git에 포함되지 않습니다. Tracked pack과 `portfolio_manifest.json`은 source membership, content hash, 민감정보 제외 경계를 검토할 수 있는 증거입니다.

CI advisory와 동일한 code quality / security scan:

```bash
ruff check app/ --select=E,F,W --ignore=E501
bandit -r app/ -x app/providers/mock_provider.py -ll
```

2026-07-14 로컬 기준 `ruff`는 `All checks passed!`, `bandit -ll`은 `No issues identified`입니다. Bandit `-ll`은 medium/high severity 기준이며, low severity 항목 전체 해소를 의미하지 않습니다.

---

## Development Plan — 완성까지 남은 것

현재 non-live test suite는 통과했습니다 (`pytest tests/ -m "not live" -q` → 4,231 passed, 2 skipped, 4 deselected, 1 warning, 2026-07-21 H84 실측). "완성"을 막는 갭과 마일스톤은 [docs/development-plan.md](./docs/development-plan.md)에 정의돼 있습니다.

```bash
python3 scripts/check_completion_readiness.py --print-env-template
python3 scripts/check_completion_readiness.py --print-proof-plan
python3 scripts/check_completion_readiness.py
python3 scripts/check_completion_readiness.py --env-file .env.prod
python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
python3 scripts/check_completion_proof_receipt.py --print-template M1
```

위 명령은 남은 M1/M2/M6 실행 준비 조건을 로컬에서 점검하고, 저장된 JSON receipt가 현재 계약과 맞는지 확인합니다. `--print-env-template`은 `.env.prod`에 옮겨 적을 입력값만 출력하고, `--print-proof-plan`은 readiness와 no-secret proof receipt 생성·검증 명령을 별도로 출력합니다. M2/M6 smoke runner는 명시한 `--proof-receipt` 경로에 preflight의 미실행 상태와 실제 smoke의 성공·실패를 atomic JSON으로 기록하며 secret 값과 URL query를 보존하지 않습니다. `.env.prod`와 `reports/`는 gitignore된 runtime 경로라서 secret과 receipt를 커밋하지 않습니다. provider API, G2B live API, AWS runtime, dataset upload, training, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않습니다. 실제 proof 이후에는 `scripts/check_completion_proof_receipt.py`로 receipt를 검증하고, 자세한 증적 실행 순서는 [docs/completion-readiness-runbook.md](./docs/completion-readiness-runbook.md)를 따릅니다.

| 마일스톤 | 내용 | 외부 의존 | 상태 (2026-07-20) |
|----------|------|-----------|--------------------|
| **M1** | Live provider 실증 — openai/gemini/claude 실호출 `-m live` 통과 + 증적 | Gemini quota/billing, Anthropic credits | 보류 — 2026-07-13 OpenAI 1회 통과; 잔여 paid proof는 사용자 요청으로 연기 |
| **M2** | G2B 실데이터 end-to-end 1건 — 수집→정규화→decision package | `G2B_API_KEY` | 미착수 |
| **M3** | excel export를 타 4종 포맷과 동등 수준으로 보강 | 없음 | ✅ 완료 |
| **M4** | CSP nonce 적용 — served HTML `script-src 'unsafe-inline'` 제거 | 없음 | ✅ 완료 — inline handler 0개, HTML nonce 기본 on, local diagnostic opt-out 유지 |
| **M5** | 800줄 초과 모듈 분할 (procurement 패키지 분할 패턴 재사용) | 없음 | ✅ 완료 — 2026-07-14 상수 모듈 drift 재분할 및 800줄 guard 추가, 초과 0개 |
| **M6** | 배포 재검증 + post-deploy smoke 증적 + 데모 URL 접근성 | 배포 환경 | 미착수 |

M1/M2/M6 외부 실증은 현재 보류하고, no-cost local workflow와 evidence 정합성 개선을 계속합니다. 외부 실증을 재개할 때는 각 마일스톤의 완료 정의(DoD)와 readiness receipt를 먼저 확인합니다.

---

## Scope & Limitations

- 완전한 문서관리 시스템이 아니라 **AI-assisted documentation MVP/PoC**입니다.
- 운영 URL(예: `admin.decisiondoc.kr`) **접근성은 추가 검증이 필요**하며, 현재 README에서 동작 보장을 하지 않습니다.
- 실제 사용자 성과 수치·운영 안정성은 검증되지 않았습니다. 검증 범위 밖의 운영 보장은 표기하지 않습니다.
- 다수 기능이 단독 구현/실험 단계이며, **본인 직접 기여 범위는 포트폴리오·면접 설명 시 별도 정리**가 필요합니다.
- 공공조달(G2B) 연동은 외부 API 키·실데이터에 의존하므로, 키 없이는 해당 흐름이 동작하지 않습니다.
- Live provider proof는 2026-07-13 OpenAI 1회만 통과했습니다. Gemini는 API quota, Claude는 account credits로 blocked이며 성공 fallback proof도 남아 있습니다.
- 로컬 procurement decision package evidence 경로는 fixture 검증이며, 실제 입찰 제출·법적 승인·계약상 확약을 의미하지 않습니다.
- 보고서 워크플로우 이력은 tenant별 local/S3 공통 backend에 결속하고 blank·malformed·invalid UTF-8·duplicate identity와 backend failure를 fail closed로 처리합니다. Mutation은 local conditional file write와 S3 conditional create/ETag CAS를 사용하고 충돌할 때마다 최신 state의 ownership·schema·transition을 다시 검증합니다. 최근 mutation receipt는 64개로 제한해 후속 CAS 뒤에도 불확실한 commit을 조정하며, 손상 receipt는 원본을 보존하고 fail closed 처리합니다. 이 보장은 tenant별 단일 report workflow state object에 한정되고 실제 AWS runtime과 다른 state object를 함께 묶는 distributed transaction은 검증 범위가 아닙니다.
- 감사 로그 append는 기존 JSONL byte prefix를 보존하고 local/S3 공통 backend를 사용합니다. Missing object는 conditional create, 기존 object는 검증된 원문을 expected value로 사용하는 CAS를 적용하며, 충돌 시 최신 JSONL을 다시 검증하고 append를 재적용합니다. Commit 응답이 불확실하면 `log_id`와 exact entry를 read-back해 후속 append 뒤에도 성공을 조정합니다. 이 보장은 tenant별 단일 audit JSONL object 범위이며 실제 AWS runtime은 검증하지 않았습니다.
- 메시지·알림 state는 tenant별 `messages.json`과 `notifications.json`에 각각 conditional create/CAS를 적용합니다. 충돌할 때마다 최신 state의 ownership·schema를 다시 검증하고 최근 mutation receipt를 64개로 제한해 commit 응답 유실 뒤 후속 CAS도 조정합니다. Local conditional lock 초기화의 동시 create도 재시도하며 receipt 손상은 원본 보존 상태로 fail closed 처리합니다. 이 보장은 각 단일 state object 범위이고 메시지 저장과 mention 알림 생성을 함께 묶는 distributed transaction, 실제 AWS runtime, 외부 SMTP·Slack 전달 성공은 검증 범위가 아닙니다.
- 사용자·초대 state는 tenant별 `users.json`과 `invites.json`에 각각 conditional create/CAS를 적용합니다. 충돌마다 최신 ownership·schema와 username uniqueness를 다시 검증하고 최근 mutation receipt를 64개로 제한해 commit 응답 유실 뒤 successor CAS도 조정합니다. 첫 관리자 생성은 빈 tenant 확인과 create를 한 CAS mutation으로 처리하고, 초대 수락은 invite를 먼저 claim한 worker 하나만 account callback을 실행하며 callback 실패 시 claim을 되돌립니다. 이 보장은 각 단일 state object 범위이고 user와 invite object를 함께 묶는 distributed transaction이나 process crash 뒤 claim 자동 복구는 제공하지 않습니다. 실제 AWS runtime과 초대 메일 전달 성공도 검증 범위가 아닙니다.
- SSO 설정 state는 tenant별 단일 object에서 local conditional write 또는 S3 conditional create/ETag CAS로 갱신합니다. 충돌할 때마다 최신 설정에 partial update를 재적용하고 최근 private mutation receipt를 64개로 제한해 commit 응답 유실 뒤 successor update도 조정합니다. Secret은 Fernet authenticated encryption과 PBKDF2 key derivation을 사용하며 복호화 실패를 평문 fallback으로 처리하지 않습니다. 서명 없는 SAML assertion과 RelayState 불일치는 거부하지만, 현재 기본 requirements에 `python3-saml` verifier가 없어 SAML ACS는 fail closed 상태이며 실제 LDAP·SAML IdP·GCloud 로그인은 검증 범위가 아닙니다.
- 사용자 템플릿과 생성 이력 state는 tenant별 `templates.jsonl`과 `history.jsonl`에 각각 conditional create/CAS를 적용합니다. 충돌마다 최신 ownership·schema 위에 add/delete/use-count 또는 add/favorite/visual-asset/promotion 변경을 재적용하고 최근 mutation receipt를 64개로 제한해 commit 응답 유실 뒤 successor CAS도 조정합니다. 대상 mutation과 delete는 API에 노출하지 않는 immutable incarnation token에 결속하므로 timestamp가 같아도 같은 ID로 재생성된 후속 record를 변경하지 않습니다. History retention으로 원본 record가 제거될 때는 receipt를 남은 최신 record로 넘겨 불확실 commit을 조정합니다. 이 보장은 각 단일 state object 범위이며 64개를 넘는 successor mutation의 불확실 commit 조정, 32회 즉시 재시도의 backoff·fairness, 실제 AWS runtime과 두 object를 함께 묶는 distributed transaction은 검증 범위가 아닙니다.
- 프로젝트 지식 `index.json`은 local conditional file write 또는 S3 conditional create/ETag CAS로 갱신합니다. 충돌마다 최신 ownership·schema·document identity 위에 add/style/metadata/delete를 최대 32회 재적용하고 최근 64개 private mutation receipt로 commit 응답 유실 뒤 successor mutation을 조정합니다. 신규 본문·style은 private incarnation 아래 immutable conditional create로 먼저 발행하고 size·SHA-256과 object path를 index에 결속합니다. Index에 없는 versioned object는 generation·procurement·report promotion authority가 아니며 정상 실패에서는 정리하지만 process crash나 cleanup failure 뒤 inert object가 남을 수 있습니다. Legacy root object는 계속 orphan을 fail closed로 탐지합니다. 이 보장은 단일 index object의 CAS와 참조된 artifact 검증 범위이며 index와 여러 artifact를 한 번에 묶는 distributed transaction, 64개를 넘는 successor reconciliation, retry backoff·fairness와 실제 AWS runtime은 검증 범위가 아닙니다.
- DocumentOps trajectory/review와 pre-training governance evidence는 같은 tenant-scoped local/S3 `StateBackend`에 결속합니다. `trajectories.jsonl`은 append/review authority이고 `trajectory_metadata.json`은 SFT export, freeze, dry-run approval, execution request, pre-execution audit를 가리키는 별도 mutable CAS index입니다. 각 artifact는 immutable conditional create로 먼저 발행한 뒤 size·SHA-256과 identity를 metadata에 최대 32회 CAS로 추가하며, commit 응답이 유실된 뒤 successor append가 있어도 exact metadata entry read-back으로 성공을 조정합니다. Blank·malformed·duplicate key·identity, count mismatch와 foreign ownership은 원본을 덮어쓰지 않고 fail closed 처리합니다. Export와 audit download는 metadata binding이 일치하는 selected-backend bytes만 반환하고 reviewer sign-off summary도 같은 backend prefix의 read-only handoff를 읽습니다. Ops-key 전용 governance inventory는 다섯 managed directory를 metadata authority와 대조해 verified·missing·tampered·invalid reference·unreferenced 상태와 exact count를 반환하고, 응답은 이슈를 우선해 collection별 최대 500개 artifact detail만 노출합니다. DocumentOps의 Review 상태 화면은 service가 training governance, artifact inventory, reviewer sign-off를 독립적으로 읽어 `boundary → artifact integrity → governance blocker → human sign-off → ready` 순서로 검토 상태와 다음 행동을 정리한 뒤 세 원본 report를 함께 표시합니다. 각 source report의 top-level `generated_at`만 제외한 canonical SHA-256과 세 hash를 묶은 review-state fingerprint를 응답에 포함합니다. Browser는 이를 현재 인증 세션의 메모리에서만 직전 동일 tenant 관측과 비교해 최초·동일·변경을 표시하고 logout 또는 invalid session에서 기준을 지웁니다. Export·freeze·dry-run approval·execution request·pre-execution audit 저장과 planning provider/model 변경은 진행 중 overview 조회를 무효화하고 이미 열린 상태를 이전 관측으로 표시합니다. 성공한 재조회만 fresh 상태를 복구하며 기존 fingerprint 기준은 유지해 실제 source 변화 여부를 다시 비교합니다. 이 비교는 저장된 receipt가 아니며 합성 결과를 atomic snapshot으로 바꾸지 않습니다. Tenant 전환이나 연속 재확인 뒤 늦게 도착한 overview 응답은 화면과 비교 기준 모두 갱신하지 않습니다. Trajectory Stats, task-filtered Reviewed SFT export/freeze 목록, Training Readiness도 각각 같은 tenant의 최신 success/error만 반영하므로 이전 응답이 count, artifact 목록, freeze 승인 대상을 되돌리지 않습니다. Training Audit Checklist는 request version, tenant, provider/model query를 함께 확인하고 planning 조건이 바뀌면 열린 checklist를 `RECHECK REQUIRED`로 낮추며 `Audit 저장` action을 제거합니다. 성공한 audit 저장은 진행 중 이전 checklist read를 무효화해 새 evidence가 가려지지 않게 합니다. H74 이전 hash-only local record는 checksum 검증으로 읽되 `size_binding_verified=false`로 구분하며 새 artifact만 size binding을 주장합니다. Private trajectory metadata는 public record와 SFT source에서 제거하며 training, upload, provider API, model promotion guard는 계속 false입니다. 이 보장은 trajectory와 metadata 각 단일 mutable object의 CAS 및 참조 artifact 검증 범위이며 두 mutable object와 여러 artifact를 한 transaction으로 묶지 않습니다. Inventory는 atomic metadata snapshot 하나를 기준으로 여러 object를 순차 관측하므로 concurrent write와 함께 실행되면 재확인이 필요합니다. Metadata 확정 전에 process가 중단되면 비권위 orphan artifact가 남을 수 있고 API와 화면 모두 자동 삭제를 허용하지 않으므로 실제 정리 전 재확인이 필요합니다. 자동 GC, 64개를 넘는 trajectory review reconciliation, retry backoff·fairness와 실제 AWS/provider/training runtime은 검증 범위가 아닙니다.
- Root tenant registry는 local/S3의 단일 `tenants.json` object에서 conditional create/CAS로 갱신합니다. 충돌할 때마다 최신 target ownership·schema에 operation을 최대 32회 재적용하고 최근 private mutation receipt를 64개로 제한합니다. API key rotation은 한 번 생성한 plaintext와 hash를 같은 mutation에 결속하며, lost response는 현재 record가 유일한 active owned authentication target일 때만 성공으로 조정합니다. 실제 AWS runtime과 여러 state object를 묶는 transaction은 검증 범위가 아닙니다.
- G2B 즐겨찾기 state는 local/S3 공통 backend에서 tenant/user ownership과 공고 identity를 검증하고 손상 원본을 보존합니다. Add/remove는 단일 bookmark object의 conditional create/CAS로 최신 state에 재적용하고 private bookmark identity와 최근 64개 mutation receipt로 불확실 commit 뒤 successor mutation을 조정합니다. 실제 G2B API 호출과 다른 state object를 함께 묶는 distributed transaction은 검증 범위가 아닙니다.
- 공공조달 판단 state와 source snapshot은 local/S3 공통 backend에서 tenant/project ownership, snapshot storage path와 JSON 구조를 검증하고 손상 원본을 보존합니다. 이 검증은 저장된 snapshot의 경로·JSON 무결성 범위이며 외부 원천 데이터의 의미적 진위, 여러 프로세스의 distributed S3 compare-and-swap, 실제 G2B/provider 호출은 보장하지 않습니다.
- Decision Council state는 local/S3 공통 backend에서 tenant/project/session identity를 검증하고 손상 원본을 보존합니다. 기존 foreign·malformed record는 조회·변경 대상에서 제외한 채 유지하지만, 여러 프로세스가 같은 S3 객체를 갱신하는 distributed compare-and-swap과 실제 G2B/provider 호출은 검증 범위가 아닙니다.
- Project/approval state는 local/S3 공통 backend에서 tenant와 record identity를 검증하고 손상 원본을 보존합니다. ID가 없는 기존 malformed record와 explicit foreign record는 호환을 위해 현재 tenant의 조회·변경 대상에서 제외한 채 유지하지만, 유효한 owned ID를 가진 schema drift는 fail closed 처리합니다. 두 store의 mutation은 local conditional file write와 S3 conditional create/ETag CAS를 사용하고 충돌마다 최신 state를 다시 검증합니다. Project는 create·field update·document add/remove·approval sync·delete overwrite를 방지하고, approval은 create·comment·terminal decision overwrite를 방지합니다. Project의 최근 mutation receipt는 64개로 제한해 record가 남아 있는 후속 CAS 뒤에도 불확실한 commit을 식별하고, approval은 exact persisted payload read-back으로 조정합니다. 이 보장은 각각 tenant별 단일 project 또는 approval state object에 한정되고 실제 AWS runtime과 두 object를 함께 묶는 distributed transaction은 검증 범위가 아닙니다.
- 회의 녹음은 recording별 `metadata.json`을 local conditional write 또는 S3 conditional create/ETag CAS로 갱신합니다. 충돌마다 최신 metadata를 다시 검증하고 전사·승인 변경을 재적용하며, 최근 private mutation receipt를 64개로 제한해 commit 응답 유실 뒤 successor CAS도 조정합니다. Audio는 content-bound immutable conditional create로 저장하고 동일 bytes의 orphan만 재사용합니다. 이 보장은 단일 metadata object 범위이며 audio와 metadata를 함께 묶는 distributed transaction, 64개를 넘는 successor mutation 조정, 32회 즉시 재시도의 backoff·fairness, 실제 AWS runtime과 실제 OpenAI transcription 성공은 검증 범위가 아닙니다.
- 결제 권한 state는 tenant별 `billing.json`을 local conditional write 또는 S3 conditional create/ETag CAS로 갱신합니다. 충돌마다 최신 account schema·tenant identity 위에 plan·status·Stripe identity 변경을 재적용하며 최근 private mutation receipt를 64개로 제한해 commit 응답 유실 뒤 successor CAS도 조정합니다. 손상 state와 receipt는 metered request를 `503`으로 차단합니다. 이 보장은 단일 billing object 범위이며 billing과 usage를 함께 묶는 transaction, 64개를 넘는 successor mutation 조정, 32회 즉시 재시도의 backoff·fairness, 실제 AWS runtime과 Stripe checkout·cancel·provider-delivered webhook은 검증 범위가 아닙니다.
- 사용량 event log와 monthly summary는 local/S3 공통 backend에서 각각 conditional create/CAS로 갱신합니다. Event log를 권위 원본으로 두고 summary coverage·aggregate를 다시 계산하며, 정확히 하나의 검증된 trailing event만 summary에서 빠진 경우에는 최신 event log 위에 summary를 CAS로 보완합니다. 손상·변조·둘 이상의 event gap은 원본 보존 상태로 fail closed 처리하고 process-local lock은 contention 완화에만 사용합니다. Generation·DocumentOps·meeting transcription·knowledge·G2B·style·procurement·report workflow·admin expansion의 provider-backed route는 tenant별 admission lock과 한도 검사를 먼저 거칩니다. Direct provider 작업과 실제 provider를 호출한 OCR·visual 호출만 동일 authority에 기록하고 실패 응답의 token도 보존합니다. 취소된 admission waiter와 rewrite/stream worker는 provider 작업이 끝나기 전에 lock을 반환하지 않으며, provider 오류 원문은 public response·상태·로그에 저장하지 않습니다. Provider를 사용하지 않는 local parse·edited export와 실제 생성 범위 밖 provider image는 한도와 provider 초기화에서 분리합니다. Event와 summary 두 객체를 함께 묶는 atomic transaction, 여러 worker 사이의 exact admission reservation, 실제 provider usage·비용 대조는 구현·검증 범위가 아닙니다.
- 스타일 프로필 state는 tenant별 단일 object에서 local conditional write 또는 S3 conditional create/ETag CAS로 갱신합니다. 충돌할 때마다 최신 profile state에 변경을 재적용하고 private incarnation과 최근 64개 mutation receipt로 replacement lifecycle과 불확실 commit을 조정합니다. 손상 state는 style API와 prompt build를 중단하지만, mock provider는 LLM prompt builder를 호출하지 않으며 실제 provider 기반 style analysis와 다른 state object를 함께 묶는 distributed transaction은 검증 범위가 아닙니다.
- Feedback와 eval evidence JSONL append는 기존 byte prefix를 보존하고 local conditional write 또는 S3 conditional create/ETag CAS를 사용합니다. 충돌할 때마다 최신 ownership·schema·중복 append identity를 검증하고 최대 32회 같은 record를 재적용합니다. Feedback은 public `feedback_id`, eval은 public `EvalRecord`에 노출하지 않는 private append identity로 commit 응답 유실 뒤 successor append까지 조정합니다. 기존 tenant 없는 record와 반복 평가 계약은 유지합니다. 이 보장은 각 단일 JSONL object 범위이며 retry backoff·fairness와 실제 AWS runtime은 검증 범위가 아닙니다.
- Runtime prompt override, A/B prompt experiment와 request pattern state도 객체별 local conditional write 또는 S3 conditional create/ETag CAS를 사용합니다. 충돌마다 최신 ownership·schema 위에 override save/increment/delete, experiment create/assign/result/conclude/delete, request append/clear를 최대 32회 재적용합니다. Override refresh는 incarnation과 누적 applied count를 유지하고 payload-bound save receipt로 동일 operation ID의 다른 payload를 거부합니다. Incarnation 필드가 없던 기존 override는 bundle·생성 시각·tenant binding으로 deterministic lineage를 계산해 concurrent refresh와 increment가 같은 record를 가리키게 합니다. A/B assignment는 variant·hint·experiment identity를 한 CAS 결과로 반환하며 background result와 conclusion도 그 identity에 결속합니다. Pending winner는 persisted result·hint·mutation receipt와 다시 대조하고, 같은 operation ID로 winner override를 저장한 뒤 concluded로 전환합니다. Override 실패 시 public active 상태를 유지해 다음 평가에서 재개하고 pending reset은 `409`로 거부합니다. Request clear는 첫 snapshot의 unmatched ID만 제거해 그 뒤 append를 보존합니다. Private metadata는 public 응답에 노출하지 않습니다. 이 보장은 각 단일 state object 범위이며 A/B와 override 객체를 함께 묶는 distributed transaction, 64개를 넘는 successor reconciliation, retry backoff·fairness와 실제 AWS runtime은 검증 범위가 아닙니다.
- Fine-tune dataset JSONL append·snapshot-bound clear, export metadata append와 model registry lifecycle mutation은 각각 local conditional write 또는 S3 conditional create/ETag CAS를 사용합니다. Dataset은 public 응답에 숨긴 append identity로 같은 request ID의 clear 후 successor 재생성을 구분하고, model registry는 immutable incarnation과 최근 64개 private mutation receipt로 register/status/eval/deprecate의 불확실 commit을 조정합니다. Export content는 filename별 immutable conditional create 후 size·SHA-256에 결속된 metadata를 별도 CAS로 확정하며, metadata가 확정되지 않은 orphan은 download/upload authority가 아닙니다. 이 보장은 dataset, metadata, registry 각 단일 object 범위이며 export content와 metadata를 묶는 distributed transaction, 64개를 넘는 successor reconciliation, retry backoff·fairness, 실제 AWS runtime·dataset upload·training execution·external polling·model promotion은 검증 범위가 아닙니다.
- 공개 공유 state는 tenant별 `shares.json`에 conditional create/CAS를 적용합니다. 충돌마다 최신 ownership·schema와 lifecycle 위에 create/access/revoke를 재적용하고 최근 mutation receipt를 64개로 제한해 commit 응답 유실 뒤 successor CAS도 조정합니다. 이미 취소된 링크는 최초 취소자와 시각을 보존합니다. 이 보장은 단일 share state object 범위이고 실제 AWS runtime, 다른 state object와의 distributed transaction, 운영 URL의 외부 접근성은 검증 범위가 아닙니다.
- Procurement review record·원본 packet·reviewed-package는 local/S3 공통 backend의 tenant/project/packet SHA-256 경로에 함께 결속합니다. Blank·malformed·invalid UTF-8·duplicate key/identity, artifact 누락·변조와 backend failure는 빈 검토함, 새 packet 또는 사용자 입력 충돌로 축소하지 않고 `500 INTERNAL_ERROR`로 중단하며 원본 bytes를 보존합니다. Pending receipt와 완료 package의 embedded receipt/manifest까지 semantic하게 다시 대조합니다. Packet은 exact orphan bytes만 재사용하고 reviewed-package는 content-addressed 경로에 immutable하게 쓴 뒤 record를 CAS로 전환합니다. S3는 `If-None-Match`/`If-Match`, local은 conditional file lock과 atomic write를 사용하며 commit 결과가 불확실하면 read-back으로 조정합니다. 여러 artifact를 한 번에 commit하는 distributed transaction과 실제 AWS S3 runtime 검증은 범위 밖입니다.
- 프로젝트 procurement review는 원본 packet SHA256과 tenant/project 경계에 묶인 검토 증빙입니다. tenant 검토함은 pending/completed 상태를 모아 보여주고 기존 프로젝트 상세와 검증된 package 다운로드로 연결합니다. 현재 source와 일치하는 완료 review는 downstream 생성 문맥과 project document provenance에 이어집니다. 이후 procurement decision이 바뀌면 해당 문서는 stale review로 다시 분류되고, 프로젝트 문서 목록·결재 요청·공유 링크에 경고와 재검토 동선이 표시됩니다. Project-linked share는 서버가 tenant/project/document/request/bundle binding을 검증하고 생성 시점 source fingerprint를 저장합니다. 공개 공유 페이지는 조회할 때마다 현재 원본을 다시 대조해 변경·삭제 상태를 경고하고 `share.view` audit evidence를 남기며, admin Locations의 외부 공유 review queue는 stale `share.create`와 drift `share.view`를 함께 보여주되 반복 조회를 영향받은 고유 링크 수로 중복 집계하지 않습니다. 이후 current 조회가 확인되면 해당 링크만 위험 queue에서 해소하고 복구 건수를 별도로 표시하며 기존 audit은 보존합니다. 공유 취소는 처리자·시각을 남기고 자연 만료와 구분하며, 같은 문서에 여러 링크가 있으면 닫힌 최신 링크보다 아직 활성인 링크를 먼저 보여줍니다. Generic legacy share는 기존 동작을 유지합니다. 연결된 결재는 요청 시점 상태를 보존하고 상세 조회와 최종 승인 직전에 현재 원본을 다시 대조하며, stale 상태의 최종 승인은 명시적 acknowledgement를 approval record와 audit에 남겨야 진행됩니다. 승인 후 원본 source fingerprint가 달라진 경우에도 immutable 승인 스냅샷을 다운로드하기 전에 별도 확인이 필요하고 그 결과가 download audit에 남습니다. 완료 receipt와 reviewed-package를 포함해 운영 승인, provider 호출, 입찰 제출을 실행하거나 허가하지 않습니다.
- Final review packet은 모든 bundle의 사람 검토가 완료된 receipt에서만 생성됩니다. 현재 tracked sample은 `pending`이라 packet을 제공하지 않습니다.

---

## Links

- GitHub: [sungjin9288/DecisionDoc-AI](https://github.com/sungjin9288/DecisionDoc-AI)
- Release evidence: [DecisionDoc AI v1.1.77 Production Release](https://github.com/sungjin9288/DecisionDoc-AI/releases/tag/v1.1.77)
- Demo: (접근 검증 후 추가)
- 엔지니어링/기여 가이드: [Contribution Note](./docs/contribution-note.md)

---

<sub>이 README의 모든 정량 수치(라우트 268 · 테스트 3,480 · env 키 94 등)는 소스 코드에서 직접 카운트했으며, 재현 커맨드를 함께 표기했습니다. 측정 근거가 없는 비용 절감률·자동화율·정확도 수치는 사용하지 않습니다.</sub>

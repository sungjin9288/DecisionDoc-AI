# Interview Story

분석 기준: 2026-10-08 현재 저장소 코드, README, local evidence, completion readiness boundary를 기준으로 작성했다. 한 페이지 요약은 [portfolio.md](./portfolio.md)에 있다. 운영·성과 주장은 검증된 범위와 분리한다.

## 1. 1분 프로젝트 소개

DecisionDoc AI는 제안서·보고서 같은 업무 문서를 구조, 작성, 검증, 형식 변환까지 한 흐름으로 다루는 로컬 문서 작업 도구입니다. 지금은 제가 구독 중인 Claude Code나 Codex 세션이 문서 내용을 쓰고, DecisionDoc 서버는 작성 지침을 주고 결과를 검증·렌더링·저장한 뒤 DOCX·PDF·PPTX·HWPX·XLSX로 바꿉니다. 처음에는 서버가 직접 LLM provider를 호출하는 구조였는데, provider를 하나의 교체 지점으로 분리해 둔 덕분에 그 자리만 바꿔 같은 파이프라인을 재사용할 수 있었습니다. `GenerationService`가 provider 호출, schema 안정화, 저장, Jinja2 rendering, lint를 조율하고, provider와 storage는 factory 뒤에 분리했습니다. 생성 결과는 project, knowledge, approval, share, export 흐름으로 이어집니다. 공공조달 기능에서는 tenant와 project에 결속된 review packet, reviewer inbox, downstream evidence freshness를 구현해 오래된 근거가 승인이나 공유로 조용히 넘어가지 않도록 했습니다. Mock/local regression과 evidence pack은 비용 없이 재현할 수 있지만, 잔여 live provider, G2B 실데이터, 배포 URL은 아직 완료 증거로 주장하지 않습니다.

## 2. 3분 상세 설명

- 배경: 개별 LLM 채팅은 초안 생성에는 편하지만 입력 근거, 문서 구조, 검토 이력, 승인, export를 일관되게 관리하기 어렵다.
- 설계: router는 HTTP 계약과 인증을 담당하고, service가 orchestration을 맡으며, provider/storage는 교체 가능한 interface로 분리했다.
- 품질: bundle schema, stabilizer, validator, lint, offline eval로 자유 형식 출력을 deterministic gate 안에 넣었다.
- 업무 흐름: 생성 문서를 project와 knowledge에 연결하고 approval, share, audit, export로 이어지게 했다.
- 조달 검토: recommendation source와 review record·packet·reviewed-package를 packet SHA-256과 tenant/project binding에 묶는다. Persisted 증빙이 손상·누락되면 빈 검토 이력으로 숨기지 않고 중단하며, review 이후 원본이 바뀌면 downstream 문서, 공유 링크, 결재에서 stale 상태를 다시 확인한다. 이 검토는 입찰 제출이나 법적 승인이 아니다.
- 증거: mock/local test, UI capture, completion readiness receipt, tracked portfolio pack manifest를 분리해 무엇이 검증됐고 무엇이 외부 환경을 기다리는지 남긴다.
- Local procurement CLI contract: `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`을 `scripts/validate_procurement_decision_package_cli_contract_manifest.py`와 `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`로 검증한다. `--write-result`와 `--result-path`를 사용해 persisted receipt를 안전한 local 경로에 남길 수 있다.
- 현재 한계: Gemini/Claude 잔여 live proof, G2B live smoke, post-deploy smoke, 사용자 성과 수치는 미검증이다. 비용 테스트는 사용자 요청에 따라 보류했다.

## 3. 기술 면접 예상 질문

| 질문 | 답변 방향 | 코드 근거 |
|---|---|---|
| FastAPI 앱은 어떻게 초기화되나요? | `create_app()`이 provider, storage, service, store, middleware, router를 wiring한다. | `app/main.py` |
| provider abstraction은 왜 필요한가요? | mock test, 모델 교체, capability routing, recoverable fallback을 route에서 분리한다. | `app/providers/factory.py`, `app/ai/pipeline.py` |
| 생성 품질은 어떻게 관리하나요? | provider JSON을 schema/stabilizer로 정규화하고 template rendering 뒤 validator/lint/eval을 적용한다. | `app/services/generation_service.py`, `app/providers/stabilizer.py`, `app/eval/` |
| bundle 구조는 무엇인가요? | 문서 유형별 schema, prompt, template, 필수 heading을 `BundleSpec`과 `DocumentSpec`으로 관리한다. | `app/bundle_catalog/spec.py`, `app/bundle_catalog/registry.py` |
| 파일 업로드는 어떻게 처리하나요? | multipart 입력을 검증하고 attachment context로 정규화한 뒤 동일한 generation service로 보낸다. | `app/routers/generate/core.py`, `app/attachments/` |
| export는 어떻게 분리했나요? | HTTP format selection은 router가 받고, 각 format renderer/service가 실제 artifact 생성을 맡는다. | `app/routers/generate/export.py`, `app/services/` |
| storage는 어떻게 교체하나요? | `DECISIONDOC_STORAGE`를 앱 초기화 시 읽고 local/S3 구현을 같은 interface 뒤에서 선택한다. | `app/storage/factory.py`, `app/storage/base.py` |
| tenant 경계는 어디서 지키나요? | middleware/auth와 tenant-aware store를 함께 사용하고 project-bound artifact를 현재 tenant에서 재검증한다. | `app/middleware/tenant.py`, `app/storage/tenant_store.py` |
| stale procurement evidence는 어떻게 처리하나요? | source fingerprint를 보존하고 조회·공유·결재 시 현재 원본과 비교해 acknowledgement 없이는 위험한 전이를 막는다. | `app/routers/projects/procurement_reviews.py`, `app/routers/history.py`, `app/routers/approvals.py` |
| 파일 기반 project/approval state 손상은 어떻게 다루나요? | missing state만 빈 목록으로 보고, blank·invalid UTF-8·schema/identity drift는 원본을 보존한 채 중단한다. Worker mutation은 conditional create/CAS 충돌마다 최신 state와 transition을 재검증하고, project receipt 또는 approval exact payload read-back으로 불확실한 commit을 조정한다. | `app/storage/project_store.py`, `app/storage/approval_store.py`, `tests/test_project_approval_store_integrity.py` |
| report workflow state의 동시성과 손상은 어떻게 다루나요? | tenant별 단일 state object에 conditional create/CAS를 적용하고 충돌마다 최신 planning·slide·approval transition을 재검증한다. Bounded private receipt로 후속 CAS 뒤의 불확실한 commit을 조정하며, blank·invalid UTF-8·backend failure·receipt drift는 원본 보존 500으로 처리한다. | `app/storage/report_workflow/`, `tests/test_report_workflow_store_integrity.py` |
| append-only 감사 로그의 worker 경쟁은 어떻게 다루나요? | 기존 JSONL raw prefix를 expected value로 사용하는 conditional create/CAS를 적용하고 충돌마다 전체 evidence를 다시 검증한다. Commit 응답이 유실된 뒤 다른 append가 이어져도 `log_id`와 exact entry read-back으로 원래 append를 조정하며, 32회 충돌 뒤에는 원본을 덮어쓰지 않고 중단한다. | `app/storage/audit_store.py`, `tests/test_audit_store_integrity.py` |
| 메시지와 알림의 worker 경쟁은 어떻게 다루나요? | 각 tenant의 message·notification object에 conditional create/CAS를 적용하고 충돌마다 최신 ownership·schema 위에 mutation을 재적용한다. Private receipt는 64개로 제한해 successor CAS 뒤 불확실한 commit을 조정하고 public 응답에서는 제거한다. 두 object를 하나의 transaction으로 묶는다고 주장하지 않는다. | `app/storage/message_store.py`, `app/storage/notification_store.py`, `tests/test_collaboration_store_integrity.py` |
| 첫 관리자와 초대 수락의 worker 경쟁은 어떻게 다루나요? | Empty-tenant 확인과 first-admin create를 한 user-state CAS mutation으로 처리한다. Invite는 먼저 claim한 worker 하나만 account callback을 실행하고 실패 시 claim을 rollback한다. User/invite record의 private receipt로 불확실 commit을 조정하지만 두 state object의 transaction이나 crash recovery라고 주장하지 않는다. | `app/storage/user_store.py`, `app/storage/invite_store.py`, `tests/test_identity_store_integrity.py` |
| 템플릿·생성 이력·공유 링크의 worker 경쟁은 어떻게 다루나요? | 각 tenant의 template/history/share object에 conditional create/CAS를 적용하고 충돌마다 최신 ownership·schema·lifecycle 위에 mutation을 재적용한다. Private receipt는 64개로 제한하고 public 응답에서 제거한다. Template/history 대상 mutation과 delete는 private immutable incarnation token에 결속해 timestamp가 같아도 같은 ID로 재생성된 후속 record를 변경하지 않는다. History retention은 제거된 record의 receipt를 남은 최신 record로 전달한다. | `app/storage/template_store.py`, `app/storage/history_store.py`, `app/storage/share_store.py`, 각 integrity test |
| procurement review 증빙의 부분 쓰기는 어떻게 막나요? | Packet은 exact bytes만 write-if-absent/reuse하고 package는 SHA-256 경로에 immutable하게 저장한 뒤 record를 CAS로 전환한다. S3 commit 응답이 불확실하면 read-back으로 조정하고 record가 확정되지 않은 artifact는 권위로 사용하지 않는다. 완료 직전 packet과 완료 package semantic binding을 다시 검증하며 persisted 오류는 사용자 409가 아닌 500으로 처리한다. | `app/storage/state_backend.py`, `app/storage/procurement_review_store.py`, `app/services/procurement_review_evidence.py`, `tests/test_procurement_review_store.py` |
| 왜 서버가 모델을 호출하지 않게 바꿨나요? | 혼자 로컬에서 쓰는 도구라 이미 구독 중인 코딩 에이전트 세션을 작성자로 쓰는 편이 비용과 키 관리가 단순했다. 서버는 provider 경로와 같은 프롬프트를 지침으로 주고, 제출된 bundle은 기존 검증·품질 보정·렌더링·이력 단계를 그대로 거친다. | `app/routers/generate/authoring.py`, `app/providers/authored_provider.py`, `tests/test_agent_authored_generation.py` |
| 세션이 잘못 쓴 문서는 어떻게 막나요? | schema·lint·문서 검증 실패를 `422 AUTHORED_BUNDLE_INVALID`와 사유 목록으로 돌려주고 이력과 프로젝트 문서는 쓰지 않는다. CLI는 종료 코드 2로 알려 세션이 사유대로 고쳐 다시 제출한다. | `app/routers/generate/authoring.py`, `scripts/decisiondoc_author.py`, `tests/test_agent_author_cli.py` |
| 근거 없는 수치는 어떻게 다루나요? | 모든 번들 프롬프트 끝에 수치 근거 규칙을 두고 다른 지시보다 우선하게 했다. 짧은 맥락의 근거 없는 수치는 품질 보정 단계가 일반 문장으로 바꾼다. 이 보정 문장이 특정 사업 문구로 고정된 결함을 새 경로 실증 중 찾아 고쳤다. | `app/bundle_catalog/system_prompt.py`, `tests/test_bundle_prompt_rules.py`, `tests/test_generate.py` |
| 테스트와 외부 증거를 어떻게 구분하나요? | mock/non-live regression은 기본 gate로 두고, M1/M2/M6는 readiness와 no-secret proof receipt를 별도 계약으로 관리한다. | `scripts/check_completion_readiness.py`, `scripts/check_completion_proof_receipt.py` |

## 4. 프로젝트 면접 예상 질문

| 질문 | 답변 방향 | 주의할 점 |
|---|---|---|
| 기존 LLM 채팅과 무엇이 다른가요? | schema, template, storage, review, approval, export, evidence lifecycle이 연결돼 있다. | 사용자 성과 수치는 말하지 않는다. |
| 가장 어려웠던 점은 무엇인가요? | 자유로운 LLM 출력과 변경 가능한 업무 근거를 검토 가능한 상태로 유지하는 것이었다. | 추상론보다 stabilizer와 freshness 사례를 든다. |
| 왜 파일 기반 store를 사용했나요? | MVP의 local reproducibility와 테스트 단순성을 우선했고, bundle storage는 S3 option을 뒀다. | 운영 DB 수준으로 과장하지 않는다. |
| 공공조달 review packet이 승인을 의미하나요? | 아니다. 검토 결과와 원본 결속을 남길 뿐 operational approval, bid submission, legal commitment를 허가하지 않는다. | 권한 경계를 명시한다. |
| 포트폴리오 증거는 어떻게 신뢰하나요? | tracked allowlist를 source와 byte 비교하고 generated SHA-256 manifest와 deterministic ZIP을 검증한다. | ZIP은 local artifact이며 repo에는 없다. |
| 현재 어디까지 검증됐나요? | mock/local regression, representative samples, local UI flow, CSP, evidence packaging, 세션 작성 경로 재현(합성 입력)은 검증 경로가 있다. | 사람 사용 검증(UAT), live provider/G2B/deploy는 미검증으로 분리한다. |
| 다음 우선순위는 무엇인가요? | 비용 없이 가능한 workflow 품질과 evidence 정합성을 계속 높이고, 외부 실증 재개 시 readiness runbook을 따른다. | 완료되지 않은 M1/M2/M6를 숨기지 않는다. |

## 5. 안전한 표현과 피할 표현

안전한 표현:

- FastAPI 기반 AI-assisted documentation PoC/MVP를 개발했다.
- 코딩 에이전트 세션이 문서를 쓰고 서버가 검증·변환하는 provider 미호출 작성 경로를 만들었다.
- provider/storage abstraction과 deterministic validation pipeline을 구현했다.
- tenant-bound procurement review와 stale evidence safeguard를 local test로 검증했다.
- 외부 실행 전 readiness와 proof receipt를 분리했다.

피할 표현:

- production-ready 또는 상용 운영이 완료됐다.
- 모든 provider fallback이 실환경에서 검증됐다.
- 실제 G2B 입찰 제출이나 법적 승인을 자동화한다.
- 사용자 생산성을 특정 수치만큼 개선했다.

## 6. 추가 학습 과제

- 실제 배포 환경의 rollback, SLO, incident response
- live provider retry/fallback의 비용·latency·quota 관측
- RDB 기반 tenant isolation과 migration strategy
- factual quality evaluation과 사용자 outcome measurement

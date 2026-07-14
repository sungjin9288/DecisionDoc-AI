# Development Roadmap

분석 기준: 2026-07-14 현재 저장소 코드, README, docs, local evidence, completion readiness boundary를 기준으로 업데이트했다. 로드맵은 외부 실증을 과장하지 않고 재현 가능한 검증 evidence 확보를 우선한다.

제품 방향성 기준 문서: [DecisionDoc AI Product Direction](./product_direction.md), 실행 계획 문서: [DecisionDoc AI Product Execution Plan](./product_execution_plan.md), local demo scenario: [DecisionDoc AI Local Product Demo Scenario](./product_demo_scenario.md), local demo runbook: [DecisionDoc AI Local Demo Runbook](./product_local_demo_runbook.md). 이 roadmap은 해당 방향성 중 재현 가능한 검증 evidence, public procurement wedge, review/sign-off workflow, exportable decision package를 우선 실행 대상으로 둔다.

Local evidence CLI contract 기준: `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`을 기준으로 stdout JSON success/failure field를 고정하고, `scripts/validate_procurement_decision_package_cli_contract_manifest.py`와 `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`로 manifest와 persisted receipt를 검증한다. 장기 보존이 필요한 검증 결과는 `--write-result --result-path <path>`로 repo 밖 임시 경로에 기록한다.

Completion readiness 기준: [development-plan.md](./development-plan.md)의 M1/M2/M6는 `scripts/check_completion_readiness.py`로 실행 준비 조건을 먼저 확인한다. proof 실행 순서와 증적 갱신 순서는 [completion-readiness-runbook.md](./completion-readiness-runbook.md)에 둔다. readiness 스크립트는 readiness만 확인하며 provider API, G2B live API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않는다.

## 1. 현재 상태 요약

- 현재 구현 완료: FastAPI 앱, 문서 생성 API, bundle catalog, provider/storage abstraction, export service, project/knowledge/approval/history/report workflow 일부, G2B search/fetch, health/metrics, Docker/AWS SAM 설정, pytest/smoke 기반 검증 경로
- 로컬 완료: export 5종 대칭성(M3), CSP nonce 적용(M4), 800줄 초과 모듈 분할(M5)
- 최근 확인한 main 자동화 증적: commit `a2575cc` 기준 GitHub Actions CI `29334312731` success, CD `29334312781` success. CD의 staging deploy/smoke는 설정 부재로 skip되어 M6 proof는 아니다.
- 개발 중: report quality learning, document ops agent, correction artifact/training workflow, fine-tune/model registry, post-deploy evidence 자동화
- 미검증/외부 의존: Gemini/Claude 및 성공 fallback proof(M1), G2B 실데이터 end-to-end(M2), 배포 접근성 및 post-deploy smoke(M6)
- 미구현 또는 증거 없음: 실제 사용자 성과 수치, 포트폴리오용 데모 영상, 현재 운영 URL 접근 검증 자료, 사용자 피드백 기반 개선 사례

현재 로컬 기준 검증:

```bash
pytest tests/ -m "not live" -q
# 2026-07-14 실측: 2991 passed, 2 skipped, 4 deselected

python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
```

## 2. Completion Milestones

| 마일스톤 | 현재 상태 | 다음 조건 |
|---|---|---|
| M1 Live provider 실증 | 진행 중. 2026-07-13 OpenAI 1회 통과; Gemini HTTP 429, Claude credit 부족, fallback 성공 미달 | Gemini quota/billing과 Anthropic credits 복구 후 Gemini/Claude/fallback live test 재실행 |
| M2 G2B 실데이터 end-to-end | 외부 실행 미착수. Runner-owned no-secret pass/fail/preflight receipt 계약은 로컬 완료 | stage URL/API key/G2B key 확보 후 `--proof-receipt`를 포함한 실제 smoke 실행 |
| M3 Export 5종 대칭성 | 완료 | README와 샘플 산출물의 수치가 코드와 계속 일치하는지 유지 |
| M4 CSP nonce | 완료. inline `on*=` handler 0개, nonce 기본 on | 새 UI 이벤트 추가 시 inline handler 금지 guard 유지 |
| M5 800줄 초과 모듈 분할 | 완료. 2026-07-14 상수 모듈 drift를 604줄 facade + 314줄 foundation으로 재분할하고 자동 guard 추가, 초과 0개 | infrastructure guard와 facade re-export 계약 유지 |
| M6 배포/post-deploy smoke | 외부 실행 미착수. Runner-owned no-secret pass/fail/preflight receipt 계약은 로컬 완료 | 배포 환경 확보 후 `--proof-receipt`를 포함한 deployed/ops smoke 실행 |

## 3. Phase 1 - MVP 완성

- 목표: 포트폴리오에서 재현 가능한 핵심 생성 흐름을 안정화한다.
- 현재 상태:
  - README는 제품 소개, 실행, 테스트, 한계 문구를 포함한다.
  - mock provider 기준 로컬 실행 절차와 대표 API 경로가 정리되어 있다.
  - 로컬 evidence gallery와 샘플 산출물이 존재한다.
  - 2026-07-08 기준 최신 static PWA screenshot과 CSP nonce 확인 로그를 갱신했다.
  - 2026-07-09 기준 main CI/CD 증적을 확인했다.
  - 직접 구현 범위와 말하면 안 되는 범위를 [contribution-note.md](./contribution-note.md)에 분리했다.
- 남은 작업:
  - 포트폴리오용 짧은 데모 영상이 필요하면 별도 캡처한다.
- 완료 기준:
  - 신규 사용자가 README만 보고 로컬 실행 가능
  - 대표 API smoke 통과
  - 포트폴리오에 첨부할 스크린샷/샘플 산출물 존재
- 산출물:
  - README 개선본
  - demo screenshot
  - sample request/response
  - smoke log

## 4. Phase 2 - 기능 고도화

- 목표: 생성 품질과 프로젝트 지식 재사용 흐름을 강화한다.
- 현재 상태:
  - export 대칭성, local procurement package, CLI contract receipt는 로컬 검증 경로를 갖고 있다.
  - 2026-07-13 local procurement package에 script-free `procurement_review.html`을 추가해 recommendation, hard filters, score factors, evidence gaps, bid readiness, handoff, pending sign-off, 실행 권한 경계를 한 화면에서 확인한다. 이 화면은 12개 artifact audit/export/hash inventory에 포함되며 별도 승인 workflow를 만들지 않는다.
  - 2026-07-13 검증된 12개 procurement artifact를 embedded `packet_manifest.json`과 함께 deterministic ZIP으로 묶는 `manage_procurement_decision_review_packet.py create/verify` 경로를 추가했다. Packet은 `review_ready`와 `operational_approval: false`를 유지하고 path, membership, SHA256/size, semantic drift를 재검증한다.
  - 2026-07-13 packet 밖의 `procurement_review_receipt.json`을 `packet_sha256`에 결속하고 요청 reviewer의 결정을 `pending`에서 `completed`로 한 번만 기록하는 receipt 경로를 추가했다. `render/apply-draft`는 packet과 pending receipt hash에 결속된 browser draft를 atomic update로 연결하며, 기존 script-free packet과 외부 실행 권한 경계는 바꾸지 않는다.
  - 2026-07-13 완료 receipt와 변경하지 않은 review packet을 `reviewed_package_manifest.json`과 함께 세 entry deterministic ZIP으로 묶는 `manage_procurement_reviewed_package.py create/verify` 경로를 추가했다. `review_completed`는 accepted, changes-requested, rejected 결과를 모두 보존하며 operational approval을 의미하지 않는다.
  - 2026-07-14 project procurement 상세 화면에서 reviewer를 지정하고 현재 tenant의 recommendation을 검증된 12-artifact review packet ZIP으로 내려받는 API/UI를 연결했다. Server는 injected procurement store를 재사용하고 packet SHA-256, package ID, artifact count, `operational_approval: false`를 응답 evidence로 제공하며 provider API, G2B live 수집, 입찰 제출은 실행하지 않는다.
  - 2026-07-14 tenant 전체의 pending/completed procurement review를 프로젝트 화면의 검토함에 모았다. 상태·reviewer 필터, 프로젝트 상세 이동, 검증된 completed package 재다운로드를 기존 lifecycle에 연결하고 검토함 조회 audit와 queue count observability를 남긴다.
  - 2026-07-14 review-bound downstream 문서에 packet source timestamp를 보존하고, 프로젝트 상세 조회 때 현재 tenant의 review evidence와 procurement decision을 다시 대조한다. `current`, stale, missing, invalid 상태를 문서 badge와 후속 조치에 표시하며, stale 상태로 결재·공유를 계속하면 확인 경고를 거친다. Project-linked share는 생성 시점 source fingerprint를 보존하고 공개 조회마다 현재 tenant 원본을 다시 확인해 post-share drift 경고와 `share.view` audit evidence를 남긴다. Admin procurement summary와 Locations overview는 이 drift audit을 기존 stale-share queue에 연결하고, 반복 조회는 최신 위험 관측만 갱신하며 영향받은 고유 링크 수를 중복 증가시키지 않는다. 이후 current 관측이 들어오면 해당 링크만 queue에서 해소하고 recovered count를 별도로 유지해 audit history와 현재 노출 상태를 분리한다. 링크 취소는 최초 처리자·시각을 보존하고 자연 만료와 구분하며, 같은 문서의 최신 링크가 닫혀도 남아 있는 다른 활성 링크를 대표로 유지해 실제 노출을 숨기지 않는다.
  - 2026-07-14 project document에서 시작한 approval은 tenant-scoped project/document/request/bundle binding과 요청 시점 freshness snapshot을 저장한다. 결재 상세와 최종 승인 직전에 현재 원본을 다시 대조하며, stale 또는 binding 불일치 상태는 명시적 acknowledgement 없이는 최종 승인되지 않는다. 성공한 acknowledgement는 확인자·시각과 함께 approval record 및 audit에 남는다.
  - report quality learning과 correction artifact 계열은 계속 개발 중이다.
  - 2026-07-13 report quality UI의 자동 통과 score/rationale를 제거하고, accepted artifact의 dimension rationale를 server gate로 강제했다.
  - 2026-07-13 mock provider와 임시 local storage만 사용하는 report workflow 생성·승인·correction artifact 저장·JSONL export 데모를 연결했다.
  - 2026-07-13 correction artifact에 stable content identity와 SHA-256 preview fingerprint를 적용했다. Save는 현재 workflow/input과 일치하는 preview만 허용하고 누락·stale input·중복 artifact를 거부하며, review packet validator도 embedded artifact fingerprint를 재검증한다.
  - 2026-07-13 저장된 correction artifact를 tenant 범위에서 단건 조회하는 detail API와 UI 검토·개별 JSON 다운로드 동선을 추가했다. 응답은 metadata-only artifact, validation, preview fingerprint를 보존하며 provider call, dataset upload, training execution은 계속 차단한다.
  - 2026-07-14 ready correction artifact 3~5개를 UI에서 직접 고르고 ordered pilot JSONL로 내려받는 tenant-safe selection flow를 추가했다. 서버는 개수, 중복·alias 중복, 존재 여부, ready gate를 재검증하며 외부 학습 작업은 실행하지 않는다.
  - 2026-07-14 pilot JSONL 다운로드 전에 ordered artifact, resolved/ready count, 전체 SHA-256, 외부 학습 비승인 경계를 확인하는 사전 검토 API/UI를 추가했다. 실제 export hash가 preview와 다르면 브라우저 저장을 중단하며, mock/local desktop·mobile에서 다운로드와 responsive boundary를 확인했다.
  - 2026-07-14 pilot export가 preview의 `preview_sha256`을 필수 precondition으로 받아 현재 ordered JSONL과 서버에서 다시 대조하도록 강화했다. 누락·stale hash는 다운로드 전에 차단하고, 성공한 preview/export는 SHA-256·artifact count·verification state를 observability와 append-only audit에 남긴다.
  - 2026-07-14 서버 검증형 export가 JSONL과 같은 request에 결속된 portable receipt를 함께 내려주도록 확장했다. Local importer는 receipt의 tenant·artifact 순서·JSONL SHA-256·preview 검증·외부 실행 비승인 경계를 확인한 뒤 원본 receipt를 pack에 보존하고 `SOURCE_MANIFEST.json` v2에 결속한다. 기존 v1 manifest는 read compatibility를 유지한다.
  - 2026-07-14 browser handoff에서 JSONL과 receipt가 따로 저장되던 부분 실패 가능성을 줄이기 위해 두 파일과 `pilot_package_manifest.json`을 하나의 deterministic ZIP으로 묶는 package endpoint/UI를 추가했다. Manifest와 server validator는 exact membership, entry size/SHA-256, tenant, artifact 순서, receipt binding, no-training boundary를 확인하고 package 전체 SHA-256은 브라우저에서 다시 대조한다.
  - 2026-07-14 local review pack importer에 `--source-package`를 추가해 검토 ZIP을 수동으로 풀지 않고 직접 가져오도록 연결했다. Importer는 server package validator를 재사용하고 package·manifest·embedded JSONL·receipt hash와 request ID를 `SOURCE_MANIFEST.json` v2에 보존하며, tamper나 혼합 source 인자는 출력 생성 전에 차단한다.
  - 2026-07-14 package import 증빙을 `SOURCE_MANIFEST.json` v3로 확장하고 embedded manifest 원문을 `SOURCE_PACKAGE_MANIFEST.json`에 atomic 보존한다. Downstream loader는 원본 ZIP 없이도 manifest hash와 entry size/SHA-256, tenant, request ID, artifact 순서, no-training boundary를 다시 검증하며 변조·symlink를 차단한다. 기존 v1/v2 source manifest는 read compatibility를 유지한다.
  - 2026-07-14 pilot review pack 생성이 source-bound `HUMAN_REVIEW_WORKSHEET.md`와 `human_review_manifest.json`까지 한 번에 준비하도록 연결했다. 검수자는 import 직후 review table과 artifact별 required action을 확인할 수 있고, draft 수정 뒤에는 같은 generator를 refresh 용도로 재실행한다. Worksheet refresh는 기존 decision template이나 browser workspace를 덮어쓰지 않는다.
  - 2026-07-14 generated/source pack 모두 기존 batch directory와 symlink를 쓰기 전에 거부하고 decision template generator도 기존 파일을 덮어쓰지 않도록 이력 경계를 강화했다. 이 immutable initialization 위에서 새 pack은 source/draft hash에 결속된 `review_decisions.json`을 한 번만 자동 생성하며, 이전 상태는 `previous_decision`에 보존하고 새 파일럿 판단은 모두 `pending`에서 시작한다.
  - 2026-07-14 non-engineering reviewer가 JSON을 직접 편집하지 않아도 되도록 pack-local `HUMAN_REVIEW_WORKSPACE.html`을 자동 생성한다. 화면은 현재 source-bound draft의 교정 전후 planning·slide·claim evidence, workflow/final reference, validation blocker와 required action을 먼저 보여주고, 결정·점수·scan·차원별 근거·구조화된 보완 요청을 받는다. 결과는 source/draft binding과 `training_authorized=false`를 보존한 browser draft로만 내려주며 원본 pack은 수정하지 않는다. Apply CLI가 stale binding과 전체 batch를 다시 검증하는 기존 경계는 유지한다.
  - 2026-07-14 `--browser-draft` apply 경로가 내려받은 decision 파일을 이동하지 않고 외부 경로에서 검증한 뒤 정확한 바이트를 SHA 기반 pack-local 이름으로 보존한다. 전체 batch 반영과 같은 suffix의 receipt 생성까지 한 명령으로 수행하며, stale·invalid·training authorization 상승·symlink·기존 hash 충돌은 어떤 artifact도 쓰기 전에 차단한다. Dry-run과 실패는 pack을 변경하지 않고 기존 `--decisions` 호환 경로는 유지한다.
  - 2026-07-14 decision 적용으로 draft hash와 검토 상태가 바뀔 때 `HUMAN_REVIEW_WORKSHEET.md`와 `human_review_manifest.json`을 같은 성공 흐름에서 현재 pack binding으로 갱신한다. Apply 전에 두 evidence target을 preflight해 symlink나 비파일 경로를 거부하고, dry-run·invalid batch·unsafe target에서는 draft와 파생 검수 증거를 모두 보존한다.
  - 2026-07-14 `sync_report_quality_pilot_pack.py --require-ready`가 artifact ready flag만으로 local review를 우회하지 못하도록 현재 manifest와 accepted decision application receipt를 필수 evidence로 검증한다. Manifest artifact hash·status·ready state·count를 현재 draft에서 다시 계산하고 receipt validator와 `require_ready=true`를 확인하며, JSONL 쓰기 직전에 pack binding과 두 evidence hash를 재검증한다. Source artifact가 이미 ready여도 새 local decision이 pending이면 `output_written=false`로 차단한다.
  - 2026-07-14 ready sync 결과를 현재 human review evidence와 함께 deterministic handoff ZIP으로 고정하는 `manage_report_quality_pilot_handoff.py create/verify` 경로를 추가했다. Exact JSONL, manifest, accepted receipt와 decision file, 최종 draft, source provenance sidecar를 embedded manifest에 결속한다. `HANDOFF_SUMMARY.md`는 reviewer·score·decision state·evidence hash·권한 경계를 사람이 읽는 표로 보여주며, verifier는 summary까지 재생성한 뒤 원래 pack 없이 membership·hash·artifact readiness·accepted transition·source binding·no-training boundary를 재검증한다. `--summary-output`은 검증된 exact Markdown만 atomic write하고 summary SHA-256을 남기며 기존 파일·symlink·변조 package에서는 어떤 output도 쓰지 않는다.
  - 2026-07-14 Admin Ops audit 화면에 report-quality pilot preview/export 필터와 receipt 대조용 request ID·전체 SHA-256·artifact count·검증 상태를 연결했다. Audit 문자열은 HTML escape하고 모바일에서는 table 내부 스크롤로 화면 overflow를 차단한다. 조회와 CSV export는 같은 action/result/시작일/종료일 filter를 사용하며, 누락·역전 기간은 요청 전에 차단하고 date-only 종료일은 해당 UTC 날짜 전체를 포함한다. 조회 API는 검증된 offset/limit, filtered total, `has_more`를 반환하고 UI는 전체 건수·현재 범위와 이전/다음 이동을 표시하며 페이지 간 filter를 유지한다. CSV는 전체 detail과 pilot 식별자를 보존하고 1,000건 query cap으로 증빙이 빠지지 않도록 별도 full export 경로를 사용한다. Spreadsheet formula로 해석될 수 있는 문자열도 안전한 text cell로 기록한다.
  - 2026-07-14 Ops 화면의 tenant selector가 admin 로그인 세션의 JWT를 유지하도록 tenant 목록 요청을 공통 인증 header 조합으로 정렬했다. `/admin/tenants`는 기존대로 admin JWT 또는 설정된 Ops key를 요구하며 권한 경계를 완화하지 않는다.
  - 2026-07-14 report-quality correction artifact 목록에 tenant-scoped `offset`/`limit`, filtered total, `has_more`를 추가하고 화면에 전체/ready 탐색과 5개 단위 페이지 이동을 연결했다. 페이지를 넘어가도 현재 tenant의 pilot 선택을 최대 5개까지 보존하며, tenant가 바뀌면 선택을 비우고 preview/export에서 기존 server-side 3~5개 ready 검증을 다시 수행한다.
  - 2026-07-14 DocumentOps trajectory 목록의 `total`을 제한된 응답 길이가 아닌 tenant·filter 기준 실제 건수로 바로잡고, `offset`/`limit`과 `returned`/`has_more` 계약을 추가했다. Browser workbench는 제목·trajectory ID·request ID·검토자 검색, 작업 유형·검토 상태 filter, 최신순/오래된 순 정렬, 10건 단위 이력 이동, 조건 변경과 새 실행 시 첫 페이지 복귀, 리뷰 후 현재 page가 비면 마지막 유효 page 복귀를 지원한다. 각 trajectory는 전체 입력·초안·근거 상태·QA gate·review history를 펼쳐보고 명시적인 검토 메모와 사람 품질 점수를 제출하며, 자동 점수로 승인하지 않는다. Mock/local desktop·390px mobile에서 검색·양방향 정렬·상세 검토·overflow·console error를 검증한다.
  - 2026-07-14 DocumentOps browser 목록을 `include_detail=false` summary-first 계약으로 전환했다. 목록 응답은 title·draft preview·QA·review 상태만 유지하고, 검토자가 펼친 기록만 tenant-scoped `GET /api/agent/document-ops/trajectories/{trajectory_id}`로 전체 입력·초안·근거·QA·review history를 불러온다. 기존 API 호출은 기본 full response를 유지하며 lazy detail 뒤의 명시적 사람 검토 흐름도 그대로 보존한다.
  - 2026-07-14 DocumentOps 상세 열람과 사람 review 요청을 append-only audit에 연결했다. Route가 명시한 action으로 정적 stats/export 경로와 구분하고, 성공·실패 resource에 tenant-scoped trajectory ID와 review 상태·결정·reviewer·버전·점수만 남긴다. 입력·초안·review notes는 audit detail에서 제외하며 Admin Ops에서 두 action을 필터링해 provenance를 확인한다.
  - 2026-07-14 DocumentOps browser review 초안을 tenant ID와 trajectory ID의 복합 page-memory key로 격리했다. Ops tenant selector가 바뀌면 trajectory 목록과 filter/page 상태를 새 tenant 기준으로 즉시 다시 읽고 이전 tenant의 지연된 목록·stats 응답을 무시해, 동일 trajectory ID가 존재해도 이전 tenant의 메모·점수를 복원하거나 오래된 card에서 제출하지 않는다.
  - 2026-07-14 browser tenant context를 signed access token의 tenant claim과 로그인·등록·refresh·LDAP login 시점마다 동기화했다. Review draft key에는 사용자 ID를 추가하고 logout/invalid session에서 전체 draft를 폐기한다. Ops tenant selector는 `/bundles` access preflight가 실패하면 선택값과 localStorage를 기존 tenant로 되돌리고, 성공한 전환만 전체 app reload로 반영해 JWT tenant mismatch와 다른 화면의 stale tenant state를 우회하지 않는다.
  - 2026-07-14 UI pilot export를 local review pack으로 가져오는 `--source-jsonl` 경로를 추가했다. Source SHA-256, tenant, 선택 순서를 manifest에 남기고 sync에서도 순서를 보존하며, membership drift와 외부 학습 실행을 차단한다.
  - 2026-07-14 pilot worksheet와 review decision template을 source manifest·ordered draft SHA-256에 결속했다. Source-bound pack은 unbound/stale decision을 거부하고, batch 검증 오류가 있으면 어떤 draft도 부분 저장하지 않는다.
  - 2026-07-14 review decision 적용 성공 시 decision SHA-256, before/after pack binding, artifact별 draft hash 전이를 pack-local receipt로 남기고 현재 ready gate와 no-training boundary를 read-only validator로 재검증하는 경로를 추가했다.
  - 2026-07-14 pilot JSONL sync를 validate-before-write로 바꿨다. Validation 또는 ready gate가 실패하면 새 출력을 만들거나 기존 출력을 덮어쓰지 않고, 성공한 write만 output SHA-256과 함께 보고하며 symlink·원본 source 경로 overwrite를 거부한다.
  - 2026-07-14 운영 API quality export checker도 validate-before-write로 정렬하고 summary/export count·tenant 일치, artifact ID uniqueness, single-tenant batch를 강제했다. Batch summary는 duplicate·mixed tenant를 명시적 blocker로 남기며 source JSONL과 symlink input/output overwrite를 거부하고, downstream evidence validator는 실제 JSONL에서 identity를 독립 재계산한다.
  - 2026-07-14 pilot JSONL 다운로드 응답에 본문 SHA-256을 포함하고 hash prefix를 파일명에 남겨, 로컬 import 뒤 `SOURCE_MANIFEST.json`과 원본 export identity를 직접 대조할 수 있게 했다.
  - 2026-07-14 final approval record template 뒤에서 같은 미승인 상태를 반복 포장하던 legacy no-cost chain을 제거했다. Evidence, discussion, plan, packet review, pending final approval record의 hash·review·권한 검증은 유지하고, 실제 실행은 별도 change control 없이는 시작할 수 없는 terminal boundary로 정리했다.
  - 2026-07-13 `proposal_kr`, `performance_plan_kr`의 대표 mock sample 6개 문서와 canonical golden fingerprint, validator/lint, request 대비 단위 수치 literal coverage 결과를 tracked evidence package로 정리했다. numeric coverage는 factual truth 검증과 분리한다.
  - 2026-07-13 tracked review dashboard에서 request 근거, validator/lint/numeric 상태, factual·human review 미완료 경계, 생성 Markdown 본문을 한 화면에 확인하도록 보강했다.
  - 2026-07-13 tracked manifest SHA256에 결속된 human review receipt와 `init/record/validate` CLI를 추가했다. 모든 bundle의 factual·visual review가 통과해야만 완료되며 외부 action 승인은 계속 `false`로 유지된다.
  - 2026-07-13 receipt 상태, reviewer, notes, manifest 결속, 외부 action 경계를 한 화면에서 확인하는 `human_review.html` companion view와 CLI `render` 경로를 추가했다. JSON receipt는 계속 증적 원본으로 유지한다.
  - 2026-07-13 completed receipt만 허용하는 finished-document review packet과 `package/verify-packet` CLI를 추가했다. Manifest-declared artifact만 포함하고 embedded SHA256 index, path boundary, tamper detection을 검증한다.
  - 2026-07-13 `human_review.html`을 request 근거, 자동 검증, 생성 문서, 사람 검토, 외부 권한 경계를 한 화면에서 확인하는 unified reviewer workspace로 확장했다. Manifest-owned `review.html`은 자동 검증 원본으로 유지한다.
  - 2026-07-13 reviewer workspace에서 bundle별 검토 값을 source-bound draft JSON으로 내려받고 `apply-draft` CLI가 manifest/receipt hash와 비승인 경계를 검증한 뒤 receipt를 atomic update하는 local sign-off 입력 흐름을 추가했다.
  - 2026-07-13 offline eval을 현재 template으로 다시 실행해 fixture 10건의 validator/lint pass evidence를 README와 case study에 연결했다.
- 남은 작업:
  - M1 live provider chain의 잔여 Gemini/Claude/fallback proof를 포함한 비용 발생 테스트는 사용자 요청에 따라 추후로 보류한다.
- 완료 기준:
  - 최소 2개 bundle에 대해 생성 결과 샘플과 품질 검증 결과 확보
  - mock provider와 최소 1개 live provider 검증 기록 존재
  - 사용자 피드백 또는 자체 평가 기준 문서화
- 산출물:
  - quality evaluation report: `reports/eval/v1/eval_report.{json,md}`
  - representative bundle sample: `docs/samples/bundle_quality_evidence/current/`
  - before/after sample: report quality correction artifact 흐름에서 유지
  - provider validation note

## 5. Phase 3 - 서비스화 / 배포

- 목표: 로컬 MVP를 외부에서 확인 가능한 배포 상태로 만든다.
- 해야 할 작업:
  - 운영 URL 또는 preview URL 확보
  - 환경변수 template 정리
  - Docker Compose 또는 AWS SAM 배포 절차 재검증
  - post-deploy smoke 결과 저장
  - security header, auth, tenant boundary 점검
- 완료 기준:
  - `/health`와 대표 smoke 통과
  - 데모 URL 또는 영상 제출 가능
  - 민감 정보가 repo와 문서에 노출되지 않음
- 산출물:
  - deployment note
  - post-deploy smoke report
  - demo link or recording

## 6. Phase 4 - 포트폴리오 완성

- 목표: 이력서, GitHub, 면접에서 일관되게 설명 가능한 프로젝트로 정리한다.
- 현재 상태:
  - README, architecture, case study, contribution note, project card, resume bullets, interview story의 claim boundary를 2026-07-14 코드와 local evidence에 맞췄다.
  - `scripts/manage_portfolio_pack.py`가 tracked source allowlist를 pack에 atomic sync하고 membership, byte content, generated SHA-256 manifest를 검증한다.
  - Local delivery ZIP은 고정 timestamp와 정렬된 entry로 재현하며 pack 밖에만 생성하고 git에는 포함하지 않는다.
  - 과거 source와 달라진 pack 파일, placeholder, historical README 개선안은 `sync --prune`으로 제거한다.
  - 운영 URL, live provider, G2B 실데이터, 사용자 성과 수치는 검증 전 claim에서 제외한다.
- 완료 기준:
  - README, case study, resume bullets, interview story가 서로 모순되지 않음
  - 구현 완료/개발 중/검증 필요가 분리되어 있음
  - 면접에서 코드 파일과 함수명을 기준으로 설명 가능
  - tracked pack과 source가 SHA-256 manifest 기준으로 일치함
- 산출물:
  - GitHub README
  - portfolio case study
  - resume bullets
  - interview answer sheet
  - `_portfolio_export/decisiondoc_ai_portfolio_pack/portfolio_manifest.json`

## 7. 우선순위 높은 다음 작업 5개

| 우선순위 | 작업 | 이유 | 예상 산출물 |
|---|---|---|---|
| 1 | local workflow 품질 개선 | 비용 없이 제품 가치와 검증 강도를 계속 높일 수 있음 | 다음 기능 slice와 focused regression |
| 2 | portfolio claim/pack 유지 | 코드 변경 뒤 문서와 증거 drift를 조기에 차단 | `manage_portfolio_pack.py check` |
| 3 | contribution note 유지 | 면접 설명이 실제 코드와 증거 범위를 넘지 않게 유지 | `docs/contribution-note.md` |
| 4 | 포트폴리오용 짧은 UI recording 선택 캡처 | 최신 screenshot은 갱신됐고, 영상은 제출 방식에 따라 선택 필요 | short recording |
| 5 | M1/M2/M6 외부 실증 | paid provider, G2B, deployment 증거가 남아 있으나 현재는 사용자 요청으로 보류 | readiness 재확인 후 runner-generated receipts |

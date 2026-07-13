# Development Roadmap

분석 기준: 2026-07-09 현재 저장소 코드, README, docs, 설정 파일, 최근 git log, worktree 상태, 최근 기능 변경 기준 GitHub Actions CI/CD 결과를 기준으로 업데이트했다. 로드맵은 포트폴리오 완성보다 먼저 재현 가능한 검증 evidence 확보를 우선한다.

제품 방향성 기준 문서: [DecisionDoc AI Product Direction](./product_direction.md), 실행 계획 문서: [DecisionDoc AI Product Execution Plan](./product_execution_plan.md), local demo scenario: [DecisionDoc AI Local Product Demo Scenario](./product_demo_scenario.md), local demo runbook: [DecisionDoc AI Local Demo Runbook](./product_local_demo_runbook.md). 이 roadmap은 해당 방향성 중 재현 가능한 검증 evidence, public procurement wedge, review/sign-off workflow, exportable decision package를 우선 실행 대상으로 둔다.

Local evidence CLI contract 기준: `docs/samples/procurement_decision_package_local_demo/cli_contract_manifest.json`의 `contract_version`을 기준으로 stdout JSON success/failure field를 고정하고, `scripts/validate_procurement_decision_package_cli_contract_manifest.py`와 `scripts/check_procurement_decision_package_cli_contract_manifest_result.py`로 manifest와 persisted receipt를 검증한다. 장기 보존이 필요한 검증 결과는 `--write-result --result-path <path>`로 repo 밖 임시 경로에 기록한다.

Completion readiness 기준: [development-plan.md](./development-plan.md)의 M1/M2/M6는 `scripts/check_completion_readiness.py`로 실행 준비 조건을 먼저 확인한다. proof 실행 순서와 증적 갱신 순서는 [completion-readiness-runbook.md](./completion-readiness-runbook.md)에 둔다. readiness 스크립트는 readiness만 확인하며 provider API, G2B live API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 실행하지 않는다.

## 1. 현재 상태 요약

- 현재 구현 완료: FastAPI 앱, 문서 생성 API, bundle catalog, provider/storage abstraction, export service, project/knowledge/approval/history/report workflow 일부, G2B search/fetch, health/metrics, Docker/AWS SAM 설정, pytest/smoke 기반 검증 경로
- 로컬 완료: export 5종 대칭성(M3), CSP nonce 적용(M4), 800줄 초과 모듈 분할(M5)
- 최근 확인한 main 자동화 증적: commit `01b9fbc` 기준 GitHub Actions CI `29027090095` success, CD `29027088935` success. CD의 staging deploy/smoke는 설정 부재로 skip되어 M6 proof는 아니다.
- 개발 중: report quality learning, document ops agent, correction artifact/training workflow, fine-tune/model registry, post-deploy evidence 자동화
- 미검증/외부 의존: Gemini/Claude 및 성공 fallback proof(M1), G2B 실데이터 end-to-end(M2), 배포 접근성 및 post-deploy smoke(M6)
- 미구현 또는 증거 없음: 실제 사용자 성과 수치, 포트폴리오용 데모 영상/스크린샷, 현재 운영 URL 접근 검증 자료, 사용자 피드백 기반 개선 사례

현재 로컬 기준 검증:

```bash
pytest tests/ -m "not live" -q
# 2026-07-14 실측: 2885 passed, 2 skipped, 4 deselected

python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
```

## 2. Completion Milestones

| 마일스톤 | 현재 상태 | 다음 조건 |
|---|---|---|
| M1 Live provider 실증 | 진행 중. 2026-07-13 OpenAI 1회 통과; Gemini HTTP 429, Claude credit 부족, fallback 성공 미달 | Gemini quota/billing과 Anthropic credits 복구 후 Gemini/Claude/fallback live test 재실행 |
| M2 G2B 실데이터 end-to-end | 미착수. `G2B_API_KEY` 없이 live 수집 불가 | stage URL/API key/G2B key 확보 후 `scripts/run_stage_procurement_smoke.py` 증적화 |
| M3 Export 5종 대칭성 | 완료 | README와 샘플 산출물의 수치가 코드와 계속 일치하는지 유지 |
| M4 CSP nonce | 완료. inline `on*=` handler 0개, nonce 기본 on | 새 UI 이벤트 추가 시 inline handler 금지 guard 유지 |
| M5 800줄 초과 모듈 분할 | 완료. 2026-07-02 기준 800줄 초과 0개 | 큰 모듈 추가 시 분할 기준 유지 |
| M6 배포/post-deploy smoke | 미착수. `.env.prod`와 runtime 증거 필요 | 배포 환경 확보 후 `scripts/run_deployed_smoke.py`와 ops smoke 증적화 |

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
  - report quality learning과 correction artifact 계열은 계속 개발 중이다.
  - 2026-07-13 report quality UI의 자동 통과 score/rationale를 제거하고, accepted artifact의 dimension rationale를 server gate로 강제했다.
  - 2026-07-13 mock provider와 임시 local storage만 사용하는 report workflow 생성·승인·correction artifact 저장·JSONL export 데모를 연결했다.
  - 2026-07-13 correction artifact에 stable content identity와 SHA-256 preview fingerprint를 적용했다. Save는 현재 workflow/input과 일치하는 preview만 허용하고 누락·stale input·중복 artifact를 거부하며, review packet validator도 embedded artifact fingerprint를 재검증한다.
  - 2026-07-13 저장된 correction artifact를 tenant 범위에서 단건 조회하는 detail API와 UI 검토·개별 JSON 다운로드 동선을 추가했다. 응답은 metadata-only artifact, validation, preview fingerprint를 보존하며 provider call, dataset upload, training execution은 계속 차단한다.
  - 2026-07-14 ready correction artifact 3~5개를 UI에서 직접 고르고 ordered pilot JSONL로 내려받는 tenant-safe selection flow를 추가했다. 서버는 개수, 중복·alias 중복, 존재 여부, ready gate를 재검증하며 외부 학습 작업은 실행하지 않는다.
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
- 해야 할 작업:
  - README 최종 정리
  - architecture diagram과 주요 코드 설명 추가
  - issue/PR/commit 기반 개발 과정 정리
  - 면접 답변에서 위험한 표현 제거
  - 직접 구현 범위와 검증된 기능만 이력서 bullet로 반영
- 완료 기준:
  - README, case study, resume bullets, interview story가 서로 모순되지 않음
  - 구현 완료/개발 중/검증 필요가 분리되어 있음
  - 면접에서 코드 파일과 함수명을 기준으로 설명 가능
- 산출물:
  - GitHub README
  - portfolio case study
  - resume bullets
  - interview answer sheet

## 7. 우선순위 높은 다음 작업 5개

| 우선순위 | 작업 | 이유 | 예상 산출물 |
|---|---|---|---|
| 1 | M1 live provider 실증 완료 | OpenAI proof는 있으나 Gemini/Claude/fallback 성공 증거가 남음 | blocked receipt 갱신 후 live provider validation note 완료 |
| 2 | M2 G2B 실데이터 smoke 준비 | 공공조달 흐름은 live key 없이는 end-to-end 증거가 없음 | G2B smoke receipt |
| 3 | M6 배포/post-deploy smoke 준비 | README Demo 링크를 채우려면 접근성 evidence가 필요 | deployment note, smoke report |
| 4 | 포트폴리오용 짧은 UI recording 선택 캡처 | 최신 screenshot은 갱신됐고, 영상은 제출 방식에 따라 선택 필요 | short recording |
| 5 | contribution note 유지 | 면접 설명이 실제 코드와 증거 범위를 넘지 않게 유지 | `docs/contribution-note.md` |

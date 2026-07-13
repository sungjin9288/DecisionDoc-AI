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
# 2026-07-09 실측: 2805 passed, 2 skipped, 4 deselected

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
  - report quality learning과 correction artifact 계열은 계속 개발 중이다.
  - 2026-07-13 report quality UI의 자동 통과 score/rationale를 제거하고, accepted artifact의 dimension rationale를 server gate로 강제했다.
  - 2026-07-13 mock provider와 임시 local storage만 사용하는 report workflow 생성·승인·correction artifact 저장·JSONL export 데모를 연결했다.
  - 2026-07-13 `proposal_kr`, `performance_plan_kr`의 대표 mock sample 6개 문서와 canonical golden fingerprint, validator/lint, request 대비 단위 수치 literal coverage 결과를 tracked evidence package로 정리했다. numeric coverage는 factual truth 검증과 분리한다.
  - 2026-07-13 tracked review dashboard에서 request 근거, validator/lint/numeric 상태, factual·human review 미완료 경계, 생성 Markdown 본문을 한 화면에 확인하도록 보강했다.
  - 2026-07-13 offline eval을 현재 template으로 다시 실행해 fixture 10건의 validator/lint pass evidence를 README와 case study에 연결했다.
- 남은 작업:
  - M1 live provider chain을 승인된 키로 검증
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

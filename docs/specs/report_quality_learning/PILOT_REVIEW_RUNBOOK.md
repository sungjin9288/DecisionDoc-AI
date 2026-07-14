# Pilot Review Runbook

이 runbook은 fine-tuning 전에 사용할 파일럿 샘플 3~5개를 만드는 절차다.

## 1. 파일럿 주제 선정

처음에는 실제 고객 민감자료보다 내부/공개/비식별 자료를 사용한다.

권장 주제:

- 공공기관 AI 교통안전 제안서
- 스마트공장 공급기업 소개서
- 내부 설치형 문서 운영 플랫폼 소개서
- G2B 사업 제안 기획안
- 운영/보안/거버넌스 보고서

## 2. Workflow 설정

Report Workflow 생성 시:

- `learning_opt_in=true`
- 원본 첨부파일은 학습 artifact에 저장하지 않음
- 민감 원문은 요약/metadata/reference만 사용
- 최종 승인 전까지 학습 후보로 보지 않음

Report Workflow UI에서 ready artifact 3~5개를 선택한 뒤 `Pilot 검토`를 실행한다. Preview는 artifact 순서, readiness, 전체 JSONL SHA-256, 외부 학습 비승인 경계를 보여준다. 다운로드 요청은 이 hash를 `preview_sha256`으로 다시 제출하며, 서버가 현재 ordered JSONL과 대조해 일치할 때만 `X-DecisionDoc-Pilot-Preview-Verified: true`와 파일을 반환한다. 누락되거나 stale한 hash는 `400` 또는 schema validation으로 차단된다.

`검토 패키지 ZIP`은 JSONL과 `report_quality_pilot_receipt_<sha12>.json` sidecar, `pilot_package_manifest.json`을 하나의 archive로 내려준다. Manifest는 exact membership, entry별 size/SHA-256, tenant, artifact 순서, request ID, 외부 실행 비승인 경계를 기록한다. 서버는 ZIP을 응답 전에 다시 검증하고 browser는 `X-DecisionDoc-Pilot-Package-SHA256`과 실제 bytes를 대조한 뒤 저장한다. 기존 `JSONL + receipt` 개별 다운로드도 호환 경로로 유지한다.

검토 패키지는 풀지 않고 importer에 그대로 전달한다. Importer가 package manifest, entry hash와 크기, JSONL, receipt, tenant, artifact 순서, no-training boundary를 다시 검증한 뒤 local review pack을 만든다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --source-package ~/Downloads/report_quality_pilot_review_package_<sha12>.zip \
  --output-root reports/report-quality
```

기존 JSONL과 receipt를 개별 다운로드한 경우에는 `--source-jsonl`과 `--source-receipt`를 함께 사용한다.

생성물:

- `reports/report-quality/pilot-rqc-001/REVIEW_INDEX.md`
- `reports/report-quality/pilot-rqc-001/drafts/*.json`
- `reports/report-quality/pilot-rqc-001/pilot-rqc-001-drafts.jsonl`
- `reports/report-quality/pilot-rqc-001/SOURCE_MANIFEST.json`
- `reports/report-quality/pilot-rqc-001/SOURCE_EXPORT_RECEIPT.json`
- `reports/report-quality/pilot-rqc-001/SOURCE_PACKAGE_MANIFEST.json` (`--source-package` 사용 시)
- `reports/report-quality/pilot-rqc-001/HUMAN_REVIEW_WORKSHEET.md`
- `reports/report-quality/pilot-rqc-001/human_review_manifest.json`
- `reports/report-quality/pilot-rqc-001/review_decisions.json`
- `reports/report-quality/pilot-rqc-001/HUMAN_REVIEW_WORKSPACE.html`

주의:

- import는 검증된 package 또는 서로 짝이 맞는 UTF-8 JSONL·server receipt, ready artifact 3~5개, 중복 없는 artifact ID, 단일 tenant를 요구한다.
- 모든 pack mode는 같은 batch ID의 출력 디렉터리에 기존 파일이 있거나 해당 경로가 symlink이면 사람의 수정과 stale artifact를 덮어쓰지 않도록 생성을 거부한다.
- `SOURCE_MANIFEST.json` v3는 원본 package와 embedded JSONL·receipt·package manifest의 SHA-256, size, request ID, tenant, 선택 순서를 기록한다. Embedded manifest 원문은 `SOURCE_PACKAGE_MANIFEST.json`에 보존하므로 원본 ZIP이 이동되거나 삭제되어도 이후 sync가 hash, entry metadata, tenant, request ID, artifact 순서, no-training boundary를 다시 확인할 수 있다. Manifest·receipt·draft 구성이 다르면 실패하며 기존 v1/v2 manifest와 JSONL+receipt 입력은 계속 읽을 수 있다.
- 가져온 artifact는 이미 ready gate를 통과했더라도 사람이 교정 내용과 점수, scan 결과를 다시 검토한다.
- 이 helper는 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

실제 ready artifact가 아직 없다면 non-ready draft를 먼저 만들 수 있다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --sample-count 3 \
  --output-root reports/report-quality
```

이 fallback으로 만든 draft는 `accepted_for_learning=false`, `human_review_status=pending`이다. 사람이 교정 근거, 점수, scan 결과, 최종본 reference를 채우기 전에는 `--require-ready` 검증이 실패하는 것이 정상이며, `accepted_for_learning=true`인 artifact에 `TODO_*`가 남아 있으면 validator가 차단한다.

사람이 `drafts/*.json`을 검토하거나 수정한 뒤에는 JSONL을 다시 동기화한다.

Pack 생성 시 worksheet와 manifest가 자동으로 만들어진다. 이후 draft를 직접 수정했다면 아래 명령으로 현재 hash와 required action을 다시 계산한다.

```bash
python3 scripts/create_report_quality_review_sheet.py \
  reports/report-quality/pilot-rqc-001
```

자동 생성 또는 refresh되는 파일:

- `reports/report-quality/pilot-rqc-001/HUMAN_REVIEW_WORKSHEET.md`
- `reports/report-quality/pilot-rqc-001/human_review_manifest.json`

worksheet는 reviewer, reviewed_at, quality score, scan 결과, 승인 여부를 정리하기 위한 파생 검수 문서다. Source import pack이면 `human_review_manifest.json`에 source manifest SHA-256, tenant, artifact 순서와 각 draft SHA-256을 함께 기록한다. 이 helper는 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

새 pack에는 현재 binding에 맞는 `review_decisions.json`과 `HUMAN_REVIEW_WORKSPACE.html`도 한 번만 생성된다. 원래 artifact 상태는 `previous_decision`에 보존하지만 새 파일럿 검토의 `decision`은 모두 `pending`에서 시작한다. 기존 pack처럼 파일이 없는 경우에만 아래 명령으로 template과 browser workspace를 추가한다.

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --create-template reports/report-quality/pilot-rqc-001/review_decisions.json

python3 scripts/create_report_quality_review_workspace.py \
  reports/report-quality/pilot-rqc-001 \
  --decisions reports/report-quality/pilot-rqc-001/review_decisions.json
```

검수자는 `HUMAN_REVIEW_WORKSPACE.html`을 브라우저에서 연다. 각 artifact 영역은 현재 workflow 상태와 final reference, validator의 valid/ready 상태, 필요한 조치, error·warning, 교정 전후 planning summary와 장표 구조, 검토 대상 claim을 현재 source-bound draft에서 읽어 보여준다. 이 근거를 확인한 뒤 `decision`, `reviewer`, `reviewed_at`, `overall_score`, `dimension_scores`, scan 결과, 차원별 근거와 보완 요청을 채운다. 새 파일럿 decision이 `pending`이면 원본 artifact가 이미 ready였어도 `사람 검토 결정 기록`을 필요한 조치로 표시한다.

`검수 Draft 다운로드`는 초기 template의 `pack_binding`, artifact 순서, `previous_decision`, `training_authorized=false`를 보존한 `review_decisions.browser-draft.json`만 만든다. HTML은 pack의 draft나 decision template을 직접 수정하지 않으며 외부 요청도 보내지 않는다.

내려받은 draft는 이동하거나 이름을 바꾸지 않고 외부 경로에서 바로 검증·보관·반영한다. 먼저 쓰기 없이 확인하려면 `--dry-run`을 붙인다.

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --browser-draft ~/Downloads/review_decisions.browser-draft.json \
  --dry-run
```

승인할 artifact만 `decision=accepted`로 바꾸고, 반려나 보완 요청은 `changes_requested` 또는 `rejected`로 둔다. Generator는 기존 template, workspace, symlink를 덮어쓰지 않는다. Draft를 직접 바꿔 기존 binding이 stale해졌다면 기존 파일을 보존하고 `review_decisions.refreshed.json`, `HUMAN_REVIEW_WORKSPACE.refreshed.html`처럼 새 경로에 template과 workspace를 다시 만든다.

결정 파일을 draft artifact에 반영할 때:

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --browser-draft ~/Downloads/review_decisions.browser-draft.json \
  --require-ready
```

Source import pack은 `--create-template`로 만든 binding이 없는 decision 파일을 거부한다. Template 생성 뒤 source manifest나 draft가 바뀌면 stale binding으로 판단해 쓰기 전에 중단한다. Decision batch 안에 잘못된 항목이 하나라도 있으면 유효한 다른 항목도 저장하지 않는다. `--require-ready`는 `accepted` decision이 validator의 ready gate를 통과하지 못하면 전체 batch 저장을 차단한다.

`--browser-draft`는 report type, schema, `training_authorized=false`, source/draft binding, 전체 decision batch를 쓰기 전에 확인한다. 통과하면 내려받은 파일의 정확한 바이트를 `review_decisions.browser-draft.<sha12>.json`으로 pack에 보존하고, 같은 suffix의 `review_decision_application_receipt.<sha12>.json`을 자동 생성한다. 적용으로 draft hash나 검토 상태가 바뀌면 `HUMAN_REVIEW_WORKSHEET.md`와 `human_review_manifest.json`도 현재 pack binding으로 즉시 갱신한다. 외부 draft, 보관본, receipt, worksheet, manifest가 symlink이거나 기존 SHA 이름과 충돌하면 덮어쓰지 않는다. Dry-run이나 실패 batch에서는 보관본, draft, receipt, worksheet, manifest를 변경하지 않는다.

기존 pack-local decision 파일을 `--decisions`로 반영하는 호환 경로에서는 `--receipt`를 직접 지정할 수 있다. 이 경로도 성공한 apply 뒤 worksheet와 manifest를 갱신한다. 두 경로의 receipt는 decision SHA-256, 적용 전/후 pack binding, artifact별 draft hash 전이를 기록한다. 적용 직후 CLI가 출력한 `receipt_path`, `review_sheet_path`, `review_manifest_path`를 확인하고 receipt를 현재 파일과 다시 대조한다.

```bash
python3 scripts/validate_report_quality_review_decision_receipt.py \
  reports/report-quality/pilot-rqc-001/review_decision_application_receipt.<sha12>.json
```

Validator는 decision file, source manifest, 현재 draft SHA-256, `ready_for_learning`, no-training boundary를 read-only로 재검증한다. 두 helper 모두 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

```bash
python3 scripts/sync_report_quality_pilot_pack.py \
  reports/report-quality/pilot-rqc-001 \
  --min-records 3
```

승인 완료 후에는 ready gate까지 함께 확인한다.

```bash
python3 scripts/sync_report_quality_pilot_pack.py \
  reports/report-quality/pilot-rqc-001 \
  --min-records 3 \
  --require-ready
```

Sync는 모든 artifact validation을 통과한 뒤에만 JSONL을 쓴다. `--require-ready`에서는 현재 draft hash·상태·집계와 일치하는 `human_review_manifest.json`과, 기존 validator를 통과한 `require_ready=true` accepted decision application receipt도 함께 요구한다. Source import artifact가 이미 ready 상태여도 새 로컬 decision이 pending이거나 current receipt가 없으면 sync하지 않는다. 성공 결과는 `output_written=true`, `output_sha256`, `review_manifest.sha256`, `decision_receipt.sha256`을 반환하며 쓰기 직전에 pack binding과 두 검수 증거를 다시 확인한다.

실패 결과의 `output_written=false`는 이번 실행이 파일을 만들거나 덮어쓰지 않았다는 뜻이며, 이전 실행에서 남은 같은 경로의 파일은 변경하지 않는다. 출력은 `.jsonl`만 허용하고 symlink, import 원본 source JSONL, symlink review evidence 경로를 거부한다. `--require-ready`가 없는 중간 sync는 기존 호환 경로대로 검수 receipt 없이도 사용할 수 있지만 학습 후보 완료 증거로 보지 않는다.

승인된 JSONL을 다른 검토자나 보관 경로로 넘길 때는 현재 검수 근거와 함께 하나의 handoff ZIP으로 고정한다.

```bash
python3 scripts/manage_report_quality_pilot_handoff.py create \
  reports/report-quality/pilot-rqc-001 \
  --jsonl reports/report-quality/pilot-rqc-001/pilot-rqc-001-drafts.jsonl

python3 scripts/manage_report_quality_pilot_handoff.py verify \
  reports/report-quality/pilot-rqc-001/report_quality_pilot_review_handoff_<sha12>.zip \
  --summary-output reports/report-quality/pilot-rqc-001-handoff-summary.md
```

Create는 JSONL이 현재 draft 순서와 내용에 정확히 일치하는지 다시 확인하고, current `human_review_manifest.json`, `require_ready=true` accepted decision receipt, receipt가 가리키는 decision file, 최종 draft 3~5개, source-bound pack의 provenance sidecar를 `handoff_manifest.json`과 함께 deterministic ZIP으로 기록한다. `HANDOFF_SUMMARY.md`는 artifact별 검수자·검토 시각·점수·결정 상태, 핵심 evidence hash, 외부 실행 비승인 경계를 사람이 읽는 표로 정리한다. Verify는 원래 pack에 접근하지 않고 summary를 같은 evidence에서 다시 생성해 exact bytes를 대조하고, membership, size/SHA-256, JSONL과 draft의 semantic identity, accepted review 전이, source binding, no-training boundary를 재검증한다. `--summary-output`은 이 검증이 모두 끝난 뒤 exact summary만 별도 Markdown으로 atomic write하고 summary SHA-256을 결과에 남긴다. Package와 summary는 임시 파일을 완전히 동기화한 뒤 최종 이름을 한 번만 생성하므로 사전 검사 직후 다른 프로세스가 같은 경로를 만들어도 기존 증거를 덮어쓰지 않는다. 기존 파일과 symlink output은 거부하며 provider API, dataset upload, training execution, model promotion을 실행하지 않는다.

## 3. 생성과 교정

각 샘플마다 아래를 기록한다.

1. AI 생성 기획안
2. AI 생성 장표 초안
3. 사람이 남긴 수정 요청
4. 사람이 고친 최종 기획/장표 구조
5. 왜 고쳤는지 dimension별 rationale
6. export 결과 확인

## 4. 최소 승인 기준

학습 후보로 인정하려면:

- 기획안 승인 완료
- 모든 장표 승인 완료
- 최종 PM/대표 승인 또는 equivalent internal sign-off 완료
- `QUALITY_RUBRIC.md` 기준 hard fail 없음
- `overall_score >= 0.80`
- required scans pass
- validator pass

## 5. Validator 실행

교정 artifact 작성 후:

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py path/to/correction_artifact.json
```

학습 후보로 사용할 수 있는 경우 expected output:

```text
PASS report quality correction artifact validated
ready_for_learning=true
```

UI/API에서 내려받은 batch JSONL은 아래처럼 검사한다.

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py \
  path/to/report_quality_correction_artifacts.jsonl \
  --require-ready \
  --min-records 3
```

expected output:

```text
PASS report quality correction artifact JSONL validated
ready_for_learning=true
artifact_count=3
min_records=3
ready_artifacts=3
not_ready_artifacts=0
```

운영 API에서 바로 내려받아 검증할 때:

```bash
SMOKE_BASE_URL=https://admin.decisiondoc.kr \
SMOKE_API_KEY=<runtime-api-key> \
python3 scripts/check_report_quality_artifacts.py \
  --min-records 3 \
  --output tmp/report_quality_correction_artifacts.jsonl
```

expected output:

```text
PASS report quality correction artifact export check
ready_artifacts=3
artifact_count=3
output_written=true
output_sha256=<sha256>
training_boundary=not_authorized
```

Checker는 summary의 ready count·tenant와 export artifact 수·tenant를 대조하고, artifact ID 중복이나 tenant 혼합, validation·ready gate 실패가 있으면 JSONL을 쓰지 않는다. 기존 output이 있어도 실패 실행은 덮어쓰지 않는다. 출력은 `.jsonl`만 허용하며 symlink를 거부한다.

다운로드된 JSONL을 batch evidence로 남길 때:

```bash
python3 scripts/summarize_report_quality_artifacts.py \
  tmp/report_quality_correction_artifacts.jsonl \
  --batch-id pilot-rqc-001 \
  --min-records 3 \
  --output reports/report-quality/pilot-rqc-001-manifest.json \
  --markdown reports/report-quality/pilot-rqc-001-summary.md
```

expected output:

```text
Report quality batch readiness: PASS
Artifact count: 3
Ready artifacts: 3
```

Batch manifest는 unique artifact 수와 tenant 수를 함께 기록한다. 중복 artifact ID는 `duplicate_artifact_ids`, 여러 tenant가 섞인 batch는 `mixed_tenants_present` blocker로 남아 readiness를 통과하지 못한다. Source는 regular `.jsonl`이어야 하며, Manifest와 Markdown output은 source JSONL을 덮어쓸 수 없고 symlink도 허용하지 않는다. Review packet evidence validator는 manifest의 readiness를 그대로 신뢰하지 않고 실제 artifact JSONL에서 ID와 tenant를 다시 계산한다.

API 경로로 저장할 때는 먼저 preview를 호출해 blocker와 `preview_fingerprint`를 확인한다.

```bash
curl -sS -X POST \
  "$BASE_URL/report-workflows/$REPORT_WORKFLOW_ID/learning/correction-artifact/preview" \
  -H "X-DecisionDoc-Api-Key: $DECISIONDOC_API_KEY" \
  -H "Content-Type: application/json" \
  --data @path/to/correction_payload.json
```

`validation.ready_for_learning=true`가 확인된 뒤, preview 응답의 `preview_fingerprint`를 변경하지 않은 correction payload에 추가해서 저장 endpoint를 호출한다. Preview 후 score, rationale, summary, workflow 상태가 바뀌었다면 기존 fingerprint를 재사용하지 않고 preview부터 다시 실행한다.

```bash
PREVIEW_FINGERPRINT=<preview-response.preview_fingerprint>
jq --arg fingerprint "$PREVIEW_FINGERPRINT" \
  '. + {preview_fingerprint: $fingerprint}' \
  path/to/correction_payload.json \
  > path/to/preview_bound_correction_payload.json

curl -sS -X POST \
  "$BASE_URL/report-workflows/$REPORT_WORKFLOW_ID/learning/correction-artifact" \
  -H "X-DecisionDoc-Api-Key: $DECISIONDOC_API_KEY" \
  -H "Content-Type: application/json" \
  --data @path/to/preview_bound_correction_payload.json
```

동일 artifact를 두 번 저장하거나 현재 입력과 맞지 않는 fingerprint를 보내면 save는 실패한다. Review packet JSON에도 fingerprint가 포함되며 local validator가 embedded preview artifact의 SHA-256과 대조한다.

## 6. Fine-Tuning 전 Stop Gate

아래 조건을 만족하기 전에는 provider fine-tune API를 호출하지 않는다.

- accepted correction artifact 최소 30개
- 서로 다른 문서 유형 최소 3개
- reviewer 2명 이상이 일부 샘플을 교차 검수
- export 깨짐 0건
- hard fail 0건
- privacy/security scan pass
- baseline provider 대비 eval prompt에서 개선 가능성이 보임

## 7. 운영 기록

각 파일럿 batch는 아래를 남긴다.

- batch id
- sample count
- accepted/rejected/changes requested count
- 평균 dimension score
- 가장 자주 나온 수정 사유
- prompt/template 개선 항목
- fine-tuning 진행 여부
- `reports/report-quality/*-manifest.json`
- `reports/report-quality/*-summary.md`

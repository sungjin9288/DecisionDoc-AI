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

Report Workflow UI에서 ready artifact 3~5개를 선택하면 응답 본문의 SHA-256 앞 12자가 포함된 `report_quality_pilot_artifacts_<sha12>.jsonl`을 내려받는다. 서버는 전체 SHA-256을 `X-DecisionDoc-Pilot-SHA256` 응답 헤더에도 기록한다. 파일을 로컬 review pack으로 가져온 뒤 `SOURCE_MANIFEST.json`의 `source_sha256`이 이 전체 hash와 일치하는지 확인한다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --source-jsonl ~/Downloads/report_quality_pilot_artifacts_<sha12>.jsonl \
  --output-root reports/report-quality
```

생성물:

- `reports/report-quality/pilot-rqc-001/REVIEW_INDEX.md`
- `reports/report-quality/pilot-rqc-001/drafts/*.json`
- `reports/report-quality/pilot-rqc-001/pilot-rqc-001-drafts.jsonl`
- `reports/report-quality/pilot-rqc-001/SOURCE_MANIFEST.json`

주의:

- import는 UTF-8 JSONL, ready artifact 3~5개, 중복 없는 artifact ID, 단일 tenant를 요구한다.
- 같은 batch ID의 출력 디렉터리에 기존 파일이 있으면 stale artifact가 섞이지 않도록 import를 거부한다.
- `SOURCE_MANIFEST.json`은 원본 경로와 SHA-256, tenant, 선택 순서를 기록한다. 이후 sync도 이 순서를 그대로 적용하며 manifest와 draft 구성이 다르면 실패한다.
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

검수자가 채워야 할 항목을 한눈에 확인하려면 worksheet를 만든다.

```bash
python3 scripts/create_report_quality_review_sheet.py \
  reports/report-quality/pilot-rqc-001
```

생성물:

- `reports/report-quality/pilot-rqc-001/HUMAN_REVIEW_WORKSHEET.md`
- `reports/report-quality/pilot-rqc-001/human_review_manifest.json`

worksheet는 reviewer, reviewed_at, quality score, scan 결과, 승인 여부를 정리하기 위한 로컬 검수 문서다. Source import pack이면 `human_review_manifest.json`에 source manifest SHA-256, tenant, artifact 순서와 각 draft SHA-256을 함께 기록한다. 이 helper는 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

JSON을 직접 수정하는 대신 decision template을 만들어 검수 결정을 반영할 수 있다.

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --create-template reports/report-quality/pilot-rqc-001/review_decisions.json
```

검수자는 `review_decisions.json`에서 각 artifact의 `decision`, `reviewer`, `reviewed_at`, `overall_score`, `dimension_scores`, scan 결과를 채운다. Template은 현재 review 상태를 그대로 시작값으로 사용하고, `pack_binding`에 source manifest와 draft SHA-256을 기록한다. 승인할 artifact만 `decision=accepted`로 유지하거나 바꾸고, 반려나 보완 요청은 `changes_requested` 또는 `rejected`로 둔다.

결정 파일을 draft artifact에 반영할 때:

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --decisions reports/report-quality/pilot-rqc-001/review_decisions.json \
  --require-ready \
  --receipt reports/report-quality/pilot-rqc-001/review_decision_application_receipt.json
```

Source import pack은 `--create-template`로 만든 binding이 없는 decision 파일을 거부한다. Template 생성 뒤 source manifest나 draft가 바뀌면 stale binding으로 판단해 쓰기 전에 중단한다. Decision batch 안에 잘못된 항목이 하나라도 있으면 유효한 다른 항목도 저장하지 않는다. `--require-ready`는 `accepted` decision이 validator의 ready gate를 통과하지 못하면 전체 batch 저장을 차단한다.

`--receipt`를 사용하면 같은 pack 안의 decision 파일 SHA-256, 적용 전/후 pack binding, artifact별 draft hash 전이를 receipt로 남긴다. 기존 receipt는 덮어쓰지 않으며 dry-run이나 실패 batch에서는 생성하지 않는다. 적용 직후 다음 명령으로 receipt와 현재 파일을 다시 대조한다.

```bash
python3 scripts/validate_report_quality_review_decision_receipt.py \
  reports/report-quality/pilot-rqc-001/review_decision_application_receipt.json
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

Sync는 모든 artifact validation과 `--require-ready` 조건이 통과한 뒤에만 JSONL을 쓴다. 실패 결과의 `output_written=false`는 이번 실행이 파일을 만들거나 덮어쓰지 않았다는 뜻이며, 이전 실행에서 남은 같은 경로의 파일은 변경하지 않는다. 성공 결과는 `output_written=true`와 `output_sha256`을 함께 반환한다. 출력은 `.jsonl`만 허용하고 symlink나 import 원본 source JSONL 경로는 거부한다.

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

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

리뷰를 시작하기 전 draft artifact와 체크리스트를 생성한다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --sample-count 3 \
  --output-root reports/report-quality
```

생성물:

- `reports/report-quality/pilot-rqc-001/REVIEW_INDEX.md`
- `reports/report-quality/pilot-rqc-001/drafts/*.json`
- `reports/report-quality/pilot-rqc-001/pilot-rqc-001-drafts.jsonl`

주의:

- 생성 직후 draft는 `accepted_for_learning=false`이고 `human_review_status=pending`이다.
- 사람이 교정 근거, 점수, scan 결과, 최종본 reference를 채우기 전에는 `--require-ready` batch validation이 실패하는 것이 정상이다.
- `accepted_for_learning=true`로 바꾼 artifact 안에 `TODO_*` placeholder가 남아 있으면 validator가 차단한다.
- 이 helper는 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

사람이 `drafts/*.json`을 수정한 뒤에는 JSONL을 다시 동기화한다.

검수자가 채워야 할 항목을 한눈에 확인하려면 worksheet를 만든다.

```bash
python3 scripts/create_report_quality_review_sheet.py \
  reports/report-quality/pilot-rqc-001
```

생성물:

- `reports/report-quality/pilot-rqc-001/HUMAN_REVIEW_WORKSHEET.md`
- `reports/report-quality/pilot-rqc-001/human_review_manifest.json`

worksheet는 reviewer, reviewed_at, quality score, scan 결과, 승인 여부를 정리하기 위한 로컬 검수 문서다. 이 helper는 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

JSON을 직접 수정하는 대신 decision template을 만들어 검수 결정을 반영할 수 있다.

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --create-template reports/report-quality/pilot-rqc-001/review_decisions.json
```

검수자는 `review_decisions.json`에서 각 artifact의 `decision`, `reviewer`, `reviewed_at`, `overall_score`, `dimension_scores`, scan 결과를 채운다. 승인할 artifact만 `decision=accepted`로 바꾸고, 반려나 보완 요청은 `changes_requested` 또는 `rejected`로 둔다.

결정 파일을 draft artifact에 반영할 때:

```bash
python3 scripts/apply_report_quality_review_decisions.py \
  reports/report-quality/pilot-rqc-001 \
  --decisions reports/report-quality/pilot-rqc-001/review_decisions.json \
  --require-ready
```

`--require-ready`는 `accepted` decision이 validator의 ready gate를 통과하지 못하면 draft 저장을 차단한다. 이 helper도 provider fine-tune API, dataset upload, training execution, model promotion을 실행하지 않는다.

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
training_boundary=not_authorized
```

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

API 경로로 저장할 때는 먼저 preview를 호출해 blocker를 확인한다.

```bash
curl -sS -X POST \
  "$BASE_URL/report-workflows/$REPORT_WORKFLOW_ID/learning/correction-artifact/preview" \
  -H "X-DecisionDoc-Api-Key: $DECISIONDOC_API_KEY" \
  -H "Content-Type: application/json" \
  --data @path/to/correction_payload.json
```

`validation.ready_for_learning=true`가 확인된 뒤에만 저장 endpoint를 호출한다.

```bash
curl -sS -X POST \
  "$BASE_URL/report-workflows/$REPORT_WORKFLOW_ID/learning/correction-artifact" \
  -H "X-DecisionDoc-Api-Key: $DECISIONDOC_API_KEY" \
  -H "Content-Type: application/json" \
  --data @path/to/correction_payload.json
```

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

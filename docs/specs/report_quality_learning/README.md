# Report Quality Learning Gate

이 spec은 DecisionDoc의 보고서 품질을 높이기 위해 `fine-tuning` 전에 반드시 거치는 **교정 데이터 생산 게이트**를 정의한다.

현재 목표는 모델을 바로 학습시키는 것이 아니다. 먼저 사람이 승인할 수 있는 수준의 보고서/제안서 샘플을 만들고, 교정 전/후 차이와 수정 이유를 구조화해서 학습 후보 데이터로 저장한다.

## Scope

포함:

- 보고서 논리 품질 rubric
- 문서/PPT 장표 디자인 품질 rubric
- 교정 전/후 learning artifact 포맷
- 파일럿 샘플 3~5개 생성/검수 절차
- 실제 fine-tuning 전 차단 조건

제외:

- provider fine-tune API 호출
- 외부 dataset upload
- provider job 생성/폴링
- fine-tuned model promotion
- 원본 첨부파일 자체 저장

## Artifacts

- [QUALITY_RUBRIC.md](./QUALITY_RUBRIC.md)
- [PILOT_REVIEW_RUNBOOK.md](./PILOT_REVIEW_RUNBOOK.md)
- [correction_artifact_template.json](./correction_artifact_template.json)
- [validate_correction_artifact.py](./validate_correction_artifact.py)
- `scripts/create_report_quality_pilot_pack.py`
  - 파일럿 리뷰용 non-ready draft artifact 3~5개와 `REVIEW_INDEX.md`를 생성한다.
  - 기본 출력은 `accepted_for_learning=false`, `human_review_status=pending` 이므로 학습 후보가 아니다.

## Backend Integration

Report Workflow 최종 승인본은 아래 API로 교정 artifact를 생성하고 저장한다.

- `POST /report-workflows/{report_workflow_id}/learning/correction-artifact/preview`
  - 승인본 snapshot과 사람 검수 payload를 합쳐 metadata-only correction artifact를 미리 만든다.
  - 저장하지 않고 `validation.ok`, `validation.ready_for_learning`, blocker를 반환한다.
- `POST /report-workflows/{report_workflow_id}/learning/correction-artifact`
  - `final_approved` 상태이고 `learning_opt_in=true`인 workflow만 저장한다.
  - 저장 대상은 원본 첨부파일이 아닌 planning/slide/final metadata와 사람 교정 사유다.
  - validator가 `ready_for_learning=true`를 반환하지 않으면 `400`으로 차단한다.
- `GET /report-workflows/learning/correction-artifacts`
  - tenant 내부에 저장된 품질 교정 artifact를 read-only summary로 조회한다.
  - `ready_only`, `limit` query로 pilot sample 검토 범위를 좁힌다.
  - 목록 응답은 artifact 원문 전체가 아니라 reviewer, score, validation 상태, workflow reference 같은 운영 metadata를 반환한다.
- `GET /report-workflows/learning/correction-artifacts/export`
  - `ready_for_learning=true` artifact를 JSONL로 다운로드한다.
  - export는 사람이 검토할 수 있는 local artifact 생성까지만 수행하며, provider fine-tune API, dataset upload, training execution은 호출하지 않는다.
  - 다운로드한 JSONL은 아래 validator로 다시 검사한다.

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py \
  report_quality_correction_artifacts.jsonl \
  --require-ready \
  --min-records 3
```

운영 API에서 summary 조회, ready JSONL 다운로드, local validation까지 한 번에 확인할 때는:

```bash
SMOKE_BASE_URL=https://admin.decisiondoc.kr \
SMOKE_API_KEY=<runtime-api-key> \
python3 scripts/check_report_quality_artifacts.py \
  --min-records 3 \
  --output tmp/report_quality_correction_artifacts.jsonl
```

이 helper도 local review artifact를 다운로드하고 검증할 뿐이며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.

다운로드한 JSONL을 파일럿 batch evidence로 남길 때는:

```bash
python3 scripts/summarize_report_quality_artifacts.py \
  tmp/report_quality_correction_artifacts.jsonl \
  --batch-id pilot-rqc-001 \
  --min-records 3 \
  --output reports/report-quality/pilot-rqc-001-manifest.json \
  --markdown reports/report-quality/pilot-rqc-001-summary.md
```

manifest는 reviewer, document type, score distribution, blocker, no-training boundary를 요약한다.

## Operating Rule

학습 후보는 아래 조건을 모두 만족해야 한다.

1. `learning_opt_in=true`인 workflow에서 생성되었다.
2. 사람이 교정 전/후 차이와 수정 이유를 기록했다.
3. `forbidden_terms_scan=pass`이고 `privacy_security_scan=pass`이다.
4. 논리, 근거, 공공/제안서 톤, 장표 구조, export readiness가 최소 기준을 넘었다.
5. 원본 첨부파일, base64, raw file bytes, secret 값이 artifact에 포함되지 않았다.
6. 별도 승인 전에는 training execution, provider fine-tune API, dataset upload, model promotion이 모두 `false`다.

## Recommended Next Step

파일럿 샘플 3~5개를 먼저 만든다.

각 샘플은 다음 흐름을 따른다.

1. 파일럿 리뷰팩을 생성한다.
   ```bash
   python3 scripts/create_report_quality_pilot_pack.py \
     --batch-id pilot-rqc-001 \
     --sample-count 3 \
     --output-root reports/report-quality
   ```
2. Report Workflow에서 `learning_opt_in=true`로 내부 테스트 프로젝트를 생성한다.
3. AI가 기획안과 장표 초안을 생성한다.
4. 사람이 결과를 고쳐서 “좋은 버전”을 만든다.
5. 수정 요청, 수정 이유, 최종본, 점수를 리뷰팩의 draft artifact에 기록한다.
6. 승인 전에는 `accepted_for_learning=false`를 유지하고, 사람이 검수 완료한 뒤에만 `accepted_for_learning=true`, `human_review_status=accepted`, scan 결과 `pass`로 바꾼다.
7. `validate_correction_artifact.py`로 shape, 품질 gate, placeholder 제거, no-training boundary를 검증한다.
   - 단일 artifact는 `.json`으로 검증한다.
   - UI/API export 결과는 `.jsonl`로 검증하고, 학습 후보 batch로 볼 때는 `--require-ready`를 붙인다.
8. `scripts/check_report_quality_artifacts.py`로 운영 API 기준 ready count와 export JSONL을 한 번 더 검증한다.
9. `scripts/summarize_report_quality_artifacts.py`로 batch manifest와 markdown summary를 만든다.
10. 최소 30~50개까지 쌓인 뒤에만 small SFT experiment로 넘어간다.

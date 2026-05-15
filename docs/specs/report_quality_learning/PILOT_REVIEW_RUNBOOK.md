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

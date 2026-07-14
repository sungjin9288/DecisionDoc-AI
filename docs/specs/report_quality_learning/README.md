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

## Explicit Human Review Gate

- UI는 overall/dimension score와 rationale에 통과값을 미리 채우지 않는다.
- Reviewer가 score와 dimension 평가 근거를 직접 입력해야 한다.
- `accepted_for_learning=true`인 artifact는 모든 required dimension의 rationale가 비어 있지 않아야 한다.
- Preview와 save는 같은 server validator를 사용하며, 미입력 score/rationale는 blocker로 반환한다.
- Preview 응답은 artifact 전체의 SHA-256 `preview_fingerprint`를 반환한다. Save는 이 값을 현재 workflow snapshot과 correction input으로 다시 만든 artifact와 대조하며, 누락·입력 변경·중복 artifact 저장을 거부한다.
- `preview_fingerprint`는 검토한 내용과 저장 내용의 동일성을 확인하는 값이다. 사용자 인증이나 전자서명을 대체하지 않는다.
- 이 gate는 correction artifact 품질만 검증하며 provider API, dataset upload, training execution, model promotion을 실행하지 않는다.

## Artifacts

- [QUALITY_RUBRIC.md](./QUALITY_RUBRIC.md)
- [PILOT_REVIEW_RUNBOOK.md](./PILOT_REVIEW_RUNBOOK.md)
- [REVIEW_PACKET_EVIDENCE_RUNBOOK.md](./REVIEW_PACKET_EVIDENCE_RUNBOOK.md)
- [review_packet_evidence_checklist.json](./review_packet_evidence_checklist.json)
- [review_packet_signoff_template.json](./review_packet_signoff_template.json)
- [training_discussion_decision_template.json](./training_discussion_decision_template.json)
- [training_experiment_plan_review_template.json](./training_experiment_plan_review_template.json)
- [training_final_approval_packet_review_template.json](./training_final_approval_packet_review_template.json)
- [training_final_approval_record_template.json](./training_final_approval_record_template.json)
- [correction_artifact_template.json](./correction_artifact_template.json)
- [validate_correction_artifact.py](./validate_correction_artifact.py)

## Local Pipeline

| 단계 | 주요 도구 | 보장하는 것 |
|------|-----------|-------------|
| Packet 검증 | `validate_review_packet.py`, `build_report_quality_review_packet_evidence.py`, `validate_report_quality_review_packet_evidence.py` | UI packet과 embedded artifact, batch membership, source hash, ready gate가 일치한다. |
| Reviewer handoff | `create_report_quality_review_packet_handoff.py`, `create_report_quality_review_packet_signoff.py`, `summarize_report_quality_review_packet_signoffs.py` | 검토 대상과 사람의 sign-off가 같은 evidence manifest에 결속된다. |
| Training discussion | `create_report_quality_review_packet_training_readiness.py`, discussion handoff/decision creator와 validator | 학습 논의를 시작할 자료가 준비됐는지만 기록하며 실행 권한은 부여하지 않는다. |
| Experiment planning | experiment plan draft/review creator와 validator | Dataset, eval, parameter 후보와 검토 결과를 planning-only artifact로 남긴다. |
| Final approval preparation | final approval packet/review/record template creator와 validator | Required approver, source hash, 미승인 상태, `not_started` execution step을 검증한다. |
| Pilot review | `create_report_quality_pilot_pack.py`, `create_report_quality_review_sheet.py`, `apply_report_quality_review_decisions.py`, receipt validator | UI export부터 사람의 교정 결정과 최종 draft까지 source-bound history를 보존한다. |
| Local verification | `run_report_quality_learning_demo.py`, `sync_report_quality_pilot_pack.py`, artifact checker와 summarizer | Mock/local 경로와 운영 API export를 같은 artifact validator로 재검증한다. |

세부 명령과 예상 출력은 [Pilot Review Runbook](./PILOT_REVIEW_RUNBOOK.md)과 [Review Packet Evidence Runbook](./REVIEW_PACKET_EVIDENCE_RUNBOOK.md)에만 둔다. 이 README는 흐름과 권한 경계를 설명하는 진입점이다.

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
  - `ready_only`, `offset`, `limit` query로 pilot sample 검토 범위와 페이지를 고른다. 응답의 `filtered_total`, `returned`, `has_more`로 다음 페이지를 판단한다.
  - 목록 응답은 artifact 원문 전체가 아니라 reviewer, score, validation 상태, workflow reference 같은 운영 metadata를 반환한다.
  - Report Workflow UI는 전체/ready 모드와 5개 단위 페이지를 제공한다. 같은 tenant 안에서는 페이지 이동 중에도 최대 5개 pilot 선택을 유지하고, tenant가 바뀌면 선택을 비운다.
- `GET /report-workflows/learning/correction-artifacts/{artifact_id}`
  - 현재 tenant 안에서 한 건의 저장 artifact를 조회한다. content `artifact_id`와 저장 wrapper ID를 모두 지원하며 다른 tenant의 record는 검색하지 않는다.
  - 응답은 metadata-only artifact, 저장 당시 validation, preview fingerprint, 외부 upload/provider/training 차단 경계를 함께 반환한다.
  - Report Workflow UI의 최근 artifact 카드에서 상세 metadata를 검토하거나 이 read-only envelope를 개별 JSON으로 내려받을 수 있다.
- `POST /report-workflows/learning/correction-artifacts/pilot-export/preview`
  - 선택한 ready artifact 3~5개의 순서, readiness, exact JSONL SHA-256, 외부 학습 비승인 경계를 저장 없이 반환한다.
- `POST /report-workflows/learning/correction-artifacts/pilot-export`
  - 현재 화면의 ready artifact 중 서로 다른 3~5개를 사람이 선택해 ordered JSONL 파일럿 묶음으로 내려받는다.
  - 서버는 tenant 범위, 최소·최대 개수, 입력 ID 중복, content/store alias 중복, artifact 존재 여부, `ready_for_learning=true`를 다시 검증한다.
  - Preview 응답의 `export_sha256`을 `preview_sha256`으로 제출해야 하며, 현재 JSONL과 다르면 `400`으로 차단한다. 성공 응답은 `X-DecisionDoc-Pilot-Preview-Verified: true`를 포함한다.
  - 성공 응답은 JSONL과 함께 server-issued receipt를 내려준다. Receipt는 request ID, tenant, ordered artifact IDs, JSONL SHA-256, preview 검증 결과, 외부 실행 비승인 경계를 보존한다.
  - Preview와 export audit은 각 요청의 request ID, 같은 SHA-256과 artifact count, 해당 server verification state를 tenant audit log에 남긴다. Export audit의 request ID는 receipt와 일치한다.
  - Admin Ops audit 화면에서 preview, export, package action을 직접 필터링하고 request ID, 전체 SHA-256, artifact count, preview verification state를 확인할 수 있다. 전체 건수와 현재 범위를 표시하며 이전·다음 페이지에서도 같은 filter를 유지한다.
  - Audit 조회와 CSV는 같은 action/result/기간 filter를 사용한다. Date-only 종료일은 해당 UTC 날짜 전체를 포함하고, pilot 식별자는 CSV의 별도 column과 전체 detail JSON에 함께 보존되며 1,000건을 넘는 결과도 포함한다.
  - 선택 export는 local review 파일만 만들며 provider API, dataset upload, training execution, model promotion을 실행하거나 승인하지 않는다.
  - 내려받은 `report_quality_pilot_artifacts_<sha12>.jsonl`은 다음 명령으로 source-bound local review pack에 연결한다. 전체 hash는 `X-DecisionDoc-Pilot-SHA256` 응답 헤더와 `SOURCE_MANIFEST.json`에서 대조한다.
- `POST /report-workflows/learning/correction-artifacts/pilot-export/package`
  - 같은 `artifact_ids`와 `preview_sha256` precondition으로 JSONL, server receipt, `pilot_package_manifest.json`을 하나의 ZIP으로 내려받는다.
  - Manifest는 exact membership, entry별 size/SHA-256, tenant, ordered artifact IDs, request ID, 외부 실행 비승인 경계를 보존한다.
  - 서버는 응답 전에 ZIP을 다시 검증하고 `X-DecisionDoc-Pilot-Package-SHA256`을 반환한다. Browser는 저장 전에 ZIP bytes의 SHA-256을 이 header와 대조한다.
  - `create_report_quality_pilot_pack.py --source-package`는 ZIP을 풀지 않고 같은 package validator를 다시 실행한 뒤 embedded JSONL과 receipt를 기존 source-bound import 흐름에 연결한다. Embedded package manifest 원문도 pack-local `SOURCE_PACKAGE_MANIFEST.json`으로 보존한다.
  - Package audit은 `report_quality.pilot_package`로 분리되며 JSONL SHA-256, artifact count, preview verification state를 남긴다.
  - ZIP은 paired handoff를 위한 container일 뿐 dataset upload, provider fine-tune, training execution, model promotion을 실행하거나 승인하지 않는다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --source-package ~/Downloads/report_quality_pilot_review_package_<sha12>.zip \
  --output-root reports/report-quality
```

생성된 `SOURCE_MANIFEST.json` v3는 원본 package, embedded JSONL, copied receipt, preserved package manifest의 SHA-256과 size, request ID, tenant, artifact 순서를 남긴다. `sync_report_quality_pilot_pack.py`는 원본 ZIP이 없어도 `SOURCE_PACKAGE_MANIFEST.json`의 hash와 entry metadata, tenant, request ID, artifact 순서, no-training boundary를 독립 재검증한다. 같은 batch ID의 기존 출력이 있으면 import를 거부하며 기존 v1/v2 source manifest와 JSONL+receipt 개별 입력도 호환 경로로 유지한다.

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

로컬 API 전체 흐름을 mock provider로 재현하고 단일 ready artifact receipt를 남길 때는:

```bash
python3 scripts/run_report_quality_learning_demo.py \
  --output /tmp/decisiondoc-report-quality-learning-demo.json
```

이 데모는 임시 local storage에서 workflow 생성부터 최종 승인, correction preview·저장·목록·JSONL export validation까지 실행한 뒤 임시 데이터를 삭제한다. receipt는 provider API와 학습 관련 외부 action이 모두 실행되지 않았음을 함께 기록한다.

운영 API에서 summary 조회, ready JSONL 다운로드, local validation까지 한 번에 확인할 때는:

```bash
SMOKE_BASE_URL=https://admin.decisiondoc.kr \
SMOKE_API_KEY=<runtime-api-key> \
python3 scripts/check_report_quality_artifacts.py \
  --min-records 3 \
  --output tmp/report_quality_correction_artifacts.jsonl
```

이 helper는 summary/export count·tenant 일치, artifact ID uniqueness, single-tenant batch, ready gate를 모두 확인한 뒤에만 local JSONL을 쓴다. 실패 시 새 파일을 만들거나 기존 output을 덮어쓰지 않는다. Provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.

다운로드한 JSONL을 파일럿 batch evidence로 남길 때는:

```bash
python3 scripts/summarize_report_quality_artifacts.py \
  tmp/report_quality_correction_artifacts.jsonl \
  --batch-id pilot-rqc-001 \
  --min-records 3 \
  --output reports/report-quality/pilot-rqc-001-manifest.json \
  --markdown reports/report-quality/pilot-rqc-001-summary.md
```

manifest는 reviewer, document type, score distribution, unique artifact 수, tenant 수, blocker, no-training boundary를 요약한다. Duplicate artifact와 mixed-tenant batch는 follow-up blocker로 남고 readiness를 통과하지 못한다. Source는 symlink가 아닌 `.jsonl`만 허용하며, downstream evidence validator가 실제 JSONL identity를 독립 재계산한다.

## Operating Rule

학습 후보는 아래 조건을 모두 만족해야 한다.

1. `learning_opt_in=true`인 workflow에서 생성되었다.
2. 사람이 교정 전/후 차이와 수정 이유를 기록했다.
3. `forbidden_terms_scan=pass`이고 `privacy_security_scan=pass`이다.
4. 논리, 근거, 공공/제안서 톤, 장표 구조, export readiness가 최소 기준을 넘었다.
5. 원본 첨부파일, base64, raw file bytes, secret 값이 artifact에 포함되지 않았다.
6. 별도 승인 전에는 training execution, provider fine-tune API, dataset upload, model promotion이 모두 `false`다.

## Recommended Next Step

파일럿 샘플 3~5개를 실제 Report Workflow에서 만들고 로컬 검수 경로로 가져온다.

각 샘플은 다음 흐름을 따른다.

1. Report Workflow에서 `learning_opt_in=true`로 내부 테스트 프로젝트를 생성한다.
2. AI가 기획안과 장표 초안을 생성한다.
3. 사람이 결과, 수정 이유, 점수, scan 결과를 검토하고 ready correction artifact로 저장한다.
4. UI에서 서로 다른 ready artifact 3~5개를 선택해 `report_quality_pilot_review_package_<sha12>.zip`을 내려받는다. 기존 JSONL + receipt 개별 다운로드도 호환 경로로 유지한다.
   - 실제 파일명에는 응답 본문 SHA-256 앞 12자가 붙고, 전체 hash는 `X-DecisionDoc-Pilot-SHA256` 응답 헤더로도 제공된다.
5. export를 source-bound 파일럿 review pack으로 가져온다.
   ```bash
   python3 scripts/create_report_quality_pilot_pack.py \
     --batch-id pilot-rqc-001 \
     --source-package ~/Downloads/report_quality_pilot_review_package_<sha12>.zip \
     --output-root reports/report-quality
   ```
6. `SOURCE_MANIFEST.json` v3, copied `SOURCE_EXPORT_RECEIPT.json`, preserved `SOURCE_PACKAGE_MANIFEST.json`이 원본 package 및 embedded JSONL SHA-256, size, request ID, tenant, artifact 순서를 함께 보존하는지 확인한다.
7. Import와 함께 자동 생성된 worksheet로 교정 내용과 승인 필드를 확인한다. Source import pack에서는 `human_review_manifest.json`의 source/draft SHA-256 binding도 함께 확인한다. Draft를 직접 수정한 뒤에는 아래 명령으로 worksheet를 refresh한다.
   ```bash
   python3 scripts/create_report_quality_review_sheet.py \
     reports/report-quality/pilot-rqc-001
   ```
8. 변경이 필요하면 현재 pack에 결속된 decision template을 만들고 `changes_requested` 또는 `rejected`를 기록한다.
   ```bash
   python3 scripts/apply_report_quality_review_decisions.py \
     reports/report-quality/pilot-rqc-001 \
     --create-template reports/report-quality/pilot-rqc-001/review_decisions.json
   ```
9. decision JSON을 작성했다면 draft artifact에 반영한다. Template 생성 뒤 source manifest나 draft가 바뀌었다면 새 template을 만들고 다시 검토한다.
   ```bash
   python3 scripts/apply_report_quality_review_decisions.py \
     reports/report-quality/pilot-rqc-001 \
     --decisions reports/report-quality/pilot-rqc-001/review_decisions.json \
     --require-ready \
     --receipt reports/report-quality/pilot-rqc-001/review_decision_application_receipt.json
   ```
10. 적용 receipt를 현재 pack과 다시 대조한다.
    ```bash
    python3 scripts/validate_report_quality_review_decision_receipt.py \
      reports/report-quality/pilot-rqc-001/review_decision_application_receipt.json
    ```
11. `sync_report_quality_pilot_pack.py --require-ready`와 `validate_correction_artifact.py`로 source 순서, shape, 품질 gate, placeholder 제거, no-training boundary를 검증한다.
   - 단일 artifact는 `.json`으로 검증한다.
   - UI/API export 결과는 `.jsonl`로 검증하고, 학습 후보 batch로 볼 때는 `--require-ready`를 붙인다.
    - UI의 `Review packet JSON` 결과는 서버 저장 전 evidence packet이므로 아래처럼 별도 validator를 사용한다.
      ```bash
      python3 docs/specs/report_quality_learning/validate_review_packet.py \
        report-quality-review-packet-<workflow_id>.json \
        --require-ready
      ```
    - 여러 packet을 묶어 사람이 검토할 batch evidence로 남길 때는:
      ```bash
      python3 scripts/summarize_report_quality_review_packets.py \
        downloads/report-quality-review-packet-*.json \
        --batch-id pilot-rqp-001 \
        --min-packets 3 \
        --require-ready \
        --output reports/report-quality/pilot-rqp-001-review-packet-manifest.json \
        --markdown reports/report-quality/pilot-rqp-001-review-packet-summary.md
      ```
    - packet에서 correction artifact JSONL을 추출해 기존 artifact 검증 흐름으로 넘길 때는:
      ```bash
      python3 scripts/export_report_quality_artifacts_from_review_packets.py \
        downloads/report-quality-review-packet-*.json \
        --batch-id pilot-rqp-001 \
        --min-packets 3 \
        --output reports/report-quality/pilot-rqp-001-from-review-packets.jsonl \
        --manifest reports/report-quality/pilot-rqp-001-from-review-packets-manifest.json

      python3 docs/specs/report_quality_learning/validate_correction_artifact.py \
        reports/report-quality/pilot-rqp-001-from-review-packets.jsonl \
        --require-ready \
        --min-records 3
      ```
    - Packet evidence 이후의 reviewer handoff, discussion, experiment plan, final approval 준비 명령은 [Review Packet Evidence Runbook](./REVIEW_PACKET_EVIDENCE_RUNBOOK.md)을 따른다. 이 local chain은 pending final approval record template에서 끝나며 provider job, dataset upload, training execution, model promotion은 계속 미승인 상태다.
11. 사람이 수정한 draft JSON을 batch JSONL로 동기화한다.
   ```bash
   python3 scripts/sync_report_quality_pilot_pack.py \
     reports/report-quality/pilot-rqc-001 \
     --min-records 3 \
     --require-ready
   ```
   - `output_written=true`와 `output_sha256`이 함께 반환된 실행만 현재 draft가 반영된 sync 성공으로 본다. 실패 실행은 기존 output을 변경하지 않는다.
12. `scripts/check_report_quality_artifacts.py`로 운영 API 기준 ready count, summary/export count·tenant 일치, unique artifact ID와 export JSONL을 한 번 더 검증한다. 성공 결과의 `output_written=true`와 `output_sha256`을 확인한다.
13. `scripts/summarize_report_quality_artifacts.py`로 batch manifest와 markdown summary를 만든다. `duplicate_artifact_ids`와 `mixed_tenants_present` blocker가 없어야 한다.
14. 최소 30~50개까지 쌓인 뒤에만 small SFT experiment로 넘어간다.

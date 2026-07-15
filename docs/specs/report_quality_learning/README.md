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
| Pilot review | `create_report_quality_pilot_pack.py`, review sheet/workspace creator, `apply_report_quality_review_decisions.py`, receipt validator | UI export부터 browser draft, 사람의 교정 결정, 최종 draft까지 source-bound history를 보존한다. |
| Local verification | `run_report_quality_learning_demo.py`, `run_report_quality_pilot_handoff_demo.py`, `sync_report_quality_pilot_pack.py`, artifact checker와 summarizer | Mock/local 경로와 운영 API export를 같은 artifact validator로 재검증하고 3-artifact handoff wiring을 simulated review receipt로 확인한다. |

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
- `POST /report-workflows/learning/correction-artifacts/pilot-package/verify`
  - 수신한 ZIP을 `multipart/form-data`의 `file`로 올리면 서버가 파일을 저장하지 않고 기존 package verifier를 메모리에서 실행한다.
  - Active tenant, exact membership, entry별 size/SHA-256, JSONL artifact 순서, receipt binding, artifact별 외부 실행 비승인 경계와 correction artifact 전체 semantic/learning-ready 조건을 다시 확인한다.
  - 응답의 `package_sha256`은 브라우저가 업로드 전에 계산한 SHA-256과 대조한다. 검증된 artifact는 reviewer·score·scan·교정 전후 기획·claim count·change request와 함께 표시되며 `operator_summary`와 `next_review_action`이 이 결과가 검토 증거이고 별도 사람 결정이 필요함을 설명한다.
  - `persisted=false`는 검증 과정이 package나 workflow record를 저장하지 않았음을 나타낸다. 5 MB 초과, 변조, not-ready artifact, 다른 tenant package는 각각 차단한다.
  - 성공·실패는 `report_quality.pilot_package_verify`, cross-tenant 접근은 공통 `access.blocked` audit 정책으로 기록한다. Audit detail의 `pilot_artifact_semantics_verified`가 receiver semantic gate 통과 여부를 보존한다.

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
   - 수신 UI에서 같은 ZIP을 검증하면 package SHA-256 기반 batch ID와 현재 파일명을 반영한 importer 명령을 바로 복사할 수 있다. 명령은 `~/Downloads`를 가정하므로 다른 위치에서 선택한 파일은 `--source-package` 경로만 바꾼다. 같은 batch ID가 이미 있으면 importer의 write-once 경계를 우회하지 말고 새 ID를 사용한다.
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
8. Import와 함께 자동 생성된 `HUMAN_REVIEW_WORKSPACE.html`에서 교정 전후 planning·slide·claim evidence, validation 상태와 required action을 확인한다. 이어서 `accepted`, `changes_requested`, `rejected` 중 사람의 결정과 점수·scan·근거를 입력하고 `review_decisions.browser-draft.json`을 내려받는다. Workspace는 현재 pack 절대경로와 기본 Downloads 파일명에 결속된 dry-run/apply 명령을 함께 보여주고 복사한다. 명령은 현재 입력으로 draft를 성공적으로 다운로드해야 활성화되며, 이후 입력이 바뀌면 다시 다운로드할 때까지 잠긴다. 마지막으로 내려받은 draft의 모든 결정이 `accepted`일 때만 `--require-ready`를 포함하며, 보완·반려·대기 결정은 일반 apply로 기록해 downstream-ready receipt와 구분한다. `--require-ready`는 CLI가 source artifact readiness를 확인하라는 요구이며 화면이 미리 통과를 주장하지 않는다. 원래 상태는 `previous_decision`에 남고 새 파일럿 판단은 `pending`에서 시작한다. Browser draft는 `review_decisions.json`의 source/draft binding과 `training_authorized=false`를 보존하며 pack 파일을 직접 수정하거나 외부 요청을 보내지 않는다. 기존 pack에 template 또는 workspace가 없다면 각 creator로 한 번만 추가한다. Decision template은 write-once publication으로 생성하며 기존 파일과 symlink는 덮어쓰지 않는다.
9. 내려받은 decision JSON을 외부 경로에서 검증한 뒤 SHA-256에 결속된 pack-local 보관본과 application receipt를 자동 생성하고 draft artifact에 반영한다. SHA 보관본은 write-once publication으로 먼저 고정되며 동시 경로 충돌이 생기면 기존 파일을 보존하고 draft를 반영하지 않는다. 성공한 apply는 `HUMAN_REVIEW_WORKSHEET.md`와 `human_review_manifest.json`도 현재 draft hash와 검토 상태로 갱신한다. Template 생성 뒤 source manifest나 draft가 바뀌었다면 기존 파일을 보존하고 새 이름으로 template과 workspace를 만든 뒤 다시 검토한다. 쓰기 전 확인만 필요하면 `--dry-run`을 붙이고, 모든 artifact가 learning-ready여야 하는 검토에서만 `--require-ready`를 사용한다. Dry-run, invalid batch, symlink evidence target에서는 기존 draft와 파생 검수 증거를 변경하지 않는다.
   ```bash
   python3 scripts/apply_report_quality_review_decisions.py \
     reports/report-quality/pilot-rqc-001 \
     --browser-draft ~/Downloads/review_decisions.browser-draft.json \
     --require-ready
   ```
10. CLI가 출력한 SHA 기반 receipt와 갱신된 worksheet/manifest 경로를 확인하고 receipt를 현재 pack과 다시 대조한다.
    ```bash
    python3 scripts/validate_report_quality_review_decision_receipt.py \
      reports/report-quality/pilot-rqc-001/review_decision_application_receipt.<sha12>.json
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
11. Standalone JSONL이 필요한 분석이나 후속 처리에서만 사람이 수정한 draft JSON을 동기화한다. Handoff만 필요하면 이 단계를 건너뛰고 12단계 `finalize`를 실행한다.
   ```bash
   python3 scripts/sync_report_quality_pilot_pack.py \
     reports/report-quality/pilot-rqc-001 \
     --min-records 3 \
     --require-ready
   ```
   - `--require-ready`는 모든 artifact가 ready인지만 보지 않는다. 현재 pack binding과 artifact 상태·count가 일치하는 `human_review_manifest.json`, `require_ready=true`로 기록된 accepted decision application receipt가 모두 있어야 한다. Source import 당시 artifact가 이미 ready여도 새 로컬 decision이 pending이면 차단한다.
   - `output_written=true`, `output_sha256`, `review_manifest.sha256`, `decision_receipt.sha256`이 함께 반환된 실행만 현재 draft와 검수 이력이 결속된 sync 성공으로 본다. 쓰기 직전 binding과 evidence hash를 다시 확인하며 실패 실행은 기존 output을 변경하지 않는다.
12. 검수 완료 pack을 ready sync한 뒤 portable handoff ZIP으로 묶고, 원래 pack 없이 다시 검증한다.
   ```bash
   python3 scripts/manage_report_quality_pilot_handoff.py finalize \
     reports/report-quality/pilot-rqc-001

   python3 scripts/manage_report_quality_pilot_handoff.py verify \
     reports/report-quality/pilot-rqc-001/report_quality_pilot_review_handoff_<sha12>.zip \
     --browser-summary-output reports/report-quality/pilot-rqc-001-handoff-summary.html
   ```
   - Finalize는 private temporary directory에서 `--require-ready` sync를 통과한 exact JSONL을 만들고 current manifest, accepted decision receipt와 decision file, 최종 draft, source provenance sidecar와 함께 embedded `handoff_manifest.json`에 결속한다. 임시 JSONL은 package 발행 뒤 삭제하며 standalone JSONL이 필요한 경우에만 기존 `sync`와 `create --jsonl`을 사용한다.
   - Handoff v2는 원문 전달용 `HANDOFF_SUMMARY.md`와 별도 runtime 없이 브라우저에서 여는 script-free `HANDOFF_SUMMARY.html`을 함께 담는다. 두 파일 모두 artifact별 reviewer, reviewed time, score, decision state와 evidence hash, no-training boundary를 보여준다.
   - Verifier는 Markdown과 HTML을 같은 evidence에서 다시 생성해 exact bytes를 대조하고 artifact readiness, JSONL/draft identity, accepted review 전이, source binding, entry hash/size, no-training boundary를 archive만으로 재검증한다. 기존 v1 archive는 Markdown 계약으로 계속 검증한다. `--browser-summary-output` 또는 `--summary-output` 중 하나를 선택하면 검증을 통과한 exact HTML 또는 Markdown만 별도 파일로 write-once 발행한다. 두 옵션은 동시에 사용할 수 없고 기존 파일·symlink·잘못된 확장자를 거부한다.
   - 실제 사람 검수 자료 없이 3-artifact 전체 wiring을 확인할 때는 `python3 scripts/run_report_quality_pilot_handoff_demo.py --output /tmp/decisiondoc-report-quality-pilot-handoff-demo.json`을 실행한다. 이어서 `python3 scripts/check_report_quality_pilot_handoff_demo_receipt.py /tmp/decisiondoc-report-quality-pilot-handoff-demo.json --json`으로 receipt contract와 simulated/no-training/secret boundary를 read-only로 다시 확인한다. 이 mock-only receipt는 `review_evidence=simulated_demo_input`, `human_review_claimed=false`, 외부 action 전부 `false`를 기록하므로 실제 사람 검수나 live provider 품질 증거로 사용하지 않는다. Checker는 삭제된 temporary artifact 자체를 다시 검증하지 않는다.
13. `scripts/check_report_quality_artifacts.py`로 운영 API 기준 ready count, summary/export count·tenant 일치, unique artifact ID와 export JSONL을 한 번 더 검증한다. 성공 결과의 `output_written=true`와 `output_sha256`을 확인한다.
14. `scripts/summarize_report_quality_artifacts.py`로 batch manifest와 markdown summary를 만든다. `duplicate_artifact_ids`와 `mixed_tenants_present` blocker가 없어야 한다.
15. 최소 30~50개까지 쌓인 뒤에만 small SFT experiment로 넘어간다.

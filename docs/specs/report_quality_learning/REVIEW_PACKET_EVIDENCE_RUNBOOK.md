# Review Packet Evidence Runbook

이 runbook은 Report Workflow UI에서 내려받은 `Review packet JSON` 파일을 로컬 evidence bundle로 검증하는 절차다.

목표는 운영 전 품질 개선 샘플을 사람이 검토할 수 있게 정리하는 것이다. 이 절차는 server artifact 저장, dataset upload, provider fine-tune API 호출, training execution, model promotion을 실행하지 않는다.

## Inputs

필수 입력:

- Report Workflow UI에서 생성한 `report-quality-review-packet-*.json`
- 각 packet은 `Review packet JSON` 버튼으로 생성된 client-side 파일이어야 한다.
- 각 packet은 서버 preview 결과의 `preview_artifact`를 포함해야 한다.

권장 위치:

```bash
mkdir -p reports/report-quality/downloads/pilot-rqp-001
```

UI에서 받은 packet 파일을 위 디렉터리에 둔다.

## Step 1. 단일 Packet 검증

먼저 각 packet이 ready gate를 통과하는지 확인한다.

```bash
python3 docs/specs/report_quality_learning/validate_review_packet.py \
  reports/report-quality/downloads/pilot-rqp-001/report-quality-review-packet-<workflow_id>.json \
  --require-ready
```

expected output:

```text
PASS report quality review packet validated
ready_for_learning=true
preview_artifact_ready_for_learning=true
```

실패하면 Report Workflow UI에서 아래 항목을 다시 확인한다.

- workflow status가 `final_approved`인지
- `learning_opt_in=true`인지
- reviewer, reviewed_at, score, scan 결과가 채워졌는지
- checklist item이 모두 pass인지
- server preview 결과가 `ready_for_learning=true`인지
- no-training boundary 값이 모두 `false`인지

## Step 2. Evidence Pipeline 생성

ready packet 여러 개를 하나의 로컬 evidence bundle로 묶는다.

```bash
python3 scripts/build_report_quality_review_packet_evidence.py \
  reports/report-quality/downloads/pilot-rqp-001/*.json \
  --batch-id pilot-rqp-001 \
  --min-packets 3 \
  --output-root reports/report-quality
```

생성물:

- `reports/report-quality/pilot-rqp-001-review-packet-manifest.json`
- `reports/report-quality/pilot-rqp-001-review-packet-summary.md`
- `reports/report-quality/pilot-rqp-001-from-review-packets.jsonl`
- `reports/report-quality/pilot-rqp-001-artifact-export-manifest.json`
- `reports/report-quality/pilot-rqp-001-artifact-batch-manifest.json`
- `reports/report-quality/pilot-rqp-001-artifact-batch-summary.md`
- `reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json`

expected output:

```text
Report quality review packet evidence pipeline: PASS
training_boundary=not_authorized
```

## Step 3. Pipeline Evidence 검증

생성된 manifest가 참조하는 파일, JSONL hash, stage readiness, count consistency, no-side-effect boundary를 다시 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_evidence.py \
  reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json
```

expected output:

```text
PASS report quality review packet evidence validated
output_count=7
require_ready=true
```

## Step 4. Correction Artifact JSONL 재검증

packet에서 추출한 correction artifact JSONL을 기존 artifact validator로 다시 확인한다.

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py \
  reports/report-quality/pilot-rqp-001-from-review-packets.jsonl \
  --require-ready \
  --min-records 3
```

expected output:

```text
PASS report quality correction artifact JSONL validated
ready_for_learning=true
ready_artifacts=3
not_ready_artifacts=0
```

## Step 5. Human Review Handoff

검토자용 handoff index와 manifest를 생성한다.

```bash
python3 scripts/create_report_quality_review_packet_handoff.py \
  reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json
```

expected output:

```text
Report quality review packet handoff: PASS
training_boundary=not_authorized
```

생성된 handoff도 다시 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_handoff.py \
  reports/report-quality/pilot-rqp-001-handoff-manifest.json
```

expected output:

```text
PASS report quality review packet handoff validated
require_ready=true
```

검토자에게 아래 파일을 전달한다.

- `pilot-rqp-001-review-packet-summary.md`
- `pilot-rqp-001-artifact-batch-summary.md`
- `pilot-rqp-001-evidence-pipeline-manifest.json`
- `pilot-rqp-001-handoff-index.md`
- `pilot-rqp-001-handoff-manifest.json`
- `pilot-rqp-001-from-review-packets.jsonl`

검토자는 아래를 확인한다.

- packet count가 계획한 샘플 수와 맞는지
- ready packet 수와 ready artifact 수가 같은지
- reviewer, score, scan 결과가 합리적인지
- blocker가 없는지
- provider/training boundary가 모두 false인지

## Stop Gate

아래 조건 중 하나라도 만족하지 못하면 다음 단계로 넘기지 않는다.

- evidence pipeline validation 실패
- correction artifact JSONL validation 실패
- `ready_artifacts < min_records`
- reviewer 또는 reviewed_at 누락
- `forbidden_terms_scan` 또는 `privacy_security_scan`이 `pass`가 아님
- no-side-effect boundary 중 하나라도 `true`
- training readiness validation 실패

## Step 6. Reviewer Sign-Off Record

handoff 검토가 끝나면 pending sign-off record를 만든 뒤 reviewer decision을 기록한다.

권장 명령:

```bash
python3 scripts/create_report_quality_review_packet_signoff.py \
  reports/report-quality/pilot-rqp-001-handoff-manifest.json
```

expected output:

```text
Report quality review packet pending signoff: PASS
training_boundary=not_authorized
```

수동으로 시작해야 하는 경우에는 `review_packet_signoff_template.json`을 복사한다.

```bash
cp docs/specs/report_quality_learning/review_packet_signoff_template.json \
  reports/report-quality/pilot-rqp-001-signoff.json
```

검토자는 생성된 pending sign-off에서 아래 필드를 확인하거나 채운다.

- `signoff_id`와 `created_at`: generator 사용 시 자동 입력, 수동 복사 시 입력
- `handoff_manifest_path`와 `handoff_manifest_sha256`: generator 사용 시 자동 입력, 수동 복사 시 입력
- `reviewer.name`
- `reviewer.title_or_team`
- `reviewer.reviewed_at`
- `decision`: `accepted`, `changes_requested`, 또는 `rejected`
- `evidence_reviewed`
- `findings`
- `acknowledgements`

완료된 sign-off를 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_signoff.py \
  reports/report-quality/pilot-rqp-001-signoff.json \
  --require-complete
```

expected output:

```text
PASS report quality review packet signoff validated
completed=true
```

이 sign-off는 evidence review 기록일 뿐이며 training execution, dataset upload, provider fine-tune API 호출, model promotion을 승인하지 않는다.

## Step 7. Sign-Off Summary

검증된 sign-off record를 operator handoff용 summary로 묶는다.

```bash
python3 scripts/summarize_report_quality_review_packet_signoffs.py \
  reports/report-quality/pilot-rqp-001-signoff.json \
  --require-complete \
  --output reports/report-quality/pilot-rqp-001-signoff-summary.json \
  --markdown reports/report-quality/pilot-rqp-001-signoff-summary.md
```

expected output:

```text
Report quality review packet signoff summary: PASS
training_boundary=not_authorized
```

이 summary는 local sign-off 파일을 읽고 summary 파일만 쓰며 reviewer approval을 대신 기록하지 않는다.

## Step 8. Training Discussion Readiness

evidence pipeline과 completed sign-off summary를 함께 검증해 학습 논의로 넘길 수 있는지 확인한다.

```bash
python3 scripts/create_report_quality_review_packet_training_readiness.py \
  reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json \
  reports/report-quality/pilot-rqp-001-signoff-summary.json \
  --min-ready-artifacts 3 \
  --output reports/report-quality/pilot-rqp-001-training-readiness-manifest.json \
  --markdown reports/report-quality/pilot-rqp-001-training-readiness.md
```

expected output:

```text
Report quality review packet training readiness: PASS
ready_for_training_discussion=true
training_boundary=not_authorized
```

생성된 readiness manifest를 다시 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_readiness.py \
  reports/report-quality/pilot-rqp-001-training-readiness-manifest.json
```

expected output:

```text
PASS report quality review packet training readiness validated
ready_for_training_discussion=true
```

이 readiness는 학습 실행 승인이 아니라 다음 논의를 위한 local gate다. 별도 승인 전까지 dataset upload, provider fine-tune API 호출, training execution, model promotion은 계속 금지한다.

## Step 9. Training Discussion Handoff

검증된 readiness manifest를 학습 논의용 handoff index와 manifest로 묶는다.

```bash
python3 scripts/create_report_quality_review_packet_training_discussion_handoff.py \
  reports/report-quality/pilot-rqp-001-training-readiness-manifest.json \
  --output-manifest reports/report-quality/pilot-rqp-001-training-discussion-handoff-manifest.json \
  --output-markdown reports/report-quality/pilot-rqp-001-training-discussion-handoff.md
```

expected output:

```text
Report quality training discussion handoff: PASS
ready_for_training_discussion=true
training_boundary=not_authorized
```

이 handoff는 논의를 위한 local file index일 뿐이며 dataset upload, provider fine-tune API 호출, training execution, model promotion을 승인하지 않는다.

## Step 10. Validate Training Discussion Handoff

생성된 training discussion handoff manifest를 다시 검증해 readiness hash, linked file hash, embedded validation, operator action, no-side-effect boundary가 유지되는지 확인한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_discussion_handoff.py \
  reports/report-quality/pilot-rqp-001-training-discussion-handoff-manifest.json
```

expected output:

```text
PASS report quality training discussion handoff validated
ready_for_training_discussion=true
training_boundary=not_authorized
```

이 validator도 local file check만 수행하며 dataset upload, provider fine-tune API 호출, training execution, model promotion을 승인하지 않는다.

## Step 11. Pending Training Discussion Decision

검증된 training discussion handoff에서 사람이 채울 pending discussion decision record를 만든다.

```bash
python3 scripts/create_report_quality_review_packet_training_discussion_decision.py \
  reports/report-quality/pilot-rqp-001-training-discussion-handoff-manifest.json \
  --output reports/report-quality/pilot-rqp-001-training-discussion-decision.json
```

expected output:

```text
Report quality training discussion pending decision: PASS
pending_validation_ok=true
training_boundary=not_authorized
```

이 record는 discussion outcome을 채우기 위한 template이다. `plan_draft_requested`를 선택해도 future experiment plan draft를 요청하는 것일 뿐이며 dataset upload, provider fine-tune API 호출, training execution, model promotion을 승인하지 않는다.

## Step 12. Validate Training Discussion Decision

사람이 discussion decision record를 작성한 뒤 completed gate를 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_discussion_decision.py \
  reports/report-quality/pilot-rqp-001-training-discussion-decision.json \
  --require-complete
```

expected output:

```text
PASS report quality training discussion decision validated
completed=true
training_boundary=not_authorized
```

completed decision도 planning-only evidence다. 별도 승인 전까지 dataset upload, provider fine-tune API 호출, provider job creation, training execution, model promotion은 계속 금지한다.

## Step 13. Training Experiment Plan Draft

completed discussion decision이 `plan_draft_requested`이고 `requested_next_step=draft_training_experiment_plan`일 때만 local experiment plan draft를 만든다.

```bash
python3 scripts/create_report_quality_review_packet_training_experiment_plan_draft.py \
  reports/report-quality/pilot-rqp-001-training-discussion-decision.json \
  --output-manifest reports/report-quality/pilot-rqp-001-training-experiment-plan-draft-manifest.json \
  --output-markdown reports/report-quality/pilot-rqp-001-training-experiment-plan-draft.md
```

expected output:

```text
Report quality training experiment plan draft: PASS
planning_only=true
training_boundary=not_authorized
```

이 plan draft는 provider, base model, dataset reference, offline eval suite, parameter placeholder, execution step을 논의용으로 정리한다. 모든 execution step은 `not_started`이며 dataset upload, provider fine-tune API 호출, provider job creation, training execution, model promotion을 승인하지 않는다.

## Step 14. Validate Training Experiment Plan Draft

생성된 plan draft manifest를 다시 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_experiment_plan_draft.py \
  reports/report-quality/pilot-rqp-001-training-experiment-plan-draft-manifest.json
```

expected output:

```text
PASS report quality training experiment plan draft validated
planning_only=true
training_boundary=not_authorized
```

이 validator는 linked decision/handoff/file hash, eval suite, execution step `not_started` 상태, no-side-effect boundary를 확인할 뿐이며 학습 실행을 시작하지 않는다.

## Step 15. Pending Training Experiment Plan Review

검증된 plan draft에서 사람이 채울 pending plan review record를 만든다.

```bash
python3 scripts/create_report_quality_review_packet_training_experiment_plan_review.py \
  reports/report-quality/pilot-rqp-001-training-experiment-plan-draft-manifest.json \
  --output reports/report-quality/pilot-rqp-001-training-experiment-plan-review.json
```

expected output:

```text
Report quality training experiment plan pending review: PASS
pending_validation_ok=true
training_boundary=not_authorized
```

이 review record는 plan draft가 별도 final approval packet 준비 단계로 넘어갈 수 있는지 사람이 판단하기 위한 template이다. `planning_complete`도 final approval packet 준비 요청일 뿐이며 dataset upload, provider fine-tune API 호출, provider job creation, training execution, model promotion을 승인하지 않는다.

## Step 16. Validate Training Experiment Plan Review

사람이 plan review record를 작성한 뒤 completed gate를 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_experiment_plan_review.py \
  reports/report-quality/pilot-rqp-001-training-experiment-plan-review.json \
  --require-complete
```

expected output:

```text
PASS report quality training experiment plan review validated
completed=true
training_boundary=not_authorized
```

completed review도 planning handoff evidence다. 별도 최종 승인 전까지 dataset upload, provider fine-tune API 호출, provider job creation/polling, training execution, model promotion은 계속 금지한다.

## Step 17. Final Approval Packet Draft

completed plan review가 `planning_complete`이고 `requested_next_step=prepare_final_approval_packet`일 때만 final approval packet draft를 만든다.

```bash
python3 scripts/create_report_quality_review_packet_training_final_approval_packet.py \
  reports/report-quality/pilot-rqp-001-training-experiment-plan-review.json \
  --output-manifest reports/report-quality/pilot-rqp-001-training-final-approval-packet-manifest.json \
  --output-markdown reports/report-quality/pilot-rqp-001-training-final-approval-packet.md
```

expected output:

```text
Report quality training final approval packet: PASS
approval_packet_only=true
training_boundary=not_authorized
```

이 packet은 최종 승인자가 볼 evidence index와 required approver roles를 묶는다. 실제 final approval은 별도 approval artifact에서만 기록해야 하며, 이 packet은 dataset upload, provider fine-tune API 호출, provider job creation/polling, training execution, model promotion을 승인하지 않는다.

## Step 18. Validate Final Approval Packet

생성된 final approval packet manifest를 다시 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_final_approval_packet.py \
  reports/report-quality/pilot-rqp-001-training-final-approval-packet-manifest.json
```

expected output:

```text
PASS report quality training final approval packet validated
approval_packet_only=true
training_boundary=not_authorized
```

이 validator는 linked review/plan/file hash, required approver roles, execution step `not_started` 상태, `final_training_approval_granted=false`, no-side-effect boundary를 확인할 뿐이며 학습 실행을 시작하지 않는다.

## Step 19. Pending Final Approval Packet Review

검증된 final approval packet에서 사람이 채울 pending packet review record를 만든다.

```bash
python3 scripts/create_report_quality_review_packet_training_final_approval_packet_review.py \
  reports/report-quality/pilot-rqp-001-training-final-approval-packet-manifest.json \
  --output reports/report-quality/pilot-rqp-001-training-final-approval-packet-review.json
```

expected output:

```text
Report quality training final approval packet pending review: PASS
pending_validation_ok=true
training_boundary=not_authorized
```

이 review record는 final approval packet이 별도 final approval record template 준비 단계로 넘어갈 수 있는지 사람이 판단하기 위한 template이다. `packet_review_complete`도 approval record template 준비 요청일 뿐이며 final approval, dataset upload, provider fine-tune API 호출, provider job creation/polling, training execution, model promotion을 승인하지 않는다.

## Step 20. Validate Final Approval Packet Review

사람이 packet review record를 작성한 뒤 completed gate를 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_final_approval_packet_review.py \
  reports/report-quality/pilot-rqp-001-training-final-approval-packet-review.json \
  --require-complete
```

expected output:

```text
PASS report quality training final approval packet review validated
completed=true
training_boundary=not_authorized
```

completed review도 approval-record preparation evidence다. 별도 최종 승인 artifact 전까지 final approval, dataset upload, provider fine-tune API 호출, provider job creation/polling, training execution, model promotion은 계속 금지한다.

## Step 21. Pending Final Approval Record Template

completed packet review에서 사람이 나중에 채울 pending final approval record template JSON/Markdown을 만든다.

```bash
python3 scripts/create_report_quality_review_packet_training_final_approval_record_template.py \
  reports/report-quality/pilot-rqp-001-training-final-approval-packet-review.json \
  --output reports/report-quality/pilot-rqp-001-training-final-approval-record-template.json \
  --markdown reports/report-quality/pilot-rqp-001-training-final-approval-record-template.md
```

expected output:

```text
Report quality training final approval record template: PASS
template_only=true
approval_granted=false
training_boundary=not_authorized
```

이 template은 최종 승인 record를 작성하기 위한 빈 슬롯과 evidence hash를 준비할 뿐이다. 생성 시점에는 `approval_record_completed=false`, `final_training_approval_granted=false`, 모든 approver decision은 `pending`이어야 하며 dataset upload, provider fine-tune API 호출, provider job creation/polling, training execution, model promotion을 승인하지 않는다.

## Step 22. Validate Final Approval Record Template

생성된 final approval record template이 pending 상태와 no-side-effect boundary를 유지하는지 검증한다.

```bash
python3 scripts/validate_report_quality_review_packet_training_final_approval_record_template.py \
  reports/report-quality/pilot-rqp-001-training-final-approval-record-template.json
```

expected output:

```text
PASS report quality training final approval record template validated
template_only=true
approval_granted=false
training_boundary=not_authorized
```

이 validator는 linked packet review/packet/file hash, pending approver slots, execution step `not_started` 상태, `final_training_approval_granted=false`, no-side-effect boundary를 확인할 뿐이며 학습 실행을 시작하지 않는다.

## Terminal Boundary

이 로컬 evidence chain은 Step 22의 pending final approval record template에서 끝난다. Template은 승인 결과가 아니라, 나중에 별도 change control 아래에서 승인자가 검토할 입력 형식이다.

현재 상태는 다음과 같다.

- `template_only=true`
- `approval_record_completed=false`
- `final_training_approval_granted=false`
- 모든 required approval은 `pending`
- provider job과 execution step은 `not_started`

따라서 추가 freeze, handoff, sign-off, closure 파일을 만들지 않는다. 학습을 진행하려면 이 runbook 밖에서 실제 승인 record, 실행 책임자, 비용 한도, provider 계정, rollback 조건을 별도 검토하고 명시적으로 승인해야 한다.

## Boundary

이 runbook의 명령은 로컬 evidence 파일만 읽거나 쓴다.

- server_file_written: `false`
- persisted_learning_artifact: `false`
- aws_deploy_started: `false`
- aws_resource_created: `false`
- aws_cost_increase_allowed: `false`
- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- training_execution_started: `false`
- model_promotion_started: `false`

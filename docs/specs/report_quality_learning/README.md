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
- [training_no_cost_freeze_template.json](./training_no_cost_freeze_template.json)
- [training_no_cost_freeze_handoff_signoff_template.json](./training_no_cost_freeze_handoff_signoff_template.json)
- [training_no_cost_evidence_bundle_handoff_signoff_template.json](./training_no_cost_evidence_bundle_handoff_signoff_template.json)
- [correction_artifact_template.json](./correction_artifact_template.json)
- [validate_correction_artifact.py](./validate_correction_artifact.py)
- [validate_review_packet.py](./validate_review_packet.py)
  - Report Workflow UI의 `Review packet JSON` 다운로드 결과를 로컬에서 검증한다.
  - Packet에 포함된 server preview artifact를 기존 correction artifact validator로 다시 검사한다.
  - `--require-ready`를 붙이면 final-approved workflow, `learning_opt_in=true`, server preview artifact ready, checklist pass, no-training/no-upload/no-provider-call boundary까지 모두 요구한다.
- `scripts/summarize_report_quality_review_packets.py`
  - 다운로드한 여러 `Review packet JSON` 파일을 batch manifest와 markdown summary로 묶는다.
  - local evidence 파일만 쓰며 server artifact 저장, dataset upload, provider fine-tune, training execution은 실행하지 않는다.
- `scripts/export_report_quality_artifacts_from_review_packets.py`
  - 검증된 `Review packet JSON`의 `preview_artifact`만 추출해 correction artifact JSONL을 만든다.
  - 결과 JSONL은 기존 `validate_correction_artifact.py`와 `summarize_report_quality_artifacts.py` 흐름으로 다시 검증할 수 있다.
  - local JSONL/manifest만 쓰며 server artifact 저장, dataset upload, provider fine-tune, training execution은 실행하지 않는다.
- `scripts/build_report_quality_review_packet_evidence.py`
  - Review packet batch summary, correction artifact JSONL export, artifact batch summary, aggregate pipeline manifest를 한 번에 만든다.
  - 운영 전 로컬 evidence packet을 사람이 검토할 때 쓰며 provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_evidence.py`
  - evidence pipeline manifest가 참조하는 파일 존재 여부, JSONL hash, stage readiness, no-side-effect boundary를 다시 검증한다.
  - provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_handoff.py`
  - 검증된 evidence pipeline manifest에서 reviewer handoff index와 handoff manifest를 생성한다.
  - local handoff 파일만 쓰며 provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_handoff.py`
  - handoff manifest가 참조하는 pipeline, index, handoff files, hash, reviewer actions, no-side-effect boundary를 다시 검증한다.
  - provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_signoff.py`
  - 검증된 handoff manifest에서 사람이 채울 pending sign-off record를 생성한다.
  - handoff manifest path/hash만 자동으로 채우며 reviewer, decision, acknowledgement는 사람이 직접 완료해야 한다.
  - local sign-off 파일만 쓰며 provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_signoff.py`
  - 사람이 작성한 review packet handoff sign-off record를 검증한다.
  - 완료된 sign-off도 evidence review 기록일 뿐이며 provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/summarize_report_quality_review_packet_signoffs.py`
  - pending/completed review packet sign-off record들을 read-only summary JSON/Markdown으로 묶는다.
  - summary는 reviewer approval을 대신 기록하지 않으며 provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_readiness.py`
  - evidence pipeline manifest와 sign-off summary를 함께 검증해 training discussion readiness manifest를 만든다.
  - 이 readiness는 사람이 학습 실험 논의를 시작하기 위한 local gate이며 provider fine-tune, dataset upload, training execution은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_readiness.py`
  - training discussion readiness manifest의 input hash, evidence 재검증, sign-off summary complete gate, no-side-effect boundary를 다시 확인한다.
  - provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_discussion_handoff.py`
  - 검증된 training readiness manifest에서 학습 논의용 local handoff manifest와 Markdown index를 만든다.
  - handoff는 evidence/sign-off/readiness 파일 경로와 hash를 묶을 뿐이며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_discussion_handoff.py`
  - training discussion handoff manifest의 readiness hash, linked file hash, embedded validation, operator action, no-side-effect boundary를 다시 확인한다.
  - provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_discussion_decision.py`
  - 검증된 training discussion handoff manifest에서 사람이 채울 pending discussion decision record를 생성한다.
  - decision은 future experiment plan draft 요청 여부만 기록할 수 있으며 provider fine-tune, dataset upload, training execution, model promotion은 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_discussion_decision.py`
  - 사람이 작성한 discussion decision record의 participant, decision, requested next step, evidence review, acknowledgement, linked handoff hash, no-side-effect boundary를 검증한다.
  - completed decision도 planning-only 기록이며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_experiment_plan_draft.py`
  - completed `plan_draft_requested` discussion decision에서 local training experiment plan draft manifest와 Markdown을 만든다.
  - provider/base model/dataset/eval/parameter 후보를 계획 문서로만 묶으며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_experiment_plan_draft.py`
  - plan draft의 linked decision/handoff/file hash, job spec, offline eval suite, execution step `not_started` 상태, no-side-effect boundary를 다시 검증한다.
  - 이 validator도 local planning artifact만 확인하며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_experiment_plan_review.py`
  - 검증된 training experiment plan draft에서 사람이 채울 pending plan review record를 생성한다.
  - review는 final approval packet을 준비할지 여부만 기록하며 provider fine-tune, dataset upload, training execution, provider job, model promotion은 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_experiment_plan_review.py`
  - 사람이 작성한 plan review record의 reviewer, decision, requested next step, evidence review, acknowledgement, linked plan hash, no-side-effect boundary를 검증한다.
  - completed review도 planning handoff 기록이며 provider fine-tune, dataset upload, training execution, provider job, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_final_approval_packet.py`
  - completed `planning_complete` plan review에서 final approval packet manifest와 Markdown index를 만든다.
  - 이 packet은 최종 승인자가 볼 evidence index일 뿐이며 final approval, provider fine-tune, dataset upload, provider job, training execution, model promotion은 기록하거나 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_final_approval_packet.py`
  - final approval packet의 linked review/plan/file hash, required approver roles, not-started job spec snapshot, no-side-effect boundary를 다시 검증한다.
  - `final_training_approval_granted=false`를 강제하며 provider fine-tune, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_final_approval_packet_review.py`
  - 검증된 final approval packet에서 사람이 채울 pending packet review record를 생성한다.
  - review는 별도 final approval record template 준비 여부만 기록하며 final approval, provider fine-tune, dataset upload, provider job, training execution, model promotion은 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_final_approval_packet_review.py`
  - 사람이 작성한 packet review record의 reviewer, decision, requested next step, evidence review, acknowledgement, linked packet hash, no-side-effect boundary를 검증한다.
  - completed review도 approval-record 준비 단계일 뿐이며 final approval, provider fine-tune, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_final_approval_record_template.py`
  - completed `packet_review_complete` packet review에서 사람이 나중에 채울 pending final approval record template JSON/Markdown을 만든다.
  - template은 최종 승인 입력 칸과 evidence hash를 준비할 뿐이며 actual final approval, provider fine-tune, dataset upload, provider job, training execution, model promotion은 기록하거나 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_final_approval_record_template.py`
  - final approval record template의 linked packet review/packet/file hash, pending approver slots, not-started job spec snapshot, no-side-effect boundary를 검증한다.
  - `template_only=true`와 `final_training_approval_granted=false`를 강제하며 provider fine-tune, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_freeze.py`
  - pending final approval record template에서 현재 학습/운영 체인을 no-cost hold로 멈추는 freeze manifest와 Markdown을 만든다.
  - freeze는 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 모두 금지하는 로컬 marker이며 비용 발생 작업을 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_freeze.py`
  - freeze manifest의 linked approval record template hash, source file hash, not-started job spec snapshot, AWS/provider/training no-cost boundary를 검증한다.
  - `freeze_only=true`와 `aws_cost_increase_allowed=false`를 강제하며 provider fine-tune, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_freezes.py`
  - 하나 이상의 no-cost freeze manifest를 다시 검증하고 read-only summary JSON/Markdown으로 묶어 운영 인계와 감사용 evidence를 만든다.
  - summary도 local 파일만 읽고 쓰며 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_freeze_handoff.py`
  - 검증된 no-cost freeze summary에서 운영자가 보관할 handoff manifest와 Markdown을 만든다.
  - handoff는 freeze summary와 freeze manifest hash를 묶는 인계 산출물일 뿐이며 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff.py`
  - no-cost freeze handoff의 summary hash, linked freeze manifest hash, source file hash, operator action, no-cost boundary를 다시 검증한다.
  - handoff도 `aws_cost_increase_allowed=false`와 `training_execution_authorized=false`를 강제하며 외부 작업을 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py`
  - 검증된 no-cost freeze handoff에서 사람이 채울 pending sign-off record를 생성한다.
  - sign-off는 handoff 검토 여부를 기록하기 위한 로컬 evidence일 뿐이며 서비스 재개, AWS runtime/cost, provider call, dataset upload, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py`
  - 사람이 작성한 no-cost freeze handoff sign-off record의 reviewer, decision, evidence review, acknowledgement, handoff hash, no-cost boundary를 검증한다.
  - completed sign-off도 freeze handoff review 기록일 뿐이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_archive_closure.py`
  - completed no-cost freeze handoff sign-off에서 프로젝트 pause/archive closure manifest와 Markdown을 만든다.
  - closure는 no-cost hold evidence를 보관하기 위한 로컬 산출물이며 서비스 재개, AWS runtime/cost, provider call, dataset upload, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_archive_closure.py`
  - archive closure의 sign-off hash, handoff hash, source file hash, operator action, no-cost boundary를 검증한다.
  - `archived_no_cost_hold` 상태와 `operation_resume_approved=false`를 강제하며 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_archive_closures.py`
  - 하나 이상의 no-cost archive closure manifest를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 pause/archive 상태 확인용 로컬 evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle.py`
  - 검증된 no-cost archive closure summary에서 최종 보관용 evidence bundle manifest와 Markdown을 만든다.
  - bundle은 linked closure/source file hash를 묶는 로컬 checksum index일 뿐이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle.py`
  - no-cost evidence bundle의 archive closure summary hash, linked closure/source file hash, operator action, no-cost boundary를 검증한다.
  - `no_cost_evidence_bundle_ready` 상태와 `operation_resume_approved=false`를 강제하며 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py`
  - 검증된 no-cost evidence bundle에서 운영자 handoff manifest와 Markdown을 만든다.
  - handoff는 final archive evidence를 전달하기 위한 로컬 산출물이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py`
  - no-cost evidence bundle handoff의 bundle hash, linked source file hash, operator action, no-cost boundary를 검증한다.
  - `no_cost_evidence_bundle_handoff_ready` 상태와 `operation_resume_approved=false`를 강제하며 AWS 비용 발생 작업, provider 호출, dataset upload, provider job, 학습 실행, 모델 승격을 기록하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py`
  - 검증된 no-cost evidence bundle handoff에서 사람이 채울 pending sign-off record를 생성한다.
  - sign-off는 final archive handoff 검토 여부를 기록하기 위한 로컬 evidence일 뿐이며 서비스 재개, AWS runtime/cost, provider call, dataset upload, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py`
  - 사람이 작성한 no-cost evidence bundle handoff sign-off record의 reviewer, decision, evidence review, acknowledgement, handoff hash, no-cost boundary를 검증한다.
  - completed sign-off도 final archive handoff review 기록일 뿐이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoffs.py`
  - 하나 이상의 completed no-cost evidence bundle handoff sign-off를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 final archive handoff review 확인용 로컬 evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_resume_guard.py`
  - 검증된 no-cost evidence bundle handoff sign-off summary에서 resume guard manifest와 Markdown을 만든다.
  - guard는 서비스 재개와 AWS 비용 증가가 별도 승인 전까지 차단되어 있음을 기록하는 로컬 산출물이며 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_resume_guard.py`
  - no-cost resume guard의 sign-off summary hash, linked source file hash, resume prerequisites, blocked actions, no-cost boundary를 검증한다.
  - `no_cost_resume_guard_active` 상태와 `resume_blocked=true`, `operation_resume_approved=false`를 강제하며 서비스 재개, AWS 비용 증가, provider 호출, dataset upload, 학습 실행, 모델 승격을 기록하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_resume_guards.py`
  - 하나 이상의 no-cost resume guard manifest를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 freeze/resume 차단 상태 확인용 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_ops_lock.py`
  - 검증된 no-cost resume guard summary에서 ops lock manifest와 Markdown을 만든다.
  - lock은 `service_operation_locked=true`, `resume_blocked=true`를 기록하는 로컬 운영 잠금 증거이며 AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_ops_lock.py`
  - no-cost ops lock의 resume guard summary hash, linked guard/source file hash, lock controls, unlock prerequisites, no-cost boundary를 검증한다.
  - `no_cost_ops_lock_active` 상태와 `service_operation_locked=true`를 강제하며 서비스 재개, AWS 비용 증가, provider 호출, dataset upload, 학습 실행, 모델 승격을 기록하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_ops_locks.py`
  - 하나 이상의 no-cost ops lock manifest를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 운영 잠금 상태 확인용 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_ops_lock_handoff.py`
  - 검증된 no-cost ops lock summary에서 운영자 handoff manifest와 Markdown을 만든다.
  - handoff는 서비스 운영 잠금 상태를 전달하기 위한 로컬 산출물이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_ops_lock_handoff.py`
  - no-cost ops lock handoff의 summary hash, linked ops lock/source file hash, operator action, no-cost boundary를 검증한다.
  - `no_cost_ops_lock_handoff_ready`, `service_operation_locked=true`, `resume_blocked=true`를 강제하며 서비스 재개, AWS 비용 증가, provider 호출, dataset upload, 학습 실행, 모델 승격을 기록하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py`
  - 검증된 no-cost ops lock handoff에서 사람이 채울 pending sign-off record를 생성한다.
  - sign-off는 운영 잠금 handoff 검토 여부를 기록하기 위한 로컬 evidence일 뿐이며 서비스 재개, AWS runtime/cost, provider call, dataset upload, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py`
  - 사람이 작성한 no-cost ops lock handoff sign-off record의 reviewer, decision, evidence review, acknowledgement, handoff hash, no-cost boundary를 검증한다.
  - completed sign-off도 운영 잠금 handoff review 기록일 뿐이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoffs.py`
  - 하나 이상의 completed no-cost ops lock handoff sign-off를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 서비스 운영 잠금 handoff review 확인용 로컬 evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_final_hold.py`
  - 검증된 no-cost ops lock handoff sign-off summary에서 최종 no-cost hold manifest와 Markdown을 만든다.
  - final hold는 서비스 운영 잠금과 resume 차단을 보관하는 로컬 terminal evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_final_hold.py`
  - final hold의 sign-off summary hash, linked source file hash, operator action, no-cost boundary를 검증한다.
  - `no_cost_final_hold_active`, `service_operation_locked=true`, `resume_blocked=true`를 강제하며 서비스 재개, AWS 비용 증가, provider 호출, dataset upload, 학습 실행, 모델 승격을 기록하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_final_holds.py`
  - 하나 이상의 no-cost final hold manifest를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 최종 pause/service-lock 상태 확인용 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_closeout_receipt.py`
  - 검증된 no-cost final hold summary에서 closeout receipt manifest와 Markdown을 만든다.
  - receipt는 현재 체인이 no-cost hold로 닫혔다는 로컬 확인서이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_closeout_receipt.py`
  - closeout receipt의 final hold summary hash, linked source file hash, operator action, no-cost boundary를 검증한다.
  - `no_cost_closeout_receipt_ready`, `service_operation_locked=true`, `resume_blocked=true`를 강제하며 서비스 재개, AWS 비용 증가, provider 호출, dataset upload, 학습 실행, 모델 승격을 기록하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_closeout_receipts.py`
  - 하나 이상의 no-cost closeout receipt를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 최종 서비스 운영 잠금과 no-cost hold 상태를 재확인하는 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion은 실행하지 않는다.
- `scripts/check_report_quality_review_packet_training_no_cost_service_lock.py`
  - closeout receipt summary 하나를 읽어 최종 service lock, resume block, no-cost boundary가 유지되는지 빠르게 검사한다.
  - check는 local read-only guard이며 파일 생성, 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_service_lock_report.py`
  - 검증된 closeout receipt summary에서 operator 공유용 service lock report JSON/Markdown을 만든다.
  - report는 최종 no-cost/service-lock 확인용 로컬 evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report.py`
  - service lock report의 closeout receipt summary hash, embedded check 결과, Markdown, operator action, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_service_lock_reports.py`
  - 하나 이상의 검증된 service lock report를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 최종 service-lock report 상태를 모아 보는 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report_summary.py`
  - service lock report summary의 readiness, counts, linked report states, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_operator_handoff.py`
  - 검증된 service lock report summary에서 operator handoff manifest와 Markdown을 만든다.
  - handoff는 최종 운영 전달용 로컬 evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff.py`
  - operator handoff의 summary hash, embedded validation, Markdown, operator action, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py`
  - 검증된 operator handoff에서 사람이 검토할 pending sign-off JSON을 만든다.
  - sign-off 생성은 로컬 review record만 만들며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py`
  - operator handoff sign-off의 handoff hash, reviewer/completion fields, acknowledgement, no-cost boundary를 검증한다.
  - validator는 completed sign-off도 review evidence로만 취급하며 서비스 재개, AWS 비용 증가, provider 호출, 학습 실행, 모델 승격을 승인하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_signoffs.py`
  - 하나 이상의 completed operator handoff sign-off를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 operator handoff review 완료 상태를 모아 보는 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff_summary.py`
  - operator handoff sign-off summary의 readiness, counts, linked signoff states, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py`
  - 검증된 operator handoff sign-off summary에서 최종 operator handoff closeout receipt JSON/Markdown을 만든다.
  - receipt는 operator review chain이 no-cost/service-lock 상태로 닫혔다는 로컬 evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py`
  - operator handoff closeout receipt의 summary hash, Markdown, source files, operator actions, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS 비용 증가, provider 호출, 학습 실행, 모델 승격을 승인하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipts.py`
  - 하나 이상의 operator handoff closeout receipt를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 operator handoff closeout receipt 상태를 한 번 더 모아 보는 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary.py`
  - operator handoff closeout receipt summary의 readiness, counts, linked receipt states, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py`
  - 검증된 operator handoff closeout receipt summary에서 최종 operator handoff closeout package JSON/Markdown을 만든다.
  - package는 운영자 전달용 로컬 evidence 묶음이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 승인하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py`
  - operator handoff closeout package의 summary hash, Markdown, source files, operator actions, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS 비용 증가, provider 호출, 학습 실행, 모델 승격을 승인하지 않는다.
- `scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_packages.py`
  - 하나 이상의 operator handoff closeout package를 다시 검증하고 read-only summary JSON/Markdown으로 묶는다.
  - summary는 최종 operator closeout package 상태를 모아 보는 로컬 audit evidence이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package_summary.py`
  - operator handoff closeout package summary의 readiness, counts, linked package states, no-cost boundary를 검증한다.
  - validator는 read-only이며 서비스 재개, AWS deploy/resource/runtime, provider API, dataset upload, provider job, training execution, model promotion을 실행하지 않는다.
- `scripts/create_report_quality_pilot_pack.py`
  - UI에서 내려받은 ready artifact JSONL 3~5개를 순서대로 로컬 review pack에 가져오고 source SHA-256, tenant, artifact 순서를 `SOURCE_MANIFEST.json`에 기록한다.
  - `--source-jsonl`이 없으면 `accepted_for_learning=false`, `human_review_status=pending`인 non-ready draft를 생성한다.
- `scripts/run_report_quality_learning_demo.py`
  - mock provider와 임시 local storage로 Report Workflow 생성, 기획·장표·최종 승인, correction artifact preview·저장·목록·JSONL export를 연결한다.
  - exported artifact를 같은 validator로 다시 검사하고 compact JSON receipt를 남긴다. provider API, dataset upload, training execution, model promotion은 호출하지 않는다.
- `scripts/sync_report_quality_pilot_pack.py`
  - 사람이 수정한 `drafts/*.json`을 batch JSONL로 다시 동기화한다.
  - source manifest가 있으면 UI 선택 순서를 보존하고, manifest와 draft 구성이 다르면 실패한다. `--require-ready`를 붙이면 모든 artifact가 학습 후보 gate를 통과하는지 확인한다.
  - Validation 또는 ready gate 실패 시 JSONL을 생성·덮어쓰지 않는다. 성공한 write만 `output_written=true`와 SHA-256을 반환하고, symlink·비-JSONL·import 원본 source 경로 overwrite를 거부한다.
- `scripts/create_report_quality_review_sheet.py`
  - `drafts/*.json` 기준으로 사람이 채워야 할 reviewer, score, scan, approval 필드를 markdown worksheet로 만든다.
  - Source import pack에서는 source manifest SHA-256, tenant, artifact 순서, 각 draft SHA-256을 `human_review_manifest.json`에 함께 결속한다. Worksheet와 manifest만 생성하며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.
- `scripts/apply_report_quality_review_decisions.py`
  - 사람이 작성한 decision JSON을 draft artifact에 반영한다.
  - Decision template은 현재 review 상태와 pack binding을 snapshot으로 남긴다. Source-bound pack은 binding 없는 파일, stale source manifest, 변경된 draft SHA-256을 거부하며, batch 검증이 모두 통과한 경우에만 draft를 저장한다.
  - `accepted` decision은 reviewer, reviewed_at, score, scan pass, validator ready gate를 충족해야 저장된다.
  - `--receipt`는 pack-local decision SHA-256, before/after binding, artifact별 draft hash 전이를 저장한다. 기존 receipt를 덮어쓰지 않고 실패/dry-run에서는 생성하지 않는다.
- `scripts/validate_report_quality_review_decision_receipt.py`
  - 적용 receipt를 현재 decision file, source manifest, ordered drafts와 대조하고 각 artifact의 ready gate를 domain validator로 다시 계산한다.
  - read-only validator이며 provider fine-tune, dataset upload, training execution, model promotion은 실행하지 않는다.

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
- `GET /report-workflows/learning/correction-artifacts/{artifact_id}`
  - 현재 tenant 안에서 한 건의 저장 artifact를 조회한다. content `artifact_id`와 저장 wrapper ID를 모두 지원하며 다른 tenant의 record는 검색하지 않는다.
  - 응답은 metadata-only artifact, 저장 당시 validation, preview fingerprint, 외부 upload/provider/training 차단 경계를 함께 반환한다.
  - Report Workflow UI의 최근 artifact 카드에서 상세 metadata를 검토하거나 이 read-only envelope를 개별 JSON으로 내려받을 수 있다.
- `POST /report-workflows/learning/correction-artifacts/pilot-export`
  - 현재 화면의 ready artifact 중 서로 다른 3~5개를 사람이 선택해 ordered JSONL 파일럿 묶음으로 내려받는다.
  - 서버는 tenant 범위, 최소·최대 개수, 입력 ID 중복, content/store alias 중복, artifact 존재 여부, `ready_for_learning=true`를 다시 검증한다.
  - 선택 export는 local review 파일만 만들며 provider API, dataset upload, training execution, model promotion을 실행하거나 승인하지 않는다.
  - 내려받은 `report_quality_pilot_artifacts.jsonl`은 다음 명령으로 source-bound local review pack에 연결한다.

```bash
python3 scripts/create_report_quality_pilot_pack.py \
  --batch-id pilot-rqc-001 \
  --source-jsonl ~/Downloads/report_quality_pilot_artifacts.jsonl \
  --output-root reports/report-quality
```

생성된 `SOURCE_MANIFEST.json`은 원본 SHA-256, tenant, artifact 순서를 남긴다. 같은 batch ID의 기존 출력이 있으면 import를 거부하며, 이후 `sync_report_quality_pilot_pack.py`도 같은 순서를 적용하고 source manifest와 draft membership이 달라지면 중단한다.

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

파일럿 샘플 3~5개를 실제 Report Workflow에서 만들고 로컬 검수 경로로 가져온다.

각 샘플은 다음 흐름을 따른다.

1. Report Workflow에서 `learning_opt_in=true`로 내부 테스트 프로젝트를 생성한다.
2. AI가 기획안과 장표 초안을 생성한다.
3. 사람이 결과, 수정 이유, 점수, scan 결과를 검토하고 ready correction artifact로 저장한다.
4. UI에서 서로 다른 ready artifact 3~5개를 선택해 `report_quality_pilot_artifacts.jsonl`로 내려받는다.
5. export를 source-bound 파일럿 review pack으로 가져온다.
   ```bash
   python3 scripts/create_report_quality_pilot_pack.py \
     --batch-id pilot-rqc-001 \
     --source-jsonl ~/Downloads/report_quality_pilot_artifacts.jsonl \
     --output-root reports/report-quality
   ```
6. `SOURCE_MANIFEST.json`의 SHA-256, tenant, artifact 순서를 원본 export와 대조한다.
7. worksheet로 교정 내용과 승인 필드를 다시 확인한다. Source import pack에서는 `human_review_manifest.json`의 source/draft SHA-256 binding도 함께 확인한다.
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
    - packet evidence 전체를 한 번에 만들 때는:
      ```bash
      python3 scripts/build_report_quality_review_packet_evidence.py \
        downloads/report-quality-review-packet-*.json \
        --batch-id pilot-rqp-001 \
        --min-packets 3 \
        --output-root reports/report-quality

      python3 scripts/validate_report_quality_review_packet_evidence.py \
        reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json

      python3 scripts/create_report_quality_review_packet_handoff.py \
        reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json

      python3 scripts/validate_report_quality_review_packet_handoff.py \
        reports/report-quality/pilot-rqp-001-handoff-manifest.json

      python3 scripts/create_report_quality_review_packet_signoff.py \
        reports/report-quality/pilot-rqp-001-handoff-manifest.json

      python3 scripts/validate_report_quality_review_packet_signoff.py \
        reports/report-quality/pilot-rqp-001-signoff.json \
        --require-complete

      python3 scripts/summarize_report_quality_review_packet_signoffs.py \
        reports/report-quality/pilot-rqp-001-signoff.json \
        --require-complete \
        --output reports/report-quality/pilot-rqp-001-signoff-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-signoff-summary.md

      python3 scripts/create_report_quality_review_packet_training_readiness.py \
        reports/report-quality/pilot-rqp-001-evidence-pipeline-manifest.json \
        reports/report-quality/pilot-rqp-001-signoff-summary.json \
        --min-ready-artifacts 3 \
        --output reports/report-quality/pilot-rqp-001-training-readiness-manifest.json \
        --markdown reports/report-quality/pilot-rqp-001-training-readiness.md

      python3 scripts/validate_report_quality_review_packet_training_readiness.py \
        reports/report-quality/pilot-rqp-001-training-readiness-manifest.json

      python3 scripts/create_report_quality_review_packet_training_discussion_handoff.py \
        reports/report-quality/pilot-rqp-001-training-readiness-manifest.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-discussion-handoff-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-discussion-handoff.md

      python3 scripts/validate_report_quality_review_packet_training_discussion_handoff.py \
        reports/report-quality/pilot-rqp-001-training-discussion-handoff-manifest.json

      python3 scripts/create_report_quality_review_packet_training_discussion_decision.py \
        reports/report-quality/pilot-rqp-001-training-discussion-handoff-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-discussion-decision.json

      python3 scripts/validate_report_quality_review_packet_training_discussion_decision.py \
        reports/report-quality/pilot-rqp-001-training-discussion-decision.json \
        --require-complete

      python3 scripts/create_report_quality_review_packet_training_experiment_plan_draft.py \
        reports/report-quality/pilot-rqp-001-training-discussion-decision.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-experiment-plan-draft-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-experiment-plan-draft.md

      python3 scripts/validate_report_quality_review_packet_training_experiment_plan_draft.py \
        reports/report-quality/pilot-rqp-001-training-experiment-plan-draft-manifest.json

      python3 scripts/create_report_quality_review_packet_training_experiment_plan_review.py \
        reports/report-quality/pilot-rqp-001-training-experiment-plan-draft-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-experiment-plan-review.json

      python3 scripts/validate_report_quality_review_packet_training_experiment_plan_review.py \
        reports/report-quality/pilot-rqp-001-training-experiment-plan-review.json \
        --require-complete

      python3 scripts/create_report_quality_review_packet_training_final_approval_packet.py \
        reports/report-quality/pilot-rqp-001-training-experiment-plan-review.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-final-approval-packet-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-final-approval-packet.md

      python3 scripts/validate_report_quality_review_packet_training_final_approval_packet.py \
        reports/report-quality/pilot-rqp-001-training-final-approval-packet-manifest.json

      python3 scripts/create_report_quality_review_packet_training_final_approval_packet_review.py \
        reports/report-quality/pilot-rqp-001-training-final-approval-packet-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-final-approval-packet-review.json

      python3 scripts/validate_report_quality_review_packet_training_final_approval_packet_review.py \
        reports/report-quality/pilot-rqp-001-training-final-approval-packet-review.json \
        --require-complete

      python3 scripts/create_report_quality_review_packet_training_final_approval_record_template.py \
        reports/report-quality/pilot-rqp-001-training-final-approval-packet-review.json \
        --output reports/report-quality/pilot-rqp-001-training-final-approval-record-template.json \
        --markdown reports/report-quality/pilot-rqp-001-training-final-approval-record-template.md

      python3 scripts/validate_report_quality_review_packet_training_final_approval_record_template.py \
        reports/report-quality/pilot-rqp-001-training-final-approval-record-template.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_freeze.py \
        reports/report-quality/pilot-rqp-001-training-final-approval-record-template.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-freeze-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-freeze.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_freeze.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_freezes.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-freeze-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-freeze-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_freeze_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-summary.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff-manifest.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff-signoff.json

      python3 scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff-signoff.json \
        --require-complete

      python3 scripts/create_report_quality_review_packet_training_no_cost_archive_closure.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-freeze-handoff-signoff.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_archive_closure.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_archive_closures.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-archive-closure-summary.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-manifest.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-manifest.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-manifest.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff.json

      python3 scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff.json \
        --require-complete

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoffs.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_resume_guard.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff-summary.json \
        --summary-markdown reports/report-quality/pilot-rqp-001-training-no-cost-evidence-bundle-handoff-signoff-summary.md \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_resume_guard.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_resume_guards.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_ops_lock.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-summary.json \
        --summary-markdown reports/report-quality/pilot-rqp-001-training-no-cost-resume-guard-summary.md \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_ops_lock.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_ops_locks.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_ops_lock_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-summary.json \
        --summary-markdown reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-summary.md \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_ops_lock_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-manifest.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff.json

      python3 scripts/validate_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff.json \
        --require-complete

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoffs.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_final_hold.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff-summary.json \
        --summary-markdown reports/report-quality/pilot-rqp-001-training-no-cost-ops-lock-handoff-signoff-summary.md \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-final-hold.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_final_hold.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_final_holds.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-summary.md

      python3 scripts/create_report_quality_review_packet_training_no_cost_closeout_receipt.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-summary.json \
        --summary-markdown reports/report-quality/pilot-rqp-001-training-no-cost-final-hold-summary.md \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_closeout_receipt.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_closeout_receipts.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-summary.md

      python3 scripts/check_report_quality_review_packet_training_no_cost_service_lock.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-summary.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_service_lock_report.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-closeout-receipt-summary.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_service_lock_reports.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report-summary.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report_summary.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report-summary.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_operator_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-service-lock-report-summary.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-manifest.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff.json

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_signoffs.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff-summary.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff_summary.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff-summary.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-signoff-summary.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipts.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-summary.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-summary.json

      python3 scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-receipt-summary.json \
        --output-manifest reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package-manifest.json \
        --output-markdown reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package-manifest.json

      python3 scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_packages.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package-manifest.json \
        --output reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package-summary.json \
        --markdown reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package-summary.md

      python3 scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package_summary.py \
        reports/report-quality/pilot-rqp-001-training-no-cost-operator-handoff-closeout-package-summary.json
      ```
11. 사람이 수정한 draft JSON을 batch JSONL로 동기화한다.
   ```bash
   python3 scripts/sync_report_quality_pilot_pack.py \
     reports/report-quality/pilot-rqc-001 \
     --min-records 3 \
     --require-ready
   ```
   - `output_written=true`와 `output_sha256`이 함께 반환된 실행만 현재 draft가 반영된 sync 성공으로 본다. 실패 실행은 기존 output을 변경하지 않는다.
12. `scripts/check_report_quality_artifacts.py`로 운영 API 기준 ready count와 export JSONL을 한 번 더 검증한다.
13. `scripts/summarize_report_quality_artifacts.py`로 batch manifest와 markdown summary를 만든다.
14. 최소 30~50개까지 쌓인 뒤에만 small SFT experiment로 넘어간다.

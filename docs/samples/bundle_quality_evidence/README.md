# Bundle Quality Evidence

`proposal_kr`와 `performance_plan_kr`의 대표 mock generation sample을 구조 품질 evidence와 함께 보관한다.

## Regenerate

저장소 루트에서 실행한다.

```bash
python3 scripts/build_finished_doc_review_samples.py \
  --output-dir docs/samples/bundle_quality_evidence \
  --run-name current \
  --no-latest \
  --bundles proposal_kr,performance_plan_kr \
  --formats ''
```

현재 package의 기준 파일은 [`current/manifest.json`](./current/manifest.json)이다. manifest는 생성된 Markdown과 response snapshot, reviewer-facing quality report/dashboard, canonical golden example의 SHA256과 byte size를 기록한다. `tests/test_build_finished_doc_review_samples.py`가 이 값과 현재 파일을 다시 비교한다.

[`current/review.html`](./current/review.html)은 manifest가 hash로 관리하는 자동 검증 원본이다. [`current/human_review.html`](./current/human_review.html)은 request 근거, validator/lint/numeric 상태, 생성 Markdown 본문, receipt의 bundle별 검토 상태, reviewer, notes, manifest 결속, 외부 action 비승인 상태를 한 화면에 모은 읽기 전용 작업공간이다. 두 화면은 서로 연결된다.

## Human Review Receipt

[`current/human_review_receipt.json`](./current/human_review_receipt.json)은 factual grounding과 visual review의 사람 판단을 기록하는 companion receipt다. receipt는 `manifest.json`의 SHA256, schema version, 생성 시각에 결속된다. manifest가 receipt 자체를 artifact로 포함하면 순환 hash가 생기므로 receipt는 manifest artifact 목록 밖에 둔다.

builder는 검토 입력이 없는 `pending` receipt와 읽기 전용 작업공간을 함께 생성한다. 기존 receipt에 reviewer, notes, review state가 하나라도 기록되어 있으면 evidence 재생성을 거부해 사람의 판단을 덮어쓰지 않는다. 작업공간은 receipt와 manifest-declared Markdown에서 다시 만들 수 있는 파생 화면이며 검토 증적의 원본은 JSON receipt다.

```bash
# 현재 receipt와 manifest 결속 검증
python3 scripts/manage_finished_doc_human_review.py validate \
  docs/samples/bundle_quality_evidence/current/human_review_receipt.json

# 한 bundle의 factual/visual review를 함께 기록
python3 scripts/manage_finished_doc_human_review.py record \
  docs/samples/bundle_quality_evidence/current/human_review_receipt.json \
  --bundle proposal_kr \
  --reviewer "reviewer-name" \
  --factual-grounding passed \
  --visual-review passed \
  --notes "요청 근거와 렌더링 결과를 대조함"

# receipt가 없는 별도 evidence package에 pending receipt 생성
python3 scripts/manage_finished_doc_human_review.py init \
  --evidence-dir path/to/evidence-package

# receipt 원본을 바꾸지 않고 읽기 화면만 재생성
python3 scripts/manage_finished_doc_human_review.py render \
  docs/samples/bundle_quality_evidence/current/human_review_receipt.json
```

모든 bundle의 두 review 항목이 `passed`일 때만 receipt status가 `completed`가 된다. `needs_revision`이 하나라도 있으면 전체 status도 `needs_revision`이다. 이 receipt는 문서 검토 기록이며 provider call, 배포, 제출, 계약 또는 다른 외부 action을 승인하지 않는다.

## Completed Review Packet

모든 bundle review가 완료된 evidence directory는 검증 가능한 ZIP packet으로 내보낼 수 있다. `package`는 manifest가 선언한 파일만 포함하고 `packet_manifest.json`에 각 entry의 SHA256과 byte size를 기록한다. Pending 또는 변조된 receipt, manifest hash 불일치, evidence directory 밖의 경로는 packet 생성 전에 거부한다.

```bash
# completed receipt에서만 동작
python3 scripts/manage_finished_doc_human_review.py package \
  path/to/completed-evidence/human_review_receipt.json

# 전달받은 packet의 파일 목록과 SHA256 재검증
python3 scripts/manage_finished_doc_human_review.py verify-packet \
  path/to/completed-evidence/finished_document_review_packet.zip
```

Packet에는 `manifest.json`, receipt, reviewer summary, manifest-declared response snapshot, Markdown, export, preview, quality artifact와 embedded packet manifest만 들어간다. ZIP 생성은 외부 action을 승인하거나 실행하지 않는다.

## Scope And Limitations

- 모든 sample은 local mock provider가 만든 fictional fixture다.
- `validator_pass`는 document schema validation, `lint_pass`는 bundle별 필수 heading·빈 section·금지 token 검사를 뜻한다.
- `numeric_grounding_review`는 단위가 붙은 출력 수치가 request에도 있는지 literal coverage를 검사한다. 일치하지 않으면 package status를 `review_required`로 낮춘다.
- numeric coverage는 수치의 사실성, 최신성, 문맥상 올바른 사용을 증명하지 않는다.
- review console에 본문과 상태가 노출되더라도 사람의 검토·승인 기록을 대신하지 않는다.
- 현재 tracked receipt는 `pending`이며 factual grounding과 human visual review를 완료했다고 주장하지 않는다.
- `human_review.html`은 자동 검증과 receipt의 현재 내용을 함께 표시하는 파생 화면이며 독립적인 승인 증적이 아니다.
- 현재 tracked sample에는 completed receipt가 없으므로 final review packet도 커밋하지 않는다.
- provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume은 실행하지 않는다.

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

[`current/review.html`](./current/review.html)은 bundle별 request 근거, validator/lint/numeric coverage 상태, factual·human review 경계, 생성 Markdown 본문을 함께 보여주는 self-contained local review console이다. 2026-07-13 Playwright로 `1440x1000`과 `390x844` viewport를 확인했으며 mobile horizontal overflow가 없음을 검증했다.

## Scope And Limitations

- 모든 sample은 local mock provider가 만든 fictional fixture다.
- `validator_pass`는 document schema validation, `lint_pass`는 bundle별 필수 heading·빈 section·금지 token 검사를 뜻한다.
- `numeric_grounding_review`는 단위가 붙은 출력 수치가 request에도 있는지 literal coverage를 검사한다. 일치하지 않으면 package status를 `review_required`로 낮춘다.
- numeric coverage는 수치의 사실성, 최신성, 문맥상 올바른 사용을 증명하지 않는다.
- review console에 본문과 상태가 노출되더라도 사람의 검토·승인 기록을 대신하지 않는다.
- factual grounding과 human visual review는 이 package로 검증하지 않았으며 manifest에서도 `false`다.
- provider API, AWS runtime, dataset upload, training execution, model promotion, production service resume은 실행하지 않는다.

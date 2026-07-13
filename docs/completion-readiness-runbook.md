# DecisionDoc Completion Readiness Runbook

기준일: 2026-07-13

이 runbook은 M1 live provider, M2 G2B 실데이터 smoke, M6 deployment smoke를 실행할 때 필요한 입력값과 증적 순서를 고정한다. 기본 절차는 readiness 확인까지만 수행한다. provider API, G2B live API, AWS runtime, dataset upload, training execution, model promotion, production service resume, bid submission, legal approval, contractual commitment는 각 단계에서 명시적으로 승인된 경우에만 실행한다. Proof receipt v2는 receipt의 command가 실제 proof를 실행한 경우에만 해당 action을 제외 목록에서 제거하고 나머지 외부 action 경계를 유지한다.

## 1. 원칙

- secret 값은 문서, README, git tracked evidence에 쓰지 않는다.
- `.env.prod`와 `reports/completion-readiness/`는 gitignore된 local runtime 경로로만 사용한다.
- readiness receipt가 `ready_to_execute`가 되기 전에는 live/deploy proof를 실행하지 않는다.
- 실행 결과는 command, timestamp, environment boundary, pass/fail 요약만 문서에 남긴다.
- 실제 입찰 제출, 법적 승인, 계약 확약은 이 repo의 completion proof 범위가 아니다.

## 2. 준비

필요한 입력값 템플릿을 먼저 확인한다.

```bash
python3 scripts/check_completion_readiness.py --print-env-template
```

이 출력은 env 항목만 포함하므로 env file parser로 그대로 읽을 수 있다. 템플릿을 바탕으로 gitignore된 파일에 실제 값을 넣는다.

```bash
python3 scripts/check_completion_readiness.py --print-env-template > /tmp/decisiondoc-completion-env-template.txt
# 실제 secret은 .env.prod 또는 별도 gitignore된 env file에만 둔다.
```

`/tmp/decisiondoc-completion-env-template.txt`는 복사용 임시 파일이다. secret을 넣지 않는다. 실제 실행에는 `.env.prod` 또는 운영자가 지정한 별도 env file을 사용한다.

readiness와 proof receipt 명령은 별도 실행 계획으로 확인한다.

```bash
python3 scripts/check_completion_readiness.py --print-proof-plan
```

이 출력은 secret 값을 포함하지 않으며 명령을 자동 실행하지 않는다.

## 3. Readiness Receipt

외부 호출 없이 남은 마일스톤의 실행 준비 상태를 기록한다.

```bash
python3 scripts/check_completion_readiness.py \
  --env-file .env.prod \
  --json \
  --output reports/completion-readiness/latest.json
```

receipt 계약을 확인한다.

```bash
python3 scripts/check_completion_readiness_result.py \
  reports/completion-readiness/latest.json \
  --write-result \
  --result-path reports/completion-readiness/latest-check.json
```

기대 결과:

- `ok: true`이면 M1/M2/M6 실행 입력값이 준비된 상태다.
- `ok: false`이면 출력된 `missing_env`, `missing_files`, `blockers`를 먼저 해결한다.
- 이 단계는 외부 API나 runtime을 호출하지 않는다.

## 4. Proof Receipt Contract

M1/M2/M6 proof를 실제로 실행한 뒤에는 secret 없는 JSON receipt를 gitignored `reports/completion-readiness/` 아래에 남긴다. 먼저 안전한 템플릿을 만든다.

```bash
python3 scripts/check_completion_proof_receipt.py --print-template M1 \
  > reports/completion-readiness/m1-live-provider-proof.json

python3 scripts/check_completion_proof_receipt.py --print-template M2 \
  > reports/completion-readiness/m2-g2b-stage-smoke-proof.json

python3 scripts/check_completion_proof_receipt.py --print-template M6 \
  > reports/completion-readiness/m6-deployment-smoke-proof.json
```

템플릿의 placeholder를 실제 command, timestamp, environment boundary, evidence refs, pass/fail summary로 바꾼 뒤 receipt 계약을 확인한다.

```bash
python3 scripts/check_completion_proof_receipt.py \
  reports/completion-readiness/m1-live-provider-proof.json \
  --write-result \
  --result-path reports/completion-readiness/m1-live-provider-proof-check.json
```

검증기는 다음을 확인한다.

- `command`가 해당 milestone의 허용 명령 목록에 포함됨
- `executed_at_utc`가 UTC `Z` suffix timestamp임
- `evidence_refs`가 비어 있지 않음
- `secret_values_recorded`가 `false`임
- receipt 문자열에 대표 secret pattern이 포함되지 않음
- excluded external action boundary가 milestone별 proof 계약과 일치함

M1 live receipt에서는 `provider API execution`, M2 실제 smoke receipt에서는 `G2B live API execution`, M6 실제 smoke receipt에서는 `AWS runtime execution`이 제외 목록에 없어야 한다. M2/M6 preflight receipt는 runtime action을 실행하지 않으므로 전체 제외 목록을 유지한다. 나머지 외부 action은 정해진 순서대로 유지한다.

proof receipt 검증도 외부 API, G2B live API, AWS runtime을 실행하지 않는다.

## 5. M1 Live Provider Proof

실행 조건:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1`
- live provider 호출 비용과 rate limit을 승인받은 상태

실행:

```bash
DECISIONDOC_PROVIDER=openai \
python3 -m pytest -q tests/test_live_providers.py -m live -rs

DECISIONDOC_PROVIDER=gemini \
python3 -m pytest -q tests/test_live_providers.py -m live -rs

DECISIONDOC_PROVIDER=claude \
python3 -m pytest -q tests/test_live_providers.py -m live -rs

DECISIONDOC_PROVIDER=openai,gemini \
DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1 \
python3 -m pytest -q \
  tests/test_live_providers.py::test_live_openai_gemini_fallback_chain_ok \
  -m live -rs
```

증적 기록 기준:

- provider별 pass 여부
- fallback test에서 첫 provider 실패와 다음 provider 성공이 확인됐는지
- secret 값이 로그에 출력되지 않았는지
- README와 `docs/evidence-gallery.md`는 실제 pass 로그가 있을 때만 갱신

GitHub Actions에서 실행할 때는 manual `live.yml` workflow를 사용한다. provider 값은 `openai`, `gemini`, `claude`, `openai,gemini` 중 하나다. `openai,gemini`는 fallback proof 전용이며 workflow 내부에서 `DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1`을 설정하고 `test_live_openai_gemini_fallback_chain_ok`만 실행한다.

```bash
gh workflow run live.yml --ref main -f provider=openai
gh workflow run live.yml --ref main -f provider=gemini
gh workflow run live.yml --ref main -f provider=claude
gh workflow run live.yml --ref main -f provider='openai,gemini'
```

## 6. M2 G2B Stage Smoke

실행 조건:

- `SMOKE_BASE_URL`
- `SMOKE_API_KEY`
- `G2B_API_KEY`
- 필요 시 `SMOKE_PROCUREMENT_URL_OR_NUMBER`
- stage 환경에서 smoke 실행이 승인된 상태

먼저 preflight만 실행한다.

```bash
python3 scripts/run_stage_procurement_smoke.py \
  --env-file .env.prod \
  --preflight
```

preflight가 통과하면 stage smoke를 실행한다.

```bash
python3 scripts/run_stage_procurement_smoke.py \
  --env-file .env.prod
```

증적 기록 기준:

- 수집 대상 공고 식별자 또는 test boundary
- smoke pass/fail 요약
- 생성된 decision package가 입찰 제출이나 법적 승인으로 해석되지 않는다는 boundary
- 실패 시 missing input, external API error, app regression을 구분

## 7. M6 Deployment Smoke

실행 조건:

- `.env.prod`
- `ALLOWED_ORIGINS` 또는 `--base-url`
- `DECISIONDOC_API_KEYS` 또는 `DECISIONDOC_API_KEY`
- `docker-compose.prod.yml`
- 배포 runtime 접근 권한

먼저 preflight만 실행한다.

```bash
python3 scripts/run_deployed_smoke.py \
  --env-file .env.prod \
  --preflight
```

preflight가 통과하면 deployed smoke를 실행한다.

```bash
python3 scripts/run_deployed_smoke.py \
  --env-file .env.prod
```

증적 기록 기준:

- `/health` pass
- 인증 없는 생성 요청 거부
- 인증된 생성/export 요청 성공
- runtime URL 접근성
- README의 Demo 링크는 접근 검증 후에만 갱신

## 8. 문서 갱신 순서

실제 proof가 끝난 뒤에만 다음 파일을 갱신한다.

1. `docs/evidence-gallery.md`
2. `docs/evidence-checklist.md`
3. `docs/implementation-evidence.md`
4. `docs/development-plan.md`
5. `docs/roadmap.md`
6. `README.md`

각 문서에는 command, date, pass/fail, remaining limitation을 함께 남긴다. 측정 근거 없는 수치나 검증되지 않은 운영 표현은 쓰지 않는다.

## 9. 중단 기준

다음 중 하나라도 발생하면 proof를 중단하고 readiness 단계로 되돌아간다.

- secret 값이 stdout, stderr, tracked file에 노출됨
- readiness receipt와 실제 env가 불일치함
- external API 비용 또는 호출 권한이 불명확함
- smoke가 입찰 제출, 법적 승인, 계약 확약으로 이어질 수 있음
- runtime URL 또는 API key 소유권이 확인되지 않음

## 10. 마무리 검증

proof 이후 최소 검증:

```bash
python3 scripts/check_completion_readiness_result.py \
  reports/completion-readiness/latest.json

python3 scripts/check_completion_proof_receipt.py \
  reports/completion-readiness/m1-live-provider-proof.json

python3 scripts/count_readme_metrics.py

pytest tests/ -m "not live" -q

git diff --check
```

live/deploy proof가 실패했더라도 non-live gate가 통과하면 로컬 회귀와 외부 환경 실패를 분리해서 기록한다.

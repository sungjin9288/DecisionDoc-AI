# QUALITY — Public Procurement Go/No-Go Copilot

## Goal

운영 중인 procurement copilot의 품질을 "문장이 그럴듯한가"가 아니라 아래 네 가지로 관리한다.

- decision quality: `GO` / `CONDITIONAL_GO` / `NO_GO`가 실제 판단과 얼마나 맞는가
- evidence quality: hard filter, missing data, score breakdown이 review 가능한가
- council quality: user goal이 role-based 방향, 이견, risk, handoff로 구조화되는가
- handoff quality: `bid_decision_kr` / `proposal_kr`까지 council handoff가 재입력 없이 이어지는가
- workflow quality: attach → evaluate → recommend → generate → approval/share 흐름이 실제로 닫히는가

---

## Starting KPI Set

아래 KPI는 post-launch 기본 세트다. 수치는 절대 기준이 아니라 운영 초기의 starting target이다.

| KPI | 정의 | 측정 소스 | Starting target |
|-----|------|-----------|-----------------|
| recommendation agreement | 사람 라벨과 recommendation 일치율 | labeled fixture / offline regression | 80%+ |
| hard-filter precision | blocking hard filter가 실제 필수 탈락 사유를 맞히는 비율 | labeled fixture / review notes | 95%+ |
| insufficient-data discipline | 정보가 부족한 케이스를 scored로 과신하지 않는 비율 | labeled fixture / regression | false-confidence 최소화 |
| council handoff coverage | recommendation-ready project 중 council session을 거쳐 `bid_decision_kr` 또는 `proposal_kr`까지 이어진 비율 | decision council session / project docs / audit | trend monitoring |
| downstream handoff usage | recommendation 이후 downstream bundle 생성 비율 | structured logs / project docs | trend monitoring |
| decision-to-document continuity | council-backed `bid_decision_kr` / `proposal_kr` 생성 후 approval/share까지 연결되는 비율 | project docs / approvals / share | trend monitoring |
| override / disagreement rate | 사람이 recommendation과 다른 결론으로 진행한 비율 | review notes / downstream usage | investigation trigger |

---

## Labeling Schema

실제 regression case는 아래 필드를 최소 단위로 가진다.

- required core
  - `case_id`
  - `title`
  - `issuer`
  - `budget`
  - `deadline`
  - `raw_text`
  - `key_requirements`
  - `capability_text`
  - `expected_recommendation`
  - `expected_score_status`
  - `slice_tags`
- optional constraint labels
  - `expected_score_min`
  - `expected_score_max`
  - `expected_hard_failure`
  - `expected_missing`
  - `label_source`
  - `review_notes`

실제 템플릿:
- [procurement_eval_labeling_template.json](/Users/sungjin/dev/personal/DecisionDoc-AI/tests/fixtures/procurement/procurement_eval_labeling_template.json)

실제 regression fixture:
- [procurement_eval_regression_cases.json](/Users/sungjin/dev/personal/DecisionDoc-AI/tests/fixtures/procurement/procurement_eval_regression_cases.json)

---

## Slice Taxonomy

`slice_tags`는 나중에 drift를 찾기 위한 최소 분류다. 각 case는 4~6개 tag를 가진다.

- domain
  - `domain:ai`
  - `domain:data`
  - `domain:security`
  - `domain:admin_service`
- issuer
  - `issuer:central_government`
  - `issuer:local_government`
  - `issuer:procurement_service`
- budget
  - `budget:small`
  - `budget:mid`
  - `budget:large`
- data quality
  - `data:complete`
  - `data:sparse`
- risk / shape
  - `risk:hard_fail`
  - `risk:missing_data`
  - `risk:consortium_required`
- expected outcome
  - `recommendation:go`
  - `recommendation:conditional_go`
  - `recommendation:no_go`

---

## Labeling Workflow

1. 공고 원문과 capability evidence를 최소 단위로 캡처한다.
2. first reviewer가 recommendation / hard failure / missing data를 기록한다.
3. second reviewer가 disagreement 여부를 표시한다.
4. disagreement가 있으면 `review_notes`에 이유를 적고 하나의 canonical label로 정리한다.
5. fixture에 case를 추가하고 `pytest -q tests/test_procurement_eval_regression.py`를 먼저 돌린다.
6. slice별 편향이 없는지 확인한 뒤 full suite를 돌린다.

---

## 50-Case Expansion Checklist

- `GO` 최소 15건
- `CONDITIONAL_GO` 최소 15건
- `NO_GO` 최소 15건
- `insufficient_data` 최소 5건
- hard-fail case 포함
  - mandatory certification
  - deadline readiness
  - consortium / partner dependency
- domain 분산 포함
  - AI
  - data
  - security
  - PMO / consulting
- issuer 분산 포함
  - 중앙부처
  - 지자체
  - 조달청/공공기관

---

## Operational Loop

주간 운영 루프는 아래 순서를 따른다.

1. 지난주 recommendation distribution 확인
2. council session이 저장된 `bid_decision_kr` / `proposal_kr` 생성 case 비율 확인
3. proposal / performance_plan 생성으로 이어진 case 확인
4. disagreement 또는 override case 5건 선별
5. fixture에 새 case 추가
6. regression 재실행
7. deterministic rule 조정이 필요하면 작은 patch로만 수정

release-complete 이후 procurement 운영 루프는 기존 `admin quality loop / project detail remediation / audit / URL handoff` 안에서 닫는다.

추가 review 항목:

7. admin location summary의 remediation handoff queue 확인
   - `shared_not_opened`: 링크는 공유됐지만 아직 열리지 않은 case
   - `opened_unresolved`: 링크는 열렸지만 override 저장 또는 retry 완료가 아직 닫히지 않은 case
   - `opened_resolved`: 링크를 열고 실제 remediation까지 닫힌 case
8. `shared_not_opened`는 handoff 자체가 실패한 backlog로 보고 owner follow-up
9. `opened_unresolved`는 project detail override / retry CTA로 바로 진입해 close
10. `opened_resolved`는 follow-through evidence로만 확인하고 unresolved queue에는 다시 섞지 않음
11. project detail procurement panel에서 latest council summary가 현재 recommendation과 같은 방향을 유지하는지 spot check
    - panel이 `stale handoff`를 표시하면 council-assisted `bid_decision_kr` / `proposal_kr` 생성 전에 반드시 rerun
12. council-backed `bid_decision_kr` / `proposal_kr` project document provenance에 council session id / revision / direction이 남는지 확인

주의:

- handoff queue는 새 persistence 없이 audit + current remediation state로 계산한다.
- review 공유는 URL/local preference state만 사용하고, server-side saved preset은 추가하지 않는다.
- `monitor` status는 기본 remediation handoff queue에서 제외한다.

---

## Immediate Next Implementation Order

1. regression fixture를 12건 이상으로 유지하고 실제 운영 case로 계속 교체
2. `slice_tags` 기반 summary report를 주기적으로 출력
3. tenant-scoped read-only ops view로 runtime recommendation distribution과 downstream handoff usage를 확인
4. 동일 ops view에서 recommendation별 downstream follow-through와 `NO_GO` override candidate를 먼저 확인
5. project-scoped override reason capture를 추가해 후보가 아니라 실제 사유를 남긴다
6. 그 이후에만 structured logs까지 합쳐 disagreement summary를 추가
7. 마지막에만 scoring weight tuning 또는 recommendation copy tuning 진행

현재 baseline:
- labeled regression fixture 12건
- recommendation bucket 최소 분산:
  - `GO` 3건 이상
  - `CONDITIONAL_GO` 4건 이상
  - `NO_GO` 3건 이상
- summary report command:
  - `python scripts/procurement_eval_summary.py --out-dir /tmp/procurement-eval-summary`
- runtime ops view:
  - `GET /admin/tenants/{tenant_id}/procurement-quality-summary`
  - `GET /admin/locations/{tenant_id}/procurement-quality-summary`
  - returns decision distribution, score status, blocking hard-filter counts, downstream bundle usage, approval status counts
  - also returns recommendation follow-through and `NO_GO` override candidate summary derived from project docs
  - also returns recent procurement / approval audit activity for investigation context
- project-scoped reason capture:
  - `POST /projects/{project_id}/procurement/override-reason`
  - appends a structured override reason block into the existing procurement `notes` field

---

## Validation Rule

품질 관련 변경은 아래 두 단계를 모두 통과해야 한다.

1. targeted:
   - `tests/test_procurement_eval_regression.py`
2. full:
   - `pytest tests/ -q --tb=short`

fixture schema가 깨지면 라벨 품질부터 다시 정리하고, scoring 수정은 그 다음에 진행한다.

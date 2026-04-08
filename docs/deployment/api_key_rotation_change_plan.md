# API Key Rotation Change Plan

이 문서는 `DECISIONDOC_API_KEYS` runtime allowlist와 `DECISIONDOC_API_KEY` smoke / caller key를
운영 change window 안에서 안전하게 교체하기 위한 실행 템플릿이다.

상세 배포 배경과 workflow contract는 [../deploy_aws.md](../deploy_aws.md),
prod 운영 기본 규칙은 [./prod_checklist.md](./prod_checklist.md)를 함께 본다.

## Quick start

현재 `main` SHA와 최근 성공한 `deploy-smoke` run URL을 먼저 채운 초안을 만들려면:

```bash
python3 scripts/prepare_api_key_rotation_change_plan.py \
  --stage prod \
  --ticket CHG-2026-0410 \
  --owner "<OWNER_NAME>" \
  --approver "<APPROVER_NAME>" \
  --old-key-label "api-key-v1" \
  --new-key-label "api-key-v2" \
  --finalize-time "2026-04-08 21:30 KST" \
  --old-key-deleted "pending" \
  --output /tmp/api-key-rotation-plan.md
```

- script는 current git SHA와 최근 성공한 `deploy-smoke [dev]` / `deploy-smoke [prod]` evidence를 자동으로 넣는다.
- script는 GitHub Actions secret 이름도 조회해서 `OPENAI_API_KEY_<STAGE>` 또는 repo-level `OPENAI_API_KEY` fallback 존재 여부를 자동으로 적는다.
- current SHA 기준 same-SHA run이 있으면 `Validation sequence`의 dev/prod run URL과 `Run smoke` / `Run meeting recording smoke` / `Run ops smoke` 결과도 자동으로 채운다.
- `--finalize-time`, `--old-key-deleted` 를 넘기면 closeout note와 finalize 기록 칸도 같이 채울 수 있다.
- script 기본값은 `direct` cutover 다. external caller 가 있으면 `--cutover-mode overlap` 또는 `--cutover-mode smoke-first` 로 바꿔서 쓴다.
- 나머지 owner, change window, rollout readiness는 운영자가 직접 채운다.
- `gh` auth가 없거나 GitHub Actions run 조회가 실패하면 script는 non-zero exit로 종료한다.

빠르게 이해해야 하는 용어:

- `Change window start/end` 는 서비스 중단 시간을 뜻하지 않는다.
  - 단순히 "이 rotation 작업을 언제 시작했고 언제 끝냈는지" 남기는 기록 칸이다.
  - 상시 운영 환경이면 `ad-hoc` 또는 `close when validation completes` 같이 적어도 된다.
- `Old key label` / `New key label` 은 secret value 자체가 아니다.
  - 사람이 old 와 new 를 구분하려고 붙이는 이름표다.
  - 예: `decisiondoc-api-current`, `decisiondoc-api-next-2026-04-08`
- `Client rollout 대상 목록 확인` 은 "이 repo 밖에서 이 API key 를 실제로 쓰는 caller 가 있는가"를 뜻한다.
  - 없으면 `yes — external caller 없음` 으로 적고 direct cutover 를 고려할 수 있다.
  - 있으면 그 caller 들이 새 key 로 넘어가는 순서를 따로 관리해야 한다.

## 1. Change metadata

아래 항목은 실행 전에 채운다.

| 항목 | 값 |
|------|----|
| Change ticket / Incident | `<TICKET_ID>` |
| Change owner | `<OWNER_NAME>` |
| Approver | `<APPROVER_NAME>` |
| Change window start | `<YYYY-MM-DD HH:MM KST>` |
| Change window end | `<YYYY-MM-DD HH:MM KST>` |
| Target stage | `dev` / `prod` |
| Old key label | `<OLD_KEY_LABEL>` |
| New key label | `<NEW_KEY_LABEL>` |
| Client rollout owner | `<CLIENT_OWNER>` |
| Rollback owner | `<ROLLBACK_OWNER>` |

간단한 기본값:

- 별도 운영 티켓이 없으면 `manual-YYYY-MM-DD-api-key-rotation`
- owner / approver / rollback owner 가 같으면 같은 이름을 반복해도 된다.
- 외부 caller 가 없으면 `Client rollout owner` 는 실제 secret 변경 담당자와 같아도 된다.

## 2. Preconditions

아래 조건이 모두 만족될 때만 시작한다.

- current `main` SHA가 확정되어 있다.
- `prod` rotation이면 같은 `main` SHA에서 성공한 `deploy-smoke [dev]` evidence가 있다.
- `DECISIONDOC_OPS_KEY`, `OPENAI_API_KEY_<STAGE>` 또는 repo-level `OPENAI_API_KEY` fallback이 유효하다.
- 새 key 전달 대상이 누구인지 식별되어 있다.
- old key를 즉시 복구할 수 있도록 안전한 저장 경로가 있다.

기록:

| 체크 | 값 |
|------|----|
| Current `main` SHA | `<GIT_SHA>` |
| Same-SHA `deploy-smoke [dev]` evidence for current `main` | `ready` / `missing` |
| Same-SHA `deploy-smoke [prod]` evidence for current `main` | `ready` / `missing` |
| Latest `deploy-smoke [dev]` run | `<RUN_ID_OR_URL>` |
| Latest `deploy-smoke [prod]` run | `<RUN_ID_OR_URL_OR_NA>` |
| OpenAI fallback 확인 | `yes` / `no` |
| Client rollout 대상 목록 확인 | `yes` / `no` |

## 3. Secret staging

기본 원칙은 overlap-first다. 다만 외부 caller 가 전혀 없고 repo 내부 smoke / deploy 경로만 존재하면
direct cutover 로 단순화할 수 있다.

1. `DECISIONDOC_API_KEYS=old,new`
2. `DECISIONDOC_API_KEY=old`

direct cutover 를 택하는 경우:

1. `DECISIONDOC_API_KEYS=new`
2. `DECISIONDOC_API_KEY=new`
3. `deploy-smoke [dev]`
4. `deploy-smoke [prod]`

이 경로는 "기존 key 를 계속 써야 하는 외부 caller 가 없음"이 확인됐을 때만 쓴다.

GitHub CLI 예시:

```bash
gh secret set DECISIONDOC_API_KEYS -R sungjin9288/DecisionDoc-AI --body "OLD_KEY,NEW_KEY"
gh secret set DECISIONDOC_API_KEY -R sungjin9288/DecisionDoc-AI --body "OLD_KEY"
```

GitHub UI로 할 경우:

1. repository `Settings -> Secrets and variables -> Actions`
2. `DECISIONDOC_API_KEYS` 를 `old,new` 로 수정
3. `DECISIONDOC_API_KEY` 는 아직 `old` 로 유지

기록:

| 항목 | 값 |
|------|----|
| Overlap allowlist 적용 시간 | `<HH:MM>` |
| 적용자 | `<NAME>` |

## 4. Validation sequence

### 4.1 Dev validation

아래 세 단계가 모두 성공해야 다음으로 진행한다.

- `Run smoke`
- `Run meeting recording smoke`
- `Run ops smoke`

기록:

| 항목 | 값 |
|------|----|
| `deploy-smoke [dev]` run id | `<RUN_ID>` |
| `Run smoke` | `success` / `fail` |
| `Run meeting recording smoke` | `success` / `fail` |
| `Run ops smoke` | `success` / `fail` |

### 4.2 Caller cutover

cutover 방식은 둘 중 하나를 선택한다.

#### Option A. External clients first

- `DECISIONDOC_API_KEYS=old,new` 상태를 유지한다.
- 외부 caller를 new key로 교체한다.
- smoke caller는 아직 `DECISIONDOC_API_KEY=old` 를 사용한다.

#### Option B. Smoke caller first

- `DECISIONDOC_API_KEYS=old,new` 상태를 유지한다.
- `DECISIONDOC_API_KEY=new` 로 바꾼다.
- `deploy-smoke [dev]` 를 다시 실행해 new caller key가 runtime allowlist에서 통과하는지 확인한다.

#### Option C. Direct cutover

- 외부 caller 가 전혀 없을 때만 사용한다.
- `DECISIONDOC_API_KEYS=new`
- `DECISIONDOC_API_KEY=new`
- `deploy-smoke [dev]` 와 `deploy-smoke [prod]` 로 바로 검증한다.

기록:

| 항목 | 값 |
|------|----|
| 선택한 cutover 방식 | `external-first` / `smoke-first` / `direct-cutover` |
| Caller cutover 완료 시간 | `<HH:MM>` |
| 추가 dev validation run | `<RUN_ID_OR_NA>` |

### 4.3 Prod validation

`prod` 는 같은 SHA의 `dev` evidence가 있을 때만 실행한다.

기록:

| 항목 | 값 |
|------|----|
| `deploy-smoke [prod]` run id | `<RUN_ID>` |
| `Run smoke` | `success` / `fail` |
| `Run meeting recording smoke` | `success` / `fail` |
| `Run ops smoke` | `success` / `fail` |

## 5. Finalize

모든 caller가 new key로 넘어간 것이 확인되면 아래 상태로 정리한다.

1. `DECISIONDOC_API_KEYS=new`
2. `DECISIONDOC_API_KEY=new`

예시:

```bash
gh secret set DECISIONDOC_API_KEYS -R sungjin9288/DecisionDoc-AI --body "NEW_KEY"
gh secret set DECISIONDOC_API_KEY -R sungjin9288/DecisionDoc-AI --body "NEW_KEY"
```

old key 삭제는 finalize 이후에만 진행한다.

기록:

| 항목 | 값 |
|------|----|
| Finalize 시간 | `<HH:MM>` |
| Old key 삭제 시간 | `<HH:MM_OR_PENDING>` |
| 삭제 담당자 | `<NAME>` |

## 6. Rollback

아래 중 하나라도 발생하면 즉시 baseline으로 되돌린다.

- `deploy-smoke [dev]` 실패
- `deploy-smoke [prod]` 실패
- external caller가 new key로 인증 실패
- 운영 중 401/403 증가

rollback 상태:

1. `DECISIONDOC_API_KEYS=old`
2. `DECISIONDOC_API_KEY=old`

예시:

```bash
gh secret set DECISIONDOC_API_KEYS -R sungjin9288/DecisionDoc-AI --body "OLD_KEY"
gh secret set DECISIONDOC_API_KEY -R sungjin9288/DecisionDoc-AI --body "OLD_KEY"
```

기록:

| 항목 | 값 |
|------|----|
| Rollback 필요 여부 | `yes` / `no` |
| Rollback 시간 | `<HH:MM_OR_NA>` |
| Rollback 사유 | `<REASON_OR_NA>` |

## 7. Closeout

change window가 끝나면 아래를 남긴다.

- 최종 active key label
- old key 삭제 여부
- dev/prod run URL
- incident 또는 change ticket closeout note

closeout note template:

```text
API key rotation completed.
- Stage: <STAGE>
- Main SHA: <GIT_SHA>
- Old key label: <OLD_KEY_LABEL>
- New key label: <NEW_KEY_LABEL>
- Dev validation run: <DEV_RUN_URL>
- Prod validation run: <PROD_RUN_URL_OR_NA>
- Finalize time: <TIME>
- Old key deleted: <YES_OR_NO>
- Owner: <OWNER_NAME>
```

# API Key Rotation Change Plan

이 문서는 `DECISIONDOC_API_KEYS` runtime allowlist와 `DECISIONDOC_API_KEY` smoke / caller key를
운영 change window 안에서 안전하게 교체하기 위한 실행 템플릿이다.

상세 배포 배경과 workflow contract는 [../deploy_aws.md](../deploy_aws.md),
prod 운영 기본 규칙은 [./prod_checklist.md](./prod_checklist.md)를 함께 본다.

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
| Latest `deploy-smoke [dev]` run | `<RUN_ID_OR_URL>` |
| Latest `deploy-smoke [prod]` run | `<RUN_ID_OR_URL_OR_NA>` |
| OpenAI fallback 확인 | `yes` / `no` |
| Client rollout 대상 목록 확인 | `yes` / `no` |

## 3. Secret staging

실행 순서는 항상 overlap-first다.

1. `DECISIONDOC_API_KEYS=old,new`
2. `DECISIONDOC_API_KEY=old`

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

기록:

| 항목 | 값 |
|------|----|
| 선택한 cutover 방식 | `external-first` / `smoke-first` |
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

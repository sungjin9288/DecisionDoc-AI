# AWS Account Security Incident Checklist

이 문서는 leaked IAM access key, suspicious activity case, account-level Lambda restriction 같은 보안 incident 이후
운영자가 즉시 따라갈 수 있는 containment / recovery / hardening checklist를 정리한다.

대상 시나리오:

- AWS Support에서 `Suspicious activity in your AWS account` 케이스가 열린 경우
- `CreateFunction`, `UpdateFunctionCode`, `DeleteFunction` 이 `AccessDeniedException` 으로 일괄 실패하는 경우
- 노출된 IAM access key를 회전/삭제해야 하는 경우

이 문서의 목적은 두 가지다.

1. 배포 실패를 code regression과 account restriction으로 빠르게 구분한다.
2. key rotation, support reply, deploy recovery, post-incident hardening을 같은 순서로 반복 가능하게 만든다.

## 1. Immediate containment

아래 항목은 순서대로 수행한다.

- `deploy-smoke`, `sam deploy`, Lambda 수동 create/update 재시도를 멈춘다.
- 노출된 access key ID suffix를 Support case 또는 경보 메시지에서 확인한다.
- 해당 IAM user와 key 사용처를 식별한다.
- CLI/운영에 꼭 필요한 경우에만 replacement key를 먼저 발급한다.
- replacement key를 실제 사용처에 반영한 뒤 leaked key를 `Inactive -> Delete` 처리한다.
- GitHub Actions가 static key가 아니라 OIDC deploy role을 쓰는지 다시 확인한다.
- CloudTrail에서 `iam.amazonaws.com`, `sts.amazonaws.com` 관련 event를 검토한다.
- 본인이 만들지 않은 IAM user / role / temporary credential이 있으면 즉시 제거한다.

## 2. Key rotation procedure

### 2.1 Local CLI key rotation

`community_` 같은 로컬 CLI user key를 교체할 때는 아래 순서를 따른다.

1. IAM Console에서 새 access key를 발급한다.
2. 로컬 profile을 새 키로 교체한다.
3. `aws sts get-caller-identity` 로 caller를 확인한다.
4. 기존 leaked key를 `Inactive` 로 바꾼다.
5. 다시 CLI가 정상 동작하면 기존 key를 삭제한다.

예시:

```bash
aws configure set aws_access_key_id NEW_ACCESS_KEY_ID --profile default
aws configure set aws_secret_access_key NEW_SECRET_ACCESS_KEY --profile default
aws configure set region ap-northeast-2 --profile default
aws sts get-caller-identity
```

주의:

- `NEW_ACCESS_KEY_ID`, `NEW_SECRET_ACCESS_KEY` 는 실제 값으로 바꿔 넣는다.
- angle bracket (`<...>`) 표기는 입력하지 않는다.
- long-lived key를 repo 내부 파일이나 `.github-actions.env` 에 저장하지 않는다.

### 2.2 Static key usage triage

다음 계정/경로를 순서대로 본다.

- local CLI profile
- 개인 shell script
- 별도 automation host
- 다른 repository secret
- root access key

이 repo 기준 canonical deploy path는 GitHub OIDC `role-to-assume` 이므로, `deploy` / `deploy-smoke` 를 위해 static AWS key를 새로 저장하면 안 된다.

## 3. Support case reply template

기존 `Suspicious activity` 케이스가 이미 열려 있으면 새 케이스를 만들지 말고 해당 케이스에 답변한다.

복구 reply template:

```text
Hello AWS Support,

I completed the requested review and remediation steps for account <ACCOUNT_ID>.

1. Exposed access keys
- Key ending in <KEY_SUFFIX_1> belongs to IAM user <IAM_USER_1> and has been rotated and deleted.
- Key ending in <KEY_SUFFIX_2> belongs to IAM user <IAM_USER_2> and has been rotated and deleted.

2. IAM / CloudTrail review
- Unauthorized IAM roles found: none
- Unauthorized IAM users found: none
- Unauthorized temporary credentials found: none

3. Account access details
- I am accessing the account from: <CITY, COUNTRY>
- VPN usage: <NO_OR_PROVIDER>
- Other users with access:
  - <USER_A> — <LOCATION_AND_PURPOSE>
  - <USER_B> — <LOCATION_AND_PURPOSE>

Additional issue:
AWS Lambda operations in ap-northeast-2 are failing with AccessDeniedException for CreateFunction, UpdateFunctionCode, and DeleteFunction even though IAM simulation shows allowed permissions.

Direct reproduction:
- Region: ap-northeast-2
- Operation: CreateFunction
- Request ID: <REQUEST_ID>

Please confirm whether there is any account-level security restriction or hold on Lambda operations, and advise what additional action is required to restore normal access.

Thank you.
```

운영 시점에 직접 채워야 하는 값:

- `<ACCOUNT_ID>`
- `<KEY_SUFFIX_*>`
- `<IAM_USER_*>`
- `<CITY, COUNTRY>`
- `<NO_OR_PROVIDER>`
- `<REQUEST_ID>`

## 4. Restriction verification

Support가 restriction 해제를 알리면, 배포를 다시 하기 전에 API-level verification을 먼저 수행한다.

### 4.1 Lambda dry-run check

```bash
aws lambda update-function-code \
  --function-name decisiondoc-ai-prod \
  --region ap-northeast-2 \
  --s3-bucket ARTIFACT_BUCKET \
  --s3-key ARTIFACT_KEY \
  --dry-run
```

해석:

- `AccessDeniedException` 이 사라지면 account restriction이 풀렸을 가능성이 높다.
- 여전히 `AccessDeniedException` 이면 deploy rerun보다 Support follow-up이 우선이다.

### 4.2 Recovery deploy order

restriction이 해제된 뒤에는 아래 순서를 유지한다.

1. `deploy-smoke [dev-green]` 또는 fresh-stack validation
2. `deploy-smoke [dev]`
3. `deploy-smoke [prod]`
4. temp validation stack cleanup

## 5. Post-incident hardening

incident 종료 후에는 아래를 확인한다.

- alternate security contact 업데이트
- primary account contact 최신화
- IAM user MFA 활성화
- 불필요한 IAM user / access key 제거
- local pre-commit hook 설치
- CI Secret Hygiene gate 정상 동작 확인
- static key 대신 OIDC / role-based deploy 유지

로컬 개발자 워크플로 hardening:

```bash
bash scripts/install_git_hooks.sh
python3 scripts/check_secret_hygiene.py
```

## 6. DecisionDoc-specific closeout checklist

이 repo에서 incident closeout은 아래가 모두 만족될 때 끝난다.

- leaked key 삭제 완료
- AWS Support case에서 restriction lifted 확인
- `deploy-smoke [dev]` 성공
- `deploy-smoke [prod]` 성공
- `decisiondoc-ai-prod` stack status `UPDATE_COMPLETE`
- 임시 `*-green` validation stack 삭제
- local secret hygiene hook / CI gate가 둘 다 유지

## 7. What not to do

다음은 기본 금지다.

- `AccessDeniedException` 상태에서 `deploy-smoke` 무한 재실행
- incident 중 console에서 임의 hotfix를 canonical deploy path로 대체
- repo 내부 파일에 static AWS credential 저장
- 이미 열린 suspicious-activity case를 두고 새 support case를 중복 생성
- `prod` 를 first recovery target으로 바로 사용

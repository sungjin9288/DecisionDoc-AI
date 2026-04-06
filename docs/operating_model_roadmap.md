# Operating Model Roadmap

이 문서는 DecisionDoc AI를 단기 데모/feature sprint 중심 개발에서 벗어나,
장기적으로 운영 가능한 product engineering model로 옮기기 위한 실행 계획이다.

현재 관찰된 핵심 문제는 다음과 같다.

- `prod` 환경이 실제 기능 검증과 release gate를 동시에 떠안고 있다.
- GitHub Actions, CloudFormation, Lambda update 권한 경계가 불명확해서 deploy failure가 product delivery를 직접 막는다.
- procurement / approval / share / public link / admin triage 같은 운영 민감 기능이 많아, 환경 분리와 smoke discipline이 약하면 개발 속도보다 운영 리스크가 더 빨리 커진다.

이 roadmap의 목표는 새 기능을 늘리는 것이 아니라, **오래 개발해도 운영이 무너지지 않는 delivery system**을 먼저 만드는 것이다.

## 1. Target State

### 1.1 Environment topology

장기 목표는 아래 3계층이다.

- `dev`
  - feature integration, local-like API verification, destructive 실험 허용
- `stage`
  - release candidate 검증, smoke/e2e/procurement live lane 검증
- `prod`
  - promote-only, operator-facing verification, manual console mutation 금지

권장 진화 순서:

1. 같은 AWS account 안에서 `dev/stage/prod` stack 완전 분리
2. 그 다음 가능하면 `prod`는 별도 AWS account로 분리

### 1.2 Deployment model

현재 in-place update 중심 deploy는 운영 리스크가 크다.
장기적으로는 다음 원칙을 적용한다.

- `stage-first deployment`
  - 모든 merged `main` commit은 먼저 `stage`에 반영
- `promote, not rebuild`
  - `prod`는 stage에서 검증된 동일 artifact를 promote
- `immutable release preference`
  - 가능하면 alias/version 또는 `blue/green stack` 기반 cutover
- `no direct prod console edits`
  - 모든 runtime/config/deploy change는 IaC 또는 workflow로만 수행

### 1.3 Access and permission model

deployability는 code quality만으로 보장되지 않는다.
아래 세 가지를 명확히 문서화해야 한다.

- 누가 deploy하는가
  - local human admin
  - GitHub Actions OIDC role
- 누가 prod를 수정할 수 있는가
  - deploy role
  - break-glass operator
- 무엇이 update를 막을 수 있는가
  - IAM policy
  - permission boundary
  - service-side restriction
  - account guardrail

운영 원칙:

- `deploy role`은 stage별로 분리
- `smoke auth user`는 운영 사용자와 분리
- `prod` write 권한은 최소화하고, break-glass path는 명시적으로 따로 둔다

### 1.4 Verification ladder

release 검증은 빠른 층과 느린 층을 분리해야 한다.

1. `fast local`
   - unit / service / schema / storage / deterministic router tests
2. `deterministic integration`
   - e2e with `mock` provider
   - UI regressions
   - project/procurement/admin contract tests
3. `external smoke`
   - deployed `stage`
   - procurement live lane
   - optional ops smoke
4. `prod verification`
   - post-deploy smoke
   - operator-facing sanity only

핵심 원칙:

- flaky upstream 의존 검증은 CI 전체를 깨는 기본 gate가 아니라,
  release decision에 반영되는 separate gate로 관리
- `prod` smoke는 feature discovery가 아니라 promotion confidence를 위한 최종 확인

### 1.5 Data and operator isolation

운영성 강화를 위해 다음을 분리한다.

- smoke tenant
- smoke user
- smoke procurement target strategy
  - optional fixed fixture
  - default discovery-first
- stale-share / admin triage 검증 데이터
- demo seed data

특히 procurement, approval, share, public `/shared/{id}` 관련 기능은
운영 데이터와 테스트 데이터를 섞지 않는 것이 장기 유지 비용을 크게 줄인다.

## 2. 4-Week Execution Plan

## Week 1 — Deploy path stabilization

목표:
- 현재 `prod` deploy blocker를 code issue가 아닌 infra/permission issue로 명확히 분리
- 운영자가 다시 같은 failure를 반복하지 않도록 runbook을 고정

실행 항목:

- `prod` deploy failure 원인 문서화
  - 무엇이 실패했고
  - 어디까지 확인됐고
  - 무엇이 아직 미해결인지 기록
- `deploy role / local admin / break-glass` 권한 경로를 표로 정리
- `prod` deploy 전 필수 확인 checklist 정의
- `UPDATE_ROLLBACK_FAILED` recovery 절차를 runbook에 고정

완료 기준:

- 운영자가 `deploy-smoke`를 무한 재시도하지 않도록 문서와 절차가 고정됨
- deploy 실패가 code issue인지 infra issue인지 10분 내 분류 가능

## Week 2 — Stage-first release lane

목표:
- 개발 완료 후 바로 `prod`로 가지 않고 `stage`에서 release candidate를 검증하는 기본 흐름 확립

실행 항목:

- `stage` stack과 secret/variable set을 `prod`와 동일 계약으로 정리
- GitHub Actions 기준 기본 promotion 흐름 정의:
  - `main` merge
  - `stage deploy-smoke`
  - success evidence 확인
  - 필요 시 `prod` deploy-smoke`
- `stage` procurement smoke를 daily/weekly 운영 체크로 사용할지 결정

현재 repo 현실에서는 dedicated `stage` stack이 아직 없으므로, 우선 `dev`를 stage-equivalent gate로 사용한다. 즉, `prod` deploy-smoke 이전에 같은 `main` SHA 기준 성공한 `dev` deploy-smoke evidence를 요구하는 방식으로 first guardrail을 건다.

완료 기준:

- feature merge 후 first deployment target이 항상 `stage`
- `prod`는 stage pass 이후에만 실행

진행 상태:

- first workflow guardrail is in progress
  - `prod` deploy-smoke 는 같은 `main` SHA에 성공한 `dev` deploy-smoke run이 없으면 기본적으로 멈춘다
  - 예외 경로는 `break_glass_reason` 입력을 명시한 운영 복구 상황으로 제한한다

## Week 3 — Immutable release path

목표:
- 기존 Lambda/function in-place update failure가 다시 delivery 전체를 막지 않도록 release 구조를 개선

권장 옵션:

1. `blue/green stack`
   - 예: `decisiondoc-ai-prod-blue`, `decisiondoc-ai-prod-green`
   - 장점: rollback과 cutover가 명확함
2. `Lambda alias/version`
   - 장점: function version promote가 쉬움
   - 단점: current SAM/API wiring 구조와의 정합성 검토 필요

DecisionDoc AI 현재 구조 기준으로는,
**parallel prod stack + cutover**가 운영적으로 더 읽기 쉬운 편이다.

실행 항목:

- 현재 SAM template가 `blue/green` naming을 수용할 수 있는지 확인
- custom domain 또는 API endpoint cutover 지점을 정의
- rollback 절차를 “stack 상태 복구”가 아니라 “previous green stack으로 복귀”로 바꾸기

현재 repo의 first implementation은 full blue/green cutover까지는 아니고, `deployment_suffix` 기반 fresh-stack workaround를 허용하는 수준이다. 예를 들어 `-green` suffix로 `decisiondoc-ai-dev-green` / `decisiondoc-ai-prod-green` 을 띄우고, 같은 suffix의 `dev` evidence를 `prod` promote gate에 연결한다.

완료 기준:

- `prod` rollback이 기존 function update rollback에 의존하지 않음
- release 문서에 active stack / standby stack 개념이 들어감

## Week 4 — Smoke and operational discipline hardening

목표:
- smoke 계층과 operator verification을 문서가 아니라 습관으로 고정

실행 항목:

- smoke 전용 tenant / user / fixture inventory 문서화
- procurement live smoke, stale-share demo, ops smoke의 용도를 구분
- `manual browser sanity`와 `automated smoke`의 역할을 명확히 분리
- release closeout checklist 정의

완료 기준:

- 어떤 smoke를 언제 돌려야 하는지 팀 내 해석 차이가 사라짐
- 운영 민감 기능 변경 시 필요한 검증이 release 전에 자동으로 떠오름

## 3. Immediate Next Actions

지금 바로 시작할 우선순위는 아래다.

1. `prod Lambda UpdateFunctionCode 403` 원인 분리 완료
   - 현재 code/workflow 문제는 아님
   - IAM allow도 확인됨
   - account/service-side restriction 추적이 우선
2. `stage-first`를 기본 release 규칙으로 선언
   - 새 기능 검증은 `stage`
   - `prod`는 promote-only
3. `deploy ownership map` 문서화
   - local admin
   - GitHub Actions deploy role
   - break-glass path

## 4. Do / Don't

### Do

- keep `mock` provider deterministic
- preserve router/service/storage/provider boundaries
- separate smoke identity from operator identity
- run local + stage verification before prod promotion
- treat `prod` as promotion target, not development workspace

### Don't

- do not use console edits as the normal release path
- do not rely on `prod` as the first place where new workflow changes are tried
- do not mix smoke tenants/users with live operator accounts
- do not let external live procurement variability decide whether core CI passes

## 5. Definition of Long-Term Readiness

아래가 충족되면 이 프로젝트는 “오래 개발하면서 운영 가능한 상태”에 가깝다.

- `dev/stage/prod` 역할이 명확하다
- `prod` deploy는 promote 성격을 가진다
- Lambda/API update 권한 경계가 문서화돼 있다
- smoke 전용 사용자/tenant가 분리돼 있다
- `prod` rollback이 사람 기억이 아니라 문서와 절차로 재현 가능하다
- 새 기능 추가보다 운영 실패 복구가 더 예측 가능하다

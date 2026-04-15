# DecisionDoc AI 회사 전달 가이드

이 문서는 DecisionDoc AI v1을 회사 담당자에게 실제로 전달할 때 사용할 **전달 순서 + 발송 문구 + 첨부 패키지 기준 문서**입니다.

목표는 두 가지입니다.

1. 상대가 무엇을 먼저 봐야 하는지 헷갈리지 않게 한다.
2. 운영 키, 접속 정보, 설명 자료, 운영 문서를 한 번에 넘기되 보안 경계를 흐리지 않는다.

## 1. 전달 전 내부 확인

회사에 자료를 보내기 전에 아래 5개를 먼저 확인합니다.

1. `https://admin.decisiondoc.kr/health` 가 정상이다.
2. `python3 scripts/run_deployed_smoke.py --env-file .env.prod` 최근 실행 결과가 성공이다.
3. `python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy` 최신 결과가 성공이다.
4. `docs/deployment/admin_v1_handoff.md` 와 현재 운영 상태가 일치한다.
5. 전달할 PDF 4종을 1회 육안 검수했다.

## 2. 회사에 넘기는 패키지 구성

기본 전달 패키지는 아래 3덩어리로 나눕니다.

### A. 소개 자료

- `output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf`
- `output/pdf/decisiondoc_ai_executive_intro_ko.pdf`
- `output/pdf/decisiondoc_ai_notebooklm_comparison_ko.pdf`
- `output/pdf/decisiondoc_ai_internal_deployment_brief_ko.pdf`

### B. 운영 문서

- [Admin v1 Handoff](../deployment/admin_v1_handoff.md)
- [admin AWS EC2 구축 가이드](../deployment/admin_aws_ec2_setup.md)
- [프로덕션 배포 체크리스트](../deployment/prod_checklist.md)
- [정보보호 정책](../security_policy.md)
- [DecisionDoc AI v1 완료 스냅샷](../v1_completion_snapshot.md)

### C. 접속 정보

- 서비스 URL: `https://admin.decisiondoc.kr`
- 운영 기준 서버: `decisiondoc-admin-prod`
- 최신 post-deploy evidence:
  - `./reports/post-deploy/latest.json`
  - `./reports/post-deploy/index.json`

주의:

- `DECISIONDOC_API_KEYS`, `DECISIONDOC_OPS_KEY`, `OPENAI_API_KEY` 원문은 문서 본문이나 일반 이메일에 직접 넣지 않습니다.
- 키 전달은 별도 안전 채널로 분리합니다.

## 3. 권장 전달 순서

### 1차: 대표/의사결정자 소개

먼저 아래만 보냅니다.

- meeting onepager
- executive intro
- notebooklm comparison

이 단계 목적은 제품 포지셔닝과 도입 필요성을 이해시키는 것입니다.

### 2차: 운영/설치 설명

관심이 확인되면 아래를 추가합니다.

- internal deployment brief
- admin v1 handoff
- security policy

이 단계 목적은 설치형 구조, 분리 운영, 데이터/권한 통제 방식을 설명하는 것입니다.

### 3차: 실제 handoff

실제 운영 전달 단계에서는 아래까지 같이 넘깁니다.

- admin AWS EC2 구축 가이드
- prod checklist
- latest post-deploy evidence 위치
- acceptance 기록 표

## 4. 외부 전달용 기본 문구

아래 문구는 메일이나 메신저에 그대로 붙여서 써도 됩니다.

```text
안녕하세요.

DecisionDoc AI v1 기준 소개 자료와 운영 개요를 전달드립니다.

이번 버전은 단순 문서 생성 도구가 아니라, 조직이 실제 문서를 만들고 검토하고 승인하고 export하는 흐름까지 포함한 내부 설치형 문서 운영 플랫폼 기준으로 정리되어 있습니다.

먼저 보실 자료는 아래 3가지입니다.
1. 미팅용 1장 요약
2. 제품 소개서
3. NotebookLM 비교 자료

운영/설치 관점까지 검토가 필요하시면 내부 설치형 도입 설명서와 운영 handoff 문서까지 이어서 드리겠습니다.

현재 기준 운영 환경은 admin.decisiondoc.kr 이며, 고객사 전용 분리 환경은 다음 단계에서 별도로 구성하는 방식입니다.
```

## 5. 내부 운영 전달용 기본 문구

```text
DecisionDoc AI v1 운영 기준선 전달드립니다.

기준 환경은 admin.decisiondoc.kr 이고, 현재 canonical deployment path는 AWS EC2 + Docker Compose 입니다.

운영 시작 문서는 아래 순서로 보시면 됩니다.
1. docs/deployment/admin_v1_handoff.md
2. docs/deployment/admin_aws_ec2_setup.md
3. docs/deployment/prod_checklist.md
4. docs/security_policy.md

최신 운영 점검 기준은 deployed smoke + post-deploy report latest.json 입니다.

이번 단계 범위에는 Dawool live rollout과 AWS stage-first lane 전환은 포함되지 않았고, 해당 내용은 next phase 문서로 분리되어 있습니다.
```

## 6. 데모 후 후속 제안 문구

```text
오늘 보신 환경은 admin 기준 운영/데모 환경입니다.

실제 도입 시에는 귀사 전용 도메인, API 키, 운영 키, 데이터 볼륨을 분리한 고객 전용 환경으로 배포하는 방식을 권장합니다.

현재 v1 기준으로는 운영 가능한 baseline과 인수인계 패키지까지 정리된 상태이며, 다음 단계에서는 고객사 전용 rollout과 운영 자동화 강화를 순차적으로 진행할 수 있습니다.
```

## 7. 절대 같이 보내지 말아야 하는 것

- `.env.prod` 원문
- OpenAI API key 원문
- `DECISIONDOC_API_KEYS` 원문
- `DECISIONDOC_OPS_KEY` 원문
- 서버 SSH private key

## 8. 전달 직전 최종 체크

- 첨부 PDF가 최신본이다.
- 링크된 문서 경로가 실제 repo와 일치한다.
- 접속 URL이 현재 운영 기준과 일치한다.
- post-deploy latest report 경로를 확인했다.
- 키 전달 경로를 별도로 정했다.

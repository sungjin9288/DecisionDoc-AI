# Dawool 다음 Phase 입력 템플릿

이 문서는 `dawool` 전용 환경을 실제로 시작하기 전에 **꼭 먼저 받아야 하는 최소 입력값**만 적는 간단한 intake 템플릿입니다.

이 문서의 목적은 배포를 하는 것이 아니라, 다음 phase를 시작할 수 있는지 빠르게 판단하는 것입니다.

배포 실행 문서는 아래를 봅니다.

- [Dawool rollout runbook](./dawool_rollout_runbook.md)
- [Dawool rollout worksheet](./dawool_rollout_worksheet.md)

## 1. 이번에 먼저 받아야 하는 정보

아래 항목이 채워져야 다음 phase 실작업을 시작할 수 있습니다.

| 항목 | 값 | 필수 여부 |
|------|----|-----------|
| 고객사/환경 이름 | `dawool` | 필수 |
| 사용할 도메인 | `<예: dawool.decisiondoc.kr>` | 필수 |
| 서버 위치 | `<AWS / 고객사 VM / 온프레미스 / 기타>` | 필수 |
| 서버 접근 방식 | `<SSH / 콘솔 / 기타>` | 필수 |
| 운영 책임자 | `<이름>` | 필수 |
| acceptance 확인 담당자 | `<이름 또는 역할>` | 필수 |
| 공인 IP 또는 예정 IP | `<IP 또는 pending>` | 필수 |
| OpenAI API 키 정책 | `<전용 키 / 기존 키 공유>` | 필수 |
| `DECISIONDOC_API_KEYS` 준비 여부 | `ready / pending` | 필수 |
| `DECISIONDOC_OPS_KEY` 준비 여부 | `ready / pending` | 필수 |
| `ALLOWED_ORIGINS` | `<예: https://dawool.decisiondoc.kr>` | 필수 |
| 데이터 보관 위치 | `<local volume / 별도 경로>` | 권장 |
| 백업 책임자 | `<이름>` | 권장 |
| 목표 일정 | `<YYYY-MM-DD 또는 pending>` | 권장 |
| 특이사항 | `<메모>` | 선택 |

## 2. 빠른 판정 기준

아래 5개가 모두 맞아야 다음 phase를 바로 시작합니다.

- 도메인이 정해졌다.
- 서버 위치와 접근 방식이 정해졌다.
- 운영 책임자와 acceptance 담당자가 정해졌다.
- `DECISIONDOC_API_KEYS` / `DECISIONDOC_OPS_KEY` 준비 여부가 명확하다.
- `admin` 환경과 분리 운영한다는 원칙이 합의됐다.

하나라도 비어 있으면, 배포 작업보다 먼저 입력값 확정이 우선입니다.

## 3. 바로 복붙해서 보낼 질문 템플릿

아래 메시지를 그대로 보내서 필요한 정보만 받으면 됩니다.

```text
Dawool 전용 환경 다음 단계 진행을 위해 아래 정보만 먼저 부탁드립니다.

1. 사용할 도메인
2. 서버 위치 (AWS / VM / 온프레미스 등)
3. 서버 접근 방식 (SSH 가능 여부)
4. 운영 책임자
5. acceptance 확인 담당자
6. 공인 IP 또는 예정 IP
7. OpenAI API 키를 전용으로 쓸지, 기존 정책을 따를지
8. DECISIONDOC_API_KEYS 준비 여부
9. DECISIONDOC_OPS_KEY 준비 여부
10. ALLOWED_ORIGINS 값

이 값들이 확인되면 Dawool 전용 rollout 단계로 바로 들어가겠습니다.
```

## 4. 다음 phase 시작 선언 예시

```text
Dawool 전용 환경의 필수 입력값이 확인되었습니다.
다음 단계에서는 dawool 전용 .env.prod, 도메인, 키, smoke/post-deploy baseline을 기준으로 실제 배포 절차를 진행하겠습니다.
```

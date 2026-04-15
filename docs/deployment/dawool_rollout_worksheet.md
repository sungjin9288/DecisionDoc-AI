# `dawool.decisiondoc.kr` 배포 준비 시트

이 문서는 `dawool.decisiondoc.kr` 고객 전용 환경을 실제로 배포하기 전에,
운영자가 필요한 입력값과 점검 결과를 한 번에 적어 두는 기록 템플릿입니다.

실행 절차 자체는 아래 문서를 기준으로 합니다.

- `docs/deployment/dawool_intake_checklist.md`
- `docs/deployment/dawool_rollout_runbook.md`

이 시트는 “무엇을 채워야 하는지”와 “어디까지 끝났는지”를 놓치지 않게 하기 위한 운영 기록용 문서입니다.

## 1. 기본 정보

| 항목 | 값 |
|------|----|
| 고객 환경 이름 | `dawool` |
| 목표 도메인 | `dawool.decisiondoc.kr` |
| 배포 담당자 | `<NAME>` |
| 점검 담당자 | `<NAME>` |
| 배포 예정일 | `<YYYY-MM-DD>` |
| 컷오버 예정 시간 | `<HH:MM KST>` |
| 운영 메모 | `<NOTES>` |

## 2. 서버 정보

| 항목 | 값 |
|------|----|
| 서버 위치 | `<on-prem / VM / cloud>` |
| 서버 OS | `<Ubuntu version>` |
| 서버 접속 방식 | `<SSH / console / other>` |
| 공인 IP | `<PUBLIC_IP>` |
| 내부 IP | `<PRIVATE_IP_OR_NA>` |
| 운영 계정 | `<USER>` |
| Docker 설치 여부 | `yes / no` |
| Docker Compose 설치 여부 | `yes / no` |

## 3. DNS / 도메인 정보

| 항목 | 값 |
|------|----|
| 루트 도메인 | `decisiondoc.kr` |
| 서브도메인 | `dawool` |
| A 레코드 값 | `<PUBLIC_IP>` |
| DNS 등록 위치 | `<Gabia / other>` |
| `dig +short dawool.decisiondoc.kr` 확인 | `pass / fail / pending` |

## 4. 환경 변수 준비

아래 값은 실제 문자열로 채웁니다. 설명용 표기나 angle bracket은 최종 `.env.prod`에 넣지 않습니다.

| 항목 | 값 | 준비 여부 |
|------|----|-----------|
| `JWT_SECRET_KEY` | `<VALUE>` | `done / pending` |
| `DECISIONDOC_API_KEYS` | `<VALUE>` | `done / pending` |
| `DECISIONDOC_OPS_KEY` | `<VALUE>` | `done / pending` |
| `OPENAI_API_KEY` | `<VALUE>` | `done / pending` |
| `ALLOWED_ORIGINS` | `https://dawool.decisiondoc.kr` | `done / pending` |

## 5. 환경 분리 확인

`admin` 환경과 아래 값이 겹치지 않아야 합니다.

| 항목 | 분리 여부 | 비고 |
|------|-----------|------|
| `JWT_SECRET_KEY` | `yes / no` | |
| `DECISIONDOC_API_KEYS` | `yes / no` | |
| `DECISIONDOC_OPS_KEY` | `yes / no` | |
| OpenAI API 키 | `yes / no / shared-by-policy` | |
| 데이터 볼륨 | `yes / no` | |
| 도메인 | `yes / no` | |

## 6. 배포 실행 기록

| 단계 | 시간 | 결과 | 비고 |
|------|------|------|------|
| 코드 clone 완료 | `<HH:MM>` | `pass / fail` | |
| `.env.prod` 작성 완료 | `<HH:MM>` | `pass / fail` | |
| `scripts/setup.sh` 완료 | `<HH:MM>` | `pass / fail` | |
| `docker build` 완료 | `<HH:MM>` | `pass / fail` | |
| `docker compose up -d` 완료 | `<HH:MM>` | `pass / fail` | |
| `http://localhost:8000/health` 확인 | `<HH:MM>` | `pass / fail` | |
| SSL 발급 완료 | `<HH:MM>` | `pass / fail` | |
| `https://dawool.decisiondoc.kr/health` 확인 | `<HH:MM>` | `pass / fail` | |

## 7. 스모크 테스트 기록

| 항목 | 결과 | 비고 |
|------|------|------|
| `GET /health -> 200` | `pass / fail` | |
| `POST /generate (no key) -> 401` | `pass / fail` | |
| `POST /generate (auth) -> 200` | `pass / fail` | |
| `POST /generate/export (auth) -> 200` | `pass / fail` | |
| 전체 smoke 완료 | `pass / fail` | |

## 8. 컷오버 전 최종 확인

아래 항목이 모두 `yes` 여야 실제 고객 사용 전환을 진행합니다.

| 항목 | 값 |
|------|----|
| DNS 정상 | `yes / no` |
| HTTPS 정상 | `yes / no` |
| app 컨테이너 healthy | `yes / no` |
| nginx 설정 테스트 통과 | `yes / no` |
| smoke 통과 | `yes / no` |
| 운영 로그 확인 | `yes / no` |
| 백업 위치 확인 | `yes / no` |
| 고객 전달 URL 확정 | `yes / no` |

## 9. 고객 전달 정보

| 항목 | 값 |
|------|----|
| 고객 접속 URL | `https://dawool.decisiondoc.kr` |
| 전달 대상자 | `<NAME / ROLE>` |
| 전달 일시 | `<YYYY-MM-DD HH:MM KST>` |
| 전달한 문서 | `<intro pdf / deployment note / other>` |
| 운영자 후속 액션 | `<NEXT_STEP>` |

## 10. 이슈 및 후속 작업

| 이슈 | 우선순위 | 담당자 | 상태 |
|------|----------|--------|------|
| `<ISSUE_1>` | `high / medium / low` | `<OWNER>` | `open / done` |
| `<ISSUE_2>` | `high / medium / low` | `<OWNER>` | `open / done` |

## 11. 운영자 메모

- 실제 `.env.prod`에는 설명용 angle bracket 표기를 넣지 않습니다.
- `DECISIONDOC_API_KEYS`와 `DECISIONDOC_OPS_KEY`는 반드시 다른 값으로 유지합니다.
- `admin`에서 검증된 절차를 그대로 따르되, 고객 전용 키/도메인/데이터 경계를 섞지 않는 것이 최우선입니다.

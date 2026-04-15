# DecisionDoc AI v1 완료 스냅샷

이 문서는 이번 단계에서 무엇을 완료로 봤는지, 무엇을 다음 phase로 넘겼는지 한 번에 정리한 snapshot입니다.

## 이번 단계에서 완료로 보는 범위

- `admin.decisiondoc.kr` 를 단일 canonical 운영 기준선으로 고정
- AWS EC2 + Docker Compose 기준 운영 문서 정리
- `scripts/run_deployed_smoke.py` + `scripts/post_deploy_check.py` 를 운영 release evidence 표준으로 고정
- ops 대시보드의 post-deploy compare / rerun 흐름 확보
- 회사 전달용 sales pack / handoff index 정리
- backup / restore / key custody / SSL renewal 기준선 문서화

## 이번 단계에서 완료로 보지 않는 범위

- `dawool.decisiondoc.kr` live rollout
- AWS SAM `stage-first / promote-only` release lane 실전 전환
- 신규 public API 확장
- 다중 고객사 동시 운영 자동화

## 지금 운영자가 기준으로 삼아야 하는 것

1. 운영 기준 URL은 `https://admin.decisiondoc.kr`
2. 운영 기준 문서는 [Admin v1 Handoff](deployment/admin_v1_handoff.md)
3. 배포 후 evidence 기준은 `./reports/post-deploy/latest.json`
4. 회사 설명 자료는 `python3 scripts/build_sales_pack.py` 로 재생성

## 다음 phase 진입 조건

### A. Dawool rollout

- `dawool` 전용 도메인 확정
- `dawool` 전용 `.env.prod` 준비
- `admin` 과 분리된 API/OPS 키 준비
- 현장 acceptance owner 지정
- admin 기준선 smoke/post-deploy 절차 재사용 가능 확인

### B. AWS release lane 강화

- `dev/stage/prod` 환경 경계 재정리
- promote-only 적용 대상과 운영자 권한 분리 확정
- GitHub Actions evidence를 release close 조건으로 고정
- break-glass 절차와 정상 release lane을 문서와 workflow에서 명확히 분리

## 운영상 해석

- 지금 v1은 “바로 설명하고, 바로 운영 점검할 수 있는 상태”까지 닫은 것입니다.
- 다음 phase는 “고객별 분리 운영과 더 강한 release automation”으로 넘어가는 단계입니다.

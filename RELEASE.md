# Release Guide

이 문서는 현재 DecisionDoc AI v1의 **실제 운영 기준 release path** 를 정리한 문서입니다.

현재 canonical release path:

- 기준 환경: `admin.decisiondoc.kr`
- 서버 기준: AWS EC2 + Docker Compose
- 배포 기준: local build + `scripts/deploy_compose_local.py`
- 증빙 기준: `scripts/run_deployed_smoke.py` + `scripts/post_deploy_check.py`

이번 문서에서 말하는 release는 AWS SAM 장기 roadmap이 아니라, **현재 실제로 운영 가능한 admin baseline release** 입니다.

장기 확장 경로는 [docs/deploy_aws.md](docs/deploy_aws.md) 와 [docs/operating_model_roadmap.md](docs/operating_model_roadmap.md) 를 따릅니다.

## 1. Release 전 확인

- [ ] 작업 브랜치 변경이 `main` 에 반영되어 있다.
- [ ] `git status --short` 기준 불필요한 로컬 변경이 없다.
- [ ] 운영 기준 문서는 [docs/deployment/admin_v1_handoff.md](docs/deployment/admin_v1_handoff.md) 와 현재 구현 상태가 일치한다.
- [ ] sales pack가 최신 상태면 `python3 scripts/build_sales_pack.py` 로 다시 생성할 수 있다.
- [ ] `.env.prod` 값과 운영 키 보관 상태를 확인했다.

## 2. Repo-level 검증

- [ ] 관련 pytest를 다시 실행했다.
- [ ] 필요한 `py_compile` 또는 문법 검증을 다시 실행했다.
- [ ] shell 스크립트가 바뀌었으면 `bash -n` 으로 확인했다.
- [ ] nginx/compose 설정이 바뀌었으면 config syntax 검증 경로를 확인했다.

기본 예시:

```bash
python3 -m py_compile app/ops/service.py app/routers/generate.py app/schemas.py scripts/post_deploy_check.py scripts/build_sales_pack.py
pytest -q tests/test_ops_post_deploy_run.py tests/test_ops_post_deploy_reports.py tests/test_build_sales_pdf.py --tb=short
```

## 3. Admin release 실행

서버 기준 release는 아래 순서를 따릅니다.

```bash
cd /opt/decisiondoc
git pull
python3 scripts/check_prod_env.py --env-file .env.prod --expected-origin https://admin.decisiondoc.kr
python3 scripts/deploy_compose_local.py --env-file .env.prod --image decisiondoc-admin-local --post-check
```

기본 기대 결과:

- Docker image build 성공
- compose rollout 성공
- `scripts/post_deploy_check.py` 성공
- `./reports/post-deploy/latest.json` 갱신

## 4. Release 후 Evidence

아래 4개가 모두 남아야 release를 완료로 봅니다.

1. `https://admin.decisiondoc.kr/health` 응답 정상
2. authenticated generate/export smoke 성공
3. `./reports/post-deploy/latest.json` 갱신
4. 필요하면 ops UI에서 latest/previous compare 확인

직접 확인 명령:

```bash
cd /opt/decisiondoc
python3 scripts/run_deployed_smoke.py --env-file .env.prod
python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy
python3 scripts/show_post_deploy_reports.py --report-dir ./reports/post-deploy --latest
```

## 5. 장애 시 분기

### Admin baseline 문제

아래 순서로 먼저 봅니다.

1. `docker compose --env-file .env.prod -f docker-compose.prod.yml ps`
2. `docker compose --env-file .env.prod -f docker-compose.prod.yml logs app --tail=100`
3. `docker compose --env-file .env.prod -f docker-compose.prod.yml exec nginx nginx -t`
4. `python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy`

### AWS release lane 문제

아래 성격이면 이 문서가 아니라 AWS runbook으로 넘깁니다.

- CloudFormation stack 문제
- Lambda `AccessDeniedException`
- `deploy-smoke` / `deploy` GitHub Actions blocker

참조:

- [docs/deploy_aws.md](docs/deploy_aws.md)
- [docs/deployment/prod_checklist.md](docs/deployment/prod_checklist.md)

## 6. 이번 release에서 제외하는 것

- `dawool` live rollout
- stage-first AWS lane 실제 적용
- 신규 public API 확대

이 범위는 [docs/v1_completion_snapshot.md](docs/v1_completion_snapshot.md) 기준으로 다음 phase에서 진행합니다.

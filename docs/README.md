# DecisionDoc AI — Documentation

## 문서 구조
- `docs/deployment/` — 설치, Docker, SSL, HA 운영 가이드
- `docs/sales/` — 영업/고객 설명용 문서
- `docs/deploy_aws.md` — AWS SAM 및 GitHub Actions 배포 runbook
- `docs/architecture.md` — 시스템 아키텍처 개요
- `docs/openspace_integration.md` — OpenSpace 및 `DESIGN.md` 도입 가이드
- `docs/user_manual.md` — 사용자/운영자 관점 기능 사용법
- `docs/security_policy.md` — 정보보호 정책
- `docs/ingestion_markitdown.md` — 문서 인제션 (MarkItDown)
- `docs/compliance/` — GS인증, CSAP, BCP/DR 등 컴플라이언스 자료

## 빠른 시작
1. [설치 가이드](deployment/install.md)
2. [Docker 배포](deployment/docker.md)
3. [AWS 배포 Runbook](deploy_aws.md)
4. [아키텍처 개요](architecture.md)
5. [OpenSpace 도입 가이드](openspace_integration.md)
6. [사용자 매뉴얼](user_manual.md)
7. [GS인증 준비](compliance/gs_certification_checklist.md)
8. [CSAP 준비](compliance/csap_checklist.md)

## 내부 운영 패키지 (판매/내부 전개 기준)
- 배포 경로 비교 및 선택 기준: [설치 가이드](deployment/install.md)
- Docker 운영 체크리스트: [Docker 배포](deployment/docker.md)
- `admin.decisiondoc.kr` AWS 구축: [AWS EC2 구축 가이드](deployment/admin_aws_ec2_setup.md)
- AWS 운영 Runbook 및 체크리스트: [AWS 배포 Runbook](deploy_aws.md), [prod 체크리스트](deployment/prod_checklist.md)
- 보안/권한/로그 정책 요약: [정보보호 정책](security_policy.md)
- Multi-site 운영 (`admin` + `dawool`): [Multi-site 운영 가이드](deployment/multi_site_operations.md)
- `decisiondoc.kr` DNS 설정: [DNS 설정 가이드](deployment/dns_setup_decisiondoc_kr.md)
- `dawool.decisiondoc.kr` 고객 전용 배포: [Dawool rollout runbook](deployment/dawool_rollout_runbook.md)
- `dawool` 실제 입력값/점검 기록: [Dawool rollout worksheet](deployment/dawool_rollout_worksheet.md)
- `.env.prod` 자동 생성: `python3 scripts/bootstrap_prod_env.py --profile <admin|dawool> --output .env.prod --openai-api-key 'sk-...'`
- `.env.prod` 사전 검증: `python3 scripts/check_prod_env.py --env-file .env.prod --expected-origin https://<site-domain>`
- local build rollout: `python3 scripts/deploy_compose_local.py --env-file .env.prod --image decisiondoc-<site>-local`

## 세일즈/설명 패키지
- [Sales Pack 인덱스](sales/README.md)
- [제품 소개서](sales/product_brief.md)
- [NotebookLM 비교 설명서](sales/notebooklm_comparison.md)
- [내부 설치형 도입 설명서](sales/internal_deployment_brief.md)

## 운영 스모크
- `python3 scripts/smoke.py` — 로컬/직접 환경변수 주입용 기본 API smoke
- `python3 scripts/run_deployed_smoke.py --env-file .env.prod` — 배포 서버 `.env.prod` 기준 API smoke
- `python3 scripts/post_deploy_check.py --env-file .env.prod` — health, compose 상태, nginx 설정, deployed smoke를 묶은 post-deploy check
- `python3 scripts/ops_smoke.py` — ops/investigate smoke
- `python3 scripts/voice_brief_smoke.py` — Voice Brief import smoke
- `python3 scripts/run_ingestion_harness.py <files...>` — 입력 문서 변환 + `/generate` 실행 하네스

## 통합 가이드
- repo-level OpenSpace / `DESIGN.md` 정리: `docs/openspace_integration.md`
- 문서 인제션 하네스: `docs/ingestion_markitdown.md`

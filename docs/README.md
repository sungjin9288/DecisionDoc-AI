# DecisionDoc AI — Documentation

## 문서 구조
- `docs/deployment/` — 설치, Docker, SSL, HA 운영 가이드
- `docs/deploy_aws.md` — AWS SAM 및 GitHub Actions 배포 runbook
- `docs/architecture.md` — 시스템 아키텍처 개요
- `docs/openspace_integration.md` — OpenSpace 및 `DESIGN.md` 도입 가이드
- `docs/user_manual.md` — 사용자/운영자 관점 기능 사용법
- `docs/security_policy.md` — 정보보호 정책
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

## 운영 스모크
- `python3 scripts/smoke.py` — 기본 API smoke
- `python3 scripts/ops_smoke.py` — ops/investigate smoke
- `python3 scripts/voice_brief_smoke.py` — Voice Brief import smoke

## 통합 가이드
- repo-level OpenSpace / `DESIGN.md` 정리: `docs/openspace_integration.md`

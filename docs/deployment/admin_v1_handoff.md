# DecisionDoc AI v1 Admin Handoff

이 문서는 `admin.decisiondoc.kr` 기준 DecisionDoc AI v1을 회사에 넘길 때 사용하는 **canonical handoff index**입니다.

현재 v1에서 지원하는 기준선은 아래 하나로 고정합니다.

- 운영 기준 환경: `admin.decisiondoc.kr`
- 서버 기준: AWS EC2 + Docker Compose
- 운영 검증 기준: `scripts/run_deployed_smoke.py` + `scripts/post_deploy_check.py`
- 회사 설명 자료 기준: `docs/sales/*` + `python3 scripts/build_sales_pack.py`

이번 v1 완료 범위에 **포함되지 않는 것**:

- `dawool.decisiondoc.kr` live rollout
- AWS `stage-first / promote-only` lane 실제 전환
- 신규 public API 기능 확장

## 1. 누가 무엇을 읽는가

| 대상 | 먼저 볼 문서 | 목적 |
|------|--------------|------|
| 총 운영자 | [admin AWS EC2 구축 가이드](./admin_aws_ec2_setup.md) | 기준 배포 경로와 운영 baseline 확인 |
| 총 운영자 | [프로덕션 배포 체크리스트](./prod_checklist.md) | 배포 전/후/장애 시 체크 순서 확인 |
| 총 운영자 | [정보보호 정책](../security_policy.md) | 권한, 키, 로그, 보존 정책 확인 |
| 회사 담당자 | [Sales Pack 인덱스](../sales/README.md) | 소개 자료와 설명 흐름 확인 |
| 회사 담당자 | [회사 전달 가이드](../sales/company_delivery_guide.md) | 실제 전달 순서와 발송 문구 확인 |
| 회사 담당자 | [DecisionDoc AI v1 완료 스냅샷](../v1_completion_snapshot.md) | 이번 완료 범위와 다음 phase 경계 확인 |
| 운영/인수인계 담당자 | [Admin v1.1.59 Acceptance Record 2026-04-30](./admin_v1_1_59_acceptance_20260430.md) | 최신 production release, deploy, smoke, Report Workflow ERP smoke acceptance 증적 확인 |
| 운영/인수인계 담당자 | [Admin v1.1.58 Acceptance Record 2026-04-30](./admin_v1_1_58_acceptance_20260430.md) | 이전 production release governance acceptance 증적 확인 |
| 운영/인수인계 담당자 | [Admin v1 Acceptance Record 2026-04-23](./admin_v1_acceptance_20260423.md) | 회사 전달용 sales PDF pack baseline과 최초 v1 handoff acceptance 증적 확인 |

## 2. 인수인계 실행 순서

1. `admin.decisiondoc.kr` 접속 경로와 운영자 책임자를 먼저 고정합니다.
2. 서버에서 `.env.prod`, SSL, Docker Compose 상태를 [admin AWS EC2 구축 가이드](./admin_aws_ec2_setup.md) 기준으로 점검합니다.
3. 배포 후에는 반드시 아래 evidence를 남깁니다.
   - `python3 scripts/run_deployed_smoke.py --env-file .env.prod`
   - `python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy`
   - `./reports/post-deploy/latest.json`
   - 최신 production acceptance record: [Admin v1.1.59 Acceptance Record 2026-04-30](./admin_v1_1_59_acceptance_20260430.md)
   - 회사 전달 pack baseline: [Admin v1 Acceptance Record 2026-04-23](./admin_v1_acceptance_20260423.md)
   - latest `main` CI green baseline 확인: `GitHub Actions CI run 25160396406 (success)`
4. 운영/API 키 보관 상태를 확인합니다.
   - `DECISIONDOC_API_KEYS`
   - `DECISIONDOC_OPS_KEY`
   - `OPENAI_API_KEY`
5. 회사 설명 자료는 아래 순서로 전달합니다.
   - [미팅용 1장 요약](../sales/meeting_onepager.md)
   - [대표 설명용 소개서](../sales/executive_intro.md)
   - [대표 미팅용 말하기 스크립트](../sales/talk_track.md)
   - [대표 시연 runbook](../sales/demo_runbook.md)
   - [NotebookLM 비교 자료](../sales/notebooklm_comparison.md)
   - [내부 설치형 도입 설명서](../sales/internal_deployment_brief.md)
   - [회사 전달 가이드](../sales/company_delivery_guide.md)
6. PDF가 필요하면 아래 명령으로 다시 생성합니다.

```bash
cd /opt/decisiondoc
python3 scripts/build_sales_pack.py
```

7. 회사 전달 직전에는 handoff readiness gate를 실행합니다.

```bash
cd /opt/decisiondoc
python3 scripts/prepare_company_handoff.py
```

이 명령은 sales PDF pack을 재생성한 뒤 `reports/company-handoff/` 아래 readiness 증적을 남깁니다.

이미 PDF가 있고 readiness만 다시 확인하려면 아래처럼 실행합니다.

```bash
python3 scripts/prepare_company_handoff.py --skip-build
```

PDF를 아직 재생성하기 전 문서 링크와 acceptance 기준만 먼저 확인하려면 아래처럼 실행합니다.

```bash
python3 scripts/check_company_handoff_ready.py --skip-pdf-check --report-dir ./reports/company-handoff
```

기본 증적 경로:

- `reports/company-handoff/latest.json`
- `reports/company-handoff/company-handoff-readiness-<timestamp>.json`

8. 실제 전달 파일을 고정하려면 bundle manifest를 생성합니다.

최종 전달 archive까지 한 번에 만들려면 아래 one-shot command를 사용합니다.

```bash
python3 scripts/package_company_handoff.py --skip-build
```

이 명령은 `prepare -> bundle 생성 -> bundle 검증 -> zip archive 생성 -> package-latest.json 증적 저장`을 순서대로 실행합니다.
`package-latest.json`, bundle `manifest.json`, bundle `README.md`에는 `release_tag`와 별도로 `source_commit`, `source_describe`, `source_exact_tag`, `exact_release_tag`가 기록됩니다.
따라서 tag 이후 handoff 자동화 보강 commit에서 package를 만들더라도, 전달 package가 어떤 실제 source commit에서 만들어졌는지 확인할 수 있습니다.

수동으로 단계별 확인이 필요할 때는 아래 명령을 사용합니다.

```bash
python3 scripts/create_company_handoff_bundle.py --skip-build
```

전달 전/후 bundle 무결성을 다시 검증하려면 아래처럼 실행합니다.

```bash
python3 scripts/verify_company_handoff_bundle.py output/company-handoff/company-handoff-<timestamp>
```

외부 전달용 단일 파일과 checksum을 만들려면 검증된 bundle을 archive로 묶습니다.

```bash
python3 scripts/archive_company_handoff_bundle.py output/company-handoff/company-handoff-<timestamp>
```

기본 bundle 경로:

- `output/company-handoff/company-handoff-<timestamp>/README.md`
- `output/company-handoff/company-handoff-<timestamp>/manifest.json`
- `output/company-handoff/company-handoff-<timestamp>/output/pdf/*.pdf`
- `output/company-handoff/company-handoff-<timestamp>/docs/**`
- `output/company-handoff/company-handoff-<timestamp>/scripts/verify_company_handoff_bundle.py`
- `output/company-handoff/company-handoff-<timestamp>/reports/company-handoff/latest.json`

bundle을 받은 쪽은 bundle root에서 아래 명령만 실행해 manifest와 파일 checksum을 다시 검증할 수 있습니다.

```bash
python3 scripts/verify_company_handoff_bundle.py .
```

전달자는 아래 두 파일을 함께 보관/전달합니다.

- `output/company-handoff/company-handoff-<timestamp>.zip`
- `output/company-handoff/company-handoff-<timestamp>.zip.sha256`
- `reports/company-handoff/package-latest.json`
- bundle `manifest.json`의 `source.exact_release_tag`

기본 산출 경로:

- `output/pdf/decisiondoc_ai_executive_intro_ko.pdf`
- `output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf`
- `output/pdf/decisiondoc_ai_notebooklm_comparison_ko.pdf`
- `output/pdf/decisiondoc_ai_internal_deployment_brief_ko.pdf`
- `output/pdf/decisiondoc_ai_company_delivery_guide_ko.pdf`

## 3. Acceptance 템플릿

아래 표를 실제 handoff 시 복사해서 채웁니다.

| 항목 | 기록값 |
|------|--------|
| 접속 URL | `https://admin.decisiondoc.kr` |
| 운영 기준 서버 | `decisiondoc-admin-prod` |
| 운영자 키 전달 여부 | `yes / no` |
| `.env.prod` preflight 통과 여부 | `pass / fail` |
| deployed smoke 통과 여부 | `pass / fail` |
| post-deploy latest report 경로 | `./reports/post-deploy/latest.json` |
| post-deploy index 경로 | `./reports/post-deploy/index.json` |
| 인수인계 일시 | `YYYY-MM-DD HH:MM KST` |
| 인수인계 담당자 | `기입` |
| 비고 | `기입` |

## 4. Known Limitations / Unsupported Paths

- 현재 v1 canonical deployment는 `admin.decisiondoc.kr` 단일 운영 환경입니다.
- `dawool`은 문서와 worksheet까지만 준비되어 있고, live rollout은 다음 phase입니다.
- AWS SAM `stage-first / prod promote-only` 모델은 roadmap에 반영되어 있지만, 현재 handoff 기준 운영 경로는 아닙니다.
- `POST /ops/post-deploy/run` 은 서버에서 docker/compose 접근이 가능한 host에서만 동작합니다.
- sales PDF 5종은 자동 생성 가능하지만 최종 전달 전 1회 육안 검수를 권장합니다.
- latest repo baseline은 `main` 기준 CI green 상태를 전제로 하지만, 이것이 곧바로 새로운 production deploy를 의미하지는 않습니다.

## 5. 장애 시 Escalation 순서

1. `https://admin.decisiondoc.kr/health` 확인
2. `docker compose --env-file .env.prod -f docker-compose.prod.yml ps`
3. `docker compose --env-file .env.prod -f docker-compose.prod.yml logs app --tail=100`
4. `python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy`
5. 키/권한 문제면 [정보보호 정책](../security_policy.md) 와 [프로덕션 배포 체크리스트](./prod_checklist.md) 기준으로 분리
6. AWS deploy blocker 성격이면 [AWS 배포 Runbook](../deploy_aws.md) 경로로 넘기고, admin EC2 baseline 문제와 섞지 않습니다.

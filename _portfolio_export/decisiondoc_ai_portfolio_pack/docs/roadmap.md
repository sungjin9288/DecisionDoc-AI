# Development Roadmap

분석 기준: 2026-06-09 현재 저장소 코드, README, docs, 설정 파일, 최근 git log, worktree 상태를 기준으로 업데이트했다. 로드맵은 포트폴리오 완성보다 먼저 재현 가능한 검증 evidence 확보를 우선한다.

## 1. 현재 상태 요약

- 현재 구현 완료: FastAPI 앱, 문서 생성 API, bundle catalog, provider/storage abstraction, export service, project/knowledge/approval/history/report workflow 일부, G2B search/fetch, health/metrics, Docker/AWS SAM 설정, pytest/smoke 기반 검증 경로
- 개발 중: report quality learning, document ops agent, correction artifact/training workflow, fine-tune/model registry, post-deploy evidence 자동화
- 미구현: 실제 사용자 성과 수치, 포트폴리오용 데모 영상/스크린샷, 현재 운영 URL 접근 검증 자료, 사용자 피드백 기반 개선 사례
- 검증 필요: live provider chain, production deployment, tenant/SSO/billing 상용 운영성, public demo flow

## 2. Phase 1 - MVP 완성

- 목표: 포트폴리오에서 재현 가능한 핵심 생성 흐름을 안정화한다.
- 해야 할 작업:
  - README를 프로젝트 소개 중심으로 재작성
  - mock provider 기준 로컬 실행 절차와 대표 API 호출 예시 정리
  - `/generate`, `/generate/export`, `/generate/from-documents` 데모 시나리오 확보
  - Web UI 스크린샷과 export 결과 샘플 저장
  - 본인 직접 기여 범위 정리
- 완료 기준:
  - 신규 사용자가 README만 보고 로컬 실행 가능
  - 대표 API smoke 통과
  - 포트폴리오에 첨부할 스크린샷/샘플 산출물 존재
- 산출물:
  - README 개선본
  - demo screenshot
  - sample request/response
  - smoke log

## 3. Phase 2 - 기능 고도화

- 목표: 생성 품질과 프로젝트 지식 재사용 흐름을 강화한다.
- 해야 할 작업:
  - bundle별 대표 golden examples 정리
  - eval/lint 결과를 README와 case study에 반영
  - feedback/report quality correction artifact 흐름을 하나의 데모로 연결
  - live provider chain을 선택적으로 검증
- 완료 기준:
  - 최소 2개 bundle에 대해 생성 결과 샘플과 품질 검증 결과 확보
  - mock provider와 최소 1개 live provider 검증 기록 존재
  - 사용자 피드백 또는 자체 평가 기준 문서화
- 산출물:
  - quality evaluation report
  - before/after sample
  - provider validation note

## 4. Phase 3 - 서비스화 / 배포

- 목표: 로컬 MVP를 외부에서 확인 가능한 배포 상태로 만든다.
- 해야 할 작업:
  - 운영 URL 또는 preview URL 확보
  - 환경변수 template 정리
  - Docker Compose 또는 AWS SAM 배포 절차 재검증
  - post-deploy smoke 결과 저장
  - security header, auth, tenant boundary 점검
- 완료 기준:
  - `/health`와 대표 smoke 통과
  - 데모 URL 또는 영상 제출 가능
  - 민감 정보가 repo와 문서에 노출되지 않음
- 산출물:
  - deployment note
  - post-deploy smoke report
  - demo link or recording

## 5. Phase 4 - 포트폴리오 완성

- 목표: 이력서, GitHub, 면접에서 일관되게 설명 가능한 프로젝트로 정리한다.
- 해야 할 작업:
  - README 최종 정리
  - architecture diagram과 주요 코드 설명 추가
  - issue/PR/commit 기반 개발 과정 정리
  - 면접 답변에서 위험한 표현 제거
  - 직접 구현 범위와 검증된 기능만 이력서 bullet로 반영
- 완료 기준:
  - README, case study, resume bullets, interview story가 서로 모순되지 않음
  - 구현 완료/개발 중/검증 필요가 분리되어 있음
  - 면접에서 코드 파일과 함수명을 기준으로 설명 가능
- 산출물:
  - GitHub README
  - portfolio case study
  - resume bullets
  - interview answer sheet

## 6. 우선순위 높은 다음 작업 5개

| 우선순위 | 작업 | 이유 | 예상 산출물 |
|---|---|---|---|
| 1 | README를 프로젝트 소개용으로 개선 | 현재 README는 운영 규칙 성격이 강해 포트폴리오 첫인상에 부족 | README PR 또는 개선본 |
| 2 | mock provider 기준 로컬 데모 실행 캡처 | 구현 기능을 눈으로 확인할 evidence 필요 | screenshot, sample output |
| 3 | 대표 API smoke 재실행 | 이력서와 README의 실행 가능 주장에 검증 근거 필요 | smoke log |
| 4 | 직접 구현 범위 정리 | 면접에서 본인 기여를 명확히 설명해야 함 | contribution note |
| 5 | live provider 또는 배포 URL 검증 | 운영/배포 표현을 쓰려면 현재 접근성 evidence 필요 | provider/deploy validation note |

# DecisionDoc AI 정보보호 정책

## 1. 목적
DecisionDoc AI의 정보 자산을 보호하고 서비스 연속성을 유지한다.

## 2. 범위
본 정책은 DecisionDoc AI 플랫폼의 모든 구성 요소에 적용된다.

## 3. 보안 원칙
- **최소 권한**: 업무 수행에 필요한 최소한의 권한만 부여
- **심층 방어**: 다중 보안 레이어 적용
- **감사 추적**: 모든 중요 행위의 로그 기록 및 보존
- **암호화 우선**: 민감 데이터는 저장 및 전송 시 암호화

## 4. 접근 통제
- 사용자 인증: JWT 토큰 (8시간 만료)
- 역할 기반 접근: admin / member / viewer
- 로그인 실패: 15분 내 10회 초과 시 차단
- 세션: 30일 이후 재인증 필요

## 5. 암호화 기준
- 전송: TLS 1.2 이상
- 비밀번호: bcrypt (rounds=12)
- SSO 시크릿: Fernet authenticated encryption (PBKDF2 키 유도)
- JWT: HS256 (최소 32바이트 키)

## 6. 로그 보존
- 감사 로그: 최소 1년 보존
- 접근 로그: 90일 보존
- 로그 무결성: Append-only, 삭제/수정 불가

## 6.1 운영 권한/로그 정책 요약 (구현 기준)
- 배포 권한
  - AWS 경로는 GitHub OIDC deploy role로 `deploy` / `deploy-smoke` workflow만 허용
  - 운영자 CLI/콘솔은 진단·복구 전용 (무분별한 prod 재배포 금지)
- 런타임 인증 키
  - `DECISIONDOC_API_KEY` / `DECISIONDOC_API_KEYS` (API 인증)
  - `DECISIONDOC_OPS_KEY` (`/ops/*` 보호)
  - `/admin/tenants`를 포함한 admin endpoint는 인증된 admin JWT 또는 설정된 Ops key 중 하나를 요구한다. Ops UI는 공통 인증 header 조합을 사용해 로그인 세션을 보존하며 두 자격 증명을 동시에 요구하지 않는다.
  - Browser tenant header는 signed access token의 tenant claim과 동기화한다. JWT tenant와 다른 selector 전환은 access preflight에서 거부하고 기존 tenant로 rollback하며, admin JWT도 `TENANT_MISMATCH`를 우회하지 않는다.
  - DocumentOps 미저장 review draft는 사용자·tenant·trajectory page-memory key로만 유지하고 logout 또는 invalid session에서 폐기한다. localStorage와 server/audit에는 draft 본문을 저장하지 않는다.
- 계정·초대 상태
  - 사용자와 초대 record는 local `data/tenants/<tenant_id>/{users,invites}.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant를 path 선택 전에 검증하고 손상 document, duplicate key, owned identity·role·timestamp drift와 duplicate username은 인증·등록·초대 수락과 후속 변경을 중단한다. Explicit foreign record는 현재 tenant에 노출하거나 인증에 사용하지 않고 원본에 보존한다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 초대 메일 전달은 현재 보장 범위가 아니다.
- 사용자 템플릿 상태
  - 재사용 문서 입력은 local `data/tenants/<tenant_id>/templates.jsonl` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant를 path 선택 전에 검증하고 malformed JSON, duplicate key, non-object·owned malformed record와 duplicate template identity는 조회와 후속 변경을 중단한다. Explicit foreign record는 현재 tenant에 노출하거나 변경하지 않고 보존하며 기존 tenant 미표기 record는 path ownership으로 읽는다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap은 현재 보장 범위가 아니다.
- 생성 이력 상태
  - 생성 문서의 재열기·즐겨찾기·시각자료·지식 승격 이력은 local `data/tenants/<tenant_id>/history.jsonl` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant를 path 선택 전에 검증하고 malformed JSON, duplicate key, non-object·owned malformed record와 duplicate entry identity는 조회와 후속 변경을 중단한다. Explicit foreign record는 현재 tenant에 노출하거나 변경하지 않고 보존하며 기존 tenant 미표기 record는 path ownership으로 읽는다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap은 현재 보장 범위가 아니다.
- 프로젝트 지식 상태
  - 참고 문서 index, 본문과 style profile은 local `data/tenants/<tenant_id>/knowledge/<project_id>/` 또는 같은 relative path의 S3 state object에 저장한다.
  - Tenant/project identity와 exact metadata schema를 검증하고 본문·style bytes를 size와 SHA-256으로 index에 결속한다. Malformed/invalid UTF-8 JSON, duplicate key·identity, missing·unexpected·orphan object와 binding drift는 knowledge API, generation context, procurement 평가, report promotion을 중단하며 원본 bytes를 보존한다.
  - 동일 process의 read-modify-write는 logical index 기준 shared lock으로 직렬화한다. 여러 S3 object를 아우르는 distributed transaction/compare-and-swap은 현재 보장 범위가 아니다.
- G2B 즐겨찾기 상태
  - 공고 즐겨찾기는 local `data/tenants/<tenant_id>/g2b_bookmarks.json` 또는 같은 relative path의 S3 state object에 저장한다. 내부 owner metadata는 현재 tenant/user로 기록하고 API 응답에서는 제거한다.
  - Tenant와 user bucket을 state 접근 전에 검증한다. Malformed/invalid UTF-8 JSON, duplicate key, invalid collection, owned record와 duplicate bid identity는 조회와 후속 추가·삭제를 중단하며 원본 bytes를 보존한다. Explicit foreign owner는 현재 user에게 노출하거나 변경하지 않는다.
  - 독립 store 인스턴스의 read-modify-write는 process-local logical state lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 G2B API 성공은 현재 보장 범위가 아니다.
- 공공조달 판단 상태
  - 판단 record는 `data/tenants/<tenant_id>/procurement_decisions.json`, source snapshot은 `data/tenants/<tenant_id>/procurement_snapshots/<project_id>/<snapshot_id>.json` 또는 같은 relative path의 S3 object에 저장한다.
  - Tenant/project, snapshot metadata ID와 storage path를 다시 대조한다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key·snapshot metadata, 비직렬화 payload와 non-finite number는 조회나 write를 중단하며 기존 bytes를 덮어쓰지 않는다. Explicit foreign decision은 현재 tenant의 판단 근거로 노출하거나 변경하지 않는다.
  - 판단 record의 read-modify-write는 backend logical object 기준 process-local lock으로 직렬화한다. Snapshot 검증은 persisted path와 JSON 구조의 무결성 범위이며 외부 원천 데이터의 의미적 진위, distributed S3 compare-and-swap과 실제 G2B/provider 성공은 현재 보장 범위가 아니다.
- 공공조달 검토 증빙 상태
  - Review record·원본 packet·reviewed-package는 local `data/tenants/<tenant_id>/procurement_reviews/<project_id>/<packet_sha256>/` 또는 같은 relative path의 S3 object에 저장한다.
  - Tenant/project/packet SHA-256과 exact record/receipt schema, packet receipt, completed package의 embedded receipt·manifest를 다시 대조한다. Blank·malformed·invalid UTF-8·duplicate key/identity, artifact 누락·변조·semantic drift와 backend failure는 검토함 조회·완료·다운로드·downstream generation을 중단하며 원본 bytes를 보존한다.
  - Prepare는 exact orphan packet만 재사용하고 completion은 content-addressed immutable package를 만든 뒤 record를 CAS로 전환한다. Local conditional file lock/atomic write와 S3 `If-None-Match`/ETag `If-Match`를 사용하고 불확실 commit은 read-back으로 조정한다. Persisted 오류는 domain 입력 충돌과 분리해 API에서 `500 INTERNAL_ERROR`로 처리한다. Multi-object distributed transaction, 실제 AWS/provider/G2B/입찰 실행은 현재 보장 범위가 아니다.
- Decision Council 상태
  - 조달 의사결정 session은 local `data/tenants/<tenant_id>/decision_council_sessions.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - Caller tenant와 persisted tenant, project/use-case/bundle로 계산한 canonical session key를 다시 대조한다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key와 owned session ID/key 중복은 조회·revision 갱신을 중단하며 원본 bytes를 보존한다. 기존 foreign·malformed record는 현재 tenant의 의사결정 근거로 사용하지 않는다.
  - Local/S3 write는 모두 앱이 선택한 backend를 통하고 process-local logical state lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 provider/G2B 성공은 현재 보장 범위가 아니다.
- 프로젝트·결재 상태
  - 프로젝트와 결재 record는 local `data/tenants/<tenant_id>/{projects,approvals}.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - Tenant와 owned project/approval identity를 state 접근 전에 검증한다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key/identity와 유효한 owned ID의 schema drift는 조회·결재 전이·후속 변경을 중단하며 원본 bytes를 보존한다. Explicit foreign record와 owned ID가 없는 기존 malformed record는 현재 tenant에 노출하거나 변경하지 않은 채 보존한다.
  - 독립 store 인스턴스의 read-modify-write는 backend logical object 기준 process-local lock으로 직렬화한다. `ProjectStore`와 `ApprovalStore`는 local conditional write와 S3 conditional create/ETag CAS를 추가로 사용하고, 충돌마다 최신 state의 ownership·schema를 다시 검증한다. Approval transition도 재검증해 worker 간 project/document/approval overwrite와 competing terminal decision을 차단한다. Project는 API에 노출하지 않는 최근 mutation ID를 64개까지 보존해 record가 남아 있는 후속 CAS 뒤에도 불확실한 commit을 조정하며 receipt 손상은 fail closed 처리한다. Approval은 exact payload read-back을 사용하고 persisted state 오류는 transition 입력 오류와 구분해 API에서 `500 INTERNAL_ERROR`로 처리한다.
  - CAS는 각각 tenant별 단일 project 또는 approval state object 범위다. 두 state object를 함께 묶는 multi-object distributed transaction과 실제 AWS runtime은 현재 보장 범위가 아니다.
- 보고서 워크플로우 상태
  - 기획·장표·시각자료·승인·승격 state는 local `data/tenants/<tenant_id>/report_workflows.json` 또는 같은 relative path의 S3 object에 저장한다.
  - Tenant와 workflow/nested identity를 state 접근 전에 검증한다. Blank·malformed·invalid UTF-8·non-list JSON, duplicate key/identity, owned schema drift와 backend failure는 조회와 후속 변경을 중단하며 원본 bytes를 보존한다.
  - 독립 store 인스턴스의 read-modify-write는 backend logical object 기준 process-local lock으로 직렬화하고, worker 간 mutation은 local conditional write 또는 S3 conditional create/ETag CAS로 확정한다. 충돌마다 최신 ownership·schema·transition을 다시 검증하며 최근 mutation receipt를 최대 64개 보존해 commit 응답 유실 뒤 후속 CAS도 조정한다. Persisted 오류와 손상 receipt는 domain 입력 오류와 구분해 API에서 `500 INTERNAL_ERROR`로 처리한다. 이 보장은 tenant별 단일 report workflow state object 범위이며 실제 AWS runtime과 multi-object transaction은 현재 보장 범위가 아니다.
- 회의 녹음 상태
  - 녹음 metadata와 audio는 local `data/tenants/<tenant_id>/meeting_recordings/<project_id>/<recording_id>/` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant/project/recording identity와 canonical audio path를 state 접근 전에 검증한다. Malformed metadata와 duplicate key는 조회·전사·승인을 중단하고 explicit foreign metadata는 현재 scope에 노출하지 않는다. Audio read는 persisted size와 SHA-256을 실제 bytes와 다시 대조한다.
  - 독립 store 인스턴스의 create와 transcript/approval 변경은 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 OpenAI transcription 성공은 현재 보장 범위가 아니다.
- 결제 권한 상태
  - plan, account status와 Stripe identity는 local `data/tenants/<tenant_id>/billing.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant와 exact account schema를 state 접근 전에 검증한다. Malformed JSON, duplicate key, tenant/plan/status/timestamp drift는 조회와 후속 변경을 중단하며 원본 bytes를 보존한다. Metered request는 tenant/auth context 확정 뒤 상태를 확인하고 검증 실패 시 `503`으로 차단한다.
  - `DECISIONDOC_ENV=prod` 또는 production 환경에서는 `STRIPE_WEBHOOK_SECRET`이 없으면 webhook 처리를 거부한다. Secret이 설정된 webhook만 JWT 예외로 진입하며 원본 payload HMAC, 5분 timestamp와 복수 `v1` 서명을 검증한다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 Stripe checkout, cancel, provider-delivered webhook 성공은 현재 보장 범위가 아니다.
- 사용량 계량 상태
  - Tenant usage event는 local `data/tenants/<tenant_id>/usage.jsonl` 또는 같은 relative path의 S3 state object에 기록하고 monthly summary는 `usage_summary.json`에 저장한다. Event log가 권위 원본이고 summary는 event coverage와 aggregate가 일치해야 하는 파생 상태다.
  - Malformed/invalid UTF-8 JSON/JSONL, blank line, duplicate key/event ID, owned field/type/token/timestamp drift, summary coverage·aggregate 불일치와 event-only partial write는 한도 검사와 후속 기록을 중단하고 원본 bytes를 보존한다. Current-month foreign summary collision도 빈 사용량으로 축소하지 않는다.
  - Generation·DocumentOps·meeting transcription·knowledge·G2B·style·procurement·report workflow·admin expansion의 provider-backed route는 tenant별 process-local admission lock 안에서 billing/usage 상태와 한도를 먼저 검사한다. Direct provider 작업은 generation event로 남기고 실제 provider를 호출한 OCR·visual 작업은 실패 token까지 합산한 auxiliary event로 남긴다. DocumentOps는 provider를 요청별로 분리하고 provider 호출 직후 usage durability를 확정한 뒤 trajectory를 저장하며 core generation은 bundle/cache/render/background eval보다 metering durability를 먼저 확정한다. 취소된 rewrite/stream worker의 provider 작업이 끝나기 전에는 admission lock을 반환하지 않고 provider 오류 원문은 public response·상태·observability log에 남기지 않는다. `/billing/usage`는 인증된 user만 조회한다.
  - Preflight 검증 실패는 `BILLING_STATE_UNAVAILABLE`, provider 호출 후 usage write 실패는 `USAGE_STATE_UNAVAILABLE` 503으로 종료한다. SSE stream은 response 시작 후 실패를 같은 code의 error event로 정규화하고 내부 상태 문구를 노출하지 않는다.
  - Event/summary write와 request admission은 한 process 안에서 직렬화한다. 취소된 admission waiter는 획득한 lock을 자동 반환하고, SSE client가 연결을 먼저 끝내도 worker가 종료하기 전에 lock을 풀지 않는다. Provider visual을 새로 만들지 않는 edited export와 실제 `max_assets` 범위 밖 provider image는 생성 한도와 provider 초기화에서 분리한다. 두 S3 object를 아우르는 distributed transaction/CAS, 여러 Lambda 인스턴스 간 exact reservation은 현재 보장 범위가 아니다.
- SSO 설정 상태
  - LDAP, SAML, GCloud, OAuth2 설정은 local `data/tenants/<tenant_id>/sso_config.json` 또는 같은 relative path의 S3 state object에 저장한다. Secret은 PBKDF2로 유도한 Fernet key로 암호화하며 복호화 실패를 암호문 평문 fallback으로 처리하지 않는다.
  - Tenant와 exact nested schema를 검증한다. Malformed JSON, duplicate key, unknown provider, type/timestamp drift와 올바르지 않은 암호문 형식은 조회와 후속 변경을 중단하고 원본 bytes를 보존한다. Explicit foreign 설정은 현재 tenant에 노출하거나 덮어쓰지 않고, tenant 필드 없는 기존 파일은 path ownership으로 읽는다.
  - Admin update는 strict Pydantic schema를 사용하고 masked secret 재전송은 기존 암호문을 유지한다. GCloud state와 SAML RelayState는 constant-time 비교하며 SAML ACS는 IdP certificate와 signed assertion 검증을 요구한다. Verifier가 없으면 인증을 거부한다.
  - 독립 store 인스턴스의 partial update는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 LDAP/SAML/GCloud 로그인 성공은 현재 보장 범위가 아니다.
- 스타일 프로필 상태
  - tone guide, bundle override, 분석 예시와 default/system metadata는 local `data/tenants/<tenant_id>/style_profiles.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant와 owned profile의 exact schema를 state 접근 전에 검증한다. Malformed JSON, duplicate key, identity/timestamp drift, duplicate example ID와 multiple default는 조회·prompt build와 후속 변경을 중단하며 원본 bytes를 보존한다. Explicit foreign record는 현재 tenant에 노출하거나 변경하지 않고 보존한다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 실제 provider 기반 style analysis 성공은 현재 보장 범위가 아니다.
- 품질 학습 상태
  - 사용자 feedback, eval evidence, runtime prompt override, A/B prompt experiment와 request pattern은 local `data/tenants/<tenant_id>/{feedback.jsonl,eval_results.jsonl,prompt_overrides.json,ab_tests.json,request_patterns.jsonl}` 또는 같은 relative path의 S3 state object에 저장한다.
  - Tenant와 owned record schema를 state 접근 전에 검증한다. Malformed/invalid UTF-8 JSON/JSONL, duplicate key·identity, identity/type/timestamp/score drift는 dashboard·eval·feedback·A/B·request-pattern API와 생성 prompt build, 후속 변경을 중단하며 원본 bytes를 보존한다. Explicit foreign record는 현재 tenant에 노출하거나 변경하지 않고 보존하며 tenant 필드 없는 기존 record는 path ownership으로 읽는다.
  - A/B winner prompt override를 먼저 저장하고 성공한 경우에만 experiment를 concluded로 기록한다. Override 저장 실패는 active experiment를 유지하고 오류를 상위 호출자에 전달한다.
  - Fine-tune dataset/export와 model registry도 같은 tenant의 local/S3 state object에 저장한다. Dataset, export metadata/content와 model lifecycle schema를 fail closed로 검증하고 export size/SHA-256, request/model/provider-job identity를 중복 없이 결속한다. 손상된 registry를 active model 없음으로 축소하지 않으며 provider job 성공 모델은 promotion eval을 마치기 전까지 inactive로 유지한다.
  - 자동 provider training은 기본값 `FINETUNE_AUTO_ENABLED=0`이고 opt-in과 threshold를 모두 만족해야 한다. Orchestrator는 명시적 execution authority가 없는 호출에서 dataset upload와 provider job creation을 수행하지 않는다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap은 현재 보장 범위가 아니며 실제 provider API, dataset upload, training execution, external job polling과 model promotion은 별도 운영 승인 범위다.
- 공개 공유 상태
  - share link는 local `data/tenants/<tenant_id>/shares.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant를 path 선택 전에 검증하고 blank·malformed·non-object JSON, duplicate key, owned malformed record와 storage key/share ID drift는 공개 조회와 후속 생성·접근 횟수·취소 변경을 중단한다. Explicit foreign record는 현재 tenant에 노출하거나 변경하지 않고 보존하며 기존 tenant 미표기 record는 path ownership으로 읽는다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 운영 URL의 외부 접근성은 현재 보장 범위가 아니다.
- 감사 로그 저장
  - 저장 위치: local `data/tenants/<tenant_id>/audit_logs.jsonl` 또는 같은 relative path의 S3 state object
  - tenant와 log identity를 append 전에 검증하고 기존 JSONL byte prefix를 보존한다. 손상·foreign·중복 evidence는 자동 복구하거나 건너뛰지 않고 read와 append를 중단한다.
  - 독립 store 인스턴스의 동시 append는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap은 현재 보장하지 않는다.
  - 조회/내보내기: `GET /admin/audit-logs`, `GET /admin/audit-logs/export`
  - 조회와 CSV 내보내기는 tenant와 action/result/기간 filter를 공유한다. 조회는 검증된 offset/limit과 전체 건수·다음 페이지 여부를 반환하고, CSV는 전체 detail JSON을 보존하며 spreadsheet formula injection이 가능한 문자열을 text cell로 처리
- 협업 상태 저장
  - 메시지와 알림은 local `data/tenants/<tenant_id>/{messages,notifications}.json` 또는 같은 relative path의 S3 state object에 저장한다.
  - tenant를 path 선택 전에 검증하고 손상 document, duplicate JSON key와 owned duplicate identity는 조회와 후속 변경을 중단한다. Explicit foreign record는 현재 tenant에 노출하거나 변경하지 않고 원본에 보존한다.
  - 독립 store 인스턴스의 read-modify-write는 process-local shared lock으로 직렬화한다. Distributed S3 compare-and-swap과 외부 SMTP·Slack 전달 성공은 현재 보장 범위가 아니다.
- 운영 로그
  - 애플리케이션 구조화 로그는 stdout 기준 (Docker는 `docker logs`, AWS는 CloudWatch)

## 7. 취약점 관리
- 정기 점검: 분기별 OWASP 점검
- 의존성: 주간 Safety check (CI/CD)
- 패치: 고위험 취약점 72시간 내 패치

## 8. 사고 대응
1. 탐지 및 분류 (1시간)
2. 격리 및 초기 대응 (4시간)
3. 원인 분석 및 복구 (24시간)
4. 재발 방지 대책 수립 (72시간)

## 9. 개정 이력
| 버전 | 날짜 | 내용 |
|------|------|------|
| 1.0 | 2025-03 | 최초 작성 |

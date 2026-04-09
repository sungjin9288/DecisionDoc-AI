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
- SSO 시크릿: AES-256 (PBKDF2 키 유도)
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
- 감사 로그 저장
  - 파일 저장 위치: `data/tenants/<tenant_id>/audit_logs.jsonl`
  - 조회/내보내기: `GET /admin/audit-logs`, `GET /admin/audit-logs/export`
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

# CSAP (클라우드서비스 보안인증) 체크리스트
## DecisionDoc AI — SaaS 보안인증 준비
> 근거: 클라우드컴퓨팅 발전 및 이용자 보호에 관한 법률 제23조의2

---

## 관리적 보호조치

### 정보보호 정책
| 통제항목 | 현황 | 구현 위치 |
|---------|------|-----------|
| 정보보호 정책 수립 | 🔶 문서화 필요 | docs/security_policy.md |
| 임직원 보안 서약 | 🔶 절차 수립 필요 | - |
| 보안 교육 | 🔶 계획 수립 필요 | - |

### 접근 관리
| 통제항목 | 현황 | 구현 위치 |
|---------|------|-----------|
| 계정 관리 | ✅ 사용자 CRUD | admin/users |
| 권한 관리 | ✅ RBAC (admin/member/viewer) | auth.py |
| 비밀번호 정책 | ✅ 8자+숫자+문자 | user_store.py |
| 접근 기록 | ✅ 감사 로그 | audit_store.py |
| 세션 관리 | ✅ JWT 8h 만료 | auth_service.py |
| SSO 지원 | ✅ LDAP/SAML | sso/ |

---

## 기술적 보호조치

### 암호화
| 통제항목 | 현황 | 구현 |
|---------|------|------|
| 전송 암호화 | ✅ TLS 1.2+ (Nginx) | nginx/nginx.conf |
| 저장 암호화 | ✅ AES-256 (SSO secrets) | sso_store.py |
| 비밀번호 해시 | ✅ bcrypt rounds=12 | user_store.py |
| JWT 서명 | ✅ HS256 | auth_service.py |

### 취약점 관리
| 통제항목 | 현황 | 구현 |
|---------|------|------|
| OWASP Top 10 대응 | ✅ 23개 취약점 수정 | security_headers.py |
| 보안 헤더 | ✅ CSP/HSTS/X-Frame | security_headers.py |
| SAST 자동화 | ✅ Bandit (CI/CD) | .github/workflows/ci.yml |
| 의존성 점검 | ✅ Safety check | CI/CD |
| Rate Limiting | ✅ 로그인 10회/15분 | rate_limit.py |

### 로깅 및 모니터링
| 통제항목 | 현황 | 구현 |
|---------|------|------|
| 접근 로그 | ✅ Nginx + Audit | audit_store.py |
| 이상 접근 탐지 | ✅ 의심 IP 집계 | /admin/audit-logs/failed-logins |
| 로그 무결성 | ✅ Append-only JSONL | audit_store.py |
| 로그 보존 | 🔶 30일 기본, 정책 수립 필요 | audit_store.delete_old() |

### 가용성
| 통제항목 | 현황 | 구현 |
|---------|------|------|
| 이중화 | 🔶 단일 인스턴스 → 수평 확장 필요 | docker-compose |
| 백업 | ✅ 수동/정기 백업 스크립트 + 배포 전 백업 | scripts/backup.sh, scripts/deploy.sh |
| 복구 절차 | ✅ 복구 스크립트와 BCP/DR 문서 존재 | scripts/restore.sh, docs/compliance/bcp_drp.md |
| 헬스체크 | ✅ /health readiness probe | main.py |

---

## 물리적 보호조치
| 통제항목 | 현황 | 비고 |
|---------|------|------|
| 데이터센터 보안 | 🔶 클라우드 제공자 의존 | AWS/NCP 활용 시 |
| 망분리 | 🔶 요구 시 구현 필요 | VPC 설계 |

---

## CSAP 준비 로드맵

### 즉시 (1개월)
- [ ] 정보보호 정책 문서 작성
- [ ] 개인정보처리방침 수립
- [ ] 보안 서약서 양식 준비

### 단기 (3개월)
- [ ] 이중화 구성 (Primary/Standby)
- [ ] RTO 4시간 / RPO 24시간 목표 설정
- [ ] 재해복구 훈련 절차 수립
- [ ] 개인정보 영향평가 (PIA)

### 중기 (6개월)
- [ ] CSAP 컨설팅 업체 선정
- [ ] 현장 심사 준비
- [ ] 인증 신청 (KISA)

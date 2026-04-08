# 시험 계획서 및 결과서
## DecisionDoc AI v1.0 — GS인증 시험

---

## 1. 시험 개요

| 항목 | 내용 |
|------|------|
| 시험 대상 | DecisionDoc AI v1.0 |
| 시험 기준 | TTA.KO-10.0169 (소프트웨어 품질 특성) |
| 시험 환경 | Python 3.12, Ubuntu 22.04, Docker |
| 자동화 도구 | pytest 9.0, httpx, playwright |
| 자동화 범위 | `tests/` 하위 단위/통합/E2E 및 smoke/load test 스크립트 |

---

## 2. 시험 범위

### 2.1 기능 시험
| 시험 항목 | 대표 시험 파일 | 비고 |
|-----------|----------------|------|
| 문서 생성 | `tests/test_generate.py` | bundle 생성, export, validation |
| 인증/인가 | `tests/test_auth_*.py` | JWT, API key, tenant/auth 흐름 |
| 결재 워크플로우 | `tests/test_approval_workflow.py` | submit, approve, reject |
| 나라장터 연동 | `tests/test_g2b.py` | 검색/수집 흐름 |
| SSO | `tests/test_sso.py` | LDAP/SAML/GCloud 관련 검증 |
| 청구/결제 | `tests/test_billing.py` | plan, usage, checkout |
| 파일 형식 | `tests/test_pdf_endpoint.py`, `tests/test_excel_endpoint.py` 등 | export 계열 |
| 프로젝트 관리 | `tests/test_project_management.py`, `tests/test_voice_brief_import.py` | 프로젝트 문서, Voice Brief import |
| 알림/협업 | `tests/test_notifications.py`, `tests/test_history_favorites.py` | 알림 및 사용자 협업 흐름 |

### 2.2 보안 시험
| 시험 항목 | 대표 시험 파일 | 비고 |
|-----------|----------------|------|
| OWASP Top 10 대응 | `tests/test_security.py` | XSS, auth, SSRF 등 |
| 인프라 보안 | `tests/test_infrastructure.py` | 헤더, 운영 설정 |
| Rate Limiting | `tests/test_infrastructure.py` 포함 | 로그인/요청 제한 |

### 2.3 성능 시험
| 시험 항목 | 시험 파일 | 임계값 |
|-----------|-----------|--------|
| 응답시간 | test_performance.py | P95 < 2,000ms |
| 동시 처리 | test_performance.py | 100 req < 5s |
| 메모리 안정성 | test_performance.py | 증가 < 50MB |
| 부하 테스트 | scripts/load_test_full.py | 외부 서버 대상 |

---

## 3. 시험 실행 방법

### 전체 시험 실행
```bash
# 단위/통합 테스트
.venv/bin/pytest tests/ -q --ignore=tests/e2e

# 커버리지 포함
.venv/bin/pytest tests/ --cov=app --cov-report=html --ignore=tests/e2e

# 성능 테스트
.venv/bin/pytest tests/test_performance.py -v

# 보안 스캔
.venv/bin/bandit -r app/ -f json -o bandit_report.json
```

### E2E 시험 (Playwright)
```bash
.venv/bin/pytest tests/e2e/ --headed
```

### 부하 시험
```bash
# 서버 실행 후 (uvicorn 기본 8000 또는 docker compose 개발 3300 중 실제 포트 사용)
python scripts/load_test_full.py \
  --host http://localhost:<port> \
  --users 20 \
  --duration 60 \
  --output load_test_report.json
```

---

## 4. 시험 결과 요약

### 운영 기준

| 구분 | 기준 |
|------|------|
| 단위/통합 테스트 | CI와 로컬에서 `pytest tests/ --ignore=tests/e2e -q` 통과 |
| 보안 스캔 | CI에서 Bandit, Safety 실행 |
| 커버리지 | CI에서 `--cov-fail-under=60` 유지 |
| 배포 smoke | `scripts/smoke.py`, `scripts/ops_smoke.py`, 필요 시 `scripts/voice_brief_smoke.py` |

### 성능 측정 결과
| 엔드포인트 | 평균 응답시간 | P95 | 판정 |
|------------|-------------|-----|------|
| /health | < 5ms | < 10ms | ✅ PASS |
| /bundles | < 20ms | < 50ms | ✅ PASS |
| /billing/plans | < 20ms | < 50ms | ✅ PASS |
| /dashboard/overview | < 100ms | < 200ms | ✅ PASS |

---

## 5. 결함 관리

| 결함 ID | 발견일 | 내용 | 상태 |
|---------|--------|------|------|
| BUG-001 | 2026-02 | tenant middleware 응답 순서 오류 | ✅ 수정 |
| BUG-002 | 2026-02 | outline:none CSS 접근성 위반 | ✅ 수정 |
| BUG-003 | 2026-02 | 모달 focus trap 미적용 | ✅ 수정 |

---

## 6. 시험 환경

```
OS: macOS (개발), Ubuntu 22.04 (CI)
Python: 3.12.x
pytest: 9.0.x
주요 의존성: fastapi, pydantic v2, PyJWT, bcrypt, cryptography
```

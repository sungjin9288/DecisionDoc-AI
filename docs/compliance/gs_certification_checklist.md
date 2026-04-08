# GS인증 (Good Software) 체크리스트
## DecisionDoc AI v1.0 — 소프트웨어품질인증
> 근거: TTA.KO-10.0169 (소프트웨어 품질 특성 및 시험방법)

---

## 1. 기능성 (Functionality)

### 1.1 적합성
| 항목 | 구현 상태 | 위치 |
|------|-----------|------|
| 공문서 생성 기능 | ✅ 구현 | app/bundle_catalog/bundles/ |
| 나라장터 연동 | ✅ 구현 | app/services/g2b_collector.py |
| 행안부 표준 양식 | ✅ 구현 | app/services/docx_service.py |
| 결재 워크플로우 | ✅ 구현 | app/storage/approval_store.py |
| 다중 파일 형식 지원 | ✅ HWP/DOCX/PDF/XLSX | app/services/ |

### 1.2 정확성
| 항목 | 구현 상태 |
|------|-----------|
| LLM 출력 검증 (lints) | ✅ app/eval/lints.py |
| JSON 스키마 검증 | ✅ app/eval/eval_store.py |
| 자동 재시도 (저품질) | ✅ generation_service.py |

### 1.3 보안성
| 항목 | 구현 상태 | 비고 |
|------|-----------|------|
| 인증/인가 | ✅ JWT + RBAC | app/middleware/auth.py |
| SSO 지원 | ✅ LDAP/SAML/G-Cloud | app/services/sso/ |
| 감사 로그 | ✅ Append-only JSONL | app/storage/audit_store.py |
| 데이터 암호화 | ✅ AES-256 (SSO secrets) | app/storage/sso_store.py |
| SQL Injection 방어 | ✅ N/A (NoSQL) | JSONL/JSON 사용 |
| XSS 방어 | ✅ escapeHtml() | app/static/index.html |
| CSRF 방어 | ✅ SameSite=Lax | auth_service.py |

---

## 2. 신뢰성 (Reliability)

### 2.1 성숙성
| 항목 | 수치 | 위치 |
|------|------|------|
| 테스트 커버리지 | 목표 70%+ | pytest --cov |
| 총 테스트 수 | 1231개 | tests/ |
| 자동화 테스트 | ✅ CI/CD (GitHub Actions) | .github/workflows/ |

### 2.2 결함 허용성
| 항목 | 구현 상태 |
|------|-----------|
| LLM 재시도 (3회 backoff) | ✅ generation_service.py |
| 저품질 자동 재생성 | ✅ heuristic_score < 0.6 |
| JSON 손상 복구 | ✅ 모든 Store |
| 백그라운드 태스크 격리 | ✅ ThreadPoolExecutor |

### 2.3 회복성
| 항목 | 구현 상태 |
|------|-----------|
| Graceful shutdown | ✅ lifespan() drain |
| Health check endpoint | ✅ /health (readiness) |
| 서비스 중단 없는 배포 | ✅ Docker rolling update |

---

## 3. 사용성 (Usability)
| 항목 | 구현 상태 |
|------|-----------|
| 한국어 UI | ✅ 전면 한국어 |
| 온보딩 가이드 | ✅ 첫 방문 모달 |
| 모바일 지원 | ✅ PWA + 반응형 |
| 접근성 | 🔶 부분 (role/tabindex 미완) |
| 오프라인 지원 | ✅ Service Worker |
| 키보드 단축키 | ✅ Cmd+Enter 등 |

---

## 4. 효율성 (Efficiency)

### 4.1 시간 효율성
| 항목 | 목표 | 측정 방법 |
|------|------|-----------|
| API 응답시간 (P95) | < 2,000ms | scripts/load_test_full.py |
| 문서 생성 시간 | < 60s | SSE 스트림 |
| 정적 자산 로드 | < 3s | Service Worker 캐시 |

### 4.2 자원 효율성
| 항목 | 수치 |
|------|------|
| Docker 이미지 크기 | < 2GB |
| 최소 메모리 | 512MB RAM |
| 권장 메모리 | 2GB RAM |

---

## 5. 유지보수성 (Maintainability)
| 항목 | 구현 상태 |
|------|-----------|
| 코드 모듈화 | ✅ 계층별 분리 (providers/services/storage) |
| 타입 힌트 | ✅ Python type hints |
| 설정 외부화 | ✅ .env / config.py |
| 로깅 구조화 | ✅ decisiondoc.* 네임스페이스 |
| API 문서 | ✅ FastAPI /docs (개발 환경) |

---

## 6. 이식성 (Portability)
| 항목 | 구현 상태 |
|------|-----------|
| Docker 컨테이너화 | ✅ multi-stage Dockerfile |
| OS 독립성 | ✅ Linux/macOS |
| 클라우드 중립 | ✅ S3 호환 스토리지 |
| 온프레미스 지원 | ✅ 로컬 LLM (Ollama) |

---

## GS인증 신청 준비 항목

### 필요 서류
- [ ] 소프트웨어 설명서 (사용자 매뉴얼)
- [ ] 소프트웨어 설계서 (아키텍처 문서)
- [ ] 시험 계획서 및 결과서
- [ ] 소스코드 (심사용)
- [ ] 설치 가이드

### 시험 기관
한국정보통신기술협회 (TTA) — https://gs.tta.or.kr

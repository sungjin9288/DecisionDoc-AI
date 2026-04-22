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

### UAT 시작 전 preflight
```bash
python3 scripts/uat_preflight.py --env-file .env.prod --report-dir ./reports/post-deploy
```

### UAT 세션 파일 생성
```bash
python3 scripts/create_uat_session.py \
  --env-file .env.prod \
  --report-dir ./reports/post-deploy \
  --output-dir ./reports/uat \
  --session-name business-uat \
  --owner "<담당자>"
```

### UAT 결과 기록 추가
```bash
python3 scripts/record_uat_result.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --owner "<담당자>" \
  --scenario "시나리오 1. 기본 사업 제안서 생성" \
  --bundle proposal_kr \
  --input-data "기본 입력 요약" \
  --attachments "intro.pdf,concept.pptx" \
  --generation-status "성공" \
  --export-status "DOCX/PDF 성공" \
  --visual-asset-status "일치" \
  --history-restore-status "확인 완료" \
  --quality-notes "문서 구조는 안정적이나 결론 문장이 다소 장문임" \
  --issues "없음" \
  --follow-up "아니오"
```

### UAT 세션 요약 확인
```bash
python3 scripts/show_uat_session.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --limit 5
```

### UAT 최종 요약 보고서 생성
```bash
python3 scripts/finalize_uat_session.py \
  --session-file ./reports/uat/uat-session-<timestamp>-business-uat.md \
  --output-dir ./reports/uat
```

### Pilot handoff 생성
```bash
python3 scripts/create_pilot_handoff.py \
  --summary-file ./reports/uat/uat-session-<timestamp>-business-uat-summary.md \
  --env-file .env.prod \
  --report-dir ./reports/post-deploy \
  --output-dir ./reports/pilot
```

### Pilot launch checklist 생성
```bash
python3 scripts/create_pilot_launch_checklist.py \
  --handoff-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot.md \
  --output-dir ./reports/pilot
```

### Pilot run sheet 생성
```bash
python3 scripts/create_pilot_run_sheet.py \
  --checklist-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist.md \
  --output-dir ./reports/pilot
```

### Pilot run sheet 기록 업데이트
```bash
python3 scripts/record_pilot_run.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --target run1 \
  --field "started_at=2026-04-22T09:00:00+09:00" \
  --field "operator=<담당자>" \
  --field "request_id=<request_id>" \
  --field "bundle_id=<bundle_id>" \
  --field "stop_decision=continue"
```

### Pilot run sheet 상태 요약 확인
```bash
python3 scripts/show_pilot_run.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md
```

### Pilot sample Run 1/Run 2 실제 실행 및 기록
```bash
python3 scripts/run_pilot_sample.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --base-url https://admin.decisiondoc.kr \
  --operator "<담당자>" \
  --business-owner "<business owner>"
```

### Pilot close-out evidence 사전 채우기
```bash
python3 scripts/prepare_pilot_closeout.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md
```

### Pilot close-out 최종 판정 반영 및 artifact 생성
```bash
python3 scripts/complete_pilot_closeout.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --accepted-for-next-batch yes
```

### Pilot completion report 생성
```bash
python3 scripts/create_pilot_completion_report.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot stakeholder share note 생성
```bash
python3 scripts/create_pilot_share_note.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot delivery index 생성
```bash
python3 scripts/create_pilot_delivery_index.py \
  --closeout-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md \
  --output-dir ./reports/pilot
```

### Pilot close-out 생성
```bash
python3 scripts/finalize_pilot_run.py \
  --run-sheet-file ./reports/pilot/uat-session-<timestamp>-business-uat-summary-pilot-launch-checklist-run-sheet.md \
  --output-dir ./reports/pilot
```

---

## 3.1 현재 단계 판단

DecisionDoc AI는 현재 기준으로 핵심 개발 범위가 대부분 구현 및 회귀 검증된 상태이며, 다음 단계의 중심은 **신규 기능 개발보다 실사용 UAT(User Acceptance Test)** 이다.

### 현재 완료에 가까운 범위

- 문서 생성 기본 플로우
- 첨부 기반 생성(`/generate/with-attachments`, `/generate/from-documents`)
- 주요 export 흐름(DOCX/PDF/PPTX/HWPX/XLSX)
- visual asset 생성 및 export 재사용
- quality-first provider routing (`claude/openai/gemini`, `attachment/visual` route 포함)
- post-deploy report, ops dashboard, compare, legacy report empty-state
- 위 기능들에 대한 unit / integration / browser regression test

### 현재 우선순위

- 신규 기능 추가보다 **실제 업무 자료 기반 UAT**
- provider 품질 비교
- 대용량/복수 첨부 성능 및 실패 패턴 확인
- export 산출물 실사용 검수

즉, 현 단계의 목표는 “기능을 더 붙이는 것”보다 “실사용 시나리오에서 어떤 케이스가 남는지 수집하고 품질을 보정하는 것”이다.

---

## 3.2 UAT 실행 체크리스트

### 사전 준비

- [ ] 운영 환경 `/health`가 `status=ok` 인지 확인
- [ ] `provider_policy_checks.quality_first = ok` 인지 확인
- [ ] `post-deploy` latest report가 최근 배포 기준으로 `passed` 인지 확인
- [ ] 테스트용 API key / admin 계정 / Ops key 접근 확인
- [ ] 첨부 테스트 파일 세트 준비
  - [ ] PDF 1건
  - [ ] DOCX 또는 PPTX 1건
  - [ ] HWPX 1건
  - [ ] 구형 `.hwp` 1건(차단 메시지 확인용)

### 기능 검수

- [ ] 기본 문서 생성 3건 이상 실행
- [ ] 첨부 기반 문서 생성 3건 이상 실행
- [ ] 첨부 없는 생성과 첨부 기반 생성의 품질 차이 기록
- [ ] 결과 화면에서 visual asset 생성 후 export 결과와 일치하는지 확인
- [ ] `history` / `server history`에서 복원 후 export가 동일 자산을 재사용하는지 확인

### 산출물 검수

- [ ] DOCX 다운로드 후 Microsoft Word 또는 호환 뷰어에서 열기 확인
- [ ] PDF 다운로드 후 레이아웃 깨짐 여부 확인
- [ ] PPTX 다운로드 후 슬라이드 편집 가능 여부 확인
- [ ] HWPX 다운로드 후 한글에서 열기/수정/재저장 가능 여부 확인
- [ ] XLSX가 포함되는 번들은 수식/시트 구조 이상 여부 확인

### 실패/품질 검수

- [ ] 구형 `.hwp` 업로드 시 `HWPX/PDF/DOCX로 변환` 안내가 노출되는지 확인
- [ ] 느린 요청, 타임아웃, provider fallback 발생 여부 기록
- [ ] 결과 문체, 구조, 사업 맥락 적합성에 대한 주관 평가 기록
- [ ] export와 화면 결과가 불일치하는 케이스가 있는지 기록

### 종료 판단

- [ ] 치명적인 생성 실패 없이 핵심 시나리오를 반복 수행 가능
- [ ] export 산출물이 실제 업무 도구에서 열리고 수정 가능
- [ ] 품질 이슈가 남아도 “후속 보정 목록”으로 정리 가능한 수준

---

## 3.3 우선 UAT 시나리오

### 시나리오 1. 기본 사업 제안서 생성

목표:
- 첨부 없이도 실사용 가능한 초안이 안정적으로 생성되는지 확인

절차:
1. 번들을 선택한다.
2. 목표/배경/제약 조건을 입력한다.
3. 문서를 생성한다.
4. 결과 탭, export 버튼, history 저장 여부를 확인한다.

통과 기준:
- 생성 성공
- 결과 탭 정상 노출
- export 버튼 정상 동작
- 문서 구조가 입력 의도와 크게 어긋나지 않음

### 시나리오 2. 첨부 기반 제안서 생성

목표:
- 참고 문서 2~3건을 업로드했을 때 문맥 반영 품질을 확인

절차:
1. PDF + PPTX + DOCX/HWPX 중 2~3건을 업로드한다.
2. 문서로 초안 생성 또는 첨부 기반 생성을 실행한다.
3. 결과 문서에서 첨부 기반 서술이 들어갔는지 확인한다.

통과 기준:
- 생성 성공
- 첨부 파일 수, 반영된 문맥, 구조적 일관성이 확인됨
- provider timeout/504 없이 완료됨

### 시나리오 3. visual asset 생성 및 export 일관성

목표:
- 화면에서 본 visual asset이 export에도 동일하게 들어가는지 확인

절차:
1. 생성 결과에서 visual asset를 만든다.
2. DOCX/PDF/PPTX/HWPX로 각각 export한다.
3. 결과 파일에서 같은 asset이 재사용되는지 확인한다.

통과 기준:
- 화면과 export 결과가 동일 자산 기준으로 일치
- DOCX/PDF/PPTX에서 자산 누락 없음
- HWPX는 실제 파일 열림 및 이미지 노출 확인

### 시나리오 4. legacy `.hwp` 차단 메시지

목표:
- 지원하지 않는 입력이 명확히 차단되고 사용자가 다음 행동을 알 수 있는지 확인

절차:
1. 구형 `.hwp` 파일을 업로드한다.
2. RFP 분석 또는 첨부 기반 생성을 시도한다.

통과 기준:
- 서버가 무한 대기하지 않음
- UI 또는 API에서 변환 안내가 명시적으로 노출됨
- 사용자가 `HWPX/PDF/DOCX` 변환 필요를 이해할 수 있음

### 시나리오 5. history 복원 + 재export

목표:
- 저장된 결과를 다시 열었을 때 동일한 문서/visual asset/export 맥락이 유지되는지 확인

절차:
1. 결과를 생성하고 history/server history에 남긴다.
2. 페이지를 새로고침하거나 다시 접속한다.
3. history에서 결과를 연다.
4. 다시 export한다.

통과 기준:
- 문서 복원 성공
- visual asset snapshot 유지
- export 결과가 최초 결과와 실질적으로 동일

---

## 3.4 UAT 결과 기록 템플릿

```md
### UAT 기록
- 일시:
- 담당자:
- 시나리오:
- 사용 번들:
- 입력 데이터:
- 첨부 파일:
- 결과:
  - 생성 성공/실패:
  - export 성공/실패:
  - visual asset 일치 여부:
  - history 복원 여부:
- 품질 메모:
- 실패/이슈:
- 후속 조치 필요 여부:
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

# DecisionDoc AI — 완성을 위한 기능 개발 계획 (Development Plan)

> 상태 정합성 갱신: **2026-09-28**. 아래 **Current Completion/Readiness Snapshot**에서 로컬 기능 상태와 외부 readiness를 구분한다. CI baseline 및 이전 검증 수치는 각 기록 날짜의 historical evidence다.
> 원칙: AGENTS.md 정직성 규칙 준수 — 모든 정량 수치는 재현 커맨드를 병기하고, 검증되지 않은 성과·운영 표현은 사용하지 않는다.
> 상위 방향 문서: [product_direction.md](./product_direction.md) · [product_execution_plan.md](./product_execution_plan.md) · [roadmap.md](./roadmap.md)

---

## 0. Current Completion/Readiness Snapshot

이 절이 현재 완료·readiness의 **유일한 volatile snapshot**이다. README, roadmap,
evidence checklist와 procurement STATUS는 이 절을 링크만 하며 독립적인 현재
pytest pass 수를 주장하지 않는다. 기능별 STATUS에는 대상·날짜·명령이 명시된
검증 기록을 유지하되, 그 수치를 합산하거나 현재 전체 suite 통과로 해석하지 않는다.

### Local Workflow Status (2026-09-28)

기능 완성 설계(`docs/superpowers/specs/2026-09-14-planned-feature-completion-design.md`)의
문서 편집본 저장·재열기·내보내기, 스타일 예제 재사용, 별도 사용자 검토 완료,
지식 재사용 흐름에는 로컬 검증 기록이 있다. 조달 복수 공고·요구사항 적용 여부는
승인 기록(`docs/future_feature_gates/README.md`)에 따라 구현됐고,
실행 계획(`docs/superpowers/plans/2026-09-21-procurement-opportunity-and-applicability.md`)의
작업 1-8 로컬 구현과 작업 9-11 전환 preflight·재시작·격리 fixture 복원 검증이
procurement STATUS(`docs/specs/public_procurement_copilot/STATUS.md`)에 기록돼 있다.

기본 앱의 복수 공고 기능은 여전히 opt-in이며 실제 사용자 데이터 전환·활성화는
하지 않았다. 다음 사용성 확인은 새 샘플 데이터의 격리 앱 또는 별도로 범위가
확인된 기존 데이터 복사본에서 진행한다. 인간 UAT, native Office 앱의 열기·편집·저장,
실제 모델의 문서 품질과 아래 M1/M2/M6 외부 조건은 별개로 남아 있다.
위 상태 요약은 전체 suite/CI 실행이나 운영 완료의 증거가 아니다.

### 기능별 현황 대조 (2026-09-28)

기획·화면·API·저장소·테스트를 현재 트리에서 다시 대조한 결과다. 상태 구분은
**로컬 검증 완료**(이번 격리 실행에서 통과) / **확인된 구현 결함**(재현 후 수정 포함) /
**미검증**(실행하지 못했거나 근거 없음) / **외부 검증 보류**(외부 환경·사람·앱 필요)다.
오래된 roadmap 항목은 이 표의 미구현 근거로 쓰지 않는다.

| 기능 | 상태 | 근거 / 남은 조건 |
|---|---|---|
| 생성 → 원문 편집 → 명시적 저장 → 재열기 → 내보내기 | 로컬 검증 완료 | 편집본 E2E(desktop/mobile), 4개 문서 bundle의 두 번째 문서 편집·저장·재열기 후 DOCX/HWPX 다운로드에 편집 내용 포함(탐색 실행). 인간 UAT·native Office는 외부 검증 보류 |
| 섹션 다시 쓰기의 draft 반영·늦은 응답 차단 | 로컬 검증 완료 | UI 회귀와 편집본 E2E. UI의 모델 응답은 stub |
| Markdown 다운로드·형식별 `export-edited`·`generate_missing_visuals=false` | 로컬 검증 완료 | 다운로드 중 `/generate/*` POST 없음. 직접 `/generate/export` API의 재생성·저장 계약은 그대로이므로 모든 API가 무과금은 아님 |
| 로컬 스타일 예제 등록·선택·기본값·삭제·생성 문맥 재사용 | 로컬 검증 완료 / 일부 미검증 | Prompt conditioning이며 모델 가중치 학습이 아님. 이 환경에 `pdfplumber`가 설치되지 않아 텍스트 PDF 예제 가져오기 1건은 미검증(설치하지 않음). 실제 모델 품질은 외부 검증 보류 |
| 별도 사용자 검토·비담당자 거부·완료 패키지 재검증 | 로컬 검증 완료 | 저장된 편집본은 생성 발급 이력이 없어 검토 생성이 `409`로 차단되고 UI에도 노출되지 않음을 확인하고 API 회귀 assertion을 추가. 문서 검토 완료는 외부 제출 승인이 아님 |
| 지식 업로드·프로젝트 격리·생성 재사용 | 로컬 검증 완료 | API/UI 회귀와 E2E. Provider/OCR 미사용 |
| 조달 복수 공고·요구사항 적용 여부 | 로컬 검증 완료(opt-in) | 명시적 opt-in 앱에서만 검증. 기본 활성화·기존 사용자 데이터 전환은 실행하지 않음 |
| PDF 표의 짧은 한글 셀 | 확인된 구현 결함 → 수정 | `구분`·`파일` 같은 2글자 셀이 글자 단위로 줄바뀜. 아래 기록 참조 |
| PPTX 번호 문단 | 확인된 구현 결함 → 수정 | `1. 항목`이 `1.`과 본문 bullet으로 분리되고 슬라이드 경계를 넘음. 아래 기록 참조 |
| 산출물 Markdown 부분집합의 기존 한계 | 미구현(승인 범위 밖) | fenced code block은 모든 형식에서 fence가 문자로 남고 들여쓰기가 사라짐. 중첩 목록 들여쓰기 미표현. HWPX 표는 기존 설계대로 `표:`/`•` 텍스트 행. PPTX는 발표용 재구성으로 문단당 최대 6개 point와 길이 절단을 적용(코드 기준, 원문 전체 보존 형식 아님). 한글 글꼴에서 `\`가 `₩` 글리프로 보이나 텍스트 값은 `\` |
| 테스트 harness drift | 확인된 테스트 결함 → 수정 | `switchPage`에 추가된 조달 상태 무효화 의존성을 스타일 이동 UI 테스트가 stub하지 않아 실패. 실제 앱에는 정의돼 있으며 테스트 stub과 호출 검사만 보완 |
| 800줄 규모 검사 | 유지보수 과제 | 기존 6개 파일만 실패(아래 목록과 동일). 기능 결함과 구분하며 이번 변경 파일은 610/172줄 |
| PPTX 표지·목차·요약·문서 구분 카드 | 확인된 구현 결함 → 수정 | PowerPoint에서 카드 텍스트가 줄바꿈 없이 카드·슬라이드 밖으로 넘치고, 표지 부제목과 구분 슬라이드 제목·리드가 카드에 가려짐. 아래 native 기록 참조 |
| HWPX native 열기·편집·저장·재열기 | 로컬 검증 완료(한컴오피스 한글) | 합성 산출물 1건. 원래 문단 58개 보존, 편집 표식 1개 추가 |
| PPTX native 열기·렌더링 | 로컬 검증 완료(PowerPoint 보기) / 편집·저장 미검증 | PowerPoint가 Microsoft 365 구독 필요로 편집·저장을 막음. 로그인·구독은 하지 않음 |
| 제안서 구조화 슬라이드 PPTX | 확인된 구현 결함 → 수정 | 음수 크기 도형으로 PowerPoint 복구 대화상자 발생, 카드 가림·넘침, `None` 표시. 아래 기록 참조 |
| DOCX·XLSX native, 인간 UAT, 실제 모델 품질, M1/M2/M6 | 외부 검증 보류 | Word·Excel 미설치. 나머지는 외부 환경·사람 필요 |

### 산출물 렌더링 점검과 표·번호 목록 보완 (2026-09-28)

합성 한글 문서(문단 내 줄바꿈, 긴 문장, 4열 표, escaped pipe, Windows 경로, 목록,
번호 목록, 코드 블록)를 `/generate/export-edited`로 5개 형식 변환했다.
PDF는 원본을, DOCX/PPTX/XLSX는 LibreOffice 26.2 headless(격리 profile)로 PDF 변환 후
`pdftoppm`으로 렌더링해 확인했다. LibreOffice는 HWPX를 열지 못해 HWPX는 package XML의
문단 텍스트로 내용 보존만 확인했다. 파일 생성 성공, LibreOffice 렌더링 확인,
native Office 편집 호환성은 서로 다른 단계이며 마지막 단계는 수행하지 않았다.

- PDF: 표 셀의 `word-break: break-word`가 min-content를 한 글자로 만들어 긴 열이 있으면
  짧은 한글 열이 글자 단위로 줄바뀜했다. 셀은 `keep-all` + `overflow-wrap: break-word`로
  한글 단어를 유지하고, 20자를 넘는 연속 토큰(URL·경로)에만 `<wbr>`를 넣어 페이지 폭을
  넘지 않게 했다. HTML entity와 강조 태그는 분할하지 않으며 텍스트 값은 바뀌지 않는다
  (`app/services/pdf_service.py`).
- PPTX: `presentation_points`의 문장 분리가 `1.` 뒤에서도 분리했다. 번호만 남은 조각을
  다음 문장에 다시 붙인다(`app/services/export_outline.py`). 문장 분리·절 분할 규칙 자체는
  바꾸지 않았다.

재현: `tests/test_pdf_table_layout.py`는 A4 본문 폭 Chromium 측정으로 `구분` 셀 2줄을
재현했고(`pdf-table-red.xml`, 1 failed/1 passed), 수정 후 짧은 한글 셀 1줄·긴 URL의
페이지 내 배치·텍스트 보존을 확인한다. `tests/test_export_outline.py`의 번호 문단 2건은
수정 전 2 failed(`pptx-ordinal-red.xml`)였다. 수정 전후 PDF 렌더와 변환 산출물은
증빙 폴더의 `artifacts/`, `artifacts-after/`에 있다.

Python 3.12.12, dotenv 로드 비활성화, 임시 DATA_DIR, mock/local, AWS metadata 비활성화,
Python non-loopback 연결·이름 해석 차단 조건에서 실행했다. 증빙:
`output/feature-status-20260928-RNaE9u/`. 아래 수치는 서로 다른 실행이며 합산하지 않는다.

| 범위 | 결과 / 증빙 |
|---|---|
| 작업 시작 시 편집·스타일 UI/API 기준선 | 2 failed, 164 passed / `baseline-regression.xml` (`pdfplumber` 미설치, 테스트 drift) |
| 작업 시작 시 통합 browser | **27 passed** / `baseline-browser.xml` |
| 공통 표, 5개 형식, 생성·golden·packet 회귀 | **300 passed**, 109.60s / `export-regression.xml` |
| 검토·지식·조달·편집본·스타일 API/저장소/UI | **893 passed**, 245.18s / `review-knowledge-procurement.xml` |
| 최종 편집·스타일·다시 쓰기 UI/API 회귀 | **180 passed, 1 failed**, 101.77s / `final-ui-regression.xml`; 실패는 `pdfplumber` 미설치 1건 |
| 최종 통합 browser(문서·스타일·검토·지식·조달) | **27 passed**, 146.06s / `final-browser.xml` |
| 무료 모드 편집본·기본 Markdown 다운로드 browser | **3 passed**, 21.87s / `final-free-browser.xml` |
| 800줄 규모 검사 | **1 failed** / `module-guide.xml`; 기존 6개 파일 |
| README metric·portfolio 계약 | **9 passed, 1 failed** / `docs-contract.xml`; 실패는 portfolio pack에 포함되지 않은 planned-feature spec 링크(이번 편집 이전부터 존재) |
| 변경 Python Ruff E/F/W(E501 제외), `git diff --check` | passed |

```bash
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_markdown_utils.py tests/test_docx_endpoint.py tests/test_export_edited.py \
  tests/test_export_outline.py tests/test_excel_endpoint.py tests/test_hwp_endpoint.py \
  tests/test_pdf_endpoint.py tests/test_pdf_table_layout.py tests/test_pptx_endpoint.py \
  tests/test_golden_snapshots.py tests/test_generate.py \
  tests/test_procurement_applicability_packet.py tests/test_generation_export_packet.py
python3 -m pytest --browser chromium -p no:cacheprovider --tb=short \
  tests/e2e/test_edited_project_copy.py tests/e2e/test_main_flow.py::test_export_flow \
  tests/e2e/test_local_style_import.py tests/e2e/test_generated_review_local_lifecycle.py \
  tests/e2e/test_knowledge_local_lifecycle.py tests/e2e/test_procurement_multi_opportunity.py \
  tests/e2e/test_procurement_requirement_applicability.py
```

README와 이 문서의 route/service/storage/test 수치는 이전 미커밋 변경 이후 갱신되지 않아
README metric 테스트가 실패하고 있었다. `python3 scripts/count_readme_metrics.py` 측정값
(라우트 315, 서비스 59, storage 59, 테스트 함수 4,250, 테스트 파일 321)으로만 맞췄고
`manage_portfolio_pack.py sync`로 mirror를 동기화했다. Portfolio 선정 범위는 넓히지 않았다.

이 환경에서는 `pytest-playwright`가 자동 로드되므로 `-p pytest_playwright.pytest_playwright`를
함께 주면 중복 등록 오류가 난다. 자체 async Playwright 측정 테스트와 pytest-playwright
E2E는 별도 프로세스로 실행했다. 격리 서버(127.0.0.1:8791, 합성 계정)로 로그인 화면을
확인했고 기존 사용자 서버는 재시작·종료하지 않았다. Starlette TestClient의 httpx
deprecation warning 1건은 남아 있다. 전체 suite/CI, native Office, 인간 UAT, 실제 모델
품질은 미검증이며 실사용 데이터·provider/AWS/G2B·설치·stage·commit·push는 실행하지 않았다.

### Native Office 확인과 PPTX 카드 배치 보완 (2026-09-29)

사용자가 앱 접근을 허용해 설치된 Microsoft PowerPoint와 한컴오피스 한글로 합성 산출물
사본(`output/feature-status-20260928-RNaE9u/native/`)을 확인했다. Word·Excel은 설치돼 있지
않아 DOCX·XLSX는 대상이 아니다. 원본 export와 사용자 문서는 열지 않았다.

- **HWPX(한글):** 열기 → 본문 첫 줄에 `NATIVE-HWP-EDIT-MARKER` 입력 → 저장하기 → 닫기 →
  다시 열기에 성공했다. 저장본(5.5K → 94.9K, SHA-256
  `e6e2131b4f6ca90eb4b39485fd822250ef3b72b5d49fea696b26a90f6e41d306`)의 section XML 문단을
  원래 export와 비교해 58개 문단이 모두 남고 편집 표식 1개만 추가됐음을 확인했다. 경로,
  escaped pipe, 번호 목록, 문단 내 줄바꿈도 그대로다. 표는 기존 설계대로 텍스트 행이며,
  구분선 문자열이 쪽 폭을 넘어 두 줄로 꺾이는 외관 문제는 남아 있다. 백그라운드 제어에서는
  저장 메뉴가 비활성으로 보고되어 앱을 앞으로 가져온 뒤 메뉴로 저장했다.
- **PPTX(PowerPoint):** 열기·슬라이드 렌더링은 확인했지만, 이 설치본은 Microsoft 365 구독이
  없어 편집·저장이 막혀 있다. 로그인·체험 시작·구독은 하지 않았으므로 PPTX native 편집·저장은
  미검증이다. 원본 사본의 해시는 바뀌지 않았다.

PowerPoint에서 확인한 PPTX 결함과 수정:

- 카드 텍스트 상자가 python-pptx 기본값(`wrap="none"`)이라 긴 요약이 카드와 슬라이드
  밖으로 한 줄로 넘어가 잘렸다. `_add_card(fit_text=True)`는 카드 폭에서 줄바꿈하고, 카드
  높이를 넘는 부분은 `…`로 줄인다. 처음에는 표지·목차·요약·문서 구분 카드에만 적용했고,
  아래 구조화 슬라이드 보완에서 카드 높이를 내용에 맞춘 뒤 모든 카드의 기본값으로 바꿨다.
- 표지 부제목과 문서 구분 슬라이드의 제목·리드 placeholder가 카드 영역과 겹쳐 가려졌다.
  카드가 있을 때만 placeholder를 카드 위로 옮긴다. 상속 위치 placeholder의 top/height만
  바꾸면 left/width가 0이 되어 제목이 세로로 쌓이는 중간 결함을 PowerPoint에서 확인해,
  상속된 left/width를 함께 기록하도록 고쳤다.
- 목차 카드 높이를 0.9in에서 1.15in(행 간격 1.25in)로 늘려 문서명과 요약 두 줄이 들어가게 했다.

변경: `app/services/pptx/primitives.py`, `basic_slides.py`, `deck_builders.py`, 신규
`tests/test_pptx_card_layout.py`. 수정 전 3 failed(`pptx-card-red.xml`), placeholder 폭 검사
추가 후 1 failed, 최종 PPTX/outline 27 passed(`pptx-card-green.xml`). 수정 후 사본
`long-lead-v2.pptx`, `native-check-v2.pptx`를 PowerPoint에서 다시 열어 표지·목차·요약·구분
슬라이드를 확인했고 LibreOffice 렌더 전후 비교는 `lo-long-combined.png`,
`lo-long-v2-combined.png`에 있다.

| 범위 | 결과 / 증빙 |
|---|---|
| PPTX·5개 형식·golden·생성·packet export 회귀(수정 후) | **418 passed**, 186.11s / `export-regression-pptx.xml` |
| 변경 Python Ruff E/F/W(E501 제외), `git diff --check` | passed |

카드 줄 수 추정은 Hangul 1em·기타 0.6em과 여유 10%를 쓰는 근사이며, 글꼴 대체나 어절 단위
줄바꿈에 따라 실제 줄 수가 달라질 수 있다. 인간 UAT와 PowerPoint 편집·저장 호환성은 남은
조건이다. 설치·로그인·구독·실사용 데이터·stage·commit·push는 없었다.

#### 제안서 구조화 슬라이드 native 확인 (2026-09-29)

합성 outline 2장(`native/structured-direct.pptx`)과 mock 제안서 번들 51장
(`native/structured-proposal.pptx`, `/generate/pptx`, `bundle_type=proposal_kr`)을 PowerPoint로
열었다. 수정 전 파일은 PowerPoint가 **"내용에 문제가 있어 복구를 시도할 수 있다"**는 대화상자를
띄웠다(복구는 누르지 않음). 원인은 카드 본문 상자 높이를 `카드 높이 - 0.6in`으로 계산해
0.55·0.56in 카드에서 음수 크기(`cy="-36575"` 등)가 생긴 기존 결함이다. 제안서 덱에는 음수
크기 도형이 85개 있었다. 같은 파일에서 음수 높이만 양수로 바꾼 사본(`structured-direct-cyfix.pptx`)은
대화상자 없이 열려 원인을 확정했다.

복구 없이 연 사본에서 확인한 레이아웃 결함과 수정:

- `장표 구성` 카드(0.56in)는 첫 줄만 보이고 나머지가 다음 카드 뒤에 가려졌다. `승인 기준`,
  `시각자료 배치 / 검증 가이드`는 카드 아래·오른쪽으로 넘쳤고, 긴 핵심 메시지는 오른쪽 도식
  부제목과 겹쳤다. 왼쪽 열 4개 카드와 가이드 카드는 줄바꿈 후 줄 수로 높이를 계산해 겹치지
  않게 쌓는다(카드별 상한 2.0/1.3/1.0/1.3in, 가이드 2.75in).
- 시각 패널 헤더 카드(0.55in)는 부제목이 카드 밖에 놓였다. 0.78in로 올리고 비교 카드 패널의
  시작 위치만 0.84in로 내렸다. 흐름 패널 단계 카드는 0.62→0.72in, 간격 0.88→0.8in로 조정하고
  화살표를 카드보다 나중에 그려 가려지지 않게 했다. 이미지 패널 캡션은 한 줄로 맞춘다.
- 입력에 `content_blocks`가 없으면 `장표 구성`에 문자열 `None`이 표시됐다. 공통
  `_clean_slide_text(None)`이 빈 문자열을 반환하도록 고쳐 기존 대체 문구(`근거 블록: …`)가 쓰인다.
- `_add_card`는 이제 기본으로 줄바꿈·크기 맞춤을 하며 본문 상자 높이는 항상 양수다.

변경: `app/services/pptx/primitives.py`, `structured_slide.py`, `visual_panels.py`와
`tests/test_pptx_card_layout.py`(구조화 테스트 5건 추가). 수정 전 3 failed
(`pptx-structured-red.xml`), `None`·흐름 패널 테스트 추가 후 2 failed(`pptx-structured-red2.xml`),
최종 PPTX/outline **32 passed**(`pptx-structured-green.xml`). 새 테스트의 `content_blocks`
기대값은 설계상 상한(3개)에 맞게 바로잡았다.

수정 후(`native/v5/`) 두 덱은 PowerPoint에서 복구 대화상자 없이 열렸다. 구조화 슬라이드와
의사결정 매트릭스·타임라인·흐름·비교 카드·KPI·거버넌스·권장 시각자료 패널을 한 장 이상씩
보고 카드 내용이 카드 안에 있고 서로 가리지 않음을 확인했다. 도형 크기 전수 점검에서 음수 0개,
카드 텍스트 넘침 추정 0건(고정 문구와 장식 화살표 제외)이다. 남은 외관 문제는 두 가지다.
PowerPoint 어절 줄바꿈으로 끝의 `.`·`?`가 다음 줄로 넘어가는 경우가 있고, 좁은 타임라인
단계 카드는 긴 근거를 앞 몇 어절과 `…`로만 보여 준다. 거버넌스 화살표가 아래 카드 윗선에 조금
겹치는 것도 남아 있다. PowerPoint 편집·저장은 구독 제한으로 여전히 미검증이다.

| 범위 | 결과 / 증빙 |
|---|---|
| PPTX·5개 형식·golden·생성·packet·시각자료 export 회귀(구조화 보완 후) | **428 passed**, 172.46s / `export-regression-structured.xml` |
| PPTX 빌더를 쓰는 편집 UI·report workflow·infrastructure·usage 테스트 | **340 passed, 4 failed**, 123.27s / `pptx-consumers.xml` |
| 변경 Python Ruff E/F/W(E501 제외), `git diff --check` | passed |

위 4건 실패는 이번 PPTX 변경과 무관한 기존 불일치다. 800줄 검사는 앞 절의 기존 6개 파일이다.
`test_index_html_style_profile_action_wiring_exists`는 이전 미커밋 변경에서 바뀐 스타일 생성
모달 연결 방식을, `test_production_procurement_review_artifact_calls_bind_resource_scope`는
이전 조달 변경 뒤의 `read_packet` 호출 수(7→8)를 기대값과 비교한다.
`test_documentation_completion_snapshot_and_core_loop_contract`는 이 문서에 `유일한 volatile
snapshot` 문구를 요구하지만, 이번 작업 시작 시점의 Snapshot 도입부에 이미 없었다. 세 파일
(`app/static/index.html`, 조달 검토 route, 이 문서의 해당 문구)은 이번 작업에서 바꾸지 않았다.
기대값을 맞추거나 문구를 되살리는 것은 해당 변경의 의도 확인이 필요해 수정하지 않았다.

### 이번 세션 export 변경의 독립 검토와 보완 (2026-09-29)

이번 세션에서 바꾼 PDF 표, PPTX 번호·카드·구조화 슬라이드, HWPX 구분선, 증빙 캡처 스크립트를
별도 검토 에이전트가 읽기 전용으로 검토했다. 보고된 5건은 모두 구체적인 재현 경로가 있어
실패 테스트를 먼저 만들고 고쳤다(`review-fixes-red.xml`, `pdf-wide-red.xml`).

| 등급 | 문제 | 수정 |
|---|---|---|
| HIGH | `_fit_card_lines`가 줄 수를 꽉 채우면 이후 줄을 `…` 없이 버림(승인 기준 3번째 항목, 흐름 단계 둘째 문장 등) | 뒤 줄이 남으면 마지막 유지 줄을 줄여 `…`를 붙인다. 생략은 항상 표시된다 |
| MEDIUM | 정리 후 빈 문자열이 되는 카드 제목·이미지 캡션(`**` 등)에서 `IndexError`로 PPTX export 실패 | 빈 결과를 방어하고 빈 캡션은 생략 |
| MEDIUM | 열이 많고 12~20자 토큰(한글 복합명사·타임스탬프·파일명)이 있는 PDF 표가 A4 밖으로 넘침(6열 재현: 722px > 567px) | `<wbr>` 간격을 열 수에 맞춰 줄임(1~2열 20, 4열 10, 6열 6, 최소 4). 2~3자 한글 단어는 계속 한 줄 |
| LOW | `font_size_pt=0`이면 HWPX 구분선 계산이 0으로 나눔 | 0 이하 글자 크기는 기본 10.5pt로 계산 |
| LOW | HWPX 표지 구분선이 사용자 여백 옵션을 무시 | 표지에도 옵션을 전달 |

검토에서 문제가 없다고 확인한 항목: placeholder 위치 보존, 슬라이드 경계, `<wbr>`가 태그·속성·HTML
entity를 쪼개지 않음과 escaping 유지, `_clean_slide_text(None)`, byte 재현성, 캡처 스크립트의
query string 처리. 한국식 날짜 `2024. 3. 15.`의 문장 분리 이상은 이전보다 나빠지지 않아 범위 밖으로 둔다.

| 수정 후 실행(브라우저 허용) | 결과 / 증빙 |
|---|---|
| PPTX·PDF·HWPX·DOCX·XLSX·golden·export·visual·gov·report workflow·생성·packet·infrastructure·증빙 캡처 | **712 passed** / `review-fixes-regression.xml` |

**최종 전체 실행(검토 보완 포함, 격리 조건, 세션과 분리된 프로세스):**

| 실행 | 결과 / 증빙 |
|---|---|
| non-live 전체, `--ignore=tests/e2e` | **1 failed, 5,447 passed, 1 skipped, 4 deselected, 1 warning**, 1,046.26s / `final-nonlive.xml`; 실패는 `pdfplumber` 미설치(설치하지 않기로 결정) |
| E2E 전체, Chromium | 1 failed, 161 passed, 1 skipped, 2 errors, 1,784.69s / `final-e2e.xml` |
| 위 E2E 실패·오류 3건만 재실행 | **3 passed**, 14.50s / `final-e2e-rerun3.xml` |

E2E 3건(DocumentOps 이력·export, localStorage 초안)은 이번 변경과 무관한 영역이다. 오류 내용은
`ERR_NETWORK_IO_SUSPENDED`, 브라우저 실행 180초 timeout, 첫 화면 로드 timeout이었다. 실행 시간이
평소(7~9분)의 3배 이상이었고, 같은 시간대 전원 로그에 유휴·wake 기록이 있다. 단독 재실행에서
통과해 장비 상태로 인한 일시적 실패로 분류하지만, 실패 기록은 덮어쓰지 않고 보존한다.

`…` 생략 보완은 합성 덱 `native/ellipsis-check.pptx`를 PowerPoint로 열어 확인했다. 복구 대화상자는
없었고, `승인 기준` 카드는 두 번째 항목 끝 `…`로, 흐름 1단계는 `요구사항 수집.…`로 생략을 표시했다.

### 800줄 규모 검사 해소: 동작 보존 모듈 분할 (2026-09-29)

사용자 승인에 따라 규모 검사에 걸린 기존 6개 모듈을 동작을 바꾸지 않는 추출로 나눴다.
검사 기준(800줄)은 바꾸지 않았다. HWPX 구분선 보완으로 803줄이 된 `hwp_service.py`도 함께 줄였다.

| 모듈 | 이전 → 이후 | 새 모듈(옮긴 내용) |
|---|---|---|
| `app/middleware/audit.py` | 816 → 747 | `audit_records.py`: IP·resource·결과 판별 순수 helper 6개 |
| `app/routers/projects/decision_evidence.py` | 857 → 714 | `_guided_review_registry.py`: disposition registry helper 6개 |
| `app/routers/projects/procurement.py` | 1077 → 775 | `_procurement_helpers.py`: 정규화·scope·observability helper |
| `app/routers/projects/procurement_reviews.py` | 879 → 727 | `_procurement_review_helpers.py`: 요구사항 context·응답·담당자 helper |
| `app/services/procurement_decision_package/package_builder.py` | 803 → 674 | `demo_seed.py`: demo decision record seeding 7개 |
| `app/storage/procurement_review_store.py` | 851 → 753 | `procurement_review_records.py`: scope·record parsing·binding 검증 순수 함수 |
| `app/services/hwp_service.py` | 803 → 757 | `hwp_image_metadata.py`: 이미지 형식·크기 판별 3개 |

원칙:
- route handler는 기존 파일과 순서를 유지했다.
- 옮긴 이름은 원래 모듈에서 다시 import해 기존 import 경로를 보존했다.
- 경로 기반 AST·문자열 검사 대상 코드는 원래 파일에 남겼다(`read_packet`/`complete`/`read_reviewed_package` 호출 수, audit 규칙 문자열 등).
- 테스트가 monkeypatch하는 이름(`state_lock` 등)은 호출 위치를 바꾸지 않았다.
- 조달 라우터의 중복 본문 5곳을 helper로 묶은 부분은 원본과 직접 대조해 코드·상태 코드·메시지·헤더 순서가 같음을 확인했다.
- 원본 사본은 작업용 scratchpad에만 보존했다.
- 파일별 작업은 하위 에이전트가 나눠 수행했고, 통합 검토와 전체 검증은 직접 수행했다.

| 격리 실행 | 결과 / 증빙 |
|---|---|
| `tests/test_infrastructure.py` | **180 passed** / `infra-after-split.xml`; 800줄 규모 검사 통과 |
| 저장소 전체 Ruff E/F/W(E501 제외) | passed |
| non-live 전체, 브라우저 실행 차단(`PLAYWRIGHT_BROWSERS_PATH` 빈 경로) | 5,292 passed, 148 브라우저 보류, 4 기타 실패, 1 skipped / `full-nonlive-split-nobrowser.xml` |
| 위 브라우저 보류·검토 테스트 19개 파일, 브라우저 허용 | **284 passed, 1 failed** / `browser-held-rerun.xml`; 실패는 `pdfplumber` 미설치 |
| E2E 전체, 별도 프로세스 | **164 passed, 1 skipped**, 448.23s / `full-e2e-split.xml` |

다른 프로젝트의 요청으로 브라우저 검사를 보류한 동안에는 브라우저 실행을 막은 조건으로 non-live를
돌렸다. 브라우저가 필요한 148건은 통과·실패가 아닌 보류로 분류하고, 보류 해제 뒤 해당 파일을
브라우저 허용 조건으로 다시 실행했다.

기타 실패 4건의 처리:
- 생성 문서 검토 3건: 검토 패킷의 PDF 생성에 브라우저가 필요했다. 위 재실행에 포함돼 통과했다.
- README metric 1건: 새 모듈로 service·storage·middleware 수가 늘었다. 측정 스크립트 값으로 갱신했다.

보류 중 분할 에이전트가 파일 목록 없이 시작한 전체 pytest 1건(PID 54631)은 정상 종료 신호로
중단했고, 결과는 중단으로만 남긴다.

### Portfolio 링크 계약과 HWPX 구분선 보완 (2026-09-29)

- **Portfolio pack 링크:** 이 문서 4곳과 `product_execution_plan.md` 3곳이 pack에 없는 문서
  (아직 추적되지 않은 `docs/superpowers/...` 설계·계획 문서, `docs/future_feature_gates/README.md`,
  pack 선정 밖의 procurement `STATUS.md`)를 Markdown 링크로 가리켜
  `test_tracked_portfolio_pack_matches_current_sources`가 실패했다. HEAD가 pack 밖 문서를 코드
  경로로 적던 관례에 맞춰 링크만 `문서명(`경로`)` 표기로 바꿨다. 문서 내용과 pack 선정 범위는
  넓히지 않았다. `manage_portfolio_pack.py check`가 처음으로 `ok: true`를 반환한다.
- **HWPX 구분선:** 표지·문서 사이 구분선이 `─` 50자라 한컴오피스 한글에서 쪽 폭을 넘어 짧은
  조각이 다음 줄로 꺾였다. 1em 가정의 41자에서도 꺾였고, 50자 결과(한 줄 약 37자)로 보면 한글은
  이 글자를 약 1.25em 폭으로 그린다. `_separator_line(opts)`가 설정된 좌우 여백과 글자 크기에서
  1.25em 기준·5% 여유로 길이를 계산한다(기본 A4 34자). 공문서 서식의 여백·글꼴 변경도 반영한다.
  `test_build_hwp_separators_fit_the_page_content_width`는 수정 전 185.2mm > 170mm로 실패했다
  (`hwp-separator-red.xml`). 수정 후 한글에서 다시 연 `native/separator-check-v2.hwpx`의 구분선은
  한 줄로 표시됐다. 폭 계수는 이 설치본의 기본 글꼴에서 관찰한 근사다.

| 범위 | 결과 / 증빙 |
|---|---|
| HWPX·golden·편집본 export·packet 회귀 | **121 passed** / `hwp-separator-green.xml` |
| `tests/test_manage_portfolio_pack.py tests/test_count_readme_metrics.py` + 문서 snapshot 계약 | **11 passed** / `docs-contract-final.xml`; portfolio `check` `ok: true` |

### 전체 격리 실행과 추가 불일치 정리 (2026-09-29)

이번 세션에서 처음으로 E2E를 제외한 전체 non-live suite를 격리 조건(dotenv 비활성화, 임시
DATA_DIR, mock/local, AWS metadata 비활성화, Python non-loopback 차단)으로 실행했다.

```bash
python3 -m pytest -q -p no:cacheprovider --tb=line -m "not live" --ignore=tests/e2e tests/
```

결과는 **9 failed, 5,427 passed, 1 skipped, 4 deselected, 1 warning**, 1,219.53s
(`full-nonlive.xml`)다. 이 실행은 아래 수정 전의 tree를 대상으로 했으며 수정 후 전체를 다시
돌리지는 않았다. 실패 분류:

| 실패 | 분류 | 처리 |
|---|---|---|
| `test_infrastructure` 3건(스타일 연결·조달 호출 수·snapshot 문구) | 기존 불일치 | 다음 절에서 수정, `test_infrastructure.py` 재실행 |
| `test_app_python_modules_stay_within_800_line_guide` | 유지보수 과제 | 기존 6개 파일, 분할하지 않음 |
| `test_real_document_parsers[pdf]` | 환경 제약 | `pdfplumber` 미설치, 설치하지 않음 |
| `test_tracked_portfolio_pack_matches_current_sources` | 기존 문서 링크 | planned-feature spec이 portfolio pack에 없음 |
| `test_cache_corruption_is_cache_miss` | 테스트 drift | 아래 수정 |
| `test_capture_guided_decision_review_demo_evidence` 2건 | 증빙 harness drift | 아래 수정 |

- **캐시 손상 테스트:** 스타일 재사용 작업 뒤 생성 캐시 키는 요청 선택자
  (`style_profile_id`, `procurement_decision_id`, `expected_procurement_decision_revision`)를 빼고
  해석된 스타일 snapshot과 조달 binding을 쓴다. 스타일이 바뀌면 캐시가 무효화되도록 한 의도된
  동작이다. 테스트는 이전 방식으로 경로를 계산해 서비스가 쓰지 않는 파일을 손상시켰다. 먼저
  생성해 서비스가 실제로 쓴 캐시 파일을 손상시키고, 재생성이 cache miss로 처리되어 같은 파일이
  유효한 bundle로 복구되는지 확인하도록 바꿨다. 기존 복구 assertion은 유지한다.
- **가이드 검토 데모 증빙 캡처:** 기본 앱(복수 공고 opt-in 아님)의 프로젝트 화면은
  `/procurement/opportunities` 목록을 조회하고, 404를 "기능 미사용"으로 보고 기존
  `/procurement` 경로를 쓴다. 캡처 스크립트는 이 설계상 404를 HTTP 오류로 기록해 증빙을 거부했다.
  이미 허용하던 `/decision-council` 탐지 404와 같은 기준으로 목록 경로의 404만 예상 응답으로
  추가했다. 목록의 500, 공고별·요구사항 하위 경로와 `/procurement`의 404는 계속 오류로 기록한다.
  이 범위를 고정하는 매개변수 테스트 6건을 추가했다. 기능 사용 여부를 알려 주는 API를 새로
  만드는 방식은 인터페이스 변경이라 택하지 않았다.

| 수정 후 실행 | 결과 / 증빙 |
|---|---|
| 데모 증빙 캡처 + 품질 hardening 테스트 | **23 passed** / `guided-demo-and-cache.xml` |
| E2E 전체(별도 프로세스, `pytest --browser chromium -m "not live" tests/e2e/`) | **1 failed, 163 passed, 1 skipped**, 426.43s / `full-e2e.xml` |
| 실패 파일 수정 후 `tests/e2e/test_guided_decision_review.py` 재실행 | **14 passed**, 36.18s / `guided-review-e2e.xml` |
| 수정 후 브라우저 없는 `test_infrastructure`·`test_quality_hardening`·`test_procurement_review_store` | **244 passed, 1 failed**, 15.83s / `infra-and-cache-final.xml`; 실패는 기존 800줄 검사 |

E2E 실패 1건(`test_guided_review_uses_the_session_bound_project_loading_path`)도 같은 원인의
테스트 drift였다. 테스트의 fetch 스텁이 예상 URL 목록 밖 요청에서 예외를 던지는데, 프로젝트
상세 로딩이 복수 공고 목록 탐지 요청을 먼저 보내 가이드 검토 화면이 나타나지 않았다. 기본 앱
기준 응답(404)을 예상 요청 순서에 넣었고, 요청 순서와 Bearer 인증 검증은 그대로 유지했다.
수정 후 E2E 전체와 non-live 전체는 다시 실행하지 않았다. 다른 세션의 요청에 따라 이후 브라우저
검사는 보류했으며, 보류 시점에 이 세션에서 실행 중인 브라우저 검사는 없었다.
보류 중 브라우저 실행 경로를 비운 조건으로 non-live 재확인을 시작했으나, 사용자의 작업 정지
지시로 약 50% 시점에 **중단**했다. 이 부분 실행은 통과·실패로 해석하지 않는다(로그만
`full-nonlive-nobrowser.log`에 보존). 재개 후 원래 조건으로 다시 실행한 결과는 아래에 기록한다.
세션 종료로 재개 후 첫 재실행도 약 70%에서 끊겨 중단으로 처리했다
(`full-nonlive-after-interrupted.log`). 이후 세션과 분리된 프로세스로 다시 실행했다.

| 수정 후 재실행(격리 조건 동일) | 결과 / 증빙 |
|---|---|
| non-live 전체, `--ignore=tests/e2e` | **3 failed, 5,440 passed, 1 skipped, 4 deselected, 1 warning**, 1,855.95s / `full-nonlive-after.xml` |
| E2E 전체, 별도 프로세스, Chromium | **164 passed, 1 skipped**, 566.69s / `full-e2e-after.xml` |

non-live 실패 3건은 모두 앞에서 분류한 항목이다: 800줄 규모 검사(기존 6개 파일), `pdfplumber`
미설치로 인한 PDF 예제 가져오기, portfolio pack에 없는 planned-feature spec 링크. 새 실패는 없다.
두 실행은 별도 프로세스이며 수치를 합산하지 않는다. 이는 로컬 mock/local 결과이고 원격 CI 결과가 아니다.

### `test_infrastructure` 기존 불일치 3건 정리 (2026-09-29)

PPTX 보완 검증에서 이번 변경과 무관하게 실패하던 3건을 코드·문서와 테스트 의도에 대조했다.

- `test_index_html_style_profile_action_wiring_exists`: 현재 UI는 스타일 생성 버튼에
  `() => submitCreateStyleProfile(modal)`을 연결한다. 제출 함수가 전달받은 모달로 연결 해제와
  중복 제출을 막으므로 코드가 맞고, 테스트의 문자열 기대값만 갱신했다.
- `test_production_procurement_review_artifact_calls_bind_resource_scope`: 늘어난 `read_packet`
  호출 1건은 `read_reviewed_package` 안에 있다. `tenant_id`·`project_id`·`packet_sha256`
  키워드를 모두 넘기고, `_require_record_scope`와 같은 범위의 review lock, 저장 레코드
  일치 확인을 거친다. 키워드 누락 검사(`incomplete_calls == []`)는 그대로 두고 기대 호출
  수만 7→8로 바꿨다. 이 보호 동작을 직접 검증하는 테스트가 없어
  `test_packet_tamper_after_completion_blocks_reviewed_package_read`를 추가했다. 완료 후 원본
  packet을 변조하면 reviewed package 읽기가 거부되고 record는 바뀌지 않는다. 임시 스크립트에서
  이 호출만 무력화하면 읽기가 허용되어, 테스트가 추가된 호출에 의존함을 확인했다.
- `test_documentation_completion_snapshot_and_core_loop_contract`: README·roadmap·evidence
  checklist가 여전히 이 절을 유일한 현재 기준으로 링크하므로, 이 절 도입부에서 빠졌던
  "유일한 volatile snapshot" 계약 문장을 기능별 STATUS 설명과 함께 복원했다.

| 격리 실행(dotenv 비활성화, 임시 DATA_DIR, mock/local, non-loopback 차단) | 결과 / 증빙 |
|---|---|
| `python3 -m pytest -q -p no:cacheprovider tests/test_infrastructure.py` | **179 passed, 1 failed** / `infra-drifts.xml`; 남은 1건은 기존 800줄 검사(6개 파일, 모듈 분할하지 않음) |
| `tests/test_procurement_review_store.py tests/test_manage_portfolio_pack.py tests/test_count_readme_metrics.py` | **60 passed, 1 failed** / `review-store-and-docs.xml`; 실패는 portfolio pack에 없는 planned-feature spec 링크(기존) |

### 로컬 세션 작성 경로, 품질 보정 문구 결함, 화면 개선 (2026-10-07)

운영자는 이 저장소를 Claude Code·Codex 세션에서 열고, 그 세션이 문서를 작성하는 로컬 사용을 목표로 정했다. 승인 게이트(`docs/future_feature_gates/agent_authored_local_generation.json`)와 설계·검증 문서(`docs/superpowers/specs/2026-10-07-agent-authored-local-generation-design.md`)를 남기고 다음을 구현했다.

- **세션 작성 경로**
  - `POST /generate/authoring-brief`는 실제 생성과 같은 프롬프트를 돌려준다. 같은 payload 준비와 문체·지식·조달 문맥을 쓴다.
  - `POST /generate/authored`는 세션이 쓴 JSON을 기존 안정화·품질 보정·스키마 검증·렌더링·lint·이력·프로젝트 연결로 처리한다. provider 이름은 `agent_authored`로 남기고, cache와 provider는 쓰지 않는다.
  - 검증 실패는 422 `AUTHORED_BUNDLE_INVALID`와 사유로 돌려주며, 이력과 프로젝트 문서는 쓰지 않는다.
  - `scripts/decisiondoc_author.py`(bundles·brief·submit)와 `.claude/skills/decisiondoc-authoring/SKILL.md`를 추가했다.
  - `scripts/run_free_local.py`에 `--agent-api-key`(0600 키 파일)와 `--procurement-multi-opportunity`를 추가했다. 기존 조달 상태가 있는 폴더는 preflight 확인 플래그 없이는 시작하지 않는다.
- **기존 결함: 품질 보정에 다른 사업 문구가 섞임**
  - proposal 품질 보정의 대체 문장이 보행 안전 사업 전용("교차로", "교통약자" 등)이었다. 짧은 맥락이나 짧은 첨부 RFP에서는 주제와 관계없이 이 문장이 문서에 들어갔다.
  - 대체 문장을 주제 중립 문장과 사용자 목표로 바꿨다.
  - 새 회귀 테스트는 수정 전 코드에서 2건 실패하고 수정 후 통과한다.
- **화면 개선**
  - 결과·비교 탭과 슬라이드 맵이 내부 id 대신 렌더링된 문서명을 표시한다.
  - 거점 카드가 팀원 생성 뒤 다시 읽힌다.
  - 업무 AI 미배정 사용자에게 "배정된 업무 AI 없음"을 표시한다.
  - 검토함과 지식 scope의 UUID를 짧게 표시하고, 전체 값은 툴팁에 남긴다.
  - 결과·비교 화면 Markdown 표에 테두리와 셀 여백을 넣었다.
  - 지식 모달은 Escape로 닫히고 닫기 버튼에 접근성 이름이 있다.
  - 조달 예산은 자릿수를 구분해 표시한다.
- **검증**
  - 이 Claude Code 세션이 skill 절차대로 합성 RFP로 `proposal_kr`을 직접 작성해 제출했다. 첫 제출에서 통과했다.
  - 작성 항목 69개가 모두 최종 문서에 남았고, DOCX·PDF(14쪽)·PPTX(11장)·HWPX·XLSX를 생성해 렌더링으로 확인했다.
  - 격리 환경 최종 전체(E2E 제외)는 5,492 passed, 1 skipped, 1 failed다. 실패 1건은 로컬 `pdfplumber` 미설치다. E2E 전체(별도 process)는 164 passed, 1 skipped다.
  - E2E 1건(`test_generate_from_documents_modal_flow`)은 탭 이름 기대값을 문서명으로 바꿨다. 의도한 동작 변경이다.
  - 첫 전체 실행에서 드러난 회귀(조달 요약 테스트가 자르는 구간 밖에 예산 함수가 있어 생긴 8건)는 함수 위치를 옮겨 고쳤다. 위 최종 수치는 고친 뒤 다시 실행한 결과다.

### Human UAT 사전 점검과 창 배경·문체 문구 보완 (2026-10-07)

Human UAT용 격리 서버(mock provider, free mode, 새 빈 저장소, loopback 외 network 차단)를
준비했다. 사람 검수 전에 Claude가 별도 빈 저장소의 서버에서 같은 시나리오를 브라우저로
조작했다. 이 점검은 Human UAT가 아니며 Human UAT는 여전히 미실행이다.

- 통과한 흐름은 다음과 같다.
  - 편집본 저장·재열기와 형식별 다운로드: `export-edited`만 호출하며, 5개 형식 모두 편집 내용을 포함한다.
  - 섹션 다시 쓰기의 초안 반영
  - 문체 예시: 수동 입력, docx·hwpx·txt 가져오기, 생성 요청에 선택 반영, 삭제 후 선택 해제
  - 지식 문서의 프로젝트 격리와 생성 문맥 포함
  - 검토 전달 → 비담당자 404 → 담당자 완료 → 같은 hash의 완료 ZIP → CLI `verified`, 변조 사본 거부
  - 조달 opt-in: 공고별 판단·요구사항 적용성 분리, 이전 판단 revision 생성 거부
- 화면 결함 두 가지를 고쳤다.
  - **창 배경:** 반투명 page card token `--surface`를 쓰던 창 패널 때문에 뒤 페이지 글자가 비쳤다. 공유 링크·번들별 설정 창의 `.modal-box`는 배경과 여백이 아예 없었다.
    - 대상 창: 검토 전달·완료, 거점 창 6개, 프로젝트 생성, 결재, 사용자 메뉴
    - 이 창들과 `.modal-box`를 불투명 `--surface-solid` 패널로 바꿨다.
    - `tests/test_modal_surface_ui.py`가 실제 CSS로 렌더링해 패널 불투명도와 여백을 확인한다.
  - **"학습" 문구:** 시작 가이드·지식 목록·업로드 옵션의 "스타일 학습" 문구를 prompt 참고라는 실제 동작에 맞게 고쳤다. `test_style_ui_copy_describes_prompt_reference_not_model_training`이 다시 들어오는 것을 막는다.
- 결과 문서 탭의 내부 id 표시 등 개선 관찰은 승인 범위 밖으로 남겼다. 목록은 UAT 기록지
  `output/uat-20260930/UAT-worksheet.md` 5절에 있다(gitignore 대상).

### PR CI 실패 원인과 테스트 단계 분리 (2026-09-30)

[sungjin9288/DecisionDoc-AI#74](https://github.com/sungjin9288/DecisionDoc-AI/pull/74)의
첫 CI(run 36650119763)는 Test job에서 8 failed, 130 errors로 끝났다. `pytest tests/`가 한
process에서 `tests/e2e`를 먼저 실행하면 pytest-playwright의 sync session과 event loop가 끝까지
남는다. 그 뒤 자체 `sync_playwright()`를 여는 UI 테스트와 `asyncio.run()`을 직접 부르는 테스트가
실패했다. 로컬 검증은 두 종류를 별도 process로 실행해 이 조합이 드러나지 않았다.

- UI·PDF 테스트 9개 파일은 `tests/browser_pages.py`의 `isolated_page()`로 pytest-playwright
  `browser` fixture에 테스트별 새 context를 연다. `test_procurement_document_binding.py`는
  기존 `tests/async_helper.run_async`를 쓴다. assertion은 바꾸지 않았다.
- 수정 후 CI(run 36652178786)는 실패 없이 84%까지 진행했지만 테스트 단계 25분 한도에서
  중단됐다. 그 runner는 첫 실행보다 구간별로 약 40% 느렸고, 앞서 error로 끝나던 UI 테스트가
  실제로 실행됐다. job 40분과 25분 한도는 늘리지 않고, CI 테스트 단계를
  `pytest tests/ -q --tb=short --ignore=tests/e2e`(25분)와 `pytest tests/e2e -q --tb=short`
  (10분, 앞 단계 실패 시에도 실행)로 나눴다. `test_ci_playwright_install_has_bounded_timeout_and_python_module_entrypoint`가
  두 단계의 명령과 한도를 확인한다.
- 로컬 재현: E2E 1개 뒤 같은 process에서 수정 대상 파일을 실행하면 수정 전 HEAD는
  5 failed, 6 errors, 수정 후 169 passed, 1 failed(로컬 `pdfplumber` 미설치, CI는 설치)였다.

### 다운로드와 재생성 경로 분리 (2026-09-28)

결과 화면의 공통 `내보내기`를 현재 탭의 `Markdown` 다운로드로 변경했다.
브라우저 Blob으로 UTF-8 `.md`를 내려받으며 서버 저장·생성 API를 호출하지 않는다.
편집 중 내용, 명시적인 빈 편집, 한글·표·경로·줄바꿈을 보존한다. 파일명에 문서 유형을
포함하고 경로 구분자·제어문자를 치환한다. 기존 다운로드 fallback 링크를 재사용한다.

형식별 다운로드는 현재 결과의 `/generate/export-edited` 변환만 사용한다.
결과가 없거나 변환이 실패해도 원요청의 생성 endpoint로 넘어가지 않는다.
누락된 시각자료가 Provider를 호출할 수 있어 strict boolean `generate_missing_visuals`를
추가했다. 결과·배치 다운로드는 `false`를 전달하며 제공된 시각자료는 유지한다.
이 경우 새 시각자료는 자동 생성하지 않는다. 필드를 생략한 API 호출은 기존 시각자료
생성을 유지하고, `/generate/export` API의 재생성·저장 계약도 그대로 남겨 둔다.
따라서 이 변경은 결과 화면의 다운로드 경계이며 모든 API의 무과금 보장이 아니다.

Python 3.12.12/pytest 8.3.2, dotenv 비활성화, 임시 DATA_DIR, mock/local,
AWS metadata 비활성화와 Python non-loopback 차단 조건에서 검증했다.
증빙 경로: `output/local-export-20260928-DdDCvy/`. 각 실행 수치를 합산하지 않는다.

| 관련 검증 | 결과 / 증빙 |
|---|---|
| 편집·저장·검토·알림 UI, 5개 형식 export API, 정적 다운로드 계약 | **93 passed**, 29.42s / `final-regression.xml` |
| 무료 모드 desktop/mobile 편집본 및 기본 Markdown 다운로드 | **3 passed**, 15.98s / `free-browser.xml` |
| 문서·스타일·검토·지식·조달 통합 | **27 passed**, 94.85s / `final-browser.xml`; 25 browser + 2 callback cases |
| 변경 Python Ruff E/F/W (E501 제외), `git diff --check` | passed |
| 별도 전체 app 800줄 제한 검사 | **1 failed**, 0.82s / `module-guide.xml`; 이번 변경 밖 6개 파일 |

API 검사는 이미지 생성이 필요한 outline을 사용해 Provider 선택, 이미지 생성,
billing admission을 금지한 상태에서 5개 형식 변환이 성공하는지 확인한다.
기존 시각자료 보존과 잘못된 boolean의 422도 검사한다. E2E는 실제 다운로드 bytes를
비교하고 다운로드 중 `/generate/*` POST가 없는지 검사한다. 입력창의 800ms 자동
추천 응답은 다운로드 전에 기다려 측정 구간을 구분한다. 초기 실행의 테스트 추출 오류와
추천 요청 혼입 실패는 보존하되 완료 근거로 사용하지 않는다.

```bash
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_edited_document_content_ui.py tests/test_edited_project_copy_ui.py \
  tests/test_generated_document_review_ui_static.py tests/test_notification_ui.py \
  tests/test_export_edited.py \
  tests/test_infrastructure.py::test_index_html_exports_current_generated_docs_without_regenerating \
  tests/test_infrastructure.py::test_index_html_keeps_blob_url_and_shows_download_fallback \
  tests/test_infrastructure.py::test_index_html_result_download_actions_use_event_listeners
DECISIONDOC_FREE_MODE=1 python3 -m pytest -p pytest_playwright.pytest_playwright \
  --browser chromium -p no:cacheprovider --tb=short \
  tests/e2e/test_edited_project_copy.py tests/e2e/test_main_flow.py::test_export_flow
python3 -m pytest -p pytest_playwright.pytest_playwright --browser chromium \
  -p no:cacheprovider --tb=short \
  tests/e2e/test_edited_project_copy.py tests/e2e/test_main_flow.py::test_export_flow \
  tests/e2e/test_local_style_import.py tests/e2e/test_generated_review_local_lifecycle.py \
  tests/e2e/test_knowledge_local_lifecycle.py tests/e2e/test_procurement_multi_opportunity.py \
  tests/e2e/test_procurement_requirement_applicability.py
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_infrastructure.py::test_app_python_modules_stay_within_800_line_guide
```

규모 검사 실패 대상은 `app/middleware/audit.py`(816),
`app/routers/projects/decision_evidence.py`(857), `app/routers/projects/procurement.py`(1077),
`app/routers/projects/procurement_reviews.py`(879),
`app/services/procurement_decision_package/package_builder.py`(803),
`app/storage/procurement_review_store.py`(851)다. 이 파일들은 이번 작업에서 수정하지 않았다.
변경한 `app/routers/generate/export.py`는 800줄이다. 기능 검증 통과와 저장소 규모
gate 실패를 구분하며 기존 dirty 변경을 임의 분할하거나 되돌리지 않았다.

Static UI와 export 경계를 함께 검사하기 위해 repo UI/docgen skill 및 기존 Playwright
검증 경로를 사용했다. 전체 suite/CI, native Office, 실제 모델 품질·운영은 미검증이다.
Starlette TestClient httpx deprecation warning 1건이 남아 있으며 설치로 해결하지 않았다.
새로 시작한 격리 서버에서 확인했고 기존 사용자 서버는 재시작하지 않았다.
기존 서버에 적용하려면 새 Python schema/route를 로드하도록 재시작이 필요하다.
실사용 데이터, 실제 Provider/AWS, 설치·배포·stage·commit·push는 실행하지 않았다.

### 섹션 다시 쓰기 결과의 초안 반영 (2026-09-28)

`섹션 다시 쓰기`가 DOM만 바꿔 복사·저장·내보내기에 반영되지 않는 경로를 수정했다.
Markdown renderer가 제공하는 heading line 위치로 원문의 해당 구간만 교체한다.
중복 제목, 코드 블록 속 heading, 인용문 heading을 구별하며 표·경로·escaped pipe와
나머지 구간을 보존한다. H1 경계도 넘지 않는다. 원본 generation Markdown은 유지하고
편집 draft를 갱신하므로 프로젝트 저장은 기존의 명시적인 편집본 저장 경로를 따른다.

취소·탭 전환·편집 시작·source 변경·인증 변경·화면 숨김 후 응답은 적용하지 않는다.
중복 제출과 빈/잘못된 응답을 막고, 제목은 HTML로 해석하지 않는다. 저장된 문서를
다시 열었을 때도 해당 문서의 bundle type으로 다시 쓰기 버튼을 연결한다.
버튼은 모바일·hover 없는 환경 및 키보드 focus에서도 표시한다.
API·provider·권한·저장 계약과 검토 완료 증빙은 변경하지 않았다.

초기 8개 실패 재현과 수정 후 증빙은 `output/section-rewrite-20260928-EN6nCA/`에 있다.
Python 3.12.12/pytest 8.3.2, dotenv 비활성화, 임시 DATA_DIR, mock/local,
non-loopback 연결 차단으로 실행했다. UI의 모델 응답은 stub이며 backend는 mock이다.
테스트를 위해 실제 사용자 데이터나 provider를 사용하지 않았다.

| 최종 관련 범위 | 결과 / 증빙 |
|---|---|
| 원문 편집·다시 쓰기·저장 UI, 검토 정적 검사, sketch UI, 다시 쓰기 API·편집본 export | **80 passed**, 19.92s / `final-regression.xml` |
| 문서·스타일·검토·지식·조달 통합 (버튼 표시 CSS 보완 전) | **26 passed**, 68.89s / `final-browser.xml`; 24 browser + 2 callback cases |
| 최종 표시 CSS 보완 후 desktop/mobile 다시 쓰기·저장·재열기·DOCX·focus | **2 passed**, 13.46s / `final-visibility.xml` |
| 변경 테스트 Ruff E/F/W (E501 제외), `git diff --check` | passed |

```bash
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_edited_document_content_ui.py tests/test_edited_project_copy_ui.py \
  tests/test_generated_document_review_ui_static.py tests/test_sketch_ui.py \
  tests/test_rewrite_section.py tests/test_export_edited.py
python3 -m pytest -p pytest_playwright.pytest_playwright --browser chromium \
  -p no:cacheprovider --tb=short \
  tests/e2e/test_edited_project_copy.py tests/e2e/test_local_style_import.py \
  tests/e2e/test_generated_review_local_lifecycle.py tests/e2e/test_knowledge_local_lifecycle.py \
  tests/e2e/test_procurement_multi_opportunity.py tests/e2e/test_procurement_requirement_applicability.py
```

Starlette TestClient의 httpx deprecation warning 1건은 남아 있으며 의존성 설치·변경은
하지 않았다. Chromium 검사는 기존 Playwright 경로를 사용한다. 실제 모델 품질,
native Word 열기·편집·저장, 인간 UAT, 전체 suite/CI는 이번 완료 범위가 아니다.
최종 표시 검사는 위 browser 명령에서 `tests/e2e/test_edited_project_copy.py`만 실행했다.
각 검증 수치는 별도 실행이며 합산하지 않는다. 재열기 화면·모달을 직접 확인했으며
실사용 데이터, AWS/provider 호출, stage·commit·push·배포는 실행하지 않았다.
당시 후속으로 남겼던 공통 `내보내기` 재생성 경로는 위의 다운로드 경로 분리에서 보완했다.

### 편집 중 문서 동작의 입력 일관성 (2026-09-28)

편집 완료를 누르기 전 입력이 draft에 반영되지 않아 내보내기·검토에서 이전 내용이
사용되고, 복사·요약은 완료한 편집도 무시하고 원문을 읽는 문제를 수정했다.
`textarea`의 input event가 해당 문서 draft를 즉시 갱신하며 복사·요약은 AI 검토와
같은 Markdown 조회 함수를 사용한다. 빈 편집은 원문으로 대체하지 않는다.
다른 탭의 문서, 원본 Markdown, 명시적인 원본 내보내기와 저장 schema는 유지한다.

실제 UI handler로 복사·요약·검토 입력, 실패 응답 후 입력 보존, 승인 요청 source와
지식 재사용 payload를 검사한다. 요약·AI 검토 응답은 로컬 stub으로 대체하며 실제
provider 품질을 입증하지 않는다. 편집본 E2E는 편집 완료 없이 DOCX 다운로드·저장 후
재열기를 수행하고 문단·표 셀을 읽어 입력 보존을 확인한다. native Word 시험은 아니다.

이번 실행 증빙은 `output/draft-actions-20260928-DAu4lf/`에 보존한다.
dotenv 비활성화, 임시 DATA_DIR, mock/local, non-loopback 연결 차단 조건을 사용한다.
초기 재현은 복사 내용 불일치 **2 failed**이며 `red.xml`에 기록했다.
최종 관련 검증은 아래와 같다. 기존 기록과 합산하지 않는다.

| 범위 | 결과 / 증빙 |
|---|---|
| 편집·복사·요약·검토·저장 UI와 검토 정적 안전장치 | **27 passed**, 9.46s / `final-ui.xml` |
| 편집본·스타일·검토·지식·조달 통합 | **26 passed**, 99.51s / `complete-browser.xml`; 24 browser + 2 callback cases |
| 변경 테스트 Ruff E/F/W (E501 제외), `git diff --check` | passed |

위 격리 환경에서 실행한 검사 범위:

```bash
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_edited_document_content_ui.py tests/test_edited_project_copy_ui.py \
  tests/test_generated_document_review_ui_static.py
python3 -m pytest -p pytest_playwright.pytest_playwright --browser chromium \
  -p no:cacheprovider --tb=short \
  tests/e2e/test_edited_project_copy.py tests/e2e/test_local_style_import.py \
  tests/e2e/test_generated_review_local_lifecycle.py tests/e2e/test_knowledge_local_lifecycle.py \
  tests/e2e/test_procurement_multi_opportunity.py tests/e2e/test_procurement_requirement_applicability.py
```

Chromium desktop/mobile 편집·재열기 화면도 확인했다. 전체 suite/CI, 실제 모델 품질,
인간 UAT와 운영 검증은 수행하지 않았다. 기존 사용자 데이터, provider/AWS, Git stage·
commit·push와 배포는 변경하지 않았다.

### 편집본과 표 내용 보존 보완 (2026-09-28)

문자열 표 행의 재생성에서 `\|`가 열 구분자로 되돌아가고 Windows 경로의
역슬래시가 사라지는 문제를 재현했다. 공통 Markdown 표 parser는 일반 문자 앞과
행 끝의 역슬래시를 보존하고, builder는 문자열·리스트 입력을 같은 셀 escaping으로
출력한다. 브라우저의 표 분리도 escaped pipe와 실제 구분자를 구별하며 기존
HTML escaping과 링크 검사를 유지한다. 전체 Markdown 문법 지원 확대는 아니다.

실제 편집본 E2E에서 렌더링된 `contenteditable`의 `innerText`가 빈 줄을 추가하는
별도 결함도 확인했다. 편집 중에는 표준 `textarea`의 원문 Markdown `value`를
읽고, 완료 후에는 기존 미리보기를 렌더링한다. 문단·표·코드 블록의 무수정 전환,
문서 탭별 draft, 명시적 빈 편집, 저장 실패 시 내용 보존을 검증했다. 저장 schema,
권한, 원본 generation 이력과 기존 검토 증빙은 바꾸지 않는다.

검증은 Python 3.12.12, dotenv 비활성화, 임시 DATA_DIR, mock/local 및 synthetic
자료를 사용했다. AWS metadata를 비활성화하고 Python의 non-loopback 연결을
차단했다. 브라우저 검사는 Chromium으로 실행했으며 서로 다른 harness를 동시에
실행하지 않았다. 초기 집중 재현은 8 failed/5 passed였고, 중간 브라우저 실행은
escaped pipe 표시 및 빈 줄 보존 실패가 있어 완료 근거로 사용하지 않았다.

최종 관련 검증은 각각 별도 실행이다. 아래 수치를 합산하지 않는다.

| 범위 | 결과 |
|---|---|
| 공통 표, DOCX/PDF/XLSX/HWPX/PPTX, 생성·golden·applicability packet 회귀 | **217 passed**, 89.83s |
| 원문 편집·HTML escaping·탭 draft·저장 실패/응답 유실 UI | **18 passed**, 8.90s |
| 편집본·스타일·검토·지식·조달 통합 | **26 passed**, 141.14s; 24 browser + 2 callback cases |
| 변경 Python 파일 Ruff E/F/W (E501 제외), `git diff --check` | passed |

```bash
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_markdown_utils.py tests/test_docx_endpoint.py tests/test_export_edited.py \
  tests/test_export_outline.py tests/test_excel_endpoint.py tests/test_hwp_endpoint.py \
  tests/test_pdf_endpoint.py tests/test_pptx_endpoint.py tests/test_golden_snapshots.py \
  tests/test_generate.py tests/test_procurement_applicability_packet.py
python3 -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_edited_document_content_ui.py tests/test_edited_project_copy_ui.py
python3 -m pytest -v -p pytest_playwright.pytest_playwright -p no:cacheprovider \
  tests/e2e/test_edited_project_copy.py tests/e2e/test_local_style_import.py \
  tests/e2e/test_generated_review_local_lifecycle.py tests/e2e/test_knowledge_local_lifecycle.py \
  tests/e2e/test_procurement_multi_opportunity.py tests/e2e/test_procurement_requirement_applicability.py \
  --browser chromium --tb=short --show-capture=no
```

위 명령은 앞서 명시한 격리 bootstrap 안에서 실행했다. 증거는
`output/markdown-fidelity-20260928-hKL7ea/`의 `red.xml`, `regression.xml`,
`editor-textarea.xml`, `complete-browser.xml`에 있다. `complete-browser/`의
desktop/mobile 편집·재열기 화면도 확인했고, 다운로드 DOCX의 실제 셀 값과 저장된
Markdown을 원문과 비교했다. 중간 실패 기록은 덮어쓰지 않았다.

DOCX 재저장 검사는 python-docx 기반 구조/내용 확인이며 Microsoft Word 앱의
열기·편집·저장이나 전체 문서 시각 검수를 대신하지 않는다. 기본 Applications
경로에 Word가 없고 workspace dependency 응답에 번들 Office renderer 경로가 없어
native Office 검증은 실행하지 않았다. Human UAT와 실제 모델 품질은 여전히 남는다.
기본 앱 활성화, 실제 사용자 데이터 변경, 유료/provider/AWS/G2B 호출, training,
배포, staging/commit/push는 수행하지 않았다. 테스트와 임시 서버는 정상 종료했다.

### Historical CI Baseline (2026-09-04)

- 아래 CI baseline의 source commit: `f993267e427678f0b1240c4fe4f19617ba362181` (문서 동기화 전 clean `origin/main` snapshot). 현재 미커밋 completion 변경의 검증은 별도 local subsection 기준이다.
- 기준일: 2026-09-04. 최종 tree의 Python 3.12 GitHub Actions 결과는 이 절의 아래 재현 명령과 [CI run 33822098256](https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/33822098256)에 함께 기록한다.
- 범위: `ENVIRONMENT=test`, `DECISIONDOC_PROVIDER=mock`, `DECISIONDOC_STORAGE=local`, `DECISIONDOC_TEMPLATE_VERSION=v1`, `DECISIONDOC_ENV=dev`의 CI 전체 테스트다. 5개 skipped test는 실행 증거로 계산하지 않는다. provider API, AWS runtime, live G2B, upload, training, promotion, deploy, production service resume, approval, bid/legal/contractual action은 실행하거나 증명하지 않는다.
- readiness: M1은 historical OpenAI proof가 있어도 Gemini/Claude/fallback external proof가 남아 **partial/blocked**다. M2는 local live G2B smoke가 완료됐지만 durable stage proof가 없어 **partial/blocked**다. M6는 deployment/runtime evidence가 없어 **blocked**다. human UAT와 external approval도 미증명이다.

```bash
# GitHub Actions Test (Python 3.12), .github/workflows/ci.yml
ENVIRONMENT=test \
DECISIONDOC_PROVIDER=mock \
DECISIONDOC_STORAGE=local \
DECISIONDOC_TEMPLATE_VERSION=v1 \
DECISIONDOC_ENV=dev \
pytest tests/ -q --tb=short
```

Final-tree CI result (2026-09-04): **4,783 passed, 5 skipped, 1 warning** in
`1187.14s`. Secret Hygiene, advisory Ruff lint, and advisory Security Scan jobs
also completed successfully in the same run. This is GitHub-hosted local/mock
test evidence, not live-provider or deployment-runtime evidence.

The merged CD authority gate at source commit `f993267e...` caused the ordinary
`main` push to run CI only; no CD run was created. Earlier [CD run
33716106642](https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/33716106642)
built and published an image for `4b075fad...`, but both the actual staging
deploy and smoke steps were skipped because the staging secrets were absent.
The later [canceled legacy-triggered run
33736731654](https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/33736731654)
left a mutable GHCR `main` tag for `b7873bb...` without a GitHub Deployment
record. These registry and workflow observations do not close M6 or authorize
a deployment.

### Local Completion Goal (2026-09-05)

대상은 `codex/generated-document-review-completion-20260904`의 미커밋 변경이다.
설계는 [Local-First Product Design](./architecture.md#local-first-product-design),
실행 순서는 [Current Local Completion Goal](./product_execution_plan.md#0-current-local-completion-goal)을 따른다.
이 첫 Goal에서는 `generated-document-review-completion`의 기존 approved
local/fake-S3 범위만 구현했고 verifier 후보는 draft로 남겼다. 이후 별도 사용자
승인에 따른 CLI 구현은 아래 후속 subsection으로 구분한다.

직전 completion 구현의 전체 non-live 실행은 **4,796 passed, 2 skipped,
4 deselected, 1 warning in 1720.37s**였다. 이는 이전 작업의 terminal 결과이며
아래 strict verifier 보완 이후의 full-suite 결과나 remote CI 결과가 아니다.
재현 명령은 `python3 -m pytest -q tests/ -m 'not live' --tb=short`다.

이번에는 authority/count의 boolean-integer 혼동과 expected-record packet size
누락을 6개 실패 테스트로, list/object decision의 처리되지 않은 TypeError를
2개 실패 테스트로 재현했다. Canonical JSON 타입과 실제 원본 packet 크기를
결속하고 잘못된 decision은 명시적 package validation error로 거부한다.
이전 pending record/schema와 exact replay 계약은 바꾸지 않는다.

최종 focused 검증 결과:

| 범위 | 결과 | 재현 명령 |
|---|---|---|
| Packet/review API, local/fake-S3, browser static, feature gate | **113 passed**, 1 warning in `80.67s` | `python3 -m pytest -q tests/storage/test_generated_document_review_store.py tests/test_generated_document_reviews.py tests/test_generation_export_packet.py tests/test_generated_document_review_ui_static.py tests/test_future_feature_gate.py --tb=short` |
| Infrastructure wiring | **2 passed**, 178 deselected, 1 warning in `0.38s` | `python3 -m pytest -q tests/test_infrastructure.py -k generated_document_review --tb=short` |
| Chromium review workflow | **8 passed**, 103 deselected in `8.10s` | `python3 -m pytest -q tests/e2e/test_main_flow.py -k generated_document_review --browser chromium --tb=short` |
| README metrics | **3 passed** in `10.55s` | `python3 -m pytest -q tests/test_count_readme_metrics.py --tb=short` |
| Portfolio contract | **7 passed** in `0.46s` | `python3 -m pytest -q tests/test_manage_portfolio_pack.py --tb=short` |

Ruff `python3 -m ruff check app/ tests/ --select E,F,W --ignore E501`와 변경한
Python 파일의 `py_compile`은 PASS다. 기존 approved gate는 그대로 admission
PASS이고, 새 verifier draft는 구조 검증 PASS 및 `--require-approved`에서 의도한
exit 1이다. 이 structural validator는 승인자 신원을 인증하는 도구가 아니다.
기존 승인 파일의 SHA-256은
`b4bb5bc5a3908556e2d93c4df605c211f5fedfbc4958211d8ef97e98714bff98`로 유지된다.

`python3 scripts/manage_portfolio_pack.py sync`와 `check`로 tracked 문서
mirror를 동기화하고 membership/byte/link 일치를 확인했다. 새 gate JSON과
상세 completion spec은 로컬 source에 보존하며 기존 tracked-docs portfolio
선정 범위를 임의로 넓히지 않는다. `git diff --check`도 PASS다.

이번 보완 후 full-suite는 다시 실행하지 않았다. 위 focused 결과를 이전 전체
결과와 합쳐 새로운 full-suite PASS로 계산하지 않는다. Warning은 기존
Starlette TestClient의 httpx deprecation이다. Human UAT, 실제 다운로드 산출물의
사람에 의한 내용/레이아웃 검수, live provider/AWS/G2B, M1/M2/M6는 이 Goal에서
증명하지 않는다. Commit, push, merge, publish도 실행하지 않는다.

### Reviewed-Package Verifier CLI (2026-09-05)

사용자가 `generated-document-reviewed-package-verifier`의 exact local CLI·tests·
문서 범위를 승인해 구현했다. 승인 전 draft SHA-256은
`d44ffb960c266ab5f1bb525e88596238184b36a27ed4f8bb3c3d048efb7dce22`,
승인 기록 SHA-256은
`508423541077c96ac0c5fff9630ab437e73d1b48e7db78da914e84dbac11d478`다.
기존 completion 승인과 pure verifier, 원본 packet CLI의 bytes는 변경하지 않았다.

새 `scripts/verify_generated_document_reviewed_package.py`는 macOS/Linux에서
regular non-symlink 파일을 `O_NOFOLLOW | O_NONBLOCK`으로 읽고 descriptor의
크기와 기존 최대 크기를 검사한 뒤 pure verifier에 bytes를 전달한다.
결과는 versioned JSON의 packet/receipt/package hashes, package size, decision과
false operational authority만 출력한다. Archive 추출, 저장소 접근, 앱 시작,
네트워크, 자격증명 읽기 또는 검토 상태 변경은 하지 않는다.

CLI가 없을 때 세 decision의 subprocess 테스트가 실패하는 RED를 확인한 뒤
구현했다. Valid/invalid 실제 CLI subprocess, 변조·deep JSON·DEFLATE 오류,
정보 비노출, regular-file/size 경계, descriptor recheck와 audit-hook 차단 검사가
전용 회귀 범위다. 최종 검증은 다음과 같다.

| 범위 | 결과 | 재현 명령 |
|---|---|---|
| CLI subprocess와 파일/오류 경계 | **32 passed** in `4.32s` | `python3 -m pytest -q tests/test_verify_generated_document_reviewed_package.py --tb=short` |
| CLI + 기존 packet/review/API/storage/gate | **138 passed**, 1 warning in `28.94s` | `python3 -m pytest -q tests/test_verify_generated_document_reviewed_package.py tests/test_generation_export_packet.py tests/storage/test_generated_document_review_store.py tests/test_generated_document_reviews.py tests/test_future_feature_gate.py --tb=short` |
| README metrics + portfolio 계약 | **10 passed** in `2.02s` | `python3 -m pytest -q tests/test_count_readme_metrics.py tests/test_manage_portfolio_pack.py --tb=short` |

CLI 전용 32건은 combined 138건에도 포함되며 별도로 합산하지 않는다.
Combined 실행 후 새 파일의 formatting과 strict false assertion을 반영하고
CLI 전용 회귀를 다시 실행한 결과가 위 32건이다. CLI `--help` 실제 실행,
approved gate의 `--require-approved`, Ruff E/F/W, 새 파일 format check,
변경 Python의 `py_compile`, portfolio sync/check와 `git diff --check`가 PASS다.
Warning은 기존 Starlette TestClient httpx deprecation이다. Portfolio는 기존
tracked-docs 선정 범위를 유지하며 새 CLI/test source를 공개 pack에 추가하지 않는다.

이번 범위에는 UI/API/schema/storage 변경이 없고 기존 pending/completed 계약을
그대로 재사용한다. Full-suite와 browser E2E는 이번 CLI 변경에서 재실행하지
않으며 위 완료 Goal의 결과를 새로운 실행 결과로 합산하지 않는다. Human UAT,
실제 문서 내용·레이아웃 검수, M1/M2/M6, AWS/provider/G2B와 배포 증거는 남아 있다.

---

## 1. "완성"의 정의

이 프로젝트에서 완성은 "기능이 많다"가 아니라 다음 3가지를 충족한 상태로 정의한다.

| 축 | 현재 | 완성 기준 |
|----|------|-----------|
| **기능 검증** | 현재 local/mock final-tree 결과와 외부 proof gap은 [Current Completion/Readiness Snapshot](#0-current-completionreadiness-snapshot) 기준. 2026-08-11 local live G2B smoke 1건은 historical local evidence | live LLM 잔여 provider와 G2B durable receipt/stage 경로도 실증 + 증적 |
| **아키텍처 위생** | ✅ 달성 (2026-07-14: 829줄 상수 모듈을 604줄 facade + 314줄 foundation으로 분리하고 800줄 guard 추가 → 초과 0개). CI advisory Ruff E/F/W와 Bandit medium/high 0건 기준 유지 | 전 모듈 800줄 이하 (전역 코딩 가이드), 계층 간 의존 방향 일관 |
| **운영 준비성** | Docker/SAM 설정과 explicit CD authority gate가 존재한다. 2026-09-03 Docker image publish 뒤 staging deploy/smoke는 secret 미설정으로 skip됐고, 2026-08-11 current-main dev deploy-smoke는 AWS 진입 전 OIDC role assume에서 실패했다 | OIDC trust 복구 + 배포 절차 재검증 + post-deploy smoke 증적 |

```bash
# 현재 final-tree CI command와 result: section 0 Current Completion/Readiness Snapshot

# 재현: CI advisory lint/security 베이스라인
ruff check app/ tests/ --select=E,F,W --ignore=E501
bandit -r app/ -x app/providers/mock_provider.py -ll

# 재현: 남은 외부 실증 준비 조건 점검(외부 호출 없음)
python3 scripts/check_completion_readiness.py --print-env-template
python3 scripts/check_completion_readiness.py --print-proof-plan
python3 scripts/check_completion_readiness.py
python3 scripts/check_completion_readiness.py --env-file .env.prod
python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json
python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json
```

2026-08-12 DocumentOps strict skill binding focused gate는 registry·Agent·API·operation store·audit `143 passed`였다. 이는 mock provider와 local/fake-S3 범위의 재측정이며 위 full non-live baseline, live provider 품질 또는 AWS runtime 증거를 대체하지 않는다.

같은 날짜 browser binding boundary의 static focused command는 `4 passed`, local Chromium focused command는 `9 passed`였다. Static check는 exact eight-field binding validator, top-level skill/version agreement, invalid response의 pre-success 차단과 allowlisted provenance renderer를 검사한다. Chromium check는 valid first run과 exact replay, malformed·authority-widened·mismatched response rejection, 기존 Agent recovery 흐름을 검증했고 desktop과 390px mobile screenshot에서 provenance overlap과 horizontal overflow가 없음을 확인했다. Browser console과 page error도 비어 있었다. 이 결과는 local loopback과 mock response 범위이며 live provider나 배포 runtime 증거를 대체하지 않는다.

DocumentOps comparison review는 source-grounded task와 함께 UI에서 선택할 수 있는 first-party skill이다. 비교 입력은 provider·captured-operation claim 전에 검증하고, `comparison_criteria`는 생략 시 `[]`이며 최대 8개·각 120자다. Local mock/backend와 loopback Chromium 측정은 exact UTF-8 hash context, raw-input trajectory redaction, exact replay, malformed context pre-success rejection과 390px overflow를 대상으로 하며 semantic change·policy/legal/operational effect는 사람 재확인 대상으로 남긴다. GitHub-derived skill-pattern reference는 [external repository analysis](./specs/external_repo_integration/ANALYSIS_20260812.md)의 clean-room design 기록만 사용하며 remote skill loading, dynamic install, provider/training/deploy/publication authority를 추가하지 않는다. Live provider, AWS runtime, external completion proof는 M1/M6의 기존 갭으로 변함없다.

Comparison file intake는 동일 task 안의 optional local convenience path다. Existing attachment parser의 20 MB upload와 12,000-character cap을 그대로 사용하고 `.hwp` legacy binary, unsupported, empty, unreadable input을 bounded `422`로 거부한다. API response와 browser check는 exact selected source bytes와 returned UTF-8 text hash를 결속하지만, semantic equivalence, source authenticity, policy/legal effect 또는 file retention을 주장하지 않는다. 이 path는 deterministic server-memory extraction만 제공하며 provider fallback/OCR, storage persistence, training, AWS, deployment, publication과 approval authority를 추가하지 않는다.

Verified line change set은 Agent provider 요청보다 먼저 local-only deterministic evidence를 만든다. 하나의 `SequenceMatcher(autojunk=False)` 결과로 full aggregate와 hunk를 계산하고 response 전체의 양쪽 exposed line 합계를 200으로 제한한 contiguous zero-prefix만 반환한다. 첫 초과 hunk는 exposed array와 half-open range를 함께 clip하며, `total_hunk_count`와 `hunks_truncated`는 전체 opcode coverage를 보존한다. Browser가 exact response bytes/header hash, fatal UTF-8, canonical JSON, strict schema, source hash/line/range/count, all-false authority와 current provenance를 모두 확인해야 Agent POST와 download가 열리고, 입력·criteria·task·tenant·auth 또는 request generation 변경은 evidence와 object URL을 폐기한다. 이 local change set은 semantic review, live provider 품질, AWS/deployment/public edge, persistence, training, approval 또는 external effect evidence가 아니다.

```bash
python3 -m pytest -q tests/test_infrastructure.py -k document_ops_agent --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k document_ops_agent --tb=short
python3 -m pytest -q tests/agents/test_skill_registry.py tests/agents/test_document_ops_agent.py tests/evals/test_document_ops_gates.py tests/test_document_ops_agent_api.py --tb=short
python3 -m pytest -q tests/test_infrastructure.py -k document_ops --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k document_ops --tb=short
python3 -m pytest -q tests/test_document_ops_agent_api.py -k comparison_document --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k comparison_file_intake --tb=short
python3 -m pytest -q tests/agents/test_document_ops_agent.py -k comparison --tb=short
python3 -m pytest -q tests/test_document_ops_agent_api.py -k comparison --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k comparison_change_set --tb=short
```

### H120 local slice

Project procurement packet은 활성 tenant admin/member의 stable user ID에 담당자를 결속하고, completion은 같은 current session-bound principal만 허용한다. v2 reviewed package attestation은 trusted tenant/project/user scope로 재검증하며 approval, bid, legal, contractual authority를 만들지 않는다. Focused H120 `64 passed`, auth/security/tenant `216 passed`, focused Chromium `1 passed`, 전체 non-live `4437 passed, 1 skipped, 4 deselected`로 no-cost 검증했다.

### H121 session-bound review access

Review packet preparation, inbox, project history와 reviewed package download는 current session-bound admin/member만 접근한다. Admin은 tenant-wide review를 관리하고 member는 자신에게 결속된 v2 evidence만 읽는다. HTTP와 browser surface는 stable target ID, receipt, rationale, attestation, session/network metadata를 노출하지 않으며 current assignment와 access scope만 사용한다. 기존 v1 storage와 reviewed package는 admin read compatibility를 유지한다. Focused procurement/auth/storage `191 passed`, focused Chromium `3 passed`, 최종 전체 non-live `4444 passed, 2 skipped, 4 deselected`로 no-cost 검증했다.

### H122 verified original review packet re-download

현재 session-bound admin 또는 stable v2 assignee는 저장된 원본 review packet을 다시 내려받을 수 있다. Route는 authorization 뒤에만 bytes를 읽고 SHA-256, receipt/record binding, package semantics와 recommendation을 다시 검증한다. Browser는 safe response headers, byte length와 SHA-256을 확인한 뒤 download를 시작하며 auth, tenant, user, project context가 바뀌면 scoped object URL과 fallback link를 폐기한다. Legacy v1은 admin-only이고 review reassignment/completion, operational approval, bid submission, provider/training/deploy authority는 추가하지 않았다. Post-review focused API/audit/infrastructure `286 passed`, focused Chromium `3 passed`, 전체 Chromium `88 passed, 1 skipped`, 전체 non-live `4448 passed, 2 skipped, 4 deselected`로 no-cost 검증했다.

### H123 Decision Evidence Map

Project detail은 procurement, Decision Council, project document, authorized
review summary, approval, report workflow와 knowledge metadata를
`decision_evidence_map.v1` read-only projection으로 연결한다. Member는 자신의
exact review assignment가 확인된 뒤에만 project를 읽고, unassigned,
differently assigned, nonexistent ID는 동일한 not-found 결과로 닫는다.
Canonical `requirement:` reference만 explicit reference coverage를 만들며
requirement 만족 증명으로 승격하지 않는다. Proposal Blueprint는 stored
reference count와 PPTX readiness만 보여주고 export/provider/approval/bid/legal
authority를 만들지 않는다. Luna 독립 review에서 발견한 assignment access,
existence oracle, misleading evidence label과 800-line guide 문제를 모두
해소했다. Focused Decision Evidence `16 passed`, 인접 project/report/review/
approval/Council/PPTX `383 passed`, focused+infrastructure `184 passed`, 최종
전체 non-live `4465 passed, 1 skipped, 4 deselected`로 no-cost 검증했다.
이 수치는 2026-07-24 H123 historical baseline이며 H124 current pass 수치가 아니다.

### H124 Evidence Neighborhood Explorer

H123 projection을 변경하지 않고 project detail의 read-only 탐색성을 강화한다.
Browser state는 tenant, user, auth revision, project, bundle, projection
fingerprint에 결속하고 scope 변경 시 선택·filter·presentation layout을 초기화한다.
Bounded response에서 O(N+E) adjacency index를 만들고 selected node의 inbound/
outbound relation과 stored provenance를 표시한다. One-hop focus/dimming,
gaps/lineage/source visibility filter, diagnostic target navigation, keyboard
focus restoration, reduced-motion, 60-node SVG priority와 complete table을
제공한다. 이 surface는 approval, export execution, provider/training, bid
submission 또는 legal authority를 만들지 않는다.

Luna review 반영으로 filtered diagnostic target은 다른 node로 대체하지 않고
명시적으로 포함하며 filter summary에 그 상태를 표시한다. Source visibility는
detail relation과 incident edge에도 적용한다. SVG는 pointer interaction만 남긴
장식 surface이고 table button이 canonical keyboard surface다. Provenance level은
authoritative=solid, record binding=dashed, derived=dotted line style로
비색상 설명하며 proof/approval을 뜻하지 않는다. Content SHA-256도 projection이
관측한 field-content binding일 뿐 external authenticity 검증이 아니다.
2026-07-27 no-cost fresh gate는 H124 UI/service/E2E subset `17 passed`, API를
포함한 focused `21 passed`, adjacent authorization/workflow `387 passed`,
combined union `404 passed`, full non-live `4,470 passed, 1 skipped,
4 deselected`다.

### H125 Guided Decision Review

Project detail의 existing decision, Evidence Map, review, document record를
Decision → Evidence → Review → Documents 순서의 읽기 전용 검토 navigator로
묶는다. 하나의 overall state와 recommended next check만 표시하며 status는
`not_observed`, `needs_attention`, `in_review`, `observed`로 제한한다.
`decision_evidence_map.v1`의 exact top-level/nested shape, coverage invariant,
bounded graph, fingerprint와 여섯 false authority flag가 모두 유효할 때만
panel을 렌더링한다. Map이 없거나 malformed, authority-drifted이면 다른
project payload에서 evidence state를 재구성하지 않고 숨긴다.

Stage control은 기존 section으로 scroll/focus만 수행한다. 승인, export,
provider, bid submission, legal/contractual action을 호출하지 않는다.
Accepted review는 acceptance record 관측일 뿐 current freshness가 아니며,
document는 canonical review/Council/provenance status 중 하나 이상이
관측되고 모두 `current`일 때만 current로 표시한다. Council payload가
독립 요청에서 빠져도 map의 stale/conflict diagnostic은 Decision
precedence를 유지한다. Luna independent review의 malformed map, document
freshness, Council diagnostic, NO_GO copy, informational diagnostic severity,
loading-path 회귀를 모두 보완했다.

2026-07-27 no-cost fresh gate는 H125 focused `7 passed`, H124+H125 static/E2E
`13 passed`, adjacent authorization/workflow `387 passed`, combined union
`411 passed`, full non-live `4,477 passed, 1 skipped, 4 deselected`다.

### H126 Guided Decision Review Handoff

현재 Guided Decision Review의 four-stage observation을 current
session-bound admin 또는 exact stable v2 assignee가 canonical JSON attachment로
내려받을 수 있다. Route는 authorized `decision_evidence_map.v1` context와
project document provenance를 다시 관측하고
`guided-decision-review-handoff.v1`을 만든다. Exact body SHA-256과 source
projection fingerprint를 response header에 결속하고 `no-store`, `nosniff`,
attachment disposition을 고정한다.

Browser는 body hash, contract/source version, tenant/user/auth revision/project
load scope, project/bundle/fingerprint, non-empty fresh-route source timestamp,
exact four-stage status, overall/next check와 six false authority fields를
현재 panel과 다시 대조한 뒤 download한다. Route가 projection을 새로
계산하므로 source timestamp는 화면 map과 달라질 수 있고 semantic binding은
timestamp equality가 아니라 exact fingerprint equality를 사용한다.
Handoff는 저장하지 않으며
`read_only=true`, `snapshot_atomic=false`,
`requires_recheck_before_reliance=true`, `handoff_persisted=false`다. 따라서
download hash는 exact bytes만 증명하며 currentness, atomic snapshot, proof,
approval, export/provider/bid/legal authority를 만들지 않는다.

2026-07-28 no-cost focused gate는 H126 service/API/static/Chromium
`15 passed`, H123-H126 map/guided-review integration `38 passed`, reusable
document provenance serializer를 포함한 project/map regression `149 passed`,
authorization/audit/security/infrastructure expansion `477 passed`다. 전체
non-live는 `4,487 passed, 1 skipped, 4 deselected`다.

### H127 Guided Decision Review Handoff Recheck

Browser가 H126 response의 exact body hash, safe headers, contract, current map과
tenant/user/auth/project scope를 검증한 경우에만 source handoff를 page memory에
보존하고 recheck를 활성화한다. Session-bound read-only POST route는 strict H126
source와 canonical SHA-256, route project와 current bundle binding을 확인한 뒤
같은 service path로 fresh H126 observation을 만든다.

`guided-decision-review-recheck-receipt.v1`은 source/current handoff와 각 exact
hash, `source_generated_at`만 제외한 두 semantic fingerprint, expected
`unchanged|changed` status를 canonical JSON으로 결속한다. Receipt와 audit은
review-only/read-only/non-atomic/recheck-required/non-persisted 경계와 six false
authority를 유지한다. `changed`는 정상 비교 결과이며 browser는 receipt를
검증·다운로드한 뒤 old source를 폐기하고 fresh project load/handoff를
요구한다. Client-supplied source는 prior server issuance를 증명하지 않고
`unchanged`도 future currentness나 atomic snapshot을 보장하지 않는다.

2026-07-28 no-cost gate는 H126/H127 service/API/static/Chromium `23 passed`,
H123-H127 map/guided-review integration `46 passed`, authorization/audit/
security/infrastructure expansion `481 passed`, full non-live `4,495 passed,
1 skipped, 4 deselected`다. Provider, AWS, G2B, dataset upload, training,
promotion, deployment와 service resume은 실행하지 않았다.

### H128 Guided Decision Review Disposition

Browser가 exact body/header/contract/scope를 검증한 H127 receipt만 page memory에
보존하고 allowlisted disposition을 선택할 수 있다. Session-bound read-only
POST route는 strict H127 receipt, canonical receipt hash, route project/current
bundle, current handoff/fingerprint, expected status를 다시 검증한다.

H128 canonical body는 기존 byte contract를 유지한다. 성공 응답 전 selected
backend에는 tenant/project/bundle/exact H128 SHA-256 scope의 strict
`guided-decision-review-disposition-issuance.v1` metadata가 conditional-create와
exact read-back으로 존재해야 한다. H129 v2는 이 same-backend issuance metadata를
독립 재검증해 metadata와 hash만 embed하며, v1 record는 migration 없이 Legacy
issuance unrecorded로 남는다. New H129 operation은 v2만 create하고 public v1
request는 matching existing v1의 exact replay만 허용하며 missing v1 write는 없다.
이 proof는 signature, actor attestation,
currentness, atomic snapshot, approval 또는 external authenticity가 아니다.

`guided-decision-review-disposition-receipt.v1`은 source receipt hash, current
handoff/fingerprint hash, `unchanged|changed` status와 disposition을 canonical
binding으로 결속한다. `unchanged`에는
`acknowledged_unchanged|review_deferred`, `changed`에는
`new_handoff_required|review_deferred`만 허용한다. Receipt는 review-only,
read-only, non-atomic, recheck-required, non-persisted이며 reviewer identity,
approval, mutation, export, provider, bid 또는 legal/contractual authority를
만들지 않는다.

Luna review에서 nested fixed-field 누락이 Pydantic default로 복원되던 문제,
POST bundle allowlist 우회, auth/tenant invalidation 뒤 page-memory source가
남던 문제를 찾았다. Terra remediation은 raw request의 명시 필드 검증,
schema-level bundle allowlist, 중앙 source cleanup으로 세 경계를 닫았다.
재검토에서 cross-tab auth event의 cleanup 우회와 pre-parsed service receipt의
field-set 소실을 추가로 찾아 같은 validator와 cleanup 경로로 보완했고, final
Luna review는 findings 없이 종료됐다.

2026-07-29 no-cost gate는 H126-H128 service/API/static/Chromium `37 passed`,
H123-H128 map/guided-review integration `60 passed`, authorization/audit/
security/infrastructure expansion `488 passed`, full non-live `4,509 passed,
1 skipped, 4 deselected`다. Provider, AWS, G2B, dataset upload, training,
promotion, deployment와 service resume은 실행하지 않았다.

### H129 historical reviewer-attributed registry evidence (2026-08-18)

H129 persists one exact H128 receipt as immutable reviewer-attributed evidence
under tenant/project/bundle/hashed-operation scope. First create returns 201;
an exact replay after username or role drift returns 200 with the original
canonical bytes and historical identity, while stable reviewer or source drift
conflicts without rewriting the authoritative record. All registry paths
strictly revalidate the nested H126-H128 chain, request/full-record bindings,
scope, matrix, hashes, and false authority before returning data.

Admin access is project-wide and assigned member access is stable-user scoped.
Browser create is enabled only from current verified page-memory H128 evidence,
uses one UUID per source/scope plus request-owned single flight, and discards
late responses after auth/tenant/user/project/bundle/source drift. 이 H129
historical registry evidence는 reviewer-attributed immutable record의 초기 검증
기록이다. 당시 숫자는 historical evidence이며 아래 H129.1 server-issued
provenance의 current meaning 또는 현재 final-tree snapshot을 대체하지 않는다.
H129도 M1/M2/M6, human UAT, deployment, external approval gap을 닫지 않으며,
provider, AWS, G2B, upload, training, promotion, deploy, approval, bid, legal,
contractual effects는 범위 밖이다.

2026-08-18 local/mock verification은 H129 focused storage/API/auth/audit
`16 passed`, adjacent handoff/static `28 passed`, focused Chromium
`1 passed, 13 deselected`, full non-E2E non-live `4,596 passed, 4 deselected`,
full non-live E2E `121 passed, 1 skipped`를 확인했다. Ruff E/F/W, `py_compile`,
Bandit medium/high, secret hygiene, portfolio와 diff gates도 통과했다.

### H129.1 current server-issued provenance (2026-08-18)

H128 success는 selected tenant/project/bundle backend에 exact canonical receipt
SHA-256의 hash-only issuance metadata를 conditional-create하고 exact read-back한
뒤에만 반환된다. H129 v2는 그 **same-backend** metadata와 metadata hash만 독립
재검증하여 `issuance_provenance=server_issued`로 결속한다. v1 bytes는 rewrite나
migration 없이 `legacy_issuance_unrecorded`로 남는다.

이는 server-issued provenance의 local storage/integrity evidence일 뿐 signature,
actor attestation, currentness, atomic snapshot, approval 또는 external
authenticity가 아니다. H129 historical reviewer attribution과 H129.1 provenance를
혼동하지 않으며, 둘 다 M1/M2/M6, human UAT, deployment, external approval과 모든
external effect gap을 닫지 않는다.

---

## 2. 현재 아키텍처 (실측 기반)

배포·인프라 관점 구성도(Nginx/TLS/PWA 포함)는 [architecture.md](./architecture.md) 참조. 여기서는 코드 레이어 관점을 다룬다. 레이어 수치는 아래 커맨드로 재측정 가능하다.

```bash
python3 scripts/count_readme_metrics.py --field router_files      # → 23 (top-level 라우터 파일)
python3 scripts/count_readme_metrics.py --field service_files     # → 59 (서비스)
python3 scripts/count_readme_metrics.py --field storage_files     # → 59 (top-level storage modules)
python3 scripts/count_readme_metrics.py --field middleware_files  # → 14 (미들웨어)
python3 scripts/count_readme_metrics.py --field route_decorators  # → 317 (라우트)
python3 scripts/count_readme_metrics.py --field test_files        # → 283 (테스트 파일)
python3 scripts/count_readme_metrics.py --field test_functions    # → 3913 (Python AST test_ 정의; pass 수 아님)
```

```text
Client (Web UI / CLI / API)
  │
  ▼
FastAPI (app/main.py — create_app(), 모듈 레벨 side-effect 없음)
  │
  ├─ Middleware layer (12개 Python 모듈)
  │     request chain: CORS → observability → request_id → security_headers
  │       → rate_limit → auth → tenant → billing → audit → metrics
  │     audit context helpers: document_ops_audit / auth_session_retention_audit
  │       / procurement_review_audit
  │
  ├─ Routers (23 top-level files, 라우트 317):
  │     generate / approvals / projects / knowledge / report_workflows
  │     auth / sso / admin / audit / billing / dashboard / history
  │     eval / finetune / local_llm / g2b / document_ops_agent
  │     templates / styles / messages / notifications / events / health
  │
  ▼
Services (51) — 도메인 오케스트레이션
  ├─ generation_service ─ 핵심 파이프라인:
  │     요청 → 캐시 → Provider.generate_bundle() → 스키마 검증
  │        → Stabilizer → Storage 저장 → Jinja2 렌더 → Lint → 반환
  ├─ export 계열: docx / pptx / pdf / hwp / excel (5종)
  ├─ 조달 계열: g2b_collector → procurement_decision_service
  │     → procurement_decision_package/ (16-모듈 패키지, 2026-07-02 분할 후 확장)
  └─ 품질 계열: report_quality_learning / prompt_optimizer / validator
  │
  ├────────────────┬─────────────────────┐
  ▼                ▼                     ▼
Providers (5)    Storage (55 modules)   Ops
  factory +        factory +             CloudWatch 조사
  fallback chain   Local / S3            Statuspage 연동
  mock / openai    (atomic write 공통)   eval / eval_live
  gemini / claude
  local
```

**설계 불변식** (변경 시 이 문서를 갱신할 것):

1. Provider·Storage는 ABC + factory — 구현 교체는 환경변수로만.
2. 모든 파일 쓰기는 atomic write(tmp + fsync + os.replace).
3. 라우트 핸들러는 `request.app.state.*`로 의존성 접근, `os.getenv` 직접 호출 금지.
4. 신규 Request 모델은 `ConfigDict(strict=True, extra="forbid")` 필수.
5. mock provider는 결정론적 — CI/CD와 로컬 데모의 기준 경로.
6. Persisted review evidence는 missing과 corrupt를 구분하고, immutable artifact를 먼저 검증한 뒤 record를 conditional create/CAS로 확정하며 domain conflict와 store failure를 다른 오류 경계로 전달한다.
7. Project/approval mutation은 각 tenant별 단일 state object의 검증된 원문을 expected value로 사용하고, conditional create/CAS 충돌마다 최신 ownership·schema를 다시 검증한다. Approval은 상태 transition도 다시 검증한다.
8. Report workflow mutation은 tenant별 단일 state object에서 conditional create/CAS를 사용하고, 충돌마다 최신 workflow state와 domain transition을 재검증한다. Bounded mutation receipt는 public schema와 분리하고 손상 시 fail closed 처리한다.
9. Audit append는 기존 JSONL byte prefix를 보존한 채 conditional create/CAS로 확정하고, 충돌마다 최신 evidence를 다시 검증한다. 불확실 commit은 `log_id`와 exact entry read-back으로 조정한다.
10. Template/history/share mutation은 각각 tenant별 단일 state object에서 conditional create/CAS를 사용하고, 충돌마다 최신 ownership·schema·lifecycle 위에 변경을 재적용한다. Bounded private receipt와 target identity read-back은 public schema와 분리하고 손상 시 fail closed 처리한다.
11. Billing account mutation은 tenant별 단일 `billing.json`에서 conditional create/CAS를 사용하고, 충돌마다 최신 tenant·account schema 위에 plan·status·Stripe identity 변경을 재적용한다. Bounded private receipt는 public billing response와 분리하고 손상 시 fail closed 처리한다.
12. Usage event append와 summary 갱신은 각각 `usage.jsonl`과 `usage_summary.json`의 conditional create/CAS로 확정한다. Event log를 권위 원본으로 유지하고 정확히 하나의 검증된 trailing event gap만 summary에 재적용하며, 손상·변조·복수 gap은 원본 보존 상태로 fail closed 처리한다.
13. Prompt override, A/B experiment, request pattern mutation은 각 tenant별 state object의 conditional create/CAS로 확정한다. Override save receipt는 operation payload에 결속하고 refresh는 incarnation과 applied count를 유지한다. A/B assignment와 result는 같은 experiment identity에 결속하며, conclusion은 persisted result와 receipt에 맞는 private pending claim만 재개한다. Request clear는 최초 snapshot identity만 제거한다.
14. Bookmark, style profile, SSO config와 root tenant registry mutation은 각 단일 state object의 conditional create/CAS로 확정한다. 최대 32회 충돌마다 최신 ownership·schema·target identity 위에 operation을 재적용하고 최근 64개 private receipt로 commit 응답 유실 뒤 successor mutation을 조정한다. Bookmark/style target은 private identity/incarnation으로 replacement lifecycle을 구분하며 private metadata는 API와 profile-only reader에 노출하지 않는다.
15. Project knowledge는 tenant/project별 `index.json`을 단일 mutable authority로 두고 conditional create/CAS 충돌마다 최신 문서 집합에 mutation을 재적용한다. Content/style은 private incarnation 아래 immutable object로 발행하고 canonical path·size·SHA-256 binding이 있는 index record만 사용한다. 최근 64개 receipt와 object metadata는 public knowledge response에서 제거하며 여러 artifact와 index를 하나의 distributed transaction으로 과장하지 않는다.
16. DocumentOps는 tenant별 `trajectories.jsonl`과 `trajectory_metadata.json`을 선택된 `StateBackend`의 서로 분리된 mutable authority로 사용한다. Trajectory append/review와 governance metadata append는 각각 conditional create/CAS 충돌마다 최신 state에 최대 32회 재적용한다. SFT export, freeze, dry-run approval, execution request, pre-execution audit는 immutable object로 먼저 발행하고 metadata의 identity·size·SHA-256 binding이 있어야 download와 governance authority가 된다. Reviewer sign-off summary도 같은 backend prefix를 read-only로 읽는다. Agent run은 service가 operation claim 전에 first-party skill을 strict public binding으로 resolve하고 canonical request identity에 포함한다. Binding은 schema version, skill name/version, risk, content SHA-256, catalog fingerprint와 code-execution/external-runtime false authority만 포함하며 instruction과 source path는 제외한다. Agent는 expected binding drift, unknown skill과 unsupported task mapping을 provider 접근 전에 거부한다. 성공 결과·trajectory·stored replay는 같은 binding을 유지하고 legacy `skill_name`/`skill_version`을 보존한다. 두 mutable object와 여러 artifact를 한 distributed transaction으로 과장하지 않으며 private trajectory metadata는 public/SFT projection에서 제거한다.
17. DocumentOps governance artifact inventory는 Ops-key가 있는 read-only route에서만 제공한다. Metadata authority를 먼저 엄격 검증하고 다섯 managed directory의 object를 `referenced_verified`, `referenced_missing`, `referenced_tampered`, `invalid_reference`, `unreferenced`로 분류한다. Metadata snapshot 하나는 atomic하지만 여러 object 관측은 transaction이 아니며 자동 삭제 권한도 없으므로 concurrent write 가능성과 실제 cleanup 전에 재확인이 필요하다. Local browser는 같은 Ops-key route를 GET으로만 읽어 exact count와 문제 artifact를 보여주며, tenant 전환이나 후속 재조회보다 늦게 도착한 응답을 폐기하고 삭제 action을 제공하지 않는다.
18. DocumentOps governance review overview는 training governance, artifact inventory, reviewer sign-off를 service에서 각각 읽어 reviewer-facing 상태로 합성한다. 경계 drift, artifact integrity, governance blocker, human sign-off 순서로 먼저 조치할 문제를 선택하고 다음 검토 행동과 원본 report를 함께 반환한다. 세 조회를 하나의 atomic snapshot으로 과장하지 않으며 수동 재확인과 dataset upload, provider call, training, model promotion 권한 `false`를 응답과 화면에서 유지한다.
19. Governance overview의 수동 재확인은 source report의 top-level `generated_at`만 제외한 canonical SHA-256을 사용한다. Browser는 성공한 동일 tenant 응답만 현재 인증 세션 메모리에서 비교해 최초·동일·변경을 표시하고 logout·invalid session에서 기준을 제거한다. Fingerprint는 상태 비교용 read-only 값이며 persisted receipt, atomic snapshot, 외부 실행 권한으로 해석하지 않는다.
20. DocumentOps governance summary·overview·inventory·reviewer sign-off 조회와 sign-off handoff 다운로드는 route가 명시한 action으로 tenant append-only audit에 기록한다. Audit detail은 surface, aggregate status, read-only 여부와 fingerprint 비저장 사실만 보존하고 fingerprint 값, source report, reviewer record를 복사하지 않는다. Authenticated Agent run은 별도 action/resource로 task type, binding SHA-256, replay 여부와 code-execution/external-runtime false authority만 DocumentOps detail에 더하고 instruction, source path, request/source body, credential, provider response는 남기지 않는다. Governance resource는 trajectory 및 Agent run resource와 분리해 Admin Ops에서 독립적으로 필터링한다.
21. Browser에서 governance source를 바꾸는 export·freeze·dry-run approval·execution request·pre-execution audit 저장과 planning provider/model 변경이 성공하면 기존 overview는 즉시 stale 상태가 된다. 이 전환은 진행 중 overview 응답도 무효화하고 이전 fingerprint 기준은 유지한다. 성공한 새 overview 조회만 fresh 상태와 ready badge를 복구하며 실패·download·read-only 조회는 freshness를 올리지 않는다.
22. DocumentOps Trajectory Stats는 같은 tenant의 연속 조회마다 request version을 증가시키고, 가장 최근 요청의 성공 또는 오류만 화면에 반영한다. 이전 성공·실패와 tenant 전환 전 응답은 accepted·pending·export count나 오류 상태를 덮어쓰지 않는다.
23. DocumentOps Reviewed SFT export 목록은 export와 freeze 목록을 함께 읽는 요청마다 version을 증가시키고 현재 tenant의 가장 최근 요청만 렌더링한다. 늦게 끝난 이전 성공, HTTP 오류, JSON parse 오류는 최신 task-filtered artifact 목록과 오류 surface를 덮어쓰거나 stale 알림을 만들지 않는다.
24. DocumentOps Training Readiness는 같은 tenant의 연속 조회마다 독립 request version을 증가시키고 response, JSON parse, error branch에서 최신 여부를 다시 확인한다. 늦은 이전 성공이나 오류는 최신 export·freeze chain을 되돌리거나 과거 freeze를 dry-run 승인 대상으로 다시 노출하지 않는다.
25. DocumentOps Training Audit Checklist는 request version, tenant, provider/model query가 모두 현재 조건과 일치할 때만 checklist와 audit 목록을 렌더링한다. Planning 조건이 바뀌면 열린 checklist를 `RECHECK REQUIRED`로 낮추고 `Audit 저장` action을 제거하며, 성공한 audit 저장은 진행 중 이전 read를 무효화해 새 evidence를 가리지 않게 한다.
26. DocumentOps Training Execution Request Records는 같은 tenant의 연속 조회마다 독립 request version을 증가시키고 response, JSON parse, error branch에서 최신 여부를 확인한다. 늦은 이전 성공이나 오류는 최신 two-person guard 기록을 되돌리지 않으며, execution request 저장 뒤 시작되는 새 조회가 저장 전 진행 중 read보다 우선한다.
27. DocumentOps Training Adapter Contract과 Training Execution Rehearsal은 각자 request version, tenant, provider/model query가 현재 planning 조건과 일치할 때만 결과를 렌더링한다. Planning 조건이 변경되면 진행 중 응답을 무효화하고 이전 config 안전 표시와 artifact reference를 `RECHECK REQUIRED`로 대체한다.
28. DocumentOps SFT Export Preview와 Reviewed SFT artifact 목록은 요청을 시작한 tenant와 task 조건이 현재 선택과 일치할 때만 렌더링한다. Training Plan Preview도 독립 request version, tenant, provider/model query를 함께 확인한다. Task 또는 planning 조건이 바뀌면 진행 중 success/error를 폐기하고 열린 evidence를 `RECHECK REQUIRED`로 대체한다.
29. Captured DocumentOps Agent 응답을 잃은 browser는 status schema, operation ID, state별 timestamp·replay·next-action, read-only와 provider-call 비승인을 모두 확인한다. Mismatched·unavailable·running 상태의 tenant와 payload는 현재 page memory에만 보존하고 Agent 버튼과 상태 재확인 버튼을 recovery promise 하나에 결속한다. Terminal success만 exact replay를 허용하며 logout·invalid session은 pending payload를 제거한다. Reload 이후 복구와 외부 provider 실행 권한은 이 browser state가 제공하지 않는다.
30. Captured Agent POST 직전에는 schema version, tenant ID, browser UUID operation ID만 browser marker로 남기고 payload는 browser storage에 저장하지 않는다. Marker는 strict `no-store` status 확인과 새 POST 차단에만 사용하며 exact replay authority가 아니다. Operator가 backend 실행 비취소와 evidence 확인 경고를 승인해 상태 추적을 종료해야 marker를 제거한다. Invalid marker와 auth/tenant context 변경은 marker를 폐기하고, storage 접근 실패는 same-page Agent 실행을 막지 않는다.
31. Captured Agent browser marker는 same-origin `localStorage`를 shared primary로 사용하고 접근 실패 시 현재 tab의 `sessionStorage`로 내려간다. 지원 browser에서는 tenant별 Web Lock 안에서 기존 marker 확인과 새 marker 기록을 직렬화해 동시 tab 중 owner 하나만 POST를 시작하게 한다. 다른 tab과 owner tab 종료 뒤 다시 연 화면은 payload 없는 marker로 status만 조회하며 explicit release 전까지 새 POST를 막는다. 두 storage가 모두 막히면 reload/cross-tab guard는 없고, Web Locks 미지원 환경에서는 완전 동시 claim의 atomicity를 보장하지 않는다. 다른 browser/device, process-crash recovery, cross-ID semantic deduplication, exactly-once provider execution과 external provider authority도 이 marker가 제공하지 않는다.
32. Captured Agent marker storage key는 tenant별로 분리한다. 같은 origin의 foreign tenant read/write/clear는 다른 tenant marker를 보존하고, 승인된 tenant 전환은 previous tenant marker만 제거한다. H96 base-key marker는 strict schema를 통과한 뒤 owning tenant만 legacy fallback으로 읽고 제거하며 foreign tenant는 이를 잘못된 marker로 삭제하지 않는다. Marker body의 exact 3-field payload-free contract와 backend operation authority는 바꾸지 않는다.
33. Browser tenant context는 signed token 또는 selector access preflight만으로 부분 전환하지 않는다. `dd_tenant_id` 저장이 성공한 뒤에만 in-memory tenant와 previous-context draft/recovery/marker를 변경하며, storage write 실패는 기존 context evidence를 그대로 보존한다. Browser storage는 durable handoff를 위한 commit point일 뿐 authorization authority가 아니다.
34. Browser auth session은 login, register, refresh, LDAP login 모두 같은 commit helper를 사용한다. Token claims를 먼저 검증하고 access/refresh token을 쓴 뒤 signed tenant ID를 마지막 commit point로 저장한다. Snapshot을 확보한 뒤 write가 하나라도 실패하면 이전 access/refresh token과 tenant를 복원하고 current user와 DocumentOps evidence를 바꾸지 않는다. 동시 401은 tab 내 하나의 refresh promise에 합류한다. Generic API 오류 경로는 refresh 성공 뒤에도 실패한 mutating request를 자동 replay하지 않고 명시적 재시도를 요구한다. 현재 tab의 commit/cleanup뿐 아니라 같은 origin의 다른 tab에서 access token, refresh token, tenant ID 또는 전체 local storage가 바뀌어도 session revision을 올려 진행 중인 이전 refresh 응답을 폐기하며, unrelated storage key는 revision에 영향을 주지 않는다. 다른 tab의 최종 signed user·tenant·role·credential version이 현재 page와 다르면 reload를 한 번만 요청해 page-memory evidence를 새 authorization context에서 다시 구성하고, 네 값이 같은 token rotation은 reload하지 않는다.
35. Browser 401 recovery는 refresh 결과를 성공, credential 거절, 일시적 endpoint 장애, browser storage commit 실패로 구분한다. 성공만 원 요청을 한 번 재시도하고 credential 거절만 invalid-session cleanup을 수행한다. 일시 장애와 storage 실패는 기존 token, tenant, current user, review draft와 pending recovery evidence를 보존하고 재시도 가능한 오류를 표시한다.
36. Protected request authorization은 access token의 signed tenant/user identity를 tenant `UserStore`의 현재 role과 `is_active`에 다시 결속한다. Persisted user가 없거나 비활성이면 token 만료 전에도 `401`, role이 바뀌면 현재 role로 RBAC를 적용하고 state read가 실패하면 `503`으로 fail closed 처리한다. `/events`도 protected route로 두고 Authorization Bearer access token을 같은 authority로 검사한다. Auth와 SSO user lifecycle route는 앱이 생성될 때 확정한 data root와 `StateBackend`를 공유하므로 process env drift가 request authority를 분리하지 않는다. Fresh install에 user state가 전혀 없는 legacy compatibility만 token payload를 유지하며, 별도 revocation table이나 cross-device push invalidation은 제공하지 않는다.
37. Password change는 password hash와 persisted `credential_version` 증가를 한 user-state CAS mutation으로 확정한다. Access/refresh token은 발급 시 version을 포함하고 protected request, SSE Bearer token, refresh exchange가 현재 user version과 다르면 `401`로 거부한다. 변경 요청을 보낸 browser만 응답의 새 token pair를 atomic session helper로 commit하고, 같은 origin의 다른 tab은 version mismatch에서 reload한다. Legacy versionless record/token은 현재 version 0일 때만 호환한다. 이는 password change 기반 전체 token 폐기이며 exact-session 선택 폐기는 다음 불변식에서 별도로 정의한다.
38. 열린 `/events` SSE는 연결 시점의 인증만으로 계속 전달하지 않는다. Browser는 access token을 URL에 넣지 않고 fetch-stream의 Authorization header로 전달한다. Server는 최대 15초 간격으로 같은 Bearer token의 expiry와 persisted user/session authority를 다시 확인하고, invalid이면 `auth_revoked`, authority read가 실패하면 `auth_unavailable` control event만 보낸 뒤 unsubscribe한다. Browser는 revoked event를 기존 single-flight refresh에 연결하고 refresh credential 거절만 invalid-session cleanup으로 처리한다. Temporary authority·endpoint·storage failure는 token, current user와 page-memory evidence를 보존하고 polling과 reconnect를 사용한다. Stale stream callback은 현재 replacement stream을 닫거나 reconnect timer를 만들 수 없다. 이는 bounded revalidation이며 즉시 cross-device push나 15초보다 짧은 termination SLA는 제공하지 않는다.
39. Register·login·invite·LDAP·SAML·GCloud·password-change token pair는 selected local/S3 backend에 conditional create한 tenant-scoped `auth-session.v2` object의 random session ID를 공유하고 refresh도 그 ID를 유지한다. 기존 `auth-session.v1` object는 strict read compatibility를 유지하고 label mutation 시 v2로 승격한다. Protected request, refresh와 `/events`는 exact owner·credential version·expiry·revoked state를 확인한다. `/auth/logout`은 현재 signed session만 CAS로 폐기하고 다른 로그인 session을 보존한다. 본인 inventory는 tenant prefix 전체를 strict 검증한 뒤 현재 credential version의 active record만 `no-store`로 반환한다. `PATCH /auth/sessions/label`은 본인 active session에 최대 40자의 user-supplied 기기 이름 또는 `null`을 CAS 저장하고 foreign·missing·inactive target을 같은 `404`로 숨긴다. Selected revoke는 current target을 `409`, foreign/missing target을 같은 `404`로 거부하고 already-revoked owner retry를 success로 조정한다. Other-session bulk revoke는 strict `confirm=true` 뒤 current를 제외한 active snapshot을 폐기하고, all-device bulk revoke는 같은 user·version의 snapshot 전체를 current-last 순서로 폐기한다. Browser profile은 session ID를 DOM에 넣지 않고 label/save/revoke action에 같은 single-flight와 stale-response guard를 적용하며 all-device 성공 뒤에만 local credential과 page-memory evidence를 정리한다. Corrupt·unavailable state는 원본 보존 `503`으로 닫고 audit은 action/result, aggregate count만 남기며 token, session ID와 user-supplied label을 복사하지 않는다. Bulk 작업은 distributed transaction이 아니므로 중간 write failure가 일부 다른 session 폐기를 남길 수 있고 current-write response-loss와 요청 뒤 생성된 session도 원자적으로 조정하지 않는다. 일반 browser logout은 local cleanup을 즉시 수행하고 endpoint failure를 서버 폐기 미확인 경고로 구분한다. Legacy sessionless token은 exact logout·inventory·label·selected/bulk revoke를 사용할 수 없다. Session state/inventory에 User-Agent/IP를 자동 결합하는 기능, admin mass revoke, expired-session GC와 즉시 push는 제공하지 않는다.
40. Auth-session label은 request boundary에서 trim한 뒤 40자로 제한하고 API schema와 persisted-state decode가 같은 validator를 사용한다. Unicode control, surrogate, line/paragraph separator와 bidirectional·invisible format 문자는 거부하되 ZWNJ/ZWJ는 자연어와 emoji 조합을 위해 허용한다. Direct storage mutation의 비정규 입력과 persisted drift는 원본 bytes를 다시 쓰지 않고 fail closed 처리한다.
41. Auth-session retention preview는 admin JWT 또는 Ops key만 허용하고 selected local/S3 backend의 tenant prefix 전체를 strict 검증한다. `auth-session-retention-preview.v1` 응답과 audit은 user ID, session ID와 label을 제외한 aggregate만 사용하고 `read_only=true`, `deletion_authorized=false`, `no-store`를 유지한다. 조회는 object를 쓰거나 삭제하지 않으며 corrupt·unavailable state는 원본 보존 `503`으로 닫는다. 실제 deletion, scheduler와 retention policy 적용은 별도 명시 승인 전까지 이 계약 밖이다.
42. Ops auth-session retention UI는 access token 또는 Ops key가 있을 때만 preview를 호출하고 30/90/180/365일 selector와 icon refresh만 제공한다. Browser는 version, read/delete boundary, aggregate count와 timestamp consistency를 strict 검증하고 현재 tenant의 최신 request generation만 렌더링한다. Invalid/stale 응답은 aggregate를 표시하지 않으며 삭제·scheduler·mutation control은 추가하지 않는다.
43. Auth-session retention policy comparison은 admin JWT 또는 Ops key 아래 한 번의 strict prefix inspection에서 30/90/180/365일 aggregate를 함께 계산한다. `auth-session-retention-comparison.v1`은 exact policy order와 count/timestamp monotonicity를 유지하고 `read_only=true`, `deletion_authorized=false`, `snapshot_atomic=false`, `requires_recheck_before_mutation=true`를 명시한다. Browser selector는 검증된 comparison만 다시 렌더링하고 refresh만 새 request를 시작한다. 응답·audit에는 user ID, session ID, label과 token을 포함하지 않으며 실제 deletion과 scheduler 권한은 추가하지 않는다.
44. Auth-session retention review handoff는 선택한 30/90/180/365일 policy와 한 번 strict inspection한 comparison을 tenant-bound `auth-session-retention-review-handoff.v2` JSON attachment로 전달한다. Canonical comparison SHA-256와 exact response-body SHA-256을 함께 검증하며 `review_only=true`, `policy_change_authorized=false`, `deletion_authorized=false`, `scheduler_authorized=false`, `snapshot_atomic=false`, `requires_recheck_before_mutation=true`, `handoff_persisted=false`를 고정한다. v1은 역사적 evidence로만 남고 recheck 입력으로는 사용하지 않는다. Browser는 hash, flag, current tenant/request generation을 통과한 response만 화면과 download에 사용하고, audit은 selected policy·aggregate count·read-only 경계만 남긴다. Session delete, scheduler, policy 저장/적용과 server-side handoff persistence는 추가하지 않는다.
45. Auth-session retention handoff freshness recheck는 exact v2 source handoff와 canonical source hash를 tenant/authority/comparison contract까지 검증한 뒤 같은 policy의 fresh inspection을 `auth-session-retention-recheck-receipt.v1`으로 전달한다. Receipt는 source/current handoff와 SHA-256, stable aggregate fingerprint SHA-256, `aggregate_status`, `fingerprint_algorithm=sha256`, `volatile_fields_excluded`, `aggregate_only=true`, false policy/delete/scheduler authority, `snapshot_atomic=false`, `requires_recheck_before_mutation=true`, `recheck_persisted=false`를 고정한다. `unchanged`는 aggregate equivalence일 뿐 session set identity나 mutation safety가 아니며, `changed`는 정상적인 read-only 결과로 새 handoff가 필요함을 뜻한다. Browser는 page memory의 verified source만 사용하고 selector, refresh, tenant·auth context change와 newer request가 이전 source 또는 completion을 폐기한다. Durable history는 aggregate-only audit에 한정하며 session, policy, scheduler, handoff와 receipt를 저장하지 않는다.

---

## 3. 갭 분석 — 무엇이 완성을 막고 있나

| # | 갭 | 근거 (실측) | 심각도 | 상태 (2026-07-13) |
|---|-----|------------|--------|--------------------|
| G1 | **Live provider 부분 실증** — OpenAI 1회 통과, Gemini/Claude/fallback 성공 proof 잔여 | 2026-07-13 M1 blocked receipt | HIGH | 진행 중 (Gemini quota, Anthropic credits 필요) |
| G2 | **G2B stage proof 잔여** — local live 수집·평가 1건은 통과했지만 durable receipt와 AWS stage 경로는 미검증 | `scripts/run_local_procurement_smoke.py`, `docs/specs/public_procurement_copilot/STATUS.md` | HIGH | 부분 완료 (2026-08-11 local live smoke) |
| G3 | **800줄 초과 모듈** — 계획 수립 시 15개 | `find app -name '*.py' -print0 \| xargs -0 wc -l \| awk '$2 != "total" && $1 > 800 {print}'` | MED | **✅ 해소 및 guard 적용** (2026-07-14, 상수 모듈 drift 재분할 → 초과 0개) |
| G4 | **excel export 비대칭** — 84줄로 타 export 대비 최소 구현 | `wc -l app/services/excel_service.py` | MED | **완료** (커밋 e9ecabc, 309줄·테스트 14개) |
| G5 | **CSP nonce 부채** — served HTML `script-src 'unsafe-inline'` 의존 해소 필요 | `app/middleware/security_headers.py`, `app/static/index.html` | MED | **✅ 완료** — inline `on*=` 핸들러 0개, HTML 응답 nonce 기본 on, `DECISIONDOC_CSP_NONCE_ENFORCED=0` local diagnostic opt-out 유지 |
| G6 | **배포 접근성 미검증** — current-main dev deploy-smoke가 AWS OIDC `AssumeRoleWithWebIdentity`에서 차단돼 stack inspection과 runtime smoke에 도달하지 못함 | GitHub Actions `deploy-smoke` run `31452991725` | MED | OIDC trust 복구 필요 |
| G7 | **모듈 레벨 side-effect** — `app/main.py`의 `app = create_app()`이 import 시점에 `.env`를 로드해 테스트 격리를 해침 | — | MED | **✅ 해결** (2026-07-02, 커밋 0023c7c) — PEP 562 모듈 `__getattr__`로 lazy 생성(캐싱). `uvicorn app.main:app`·Mangum·기존 import 전부 무변경 동작 |

---

생성 export packet의 source는 이제 selected local/S3 backend에 bounded durable state로 보존되어 restart·독립 worker 재다운로드를 지원한다. 이는 local implementation/integrity 범위를 보강한 것이며 M1 live provider, M2 G2B stage receipt, M6 AWS deploy/runtime proof의 외부 실증 갭을 해소하지 않는다.

### Generated document review completion local slice (2026-09-04)

저장된 project document를 current session-bound reviewer에게 전달하고 그 검토를
완료하는 별도 경로를 구현했다. Packet manifest는 project/document/request/bundle과
document source SHA-256, 선택된 최대 5개 형식을 포함하고, immutable packet과 record는 selected
`StateBackend`에 저장된다. Admin은 활성 tenant admin/member를 지정하고 member는
자신에게만 지정한다. API key, Ops key, sessionless JWT, viewer, inactive/foreign
identity는 이 경로를 사용할 수 없다.

Exact current stable assignee는 source가 `current`일 때 한 번의 UUIDv4 operation으로
`accepted`, `changes_requested`, `rejected` 중 하나와 근거를 기록할 수 있다. Store는
원본 packet과 canonical receipt를 묶은 deterministic reviewed package를 content-addressed
경로에 먼저 쓰고, pending v1 record를 completed v2로 exact CAS 전환한다. 동일 assignee,
operation, decision, rationale replay만 저장된 package를 다시 검증해 반환하며 다른 입력과
경쟁 전이는 원본을 덮어쓰지 않고 중단한다. Public summary와 audit에는 rationale,
operation ID, stable user ID, session/network metadata를 노출하지 않는다.

Browser는 project action, pending/completed inbox와 project history를 제공한다.
ZIP media type, `Content-Length`, packet/manifest SHA-256, artifact count,
reviewer binding, review-only, persisted state와 seven all-false authority headers가
모두 맞고 packet 또는 reviewed-package bytes의 SHA-256이 일치한 뒤에만 download를
시작한다. Source가 `changed` 또는 `missing`이면 completion 없이 pending evidence를
보존하고, historical packet download는 기존 bytes를 변경하지 않고
명시적 확인을 요구한다. Auth, tenant, user, project, document, packet 또는 request
generation과 completion operation drift는 늦은 response와 object URL을 폐기한다.

이 slice는 reassignment, reminder/notification, expiry, deletion, approval state
mutation, provider call, live AWS/S3 or G2B, dataset upload, training,
deployment 또는 production resume를 포함하지 않는다. Focused 재현 명령은 다음과
같으며 current full-suite pass 수는 section 0의 별도 snapshot을 대체하지 않는다.

```bash
python3 -m pytest -q tests/test_generation_export_packet.py --tb=short
python3 -m pytest -q tests/storage/test_generated_document_review_store.py --tb=short
python3 -m pytest -q tests/test_generated_document_reviews.py tests/test_infrastructure.py -k generated_document_review --tb=short
python3 -m pytest -q tests/test_generated_document_review_ui_static.py --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k generated_document_review --browser chromium --tb=short
```

---

## 4. 마일스톤 계획

### M1 — Live Provider 실증 (G1) · 외부 의존: API 키, 소액 비용

- 작업:
  1. openai / gemini / claude 각 1회 실호출로 `pytest -m live` 통과.
  2. fallback chain(`DECISIONDOC_PROVIDER=openai,gemini`) 실측 1회 — 1차 실패 시 2차 전환 확인.
  3. 실행 로그·타임스탬프·커맨드를 `docs/evidence-gallery.md`에 증적으로 기록.
- 완료 정의(DoD): live 테스트 통과 로그가 docs에 남고, README의 "live 미검증" 한계 문구를 "N회 실증(날짜·커맨드)"으로 갱신.
- 리스크: provider별 요금·rate limit → mock 대비 diff가 큰 응답은 stabilizer 회귀로 흡수.
- 2026-07-13 실행 결과: OpenAI live generation은 `1 passed in 23.26s`. Gemini는 `gemini-2.5-pro`와 `gemini-2.0-flash` 모두 HTTP 429, Claude는 account credit balance 부족으로 HTTP 400. Fallback은 OpenAI 강제 401 뒤 Gemini 호출까지 확인했지만 Gemini 429로 성공하지 못했다. M1은 `blocked`이며 quota/credits 복구 후 잔여 3개 test를 재실행한다.

### M2 — G2B 실데이터 End-to-End (G2) · 외부 의존: `G2B_API_KEY` (data.go.kr)

- 작업:
  1. 실 공고 1건 수집 → 정규화 → decision package 산출까지 단일 케이스 통과.
  2. 산출 결과를 fixture로 고정해 회귀 테스트화 (키 없는 CI에서도 재현).
  3. GO / CONDITIONAL_GO / NO_GO 판정 재현성 확인.
- DoD: 실데이터 1건의 end-to-end 실행 증적 + 해당 케이스의 키-불필요 회귀 테스트. 입찰 제출·법적 승인은 범위 밖(기존 boundary 유지).
- 2026-07-14 local 준비: `run_stage_procurement_smoke.py --proof-receipt`가 preflight를 미실행 `blocked` 상태로, 실제 smoke를 `passed` 또는 `failed` 상태로 atomic 기록한다. Host와 안전한 공고 식별자만 남기고 API key, password, URL userinfo/query는 receipt에서 제외한다.
- 2026-08-11 local 실증: real FastAPI app, temporary local storage, mock LLM provider와 live G2B auto-discovery로 공고 `R26BK01664082`를 수집·정규화·평가하고 `NO_GO`, Decision Council, downstream block/override/retry smoke를 통과했다. 이 결과는 no-AWS local evidence이며 M2 durable proof receipt나 deployed stage runtime을 대신하지 않는다.

### M3 — Export 5종 대칭성 (G4) · 외부 의존 없음 · ✅ 완료 (2026-07-02, 커밋 e9ecabc)

- 결과: 표지+요약(메트릭)+doc_type별 다중 시트, 헤더 서식/열 너비/text_wrap, 빈 입력·특수문자·32,767자 한계·시트명 정규화 방어. `build_excel` 시그니처 무변경. 테스트 6→14개(openpyxl 재오픈 검증 포함).

### M4 — 보안 성숙: CSP Nonce (G5) · 외부 의존 없음 · ✅ 완료 (2026-07-08)

- 완료: 요청별 nonce 생성/HTML 스탬핑/헤더 배선 + 테스트. page-tab, mobile bottom navigation, PWA install prompt, local LLM setup guide, SSO tabs, header user menu, notification bell/list, profile modal, AI rank roster, generation quick controls, G2B static/dynamic controls, batch results, bundle related modal, attachment actions, upload modals, static shell controls, ops static controls, SSO/Billing dynamic controls, RFP result modal, knowledge page/doc actions, report workflow shell/list/artifact/detail/quality/slide actions, locations shell, DocumentOps toolbar/dynamic actions, history dynamic actions, message thread, onboarding, result-download, share/auth/approval-request/project modal/list, project detail/search, dashboard retry, meeting recording, procurement role actions, style profile actions, location procurement summary, bundle recommendation close action까지 inline handler 없이 `addEventListener` 또는 delegated listener로 전환 완료.
- 완료 증거: `app/static/index.html`의 inline `on*=` 핸들러 0개. served HTML은 기본적으로 per-request nonce를 받고, nonce가 존재하는 `script-src`에서는 `'unsafe-inline'`을 제거한다. `DECISIONDOC_CSP_NONCE_ENFORCED=0`은 local diagnostic opt-out으로만 유지한다.
- DoD 달성: 이벤트 위임 완료 + nonce enforcement 기본 on + served HTML `script-src`에서 unsafe-inline 부재 + 관련 UI/CSP guard 통과.

```bash
python3 - <<'PY'
from pathlib import Path
import re
html = Path('app/static/index.html').read_text(encoding='utf-8')
print(len(re.findall(r'\son[a-zA-Z]+\s*=', html)))  # → 0
PY
```

### M5 — 코드 위생: 800줄 초과 모듈 분할 (G3) · 외부 의존 없음 · ✅ 완료 및 guard 적용 (2026-07-14, 800줄 초과 0개)

`procurement_decision_package_service.py`(4,883줄) 분할 패턴(순수 코드 이동 + facade re-export + AST 동일성 검증)을 재사용한다.

**완료 (2026-07-02):**

| 모듈 | 이전 | 결과 | 커밋 |
|------|------|------|------|
| `app/storage/trajectory_store.py` | 2,665 | 13모듈 mixin 패키지 (최대 446줄) | dd2562f |
| `app/services/generation_service.py` | 2,331 | 13모듈 패키지 (최대 347줄) | 5596499 |
| `app/routers/admin.py` | 2,246 | 9모듈 sub-router 패키지 (최대 747줄) | 9c56d4a |
| `app/routers/generate.py` | 2,170 | 6모듈 sub-router 패키지 (최대 698줄) | 195dc43 |
| `app/providers/mock_provider.py` | 1,794 | 9모듈 fixture 패키지 (최대 421줄) | 806531e |

**잔여 10개도 완료 (2026-07-02):**

| 모듈 | 이전 | 결과 | 커밋 |
|------|------|------|------|
| `app/routers/projects.py` | 1,468 | 4모듈 sub-router (최대 658줄) | d27d0c5 |
| `app/services/pptx_service.py` | 1,410 | 6모듈 (최대 558줄) | a7f76e7 |
| `app/services/report_workflow_service.py` | 1,322 | 6모듈 mixin (최대 371줄) | 9af900f |
| `app/services/procurement_decision_service.py` | 1,252 | 7모듈 mixin (최대 402줄) | 41bd6e2 |
| `app/schemas.py` | 1,179 | 12모듈 도메인 분할, OpenAPI byte-identical | b883254 |
| `app/storage/report_workflow_store.py` | 1,159 | 8모듈 mixin (최대 280줄) | ba32780 |
| `app/ops/service.py` | 990 | 7모듈 mixin (최대 314줄) | 0e4be91 |
| `app/storage/knowledge_store.py` | 973 | 7모듈 mixin (최대 303줄) | 44c06fe |
| `app/services/attachment_service.py` | 881 | 5모듈 (최대 312줄) | 4ecaa97 |
| `app/services/decision_council_service.py` | 805 | 4모듈 (최대 415줄) | 683457c |

- 2026-07-14 후속 점검에서 `app/services/procurement_decision_package/constants.py`가 829줄로 다시 커진 drift를 확인했다. package foundation 상수를 `package_constants.py`로 이동해 기존 import facade 604줄과 foundation 314줄로 분리했고, 126개 기존 export의 AST 이름 및 runtime 값 동일성을 확인했다.
- DoD 달성: `find app -name '*.py' -print0 | xargs -0 wc -l | awk '$2 != "total" && $1 > 800 {print}'` → **0개**. `tests/test_infrastructure.py`가 app 모듈 상한과 foundation re-export identity를 계속 검증한다.

### M6 — 운영 준비성 (G6) · 외부 의존: 배포 환경

- 작업:
  1. Docker Compose · AWS SAM 배포 절차 재실행/재검증.
  2. post-deploy smoke(`scripts/smoke.py`, `scripts/ops_smoke.py`) 결과 증적화.
  3. 데모 URL 접근성 확인 후 README Links의 "Demo: (접근 검증 후 추가)" 갱신.
- DoD: 신규 환경에서 README 절차만으로 배포 재현 + smoke 통과 로그.
- 2026-07-14 local 준비: `run_deployed_smoke.py --proof-receipt`가 preflight와 실제 deployed smoke의 상태·UTC 시각·runtime host·남은 제한을 validator-compatible receipt로 남긴다. Preflight는 AWS runtime 실행 증거로 취급하지 않으며 실제 runtime은 아직 실행하지 않았다.
- 2026-08-11 무료 local baseline: `DECISIONDOC_FREE_MODE=1`에서 cloud provider 직접 생성과 factory chain, S3 bundle/state storage, remote local-LLM endpoint를 fail closed로 차단한다. `run_free_local.py`는 mock 또는 loopback Ollama만 선택하고 provider capability, local data root, search/finetune disablement와 cloud secret clearing을 강제한다. Inherited AWS profile/container/web-identity source를 제거하고 metadata/shared config credential lookup도 비활성화한다. 기본 `docker-compose.yml`도 mock/local/free mode로 시작하며 production compose와 SAM 전환은 별도 proof 경계로 유지한다.

---

## 5. 실행 순서와 의존 관계

```text
M1 (live 실증) ──┐
                 ├──> README/evidence 갱신 ──> M6 (배포 검증)
M2 (G2B e2e)  ──┘
M3 (excel)  ── 완료
M4 (CSP)    ── 완료
M5 (분할)   ── 완료
```

- **M1·M2가 최우선**: 코드가 아닌 "증거"가 완성의 병목이다.
- M1·M2·M6 실행 전에는 `python3 scripts/check_completion_readiness.py --print-env-template`으로 필요한 env 입력값을 확인하고, `python3 scripts/check_completion_readiness.py --print-proof-plan`으로 readiness와 no-secret proof receipt 명령을 확인한다. secret은 gitignore된 `.env.prod` 같은 파일에 둔 뒤 `python3 scripts/check_completion_readiness.py --env-file .env.prod`로 provider key, G2B/stage smoke, 배포 smoke 입력값을 먼저 확인한다. 필요하면 `python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json`으로 gitignore된 local receipt를 남기고 `python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json`로 receipt 계약을 확인한다. 이 명령은 readiness만 확인하며 live provider, G2B live API, AWS runtime은 실행하지 않는다. 실제 proof 실행과 문서 갱신 순서는 [completion-readiness-runbook.md](./completion-readiness-runbook.md)를 따른다.
- M3·M4·M5는 외부 의존 없는 정리 마일스톤으로 완료됐다.
- 각 마일스톤 완료 시 [roadmap.md](./roadmap.md)와 README 수치·한계 문구를 함께 갱신한다 (정직성 규칙).

### H119 local reviewer registry

H119 is a completed no-cost local slice. It adds a session-admin-only immutable disposition registry while retaining H118 as a non-persistent deterministic receipt. Parent/Luna review findings were remediated, focused retention `36 passed, 238 deselected`, broad auth/security `500 passed`, full Chromium `84 passed, 1 skipped`, and full non-live `4429 passed, 1 skipped, 4 deselected`. Paid provider, G2B, AWS runtime, Stripe, Statuspage, deployment, and service resume were not run.

## 6. 하지 않을 것 (Non-Goals)

- phase 클로저 영수증·documentops 산출물 재생성 (2026-07-02 정리 완료, `.gitignore`로 차단).
- 측정 근거 없는 성과 수치(비용 절감률, 정확도 등) 표기.
- 실제 입찰 제출·법적 승인·계약 확약을 암시하는 기능/문구.

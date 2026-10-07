# Agent-authored Local Generation Design (2026-10-07)

- Gate: `docs/future_feature_gates/agent_authored_local_generation.json` (approved 2026-10-07)
- Scope: 로컬에서 이 저장소를 연 Claude Code·Codex 세션이 문서 내용을 직접 쓰고, DecisionDoc이 검증·저장·내보내기를 맡는다.
- 서버가 하지 않는 것: provider나 외부 API 호출. 문서 내용이 세션의 모델로 전달되는 것은 사용자가 그 세션을 쓰는 데 따른 것이며, 서버가 추가로 보내지 않는다.

## 1. 문제

생성·검증·내보내기·프로젝트 저장은 웹 화면이나 `/generate` 계열 API로만 쓸 수 있었다. 이 경로는 언제나 설정된 provider를 호출한다. 그래서 구독형 Claude Code·Codex 세션이 직접 쓴 초안은 번들 구조, 문체·지식 문맥, 스키마 검증, export, 이력을 쓸 수 없었다.

## 2. 설계

| 단계 | 담당 | 구현 |
|---|---|---|
| 작성 지침 | 서버 | `POST /generate/authoring-brief`가 `GenerationService.build_authoring_brief`를 호출한다. 실제 생성과 같은 `_prepare_generation_payload`를 쓴다. 준비 과정에는 조달 binding, 문체 snapshot, 프로젝트·지식 문맥 주입이 포함된다. 피드백 힌트도 함께 써서 `build_bundle_prompt` 결과를 돌려준다. provider는 해석하지 않는다. |
| 내용 작성 | 세션 | 지침의 프롬프트와 `schema.json`을 따라 `bundle.json`을 쓴다. |
| 처리 | 서버 | `POST /generate/authored`가 기존 `_run_generate_with_result`를 `authored_bundle`과 함께 호출한다. `AuthoredBundleProvider`(name `agent_authored`)가 provider 호출을 대신하고, 그 뒤 처리는 기존 생성과 같다(아래 목록). |
| 실패 보고 | 서버 | 스키마·lint·문서 검증 실패는 422 `AUTHORED_BUNDLE_INVALID`와 `errors`로 돌려준다. 실패 시 이력과 프로젝트 문서는 쓰지 않는다. |
| 프로젝트 연결 | 서버 | `project_id`가 있으면 stream 경로와 같은 `link_generated_document` helper로 연결하고 `project_document_id`를 돌려준다. |
| 도구 | 세션 | `scripts/decisiondoc_author.py`: `bundles`, `brief`(지침·요청·스키마 파일 생성), `submit`(제출, 문서별 Markdown 저장, `export-edited`로 형식별 내려받기). |
| 실행 | 사용자 | `scripts/run_free_local.py --agent-api-key`가 `<data-dir>/.agent-api-key`(0600)를 만들거나 재사용해 `DECISIONDOC_API_KEYS`로 넘긴다. `--procurement-multi-opportunity`는 opt-in 앱 factory를 쓴다. 기존 조달 상태가 있으면 preflight 확인 없이는 시작하지 않는다. |
| 안내 | 세션 | `.claude/skills/decisiondoc-authoring/SKILL.md`(Codex는 `.agents/skills/decisiondoc-authoring/SKILL.md`가 같은 파일을 가리킴), `AGENTS.md`·`CLAUDE.md`의 짧은 연결 절. |

**처리 단계에서 재사용하는 기존 단계**
- 안정화
- 품질 보정
- 스키마 검증
- 렌더링
- lint
- 이력 저장

**처리 단계에서 하지 않는 일**
- 캐시를 읽거나 쓰지 않는다.
- 웹 검색 문맥을 넣지 않는다.

일반 `/generate` 경로의 호출 형태는 바꾸지 않았다. `authored_bundle`은 작성 경로에서만 넘긴다.

## 3. 함께 고친 기존 결함

**proposal 품질 보정의 다른 사업 문구 혼입**

- **결함:** `quality_guard_attachment.py`, `quality_guard_finish.py`, `slide_outline_data.py`의 대체 문장이 보행 안전 사업 전용이었다("교차로", "교통약자", "장애인 보호" 등).
- **작동 조건:** 아래 두 경우에 주제와 관계없이 이 문장이 문서에 들어갔다.
  - 짧은 일반 맥락(80토큰 이하, 숫자 없음)에서 근거 없는 수치가 있는 필드
  - 짧은 첨부 RFP
- **수정:**
  - 대체 문장을 주제 중립 문장으로 바꿨다. 일반 맥락의 배경 문장에는 사용자의 `goal`을 넣는다.
  - `test_proposal_quality_guard_fallback_stays_on_requested_subject`는 수정 전 코드에서 2건 실패하고 수정 후 통과한다.
  - 기존 두 테스트는 같은 의도(수치 제거, 고정 구조)를 유지하고 기대 문장만 바꿨다.

## 4. 검증 (격리: dotenv 차단, 임시 `DATA_DIR`, mock/local, loopback 외 network 차단)

| 대상 | 결과 |
|---|---|
| `tests/test_agent_authored_generation.py` | 5 passed. 지침 프롬프트가 provider 경로의 프롬프트와 같고, provider·cache 미사용, 프로젝트 연결, 422와 무기록, 알 수 없는 필드 거부를 확인 |
| `tests/test_agent_author_cli.py` | 5 passed. API key 인증, 지침 파일, 제출·형식별 내보내기, 거부 사유, 잘못된 키 401 |
| `tests/test_run_free_local.py` + `tests/test_free_mode.py` | 30 passed |
| 생성 회귀(`test_generate`, `test_generation_style_selection`, `test_procurement_generation_binding`, `test_quality_hardening`, `test_procurement_bundle_handoff`) | 리팩터링 직후 127 passed |
| 최종 전체(E2E 제외, `-m 'not live'`) | 5,492 passed, 1 skipped, 1 failed. 실패는 로컬 `pdfplumber` 미설치로 생긴 기존 환경 제약(`test_real_document_parsers[pdf]`) |
| 최종 E2E 전체(`tests/e2e`, 별도 process) | 164 passed, 1 skipped |
| `ruff check app/ tests/ --select=E,F,W --ignore=E501` | 통과 |

**실제 세션 작성 E2E**

- **절차:** 이 저장소를 연 Claude Code 세션이 skill 절차를 그대로 따랐다(bundles → brief → `bundle.json` 직접 작성 → submit).
  - 서버: 새 빈 데이터 폴더, 에이전트 키
  - 대상: `proposal_kr`, 합성 RFP 자료
  - 첫 제출에서 검증을 통과했다.
- **결과 확인:**
  - DOCX·PDF(14쪽)·PPTX(11장)·HWPX·XLSX가 생성됐다.
  - 작성 항목 69개가 모두 최종 Markdown에 남았고, 다른 사업 문구는 없었다.
  - 5개 형식 모두 본문 문장을 포함했다.
  - PDF 표와 PPTX 구조화 슬라이드를 렌더링해 확인했다.
- 증빙은 `output/agent-e2e-20261007/`(gitignore 대상)에 있다.

## 5. 후속 정리 (2026-10-07)

- **지시문 중복 제거:** `BundleSpec.stability_checklist`가 `prompt_hint`를 한 번 더 넣던 중복을 없앴다. `prompt_hint`는 시스템 지시에 한 번만 들어간다.
- **수치 규칙 통일:** 스타일 가이드의 "구체적 수치 반드시 포함"과 제안서 지시문의 "수치로 증명"을 근거 조건부 표현으로 바꿨다. 모든 번들 프롬프트 끝의 공통 품질 기준에 "수치 근거(다른 지시보다 우선)" 규칙을 추가했다.
  - `tests/test_bundle_prompt_rules.py` 41건은 수정 전 코드에서 모두 실패하고 수정 후 통과한다.
- **CLI 조달 연결:** `brief`에 `--procurement-decision-id`·`--procurement-revision`을 추가했다.
  - `tests/test_agent_authored_procurement.py`(local·fake-S3)는 다음을 확인한다: 선택 공고 문맥만 지침에 들어감, 결과 binding, provider 미호출, 이전 revision 409.

## 6. 남은 한계

- Human UAT와 실제 모델 출력 품질 평가는 이 작업으로 대신하지 않는다.
- 결과·준공 보고서와 투자제안서 지시문의 수치 요구는 그대로 두었다. 공통 우선 규칙으로 근거 없는 수치 생성을 막는다.

## 7. 재현 가능한 증거 (2026-10-08)

- **입력 보존:** 4절의 합성 입력과 세션 작성 결과를 `docs/samples/agent_authored_local/`에 두었다.
- **재제출 스크립트:** `scripts/capture_agent_authored_evidence.py`가 임시 데이터 폴더의 앱에 같은 작성 결과를 다시 제출한다. `.env`를 읽지 않고 provider를 호출하지 않는다.
  - receipt(`evidence/cli-logs/agent_authored_evidence.json`)에 provider `agent_authored`, 작성 문장 유지 수, 5종 형식 크기, PDF 쪽수, PPTX 장수를 기록한다.
  - 4절의 69개 항목은 Markdown만 대조했다. 이 스크립트는 20자 이상 작성 문장 106개를 Markdown과 slide outline에서 함께 대조하고, 하나라도 빠지면 실패한다.
- **미리보기:** PDF는 PyMuPDF로, PPTX는 LibreOffice로 PDF 변환 후 렌더링한 이미지를 `evidence/screenshots/agent-authored-*.png`에 둔다. 형식별 파일 자체는 저장소에 넣지 않는다.
- **테스트:** `tests/test_capture_agent_authored_evidence.py`가 재제출 결과, 환경 변수 복원, 형식별 파일 미보관, receipt 거부 조건을 확인한다.


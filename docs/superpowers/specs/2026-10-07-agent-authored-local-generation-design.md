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

## 5. 남은 한계

- 지침 프롬프트에는 번들 지시문 일부가 두 번 들어 있다. 스타일 규칙("구체적 수치 반드시 포함")과 품질 기준("근거 없는 수치 금지")도 서로 충돌한다. skill은 근거 없는 수치를 쓰지 않도록 정했지만, 프롬프트 정리는 별도 과제다.
- 조달 binding 생성(`procurement_decision_id`)은 API로는 가능하지만 CLI 옵션으로는 노출하지 않았다.
- Human UAT와 실제 모델 출력 품질 평가는 이 작업으로 대신하지 않는다.

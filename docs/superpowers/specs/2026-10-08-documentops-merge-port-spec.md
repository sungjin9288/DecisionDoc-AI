# DecisionDoc → DocumentOps 기능 이식 명세 (2026-10-08)

- 상위 계획: `proposal-v3-work/docs/integration/decisiondoc-documentops-map-20261007.md` (이하 "대응표")
- 이 문서의 범위: 대응표 6절 3단계 "DecisionDoc 기능 이식"을 실행할 수 있도록, 기능별로 **가져올 코드·끊을 의존성·DocumentOps 연결 지점·검증 방법**을 정한다.
- 조사 방식: 두 저장소를 읽기만 했다. `proposal-v3-work`의 고객·작업 폴더(`deliverables/`, `jobs/`, `input/`, `output/`, `work/`, `.build/`, `ai_training/`, `evidence/`, `references/`, `projects/ai_safety_v3/`)는 열지 않았다.
- 이 문서는 설계다. 어느 저장소의 코드도 바꾸지 않았다.

## 0. 이미 정해진 것 (대응표, 사용자 결정 2026-10-07)

| 결정 | 내용 |
|---|---|
| 저장소 | 새 저장소. DocumentOps 핵심 + 필요한 DecisionDoc 기능만 |
| 실행 형태 | 서버 없음, 로컬 CLI |
| 화면 | 없음. Claude·Codex 세션에서 프로젝트 폴더를 열어 사용 |
| 순서 | DocumentOps 완성이 먼저, 통합은 그 다음 |
| 이식 순서(권고) | HWPX → 번들 20종 → 수치 근거·필수 섹션 → G2B Go/No-Go → 로컬 문체 예시 |

이 문서는 위 결정을 바꾸지 않는다. 8절에 결정이 더 필요한 항목을 따로 적었다.

## 1. 두 구조의 차이와 이식 원칙

| 항목 | DecisionDoc | DocumentOps |
|---|---|---|
| 작성 결과의 형태 | 번들 JSON(문서 키별 필드) → Jinja2 템플릿 → 문서별 Markdown | 세션이 쓴 Markdown 원고 + `[source: id]` 근거 표시 |
| 구조 강제 | JSON schema, stabilizer, 필수 heading lint | 없음(카탈로그 `sections`·`required_fields`는 설계 브리프에만 복사되고 검사하지 않음) |
| 근거 검사 | `numeric_grounding`(원문 대비 수치 토큰, 생성 파이프라인에는 미연결) | `quality/document.py::evaluate_document_evidence`(줄 단위 근거 표시, 날짜·비율·금액·단위 수치 차단) |
| 형식 출력 | Markdown 블록 → DOCX·PDF(Chromium)·PPTX·HWPX·XLSX | 승인된 Markdown → DOCX·PPTX(디자인 경로), PDF는 LibreOffice 변환 |
| 상태·기록 | tenant별 store, 이력, 승인 | job 상태기계, 해시 봉인 sidecar, receipt |

**원칙**
1. **DocumentOps의 원고·상태·근거 모델이 기준이다.** DecisionDoc 기능은 그 모델에 맞춰 들어간다. DecisionDoc의 저장소·tenant·서버 구조는 가져오지 않는다.
2. **세션이 모든 문장을 쓴다.** 도구가 문장을 채워 넣는 코드(DecisionDoc 품질 보정의 대체 문장)는 가져오지 않는다.
3. **데이터는 변환해서, 코드는 최소로 가져온다.** 번들은 Python 코드가 아니라 문서 유형 데이터 파일로 옮긴다.
4. **기능마다 원래 테스트를 함께 옮기고**, DocumentOps 쪽 연결 테스트를 추가한다. 형식 출력은 실제 앱 렌더 확인을 거친다.

## 2. 이식 단위

난이도: S(며칠 안, 의존성 거의 없음) / M(어댑터 필요) / L(구조 변경 필요).

### 2-1. HWPX 출력 — S, 1순위

- **가져올 코드:** `app/services/hwp_service.py`(758줄)의 `build_hwp(docs, title, gov_options=None, visual_assets=None) -> bytes`
  - 함께 필요: `hwp_image_metadata.py`(50), `export_reproducibility.py`(50, 고정 시각 ZIP), `export_labels.py`(34)
  - 외부 라이브러리 없음(stdlib zipfile·re·html·struct). 폰트·템플릿 파일 없음.
- **끊을 의존성**
  - `visual_asset_service.py`: 쓰는 함수 2개(`decode_visual_asset_bytes`, `group_visual_assets_by_doc_type`)만 복사한다. 이 모듈은 상단에서 provider를 import한다.
  - `GovDocOptions`: `app/schemas/visual_assets.py`의 pydantic 모델 대신 일반 dataclass로 옮긴다.
- **입력 어댑터(권고):** DecisionDoc의 `markdown_utils.parse_markdown_blocks` 대신 DocumentOps의 `formats/outline.py::summarize_outline`이 만든 블록을 HWPX 문단으로 바꾼다.
  - 이유: DOCX·PPTX와 같은 파서를 써야 `[source: id]` 표시, 표, 이미지가 형식마다 같게 처리된다.
  - 첫 단계에서는 기존 파서로 옮겨 동작을 맞춘 뒤 어댑터로 바꿔도 된다. 이 경우 두 결과의 문단 텍스트가 같은지 테스트로 확인한다.
- **DocumentOps 연결 지점**
  - 새 모듈 `documentops/formats/hwpx.py::export_hwpx(job, artifact_id=None, *, reviewed_image_authority)`
    - `approved_export_source()`로 승인된 원고를 받는다.
    - 원고를 HWPX bytes로 만든다.
    - `write_export_artifact(job, source, ExportFormat.HWPX, "hwpx", content)`로 sidecar와 함께 저장한다.
  - 형식 목록이 하드코딩된 곳을 함께 고친다.
    - `core/models.py`의 `SUPPORTED_FORMATS`·`OutputFormat`, `ExportFormat`, export id 정규식
    - `formats/assembly.py` 정규식
    - `cli.py` export 선택지와 분기
    - `core/resume.py` 다음 행동 생성
    - `quality/project_policy.py::_export_contributors`(HWPX 구조 검사 추가)
- **바꿔야 할 동작**
  - 표지의 "완성형 문서 패키지" 문구와 지표 카드는 선택 옵션으로 바꾼다. DocumentOps의 표지·디자인 결정과 겹친다.
  - 문단·표 스타일(현재 본문·제목1–3, 고정 크기)은 DocumentOps house style(10.5pt 표, 공공 보고서 장 구성)과 맞추는 후속 작업으로 둔다.
  - SVG 시각자료는 HWPX에 들어가지 않고 제목·설명 텍스트만 남는다. 래스터 이미지만 문서당 2개까지 넣는다. 이 한계를 사용자 안내에 적는다.
- **테스트:** `tests/test_hwp_endpoint.py` 중 `build_hwp` 직접 호출 19건, `tests/test_gov_format.py`의 HWPX 관련 약 5건, `tests/test_export_reproducibility.py` 일부를 옮긴다. HTTP 경유 4건은 제외한다.
- **완료 확인:** 한컴오피스 한글(이 Mac에 설치됨)에서 열기·편집·저장·다시 열기. DecisionDoc에서는 2026-09-29 합성 문서 1건으로 확인한 기록이 있다.

### 2-2. 입력 파일 텍스트 추출 — S, 신규 권고(대응표에 없음)

- **이유:** DocumentOps에는 PDF·HWPX·DOCX 원문을 읽는 코드가 없다. 세션이 PDF는 직접 읽을 수 있지만 HWPX 공고문·제안요청서는 읽지 못한다. 공공 제안 작업의 첫 입력이 막힌다.
- **가져올 코드:** `app/services/attachment/core.py::extract_text`(329)와 `format_extractors.py`(282), `pdf_extraction.py`(308), `constants.py`(50)
  - HWPX: zipfile + defusedxml로 `Contents/section*.xml`의 `<t>` 추출
  - DOCX: python-docx / PDF: pdfplumber
  - LLM·markitdown fallback(`extract_text_with_ai_fallback`)은 가져오지 않는다.
- **DocumentOps 연결 지점:** `documentops source extract <source_id>`
  - `sources/intake.py`의 해시 결속 source에서 텍스트 파생본을 만든다.
  - 파생본은 원본 source hash에 결속된 sidecar로 저장한다.
  - 세션은 이 텍스트를 읽고 `[source: id]`로 인용한다.
- **의존성 추가:** defusedxml, pdfplumber. python-docx는 이미 선택 의존성이다.
- **테스트:** DecisionDoc의 attachment 추출 테스트 중 형식별 단위 테스트를 옮긴다. ZIP 폭탄·멤버 수 제한 검사를 유지한다.

### 2-3. 문서 유형 카탈로그(번들 20종) — 데이터 S, 연결 M

- **가져올 것(데이터만)**
  - 20개 번들(`app/bundle_catalog/bundles/*.py`, 약 2,900줄)의 문서 구성, 문서별 필수 heading(`validator_headings`·`lint_headings`·`critical_non_empty_headings`), `prompt_hint`
  - `style_guide.yaml`의 번들별 문체 지시
  - `system_prompt.py`의 공통 품질 기준. "수치 근거" 우선 규칙을 포함한다.
- **가져오지 않을 것**
  - JSON schema, Jinja2 템플릿 61개, stabilizer: provider 출력을 구조에 맞추던 장치다. 세션이 Markdown을 직접 쓰면 필수 섹션 검사(2-4)로 같은 보장을 얻는다.
  - `build_bundle_prompt`: tenant, A/B 실험, prompt override, LLM 평가 피드백에 묶여 있다. 작성 지침은 DocumentOps의 author packet과 skill로 전달한다.
  - few-shot 예시: 20개 중 9개 번들의 예시에 억 원 단위 금액이 들어 있다(예: `feasibility_report_kr`의 "연간 유지보수 비용 18억 원"). 근거 없는 수치를 부추긴다. 수치를 "확인 필요"로 바꾼 사본을 따로 만들 때만 포함한다.
- **변환 방법:** `scripts/export_documentops_type_catalog.py`가 `docs/integration/documentops-type-catalog-v1.json`을 만든다(2026-10-08 준비 완료). 손으로 옮기지 않는다.
  - 형태: `{id, name_ko, category, documents: [{key, required_headings, non_empty_headings}], guidance, guidance_json_fields, style_rules, amount_mentions, few_shot_excluded}`와 공통 `quality_rules`·`style_guide`
  - `guidance_json_fields`: JSON 출력용으로 쓴 지침이 언급하는 필드 이름. Markdown 원고용으로 고쳐 써야 한다.
  - `amount_mentions`: 지침 속 금액·비율 예시(5개 번들). 이식할 때 바꿔 쓴다.
  - 변환 결과와 원본 registry를 대조하는 테스트를 같이 둔다(유형 20개, 문서 키, heading 목록 일치).
- **DocumentOps 연결 지점**
  - 데이터 파일: `documentops/design/data/bundles-v1.json`, pyproject package-data에 추가
  - 현재 "유형"이 세 군데로 나뉘어 있다: `JobConfig.document_type`(자유 문자열), 디자인 카탈로그 5종, 역할 구성 3종. 연결 방법은 아래로 정한다.
    - `job init --type <bundle_id>`가 `document_type`에 번들 id를 기록한다.
    - 번들마다 디자인 카탈로그 유형(proposal/request/plan/presentation/estimate)과 역할 구성(proposal_kr/report_kr/manual_kr)으로 가는 대응을 데이터에 둔다.
  - author packet(`authoring/packet.py::_packet_payload`)에 `type_binding: {id, sha256}`을 추가한다. 해시 봉인된 packet이므로 기존 packet의 bytes와 경로가 바뀐다. 기존 job은 binding 없이 그대로 읽히도록 호환을 유지한다.
- **번들 하나 = 문서 여러 개 처리:** `proposal_kr`처럼 문서가 4개인 번들은 원고 하나에 문서별 H1 장으로 쓴다. HWPX·XLSX 출력은 H1을 문서 단위로 나눠 `docs` 목록을 만든다.

### 2-4. 필수 섹션 검사 — S

- **가져올 코드:** `app/eval/lints.py`(52)의 heading 누락·TODO/TBD·빈 필수 섹션 검사, `app/eval/bundle_eval.py`(195)의 미채움 자리표시자(`{{}}`) 검사. 입력을 2-3의 데이터로 바꾼다.
- **DocumentOps 연결 지점:** 새 `quality/sections.py`가 `QualityReport`를 돌려준다.
  - draft-ready → evidence-passed 전이(`authoring/evidence.py::evaluate_evidence`)에서 근거 검사와 함께 실행한다.
  - `run_all_qa`의 contributor 목록에도 추가한다.
  - 유형 binding이 없는 job은 검사를 건너뛰고 `warn` 대신 "적용 안 함"으로 기록한다.
- **수치 근거:** DocumentOps의 `evaluate_document_evidence`가 이미 더 강하다. DecisionDoc `numeric_grounding.py`(121)는 옮기지 않는다. 한국어 단위 목록(억원·만원·개월·명·건 등)만 대조해서 DocumentOps 패턴에 빠진 것이 있으면 추가한다.
- **가져오지 않을 것:** `quality_guard_*`(proposal 대체 문장 주입), `llm_judge`·`eval_store`·`pipeline`(provider·store 결합)

### 2-5. 조달 Go/No-Go 판단 — 점수 M, 판단 패키지 L

- **가져올 코드:** `app/services/procurement_decision/`의 결정적 부분(약 1,400줄)
  - `hard_filters.py`(387): 필수 조건 8종(`mandatory_eligibility_mismatch`, `mandatory_certification_or_license`, `regional_or_participation_restriction`, `mandatory_consortium_requirement`, `impossible_deadline`, `prohibited_risk_condition`, `required_deliverable_capability`, `mandatory_domain_experience`)
  - `soft_fit_scoring.py`(402): 가중 10개 차원, 합계 1.0
  - `recommendation.py`(105): 필수 조건 실패 시 NO_GO, 자료 부족 시 CONDITIONAL_GO, 75점 이상 GO, 55점 미만 NO_GO
  - `checklist.py`(177), `constants.py`(77), `text_utils.py`(103)
  - 필요한 pydantic 모델만 `app/schemas/procurement.py`에서 복사한다(약 270–458줄). `app.schemas` 패키지 import는 인증 모듈까지 끌고 오므로 쓰지 않는다.
- **끊을 의존성:** `service_core_mixin.py`의 store·tenant·지식 저장소 조회를 `_build_inputs(json)`으로 바꾼다. 마감일 필터의 현재 시각은 주입해서 결과를 재현 가능하게 한다.
- **입력:** 세션이 공고문(2-2로 추출)과 회사 역량 자료를 읽고 `parsed_rfp_fields`·`capability_profile` JSON을 쓴다. DecisionDoc에서는 이 부분이 LLM 호출(`rfp_parser`)이었다.
- **DocumentOps 연결 지점:** `documentops/decision/procurement.py` + `procurement check --input <json> --json`
  - 기존 `quality/quantitative`(견적·일정 검사)와 같은 형태: strict 입력 모델 → 결정적 보고서 → `add_*_parsers`
  - 보고서에 `authorizes_bid_submission: false` 같은 권한 없음 표시를 둔다. 판단 결과는 입찰 제출이나 승인이 아니다.
  - 결과 JSON을 `bid_decision_kr` 유형 원고의 근거 source로 등록할 수 있게 한다.
- **보류**
  - 판단 패키지(`procurement_decision_package/`, 24개 모듈 약 7,800줄): store·source binding·docx에 묶여 있다. 점수 모듈을 먼저 쓰고 필요성을 본 뒤 정한다.
  - 나라장터 수집(`g2b_collector.py`): 외부 API 키와 네트워크 호출이 필요하다. 처음에는 공고 파일을 직접 넣는다.
- **테스트:** `test_procurement_decision_service.py`(9), `test_procurement_eval_regression.py`(3)를 store 없이 돌도록 옮긴다.

### 2-6. 로컬 문체 예시 추출 — S

- **가져올 코드:** `app/services/local_style_examples.py`(59)의 `extract_local_examples(filename, raw) -> list[str]`(최대 8줄, 줄당 1,000자). 2-2의 추출기를 쓴다.
- **DocumentOps 연결 지점:** `knowledge` 저장소의 `EXAMPLE` 후보로 넣는다(`KnowledgeStore.add_candidate`). 사람 검토 뒤에만 쓰는 기존 게이트를 그대로 적용한다.
- 문체 예시는 prompt 참고 자료이며 모델 학습이 아니다. 이 원칙과 문구를 그대로 가져간다.

### 2-7. XLSX 출력 — S, 후순위

- `app/services/excel_service.py`(308)의 `build_excel(docs, title) -> bytes`. 의존성은 xlsxwriter다.
- 문서 표를 시트로 옮기는 기능이라 쓰임이 제한적이다. 견적·일정 검사(`quality/quantitative`) 결과를 표로 내보내는 용도와 함께 필요성을 보고 정한다.

## 3. DecisionDoc 세션 작성 경로의 정리

DecisionDoc의 `/generate/authoring-brief`·`/generate/authored`·`scripts/decisiondoc_author.py`(#75–#77)는 DocumentOps의 author packet·`job resume`과 같은 역할을 한다. 대응표 7절이 경고한 대로 두 경로를 계속 키우면 중복이 늘어난다.

- 새 저장소에는 이 경로를 가져가지 않는다. 쓸모 있는 것은 이미 2-3·2-4에 들어 있다(번들 지침, 수치 근거 우선 규칙, 필수 섹션).
- DecisionDoc 저장소에서는 이 경로를 결함 수정만 하고 기능을 더 늘리지 않는 것을 권고한다(8절 결정 2).

## 4. 가져오지 않는 것

| 항목 | 이유 |
|---|---|
| FastAPI 서버, 웹 화면(단일 파일 SPA) | 서버·화면 없음 결정 |
| tenant·인증·SSO·과금·S3·Lambda·운영 middleware | 로컬 단일 사용자 도구 |
| provider factory·모델 호출·AI 보조 기능 9종 | 세션이 작성 |
| 품질 보정 대체 문장(`quality_guard_*`) | 도구가 문장을 넣지 않는다 |
| JSON schema·Jinja2 템플릿·stabilizer | 세션이 Markdown을 직접 쓰고 필수 섹션으로 검사 |
| DecisionDoc의 DocumentOps trajectory·SFT 거버넌스 | 2026-08-26 결정과 같음 |
| 승인·결재·검토 receipt | DocumentOps의 review·revision 기록을 쓴다. 단계 이름만 참고 |

## 5. 의존성과 라이선스

- DecisionDoc은 MIT(저작권자 본인)이다. vendored 코드와 번들 폰트·바이너리 템플릿은 없다.
- 추가될 라이브러리는 모두 permissive다: defusedxml(PSF), pdfplumber(MIT), xlsxwriter(BSD, 2-7을 할 때만).
- DocumentOps가 이미 쓰지만 선언하지 않은 PyMuPDF는 통합 저장소에서 선언하거나 쓰는 곳을 정리한다.

## 6. 순서와 검증

| 단계 | 단위 | 완료 확인 |
|---|---|---|
| 1 | HWPX 출력(2-1) | 옮긴 테스트 통과, 한글에서 열기·편집·저장·다시 열기 |
| 2 | 입력 추출(2-2) | 형식별 추출 테스트, 합성 HWPX 공고문으로 `source extract` → 세션 인용 → 근거 검사 통과 |
| 3 | 문서 유형(2-3) + 필수 섹션(2-4) | 변환 결과 대조 테스트, 유형 binding packet 생성, 필수 섹션 누락 원고가 차단되는 테스트 |
| 4 | 조달 판단(2-5) | 옮긴 회귀 테스트, 합성 공고·역량 JSON으로 GO/CONDITIONAL_GO/NO_GO 각 1건 |
| 5 | 문체 예시(2-6) | 추출 → 후보 → 검토 승인 뒤에만 사용되는 테스트 |
| 6 | XLSX(2-7) | 필요하다고 정한 경우만 |

- 각 단계는 DocumentOps의 기존 전체 테스트와 coverage 기준(85% 이상)을 유지한다.
- 실제 앱 렌더 확인은 DocumentOps 규칙(디자인 변경은 렌더를 실제로 본 뒤에만 인정)을 따른다.
- 단계별 작업량 추정(코드 이식 기준, 문서·검증 제외): 1·2단계 각 S, 3단계 M, 4단계 M, 5·6단계 S.

## 7. 위험

- **DocumentOps가 계속 바뀐다.** 연결 지점(형식 목록, packet 구조, QA contributor 목록)은 하드코딩이라 이식 중 충돌이 잦을 수 있다. 이식은 DocumentOps 쪽 작업이 멈춘 시점에 단위별로 한다.
- **packet 해시 변경:** 유형 binding을 넣으면 packet bytes가 바뀐다. 기존 job의 재개(`job resume`)가 깨지지 않는지 확인해야 한다.
- **HWPX 스타일 차이:** DecisionDoc HWPX는 자체 스타일이다. DocumentOps의 공공문서 디자인과 맞추기 전까지 DOCX와 HWPX의 모양이 다르다.
- **few-shot·지침의 수치:** 번들 데이터를 옮길 때 구체적 금액·기간이 섞이면 근거 검사와 충돌한다. 변환 스크립트에서 수치를 검사한다.

## 8. 결정 (2026-10-08)

| 항목 | 결정 |
|---|---|
| 순서 | DocumentOps 완성이 먼저(10-07 결정 유지). 그 전에는 DecisionDoc 쪽 준비만 한다: 번들 변환 스크립트(2-3), 이식 대상 모듈의 의존성 정리(2-1·2-2) |
| DecisionDoc | 포트폴리오 저장소로 보존하고 결함 수정만 한다. Human UAT는 "세션 작성 → HWPX·DOCX 출력" 흐름을 실제 문서 1–2건으로 확인하는 범위로 줄인다 |
| 새 저장소 공개 범위 | 비공개로 시작. 공개는 나중에 따로 정한다. 고객 자료와 보호 산출물은 처음부터 넣지 않는다 |
| 문서 유형 이식 형태 | 2-3 권고안(필수 섹션·지침 데이터로 변환) |

### 결정 당시의 검토 내용

1. **순서:** 대응표의 "DocumentOps 완성이 먼저"를 유지하는가. DocumentOps에는 하나로 된 완성 기준이 없다(`docs/DESIGN_LEARNING_PLAN.md` Q1–Q7, `docs/CLAUDE_DEVELOPMENT_HANDOFF.md` §5 A–E). 특히 Q5는 사용자 판정 2건 이상이 필요하다.
   - 권고: 유지한다. 다만 새 저장소를 만들지 않고도 할 수 있는 준비(2-3의 번들 변환 스크립트, 2-1·2-2의 의존성 정리)는 DecisionDoc 쪽에서 먼저 해 둘 수 있다.
2. **DecisionDoc의 앞으로:** 새 저장소에 화면과 서버가 없으므로 DecisionDoc 웹 화면은 이어지지 않는다.
   - 권고: DecisionDoc은 포트폴리오 저장소로 두고 결함 수정만 한다. Human UAT는 웹 화면 대신 "세션 작성 → HWPX·DOCX 출력" 흐름만 실제 문서 1–2건으로 확인한다.
3. **새 저장소 이름과 공개 범위:** 대응표에서 미정. 공개한다면 고객 자료와 보호 산출물은 처음부터 넣지 않는다(대응표 4절).
4. **문서 유형 이식 형태(2-3):** 번들을 JSON·Jinja2 구조 그대로가 아니라 필수 섹션·지침 데이터로 옮기는 안. 이 문서의 권고안이다.

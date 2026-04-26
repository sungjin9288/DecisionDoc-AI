# Report Workflow ERP Implementation Plan

이 문서는 `docs/specs/report_workflow_erp/PRD.md`를 실제 코드로 옮기기 위한 구현 순서다. 목표는 기존 원클릭 생성 흐름을 깨지 않고 단계형 보고서 제작 레일을 점진적으로 추가하는 것이다.

## 1. 현재 repo 기준선

관련 기존 기능:

- `POST /generate/sketch`
  - 현재도 보고서/문서의 빠른 outline과 PPT slide breakdown을 만들 수 있다.
- `app/services/sketch_service.py`
  - Step 1 기획안 생성의 시작점으로 재사용 가능하다.
- `app/storage/approval_store.py`
  - 기안, 검토, 최종 승인 상태 전이를 이미 제공한다.
- `app/routers/approvals.py`
  - 최종 결재와 다운로드 흐름이 이미 존재한다.
- `app/storage/project_store.py`, `app/routers/projects.py`
  - 프로젝트 단위 문서 관리 기반이 이미 있다.
- `app/static/index.html`
  - 현재 UI는 single-file static admin UI이며, 첫 MVP는 이 파일 안에 단계형 패널을 추가하는 방식이 blast radius가 가장 작다.

## 2. 구현 원칙

- 기존 `/generate`, `/generate/from-documents`, `/generate/export`는 유지한다.
- 새 기능은 `/report-workflows/*` namespace로 분리한다.
- 첫 MVP는 local/S3 state backend와 tenant boundary를 기존 store 패턴에 맞춘다.
- 보고서 기획안과 장표 초안은 versioned snapshot으로 저장한다.
- 승인 상태 전이는 backend에서 강제한다. UI만으로 막지 않는다.
- 장표 생성은 승인된 planning version을 입력으로 사용한다.

## 3. Phase 1 Backend MVP

### 3.1 Schema 추가

파일:

- `app/schemas.py`

추가 모델:

- `CreateReportWorkflowRequest`
- `UpdateReportPlanningRequest`
- `ReportWorkflowActionRequest`
- `UpdateReportSlideRequest`
- `GenerateReportSlidesRequest`

검증 규칙:

- `title`은 필수
- `report_type`은 문자열로 시작하되 이후 enum화 가능
- `source_bundle_id` 기본값은 `presentation_kr`
- `docs`와 `attachments_context`는 optional

### 3.2 Store 추가

파일:

- `app/storage/report_workflow_store.py`

주요 dataclass:

- `ReportWorkflowRecord`
- `PlanningVersion`
  - `planning_brief`: 기획 전제와 승인 요청 범위
  - `audience_decision_needs`: 독자/승인권자가 확인해야 할 판단 기준
  - `narrative_arc`: 문제 정의에서 승인 요청까지 이어지는 보고서 흐름
  - `source_strategy`: 첨부자료와 근거를 장표별로 매핑하는 전략
  - `template_guidance`: 공통 장표 구조, 시각화 규칙, 톤앤매너
  - `quality_bar`: 기획 승인 및 장표 제작 전환 기준
- `SlidePlan`
  - `decision_question`: 장표별 승인권자 판단 질문
  - `narrative_role`: 전체 보고서 흐름에서 장표가 맡는 역할
  - `content_blocks`: 장표 내 구성 블록
  - `data_needs`: 추가 데이터와 검증 필요 항목
  - `design_notes`: 레이아웃/시각화 상세 지시
  - `acceptance_criteria`: 장표별 승인 기준
- `SlideDraft`
- `WorkflowComment`

필수 메서드:

```python
create(...)
get(report_workflow_id, tenant_id=...)
list_by_tenant(tenant_id, status=None)
save_planning(...)
approve_planning(...)
request_planning_changes(...)
save_slides(...)
approve_slide(...)
request_slide_changes(...)
submit_final(...)
approve_final(...)
```

저장 위치:

```text
data/tenants/{tenant_id}/report_workflows.json
```

상태 전이 guard:

- `planning_approved` 전에는 `save_slides` 금지
- 모든 필수 slide가 approved 전에는 `submit_final` 금지
- `final_approved` 이후에는 planning/slides 변경 금지

### 3.3 Service 추가

파일:

- `app/services/report_workflow_service.py`

역할:

- planning prompt 생성
- provider 호출
- planning JSON parse/fallback
- approved planning 기반 slide draft prompt 생성
- slide draft JSON parse/fallback
- store 상태 전이 호출

Provider fallback:

- provider가 structured JSON을 깨면 최소 planning/slide 구조를 생성하고 `quality_warning`을 저장한다.

### 3.4 Router 추가

파일:

- `app/routers/report_workflows.py`
- `app/main.py` router include

MVP endpoints:

```text
POST /report-workflows
GET /report-workflows
GET /report-workflows/{id}
POST /report-workflows/{id}/planning/generate
POST /report-workflows/{id}/planning/request-changes
POST /report-workflows/{id}/planning/approve
POST /report-workflows/{id}/slides/generate
POST /report-workflows/{id}/slides/{slide_id}/request-changes
POST /report-workflows/{id}/slides/{slide_id}/approve
POST /report-workflows/{id}/final/submit
POST /report-workflows/{id}/final/approve
```

## 4. Phase 2 UI MVP

파일:

- `app/static/index.html`

추가 UI:

- 상단 또는 bundle area에 `단계형 보고서 제작` 버튼
- `Report Workflow` page/panel
- 프로젝트 생성 form
- Stepper:
  - `1. 기획`
  - `2. 장표 제작`
  - `3. 최종 승인`
- Planning view:
  - 기획 브리프
  - 전체 메시지
  - 독자 의사결정 기준
  - 보고서 스토리라인
  - 자료/근거 전략
  - 템플릿/디자인 가이드
  - 완성 기준
  - 목차
  - 장표별 계획 카드: 의사결정 질문, narrative role, content blocks, data needs, design notes, acceptance criteria
  - 수정 요청
  - 승인 버튼
- Slides view:
  - 장표별 카드
  - 장표 상태 badge
  - 수정 요청
  - 장표 승인
- Final view:
  - 승인 가능 여부
  - 미승인 장표 목록
  - 최종 승인 버튼

UI guard:

- 기획 승인 전에는 `장표 생성` 버튼 disabled
- 미승인 장표가 있으면 `최종 승인` 버튼 disabled
- 최종 승인 이후에는 수정 버튼 disabled

## 5. Phase 3 Approval/Project 연동

목표는 제작 상태와 조직 결재 상태를 섞지 않고, 최종 제출 시점에만 명확하게 연결하는 것이다.

### 5.1 기능 경계

| 모듈 | 책임 | 수정 가능 상태 |
| --- | --- | --- |
| `ReportWorkflowStore` | 기획/장표/최종 제출 전 제작 상태 | `planning_*`, `slides_*`, `final_review` |
| `ApprovalStore` | PM/대표 조직 결재 상태 | `pending`, `approved`, `rejected` 계열 |
| `ProjectStore` | 승인 산출물의 프로젝트 연결 | 최종 승인 이후 document metadata |
| `KnowledgeStore` | opt-in 학습/재사용 artifact | 승인된 artifact metadata |

원칙:

- planning/slides 제작 상태는 `ApprovalStore`에 넣지 않는다.
- `final/submit` 시 승인 snapshot을 만들고 `ApprovalStore` record를 생성하거나 연결한다.
- `ApprovalStore` approval 결과는 `ReportWorkflowRecord.final_*` 필드에 mirror하되, planning/slides version은 변경하지 않는다.
- 최종 승인 이후 project document와 knowledge candidate를 생성할 수 있지만, 이 작업은 report workflow 상태 전이와 별도 side effect로 관리한다.

### 5.2 Approval chain model

추가 후보 파일:

- `app/storage/report_workflow_store.py`
  - `ApprovalStep` dataclass 추가
  - `approval_steps: list[ApprovalStep]` 필드 추가
- `app/storage/report_workflow_store.py`
  - final submit 시 PM/대표 approval chain 생성
  - PM 승인 전 executive 승인 차단
  - final changes requested 상태와 comment 저장 담당
- 후속 `app/services/report_workflow_approval_service.py`
  - ApprovalStore 연결 및 status mirror 담당
- `app/routers/report_workflows.py`
  - `POST /report-workflows/{id}/final/submit`
  - `POST /report-workflows/{id}/final/pm-approve`
  - `POST /report-workflows/{id}/final/executive-approve`
  - `POST /report-workflows/{id}/final/request-changes`

`ApprovalStep` 초안:

```python
@dataclass
class ApprovalStep:
    step_id: str
    stage: str  # pm_review | executive_review
    label: str
    status: str = "pending"
    actor: str | None = None
    decided_at: str | None = None
    comment: str = ""
```

상태 규칙:

- `submit_final`은 모든 필수 slide가 `approved`일 때만 가능하다.
- `submit_final`은 `approval_steps=[pm_review, executive_review]`를 생성한다.
- PM step이 `approved`가 아니면 executive step을 승인할 수 없다.
- PM 또는 executive가 changes requested를 남기면 workflow status는 `final_changes_requested`가 되고, slide 수정 이후 `slides_draft`로 돌아간다.
- 다시 장표가 모두 승인되면 `submit_final`을 다시 호출해 approval step을 새 snapshot으로 재생성한다.
- `final_approved` 이후에는 planning/slides/final request changes를 모두 차단한다.

### 5.3 UI separation

Static admin UI는 다음처럼 기능을 나눈다.

- `문서 생성`
  - 빠른 원클릭 생성만 담당한다.
  - report workflow 상태를 생성하거나 변경하지 않는다.
- `보고서 워크플로우`
  - project intake, planning, slide studio, slide review를 담당한다.
  - PM/대표 결재 상태는 summary badge로만 보여준다.
- `결재함`
  - PM/대표에게 배정된 최종 결재 item을 보여준다.
  - 기획/장표 개별 수정 workflow를 보여주지 않는다.
- `프로젝트`
  - final approved 결과물을 project document로 보여준다.
- `지식 관리`
  - opt-in artifact와 승인 산출물을 재사용 후보로 보여준다.

### 5.4 Project/Knowledge 연동

연동 방향:

- `ReportWorkflowRecord`를 기존 project document로 등록한다.
- 최종 승인 시 기존 `/approvals` record를 자동 생성하거나 연결한다.
- 승인된 report workflow를 project knowledge로 promote 가능하게 한다.
- 자동 promote는 MVP에서는 하지 않고, `promote` button 또는 explicit API로 분리한다.

주의:

- 기존 `ApprovalStore`를 무리하게 확장하지 않는다.
- 보고서 제작 중간 상태는 `ReportWorkflowStore`가 책임지고, 조직 결재/다운로드는 `ApprovalStore`와 연결한다.
- 기존 `ApprovalStore.get()`는 tenant boundary route guard를 통해 사용해야 하므로, 새 연동 service는 항상 `tenant_id`를 명시한다.

## 6. Test Plan

Backend tests:

```text
tests/test_report_workflow_store.py
tests/test_report_workflows_api.py
tests/test_report_workflow_service.py
```

핵심 테스트:

- workflow 생성
- planning 생성/저장
- planning 승인 전 slides 생성 차단
- planning 승인 후 slides 생성 허용
- 장표별 승인 저장
- 미승인 장표가 있으면 final submit 차단
- 모든 장표 승인 후 final approve 성공
- final approved 이후 수정 차단
- tenant boundary 검증
- final submit 시 approval step 생성
- PM 승인 전 executive 승인 차단
- PM changes requested 시 final_changes_requested 저장
- final approval 이후 ApprovalStore와 workflow final mirror 일치
- 결재함에는 final approval item만 노출되고 planning/slide 내부 승인 이벤트는 노출되지 않음

Regression tests:

```text
tests/test_sketch_endpoint.py
tests/test_approval_workflow.py
tests/test_generate.py
```

## 7. Recommended First Commit

첫 구현 commit 범위:

- `app/storage/report_workflow_store.py`
- `tests/test_report_workflow_store.py`
- `app/schemas.py` 최소 schema

이 범위만 먼저 구현하면 provider/API/UI 없이도 핵심 상태 전이 모델을 검증할 수 있다.

## 8. Implementation Order

1. Store와 상태 전이 테스트를 먼저 만든다.
2. Router CRUD를 붙인다.
3. Planning generate service를 붙인다.
4. Slides generate service를 붙인다.
5. Static UI panel을 붙인다.
6. ApprovalStep dataclass와 final approval chain guard를 붙인다.
7. ApprovalStore 연결 service를 추가한다.
8. Project/Knowledge promote metadata를 붙인다.
9. E2E와 deployed smoke를 추가한다.

## 9. Risks

- `app/static/index.html`이 매우 크기 때문에 UI 변경은 regression risk가 높다.
- provider output JSON 안정성이 낮으면 planning/slide parser fallback이 필요하다.
- 기존 approval workflow와 새 report workflow를 너무 일찍 합치면 상태 모델이 복잡해진다.
- 장표별 versioning을 생략하면 AI 학습 데이터와 수정 이력 품질이 떨어진다.
- PM/대표 결재 chain을 UI badge만으로 구현하면 backend guard가 약해진다. 반드시 store/service layer에서 순서를 강제한다.
- 최종 승인 이후 project/knowledge side effect가 실패할 수 있으므로, final approval과 promote를 transaction처럼 묶지 않고 재시도 가능한 후속 작업으로 분리한다.

## 10. Definition of Done

- 사용자가 단계형 보고서 프로젝트를 생성할 수 있다.
- 기획안 생성, 수정 요청, 승인 상태가 저장된다.
- 승인된 기획안을 기반으로 장표 초안이 생성된다.
- 장표별 승인 상태가 저장된다.
- 최종 승인 상태가 저장된다.
- PM/대표 approval chain이 저장되고 순서가 backend에서 강제된다.
- final approval item이 기존 결재함과 연결된다.
- 최종 승인 결과물을 project/knowledge로 promote할 수 있는 metadata가 저장된다.
- 기존 원클릭 생성 테스트가 깨지지 않는다.
- 새 workflow store/router/service 테스트가 통과한다.

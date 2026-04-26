# Report Workflow ERP PRD

DecisionDoc AI의 보고서 생성 경험을 "원클릭 생성" 중심에서 "기획, 제작, 장표별 승인, 최종 결재"가 분리된 단계형 업무 시스템으로 전환하기 위한 제품 스펙이다.

## 1. 배경 / Background

현재 웹 UI는 사용자가 입력값과 첨부자료를 넣고 한 번에 문서를 생성하는 흐름이 중심이다. 이 방식은 빠른 초안 생성에는 유리하지만, 실제 제안서/보고서 품질 관리에는 한계가 있다.

- 보고서 전체 구조가 먼저 합의되지 않은 상태에서 장표가 생성된다.
- 수정 요청이 "전체 문서 재생성"이나 수동 편집으로 흩어진다.
- PM, 대표, 검토자 승인 이력이 문서 생성 데이터와 분리된다.
- 어떤 기획안, 어떤 장표 구조, 어떤 피드백이 좋은 결과를 만들었는지 학습 데이터로 축적하기 어렵다.

따라서 DecisionDoc AI는 단일 생성 도구가 아니라, 보고서 제작 프로젝트를 단계별로 운영하는 lightweight ERP 흐름을 제공해야 한다.

## 2. 목표 / Goals

- 보고서 생성 전 `기획안`을 먼저 만들고 승인받는다.
- 기획안에는 전체 보고서 구조, 장표별 목적, 메시지, 시각화 방향, 템플릿 지시가 포함된다.
- 승인된 기획안을 기준으로 전체 장표 초안을 제작한다.
- 장표별 수정 요청과 승인을 따로 관리한다.
- 완성본은 PM, 대표, 최종 의사결정권자에게 승인 요청할 수 있다.
- 승인/수정/채택 데이터를 향후 prompt 개선, template 추천, 품질 평가에 재사용한다.

## 3. 비목표 / Non-Goals

- 첫 MVP에서 완전한 ERP 회계/자원관리 기능은 만들지 않는다.
- 첫 MVP에서 PowerPoint binary 편집기를 직접 구현하지 않는다.
- 첫 MVP에서 복잡한 권한 매트릭스나 조직도 approval chain builder를 만들지 않는다.
- 기존 `/generate` 원클릭 생성 API를 제거하지 않는다. 빠른 초안 모드는 계속 유지한다.

## 4. 대상 사용자 / Users

- `Owner`: 보고서 프로젝트를 생성하고 최종 납품 책임을 지는 사용자
- `Planner`: 보고서 기획안과 장표 구조를 작성하는 사용자
- `PM Reviewer`: 실무 품질, 제안 전략, 일정 관점에서 승인하는 사용자
- `Executive Approver`: 대표 또는 최종 의사결정권자
- `AI Operator`: AI 생성 결과를 조정하고 재생성/수정 요청을 수행하는 사용자

## 5. 핵심 워크플로우 / Workflow

### Step 0. 프로젝트 생성

사용자는 보고서 프로젝트를 만든다.

필수 입력:

- 프로젝트명
- 고객/기관명
- 보고서 목적
- 제출 대상 또는 승인 대상
- 첨부자료
- 보고서 유형: 제안서, 경영보고서, 사업계획서, 수행계획서, 발표자료 등

결과:

- `report_project_id` 생성
- 상태: `planning_required`

### Step 1. 기획단계

AI는 바로 장표를 만들지 않고 먼저 `보고서 기획안`을 만든다.

기획안 구성은 단순 목차가 아니라 `보고서 설계서(planning blueprint)`로 관리한다.

- 전체 보고서 목적과 핵심 메시지
- 기획 브리프: 보고서가 해결할 의사결정 맥락, 전제, 승인 요청 범위
- 예상 독자와 의사결정 기준
- 전체 narrative arc: 문제 정의, 근거, 해결 방향, 승인 요청으로 이어지는 흐름
- 자료/근거 전략: 첨부자료와 외부 근거를 어떤 장표에 사용할지에 대한 매핑
- 템플릿/디자인 가이드: 장표 공통 구조, 시각화 규칙, 톤앤매너
- 완성 기준: 기획 승인 기준과 제작 단계로 넘길 수 있는 품질 기준
- 전체 목차
- 장표별 구조
- 각 장표별 핵심 주장
- 각 장표별 의사결정 질문과 narrative role
- 각 장표별 content blocks
- 각 장표별 포함해야 할 근거/자료
- 각 장표별 추가 data needs
- 각 장표별 시각화 방향
- 각 장표별 템플릿/레이아웃 설명
- 각 장표별 승인 기준
- 누락 자료와 추가 질문
- 리스크와 보완 방향

상태:

- `planning_draft`
- `planning_changes_requested`
- `planning_approved`

승인 규칙:

- 기획안 승인 전에는 전체 장표 제작을 실행할 수 없다.
- 수정 요청은 기획안 전체 또는 특정 장표 계획 단위로 남긴다.
- 승인된 기획안은 version snapshot으로 고정한다.

### Step 2. 전체 보고서 장표 제작

승인된 기획안을 기준으로 AI가 장표 초안을 만든다.

출력 단위:

- `slide_id`
- 장표 제목
- 장표 목적
- 본문 초안
- 도표/시각화 지시
- speaker note 또는 설명
- 사용된 근거 자료
- 생성 prompt/version metadata

상태:

- `slides_generating`
- `slides_draft`
- `slide_changes_requested`
- `slide_approved`
- `slides_approved`

승인 규칙:

- 각 장표는 개별 승인 가능해야 한다.
- 특정 장표 수정 요청이 있어도 승인된 장표는 잠그거나 변경 영향 범위를 표시한다.
- 전체 보고서 승인 전 모든 필수 장표는 `slide_approved` 상태여야 한다.

### Step 3. 최종 승인

모든 장표가 승인되면 PM/대표 승인 단계로 이동한다.

상태:

- `final_review`
- `final_changes_requested`
- `final_approved`
- `delivered`

결과:

- 최종 보고서 export
- 승인 이력 snapshot
- 학습/품질 평가용 artifact 저장

## 6. 상태 모델 / State Model

권장 상위 상태:

```text
planning_required
planning_draft
planning_changes_requested
planning_approved
slides_generating
slides_draft
slides_changes_requested
slides_approved
final_review
final_changes_requested
final_approved
delivered
archived
```

권장 전이:

```text
planning_required -> planning_draft
planning_draft -> planning_changes_requested
planning_changes_requested -> planning_draft
planning_draft -> planning_approved
planning_approved -> slides_generating
slides_generating -> slides_draft
slides_draft -> slides_changes_requested
slides_changes_requested -> slides_draft
slides_draft -> slides_approved
slides_approved -> final_review
final_review -> final_changes_requested
final_changes_requested -> slides_draft
final_review -> final_approved
final_approved -> delivered
```

## 7. 데이터 모델 초안 / Data Model

### ReportProject

```json
{
  "report_project_id": "uuid",
  "tenant_id": "default",
  "title": "2026 스마트공장 제안서",
  "client": "국토교통부",
  "report_type": "proposal_presentation",
  "status": "planning_draft",
  "owner": "sungjin",
  "created_at": "iso",
  "updated_at": "iso",
  "source_bundle_id": "presentation_kr",
  "source_request_id": "optional",
  "current_plan_version": 1,
  "current_slide_version": 0
}
```

### PlanningVersion

```json
{
  "plan_id": "uuid",
  "report_project_id": "uuid",
  "version": 1,
  "status": "draft",
  "objective": "보고서 목적",
  "audience": "PM/대표/발주기관",
  "executive_message": "핵심 메시지",
  "planning_brief": "의사결정 맥락과 승인 요청 범위",
  "audience_decision_needs": ["승인권자가 확인해야 할 판단 기준"],
  "narrative_arc": ["문제 정의", "근거", "해결 방향", "승인 요청"],
  "source_strategy": ["첨부자료와 근거의 장표별 매핑 전략"],
  "template_guidance": ["headline/evidence/decision block 구조"],
  "quality_bar": ["기획 승인과 장표 제작 전환 기준"],
  "table_of_contents": ["..."],
  "slide_plans": [
    {
      "slide_id": "slide-001",
      "page": 1,
      "title": "사업 이해와 제안 방향",
      "purpose": "발주 배경과 제안 전략을 한 장에서 설명",
      "key_message": "교차로 안전 문제를 AI 기반 감지 체계로 해결한다",
      "decision_question": "이 사업에서 어떤 제안 방향을 승인할 것인가?",
      "narrative_role": "문제 정의에서 제안 방향으로 넘어가는 연결 장표",
      "layout": "상단 메시지, 좌측 문제정의, 우측 솔루션 구조도",
      "visual_direction": "교차로 위험요소 흐름도",
      "required_evidence": ["RFP 요구사항", "회사 실적", "기술 구성도"],
      "content_blocks": ["발주 배경", "핵심 문제", "제안 방향"],
      "data_needs": ["RFP 요구사항 원문", "기술 구성 근거"],
      "design_notes": ["좌측 문제, 우측 해결 구조를 대비 배치"],
      "acceptance_criteria": ["핵심 질문에 답함", "근거와 추가 확인 항목이 분리됨"],
      "approval_status": "pending"
    }
  ],
  "open_questions": ["..."],
  "risk_notes": ["..."],
  "created_by": "ai",
  "approved_by": null,
  "approved_at": null
}
```

### SlideDraft

```json
{
  "slide_id": "slide-001",
  "report_project_id": "uuid",
  "plan_version": 1,
  "draft_version": 1,
  "status": "draft",
  "title": "사업 이해와 제안 방향",
  "body": "장표 본문",
  "visual_spec": "도식화 지시",
  "speaker_note": "PM 설명용 note",
  "source_refs": ["file.pdf#p3"],
  "comments": [],
  "approved_by": null,
  "approved_at": null
}
```

### WorkflowComment

```json
{
  "comment_id": "uuid",
  "target_type": "plan|slide|final",
  "target_id": "slide-001",
  "author": "pm",
  "role": "reviewer",
  "content": "3번 장표에 실증사례를 추가",
  "is_change_request": true,
  "created_at": "iso"
}
```

## 8. API 초안 / API Draft

기존 `/projects`, `/approvals`, `/generate/sketch`, `/generate`, `/generate/export`를 재사용하되 보고서 워크플로우 전용 API를 추가한다.

```text
POST   /report-workflows
GET    /report-workflows
GET    /report-workflows/{id}

POST   /report-workflows/{id}/planning/generate
PUT    /report-workflows/{id}/planning
POST   /report-workflows/{id}/planning/request-changes
POST   /report-workflows/{id}/planning/approve

POST   /report-workflows/{id}/slides/generate
GET    /report-workflows/{id}/slides
PUT    /report-workflows/{id}/slides/{slide_id}
POST   /report-workflows/{id}/slides/{slide_id}/request-changes
POST   /report-workflows/{id}/slides/{slide_id}/approve

POST   /report-workflows/{id}/final/submit
POST   /report-workflows/{id}/final/request-changes
POST   /report-workflows/{id}/final/approve
POST   /report-workflows/{id}/export
```

## 9. 기능 분리 원칙 / Functional Boundaries

단계형 보고서 제작은 "생성 기능"이 아니라 여러 업무 기능이 연결된 제작/검토/결재 시스템으로 취급한다. 각 기능은 다음 책임만 가진다.

| 기능 영역 | 책임 | 소유 데이터 | 다른 영역으로 넘기는 산출물 |
| --- | --- | --- | --- |
| Project Intake | 보고서 프로젝트 생성, 고객/목적/첨부 맥락 수집 | `ReportWorkflowRecord` 기본 metadata, source refs | planning 입력 context |
| Planning Studio | 전체 목차, 장표별 목적/메시지/레이아웃 기획 | `PlanningVersion`, `SlidePlan` | approved planning snapshot |
| Slide Studio | 승인된 기획안을 기준으로 장표 초안 생성/재생성 | `SlideDraft`, draft version, visual spec | slide approval candidate |
| Slide Review | 장표별 수정 요청과 승인 | slide comments, slide approval status | all-slides-approved gate |
| Executive Approval | PM/대표/최종권자 결재 chain | approval steps, decision comments, final snapshot | final approved package |
| Delivery/Export | PPTX export, 납품 snapshot 고정 | export metadata, file refs | delivered artifact |
| Learning Capture | opt-in된 승인/수정 데이터를 학습 후보로 저장 | `learning_artifacts` | prompt/eval 개선 입력 |

경계 규칙:

- `ReportWorkflowStore`는 제작 중간 상태의 source of truth다.
- `ApprovalStore`는 조직 결재 요청과 최종 승인 이력의 source of truth다.
- Planning/Slide 수정 요청은 `ReportWorkflowStore` 내부 comment로 유지하고, 최종 조직 결재가 필요한 시점에만 `ApprovalStore`로 연결한다.
- `ProjectStore`와 `KnowledgeStore`는 최종 승인 이후 자산화/검색/재사용 레일이며 제작 상태를 직접 변경하지 않는다.
- 원클릭 `/generate` 흐름은 빠른 초안 생성 모드로 유지하고, ERP workflow의 승인 상태를 변경하지 않는다.

## 10. 결재 구조 / Approval Structure

보고서 제작에는 두 종류의 승인이 존재한다.

1. 제작 승인
   - 대상: 기획안, 개별 장표
   - 목적: AI가 다음 제작 단계로 넘어가도 되는지 확인
   - 저장 위치: `ReportWorkflowStore`
   - 예: 기획 승인 전 장표 생성 차단, 장표 승인 전 최종 검토 차단

2. 조직 결재
   - 대상: 최종 보고서 package
   - 목적: PM/대표/최종권자에게 제출 가능한 산출물인지 결재
   - 저장 위치: `ApprovalStore` + `ReportWorkflowRecord.final_*` mirror
   - 예: PM 승인 후 대표 승인, 대표 반려 시 final changes requested

### 기본 결재 chain

MVP 이후의 기본 chain은 다음 순서를 따른다.

```text
Owner submit
  -> PM Reviewer approval
  -> Executive Approver approval
  -> final_approved
  -> delivered/export locked
```

역할별 책임:

| 역할 | 승인 대상 | 가능 액션 | 차단 규칙 |
| --- | --- | --- | --- |
| Owner | 프로젝트 생성, 최종 제출 | create, submit final, export draft | executive approve 불가 |
| Planner | 기획안 | generate/request changes/approve planning | final approve 불가 |
| PM Reviewer | 장표 품질, 실무 타당성 | approve slide, request slide/final changes, PM approve | planning 없이 slide approve 불가 |
| Executive Approver | 최종 보고서 | executive approve, reject/request changes | 모든 필수 장표 승인 전 결재 불가 |
| Admin/Ops | 운영 복구 | audit/read-only override 후보 | 일반 결재자로 자동 간주하지 않음 |

### ApprovalStep 모델 초안

```json
{
  "step_id": "uuid",
  "workflow_id": "uuid",
  "sequence": 1,
  "stage": "pm_review",
  "required_role": "pm_reviewer",
  "assignee_user_id": "optional",
  "status": "pending|approved|changes_requested|skipped",
  "decided_by": null,
  "decided_at": null,
  "comment": "",
  "snapshot_ref": "planning:v1/slides:v2/export:draft"
}
```

상태 전이:

```text
slides_approved -> final_review
final_review -> pm_changes_requested
pm_changes_requested -> slides_draft
final_review -> pm_approved
pm_approved -> executive_review
executive_review -> executive_changes_requested
executive_changes_requested -> slides_draft
executive_review -> final_approved
final_approved -> delivered
```

최소 backend guard:

- PM 승인 전 대표 승인 불가
- 모든 필수 장표 승인 전 PM 승인 불가
- final 승인 이후 planning/slides/final comments 변경 불가
- changes requested 이후 재생성/수정되면 해당 approval step은 다시 `pending`으로 돌아간다.
- 같은 사용자가 Owner이면서 Executive일 수는 있지만, 기본 정책은 self-final-approval을 경고 또는 차단한다. MVP에서는 경고 metadata를 남기고, enterprise phase에서 tenant policy로 차단한다.

## 11. UI 초안 / UI Draft

기존 메인 생성 화면에 "단계형 보고서 제작" 진입점을 추가한다.

화면 구성:

- `보고서 프로젝트 대시보드`
  - 프로젝트명, 고객명, 현재 단계, 승인 대기자, 마지막 수정일
- `0. 프로젝트/소스`
  - 고객/목적/제출 대상
  - 첨부/참조자료 요약
  - owner/PM/대표 후보 지정
- `1. 기획`
  - AI 기획안 생성
  - 전체 목차
  - 장표별 계획 카드
  - 수정 요청
  - 기획 승인
- `2. 장표 제작`
  - 장표 리스트
  - 장표별 AI 재생성/수정
  - 장표별 승인 상태
  - 전체 장표 승인율
- `3. 최종 승인`
  - PM 승인 상태
  - 대표 승인 상태
  - 최종 변경 요청
  - export
  - delivery snapshot

UI 분리:

- `문서 생성`: 빠른 초안/원클릭 생성. ERP 상태 없음.
- `보고서 워크플로우`: 단계형 제작 및 승인. workflow 상태 source.
- `결재함`: 조직 결재 대기/승인/반려 목록. final approval source.
- `프로젝트`: 승인된 산출물과 고객/과업 단위 관리.
- `지식 관리`: opt-in artifact와 승인된 결과의 재사용.

## 12. AI 학습 데이터 / Learning Data

학습 또는 prompt 개선에 사용할 수 있는 이벤트:

- 승인된 기획안
- 반려된 기획안과 수정 요청
- 장표별 승인/수정 요청
- 최종 승인본
- export된 결과물
- 생성 provider/model/prompt version
- 사용자가 직접 편집한 diff

저장 원칙:

- tenant boundary를 유지한다.
- 승인된 결과와 반려된 결과를 구분한다.
- 원본 첨부자료는 그대로 학습에 사용하지 않고, extract된 metadata와 참조만 저장한다.
- 개인정보/영업비밀이 포함될 수 있으므로 opt-in learning flag를 둔다.

결정:

- `learning_opt_in` 기본값은 workflow 단위 `false`다.
- tenant 단위 default policy는 후속 phase에서 추가하되, workflow 단위 opt-in이 항상 우선한다.
- 원본 첨부파일 자체는 learning artifact에 저장하지 않는다.
- 승인된 planning/slides/final metadata와 수정 요청 텍스트만 저장한다.

## 13. MVP 구현 범위 / MVP Scope

1차 MVP:

- JSON 기반 `ReportWorkflowStore`
- `POST /report-workflows`
- `POST /report-workflows/{id}/planning/generate`
- `POST /report-workflows/{id}/planning/approve`
- `POST /report-workflows/{id}/slides/generate`
- `POST /report-workflows/{id}/slides/{slide_id}/approve`
- `POST /report-workflows/{id}/final/approve`
- 단일 HTML UI에 단계형 패널 추가
- pytest service/router 테스트

2차:

- 장표별 수정 요청
- PM/대표 approval chain model
- `final/submit` 시 `ApprovalStore` record 생성 또는 연결
- approval notification 연동
- 프로젝트 상세 페이지와 양방향 연결
- 최종 export snapshot

3차:

- prompt learning/eval store 연결
- 장표별 품질 점수
- version diff UI
- tenant별 결재 정책과 self-approval 차단 정책

## 14. 기존 기능 재사용 지점 / Reuse

- `app/services/sketch_service.py`
  - Step 1 planning draft의 기반으로 확장 가능
- `app/storage/approval_store.py`
  - Step 3 최종 승인 또는 승인 이벤트 기록에 재사용 가능
- `app/storage/project_store.py`
  - report project linkage에 재사용 가능
- `app/routers/generate.py`
  - Step 2 slides generation에서 기존 generation provider routing 재사용 가능
- `app/static/index.html`
  - 첫 MVP는 별도 SPA 도입 없이 기존 static admin UI에 패널 추가

## 15. Acceptance Criteria

- 사용자는 원클릭 생성 대신 단계형 보고서 프로젝트를 만들 수 있다.
- 기획안 승인 전에는 장표 생성이 막힌다.
- 기획안에는 장표별 제목, 목적, 핵심 메시지, 레이아웃, 시각화 지시가 포함된다.
- 장표 생성 후 장표별 승인 상태를 확인할 수 있다.
- 모든 필수 장표가 승인되지 않으면 최종 승인으로 넘어갈 수 없다.
- 최종 승인 이력이 저장된다.
- PM 승인 전 대표 승인이 불가능하다.
- 최종 승인 후 planning/slides 수정이 불가능하다.
- 결재함에서는 최종 보고서 approval만 보이고, 기획/장표 제작 내부 상태는 보고서 워크플로우에서만 보인다.
- 승인된 workflow는 project/knowledge로 promote 가능한 metadata를 가진다.
- 기존 `/generate` 원클릭 흐름은 깨지지 않는다.

## 16. 결정된 사항 / Decisions

- PPTX export는 MVP에 포함하며 기존 `pptx_service.build_pptx` adapter를 재사용한다.
- 장표별 승인자는 기본적으로 PM Reviewer가 담당하고, 후속 phase에서 optional specialist reviewer를 추가한다.
- AI learning opt-in은 workflow 단위로 시작한다.
- 기존 `approvals`와 `report-workflows`는 합치지 않는다. 최종 조직 결재 시점에만 연결한다.
- Report Workflow 화면은 제작 상태를, 결재함은 조직 결재 상태를 보여준다.

## 17. 남은 질문 / Open Questions

- tenant별로 PM/대표 기본 assignee를 어디서 관리할지 결정해야 한다.
- self-final-approval을 모든 tenant에서 차단할지, warning으로 시작할지 운영 정책을 정해야 한다.
- 승인 완료된 smoke/test workflow를 정리할 archive/delete API를 언제 추가할지 결정해야 한다.

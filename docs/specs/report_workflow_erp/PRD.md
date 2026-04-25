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

기획안 구성:

- 전체 보고서 목적과 핵심 메시지
- 예상 독자와 의사결정 포인트
- 전체 목차
- 장표별 구조
- 각 장표별 핵심 주장
- 각 장표별 포함해야 할 근거/자료
- 각 장표별 시각화 방향
- 각 장표별 템플릿/레이아웃 설명
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
  "table_of_contents": ["..."],
  "slide_plans": [
    {
      "slide_id": "slide-001",
      "page": 1,
      "title": "사업 이해와 제안 방향",
      "purpose": "발주 배경과 제안 전략을 한 장에서 설명",
      "key_message": "교차로 안전 문제를 AI 기반 감지 체계로 해결한다",
      "layout": "상단 메시지, 좌측 문제정의, 우측 솔루션 구조도",
      "visual_direction": "교차로 위험요소 흐름도",
      "required_evidence": ["RFP 요구사항", "회사 실적", "기술 구성도"],
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

## 9. UI 초안 / UI Draft

기존 메인 생성 화면에 "단계형 보고서 제작" 진입점을 추가한다.

화면 구성:

- `보고서 프로젝트 대시보드`
  - 프로젝트명, 고객명, 현재 단계, 승인 대기자, 마지막 수정일
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
  - 승인 대상자
  - 최종 변경 요청
  - export
  - delivery snapshot

## 10. AI 학습 데이터 / Learning Data

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

## 11. MVP 구현 범위 / MVP Scope

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
- approval notification 연동
- 프로젝트 상세 페이지와 양방향 연결
- 최종 export snapshot

3차:

- prompt learning/eval store 연결
- 장표별 품질 점수
- PM/대표 role 기반 approval chain
- version diff UI

## 12. 기존 기능 재사용 지점 / Reuse

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

## 13. Acceptance Criteria

- 사용자는 원클릭 생성 대신 단계형 보고서 프로젝트를 만들 수 있다.
- 기획안 승인 전에는 장표 생성이 막힌다.
- 기획안에는 장표별 제목, 목적, 핵심 메시지, 레이아웃, 시각화 지시가 포함된다.
- 장표 생성 후 장표별 승인 상태를 확인할 수 있다.
- 모든 필수 장표가 승인되지 않으면 최종 승인으로 넘어갈 수 없다.
- 최종 승인 이력이 저장된다.
- 기존 `/generate` 원클릭 흐름은 깨지지 않는다.

## 14. Open Questions

- 첫 MVP에서 실제 PPTX 파일까지 생성할지, markdown/HTML 장표 draft까지만 만들지 결정해야 한다.
- 장표별 승인자를 PM 한 명으로 둘지, role 기반 다중 승인으로 갈지 결정해야 한다.
- AI learning opt-in을 tenant 단위로 둘지 project 단위로 둘지 결정해야 한다.
- 기존 `approvals`와 새 `report-workflows`를 하나로 합칠지, 최종 승인 단계에서만 연결할지 결정해야 한다.

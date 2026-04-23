# DecisionDoc AI 회사 전달 메시지 초안 - 2026-04-23

이 문서는 DecisionDoc AI v1.1.4 기준 회사 전달 메일 또는 메신저에 바로 붙여 넣을 수 있는 실행용 문안입니다.

기준 운영 환경은 `https://admin.decisiondoc.kr` 이며, 현재 전달 범위는 `admin` 운영 baseline입니다. 고객사 전용 분리 환경 구성은 다음 단계에서 별도 rollout로 진행합니다.

## 1. 발송 전 체크리스트

- 수신자가 대표/의사결정자인지, 운영/보안 담당자인지 구분한다.
- 1차 발송에는 소개 PDF 3종만 첨부한다.
- 운영 검토가 시작된 뒤에만 운영/보안 문서를 추가 발송한다.
- API key, ops key, provider key, SSH private key는 메일이나 일반 메신저에 넣지 않는다.
- 키 전달이 필요하면 별도 보안 채널을 먼저 정한다.
- 데모 일정과 참석자를 확인한 뒤 서비스 URL을 공유한다.

## 2. 1차 발송 - 대표/의사결정자용

### 권장 제목

```text
DecisionDoc AI v1 소개 자료 전달드립니다
```

또는

```text
내부 설치형 AI 문서 생성 플랫폼 DecisionDoc AI 소개 자료
```

### 첨부 파일

- `output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf`
- `output/pdf/decisiondoc_ai_executive_intro_ko.pdf`
- `output/pdf/decisiondoc_ai_notebooklm_comparison_ko.pdf`

### 발송 문안

```text
안녕하세요.

DecisionDoc AI v1.1.4 기준 소개 자료를 전달드립니다.

DecisionDoc AI는 단순한 AI 문서 작성 도구가 아니라, 조직 내부에서 제안서·검토 문서·의사결정 문서를 생성하고 검토하고 export하는 흐름까지 고려한 내부 설치형 문서 운영 플랫폼입니다.

먼저 검토하실 자료는 아래 3가지입니다.
1. 미팅용 1장 요약
2. 제품 소개서
3. NotebookLM 비교 자료

현재 기준 운영 환경은 https://admin.decisiondoc.kr 입니다.
고객사 전용 분리 환경은 실제 도입 검토 단계에서 별도 도메인, API key, 운영 key, 데이터 저장소를 분리해 구성하는 방식으로 진행합니다.

운영/보안/설치 방식까지 검토가 필요하시면 내부 설치형 운영 설명서와 handoff 문서를 추가로 전달드리겠습니다.
```

## 3. 2차 발송 - 운영/보안 담당자용

### 권장 제목

```text
DecisionDoc AI v1 운영 기준선 및 설치형 도입 자료 전달드립니다
```

### 첨부 또는 링크

- `output/pdf/decisiondoc_ai_internal_deployment_brief_ko.pdf`
- `output/pdf/decisiondoc_ai_company_delivery_guide_ko.pdf`
- `docs/deployment/admin_v1_handoff.md`
- `docs/deployment/admin_v1_acceptance_20260423.md`
- `docs/security_policy.md`

### 발송 문안

```text
안녕하세요.

DecisionDoc AI v1.1.4 운영 기준선과 설치형 도입 검토 자료를 전달드립니다.

현재 admin 기준 운영 환경은 https://admin.decisiondoc.kr 이며, release v1.1.4 기준으로 production deploy, provider routing, post-deploy smoke, sales PDF pack 검증이 완료된 상태입니다.

운영 검토 시에는 아래 순서로 보시면 됩니다.
1. 내부 설치형 도입 설명서
2. 회사 전달 가이드
3. Admin v1 handoff 문서
4. Admin v1 acceptance record
5. 정보보호 정책

이번 전달 범위는 admin 운영 baseline입니다.
고객사 전용 분리 환경은 별도 도메인, 별도 runtime API key, 별도 ops key, 별도 데이터 저장소 기준으로 다음 phase에서 구성하는 것을 권장합니다.

API key, provider key, ops key, SSH private key는 본 메일에 포함하지 않았습니다.
실제 운영 키 전달이 필요한 경우 별도 보안 채널을 지정한 뒤 분리 전달하겠습니다.
```

## 4. 데모 일정 확정용 짧은 문안

```text
자료 검토 후 30분 정도의 데모 미팅을 제안드립니다.

데모에서는 아래 흐름만 짧게 확인하겠습니다.
1. 기본 문서 생성
2. 첨부 자료 기반 문서 생성
3. PDF/export 결과 확인
4. 운영/보안 분리 방식 설명

가능하신 일정 2~3개를 주시면 맞춰서 진행하겠습니다.
```

## 5. 현재 상태 한 줄 요약

```text
DecisionDoc AI admin 운영 baseline은 v1.1.4 기준 production 배포와 post-deploy smoke가 통과되어 회사 전달 가능한 상태이며, 고객사 전용 분리 환경은 다음 단계에서 별도 rollout로 구성합니다.
```

## 6. 절대 같이 보내지 말아야 하는 것

- `.env.prod` 원문
- `DECISIONDOC_API_KEYS`
- `DECISIONDOC_OPS_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- 서버 SSH private key

## 7. 발송 후 남길 기록

- 발송 일시
- 수신자와 역할
- 첨부한 PDF 목록
- 공유한 운영 문서 목록
- 데모 일정 후보
- 키 전달 여부와 사용한 보안 채널

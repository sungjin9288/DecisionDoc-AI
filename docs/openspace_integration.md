# DecisionDoc AI OpenSpace Integration Guide

## 목적
이 문서는 DecisionDoc AI에 OpenSpace를 어떤 방식으로 붙여야 하는지, 그리고 어디까지 붙이지 말아야 하는지를 정리한다.

핵심 방향은 다음과 같다.
- OpenSpace를 FastAPI 서비스의 핵심 런타임 안에 집어넣지 않는다.
- OpenSpace를 개발/운영용 보조 학습 계층으로 붙인다.
- 반복되는 문서 생성, 평가, 템플릿 개선, 운영 점검 작업에서 스킬을 진화시킨다.
- 기존 provider, storage, auth, tenant, export 경계를 그대로 유지한다.

현재 실제 반영 범위는 Phase 1이다.
- repo-local bridge skill scaffolding은 존재한다.
- `Decision Council v1`와 procurement hardening 문맥을 이 skill들이 읽도록 정리한다.
- OpenSpace runtime dependency, MCP 서버 연결, 앱 내부 호출은 현재 scope가 아니다.

## 이 레포에서의 적합도
DecisionDoc AI는 OpenSpace와 궁합이 나쁘지 않지만, `orchestration`과는 쓰임새가 다르다.

이 레포에서 OpenSpace가 잘 맞는 영역:
- 번들별 프롬프트/템플릿 개선 루프
- 평가 실패 패턴 분석 및 재시도 가이드
- 운영 체크리스트 자동화
- 문서 품질 하드닝 작업
- static/PWA 셸 개선 작업

이 레포에서 OpenSpace가 직접 주도하면 안 되는 영역:
- 요청 처리 런타임
- 인증/인가 판단
- 테넌트 경계
- 스토리지 구현 교체
- provider 호출 계약 자체의 변경

## 원칙

### 1. OpenSpace는 외부 에이전트 레이어다
OpenSpace는 이 앱의 런타임 dependency로 주입하는 것이 아니라, Codex/Claude/Cursor 같은 에이전트가 이 repo를 다룰 때 쓰는 학습/복구/재사용 레이어다.

즉:
- 앱은 계속 `FastAPI + provider/storage abstraction` 구조로 동작한다.
- OpenSpace는 repo 작업을 더 잘 수행하도록 돕는다.

### 2. repo 파일이 항상 우선이다
다음 파일들이 OpenSpace보다 우선한다.
- `/Users/sungjin/dev/personal/DecisionDoc-AI/AGENTS.md`
- `/Users/sungjin/dev/personal/DecisionDoc-AI/README.md`
- `/Users/sungjin/dev/personal/DecisionDoc-AI/docs/architecture.md`
- `/Users/sungjin/dev/personal/DecisionDoc-AI/docs/security_policy.md`
- `/Users/sungjin/dev/personal/DecisionDoc-AI/docs/test_plan.md`

### 3. mock/provider/storage 경계는 유지한다
OpenSpace 도입으로 인해 다음 동작이 흔들리면 안 된다.
- `mock` provider의 결정론적 테스트 경로
- `local`/`s3` storage abstraction
- FastAPI app startup wiring
- strict Pydantic validation
- export pipeline의 기존 형식별 동작

## 권장 구조

### 공용 OpenSpace 설치
이 섹션은 향후 선택적 host integration을 위한 참고다. 현재 repo 구현 완료 범위는 아니다.

권장 경로:
`/Users/sungjin/dev/personal/agent-infra/OpenSpace`

권장 설치:

```bash
git clone https://github.com/HKUDS/OpenSpace.git /Users/sungjin/dev/personal/agent-infra/OpenSpace
cd /Users/sungjin/dev/personal/agent-infra/OpenSpace
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
openspace-mcp --help
```

### 호스트 에이전트 MCP 연결
실제 사용하는 에이전트 호스트에 `openspace-mcp`를 연결할 수 있지만, 현재 repo release contract는 여기에 의존하지 않는다.

예시:

```json
{
  "mcpServers": {
    "openspace": {
      "command": "openspace-mcp",
      "toolTimeout": 600,
      "env": {
        "OPENSPACE_HOST_SKILL_DIRS": "/path/to/agent/skills",
        "OPENSPACE_WORKSPACE": "/Users/sungjin/dev/personal/agent-infra/OpenSpace",
        "OPENSPACE_API_KEY": "optional"
      }
    }
  }
}
```

### repo-local bridge skill
이 레포는 이미 `.agents/skills/`를 사용하므로, 현재 OpenSpace 반영은 OpenSpace bridge skill과 repo-local domain skill을 함께 두는 방식으로 정리한다.

현재 유지 대상 디렉터리:
- `.agents/skills/decisiondoc-procurement-eval/`
- `.agents/skills/decisiondoc-openspace-bootstrap/`
- `.agents/skills/decisiondoc-openspace-docgen/`
- `.agents/skills/decisiondoc-openspace-eval/`
- `.agents/skills/decisiondoc-openspace-ui/`

구분:
- `decisiondoc-openspace-*` 계열은 OpenSpace 보조 학습/복구 레이어를 위한 bridge skill이다.
- `decisiondoc-procurement-eval`은 procurement/G2B/domain-specific 작업을 위한 repo-local task skill이며, OpenSpace bridge 자체를 대체하지 않는다.

## 프로젝트별 상세 이식안

### A. Bootstrap skill
목적:
- 에이전트가 이 repo를 다룰 때 먼저 읽어야 할 파일과 금지 경계를 고정

권장 내용:

```md
# decisiondoc-openspace-bootstrap

Read first:
1. `AGENTS.md`
2. `README.md`
3. `docs/architecture.md`
4. `docs/security_policy.md`
5. `docs/test_plan.md`

Rules:
- Preserve provider and storage abstractions.
- Keep `mock` flow deterministic.
- Do not move env lookups into route handlers.
- Do not widen auth, tenant, or export semantics without explicit repo support.
```

### B. Doc generation skill
목적:
- 번들 작성, 프롬프트 구조화, 템플릿 개선, export 전후 정리 같은 반복 작업 학습

가장 먼저 학습시키기 좋은 작업:
- `app/templates/` 아래 Jinja 템플릿 개선
- `app/services/` 문서 생성 파이프라인의 품질 향상
- `app/bundle_catalog/` 신규 bundle 설계 보조
- `docs/` 사용자용 예시 문서 정리

권장 규칙:
- route handler 안에 복잡한 비즈니스 로직을 밀어 넣지 않는다.
- `services/`, `providers/`, `storage/`, `templates/` 경계를 유지한다.
- provider-specific fallback을 조용히 추가하지 않는다.

### C. Eval skill
목적:
- 평가 실패 패턴을 스킬로 축적하고, 반복되는 품질 저하를 줄임

좋은 초기 대상:
- `app/eval/`
- `app/eval_live/`
- `tests/test_quality_*`
- 품질 lint 실패 후 보정 루프

권장 규칙:
- `live` 평가는 항상 선택적 경로로 취급
- 환경변수 미설정은 fail이 아니라 `skipped`로 다루는 현재 repo 관행을 유지
- 품질 개선은 템플릿/서비스/평가 규칙 보정으로 우선 해결

### D. UI skill
목적:
- `app/static/` 아래 PWA 셸과 정적 화면을 더 일관되게 개선

이 레포에서 `DESIGN.md`는 가능하지만 보조 역할이어야 한다.

적용 위치:
- `/Users/sungjin/dev/personal/DecisionDoc-AI/DESIGN.md`

적용 대상:
- `app/static/index.html`
- `app/static/offline.html`
- PWA icon/manifest와 맞물리는 정적 경험

적용하지 말아야 할 것:
- approval workflow semantics
- tenant/project/security flows
- API contract

## 권장 파일 구조

```text
DecisionDoc-AI/
├── .agents/
│   └── skills/
│       ├── decisiondoc-procurement-eval/
│       ├── decisiondoc-openspace-bootstrap/
│       │   └── SKILL.md
│       ├── decisiondoc-openspace-docgen/
│       │   └── SKILL.md
│       ├── decisiondoc-openspace-eval/
│       │   └── SKILL.md
│       └── decisiondoc-openspace-ui/
│           └── SKILL.md
├── docs/
│   └── openspace_integration.md
├── app/
│   ├── services/
│   ├── eval/
│   ├── eval_live/
│   ├── templates/
│   └── static/
└── DESIGN.md
```

## 상세 구축 단계

### Phase 0: 공용 설치
선택적 future integration. 현재 repo 구현 완료 범위는 아님.

### Phase 1: repo bootstrap 연결
현재 반영 완료 범위.

- `.agents/skills/decisiondoc-procurement-eval/SKILL.md`
- `.agents/skills/decisiondoc-openspace-bootstrap/SKILL.md`
- `.agents/skills/decisiondoc-openspace-docgen/SKILL.md`
- `.agents/skills/decisiondoc-openspace-eval/SKILL.md`
- `.agents/skills/decisiondoc-openspace-ui/SKILL.md`

이 skill들의 현재 역할:
- `decisiondoc-openspace-*` 계열:
  - repo contract first
  - generation/eval/ui hardening 가이드 축적
- `decisiondoc-procurement-eval`:
  - procurement / Decision Council / G2B / admin route 관련 domain 규칙 유지

앱 runtime이나 request path에는 연결하지 않는다.

### Phase 2: 문서 생성 루프 연결
반복 빈도가 높은 문서 생성 흐름부터 붙인다.

추천 순서:
1. 템플릿 개선
2. bundle prompt 개선
3. export 전후 포맷 품질 개선
4. docs 사용 예시 개선

### Phase 3: eval/quality 루프 연결
반복 실패가 잘 쌓이는 품질 경로를 OpenSpace가 복구 가능하게 만든다.

추천 순서:
1. 품질 lint 실패 원인 분류
2. fixture 기반 품질 회귀 분석
3. live 평가 실패 시 `skipped / timeout / provider error / schema issue` 분류

### Phase 4: UI에 `DESIGN.md` 선택 적용
`DESIGN.md`는 정적 셸 개선 작업에만 제한적으로 도입한다.

좋은 대상:
- landing/empty state
- offline 상태 화면
- export/download 대기 화면

나쁜 대상:
- 복잡한 운영 플로우 semantics
- 권한/승인 로직

## 먼저 진화시킬 스킬 후보

### 1. prompt/template repair
관찰 포인트:
- 자주 누락되는 섹션
- bundle별 서식 일관성
- 한국어 문체 drift

### 2. eval failure triage
관찰 포인트:
- heuristic lint 반복 실패
- live vs mock 차이
- bundle별 취약 패턴

### 3. export polish
관찰 포인트:
- docx/pdf/pptx/xlsx 변환 시 품질 이슈
- 섹션 헤더, 표, 리스트, 문단 spacing 불안정

### 4. ops checklist generation
관찰 포인트:
- 운영 runbook 반복 작업
- 배포 후 점검 순서
- 장애 대응 문서의 일관성

## `DESIGN.md` 사용 규칙

### 권장
- visual rhythm
- typography hierarchy
- static shell tone
- empty/loading/offline/export states

### 금지
- backend architecture authority
- security policy authority
- tenant or approval semantics override
- provider selection policy

## 최소 체크리스트
- [ ] `.agents/skills/` 아래 bootstrap/docgen/eval/ui bridge skill이 존재한다
- [ ] 각 skill이 runtime integration out-of-scope 원칙을 유지한다
- [ ] `mock` provider 테스트 경로를 건드리지 않는다
- [ ] provider/storage/auth/tenant 경계를 유지한다
- [ ] `DESIGN.md`는 정적 셸 작업에만 제한적으로 사용한다

## 추천 파일럿

### 파일럿 1
범위:
- `app/templates/`
- `app/services/`
- 관련 테스트

목표:
- 문서 생성 품질 향상
- 반복적인 포맷/섹션 오류 감소

### 파일럿 2
범위:
- `app/eval/`
- `app/eval_live/`
- 품질 테스트

목표:
- 실패 분류 정확도 향상
- 반복 회귀를 더 빨리 식별

### 파일럿 3
범위:
- `app/static/`
- `DESIGN.md`

목표:
- 정적 UX 품질 개선
- 제품 톤 정리

## 결론
DecisionDoc AI에는 OpenSpace를 "자율 문서 생성 서비스 엔진"으로 넣는 것이 아니라, "이 repo를 다루는 에이전트의 반복 작업 학습 계층"으로 넣는 것이 맞다.

가장 높은 ROI는:
- 템플릿/프롬프트/평가/운영 문서 루프

가장 낮은 ROI 또는 금지에 가까운 영역은:
- 핵심 요청 처리 런타임과 보안/테넌시 경계

## Smoke 검증

현재 repo release contract에서 required한 OpenSpace 검증은 repo-local skill 존재와 문서 정합성까지다.

선택적 host integration smoke가 필요하더라도 현재 repo는 별도 smoke 스크립트를 유지하지 않는다. 이 검증은 host-side credential/session 조건에 크게 의존하므로, release gate 해석은 다음 순서를 따른다.
- repo-local skill files 존재
- skill docs가 current procurement / Decision Council / eval boundaries와 맞는지
- optional host integration smoke는 참고 증거로만 사용

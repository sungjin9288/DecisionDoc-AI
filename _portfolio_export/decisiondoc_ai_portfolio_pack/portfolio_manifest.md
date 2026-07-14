# Portfolio Package Manifest

## 프로젝트 정보

- 프로젝트명: DecisionDoc AI
- 기준일: 2026-07-14
- 현재 상태: AI-assisted documentation PoC/MVP 고도화, 외부 실증 보류
- 핵심 기술스택: Python 3.12, FastAPI, Pydantic v2, Jinja2, provider/storage abstraction, Docker Compose, AWS SAM/Lambda, pytest
- 이력서 반영 가능 여부: 조건부 가능

## 패키지 원칙

`_portfolio_export/decisiondoc_ai_portfolio_pack/`은 저장소의 tracked 문서와 local evidence를 그대로 복제한 검토용 패키지다. `scripts/manage_portfolio_pack.py`가 source allowlist, pack membership, 파일 내용, SHA-256 manifest를 함께 검증한다.

포함 범위:

- README, DEV_LOG, 링크, 제품 방향과 실행 계획
- architecture, case study, contribution note, project card, resume bullets, interview story, roadmap
- local API, UI, architecture, execution, generated document evidence
- 각 파일의 path, size, SHA-256을 기록한 `portfolio_manifest.json`

제외 범위:

- `.env`, API key, token, password, credential
- `app/`, `tests/` 등 application source code
- 고객사·기관 내부자료와 개인정보
- dependency, build, cache, git metadata
- provider API, G2B live API, AWS runtime 실행 결과

## 재현 명령

```bash
python3 scripts/manage_portfolio_pack.py sync --prune
python3 scripts/manage_portfolio_pack.py check
python3 scripts/manage_portfolio_pack.py package
python3 scripts/manage_portfolio_pack.py verify-zip
```

- `sync --prune`: tracked allowlist를 pack에 atomic copy하고 오래된 파일을 제거한다.
- `check`: source와 pack의 membership, byte content, JSON manifest가 같은지 확인한다.
- `package`: 고정 timestamp와 정렬된 entry로 deterministic ZIP을 만든다.
- `verify-zip`: ZIP entry와 pack content가 정확히 같은지 다시 확인한다.

## 산출물 상태

- Tracked pack: `_portfolio_export/decisiondoc_ai_portfolio_pack/`
- Tracked integrity manifest: `_portfolio_export/decisiondoc_ai_portfolio_pack/portfolio_manifest.json`
- Local delivery ZIP: `_portfolio_export/decisiondoc_ai_portfolio_pack.zip`
- ZIP tracking: `.gitignore` 대상. 필요할 때 위 명령으로 생성하며 저장소에는 커밋하지 않는다.
- 외부 실증: 이 package 생성과 검증은 provider, G2B, AWS를 호출하지 않으며 운영 승인이나 입찰 제출을 의미하지 않는다.

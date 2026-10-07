---
name: decisiondoc-authoring
description: Write a DecisionDoc document (proposal, RFP analysis, report, decision doc and other bundles) yourself in this session, then validate, store and export it with the local DecisionDoc server. Use when the user asks to create or draft a document locally with DecisionDoc.
---

# DecisionDoc 로컬 문서 작성

이 세션이 문서 내용을 직접 쓰고, DecisionDoc이 나머지를 처리한다.

- **DecisionDoc이 처리하는 것:** 번들 구조, 문체 예시, 프로젝트 지식, 스키마 검증, 품질 검사, 이력·프로젝트 저장, DOCX/PDF/PPTX/HWPX/XLSX 내보내기
- **서버가 하지 않는 것:** 모델이나 외부 API 호출. 이 경로에서 서버는 아무것도 호출하지 않는다.

## 준비

로컬 서버가 에이전트 키와 함께 실행 중이어야 한다. 없으면 사용자에게 아래 명령으로 띄우도록 요청하거나, 허락을 받고 백그라운드로 실행한다.

```bash
python3 scripts/run_free_local.py --agent-api-key
```

- **기본값:** 주소 `http://127.0.0.1:8000`, 데이터 `./data/free-local`
- **다른 주소:** `--port`, `--data-dir`를 바꿨으면 `DECISIONDOC_URL`과 `DECISIONDOC_AGENT_API_KEY_FILE`(`<data-dir>/.agent-api-key`)을 맞춘다.
- **조달 복수 공고 opt-in:** `--procurement-multi-opportunity`를 쓴다. 기존 조달 데이터가 있는 폴더는 preflight 안내가 나온다.
- 키 파일 내용을 출력하거나 다른 곳에 옮기지 않는다.

## 작성 순서

1. **번들 고르기**
   - `python3 scripts/decisiondoc_author.py bundles`로 번들 id와 문서 키를 본다.
   - 사용자가 원하는 문서 종류에 맞는 번들을 고른다. 확실하지 않으면 묻는다.
2. **지침 받기**
   - 맥락 자료는 파일로 넘긴다(`--context-file`). 프로젝트에 저장하려면 `--project-id`, 저장된 문체를 쓰려면 `--style-profile-id`를 더한다.
   - 조달 공고 판단에 묶어 쓰려면 `--project-id`와 함께 `--procurement-decision-id`, `--procurement-revision`(현재 판단 revision)을 준다. revision이 바뀌었으면 409가 나오므로 최신 revision으로 다시 받는다.

   ```bash
   python3 scripts/decisiondoc_author.py brief --bundle <id> --title "<제목>" --goal "<목표>" \
     --context-file <자료.md> --out work/<문서이름>
   ```

3. **작성**
   - `work/<문서이름>/brief.md`의 생성 프롬프트를 그대로 따라 `work/<문서이름>/bundle.json`을 쓴다.
     - JSON 객체 하나만 쓴다.
     - 최상위 키는 문서 키이고 구조는 `schema.json`을 따른다.
     - 모든 필수 필드를 채운다.
     - 프롬프트에 들어 있는 문체 예시, 프로젝트 지식, 조달 문맥을 반영한다.
4. **제출**

   ```bash
   python3 scripts/decisiondoc_author.py submit --dir work/<문서이름> --formats docx,pptx,hwpx
   ```

   - 종료 코드 2와 `AUTHORED_BUNDLE_INVALID`가 나오면 `errors` 사유대로 `bundle.json`을 고쳐 다시 제출한다.
   - 결과물은 `work/<문서이름>/output/`에 생긴다. 형식별 파일과 문서별 `.md`가 들어 있다.
5. **보고**
   - 만든 파일 경로를 알린다. `--project-id`를 썼다면 `project_document_id`도 알린다.
   - 웹 화면(같은 서버 주소)의 프로젝트·이력에서 열어 편집·검토할 수 있다고 안내한다.

## 작성 규칙

- **수치:** 근거 없는 수치, 일정, 금액, 성과를 만들지 않는다. 맥락에 없는 숫자는 "확인 필요"로 적는다. 프롬프트 끝의 "수치 근거" 규칙이 다른 수치 요구보다 우선한다.
  - 짧은 맥락에서 근거 없는 수치를 쓰면 품질 보정 단계가 그 필드를 일반 문장으로 바꿀 수 있다.
- **문체 예시:** 문체 예시는 prompt 참고 자료이며 모델 학습이 아니다. 예시 문장을 그대로 베끼지 말고 어조만 따른다.
- **승인 표현:** 검토 완료, 결재, 제출 승인을 문서에서 이미 된 일처럼 쓰지 않는다.
- **자료 보안:** 사용자 자료 중 비밀번호, 개인정보, 고객 원본처럼 민감한 것은 `bundle.json`에 옮기지 않는다.
- **서버 호출 금지:** 서버의 `/generate`, `/generate/stream`을 호출하지 않는다. 그 경로는 서버 쪽 provider를 쓴다.

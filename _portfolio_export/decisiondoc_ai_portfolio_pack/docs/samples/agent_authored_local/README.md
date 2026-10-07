# 세션 작성 실증 샘플

로컬 세션 작성 경로를 다시 확인하는 데 쓰는 입력과 작성 결과다. 모두 합성 데이터이며 실제 기관·사업과 무관하다.

| 파일 | 내용 |
|---|---|
| `input.json` | 작성 요청: 제목, 목표, 번들(`proposal_kr`), 합성 RFP 맥락 |
| `bundle.json` | Claude Code 세션이 `.claude/skills/decisiondoc-authoring/SKILL.md` 절차로 받은 지침에 따라 직접 쓴 4개 문서 내용(2026-10-07) |

다시 제출해 증거를 갱신하는 명령은 아래와 같다. 임시 데이터 폴더의 앱을 쓰며 provider와 외부 서비스를 호출하지 않는다.

```bash
python3 scripts/capture_agent_authored_evidence.py
python3 scripts/capture_agent_authored_evidence.py --check-only
```

결과는 `evidence/cli-logs/agent_authored_evidence.json`, `evidence/generated-samples/agent-authored/`, `evidence/screenshots/agent-authored-*.png`에 쓴다. 형식별 파일(DOCX·PDF·PPTX·HWPX·XLSX)은 임시 폴더에만 만들고 저장소에 넣지 않는다.

`bundle.json`은 작성 당시의 지침으로 쓴 결과다. 이후 지침이 바뀌어도 이 파일을 다시 쓰지 않으며, 재제출은 현재 서버가 같은 작성 결과를 어떻게 처리하는지를 보여 준다.

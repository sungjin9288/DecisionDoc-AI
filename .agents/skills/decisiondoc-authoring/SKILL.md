---
name: decisiondoc-authoring
description: Write a DecisionDoc document (proposal, RFP analysis, report, decision doc and other bundles) yourself in this session, then validate, store and export it with the local DecisionDoc server. Use when the user asks to create or draft a document locally with DecisionDoc.
---

# DecisionDoc 로컬 문서 작성 (Codex)

절차와 규칙은 Claude Code와 같다. `.claude/skills/decisiondoc-authoring/SKILL.md`를 읽고 그대로 따른다.

- 세션이 `bundle.json`을 직접 쓰고 `scripts/decisiondoc_author.py`의 `brief` → `submit`으로 처리한다.
- 서버의 `/generate`, `/generate/stream`은 호출하지 않는다.

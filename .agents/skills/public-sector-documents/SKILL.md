---
name: public-sector-documents
description: Check a Korean public-sector proposal or report (공공기관·공기업·지자체·국책과업) against its RFP and official rules — requirement trace table (요구사항 대비표), evaluation cross-reference table (조견표) with PDF pages, and unknown RFP conditions. Use when the user works on a 제안서, 사업수행계획서 or project report for a public agency, or gives an RFP/제안요청서/과업지시서.
---

# 공공 과업 문서 검사 (Codex)

절차와 규칙은 Claude Code와 같다. `.claude/skills/public-sector-documents/SKILL.md`를 읽고 그대로 따른다.

- `scripts/publicdoc.py`의 `text` → `scan-requirements` → RFP 조건 카드 작성 → `check-profile` → `trace` → `crosswalk --pdf` 순서이고, 공공 표기는 `notation`, 보고서는 `report-skeleton`·`report-check`, 제출 전에는 `submission`으로 검사한다.
- 서버, provider, 외부 서비스는 쓰지 않는다.

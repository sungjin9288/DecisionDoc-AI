# Phase 42 Production Browser UAT Evidence

Status: `PRODUCTION_BROWSER_UAT_PASSED_WITH_DOWNLOAD_RUNTIME_LIMITATION_NO_TRAINING_AUTHORIZATION`

Created at: `2026-05-13T09:34:16+09:00`

## Purpose

Phase 42 records production browser-level UAT after Phase 41 backend post-deploy smoke passed.

This phase used the Codex in-app browser against `https://admin.decisiondoc.kr` to verify that the admin UI can run the document-generation flow, render the generated result controls, expose PDF/PPTX/HWP download actions without console errors, and show the step-based Report Workflow approval UX.

Codex in-app browser does not support native download events, so OS-level file-save and file-open verification remains a manual Chrome/Safari follow-up. To reduce that gap, Phase 42 also ran backend export integrity checks against the production export endpoint and verified PDF, PPTX, and HWP/HWPX response structures.

This phase did not authorize or start model training, external dataset upload, provider fine-tune API calls, provider job creation/polling, model candidate emission, or model promotion.

## Browser Runtime

- Target: `https://admin.decisiondoc.kr`
- Browser runtime: Codex in-app browser
- Observed session: `안성진 · PM`
- Page title: `DecisionDoc AI — AI 문서 생성기`
- Download runtime limitation: `Downloads are not supported by Codex In-app Browser.`

## Document Generation UI UAT

| Check | Result |
|---|---|
| Production admin page loaded | `passed` |
| Existing PM session visible | `passed` |
| Synthetic input present | `passed` |
| `AI 사업 제안서 문서 생성하기` clicked | `passed` |
| Document sketch rendered | `passed` |
| `이 구성으로 생성하기` clicked | `passed` |
| Generated result screen rendered | `passed` |
| Result action buttons rendered | `passed` |
| `LLM 생성 (fallback)` metadata rendered | `passed` |
| Individual download controls rendered | `passed` |

Synthetic scenario:

- Title: `HWPX 운영 검증 20260504`
- Goal: `비민감 synthetic 입력으로 HWPX 다운로드 파일 구조를 검증한다`
- Background: `JSON, YAML, HTML 형식의 공개 가능한 synthetic 참고 자료를 첨부해 문서 생성 흐름을 검증한다`
- Constraints: `실제 고객 데이터 없이 synthetic 자료만 사용하고 timeout, 504, 첨부 반영 품질을 확인한다`
- Bundle: `AI 사업 제안서`

## Download Click Checks

| Action | UI click | Console errors | Native download event |
|---|---:|---:|---:|
| Individual PDF | `passed` | `0` | `unsupported by Codex in-app browser` |
| Top-level PPT download | `passed` | `0` | `unsupported by Codex in-app browser` |
| Top-level HWP | `passed` | `0` | `unsupported by Codex in-app browser` |

These checks prove that the production UI controls are reachable and do not throw browser console errors in the Codex runtime. They do not prove that the host OS saved files into `~/Downloads`.

## Backend Export Integrity Complement

The production export endpoint was called with non-sensitive synthetic documents to validate file structure independently of the in-app browser download limitation.

| Format | HTTP | Content type | Size | Integrity |
|---|---:|---|---:|---|
| PDF | `200` | `application/pdf` | `217680` bytes | `%PDF` magic bytes |
| PPTX | `200` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `41501` bytes | ZIP valid, required OOXML entries present |
| HWP/HWPX | `200` | `application/hwp+zip` | `4818` bytes | ZIP valid, required HWPX entries present |

Required entries confirmed:

- PPTX: `[Content_Types].xml`, `ppt/presentation.xml`, `ppt/slides/slide1.xml`
- HWP/HWPX: `mimetype`, `Contents/header.xml`, `Contents/section0.xml`

## Report Workflow UI UAT

| Check | Result |
|---|---|
| `보고서 워크플로우` tab visible | `passed` |
| Step-based workflow page rendered | `passed` |
| Project creation form rendered | `passed` |
| Owner / PM Reviewer / Executive Approver chain rendered | `passed` |
| Planning section rendered | `passed` |
| Slides section rendered | `passed` |
| Final approval section rendered | `passed` |
| Existing smoke workflow selectable | `passed` |
| Final-approved workflow detail rendered | `passed` |
| PPTX export button rendered | `passed` |
| Snapshot export button rendered | `passed` |

Observed workflow:

- Title: `[SMOKE] Report Workflow Blueprint a8a40549`
- Final status: `final_approved`
- Slide approval state: `2/2`
- PM approval: `approved`
- Executive approval: `approved`
- Project document saved: `document=daff8d43-e1b3-4f24-91c4-04564d65ac61`
- Learning opt-in: disabled, so Knowledge promotion is blocked while project save remains available.

## Follow-Ups

- OS-level file-save/open verification remains manual because Codex in-app browser reports native downloads as unsupported.
- The result screen was visible and usable, but the global generation status text remained stale as `AI가 문서를 생성하는 중...` after the result controls rendered. This is a UI polish follow-up, not a blocking generation/export failure.

## Boundary Statement

Allowed and observed in this phase:

- Production UI document-generation flow
- Normal production generation provider call through the UI
- Production export endpoint responses for PDF, PPTX, and HWP/HWPX
- Report Workflow UI inspection of a previously smoke-created final-approved workflow

Still not allowed and not observed:

- External dataset upload
- Provider fine-tune API calls
- Provider job creation or polling
- Training execution
- Model candidate emission
- Model promotion
- Server-generated reviewer approval records

## Next Step

If release sign-off requires actual local files, complete manual Chrome/Safari download-open verification for PDF, PPTX, and HWP/HWPX outside Codex in-app browser. Otherwise, Phase 42 is sufficient to mark browser UI UAT passed with a documented native-download runtime limitation.

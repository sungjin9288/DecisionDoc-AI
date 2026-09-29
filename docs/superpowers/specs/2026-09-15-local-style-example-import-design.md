# Local Style Example Import

Status: approved by the repository operator; implemented and locally verified.

## Observed Gap

The existing `/styles/{profile_id}/analyze` route requires structured LLM style
analysis. On 2026-09-15, calling `analyze_document_style` with a synthetic UTF-8
TXT file and the actual MockProvider returned `ValueError: example.txt: 문체
분석에 실패했습니다.` The mock invocation counter was one; no external provider
was used. MockProvider returns another task's JSON shape for this prompt.

Manual examples already persist and reach the generation style prompt. Adding
fake successful style-analysis output would not make uploaded document reuse
work. Enabling a paid provider would violate the current no-cost scope.

## Selected Approach

Add an explicit local example-import action alongside the existing analysis
capability. It extracts text using the existing attachment parser, selects bounded
verbatim excerpts, and saves ordinary StyleExample records. It must not infer
formality, invent patterns, call a provider, use an AI/OCR fallback, or claim that
model weights changed. Existing provider-backed analysis remains separate.

Alternative: require users to paste every example manually. That is safe and
already available, but does not close the uploaded-document workflow. Replacing
the LLM analyzer globally is also rejected because it would silently change the
meaning of existing provider-backed analysis.

## Contract

- Proposed route: `POST /styles/{profile_id}/import-examples`, using the existing
  tenant style authorization and selected storage backend.
- Accept TXT, MD, DOCX, HWPX and text-layer PDF. Use the non-AI extraction API;
  reject scanned PDFs, images, archives, empty text, unsupported formats and
  malformed input. Never substitute synthetic OCR content.
- Bound each batch to eight files and each file to the existing attachment byte
  cap. Apply the parser's text cap, then select at most eight distinct, nonblank
  excerpts per file, each at most 1,000 characters. Excerpts must be contiguous
  substrings of extracted text; select deterministically in source order. Do not
  summarize or claim semantic completeness of truncated input.
- Recheck the profile in the current tenant before saving. Keep existing examples,
  tone guides and other tenants unchanged. Save no empty examples. A file that
  fails parsing produces a per-file error and does not create its example.
- Return imported entries and per-file failures with `method=local_text` and
  `provider_calls=0`. Existing analysis fields must not be fabricated.
- Use the existing source filename, actor, time, bundle filter and sample sentence
  fields. Keep extracted patterns empty. No profile-schema migration is required.
- UI command: `문서 예문 가져오기`. Show imported and failed counts accurately,
  retain single-flight and stale auth/profile response guards, and do not silently
  retry an uncertain POST. Make imported excerpts inspectable through the existing
  examples list. Manual editing/removal remains the existing workflow.

## Files And Verification

Keep parsing/selection in a focused service module, the multipart route in
`app/routers/styles.py`, and UI wiring beside existing style actions in
`app/static/index.html`. Reuse attachment parsing and StyleStore; add no dependency.

Failure-first tests must cover actual MockProvider-free import, TXT/DOCX/text-PDF
source excerpts, duplicates, truncation, byte/count limits, malformed/scanned
inputs, partial batches, missing/foreign profile, and no tone changes. Provider
factories and AI fallback functions should fail tests if invoked by this route.

Integration proof: import synthetic source text, reload the style profile, select
it, and inspect the generation prompt/cache behavior. Browser E2E must use the
real local API to import and reload; synthetic provider output only proves prompt
plumbing, not actual style quality. Controlled response tests cover repeated
clicks, partial failures and stale auth/profile results.

## Boundaries

No model training, external uploads, provider calls, live AWS/G2B, deployment,
dependency installation, credentials, commit or push. Preserve the current dirty
tree and user server data. Use isolated temporary local/fake-S3 test data.
The associated feature gate records the operator's approval. This does not grant
external effects or complete all planned product capabilities.

## Implementation And Verification

- Added `POST /styles/{profile_id}/import-examples` and the separate local import
  button. The existing provider-backed button is now explicitly `AI 문체 분석`.
- Local extraction saves ordinary examples with empty patterns; existing tone,
  selected-style snapshots, storage CAS and tenant ownership checks are reused.
- Office packages additionally reject more than 1,000 members, expansion beyond
  20 MB, unsafe XML entities and malformed XML before extraction. The shared
  HWPX extractor now uses its existing safe XML parser instead of a prefix-specific
  regex, preserving namespace-qualified text and XML escapes.
- The missing endpoint was reproduced as HTTP 404 before implementation. Invalid
  bundle identity and malformed/package input tests also failed before correction.
  A namespace-qualified HWPX fixture failed before the parser correction.
- `python3 -m pytest -q tests/test_local_style_example_import.py
  tests/test_local_style_import_ui.py tests/test_manual_style_ui.py
  tests/test_generation_style_selection.py tests/test_style_system.py
  tests/test_style_store_integrity.py tests/test_attachments.py --tb=short
  --show-capture=no`: **178 passed**, one existing Starlette/httpx deprecation
  warning, 25.35 seconds. Covers local/fake-S3 import, actual TXT/MD/DOCX/HWPX/PDF
  parsers, batch and byte bounds, blank/invalid inputs, source excerpt order,
  unchanged tone, foreign profile rejection, generation prompt/snapshot changes,
  single-flight and stale auth/profile browser responses.
- `python3 -m pytest -q -p pytest_playwright.pytest_playwright
  tests/e2e/test_local_style_import.py tests/e2e/test_main_flow.py
  -k 'local_style_import_reload or manual_style_generation_and_edited_docx_download'
  --browser chromium --tb=short --show-capture=no`: **5 passed, 113 deselected**,
  15.64 seconds. Real local API import/reload and manual style/export regressions;
  desktop/mobile checks included screenshots, no horizontal overflow/page errors.
- Tests ran with dotenv disabled, a temporary HOME/data root, mock provider,
  local storage and no external calls. PDF tests needed the already bundled
  `pdfplumber` dependencies on PYTHONPATH; no package was installed. API/UI tests
  used Python 3.12 and the existing Chromium browser cache.
- Targeted Ruff E/F/W (excluding E501), approved feature-gate validation and
  `git diff --check` passed. Full repository tests and human UAT were not run.

## Remaining Limits

This is bounded verbatim excerpt reuse, not semantic style inference or model
training. Long documents are truncated; examples are inspectable/removable but
not semantically ranked. Image-only PDFs require text extraction elsewhere and
are rejected without OCR. A lost POST response requires checking the saved list;
there is no automatic retry or cross-request deduplication. Model output style
quality is not proved by mock prompt verification.

## Style Deletion Follow-Up

The existing profile and bundle-override delete UI did not check HTTP success.
A controlled HTTP 503 reproduced a false profile-deletion success and list
refresh. Example deletion also lacked request/view ownership protection.

The three existing delete actions now share an HTTP-checked, single-flight
handler. Failures retain the current view; late responses after auth changes,
profile navigation or detail re-render do not change the new view. Delete buttons
are disabled while pending and restored afterward. The subsequent profile-list
refresh also checks the captured auth and detail view before rendering. No API,
permission or storage contract changed, and no automatic DELETE retry was added.

- `python3 -m pytest -q tests/test_style_delete_ui.py
  tests/test_local_style_import_ui.py tests/test_manual_style_ui.py --tb=short
  --show-capture=no`: **48 passed**, 30.50 seconds. Controlled HTTP/network failure,
  success, double invocation, auth/profile transitions and late list responses.
- `python3 -m pytest -q -p pytest_playwright.pytest_playwright
  tests/e2e/test_local_style_import.py --browser chromium --tb=short
  --show-capture=no`: **2 passed**, 4.63 seconds. Real local desktop/mobile import,
  reload, example deletion, profile deletion and reload persistence. Only isolated
  synthetic test records were deleted; user data was not touched.
- Targeted Ruff E/F/W (excluding E501) and `git diff --check` passed. The user
  server remained at `http://127.0.0.1:8788/`; health reported mock/free mode.
- The `decisiondoc-openspace-ui` skill was used to keep the correction within the
  existing static UI behavior. No layout redesign or new feature admission.

Full repository tests and human UAT remain separate; these checks do not prove
completion of all planned product functionality.

## Default Selection And Detail Read Follow-Up

Controlled browser tests reproduced duplicate default-setting POSTs and stale
detail responses reopening a previous profile. Ten new regression cases failed
before the correction. Default-setting now disables its submitting control and
checks the captured auth/profile/view before reporting success or refreshing.
Detail reads require the latest request, unchanged auth/view, and the requested
profile identity; out-of-order or mismatched responses cannot replace the view.
Existing backend authorization, default-selection semantics and cache contracts
were not changed.

- `python3 -m pytest -q tests/test_style_default_ui.py
  tests/test_style_delete_ui.py tests/test_manual_style_ui.py
  tests/test_local_style_import_ui.py tests/test_generation_style_selection.py
  --tb=short --show-capture=no`: **73 passed**, one existing Starlette/httpx
  deprecation warning, 32.44 seconds. Includes immutable style snapshot and
  default-change cache regressions as well as controlled browser responses.
- `python3 -m pytest -q -p pytest_playwright.pytest_playwright
  tests/e2e/test_local_style_import.py --browser chromium --tb=short
  --show-capture=no`: **4 passed**, 6.65 seconds. Desktop/mobile local import,
  deletion and default-setting/reload/generation-selector badge persistence.
- Targeted Ruff E/F/W (excluding E501) and `git diff --check` passed. Only
  isolated mock/local test records were mutated; user data, external effects,
  deployment and commit/push remain untouched.

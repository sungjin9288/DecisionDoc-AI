"""Static reviewer summary for a finished-document human review receipt."""
from __future__ import annotations

import html
from typing import Any, Mapping
from urllib.parse import quote

from app.eval.human_review_receipt import DRAFT_SCHEMA_VERSION, DRAFT_SCOPE


STATUS_LABELS = {
    "pending": "검토 대기",
    "completed": "검토 완료",
    "needs_revision": "수정 필요",
    "not_reviewed": "미검토",
    "passed": "통과",
    "accepted": "수락",
    "not_authorized": "승인 안 됨",
    "authorized": "승인됨",
}


REVIEW_DRAFT_SCRIPT = """<script>
(() => {
  const workspace = document.querySelector("[data-review-workspace]");
  const downloadButton = document.querySelector("[data-download-review-draft]");
  const message = document.querySelector("[data-review-draft-message]");
  if (!workspace || !downloadButton || !message) return;

  const readField = (group, name) => group.querySelector(`[name="${name}"]`).value.trim();
  const reviewGroups = Array.from(document.querySelectorAll("[data-review-form]"));

  function reviewValues(group) {
    return {
      factual_grounding: readField(group, "factual_grounding"),
      visual_review: readField(group, "visual_review"),
      reviewer: readField(group, "reviewer"),
      notes: readField(group, "notes"),
    };
  }

  reviewGroups.forEach(group => {
    group.dataset.initialReview = JSON.stringify(reviewValues(group));
  });

  function readReview(group) {
    const review = reviewValues(group);
    const values = Object.values(review);
    if (values.every(value => !value)) return null;
    if (JSON.stringify(review) === group.dataset.initialReview) return null;
    if (values.some(value => !value)) {
      const missingField = Object.entries(review).find(([, value]) => !value)[0];
      group.querySelector(`[name="${missingField}"]`).focus();
      throw new Error(`${group.dataset.bundle}: 검토 항목을 모두 입력해야 합니다.`);
    }
    return review;
  }

  downloadButton.addEventListener("click", () => {
    try {
      const reviews = Object.create(null);
      reviewGroups.forEach(group => {
        const review = readReview(group);
        if (review) reviews[group.dataset.bundle] = review;
      });
      if (!Object.keys(reviews).length) {
        throw new Error("저장할 검토 기록이 없습니다.");
      }

      const externalActions = Object.create(null);
      document.querySelectorAll("[data-external-action]").forEach(row => {
        externalActions[row.dataset.externalAction] = false;
      });
      const draft = {
        schema_version: workspace.dataset.draftSchemaVersion,
        scope: workspace.dataset.draftScope,
        created_at: new Date().toISOString(),
        source: {
          receipt_path: workspace.dataset.receiptPath,
          receipt_sha256: workspace.dataset.receiptSha256,
          manifest_path: "manifest.json",
          manifest_sha256: workspace.dataset.manifestSha256,
        },
        reviews,
        external_actions_authorized: externalActions,
      };

      const blob = new Blob([`${JSON.stringify(draft, null, 2)}\n`], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "human_review_draft.json";
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
      message.dataset.tone = "pass";
      message.textContent = `${Object.keys(reviews).length}개 bundle 검토 draft를 생성했습니다.`;
    } catch (error) {
      message.dataset.tone = "fail";
      message.textContent = error instanceof Error ? error.message : String(error);
    }
  });
})();
</script>"""


def _label(value: Any) -> str:
    text = str(value or "")
    return STATUS_LABELS.get(text, text or "기록 없음")


def _tone(value: Any) -> str:
    if value in {"completed", "passed", "accepted"}:
        return "pass"
    if value in {"needs_revision", "authorized"}:
        return "fail"
    return "pending"


def _status(value: Any) -> str:
    return (
        f'<span class="status status-{_tone(value)}">'
        f"{html.escape(_label(value))}"
        "</span>"
    )


def _href(path: str) -> str:
    return html.escape(quote(path, safe="/._-"))


def _request_rows(request: Any) -> str:
    request = request if isinstance(request, Mapping) else {}
    fields = (
        ("goal", "목표"),
        ("context", "입력 근거"),
        ("constraints", "제약 조건"),
        ("audience", "검토 대상"),
    )
    return "".join(
        f"<dt>{label}</dt><dd>{html.escape(str(request.get(field) or '기록 없음'))}</dd>"
        for field, label in fields
    )


def _quality_rows(quality: Any) -> str:
    quality = quality if isinstance(quality, Mapping) else {}
    numeric_review = quality.get("numeric_grounding_review")
    numeric_review = numeric_review if isinstance(numeric_review, Mapping) else {}
    checks = (
        ("Schema validator", "passed" if quality.get("validator_pass") else "needs_revision"),
        ("Bundle lint", "passed" if quality.get("lint_pass") else "needs_revision"),
        ("수치 근거", numeric_review.get("status") or "pending"),
    )
    return "".join(
        f"<div><dt>{label}</dt><dd>{_status(status)}</dd></div>"
        for label, status in checks
    )


def _document_rows(
    bundle: Mapping[str, Any],
    documents: Mapping[str, str],
) -> str:
    markdown_files = bundle.get("markdown_docs")
    if not isinstance(markdown_files, Mapping):
        return ""

    rows: list[str] = []
    for index, (document_type, path) in enumerate(markdown_files.items()):
        markdown = documents.get(str(document_type), "")
        open_attribute = " open" if index == 0 else ""
        rows.append(
            f"<details class='document'{open_attribute}>"
            "<summary>"
            f"<strong>{html.escape(str(document_type))}</strong>"
            f"<span>{len(markdown.splitlines())} lines</span>"
            "</summary>"
            "<div class='document-body'>"
            f"<a class='file-link' href='{_href(str(path))}'>Markdown 원문</a>"
            f"<pre>{html.escape(markdown)}</pre>"
            "</div>"
            "</details>"
        )
    return "".join(rows)


def _review_state_options(selected_value: Any) -> str:
    selected = str(selected_value or "")
    if selected == "not_reviewed":
        selected = ""
    options = (("", "선택"), ("passed", "통과"), ("needs_revision", "수정 필요"))
    return "".join(
        f'<option value="{value}"{" selected" if value == selected else ""}>{label}</option>'
        for value, label in options
    )


def _review_input(bundle_type: str, review: Mapping[str, Any]) -> str:
    reviewer = html.escape(str(review.get("reviewer") or ""), quote=True)
    notes = html.escape(str(review.get("notes") or ""))
    return (
        f'<fieldset class="review-entry" data-review-form data-bundle="{html.escape(bundle_type, quote=True)}">'
        "<legend>검토 기록 작성</legend>"
        '<div class="review-fields">'
        '<label><span>사실 근거</span><select name="factual_grounding">'
        f'{_review_state_options(review.get("factual_grounding"))}</select></label>'
        '<label><span>시각 검토</span><select name="visual_review">'
        f'{_review_state_options(review.get("visual_review"))}</select></label>'
        f'<label><span>검토자</span><input name="reviewer" value="{reviewer}" autocomplete="name"></label>'
        f'<label class="review-notes"><span>검토 메모</span><textarea name="notes" rows="3">{notes}</textarea></label>'
        "</div>"
        "</fieldset>"
    )


def _bundle_review_rows(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    bundle_documents: Mapping[str, Mapping[str, str]],
) -> str:
    manifest_bundles = manifest.get("bundles")
    bundle_reviews = receipt.get("bundle_reviews")
    if not isinstance(manifest_bundles, Mapping) or not isinstance(bundle_reviews, Mapping):
        return ""

    rows: list[str] = []
    for bundle_type, review_value in bundle_reviews.items():
        review = review_value if isinstance(review_value, Mapping) else {}
        bundle_value = manifest_bundles.get(bundle_type)
        bundle = bundle_value if isinstance(bundle_value, Mapping) else {}
        title = str(bundle.get("title") or bundle_type)
        reviewer = str(review.get("reviewer") or "미지정")
        reviewed_at = str(review.get("reviewed_at") or "미검토")
        notes = str(review.get("notes") or "기록 없음")
        documents = bundle_documents.get(str(bundle_type), {})
        rows.append(
            "<section class='review-row'>"
            "<header class='review-row-header'>"
            "<div>"
            f"<p class='bundle-id'>{html.escape(str(bundle_type))}</p>"
            f"<h2>{html.escape(title)}</h2>"
            "</div>"
            f"{_status(review.get('decision'))}"
            "</header>"
            "<div class='review-context'>"
            "<section class='context-section'>"
            "<h3>요청 근거</h3>"
            f"<dl class='request-data'>{_request_rows(bundle.get('request'))}</dl>"
            "</section>"
            "<section class='context-section'>"
            "<h3>자동 검증</h3>"
            f"<dl class='check-list'>{_quality_rows(bundle.get('quality'))}</dl>"
            "</section>"
            "</div>"
            "<dl class='review-states'>"
            "<div><dt>사실 근거</dt>"
            f"<dd>{_status(review.get('factual_grounding'))}</dd></div>"
            "<div><dt>시각 검토</dt>"
            f"<dd>{_status(review.get('visual_review'))}</dd></div>"
            "<div><dt>검토자</dt>"
            f"<dd>{html.escape(reviewer)}</dd></div>"
            "<div><dt>검토 시각</dt>"
            f"<dd>{html.escape(reviewed_at)}</dd></div>"
            "</dl>"
            "<div class='notes'>"
            "<h3>검토 메모</h3>"
            f"<p>{html.escape(notes)}</p>"
            "</div>"
            f"{_review_input(str(bundle_type), review)}"
            "<section class='documents'>"
            "<h3>생성 문서</h3>"
            f"{_document_rows(bundle, documents)}"
            "</section>"
            "</section>"
        )
    return "".join(rows)


def _external_action_rows(receipt: Mapping[str, Any]) -> str:
    actions = receipt.get("external_actions_authorized")
    if not isinstance(actions, Mapping):
        return ""
    return "".join(
        f'<li data-external-action="{html.escape(str(action), quote=True)}">'
        f"<code>{html.escape(str(action))}</code>"
        f"{_status('authorized' if authorized else 'not_authorized')}"
        "</li>"
        for action, authorized in actions.items()
    )


def build_human_review_summary(
    *,
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    validation: Mapping[str, Any],
    receipt_sha256: str,
    bundle_documents: Mapping[str, Mapping[str, str]] | None = None,
    receipt_path: str = "human_review_receipt.json",
    review_dashboard_path: str = "review.html",
) -> str:
    """Render a local reviewer workspace from a validated review receipt."""
    receipt_status = receipt.get("status")
    valid = validation.get("ok") is True
    overall_status = receipt_status if valid else "needs_revision"
    evidence = receipt.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    bundle_documents = bundle_documents or {}
    manifest_sha256 = str(evidence.get("manifest_sha256") or "")

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>문서 검토 작업공간</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f5f6;
      --surface: #ffffff;
      --surface-muted: #f7f9f9;
      --border: #d6dddf;
      --border-strong: #aebabc;
      --text: #182326;
      --muted: #5b696d;
      --accent: #0f766e;
      --accent-strong: #0b5e58;
      --pass-bg: #e9f6ef;
      --pass-text: #166534;
      --pending-bg: #fff4d6;
      --pending-text: #8a4b08;
      --fail-bg: #feecec;
      --fail-text: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Pretendard, SUIT, -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", sans-serif;
      letter-spacing: 0;
    }}
    .shell {{ width: min(1080px, calc(100vw - 40px)); margin: 0 auto 64px; }}
    .page-header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
      padding: 38px 0 24px;
      border-bottom: 1px solid var(--border-strong);
    }}
    .eyebrow {{ margin: 0 0 7px; color: var(--accent-strong); font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; line-height: 1.25; }}
    h2 {{ margin: 0; font-size: 20px; line-height: 1.4; }}
    h3 {{ margin: 0 0 8px; font-size: 13px; }}
    p {{ line-height: 1.6; }}
    .page-header p:not(.eyebrow) {{ margin: 0; color: var(--muted); }}
    .header-actions {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }}
    .file-link {{ color: var(--accent-strong); font-size: 13px; font-weight: 700; text-decoration: none; }}
    .file-link:hover {{ text-decoration: underline; }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .status-pass {{ background: var(--pass-bg); color: var(--pass-text); }}
    .status-pending {{ background: var(--pending-bg); color: var(--pending-text); }}
    .status-fail {{ background: var(--fail-bg); color: var(--fail-text); }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-bottom: 1px solid var(--border-strong); }}
    .metric {{ padding: 18px 20px; border-right: 1px solid var(--border); }}
    .metric:first-child {{ padding-left: 0; }}
    .metric:last-child {{ border-right: 0; }}
    .metric span {{ display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; }}
    .metric strong {{ font-size: 20px; }}
    .evidence {{ padding: 22px 0; border-bottom: 1px solid var(--border-strong); }}
    .evidence dl {{ display: grid; grid-template-columns: 150px 1fr; margin: 0; }}
    .evidence dt, .evidence dd {{ margin: 0; padding: 9px 0; border-bottom: 1px solid var(--border); }}
    .evidence dt {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .evidence dd {{ min-width: 0; font-size: 13px; overflow-wrap: anywhere; }}
    code {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 12px; }}
    .review-row {{ padding: 28px 0; border-bottom: 1px solid var(--border-strong); }}
    .review-row-header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }}
    .bundle-id {{ margin: 0 0 5px; color: var(--accent-strong); font-size: 12px; font-weight: 800; }}
    .review-context {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px; margin-top: 22px; }}
    .context-section {{ min-width: 0; }}
    .request-data {{ display: grid; grid-template-columns: 92px 1fr; margin: 0; border-top: 1px solid var(--border); }}
    .request-data dt, .request-data dd {{ margin: 0; padding: 9px 0; border-bottom: 1px solid var(--border); line-height: 1.55; }}
    .request-data dt {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .request-data dd {{ font-size: 13px; }}
    .check-list {{ margin: 0; border-top: 1px solid var(--border); }}
    .check-list > div {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; min-height: 46px; border-bottom: 1px solid var(--border); }}
    .check-list dt {{ color: var(--muted); font-size: 13px; }}
    .check-list dd {{ margin: 0; }}
    .review-states {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 20px 0 0; border-top: 1px solid var(--border); }}
    .review-states > div {{ min-width: 0; padding: 12px 16px; border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
    .review-states > div:first-child {{ padding-left: 0; }}
    .review-states > div:last-child {{ border-right: 0; }}
    .review-states dt {{ margin-bottom: 7px; color: var(--muted); font-size: 12px; font-weight: 700; }}
    .review-states dd {{ margin: 0; min-height: 28px; font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }}
    .notes {{ padding: 16px 0 0; }}
    .notes p {{ margin: 0; padding: 13px 15px; border-left: 3px solid var(--border-strong); background: var(--surface-muted); font-size: 13px; white-space: pre-wrap; }}
    .review-entry {{ margin: 22px 0 0; padding: 18px 0 0; border: 0; border-top: 1px solid var(--border); }}
    .review-entry legend {{ padding: 0; font-size: 13px; font-weight: 800; }}
    .review-fields {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 12px; }}
    .review-fields label {{ display: grid; gap: 6px; min-width: 0; }}
    .review-fields label span {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .review-fields select, .review-fields input, .review-fields textarea {{ width: 100%; min-height: 42px; padding: 9px 10px; border: 1px solid var(--border-strong); border-radius: 5px; background: var(--surface); color: var(--text); font: inherit; font-size: 13px; }}
    .review-fields textarea {{ resize: vertical; line-height: 1.55; }}
    .review-fields select:focus, .review-fields input:focus, .review-fields textarea:focus {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .review-notes {{ grid-column: 1 / -1; }}
    .documents {{ margin-top: 24px; }}
    .document {{ border-top: 1px solid var(--border); background: var(--surface); }}
    .document:last-child {{ border-bottom: 1px solid var(--border); }}
    .document summary {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; min-height: 48px; padding: 10px 12px; cursor: pointer; list-style: none; }}
    .document summary::-webkit-details-marker {{ display: none; }}
    .document summary::after {{ content: "+"; color: var(--accent-strong); font-size: 18px; font-weight: 700; }}
    .document[open] summary::after {{ content: "−"; }}
    .document summary strong {{ flex: 1; }}
    .document summary span {{ color: var(--muted); font-size: 12px; }}
    .document-body {{ padding: 0 12px 14px; }}
    pre {{ max-height: 520px; overflow: auto; margin: 10px 0 0; padding: 16px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-muted); color: #243236; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 12px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .boundary {{ padding: 28px 0; }}
    .boundary h2 {{ margin-bottom: 14px; }}
    .boundary ul {{ margin: 0; padding: 0; border-top: 1px solid var(--border); list-style: none; }}
    .boundary li {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; min-height: 48px; border-bottom: 1px solid var(--border); }}
    .draft-actions {{ display: flex; justify-content: space-between; gap: 20px; align-items: center; padding: 24px 0; border-bottom: 1px solid var(--border-strong); }}
    .draft-actions h2 {{ font-size: 16px; }}
    .draft-actions p {{ min-height: 20px; margin: 5px 0 0; color: var(--muted); font-size: 13px; }}
    .draft-actions p[data-tone="pass"] {{ color: var(--pass-text); }}
    .draft-actions p[data-tone="fail"] {{ color: var(--fail-text); }}
    .primary-action {{ min-height: 42px; padding: 9px 14px; border: 1px solid var(--accent); border-radius: 5px; background: var(--accent); color: #fff; font: inherit; font-size: 13px; font-weight: 800; cursor: pointer; white-space: nowrap; }}
    .primary-action:hover {{ background: var(--accent-strong); }}
    .primary-action:focus-visible {{ outline: 2px solid var(--accent-strong); outline-offset: 3px; }}
    @media (max-width: 780px) {{
      .summary, .review-states {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric:nth-child(2), .review-states > div:nth-child(2) {{ border-right: 0; }}
      .metric:nth-child(-n+2) {{ border-bottom: 1px solid var(--border); }}
      .review-states > div:nth-child(3) {{ padding-left: 0; }}
      .review-context {{ grid-template-columns: 1fr; }}
      .review-fields {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 560px) {{
      .shell {{ width: min(100vw - 24px, 1080px); }}
      .page-header, .review-row-header {{ flex-direction: column; }}
      .page-header {{ padding-top: 24px; }}
      h1 {{ font-size: 25px; }}
      .header-actions {{ justify-content: flex-start; }}
      .metric {{ padding: 14px 10px; }}
      .metric:first-child {{ padding-left: 10px; }}
      .evidence dl {{ grid-template-columns: 1fr; }}
      .evidence dt {{ padding-bottom: 0; border-bottom: 0; }}
      .evidence dd {{ padding-top: 4px; }}
      .request-data {{ grid-template-columns: 1fr; }}
      .request-data dt {{ padding-bottom: 0; border-bottom: 0; }}
      .request-data dd {{ padding-top: 4px; }}
      .boundary li {{ align-items: flex-start; padding: 10px 0; }}
      .review-fields {{ grid-template-columns: 1fr; }}
      .review-notes {{ grid-column: auto; }}
      .draft-actions {{ align-items: stretch; flex-direction: column; }}
      .primary-action {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main class="shell" data-review-workspace
        data-draft-schema-version="{html.escape(DRAFT_SCHEMA_VERSION, quote=True)}"
        data-draft-scope="{html.escape(DRAFT_SCOPE, quote=True)}"
        data-receipt-path="{html.escape(receipt_path, quote=True)}"
        data-receipt-sha256="{html.escape(receipt_sha256, quote=True)}"
        data-manifest-sha256="{html.escape(manifest_sha256, quote=True)}">
    <header class="page-header">
      <div>
        <p class="eyebrow">Manifest-bound review workspace</p>
        <h1>문서 검토 작업공간</h1>
        <p>최근 기록 {html.escape(str(receipt.get('updated_at') or '기록 없음'))}</p>
      </div>
      <div class="header-actions">
        <a class="file-link" href="{_href(review_dashboard_path)}">자동 검증 원본</a>
        <a class="file-link" href="{_href(receipt_path)}">Receipt JSON</a>
        {_status(overall_status)}
      </div>
    </header>
    <section class="summary" aria-label="통합 검토 요약">
      <div class="metric"><span>Bundle</span><strong>{validation.get('bundle_count', 0)}</strong></div>
      <div class="metric"><span>검토 기록</span><strong>{validation.get('reviewed_count', 0)}</strong></div>
      <div class="metric"><span>수락</span><strong>{validation.get('accepted_count', 0)}</strong></div>
      <div class="metric"><span>Receipt 검증</span><strong>{'통과' if valid else '실패'}</strong></div>
    </section>
    <section class="evidence">
      <h2>증적 결속</h2>
      <dl>
        <dt>Manifest</dt><dd><a class="file-link" href="manifest.json">{html.escape(str(evidence.get('manifest_path') or 'manifest.json'))}</a></dd>
        <dt>Manifest SHA256</dt><dd><code>{html.escape(str(evidence.get('manifest_sha256') or '기록 없음'))}</code></dd>
        <dt>Receipt SHA256</dt><dd><code>{html.escape(receipt_sha256)}</code></dd>
        <dt>Schema</dt><dd><code>{html.escape(str(evidence.get('manifest_schema_version') or '기록 없음'))}</code></dd>
        <dt>생성 시각</dt><dd>{html.escape(str(evidence.get('manifest_generated_at') or '기록 없음'))}</dd>
      </dl>
    </section>
    {_bundle_review_rows(manifest, receipt, bundle_documents)}
    <section class="draft-actions">
      <div>
        <h2>검토 Draft</h2>
        <p data-review-draft-message role="status" aria-live="polite"></p>
      </div>
      <button class="primary-action" type="button" data-download-review-draft>Review draft 다운로드</button>
    </section>
    <section class="boundary">
      <h2>외부 실행 권한</h2>
      <ul>{_external_action_rows(receipt)}</ul>
    </section>
  </main>
  {REVIEW_DRAFT_SCRIPT}
</body>
</html>"""

"""Static reviewer summary for a finished-document human review receipt."""
from __future__ import annotations

import html
from typing import Any, Mapping
from urllib.parse import quote


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


def _bundle_review_rows(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
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
        rows.append(
            "<section class='review-row'>"
            "<header class='review-row-header'>"
            "<div>"
            f"<p class='bundle-id'>{html.escape(str(bundle_type))}</p>"
            f"<h2>{html.escape(title)}</h2>"
            "</div>"
            f"{_status(review.get('decision'))}"
            "</header>"
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
            "</section>"
        )
    return "".join(rows)


def _external_action_rows(receipt: Mapping[str, Any]) -> str:
    actions = receipt.get("external_actions_authorized")
    if not isinstance(actions, Mapping):
        return ""
    return "".join(
        "<li>"
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
    receipt_path: str = "human_review_receipt.json",
    review_dashboard_path: str = "review.html",
) -> str:
    """Render a read-only HTML summary from a validated review receipt."""
    receipt_status = receipt.get("status")
    valid = validation.get("ok") is True
    overall_status = receipt_status if valid else "needs_revision"
    evidence = receipt.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>사람 검토 기록</title>
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
    .review-states {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 20px 0 0; border-top: 1px solid var(--border); }}
    .review-states > div {{ min-width: 0; padding: 12px 16px; border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
    .review-states > div:first-child {{ padding-left: 0; }}
    .review-states > div:last-child {{ border-right: 0; }}
    .review-states dt {{ margin-bottom: 7px; color: var(--muted); font-size: 12px; font-weight: 700; }}
    .review-states dd {{ margin: 0; min-height: 28px; font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }}
    .notes {{ padding: 16px 0 0; }}
    .notes p {{ margin: 0; padding: 13px 15px; border-left: 3px solid var(--border-strong); background: var(--surface-muted); font-size: 13px; white-space: pre-wrap; }}
    .boundary {{ padding: 28px 0; }}
    .boundary h2 {{ margin-bottom: 14px; }}
    .boundary ul {{ margin: 0; padding: 0; border-top: 1px solid var(--border); list-style: none; }}
    .boundary li {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; min-height: 48px; border-bottom: 1px solid var(--border); }}
    @media (max-width: 780px) {{
      .summary, .review-states {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric:nth-child(2), .review-states > div:nth-child(2) {{ border-right: 0; }}
      .metric:nth-child(-n+2) {{ border-bottom: 1px solid var(--border); }}
      .review-states > div:nth-child(3) {{ padding-left: 0; }}
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
      .boundary li {{ align-items: flex-start; padding: 10px 0; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="page-header">
      <div>
        <p class="eyebrow">Manifest-bound review</p>
        <h1>사람 검토 기록</h1>
        <p>최근 기록 {html.escape(str(receipt.get('updated_at') or '기록 없음'))}</p>
      </div>
      <div class="header-actions">
        <a class="file-link" href="{_href(review_dashboard_path)}">문서 검토</a>
        <a class="file-link" href="{_href(receipt_path)}">Receipt JSON</a>
        {_status(overall_status)}
      </div>
    </header>
    <section class="summary" aria-label="사람 검토 요약">
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
        <dt>Schema</dt><dd><code>{html.escape(str(evidence.get('manifest_schema_version') or '기록 없음'))}</code></dd>
        <dt>생성 시각</dt><dd>{html.escape(str(evidence.get('manifest_generated_at') or '기록 없음'))}</dd>
      </dl>
    </section>
    {_bundle_review_rows(manifest, receipt)}
    <section class="boundary">
      <h2>외부 실행 권한</h2>
      <ul>{_external_action_rows(receipt)}</ul>
    </section>
  </main>
</body>
</html>"""

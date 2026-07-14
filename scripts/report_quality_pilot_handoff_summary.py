"""Render the operator summary embedded in a reviewed pilot handoff."""
from __future__ import annotations

import hashlib
import html
from typing import Any, Mapping


SUMMARY_NAME = "HANDOFF_SUMMARY.md"
HTML_SUMMARY_NAME = "HANDOFF_SUMMARY.html"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _markdown_text(value: Any) -> str:
    text = html.escape(str(value if value is not None else "-"), quote=False)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _code(value: Any) -> str:
    text = html.escape(str(value if value is not None else "-"), quote=False)
    text = text.replace("`", "").replace("\r", " ").replace("\n", " ")
    return f"`{text}`"


def _html_text(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"), quote=True)


def render_report_quality_pilot_handoff_summary(
    manifest: Mapping[str, Any],
    review_manifest: Mapping[str, Any],
) -> str:
    """Return a stable, reviewer-readable view of the handoff evidence."""
    jsonl = _as_dict(manifest.get("jsonl"))
    review = _as_dict(manifest.get("review"))
    rows = [row for row in _as_list(review_manifest.get("artifacts")) if isinstance(row, dict)]
    table_rows = "\n".join(
        "| {artifact_id} | {reviewer} | {reviewed_at} | {score} | {status} | {ready} |".format(
            artifact_id=_markdown_text(row.get("artifact_id")),
            reviewer=_markdown_text(row.get("reviewer")),
            reviewed_at=_markdown_text(row.get("reviewed_at")),
            score=_markdown_text(row.get("overall_score")),
            status=_markdown_text(row.get("human_review_status")),
            ready="yes" if row.get("ready_for_learning") is True else "no",
        )
        for row in rows
    )
    if not table_rows:
        table_rows = "| - | - | - | - | - | - |"

    source_bound = _as_dict(manifest.get("pack_binding")).get("source_manifest") is not None
    return f"""# Report Quality Pilot Review Handoff

## Batch

- batch_id: {_code(manifest.get('batch_id'))}
- artifact_count: {_code(manifest.get('artifact_count'))}
- source_bound: {_code(str(source_bound).lower())}
- training_authorized: `false`

## Reviewed Artifacts

| artifact_id | reviewer | reviewed_at | overall_score | review_status | ready |
| --- | --- | --- | --- | --- | --- |
{table_rows}

## Evidence

- JSONL SHA-256: {_code(jsonl.get('sha256'))}
- human review manifest SHA-256: {_code(review.get('manifest_sha256'))}
- decision receipt SHA-256: {_code(review.get('decision_receipt_sha256'))}
- decision file SHA-256: {_code(review.get('decision_file_sha256'))}

## Authorization Boundary

- external dataset upload: `not authorized`
- provider fine-tune API: `not authorized`
- provider job creation: `not authorized`
- training execution: `not authorized`
- model promotion: `not authorized`

검증 명령:

```bash
python3 scripts/manage_report_quality_pilot_handoff.py verify <handoff.zip>
```
"""


def render_report_quality_pilot_handoff_html(
    manifest: Mapping[str, Any],
    review_manifest: Mapping[str, Any],
) -> str:
    """Return a stable, script-free browser view of the handoff evidence."""
    jsonl = _as_dict(manifest.get("jsonl"))
    review = _as_dict(manifest.get("review"))
    rows = [row for row in _as_list(review_manifest.get("artifacts")) if isinstance(row, dict)]
    table_rows = "".join(
        f"""<tr>
          <td><strong>{_html_text(row.get('artifact_id'))}</strong></td>
          <td>{_html_text(row.get('reviewer'))}</td>
          <td>{_html_text(row.get('reviewed_at'))}</td>
          <td>{_html_text(row.get('overall_score'))}</td>
          <td><span class="status">{_html_text(row.get('human_review_status'))}</span></td>
          <td>{'yes' if row.get('ready_for_learning') is True else 'no'}</td>
        </tr>"""
        for row in rows
    )
    if not table_rows:
        table_rows = '<tr><td colspan="6">검토 artifact가 없습니다.</td></tr>'

    source_bound = _as_dict(manifest.get("pack_binding")).get("source_manifest") is not None
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Report Quality Pilot Review Handoff</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #202522;
      background: #f4f6f5;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f6f5; line-height: 1.55; }}
    header {{ background: #18352d; color: #ffffff; border-bottom: 6px solid #d6a84b; }}
    .header-inner, main {{ width: min(1120px, calc(100% - 40px)); margin: 0 auto; }}
    .header-inner {{ padding: 44px 0 38px; }}
    .eyebrow {{ margin: 0 0 10px; color: #d7e8e1; font-size: 13px; font-weight: 700; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: 34px; line-height: 1.2; letter-spacing: 0; }}
    .lede {{ max-width: 760px; margin: 14px 0 0; color: #e9f1ee; font-size: 16px; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }}
    .badge {{ display: inline-flex; align-items: center; min-height: 32px; padding: 6px 10px; border: 1px solid #8bb5a5; border-radius: 4px; font-size: 13px; font-weight: 700; }}
    .badge-boundary {{ border-color: #e8c77f; color: #ffe5ad; }}
    main {{ padding: 36px 0 56px; }}
    section {{ padding: 28px 0; border-top: 1px solid #cfd6d2; }}
    section:first-child {{ padding-top: 0; border-top: 0; }}
    h2 {{ margin: 0 0 16px; font-size: 21px; letter-spacing: 0; }}
    .facts {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .fact {{ min-width: 0; padding: 15px 16px; background: #ffffff; border: 1px solid #d7ddda; border-radius: 4px; }}
    .fact dt {{ margin: 0 0 5px; color: #5a645f; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .fact dd {{ margin: 0; font-size: 16px; font-weight: 700; overflow-wrap: anywhere; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid #cfd6d2; background: #ffffff; }}
    table {{ width: 100%; min-width: 820px; border-collapse: collapse; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid #e2e6e4; text-align: left; vertical-align: top; }}
    th {{ background: #edf2ef; color: #46504b; font-size: 12px; text-transform: uppercase; }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-block; padding: 3px 7px; border-radius: 4px; background: #dff1e8; color: #215b43; font-size: 12px; font-weight: 700; }}
    .hashes {{ display: grid; gap: 10px; margin: 0; }}
    .hashes div {{ display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 14px; align-items: start; }}
    .hashes dt {{ color: #5a645f; font-weight: 700; }}
    .hashes dd {{ margin: 0; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }}
    .boundary {{ padding: 22px; background: #fff6df; border: 1px solid #e2bd68; border-radius: 4px; }}
    .boundary h2 {{ color: #654607; }}
    .boundary ul {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 28px; margin: 0; padding-left: 20px; }}
    .verify {{ margin: 0; padding: 14px 16px; background: #272b29; color: #f5f7f6; border-radius: 4px; overflow-x: auto; }}
    footer {{ padding: 22px 0 34px; color: #68716d; font-size: 12px; }}
    @media (max-width: 760px) {{
      .header-inner, main {{ width: min(100% - 28px, 1120px); }}
      .header-inner {{ padding: 32px 0 28px; }}
      h1 {{ font-size: 28px; }}
      .facts {{ grid-template-columns: 1fr; }}
      .hashes div {{ grid-template-columns: 1fr; gap: 4px; }}
      .boundary ul {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <p class="eyebrow">DecisionDoc AI · Reviewed Pilot</p>
      <h1>Report Quality Pilot Review Handoff</h1>
      <p class="lede">검토가 완료된 correction artifact와 증빙 hash, 외부 실행 권한 경계를 한 화면에서 확인합니다.</p>
      <div class="badges">
        <span class="badge">Review completed</span>
        <span class="badge badge-boundary">Training not authorized</span>
      </div>
    </div>
  </header>
  <main>
    <section aria-labelledby="batch-heading">
      <h2 id="batch-heading">Batch</h2>
      <dl class="facts">
        <div class="fact"><dt>Batch ID</dt><dd>{_html_text(manifest.get('batch_id'))}</dd></div>
        <div class="fact"><dt>Artifact count</dt><dd>{_html_text(manifest.get('artifact_count'))}</dd></div>
        <div class="fact"><dt>Source bound</dt><dd>{str(source_bound).lower()}</dd></div>
      </dl>
    </section>
    <section aria-labelledby="artifacts-heading">
      <h2 id="artifacts-heading">Reviewed Artifacts</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Artifact ID</th><th>Reviewer</th><th>Reviewed at</th><th>Score</th><th>Status</th><th>Ready</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </section>
    <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">Evidence</h2>
      <dl class="hashes">
        <div><dt>JSONL SHA-256</dt><dd><code>{_html_text(jsonl.get('sha256'))}</code></dd></div>
        <div><dt>Human review manifest</dt><dd><code>{_html_text(review.get('manifest_sha256'))}</code></dd></div>
        <div><dt>Decision receipt</dt><dd><code>{_html_text(review.get('decision_receipt_sha256'))}</code></dd></div>
        <div><dt>Decision file</dt><dd><code>{_html_text(review.get('decision_file_sha256'))}</code></dd></div>
      </dl>
    </section>
    <section class="boundary" aria-labelledby="boundary-heading">
      <h2 id="boundary-heading">Authorization Boundary</h2>
      <ul>
        <li>External dataset upload: <strong>not authorized</strong></li>
        <li>Provider fine-tune API: <strong>not authorized</strong></li>
        <li>Provider job creation: <strong>not authorized</strong></li>
        <li>Training execution: <strong>not authorized</strong></li>
        <li>Model promotion: <strong>not authorized</strong></li>
      </ul>
    </section>
    <section aria-labelledby="verify-heading">
      <h2 id="verify-heading">Independent Verification</h2>
      <pre class="verify"><code>python3 scripts/manage_report_quality_pilot_handoff.py verify &lt;handoff.zip&gt;</code></pre>
    </section>
    <footer>이 화면은 handoff evidence에서 deterministic하게 생성된 script-free artifact입니다.</footer>
  </main>
</body>
</html>
"""


def verify_report_quality_pilot_handoff_summary(
    entries: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    review_manifest: Mapping[str, Any],
    *,
    require_html: bool = False,
) -> None:
    """Require the packaged summary to match the reviewed evidence exactly."""
    summary = manifest.get("summary")
    if not isinstance(summary, dict) or summary.get("path") != SUMMARY_NAME:
        raise ValueError("handoff summary path is invalid")
    if SUMMARY_NAME not in entries:
        raise ValueError("handoff summary is missing")
    summary_bytes = entries[SUMMARY_NAME]
    if summary.get("sha256") != _sha256(summary_bytes):
        raise ValueError("handoff summary SHA-256 mismatch")
    expected = render_report_quality_pilot_handoff_summary(
        manifest,
        review_manifest,
    ).encode("utf-8")
    if summary_bytes != expected:
        raise ValueError("handoff summary does not match the reviewed evidence")

    browser_summary = manifest.get("browser_summary")
    if not require_html and browser_summary is None and HTML_SUMMARY_NAME not in entries:
        return
    if not isinstance(browser_summary, dict) or browser_summary.get("path") != HTML_SUMMARY_NAME:
        raise ValueError("handoff browser summary path is invalid")
    if HTML_SUMMARY_NAME not in entries:
        raise ValueError("handoff browser summary is missing")
    html_bytes = entries[HTML_SUMMARY_NAME]
    if browser_summary.get("sha256") != _sha256(html_bytes):
        raise ValueError("handoff browser summary SHA-256 mismatch")
    expected_html = render_report_quality_pilot_handoff_html(
        manifest,
        review_manifest,
    ).encode("utf-8")
    if html_bytes != expected_html:
        raise ValueError("handoff browser summary does not match the reviewed evidence")

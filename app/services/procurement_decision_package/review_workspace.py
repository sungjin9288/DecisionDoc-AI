"""Self-contained browser workspace for a procurement decision package.

The workspace is a read-only projection of a validated local package. It does
not add an approval action, call a provider, or perform any external operation.
"""
from __future__ import annotations

import html
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import quote

from app.services.procurement_decision_package.constants import (
    INCLUDED_ARTIFACT_ORDER,
    PROCUREMENT_REVIEW_NAME,
)


STATUS_LABELS = {
    "blocked": "차단",
    "blocked_until_review": "검토 전 차단",
    "conditional": "조건부",
    "expected_shape_only": "예상 형식 검증",
    "needs_review": "검토 필요",
    "pass": "통과",
    "pending": "검토 대기",
    "ready": "준비됨",
    "record_shape": "저장 레코드 형식 검증",
    "source_fact": "근거 확인",
    "unknown": "미확정",
    "missing_evidence": "근거 부족",
}


def _text(value: Any, *, fallback: str = "기록 없음") -> str:
    text = str(value or "").strip()
    return html.escape(text or fallback)


def _label(value: Any) -> str:
    raw = str(value or "").strip()
    return STATUS_LABELS.get(raw, raw.replace("_", " ") or "기록 없음")


def _tone(value: Any) -> str:
    if value in {"GO", "pass", "ready", "source_fact"}:
        return "pass"
    if value in {"NO_GO", "blocked", "missing_evidence"}:
        return "fail"
    return "pending"


def _status(value: Any) -> str:
    return (
        f'<span class="status status-{_tone(value)}">'
        f"{_text(_label(value))}</span>"
    )


def _rows(
    items: Iterable[Mapping[str, Any]],
    renderer: Callable[[Mapping[str, Any]], str],
) -> str:
    return "".join(renderer(item) for item in items)


def _hard_filter_row(item: Mapping[str, Any]) -> str:
    return f"""<tr>
      <td><code>{_text(item.get('filter_id'))}</code></td>
      <td>{_status(item.get('status'))}</td>
      <td>{_text(item.get('reason'))}</td>
    </tr>"""


def _score_factor_row(item: Mapping[str, Any]) -> str:
    score = int(item.get("score") or 0)
    evidence_ids = item.get("evidence_ids") or []
    evidence = ", ".join(str(value) for value in evidence_ids)
    return f"""<tr>
      <td>{_text(str(item.get('name') or '').replace('_', ' '))}</td>
      <td class="score-cell"><strong>{score}</strong><span class="meter"><span style="width: {score}%"></span></span></td>
      <td><code>{_text(evidence)}</code></td>
    </tr>"""


def _evidence_rows(items: Iterable[Mapping[str, Any]], evidence_type: str) -> str:
    matching = [item for item in items if item.get("type") == evidence_type]
    return "".join(
        f"""<li>
          <div class="list-heading">{_status(item.get('type'))}<code>{_text(item.get('evidence_id'))}</code></div>
          <p>{_text(item.get('summary'))}</p>
          <small>Source: {_text(item.get('source'))}</small>
        </li>"""
        for item in matching
    )


def _checklist_row(item: Mapping[str, Any]) -> str:
    return f"""<tr>
      <td><strong>{_text(item.get('label'))}</strong><br><code>{_text(item.get('item_id'))}</code></td>
      <td>{_status(item.get('status'))}</td>
      <td>{_text(item.get('owner'))}</td>
      <td><code>{_text(item.get('required_before'))}</code></td>
    </tr>"""


def _plain_list(items: Iterable[Any]) -> str:
    return "".join(f"<li><code>{_text(item)}</code></li>" for item in items)


def _artifact_links() -> str:
    links = []
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        if artifact_name == PROCUREMENT_REVIEW_NAME:
            links.append(
                f'<li aria-current="page"><span>{_text(artifact_name)}</span><small>현재 화면</small></li>'
            )
            continue
        links.append(
            f'<li><a href="{quote(artifact_name)}">{_text(artifact_name)}</a><small>열기</small></li>'
        )
    return "".join(links)


def render_procurement_review_workspace(package_doc: Mapping[str, Any]) -> str:
    """Render a validated package as a local, read-only review workspace."""
    package = package_doc["package"]
    opportunity = package["opportunity_ref"]
    soft_fit = package["soft_fit_score"]
    validation = package["validation_summary"]
    reviewer = package["reviewer_handoff"]
    proposal = package["proposal_handoff"]
    signoff = package["pending_signoff"]
    score = int(soft_fit["score"])

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=">
  <title>{_text(opportunity['title'])} | Procurement Review</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f5f4;
      --surface: #ffffff;
      --text: #17201f;
      --muted: #5c6866;
      --border: #d6dddb;
      --accent: #0f766e;
      --accent-soft: #e6f3f1;
      --blue: #245b9e;
      --blue-soft: #eaf1fa;
      --pass: #237a45;
      --pass-soft: #e9f6ee;
      --warn: #a35b13;
      --warn-soft: #fff4df;
      --fail: #b23a3a;
      --fail-soft: #fcecec;
      --shadow: 0 8px 24px rgba(20, 35, 32, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: Pretendard, SUIT, "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; }}
    a {{ color: var(--blue); text-underline-offset: 3px; }}
    code {{ overflow-wrap: anywhere; color: #31504b; font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.86em; }}
    main {{ width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 36px 0 72px; }}
    header {{ padding: 0 0 28px; border-bottom: 3px solid var(--accent); }}
    .eyebrow {{ margin: 0 0 8px; color: var(--accent); font-size: 0.78rem; font-weight: 800; text-transform: uppercase; }}
    h1 {{ margin: 0; max-width: 900px; font-size: 2.6rem; line-height: 1.16; letter-spacing: 0; overflow-wrap: anywhere; }}
    h2 {{ margin: 0; font-size: 1.22rem; letter-spacing: 0; }}
    h3 {{ margin: 0; font-size: 1rem; letter-spacing: 0; }}
    p {{ margin: 0; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 16px; color: var(--muted); font-size: 0.88rem; }}
    .status-band {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); background: var(--surface); border-bottom: 1px solid var(--border); box-shadow: var(--shadow); }}
    .metric {{ min-width: 0; padding: 20px; border-right: 1px solid var(--border); }}
    .metric:last-child {{ border-right: 0; }}
    .metric-label {{ display: block; margin-bottom: 8px; color: var(--muted); font-size: 0.78rem; font-weight: 700; }}
    .metric-value {{ display: block; font-size: 1.08rem; overflow-wrap: anywhere; }}
    .score-value {{ font-size: 1.65rem; line-height: 1; }}
    .status {{ display: inline-flex; align-items: center; min-height: 26px; padding: 3px 9px; border: 1px solid currentColor; border-radius: 999px; font-size: 0.76rem; font-weight: 800; white-space: nowrap; }}
    .status-pass {{ color: var(--pass); background: var(--pass-soft); }}
    .status-pending {{ color: var(--warn); background: var(--warn-soft); }}
    .status-fail {{ color: var(--fail); background: var(--fail-soft); }}
    section {{ padding: 28px 0; border-bottom: 1px solid var(--border); }}
    .section-heading {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 18px; }}
    .section-heading p {{ color: var(--muted); font-size: 0.88rem; }}
    .decision-copy {{ max-width: 900px; font-size: 1.05rem; }}
    .next-action {{ margin-top: 18px; padding: 16px 18px; border-left: 4px solid var(--accent); background: var(--accent-soft); }}
    .next-action strong {{ display: block; margin-bottom: 4px; }}
    .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px; }}
    .panel {{ min-width: 0; padding-top: 14px; border-top: 2px solid var(--border); }}
    .panel h3 {{ margin-bottom: 12px; }}
    .review-list, .plain-list, .artifact-list {{ margin: 0; padding: 0; list-style: none; }}
    .review-list li {{ padding: 14px 0; border-bottom: 1px solid var(--border); }}
    .review-list li:last-child {{ border-bottom: 0; }}
    .review-list p {{ margin: 8px 0 4px; }}
    .review-list small {{ color: var(--muted); overflow-wrap: anywhere; }}
    .list-heading {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
    .plain-list {{ display: grid; gap: 8px; }}
    .plain-list li {{ padding: 10px 12px; background: var(--surface); border-left: 3px solid var(--warn); }}
    .table-wrap {{ width: 100%; overflow-x: auto; }}
    table {{ width: 100%; min-width: 720px; border-collapse: collapse; background: var(--surface); }}
    th, td {{ padding: 13px 14px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 0.76rem; text-transform: uppercase; background: #eef2f1; }}
    .score-cell {{ min-width: 180px; }}
    .meter {{ display: inline-block; width: 112px; height: 7px; margin-left: 12px; overflow: hidden; vertical-align: middle; background: #dce4e2; border-radius: 999px; }}
    .meter span {{ display: block; height: 100%; background: var(--accent); }}
    .handoff dl {{ display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 10px 16px; margin: 0; }}
    dt {{ color: var(--muted); font-size: 0.82rem; font-weight: 700; }}
    dd {{ min-width: 0; margin: 0; overflow-wrap: anywhere; }}
    .boundary {{ border-bottom: 0; }}
    .boundary-note {{ padding: 18px; color: #6b2e2e; background: var(--fail-soft); border-left: 4px solid var(--fail); }}
    .artifact-list {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: var(--border); border: 1px solid var(--border); }}
    .artifact-list li {{ display: flex; min-width: 0; justify-content: space-between; gap: 12px; padding: 12px; background: var(--surface); }}
    .artifact-list a, .artifact-list span {{ min-width: 0; overflow-wrap: anywhere; }}
    .artifact-list small {{ flex: 0 0 auto; color: var(--muted); }}
    footer {{ padding-top: 24px; color: var(--muted); font-size: 0.82rem; }}
    @media (max-width: 800px) {{
      main {{ width: min(100% - 24px, 1180px); padding-top: 22px; }}
      .status-band, .grid-2 {{ grid-template-columns: 1fr; }}
      .metric {{ border-right: 0; border-bottom: 1px solid var(--border); }}
      .metric:last-child {{ border-bottom: 0; }}
      .artifact-list {{ grid-template-columns: 1fr; }}
      .handoff dl {{ grid-template-columns: 1fr; gap: 4px; }}
      .handoff dd {{ margin-bottom: 10px; }}
      .section-heading {{ align-items: start; flex-direction: column; }}
      h1 {{ font-size: 1.8rem; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      main {{ width: 100%; padding: 0; }}
      .status-band {{ box-shadow: none; border: 1px solid var(--border); }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body>
  <main data-procurement-review-workspace data-package-id="{_text(package['package_id'])}">
    <header>
      <p class="eyebrow">Local procurement review package</p>
      <h1>{_text(opportunity['title'])}</h1>
      <div class="meta">
        <span>Opportunity <code>{_text(opportunity['opportunity_id'])}</code></span>
        <span>Package <code>{_text(package['package_id'])}</code></span>
        <span>Source <code>{_text(opportunity['source_type'])}</code></span>
        <span>Updated {_text(package_doc.get('updated_at'))}</span>
      </div>
    </header>

    <div class="status-band" aria-label="핵심 검토 상태">
      <div class="metric"><span class="metric-label">Recommendation</span><strong class="metric-value">{_text(package['recommendation'])}</strong></div>
      <div class="metric"><span class="metric-label">Soft fit</span><strong class="metric-value score-value">{score}<small>/100</small></strong></div>
      <div class="metric"><span class="metric-label">Proposal handoff</span><strong class="metric-value">{_status(proposal['drafting_status'])}</strong></div>
      <div class="metric"><span class="metric-label">Sign-off</span><strong class="metric-value">{_status(signoff['status'])}</strong></div>
    </div>

    <section aria-labelledby="decision-heading">
      <div class="section-heading"><h2 id="decision-heading">판단 요약</h2><p>{_text(_label(validation['schema_status']))}</p></div>
      <p class="decision-copy">{_text(package['recommendation_reason'])}</p>
      <div class="next-action"><strong>다음 검토 행동</strong><p>{_text(validation['next_review_action'])}</p></div>
    </section>

    <section aria-labelledby="filters-heading">
      <div class="section-heading"><h2 id="filters-heading">Hard filters</h2><p>필수 조건과 미확정 조건을 분리해 확인합니다.</p></div>
      <div class="table-wrap"><table><thead><tr><th>Filter</th><th>Status</th><th>Reason</th></tr></thead><tbody>{_rows(package['hard_filters'], _hard_filter_row)}</tbody></table></div>
    </section>

    <section aria-labelledby="score-heading">
      <div class="section-heading"><h2 id="score-heading">Soft fit score</h2><p>Band: {_text(soft_fit['band'])}</p></div>
      <div class="table-wrap"><table><thead><tr><th>Factor</th><th>Score</th><th>Evidence</th></tr></thead><tbody>{_rows(soft_fit['factors'], _score_factor_row)}</tbody></table></div>
    </section>

    <section aria-labelledby="evidence-heading">
      <div class="section-heading"><h2 id="evidence-heading">근거와 공백</h2><p>확인된 사실과 필요한 근거를 혼합하지 않습니다.</p></div>
      <div class="grid-2">
        <div class="panel"><h3>확인된 근거</h3><ul class="review-list">{_evidence_rows(package['evidence_summary'], 'source_fact')}</ul></div>
        <div class="panel"><h3>미확보 근거</h3><ul class="review-list">{_evidence_rows(package['evidence_summary'], 'missing_evidence')}</ul></div>
      </div>
    </section>

    <section aria-labelledby="readiness-heading">
      <div class="section-heading"><h2 id="readiness-heading">Bid readiness</h2><p>준비 상태는 제출 승인과 동일하지 않습니다.</p></div>
      <div class="table-wrap"><table><thead><tr><th>Item</th><th>Status</th><th>Owner</th><th>Required before</th></tr></thead><tbody>{_rows(package['bid_readiness_checklist'], _checklist_row)}</tbody></table></div>
    </section>

    <section aria-labelledby="handoff-heading">
      <div class="section-heading"><h2 id="handoff-heading">검토 및 제안서 handoff</h2><p>기존 review-only 경계를 유지합니다.</p></div>
      <div class="grid-2 handoff">
        <div class="panel"><h3>Reviewer request</h3><dl><dt>Reviewer</dt><dd>{_text(reviewer['requested_reviewer'])}</dd><dt>Decision</dt><dd><code>{_text(reviewer['requested_decision'])}</code></dd><dt>Prompt</dt><dd>{_text(reviewer['review_prompt'])}</dd><dt>Scope</dt><dd><code>{_text(signoff['signoff_scope'])}</code></dd></dl></div>
        <div class="panel"><h3>Proposal preparation</h3><dl><dt>Status</dt><dd>{_status(proposal['drafting_status'])}</dd><dt>Allowed next steps</dt><dd><ul class="plain-list">{_plain_list(proposal['allowed_next_steps'])}</ul></dd><dt>Blocked until</dt><dd><ul class="plain-list">{_plain_list(proposal['blocked_until'])}</ul></dd></dl></div>
      </div>
    </section>

    <section aria-labelledby="artifacts-heading">
      <div class="section-heading"><h2 id="artifacts-heading">Artifact index</h2><p>{len(INCLUDED_ARTIFACT_ORDER)}개 artifact가 동일한 audit/export 계약에 포함됩니다.</p></div>
      <ul class="artifact-list">{_artifact_links()}</ul>
    </section>

    <section class="boundary" aria-labelledby="boundary-heading">
      <div class="section-heading"><h2 id="boundary-heading">실행 권한 경계</h2><p>Operational approval: {_text(str(signoff['operational_approval']).lower())}</p></div>
      <p class="boundary-note">{_text(reviewer['non_authorization_note'])}</p>
    </section>

    <footer>이 화면은 검증된 local package의 읽기 전용 projection입니다. 별도 승인 또는 외부 실행을 생성하지 않습니다.</footer>
  </main>
</body>
</html>
"""

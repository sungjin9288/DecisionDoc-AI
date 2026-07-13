"""Browser review draft for a packet-bound procurement receipt."""
from __future__ import annotations

import hashlib
import html
import json
from typing import Any, Mapping
from urllib.parse import quote

from app.services.procurement_decision_package.constants import (
    EXPLICIT_AUTHORIZATION_BOUNDARY,
)
from app.services.procurement_decision_package.review_receipt import (
    REVIEW_RECEIPT_COMPLETED,
    REVIEW_RECEIPT_PENDING,
    record_procurement_review_decision,
    validate_procurement_review_receipt,
)


REVIEW_DRAFT_SCHEMA_VERSION = "decisiondoc.procurement_review_receipt_draft.v1"
REVIEW_DRAFT_FIELD_ORDER = (
    "schema_version",
    "source",
    "review",
    "authorization_boundary",
    "operational_approval",
)
REVIEW_DRAFT_SOURCE_FIELD_ORDER = (
    "packet_sha256",
    "packet_size_bytes",
    "receipt_sha256",
    "receipt_size_bytes",
)
REVIEW_DRAFT_REVIEW_FIELD_ORDER = (
    "reviewer",
    "decision",
    "rationale",
    "reviewed_at",
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _require_ordered_object(
    value: Any,
    expected_fields: tuple[str, ...],
    *,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or tuple(value) != expected_fields:
        raise ValueError(f"procurement review draft {field} fields are invalid")
    return value


def _require_matching_receipt_content(
    receipt: Mapping[str, Any],
    receipt_content: bytes,
) -> None:
    try:
        source_receipt = json.loads(receipt_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("procurement review receipt content is invalid") from exc
    if (
        not isinstance(source_receipt, dict)
        or tuple(source_receipt) != tuple(receipt)
        or source_receipt != dict(receipt)
    ):
        raise ValueError("procurement review receipt content does not match the receipt")


def apply_procurement_review_draft(
    receipt: Mapping[str, Any],
    draft: Mapping[str, Any],
    packet_content: bytes,
    *,
    receipt_content: bytes,
) -> dict[str, Any]:
    """Validate a browser draft and return the completed receipt."""
    current = dict(receipt)
    validate_procurement_review_receipt(current, packet_content)
    _require_matching_receipt_content(current, receipt_content)
    if current["status"] != REVIEW_RECEIPT_PENDING:
        raise ValueError("procurement review receipt is already completed")

    draft_doc = _require_ordered_object(
        dict(draft),
        REVIEW_DRAFT_FIELD_ORDER,
        field="root",
    )
    if draft_doc["schema_version"] != REVIEW_DRAFT_SCHEMA_VERSION:
        raise ValueError("procurement review draft schema_version is invalid")

    source = _require_ordered_object(
        draft_doc["source"],
        REVIEW_DRAFT_SOURCE_FIELD_ORDER,
        field="source",
    )
    expected_source = {
        "packet_sha256": _sha256(packet_content),
        "packet_size_bytes": len(packet_content),
        "receipt_sha256": _sha256(receipt_content),
        "receipt_size_bytes": len(receipt_content),
    }
    for field, expected in expected_source.items():
        if source[field] != expected:
            raise ValueError(f"procurement review draft source.{field} is stale")

    if draft_doc["authorization_boundary"] != EXPLICIT_AUTHORIZATION_BOUNDARY:
        raise ValueError("procurement review draft authorization_boundary is invalid")
    if draft_doc["operational_approval"] is not False:
        raise ValueError("procurement review draft must not authorize operational action")

    review = _require_ordered_object(
        draft_doc["review"],
        REVIEW_DRAFT_REVIEW_FIELD_ORDER,
        field="review",
    )
    return record_procurement_review_decision(
        current,
        packet_content,
        reviewer=review["reviewer"],
        decision=review["decision"],
        rationale=review["rationale"],
        reviewed_at=review["reviewed_at"],
    )


def _text(value: Any, *, fallback: str = "기록 없음") -> str:
    text = str(value or "").strip()
    return html.escape(text or fallback)


def _attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _file_link(path: str, label: str) -> str:
    if not path:
        return ""
    href = html.escape(quote(path, safe="/._-"), quote=True)
    return f'<a href="{href}">{html.escape(label)}</a>'


def _pending_form() -> str:
    return """
    <section aria-labelledby="decision-heading">
      <div class="section-heading">
        <div><p class="eyebrow">Requested reviewer decision</p><h2 id="decision-heading">검토 결정</h2></div>
        <span class="status status-pending">검토 대기</span>
      </div>
      <form data-review-draft-form>
        <div class="form-grid">
          <label><span>Decision</span><select name="decision" required>
            <option value="">선택</option>
            <option value="accepted">Accepted</option>
            <option value="changes_requested">Changes requested</option>
            <option value="rejected">Rejected</option>
          </select></label>
          <label class="wide"><span>Rationale</span><textarea name="rationale" rows="5" required></textarea></label>
        </div>
        <div class="form-actions">
          <p data-review-draft-message role="status" aria-live="polite"></p>
          <button type="submit">Review draft 다운로드</button>
        </div>
      </form>
    </section>"""


def _completed_review(receipt: Mapping[str, Any]) -> str:
    return f"""
    <section aria-labelledby="decision-heading">
      <div class="section-heading">
        <div><p class="eyebrow">Recorded reviewer decision</p><h2 id="decision-heading">검토 결정</h2></div>
        <span class="status status-completed">검토 완료</span>
      </div>
      <dl class="details">
        <dt>Decision</dt><dd><strong>{_text(receipt.get('decision'))}</strong></dd>
        <dt>Rationale</dt><dd>{_text(receipt.get('rationale'))}</dd>
        <dt>Reviewed at</dt><dd><code>{_text(receipt.get('reviewed_at'))}</code></dd>
      </dl>
    </section>"""


REVIEW_DRAFT_SCRIPT = """<script>
(() => {
  const workspace = document.querySelector("[data-review-receipt-workspace]");
  const form = document.querySelector("[data-review-draft-form]");
  const message = document.querySelector("[data-review-draft-message]");
  if (!workspace || !form || !message) return;

  form.addEventListener("submit", event => {
    event.preventDefault();
    const decision = form.elements.decision.value.trim();
    const rationale = form.elements.rationale.value.trim();
    if (!decision || !rationale) {
      message.dataset.tone = "fail";
      message.textContent = "Decision과 rationale를 모두 입력해야 합니다.";
      return;
    }

    const draft = {
      schema_version: workspace.dataset.draftSchemaVersion,
      source: {
        packet_sha256: workspace.dataset.packetSha256,
        packet_size_bytes: Number(workspace.dataset.packetSizeBytes),
        receipt_sha256: workspace.dataset.receiptSha256,
        receipt_size_bytes: Number(workspace.dataset.receiptSizeBytes),
      },
      review: {
        reviewer: workspace.dataset.reviewer,
        decision,
        rationale,
        reviewed_at: new Date().toISOString(),
      },
      authorization_boundary: workspace.dataset.authorizationBoundary,
      operational_approval: false,
    };
    const blob = new Blob([`${JSON.stringify(draft, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "procurement_review_draft.json";
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    message.dataset.tone = "pass";
    message.textContent = "Packet-bound review draft를 생성했습니다.";
  });
})();
</script>"""


def render_procurement_review_receipt_workspace(
    receipt: Mapping[str, Any],
    packet_content: bytes,
    *,
    receipt_content: bytes,
    packet_path: str = "",
    receipt_path: str = "",
) -> str:
    """Render a companion form without changing the packet or receipt."""
    receipt_doc = dict(receipt)
    validate_procurement_review_receipt(receipt_doc, packet_content)
    _require_matching_receipt_content(receipt_doc, receipt_content)
    status = receipt_doc["status"]
    if status not in {REVIEW_RECEIPT_PENDING, REVIEW_RECEIPT_COMPLETED}:
        raise ValueError("procurement review receipt status is invalid")

    decision_section = (
        _pending_form()
        if status == REVIEW_RECEIPT_PENDING
        else _completed_review(receipt_doc)
    )
    script = REVIEW_DRAFT_SCRIPT if status == REVIEW_RECEIPT_PENDING else ""
    links = " ".join(
        value
        for value in (
            _file_link(packet_path, "Packet ZIP"),
            _file_link(receipt_path, "Receipt JSON"),
        )
        if value
    )
    packet_sha256 = _sha256(packet_content)
    receipt_sha256 = _sha256(receipt_content)

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=">
  <title>{_text(receipt_doc['package_id'])} | Procurement Review Receipt</title>
  <style>
    :root {{ color-scheme: light; --bg:#f4f6f5; --surface:#fff; --text:#17201f; --muted:#5c6866; --border:#d4dcda; --accent:#0f766e; --accent-dark:#0b5d57; --pending:#9a5b14; --pending-bg:#fff4df; --done:#237a45; --done-bg:#e9f6ee; --fail:#b42318; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:Pretendard,SUIT,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; letter-spacing:0; }}
    main {{ width:min(880px,calc(100% - 32px)); margin:0 auto; padding:36px 0 64px; }}
    header {{ padding-bottom:24px; border-bottom:3px solid var(--accent); }}
    h1 {{ margin:0; font-size:30px; line-height:1.25; overflow-wrap:anywhere; }}
    h2 {{ margin:0; font-size:20px; }}
    p {{ line-height:1.6; }}
    .eyebrow {{ margin:0 0 7px; color:var(--accent-dark); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .subtitle {{ margin:8px 0 0; color:var(--muted); }}
    .links {{ display:flex; gap:16px; margin-top:14px; font-size:13px; }}
    a {{ color:var(--accent-dark); font-weight:700; text-underline-offset:3px; }}
    section {{ padding:26px 0; border-bottom:1px solid var(--border); }}
    .section-heading {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:18px; }}
    .status {{ display:inline-flex; min-height:28px; align-items:center; padding:4px 9px; border-radius:999px; font-size:12px; font-weight:800; white-space:nowrap; }}
    .status-pending {{ color:var(--pending); background:var(--pending-bg); }}
    .status-completed {{ color:var(--done); background:var(--done-bg); }}
    .details {{ display:grid; grid-template-columns:160px minmax(0,1fr); margin:0; }}
    .details dt,.details dd {{ margin:0; padding:10px 0; border-bottom:1px solid var(--border); overflow-wrap:anywhere; }}
    .details dt {{ color:var(--muted); font-size:12px; font-weight:700; }}
    .details dd {{ font-size:14px; }}
    code {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; }}
    .form-grid {{ display:grid; gap:16px; }}
    label {{ display:grid; gap:7px; }}
    label span {{ color:var(--muted); font-size:12px; font-weight:700; }}
    select,textarea {{ width:100%; padding:10px 11px; border:1px solid #9caaa7; border-radius:5px; background:var(--surface); color:var(--text); font:inherit; font-size:14px; }}
    select:focus,textarea:focus {{ outline:2px solid var(--accent); outline-offset:2px; }}
    textarea {{ resize:vertical; line-height:1.55; }}
    .form-actions {{ display:flex; justify-content:space-between; gap:20px; align-items:center; margin-top:18px; }}
    .form-actions p {{ min-height:22px; margin:0; color:var(--muted); font-size:13px; }}
    .form-actions p[data-tone="pass"] {{ color:var(--done); }}
    .form-actions p[data-tone="fail"] {{ color:var(--fail); }}
    button {{ min-height:42px; padding:9px 14px; border:1px solid var(--accent); border-radius:5px; background:var(--accent); color:#fff; font:inherit; font-size:13px; font-weight:800; cursor:pointer; white-space:nowrap; }}
    button:hover {{ background:var(--accent-dark); }}
    .boundary {{ border-bottom:0; }}
    .boundary p {{ margin:0; padding:15px 17px; border-left:4px solid var(--fail); background:#fcecec; overflow-wrap:anywhere; }}
    @media (max-width:600px) {{ main {{ width:min(100% - 24px,880px); padding-top:24px; }} h1 {{ font-size:25px; }} .section-heading,.form-actions {{ flex-direction:column; align-items:stretch; }} .details {{ grid-template-columns:1fr; }} .details dt {{ padding-bottom:0; border-bottom:0; }} .details dd {{ padding-top:4px; }} button {{ width:100%; }} }}
  </style>
</head>
<body>
  <main data-review-receipt-workspace
        data-draft-schema-version="{_attr(REVIEW_DRAFT_SCHEMA_VERSION)}"
        data-packet-sha256="{_attr(packet_sha256)}"
        data-packet-size-bytes="{len(packet_content)}"
        data-receipt-sha256="{_attr(receipt_sha256)}"
        data-receipt-size-bytes="{len(receipt_content)}"
        data-reviewer="{_attr(receipt_doc['reviewer'])}"
        data-authorization-boundary="{_attr(EXPLICIT_AUTHORIZATION_BOUNDARY)}">
    <header>
      <p class="eyebrow">Packet-bound local review</p>
      <h1>조달 검토 Receipt</h1>
      <p class="subtitle">Package <code>{_text(receipt_doc['package_id'])}</code></p>
      <div class="links">{links}</div>
    </header>
    <section aria-labelledby="evidence-heading">
      <div class="section-heading"><div><p class="eyebrow">Source identity</p><h2 id="evidence-heading">검토 증적</h2></div></div>
      <dl class="details">
        <dt>Recommendation</dt><dd><strong>{_text(receipt_doc['recommendation'])}</strong></dd>
        <dt>Requested reviewer</dt><dd>{_text(receipt_doc['reviewer'])}</dd>
        <dt>Packet SHA256</dt><dd><code>{_text(packet_sha256)}</code></dd>
        <dt>Receipt SHA256</dt><dd><code>{_text(receipt_sha256)}</code></dd>
      </dl>
    </section>
    {decision_section}
    <section class="boundary" aria-labelledby="boundary-heading">
      <div class="section-heading"><div><p class="eyebrow">Authority boundary</p><h2 id="boundary-heading">실행 권한</h2></div></div>
      <p>{_text(EXPLICIT_AUTHORIZATION_BOUNDARY)} Operational approval은 계속 <strong>false</strong>입니다.</p>
    </section>
  </main>
  {script}
</body>
</html>
"""

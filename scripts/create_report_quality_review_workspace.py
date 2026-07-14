#!/usr/bin/env python3
"""Create a source-bound browser workspace for Report Quality pilot review."""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import (  # noqa: E402
    MIN_EXPORT_READINESS_SCORE,
    MIN_OVERALL_SCORE,
    MIN_REQUIRED_DIMENSION_SCORE,
    MIN_VISUAL_DESIGN_SCORE,
    REQUIRED_DIMENSIONS,
)
from scripts.apply_report_quality_review_decisions import (  # noqa: E402
    ALLOWED_DECISIONS,
    ALLOWED_SCAN_VALUES,
)
from scripts.report_quality_pilot_pack_provenance import (  # noqa: E402
    load_pilot_pack,
    require_current_pack_binding,
)


DECISION_SCHEMA = "decisiondoc_report_quality_human_review_decisions.v1"
DEFAULT_DECISIONS_NAME = "review_decisions.json"
DEFAULT_OUTPUT_NAME = "HUMAN_REVIEW_WORKSPACE.html"
DOWNLOAD_NAME = "review_decisions.browser-draft.json"

DIMENSION_LABELS = {
    "logic": "논리 구조",
    "evidence": "근거 품질",
    "audience_fit": "독자 적합성",
    "slide_structure": "장표 구조",
    "visual_design": "시각 설계",
    "public_sector_tone": "공공 문서 톤",
    "export_readiness": "내보내기 준비도",
    "learning_value": "학습 가치",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "")


def _escape(value: Any, *, quote: bool = False) -> str:
    return html.escape(_text(value), quote=quote)


def _selected(value: Any, option: str) -> str:
    return " selected" if _text(value) == option else ""


def _lines(value: Any) -> str:
    return "\n".join(_text(item) for item in _as_list(value))


def _safe_script_json(payload: dict[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _resolve_pack_file(pack_dir: Path, path: Path | None, default_name: str) -> Path:
    candidate = path.expanduser() if path is not None else pack_dir / default_name
    if candidate.is_symlink():
        raise ValueError(f"symlink pack files are not allowed: {candidate}")
    resolved = candidate.resolve()
    if resolved.parent != pack_dir:
        raise ValueError(f"pack file must be written directly inside the pilot pack: {resolved}")
    return resolved


def _load_decision_template(pack_dir: Path, decisions_path: Path) -> dict[str, Any]:
    payload = json.loads(decisions_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review decision template root must be an object")
    if payload.get("report_type") != "report_quality_human_review_decision_template":
        raise ValueError("review decision template report_type is invalid")
    if payload.get("schema_version") != DECISION_SCHEMA:
        raise ValueError("review decision template schema_version is invalid")
    if payload.get("training_authorized") is not False:
        raise ValueError("review decision template must keep training_authorized=false")

    snapshot = load_pilot_pack(pack_dir)
    require_current_pack_binding(snapshot, payload.get("pack_binding"))
    decisions = payload.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("review decision template must contain decisions")
    if not all(isinstance(item, dict) for item in decisions):
        raise ValueError("review decision template decisions must be objects")
    expected_ids = [draft.artifact_id for draft in snapshot.drafts]
    actual_ids = [_text(item.get("artifact_id")).strip() for item in decisions]
    if actual_ids != expected_ids:
        raise ValueError("review decision template artifact order does not match the pilot pack")
    for index, item in enumerate(decisions):
        if item.get("decision") not in ALLOWED_DECISIONS:
            raise ValueError(f"review decision template decisions[{index}].decision is invalid")
        for scan_key in ("forbidden_terms_scan", "privacy_security_scan"):
            if item.get(scan_key) not in ALLOWED_SCAN_VALUES:
                raise ValueError(f"review decision template decisions[{index}].{scan_key} is invalid")
    return payload


def _select(name: str, value: Any, options: Sequence[tuple[str, str]]) -> str:
    option_html = "".join(
        f'<option value="{_escape(option, quote=True)}"{_selected(value, option)}>{_escape(label)}</option>'
        for option, label in options
    )
    return f'<select name="{_escape(name, quote=True)}">{option_html}</select>'


def _score_input(name: str, value: Any) -> str:
    rendered_value = "" if value is None else _text(value)
    return (
        f'<input name="{_escape(name, quote=True)}" type="number" min="0" max="1" '
        f'step="0.01" inputmode="decimal" value="{_escape(rendered_value, quote=True)}">'
    )


def _dimension_rows(decision: dict[str, Any]) -> str:
    scores = _as_dict(decision.get("dimension_scores"))
    rationale = _as_dict(decision.get("rationale_by_dimension"))
    return "".join(
        f"""<div class="dimension-row">
          <label><span>{_escape(DIMENSION_LABELS.get(dimension, dimension))}</span>
            {_score_input(f'dimension_score:{dimension}', scores.get(dimension))}
          </label>
          <label class="rationale"><span>판단 근거</span>
            <textarea name="rationale:{_escape(dimension, quote=True)}" rows="2">{_escape(rationale.get(dimension))}</textarea>
          </label>
        </div>"""
        for dimension in REQUIRED_DIMENSIONS
    )


def _list_field(name: str, label: str, value: Any) -> str:
    return f"""<label><span>{_escape(label)}</span>
      <textarea name="{_escape(name, quote=True)}" rows="3">{_escape(_lines(value))}</textarea>
    </label>"""


def _change_request_rows(value: Any) -> str:
    requests = [item for item in _as_list(value) if isinstance(item, dict)] or [{}]
    return "".join(
        f"""<fieldset class="change-request" data-change-request>
          <legend>보완 요청 {index + 1}</legend>
          <div class="change-request-fields">
            <label><span>대상</span><input name="target" value="{_escape(item.get('target'), quote=True)}"></label>
            <label><span>이슈</span><textarea name="issue" rows="2">{_escape(item.get('issue'))}</textarea></label>
            <label><span>교정 방향</span><textarea name="correction" rows="2">{_escape(item.get('correction'))}</textarea></label>
            <label><span>요청 근거</span><textarea name="rationale" rows="2">{_escape(item.get('rationale'))}</textarea></label>
          </div>
        </fieldset>"""
        for index, item in enumerate(requests)
    )


def _decision_section(decision: dict[str, Any], index: int) -> str:
    artifact_id = _text(decision.get("artifact_id"))
    previous = _text(decision.get("previous_decision")) or "pending"
    decision_options = (
        ("pending", "검토 대기"),
        ("accepted", "승인"),
        ("changes_requested", "보완 요청"),
        ("rejected", "반려"),
    )
    scan_options = (("not_run", "미실행"), ("pass", "통과"), ("fail", "실패"))
    return f"""<section class="artifact" data-review-form data-artifact-id="{_escape(artifact_id, quote=True)}">
      <header class="artifact-header">
        <div>
          <p class="artifact-order">Artifact {index + 1}</p>
          <h2>{_escape(artifact_id)}</h2>
          <p>{_escape(decision.get('domain') or 'domain 미기록')} · {_escape(decision.get('report_workflow_id') or 'workflow 미기록')}</p>
        </div>
        <div class="artifact-links">
          <span class="status">이전 결정: {_escape(previous)}</span>
          <a href="drafts/{quote(artifact_id, safe='')}.json">원본 draft</a>
        </div>
      </header>

      <div class="primary-fields">
        <label><span>검토 결정</span>{_select('decision', decision.get('decision'), decision_options)}</label>
        <label><span>검수자</span><input name="reviewer" value="{_escape(decision.get('reviewer'), quote=True)}"></label>
        <label><span>검토 시각 (ISO 8601)</span><input name="reviewed_at" value="{_escape(decision.get('reviewed_at'), quote=True)}" placeholder="2026-07-14T10:00:00+09:00"></label>
        <label><span>종합 점수</span>{_score_input('overall_score', decision.get('overall_score'))}</label>
        <label><span>금지어 scan</span>{_select('forbidden_terms_scan', decision.get('forbidden_terms_scan'), scan_options)}</label>
        <label><span>개인정보·보안 scan</span>{_select('privacy_security_scan', decision.get('privacy_security_scan'), scan_options)}</label>
      </div>

      <details open>
        <summary>품질 차원 점수와 근거</summary>
        <div class="dimension-list">{_dimension_rows(decision)}</div>
      </details>
      <details>
        <summary>Claim과 보완 기록</summary>
        <div class="list-fields">
          {_list_field('confirmed_claims', '확인된 claim (한 줄에 하나)', decision.get('confirmed_claims'))}
          {_list_field('assumed_claims', '가정 claim (한 줄에 하나)', decision.get('assumed_claims'))}
          {_list_field('todo_claims', '미해결 claim (한 줄에 하나)', decision.get('todo_claims'))}
          {_list_field('hard_failures', 'Hard failure (한 줄에 하나)', decision.get('hard_failures'))}
        </div>
        <div class="change-requests">{_change_request_rows(decision.get('change_requests'))}</div>
      </details>
    </section>"""


WORKSPACE_SCRIPT = """<script>
(() => {
  const templateNode = document.querySelector("#review-decision-template");
  const downloadButton = document.querySelector("[data-download-draft]");
  const message = document.querySelector("[data-workspace-message]");
  if (!templateNode || !downloadButton || !message) return;

  const template = JSON.parse(templateNode.textContent);
  const groups = Array.from(document.querySelectorAll("[data-review-form]"));
  const lineValues = value => value
    .replaceAll(String.fromCharCode(13), "")
    .split(String.fromCharCode(10))
    .map(item => item.trim())
    .filter(Boolean);
  const field = (group, name) => group.querySelector(`[name="${name}"]`);
  const textValue = (group, name) => field(group, name).value.trim();

  function scoreValue(group, name) {
    const raw = textValue(group, name);
    if (!raw) return null;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      field(group, name).focus();
      throw new Error(`${group.dataset.artifactId}: ${name} 점수는 0과 1 사이여야 합니다.`);
    }
    return value;
  }

  function readDecision(group, source) {
    const decision = structuredClone(source);
    decision.decision = textValue(group, "decision");
    decision.reviewer = textValue(group, "reviewer");
    decision.reviewed_at = textValue(group, "reviewed_at");
    decision.overall_score = scoreValue(group, "overall_score");
    decision.forbidden_terms_scan = textValue(group, "forbidden_terms_scan");
    decision.privacy_security_scan = textValue(group, "privacy_security_scan");
    decision.dimension_scores = Object.create(null);
    decision.rationale_by_dimension = Object.create(null);
    template.required_dimensions.forEach(dimension => {
      decision.dimension_scores[dimension] = scoreValue(group, `dimension_score:${dimension}`);
      decision.rationale_by_dimension[dimension] = textValue(group, `rationale:${dimension}`);
    });
    ["confirmed_claims", "assumed_claims", "todo_claims", "hard_failures"].forEach(name => {
      decision[name] = lineValues(field(group, name).value);
    });
    decision.change_requests = Array.from(group.querySelectorAll("[data-change-request]")).flatMap(row => {
      const request = Object.fromEntries(["target", "issue", "correction", "rationale"].map(name => [name, textValue(row, name)]));
      const values = Object.values(request);
      if (values.every(value => !value)) return [];
      if (values.some(value => !value)) {
        throw new Error(`${group.dataset.artifactId}: 보완 요청 항목을 모두 입력하거나 모두 비워야 합니다.`);
      }
      return [request];
    });
    if (decision.decision === "accepted") {
      const missing = [];
      if (!decision.reviewer) missing.push("검수자");
      if (!decision.reviewed_at) missing.push("검토 시각");
      if (decision.overall_score === null) missing.push("종합 점수");
      if (decision.forbidden_terms_scan !== "pass") missing.push("금지어 scan 통과");
      if (decision.privacy_security_scan !== "pass") missing.push("개인정보·보안 scan 통과");
      if (decision.overall_score !== null && decision.overall_score < template.minimum_overall_score) missing.push(`종합 점수 ${template.minimum_overall_score} 이상`);
      template.required_dimensions.forEach(dimension => {
        const score = decision.dimension_scores[dimension];
        const minimum = template.minimum_dimension_scores[dimension];
        if (score === null) missing.push(`${dimension} 점수`);
        else if (score < minimum) missing.push(`${dimension} 점수 ${minimum} 이상`);
        if (!decision.rationale_by_dimension[dimension]) missing.push(`${dimension} 판단 근거`);
      });
      if (decision.hard_failures.length) missing.push("hard failure 해소");
      if (missing.length) {
        throw new Error(`${group.dataset.artifactId}: 승인에 필요한 항목 - ${missing.join(", ")}`);
      }
    }
    return decision;
  }

  downloadButton.addEventListener("click", () => {
    try {
      const draft = structuredClone(template.decision_file);
      draft.created_at = new Date().toISOString();
      draft.training_authorized = false;
      draft.decisions = groups.map((group, index) => readDecision(group, draft.decisions[index]));
      const blob = new Blob([`${JSON.stringify(draft, null, 2)}\n`], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = template.download_name;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
      message.dataset.tone = "pass";
      message.textContent = `${draft.decisions.length}개 artifact의 source-bound draft를 생성했습니다.`;
    } catch (error) {
      message.dataset.tone = "fail";
      message.textContent = error instanceof Error ? error.message : String(error);
    }
  });
})();
</script>"""


def render_report_quality_review_workspace(
    *,
    decision_file: dict[str, Any],
    pack_dir: Path,
) -> str:
    decisions = [item for item in _as_list(decision_file.get("decisions")) if isinstance(item, dict)]
    binding = _as_dict(decision_file.get("pack_binding"))
    source_manifest = _as_dict(binding.get("source_manifest"))
    embedded = {
        "decision_file": decision_file,
        "download_name": DOWNLOAD_NAME,
        "minimum_overall_score": MIN_OVERALL_SCORE,
        "minimum_dimension_scores": {
            dimension: (
                MIN_VISUAL_DESIGN_SCORE
                if dimension == "visual_design"
                else MIN_EXPORT_READINESS_SCORE
                if dimension == "export_readiness"
                else MIN_REQUIRED_DIMENSION_SCORE
            )
            for dimension in REQUIRED_DIMENSIONS
        },
        "required_dimensions": list(REQUIRED_DIMENSIONS),
    }
    sections = "".join(_decision_section(decision, index) for index, decision in enumerate(decisions))
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Report Quality Pilot 검수</title>
  <style>
    :root {{ color-scheme: light; --bg:#f4f6f6; --surface:#fff; --muted:#5c696c; --text:#182326; --line:#d5ddde; --strong:#9fadaf; --accent:#0f766e; --accent-dark:#0b5d57; --pass:#166534; --fail:#b42318; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:Pretendard,SUIT,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; letter-spacing:0; }}
    a {{ color:var(--accent-dark); font-weight:700; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
    button,input,select,textarea {{ font:inherit; }}
    .shell {{ width:min(1120px,calc(100vw - 40px)); margin:0 auto 72px; }}
    .page-header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; padding:36px 0 24px; border-bottom:1px solid var(--strong); }}
    .eyebrow,.artifact-order {{ margin:0 0 6px; color:var(--accent-dark); font-size:12px; font-weight:800; text-transform:uppercase; }}
    h1 {{ margin:0 0 8px; font-size:30px; line-height:1.25; }} h2 {{ margin:0 0 5px; font-size:20px; overflow-wrap:anywhere; }}
    p {{ line-height:1.55; }} .page-header p:not(.eyebrow),.artifact-header p:not(.artifact-order) {{ margin:0; color:var(--muted); font-size:13px; }}
    .header-links,.artifact-links {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }}
    .binding {{ display:grid; grid-template-columns:160px minmax(0,1fr); margin:0; padding:18px 0; border-bottom:1px solid var(--strong); }}
    .binding dt,.binding dd {{ margin:0; padding:8px 0; border-bottom:1px solid var(--line); font-size:13px; }} .binding dt {{ color:var(--muted); font-weight:700; }} .binding dd {{ overflow-wrap:anywhere; }}
    code {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; }}
    .artifact {{ padding:28px 0; border-bottom:1px solid var(--strong); }}
    .artifact-header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }}
    .status {{ padding:5px 9px; border-radius:5px; background:#fff4d6; color:#7a4307; font-size:12px; font-weight:800; }}
    .primary-fields {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:22px; }}
    label {{ display:grid; gap:6px; min-width:0; }} label span {{ color:var(--muted); font-size:12px; font-weight:700; }}
    input,select,textarea {{ width:100%; min-height:42px; padding:9px 10px; border:1px solid var(--strong); border-radius:5px; background:var(--surface); color:var(--text); font-size:13px; }}
    textarea {{ resize:vertical; line-height:1.5; }} input:focus,select:focus,textarea:focus {{ outline:2px solid var(--accent); outline-offset:2px; }}
    details {{ margin-top:20px; border-top:1px solid var(--line); }} summary {{ padding:14px 0; cursor:pointer; font-size:13px; font-weight:800; }}
    .dimension-list {{ border-top:1px solid var(--line); }} .dimension-row {{ display:grid; grid-template-columns:180px minmax(0,1fr); gap:14px; padding:12px 0; border-bottom:1px solid var(--line); }}
    .list-fields {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .change-requests {{ margin-top:16px; }} .change-request {{ margin:0; padding:16px 0; border:0; border-top:1px solid var(--line); }} .change-request legend {{ padding:0 8px 0 0; font-size:12px; font-weight:800; }} .change-request-fields {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .actions {{ position:sticky; bottom:0; display:flex; justify-content:space-between; gap:20px; align-items:center; padding:16px 0; border-top:1px solid var(--strong); background:color-mix(in srgb,var(--bg) 94%,transparent); backdrop-filter:blur(10px); }}
    .actions p {{ margin:0; color:var(--muted); font-size:13px; }} .actions p[data-tone="pass"] {{ color:var(--pass); }} .actions p[data-tone="fail"] {{ color:var(--fail); }}
    .primary-action {{ min-height:42px; padding:9px 14px; border:1px solid var(--accent); border-radius:5px; background:var(--accent); color:#fff; font-weight:800; cursor:pointer; white-space:nowrap; }} .primary-action:hover {{ background:var(--accent-dark); }}
    @media (max-width:760px) {{ .primary-fields {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .dimension-row {{ grid-template-columns:140px minmax(0,1fr); }} }}
    @media (max-width:560px) {{ .shell {{ width:calc(100vw - 24px); }} .page-header,.artifact-header,.actions {{ flex-direction:column; }} .header-links,.artifact-links {{ justify-content:flex-start; }} .binding,.primary-fields,.dimension-row,.list-fields,.change-request-fields {{ grid-template-columns:1fr; }} .binding dt {{ padding-bottom:0; border-bottom:0; }} .binding dd {{ padding-top:4px; }} .actions {{ align-items:stretch; }} .primary-action {{ width:100%; }} h1 {{ font-size:25px; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="page-header">
      <div><p class="eyebrow">Source-bound local review</p><h1>Report Quality Pilot 검수</h1><p>{len(decisions)}개 artifact · training authorization 없음</p></div>
      <nav class="header-links"><a href="HUMAN_REVIEW_WORKSHEET.md">검수 worksheet</a><a href="human_review_manifest.json">검수 manifest</a><a href="review_decisions.json">초기 decision JSON</a></nav>
    </header>
    <dl class="binding">
      <dt>Pack</dt><dd><code>{_escape(pack_dir)}</code></dd>
      <dt>Source manifest SHA256</dt><dd><code>{_escape(source_manifest.get('sha256') or 'generated draft pack')}</code></dd>
      <dt>Training boundary</dt><dd><strong>not authorized</strong></dd>
    </dl>
    {sections}
    <section class="actions">
      <p data-workspace-message role="status" aria-live="polite">입력 결과는 원본을 바꾸지 않고 source-bound JSON draft로 내려받습니다.</p>
      <button class="primary-action" type="button" data-download-draft>검수 Draft 다운로드</button>
    </section>
  </main>
  <script id="review-decision-template" type="application/json">{_safe_script_json(embedded)}</script>
  {WORKSPACE_SCRIPT}
</body>
</html>
"""


def create_report_quality_review_workspace(
    *,
    pack_dir: Path,
    decisions_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    resolved_decisions_path = _resolve_pack_file(
        resolved_pack_dir,
        decisions_path,
        DEFAULT_DECISIONS_NAME,
    )
    resolved_output_path = _resolve_pack_file(
        resolved_pack_dir,
        output_path,
        DEFAULT_OUTPUT_NAME,
    )
    if resolved_output_path.exists():
        raise ValueError(f"refusing to overwrite existing review workspace: {resolved_output_path}")
    if resolved_output_path == resolved_decisions_path:
        raise ValueError("review workspace and decision template must be different files")

    decision_file = _load_decision_template(resolved_pack_dir, resolved_decisions_path)
    workspace = render_report_quality_review_workspace(
        decision_file=decision_file,
        pack_dir=resolved_pack_dir,
    )
    _write_text_atomic(resolved_output_path, workspace)
    return {
        "report_type": "report_quality_human_review_workspace_created",
        "schema_version": "decisiondoc_report_quality_human_review_workspace.v1",
        "created_at": _now_iso(),
        "ok": True,
        "pack_dir": str(resolved_pack_dir),
        "decisions_path": str(resolved_decisions_path),
        "output_path": str(resolved_output_path),
        "download_name": DOWNLOAD_NAME,
        "artifact_count": len(decision_file["decisions"]),
        "training_authorized": False,
        "side_effect_boundary": {
            "reads_local_decision_json": True,
            "writes_local_review_workspace": True,
            "writes_local_draft_json": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a local browser workspace for Report Quality pilot review.",
    )
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--decisions", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = create_report_quality_review_workspace(
            pack_dir=args.pack_dir,
            decisions_path=args.decisions,
            output_path=args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PASS report quality human review workspace created")
        print(f"output_path={result['output_path']}")
        print(f"artifact_count={result['artifact_count']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

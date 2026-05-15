#!/usr/bin/env python3
"""Create draft review artifacts for a Report Quality Learning pilot batch."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/correction_artifact_template.json"
DEFAULT_OUTPUT_ROOT = Path("reports/report-quality")

DEFAULT_SAMPLE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "document_type": "proposal_deck",
        "audience": "executive_pm_public_sector",
        "domain": "public_sector_ai_traffic_safety",
        "slide_count": 10,
        "topic": "공공기관 AI 교통안전 제안서",
    },
    {
        "document_type": "company_intro_deck",
        "audience": "procurement_pm_and_executive",
        "domain": "smart_factory_supplier",
        "slide_count": 8,
        "topic": "스마트공장 공급기업 소개서",
    },
    {
        "document_type": "governance_report",
        "audience": "pm_security_compliance_owner",
        "domain": "document_ops_governance",
        "slide_count": 9,
        "topic": "운영/보안/거버넌스 보고서",
    },
    {
        "document_type": "g2b_planning_deck",
        "audience": "proposal_team_and_decision_owner",
        "domain": "g2b_proposal_planning",
        "slide_count": 12,
        "topic": "G2B 사업 제안 기획안",
    },
    {
        "document_type": "onepager",
        "audience": "ceo_pm_business_owner",
        "domain": "installed_document_platform",
        "slide_count": 1,
        "topic": "내부 설치형 문서 운영 플랫폼 소개서",
    },
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _load_template() -> dict[str, Any]:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"template root must be an object: {TEMPLATE_PATH}")
    return payload


def _sample_profile(index: int) -> dict[str, Any]:
    return DEFAULT_SAMPLE_PROFILES[index % len(DEFAULT_SAMPLE_PROFILES)]


def _build_artifact_draft(
    *,
    template: dict[str, Any],
    batch_id: str,
    sample_index: int,
    tenant_id: str,
    reviewer: str,
) -> dict[str, Any]:
    sample_no = sample_index + 1
    profile = _sample_profile(sample_index)
    artifact = copy.deepcopy(template)
    artifact["artifact_id"] = f"{batch_id}_sample_{sample_no:03d}"
    artifact["created_at"] = _now_iso()

    workflow = artifact.setdefault("workflow_reference", {})
    workflow["tenant_id"] = tenant_id
    workflow["report_workflow_id"] = f"TODO_REPORT_WORKFLOW_ID_{sample_no:03d}"
    workflow["project_id"] = f"TODO_PROJECT_ID_{sample_no:03d}"
    workflow["workflow_status"] = "final_approved"
    workflow["learning_opt_in"] = True
    workflow["source_material_policy"] = "metadata_only"

    document_profile = artifact.setdefault("document_profile", {})
    document_profile["document_type"] = profile["document_type"]
    document_profile["audience"] = profile["audience"]
    document_profile["domain"] = profile["domain"]
    document_profile["language"] = "ko"
    document_profile["slide_count"] = profile["slide_count"]

    before = artifact.setdefault("before", {})
    before["planning_summary"] = (
        f"[{profile['topic']}] AI 초안의 구조, 논리 약점, 근거 공백, 장표 설계 문제를 요약한다."
    )
    before["slide_outline_summary"] = [
        {
            "slide_no": 1,
            "title": "TODO_AI_DRAFT_SLIDE_TITLE",
            "message": "TODO_AI_DRAFT_CORE_MESSAGE",
            "issue": "TODO_LOGIC_EVIDENCE_VISUAL_ISSUE",
        }
    ]
    before["visible_claims"] = [
        {
            "claim": "TODO_VISIBLE_CLAIM_TO_VERIFY",
            "status": "todo",
            "evidence_reference": "metadata/reference only; no raw attachment content",
        }
    ]

    correction = artifact.setdefault("correction", {})
    correction["reviewer"] = reviewer
    correction["reviewed_at"] = ""
    correction["change_requests"] = [
        {
            "target": "planning",
            "issue": "TODO_초안의 가장 큰 논리/근거/디자인 문제",
            "correction": "TODO_사람이 교정한 구조 또는 메시지",
            "rationale": "TODO_왜 이 교정이 보고서 품질과 의사결정에 필요한지",
        }
    ]
    correction["rationale_by_dimension"] = {
        key: f"TODO_{key}_교정_근거"
        for key in artifact["quality_baseline"]["dimension_scores"]
    }

    after = artifact.setdefault("after", {})
    after["planning_summary"] = "TODO_사람이 승인 가능한 최종 기획 구조 요약"
    after["slide_outline_summary"] = [
        {
            "slide_no": 1,
            "title": "TODO_FINAL_SLIDE_TITLE",
            "message": "TODO_FINAL_CORE_MESSAGE",
            "layout": "TODO_FINAL_LAYOUT_DIRECTION",
            "visual_asset": "TODO_FINAL_VISUAL_ASSET_DIRECTION",
        }
    ]
    after["final_output_reference"] = f"report_workflow_snapshot:{workflow['report_workflow_id']}"

    labels = artifact.setdefault("learning_labels", {})
    labels["accepted_for_learning"] = False
    labels["forbidden_terms_scan"] = "not_run"
    labels["privacy_security_scan"] = "not_run"
    labels["human_review_status"] = "pending"

    boundary = artifact.setdefault("training_boundary", {})
    for key in boundary:
        boundary[key] = False

    return artifact


def _render_index(
    *,
    batch_id: str,
    output_dir: Path,
    artifacts: list[dict[str, Any]],
    jsonl_path: Path,
) -> str:
    rows = "\n".join(
        "| {artifact_id} | {document_type} | {domain} | {status} |".format(
            artifact_id=artifact.get("artifact_id", "-"),
            document_type=artifact.get("document_profile", {}).get("document_type", "-"),
            domain=artifact.get("document_profile", {}).get("domain", "-"),
            status=artifact.get("learning_labels", {}).get("human_review_status", "-"),
        )
        for artifact in artifacts
    )
    return f"""# Report Quality Pilot Review Pack

- batch_id: `{batch_id}`
- generated_at: `{_now_iso()}`
- output_dir: `{output_dir}`
- draft_jsonl: `{jsonl_path}`
- training_authorized: `false`

## Purpose

이 review pack은 실제 fine-tuning 전에 사람이 교정 전/후 차이와 수정 이유를 기록하기 위한 초안이다.
생성된 artifact는 기본적으로 `accepted_for_learning=false`, `human_review_status=pending` 이므로 학습 후보가 아니다.

## Drafts

| artifact_id | document_type | domain | review_status |
| --- | --- | --- | --- |
{rows}

## Reviewer Checklist

- 각 draft의 `TODO_*` 값을 실제 workflow snapshot 기준으로 채운다.
- 원본 첨부파일, base64, raw file bytes, secret, API key 값은 넣지 않는다.
- `quality_baseline.dimension_scores`와 `overall_score`는 사람이 검수한 점수로 입력한다.
- 모든 hard fail이 없어야 하며, required scans는 `pass`여야 한다.
- 승인할 때만 `learning_labels.accepted_for_learning=true`와 `human_review_status=accepted`로 바꾼다.
- training boundary 값은 별도 실행 승인 전까지 모두 `false`로 유지한다.

## Validation Commands

단일 artifact 검증:

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py \\
  {output_dir}/drafts/{artifacts[0].get('artifact_id', 'sample')}.json
```

승인 완료 후 batch 검증:

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py \\
  {jsonl_path} \\
  --require-ready \\
  --min-records {len(artifacts)}
```

승인 완료 후 batch summary 생성:

```bash
python3 scripts/summarize_report_quality_artifacts.py \\
  {jsonl_path} \\
  --batch-id {batch_id} \\
  --min-records {len(artifacts)} \\
  --output reports/report-quality/{batch_id}-manifest.json \\
  --markdown reports/report-quality/{batch_id}-summary.md
```
"""


def create_report_quality_pilot_pack(
    *,
    batch_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    sample_count: int = 3,
    tenant_id: str = "system",
    reviewer: str = "TODO_REVIEWER",
) -> dict[str, Any]:
    batch_id = batch_id.strip()
    if not batch_id:
        raise ValueError("batch_id must be non-empty")
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    if sample_count > 20:
        raise ValueError("sample_count must be 20 or fewer")

    output_dir = output_root / batch_id
    drafts_dir = output_dir / "drafts"
    template = _load_template()
    artifacts = [
        _build_artifact_draft(
            template=template,
            batch_id=batch_id,
            sample_index=index,
            tenant_id=tenant_id,
            reviewer=reviewer,
        )
        for index in range(sample_count)
    ]

    draft_paths: list[Path] = []
    for artifact in artifacts:
        path = drafts_dir / f"{artifact['artifact_id']}.json"
        _write_text_atomic(path, json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        draft_paths.append(path)

    jsonl_path = output_dir / f"{batch_id}-drafts.jsonl"
    _write_text_atomic(
        jsonl_path,
        "\n".join(json.dumps(artifact, ensure_ascii=False, sort_keys=True) for artifact in artifacts) + "\n",
    )
    index_path = output_dir / "REVIEW_INDEX.md"
    _write_text_atomic(
        index_path,
        _render_index(batch_id=batch_id, output_dir=output_dir, artifacts=artifacts, jsonl_path=jsonl_path),
    )

    return {
        "batch_id": batch_id,
        "output_dir": str(output_dir),
        "index_path": str(index_path),
        "jsonl_path": str(jsonl_path),
        "draft_paths": [str(path) for path in draft_paths],
        "sample_count": sample_count,
        "training_authorized": False,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create non-ready draft correction artifacts for a report quality pilot review batch.",
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--tenant-id", default="system")
    parser.add_argument("--reviewer", default="TODO_REVIEWER")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = create_report_quality_pilot_pack(
            batch_id=args.batch_id,
            output_root=args.output_root,
            sample_count=args.sample_count,
            tenant_id=args.tenant_id,
            reviewer=args.reviewer,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PASS report quality pilot review pack created")
        print(f"batch_id={result['batch_id']}")
        print(f"sample_count={result['sample_count']}")
        print(f"index_path={result['index_path']}")
        print(f"jsonl_path={result['jsonl_path']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

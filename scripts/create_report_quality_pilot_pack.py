#!/usr/bin/env python3
"""Create or import artifacts for a Report Quality Learning pilot review pack."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402


TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/correction_artifact_template.json"
DEFAULT_OUTPUT_ROOT = Path("reports/report-quality")
BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

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
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _validate_batch_id(batch_id: str) -> str:
    normalized = batch_id.strip()
    if not normalized:
        raise ValueError("batch_id must be non-empty")
    if not BATCH_ID_PATTERN.fullmatch(normalized):
        raise ValueError("batch_id must use only letters, numbers, '.', '_', or '-' and must not contain paths")
    return normalized


def _load_ready_source_jsonl(source_jsonl: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_path = source_jsonl.expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"source JSONL file not found: {source_path}")

    source_bytes = source_path.read_bytes()
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{source_path}: source JSONL must be UTF-8") from exc

    artifacts: list[dict[str, Any]] = []
    artifact_ids: list[str] = []
    tenant_ids: set[str] = set()
    for line_no, raw_line in enumerate(source_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source_path}: line {line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{source_path}: line {line_no}: artifact root must be an object")

        validation = validate_correction_artifact(payload)
        if not validation["ok"]:
            details = "; ".join(validation["errors"])
            raise ValueError(f"{source_path}: line {line_no}: invalid correction artifact: {details}")
        if not validation["ready_for_learning"]:
            raise ValueError(f"{source_path}: line {line_no}: artifact must be ready_for_learning")

        artifact_id = str(payload.get("artifact_id") or "").strip()
        if not ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
            raise ValueError(
                f"{source_path}: line {line_no}: artifact_id must be safe for a local filename"
            )
        tenant_id = str(payload.get("workflow_reference", {}).get("tenant_id") or "").strip()
        if not tenant_id:
            raise ValueError(f"{source_path}: line {line_no}: workflow_reference.tenant_id must be non-empty")

        artifacts.append(payload)
        artifact_ids.append(artifact_id)
        tenant_ids.add(tenant_id)

    if not 3 <= len(artifacts) <= 5:
        raise ValueError("source JSONL must contain between 3 and 5 ready artifacts")
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("source JSONL artifact_ids must be unique")
    if len(tenant_ids) != 1:
        raise ValueError("source JSONL artifacts must belong to one tenant")

    return artifacts, {
        "path": str(source_path),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "artifact_ids": artifact_ids,
        "tenant_id": next(iter(tenant_ids)),
    }


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
    source_info: dict[str, Any] | None = None,
    source_manifest_path: Path | None = None,
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
    if source_info is None:
        purpose = (
            "이 review pack은 실제 fine-tuning 전에 사람이 교정 전/후 차이와 수정 이유를 기록하기 위한 초안이다.\n"
            "생성된 artifact는 기본적으로 `accepted_for_learning=false`, `human_review_status=pending` 이므로 학습 후보가 아니다."
        )
        reviewer_checklist = """- 각 draft의 `TODO_*` 값을 실제 workflow snapshot 기준으로 채운다.
- 원본 첨부파일, base64, raw file bytes, secret, API key 값은 넣지 않는다.
- `quality_baseline.dimension_scores`와 `overall_score`는 사람이 검수한 점수로 입력한다.
- 모든 hard fail이 없어야 하며, required scans는 `pass`여야 한다.
- 승인할 때만 `learning_labels.accepted_for_learning=true`와 `human_review_status=accepted`로 바꾼다.
- training boundary 값은 별도 실행 승인 전까지 모두 `false`로 유지한다."""
        source_details = ""
    else:
        purpose = (
            "이 review pack은 Report Workflow UI에서 사람이 선택해 내보낸 ready artifact를 로컬 파일럿 검수 절차로 연결한다.\n"
            "가져온 artifact는 기존 ready 상태와 입력 순서를 보존하지만, 이 pack 자체는 dataset upload나 학습 실행을 승인하지 않는다."
        )
        reviewer_checklist = """- source manifest의 SHA-256과 artifact 순서가 원본 pilot export와 일치하는지 확인한다.
- 교정 전/후 내용, dimension rationale, score, scan 결과를 다시 검토한다.
- 추가 보완이 필요하면 review decision을 `changes_requested` 또는 `rejected`로 기록한다.
- 원본 첨부파일, base64, raw file bytes, secret, API key 값은 추가하지 않는다.
- training boundary 값은 별도 실행 승인 전까지 모두 `false`로 유지한다."""
        source_details = f"""
- source_jsonl: `{source_info['path']}`
- source_sha256: `{source_info['sha256']}`
- source_manifest: `{source_manifest_path}`
- source_tenant_id: `{source_info['tenant_id']}`"""

    return f"""# Report Quality Pilot Review Pack

- batch_id: `{batch_id}`
- generated_at: `{_now_iso()}`
- output_dir: `{output_dir}`
- draft_jsonl: `{jsonl_path}`
- training_authorized: `false`
{source_details}

## Purpose

{purpose}

## Artifacts

| artifact_id | document_type | domain | review_status |
| --- | --- | --- | --- |
{rows}

## Reviewer Checklist

{reviewer_checklist}

## Validation Commands

단일 artifact 검증:

```bash
python3 docs/specs/report_quality_learning/validate_correction_artifact.py \\
  {output_dir}/drafts/{artifacts[0].get('artifact_id', 'sample')}.json
```

승인 완료 후 batch 검증:

```bash
python3 scripts/sync_report_quality_pilot_pack.py \\
  {output_dir} \\
  --min-records {len(artifacts)} \\
  --require-ready

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
    source_jsonl: Path | None = None,
) -> dict[str, Any]:
    batch_id = _validate_batch_id(batch_id)

    output_dir = output_root / batch_id
    drafts_dir = output_dir / "drafts"
    source_info: dict[str, Any] | None = None
    if source_jsonl is not None:
        artifacts, source_info = _load_ready_source_jsonl(source_jsonl)
        sample_count = len(artifacts)
        source_mode = "exported_ready_jsonl"
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError(f"source import output directory must be empty: {output_dir}")
    else:
        if sample_count < 1:
            raise ValueError("sample_count must be at least 1")
        if sample_count > 20:
            raise ValueError("sample_count must be 20 or fewer")
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
        source_mode = "generated_drafts"

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
    source_manifest_path: Path | None = None
    if source_info is not None:
        source_manifest_path = output_dir / "SOURCE_MANIFEST.json"
        source_manifest = {
            "report_type": "report_quality_pilot_source_manifest",
            "schema_version": "decisiondoc_report_quality_pilot_source_manifest.v1",
            "generated_at": _now_iso(),
            "batch_id": batch_id,
            "source": {
                **source_info,
                "format": "jsonl",
                "artifact_count": len(artifacts),
                "order_preserved": True,
            },
            "validation": {
                "all_valid": True,
                "all_ready_for_learning": True,
                "unique_artifact_ids": True,
                "single_tenant": True,
            },
            "side_effect_boundary": {
                "reads_local_jsonl": True,
                "writes_local_review_pack": True,
                "external_dataset_upload_started": False,
                "provider_fine_tune_api_called": False,
                "provider_job_created": False,
                "training_execution_started": False,
                "model_promotion_started": False,
            },
        }
        _write_text_atomic(
            source_manifest_path,
            json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    index_path = output_dir / "REVIEW_INDEX.md"
    _write_text_atomic(
        index_path,
        _render_index(
            batch_id=batch_id,
            output_dir=output_dir,
            artifacts=artifacts,
            jsonl_path=jsonl_path,
            source_info=source_info,
            source_manifest_path=source_manifest_path,
        ),
    )

    return {
        "batch_id": batch_id,
        "source_mode": source_mode,
        "output_dir": str(output_dir),
        "index_path": str(index_path),
        "jsonl_path": str(jsonl_path),
        "source_manifest_path": str(source_manifest_path) if source_manifest_path else None,
        "draft_paths": [str(path) for path in draft_paths],
        "sample_count": sample_count,
        "ready_artifacts": sample_count if source_info is not None else 0,
        "training_authorized": False,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create draft artifacts or import a ready JSONL for a report quality pilot review batch.",
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-count", type=int, default=None)
    parser.add_argument("--tenant-id", default="system")
    parser.add_argument("--reviewer", default="TODO_REVIEWER")
    parser.add_argument(
        "--source-jsonl",
        type=Path,
        default=None,
        help="Import a UI-exported JSONL containing 3 to 5 ready artifacts.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.source_jsonl is not None and args.sample_count is not None:
            raise ValueError("--sample-count cannot be combined with --source-jsonl")
        result = create_report_quality_pilot_pack(
            batch_id=args.batch_id,
            output_root=args.output_root,
            sample_count=args.sample_count if args.sample_count is not None else 3,
            tenant_id=args.tenant_id,
            reviewer=args.reviewer,
            source_jsonl=args.source_jsonl,
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
        print(f"source_mode={result['source_mode']}")
        print(f"index_path={result['index_path']}")
        print(f"jsonl_path={result['jsonl_path']}")
        if result["source_manifest_path"]:
            print(f"source_manifest_path={result['source_manifest_path']}")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

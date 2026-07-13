#!/usr/bin/env python3
"""Build repeatable mock document samples for structural and visual review."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.bundle_catalog.registry import get_bundle_spec  # noqa: E402
from app.eval.lints import lint_docs  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.review_preview import build_review_dashboard, preview_export_bytes  # noqa: E402
from app.services.validator import validate_docs  # noqa: E402


EVIDENCE_SCHEMA_VERSION = "decisiondoc.finished_document_review.v2"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "review_samples"
DEFAULT_FORMATS = ("docx", "pdf", "pptx", "hwp")
GOLDEN_EXAMPLE_DIR = REPO_ROOT / "app" / "bundle_catalog" / "golden_examples"
EXCLUDED_EXTERNAL_ACTIONS = (
    "provider_api_execution",
    "aws_runtime_execution",
    "dataset_upload",
    "training_execution",
    "model_promotion",
    "production_service_resume",
)

SAMPLE_PAYLOADS: dict[str, dict[str, str]] = {
    "proposal_kr": {
        "title": "국토교통 통합형 서비스 발굴 경연 사업 제안서",
        "goal": "교통약자 안전 확보와 도시 운영 효율 개선을 동시에 달성할 수 있는 AI 기반 통합 서비스를 제안한다.",
        "context": (
            "발주처는 국토교통부이며, 실증 대상은 보행자 안전구역·대중교통 환승 거점이다. "
            "예산은 65억 원, 사업 기간은 24개월, 최종 산출물은 제안서·발표자료·수행계획서 패키지다."
        ),
        "constraints": (
            "개인정보 및 위치정보 보호를 충족해야 하며, 1차년도 내 시범 운영과 정량 KPI 검증을 완료해야 한다."
        ),
        "audience": "발주처 평가위원, PMO, 도시교통 실무 책임자",
    },
    "performance_plan_kr": {
        "title": "국토교통 통합형 서비스 발굴 경연 사업수행계획서",
        "goal": "보행자 안전구역·환승 거점의 교통약자 안전을 개선하는 AI 통합 플랫폼을 24개월 내 구축·검수·이관한다.",
        "context": (
            "계약 기간은 2026년 1월부터 2027년 12월까지이며, 발주처는 국토교통부다. "
            "산출물은 착수보고서, AI 설계서, 통합 테스트 결과서, 완료보고서, 운영 매뉴얼이다."
        ),
        "constraints": (
            "단계별 검수 기준과 운영 회의체를 명확히 정의해야 하고, 공공 클라우드·현장 장비 연동을 동시에 고려해야 한다."
        ),
        "audience": "발주처 감독관, 사업 PM, 품질 검수 위원",
    },
}


@contextmanager
def _local_mock_environment(data_dir: Path) -> Iterator[None]:
    overrides = {
        "DECISIONDOC_PROVIDER": "mock",
        "DECISIONDOC_PROVIDER_GENERATION": "mock",
        "DECISIONDOC_PROVIDER_ATTACHMENT": "mock",
        "DECISIONDOC_PROVIDER_VISUAL": "mock",
        "DECISIONDOC_STORAGE": "local",
        "DECISIONDOC_ENV": "dev",
        "DECISIONDOC_MAINTENANCE": "0",
        "DECISIONDOC_CACHE_ENABLED": "0",
        "DATA_DIR": str(data_dir),
        "EXPORT_DIR": str(data_dir / "exports"),
    }
    with patch.dict(os.environ, overrides, clear=False):
        os.environ.pop("DECISIONDOC_API_KEY", None)
        os.environ.pop("DECISIONDOC_API_KEYS", None)
        yield


def _reset_generated_dir(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        manifest_path = path / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"refusing to replace an unrecognized output directory: {path}") from exc
        if not isinstance(manifest.get("bundles"), dict):
            raise RuntimeError(f"refusing to replace an unrecognized output directory: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _temporary_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.tmp.{uuid4().hex}")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _temporary_path(path)
    with temporary_path.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, path)


def _write_text(path: Path, content: str) -> None:
    _write_bytes(path, content.encode("utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_evidence(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(relative_to)),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _build_generate_payload(bundle_type: str) -> dict[str, Any]:
    base = SAMPLE_PAYLOADS[bundle_type]
    return {
        "title": base["title"],
        "goal": base["goal"],
        "context": base["context"],
        "constraints": base["constraints"],
        "audience": base["audience"],
        "bundle_type": bundle_type,
    }


def _generate_bundle(client: TestClient, bundle_type: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _build_generate_payload(bundle_type)
    response = client.post("/generate", json=payload)
    if response.status_code != 200:
        raise RuntimeError(
            f"{bundle_type} generate failed with {response.status_code}: {response.text[:300]}"
        )
    body = response.json()
    docs = body.get("docs")
    if body.get("provider") != "mock" or not isinstance(docs, list) or not docs:
        raise RuntimeError(f"{bundle_type} returned an invalid mock generation response")
    return body, docs


def _stable_response_snapshot(
    *,
    bundle_type: str,
    body: dict[str, Any],
    docs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": body.get("provider"),
        "schema_version": body.get("schema_version"),
        "bundle_type": bundle_type,
        "title": body.get("title"),
        "doc_count": len(docs),
        "doc_types": [str(doc["doc_type"]) for doc in docs],
    }


def _write_markdown_docs(
    *,
    docs: list[dict[str, Any]],
    markdown_dir: Path,
    run_dir: Path,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    markdown_files: dict[str, str] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for doc in docs:
        doc_type = str(doc["doc_type"])
        markdown_path = markdown_dir / f"{doc_type}.md"
        _write_text(markdown_path, str(doc["markdown"]))
        markdown_files[doc_type] = str(markdown_path.relative_to(run_dir))
        evidence[doc_type] = _file_evidence(markdown_path, relative_to=run_dir)
    return markdown_files, evidence


def _quality_evidence(
    *,
    bundle_type: str,
    docs: list[dict[str, Any]],
    generated_files: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    validate_docs(docs)
    rendered = {str(doc["doc_type"]): str(doc["markdown"]) for doc in docs}
    bundle_spec = get_bundle_spec(bundle_type)
    lint_errors = lint_docs(
        rendered,
        lint_headings_override=bundle_spec.lint_headings_map(),
        critical_headings_override=bundle_spec.critical_non_empty_headings_map(),
    )
    golden_path = GOLDEN_EXAMPLE_DIR / f"{bundle_type}_example.md"
    if not golden_path.is_file():
        raise RuntimeError(f"canonical golden example is missing: {golden_path}")
    return {
        "validator_pass": True,
        "lint_pass": not lint_errors,
        "lint_errors": lint_errors,
        "generated_markdown": generated_files,
        "canonical_golden_example": _file_evidence(golden_path, relative_to=REPO_ROOT),
        "review_scope": "structural_validation_and_bundle_lint",
        "factual_grounding_verified": False,
        "human_visual_review_completed": False,
    }


def _export_docs(
    client: TestClient,
    *,
    title: str,
    docs: list[dict[str, Any]],
    export_format: str,
) -> bytes:
    response = client.post(
        "/generate/export-edited",
        json={"format": export_format, "title": title, "docs": docs},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"export {export_format} failed with {response.status_code}: {response.text[:300]}"
        )
    return response.content


def _ext_for_format(export_format: str) -> str:
    return {
        "docx": ".docx",
        "pdf": ".pdf",
        "pptx": ".pptx",
        "hwp": ".hwpx",
    }[export_format]


def _write_exports(
    client: TestClient,
    *,
    bundle_type: str,
    title: str,
    docs: list[dict[str, Any]],
    formats: list[str],
    bundle_dir: Path,
    run_dir: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    export_dir = bundle_dir / "exports"
    preview_dir = bundle_dir / "previews"
    exported_files: dict[str, str] = {}
    preview_files: dict[str, str] = {}
    previews: dict[str, list[str]] = {}

    for export_format in formats:
        content = _export_docs(client, title=title, docs=docs, export_format=export_format)
        export_path = export_dir / f"{bundle_type}{_ext_for_format(export_format)}"
        _write_bytes(export_path, content)
        exported_files[export_format] = str(export_path.relative_to(run_dir))
        preview_lines = preview_export_bytes(export_format, content)
        if preview_lines:
            previews[export_format] = preview_lines
            preview_path = preview_dir / f"{export_format}.txt"
            _write_text(preview_path, "\n".join(preview_lines))
            preview_files[export_format] = str(preview_path.relative_to(run_dir))
    return exported_files, preview_files, previews


def _render_quality_report(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    rows = []
    for bundle_type, bundle in manifest["bundles"].items():
        quality = bundle["quality"]
        rows.append(
            f"| `{bundle_type}` | {bundle['doc_count']} | "
            f"{'pass' if quality['validator_pass'] else 'fail'} | "
            f"{'pass' if quality['lint_pass'] else 'fail'} | "
            f"`{quality['canonical_golden_example']['sha256']}` |"
        )
    return "\n".join(
        [
            "# Bundle Quality Evidence",
            "",
            f"- generated_at: `{manifest['generated_at']}`",
            "- provider: `mock`",
            f"- status: `{manifest['status']}`",
            "",
            "## Summary",
            "",
            f"- bundles: `{summary['bundle_count']}`",
            f"- generated documents: `{summary['document_count']}`",
            f"- validator passes: `{summary['validator_pass_count']}`",
            f"- lint passes: `{summary['lint_pass_count']}`",
            "",
            "| bundle | docs | validator | bundle lint | canonical golden SHA256 |",
            "| --- | ---: | --- | --- | --- |",
            *rows,
            "",
            "## Scope And Limitations",
            "",
            "- These are deterministic fictional fixtures generated with the local mock provider.",
            "- The evidence proves schema validation and bundle-aware structural lint only.",
            "- Factual grounding and human visual review are not marked complete by this report.",
            "- No provider API, AWS runtime, dataset upload, training, model promotion, or production resume action ran.",
            "",
        ]
    )


def _validate_run_name(run_name: str | None) -> None:
    if run_name is None:
        return
    if not run_name or Path(run_name).name != run_name or run_name in {".", ".."}:
        raise ValueError("run_name must be one safe directory name")


def run(
    output_root: Path,
    bundles: list[str],
    formats: list[str],
    *,
    run_name: str | None = None,
    mirror_latest: bool = True,
) -> Path:
    """Generate local samples and write a structural quality evidence package."""
    _validate_run_name(run_name)
    generated_at = datetime.now(timezone.utc)
    directory_name = run_name or generated_at.strftime("%Y%m%d-%H%M%S")
    run_dir = output_root / directory_name
    _reset_generated_dir(run_dir)

    manifest: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": "pending",
        "generated_at": generated_at.isoformat(),
        "execution_mode": {
            "provider": "mock",
            "storage": "temporary_local",
            "fixture_kind": "fictional",
        },
        "summary": {},
        "bundles": {},
        "artifacts": {},
        "external_actions": {action: False for action in EXCLUDED_EXTERNAL_ACTIONS},
    }
    bundle_previews: dict[str, dict[str, list[str]]] = {}

    with tempfile.TemporaryDirectory(prefix="decisiondoc-finished-doc-review-") as temporary_dir:
        with _local_mock_environment(Path(temporary_dir)):
            with TestClient(create_app()) as client:
                for bundle_type in bundles:
                    body, docs = _generate_bundle(client, bundle_type)
                    payload = _build_generate_payload(bundle_type)
                    bundle_dir = run_dir / bundle_type
                    markdown_dir = bundle_dir / "markdown"

                    response_path = bundle_dir / "generate_response.json"
                    _write_json(
                        response_path,
                        _stable_response_snapshot(bundle_type=bundle_type, body=body, docs=docs),
                    )
                    markdown_files, generated_file_evidence = _write_markdown_docs(
                        docs=docs,
                        markdown_dir=markdown_dir,
                        run_dir=run_dir,
                    )
                    exported_files, preview_files, previews = _write_exports(
                        client,
                        bundle_type=bundle_type,
                        title=payload["title"],
                        docs=docs,
                        formats=formats,
                        bundle_dir=bundle_dir,
                        run_dir=run_dir,
                    )
                    quality = _quality_evidence(
                        bundle_type=bundle_type,
                        docs=docs,
                        generated_files=generated_file_evidence,
                    )
                    if not quality["lint_pass"]:
                        raise RuntimeError(f"{bundle_type} bundle lint failed: {quality['lint_errors']}")

                    bundle_previews[bundle_type] = previews
                    manifest["bundles"][bundle_type] = {
                        "title": payload["title"],
                        "request": payload,
                        "response_snapshot": _file_evidence(response_path, relative_to=run_dir),
                        "doc_count": len(docs),
                        "exports": exported_files,
                        "markdown_docs": markdown_files,
                        "preview_files": preview_files,
                        "quality": quality,
                    }

    bundle_records = list(manifest["bundles"].values())
    manifest["summary"] = {
        "bundle_count": len(bundle_records),
        "document_count": sum(int(bundle["doc_count"]) for bundle in bundle_records),
        "validator_pass_count": sum(bool(bundle["quality"]["validator_pass"]) for bundle in bundle_records),
        "lint_pass_count": sum(bool(bundle["quality"]["lint_pass"]) for bundle in bundle_records),
    }
    manifest["status"] = "passed"

    quality_report_path = run_dir / "quality_report.md"
    review_dashboard_path = run_dir / "review.html"
    _write_text(quality_report_path, _render_quality_report(manifest))
    _write_text(
        review_dashboard_path,
        build_review_dashboard(
            generated_at=manifest["generated_at"],
            manifest=manifest,
            bundle_previews=bundle_previews,
        ),
    )
    manifest["artifacts"] = {
        "quality_report": _file_evidence(quality_report_path, relative_to=run_dir),
        "review_dashboard": _file_evidence(review_dashboard_path, relative_to=run_dir),
    }
    _write_json(run_dir / "manifest.json", manifest)

    latest_dir = output_root / "latest"
    if mirror_latest and run_dir != latest_dir:
        _reset_generated_dir(latest_dir)
        shutil.copytree(run_dir, latest_dir, dirs_exist_ok=True)
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build finished-document review samples.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root output directory for generated review samples.",
    )
    parser.add_argument(
        "--bundles",
        default="proposal_kr,performance_plan_kr",
        help="Comma-separated bundle ids to generate.",
    )
    parser.add_argument(
        "--formats",
        default=",".join(DEFAULT_FORMATS),
        help="Comma-separated export formats (docx,pdf,pptx,hwp). Use an empty value for Markdown only.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Use one stable output directory name instead of a timestamp.",
    )
    parser.add_argument(
        "--no-latest",
        action="store_true",
        help="Do not mirror the generated package to output-dir/latest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundles = [item.strip() for item in str(args.bundles).split(",") if item.strip()]
    formats = [item.strip() for item in str(args.formats).split(",") if item.strip()]

    if not bundles:
        raise SystemExit("At least one bundle is required.")
    unsupported_bundles = [item for item in bundles if item not in SAMPLE_PAYLOADS]
    if unsupported_bundles:
        raise SystemExit(f"Unsupported sample bundles: {', '.join(unsupported_bundles)}")
    unsupported_formats = [item for item in formats if item not in DEFAULT_FORMATS]
    if unsupported_formats:
        raise SystemExit(f"Unsupported export formats: {', '.join(unsupported_formats)}")

    run_dir = run(
        args.output_dir,
        bundles,
        formats,
        run_name=args.run_name,
        mirror_latest=not args.no_latest,
    )
    print(f"review samples written to {run_dir}")
    if not args.no_latest and run_dir.name != "latest":
        print(f"latest review samples mirrored at {args.output_dir / 'latest'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

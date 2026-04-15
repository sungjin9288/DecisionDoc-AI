#!/usr/bin/env python3
"""Generate repeatable finished-document review samples for key bundles.

This script uses the local FastAPI app with the mock provider to generate
submission-ready sample outputs and exports them to DOCX/PDF/PPTX/HWPX so
document quality can be reviewed visually before live deployment.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.review_preview import build_review_dashboard, preview_export_bytes

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "review_samples"
DEFAULT_DATA_DIR = REPO_ROOT / "tmp" / "review-samples-data"
DEFAULT_FORMATS = ("docx", "pdf", "pptx", "hwp")

SAMPLE_PAYLOADS: dict[str, dict[str, str]] = {
    "proposal_kr": {
        "title": "국토교통 통합형 서비스 발굴 경연 사업 제안서",
        "goal": "교통약자 안전 확보와 도시 운영 효율 개선을 동시에 달성할 수 있는 AI 기반 통합 서비스를 제안한다.",
        "context": (
            "발주처는 국토교통부이며, 실증 대상은 교차로·스쿨존·대중교통 환승 거점이다. "
            "예산은 65억 원, 사업 기간은 24개월, 최종 산출물은 제안서·발표자료·수행계획서 패키지다."
        ),
        "constraints": (
            "개인정보 및 위치정보 보호를 충족해야 하며, 1차년도 내 시범 운영과 정량 KPI 검증을 완료해야 한다."
        ),
        "audience": "발주처 평가위원, PMO, 도시교통 실무 책임자",
    },
    "performance_plan_kr": {
        "title": "국토교통 통합형 서비스 발굴 경연 사업수행계획서",
        "goal": "교차로·스쿨존·환승 거점의 교통약자 안전을 개선하는 AI 통합 플랫폼을 24개월 내 구축·검수·이관한다.",
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


def _configure_env() -> None:
    os.environ["DECISIONDOC_PROVIDER"] = "mock"
    os.environ["DECISIONDOC_ENV"] = "dev"
    os.environ["DECISIONDOC_MAINTENANCE"] = "0"
    os.environ["DECISIONDOC_CACHE_ENABLED"] = "0"
    os.environ["DATA_DIR"] = str(DEFAULT_DATA_DIR)
    os.environ.pop("DECISIONDOC_API_KEY", None)
    os.environ.pop("DECISIONDOC_API_KEYS", None)


def _ensure_clean_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def _export_docs(
    client: TestClient,
    *,
    title: str,
    docs: list[dict[str, Any]],
    export_format: str,
) -> bytes:
    response = client.post(
        "/generate/export-edited",
        json={
            "format": export_format,
            "title": title,
            "docs": docs,
        },
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


def run(output_root: Path, bundles: list[str], formats: list[str]) -> Path:
    _configure_env()
    _reset_dir(DEFAULT_DATA_DIR)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_root / timestamp
    _ensure_clean_dir(run_dir)

    app = create_app()
    client = TestClient(app)

    manifest: dict[str, Any] = {
        "generated_at": timestamp,
        "bundles": {},
    }
    bundle_previews: dict[str, dict[str, list[str]]] = {}

    for bundle_type in bundles:
        payload = _build_generate_payload(bundle_type)
        response = client.post("/generate", json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"{bundle_type} generate failed with {response.status_code}: {response.text[:300]}"
            )
        body = response.json()
        docs = body["docs"]

        bundle_dir = run_dir / bundle_type
        markdown_dir = bundle_dir / "markdown"
        export_dir = bundle_dir / "exports"
        preview_dir = bundle_dir / "previews"
        _ensure_clean_dir(markdown_dir)
        _ensure_clean_dir(export_dir)
        _ensure_clean_dir(preview_dir)

        _write_text(bundle_dir / "generate_response.json", json.dumps(body, ensure_ascii=False, indent=2))

        markdown_files: dict[str, str] = {}
        for doc in docs:
            doc_type = str(doc["doc_type"])
            markdown_path = markdown_dir / f"{doc_type}.md"
            _write_text(markdown_path, str(doc["markdown"]))
            markdown_files[doc_type] = str(markdown_path.relative_to(run_dir))

        exported_files: dict[str, str] = {}
        preview_files: dict[str, str] = {}
        bundle_previews[bundle_type] = {}
        for export_format in formats:
            content = _export_docs(client, title=payload["title"], docs=docs, export_format=export_format)
            filename = f"{bundle_type}{_ext_for_format(export_format)}"
            export_path = export_dir / filename
            _write_bytes(export_path, content)
            exported_files[export_format] = str(export_path.relative_to(run_dir))
            preview_lines = preview_export_bytes(export_format, content)
            if preview_lines:
                bundle_previews[bundle_type][export_format] = preview_lines
                preview_path = preview_dir / f"{export_format}.txt"
                _write_text(preview_path, "\n".join(preview_lines))
                preview_files[export_format] = str(preview_path.relative_to(run_dir))

        manifest["bundles"][bundle_type] = {
            "title": payload["title"],
            "request": payload,
            "doc_count": len(docs),
            "exports": exported_files,
            "markdown_docs": markdown_files,
            "preview_files": preview_files,
        }

    _write_text(run_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    _write_text(
        run_dir / "review.html",
        build_review_dashboard(
            generated_at=timestamp,
            manifest=manifest,
            bundle_previews=bundle_previews,
        ),
    )
    latest_dir = output_root / "latest"
    if latest_dir.exists() or latest_dir.is_symlink():
        if latest_dir.is_dir() and not latest_dir.is_symlink():
            shutil.rmtree(latest_dir)
        else:
            latest_dir.unlink()
    shutil.copytree(run_dir, latest_dir)
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
        help="Comma-separated export formats (docx,pdf,pptx,hwp).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundles = [item.strip() for item in str(args.bundles).split(",") if item.strip()]
    formats = [item.strip() for item in str(args.formats).split(",") if item.strip()]

    unsupported_bundles = [item for item in bundles if item not in SAMPLE_PAYLOADS]
    if unsupported_bundles:
        raise SystemExit(f"Unsupported sample bundles: {', '.join(unsupported_bundles)}")

    unsupported_formats = [item for item in formats if item not in DEFAULT_FORMATS]
    if unsupported_formats:
        raise SystemExit(f"Unsupported export formats: {', '.join(unsupported_formats)}")

    run_dir = run(args.output_dir, bundles, formats)
    print(f"review samples written to {run_dir}")
    print(f"latest review samples mirrored at {args.output_dir / 'latest'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

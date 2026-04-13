#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert source material and run a DecisionDoc generate request.",
    )
    parser.add_argument("inputs", nargs="+", help="Input files to ingest.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("DECISIONDOC_BASE_URL", "http://localhost:8000"),
        help="DecisionDoc base URL (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("DECISIONDOC_API_KEY", ""),
        help="DecisionDoc API key. Falls back to DECISIONDOC_API_KEY.",
    )
    parser.add_argument("--title", default="", help="Override generated title.")
    parser.add_argument(
        "--goal",
        default="입력 문서를 근거로 의사결정 문서를 생성합니다.",
        help="Generation goal.",
    )
    parser.add_argument(
        "--doc-types",
        default="adr,onepager,eval_plan,ops_checklist",
        help="Comma-separated doc types.",
    )
    parser.add_argument(
        "--bundle-type",
        default="tech_decision",
        help="Bundle type for /generate requests.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/ingestion_harness",
        help="Directory for request/response artifacts.",
    )
    parser.add_argument(
        "--tenant-id",
        default="",
        help="Optional tenant header value.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--disable-pdf-endpoint",
        action="store_true",
        help="Force generic /generate flow even for a single PDF input.",
    )
    parser.add_argument(
        "--enable-markitdown-plugins",
        action="store_true",
        help="Enable MarkItDown plugins for non-text inputs.",
    )
    return parser


def _headers(api_key: str, tenant_id: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["X-DecisionDoc-Api-Key"] = api_key
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers


def _load_markitdown_converter(enable_plugins: bool):
    try:
        from markitdown import MarkItDown  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "markitdown is required for non-text inputs. "
            "Install optional deps with `pip install -r requirements-integrations.txt`."
        ) from exc
    return MarkItDown(enable_plugins=enable_plugins)


def _read_input_markdown(path: Path, *, enable_plugins: bool) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8")

    converter = _load_markitdown_converter(enable_plugins)
    result = converter.convert(str(path))
    return result.text_content


def _build_context(entries: list[tuple[Path, str]]) -> str:
    blocks: list[str] = []
    for path, markdown in entries:
        blocks.append(f"# Source: {path.name}\n\n{markdown.strip()}")
    return "\n\n---\n\n".join(blocks).strip()


def _write_artifacts(output_dir: Path, payload: dict[str, Any], response_body: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "request.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "response.json").write_text(
        json.dumps(response_body, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    docs_dir = output_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for doc in response_body.get("docs", []):
        doc_type = str(doc.get("doc_type", "unknown")).strip() or "unknown"
        markdown = str(doc.get("markdown", ""))
        (docs_dir / f"{doc_type}.md").write_text(markdown, encoding="utf-8")


def _single_pdf_mode(paths: list[Path], disable_pdf_endpoint: bool) -> bool:
    return not disable_pdf_endpoint and len(paths) == 1 and paths[0].suffix.lower() == ".pdf"


def _run_single_pdf(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    tenant_id: str,
    path: Path,
    title: str,
    goal: str,
    doc_types: str,
) -> dict[str, Any]:
    headers = _headers(api_key, tenant_id)
    with path.open("rb") as handle:
        response = client.post(
            f"{base_url}/generate/from-pdf",
            headers=headers,
            data={"doc_types": doc_types, "tenant_id": tenant_id or "default"},
            files={"file": (path.name, handle, "application/pdf")},
        )
    response.raise_for_status()
    body = response.json()
    if title or goal:
        body.setdefault("harness_notes", {})
        body["harness_notes"]["title_override_requested"] = bool(title)
        body["harness_notes"]["goal_override_requested"] = bool(goal)
    return body


def _run_generic_generate(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    tenant_id: str,
    paths: list[Path],
    title: str,
    goal: str,
    doc_types: str,
    bundle_type: str,
    enable_markitdown_plugins: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    entries = [
        (path, _read_input_markdown(path, enable_plugins=enable_markitdown_plugins))
        for path in paths
    ]
    payload = {
        "title": title or paths[0].stem,
        "goal": goal,
        "context": _build_context(entries),
        "doc_types": [item.strip() for item in doc_types.split(",") if item.strip()],
        "bundle_type": bundle_type,
    }
    response = client.post(
        f"{base_url}/generate",
        headers=_headers(api_key, tenant_id),
        json=payload,
    )
    response.raise_for_status()
    return payload, response.json()


def main() -> int:
    args = _build_parser().parse_args()
    paths = [Path(item).expanduser().resolve() for item in args.inputs]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"Missing input files: {', '.join(missing)}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(timeout=args.timeout_sec) as client:
        if _single_pdf_mode(paths, args.disable_pdf_endpoint):
            payload = {
                "mode": "generate/from-pdf",
                "input": str(paths[0]),
                "doc_types": args.doc_types,
            }
            response_body = _run_single_pdf(
                client,
                base_url=base_url,
                api_key=args.api_key,
                tenant_id=args.tenant_id,
                path=paths[0],
                title=args.title,
                goal=args.goal,
                doc_types=args.doc_types,
            )
        else:
            payload, response_body = _run_generic_generate(
                client,
                base_url=base_url,
                api_key=args.api_key,
                tenant_id=args.tenant_id,
                paths=paths,
                title=args.title,
                goal=args.goal,
                doc_types=args.doc_types,
                bundle_type=args.bundle_type,
                enable_markitdown_plugins=args.enable_markitdown_plugins,
            )

    _write_artifacts(output_dir, payload, response_body)
    print(
        json.dumps(
            {
                "bundle_id": response_body.get("bundle_id", ""),
                "request_id": response_body.get("request_id", ""),
                "output_dir": str(output_dir),
                "doc_count": len(response_body.get("docs", [])),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

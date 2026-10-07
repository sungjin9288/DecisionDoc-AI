#!/usr/bin/env python3
"""Local authoring CLI for a Claude Code or Codex session opened on this repo.

The session writes the document itself; DecisionDoc supplies the brief and
then validates, renders, stores and exports what the session wrote.

    python3 scripts/decisiondoc_author.py bundles
    python3 scripts/decisiondoc_author.py brief --bundle proposal_kr \\
        --title "..." --goal "..." --context-file notes.md --out work/doc1
    #   (the session writes work/doc1/bundle.json from work/doc1/brief.md)
    python3 scripts/decisiondoc_author.py submit --dir work/doc1 --formats docx,pptx,hwpx

The server must be running locally with an agent key, e.g.
``python3 scripts/run_free_local.py --agent-api-key``. The server never calls
a model provider on this path. See .claude/skills/decisiondoc-authoring/SKILL.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_SERVER = "http://127.0.0.1:8000"
DEFAULT_KEY_FILE = _PROJECT_ROOT / "data" / "free-local" / ".agent-api-key"
API_KEY_HEADER = "X-DecisionDoc-Api-Key"
EXIT_INVALID_BUNDLE = 2
# CLI name -> (export-edited format, file extension)
FORMATS = {
    "docx": ("docx", ".docx"),
    "pdf": ("pdf", ".pdf"),
    "pptx": ("pptx", ".pptx"),
    "hwpx": ("hwp", ".hwpx"),
    "xlsx": ("excel", ".xlsx"),
}
BRIEF_INSTRUCTIONS = """## 작성 방법

1. 아래 "생성 프롬프트"를 그대로 따라 문서 내용을 작성한다.
2. 결과는 이 폴더의 `bundle.json`에 JSON 객체 하나로 저장한다. 최상위 키는 문서 키({doc_keys})이고 구조는 `schema.json`을 따른다.
3. 근거가 없는 수치·일정·금액은 만들지 않는다. 맥락에 없는 숫자는 쓰지 말고 확인이 필요한 항목으로 적는다.
4. `python3 scripts/decisiondoc_author.py submit --dir <이 폴더>`로 제출한다. 422가 나오면 출력된 사유대로 `bundle.json`을 고쳐 다시 제출한다.
"""


def _safe_name(title: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", title).strip(" ._")
    return (name or "document")[:80]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_request(args: argparse.Namespace) -> dict[str, Any]:
    context = args.context or ""
    if args.context_file:
        file_text = Path(args.context_file).read_text(encoding="utf-8")
        context = f"{context}\n\n{file_text}".strip() if context else file_text
    request: dict[str, Any] = {"title": args.title, "goal": args.goal, "bundle_type": args.bundle}
    optional = {
        "context": context,
        "constraints": args.constraints,
        "audience": args.audience,
        "project_id": args.project_id,
        "style_profile_id": args.style_profile_id,
    }
    request.update({key: value for key, value in optional.items() if value})
    return request


def write_brief(client: Any, request: dict[str, Any], out_dir: Path) -> Path:
    response = client.post("/generate/authoring-brief", json=request)
    response.raise_for_status()
    brief = response.json()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "request.json", request)
    _write_json(out_dir / "schema.json", brief["json_schema"])
    instructions = BRIEF_INSTRUCTIONS.format(doc_keys=", ".join(brief["doc_keys"]))
    (out_dir / "brief.md").write_text(
        f"# 작성 지침: {request['title']}\n\n- 번들: `{brief['bundle_type']}`\n"
        f"- 문서 키: {', '.join(brief['doc_keys'])}\n\n{instructions}\n## 생성 프롬프트\n\n{brief['prompt']}\n",
        encoding="utf-8",
    )
    return out_dir / "brief.md"


def submit(client: Any, work_dir: Path, formats: list[str]) -> dict[str, Any]:
    """Submit bundle.json; return a summary, or raise ValueError with the server's reasons."""
    request = _load_json(work_dir / "request.json")
    bundle = _load_json(work_dir / "bundle.json")
    response = client.post("/generate/authored", json={"request": request, "bundle": bundle})
    if response.status_code == 422:
        detail = response.json().get("detail", response.json())
        raise ValueError(json.dumps(detail, ensure_ascii=False, indent=2))
    response.raise_for_status()
    result = response.json()
    _write_json(work_dir / "response.json", result)

    out_dir = work_dir / "output"
    out_dir.mkdir(exist_ok=True)
    files = []
    for doc in result["docs"]:
        path = out_dir / f"{doc['doc_type']}.md"
        path.write_text(doc["markdown"], encoding="utf-8")
        files.append(str(path))
    docs = [
        {
            "doc_type": doc["doc_type"],
            "markdown": doc["markdown"],
            "total_slides": doc.get("total_slides"),
            "slide_outline": doc.get("slide_outline") or [],
        }
        for doc in result["docs"]
    ]
    for name in formats:
        export_format, extension = FORMATS[name]
        exported = client.post(
            "/generate/export-edited",
            json={
                "bundle_id": result["bundle_id"],
                "bundle_type": request["bundle_type"],
                "title": result["title"],
                "format": export_format,
                "docs": docs,
                # Conversion only: never create visuals with a provider.
                "generate_missing_visuals": False,
            },
        )
        exported.raise_for_status()
        path = out_dir / f"{_safe_name(result['title'])}{extension}"
        path.write_bytes(exported.content)
        files.append(str(path))
    return {
        "request_id": result["request_id"],
        "bundle_id": result["bundle_id"],
        "provider": result["provider"],
        "project_document_id": result.get("project_document_id"),
        "files": files,
    }


def list_bundles() -> list[dict[str, Any]]:
    from app.bundle_catalog.registry import BUNDLE_REGISTRY

    return [
        {"id": spec.id, "name": spec.name_ko, "doc_keys": list(spec.doc_keys)}
        for spec in BUNDLE_REGISTRY.values()
    ]


def _api_key() -> str:
    key = os.environ.get("DECISIONDOC_AGENT_API_KEY", "").strip()
    if key:
        return key
    key_file = Path(os.environ.get("DECISIONDOC_AGENT_API_KEY_FILE", DEFAULT_KEY_FILE))
    if not key_file.is_file():
        raise SystemExit(
            f"agent API key not found: {key_file}. "
            "Start the server with `python3 scripts/run_free_local.py --agent-api-key`."
        )
    return key_file.read_text(encoding="utf-8").strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local authoring CLI for agent sessions.")
    parser.add_argument("--server", default=os.environ.get("DECISIONDOC_URL", DEFAULT_SERVER))
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("bundles", help="List bundle ids and their document keys.")

    brief = commands.add_parser("brief", help="Write brief.md, request.json and schema.json.")
    brief.add_argument("--bundle", required=True)
    brief.add_argument("--title", required=True)
    brief.add_argument("--goal", required=True)
    brief.add_argument("--context", default="")
    brief.add_argument("--context-file")
    brief.add_argument("--constraints", default="")
    brief.add_argument("--audience", default="")
    brief.add_argument("--project-id", default="")
    brief.add_argument("--style-profile-id", default="")
    brief.add_argument("--out", required=True, help="Work directory for this document.")

    send = commands.add_parser("submit", help="Submit bundle.json and download formats.")
    send.add_argument("--dir", required=True, help="Work directory created by brief.")
    send.add_argument("--formats", default="docx", help=f"Comma list of {', '.join(FORMATS)} or 'none'.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "bundles":
        print(json.dumps(list_bundles(), ensure_ascii=False, indent=2))
        return 0

    import httpx

    formats: list[str] = []
    if args.command == "submit" and args.formats.strip().lower() != "none":
        formats = [item.strip().lower() for item in args.formats.split(",") if item.strip()]
        unknown = sorted(set(formats) - set(FORMATS))
        if unknown:
            raise SystemExit(f"unknown format: {', '.join(unknown)}")

    with httpx.Client(base_url=args.server, headers={API_KEY_HEADER: _api_key()}, timeout=300) as client:
        if args.command == "brief":
            path = write_brief(client, _build_request(args), Path(args.out))
            print(f"brief written: {path}")
            return 0
        try:
            summary = submit(client, Path(args.dir), formats)
        except ValueError as exc:
            print(f"bundle.json was rejected:\n{exc}", file=sys.stderr)
            return EXIT_INVALID_BUNDLE
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

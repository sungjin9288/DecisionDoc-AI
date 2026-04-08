#!/usr/bin/env python3
"""Push generated decision documents to a Notion page.

Requires:
    pip install -r requirements-integrations.txt   # notion-client>=2.2.1

Environment variables:
    NOTION_API_KEY          — Notion Integration Token (required)
    NOTION_PARENT_PAGE_ID   — Default parent page ID (can also use --parent-page-id)

Usage:

    # Mode 1: Generate documents then push to Notion
    NOTION_API_KEY=secret_xxx \\
    NOTION_PARENT_PAGE_ID=xxxxxxxxxx \\
    DECISIONDOC_PROVIDER=mock \\
    python scripts/notion_push.py \\
        --title "Redis 도입 결정" \\
        --goal "세션 캐싱 성능 개선" \\
        --context "현재 동기 HTTP 호출, 피크타임 타임아웃"

    # Mode 2: Push existing markdown files from a directory
    python scripts/notion_push.py \\
        --from-dir ./docs/redis-decision \\
        --title "Redis 도입" \\
        --parent-page-id xxxxxxxxxx
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

# Ensure the project root is on sys.path so `app.*` imports work when running
# this script directly (e.g. `python scripts/notion_push.py`) without PYTHONPATH.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOC_TYPE_ORDER = ["adr", "onepager", "eval_plan", "ops_checklist"]
DOC_TYPE_LABELS = {
    "adr": "ADR (Architecture Decision Record)",
    "onepager": "One Pager",
    "eval_plan": "Evaluation Plan",
    "ops_checklist": "Operations Checklist",
}
METADATA_FILENAME = "_metadata.json"


# ---------------------------------------------------------------------------
# Markdown → Notion block conversion
# ---------------------------------------------------------------------------

def _rich_text(content: str) -> list[dict]:
    """Build a Notion rich_text array for plain text content."""
    return [{"type": "text", "text": {"content": content}}]


def _md_line_to_block(line: str) -> dict | None:
    """Convert a single markdown line to a Notion block dict.

    Returns None for blank lines (caller decides whether to skip or insert divider).

    Supported conversions:
        # text      → heading_1
        ## text     → heading_2
        ### text    → heading_3
        - text      → bulleted_list_item
        * text      → bulleted_list_item
        other       → paragraph
    """
    stripped = line.strip()
    if not stripped:
        return None

    # H1: # title (but not ## or ###)
    if stripped.startswith("# ") and not stripped.startswith("## "):
        text = stripped[2:].strip()
        return {
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": _rich_text(text)},
        }

    # H2: ## title (but not ###)
    if stripped.startswith("## ") and not stripped.startswith("### "):
        text = stripped[3:].strip()
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": _rich_text(text)},
        }

    # H3: ### title
    if stripped.startswith("### "):
        text = stripped[4:].strip()
        return {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": _rich_text(text)},
        }

    # Bulleted list: - item or * item
    if stripped.startswith("- ") or stripped.startswith("* "):
        text = stripped[2:].strip()
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich_text(text)},
        }

    # Default: paragraph
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(stripped)},
    }


def _md_to_notion_blocks(markdown: str) -> list[dict]:
    """Convert a full markdown document to a list of Notion block dicts.

    Strategy:
    - Split by newlines, convert each non-blank line via _md_line_to_block()
    - Consecutive blank lines are collapsed to a single blank (skipped)
    - Blank lines between content lines are preserved as nothing (Notion handles spacing)
    """
    blocks: list[dict] = []
    prev_blank = False

    for line in markdown.splitlines():
        block = _md_line_to_block(line)
        if block is None:
            prev_blank = True
            continue
        prev_blank = False
        blocks.append(block)

    return blocks


# ---------------------------------------------------------------------------
# Notion API helpers
# ---------------------------------------------------------------------------

def _append_blocks_chunked(
    client,
    page_id: str,
    blocks: list[dict],
    chunk_size: int = 100,
) -> None:
    """Append blocks in chunks to respect Notion API's 100-block limit."""
    for i in range(0, len(blocks), chunk_size):
        chunk = blocks[i : i + chunk_size]
        client.blocks.children.append(block_id=page_id, children=chunk)


def _create_notion_page(client, parent_page_id: str, title: str) -> str:
    """Create a new Notion page under parent_page_id. Returns the new page ID."""
    response = client.pages.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        properties={
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
    )
    return response["id"]


def _append_doc_section(client, page_id: str, doc_type: str, markdown_content: str) -> None:
    """Append a section heading + content blocks for one doc_type."""
    label = DOC_TYPE_LABELS.get(doc_type, doc_type)

    # Section divider
    divider = {"object": "block", "type": "divider", "divider": {}}
    heading = {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich_text(label)},
    }
    _append_blocks_chunked(client, page_id, [divider, heading])

    # Content blocks
    content_blocks = _md_to_notion_blocks(markdown_content)
    if content_blocks:
        _append_blocks_chunked(client, page_id, content_blocks)


def _read_output_metadata(dir_path: Path) -> dict:
    """Read optional metadata emitted by scripts/decide.py output mode."""
    meta_path = dir_path / METADATA_FILENAME
    if not meta_path.is_file():
        return {}
    try:
        import json

        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Execution modes
# ---------------------------------------------------------------------------

def _push_docs_to_notion(
    client,
    docs: list[dict],
    title: str,
    parent_page_id: str,
    provider: str = "",
) -> str:
    """Create a Notion page and push all docs as sections. Returns the page URL."""
    print(f"[notion_push] Creating Notion page: {title!r}", file=sys.stderr)
    page_id = _create_notion_page(client, parent_page_id, title)

    # Header block
    header_text = "Generated by DecisionDoc AI"
    if provider:
        header_text += f" | Provider: {provider}"
    header_block = {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": _rich_text(header_text),
            "color": "gray",
        },
    }
    _append_blocks_chunked(client, page_id, [header_block])

    # Append each doc section in canonical order
    ordered_docs = sorted(
        docs,
        key=lambda d: DOC_TYPE_ORDER.index(d["doc_type"]) if d["doc_type"] in DOC_TYPE_ORDER else 99,
    )
    for doc in ordered_docs:
        print(f"[notion_push]   Appending section: {doc['doc_type']}", file=sys.stderr)
        _append_doc_section(client, page_id, doc["doc_type"], doc["markdown"])

    # Build Notion URL from page ID
    page_url = f"https://notion.so/{page_id.replace('-', '')}"
    return page_url


def _run_generate_and_push(args: argparse.Namespace, client) -> str:
    """Mode 1: Generate documents then push to Notion. Returns Notion page URL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Run decide.py logic directly (reuse the CLI internals)
        # We import here to keep the import inside the function scope
        decide_script = Path(__file__).resolve().parent / "decide.py"
        if not decide_script.is_file():
            raise SystemExit("Error: scripts/decide.py not found. Run from project root.")

        import subprocess
        cmd = [sys.executable, str(decide_script), "--output", str(tmp_path)]
        if args.title:
            cmd += ["--title", args.title]
        if args.goal:
            cmd += ["--goal", args.goal]
        if getattr(args, "context", None):
            cmd += ["--context", args.context]
        if getattr(args, "constraints", None):
            cmd += ["--constraints", args.constraints]
        if getattr(args, "doc_types", None):
            cmd += ["--doc-types", args.doc_types]

        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            raise SystemExit("Error: Document generation failed. See output above.")

        # Read generated files
        return _run_from_dir_path(tmp_path, args.title, args.parent_page_id, client, provider="")


def _run_from_dir_path(dir_path: Path, title: str, parent_page_id: str, client, provider: str = "") -> str:
    """Read markdown files from dir_path and push to Notion. Returns page URL."""
    docs = []
    for doc_type in DOC_TYPE_ORDER:
        md_path = dir_path / f"{doc_type}.md"
        if md_path.is_file():
            docs.append({
                "doc_type": doc_type,
                "markdown": md_path.read_text(encoding="utf-8").strip(),
            })

    if not docs:
        raise SystemExit(f"Error: No markdown files found in {dir_path}")

    if not provider:
        provider = str(_read_output_metadata(dir_path).get("provider", "")).strip()

    return _push_docs_to_notion(client, docs, title, parent_page_id, provider=provider)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Push decision documents to Notion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode 1: Generate + push
    gen_group = parser.add_argument_group("Mode 1: Generate documents then push")
    gen_group.add_argument("--title", help="Decision title (page title in Notion)")
    gen_group.add_argument("--goal", help="Goal / objective")
    gen_group.add_argument("--context", default="", help="Background context (optional)")
    gen_group.add_argument("--constraints", default="", help="Constraints (optional)")
    gen_group.add_argument("--doc-types", dest="doc_types", help="Comma-separated doc types (optional)")

    # Mode 2: Push from directory
    dir_group = parser.add_argument_group("Mode 2: Push existing markdown files")
    dir_group.add_argument("--from-dir", metavar="DIR", help="Directory with {doc_type}.md files")

    # Common
    common_group = parser.add_argument_group("Common options")
    common_group.add_argument(
        "--parent-page-id",
        dest="parent_page_id",
        help="Notion parent page ID (or set NOTION_PARENT_PAGE_ID env var)",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    load_dotenv()
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Resolve Notion credentials
    notion_api_key = os.getenv("NOTION_API_KEY", "").strip()
    if not notion_api_key:
        print("Error: NOTION_API_KEY environment variable is required.", file=sys.stderr)
        return 1

    parent_page_id = args.parent_page_id or os.getenv("NOTION_PARENT_PAGE_ID", "").strip()
    if not parent_page_id:
        print(
            "Error: Notion parent page ID is required. "
            "Use --parent-page-id or set NOTION_PARENT_PAGE_ID.",
            file=sys.stderr,
        )
        return 1

    # Title is always required
    if not args.title:
        print("Error: --title is required (used as the Notion page title).", file=sys.stderr)
        return 1

    # Import notion client (requires: pip install -r requirements-integrations.txt)
    try:
        from notion_client import Client
    except ImportError:
        print(
            "Error: notion-client is not installed.\n"
            "Install it with: pip install -r requirements-integrations.txt",
            file=sys.stderr,
        )
        return 1

    client = Client(auth=notion_api_key)

    # Choose execution mode
    try:
        if args.from_dir:
            from_dir = Path(args.from_dir)
            if not from_dir.is_dir():
                print(f"Error: Directory not found: {from_dir}", file=sys.stderr)
                return 1
            page_url = _run_from_dir_path(from_dir, args.title, parent_page_id, client)
        elif args.goal:
            page_url = _run_generate_and_push(args, client)
        else:
            print(
                "Error: Specify either --goal (Mode 1: generate + push) "
                "or --from-dir (Mode 2: push existing files).",
                file=sys.stderr,
            )
            return 1
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: Notion push failed: {e}", file=sys.stderr)
        return 1

    print("\nNotion 페이지 생성 완료")
    print(f"URL: {page_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

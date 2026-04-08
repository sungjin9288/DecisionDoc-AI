#!/usr/bin/env python3
"""Format generated markdown files from a directory into a PR comment body.

Reads markdown files from the given output directory and prints a formatted
PR comment to stdout (to be piped to `gh pr comment --body-file -`).

Usage:
    python scripts/format_pr_comment.py ./decide-output
    python scripts/format_pr_comment.py ./decide-output | gh pr comment 42 --body-file -
"""
import json
import sys
from pathlib import Path

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
# Formatting
# ---------------------------------------------------------------------------

def _read_metadata(output_dir: Path) -> dict:
    """Read optional _metadata.json written by decide.py (if extended in future)."""
    meta_path = output_dir / METADATA_FILENAME
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def format_comment(output_dir: Path) -> str:
    """Build the full PR comment body from markdown files in output_dir."""
    metadata = _read_metadata(output_dir)
    provider = metadata.get("provider", "")
    bundle_id = metadata.get("bundle_id", "")

    lines: list[str] = []

    # Header
    lines.append("## 🤖 DecisionDoc AI — 자동 생성 문서")
    lines.append("")

    # Metadata line
    meta_parts = []
    if provider:
        meta_parts.append(f"Provider: **{provider}**")
    if bundle_id:
        meta_parts.append(f"Bundle: `{bundle_id[:12]}...`")
    meta_parts.append("PR body의 `<!-- decide ... -->` 마커로부터 자동 생성")

    lines.append("> " + " | ".join(meta_parts))
    lines.append("")

    # Doc sections
    found_any = False
    for doc_type in DOC_TYPE_ORDER:
        md_path = output_dir / f"{doc_type}.md"
        if not md_path.is_file():
            continue

        found_any = True
        label = DOC_TYPE_LABELS.get(doc_type, doc_type)
        content = md_path.read_text(encoding="utf-8").strip()

        lines.append(f"<details>")
        lines.append(f"<summary><b>{label}</b></summary>")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if not found_any:
        lines.append("*생성된 문서가 없습니다. 워크플로우 로그를 확인하세요.*")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        "*이 코멘트는 [DecisionDoc AI](https://github.com)에 의해 자동 생성되었습니다. "
        "내용을 검토하고 필요에 따라 수정하세요.*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: format_pr_comment.py <output-dir>", file=sys.stderr)
        return 1

    output_dir = Path(sys.argv[1])
    if not output_dir.is_dir():
        print(f"Error: Output directory not found: {output_dir}", file=sys.stderr)
        return 1

    comment = format_comment(output_dir)
    print(comment)
    return 0


if __name__ == "__main__":
    sys.exit(main())

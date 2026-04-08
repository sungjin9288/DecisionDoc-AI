#!/usr/bin/env python3
"""Parse the <!-- decide ... --> marker from a PR body.

Reads PR_BODY from the environment variable (set by GitHub Actions workflow).

Outputs:
  1. GITHUB_OUTPUT file — has_marker=true/false
  2. /tmp/decide_args.json — parsed key/value pairs (avoids shell injection)

Marker format in PR body:
    <!-- decide
    title: Redis 세션 캐싱 도입
    goal: HTTP 세션 동기화 병목 해소
    context: 현재 동기 HTTP 호출 방식
    constraints: AWS 환경, 팀 내 Redis 경험 없음
    doc_types: adr,onepager
    -->

The script exits 0 in all cases (missing marker is not an error).
"""
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER_PATTERN = re.compile(
    r"<!--\s*decide\s*\n(.*?)\n\s*-->",
    re.DOTALL | re.IGNORECASE,
)
KEY_VALUE_PATTERN = re.compile(r"^(\w+)\s*:\s*(.+)$", re.MULTILINE)

OUTPUT_JSON_PATH = Path("/tmp/decide_args.json")
SUPPORTED_KEYS = {"title", "goal", "context", "constraints", "priority", "audience", "doc_types"}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_marker(body: str) -> dict[str, str] | None:
    """Extract key:value pairs from the <!-- decide ... --> marker.

    Returns None if the marker is absent or does not contain required keys.
    """
    match = MARKER_PATTERN.search(body)
    if not match:
        return None

    block = match.group(1)
    result: dict[str, str] = {}
    for kv_match in KEY_VALUE_PATTERN.finditer(block):
        key = kv_match.group(1).strip().lower()
        value = kv_match.group(2).strip()
        if key in SUPPORTED_KEYS and value:
            result[key] = value

    return result if result else None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_github_output(data: dict[str, str]) -> None:
    """Write key=value pairs to the GITHUB_OUTPUT file (or stdout for local testing)."""
    github_output_path = os.getenv("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in data.items()]
    content = "\n".join(lines) + "\n"

    if github_output_path:
        with open(github_output_path, "a", encoding="utf-8") as f:
            f.write(content)
    else:
        # Local testing: print to stdout so developers can see the output
        print("[GITHUB_OUTPUT]")
        print(content, end="")


def _write_args_json(data: dict[str, str]) -> None:
    """Write parsed args to /tmp/decide_args.json for safe shell-injection-free passing."""
    try:
        OUTPUT_JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[parse_decide_marker] Args written to {OUTPUT_JSON_PATH}", file=sys.stderr)
    except OSError as e:
        print(f"[parse_decide_marker] Warning: Cannot write {OUTPUT_JSON_PATH}: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    pr_body = os.getenv("PR_BODY", "")

    if not pr_body.strip():
        print("[parse_decide_marker] PR_BODY is empty — no marker to parse.", file=sys.stderr)
        _write_github_output({"has_marker": "false"})
        return 0

    parsed = _parse_marker(pr_body)

    if parsed is None:
        print("[parse_decide_marker] No <!-- decide --> marker found in PR body.", file=sys.stderr)
        _write_github_output({"has_marker": "false"})
        return 0

    if not parsed.get("title") or not parsed.get("goal"):
        print(
            "[parse_decide_marker] Marker found but missing required fields: title, goal.",
            file=sys.stderr,
        )
        _write_github_output({"has_marker": "false"})
        return 0

    print(
        f"[parse_decide_marker] Marker parsed: title={parsed.get('title')!r}, goal={parsed.get('goal')!r}",
        file=sys.stderr,
    )
    _write_github_output({"has_marker": "true"})
    _write_args_json(parsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

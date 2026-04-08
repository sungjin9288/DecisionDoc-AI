#!/usr/bin/env python3
"""Summarize labeled procurement regression fixtures into JSON/Markdown reports."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "procurement"
    / "procurement_eval_regression_cases.json"
)


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fixture payload must be a list")
    return [case for case in payload if isinstance(case, dict)]


def build_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    recommendation_counts: Counter[str] = Counter()
    score_status_counts: Counter[str] = Counter()
    dimension_counts: dict[str, Counter[str]] = defaultdict(Counter)
    hard_fail_case_ids: list[str] = []
    sparse_case_ids: list[str] = []

    for case in cases:
        recommendation = str(case.get("expected_recommendation", "")).strip()
        score_status = str(case.get("expected_score_status", "")).strip()
        case_id = str(case.get("case_id", "")).strip()

        if recommendation:
            recommendation_counts[recommendation] += 1
        if score_status:
            score_status_counts[score_status] += 1
        if case.get("expected_hard_failure"):
            hard_fail_case_ids.append(case_id)

        for raw_tag in case.get("slice_tags", []) or []:
            if not isinstance(raw_tag, str) or ":" not in raw_tag:
                continue
            dimension, value = raw_tag.split(":", 1)
            dimension = dimension.strip()
            value = value.strip()
            if not dimension or not value:
                continue
            dimension_counts[dimension][value] += 1
            if dimension == "data" and value == "sparse":
                sparse_case_ids.append(case_id)

    return {
        "fixture_count": len(cases),
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "score_status_counts": dict(sorted(score_status_counts.items())),
        "slice_dimensions": {
            dimension: dict(sorted(counts.items()))
            for dimension, counts in sorted(dimension_counts.items())
        },
        "hard_fail_case_ids": sorted(case_id for case_id in hard_fail_case_ids if case_id),
        "sparse_case_ids": sorted(case_id for case_id in sparse_case_ids if case_id),
    }


def render_markdown(summary: dict[str, Any], *, fixture_path: Path) -> str:
    lines = [
        "# Procurement Eval Summary",
        "",
        f"- fixture: `{fixture_path}`",
        f"- total cases: **{summary['fixture_count']}**",
        "",
        "## Recommendation distribution",
        "",
    ]
    for key, value in summary["recommendation_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(
        [
            "",
            "## Score status distribution",
            "",
        ]
    )
    for key, value in summary["score_status_counts"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(
        [
            "",
            "## Slice coverage",
            "",
        ]
    )
    for dimension, counts in summary["slice_dimensions"].items():
        lines.append(f"### {dimension}")
        lines.append("")
        for key, value in counts.items():
            lines.append(f"- `{key}`: {value}")
        lines.append("")

    lines.extend(
        [
            "## Risk buckets",
            "",
            f"- hard fail cases: {', '.join(summary['hard_fail_case_ids']) or 'none'}",
            f"- sparse data cases: {', '.join(summary['sparse_case_ids']) or 'none'}",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_reports(*, summary: dict[str, Any], fixture_path: Path, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "procurement_eval_summary.json"
    md_path = out_dir / "procurement_eval_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(summary, fixture_path=fixture_path), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize procurement evaluation fixtures.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--out-dir", type=Path, help="When set, write JSON and Markdown reports into this directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_path = args.fixture.resolve()
    cases = load_cases(fixture_path)
    summary = build_summary(cases)

    if args.out_dir:
        json_path, md_path = write_reports(summary=summary, fixture_path=fixture_path, out_dir=args.out_dir.resolve())
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
    else:
        print(render_markdown(summary, fixture_path=fixture_path), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
